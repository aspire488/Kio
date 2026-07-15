"""BrowserBackend protocol placeholder.

Defines the interface for backend implementations used by BrowserFacade.
No concrete logic is required for the current batch – backends can be
selected lazily inside BrowserFacade if needed.
"""

from __future__ import annotations
from typing import Protocol

class BrowserBackend(Protocol):
    """Minimal protocol for a browser backend.

    Implementations may provide methods such as ``start`` and ``shutdown``.
    """

    def start(self) -> None: ...
    def shutdown(self) -> None: ...
    def health(self) -> dict[str, Any]: ...

__all__ = ["BrowserBackend"]
