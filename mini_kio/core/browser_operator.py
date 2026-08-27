"""
browser_operator.py — KIO Browser Operator
===========================================
Routing:
    youtube_play   → play_youtube()
    search         → search_google()
    search_youtube → search_youtube()
    open_url       → open_url()

Fallback chain: BrowserRuntime (Playwright) → webbrowser.open()
All Playwright async ops run on a single persistent background event loop
to keep the subprocess pipe alive across calls.
"""

from __future__ import annotations

import asyncio
import logging
import threading
import time
import urllib.parse
import os
import webbrowser
from typing import Any, Dict

from mini_kio.core.operator_protocol import OperatorDescriptor

logger = logging.getLogger(__name__)

# ── Persistent background event loop for BrowserRuntime ──────────────
# ponytail: one global loop + daemon thread; per-account loops if isolation matters
_br_loop: asyncio.AbstractEventLoop | None = None
_br_thread: threading.Thread | None = None
_br_loop_lock = threading.Lock()


def _ensure_br_loop() -> asyncio.AbstractEventLoop:
    """Return a running event loop dedicated to BrowserRuntime, creating it on first call."""
    global _br_loop, _br_thread
    if _br_loop is not None and _br_loop.is_running():
        return _br_loop
    with _br_loop_lock:
        if _br_loop is not None and _br_loop.is_running():
            return _br_loop
        _br_loop = asyncio.new_event_loop()
        _br_thread = threading.Thread(
            target=_br_loop.run_forever, daemon=True, name="kio-br-loop",
        )
        _br_thread.start()
        return _br_loop


def _br_run_async(coro, timeout: float = 30.0):
    """Run a coroutine on the persistent BrowserRuntime event loop from sync code."""
    loop = _ensure_br_loop()
    future = asyncio.run_coroutine_threadsafe(coro, loop)
    return future.result(timeout=timeout)


_br_start_lock = threading.Lock()

def _get_browser_runtime():
    """Get BrowserRuntime, starting it first if needed. Returns None if unavailable."""
    try:
        from mini_kio.core.runtime import get_runtime
        rt = get_runtime()
        if rt is None or rt.browser_runtime is None:
            return None
        br = rt.browser_runtime
        if not getattr(br, '_started', False):
            with _br_start_lock:
                if not getattr(br, '_started', False):
                    _br_run_async(br.start())
                    _ws = getattr(rt, '_browser_default_workspace', 'default')
                    if not br.workspaces.exists(_ws):
                        from mini_kio.runtime.browser_runtime.types import WorkspaceConfig
                        _br_run_async(br.open_workspace(WorkspaceConfig(name=_ws)))
        return br
    except Exception as exc:
        logger.error("BrowserRuntime start failed: %s", exc, exc_info=True)
        return None

def _browser_runtime_error() -> str | None:
    """Return the last BrowserRuntime start error, or None if not applicable."""
    try:
        from mini_kio.core.runtime import get_runtime
        rt = get_runtime()
        if rt is None or rt.browser_runtime is None:
            return None
        return getattr(rt.browser_runtime, '_start_error', None)
    except Exception:
        return None

def _try_browser_runtime_navigate(url: str) -> bool | None:
    """Try to navigate using BrowserRuntime. Returns None if unavailable."""
    try:
        from mini_kio.core.runtime import get_runtime
        br = _get_browser_runtime()
        if br is None:
            return None
        rt = get_runtime()
        tab_id = br.tabs.active_tab_id
        if tab_id is None:
            _ws = getattr(rt, '_browser_default_workspace', 'default')
            info = _br_run_async(br.new_tab(_ws, url=url))
            return info is not None
        result = _br_run_async(br.goto(tab_id, url))
        return result.success if result else None
    except Exception as exc:
        logger.debug("[BROWSER_RUNTIME] navigate failed, falling back: %s", exc)
        return None

def _safe_webbrowser_open(url: str) -> bool:
    if os.environ.get("KIO_TEST_MODE") == "1":
        logger.info("[TEST MODE] Blocked webbrowser.open(%s)", url)
        return True
    # Priority: Browser Connector → BrowserRuntime → system browser
    from mini_kio.core.command_router import _get_connector
    conn = _get_connector()
    if conn and conn.is_connected():
        try:
            from mini_kio.core.async_utils import safe_run_async
            result = safe_run_async(conn.open_tab(url))
            return result.success
        except Exception as exc:
            logger.debug("[CONNECTOR] open_tab failed, falling back: %s", exc)
    br_result = _try_browser_runtime_navigate(url)
    if br_result is not None:
        return br_result
    return webbrowser.open(url)

def _register_browser_session(action: str, url: str) -> None:
    """Register a lightweight session record for a browser_operator action."""
    try:
        from mini_kio.core.routing_utils import get_browser_registry
        get_browser_registry().create_session(action, url)
    except Exception as exc:
        logger.warning("[BROWSER_SESSION] Registration error: %s", exc)

# ---------------------------------------------------------------------------
# Operator Descriptor
# ---------------------------------------------------------------------------

BROWSER_OPERATOR_DESCRIPTOR: OperatorDescriptor = {
    "tool_name": "browser_operator",
    "tool_version": "1.0.0",
    "ram_budget_mb": 8.0,
    "timeout_seconds": 10,
    "side_effect": True,
    "lifecycle_type": "browser",
    "supported_actions": ["play_youtube", "search_youtube", "open_url", "search_google"]
}


def _normalize_public_result(action: str, target: str, result: Dict[str, Any], start_time: float) -> Dict[str, Any]:
    """Normalize public API results to the deterministic target shape."""
    def _normalize_bool(value: Any) -> bool:
        if isinstance(value, bool):
            return value
        if isinstance(value, (int, float)):
            return bool(value)
        if isinstance(value, str):
            normalized = value.strip().lower()
            if normalized in {"true", "1", "yes", "y", "ok", "success"}:
                return True
            if normalized in {"false", "0", "no", "n", "fail", "failed", "failure"}:
                return False
        return bool(value)

    def _normalize_pid(value: Any) -> Any:
        if isinstance(value, bool):
            return None
        if isinstance(value, int):
            return value
        if isinstance(value, str) and value.strip().isdigit():
            return int(value.strip())
        return None

    if not isinstance(result, dict):
        result = {"success": False, "message": str(result)}

    out: Dict[str, Any] = dict(result)

    if "success" not in out and "status" in out:
        out["success"] = out["status"]

    if "message" not in out:
        out["message"] = out.get("error") or out.get("reason") or out.get("details") or ""

    out["success"] = _normalize_bool(out.get("success", False))
    out["message"] = str(out.get("message") or "")

    out["action"] = action
    out["target"] = target
    
    # BROWSER LIFECYCLE (Gate 2.5 Stabilization): Always non-trackable
    out["verification_mode"] = "noop"

    try:
        out["elapsed_ms"] = int((time.time() - float(start_time)) * 1000)
    except Exception:
        out["elapsed_ms"] = 0

    pid_value = out.get("pid", out.get("process_id"))
    out["pid"] = _normalize_pid(pid_value)

    failure_class = out.get("failure_class")
    if not isinstance(failure_class, str):
        failure_class = str(failure_class or "")

    if failure_class:
        out["failure_class"] = failure_class
    else:
        if out["success"]:
            out["failure_class"] = ""
        else:
            msg = out["message"].lower()
            if "timeout" in msg:
                out["failure_class"] = "timeout"
            elif "invalid url" in msg or ("invalid" in msg and "url" in msg):
                out["failure_class"] = "invalid_url"
            elif "no browser" in msg or "browser not found" in msg or "could not locate" in msg or "cannot find" in msg:
                out["failure_class"] = "browser_not_found"
            elif "failed to open" in msg or "failed to launch" in msg or "open_url failed" in msg or "search failed" in msg or "play failed" in msg:
                out["failure_class"] = "launch_failed"
            elif "verification" in msg or "verify" in msg:
                out["failure_class"] = "verification_failed"
            elif "invalid" in msg or "no search query" in msg or "no youtube search query" in msg or "no video query" in msg:
                out["failure_class"] = "invalid_url"
            else:
                out["failure_class"] = "internal_error"

    return out


def open_url(url: str) -> Dict[str, Any]:
    """Open a URL in the default browser."""
    start_time = time.time()
    try:
        if not url.startswith(("http://", "https://")):
            url = "https://" + url
        _safe_webbrowser_open(url)
        logger.info(f"[BROWSER] opened: {url}")
        _register_browser_session("open_url", url)
        
        # Friendly name extraction to avoid URL leakage (BUG 4)
        from mini_kio.core.runtime_response_formatter import _extract_url_name
        friendly_name = _extract_url_name(url)
        
        return _normalize_public_result("open_url", url, {"success": True, "message": f"Opened {friendly_name}"}, start_time)
    except Exception as exc:
        logger.error(f"[BROWSER] open_url failed: {exc}")
        return _normalize_public_result(
            "open_url",
            url,
            {"success": False, "message": f"Failed to open the requested page: {str(exc)[:40]}"},
            start_time,
        )


def search_google(query: str) -> Dict[str, Any]:
    """Search Google in the default browser."""
    start_time = time.time()
    if not query:
        return _normalize_public_result(
            "search",
            "google",
            {"success": False, "message": "No search query"},
            start_time,
        )
    try:
        url = f"https://www.google.com/search?q={urllib.parse.quote_plus(query)}"
        _safe_webbrowser_open(url)
        logger.info(f"[BROWSER] Google search: {query!r}")
        _register_browser_session("search_google", url)
        return _normalize_public_result(
            "search",
            "google",
            {"success": True, "message": f"Searched Google: {query}"},
            start_time,
        )
    except Exception as exc:
        return _normalize_public_result(
            "search",
            "google",
            {"success": False, "message": f"Google search failed: {str(exc)[:80]}"},
            start_time,
        )


def search_youtube(query: str) -> Dict[str, Any]:
    """Search YouTube in the default browser."""
    start_time = time.time()
    if not query:
        return _normalize_public_result(
            "search_youtube",
            "youtube",
            {"success": False, "message": "No YouTube search query"},
            start_time,
        )
    try:
        url = f"https://www.youtube.com/results?search_query={urllib.parse.quote_plus(query)}"
        _safe_webbrowser_open(url)
        logger.info(f"[BROWSER] YouTube search: {query!r}")
        _register_browser_session("search_youtube", url)
        return _normalize_public_result(
            "search_youtube",
            "youtube",
            {"success": True, "message": f"Searched YouTube: {query}"},
            start_time,
        )
    except Exception as exc:
        return _normalize_public_result(
            "search_youtube",
            "youtube",
            {"success": False, "message": f"YouTube search failed: {str(exc)[:80]}"},
            start_time,
        )


def play_youtube(query: str) -> Dict[str, Any]:
    """
    Open YouTube search results (filtered for videos).
    Uses deterministic video-only filter to feel 'playback-oriented'.
    No scraping — uses webbrowser.open() only.
    """
    start_time = time.time()
    if not query:
        return _normalize_public_result(
            "youtube_play",
            "youtube",
            {"success": False, "message": "No video query"},
            start_time,
        )
    try:
        encoded = urllib.parse.quote_plus(query)
        # Filter: Videos Only (EgIQAQ%253D%253D) + Search
        url = f"https://www.youtube.com/results?search_query={encoded}&sp=EgIQAQ%253D%253D"
        _safe_webbrowser_open(url)
        logger.info(f"[BROWSER] YouTube play: {query!r}")
        _register_browser_session("play_youtube", url)
        return _normalize_public_result(
            "youtube_play",
            "youtube",
            {"success": True, "message": f"Opened YouTube for: {query}. Click the first video to play."},
            start_time,
        )
    except Exception as exc:
        return _normalize_public_result(
            "youtube_play",
            "youtube",
            {"success": False, "message": f"YouTube play failed: {str(exc)[:80]}"},
            start_time,
        )


# ---------------------------------------------------------------------------
# BrowserRuntime execution handlers (DOM + scripting dispatch)
# ---------------------------------------------------------------------------

_BROWSER_DOM_DISPATCH: dict[str, tuple[str, str]] = {
    "browser_click": ("dom", "click"),
    "browser_hover": ("dom", "hover"),
    "browser_scroll": ("dom", "scroll_into_view"),
    "browser_drag": ("dom", "drag_and_drop"),
    "browser_select": ("dom", "select"),
    "browser_fill": ("dom", "fill"),
    "browser_type": ("dom", "fill"),
    "browser_keypress": ("dom", "press_key"),
    "browser_evaluate": ("scripting", "evaluate"),
    "browser_extract_text": ("scripting", "extract_text"),
    "browser_extract_html": ("scripting", "extract_html"),
    "browser_screenshot": ("scripting", "screenshot"),
    "browser_pdf": ("scripting", "pdf"),
}

def _br_dispatch(action: str, target_json: str) -> dict:
    """Call a BrowserRuntime controller method, falling back to Browser Connector, and return a normalized dict."""
    try:

        import json
        params = json.loads(target_json) if isinstance(target_json, str) and target_json.startswith('{') else {}
        tab_id = params.pop('tab_id', '')
        start = time.time()
        # Try Browser Connector first
        conn = _get_connector()
        if conn and conn.is_connected():
            try:
                from mini_kio.core.async_utils import safe_run_async
                script_name = action.replace('browser_', '')
                args = list(params.values()) if params else None
                result = safe_run_async(conn.execute_script(tab_id, script_name, args=args))
                if result.success:
                    return {"success": True, "message": result.error or f"{action} via connector succeeded.", "action": action, "target": target_json, "elapsed_ms": int((time.time() - start) * 1000)}
            except Exception as exc:
                logger.debug("[CONNECTOR] %s failed, falling back: %s", action, exc)
        # Fallback to BrowserRuntime
        br = _get_browser_runtime()
        if br is None:
            err = _browser_runtime_error()
            msg = f"BrowserRuntime not available: {err}" if err else "BrowserRuntime not available."
            return {"success": False, "message": msg, "action": action, "target": target_json}
        page = br.tabs.get_page(tab_id)
        controller, method_name = _BROWSER_DOM_DISPATCH[action]
        ctrl = getattr(br, controller)
        fn = getattr(ctrl, method_name)

        if action == "browser_drag":
            result = _br_run_async(fn(page, params.pop('source'), params.pop('target'), **params))
        elif action == "browser_keypress":
            result = _br_run_async(fn(page, **params))
        elif action == "browser_evaluate":
            result = _br_run_async(fn(page, params.pop('expression'), params.pop('arg', None)))
        elif action == "browser_screenshot":
            from pathlib import Path
            save_path = Path(params.pop('path'))
            result_path = _br_run_async(fn(page, save_path, **params))
            return {"success": True, "message": f"Screenshot saved to {result_path}", "action": action, "target": target_json, "path": str(result_path)}
        elif action == "browser_pdf":
            from pathlib import Path
            save_path = Path(params.pop('path'))
            result_path = _br_run_async(fn(page, save_path, **params))
            return {"success": True, "message": f"PDF saved to {result_path}", "action": action, "target": target_json, "path": str(result_path)}
        elif action == "browser_extract_text" or action == "browser_extract_html":
            result = _br_run_async(fn(page, params.pop('selector', None)))
            return {"success": True, "message": str(result), "action": action, "target": target_json, "content": str(result)}
        else:
            result = _br_run_async(fn(page, **params))
        return {"success": result.success, "message": result.error or ("Done." if result.success else "Action failed."),
                "action": action, "target": target_json, "elapsed_ms": int((time.time() - start) * 1000)}
    except Exception as exc:
        return {"success": False, "message": f"Browser action failed: {exc}", "action": action, "target": target_json}

def browser_click(target: str) -> dict:
    return _br_dispatch("browser_click", target)
def browser_hover(target: str) -> dict:
    return _br_dispatch("browser_hover", target)
def browser_scroll(target: str) -> dict:
    return _br_dispatch("browser_scroll", target)
def browser_drag(target: str) -> dict:
    return _br_dispatch("browser_drag", target)
def browser_select(target: str) -> dict:
    return _br_dispatch("browser_select", target)
def browser_fill(target: str) -> dict:
    return _br_dispatch("browser_fill", target)
def browser_type(target: str) -> dict:
    return _br_dispatch("browser_fill", target)
def browser_keypress(target: str) -> dict:
    return _br_dispatch("browser_keypress", target)
def browser_evaluate(target: str) -> dict:
    return _br_dispatch("browser_evaluate", target)
def browser_extract_text(target: str) -> dict:
    return _br_dispatch("browser_extract_text", target)
def browser_extract_html(target: str) -> dict:
    return _br_dispatch("browser_extract_html", target)
def browser_screenshot(target: str) -> dict:
    return _br_dispatch("browser_screenshot", target)
def browser_pdf(target: str) -> dict:
    return _br_dispatch("browser_pdf", target)

def browser_goto(url: str) -> dict:
    """Navigate to URL using the best available backend (Connector → Runtime → system)."""
    if not url.startswith(("http://", "https://")):
        url = "https://" + url
    # Try Browser Connector first
    from mini_kio.core.command_router import _get_connector
    conn = _get_connector()
    if conn and conn.is_connected():
        try:
            from mini_kio.core.async_utils import safe_run_async
            result = safe_run_async(conn.open_tab(url))
            if result.success:
                return {"success": True, "message": f"Navigating to {url} via connector.", "action": "browser_goto", "target": url}
        except Exception as exc:
            logger.debug("[CONNECTOR] open_tab failed in browser_goto: %s", exc)
    # Fallback to BrowserRuntime
    br_result = _try_browser_runtime_navigate(url)
    if br_result is not None:
        msg = f"Navigating to {url}" if br_result else f"Navigation to {url} failed."
        return {"success": br_result, "message": msg, "action": "browser_goto", "target": url}
    # Final fallback: system browser via webbrowser.open
    webbrowser.open(url)
    return {"success": True, "message": f"Opened {url} via system browser.", "action": "browser_goto", "target": url}

BROWSER_HANDLERS: dict[str, object] = {
    "browser_goto": browser_goto,
    "browser_click": browser_click,
    "browser_hover": browser_hover,
    "browser_scroll": browser_scroll,
    "browser_drag": browser_drag,
    "browser_select": browser_select,
    "browser_fill": browser_fill,
    "browser_type": browser_type,
    "browser_keypress": browser_keypress,
    "browser_evaluate": browser_evaluate,
    "browser_extract_text": browser_extract_text,
    "browser_extract_html": browser_extract_html,
    "browser_screenshot": browser_screenshot,
    "browser_pdf": browser_pdf,
}

# Alias kept for backward compatibility
play_youtube_video = play_youtube

__all__ = ["open_url", "search_google", "search_youtube", "play_youtube", "play_youtube_video"]
