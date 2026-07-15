"""Typed data structures shared across browser_runtime.

Provides dataclasses and enums used throughout the runtime components.
"""

from __future__ import annotations

import time
import uuid
from dataclasses import dataclass, field
from enum import Enum
from pathlib import Path
from typing import Any, Optional, Union, List, Dict

# ---------------------------------------------------------------------------
# Basic enums
# ---------------------------------------------------------------------------

class EventType(str, Enum):
    """All event types emitted on the EventBus.

    The set is deliberately exhaustive – new components should add their own
    values here.
    """

    # Lifecycle / process events
    LAUNCH = "launch"
    SHUTDOWN = "shutdown"
    RESTART = "restart"
    CRASH = "crash"
    ERROR = "error"
    HEALTH_CHECK = "health_check"

    # Navigation events
    NAVIGATION_STARTED = "navigation_started"
    NAVIGATION_SUCCEEDED = "navigation_succeeded"
    NAVIGATION_FAILED = "navigation_failed"

    # DOM actions
    DOM_ACTION = "dom_action"

    # Tab management
    TAB_CREATED = "tab_created"
    TAB_CLOSED = "tab_closed"
    TAB_SWITCHED = "tab_switched"

    # Download handling
    DOWNLOAD_STARTED = "download_started"
    DOWNLOAD_COMPLETED = "download_completed"
    DOWNLOAD_FAILED = "download_failed"
    DOWNLOAD_CANCELLED = "download_cancelled"

    # Upload handling
    UPLOAD_STARTED = "upload_started"
    UPLOAD_COMPLETED = "upload_completed"
    UPLOAD_FAILED = "upload_failed"

    # Recovery workflow
    RECOVERY_STARTED = "recovery_started"
    RECOVERY_SUCCEEDED = "recovery_succeeded"
    RECOVERY_FAILED = "recovery_failed"

    # Session & persistence
    SESSION_SAVED = "session_saved"
    SESSION_RESTORED = "session_restored"
    SESSION_DELETED = "session_deleted"

    # Checkpoints
    CHECKPOINT_CREATED = "checkpoint_created"
    CHECKPOINT_RESTORED = "checkpoint_restored"
    CHECKPOINT_DELETED = "checkpoint_deleted"

    # Workflow recording
    WORKFLOW_STARTED = "workflow_started"
    WORKFLOW_STEP = "workflow_step"
    WORKFLOW_COMPLETED = "workflow_completed"
    WORKFLOW_REPLAYED = "workflow_replayed"

    # Healers / retry
    SELECTOR_HEALED = "selector_healed"
    RETRY_ATTEMPT = "retry_attempt"

    # Auth detection
    AUTH_DETECTED = "auth_detected"
    HUMAN_HANDOFF_REQUESTED = "human_handoff_requested"

    # Agents
    AGENT_STARTED = "agent_started"
    AGENT_COMPLETED = "agent_completed"
    AGENT_FAILED = "agent_failed"
    AGENT_MONITOR_TRIGGER = "agent_monitor_trigger"

    # OCR / Vision
    OCR_EXTRACTED = "ocr_extracted"
    VISION_HYBRID_RESULT = "vision_hybrid_result"

    # Clipboard
    CLIPBOARD_READ = "clipboard_read"
    CLIPBOARD_WRITTEN = "clipboard_written"

    # File picker
    FILE_PICKER_OPENED = "file_picker_opened"
    FILE_PICKER_COMPLETED = "file_picker_completed"

    # History
    HISTORY_PAGE_VISITED = "history_page_visited"
    HISTORY_CLEARED = "history_cleared"
    HISTORY_SEARCHED = "history_searched"

    # Bookmarks
    BOOKMARK_CREATED = "bookmark_created"
    BOOKMARK_REMOVED = "bookmark_removed"
    BOOKMARK_UPDATED = "bookmark_updated"

    # Accessibility
    ACCESSIBILITY_SNAPSHOT = "accessibility_snapshot"

    # Permissions
    PERMISSION_GRANTED = "permission_granted"
    PERMISSION_DENIED = "permission_denied"
    PERMISSION_RESET = "permission_reset"

    # Printing
    PRINT_STARTED = "print_started"
    PRINT_COMPLETED = "print_completed"
    PRINT_FAILED = "print_failed"
    PDF_GENERATED = "pdf_generated"

    # Visual diff
    SCREENSHOT_TAKEN = "screenshot_taken"
    VISUAL_DIFF_COMPUTED = "visual_diff_computed"

    # Tab groups
    TAB_GROUP_CREATED = "tab_group_created"
    TAB_GROUP_REMOVED = "tab_group_removed"
    TAB_GROUP_UPDATED = "tab_group_updated"
    TAB_GROUP_COLLAPSED = "tab_group_collapsed"
    TAB_GROUP_EXPANDED = "tab_group_expanded"

    # Window groups
    WINDOW_GROUP_CREATED = "window_group_created"
    WINDOW_GROUP_REMOVED = "window_group_removed"
    WINDOW_GROUP_UPDATED = "window_group_updated"

    # Multi-browser instances
    INSTANCE_CREATED = "instance_created"
    INSTANCE_CLOSED = "instance_closed"
    INSTANCE_CRASHED = "instance_crashed"
    INSTANCE_SWITCHED = "instance_switched"

    # Incognito
    INCOGNITO_STARTED = "incognito_started"
    INCOGNITO_ENDED = "incognito_ended"

    # Manual takeover
    TAKEOVER_REQUESTED = "takeover_requested"
    TAKEOVER_COMPLETED = "takeover_completed"
    TAKEOVER_RESUMED = "takeover_resumed"

    # Monitoring / diagnostics
    BROWSER_METRICS = "browser_metrics"
    BROWSER_TELEMETRY = "browser_telemetry"
    DIAGNOSTIC_SNAPSHOT = "diagnostic_snapshot"


class BrowserState(str, Enum):
    """High‑level state of the underlying browser process."""

    STOPPED = "stopped"
    LAUNCHING = "launching"
    RUNNING = "running"
    SHUTTING_DOWN = "shutting_down"
    RESTARTING = "restarting"
    CRASHED = "crashed"


# ---------------------------------------------------------------------------
# Core data structures
# ---------------------------------------------------------------------------

@dataclass(slots=True)
class BrowserEvent:
    """An event emitted on the EventBus.

    *type* is one of :class:`EventType`. ``payload`` is an arbitrary mapping
    that callers may attach additional context to.
    """

    type: EventType
    payload: Dict[str, Any] = field(default_factory=dict)


@dataclass(slots=True)
class ActionResult:
    """Result of a DOM action performed by :class:`DomController`."""

    success: bool
    action: str
    selector: str
    verified: bool = False
    duration_ms: float = 0.0
    error: Optional[str] = None
    details: Optional[Dict[str, Any]] = None


@dataclass(slots=True)
class NavigationResult:
    """Outcome of a navigation request via :class:`Navigator`."""

    success: bool
    url: str
    final_url: str
    status_code: Optional[int] = None
    attempts: int = 1
    duration_ms: float = 0.0
    error: Optional[str] = None


@dataclass(slots=True)
class DownloadInfo:
    """Tracks a single download's lifecycle.

    ``download_id`` is generated automatically.
    """

    state: str = "pending"
    download_id: str = field(default_factory=lambda: str(uuid.uuid4()))
    url: Optional[str] = None
    suggested_filename: Optional[str] = None
    save_path: Optional[Path] = None
    bytes_received: Optional[int] = None
    total_bytes: Optional[int] = None
    error: Optional[str] = None
    finished_at: Optional[float] = None


@dataclass(slots=True)
class UploadResult:
    """Result of a file‑upload operation via :class:`UploadManager`."""

    success: bool
    selector: str
    files: List[str]
    error: Optional[str] = None


@dataclass(slots=True)
class TabInfo:
    """Metadata for a browser tab tracked by :class:`TabManager`."""

    tab_id: str
    url: str
    title: str
    workspace: str
    pinned: bool = False


# ---------------------------------------------------------------------------
# Configuration objects
# ---------------------------------------------------------------------------

@dataclass(slots=True)
class LaunchConfig:
    """Configuration for launching the Playwright browser.

    Only the fields accessed by the runtime are defined; additional fields can
    be added later without breaking existing code.
    """

    # Core launch parameters
    browser_type: str = "chromium"
    headless: bool = True
    args: List[str] = field(default_factory=list)
    slow_mo_ms: Optional[int] = None
    executable_path: Optional[str] = None
    proxy_server: Optional[str] = None

    # Viewport / user‑agent defaults
    viewport_width: int = 1280
    viewport_height: int = 720
    user_agent: Optional[str] = None
    locale: Optional[str] = None
    timezone_id: Optional[str] = None

    # Directories & timeouts
    downloads_dir: Optional[Path] = None
    default_navigation_timeout_ms: int = 30_000
    default_action_timeout_ms: int = 15_000

    # Watchdog / restart behaviour
    watchdog_interval_s: float = 5.0
    watchdog_unresponsive_threshold_s: float = 30.0
    max_restart_attempts: int = 3


@dataclass(slots=True)
class WorkspaceConfig:
    """Configuration for a named workspace (browser context)."""

    name: str
    incognito: bool = False
    persistent: bool = False
    extra_http_headers: Optional[Dict[str, str]] = None
    permissions: List[str] = field(default_factory=list)

    def profile_dir(self, storage_root: Path) -> Path:
        """Return the on‑disk profile directory for a persistent workspace.

        ``storage_root`` is the base directory supplied to ``BrowserRuntime``.
        """

        return storage_root / "workspaces" / self.name


@dataclass(slots=True)
class HealthSnapshot:
    """Aggregated health information returned by :meth:`BrowserRuntime.health`."""

    state: BrowserState
    responsive: bool
    open_tabs: int
    uptime_s: float
    restart_count: int
    last_error: Optional[str] = None

# Backward‑compatibility alias – some external code referenced ``BrowserHealth``.
BrowserHealth = HealthSnapshot


# Forward declarations for types defined in extension modules
# (full definitions live in checkpoint.py, agents.py — these are re-exports
# to keep runtime.py imports clean)
class Checkpoint:
    pass


class WorkflowRecording:
    pass
