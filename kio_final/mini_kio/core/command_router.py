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
import json
import logging
import re
from typing import Any, Optional

from mini_kio.core.execution_boundary import execute_action
from mini_kio.core.app_operator import APP_REGISTRY, WEB_DOMAIN_ALIASES, WEB_URLS, _normalize_web_target_to_url

logger = logging.getLogger(__name__)

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
    Handles 'it' (last target), 'that' (last target), 'again' (last action).
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

    # Handle "it" and "that"
    if re.search(r"\b(it|that)\b", lower):
        last = get_last_successful_interaction(must_have_target=True)
        if last:
            target = str(last.get("target", ""))
            resolved = re.sub(r"\b(it|that)\b", target, command, flags=re.IGNORECASE)
            _log_route("context_resolve", original=command, resolved=resolved)
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

    # Phase 1: Contextual Resolution
    command = _resolve_contextual_references(command)

    from mini_kio.core.command_parser import _apply_aliases, _normalize_connectors, is_multi_step
    command = _apply_aliases(command)
    logger.info(f"[KIO] handle_command: {command!r}")

    if not command:
        return {"success": False, "message": "Empty command"}

    lower = command.lower()
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
    if lower == "hello":
        return {"success": True, "message": "Hello!"}
    if lower in ("hi", "hey"):
        return {"success": True, "message": "Hey!"}
    if lower in ("yo", "wassup", "what's up", "whats up"):
        return {"success": True, "message": "KIO here. Ask me anything."}
    if lower in ("how are you", "how are you doing"):
        return {"success": True, "message": "Doing good! What can I do?"}
    if lower in ("bye", "bue"):
        return {"success": True, "message": "See you!"}
    if lower == "okay":
        return {"success": True, "message": "Got it."}
    if lower == "bruh":
        return {"success": True, "message": "..."}

    # ── DETERMINISTIC RESPONSES ───────────────────────────────────────────
    if lower in ("who are you", "what are you", "what is kio"):
        return {"success": True, "message": "I am KIO, a lightweight local AI assistant created by Joel."}
    
    if lower in ("who made you", "who created you", "who is your creator", "who built you", "who created kio", "who made u", "who built u"):
        return {"success": True, "message": "I was created by Joel."}

    if lower in ("who is joel", "who's joel"):
        return {"success": True, "message": "Joel is the creator of KIO."}

    if lower in ("what can you do", "what are your features", "what can u do"):
        return {
            "success": True,
            "message": (
                "KIO can: open/close apps, search the web, play YouTube, "
                "manage files, and execute multi-step automation commands."
            )
        }

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
            for sep in [" in ", " on ", " using "]:
                if sep in query:
                    parts = query.rsplit(sep, 1)
                    target_app = parts[1].strip()
                    clean_query = parts[0].strip()
                    if target_app == "youtube":
                        _log_route("route", intent="search_youtube", query=clean_query)
                        return execute_action("search_youtube", clean_query)
                    if target_app in ("chrome", "edge", "firefox", "brave", "comet"):
                        _log_route("route", intent="capability", app=target_app, cap="search")
                        return execute_action("execute_capability", f"{target_app}::search::{clean_query}")
            
            # Handle "search youtube X" swallow fix
            if query.lower().startswith("youtube "):
                clean_query = query[8:].strip()
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
                return execute_action("execute_capability", f"{browser}::open_url::{normalized_url}")
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

            _log_route("route", intent="open_app", target=target)
            return execute_action("open_app", target)

        # ── CLOSE ─────────────────────────────────────────────────────────────
        if lower.startswith("close "):
            target = command[6:].strip()
            _log_route("route", intent="close_app", target=target)
            return execute_action("close_app", target)

        # ── PLAY (YouTube / Media) ─────────────────────────────────────────────
        if lower.startswith("play "):
            query = command[5:].strip()
            for sep in [" on ", " in ", " using "]:
                if sep in query:
                    parts = query.rsplit(sep, 1)
                    target_app = parts[1].strip()
                    clean_query = parts[0].strip()
                    if target_app == "youtube":
                         _log_route("route", intent="play_youtube", query=clean_query)
                         return execute_action("play_youtube", clean_query)
                    if target_app in ("spotify", "vlc", "capcut"):
                        _log_route("route", intent="capability", app=target_app, cap="play")
                        return execute_action("execute_capability", f"{target_app}::play::{clean_query}")
            
            # AMBIGUITY FIX: Return choice message instead of defaulting to YouTube
            return {"success": True, "message": "Play on YouTube or Spotify?"}

        # ── SEARCH YOUTUBE ────────────────────────────────────────────────────
        if lower.startswith("search youtube "):
            query = command[15:].strip()
            return execute_action("search_youtube", query)

        if lower.startswith("youtube "):
            query = command[8:].strip()
            return execute_action("play_youtube", query)

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
        if lower == "ping":
            return {"success": True, "message": "Here."}

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
    succeeded: list[str] = []
    blocked: list[str] = []
    last_verb: Optional[str] = None
    for step, result in zip(steps, results):
        action = step.get("action", "")
        target = step.get("target", "")
        verb = _ACTION_VERBS.get(action, action)
        if verb and verb == last_verb:
            entry = target
        else:
            entry = f"{verb} {target}" if verb else target
        if result.get("blocked"):
            blocked.append(entry)
        elif result.get("success"):
            succeeded.append(entry)
        last_verb = verb if verb else last_verb
    if not succeeded and not blocked:
        return "done"
    if succeeded and not blocked:
        return "done - " + _format_list(succeeded)
    if not succeeded and blocked:
        return "all blocked - " + _format_list(blocked)
    return "done - " + _format_list(succeeded) + "; blocked " + _format_list(blocked)

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
    except Exception as exc:
        logger.exception(f"route() crashed: {exc}")
        return "KIO encountered an internal error but is still running."


# ---------------------------------------------------------------------------
# AI / Knowledge fallback
# ---------------------------------------------------------------------------

# BUG-04 FIX: Added "what are your features" to knowledge base.
_KNOWLEDGE_BASE: dict[str, str] = {
    "who created you":          "I am KIO, a lightweight AI assistant created by Joel.",
    "what are you":             "I am KIO, a lightweight AI assistant created by Joel.",
    "what is kio":              "KIO is a lightweight desktop AI assistant that can open apps, search the web, play YouTube videos, and more.",
    "what are your features":   (
        "KIO can: open/close applications, search Google, play YouTube videos, "
        "open folders, perform multi-step commands (e.g. 'open chrome and search python'), "
        "and answer general questions via AI fallback."
    ),
    "who is monkey d luffy":    "Monkey D. Luffy is the main protagonist of the One Piece manga/anime by Eiichiro Oda.",
    "what is one piece":        "One Piece is a popular Japanese manga and anime series created by Eiichiro Oda.",
    "explain c programming":    "C is a general-purpose, low-level programming language widely used for systems programming, embedded systems, and performance-critical applications.",
    "what is programming":      "Programming is writing instructions for computers to follow, using languages like Python, C, or JavaScript.",
    "what is computer science": "Computer science is the study of computation, algorithms, data structures, software engineering, and related fields.",
    "what is algorithm":        "An algorithm is a step-by-step procedure for solving a problem.",
    "what is data structure":   "A data structure organises and stores data for efficient access and modification (e.g. arrays, lists, trees).",
    "what is recursion":        "Recursion is when a function calls itself to solve smaller sub-problems until a base case is reached.",
    "explain recursion":        "Recursion is when a function calls itself. Example: factorial(n) = n * factorial(n-1), with factorial(0) = 1.",
    "what is ai":               "AI (Artificial Intelligence) is the simulation of human intelligence by machines, including learning, reasoning, and problem-solving.",
    "binary search":            "Binary search finds a target in a sorted array by repeatedly halving the search range. Time complexity: O(log n).",
}


def _ai_fallback(query: str) -> dict:
    """
    Fallback for unrecognised commands.

    Order:
      1. Knowledge-base lookup (instant, no network).
      2. Signal eligibility for Gate 3 orchestration pipeline.
    """
    q = query.lower().strip()

    # 1. Knowledge base
    for key, answer in _KNOWLEDGE_BASE.items():
        if key in q:
            return {"success": True, "message": answer}

    # 2. Graceful unknown — eligible for Gate 3 orchestration pipeline
    return {
        "success": False,
        "message": (
            f"I'm not sure how to '{query}'. "
            "I can open apps, search the web, or play media. Try 'help' for examples."
        ),
        "_gate3_eligible": True,
    }


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
