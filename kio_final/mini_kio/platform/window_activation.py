"""
window_activation.py — Windows Foreground Activation

Brings a specific browser window to the foreground using its tracked PID.

No system-wide scanning. No process enumeration fallback.
Only operates on the exact PID provided by the caller.
"""

import ctypes
import logging
from typing import List

logger = logging.getLogger(__name__)

# ── Windows constants ─────────────────────────────────────────────

SW_RESTORE = 9
SW_SHOW = 5

_CALLBACK_TYPE = ctypes.WINFUNCTYPE(ctypes.c_bool, ctypes.c_int, ctypes.c_int)

# ── ctypes bindings (loaded once at module level) ─────────────────

_user32 = ctypes.windll.user32

_EnumWindows = _user32.EnumWindows
_GetWindowThreadProcessId = _user32.GetWindowThreadProcessId
_IsWindowVisible = _user32.IsWindowVisible
_IsIconic = _user32.IsIconic
_ShowWindow = _user32.ShowWindow
_SetForegroundWindow = _user32.SetForegroundWindow
_BringWindowToTop = _user32.BringWindowToTop
_GetForegroundWindow = _user32.GetForegroundWindow
_AttachThreadInput = _user32.AttachThreadInput
_GetWindowTextLengthW = _user32.GetWindowTextLengthW


# ── Internal helpers ──────────────────────────────────────────────


def _find_windows_for_pid(pid: int) -> List[int]:
    """Return visible top-level window handles for a single process PID."""
    target = {pid}
    results: List[int] = []

    def callback(hwnd: int, _param) -> bool:
        hwnd_pid = ctypes.c_ulong()
        _GetWindowThreadProcessId(hwnd, ctypes.byref(hwnd_pid))
        # Patch 3: Filter for windows with titles (actual UI windows)
        if hwnd_pid.value in target and _IsWindowVisible(hwnd):
            if _GetWindowTextLengthW(hwnd) > 0:
                results.append(hwnd)
        return True

    _EnumWindows(_CALLBACK_TYPE(callback), None)
    return results


def _force_foreground(hwnd: int) -> None:
    """Bring a window to foreground, working around Windows foreground lock
    by attaching to the foreground thread's input queue."""
    fore_hwnd = _GetForegroundWindow()
    if fore_hwnd == hwnd:
        return

    fore_tid = ctypes.c_ulong()
    target_tid = ctypes.c_ulong()
    _GetWindowThreadProcessId(fore_hwnd, ctypes.byref(fore_tid))
    _GetWindowThreadProcessId(hwnd, ctypes.byref(target_tid))

    attached = False
    if fore_tid.value and target_tid.value and fore_tid.value != target_tid.value:
        try:
            _AttachThreadInput(fore_tid, target_tid, True)
            attached = True
        except Exception:
            pass

    try:
        if _IsIconic(hwnd):
            _ShowWindow(hwnd, SW_RESTORE)
        _ShowWindow(hwnd, SW_SHOW)
        _SetForegroundWindow(hwnd)
        _BringWindowToTop(hwnd)
    finally:
        if attached:
            try:
                _AttachThreadInput(fore_tid, target_tid, False)
            except Exception:
                pass


# ── Public API ────────────────────────────────────────────────────


def activate_browser_window(pid: int) -> bool:
    """
    Bring a browser window to the foreground by exact PID.

    Uses only the given PID — never scans all browser processes.
    Returns True if at least one window was activated.
    Never raises.
    """
    if pid <= 0:
        return False
    try:
        hwnds = _find_windows_for_pid(pid)
        if not hwnds:
            logger.warning("[WINDOW] No visible windows found for PID %d", pid)
            return False
        _force_foreground(hwnds[0])
        logger.info("[WINDOW] Activated window for PID %d (hwnd=%d)", pid, hwnds[0])
        return True
    except Exception as exc:
        logger.warning("[WINDOW] Activation error for PID %d: %s", pid, exc)
        return False


def try_activate_browser(pid: int) -> None:
    """
    Safe activation wrapper — never raises, never breaks functionality.

    Only operates on the given PID.  If pid <= 0, does nothing.
    """
    if pid <= 0:
        return
    try:
        activate_browser_window(pid)
    except Exception:
        pass
