"""
command_router.py — KIO Command Router (Thin pipeline delegate)
================================================================
This module is now a thin delegation layer over the authoritative Pipeline.
The Pipeline owns all classification, resolution, and execution routing.
command_router provides backward-compatible entry points (handle_command,
route, route_request) and shared browser helpers used by the pipeline
coordinator.
"""

from __future__ import annotations

import asyncio
import importlib.util
import json
import logging
import os
import re
import sys
from typing import Any, Optional

from mini_kio.core.pipeline import Pipeline

logger = logging.getLogger(__name__)

_INSTANCE: Pipeline | None = None


def _get_pipeline() -> Pipeline:
    global _INSTANCE
    if _INSTANCE is None:
        _INSTANCE = Pipeline()
    return _INSTANCE


# ---------------------------------------------------------------------------
# Browser helpers — shared with pipeline coordinator
# ---------------------------------------------------------------------------

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
        # Wrap the raw connector in the generic state-verification pipeline so
        # every browser/media provider (which all call _get_connector) benefits
        # automatically. The ACK is only a trigger; success requires observed
        # Chrome state.
        try:
            from mini_kio.core.state_verification import VerifiedConnector
            _CONNECTOR_INSTANCE = VerifiedConnector(_CONNECTOR_INSTANCE)
        except Exception as exc:
            logger.warning("[CONNECTOR] verification wrapper unavailable, falling back to raw: %s", exc)
    if not _CONNECTOR_STARTED and config.BROWSER_CONNECTOR_ENABLED:
        _CONNECTOR_STARTED = True
        conn = _CONNECTOR_INSTANCE
        if conn and not conn._mock:
            conn.start_background()
    return _CONNECTOR_INSTANCE


def _stop_connector() -> None:
    """Stop the background Browser Connector (daemon thread + WS server)."""
    global _CONNECTOR_INSTANCE, _CONNECTOR_STARTED
    conn = _CONNECTOR_INSTANCE
    if conn is None or not _CONNECTOR_STARTED:
        return
    try:
        loop = getattr(conn, "_loop", None)
        if loop is not None and loop.is_running():
            asyncio.run_coroutine_threadsafe(conn.stop(), loop).result(timeout=5)
        else:
            conn.stop()
    except Exception as exc:
        logger.warning("[CONNECTOR] shutdown failed: %s", exc)
    finally:
        _CONNECTOR_STARTED = False
        _CONNECTOR_INSTANCE = None


def _use_browser_runtime() -> bool:
    from mini_kio.core.browser_operator import _get_browser_runtime
    return _get_browser_runtime() is not None


def _br_focus_tab(target: str) -> dict:
    try:
        from mini_kio.core.runtime import get_runtime
        from mini_kio.core.browser_operator import _br_run_async
        rt = get_runtime()
        br = rt.browser_runtime
        tabs = br.tabs.list_tabs()
        tgt_lower = target.lower()
        match = None
        for t in tabs:
            if tgt_lower in t.title.lower() or tgt_lower in t.url.lower():
                match = t
                break
        if not match:
            return {"success": False, "message": f"Couldn't find tab matching '{target}'."}
        _br_run_async(br.tabs.switch(match.tab_id))
        return {"success": True, "message": f"Focused {target.capitalize()} tab."}
    except Exception as exc:
        return {"success": False, "message": f"Couldn't focus {target}: {exc}"}


def _br_list_tabs() -> dict:
    try:
        from mini_kio.core.runtime import get_runtime
        rt = get_runtime()
        br = rt.browser_runtime
        tabs = br.tabs.list_tabs()
        if not tabs:
            return {"success": True, "message": "No tabs open.", "action": "list_tabs"}
        lines = [f"  {t.title or t.url}" for t in tabs]
        return {"success": True, "message": "Open tabs:\n" + "\n".join(lines), "action": "list_tabs"}
    except Exception as exc:
        return {"success": False, "message": f"Couldn't list tabs: {exc}"}


def _br_close_tab(target: str) -> dict:
    try:
        from mini_kio.core.runtime import get_runtime
        from mini_kio.core.browser_operator import _br_run_async
        rt = get_runtime()
        br = rt.browser_runtime
        tabs = br.tabs.list_tabs()
        tgt_lower = target.lower()
        match = None
        for t in tabs:
            if tgt_lower in t.title.lower() or tgt_lower in t.url.lower():
                match = t
                break
        if not match:
            return {"success": False, "message": f"Couldn't find tab matching '{target}'."}
        _br_run_async(br.tabs.close(match.tab_id))
        return {"success": True, "message": f"Closed {target.capitalize()} tab."}
    except Exception as exc:
        return {"success": False, "message": f"Couldn't close {target}: {exc}"}


def _check_br_available() -> bool:
    # PERFORMANCE (system-level): this probe gates browser-tab fallback paths
    # in close/focus/open handling. It must be a FAST state check — returning
    # True only when the BrowserRuntime is ALREADY started — and must NEVER
    # trigger a multi-second Playwright start attempt. Real browser opens
    # (browser_goto / execute_capability) start the runtime on demand through
    # their own handler; availability probes in deterministic fallback chains
    # must not pay that cost when the browser is simply down.
    try:
        from mini_kio.core.runtime import get_runtime
        rt = get_runtime()
        if rt is None:
            return False
        br = getattr(rt, "browser_runtime", None)
        if br is None:
            return False
        return bool(getattr(br, "_started", False))
    except Exception:
        return False


_CONNECTOR_MODULES_LOADED = False
_BC_PKG = "_kio_bc"


def _load_connector_module():
    global _CONNECTOR_MODULES_LOADED
    if _CONNECTOR_MODULES_LOADED:
        return sys.modules.get(f"{_BC_PKG}.connector")
    _here = os.path.dirname(os.path.abspath(__file__))
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


from mini_kio.core import config


# ---------------------------------------------------------------------------
# Main dispatcher — delegates to Pipeline
# ---------------------------------------------------------------------------

_ACTION_VERBS: dict[str, str] = {
    "open_app": "opened", "close_app": "closed", "search_web": "searched",
    "search_google": "searched", "search_youtube": "searched", "play_youtube": "played",
    "open_folder": "opened", "execute_capability": "ran",
    "open": "opened", "close": "closed", "focus": "focused",
    "search": "searched", "play": "played",
    "lock": "locked", "shutdown": "shut down", "restart": "restarted",
}


def _format_list(items: list[str]) -> str:
    if not items:
        return ""
    if len(items) == 1:
        return items[0]
    if len(items) == 2:
        return f"{items[0]} and {items[1]}"
    return ", ".join(items[:-1]) + f", and {items[-1]}"


def _display_step_target(target: str) -> str:
    """User-safe display name for a step target (BC-5)."""
    from mini_kio.core.target_ref import display_target_name
    return display_target_name(str(target or ""))


def _summarize_steps(steps: list[dict[str, Any]], results: list[dict[str, Any]]) -> str:
    """Truthful aggregate of per-step outcomes (BC-6).

    Reports each step's verified outcome and composes natural partial-success
    language — never a blanket "done - opened A and B" from unverified ACKs.
    """
    succeeded: dict[str, list[str]] = {}  # past-tense verb -> display targets
    failed: list[tuple[str, str]] = []  # (verb_base, display_target)
    blocked: list[str] = []

    for step, result in zip(steps, results):
        action = step.get("action", "")
        target = _display_step_target(step.get("target", ""))
        verb = _ACTION_VERBS.get(action, action)
        if result.get("blocked"):
            # Blocked steps read naturally under "I couldn't ..." so they need
            # the BASE verb ("close Paint"), never the past-tense form
            # ("closed Paint").
            base_verb = action.replace("_tab", "").replace("_app", "").replace("_web", "")
            blocked.append(f"{base_verb or action} {target}")
        elif result.get("success"):
            succeeded.setdefault(verb, [])
            succeeded[verb].append(target)
        else:
            base_verb = action.replace("_tab", "").replace("_app", "").replace("_web", "")
            failed.append((base_verb or action, target))

    parts: list[str] = []
    if succeeded:
        # Group by past-tense verb: "Opened ChatGPT and Telegram." or
        # "Opened ChatGPT and closed Notepad." — never a generic "Done X, Y".
        bits = [f"{verb} {_format_list(targets)}" for verb, targets in succeeded.items()]
        parts.append(_format_list(bits))
    if failed:
        failed_parts = [f"{v} {t}" for v, t in failed]
        if parts:
            parts.append(f"but I couldn't {_format_list(failed_parts)}")
        else:
            parts.append(f"I couldn't {_format_list(failed_parts)}")
    if blocked:
        if parts:
            parts.append(f"and {_format_list(blocked)} were blocked")
        else:
            parts.append(f"I couldn't {_format_list(blocked)}")

    if not parts:
        return "Done."
    text = " ".join(parts).strip()
    if text and text[0].islower():
        text = text[0].upper() + text[1:]
    if not text.endswith((".", "!", "?")):
        text += "."
    return text


# Desktop-action step family (multi-step chains like "open notepad and type
# hello and save"). Each wording converges on the SAME canonical desktop
# executor the single-step classifier uses (_exec_desktop_action) — never a
# separate per-phrase handler. Shortcut words normalize to their canonical
# key combos.
_DESKTOP_STEP_SHORTCUT_COMBOS = {
    "save": "ctrl+s", "copy": "ctrl+c", "paste": "ctrl+v",
    "select": "ctrl+a", "select_all": "ctrl+a",
    "undo": "ctrl+z", "redo": "ctrl+y",
}


def _run_desktop_action_step(action: str, target: str) -> dict:
    """Run one desktop-action step through the canonical desktop executor."""
    from mini_kio.core.pipeline import _ExecutionCoordinator

    canonical = action
    if action in ("press", "hit", "tap"):
        canonical = "key_press"
    elif action == "write":
        canonical = "type"

    params: dict[str, Any] = {"action": canonical, "target": target, "metadata": {}}
    if canonical == "type":
        # "type hello" -> payload "hello" typed into the current focus
        # (the previous step usually opened/focused the target window).
        params["metadata"]["payload"] = target
        params["target"] = ""
    elif action in _DESKTOP_STEP_SHORTCUT_COMBOS:
        # Semantic edit actions ("save", "copy", "paste", "select all",
        # "undo", "redo") keep their semantic name at the intent layer and
        # carry the key combo in metadata — the executor resolves the
        # contextual target and verifies the real result. Explicit "press
        # ctrl+s" (action=key_press with its own target) stays literal.
        params["action"] = action
        params["metadata"]["combo"] = _DESKTOP_STEP_SHORTCUT_COMBOS[action]
        params["target"] = ""

    try:
        return _ExecutionCoordinator()._exec_desktop_action(params, None)
    except Exception as exc:
        logger.exception("[MULTI] desktop-action step %s crashed: %s", action, exc)
        return {"success": False, "message": f"Couldn't {action}: {exc}"}


def _run_single_step(action: str, target: str) -> dict:
    """Run ONE step of a multi-action request with per-step verification.

    Every step is executed independently through the same authoritative path a
    single command uses (open -> capability/native routing + verification,
    close -> tab-aware close, play -> MediaManager, desktop actions -> the
    canonical desktop executor, else execute_action).
    """
    from mini_kio.core.execution_boundary import execute_action
    from mini_kio.core.async_utils import safe_run_async
    from mini_kio.media.media_manager import MediaManager

    if action == "close":
        # Same browser-vs-app decision as the single-step classifier: browser
        # names close the browser app; everything else is tab-scoped.
        from mini_kio.core.target_ref import parse_target
        if parse_target(target).kind == "browser":
            return execute_action("close_app", target)
        if _check_br_available():
            result = _br_close_tab(target)
            if result.get("success"):
                return result
        if config.BROWSER_CONNECTOR_ENABLED:
            conn = _get_connector()
            if conn and conn.is_connected():
                try:
                    close_result = safe_run_async(conn.close_tab(target))
                    if bool(getattr(close_result, "success", False)):
                        return {
                            "success": True,
                            "message": f"Closed {target.capitalize()} tab.",
                            "action": action, "target": target,
                        }
                except BaseException as exc:
                    logger.warning("[CONNECTOR] multi-step close_tab failed: %s", exc)
        # Web-aware close (capability registry / connector / truthful failure):
        # mirrors the single-step path so "close X and Y" closes each target
        # through the same canonical owner a single close uses. Never escalates
        # to the host browser process.
        return execute_action("close_app", target)

    if action == "focus":
        # Same routing as single-step focus (browser tab focus first, then
        # native app window focus).
        if _check_br_available():
            result = _br_focus_tab(target)
            if result.get("success"):
                return result
        conn = _get_connector()
        if conn and conn.is_connected():
            try:
                focus_result = safe_run_async(conn.focus_tab(target))
                if getattr(focus_result, "success", False):
                    return {"success": True, "message": f"Focused {target.capitalize()} tab.", "action": action, "target": target}
            except BaseException as exc:
                logger.warning("[CONNECTOR] multi-step focus_tab failed: %s", exc)
        try:
            from mini_kio.core.pipeline import _ExecutionCoordinator
            native = _ExecutionCoordinator()._try_native_focus(target)
            if native:
                return native
        except BaseException as exc:
            logger.warning("multi-step native focus failed: %s", exc)
        return {"success": False, "message": f"Couldn't focus {target}.", "action": action, "target": target}

    if action == "open":
        # Same routing as a single "open X": native app -> open_app, web app ->
        # capability open (registers session + tab-identity verification).
        from mini_kio.core.routing_utils import get_browser_routing
        route_info = get_browser_routing(target)
        if route_info["route_type"] == "native":
            from mini_kio.core.pipeline import _ExecutionCoordinator
            reused = _ExecutionCoordinator()._reuse_running_app(route_info["target"])
            if reused:
                return reused
            return execute_action("open_app", route_info["target"])
        if route_info["route_type"] == "browser_fallback":
            return execute_action("execute_capability", route_info["target"])
        return execute_action("search_web", target)

    if action == "play":
        mm = MediaManager.get_instance()
        try:
            play_result = mm.play(target)
            if isinstance(play_result, dict):
                return {"success": play_result.get("success", False), "message": play_result.get("message", ""), "action": action, "target": target}
            return {"success": True, "message": str(play_result), "action": action, "target": target}
        except Exception as exc:
            return {"success": False, "message": f"Playback failed: {exc}", "action": action, "target": target}

    # Desktop-action family: type / press / hit / tap / save / copy / paste /
    # select / undo / redo / scroll / click (incl. "write" alias). These must
    # reach the canonical desktop-action executor — never the execution
    # boundary, whose "type"/"click"/"scroll" aliases mean BROWSER DOM
    # operations.
    if action in {
        "type", "write", "press", "hit", "tap", "save", "copy", "paste",
        "select", "select_all", "undo", "redo", "scroll", "click",
    }:
        return _run_desktop_action_step(action, target)

    return execute_action(action, target)


def _execute_multi_step(steps: list[dict[str, Any]]) -> dict:
    """Execute parsed multi-step commands (BC-6).

    Each step is resolved, executed, and verified INDEPENDENTLY. No early abort
    on a failing step (independent actions still run); the final result is an
    honest aggregate of per-step outcomes (all/partial/none).
    """
    results: list[dict[str, Any]] = []
    for step in steps:
        action = step.get("action", "")
        target = step.get("target", "")
        try:
            result = _run_single_step(action, target)
        except BaseException as exc:
            logger.exception("[MULTI] step %s/%s crashed: %s", action, target, exc)
            result = {"success": False, "message": "Step failed.", "action": action, "target": target}
        if not isinstance(result, dict):
            result = {"success": bool(result), "message": str(result), "action": action, "target": target}
        results.append(result)

    succeeded = sum(1 for r in results if r.get("success") and not r.get("blocked"))
    total = len(steps)
    all_ok = total > 0 and succeeded == total
    return {
        "success": all_ok,
        "message": _summarize_steps(steps, results),
        "results": results,
    }


# ---------------------------------------------------------------------------
# Interface-facing entry points (backward compatible)
# ---------------------------------------------------------------------------

def handle_command(command: str, session_id: str = "local_0") -> dict:
    """Route command through the authoritative Pipeline."""
    try:
        pipeline = _get_pipeline()
        return pipeline.run(command, session_id=session_id)
    except Exception as exc:
        logger.exception("handle_command failed for %r", command)
        return {"success": False, "message": f"Error: {exc}"}


def route(text: str, user_id: int = 0, channel: str = "telegram") -> str:
    """Channel-facing dispatcher (backward-compat wrapper)."""
    try:
        from mini_kio.core.runtime import dispatch_channel_input, format_channel_reply
        result = dispatch_channel_input(text, channel=channel, user_id=user_id)
        return format_channel_reply(result)
    except BaseException as exc:
        logger.exception(f"route() crashed: {exc}")
        return "KIO encountered an internal error but is still running."


def route_request(req) -> str:
    """Canonical interface entry point."""
    return route(text=req.text, user_id=req.user_id, channel=req.channel)


__all__ = ["handle_command", "route"]
