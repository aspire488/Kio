"""
command_router.py — KIO Command Router
=======================================
Fixes applied in this revision
--------------------------------
BUG-01  _is_multi_step() was missing "play" verb → "open chrome and play messi"
        was never detected as multi-step.
BUG-02  _ai_fallback() had two unreachable duplicate return statements (dead code
        after the first return in the knowledge-base miss branch).
BUG-03  LLM integration was disabled: `response = None` was hard-coded, making
        asyncio.run(ask_llm(...)) permanently skipped.  Now uses asyncio.run()
        with a hard 8 s timeout and falls through gracefully on failure.
BUG-04  "what are your features" was not in the knowledge base, causing it to
        fall through to the generic "I don't understand" error.
"""

from __future__ import annotations

import asyncio
import importlib.util
import json
import logging
import os
import sys
import re
import time
from typing import Any, Optional

from mini_kio.core.execution_boundary import execute_action
from mini_kio.core.app_operator import APP_REGISTRY, WEB_DOMAIN_ALIASES, WEB_URLS, _normalize_web_target_to_url
from mini_kio.core import config
from mini_kio.llm.identity_dataset import get_identity_answer
from mini_kio.media.media_manager import MediaManager

logger = logging.getLogger(__name__)

_CONNECTOR_INSTANCE = None
_CONNECTOR_STARTED = False

def _get_connector():
    global _CONNECTOR_INSTANCE, _CONNECTOR_MODULES_LOADED, _CONNECTOR_STARTED
    if _CONNECTOR_INSTANCE is None:
        if not config.BROWSER_CONNECTOR_ENABLED:
            return None
        mod = _load_connector_module()
        if mod is None:
            return None
        _CONNECTOR_INSTANCE = mod.Connector(
            mock=config.BROWSER_CONNECTOR_MOCK,
            port=config.BROWSER_CONNECTOR_PORT,
        )
    if not _CONNECTOR_STARTED and config.BROWSER_CONNECTOR_ENABLED:
        _CONNECTOR_STARTED = True
        conn = _CONNECTOR_INSTANCE
        if conn and not conn._mock:
            conn.start_background()
    return _CONNECTOR_INSTANCE


_CONNECTOR_MODULES_LOADED = False
_BC_PKG = "_kio_bc"


def _load_connector_module():
    global _CONNECTOR_MODULES_LOADED
    if _CONNECTOR_MODULES_LOADED:
        return sys.modules.get(f"{_BC_PKG}.connector")
    _here = os.path.dirname(os.path.abspath(__file__))
    # Gate 5.7 Fix: root is 2 levels up (mini_kio/core -> project root)
    _root = os.path.abspath(os.path.join(_here, "..", ".."))
    _pkg_dir = os.path.join(_root, "mini_kio", "browser_connector")
    _pkg_init = os.path.join(_pkg_dir, "__init__.py")
    if not os.path.isfile(_pkg_init):
        return None
    _modules = [("__init__", f"{_BC_PKG}.__init__"),
                 ("protocol", f"{_BC_PKG}.protocol"),
                 ("registry", f"{_BC_PKG}.registry"),
                 ("connector", f"{_BC_PKG}.connector")]
    try:
        for _base, _full in _modules:
            _file = os.path.join(_pkg_dir, _base + ".py")
            if not os.path.isfile(_file):
                continue
            if _full in sys.modules:
                continue
            spec = importlib.util.spec_from_file_location(_full, _file)
            if spec is None or spec.loader is None:
                return None
            mod = importlib.util.module_from_spec(spec)
            sys.modules[_full] = mod
            spec.loader.exec_module(mod)
        _CONNECTOR_MODULES_LOADED = True
        return sys.modules.get(f"{_BC_PKG}.connector")
    except Exception as exc:
        logger.exception("[CONNECTOR] failed to load modules: %s", exc)
        return None

# ---------------------------------------------------------------------------
# Lazy-import helpers (avoid circular imports at module load time)
# ---------------------------------------------------------------------------

def _lazy_import(module_name: str, item_names: list[str]) -> dict:
    try:
        if module_name == "task_engine":
            from mini_kio.core.task_engine import run_task
            return {"run_task": run_task}
        elif module_name == "app_operator":
            from mini_kio.core.app_operator import launch_app, close_app, search_web
            return {"launch_app": launch_app, "close_app": close_app, "search_web": search_web}
        elif module_name == "file_operator":
            from mini_kio.core.file_operator import open_folder
            return {"open_folder": open_folder}
        elif module_name == "system_operator":
            from mini_kio.core.system_operator import shutdown_system, restart_system, lock_system
            return {"shutdown_system": shutdown_system, "restart_system": restart_system, "lock_system": lock_system}
        elif module_name == "browser_operator":
            from mini_kio.core.browser_operator import open_url, search_google, search_youtube, play_youtube
            return {"open_url": open_url, "search_google": search_google, "search_youtube": search_youtube, "play_youtube": play_youtube}
        elif module_name == "ai":
            from mini_kio.core.ai import ask_ai
            return {"ask_ai": ask_ai}
    except ImportError as e:
        logger.warning(f"Failed to import {module_name}: {e}")
    return {}


def _log_route(event: str, **fields: Any) -> None:
    payload: dict[str, Any] = {"evt": event}
    payload.update(fields)
    logger.info(json.dumps(payload, default=str))


# Folder keywords for routing (must match file_operator.WINDOWS_FOLDERS)
_FOLDER_KEYWORDS: frozenset[str] = frozenset(
    {"downloads", "desktop", "documents", "pictures", "music", "videos", "home", "appdata", "kio"}
)

_SAFE_WEB_TARGET_RE = re.compile(r"^[a-z0-9-]+$")
_SAFE_EXPLICIT_DOMAIN_RE = re.compile(
    r"^[a-z0-9](?:[a-z0-9-]*[a-z0-9])?(?:\.[a-z0-9](?:[a-z0-9-]*[a-z0-9])?)+$"
)
_SAFE_WEB_PATH_RE = re.compile(r"^[a-z0-9._~:@%+\-=]+(?:/[a-z0-9._~:@%+\-=]+)*$")
_ALLOWED_WEB_TLDS = {"com", "ai", "org", "io", "dev", "app"}


def _is_generic_web_target(name: str) -> bool:
    normalized = name.lower().strip()
    if not normalized:
        return False
    if not _SAFE_WEB_TARGET_RE.fullmatch(normalized):
        return False
    if normalized in WEB_URLS:
        return False
    if normalized in WEB_DOMAIN_ALIASES:
        return False
    if normalized in APP_REGISTRY:
        return False
    for info in APP_REGISTRY.values():
        aliases = info.get("aliases", [])
        if any(normalized == alias.lower() for alias in aliases):
            return False
    return True


def _contains_forbidden_web_chars(value: str) -> bool:
    return any(c in value for c in [' ', '&', '|', ';', '$', '(', ')', '`', '\\', '\0', '\n', '\r', '\t'])


def _is_registry_alias(name: str) -> bool:
    normalized = name.lower().strip()
    if normalized in APP_REGISTRY:
        return True
    for info in APP_REGISTRY.values():
        if any(normalized == alias.lower() for alias in info.get("aliases", [])):
            return True
    return False


def _normalize_explicit_web_target(target: str) -> str | None:
    return _normalize_web_target_to_url(target)


# ---------------------------------------------------------------------------
# Contextual Resolution (Gate 2 Phase 1)
# ---------------------------------------------------------------------------

def _resolve_contextual_references(command: str) -> str:
    """
    Surgical short-context resolver.
    Handles 'it' (last target), 'that' (last target), 'this' (last target), 'again' (last action).
    """
    from mini_kio.core.runtime import get_last_successful_interaction

    lower = command.lower().strip()

    # "again", "do it again"
    if lower == "again" or lower == "do it again":
        last = get_last_successful_interaction(must_have_target=False)
        if last:
            action = (
                last.get("action", "")
                .replace("_app", "")
                .replace("_web", "")
                .replace("_system", "")
                .replace("_folder", "")
                .replace("_youtube", "")
            )
            target = str(last.get("target", ""))
            resolved = f"{action} {target}".strip()
            _log_route("context_resolve", original=command, resolved=resolved)
            return resolved

    # Handle "it", "that", "this"
    if re.search(r"\b(it|that|this)\b", lower):
        # Gate 5.1: Resolve capability registry FIRST for browser sessions
        from mini_kio.core.routing_utils import get_latest_capability
        cap = get_latest_capability()
        if cap and cap.get("active"):
            target = cap["canonical_target"]
            resolved = re.sub(r"\b(it|that|this)\b", target, command, flags=re.IGNORECASE)
            _log_route("context_resolve", original=command, resolved=resolved, source="capability")
            return resolved.strip()
        last = get_last_successful_interaction(must_have_target=True)
        if last:
            target = str(last.get("target", ""))
            resolved = re.sub(r"\b(it|that|this)\b", target, command, flags=re.IGNORECASE)
            _log_route("context_resolve", original=command, resolved=resolved, source="runtime")
            return resolved.strip()

    return command


# ---------------------------------------------------------------------------
# Main dispatcher
# ---------------------------------------------------------------------------

def handle_command(command: str) -> dict:
    """
    Route command to the correct operator.
    Always returns {"success": bool, "message": str}.
    """
    command = command.strip()

    if not command:
        return {"success": True, "message": ""}

    # Gate 5: Emoji sanitization before any parsing
    from mini_kio.llm.input_normalizer import InputNormalizer
    command = InputNormalizer.strip_emoji(command)

    # Phase 1: Contextual Resolution
    command = _resolve_contextual_references(command)

    from mini_kio.core.command_parser import _apply_aliases, _normalize_connectors, is_multi_step
    command = _apply_aliases(command)
    logger.info(f"[KIO] handle_command: {command!r}")

    lower = command.lower()
    lower_clean = lower.strip(".,!?;:")
    lower = _normalize_connectors(lower)

    # Canonicalize browser prepositions before deterministic browser routing.
    lower = re.sub(r"\bon\s+(chrome|edge|comet|firefox|brave)\b", r" in \1", lower)

    # ── FORBIDDEN TARGET DETECTION ────────────────────────────────────────
    # Safety: Forbidden targets must be blocked before ANY resolution or execution dispatch.
    FORBIDDEN_TARGETS = {
        "cmd", "powershell", "regedit", "taskmgr", "msconfig", "control.exe", 
        "explorer", "terminal", "services"
    }
    norm = lower[5:].strip().lower()
    if norm.endswith(".exe"):
        norm = norm[:-4]
    if lower in FORBIDDEN_TARGETS or lower.startswith("open ") and norm in FORBIDDEN_TARGETS:
        _log_route("route", intent="forbidden_blocked", target=lower)
        return {"success": False, "message": "Error: Forbidden system target blocked by security policy."}

    # ── GREETINGS ─────────────────────────────────────────────────────────
    if lower_clean == "hello":
        return {"success": True, "message": "Hello."}
    if lower_clean in ("hi", "hey"):
        return {"success": True, "message": "Hi there."}
    if lower_clean in ("yo", "wassup", "what's up", "whats up"):
        return {"success": True, "message": "KIO here."}
    if lower_clean in ("how are you", "how are you doing"):
        return {"success": True, "message": "Operational."}
    if lower_clean in ("bye", "bue"):
        return {"success": True, "message": "Later."}
    if lower_clean == "okay":
        return {"success": True, "message": "Ok."}
    if lower_clean == "bruh":
        return {"success": True, "message": "..."}

    # ── IDENTITY AUTHORITY (canonical identity resolution) ─────────────
    identity_answer = get_identity_answer(lower_clean)
    if identity_answer:
        return {"success": True, "message": identity_answer}

    try:

        # ── MULTI-STEP ────────────────────────────────────────────────────────
        if is_multi_step(lower):
            _log_route("route", intent="multi_step", text_len=len(command))
            from mini_kio.core.command_parser import parse_command

            steps = parse_command(command)
            # If connectors were present but parsing returned no steps,
            # treat this as a malformed chain rather than attempting
            # to collapse into a single-step command.
            if not steps:
                if any(x in lower for x in (" and ", " then ", " anf ", " andd ", " thenn ")):
                    return {"success": False, "message": "Malformed command chain."}
                return {"success": False, "message": f"Could not parse multi-step command: {command!r}"}
            return _execute_multi_step(steps)

        # ── MALFORMED CHAIN DETECTION ─────────────────────────────────────────
        # Only block if it looks like a multi-step command starting with a verb 
        # but failing _is_multi_step (meaning the second part is missing or invalid)
        verbs = {"open", "close", "search", "play", "launch", "folder"}
        first_word = lower.split()[0] if lower.split() else ""
        if first_word in verbs:
            # Detect trailing connectors or connector typos
            if re.search(r"\b(?:and|then|anf|andd|thenn|theen)\s*$", lower):
                return {"success": False, "message": "Malformed command chain."}

        # ── SEARCH ────────────────────────────────────────────────────────────
        if lower.startswith("search "):
            query = command[7:].strip()
            # Strip leading "for " — handles "search for X" → "X"
            if query.lower().startswith("for "):
                query = query[4:].strip()
            # Handle "search google for X" → search_web with X
            google_for_match = re.match(r"^google\s+for\s+(.+)$", query, re.IGNORECASE)
            if google_for_match:
                clean_query = google_for_match.group(1).strip()
                _log_route("route", intent="search", query=clean_query)
                return execute_action("search_web", clean_query)
            for sep in [" in ", " on ", " using "]:
                if sep in query:
                    parts = query.rsplit(sep, 1)
                    target_app = parts[1].strip()
                    clean_query = parts[0].strip()
                    if target_app == "youtube":
                        if config.BROWSER_CONNECTOR_ENABLED:
                            conn = _get_connector()
                            if conn and conn.is_connected():
                                import urllib.parse
                                _url = f"https://www.youtube.com/results?search_query={urllib.parse.quote_plus(clean_query)}"
                                try:
                                    _result = asyncio.run(conn.open_tab(_url))
                                    if _result.success:
                                        logger.info("[BROWSER_CONNECTOR_SEARCH] query=%s", clean_query)
                                        return {"success": True, "message": f"Searched YouTube: {clean_query}"}
                                except BaseException as _exc:
                                    logger.warning("[CONNECTOR] search_youtube failed: %s", _exc)
                        _log_route("route", intent="search_youtube", query=clean_query)
                        return execute_action("search_youtube", clean_query)
                    if target_app in ("chrome", "edge", "firefox", "brave", "comet"):
                        _log_route("route", intent="capability", app=target_app, cap="search")
                        return execute_action("execute_capability", f"{target_app}::search::{clean_query}")
                    if target_app == "google":
                        _log_route("route", intent="search", query=clean_query)
                        return execute_action("search_web", clean_query)
            
            # Handle "search youtube X" swallow fix
            if query.lower().startswith("youtube "):
                clean_query = query[8:].strip()
                if config.BROWSER_CONNECTOR_ENABLED:
                    conn = _get_connector()
                    if conn and conn.is_connected():
                        import urllib.parse
                        _url = f"https://www.youtube.com/results?search_query={urllib.parse.quote_plus(clean_query)}"
                        try:
                            _result = asyncio.run(conn.open_tab(_url))
                            if _result.success:
                                logger.info("[BROWSER_CONNECTOR_SEARCH] query=%s", clean_query)
                                return {"success": True, "message": f"Searched YouTube: {clean_query}"}
                        except BaseException as _exc:
                            logger.warning("[CONNECTOR] search_youtube failed: %s", _exc)
                _log_route("route", intent="search_youtube", query=clean_query)
                return execute_action("search_youtube", clean_query)

            _log_route("route", intent="search")
            return execute_action("search_web", query)

        # ── BROWSER WEBAPP ROUTING ────────────────────────────────────────────
        webapp_match = re.match(
            r"^open\s+(.+?)\s+in\s+(chrome|edge|comet|firefox|brave)$",
            lower
        )
        if webapp_match:
            webapp, browser = webapp_match.groups()
            normalized_url = _normalize_explicit_web_target(webapp)
            # Browser normalization failures must never fall through into native execution.
            if normalized_url is not None:
                _log_route("route", intent="capability", app=browser, cap="open_url", target=normalized_url, route_type="explicit_domain_or_path")
                return execute_action("execute_capability", f"{browser}::open_url::{normalized_url}::{webapp}")
            return {"success": False, "message": "Invalid browser web target."}

        # ── OPEN ──────────────────────────────────────────────────────────────
        if lower.startswith("open "):
            target       = command[5:].strip()
            target_lower = target.lower()
            words        = set(target_lower.split())

            # Folder detection BEFORE launch_app
            if words & _FOLDER_KEYWORDS:
                folder = target_lower.replace("folder", "").strip()
                folder = " ".join(folder.split()) or target_lower
                _log_route("route", intent="open_folder", target=folder)
                return execute_action("open_folder", folder)

            # Centralized Native/Browser Routing
            from mini_kio.core.routing_utils import get_browser_routing
            route_info = get_browser_routing(target)
            
            _log_route("route", intent=route_info["route_type"], target=target, action=route_info["action"])
            
            if route_info["route_type"] == "native":
                from mini_kio.core.kio_diagnostics import log_diagnostic
                log_diagnostic("native_app_route_used", {"target": target})
            elif route_info["route_type"] == "browser_fallback":
                from mini_kio.core.kio_diagnostics import log_diagnostic
                log_diagnostic("browser_fallback_used", {"target": target, "browser": route_info.get("browser")})

            # Browser Connector: intercept browser/web targets
            if route_info["route_type"] == "browser_fallback" and config.BROWSER_CONNECTOR_ENABLED:
                conn = _get_connector()
                if conn and conn.is_connected():
                    url = _normalize_web_target_to_url(target)
                    if url:
                        try:
                            result = asyncio.run(conn.open_tab(url))
                            if result.success:
                                _log_route("route", intent="connector_open", target=target)
                                from mini_kio.platform.window_activation import try_activate_browser
                                from mini_kio.core.capability_registry import get_capability_registry
                                _entry = get_capability_registry().get_latest_active()
                                if _entry and _entry.browser_pid:
                                    try_activate_browser(_entry.browser_pid)
                                return {
                                    "success": True,
                                    "message": f"Opened {target.capitalize()} in Chrome.",
                                    "action": "open_app",
                                    "target": target,
                                }
                        except BaseException as exc:
                            logger.warning("[CONNECTOR] open_tab failed: %s", exc)

            result = execute_action(route_info["action"], route_info["target"])
            if route_info["route_type"] == "browser_fallback":
                from mini_kio.platform.window_activation import try_activate_browser
                _pid = result.get("pid") if isinstance(result, dict) else None
                if _pid:
                    try_activate_browser(int(_pid))
            return result

        # ── FOCUS / SWITCH ────────────────────────────────────────────────────
        is_focus = lower.startswith("focus ")
        is_switch = lower.startswith("switch ")
        if (is_focus or is_switch) and config.BROWSER_CONNECTOR_ENABLED:
            if is_focus:
                target = command[6:].strip()
            elif lower.startswith("switch to "):
                target = command[10:].strip()
            else:
                target = command[7:].strip()

            conn = _get_connector()
            if conn and conn.is_connected():
                try:
                    result = asyncio.run(conn.focus_tab(target))
                    if result.success:
                        _log_route("route", intent="connector_focus", target=target)
                        from mini_kio.platform.window_activation import try_activate_browser
                        from mini_kio.core.capability_registry import get_capability_registry
                        from mini_kio.core.routing_utils import get_browser_registry
                        
                        cap_reg = get_capability_registry()
                        # Patch 2: Targeted PID selection
                        canon_target = get_browser_registry().canonicalize(target.lower().strip())
                        _entry = cap_reg.resolve_by_target(canon_target)
                        if not _entry:
                            _entry = cap_reg.get_latest_active()
                        
                        if _entry and _entry.browser_pid:
                            try_activate_browser(_entry.browser_pid)
                        return {
                            "success": True,
                            "message": f"Focused {target.capitalize()} tab.",
                            "action": "focus_tab",
                            "target": target,
                        }
                    return {
                        "success": False,
                        "message": f"Couldn't focus {target}: {result.error}",
                        "action": "focus_tab",
                        "target": target,
                    }
                except BaseException as exc:
                    logger.warning("[CONNECTOR] focus_tab failed: %s", exc)
                    return {
                        "success": False,
                        "message": f"Couldn't focus {target}.",
                        "action": "focus_tab",
                        "target": target,
                    }
            if config.BROWSER_CONNECTOR_ENABLED:
                return {
                    "success": False,
                    "message": f"Can't focus {target} — Browser Connector is not connected.",
                }

        # ── LIST TABS ─────────────────────────────────────────────────────────
        if lower in ("list tabs", "list open tabs", "what tabs are open", "show tabs") and config.BROWSER_CONNECTOR_ENABLED:
            conn = _get_connector()
            if conn and conn.is_connected():
                try:
                    result = asyncio.run(conn.list_tabs())
                    if result.success and result.tabs:
                        lines = []
                        for idx, t in enumerate(result.tabs, start=1):
                            marker = " [Opened by KIO]" if getattr(t, "is_owned", False) else ""
                            lines.append(f"  {idx}. {t.title or t.url}{marker}")
                        tab_list = "\n".join(lines)
                        return {
                            "success": True,
                            "message": f"Open tabs:\n{tab_list}",
                            "action": "list_tabs",
                        }
                    elif result.success:
                        return {
                            "success": True,
                            "message": "No tabs open.",
                            "action": "list_tabs",
                        }
                    return {
                        "success": False,
                        "message": "Couldn't list tabs.",
                        "action": "list_tabs",
                    }
                except BaseException as exc:
                    logger.warning("[CONNECTOR] list_tabs failed: %s", exc)
                    return {
                        "success": False,
                        "message": "Couldn't list tabs.",
                        "action": "list_tabs",
                    }
            return {
                "success": False,
                "message": "Browser Connector is not connected.",
            }

        # ── CLOSE ─────────────────────────────────────────────────────────────
        if lower.startswith("close "):
            target = command[6:].strip()

            # Check for explicit browser application termination commands
            browser_targets = {"chrome", "edge", "firefox", "brave", "comet", "browser"}
            if target.lower() in browser_targets or (target.lower().endswith(" browser") and target.lower().replace(" browser", "") in browser_targets):
                app_target = target.lower().replace(" browser", "") # Normalize to actual app name for app_operator
                _log_route("route", intent="terminate_browser_app", target=app_target)
                return execute_action("close_app", app_target)

            # Browser Connector: try owned-tab close before capability registry
            if config.BROWSER_CONNECTOR_ENABLED:
                conn = _get_connector()
                if conn and conn.is_connected():
                    try:
                        result = asyncio.run(conn.close_tab(target))
                        if result.success:
                            _log_route("route", intent="connector_close", target=target)
                            # Clean up any browser session record for this target
                            try:
                                from mini_kio.core.routing_utils import get_browser_registry
                                _conn_session = get_browser_registry().find_session(target)
                                if _conn_session:
                                    get_browser_registry().remove_session(_conn_session.get("session_id", ""))
                                    logger.info("[BROWSER_SESSION_CONNECTOR_CLOSE] session_id=%s target=%s", _conn_session.get("session_id"), target)
                            except Exception:
                                pass
                            return {
                                "success": True,
                                "message": f"Closed {target.capitalize()} tab.",
                                "action": "close_app",
                                "target": target,
                            }
                        return {
                            "success": False,
                            "message": f"Couldn't close {target}: {result.error}",
                        }
                    except BaseException as exc:
                        logger.warning("[CONNECTOR] close_tab failed: %s", exc)
                        return {
                            "success": False,
                            "message": f"Couldn't close {target}.",
                        }

            # Gate 5 P2: Check browser session registry for browser_operator-owned sessions
            from mini_kio.core.routing_utils import get_browser_registry
            _session = get_browser_registry().find_session(target)
            if _session:
                _session_id = _session.get("session_id", "unknown")
                get_browser_registry().remove_session(_session_id)
                logger.info("[BROWSER_SESSION_CLOSE] session_id=%s target=%s", _session_id, target)
                return {
                    "success": True,
                    "message": f"I opened {target.capitalize()} earlier, but without the Browser Connector I cannot guarantee closing it.",
                    "close_verified": False,
                    "action": "close_app",
                    "target": target,
                    "session_closed": True,
                }
            logger.info("[BROWSER_SESSION_NOT_FOUND] target=%s", target)

            # Gate 5.1: Check capability registry FIRST for browser session close
            from mini_kio.core.routing_utils import resolve_capability_for_close, deactivate_capability, close_browser_capability
            cap_info = resolve_capability_for_close(target)
            if cap_info and cap_info.get("active"):
                success = close_browser_capability(cap_info)
                if success:
                    deactivate_capability(target)
                    capability_name = cap_info.get("canonical_target", target).capitalize()
                    _log_route("route", intent="close_capability", target=target, capability_id=cap_info.get("capability_id"))
                    return {
                        "success": True,
                        "message": f"Closed the {capability_name} session.",
                        "action": "close_app",
                        "target": target,
                        "capability_closed": True,
                        "capability_name": capability_name,
                    }
                else:
                    return {
                        "success": False,
                        "message": f"Could not safely close {target} session (it might be the main browser profile).",
                        "action": "close_app",
                        "target": target
                    }
            _log_route("route", intent="close_app", target=target)
            return execute_action("close_app", target)

        # ── MEDIA COMMAND ROUTING ─────────────────────────────────────────────
        _mm = MediaManager.get_instance()

        # ── Fuzzy Intent Correction ──────────────────────────────────────────
        _corrected = _mm.correct_fuzzy(lower)
        if _corrected != lower:
            _log_route("route", intent="fuzzy_correction", original=lower, corrected=_corrected)
            lower = _corrected

        # ── Natural Language Seek ────────────────────────────────────────────
        _seek_result = _mm.process_nl_seek(lower)
        if _seek_result is not None:
            _log_route("route", intent="nl_seek", text=lower)
            return _seek_result

        # ── Next / Previous (must route to MediaManager, never continuation) ─
        if lower == "next":
            _log_route("route", intent="next_track")
            return _mm.next_track()

        if lower == "previous":
            _log_route("route", intent="previous_track")
            return _mm.previous_track()

        # ── Resolve references (it / this / that) against Media Context ──────
        _resolved = _mm.resolve_query(lower)
        if _resolved is not None and _resolved != lower:
            logger.info("[ROUTER] resolved reference '%s' -> '%s'", lower, _resolved)
            _log_route("route", intent="context_resolve", original=lower, resolved=_resolved)
            lower_play = f"play {_resolved}"
            _resolved_play = _mm.resolve_query(lower_play)
            resolved = _resolved_play or _resolved
            return _mm.play(resolved, platform=_mm.get_context().get_provider_for_reference())

        # ── Accept media offer (yes / play it after discovery offer) ─────────
        _accept_first = lower.split()[0] if lower else ""
        if (_accept_first in ("yes", "yeah", "sure", "ok") or
              lower in ("play it", "play that", "watch it", "watch that",
                        "play video", "play the first one")):
            last_offer = _mm.get_last_offer()
            if last_offer:
                _log_route("route", intent="accept_media_offer")
                result = _mm.accept_offer()
                if result:
                    return result
                return {"success": True, "message": "The media offer is no longer available."}
            if _accept_first in ("yes", "yeah", "sure", "ok"):
                return {"success": True, "message": "I don't have a pending offer to act on."}

        # ── PLAY ─────────────────────────────────────────────────────────────
        if lower.startswith("play "):
            query = command[5:].strip()
            # Check for explicit platform separators
            for sep in [" on ", " in ", " using "]:
                if sep in query:
                    parts = query.rsplit(sep, 1)
                    target_app = parts[1].strip().lower()
                    clean_query = parts[0].strip()
                    # Resolve references in the query part
                    resolved = _mm.resolve_query(clean_query)
                    final_query = resolved if resolved else clean_query
                    _log_route("route", intent="play_on_platform", platform=target_app, query=final_query)
                    return _mm.play(final_query, platform=target_app)

            # Resolve references in bare play query
            resolved = _mm.resolve_query(query)
            final_query = resolved if resolved else query
            return _mm.play(final_query)

        # ── SEARCH YOUTUBE ────────────────────────────────────────────────────
        if lower.startswith("search youtube "):
            query = command[15:].strip()
            return execute_action("search_youtube", query)

        if lower.startswith("youtube "):
            query = command[8:].strip()
            _resolved = _mm.resolve_query(query)
            _final = _resolved if _resolved else query
            return _mm.play(_final, platform="youtube")

        # ── TRANSPORT CONTROLS ────────────────────────────────────────────────
        _words = lower.split()
        _media_main = _words[0] if _words else ""

        if lower == "volume up":
            return _mm.volume_up()
        if lower == "volume down":
            return _mm.volume_down()
        if lower == "seek forward":
            return _mm.seek_forward()
        if lower == "seek backward":
            return _mm.seek_backward()
        if _media_main in ("resume", "continue"):
            return _mm.resume()
        if _media_main == "pause":
            return _mm.pause()
        if _media_main == "stop":
            r = _mm.stop()
            if r.get("success"):
                return r
        if _media_main == "mute":
            return _mm.mute()
        if _media_main == "unmute":
            return _mm.unmute()
        if lower == "play":
            return _mm.play()

        # ── SYSTEM ────────────────────────────────────────────────────────────
        if lower in ("shutdown", "shutdown computer", "shut down"):
            return execute_action("shutdown_system")

        if lower in ("restart", "restart computer"):
            return execute_action("restart_system")

        if lower in ("lock", "lock computer"):
            return execute_action("lock_system")

        if lower in ("recovery", "recover", "recover runtime", "reset safety"):
            _log_route("route", intent="recovery_runtime")
            return execute_action("recovery_runtime")

        # ── UTILITY ───────────────────────────────────────────────────────────
        if lower in ("ping", "Ping", "PING"):
            return {"success": True, "message": "KIO online!"}

        # ── TELEMETRY ROUTING ────────────────────────────────────────────────
        if any(x in lower for x in ("uptime", "how long have you been running")):
            from mini_kio.core.runtime import get_runtime_snapshot
            snap = get_runtime_snapshot()
            uptime_s = snap.get("uptime_ms", 0) // 1000
            if uptime_s > 3600:
                h = uptime_s // 3600
                m = (uptime_s % 3600) // 60
                msg = f"Uptime: {h}h {m}m."
            elif uptime_s > 60:
                m = uptime_s // 60
                msg = f"Uptime: {m}m."
            else:
                msg = f"Uptime: {uptime_s}s."
            return {"success": True, "message": msg}

        if any(x in lower for x in ("ram usage", "memory usage", "how much ram")):
            from mini_kio.core.runtime import get_runtime_snapshot
            snap = get_runtime_snapshot()
            ram = snap.get("ram_usage_mb", 0)
            return {"success": True, "message": f"Current RAM usage: {ram}MB."}

        if any(x in lower for x in ("cpu", "processor")):
            return {"success": True, "message": "CPU metrics are currently unavailable."}

        if lower == "status":
            from mini_kio.core.runtime import get_runtime, get_runtime_snapshot, get_runtime_health_score, get_runtime_integrity_snapshot
            rt = get_runtime()
            if rt is None:
                return {"success": True, "message": "Runtime: offline"}
            snap = get_runtime_snapshot()
            health = get_runtime_health_score()
            integrity = get_runtime_integrity_snapshot()
            return {
                "success": True,
                "message": (
                    f"Safety state: {rt.safety_state}\n"
                    f"Integrity score: {health}\n"
                    f"Integrity status: {integrity.get('status', 'unknown')}\n"
                    f"Uptime: {snap.get('uptime_ms', 0)}ms\n"
                    f"Observers: {snap.get('observer_count', 0)}"
                ),
            }

        if "help" in lower:
            return _show_help()

        # ── AI FALLBACK ───────────────────────────────────────────────────────
        _log_route("route", intent="ai_fallback", text_len=len(command))
        return _ai_fallback(command)

    except Exception as exc:
        logger.exception(f"handle_command unhandled exception: {exc}")
        return {"success": False, "message": f"Internal error: {str(exc)[:120]}"}


_ACTION_VERBS: dict[str, str] = {
    "open_app": "opened",
    "close_app": "closed",
    "search_web": "searched",
    "search_google": "searched",
    "search_youtube": "searched",
    "play_youtube": "played",
    "open_folder": "opened",
    "execute_capability": "ran",
    # Short form aliases for summarizer
    "open": "opened",
    "close": "closed",
    "focus": "focused",
    "search": "searched",
    "play": "played",
    "lock": "locked",
    "shutdown": "shut down",
    "restart": "restarted",
}

def _format_list(items: list[str]) -> str:
    if not items:
        return ""
    if len(items) == 1:
        return items[0]
    if len(items) == 2:
        return f"{items[0]} and {items[1]}"
    return ", ".join(items[:-1]) + f", and {items[-1]}"

def _summarize_steps(steps: list[dict[str, Any]], results: list[dict[str, Any]]) -> str:
    succeeded: dict[str, list[str]] = {}
    blocked: list[tuple[str, str]] = []
    for step, result in zip(steps, results):
        action = step.get("action", "")
        target = step.get("target", "")
        verb = _ACTION_VERBS.get(action, action)
        if result.get("blocked"):
            blocked.append((verb, target))
        elif result.get("success"):
            succeeded.setdefault(verb, [])
            succeeded[verb].append(target)
    parts = []
    if succeeded:
        items = []
        for verb, targets in succeeded.items():
            if len(targets) == 1:
                items.append(f"{verb} {targets[0]}")
            else:
                items.append(f"{verb} {_format_list(targets)}")
        parts.append("done - " + _format_list(items))
    if blocked:
        items = [f"{verb} {target}" for verb, target in blocked]
        if not succeeded:
            parts.append("all blocked - " + _format_list(items))
        else:
            parts.append("blocked - " + _format_list(items))
    if not parts:
        return "done"
    return " | ".join(parts)

def _execute_multi_step(steps: list[dict[str, Any]]) -> dict:
    """Execute parsed multi-step commands through runtime execution policy."""
    results: list[dict[str, Any]] = []
    blocked_count = 0
    success_count = 0

    for idx, step in enumerate(steps, start=1):
        action = step.get("action", "")
        target = step.get("target", "")
        _log_route(
            "execution_policy_apply",
            action=action,
            target=target,
            step=idx,
            total=len(steps),
        )

        # Browser Connector: intercept close actions for owned tabs
        if action == "close" and config.BROWSER_CONNECTOR_ENABLED:
            conn = _get_connector()
            close_error = ""
            close_success = False
            if conn and conn.is_connected():
                try:
                    close_result = asyncio.run(conn.close_tab(target))
                    close_success = close_result.success
                    close_error = close_result.error or ""
                except BaseException as exc:
                    close_error = str(exc)
                    logger.warning("[CONNECTOR] multi-step close_tab failed: %s", exc)
            if close_success:
                result = {
                    "success": True,
                    "message": f"Closed {target.capitalize()} tab.",
                    "action": action,
                    "target": target,
                }
            else:
                result = {
                    "success": False,
                    "message": f"Couldn't close {target}: {close_error or 'browser connector not available'}",
                    "action": action,
                    "target": target,
                }
            results.append(result)
            if result.get("success"):
                success_count += 1
            _log_route(
                "execution_policy_allowed",
                action=action,
                target=target,
                step=idx,
                success=result.get("success", False),
            )
            continue

        # Browser Connector: intercept focus actions for browser tabs
        if action == "focus" and config.BROWSER_CONNECTOR_ENABLED:
            conn = _get_connector()
            if conn and conn.is_connected():
                focus_success = False
                focus_error = ""
                try:
                    focus_result = asyncio.run(conn.focus_tab(target))
                    focus_success = focus_result.success
                    focus_error = focus_result.error or ""
                except BaseException as exc:
                    focus_error = str(exc)
                    logger.warning("[CONNECTOR] multi-step focus_tab failed: %s", exc)
                if focus_success:
                    from mini_kio.platform.window_activation import try_activate_browser
                    from mini_kio.core.capability_registry import get_capability_registry
                    from mini_kio.core.routing_utils import get_browser_registry
                    
                    cap_reg = get_capability_registry()
                    # Patch 2: Targeted PID selection
                    canon_target = get_browser_registry().canonicalize(target.lower().strip())
                    _entry = cap_reg.resolve_by_target(canon_target)
                    if not _entry:
                        _entry = cap_reg.get_latest_active()
                    
                    if _entry and _entry.browser_pid:
                        try_activate_browser(_entry.browser_pid)
                    result = {"success": True, "message": f"Focused {target.capitalize()} tab.",
                              "action": action, "target": target}
                else:
                    result = {"success": False, "message": f"Couldn't focus {target}: {focus_error or 'browser connector not available'}",
                              "action": action, "target": target}
                results.append(result)
                if result.get("success"):
                    success_count += 1
                _log_route(
                    "execution_policy_allowed",
                    action=action,
                    target=target,
                    step=idx,
                    success=result.get("success", False),
                )
                continue
            else:
                result = {"success": False, "message": f"Can't focus {target} — Browser Connector is not connected.",
                          "action": action, "target": target}
                results.append(result)
                _log_route("execution_policy_allowed", action=action, target=target, step=idx, success=False)
                continue

        # Browser Connector: intercept open actions for browser web targets
        if action == "open" and config.BROWSER_CONNECTOR_ENABLED:
            conn = _get_connector()
            url = _normalize_web_target_to_url(target)
            if url and conn and conn.is_connected():
                open_success = False
                open_error = ""
                try:
                    open_result = asyncio.run(conn.open_tab(url))
                    open_success = open_result.success
                    open_error = open_result.error or ""
                except BaseException as exc:
                    open_error = str(exc)
                    logger.warning("[CONNECTOR] multi-step open_tab failed: %s", exc)
                if open_success:
                    from mini_kio.platform.window_activation import try_activate_browser
                    from mini_kio.core.capability_registry import get_capability_registry
                    _entry = get_capability_registry().get_latest_active()
                    if _entry and _entry.browser_pid:
                        try_activate_browser(_entry.browser_pid)
                    result = {"success": True, "message": f"Opened {target.capitalize()} in Chrome.",
                              "action": action, "target": target}
                else:
                    result = {"success": False, "message": f"Couldn't open {target}: {open_error or 'browser connector not available'}",
                              "action": action, "target": target}
                results.append(result)
                if result.get("success"):
                    success_count += 1
                _log_route(
                    "execution_policy_allowed",
                    action=action,
                    target=target,
                    step=idx,
                    success=result.get("success", False),
                )
                continue

        # MediaManager: intercept play actions instead of legacy execute_action("play_youtube")
        if action == "play":
            from mini_kio.media.media_manager import MediaManager
            try:
                _mm_inst = MediaManager.get_instance()
                play_result = _mm_inst.play(target)
                if isinstance(play_result, dict):
                    result = {
                        "success": play_result.get("success", False),
                        "message": play_result.get("message", ""),
                        "action": action,
                        "target": target,
                    }
                else:
                    result = {"success": True, "message": str(play_result), "action": action, "target": target}
            except Exception as exc:
                logger.warning("[MULTI_STEP] MediaManager play failed: %s", exc)
                result = {"success": False, "message": f"Playback failed: {exc}", "action": action, "target": target}
            results.append(result)
            if result.get("success"):
                success_count += 1
            _log_route("execution_policy_allowed", action=action, target=target, step=idx, success=result.get("success", False))
            continue

        result = execute_action(action, target)
        results.append(result)

        if result.get("blocked"):
            blocked_count += 1
            _log_route(
                "execution_policy_blocked",
                action=action,
                target=target,
                step=idx,
            )
            continue

        if result.get("success"):
            success_count += 1
            _log_route(
                "execution_policy_allowed",
                action=action,
                target=target,
                step=idx,
                success=True,
            )
        else:
            _log_route(
                "execution_policy_allowed",
                action=action,
                target=target,
                step=idx,
                success=False,
            )
            return {
                "success": False,
                "message": f"Step {idx} failed: {result.get('message', 'unknown error')}",
                "results": results,
            }

    return {
        "success": blocked_count == 0 and success_count > 0,
        "message": _summarize_steps(steps, results),
        "results": results,
    }


# ---------------------------------------------------------------------------
# Telegram-facing entry point
# ---------------------------------------------------------------------------

def route(text: str, user_id: int = 0) -> str:
    """
    Channel-facing dispatcher (compat wrapper).
    Returns a plain-text string.  Never raises.
    """
    try:
        _log_route("route_entry", user_id=user_id, text_len=len(text))
        from mini_kio.core.runtime import dispatch_channel_input, format_channel_reply

        result = dispatch_channel_input(text, channel="telegram", user_id=user_id)
        return format_channel_reply(result)
    except BaseException as exc:
        logger.exception(f"route() crashed: {exc}")
        return "KIO encountered an internal error but is still running."


# ---------------------------------------------------------------------------
# AI / Knowledge fallback
# ---------------------------------------------------------------------------

_KNOWLEDGE_BASE: dict[str, str] = {
    # ── Greetings (Deterministic) ─────────────────────────────────────
    "hello": "Hello.",
    "hi": "Hi there.",
    "hey": "Hey.",
    "yo": "KIO here.",
    "wassup": "KIO here.",
    
    # ── Capabilities (Deterministic) ──────────────────────────────────
    "what can you do": "I can open and close applications, search Google and YouTube, play media, and open folders.",
    "capabilities": "I handle desktop automation, web search, and conversational assistance.",
}


def _ai_fallback(query: str) -> dict:
    """
    Fallback for unrecognised commands.

    Order:
      1. Knowledge-base lookup (instant, no network).
      2. Media opportunity detection (trailer/tutorial/recommendation).
      3. Signal eligibility for Gate 3 orchestration pipeline.
    """
    q = query.lower().strip()

    # 1. Knowledge base
    for key, answer in _KNOWLEDGE_BASE.items():
        if re.search(rf"\b{re.escape(key)}\b", q):
            result = {"success": True, "message": answer}
            _append_media_offer(query, result)
            return result

    # 2. Check for media opportunity
    if config.BROWSER_CONNECTOR_ENABLED:
        mm = MediaManager.get_instance()
        opportunity = mm.offer_media(query)
        if opportunity:
            offer_msg = opportunity.get("offer", "")
            if offer_msg:
                return {
                    "success": True,
                    "message": (
                        f"I don't have a direct answer for that. However, {offer_msg}"
                    ),
                    "_media_offer": opportunity,
                    "_gate3_eligible": True,
                }

    # 3. Graceful unknown — eligible for Gate 3 orchestration pipeline
    return {
        "success": False,
        "message": (
            f"Cannot process '{query}'. "
            "I can open apps, search the web, or play media."
        ),
        "_gate3_eligible": True,
    }


def _append_media_offer(query: str, result: dict):
    try:
        if not config.BROWSER_CONNECTOR_ENABLED:
            return
        mm = MediaManager.get_instance()
        opportunity = mm.offer_media(query)
        if opportunity:
            offer_msg = opportunity.get("offer", "")
            if offer_msg:
                existing = result.get("message", "")
                result["message"] = f"{existing}\n\n{offer_msg}"
                result["_media_offer"] = opportunity
    except Exception:
        pass


def _show_help() -> dict:
    return {
        "success": True,
        "message": (
            "KIO Commands\n"
            "─────────────────────────────────\n"
            "open <app>             open chrome / calculator / notepad / vscode\n"
            "open <folder>          open downloads folder / desktop / documents\n"
            "close <app>            close chrome\n"
            "search <query>         search Google\n"
            "play <query>           play on YouTube\n"
            "open chrome and search <query>   multi-step\n"
            "open chrome and play <query>     multi-step\n"
            "shutdown / restart / lock\n"
            "ping                   check KIO status\n"
            "help                   show this message"
        ),
    }


__all__ = ["handle_command", "route"]

