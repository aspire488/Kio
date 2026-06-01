"""
browser_session_registry.py — Centralized Browser Canonicalization

Provides a single source of truth for:
- canonical browser target names (e.g., 'ig' -> 'instagram')
- browser-to-URL mapping
- active session tracking handles
"""

import logging
from typing import Optional, Dict

logger = logging.getLogger(__name__)

_CANONICAL_TARGETS = {
    "ig": "instagram",
    "insta": "instagram",
    "fb": "facebook",
    "yt": "youtube",
    "utube": "youtube",
    "goog": "google",
    "g": "google",
    "gpt": "chatgpt",
    "chat": "chatgpt",
}

_TARGET_URLS = {
    "instagram": "https://www.instagram.com",
    "facebook": "https://www.facebook.com",
    "youtube": "https://www.youtube.com",
    "google": "https://www.google.com",
    "chatgpt": "https://chat.openai.com",
    "github": "https://github.com",
    "reddit": "https://www.reddit.com",
    "twitter": "https://twitter.com",
    "x": "https://x.com",
}

class BrowserSessionRegistry:
    """Central registry for browser targets and session handles."""
    
    def __init__(self):
        self._active_sessions = {}
        self._diag = {
            "browser_canonicalization_used": 0
        }

    def canonicalize(self, target: str) -> str:
        """Resolve a target name to its canonical form."""
        target = target.lower().strip()
        canonical = _CANONICAL_TARGETS.get(target, target)
        if canonical != target:
            self._diag["browser_canonicalization_used"] += 1
        return canonical

    def get_url(self, target: str) -> Optional[str]:
        """Get the URL for a canonical target."""
        canonical = self.canonicalize(target)
        return _TARGET_URLS.get(canonical)

    def register_session(self, browser_id: str, session_data: dict):
        """Track an active browser session."""
        self._active_sessions[browser_id] = session_data

    def get_session(self, browser_id: str) -> Optional[dict]:
        """Retrieve tracking data for a browser session."""
        return self._active_sessions.get(browser_id)

    def unregister_session(self, browser_id: str):
        """Remove a tracked session."""
        if browser_id in self._active_sessions:
            del self._active_sessions[browser_id]

    def get_diagnostics(self) -> dict:
        return dict(self._diag)
