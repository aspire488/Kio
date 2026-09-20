"""Throwaway probe: does a console child spawned from a console-less parent
(pythonw.exe, i.e. how KIO runs) create a *visible* console window?

Run the outer half with pythonw.exe.  The inner half (child mode) spawns
cmd.exe the three ways KIO actually does and reports which ones produced a
top-level ConsoleWindowClass window.
"""
from __future__ import annotations

import ctypes
import ctypes.wintypes as wt
import json
import subprocess
import sys
import time

CREATE_NO_WINDOW = 0x08000000
CREATE_BREAKAWAY_FROM_JOB = 0x00100000

user32 = ctypes.windll.user32
EnumWindows = user32.EnumWindows
EnumWindowsProc = ctypes.WINFUNCTYPE(wt.BOOL, wt.HWND, wt.LPARAM)


def visible_console_windows() -> list[dict]:
    """Top-level, visible ConsoleWindowClass windows and their owning PID."""
    found: list[dict] = []

    def _cb(hwnd, _lparam):
        if not user32.IsWindowVisible(hwnd):
            return True
        cls = ctypes.create_unicode_buffer(256)
        user32.GetClassNameW(hwnd, cls, 256)
        if cls.value not in ("ConsoleWindowClass", "PseudoConsoleWindow"):
            return True
        pid = wt.DWORD()
        user32.GetWindowThreadProcessId(hwnd, ctypes.byref(pid))
        title = ctypes.create_unicode_buffer(512)
        user32.GetWindowTextW(hwnd, title, 512)
        found.append({"pid": pid.value, "class": cls.value, "title": title.value})
        return True

    EnumWindows(EnumWindowsProc(_cb), 0)
    return found


def _run_case(label: str, **kwargs) -> dict:
    before = {(w["pid"], w["title"]) for w in visible_console_windows()}
    # A child that lives long enough for us to sample its window.
    proc = subprocess.Popen(
        ["cmd.exe", "/c", "ping -n 3 127.0.0.1 > nul"],
        shell=False, **kwargs,
    )
    time.sleep(1.0)
    during = visible_console_windows()
    ours = [
        w for w in during
        if (w["pid"], w["title"]) not in before and w["pid"] == proc.pid
    ]
    proc.kill()
    proc.wait(timeout=5)
    return {
        "case": label,
        "child_pid": proc.pid,
        "visible_window_while_child_alive": bool(ours),
        "windows": ours,
    }


def child_mode() -> None:
    results = [
        _run_case("no flags, no redirection"),
        _run_case("capture_output=True (piped stdio)",
                  stdout=subprocess.PIPE, stderr=subprocess.PIPE, stdin=subprocess.DEVNULL),
        _run_case("creationflags=0x00100000 (CREATE_BREAKAWAY_FROM_JOB)",
                  creationflags=CREATE_BREAKAWAY_FROM_JOB),
        _run_case("creationflags=0x08000000 (CREATE_NO_WINDOW)",
                  creationflags=CREATE_NO_WINDOW),
    ]
    parent_has_console = bool(ctypes.windll.kernel32.GetConsoleWindow())
    print(json.dumps({
        "parent_has_console": parent_has_console,
        "parent_exe": sys.executable,
        "results": results,
    }, indent=2))


if __name__ == "__main__":
    child_mode()
