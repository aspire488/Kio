"""
registry.py - Browser Connector V1 Tab Registry

Runtime-memory-only tab ownership tracking.

Rules:
- Only tabs opened via connector open_tab may enter the registry.
- User tabs (opened manually in Chrome) must NEVER be registered.
- No persistence, no disk storage, no database.
"""

from __future__ import annotations

import logging
from typing import Optional
from urllib.parse import urlparse

from .protocol import OwnedTab

logger = logging.getLogger(__name__)


class TabRegistry:
    """In-memory registry of KIO-owned browser tabs.

    Thread-safe for single-threaded asyncio usage.
    """

    def __init__(self):
        self._tabs: dict[int, OwnedTab] = {}  # tab_id → OwnedTab

    # ── Mutation ─────────────────────────────────────────────────────

    def add(self, tab: OwnedTab) -> None:
        """Register a KIO-owned tab.

        Must only be called after the extension confirms the tab was
        created by a connector open_tab command.
        """
        if not isinstance(tab, OwnedTab):
            raise TypeError("expected OwnedTab instance")
        if tab.tab_id < 1:
            raise ValueError(f"invalid tab_id: {tab.tab_id}")
        self._tabs[tab.tab_id] = tab
        logger.info("[REGISTRY] added tab %d: %s", tab.tab_id, tab.url)

    def remove(self, tab_id: int) -> Optional[OwnedTab]:
        """Remove a tab from the registry.

        Called when:
        - Connector confirms close_tab succeeded
        - Extension reports tab_closed (user closed tab manually)
        """
        tab = self._tabs.pop(tab_id, None)
        if tab:
            logger.info("[REGISTRY] removed tab %d: %s", tab_id, tab.url)
        return tab

    def update_url(self, tab_id: int, url: str, title: str = "") -> bool:
        """Update a tab's URL and title (from tab_updated event)."""
        tab = self._tabs.get(tab_id)
        if tab is None:
            return False
        tab.url = url
        if title:
            tab.title = title
        return True

    def clear(self) -> None:
        """Remove all entries. Called on Chrome restart or disconnect."""
        self._tabs.clear()
        logger.info("[REGISTRY] cleared all tabs")

    # ── Lookup ───────────────────────────────────────────────────────

    def get(self, tab_id: int) -> Optional[OwnedTab]:
        """Get a tab by its Chrome tab ID."""
        return self._tabs.get(tab_id)

    def find_by_url(self, url: str) -> Optional[OwnedTab]:
        """Find a tab by exact URL match."""
        for tab in self._tabs.values():
            if tab.url == url:
                return tab
        return None

    def find_by_domain(self, domain: str) -> list[OwnedTab]:
        """Find all tabs matching a domain.

        Supports bidirectional domain matching:
          "youtube.com" matches "www.youtube.com"
          "www.youtube.com" matches "youtube.com"
        """
        target = domain.lower().strip().rstrip("/").replace(" ", "")
        if not target:
            return []
            
        results = []
        for tab in self._tabs.values():
            try:
                parsed = urlparse(tab.url)
                host = (parsed.hostname or "").lower()
            except Exception:
                continue
            
            if not host:
                continue

            # Bidirectional suffix matching
            if target == host or host.endswith("." + target) or target.endswith("." + host):
                results.append(tab)
        return results

    def find_by_text(self, text: str) -> list[OwnedTab]:
        """Find tabs by text match in URL or title."""
        text_norm = text.lower().replace(" ", "")
        results = []
        for tab in self._tabs.values():
            if text_norm in tab.url.lower().replace(" ", "") or \
               text_norm in tab.title.lower().replace(" ", ""):
                results.append(tab)
        return results

    def resolve(self, target: str) -> Optional[OwnedTab]:
        """Flexible lookup: exact URL → domain → text match.

        Returns the best match or None.
        """
        # Exact URL match
        tab = self.find_by_url(target)
        if tab:
            return tab

        # Try as domain
        domain_matches = self.find_by_domain(target)
        if len(domain_matches) == 1:
            return domain_matches[0]

        # Text match
        text_matches = self.find_by_text(target)
        if len(text_matches) == 1:
            return text_matches[0]

        # Multiple matches - return first
        if domain_matches:
            return domain_matches[0]
        if text_matches:
            return text_matches[0]

        return None

    def list_all(self) -> list[OwnedTab]:
        """Return all owned tabs, newest first."""
        return sorted(self._tabs.values(),
                      key=lambda t: t.created_at, reverse=True)

    # ── Queries ──────────────────────────────────────────────────────

    def owned_count(self) -> int:
        """Number of tabs in the registry."""
        return len(self._tabs)

    def is_owned(self, tab_id: int) -> bool:
        """Check if a tab_id is owned by KIO."""
        return tab_id in self._tabs

    def validate_ownership(self, tab_id: int, url: str = "") -> bool:
        """Validate that a tab is owned AND optionally matches URL.

        This is the core ownership enforcement check.
        """
        tab = self._tabs.get(tab_id)
        if tab is None:
            return False
        if url and tab.url != url:
            return False
        return True
