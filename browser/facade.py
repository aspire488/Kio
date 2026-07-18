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

    def extract_dom(self) -> Any:
        """Return a structured DOM representation of the current page.

        Uses the existing `browser_extract_html` operator to obtain the raw HTML
        of the active tab and then delegates parsing to the Scrapling adapter.
        This provides a minimal *structured extraction* capability for the
        BrowserFacade without pulling in the full Scrapling API surface.
        """
        # Get raw HTML of the current page (no selector → full page).
        payload = json.dumps({})
        html_result = bo.browser_extract_html(payload)
        html = html_result.get("content", "")
        if not html:
            return {"status": False, "error": "no html retrieved"}
        try:
            # Lazy import to avoid hard dependency at module load.
            from adapters.scrapling.adapter import Adapter as ScraplingAdapter
            scrap = ScraplingAdapter()
            dom = scrap.extract_dom(html)
            return {"status": True, "dom": dom}
        except Exception as exc:
            # ponytail: placeholder – replace with full extraction pipeline when needed
            return {"status": False, "error": str(exc)}

    def extract_tables(self, selector: str) -> Any:
        """Extract HTML tables from the current page (or a sub‑selector).

        Retrieves the HTML for the given selector via `browser_extract_html`
        and then forwards the DOM to Scrapling's `extract_tables` helper.
        Returns a dict with ``status`` and ``tables`` (list) on success.
        """
        payload = json.dumps({"selector": selector})
        html_result = bo.browser_extract_html(payload)
        html = html_result.get("content", "")
        if not html:
            return {"status": False, "error": "no html retrieved"}
        try:
            from adapters.scrapling.adapter import Adapter as ScraplingAdapter
            scrap = ScraplingAdapter()
            dom = scrap.extract_dom(html)
            tables = scrap.extract_tables(dom)
            return {"status": True, "tables": tables}
        except Exception as exc:
            # ponytail: placeholder – replace with full table‑extraction pipeline when needed
            return {"status": False, "error": str(exc)}

    def extract_links(self, selector: str) -> Any:
        """Extract anchor links (href) from the current page (or a sub‑selector).

        Uses `browser_extract_html` to obtain HTML for the selector, then
        delegates to Scrapling's `extract_links` helper which returns a list of
        URL strings.
        """
        payload = json.dumps({"selector": selector})
        html_result = bo.browser_extract_html(payload)
        html = html_result.get("content", "")
        if not html:
            return {"status": False, "error": "no html retrieved"}
        try:
            from adapters.scrapling.adapter import Adapter as ScraplingAdapter
            scrap = ScraplingAdapter()
            dom = scrap.extract_dom(html)
            links = scrap.extract_links(dom)
            return {"status": True, "links": links}
        except Exception as exc:
            # ponytail: placeholder – replace with full link‑extraction pipeline when needed
            return {"status": False, "error": str(exc)}

__all__ = ["BrowserFacadeImpl"]
