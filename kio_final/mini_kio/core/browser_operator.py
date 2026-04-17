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
import urllib.parse
import webbrowser
from typing import Dict

logger = logging.getLogger(__name__)


def open_url(url: str) -> Dict[str, str]:
    """Open a URL in the default browser."""
    try:
        if not url.startswith(("http://", "https://")):
            url = "https://" + url
        webbrowser.open(url)
        logger.info(f"[BROWSER] opened: {url}")
        return {"success": True, "message": f"Opened {url}"}
    except Exception as exc:
        logger.error(f"[BROWSER] open_url failed: {exc}")
        return {"success": False, "message": f"Failed to open {url}: {str(exc)[:80]}"}


def search_google(query: str) -> Dict[str, str]:
    """Search Google in the default browser."""
    if not query:
        return {"success": False, "message": "No search query"}
    try:
        url = f"https://www.google.com/search?q={urllib.parse.quote_plus(query)}"
        webbrowser.open(url)
        logger.info(f"[BROWSER] Google search: {query!r}")
        return {"success": True, "message": f"Searched Google: {query}"}
    except Exception as exc:
        return {"success": False, "message": f"Google search failed: {str(exc)[:80]}"}


def search_youtube(query: str) -> Dict[str, str]:
    """Search YouTube in the default browser."""
    if not query:
        return {"success": False, "message": "No YouTube search query"}
    try:
        url = f"https://www.youtube.com/results?search_query={urllib.parse.quote_plus(query)}"
        webbrowser.open(url)
        logger.info(f"[BROWSER] YouTube search: {query!r}")
        return {"success": True, "message": f"Searched YouTube: {query}"}
    except Exception as exc:
        return {"success": False, "message": f"YouTube search failed: {str(exc)[:80]}"}


def play_youtube(query: str) -> Dict[str, str]:
    """
    Open YouTube search results (with autoplay flag).
    No scraping — uses webbrowser.open() only.
    """
    if not query:
        return {"success": False, "message": "No video query"}
    try:
        encoded = urllib.parse.quote_plus(query)
        url = f"https://www.youtube.com/results?search_query={encoded}&autoplay=1"
        webbrowser.open(url)
        logger.info(f"[BROWSER] YouTube play: {query!r}")
        return {"success": True, "message": f"Playing on YouTube: {query}"}
    except Exception as exc:
        return {"success": False, "message": f"YouTube play failed: {str(exc)[:80]}"}


# Alias kept for backward compatibility
play_youtube_video = play_youtube

__all__ = ["open_url", "search_google", "search_youtube", "play_youtube", "play_youtube_video"]
