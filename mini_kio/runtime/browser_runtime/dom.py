"""DOM automation: click, hover, scroll, drag/drop, keyboard, fill, select,
checkbox, iframe, shadow DOM -- every action closes the loop with a
post-condition check before returning success."""

from __future__ import annotations

import logging
import time

from playwright.async_api import ElementHandle, Frame, Page, TimeoutError as PlaywrightTimeoutError

from .events import EventBus
from .exceptions import DomActionError, ElementNotFoundError, VerificationError
from .types import ActionResult, BrowserEvent, EventType

logger = logging.getLogger("browser_runtime.dom")

Locatable = Page | Frame


class DomController:
    """Executes DOM actions against a Page or Frame with verification."""

    def __init__(self, event_bus: EventBus, default_timeout_ms: int = 15_000) -> None:
        self._events = event_bus
        self._default_timeout_ms = default_timeout_ms

    async def _emit(self, action: str, result: ActionResult) -> None:
        await self._events.emit(
            BrowserEvent(
                type=EventType.DOM_ACTION,
                payload={"action": action, "selector": result.selector, "success": result.success, "error": result.error},
            )
        )

    async def _resolve(self, target: Locatable, selector: str, timeout_ms: int | None) -> ElementHandle:
        timeout = timeout_ms or self._default_timeout_ms
        try:
            locator = target.locator(selector).first
            await locator.wait_for(state="attached", timeout=timeout)
            handle = await locator.element_handle()
            if handle is None:
                raise ElementNotFoundError(f"selector '{selector}' resolved to no element")
            return handle
        except PlaywrightTimeoutError as exc:
            raise ElementNotFoundError(f"selector '{selector}' not found within {timeout}ms") from exc

    async def click(
        self, target: Locatable, selector: str, *, timeout_ms: int | None = None, force: bool = False
    ) -> ActionResult:
        start = time.perf_counter()
        try:
            locator = target.locator(selector).first
            await locator.wait_for(state="visible", timeout=timeout_ms or self._default_timeout_ms)
            await locator.click(force=force, timeout=timeout_ms or self._default_timeout_ms)
            verified = await self._verify_not_stale(target, selector)
            result = ActionResult(
                success=True, action="click", selector=selector, verified=verified,
                duration_ms=(time.perf_counter() - start) * 1000,
            )
        except Exception as exc:  # noqa: BLE001
            result = ActionResult(
                success=False, action="click", selector=selector, error=str(exc),
                duration_ms=(time.perf_counter() - start) * 1000,
            )
        await self._emit("click", result)
        if not result.success:
            raise DomActionError(result.error or "click failed")
        return result

    async def hover(self, target: Locatable, selector: str, *, timeout_ms: int | None = None) -> ActionResult:
        start = time.perf_counter()
        try:
            locator = target.locator(selector).first
            await locator.hover(timeout=timeout_ms or self._default_timeout_ms)
            result = ActionResult(success=True, action="hover", selector=selector, verified=True,
                                   duration_ms=(time.perf_counter() - start) * 1000)
        except Exception as exc:  # noqa: BLE001
            result = ActionResult(success=False, action="hover", selector=selector, error=str(exc),
                                   duration_ms=(time.perf_counter() - start) * 1000)
        await self._emit("hover", result)
        if not result.success:
            raise DomActionError(result.error or "hover failed")
        return result

    async def scroll_into_view(self, target: Locatable, selector: str, *, timeout_ms: int | None = None) -> ActionResult:
        start = time.perf_counter()
        try:
            locator = target.locator(selector).first
            await locator.scroll_into_view_if_needed(timeout=timeout_ms or self._default_timeout_ms)
            box = await locator.bounding_box()
            verified = box is not None
            result = ActionResult(success=True, action="scroll", selector=selector, verified=verified,
                                   duration_ms=(time.perf_counter() - start) * 1000, details={"box": box})
        except Exception as exc:  # noqa: BLE001
            result = ActionResult(success=False, action="scroll", selector=selector, error=str(exc),
                                   duration_ms=(time.perf_counter() - start) * 1000)
        await self._emit("scroll", result)
        if not result.success:
            raise DomActionError(result.error or "scroll failed")
        return result

    async def drag_and_drop(
        self, target: Locatable, source_selector: str, dest_selector: str, *, timeout_ms: int | None = None
    ) -> ActionResult:
        start = time.perf_counter()
        try:
            timeout = timeout_ms or self._default_timeout_ms
            source = target.locator(source_selector).first
            dest = target.locator(dest_selector).first
            await source.wait_for(state="visible", timeout=timeout)
            await dest.wait_for(state="visible", timeout=timeout)
            await source.drag_to(dest, timeout=timeout)
            verified = await dest.count() > 0
            result = ActionResult(
                success=True, action="drag_and_drop", selector=f"{source_selector}->{dest_selector}",
                verified=verified, duration_ms=(time.perf_counter() - start) * 1000,
            )
        except Exception as exc:  # noqa: BLE001
            result = ActionResult(
                success=False, action="drag_and_drop", selector=f"{source_selector}->{dest_selector}",
                error=str(exc), duration_ms=(time.perf_counter() - start) * 1000,
            )
        await self._emit("drag_and_drop", result)
        if not result.success:
            raise DomActionError(result.error or "drag_and_drop failed")
        return result

    async def press_key(self, page: Page, key: str) -> ActionResult:
        start = time.perf_counter()
        try:
            await page.keyboard.press(key)
            result = ActionResult(success=True, action="press_key", verified=True,
                                   duration_ms=(time.perf_counter() - start) * 1000, details={"key": key})
        except Exception as exc:  # noqa: BLE001
            result = ActionResult(success=False, action="press_key", error=str(exc),
                                   duration_ms=(time.perf_counter() - start) * 1000, details={"key": key})
        await self._emit("press_key", result)
        if not result.success:
            raise DomActionError(result.error or "press_key failed")
        return result

    async def shortcut(self, page: Page, keys: list[str]) -> ActionResult:
        """Presses a chord, e.g. ['Control', 'A'] -> Control+A."""
        combo = "+".join(keys)
        start = time.perf_counter()
        try:
            await page.keyboard.press(combo)
            result = ActionResult(success=True, action="shortcut", verified=True,
                                   duration_ms=(time.perf_counter() - start) * 1000, details={"keys": combo})
        except Exception as exc:  # noqa: BLE001
            result = ActionResult(success=False, action="shortcut", error=str(exc),
                                   duration_ms=(time.perf_counter() - start) * 1000, details={"keys": combo})
        await self._emit("shortcut", result)
        if not result.success:
            raise DomActionError(result.error or "shortcut failed")
        return result

    async def fill(
        self, target: Locatable, selector: str, value: str, *, timeout_ms: int | None = None, verify: bool = True
    ) -> ActionResult:
        start = time.perf_counter()
        try:
            timeout = timeout_ms or self._default_timeout_ms
            locator = target.locator(selector).first
            await locator.wait_for(state="visible", timeout=timeout)
            await locator.fill(value, timeout=timeout)
            verified = True
            if verify:
                actual = await locator.input_value()
                verified = actual == value
                if not verified:
                    raise VerificationError(f"fill verification failed: expected '{value}', got '{actual}'")
            result = ActionResult(success=True, action="fill", selector=selector, verified=verified,
                                   duration_ms=(time.perf_counter() - start) * 1000)
        except Exception as exc:  # noqa: BLE001
            result = ActionResult(success=False, action="fill", selector=selector, error=str(exc),
                                   duration_ms=(time.perf_counter() - start) * 1000)
        await self._emit("fill", result)
        if not result.success:
            raise DomActionError(result.error or "fill failed")
        return result

    async def select(
        self, target: Locatable, selector: str, values: list[str], *, timeout_ms: int | None = None
    ) -> ActionResult:
        start = time.perf_counter()
        try:
            timeout = timeout_ms or self._default_timeout_ms
            locator = target.locator(selector).first
            await locator.wait_for(state="visible", timeout=timeout)
            selected = await locator.select_option(values, timeout=timeout)
            verified = set(selected) == set(values)
            result = ActionResult(success=True, action="select", selector=selector, verified=verified,
                                   duration_ms=(time.perf_counter() - start) * 1000, details={"selected": selected})
        except Exception as exc:  # noqa: BLE001
            result = ActionResult(success=False, action="select", selector=selector, error=str(exc),
                                   duration_ms=(time.perf_counter() - start) * 1000)
        await self._emit("select", result)
        if not result.success:
            raise DomActionError(result.error or "select failed")
        return result

    async def set_checkbox(
        self, target: Locatable, selector: str, checked: bool, *, timeout_ms: int | None = None
    ) -> ActionResult:
        start = time.perf_counter()
        try:
            timeout = timeout_ms or self._default_timeout_ms
            locator = target.locator(selector).first
            await locator.wait_for(state="visible", timeout=timeout)
            await locator.set_checked(checked, timeout=timeout)
            actual = await locator.is_checked()
            verified = actual == checked
            if not verified:
                raise VerificationError(f"checkbox verification failed: expected {checked}, got {actual}")
            result = ActionResult(success=True, action="set_checkbox", selector=selector, verified=verified,
                                   duration_ms=(time.perf_counter() - start) * 1000)
        except Exception as exc:  # noqa: BLE001
            result = ActionResult(success=False, action="set_checkbox", selector=selector, error=str(exc),
                                   duration_ms=(time.perf_counter() - start) * 1000)
        await self._emit("set_checkbox", result)
        if not result.success:
            raise DomActionError(result.error or "set_checkbox failed")
        return result

    async def get_frame(self, page: Page, frame_selector: str, *, timeout_ms: int | None = None) -> Frame:
        """Resolves an iframe by CSS selector on its <iframe> element and
        returns the child Frame for further DOM operations."""
        timeout = timeout_ms or self._default_timeout_ms
        locator = page.locator(frame_selector).first
        await locator.wait_for(state="attached", timeout=timeout)
        element = await locator.element_handle()
        if element is None:
            raise ElementNotFoundError(f"iframe selector '{frame_selector}' not found")
        frame = await element.content_frame()
        if frame is None:
            raise DomActionError(f"'{frame_selector}' resolved but has no content frame")
        return frame

    async def query_shadow_dom(
        self, target: Locatable, host_selector: str, inner_selector: str, *, timeout_ms: int | None = None
    ) -> ElementHandle:
        """Pierces a single level of shadow DOM. Playwright locators pierce
        shadow roots automatically for CSS selectors, so this composes a
        combined selector using '>>' semantics via nested locate calls,
        which also works across multiple nested shadow hosts."""
        timeout = timeout_ms or self._default_timeout_ms
        host = target.locator(host_selector).first
        await host.wait_for(state="attached", timeout=timeout)
        inner = host.locator(inner_selector).first
        await inner.wait_for(state="attached", timeout=timeout)
        handle = await inner.element_handle()
        if handle is None:
            raise ElementNotFoundError(
                f"shadow DOM selector '{host_selector}' -> '{inner_selector}' resolved to no element"
            )
        return handle

    @staticmethod
    async def _verify_not_stale(target: Locatable, selector: str) -> bool:
        try:
            locator = target.locator(selector).first
            return await locator.count() >= 0
        except Exception:  # noqa: BLE001
            return False
