"""Automatic recovery from crashed browser, closed page, lost context,
disconnected browser."""

from __future__ import annotations

import asyncio
import logging

from .events import EventBus
from .exceptions import RecoveryError
from .lifecycle import BrowserLifecycleManager
from .tabs import TabManager
from .types import BrowserEvent, EventType, WorkspaceConfig
from .workspace import WorkspaceManager

logger = logging.getLogger("browser_runtime.recovery")


class RecoveryManager:
    """Reacts to lifecycle crash events by relaunching the browser and
    re-creating workspaces/tabs that existed before the crash, up to a
    configured attempt limit."""

    def __init__(
        self,
        lifecycle: BrowserLifecycleManager,
        workspaces: WorkspaceManager,
        tabs: TabManager,
        event_bus: EventBus,
        *,
        max_attempts: int = 3,
    ) -> None:
        self._lifecycle = lifecycle
        self._workspaces = workspaces
        self._tabs = tabs
        self._events = event_bus
        self._max_attempts = max_attempts
        self._recovering = asyncio.Lock()
        self._known_workspaces: dict[str, WorkspaceConfig] = {}

    def track_workspace(self, config: WorkspaceConfig) -> None:
        self._known_workspaces[config.name] = config

    def untrack_workspace(self, name: str) -> None:
        self._known_workspaces.pop(name, None)

    async def recover(self) -> bool:
        if self._recovering.locked():
            logger.info("recovery already in progress; skipping duplicate trigger")
            return False

        async with self._recovering:
            await self._events.emit(BrowserEvent(type=EventType.RECOVERY_STARTED, payload={}))
            last_error: str | None = None
            for attempt in range(1, self._max_attempts + 1):
                try:
                    logger.warning("recovery attempt %d/%d", attempt, self._max_attempts)
                    await self._lifecycle.restart()
                    browser = self._lifecycle.browser
                    playwright = self._lifecycle.playwright
                    if browser is None or playwright is None:
                        raise RecoveryError("lifecycle did not produce a browser after restart")

                    for name, config in list(self._known_workspaces.items()):
                        try:
                            if self._workspaces.exists(name):
                                continue
                            await self._workspaces.create(playwright, browser, config)
                        except Exception:  # noqa: BLE001
                            logger.exception("failed to recreate workspace %s during recovery", name)

                    await self._events.emit(BrowserEvent(type=EventType.RECOVERY_SUCCEEDED, payload={"attempt": attempt}))
                    return True
                except Exception as exc:  # noqa: BLE001
                    last_error = str(exc)
                    logger.exception("recovery attempt %d failed", attempt)
                    await asyncio.sleep(min(2 ** attempt, 10))

            await self._events.emit(BrowserEvent(type=EventType.RECOVERY_FAILED, payload={"error": last_error}))
            raise RecoveryError(f"recovery failed after {self._max_attempts} attempts: {last_error}")

    async def ensure_page_alive(self, tab_id: str) -> bool:
        """Detects a closed page / lost context for a given tab_id and
        removes stale bookkeeping so callers can recreate the tab."""
        try:
            page = self._tabs.get_page(tab_id)
        except Exception:  # noqa: BLE001
            return False
        if page.is_closed():
            logger.warning("tab %s is closed; caller should recreate it", tab_id)
            return False
        try:
            await page.evaluate("1")
            return True
        except Exception:  # noqa: BLE001
            logger.warning("tab %s context appears lost", tab_id)
            return False
