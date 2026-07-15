"""Persistent named browser workspaces (profiles)."""

from __future__ import annotations

import asyncio
import logging
from pathlib import Path

from playwright.async_api import Browser, BrowserContext, Playwright

from .events import EventBus
from .exceptions import WorkspaceError, WorkspaceNotFoundError
from .types import BrowserEvent, EventType, LaunchConfig, WorkspaceConfig

logger = logging.getLogger("browser_runtime.workspace")


class WorkspaceManager:
    """Creates and tracks isolated BrowserContext instances.

    Each workspace maps to a named, on-disk profile directory when
    `persistent=True`, giving it its own cookies/localStorage/cache that
    survive process restarts. Incognito workspaces get a fresh in-memory
    context that is discarded on close. There is no hard limit on the
    number of concurrent workspaces beyond host resources.
    """

    def __init__(self, storage_root: Path, launch_config: LaunchConfig, event_bus: EventBus) -> None:
        self._storage_root = storage_root
        self._launch_config = launch_config
        self._events = event_bus
        self._contexts: dict[str, BrowserContext] = {}
        self._configs: dict[str, WorkspaceConfig] = {}
        self._lock = asyncio.Lock()
        self._storage_root.mkdir(parents=True, exist_ok=True)

    async def create(
        self,
        playwright: Playwright,
        browser: Browser | None,
        config: WorkspaceConfig,
    ) -> BrowserContext:
        async with self._lock:
            if config.name in self._contexts:
                raise WorkspaceError(f"workspace '{config.name}' already exists")

            viewport = {
                "width": self._launch_config.viewport_width,
                "height": self._launch_config.viewport_height,
            }

            if config.incognito or not config.persistent:
                if browser is None:
                    raise WorkspaceError("a running Browser is required for non-persistent workspaces")
                context = await browser.new_context(
                    viewport=viewport,
                    user_agent=self._launch_config.user_agent,
                    locale=self._launch_config.locale,
                    timezone_id=self._launch_config.timezone_id,
                    extra_http_headers=config.extra_http_headers or None,
                    accept_downloads=True,
                )
            else:
                profile_dir = config.profile_dir(self._storage_root)
                profile_dir.mkdir(parents=True, exist_ok=True)
                launcher = getattr(playwright, self._launch_config.browser_type)
                context = await launcher.launch_persistent_context(
                    user_data_dir=str(profile_dir),
                    headless=self._launch_config.headless,
                    args=self._launch_config.args,
                    viewport=viewport,
                    user_agent=self._launch_config.user_agent,
                    locale=self._launch_config.locale,
                    timezone_id=self._launch_config.timezone_id,
                    extra_http_headers=config.extra_http_headers or None,
                    accept_downloads=True,
                    downloads_path=str(self._launch_config.downloads_dir)
                    if self._launch_config.downloads_dir
                    else None,
                )

            if config.permissions:
                try:
                    await context.grant_permissions(config.permissions)
                except Exception:  # noqa: BLE001
                    logger.warning("failed to grant permissions for workspace %s", config.name)

            context.set_default_navigation_timeout(self._launch_config.default_navigation_timeout_ms)
            context.set_default_timeout(self._launch_config.default_action_timeout_ms)

            self._contexts[config.name] = context
            self._configs[config.name] = config
            await self._events.emit(
                BrowserEvent(
                    type=EventType.LAUNCH,
                    payload={"workspace": config.name, "kind": "workspace_created"},
                )
            )
            return context

    def get(self, name: str) -> BrowserContext:
        context = self._contexts.get(name)
        if context is None:
            raise WorkspaceNotFoundError(f"workspace '{name}' not found")
        return context

    def exists(self, name: str) -> bool:
        return name in self._contexts

    def list_workspaces(self) -> list[str]:
        return list(self._contexts.keys())

    async def close(self, name: str) -> None:
        async with self._lock:
            context = self._contexts.pop(name, None)
            self._configs.pop(name, None)
            if context is not None:
                await context.close()

    async def close_all(self) -> None:
        async with self._lock:
            for name, context in list(self._contexts.items()):
                try:
                    await context.close()
                except Exception:  # noqa: BLE001
                    logger.warning("error closing workspace %s", name)
            self._contexts.clear()
            self._configs.clear()

    def clear_cache_path(self, name: str) -> Path | None:
        config = self._configs.get(name)
        if config is None or not config.persistent:
            return None
        return config.profile_dir(self._storage_root)
