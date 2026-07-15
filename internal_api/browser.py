"""Browser facade protocol for internal API.

Adapters implement this protocol to provide browser interactions such as navigation,
clicking elements, and extracting text.
"""

from __future__ import annotations
from typing import Protocol


class BrowserFacade(Protocol):
    """Abstract browser operations used by the execution fabric."""

    def navigate(self, url: str) -> None: ...
    """Navigate to the specified URL."""

    def click(self, selector: str) -> None: ...
    """Click an element identified by a CSS or xpath selector."""

    def get_text(self, selector: str) -> str: ...
    """Return the text content of an element identified by selector."""
