"""Process ownership guard for the KIO runtime.

The bot, connector and MCP servers are one ownership domain.  Starting a
second KIO runtime must fail before it can bind the connector port or begin a
second Telegram long-poll loop.
"""

from __future__ import annotations

import logging
import os

logger = logging.getLogger(__name__)

_MUTEX_NAME = r"Local\KIO.Runtime.Owner.v1"
_ERROR_ALREADY_EXISTS = 183
_handle: int | None = None


def acquire_runtime_owner() -> bool:
    """Acquire the process-wide KIO runtime ownership token.

    A Windows named mutex is released automatically if the owning process
    crashes, avoiding stale PID-file failures.  Other platforms retain the
    existing behavior until they gain a native ownership implementation.
    """
    global _handle
    if _handle is not None:
        return True
    if os.name != "nt":
        return True

    import ctypes
    from ctypes import wintypes

    # ctypes defaults a Win32 function's return value to a 32-bit int.  A
    # mutex HANDLE is pointer-sized, so declare it explicitly or a valid
    # 64-bit handle can be truncated and mistaken for failure.
    kernel32 = ctypes.WinDLL("kernel32", use_last_error=True)
    create_mutex = kernel32.CreateMutexW
    create_mutex.argtypes = (wintypes.LPVOID, wintypes.BOOL, wintypes.LPCWSTR)
    create_mutex.restype = wintypes.HANDLE
    close_handle = kernel32.CloseHandle
    close_handle.argtypes = (wintypes.HANDLE,)
    close_handle.restype = wintypes.BOOL

    handle = create_mutex(None, False, _MUTEX_NAME)
    if not handle:
        logger.error("[RUNTIME_OWNER] CreateMutexW failed winerror=%s", ctypes.get_last_error())
        return False
    if ctypes.get_last_error() == _ERROR_ALREADY_EXISTS:
        close_handle(handle)
        logger.warning("[RUNTIME_OWNER] another KIO runtime already owns the service")
        return False
    _handle = int(handle)
    logger.info("[RUNTIME_OWNER] acquired pid=%s", os.getpid())
    return True


def release_runtime_owner() -> None:
    global _handle
    if _handle is None or os.name != "nt":
        return
    import ctypes
    from ctypes import wintypes
    kernel32 = ctypes.WinDLL("kernel32", use_last_error=True)
    kernel32.CloseHandle.argtypes = (wintypes.HANDLE,)
    kernel32.CloseHandle.restype = wintypes.BOOL
    kernel32.CloseHandle(_handle)
    _handle = None
    logger.info("[RUNTIME_OWNER] released pid=%s", os.getpid())
