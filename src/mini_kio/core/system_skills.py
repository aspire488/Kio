"""
Mini-KIO safe system actions: browser, editor, screenshot, notifications, light system stats.

Subprocess calls use argv lists only (``shell=False``). Nothing here executes AI output.
"""

from __future__ import annotations

import json
import logging
import os
import platform
import shutil
import socket
import subprocess
import time
import webbrowser
from pathlib import Path
from typing import Any, TypedDict

from .config import SAFE_MODE, APP_PATHS

logger = logging.getLogger(__name__)

YOUTUBE_URL = "https://www.youtube.com"

# Whitelisted browser targets (never pass raw user text to the shell).
_WEB_URLS: dict[str, str] = {
    "youtube": YOUTUBE_URL,
    "google": "https://www.google.com",
    "github": "https://github.com",
    "gmail": "https://mail.google.com",
    "stackoverflow": "https://stackoverflow.com",
    "reddit": "https://www.reddit.com",
}

# Windows known folders via explorer (shell: namespace only — fixed strings).
_WIN_SHELL_FOLDERS: dict[str, str] = {
    "downloads": "shell:Downloads",
    "documents": "shell:Documents",
    "desktop": "shell:Desktop",
    "pictures": "shell:Pictures",
    "music": "shell:Music",
    "videos": "shell:Videos",
}

# Normalize multi-word phrases to internal keys (still must resolve in maps below).
_OPEN_ALIASES: dict[str, str] = {
    "visual studio code": "vscode",
    "vs code": "vscode",
    "google chrome": "chrome",
    "microsoft edge": "edge",
    "file explorer": "explorer",
    "windows explorer": "explorer",
    "windows terminal": "terminal",
    "command prompt": "cmd",
    "snipping tool": "snipping tool",
    "task manager": "task manager",
}

_MAX_OPEN_TARGET_LEN = 80


def _normalize_open_name(raw: str) -> str:
    t = " ".join(raw.strip().lower().split())
    return t.strip(".,!?;:")[:_MAX_OPEN_TARGET_LEN]


def _popen_detached(argv: list[str]) -> None:
    """Start a child process without waiting; argv is fixed — no shell."""
    kwargs: dict[str, Any] = {
        "stdout": subprocess.DEVNULL,
        "stderr": subprocess.DEVNULL,
        "start_new_session": True,
    }
    if platform.system() == "Windows":
        creation = getattr(subprocess, "CREATE_NEW_PROCESS_GROUP", 0)
        detached = getattr(subprocess, "DETACHED_PROCESS", 0)
        if creation | detached:
            kwargs["creationflags"] = creation | detached
    if SAFE_MODE:
        print(f"[DEV MODE] command launch requested: Popen {argv}")
    else:
        subprocess.Popen(argv, **kwargs)


def _vscode_argv() -> list[str]:
    binary = (APP_PATHS.get("vscode") or "code").strip()
    if not binary or any(c in binary for c in ";&|<>$\n\r`"):
        raise ValueError("invalid_vscode_path")
    return [binary]


_APP_CACHE: dict[str, str] = {}

def discover_application(target: str) -> str | None:
    """Discover executable recursively within 3 levels deep."""
    if target in _APP_CACHE:
        return _APP_CACHE[target]
    
    target_exe = target.lower()
    if not target_exe.endswith(".exe"):
        target_exe += ".exe"
    
    if target_exe == "vscode.exe":
        target_exe = "code.exe"
        
    search_dirs = [
        os.environ.get("ProgramW6432", "C:\\Program Files"),
        os.environ.get("ProgramFiles(x86)", "C:\\Program Files (x86)"),
        os.path.join(os.environ.get("LOCALAPPDATA", "C:\\Users\\Default\\AppData\\Local"), "Programs"),
        os.environ.get("LOCALAPPDATA", "C:\\Users\\Default\\AppData\\Local"),
    ]
    
    for sdir in search_dirs:
        if not os.path.exists(sdir):
            continue
        try:
            for root, dirs, files in os.walk(sdir):
                depth = root[len(sdir):].count(os.sep)
                if depth > 3:
                    dirs.clear()
                    continue
                for f in files:
                    if f.lower() == target_exe:
                        found = os.path.join(root, f)
                        _APP_CACHE[target] = found
                        return found
        except Exception:
            pass
    return None

def close_application(target: str) -> ActionResult:
    target_exe = target.lower()
    if not target_exe.endswith(".exe"):
        target_exe += ".exe"
    if target_exe == "vscode.exe":
        target_exe = "code.exe"
        
    try:
        if SAFE_MODE:
            print(f"[DEV MODE] command launch requested: taskkill {target_exe}")
        else:
            subprocess.run(["taskkill", "/IM", target_exe, "/F"], capture_output=True, check=True)
        return _ok(f"Closed {target}.")
    except Exception as e:
        return _fail(f"Could not close {target}: {e}")


def _linux_folder_path(folder_key: str) -> Path | None:
    home = Path.home()
    sub = {
        "downloads": home / "Downloads",
        "documents": home / "Documents",
        "desktop": home / "Desktop",
        "pictures": home / "Pictures",
        "music": home / "Music",
        "videos": home / "Videos",
    }.get(folder_key)
    return sub


def launch_application(app_name: str) -> ActionResult:
    """
    Open a whitelisted website, Windows shell folder, or application.

    Uses ``subprocess`` with argv lists only (no shell, no AI-driven execution).
    Unknown names return a safe error — arbitrary paths or commands are rejected.
    """
    key = _normalize_open_name(app_name)
    if not key:
        _log_automation("launch_application", False, reason="empty")
        return _fail("Say what to open, e.g. open chrome or open downloads.")

    key = _OPEN_ALIASES.get(key, key)
    if key in ("code",):
        key = "vscode"

    if key in _WEB_URLS:
        try:
            if SAFE_MODE:
                print("[DEV MODE] browser launch requested")
            else:
                webbrowser.open(_WEB_URLS[key])
            _log_automation("launch_application", True, kind="web", target=key)
            return _ok(f"Opened {_WEB_URLS[key]} in your browser.")
        except Exception as e:
            _log_automation("launch_application", False, kind="web", target=key)
            return _fail(f"Could not open browser: {e}")

    sysname = platform.system()

    if key in _WIN_SHELL_FOLDERS:
        shell_arg = _WIN_SHELL_FOLDERS[key]
        if sysname == "Windows":
            try:
                _popen_detached(["explorer", shell_arg])
                _log_automation("launch_application", True, kind="folder", target=key)
                return _ok(f"Opened {key.replace('_', ' ')}.")
            except Exception as e:
                _log_automation("launch_application", False, kind="folder", target=key)
                return _fail(f"Could not open folder: {e}")
        lp = _linux_folder_path(key)
        if lp is not None:
            try:
                if lp.is_dir():
                    _popen_detached(["xdg-open", str(lp)])
                else:
                    _popen_detached(["xdg-open", str(lp.parent)])
                _log_automation("launch_application", True, kind="folder", target=key)
                return _ok(f"Opened {key}.")
            except Exception as e:
                _log_automation("launch_application", False, kind="folder", target=key)
                return _fail(f"Could not open folder: {e}")
        _log_automation("launch_application", False, kind="folder", target=key)
        return _fail("Folder shortcuts are only configured for Windows and Linux.")

    if key == "vscode":
        try:
            cmd = _vscode_argv()
            _popen_detached(cmd)
            _log_automation("launch_application", True, kind="app", target="vscode")
            return _ok("Launched VS Code.")
        except ValueError:
            _log_automation("launch_application", False, reason="invalid_path", target="vscode")
            return _fail("Invalid editor path in configuration.")
        except FileNotFoundError:
            _log_automation("launch_application", False, reason="not_found", target="vscode")
            return _fail("Editor not found. Set VSCODE_PATH in .env or install the `code` command.")
        except Exception as e:
            _log_automation("launch_application", False, target="vscode")
            return _fail(f"Failed to launch editor: {e}")

    if sysname == "Windows":
        # 1. Check cache / 2. Discover executable
        exe_path = discover_application(key)
        if exe_path:
            argv = [exe_path]
        else:
            argv = [key]
        
        # 3. Launch via subprocess.Popen
        try:
            _popen_detached(argv)
            _log_automation("launch_application", True, kind="app", target=key)
            return _ok(f"Started {key}.")
        except Exception as e:
            _log_automation("launch_application", False, kind="app", target=key)
            return _fail(f"Could not start {key}. Error: {e}")

    # Linux fallback omitted for brevity if user only uses Windows (but code is unchanged below if needed)
    linux_map: dict[str, list[str]] = {
        "chrome": ["google-chrome", "chromium-browser", "chromium", "chrome"],
        "firefox": ["firefox"],
        "edge": ["microsoft-edge"],
        "calculator": [APP_PATHS.get("calculator", "gnome-calculator")],
        "terminal": [APP_PATHS.get("terminal", "x-terminal-emulator")],
        "explorer": [APP_PATHS.get("files", "xdg-open"), str(Path.home())],
    }
    if key in linux_map:
        spec = linux_map[key]
        if key == "explorer":
            bin0, path = spec[0], spec[1]
            try:
                _popen_detached([bin0, path])
                _log_automation("launch_application", True, kind="app", target=key)
                return _ok("Opened file manager.")
            except Exception as e:
                _log_automation("launch_application", False, kind="app", target=key)
                return _fail(f"Could not open file manager: {e}")
        for exe in spec:
            if not exe:
                continue
            try:
                _popen_detached([exe])
                _log_automation("launch_application", True, kind="app", target=key)
                return _ok(f"Started {key}.")
            except FileNotFoundError:
                continue
            except Exception as e:
                _log_automation("launch_application", False, kind="app", target=key)
                return _fail(f"Could not start {key}: {e}")

    _log_automation("launch_application", False, reason="unknown_target", target=key)
    return _fail(f"Could not start \"{key}\" (unknown target).")

def open_file(filepath: str) -> ActionResult:
    p = Path(filepath).expanduser().resolve()
    if not p.exists():
        return _fail(f"File or folder not found: {filepath}")
    sysname = platform.system()
    try:
        if sysname == "Windows":
            os.startfile(str(p))
        elif sysname == "Darwin":
            _popen_detached(["open", str(p)])
        else:
            _popen_detached(["xdg-open", str(p)])
        return _ok(f"Opened file: {p.name}")
    except Exception as e:
        return _fail(f"Failed to open file: {e}")

def edit_file(filepath: str, content: str, mode: str = "w") -> ActionResult:
    p = Path(filepath).expanduser().resolve()
    lower_p = str(p).lower()
    sysname = platform.system()
    if sysname == "Windows":
        if "c:\\windows" in lower_p or "c:\\program files" in lower_p:
            return _fail("Security error: Cannot edit system directories.")
    elif sysname == "Linux" or sysname == "Darwin":
        if lower_p.startswith(("/bin", "/sbin", "/etc", "/usr", "/var", "/boot", "/system")):
            return _fail("Security error: Cannot edit system directories.")
            
    try:
        with open(p, mode, encoding="utf-8") as f:
            f.write(content)
        action_name = "Appended to" if mode == "a" else "Wrote to"
        return _ok(f"{action_name} {p.name}")
    except Exception as e:
        return _fail(f"Failed to edit file: {e}")

def calculate(expression: str) -> ActionResult:
    import ast
    import operator
    
    op_map = {
        ast.Add: operator.add,
        ast.Sub: operator.sub,
        ast.Mult: operator.mul,
        ast.Div: operator.truediv,
        ast.USub: operator.neg,
        ast.UAdd: operator.pos,
    }
    
    def _eval(node: ast.expr) -> Any:
        if isinstance(node, ast.Constant) and isinstance(node.value, (int, float)):
            return node.value
        elif isinstance(node, ast.BinOp):
            return op_map[type(node.op)](_eval(node.left), _eval(node.right))
        elif isinstance(node, ast.UnaryOp):
            return op_map[type(node.op)](_eval(node.operand))
        raise TypeError("Unsupported operation")

    e = expression.strip()
    try:
        node = ast.parse(e, mode='eval')
        result = _eval(node.body)
        res_str = f"Result of {e}: {result}"
        send_notification("KIO Calculator", res_str)
        return _ok(res_str)
    except ZeroDivisionError:
        return _fail("Cannot divide by zero")
    except Exception as err:
        return _fail(f"Calculation failed: {err}")

def play_youtube(query: str) -> ActionResult:
    if query.startswith("http"):
        url = query
    else:
        from urllib.parse import quote
        url = f"https://www.youtube.com/results?search_query={quote(query)}"
    try:
        if SAFE_MODE:
            print("[DEV MODE] browser launch requested")
        else:
            webbrowser.open(url)
        return _ok(f"Opened YouTube for search: {query}")
    except Exception as e:
        return _fail(f"Failed to open YouTube: {e}")

def search_google(query: str) -> ActionResult:
    from urllib.parse import quote
    url = f"https://www.google.com/search?q={quote(query)}"
    try:
        if SAFE_MODE:
            print("[DEV MODE] browser launch requested")
        else:
            webbrowser.open(url)
        return _ok(f"Searched Google for: {query}")
    except Exception as e:
        return _fail(f"Failed to search Google: {e}")

def perform_app_task(app: str, action: str) -> ActionResult:
    app_low = app.lower()
    if "calc" in app_low:
        if action.startswith("calculate "):
            action = action[10:]
        # Open calculator
        launch_application("calculator")
        return calculate(action)
    return _fail(f"Task '{action}' for app '{app}' is not supported.")


class ActionResult(TypedDict, total=False):
    """Normalized return shape for all automation helpers."""

    success: bool
    message: str
    data: dict[str, Any]


def _log_automation(action: str, ok: bool, **extra: Any) -> None:
    payload: dict[str, Any] = {"evt": "automation", "action": action, "ok": ok}
    payload.update(extra)
    (logger.info if ok else logger.warning)(json.dumps(payload, default=str))


def _ok(msg: str) -> ActionResult:
    return {"success": True, "message": msg}


def _fail(msg: str) -> ActionResult:
    return {"success": False, "message": msg}


def _ps_escape(s: str, max_len: int = 240) -> str:
    t = (s or "")[:max_len].replace("'", "''")
    return f"'{t}'"


def send_notification(title: str, message: str) -> None:
    """
    Show a local desktop notification (never Telegram). Never raises.

    Windows: try BurntToast; fallback to WinForms message box.
    Linux: ``notify-send``; fallback print to stderr.
    macOS: ``osascript`` display notification; fallback print.
    """
    title = (title or "KIO")[:200]
    message = (message or "")[:2000]
    try:
        sysname = platform.system()
        if sysname == "Windows":
            t_esc = _ps_escape(title)
            m_esc = _ps_escape(message)
            toast_cmd = (
                "try { Import-Module BurntToast -ErrorAction Stop; "
                + f"New-BurntToastNotification -Text {t_esc},{m_esc} "
                + "} catch { Add-Type -AssemblyName System.Windows.Forms; "
                + f"[System.Windows.Forms.MessageBox]::Show({m_esc},{t_esc})"
                + " }"
            )
            if SAFE_MODE:
                print("[DEV MODE] command launch requested: powershell notification")
            else:
                subprocess.run(
                    [
                        "powershell",
                        "-NoProfile",
                        "-NonInteractive",
                        "-ExecutionPolicy",
                        "Bypass",
                        "-Command",
                        toast_cmd,
                    ],
                    capture_output=True,
                    timeout=30,
                    text=True,
                )
            _log_automation("notification", True, channel="windows")
            return

        if sysname == "Darwin":
            script = (
                f'display notification {json.dumps(message)} '
                f'with title {json.dumps(title)}'
            )
            if SAFE_MODE:
                print("[DEV MODE] command launch requested: osascript notification")
            else:
                subprocess.run(
                    ["osascript", "-e", script],
                    capture_output=True,
                    timeout=15,
                    text=True,
                )
            _log_automation("notification", True, channel="macos")
            return

        # Linux / BSD
        if SAFE_MODE:
            print("[DEV MODE] command launch requested: notify-send")
            class _DummyR: returncode = 0
            r = _DummyR()
        else:
            r = subprocess.run(
                ["notify-send", title, message],
                capture_output=True,
                timeout=10,
                text=True,
            )
        if r.returncode == 0:
            _log_automation("notification", True, channel="notify-send")
        else:
            print(f"[KIO notify] {title}: {message}", flush=True)
            _log_automation("notification", True, channel="print")
    except Exception as e:
        logger.debug("send_notification failed: %s", e)
        try:
            print(f"[KIO notify] {title}: {message}", flush=True)
        except OSError:
            pass
        _log_automation("notification", False, error_type=type(e).__name__)


def _active_window_windows() -> dict[str, str] | None:
    try:
        import ctypes
        from ctypes import wintypes

        user32 = ctypes.windll.user32
        kernel32 = ctypes.windll.kernel32
        hwnd = user32.GetForegroundWindow()
        if not hwnd:
            return None
        n = user32.GetWindowTextLengthW(hwnd) + 1
        buf = ctypes.create_unicode_buffer(n)
        user32.GetWindowTextW(hwnd, buf, n)
        wtitle = buf.value or ""

        pid = wintypes.DWORD()
        user32.GetWindowThreadProcessId(hwnd, ctypes.byref(pid))
        app = "unknown"
        PROCESS_QUERY_LIMITED_INFORMATION = 0x1000
        h = kernel32.OpenProcess(PROCESS_QUERY_LIMITED_INFORMATION, False, pid.value)
        if h:
            try:
                out = ctypes.create_unicode_buffer(1024)
                sz = wintypes.DWORD(1024)
                if hasattr(kernel32, "QueryFullProcessImageNameW"):
                    if kernel32.QueryFullProcessImageNameW(h, 0, out, ctypes.byref(sz)):
                        app = Path(out.value).name
            finally:
                kernel32.CloseHandle(h)
        return {"app": app, "title": wtitle}
    except Exception:
        return None


def _active_window_linux() -> dict[str, str] | None:
    try:
        if SAFE_MODE:
            print("[DEV MODE] command launch requested: xdotool")
            return None
        r = subprocess.run(
            ["xdotool", "getactivewindow"],
            capture_output=True,
            text=True,
            timeout=2,
        )
        if r.returncode != 0:
            return None
        wid = r.stdout.strip()
        if not wid.isdigit():
            return None
        name = subprocess.run(
            ["xdotool", "getwindowname", wid],
            capture_output=True,
            text=True,
            timeout=2,
        )
        cls = subprocess.run(
            ["xdotool", "getwindowclassname", wid],
            capture_output=True,
            text=True,
            timeout=2,
        )
        return {
            "app": (cls.stdout or "").strip() or "unknown",
            "title": (name.stdout or "").strip(),
        }
    except (FileNotFoundError, subprocess.TimeoutExpired, OSError):
        return None


def get_active_window() -> dict[str, str] | None:
    """
    Read foreground window title and app name only (no keylogging, no recording).

    Returns ``{"app": str, "title": str}`` or ``None`` if unavailable.
    """
    try:
        if platform.system() == "Windows":
            return _active_window_windows()
        if platform.system() == "Darwin":
            # Lightweight: no extra deps; optional osascript front app
            script = (
                'tell application "System Events" to get name of first application process '
                'whose frontmost is true'
            )
            if SAFE_MODE:
                print("[DEV MODE] command launch requested: osascript active window")
                return None
            r = subprocess.run(
                ["osascript", "-e", script],
                capture_output=True,
                text=True,
                timeout=3,
            )
            if r.returncode == 0:
                return {"app": r.stdout.strip(), "title": ""}
            return None
        return _active_window_linux()
    except Exception:
        return None


def open_youtube() -> ActionResult:
    """Backward-compatible wrapper for ``launch_application("youtube")``."""
    return launch_application("youtube")


def open_vscode() -> ActionResult:
    """Backward-compatible wrapper for ``launch_application("vscode")``."""
    return launch_application("vscode")


def _screenshot_windows_powershell(path: Path) -> bool:
    path_str = str(path.resolve())
    path_escaped = path_str.replace("'", "''")
    script = (
        "Add-Type -AssemblyName System.Drawing,System.Windows.Forms; "
        "$b = [System.Windows.Forms.Screen]::PrimaryScreen.Bounds; "
        "$bmp = New-Object System.Drawing.Bitmap $b.Width, $b.Height; "
        "$g = [System.Drawing.Graphics]::FromImage($bmp); "
        "$g.CopyFromScreen($b.Location, [System.Drawing.Point]::Empty, $b.Size); "
        f"$bmp.Save('{path_escaped}', [System.Drawing.Imaging.ImageFormat]::Png); "
        "$g.Dispose(); $bmp.Dispose()"
    )
    try:
        if SAFE_MODE:
            print("[DEV MODE] command launch requested: powershell screenshot")
            return False
        r = subprocess.run(
            [
                "powershell",
                "-NoProfile",
                "-NonInteractive",
                "-ExecutionPolicy",
                "Bypass",
                "-Command",
                script,
            ],
            capture_output=True,
            timeout=30,
            text=True,
        )
        return r.returncode == 0 and path.exists()
    except (FileNotFoundError, subprocess.TimeoutExpired, OSError):
        return False


def take_screenshot(save_dir: str = "~/Pictures") -> ActionResult:
    """Capture the screen: Windows (.NET), Linux tools, optional pyautogui."""
    save_path = Path(save_dir).expanduser()
    save_path.mkdir(parents=True, exist_ok=True)

    timestamp = time.strftime("%Y%m%d_%H%M%S")
    filename = save_path / f"mini_kio_{timestamp}.png"

    if platform.system() == "Windows":
        if _screenshot_windows_powershell(filename):
            _log_automation("screenshot", True, via="powershell")
            return _ok(f"Screenshot saved: {filename}")

    for cmd in (
        ["gnome-screenshot", "-f", str(filename)],
        ["scrot", str(filename)],
        ["import", "-window", "root", str(filename)],
    ):
        try:
            if SAFE_MODE:
                print(f"[DEV MODE] command launch requested: {' '.join(cmd)}")
                continue
            result = subprocess.run(
                cmd,
                timeout=10,
                stdout=subprocess.DEVNULL,
                stderr=subprocess.DEVNULL,
            )
            if result.returncode == 0 and filename.exists():
                _log_automation("screenshot", True)
                return _ok(f"Screenshot saved: {filename}")
        except (FileNotFoundError, subprocess.TimeoutExpired):
            continue

    try:
        import pyautogui

        img = pyautogui.screenshot()
        img.save(str(filename))
        _log_automation("screenshot", True, via="pyautogui")
        return _ok(f"Screenshot saved: {filename}")
    except Exception as e:
        _log_automation("screenshot", False)
        return _fail(f"Screenshot failed. Error: {e}")


def _cpu_percent_sample() -> float | None:
    """Approximate total CPU percent (stdlib only)."""
    sysname = platform.system()
    if sysname == "Linux":
        try:

            def read_cpu() -> tuple[int, int]:
                with open("/proc/stat", encoding="utf-8") as f:
                    line = f.readline()
                parts = line.split()
                if len(parts) < 8 or parts[0] != "cpu":
                    return 0, 1
                nums = [int(x) for x in parts[1:8]]
                idle = nums[3] + nums[4]
                total = sum(nums)
                return idle, total

            i1, t1 = read_cpu()
            time.sleep(0.25)
            i2, t2 = read_cpu()
            dt = t2 - t1
            if dt <= 0:
                return None
            return max(0.0, min(100.0, 100.0 * (1.0 - (i2 - i1) / dt)))
        except (OSError, ValueError, IndexError):
            return None

    if sysname == "Windows":
        try:
            import ctypes
            from ctypes import wintypes

            class FILETIME(ctypes.Structure):
                _fields_ = [
                    ("dwLowDateTime", wintypes.DWORD),
                    ("dwHighDateTime", wintypes.DWORD),
                ]

            def ft_int(ft: FILETIME) -> int:
                return int(ft.dwLowDateTime) + (int(ft.dwHighDateTime) << 32)

            idle1, k1, u1 = FILETIME(), FILETIME(), FILETIME()
            idle2, k2, u2 = FILETIME(), FILETIME(), FILETIME()
            ctypes.windll.kernel32.GetSystemTimes(
                ctypes.byref(idle1), ctypes.byref(k1), ctypes.byref(u1)
            )
            time.sleep(0.25)
            ctypes.windll.kernel32.GetSystemTimes(
                ctypes.byref(idle2), ctypes.byref(k2), ctypes.byref(u2)
            )
            idled = ft_int(idle2) - ft_int(idle1)
            total = (
                ft_int(k2) - ft_int(k1) + ft_int(u2) - ft_int(u1) + idled
            )
            if total <= 0:
                return None
            return max(0.0, min(100.0, 100.0 * (1.0 - idled / total)))
        except Exception:
            return None

    return None


def get_cpu_usage_message() -> ActionResult:
    p = _cpu_percent_sample()
    if p is None:
        return _fail("CPU usage not available on this platform.")
    return _ok(f"CPU usage (approx): {p:.1f}%")


def _memory_summary() -> str | None:
    sysname = platform.system()
    if sysname == "Linux":
        try:
            meminfo: dict[str, int] = {}
            for line in Path("/proc/meminfo").read_text().splitlines():
                parts = line.split()
                if len(parts) >= 2 and parts[1].isdigit():
                    meminfo[parts[0].rstrip(":")] = int(parts[1])
            total = meminfo.get("MemTotal", 0) // 1024
            avail = meminfo.get("MemAvailable", 0) // 1024
            used = total - avail if total else 0
            return f"RAM: {used} MB used / {total} MB total ({avail} MB available)"
        except OSError:
            return None

    if sysname == "Windows":
        try:
            import ctypes
            from ctypes import wintypes

            class MEMORYSTATUSEX(ctypes.Structure):
                _fields_ = [
                    ("dwLength", wintypes.DWORD),
                    ("dwMemoryLoad", wintypes.DWORD),
                    ("ullTotalPhys", ctypes.c_ulonglong),
                    ("ullAvailPhys", ctypes.c_ulonglong),
                    ("ullTotalPageFile", ctypes.c_ulonglong),
                    ("ullAvailPageFile", ctypes.c_ulonglong),
                    ("ullTotalVirtual", ctypes.c_ulonglong),
                    ("ullAvailVirtual", ctypes.c_ulonglong),
                    ("ullAvailExtendedVirtual", ctypes.c_ulonglong),
                ]

            stat = MEMORYSTATUSEX()
            stat.dwLength = ctypes.sizeof(MEMORYSTATUSEX)
            if ctypes.windll.kernel32.GlobalMemoryStatusEx(ctypes.byref(stat)):
                total_mb = stat.ullTotalPhys // (1024 * 1024)
                avail_mb = stat.ullAvailPhys // (1024 * 1024)
                used_mb = total_mb - avail_mb
                return (
                    f"RAM: {used_mb} MB used / {total_mb} MB total "
                    f"({avail_mb} MB available, load {stat.dwMemoryLoad}%)"
                )
        except Exception:
            return None

    return None


def get_memory_usage_message() -> ActionResult:
    s = _memory_summary()
    if not s:
        return _fail("Memory stats not available.")
    return _ok(s)


def get_disk_usage_message() -> ActionResult:
    try:
        du = shutil.disk_usage(Path.home())
    except OSError:
        du = shutil.disk_usage("/")
    total = du.total // (1024 * 1024)
    free = du.free // (1024 * 1024)
    used = du.used // (1024 * 1024)
    return _ok(f"Disk: {used} MB used, {free} MB free, {total} MB total (approx)")


def get_ip_address_message() -> ActionResult:
    try:
        s = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
        try:
            s.connect(("8.8.8.8", 80))
            ip = s.getsockname()[0]
        finally:
            s.close()
        return _ok(f"Local IPv4 (route hint): {ip}")
    except OSError as e:
        return _fail(f"Could not determine IP: {e}")


def get_system_info() -> ActionResult:
    """Collect OS, Python version, and RAM when available (Linux /proc or Windows ctypes)."""
    try:
        info: dict[str, Any] = {
            "os": platform.system(),
            "version": platform.version()[:50],
            "python": platform.python_version(),
        }

        meminfo_path = Path("/proc/meminfo")
        if meminfo_path.exists():
            meminfo: dict[str, int] = {}
            for line in meminfo_path.read_text().splitlines():
                parts = line.split()
                if len(parts) >= 2 and parts[1].isdigit():
                    meminfo[parts[0].rstrip(":")] = int(parts[1])
            total_mb = meminfo.get("MemTotal", 0) // 1024
            avail_mb = meminfo.get("MemAvailable", 0) // 1024
            info["ram_total_mb"] = total_mb
            info["ram_available_mb"] = avail_mb
            info["ram_used_mb"] = total_mb - avail_mb

        _log_automation("sysinfo", True)
        return {"success": True, "message": "ok", "data": info}
    except Exception as e:
        _log_automation("sysinfo", False)
        return _fail(f"Could not get system info: {e}")


sysinfo = get_system_info
