"""BrowserFacade implementation.

Provides a thin wrapper conforming to the internal_api BrowserFacade protocol.
All heavy lifting is delegated to existing mini_kio core browser_operator functions.
"""

from __future__ import annotations

import json
from typing import Any

# Import the existing browser_operator functions for actual work.
from mini_kio.core import browser_operator as bo

class BrowserFacadeImpl:
    """Concrete implementation of the BrowserFacade protocol.

    Implements only the required methods with minimal behaviour.
    """

    def navigate(self, url: str) -> None:
        """Navigate to a URL using the best available backend.
        """
        # Reuse the existing browser_goto which handles connector/runtime/fallback.
        bo.browser_goto(url)

    def click(self, selector: str) -> None:
        """Click an element identified by a CSS or XPath selector.
        """
        # Use the generic browser_click handler which expects a JSON string.
        payload = json.dumps({"selector": selector})
        bo.browser_click(payload)

    def get_text(self, selector: str) -> str:
        """Return text content of element identified by selector.
        """
        payload = json.dumps({"selector": selector})
        result = bo.browser_extract_text(payload)
        # The handler returns a dict with a "content" key.
        return result.get("content", "")

__all__ = ["BrowserFacadeImpl"]
