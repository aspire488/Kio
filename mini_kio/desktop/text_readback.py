"""Read the foreground window's primary text control (read-only, ctypes).

Generic capability: any Win32 app whose content lives in a standard
Edit/RichEdit child control (Notepad, Word, editors, search fields) can be
read back so TYPE / PASTE / COPY can be VERIFIED against real application
state. Apps with nonstandard rendering (browsers, games) return a truthful
"cannot read" result - never a fabricated success.
"""
import ctypes
from ctypes import wintypes

_user32 = ctypes.windll.user32
_EnumChildWindows = _user32.EnumChildWindows
_EnumChildProc = ctypes.WINFUNCTYPE(ctypes.c_bool, wintypes.HWND, wintypes.LPARAM)
_GetWindowTextLengthW = _user32.GetWindowTextLengthW
_GetWindowTextW = _user32.GetWindowTextW
_GetForegroundWindow = _user32.GetForegroundWindow
_GetClassNameW = _user32.GetClassNameW


def _class_name(hwnd):
    buf = ctypes.create_unicode_buffer(256)
    _GetClassNameW(hwnd, buf, 255)
    return buf.value


def _collect_text_controls(root):
    """Collect child controls that hold editable text (Edit/RichEdit family)."""
    found = []

    def _cb(hwnd, lparam):
        cls = _class_name(hwnd)
        if "Edit" in cls or "RichEdit" in cls:
            found.append(hwnd)
        return True

    _EnumChildWindows(root, _EnumChildProc(_cb), 0)
    return found


def read_foreground_text():
    """Return {success, text, chars, control_class} for the foreground window.

    Returns success=False (never fake data) when the foreground window has no
    readable standard text control.
    """
    try:
        fore = _GetForegroundWindow()
        if not fore:
            return {"success": False, "message": "No foreground window."}
        controls = _collect_text_controls(fore)
        if not controls:
            return {
                "success": False,
                "message": "Foreground window has no readable text control.",
                "hwnd": int(fore),
                "class": _class_name(fore),
            }
        # Prefer the largest control (the main content pane, not a small field).
        best = None
        best_len = -1
        for hwnd in controls:
            ln = _GetWindowTextLengthW(hwnd)
            if ln > best_len:
                best_len = ln
                best = hwnd
        if best is None or best_len < 0:
            return {"success": False, "message": "Text control is empty."}
        buf = ctypes.create_unicode_buffer(best_len + 1)
        _GetWindowTextW(best, buf, best_len + 1)
        text = buf.value
        return {
            "success": True,
            "text": text,
            "chars": len(text),
            "hwnd": int(fore),
            "control_class": _class_name(best),
        }
    except Exception as exc:  # pragma: no cover - defensive
        return {"success": False, "message": "read_foreground_text failed: %s" % exc}


def payload_present(payload, window_text):
    """Normalized containment check - meaningful content must actually be there."""
    if not payload or not window_text:
        return False
    norm = lambda s: " ".join(s.lower().split())
    return norm(payload) in norm(window_text)
