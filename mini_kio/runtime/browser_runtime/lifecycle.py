"""Browser process lifecycle: launch, shutdown, restart, watchdog, health."""

from __future__ import annotations

import asyncio
import logging
import time

from playwright.async_api import Browser, Playwright, async_playwright

from .events import EventBus
from .exceptions import LaunchError, ShutdownError
from .types import BrowserState, EventType, HealthSnapshot, LaunchConfig, BrowserEvent

logger = logging.getLogger("browser_runtime.lifecycle")


class BrowserLifecycleManager:
    """Owns the Playwright driver and top-level Browser process.

    Responsibilities: launch, graceful shutdown, restart, a background
    watchdog that polls responsiveness, and health snapshots. This class
    does not know about tabs or workspaces -- it only owns the process.
    """

    def __init__(self, config: LaunchConfig, event_bus: EventBus) -> None:
        self._config = config
        self._events = event_bus
        self._playwright: Playwright | None = None
        self._browser: Browser | None = None
        self._state = BrowserState.STOPPED
        self._started_at: float | None = None
        self._restart_count = 0
        self._last_error: str | None = None
        self._watchdog_task: asyncio.Task | None = None
        self._on_crash_callback = None  # set by RuntimeSupervisor via set_crash_handler
        self._lock = asyncio.Lock()

    @property
    def state(self) -> BrowserState:
        return self._state

    @property
    def browser(self) -> Browser | None:
        return self._browser

    @property
    def playwright(self) -> Playwright | None:
        return self._playwright

    def set_crash_handler(self, callback) -> None:
        self._on_crash_callback = callback

    async def launch(self) -> Browser:
        async with self._lock:
            if self._state == BrowserState.RUNNING and self._browser is not None:
                return self._browser
            self._state = BrowserState.LAUNCHING
            try:
                self._playwright = await async_playwright().start()
                launcher = getattr(self._playwright, self._config.browser_type)
                launch_kwargs: dict = {
                    "headless": self._config.headless,
                    "args": self._config.args,
                    "slow_mo": self._config.slow_mo_ms or None,
                }
                if self._config.executable_path:
                    launch_kwargs["executable_path"] = self._config.executable_path
                if self._config.proxy_server:
                    launch_kwargs["proxy"] = {"server": self._config.proxy_server}

                self._browser = await launcher.launch(**launch_kwargs)
                self._browser.on("disconnected", self._handle_disconnect)
                self._state = BrowserState.RUNNING
                self._started_at = time.time()
                self._last_error = None
                await self._events.emit(
                    BrowserEvent(type=EventType.LAUNCH, payload={"browser_type": self._config.browser_type})
                )
                self._ensure_watchdog()
                return self._browser
            except Exception as exc:  # noqa: BLE001
                self._state = BrowserState.CRASHED
                self._last_error = str(exc)
                await self._events.emit(BrowserEvent(type=EventType.ERROR, payload={"stage": "launch", "error": str(exc)}))
                raise LaunchError(f"failed to launch browser: {exc}") from exc

    def _handle_disconnect(self, *_args) -> None:
        if self._state in (BrowserState.SHUTTING_DOWN, BrowserState.STOPPED):
            return
        logger.warning("browser disconnected unexpectedly")
        self._state = BrowserState.CRASHED
        asyncio.create_task(self._events.emit(BrowserEvent(type=EventType.CRASH, payload={})))
        if self._on_crash_callback is not None:
            asyncio.create_task(self._on_crash_callback())

    async def shutdown(self) -> None:
        async with self._lock:
            if self._state == BrowserState.STOPPED:
                return
            self._state = BrowserState.SHUTTING_DOWN
            self._cancel_watchdog()
            try:
                if self._browser is not None:
                    try:
                        await self._browser.close()
                    except Exception:  # ponytail: browser may already be disconnected
                        pass
                if self._playwright is not None:
                    try:
                        await self._playwright.stop()
                    except Exception:  # ponytail: playwright may already be stopped
                        pass
            except Exception as exc:
                raise ShutdownError(f"error during shutdown: {exc}") from exc
            finally:
                self._browser = None
                self._playwright = None
                self._state = BrowserState.STOPPED
                await self._events.emit(BrowserEvent(type=EventType.SHUTDOWN, payload={}))

    async def restart(self) -> Browser:
        self._state = BrowserState.RESTARTING
        await self._events.emit(BrowserEvent(type=EventType.RESTART, payload={"attempt": self._restart_count + 1}))
        try:
            await self.shutdown()
        except ShutdownError:
            logger.warning("shutdown during restart raised; continuing with relaunch")
        self._restart_count += 1
        return await self.launch()

    def _ensure_watchdog(self) -> None:
        if self._watchdog_task is None or self._watchdog_task.done():
            self._watchdog_task = asyncio.create_task(self._watchdog_loop())

    def _cancel_watchdog(self) -> None:
        if self._watchdog_task is not None:
            self._watchdog_task.cancel()
            self._watchdog_task = None

    async def _watchdog_loop(self) -> None:
        while self._state == BrowserState.RUNNING:
            try:
                await asyncio.sleep(self._config.watchdog_interval_s)
                responsive = await self._probe_responsive()
                await self._events.emit(
                    BrowserEvent(type=EventType.HEALTH_CHECK, payload={"responsive": responsive})
                )
                if not responsive:
                    logger.warning("watchdog detected unresponsive browser; triggering crash handler")
                    self._state = BrowserState.CRASHED
                    if self._on_crash_callback is not None:
                        await self._on_crash_callback()
                    return
            except asyncio.CancelledError:
                return
            except Exception:  # noqa: BLE001
                logger.exception("watchdog loop error")

    async def _probe_responsive(self) -> bool:
        if self._browser is None:
            return False
        try:
            await asyncio.wait_for(self._probe_contexts(), timeout=self._config.watchdog_unresponsive_threshold_s)
            return True
        except Exception:  # noqa: BLE001
            return False

    async def _probe_contexts(self) -> None:
        if self._browser is None:
            return
        _ = self._browser.contexts  # cheap property access proves the connection object is alive
        if self._browser.is_connected() is False:
            raise ConnectionError("browser reports not connected")

    def health(self, open_tabs: int) -> HealthSnapshot:
        uptime = time.time() - self._started_at if self._started_at else 0.0
        responsive = self._browser.is_connected() if self._browser else False
        return HealthSnapshot(
            state=self._state,
            responsive=responsive,
            open_tabs=open_tabs,
            uptime_s=uptime,
            restart_count=self._restart_count,
            last_error=self._last_error,
        )
