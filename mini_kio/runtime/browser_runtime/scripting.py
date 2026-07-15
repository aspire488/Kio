"""JavaScript evaluation/injection, console capture, extraction, screenshots, PDF."""

from __future__ import annotations

import logging
import time
from pathlib import Path
from typing import Any

from playwright.async_api import ConsoleMessage, Page

from .events import EventBus
from .exceptions import ScriptingError
from .types import BrowserEvent, EventType

logger = logging.getLogger("browser_runtime.scripting")


class ScriptingController:
    """Runs JS against a Page and extracts content/artifacts."""

    def __init__(self, event_bus: EventBus) -> None:
        self._events = event_bus
        self._console_logs: dict[int, list[dict[str, Any]]] = {}

    def attach_console_capture(self, page: Page) -> None:
        page_id = id(page)
        self._console_logs.setdefault(page_id, [])

        def _on_console(msg: ConsoleMessage) -> None:
            self._console_logs[page_id].append(
                {"type": msg.type, "text": msg.text, "location": msg.location, "timestamp": time.time()}
            )

        page.on("console", _on_console)
        page.on("pageerror", lambda exc: self._console_logs[page_id].append(
            {"type": "pageerror", "text": str(exc), "timestamp": time.time()}
        ))

    def get_console_logs(self, page: Page) -> list[dict[str, Any]]:
        return list(self._console_logs.get(id(page), []))

    def clear_console_logs(self, page: Page) -> None:
        self._console_logs[id(page)] = []

    async def evaluate(self, page: Page, expression: str, arg: Any = None) -> Any:
        try:
            if arg is None:
                return await page.evaluate(expression)
            return await page.evaluate(expression, arg)
        except Exception as exc:  # noqa: BLE001
            await self._events.emit(BrowserEvent(type=EventType.ERROR, payload={"stage": "evaluate", "error": str(exc)}))
            raise ScriptingError(f"evaluate failed: {exc}") from exc

    async def inject_script(self, page: Page, *, path: str | None = None, content: str | None = None) -> None:
        if not path and not content:
            raise ScriptingError("inject_script requires either 'path' or 'content'")
        try:
            if path:
                await page.add_script_tag(path=path)
            else:
                await page.add_script_tag(content=content)
        except Exception as exc:  # noqa: BLE001
            raise ScriptingError(f"inject_script failed: {exc}") from exc

    async def extract_text(self, page: Page, selector: str | None = None) -> str:
        try:
            if selector:
                return await page.locator(selector).first.inner_text()
            return await page.evaluate("document.body ? document.body.innerText : ''")
        except Exception as exc:  # noqa: BLE001
            raise ScriptingError(f"extract_text failed: {exc}") from exc

    async def extract_html(self, page: Page, selector: str | None = None) -> str:
        try:
            if selector:
                return await page.locator(selector).first.inner_html()
            return await page.content()
        except Exception as exc:  # noqa: BLE001
            raise ScriptingError(f"extract_html failed: {exc}") from exc

    async def screenshot(
        self, page: Page, save_path: Path, *, full_page: bool = True, selector: str | None = None
    ) -> Path:
        try:
            save_path.parent.mkdir(parents=True, exist_ok=True)
            if selector:
                await page.locator(selector).first.screenshot(path=str(save_path))
            else:
                await page.screenshot(path=str(save_path), full_page=full_page)
            return save_path
        except Exception as exc:  # noqa: BLE001
            raise ScriptingError(f"screenshot failed: {exc}") from exc

    async def pdf(self, page: Page, save_path: Path, *, landscape: bool = False, print_background: bool = True) -> Path:
        try:
            save_path.parent.mkdir(parents=True, exist_ok=True)
            await page.pdf(path=str(save_path), landscape=landscape, print_background=print_background)
            return save_path
        except Exception as exc:  # noqa: BLE001
            raise ScriptingError(f"pdf export failed (headless Chromium required): {exc}") from exc
