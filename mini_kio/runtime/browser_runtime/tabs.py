"""Multi-tab management: create, close, switch, duplicate, pin, history."""

from __future__ import annotations

import asyncio
import logging

from playwright.async_api import BrowserContext, Page

from .events import EventBus
from .exceptions import TabNotFoundError
from .types import BrowserEvent, EventType, TabInfo

logger = logging.getLogger("browser_runtime.tabs")


class TabManager:
    """Tracks Playwright Pages per workspace and exposes tab-level ops."""

    def __init__(self, event_bus: EventBus) -> None:
        self._events = event_bus
        self._pages: dict[str, Page] = {}
        self._info: dict[str, TabInfo] = {}
        self._active_tab_id: str | None = None
        self._pinned: set[str] = set()
        self._lock = asyncio.Lock()

    async def create(self, context: BrowserContext, workspace: str, url: str | None = None) -> TabInfo:
        async with self._lock:
            page = await context.new_page()
            tab_id = f"tab_{len(self._pages) + 1}_{id(page)}"
            page.on("close", lambda: asyncio.create_task(self._handle_page_closed(tab_id)))
            if url:
                await page.goto(url, wait_until="domcontentloaded")
            info = TabInfo(tab_id=tab_id, url=page.url, title=await self._safe_title(page), workspace=workspace)
            self._pages[tab_id] = page
            self._info[tab_id] = info
            self._active_tab_id = tab_id
            await self._events.emit(BrowserEvent(type=EventType.TAB_CREATED, payload={"tab_id": tab_id, "url": info.url}))
            return info

    async def _handle_page_closed(self, tab_id: str) -> None:
        self._pages.pop(tab_id, None)
        self._info.pop(tab_id, None)
        self._pinned.discard(tab_id)
        if self._active_tab_id == tab_id:
            self._active_tab_id = next(iter(self._pages), None)
        await self._events.emit(BrowserEvent(type=EventType.TAB_CLOSED, payload={"tab_id": tab_id}))

    @staticmethod
    async def _safe_title(page: Page) -> str:
        try:
            return await page.title()
        except Exception:  # noqa: BLE001
            return ""

    def get_page(self, tab_id: str) -> Page:
        page = self._pages.get(tab_id)
        if page is None:
            raise TabNotFoundError(f"tab '{tab_id}' not found")
        return page

    def active_page(self) -> Page:
        if self._active_tab_id is None:
            raise TabNotFoundError("no active tab")
        return self.get_page(self._active_tab_id)

    @property
    def active_tab_id(self) -> str | None:
        return self._active_tab_id

    def list_tabs(self, workspace: str | None = None) -> list[TabInfo]:
        tabs = list(self._info.values())
        if workspace is not None:
            tabs = [t for t in tabs if t.workspace == workspace]
        return tabs

    async def close(self, tab_id: str) -> None:
        page = self.get_page(tab_id)
        await page.close()

    async def switch(self, tab_id: str) -> TabInfo:
        if tab_id not in self._pages:
            raise TabNotFoundError(f"tab '{tab_id}' not found")
        self._active_tab_id = tab_id
        await self._events.emit(BrowserEvent(type=EventType.TAB_SWITCHED, payload={"tab_id": tab_id}))
        page = self._pages[tab_id]
        await page.bring_to_front()
        return self._info[tab_id]

    async def duplicate(self, tab_id: str) -> TabInfo:
        page = self.get_page(tab_id)
        context = page.context
        source_info = self._info[tab_id]
        return await self.create(context, source_info.workspace, url=page.url)

    def pin(self, tab_id: str) -> None:
        if tab_id not in self._pages:
            raise TabNotFoundError(f"tab '{tab_id}' not found")
        self._pinned.add(tab_id)
        self._info[tab_id].pinned = True

    def unpin(self, tab_id: str) -> None:
        self._pinned.discard(tab_id)
        if tab_id in self._info:
            self._info[tab_id].pinned = False

    def is_pinned(self, tab_id: str) -> bool:
        return tab_id in self._pinned

    async def back(self, tab_id: str) -> None:
        page = self.get_page(tab_id)
        await page.go_back(wait_until="domcontentloaded")
        self._info[tab_id].url = page.url

    async def forward(self, tab_id: str) -> None:
        page = self.get_page(tab_id)
        await page.go_forward(wait_until="domcontentloaded")
        self._info[tab_id].url = page.url

    async def reload(self, tab_id: str) -> None:
        page = self.get_page(tab_id)
        await page.reload(wait_until="domcontentloaded")
        self._info[tab_id].url = page.url

    async def refresh_info(self, tab_id: str) -> TabInfo:
        page = self.get_page(tab_id)
        info = self._info[tab_id]
        info.url = page.url
        info.title = await self._safe_title(page)
        return info

    async def close_all(self, workspace: str | None = None) -> None:
        targets = [tid for tid, info in self._info.items() if workspace is None or info.workspace == workspace]
        for tab_id in targets:
            try:
                await self.close(tab_id)
            except TabNotFoundError:
                continue
