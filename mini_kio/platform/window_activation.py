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
_GetWindowTextW = _user32.GetWindowTextW
_GetWindowLongW = _user32.GetWindowLongW

# Foreground-lock workaround bindings (taskbar-flashing fix)
_keybd_event = _user32.keybd_event
_SetWindowPos = _user32.SetWindowPos

# Window style constants
_GWL_EXSTYLE = -20
_WS_EX_TOOLWINDOW = 0x00000080

# SetWindowPos constants
_HWND_TOPMOST = -1
_HWND_NOTOPMOST = -2
_SWP_NOSIZE = 0x0001
_SWP_NOMOVE = 0x0002
_SWP_SHOWWINDOW = 0x0040
_KEYEVENTF_KEYUP = 0x0002
_VK_MENU = 0x12


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
    """Bring a window to the SCREEN foreground (never just the taskbar).

    Windows refuses SetForegroundWindow for a process that does not hold the
    foreground activation lock — the classic symptom is the target app only
    BLINKING in the taskbar instead of appearing. The canonical workaround
    sequence:
      1. restore from minimized + show the window
      2. attach our input queue to the foreground thread (when different)
      3. simulate a user ALT keystroke — the OS grants foreground privilege
         only to the process "receiving input", and a synthetic ALT press
         releases that lock
      4. SetForegroundWindow + BringWindowToTop
      5. force the z-order to TOPMOST then release it, guaranteeing the
         window is drawn above every other window
    """
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
        # Foreground-lock workaround: a synthetic ALT press makes the system
        # believe the user is switching apps, releasing the activation lock
        # so SetForegroundWindow succeeds (taskbar-flashing fix).
        try:
            _keybd_event(_VK_MENU, 0, 0, 0)
            _SetForegroundWindow(hwnd)
            _keybd_event(_VK_MENU, 0, _KEYEVENTF_KEYUP, 0)
        except Exception:
            _SetForegroundWindow(hwnd)
        _BringWindowToTop(hwnd)
        # Force the window above everything, then release TOPMOST so it is
        # simply the foreground window (not pinned on top forever).
        try:
            _SetWindowPos(hwnd, _HWND_TOPMOST, 0, 0, 0, 0,
                          _SWP_NOMOVE | _SWP_NOSIZE | _SWP_SHOWWINDOW)
            _SetWindowPos(hwnd, _HWND_NOTOPMOST, 0, 0, 0, 0,
                          _SWP_NOMOVE | _SWP_NOSIZE | _SWP_SHOWWINDOW)
        except Exception:
            pass
    finally:
        if attached:
            try:
                _AttachThreadInput(fore_tid, target_tid, False)
            except Exception:
                pass


# ── Public API ────────────────────────────────────────────────────


def list_visible_windows() -> list[dict]:
    """
    Enumerate the user's visible top-level application windows (pure read).

    Returns a list of {"pid": int, "title": str, "is_foreground": bool}.
    Excludes: tool windows (taskbar/popups), empty-title windows, and windows
    owned by the current process (KIO's own console). No activation, no side
    effects, no process scanning — a single fast EnumWindows pass.
    """
    import os

    self_pid = os.getpid()
    foreground = _GetForegroundWindow()
    results: list[dict] = []

    def callback(hwnd: int, _param) -> bool:
        if not _IsWindowVisible(hwnd):
            return True
        try:
            style = _GetWindowLongW(hwnd, _GWL_EXSTYLE)
        except Exception:
            style = 0
        if style & _WS_EX_TOOLWINDOW:
            return True
        pid = ctypes.c_ulong()
        _GetWindowThreadProcessId(hwnd, ctypes.byref(pid))
        if pid.value == self_pid:
            return True
        # Elevated applications (e.g. DaVinci Resolve running as admin) cannot
        # have their window titles read cross-integrity: GetWindowTextLengthW
        # returns 0 even though the window is a real visible application.
        # Dropping them here is exactly why "Resolve was open but not listed".
        # Return the window with an empty title and let the desktop-state layer
        # decide by resolving the owning executable (system shells are skipped
        # there; real apps are kept and shown by application name).
        length = _GetWindowTextLengthW(hwnd)
        title = ""
        if length > 0:
            buff = ctypes.create_unicode_buffer(length + 1)
            _GetWindowTextW(hwnd, buff, length + 1)
            title = (buff.value or "").strip()
        results.append({
            "pid": int(pid.value),
            "title": title,
            "is_foreground": hwnd == foreground,
        })
        return True

    try:
        _EnumWindows(_CALLBACK_TYPE(callback), None)
    except Exception as exc:
        logger.warning("[WINDOW] list_visible_windows failed: %s", exc)
    return results


def activate_window(pid: int) -> bool:
    """
    Bring an arbitrary application window to the foreground by PID.

    Generic activation (any app, not just browsers). Never scans processes;
    only operates on the exact PID supplied by the caller.
    """
    if pid <= 0:
        return False
    try:
        hwnds = _find_windows_for_pid(pid)
        if not hwnds:
            return False
        _force_foreground(hwnds[0])
        return True
    except Exception as exc:
        logger.warning("[WINDOW] Activation error for PID %d: %s", pid, exc)
        return False


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
