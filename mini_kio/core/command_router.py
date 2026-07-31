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
    if not _CONNECTOR_STARTED and config.BROWSER_CONNECTOR_ENABLED:
        _CONNECTOR_STARTED = True
        conn = _CONNECTOR_INSTANCE
        if conn and not conn._mock:
            conn.start_background()
    return _CONNECTOR_INSTANCE


def _use_browser_runtime() -> bool:
    from mini_kio.core.runtime import get_runtime
    rt = get_runtime()
    if rt is None or rt.browser_runtime is None:
        return False
    br = rt.browser_runtime
    return getattr(br, '_started', False)


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
    return _use_browser_runtime()


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
    """Execute parsed multi-step commands."""
    from mini_kio.core.app_operator import _normalize_web_target_to_url
    from mini_kio.core.execution_boundary import execute_action
    from mini_kio.core.async_utils import safe_run_async
    from mini_kio.media.media_manager import MediaManager

    results: list[dict[str, Any]] = []
    blocked_count = 0
    success_count = 0

    for idx, step in enumerate(steps, start=1):
        action = step.get("action", "")
        target = step.get("target", "")

        if action == "close":
            if _check_br_available():
                results.append(_br_close_tab(target))
                success_count += 1 if results[-1].get("success") else 0
                continue
            if config.BROWSER_CONNECTOR_ENABLED:
                conn = _get_connector()
                if conn and conn.is_connected():
                    try:
                        close_result = safe_run_async(conn.close_tab(target))
                        ok = close_result.success
                        results.append({
                            "success": ok,
                            "message": f"Closed {target.capitalize()} tab." if ok else f"Couldn't close {target}.",
                            "action": action, "target": target,
                        })
                        if ok:
                            success_count += 1
                        continue
                    except BaseException as exc:
                        logger.warning("[CONNECTOR] multi-step close_tab failed: %s", exc)

        if action == "focus":
            if _check_br_available():
                results.append(_br_focus_tab(target))
                success_count += 1 if results[-1].get("success") else 0
                continue
            conn = _get_connector()
            if conn and conn.is_connected():
                try:
                    focus_result = safe_run_async(conn.focus_tab(target))
                    if focus_result.success:
                        results.append({"success": True, "message": f"Focused {target.capitalize()} tab.", "action": action, "target": target})
                        success_count += 1
                    else:
                        results.append({"success": False, "message": f"Couldn't focus {target}.", "action": action, "target": target})
                    continue
                except BaseException as exc:
                    logger.warning("[CONNECTOR] multi-step focus_tab failed: %s", exc)
                    results.append({"success": False, "message": f"Couldn't focus {target}.", "action": action, "target": target})
                    continue

        if action == "open":
            url = _normalize_web_target_to_url(target)
            if url:
                from mini_kio.core.browser_operator import open_url
                result = open_url(url)
                results.append(result)
                if result.get("success"):
                    success_count += 1
                continue

        if action == "play":
            mm = MediaManager.get_instance()
            try:
                play_result = mm.play(target)
                if isinstance(play_result, dict):
                    result = {"success": play_result.get("success", False), "message": play_result.get("message", ""), "action": action, "target": target}
                else:
                    result = {"success": True, "message": str(play_result), "action": action, "target": target}
            except Exception as exc:
                result = {"success": False, "message": f"Playback failed: {exc}", "action": action, "target": target}
            results.append(result)
            if result.get("success"):
                success_count += 1
            continue

        result = execute_action(action, target)
        results.append(result)
        if result.get("blocked"):
            blocked_count += 1
            continue
        if result.get("success"):
            success_count += 1
        else:
            return {"success": False, "message": f"Step {idx} failed: {result.get('message', 'unknown error')}", "results": results}

    return {"success": blocked_count == 0 and success_count > 0, "message": _summarize_steps(steps, results), "results": results}


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
