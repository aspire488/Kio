"""Navigation utilities for BrowserFacade.

Provides simple wrappers that delegate to the underlying backend.
Currently these are thin pass‑throughs using the existing browser_operator.
"""

from __future__ import annotations

from mini_kio.core import browser_operator as bo

def navigate(url: str) -> None:
    bo.browser_goto(url)

def back() -> None:
    # Placeholder – could be implemented via a backend method.
    pass

def forward() -> None:
    pass

__all__ = ["navigate", "back", "forward"]
