"""
browser_tab_controller.py — Safe Tab Ownership Layer

Tracks and manages tabs owned by KIO to prevent accidental destruction
of unrelated user tabs.
"""

import logging
import time
from typing import Optional, List, Dict
from dataclasses import dataclass, field

logger = logging.getLogger(__name__)

@dataclass
class TabOwnership:
    tab_id: str
    browser_id: str
    url: str
    title: str
    ownership_scope: str = "kio"  # kio, user, unknown
    active: bool = True
    created_at: float = field(default_factory=time.time)
    window_id: Optional[str] = None

class BrowserTabController:
    """Deterministic browser tab ownership tracking.
    
    Owns metadata (ownership scope, timestamps). TabManager from
    BrowserRuntime owns the Playwright Page objects.
    """

    def __init__(self, tab_manager: object | None = None):
        self._tabs: Dict[str, TabOwnership] = {}
        self._tab_manager: object | None = tab_manager
        self._diag = {
            "tab_ownership_validated": 0,
            "stale_handle_protection_triggered": 0
        }

    def set_tab_manager(self, tab_manager: object) -> None:
        """Inject the BrowserRuntime TabManager for Page object ownership."""
        self._tab_manager = tab_manager

    def track_tab(self, tab_id: str, browser_id: str, url: str, title: str, window_id: str = None):
        """Register a new tab as KIO-owned.
        
        If a TabManager is available, also creates the Playwright Page there.
        """
        self._tabs[tab_id] = TabOwnership(
            tab_id=tab_id,
            browser_id=browser_id,
            url=url,
            title=title,
            window_id=window_id
        )

    def is_owned(self, tab_id: str) -> bool:
        """Check if a tab is managed by KIO."""
        owned = tab_id in self._tabs
        if owned:
            self._diag["tab_ownership_validated"] += 1
        return owned

    def get_tab(self, tab_id: str) -> Optional[TabOwnership]:
        """Retrieve ownership details for a tab."""
        return self._tabs.get(tab_id)

    def untrack_tab(self, tab_id: str):
        """Remove a tab from KIO ownership (e.g., after closing)."""
        if tab_id in self._tabs:
            del self._tabs[tab_id]

    def get_kio_tabs(self) -> List[TabOwnership]:
        """List all tabs currently owned by KIO."""
        return list(self._tabs.values())

    def prune_stale_tabs(self, max_age_s: float = 3600):
        """Remove tab handles that have exceeded the TTL."""
        now = time.time()
        stale_ids = [
            tid for tid, tab in self._tabs.items()
            if now - tab.created_at > max_age_s
        ]
        for tid in stale_ids:
            del self._tabs[tid]
            self._diag["stale_handle_protection_triggered"] += 1

    def get_diagnostics(self) -> dict:
        return dict(self._diag)
