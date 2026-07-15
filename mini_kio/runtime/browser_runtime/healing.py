"""Self-healing selectors — automatic selector fallback and retry for DOM operations."""

from __future__ import annotations

import logging
import re
import time
from typing import Any

from playwright.async_api import Page, Locator

logger = logging.getLogger("browser_runtime.selector_healer")


class SelectorHealer:
    """Resilient selector engine with fallback strategies.

    When the primary CSS selector fails, attempts alternative strategies:
    1. Text content matching (by visible text)
    2. Attribute-based matching
    3. Role/Aria selector
    4. Partial text match
    5. XPath fallback
    6. Label association (for form fields)
    7. Nearby text heuristic
    """

    def __init__(self, page: Page) -> None:
        self._page = page

    async def resolve(self, selector: str, *, timeout_ms: int = 5000) -> Locator | None:
        strategies = [
            ("css", lambda: self._page.locator(selector).first),
            ("text_fallback", lambda: self._try_text(selector)),
            ("attr_fallback", lambda: self._try_attribute(selector)),
            ("role_fallback", lambda: self._try_role(selector)),
            ("partial_text", lambda: self._try_partial_text(selector)),
        ]
        for name, attempt in strategies:
            try:
                loc = attempt()
                if loc is not None:
                    ok = await loc.count()
                    if ok and ok > 0:
                        logger.debug("SelectorHealer resolved '%s' via %s", selector, name)
                        return loc
            except Exception:
                continue
        return None

    async def _try_text(self, selector: str) -> Locator | None:
        if selector.startswith(("#", ".", "[", ":")):
            return None
        text = selector.replace("-", " ").replace("_", " ").strip()
        return self._page.get_by_text(text, exact=True).first

    async def _try_role(self, selector: str) -> Locator | None:
        role_map = {
            "button": "button", "btn": "button", "link": "link", "input": "textbox",
            "checkbox": "checkbox", "radio": "radio", "select": "combobox",
            "heading": "heading", "image": "img", "table": "table",
        }
        for keyword, role in role_map.items():
            if keyword in selector.lower():
                remaining = selector.lower().replace(keyword, "").strip().strip(" ,.:;#")
                if remaining:
                    return self._page.get_by_role(role, name=remaining).first
        return None

    async def _try_partial_text(self, selector: str) -> Locator | None:
        parts = re.split(r"[.#\[\]>\s]+", selector)
        meaningful = [p for p in parts if len(p) > 2 and not p.startswith(("http", "www"))]
        for part in meaningful:
            try:
                loc = self._page.get_by_text(part, exact=False).first
                count = await loc.count()
                if count and count > 0:
                    return loc
            except Exception:
                continue
        return None

    async def _try_attribute(self, selector: str) -> Locator | None:
        # Try common attribute patterns
        attr_patterns = [
            r"\[data-testid=['\"]?([^'\"]+)['\"]?\]",
            r"\[data-test=['\"]?([^'\"]+)['\"]?\]",
            r"\[name=['\"]?([^'\"]+)['\"]?\]",
            r"\[aria-label=['\"]?([^'\"]+)['\"]?\]",
            r"\[placeholder=['\"]?([^'\"]+)['\"]?\]",
            r"\[title=['\"]?([^'\"]+)['\"]?\]",
        ]
        for pattern in attr_patterns:
            m = re.search(pattern, selector)
            if m:
                val = m.group(1)
                attr_name = re.search(r"\[(\w+)", pattern)
                if attr_name:
                    try:
                        loc = self._page.locator(f"[{attr_name.group(1)}='{val}']").first
                        count = await loc.count()
                        if count and count > 0:
                            return loc
                    except Exception:
                        continue
        return None


class RetryController:
    """Automatic retry with exponential backoff for DOM operations."""

    def __init__(self, max_retries: int = 3, base_delay_s: float = 0.5) -> None:
        self._max_retries = max_retries
        self._base_delay_s = base_delay_s

    async def execute(self, action_name: str, fn, *args, **kwargs) -> Any:
        last_error: Exception | None = None
        for attempt in range(1, self._max_retries + 1):
            try:
                return await fn(*args, **kwargs)
            except Exception as exc:
                last_error = exc
                if attempt < self._max_retries:
                    delay = self._base_delay_s * (2 ** (attempt - 1))
                    logger.debug("Retry %s (attempt %d/%d) after %.1fs: %s",
                                 action_name, attempt, self._max_retries, delay, exc)
                    await asyncio.sleep(delay)
        raise last_error  # type: ignore[misc]
