"""Tab management for BrowserFacade.

Only minimal stubs are needed for compilation.
"""

from __future__ import annotations

def list_tabs() -> list[int]:
    """Return a list of tab identifiers.
    Uses the runtime BrowserRuntime if available, otherwise empty list.
    """
    try:
        from mini_kio.core.runtime import get_runtime
        rt = get_runtime()
        br = rt.browser_runtime if rt else None
        if br:
            return list(br.tabs.tabs.keys())
    except Exception:
        pass
    return []

def close_tab(tab_id: int) -> bool:
    """Close a tab by id – placeholder returns False.
    """
    return False

__all__ = ["list_tabs", "close_tab"]
