"""Exception hierarchy for browser_runtime."""

from __future__ import annotations


class BrowserRuntimeError(Exception):
    """Base exception for all browser_runtime errors."""


class LaunchError(BrowserRuntimeError):
    """Raised when the browser process fails to launch."""


class ShutdownError(BrowserRuntimeError):
    """Raised when the browser process fails to shut down cleanly."""


class WorkspaceError(BrowserRuntimeError):
    """Raised for workspace/profile management failures."""


class WorkspaceNotFoundError(WorkspaceError):
    """Raised when a named workspace does not exist."""


class TabError(BrowserRuntimeError):
    """Raised for tab lifecycle failures."""


class TabNotFoundError(TabError):
    """Raised when referencing a tab id that does not exist."""


class NavigationError(BrowserRuntimeError):
    """Raised when navigation fails after all retries."""


class NavigationTimeoutError(NavigationError):
    """Raised when navigation exceeds the configured timeout."""


class VerificationError(BrowserRuntimeError):
    """Raised when a closed-loop action verification fails."""


class DomActionError(BrowserRuntimeError):
    """Raised when a DOM automation action fails."""


class ElementNotFoundError(DomActionError):
    """Raised when a target selector resolves to no element."""


class DownloadError(BrowserRuntimeError):
    """Raised for download failures."""


class DownloadTimeoutError(DownloadError):
    """Raised when a download does not complete in time."""


class UploadError(BrowserRuntimeError):
    """Raised for upload/file-input failures."""


class UploadValidationError(UploadError):
    """Raised when files supplied for upload fail validation."""


class ScriptingError(BrowserRuntimeError):
    """Raised when JS evaluation/injection fails."""


class RecoveryError(BrowserRuntimeError):
    """Raised when automatic recovery from a crash fails."""


class RuntimeNotStartedError(BrowserRuntimeError):
    """Raised when an operation is attempted before runtime.start()."""
