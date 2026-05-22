"""
browser_operator.py — KIO Browser Operator
===========================================
Status: no bugs found in the original.  File preserved as-is with minor
docstring improvements.

Routing:
    youtube_play   → play_youtube()
    search         → search_google()
    search_youtube → search_youtube()
    open_url       → open_url()

No scraping, no selenium, no network requests — only webbrowser.open().
"""

from __future__ import annotations

import logging
import time
import urllib.parse
import webbrowser
from typing import Any, Dict

from mini_kio.core.operator_protocol import OperatorDescriptor

logger = logging.getLogger(__name__)

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
        webbrowser.open(url)
        logger.info(f"[BROWSER] opened: {url}")
        return _normalize_public_result("open_url", url, {"success": True, "message": f"Opened {url}"}, start_time)
    except Exception as exc:
        logger.error(f"[BROWSER] open_url failed: {exc}")
        return _normalize_public_result(
            "open_url",
            url,
            {"success": False, "message": f"Failed to open {url}: {str(exc)[:80]}"},
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
        webbrowser.open(url)
        logger.info(f"[BROWSER] Google search: {query!r}")
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
        webbrowser.open(url)
        logger.info(f"[BROWSER] YouTube search: {query!r}")
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
        webbrowser.open(url)
        logger.info(f"[BROWSER] YouTube play: {query!r}")
        return _normalize_public_result(
            "youtube_play",
            "youtube",
            {"success": True, "message": f"Playing on YouTube: {query}"},
            start_time,
        )
    except Exception as exc:
        return _normalize_public_result(
            "youtube_play",
            "youtube",
            {"success": False, "message": f"YouTube play failed: {str(exc)[:80]}"},
            start_time,
        )


# Alias kept for backward compatibility
play_youtube_video = play_youtube

__all__ = ["open_url", "search_google", "search_youtube", "play_youtube", "play_youtube_video"]
