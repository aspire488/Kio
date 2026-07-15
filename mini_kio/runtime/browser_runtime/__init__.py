"""browser_runtime -- standalone, integration-ready Playwright browser runtime.

Exposes BrowserRuntime as the primary facade. All sub-components
(BrowserLifecycleManager, WorkspaceManager, TabManager, Navigator,
DomController, DownloadManager, UploadManager, ScriptingController,
RecoveryManager) are independently importable for callers that want finer
control or to wire their own dependency graph.
"""

from .dom import DomController
from .downloads import DownloadManager
from .events import EventBus
from .exceptions import (
    BrowserRuntimeError,
    DomActionError,
    DownloadError,
    DownloadTimeoutError,
    ElementNotFoundError,
    LaunchError,
    NavigationError,
    NavigationTimeoutError,
    RecoveryError,
    RuntimeNotStartedError,
    ScriptingError,
    ShutdownError,
    TabError,
    TabNotFoundError,
    UploadError,
    UploadValidationError,
    VerificationError,
    WorkspaceError,
    WorkspaceNotFoundError,
)
from .lifecycle import BrowserLifecycleManager
from .navigation import Navigator
from .recovery import RecoveryManager
from .runtime import BrowserRuntime
from .scripting import ScriptingController
from .tabs import TabManager
from .types import (
    ActionResult,
    BrowserEvent,
    BrowserState,
    DownloadInfo,
    EventType,
    HealthSnapshot,
    LaunchConfig,
    NavigationResult,
    TabInfo,
    UploadResult,
    WorkspaceConfig,
)
from .uploads import UploadManager
from .workspace import WorkspaceManager

__all__ = [
    "BrowserRuntime",
    "BrowserLifecycleManager",
    "WorkspaceManager",
    "TabManager",
    "Navigator",
    "DomController",
    "DownloadManager",
    "UploadManager",
    "ScriptingController",
    "RecoveryManager",
    "EventBus",
    "LaunchConfig",
    "WorkspaceConfig",
    "TabInfo",
    "ActionResult",
    "NavigationResult",
    "DownloadInfo",
    "UploadResult",
    "HealthSnapshot",
    "BrowserEvent",
    "EventType",
    "BrowserState",
    "BrowserRuntimeError",
    "LaunchError",
    "ShutdownError",
    "WorkspaceError",
    "WorkspaceNotFoundError",
    "TabError",
    "TabNotFoundError",
    "NavigationError",
    "NavigationTimeoutError",
    "VerificationError",
    "DomActionError",
    "ElementNotFoundError",
    "DownloadError",
    "DownloadTimeoutError",
    "UploadError",
    "UploadValidationError",
    "ScriptingError",
    "RecoveryError",
    "RuntimeNotStartedError",
]

__version__ = "1.0.0"
