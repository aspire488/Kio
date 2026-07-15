"""Navigation with retries, timeout handling, and verification."""

from __future__ import annotations

import asyncio
import logging
import time
import urllib.parse

from playwright.async_api import Page, TimeoutError as PlaywrightTimeoutError

from .events import EventBus
from .exceptions import NavigationError, NavigationTimeoutError
from .types import BrowserEvent, EventType, NavigationResult

logger = logging.getLogger("browser_runtime.navigation")


class Navigator:
    """Navigates pages with automatic retry and post-navigation verification."""

    def __init__(self, event_bus: EventBus, default_timeout_ms: int = 30_000, max_retries: int = 3) -> None:
        self._events = event_bus
        self._default_timeout_ms = default_timeout_ms
        self._max_retries = max_retries

    async def goto(
        self,
        page: Page,
        url: str,
        *,
        wait_until: str = "domcontentloaded",
        timeout_ms: int | None = None,
        max_retries: int | None = None,
        verify_substring: str | None = None,
    ) -> NavigationResult:
        timeout = timeout_ms or self._default_timeout_ms
        retries = max_retries if max_retries is not None else self._max_retries
        start = time.perf_counter()
        await self._events.emit(BrowserEvent(type=EventType.NAVIGATION_STARTED, payload={"url": url}))

        last_error: str | None = None
        for attempt in range(1, retries + 1):
            try:
                response = await page.goto(url, wait_until=wait_until, timeout=timeout)
                status_code = response.status if response else None
                ok = await self._verify(page, url, verify_substring)
                duration_ms = (time.perf_counter() - start) * 1000
                if not ok:
                    last_error = "post-navigation verification failed"
                    logger.warning("navigation verification failed for %s (attempt %d/%d)", url, attempt, retries)
                    if attempt < retries:
                        await asyncio.sleep(min(2 ** attempt, 8))
                        continue
                    result = NavigationResult(
                        success=False,
                        url=url,
                        final_url=page.url,
                        status_code=status_code,
                        attempts=attempt,
                        duration_ms=duration_ms,
                        error=last_error,
                    )
                    await self._events.emit(
                        BrowserEvent(type=EventType.NAVIGATION_FAILED, payload={"url": url, "error": last_error})
                    )
                    return result

                result = NavigationResult(
                    success=True,
                    url=url,
                    final_url=page.url,
                    status_code=status_code,
                    attempts=attempt,
                    duration_ms=duration_ms,
                )
                await self._events.emit(
                    BrowserEvent(
                        type=EventType.NAVIGATION_SUCCEEDED,
                        payload={"url": url, "final_url": page.url, "status_code": status_code},
                    )
                )
                return result
            except PlaywrightTimeoutError as exc:
                last_error = f"timeout: {exc}"
                logger.warning("navigation timeout for %s (attempt %d/%d)", url, attempt, retries)
            except Exception as exc:  # noqa: BLE001
                last_error = str(exc)
                logger.warning("navigation error for %s (attempt %d/%d): %s", url, attempt, retries, exc)

            if attempt < retries:
                await asyncio.sleep(min(2 ** attempt, 8))

        duration_ms = (time.perf_counter() - start) * 1000
        await self._events.emit(BrowserEvent(type=EventType.NAVIGATION_FAILED, payload={"url": url, "error": last_error}))
        if last_error and last_error.startswith("timeout"):
            raise NavigationTimeoutError(f"navigation to {url} timed out after {retries} attempts: {last_error}")
        raise NavigationError(f"navigation to {url} failed after {retries} attempts: {last_error}")

    async def search(self, page: Page, engine_url_template: str, query: str, **goto_kwargs) -> NavigationResult:
        """engine_url_template must contain a '{query}' placeholder, e.g.
        'https://duckduckgo.com/?q={query}'."""
        url = engine_url_template.format(query=urllib.parse.quote_plus(query))
        return await self.goto(page, url, **goto_kwargs)

    @staticmethod
    async def _verify(page: Page, requested_url: str, verify_substring: str | None) -> bool:
        try:
            if verify_substring is not None:
                content = await page.content()
                if verify_substring not in content:
                    return False
            # basic sanity: the page did not land on about:blank unless requested
            if page.url == "about:blank" and requested_url != "about:blank":
                return False
            return True
        except Exception:  # noqa: BLE001
            return False
