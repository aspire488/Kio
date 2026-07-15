"""Multi-browser instance manager — Chrome, Edge, Firefox, incognito profiles."""

from __future__ import annotations

import logging
import time
import uuid
from pathlib import Path
from typing import Any

from playwright.async_api import Browser, Playwright, async_playwright

from .events import EventBus
from .exceptions import LaunchError
from .types import BrowserEvent, BrowserState, EventType, LaunchConfig

logger = logging.getLogger("browser_runtime.instances")


class BrowserInstance:
    """A single Playwright browser instance with its own state."""

    def __init__(self, instance_id: str, browser_type: str, label: str, incognito: bool) -> None:
        self.id = instance_id
        self.browser_type = browser_type
        self.label = label
        self.incognito = incognito
        self.state = BrowserState.STOPPED
        self.playwright: Playwright | None = None
        self.browser: Browser | None = None
        self.started_at: float = 0.0
        self.last_error: str | None = None


class BrowserInstanceManager:
    """Manages multiple Playwright browser instances (Chrome, Edge, Firefox, incognito)."""

    _BROWSER_ALIASES = {
        "chrome": "chromium",
        "edge": "chromium",
        "firefox": "firefox",
        "webkit": "webkit",
    }

    def __init__(self, event_bus: EventBus, default_config: LaunchConfig | None = None) -> None:
        self._events = event_bus
        self._default_config = default_config or LaunchConfig()
        self._instances: dict[str, BrowserInstance] = {}
        self._active_instance_id: str | None = None

    async def launch(self, browser_type: str = "chromium", *,
                     label: str = "", incognito: bool = False,
                     config: LaunchConfig | None = None,
                     executable_path: str | None = None) -> BrowserInstance:
        resolved = self._BROWSER_ALIASES.get(browser_type.lower(), browser_type)
        instance_id = str(uuid.uuid4())[:12]
        label = label or f"{resolved}_{instance_id[:6]}"
        instance = BrowserInstance(instance_id, resolved, label, incognito)
        instance.state = BrowserState.LAUNCHING

        cfg = config or self._default_config
        try:
            pw = await async_playwright().start()
            instance.playwright = pw
            launcher = getattr(pw, resolved)
            launch_kwargs: dict = {
                "headless": cfg.headless,
                "args": cfg.args,
                "slow_mo": cfg.slow_mo_ms or None,
            }
            if executable_path:
                launch_kwargs["executable_path"] = executable_path
            elif cfg.executable_path:
                launch_kwargs["executable_path"] = cfg.executable_path
            if cfg.proxy_server:
                launch_kwargs["proxy"] = {"server": cfg.proxy_server}

            browser = await launcher.launch(**launch_kwargs)
            instance.browser = browser
            instance.state = BrowserState.RUNNING
            instance.started_at = time.time()

            self._instances[instance_id] = instance
            self._active_instance_id = instance_id

            self._events.emit_nowait(
                BrowserEvent(type=EventType.INSTANCE_CREATED, payload={
                    "instance_id": instance_id, "browser_type": resolved,
                    "label": label, "incognito": incognito,
                })
            )
            logger.info("Browser instance '%s' (%s) launched", label, resolved)
            return instance
        except Exception as exc:
            instance.state = BrowserState.CRASHED
            instance.last_error = str(exc)
            raise LaunchError(f"Failed to launch '{label}': {exc}") from exc

    async def close(self, instance_id: str) -> bool:
        instance = self._instances.pop(instance_id, None)
        if instance is None:
            return False
        instance.state = BrowserState.SHUTTING_DOWN
        try:
            if instance.browser:
                await instance.browser.close()
            if instance.playwright:
                await instance.playwright.stop()
        except Exception as exc:
            logger.warning("Error closing instance '%s': %s", instance_id, exc)
        instance.state = BrowserState.STOPPED
        if self._active_instance_id == instance_id:
            self._active_instance_id = next(iter(self._instances.keys()), None)
        self._events.emit_nowait(
            BrowserEvent(type=EventType.INSTANCE_CLOSED, payload={"instance_id": instance_id})
        )
        return True

    async def close_all(self) -> None:
        for iid in list(self._instances.keys()):
            await self.close(iid)

    def get(self, instance_id: str) -> BrowserInstance | None:
        return self._instances.get(instance_id)

    def get_active(self) -> BrowserInstance | None:
        if self._active_instance_id:
            return self._instances.get(self._active_instance_id)
        return None

    def switch_active(self, instance_id: str) -> bool:
        if instance_id not in self._instances:
            return False
        self._active_instance_id = instance_id
        self._events.emit_nowait(
            BrowserEvent(type=EventType.INSTANCE_SWITCHED, payload={"instance_id": instance_id})
        )
        return True

    def list_all(self) -> list[dict[str, Any]]:
        return [
            {"id": i.id, "browser_type": i.browser_type, "label": i.label,
             "state": i.state.value, "incognito": i.incognito,
             "started_at": i.started_at, "last_error": i.last_error}
            for i in self._instances.values()
        ]

    def count(self) -> int:
        return len(self._instances)

    @property
    def active_instance_id(self) -> str | None:
        return self._active_instance_id
