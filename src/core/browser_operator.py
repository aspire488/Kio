"""
Browser Operator - Handle browser actions like YouTube play, search, etc.

Functions:
- open_url: Open any URL in default browser
- search_google: Search Google
- search_youtube: Search YouTube
- play_youtube_video: Play YouTube video by search query
"""

import logging
import urllib.parse
import webbrowser
from typing import Dict

logger = logging.getLogger(__name__)


def open_url(url: str) -> Dict[str, str]:
    """
    Open a URL in the default web browser.

    Args:
        url: The URL to open

    Returns:
        {"success": bool, "message": str}
    """
    try:
        if not url.startswith(('http://', 'https://')):
            url = 'https://' + url
        webbrowser.open(url)
        logger.info(f"[BROWSER] opened URL: {url}")
        return {"success": True, "message": f"Opened {url}"}
    except Exception as e:
        logger.error(f"[BROWSER] failed to open URL {url}: {e}")
        return {"success": False, "message": f"Failed to open {url}: {str(e)[:80]}"}


def search_google(query: str) -> Dict[str, str]:
    """
    Search Google in the default browser.

    Args:
        query: Search query

    Returns:
        {"success": bool, "message": str}
    """
    if not query:
        return {"success": False, "message": "No search query"}

    try:
        encoded = urllib.parse.quote_plus(query)
        url = f"https://www.google.com/search?q={encoded}"
        webbrowser.open(url)
        logger.info(f"[BROWSER] searched Google: {query}")
        return {"success": True, "message": f"Searched Google: {query}"}
    except Exception as e:
        logger.error(f"[BROWSER] Google search failed for {query}: {e}")
        return {"success": False, "message": f"Google search failed: {str(e)[:80]}"}


def search_youtube(query: str) -> Dict[str, str]:
    """
    Search YouTube in the default browser.

    Args:
        query: Search query

    Returns:
        {"success": bool, "message": str}
    """
    if not query:
        return {"success": False, "message": f"No YouTube search query"}

    try:
        encoded = urllib.parse.quote_plus(query)
        url = f"https://www.youtube.com/results?search_query={encoded}"
        webbrowser.open(url)
        logger.info(f"[BROWSER] searched YouTube: {query}")
        return {"success": True, "message": f"Searched YouTube: {query}"}
    except Exception as e:
        logger.error(f"[BROWSER] YouTube search failed for {query}: {e}")
        return {"success": False, "message": f"YouTube search failed: {str(e)[:80]}"}


def play_youtube(query: str) -> Dict[str, str]:
    """
    Open YouTube search results with autoplay.
    Uses lightweight redirect without scraping.

    Args:
        query: Video search query

    Returns:
        {"success": bool, "message": str}
    """
    if not query:
        return {"success": False, "message": "No video query"}

    try:
        encoded = urllib.parse.quote_plus(query)
        url = f"https://www.youtube.com/results?search_query={encoded}&autoplay=1"
        webbrowser.open(url)
        logger.info(f"[BROWSER] playing YouTube: {query}")
        return {"success": True, "message": f"Playing on YouTube: {query}"}
    except Exception as e:
        logger.error(f"[BROWSER] YouTube play failed for {query}: {e}")
        return {"success": False, "message": f"YouTube play failed: {str(e)[:80]}"}


def play_youtube_video(query: str) -> Dict[str, str]:
    """
    Play a YouTube video by search query.
    Opens YouTube search results page.

    Args:
        query: Video search query (e.g., "messi highlights")

    Returns:
        {"success": bool, "message": str}
    """
    if not query:
        return {"success": False, "message": "No video query"}

    try:
        # For now, just search YouTube - in a more advanced implementation,
        # this could scrape the first result and open it directly
        encoded = urllib.parse.quote_plus(query)
        url = f"https://www.youtube.com/results?search_query={encoded}"
        webbrowser.open(url)
        logger.info(f"[BROWSER] playing YouTube video: {query}")
        return {"success": True, "message": f"Playing YouTube: {query}"}
    except Exception as e:
        logger.error(f"[BROWSER] YouTube play failed for {query}: {e}")
        return {"success": False, "message": f"YouTube play failed: {str(e)[:80]}"}


__all__ = ["open_url", "search_google", "search_youtube", "play_youtube", "play_youtube_video"]