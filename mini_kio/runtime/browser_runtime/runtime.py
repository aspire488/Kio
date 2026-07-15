"""Top-level facade wiring every browser_runtime component together via
dependency injection. This is the single integration point for callers."""

from __future__ import annotations

import logging
from pathlib import Path
from typing import Any

from playwright.async_api import Page

from .accessibility import AccessibilityController
from .agents import AgentResult, MonitoringAgent, ParallelAgentManager, ResearchAgent
from .bookmarks import BookmarkManager
from .checkpoint import CheckpointManager, WorkflowRecorder, WorkflowReplayEngine
from .dom import DomController
from .downloads import DownloadManager
from .events import EventBus
from .exceptions import RuntimeNotStartedError
from .file_picker import ClipboardIntegration, FilePickerHandler
from .healing import RetryController, SelectorHealer
from .history import HistoryManager
from .instances import BrowserInstanceManager
from .lifecycle import BrowserLifecycleManager
from .navigation import Navigator
from .permissions import PermissionManager
from .printing import PrintManager
from .reauth import CaptchaMFAHandler, ReauthDetector
from .recovery import RecoveryManager
from .scripting import ScriptingController
from .session import CookieManager, SessionPersistence
from .tab_groups import TabGroupManager
from .tabs import TabManager
from .types import (
    Checkpoint,
    HealthSnapshot,
    LaunchConfig,
    NavigationResult,
    TabInfo,
    WorkspaceConfig,
    WorkflowRecording,
)
from .uploads import UploadManager
from .vision import OCREngine, VisionHybrid
from .visual_diff import VisualDiffController
from .window_groups import WindowGroupManager
from .workspace import WorkspaceManager

logger = logging.getLogger("browser_runtime")


class BrowserRuntime:
    """Facade over all browser automation components.

    Construct with a storage root and LaunchConfig; call `start()` before
    any other method, and `stop()` on shutdown. All sub-components are
    plain, independently testable classes injected here -- there are no
    globals or singletons.
    """

    def __init__(
        self,
        storage_root: Path,
        launch_config: LaunchConfig | None = None,
        *,
        event_bus: EventBus | None = None,
    ) -> None:
        self._storage_root = storage_root
        self._config = launch_config or LaunchConfig(downloads_dir=storage_root / "downloads")
        self.events = event_bus or EventBus()

        # Core components
        self.lifecycle = BrowserLifecycleManager(self._config, self.events)
        self.workspaces = WorkspaceManager(storage_root, self._config, self.events)
        self.tabs = TabManager(self.events)
        self.navigator = Navigator(self.events, default_timeout_ms=self._config.default_navigation_timeout_ms)
        self.dom = DomController(self.events, default_timeout_ms=self._config.default_action_timeout_ms)
        self.downloads = DownloadManager(self.events)
        self.uploads = UploadManager(self.events)
        self.scripting = ScriptingController(self.events)
        self.recovery = RecoveryManager(
            self.lifecycle, self.workspaces, self.tabs, self.events,
            max_attempts=self._config.max_restart_attempts,
        )

        # Session & persistence
        self.session = SessionPersistence(storage_root)
        self.cookies = CookieManager()

        # Checkpoints & workflow
        self.checkpoints = CheckpointManager(storage_root)
        self.workflows = WorkflowRecorder(storage_root)
        self.replay = WorkflowReplayEngine(self.dom, self.navigator)

        # Selector healing & retry
        self.retry = RetryController()

        # OCR & Vision
        self.ocr = OCREngine()
        self.vision = VisionHybrid(self.ocr, storage_root / ".kio_vision_cache")

        # File picker & clipboard
        self.file_picker = FilePickerHandler()
        self.clipboard = ClipboardIntegration()

        # Auth detection
        self.reauth_detector = ReauthDetector()
        self.captcha_mfa = CaptchaMFAHandler()

        # History & bookmarks
        self.history = HistoryManager(storage_root, self.events)
        self.bookmarks = BookmarkManager(storage_root, self.events)

        # Tab & window groups
        self.tab_groups = TabGroupManager(self.events)
        self.window_groups = WindowGroupManager(self.events)

        # Accessibility
        self.accessibility = AccessibilityController(self.events)

        # Permissions
        self.permissions = PermissionManager(self.events)

        # Printing / PDF
        self.printing = PrintManager(self.events)

        # Visual diff
        self.visual_diff = VisualDiffController(self.events)

        # Multi-browser instance manager
        self.instances = BrowserInstanceManager(self.events, self._config)

        # Agents
        self.research_agent = ResearchAgent(self.navigator, self.scripting, self.dom, self.ocr)
        self.monitoring = MonitoringAgent(self)
        self.parallel_agents = ParallelAgentManager(self)

        self.lifecycle.set_crash_handler(self._on_crash)
        self._started = False
        self._start_error: str | None = None

    async def start(self) -> None:
        try:
            await self.lifecycle.launch()
            self._started = True
            self._start_error = None
        except Exception as exc:
            self._start_error = str(exc)
            logger.error("BrowserRuntime start failed: %s", exc, exc_info=True)
            raise

    async def stop(self) -> None:
        self.monitoring.stop_all()
        await self.workspaces.close_all()
        await self.lifecycle.shutdown()
        self._started = False

    def _require_started(self) -> None:
        if not self._started:
            raise RuntimeNotStartedError("call BrowserRuntime.start() before using the runtime")

    async def _on_crash(self) -> None:
        try:
            await self.recovery.recover()
        except Exception:
            logger.exception("automatic recovery failed; runtime remains in CRASHED state")

    # -- workspace / tab convenience wiring -------------------------------

    async def open_workspace(self, config: WorkspaceConfig, *,
                             restore_session: bool = False) -> None:
        self._require_started()
        playwright = self.lifecycle.playwright
        browser = self.lifecycle.browser
        if playwright is None:
            raise RuntimeNotStartedError("playwright driver not available")
        await self.workspaces.create(playwright, browser, config)
        self.recovery.track_workspace(config)
        if restore_session and config.persistent:
            context = self.workspaces.get(config.name)
            await self.session.restore(context, config.name)

    async def close_workspace(self, name: str, *,
                              save_session: bool = False) -> None:
        if save_session:
            try:
                context = self.workspaces.get(name)
                await self.session.save(context, name)
            except Exception:
                pass
        await self.tabs.close_all(workspace=name)
        await self.workspaces.close(name)
        self.recovery.untrack_workspace(name)

    async def new_tab(self, workspace: str, url: str | None = None) -> TabInfo:
        self._require_started()
        context = self.workspaces.get(workspace)
        info = await self.tabs.create(context, workspace, url=url)
        page = self.tabs.get_page(info.tab_id)
        self.scripting.attach_console_capture(page)
        return info

    def page(self, tab_id: str) -> Page:
        return self.tabs.get_page(tab_id)

    async def goto(self, tab_id: str, url: str, **kwargs) -> NavigationResult:
        page = self.tabs.get_page(tab_id)
        result = await self.navigator.goto(page, url, **kwargs)
        await self.tabs.refresh_info(tab_id)
        return result

    async def checkpoint(self, tab_id: str, *, name: str | None = None,
                         with_screenshot: bool = True, with_dom: bool = False) -> Checkpoint:
        page = self.tabs.get_page(tab_id)
        info = self.tabs.list_tabs()
        tab_info = next((t for t in info if t.tab_id == tab_id), None)
        return await self.checkpoints.create(
            page, tab_info.workspace if tab_info else "default",
            tab_id=tab_id, name=name, with_screenshot=with_screenshot, with_dom=with_dom,
        )

    async def restore_checkpoint(self, tab_id: str, cp_id: str) -> bool:
        page = self.tabs.get_page(tab_id)
        return await self.checkpoints.restore(page, cp_id)

    async def save_session(self, workspace: str) -> dict:
        context = self.workspaces.get(workspace)
        return await self.session.save(context, workspace)

    async def restore_session(self, workspace: str) -> bool:
        context = self.workspaces.get(workspace)
        return await self.session.restore(context, workspace)

    def health(self) -> HealthSnapshot:
        return self.lifecycle.health(open_tabs=len(self.tabs.list_tabs()))

    def diagnostics(self) -> dict[str, Any]:
        return {
            "state": self.lifecycle.state.value if self.lifecycle else "unknown",
            "started": self._started,
            "open_tabs": len(self.tabs.list_tabs()),
            "tab_groups": len(self.tab_groups.list_all()),
            "window_groups": len(self.window_groups.list_all()),
            "instances": self.instances.count(),
            "history_workspaces": len(self.history._entries) if hasattr(self, 'history') else 0,
            "bookmarks_count": sum(len(b) for b in self.bookmarks._bookmarks.values()) if hasattr(self, 'bookmarks') else 0,
            "workspaces": list(self.workspaces._contexts.keys()) if hasattr(self.workspaces, '_contexts') else [],
            "downloads_active": len(self.downloads._active) if hasattr(self.downloads, '_active') else 0,
            "observers": len(self.events._handlers) if hasattr(self.events, '_handlers') else 0,
        }

    async def __aenter__(self) -> "BrowserRuntime":
        await self.start()
        return self

    async def __aexit__(self, *_exc_info) -> None:
        await self.stop()
