"""Verify KIO's internal helper processes never open a console window.

Run this with ``pythonw.exe`` (or plain python — it re-execs itself under
pythonw when it detects it has a console, since that is how KIO runs).

It invokes the real spawn paths KIO uses during normal operation while a
sampler thread watches for *new* top-level console windows, so even a
briefly-flashing window is caught.  Exit code 0 means no window appeared.
"""
from __future__ import annotations

import ctypes
import ctypes.wintypes as wt
import json
import os
import subprocess
import sys
import threading
import time

CONSOLE_CLASSES = ("ConsoleWindowClass", "PseudoConsoleWindow")
user32 = ctypes.windll.user32
EnumWindows = user32.EnumWindows
EnumWindowsProc = ctypes.WINFUNCTYPE(wt.BOOL, wt.HWND, wt.LPARAM)


def console_windows() -> list[dict]:
    found: list[dict] = []

    def _cb(hwnd, _lparam):
        if not user32.IsWindowVisible(hwnd):
            return True
        cls = ctypes.create_unicode_buffer(256)
        user32.GetClassNameW(hwnd, cls, 256)
        if cls.value not in CONSOLE_CLASSES:
            return True
        pid = wt.DWORD()
        user32.GetWindowThreadProcessId(hwnd, ctypes.byref(pid))
        title = ctypes.create_unicode_buffer(512)
        user32.GetWindowTextW(hwnd, title, 512)
        found.append({"pid": pid.value, "class": cls.value, "title": title.value})
        return True

    EnumWindows(EnumWindowsProc(_cb), 0)
    return found


class WindowWatcher:
    """Poll for new console windows while spawn paths are exercised."""

    def __init__(self) -> None:
        self._stop = threading.Event()
        self.seen: list[dict] = []
        self._baseline = {(w["pid"], w["class"]) for w in console_windows()}
        self._thread = threading.Thread(target=self._run, daemon=True)

    def _run(self) -> None:
        while not self._stop.is_set():
            for w in console_windows():
                key = (w["pid"], w["class"])
                if key not in self._baseline:
                    self._baseline.add(key)
                    self.seen.append(dict(w, t=time.time()))
            time.sleep(0.005)

    def __enter__(self) -> "WindowWatcher":
        self._thread.start()
        return self

    def __exit__(self, *exc: object) -> None:
        self._stop.set()
        self._thread.join(timeout=2.0)


def _invoke(label: str, fn) -> dict:
    """Run one spawn path and record its result plus any window it created."""
    with WindowWatcher() as watcher:
        try:
            value = fn()
            error = None
        except Exception as exc:  # noqa: BLE001
            value, error = None, f"{type(exc).__name__}: {exc}"
        time.sleep(0.15)  # let a short-lived child finish before sampling stops
    return {
        "path": label,
        "ok": error is None,
        "error": error,
        "value": value if isinstance(value, (str, int, float, bool, type(None))) else "...",
        "windows_created": watcher.seen,
    }


def exercise() -> list[dict]:
    results: list[dict] = []

    # 1. TerminalProvider — the site that used CREATE_BREAKAWAY_FROM_JOB.
    from mini_kio.core.providers.terminal_provider import TerminalProvider

    tp = TerminalProvider()

    def _terminal() -> dict:
        r = tp.execute("run_command", "dir")
        return {
            "success": r.get("success"),
            "exit_code": r.get("exit_code"),
            "message_len": len(r.get("message") or ""),
            "has_stdout": bool((r.get("stdout") or "").strip()),
            "message_head": (r.get("message") or "")[:60].replace("\n", " "),
        }

    results.append(_invoke("TerminalProvider.run_command('dir')", _terminal))

    # 2. WindowManager powershell probe.
    from mini_kio.desktop import WindowManager

    results.append(_invoke(
        "WindowManager.list_windows()", lambda: len(WindowManager.list_windows())))

    # 3. App discovery powershell probe (Get-StartApps).
    from mini_kio.core import app_operator

    results.append(_invoke(
        "app_operator._uwp_start_apps()", lambda: len(app_operator._uwp_start_apps())))

    # 4. Diagnostics fallback tasklist probe.
    from mini_kio.core import kio_diagnostics

    results.append(_invoke(
        "kio_diagnostics._is_process_running_tasklist('notepad')",
        lambda: kio_diagnostics._is_process_running_tasklist("notepad")))

    # 5. Operational-health nvidia-smi probe (the on-demand GPU read).
    from mini_kio.core import operational_health

    results.append(_invoke(
        "operational_health._system_metrics()",
        lambda: operational_health._system_metrics().get("gpu")))

    # 6. MCP git server subprocess.
    from mini_kio.core.mcp.servers.mcp_git_server import GitMCPServer

    results.append(_invoke(
        "GitMCPServer._git(repo, 'status', '--porcelain')",
        lambda: GitMCPServer()._git(os.getcwd(), "status", "--porcelain")[0]))

    # 7. MCP docker server subprocess (docker may be absent — either way no window).
    from mini_kio.core.mcp.servers.mcp_docker_server import _run_docker

    results.append(_invoke(
        "mcp_docker._run_docker(['version'])", lambda: _run_docker(["version"])["success"]))

    # 8. Terminal provider's allowlist must still refuse dangerous commands.
    results.append(_invoke(
        "TerminalProvider refuses 'rm -rf /'",
        lambda: tp.execute("run_command", "rm -rf /").get("success")))

    return results


def main() -> int:
    if ctypes.windll.kernel32.GetConsoleWindow():
        pythonw = os.path.join(os.path.dirname(sys.executable), "pythonw.exe")
        if os.path.exists(pythonw):
            root = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
            env = dict(os.environ)
            env["PYTHONPATH"] = root + os.pathsep + env.get("PYTHONPATH", "")
            proc = subprocess.run(
                [pythonw, os.path.abspath(__file__)] + sys.argv[1:],
                capture_output=True, text=True, timeout=300, cwd=root, env=env,
            )
            sys.stdout.write(proc.stdout)
            sys.stderr.write(proc.stderr)
            return proc.returncode

    report = {
        "parent_has_console": bool(ctypes.windll.kernel32.GetConsoleWindow()),
        "parent_exe": sys.executable,
        "paths": exercise(),
    }
    total_windows = sum(len(p["windows_created"]) for p in report["paths"])
    report["total_windows_created"] = total_windows
    report["result"] = "PASS" if total_windows == 0 else "FAIL"
    print(json.dumps(report, indent=2))
    return 0 if total_windows == 0 else 1


if __name__ == "__main__":
    sys.exit(main())
