"""
app_operator.py — KIO App Operator
=====================================
Fixes applied in this revision
--------------------------------
BUG-05  Spotify / Discord paths used literal `%USERNAME%` — Python does not
        expand Windows environment variables inside string literals.
        Fixed: use os.path.expandvars() + Path.home() at call time.
BUG-06  Discord path contained glob pattern `app-*` which Path.exists() can
        never resolve.  Fixed: use glob() at resolve time.
BUG-07  VSCode path was static; added dynamic _resolve_vscode_path() that
        checks LOCALAPPDATA and falls back to shutil.which("code").
PID-FIX Refine captured PID to handle launchers (Chrome, Notepad).
        Added /F fallback for stubborn apps.
"""

from __future__ import annotations

import glob
import logging
import os
import platform
import shutil
import subprocess
import tempfile
import time
import urllib.parse
import webbrowser
import ctypes
from pathlib import Path
from typing import Optional, Dict, Any

logger = logging.getLogger(__name__)

_IS_WINDOWS = platform.system() == "Windows"


# ---------------------------------------------------------------------------
# Internal Normalization Helpers
# ---------------------------------------------------------------------------

def _find_active_process(info: Dict) -> Optional[int]:
    """Surgical 1s bounded lookup for a uniquely matching active process."""
    if not _IS_WINDOWS: return None
    try:
        import psutil
        proc_name = info.get("process", "").lower()
        if not proc_name: return None
        
        uwp_packages = info.get("uwp_packages", [])
        targets = {proc_name}
        for u in uwp_packages: targets.add(u.lower())
        normalized = {t if t.endswith(".exe") else t + ".exe" for t in targets}
        
        # Bounded lookup
        matches = []
        for proc in psutil.process_iter(['pid', 'name']):
            try:
                if proc.info['name'] and proc.info['name'].lower() in normalized:
                    matches.append(proc.info['pid'])
            except (psutil.NoSuchProcess, psutil.AccessDenied):
                continue
        
        # Only return if unique to prevent accidental mass kills
        if len(matches) == 1:
            return matches[0]
    except Exception:
        pass
    return None


def _graceful_uwp_close(pid: int, name: str):
    """Attempt graceful WM_CLOSE on Calculator window specifically (after core termination)."""
    if not _IS_WINDOWS: return
    if name.lower() not in ("calculator", "calc"): return
    
    try:
        EnumWindows = ctypes.windll.user32.EnumWindows
        EnumWindowsProc = ctypes.WINFUNCTYPE(ctypes.c_bool, ctypes.c_void_p, ctypes.c_void_p)
        GetWindowTextW = ctypes.windll.user32.GetWindowTextW
        GetWindowTextLengthW = ctypes.windll.user32.GetWindowTextLengthW
        PostMessageW = ctypes.windll.user32.PostMessageW
        IsWindowVisible = ctypes.windll.user32.IsWindowVisible
        WM_CLOSE = 0x0010
        
        # We target visible windows with title "Calculator"
        # This is the safest way to target the ghosted UWP frame without killing ApplicationFrameHost.
        def foreach_window(hwnd, lParam):
            if IsWindowVisible(hwnd):
                length = GetWindowTextLengthW(hwnd)
                if length > 0:
                    buff = ctypes.create_unicode_buffer(length + 1)
                    GetWindowTextW(hwnd, buff, length + 1)
                    if buff.value == "Calculator":
                        PostMessageW(hwnd, WM_CLOSE, 0, 0)
            return True
        
        EnumWindows(EnumWindowsProc(foreach_window), 0)
    except Exception as e:
        logger.debug(f"[APP] UWP graceful close failed: {e}")



# ---------------------------------------------------------------------------
# Temporary session helpers
# ---------------------------------------------------------------------------

CHROME_TEMP_PROFILE_DIRS: Dict[int, str] = {}


def _cleanup_chrome_temp_profile(pid: int) -> None:
    path = CHROME_TEMP_PROFILE_DIRS.pop(pid, None)
    if not path:
        return
    try:
        shutil.rmtree(path, ignore_errors=True)
        logger.info(f"[APP] cleaned up chrome temp profile for pid {pid}: {path}")
    except Exception as exc:
        logger.debug(f"[APP] failed to remove chrome temp profile {path}: {exc}")


# ---------------------------------------------------------------------------
# Dynamic path helpers
# ---------------------------------------------------------------------------

def _expand(path: str) -> str:
    """Expand environment variables in a Windows-style path."""
    return os.path.expandvars(path)


def _resolve_vscode_path() -> Optional[str]:
    """Find VS Code without relying on a hardcoded username."""
    local = os.environ.get("LOCALAPPDATA", "")
    appdata = os.environ.get("APPDATA", "")
    candidates = [
        Path(local) / "Programs" / "Microsoft VS Code" / "Code.exe",
        Path(appdata) / "Local" / "Programs" / "Microsoft VS Code" / "Code.exe",
        Path(r"C:\Program Files\Microsoft VS Code\Code.exe"),
        Path(r"C:\Program Files (x86)\Microsoft VS Code\Code.exe"),
    ]
    for p in candidates:
        if p.exists():
            return str(p)
    # Fall back to PATH
    found = shutil.which("code")
    return found


def _resolve_discord_path() -> Optional[str]:
    """Resolve Discord exe via glob (install path includes version number)."""
    local = os.environ.get("LOCALAPPDATA", str(Path.home() / "AppData" / "Local"))
    pattern = str(Path(local) / "Discord" / "app-*" / "Discord.exe")
    matches = sorted(glob.glob(pattern))
    if matches:
        return matches[-1]  # latest version
    # Fallback: Update.exe launcher
    update_exe = Path(local) / "Discord" / "Update.exe"
    if update_exe.exists():
        return str(update_exe)
    return None


def _resolve_spotify_path() -> Optional[str]:
    """Resolve Spotify exe using environment-expanded paths."""
    local = os.environ.get("LOCALAPPDATA", "")
    roaming = os.environ.get("APPDATA", "")
    candidates = [
        Path(roaming) / "Spotify" / "Spotify.exe",
        Path(local) / "Microsoft" / "WindowsApps" / "Spotify.exe",
    ]
    for p in candidates:
        if p.exists():
            return str(p)
    return None


def _resolve_codex_path() -> Optional[str]:
    """Surgical Windows discovery for Codex."""
    if not _IS_WINDOWS: return None
    
    # 1. shutil.which()
    for exe in ["codex.exe", "codex.cmd", "codex"]:
        found = shutil.which(exe)
        if found: return found
        
    # 2. Registry / Common Paths
    local = os.environ.get("LOCALAPPDATA", "")
    appdata = os.environ.get("APPDATA", "")
    prog_files = os.environ.get("ProgramFiles", r"C:\Program Files")
    
    candidates = [
        Path(prog_files) / "Codex" / "Codex.exe",
        Path(local) / "Programs" / "Codex" / "Codex.exe",
        Path(appdata) / "Programs" / "Codex" / "Codex.exe",
        Path(local) / "Codex" / "Codex.exe",
    ]
    for p in candidates:
        if p.exists(): return str(p)
        
    # 3. WindowsApps aliases
    win_apps = Path(local) / "Microsoft" / "WindowsApps" / "codex.exe"
    if win_apps.exists(): return str(win_apps)
    
    return None


# ---------------------------------------------------------------------------
# APP_REGISTRY
# ---------------------------------------------------------------------------

APP_REGISTRY: Dict[str, Dict[str, Any]] = {
    "chrome": {
        "lifecycle": "browser",
        "exe": "chrome.exe",
        "process": "chrome.exe",
        "aliases": ["google chrome", "chrome browser", "browser"],
        "paths": [
            r"C:\Program Files\Google\Chrome\Application\chrome.exe",
            r"C:\Program Files (x86)\Google\Chrome\Application\chrome.exe",
        ],
    },
    "edge": {
        "lifecycle": "browser",
        "exe": "msedge.exe",
        "process": "msedge.exe",
        "aliases": ["microsoft edge", "ms edge"],
        "paths": [
            r"C:\Program Files (x86)\Microsoft\Edge\Application\msedge.exe",
            r"C:\Program Files\Microsoft\Edge\Application\msedge.exe",
        ],
    },
    "comet": {
        "lifecycle": "browser",
        "exe": "comet.exe",
        "process": "comet.exe",
        "paths": [
            r"%LOCALAPPDATA%\Perplexity\Comet\Application\comet.exe",
        ],
    },
    "firefox": {
        "lifecycle": "browser",
        "exe": "firefox.exe",
        "process": "firefox.exe",
        "paths": [
            r"C:\Program Files\Mozilla Firefox\firefox.exe",
            r"C:\Program Files (x86)\Mozilla Firefox\firefox.exe",
        ],
    },
    "brave": {
        "lifecycle": "browser",
        "exe": "brave.exe",
        "process": "brave.exe",
        "aliases": ["brave browser"],
        "paths": [
            r"C:\Program Files\BraveSoftware\Brave-Browser\Application\brave.exe",
            r"C:\Program Files (x86)\BraveSoftware\Brave-Browser\Application\brave.exe",
            r"%LOCALAPPDATA%\BraveSoftware\Brave-Browser\Application\brave.exe",
        ],
    },
    "vscode": {
        "lifecycle": "electron",
        "exe": "Code.exe",
        "process": "Code.exe",
        "aliases": ["vs code", "visual studio code", "editor", "code", "vsc"],
        "cli": "code",
        "dynamic_resolver": "_resolve_vscode_path",
    },
    "codex": {
        "lifecycle": "standard",
        "exe": "Codex.exe",
        "process": "Codex.exe",
        "aliases": ["codex launcher"],
        "dynamic_resolver": "_resolve_codex_path",
    },
    "notepad": {
        "lifecycle": "uwp",
        "exe": "notepad.exe",
        "process": "notepad.exe",
        "system": True,
        "uwp_packages": ["Notepad.exe", "ApplicationFrameHost.exe"],
    },
    "calculator": {
        "lifecycle": "uwp",
        "exe": "calc.exe",
        "process": "calc.exe",
        "aliases": ["calc"],
        "system": True,
        "uwp_packages": ["CalculatorApp.exe", "ApplicationFrameHost.exe", "Win32Calculator.exe"],
    },
    "explorer": {
        "lifecycle": "launcher",
        "exe": "explorer.exe",
        "process": "explorer.exe",
        "system": True,
    },
    "cmd": {
        "lifecycle": "launcher",
        "exe": "cmd.exe",
        "process": "cmd.exe",
        "aliases": ["command prompt", "terminal"],
        "system": True,
    },
    "powershell": {
        "lifecycle": "launcher",
        "exe": "powershell.exe",
        "process": "powershell.exe",
        "system": True,
    },
    "paint": {
        "lifecycle": "standard",
        "exe": "mspaint.exe",
        "process": "mspaint.exe",
        "system": True,
    },
    "capcut": {
        "lifecycle": "standard",
        "exe": "CapCut.exe",
        "process": "CapCut.exe",
        "paths": [
            r"C:\Program Files\CapCut\CapCut.exe",
            r"C:\Program Files (x86)\CapCut\CapCut.exe",
            r"%LOCALAPPDATA%\CapCut\Apps\CapCut.exe",
        ],
    },
    "vlc": {
        "lifecycle": "standard",
        "exe": "vlc.exe",
        "process": "vlc.exe",
        "paths": [
            r"C:\Program Files\VideoLAN\VLC\vlc.exe",
            r"C:\Program Files (x86)\VideoLAN\VLC\vlc.exe",
        ],
    },
    "spotify": {
        "lifecycle": "electron",
        "exe": "Spotify.exe",
        "process": "Spotify.exe",
        "dynamic_resolver": "_resolve_spotify_path",
    },
    "discord": {
        "lifecycle": "electron",
        "exe": "Discord.exe",
        "process": "Discord.exe",
        "dynamic_resolver": "_resolve_discord_path",
    },
    "telegram": {
        "lifecycle": "singleton",
        "exe": "Telegram.exe",
        "process": "Telegram.exe",
        "paths": [
            r"%APPDATA%\Telegram Desktop\Telegram.exe",
        ],
    },
}

# Web apps — opened directly in the default browser
WEB_URLS: Dict[str, str] = {
    "youtube":      "https://youtube.com",
    "whatsapp":     "https://web.whatsapp.com",
    "whatsapp web": "https://web.whatsapp.com",
    "telegram":     "https://web.telegram.org",
    "claude":       "https://claude.ai",
    "claude ai":    "https://claude.ai",
    "chatgpt":      "https://chat.openai.com",
    "gmail":        "https://gmail.com",
    "github":       "https://github.com",
    "google":       "https://google.com",
    "netflix":      "https://netflix.com",
}

# Dynamic resolvers map
_DYNAMIC_RESOLVERS = {
    "_resolve_vscode_path":  _resolve_vscode_path,
    "_resolve_spotify_path": _resolve_spotify_path,
    "_resolve_discord_path": _resolve_discord_path,
    "_resolve_codex_path":   _resolve_codex_path,
}


# ---------------------------------------------------------------------------
# Public API
# ---------------------------------------------------------------------------

def launch_app(name: str) -> dict:
    """Launch an application by name.  Returns {"success": bool, "message": str, "pid": int, "canonical_name": str}."""
    key = name.lower().strip()
    logger.info(f"[APP] launch_app: {key!r}")

    # 1. Registry
    info = _find_in_registry(key)
    if info:
        # Resolve canonical name from registry key
        canonical = key
        for k, v in APP_REGISTRY.items():
            if v == info:
                canonical = k
                break
        result = _launch_from_info(info, key)
        result["canonical_name"] = canonical
        return result

    # 2. Web URL
    if key in WEB_URLS:
        return _open_url(WEB_URLS[key], key)

    # 3. Discovery
    result = _discover_and_launch(key)
    if "canonical_name" not in result:
        result["canonical_name"] = key
    return result


def close_app(name: str, pid: Optional[int] = None) -> dict:
    """Kill an application.  Returns {"success": bool, "message": str}."""
    key = name.lower().strip()
    logger.info(f"[APP] close_app: {key!r} (pid override: {pid})")

    if not _IS_WINDOWS:
        return _pkill(key)

    # Priority 1: Targeted PID termination (Tree-Aware)
    if pid is not None:
        try:
            import psutil
            try:
                p = psutil.Process(pid)
                if p.name().lower() == "applicationframehost.exe":
                    return {"success": False, "message": f"Refusing to kill UWP wrapper (ApplicationFrameHost). Close the app manually if needed."}
            except (psutil.NoSuchProcess, psutil.AccessDenied):
                pass

            # Use /T (Tree) to ensure all subprocesses (tabs, helpers) are terminated.
            # No /F for graceful termination as per SPEC 4.1.
            result = subprocess.run(
                ["taskkill", "/T", "/PID", str(pid)],
                capture_output=True, text=True, timeout=6,
            )
            
            # Bounded verification delay: If taskkill failed or reported stubbornness
            if result.returncode != 0 or "forcefully" in result.stderr.lower():
                time.sleep(1.2)
                # FINAL VERIFICATION: Check if it actually closed despite the error
                try:
                    import psutil
                    if not psutil.pid_exists(pid):
                         result = subprocess.CompletedProcess(result.args, 0, result.stdout, result.stderr)
                    else:
                        p = psutil.Process(pid)
                        if not p.is_running() or p.status() == psutil.STATUS_ZOMBIE:
                             result = subprocess.CompletedProcess(result.args, 0, result.stdout, result.stderr)
                        else:
                            # Maybe it's in the process of closing
                            time.sleep(1.0)
                            if not psutil.pid_exists(pid):
                                result = subprocess.CompletedProcess(result.args, 0, result.stdout, result.stderr)
                except (psutil.NoSuchProcess, psutil.AccessDenied):
                    result = subprocess.CompletedProcess(result.args, 0, result.stdout, result.stderr)

            if result.returncode == 0:
                logger.info(f"[APP] targeted tree killed: {pid}")
                _cleanup_chrome_temp_profile(pid)
                
                # Suffix Fix: Graceful WM_CLOSE for Calculator UI
                _graceful_uwp_close(pid, name)

                # Phase E: UWP Container-Aware Check (Honesty)
                info = _find_in_registry(key)
                if info and info.get("lifecycle") == "uwp":
                     return {"success": True, "message": f"Closed {name}. Core process terminated, but UWP shell may persist.", "pid": pid}

                return {"success": True, "message": f"Closed {name} (pid {pid})", "pid": pid}
            
            # If PID not found or already gone
            if "not found" in result.stderr.lower() or "not running" in result.stderr.lower():
                _cleanup_chrome_temp_profile(pid)
                return {"success": True, "message": f"{name} was already closed.", "pid": pid}
            
            # SURGICAL FALLBACK: If graceful kill fails because forceful termination is required
            # (common for modern Notepad/UWP apps), we escalate if we have a tracked PID.
            if "forcefully" in result.stderr.lower() or "/f" in result.stderr.lower():
                logger.info(f"[APP] Graceful kill failed for pid {pid}, retrying forcefully (/F)")
                f_result = subprocess.run(
                    ["taskkill", "/F", "/T", "/PID", str(pid)],
                    capture_output=True, text=True, timeout=6,
                )
                if f_result.returncode == 0:
                    _cleanup_chrome_temp_profile(pid)
                    
                    # Suffix Fix: Graceful WM_CLOSE for Calculator UI
                    _graceful_uwp_close(pid, name)

                    # Phase E: UWP Container-Aware Check
                    info = _find_in_registry(key)
                    if info and info.get("lifecycle") == "uwp":
                         return {"success": True, "message": f"Closed {name}. Core process terminated, but UWP shell may persist.", "pid": pid}
                         
                    return {"success": True, "message": f"Closed {name} (pid {pid}) forcefully.", "pid": pid}

            # If it still fails, report it.
            msg = f"Failed to close {name} (pid {pid}) gracefully."
            logger.warning(f"[APP] taskkill /T rc={result.returncode} for pid {pid}: {result.stderr}")
            return {"success": False, "message": msg, "pid": pid}

        except subprocess.TimeoutExpired:
            return {"success": False, "message": f"Timeout closing {name} (pid {pid})", "pid": pid}
        except Exception as exc:
            logger.error(f"[APP] Error closing pid {pid}: {exc}")
            return {"success": False, "message": f"Error closing {name}: {exc}", "pid": pid}

    # No wildcard fallback (/IM) for non-system apps to respect ownership isolation.
    # Recovery Phase: if app not tracked, attempt ONE bounded recovery lookup.
    info = _find_in_registry(key)
    if info:
        found_pid = _find_active_process(info)
        if found_pid:
            logger.info(f"[APP] recovery found unique pid {found_pid} for {key}")
            # Adopt and close
            return close_app(name, pid=found_pid)

    return {"success": False, "message": f"Cannot close {name}: No tracked process found for this session."}


def search_web(query: str) -> dict:
    """Open a Google search.  Returns {"success": bool, "message": str}."""
    if not query:
        return {"success": False, "message": "No search query"}
    encoded = urllib.parse.quote_plus(query)
    url = f"https://www.google.com/search?q={encoded}"
    try:
        webbrowser.open(url)
        logger.info(f"[APP] search: {query!r}")
        return {"success": True, "message": f"Searched: {query}"}
    except Exception as exc:
        return {"success": False, "message": f"Search failed: {str(exc)[:80]}"}


# ---------------------------------------------------------------------------
# Internal helpers
# ---------------------------------------------------------------------------

def _find_in_registry(key: str) -> Optional[Dict]:
    if key in APP_REGISTRY:
        return APP_REGISTRY[key]
    for info in APP_REGISTRY.values():
        if key in info.get("aliases", []):
            return info
    return None


def _open_url(url: str, label: str) -> dict:
    try:
        webbrowser.open(url)
        # Use "Launched" for URIs without PID tracking
        return {"success": True, "message": f"Launched {label} in browser."}
    except Exception as exc:
        return {"success": False, "message": f"Failed to open {label}: {str(exc)[:80]}"}


def _resolve_path(info: Dict) -> Optional[str]:
    """Return a usable executable path for an app registry entry."""
    # Dynamic resolver (Spotify, Discord, VSCode)
    resolver_name = info.get("dynamic_resolver")
    if resolver_name and resolver_name in _DYNAMIC_RESOLVERS:
        result = _DYNAMIC_RESOLVERS[resolver_name]()
        if result:
            return result

    # CLI name on PATH (e.g. "code" for VSCode)
    cli = info.get("cli")
    if cli and shutil.which(cli):
        return cli

    # Static paths list
    for raw_path in info.get("paths", []):
        p = Path(_expand(raw_path))
        if p.exists():
            return str(p)

    # System apps — use just the exe name (resolvable via PATH)
    if info.get("system"):
        return info.get("exe")

    # Windows 'where' command
    if _IS_WINDOWS and "exe" in info:
        try:
            r = subprocess.run(
                ["where", info["exe"]],
                capture_output=True, text=True, timeout=3,
            )
            if r.returncode == 0:
                return r.stdout.strip().splitlines()[0]
        except Exception:
            pass

    # shutil.which fallback
    found = shutil.which(info.get("exe", ""))
    return found


def _verify_process_started_windows(proc_name: str, timeout_s: int = 3, uwp_packages: list[str] | None = None) -> bool:
    """Lightweight verification: poll Windows tasklist for a process image name."""
    if not proc_name:
        return False
        
    target_names = {proc_name.strip().lower()}
    if uwp_packages:
        for u in uwp_packages:
            target_names.add(u.strip().lower())
            
    normalized_targets = set()
    for name in target_names:
        if not name.endswith('.exe'):
            normalized_targets.add(name + '.exe')
        else:
            normalized_targets.add(name)

    deadline = time.time() + float(timeout_s)
    while time.time() < deadline:
        try:
            r = subprocess.run(["tasklist"], capture_output=True, text=True, timeout=2)
            out = (r.stdout or "").lower()
            for name in normalized_targets:
                if name in out:
                    return True
        except Exception:
            pass
        time.sleep(0.4)
    return False


def _refine_pid_windows(
    initial_pid: int,
    proc_name: str,
    prior_pids: set[int] | None = None,
    launch_start: float | None = None,
    uwp_packages: list[str] | None = None,
    lifecycle: str = "standard",
) -> int | None:
    """Surgical PID refinement: Capture the 'real' PID if the initial one is a transient launcher."""
    if not _IS_WINDOWS:
        return initial_pid

    prior_pids = prior_pids or set()
    if launch_start is None:
        launch_start = time.time()

    uwp_packages = uwp_packages or []

    try:
        import psutil
        
        target_names = {proc_name.lower()}
        for u in uwp_packages:
            target_names.add(u.lower())
        
        normalized_targets = {t if t.endswith(".exe") else t + ".exe" for t in target_names}

        # Helper exclusion logic
        def _is_valid_root(proc: psutil.Process) -> bool:
            try:
                cmdline = proc.cmdline()
                name = proc.name().lower()
            except (psutil.NoSuchProcess, psutil.AccessDenied):
                return False

            # Reject common helper/launcher wrappers if they are not explicitly what we launched
            if name in ("conhost.exe", "cmd.exe", "powershell.exe", "update.exe", "launcher.exe", "bash.exe", "wsl.exe"):
                if lifecycle != "launcher":
                    return False

            if len(cmdline) <= 1:
                return True

            for arg in cmdline[1:]:
                # Common Electron / Browser / Chromium helpers
                arg_lower = arg.lower()
                if any(x in arg_lower for x in (
                    "--type=renderer", 
                    "--type=gpu-process", 
                    "--type=utility", 
                    "--type=crashpad-handler", 
                    "--type=broker"
                )):
                    return False
                
            if lifecycle == "browser":
                for arg in cmdline[1:]:
                    if arg.lower().startswith("--type="):
                        return arg.lower() == "--type=browser"
                        
            return True

        # Packaged app detection
        is_packaged_broker = False
        try:
            initial_proc = psutil.Process(initial_pid)
            if initial_proc.is_running():
                iname = initial_proc.name().lower()
                if iname in ("applicationframehost.exe", "shellexperiencehost.exe"):
                    is_packaged_broker = True
        except (psutil.NoSuchProcess, psutil.AccessDenied):
            pass

        # Helper for bounded fallback
        def _apply_fallback(pid: int) -> int | None:
            try:
                f_proc = psutil.Process(pid)
                if not f_proc.is_running():
                    return None
                f_name = f_proc.name().lower()
                # Rule 2: Preserve wrapper rejection
                if f_name in ("cmd.exe", "conhost.exe", "update.exe"):
                    return None
                return pid
            except (psutil.NoSuchProcess, psutil.AccessDenied):
                return None

        # UWP Refinement
        if lifecycle == "uwp" or is_packaged_broker:
            deadline = launch_start + 3.0
            
            def _find_latest_uwp_process(exclude_pids: set[int]) -> psutil.Process | None:
                newest_proc = None
                newest_time = 0.0
                for proc in psutil.process_iter(['pid', 'name', 'create_time']):
                    try:
                        pid = proc.info['pid']
                        name = proc.info['name']
                        if pid in exclude_pids:
                            continue
                        if not name or name.lower() not in normalized_targets:
                            continue
                        if not proc.is_running():
                            continue
                        if not _is_valid_root(proc):
                            continue
                            
                        ctime = proc.info['create_time']
                        if ctime > newest_time:
                            newest_time = ctime
                            newest_proc = proc
                    except (psutil.NoSuchProcess, psutil.AccessDenied):
                        continue
                return newest_proc

            while time.time() < deadline:
                newest_proc = _find_latest_uwp_process(prior_pids)
                if newest_proc is not None:
                    logger.info(f"[APP] PID refined for {proc_name} (UWP): {initial_pid} -> {newest_proc.pid}")
                    return newest_proc.pid
                time.sleep(0.1)
                
            logger.info(f"[APP] UWP PID refinement timeout for {proc_name}, applying fallback")
            return _apply_fallback(initial_pid)

        # Singleton reuse detection
        if lifecycle == "singleton":
            def _find_latest_singleton() -> psutil.Process | None:
                newest_proc = None
                newest_time = 0.0
                for proc in psutil.process_iter(['pid', 'name', 'create_time']):
                    try:
                        pid = proc.info['pid']
                        name = proc.info['name']
                        if not name or name.lower() not in normalized_targets:
                            continue
                        if not proc.is_running():
                            continue
                        if not _is_valid_root(proc):
                            continue
                        ctime = proc.info['create_time']
                        if ctime > newest_time:
                            newest_time = ctime
                            newest_proc = proc
                    except (psutil.NoSuchProcess, psutil.AccessDenied):
                        continue
                return newest_proc

            deadline = launch_start + 3.0
            while time.time() < deadline:
                new_proc = _find_latest_singleton()
                # If we found a process and it's NOT in prior_pids, it's new
                if new_proc and new_proc.pid not in prior_pids:
                    logger.info(f"[APP] PID refined for {proc_name} (new singleton instance): {initial_pid} -> {new_proc.pid}")
                    return new_proc.pid
                time.sleep(0.1)
            
            # If we timeout and no NEW process, fallback to existing
            existing = _find_latest_singleton()
            if existing and existing.pid in prior_pids:
                logger.info(f"[APP] Singleton reuse detected for {proc_name}: {existing.pid}")
                return existing.pid
            
            logger.info(f"[APP] Singleton PID refinement failed for {proc_name}, applying fallback")
            return _apply_fallback(initial_pid)

        # Standard / Browser / Electron refinement (Tree lineage and creation time)
        target_name = proc_name.lower()
        if not target_name.endswith(".exe"):
            target_name += ".exe"

        def _find_recent_target_child(parent_proc: psutil.Process) -> psutil.Process | None:
            newest_proc = None
            newest_time = 0.0
            now = time.time()
            for child in parent_proc.children(recursive=True):
                try:
                    if child.is_running() and child.name().lower() == target_name and _is_valid_root(child):
                        create_time = child.create_time()
                        if (now - create_time) < 5.0 and create_time > newest_time:
                            newest_time = create_time
                            newest_proc = child
                except (psutil.NoSuchProcess, psutil.AccessDenied):
                    continue
            return newest_proc

        def _find_root_ancestor(proc: psutil.Process) -> psutil.Process | None:
            for ancestor in proc.parents():
                try:
                    if ancestor.name().lower() == target_name and _is_valid_root(ancestor):
                        return ancestor
                except (psutil.NoSuchProcess, psutil.AccessDenied):
                    continue
            return None

        def _find_latest_matching_process(exclude_pids: set[int], allow_stale: bool = False) -> psutil.Process | None:
            root_proc = None
            root_time = 0.0
            now = time.time()
            for proc in psutil.process_iter(['pid', 'name', 'create_time']):
                try:
                    pid = proc.info['pid']
                    name = proc.info['name']
                    create_time = proc.info['create_time']
                    if pid in exclude_pids:
                        continue
                    if not name or name.lower() != target_name:
                        continue
                    if not proc.is_running():
                        continue
                    if not allow_stale and (create_time < launch_start - 2.0 or create_time > now + 2.0):
                        continue
                    if _is_valid_root(proc):
                        if create_time > root_time:
                            root_time = create_time
                            root_proc = proc
                except (psutil.NoSuchProcess, psutil.AccessDenied):
                    continue
            return root_proc

        try:
            if initial_pid > 0:
                p = psutil.Process(initial_pid)
                if p.is_running():
                    if _is_valid_root(p):
                        return initial_pid

                    parent_root = _find_root_ancestor(p)
                    if parent_root is not None:
                        logger.info(
                            f"[APP] PID refined for {proc_name} via ancestor root: {initial_pid} -> {parent_root.pid}"
                        )
                        return parent_root.pid

                    child_proc = _find_recent_target_child(p)
                    if child_proc is not None:
                        logger.info(
                            f"[APP] PID refined for {proc_name} via child: {initial_pid} -> {child_proc.pid}"
                        )
                        return child_proc.pid

                    if p.name().lower() == target_name:
                        newest_proc = _find_latest_matching_process({initial_pid} | prior_pids)
                        if newest_proc is not None:
                            logger.info(
                                f"[APP] PID refined for {proc_name}: {initial_pid} -> {newest_proc.pid}"
                            )
                            return newest_proc.pid
                        return initial_pid
        except (psutil.NoSuchProcess, psutil.AccessDenied):
            pass

        # Standard / Browser / Electron refinement (Tree lineage and creation time)
        deadline = launch_start + 2.0
        while time.time() < deadline:
            newest_proc = _find_latest_matching_process(prior_pids)
            if newest_proc is not None:
                logger.info(f"[APP] PID refined for {proc_name}: {initial_pid} -> {newest_proc.pid}")
                return newest_proc.pid
            time.sleep(0.2)

        # Launcher-detach refinement: If no new process found, maybe it re-used a singleton?
        # Standard/Electron apps sometimes behave as singletons.
        fallback_proc = _find_latest_matching_process(set(), allow_stale=True)
        if fallback_proc is not None:
            logger.info(
                f"[APP] PID fallback refined for {proc_name}: {initial_pid} -> {fallback_proc.pid}"
            )
            return fallback_proc.pid
    except Exception as exc:
        logger.debug(f"[APP] PID refinement skipped: {exc}")

    return _apply_fallback(initial_pid)


def _launch_from_info(info: Dict, name: str) -> dict:
    path = _resolve_path(info)
    if not path:
        if name.lower() == "codex":
            local = os.environ.get("LOCALAPPDATA", "...\\AppData\\Local")
            appdata = os.environ.get("APPDATA", "...\\AppData\\Roaming")
            prog = os.environ.get("ProgramFiles", "C:\\Program Files")
            summary = f"Codex not found in: PATH, {prog}\\Codex, {local}\\Programs\\Codex, {appdata}\\Programs\\Codex, {local}\\Microsoft\\WindowsApps"
            return {"success": False, "message": summary}
        return {"success": False, "message": f"Cannot find {name} — is it installed?"}

    if os.path.isabs(path) and not Path(path).exists():
        return {"success": False, "message": f"Cannot find {name} at {path}"}

    temp_profile_dir = None
    try:
        # Prefer direct execution to capture valid PID
        launch_cmd = [path] if os.path.isabs(path) else [shutil.which(path) or path]
        prior_pids: set[int] = set()
        launch_start = time.time()
        if _IS_WINDOWS:
            try:
                import psutil
                proc_name = info.get("process") or Path(path).name
                uwp_packages = info.get("uwp_packages", [])
                lifecycle = info.get("lifecycle", "standard")
                
                target_names = {proc_name.lower()}
                for u in uwp_packages:
                    target_names.add(u.lower())
                
                normalized_targets = {t if t.endswith(".exe") else t + ".exe" for t in target_names}

                for proc in psutil.process_iter(['pid', 'name']):
                    try:
                        if proc.info['name'] and proc.info['name'].lower() in normalized_targets:
                            prior_pids.add(proc.pid)
                    except (psutil.NoSuchProcess, psutil.AccessDenied):
                        continue
            except Exception:
                prior_pids = set()

        if isinstance(info.get("exe"), str) and info.get("exe").lower() == "chrome.exe":
            try:
                temp_profile_dir = tempfile.mkdtemp(prefix="kio_chrome_")
                launch_cmd.extend([
                    "--user-data-dir=" + temp_profile_dir,
                    "--new-window",
                    "--no-first-run",
                    "--disable-extensions",
                ])
            except Exception as exc:
                logger.debug(f"[APP] unable to create chrome temp profile: {exc}")

        if os.path.isabs(launch_cmd[0]) or shutil.which(launch_cmd[0]):
            proc = subprocess.Popen(
                launch_cmd,
                shell=False,
                creationflags=_creation_flags(),
                stdout=subprocess.DEVNULL,
                stderr=subprocess.DEVNULL,
            )
        else:
            # Fallback for shell-associated files or missing paths
            proc = subprocess.Popen(
                ["cmd", "/c", "start", "", path],
                shell=False,
                creationflags=_creation_flags(),
            )
        
        pid = proc.pid
        if temp_profile_dir is not None:
            CHROME_TEMP_PROFILE_DIRS[pid] = temp_profile_dir
        logger.info(f"[APP] launched: {path} (initial pid: {pid})")

        # Lightweight verification: poll for process presence by image name
        proc_name = info.get("process") or Path(path).name
        uwp_packages = info.get("uwp_packages", [])
        lifecycle = info.get("lifecycle", "standard")
        if _IS_WINDOWS:
            if _verify_process_started_windows(proc_name, timeout_s=3, uwp_packages=uwp_packages):
                # Refine PID to handle launchers/aliases
                final_pid = _refine_pid_windows(pid, proc_name, prior_pids=prior_pids, launch_start=launch_start, uwp_packages=uwp_packages, lifecycle=lifecycle)
                if final_pid is None:
                    logger.warning(f"[APP] Ownership refinement failed for: {proc_name}")
                    # Honest capability response: successful launch but untracked
                    return {"success": True, "message": f"Launched {name} (ownership not tracked)."}
                logger.info(f"[DEBUG_APP] final_pid refined: {final_pid}")
                return {"success": True, "message": f"Opened {name}", "pid": final_pid}
            else:
                logger.warning(f"[APP] launch verification failed for: {proc_name}")
                if temp_profile_dir is not None:
                    _cleanup_chrome_temp_profile(pid)
                return {"success": False, "message": f"Failed to launch {name}.", "pid": pid}
        else:
            # Non-windows: best-effort via Popen status
            return {"success": True, "message": f"Opened {name}", "pid": pid}
    except FileNotFoundError:
        if temp_profile_dir is not None:
            if 'pid' in locals():
                _cleanup_chrome_temp_profile(pid)
            else:
                shutil.rmtree(temp_profile_dir, ignore_errors=True)
        return {"success": False, "message": f"Cannot find {name}"}
    except Exception as exc:
        if temp_profile_dir is not None:
            if 'pid' in locals():
                _cleanup_chrome_temp_profile(pid)
            else:
                shutil.rmtree(temp_profile_dir, ignore_errors=True)
        return {"success": False, "message": f"Failed to open {name}: {str(exc)[:80]}"}


def _fuzzy_app_discovery(name: str) -> Optional[str]:
    """
    Search for executables in standard locations with a high similarity threshold.
    Limited to 2 levels of subdirectories to prevent disk thrashing.
    """
    if not _IS_WINDOWS:
        return None

    local_app_data = os.environ.get("LOCALAPPDATA", "")
    roaming_app_data = os.environ.get("APPDATA", "")
    user_profile = os.environ.get("USERPROFILE", "")
    search_dirs = [
        os.environ.get("ProgramFiles", r"C:\Program Files"),
        os.environ.get("ProgramFiles(x86)", r"C:\Program Files (x86)"),
        local_app_data,
        roaming_app_data,
        os.path.join(local_app_data, "Programs"),
        os.path.join(local_app_data, "Microsoft", "WindowsApps"),
        os.path.join(user_profile, "scoop", "apps"),
        os.path.join(os.environ.get("ProgramData", ""), "chocolatey", "bin"),
        os.path.join(roaming_app_data, "npm"),
    ]

    target = name.lower().strip()
    for base in search_dirs:
        if not base or not os.path.exists(base):
            continue
        try:
            # Level 1: C:\Program Files\AppName
            for entry in os.scandir(base):
                if entry.is_dir():
                    try:
                        # Level 2: C:\Program Files\AppName\app.exe
                        for sub_entry in os.scandir(entry.path):
                            if sub_entry.is_file() and sub_entry.name.lower().endswith(".exe"):
                                # Simple prefix/containment check for high confidence
                                stem = Path(sub_entry.name).stem.lower()
                                if stem == target or stem.startswith(target) or target in stem:
                                    # Basic confidence: if length delta is small
                                    if abs(len(stem) - len(target)) <= 2:
                                        return sub_entry.path
                    except (PermissionError, OSError):
                        continue
        except (PermissionError, OSError):
            continue
    return None


def _discover_and_launch(name: str) -> dict:
    """Try 'where', shutil.which, fuzzy discovery, then shell-free Popen."""
    exe = name if name.endswith(".exe") else f"{name}.exe"

    # 1. System PATH via 'where'
    if _IS_WINDOWS:
        try:
            r = subprocess.run([
                "where",
                exe,
            ], capture_output=True, text=True, timeout=2)
            if r.returncode == 0:
                path = r.stdout.strip().splitlines()[0]
                return _launch_path(path, name)
        except Exception:
            pass

    # 2. System PATH via shutil.which
    found = shutil.which(exe)
    if found:
        return _launch_path(found, name)

    # 3. Fuzzy Discovery (Bounded fallback)
    fuzzy_path = _fuzzy_app_discovery(name)
    if fuzzy_path:
        logger.info(f"[APP] fuzzy discovery found: {fuzzy_path}")
        return _launch_path(fuzzy_path, name)

    # Absolute last resort — launch by name via cmd start (no verified path)
    try:
        subprocess.Popen(["cmd", "/c", "start", "", name], shell=False, creationflags=_creation_flags())
        # Best-effort verification
        if _IS_WINDOWS and _verify_process_started_windows(f"{name}.exe", timeout_s=3):
            # Use "Launched" when path/ownership is unverified
            return {"success": True, "message": f"Launched {name}"}
        if not _IS_WINDOWS:
            return {"success": True, "message": f"Launched {name}"}
        return {"success": False, "message": f"Failed to launch {name}."}
    except Exception as exc:
        return {"success": False, "message": f"Cannot find or open: {name}"}


def _launch_path(path: str, name: str) -> dict:
    """Helper to launch a verified path and verify process start."""
    try:
        # Prefer direct execution to capture valid PID
        launch_cmd = [path] if os.path.isabs(path) else [shutil.which(path) or path]
        
        if os.path.isabs(launch_cmd[0]) or shutil.which(launch_cmd[0]):
            proc = subprocess.Popen(
                launch_cmd,
                shell=False,
                creationflags=_creation_flags(),
                stdout=subprocess.DEVNULL,
                stderr=subprocess.DEVNULL,
            )
        else:
            proc = subprocess.Popen([
                "cmd",
                "/c",
                "start",
                "",
                path,
            ], shell=False, creationflags=_creation_flags())
        
        pid = proc.pid
        logger.info(f"[APP] launched: {path} (initial pid: {pid})")

        proc_name = Path(path).name
        if _IS_WINDOWS:
            if _verify_process_started_windows(proc_name, timeout_s=3):
                final_pid = _refine_pid_windows(pid, proc_name)
                if final_pid is None:
                    # Honest capability response: successful launch but untracked
                    return {"success": True, "message": f"Launched {name} (ownership not tracked)."}
                return {"success": True, "message": f"Opened {name}", "pid": final_pid}
            else:
                logger.warning(f"[APP] launch verification failed for: {proc_name}")
                return {"success": False, "message": f"Failed to launch {name}.", "pid": pid}
        return {"success": True, "message": f"Opened {name}", "pid": pid}
    except Exception as exc:
        return {"success": False, "message": f"Failed to open {name}: {str(exc)[:80]}"}


def _pkill(name: str) -> dict:
    try:
        subprocess.run(["pkill", "-f", name], timeout=4)
        return {"success": True, "message": f"Closed {name}"}
    except Exception as exc:
        return {"success": False, "message": f"Cannot close {name}: {str(exc)[:80]}"}


def _creation_flags() -> int:
    return 0x00000008 if _IS_WINDOWS else 0  # DETACHED_PROCESS



# ---------------------------------------------------------------------------
# Capabilities
# ---------------------------------------------------------------------------
APP_CAPABILITIES = {
    "chrome": ["search", "open_url", "youtube", "new_tab"],
    "edge": ["search", "open_url", "youtube"],
    "firefox": ["search", "open_url", "youtube"],
    "brave": ["search", "open_url", "youtube"],
    "comet": ["search", "open_url", "youtube"],
    "spotify": ["play", "pause", "next", "previous"],
    "vlc": ["play", "pause"],
    "youtube": ["play"],
    "vscode": ["open_project", "open_file"],
    "telegram": ["send_message"],
    "capcut": ["play"],
}

def execute_capability(target: str) -> dict:
    parts = target.split("::", 2)
    if len(parts) < 2:
        return {"success": False, "message": "Invalid capability routing format."}
    
    app_name, cap = parts[0], parts[1]
    args = parts[2] if len(parts) == 3 else ""
    
    caps = APP_CAPABILITIES.get(app_name, [])
    if cap not in caps:
        return {"success": False, "message": f"{app_name} does not support '{cap}'."}
        
    logger.info(f"[CAPABILITY] Routing {cap} to {app_name} with args: {args}")

    from mini_kio.core.runtime import get_runtime
    rt = get_runtime()
    
    if cap == "play" and app_name == "spotify":
        query = urllib.parse.quote(args)
        # Try URI first
        try:
            info = _find_in_registry("spotify")
            prior_pids = set()
            launch_start = time.time()
            if _IS_WINDOWS:
                import psutil
                proc_name = info.get("process", "Spotify.exe") if info else "Spotify.exe"
                for proc in psutil.process_iter(['pid', 'name']):
                    try:
                        if proc.info['name'] and proc.info['name'].lower() == proc_name.lower():
                            prior_pids.add(proc.pid)
                    except (psutil.NoSuchProcess, psutil.AccessDenied): continue

            proc = subprocess.Popen(["cmd", "/c", "start", f"spotify:search:{query}"], shell=False)
            
            # Attempt Bounded Ownership Registration
            if _IS_WINDOWS and info:
                time.sleep(1.0) # Wait for URI to trigger
                final_pid = _refine_pid_windows(proc.pid, info.get("process", "Spotify.exe"), prior_pids=prior_pids, launch_start=launch_start, lifecycle="electron")
                if final_pid and rt:
                    rt.register_tracked_process(final_pid, "spotify", f"spotify:search:{args}")
                    return {"success": True, "message": f"Playing {args} on Spotify.", "pid": final_pid, "canonical_name": "spotify"}

            return {"success": True, "message": f"Launched Spotify search for {args}."}
        except Exception:
            # Fallback to web
            webbrowser.open(f"https://open.spotify.com/search/{query}")
            return {"success": True, "message": f"Launched {args} search on Spotify Web."}

    if cap in ("search", "open_url", "youtube") or (cap == "play" and app_name == "youtube"):
        if cap == "search":
            url = f"https://www.google.com/search?q={urllib.parse.quote_plus(args)}"
        elif cap == "youtube" or (cap == "play" and app_name == "youtube"):
            url = f"https://www.youtube.com/results?search_query={urllib.parse.quote_plus(args)}"
        else:
            # Deterministic web app lookup
            if args.lower() in WEB_URLS:
                url = WEB_URLS[args.lower()]
            else:
                url = args if args.startswith("http") else "https://" + args
            
        info = _find_in_registry(app_name)
        if not info:
            return {"success": False, "message": f"Browser {app_name} not found in registry."}
        
        path = _resolve_path(info)
        if not path:
             return {"success": False, "message": f"Browser {app_name} path not found."}
             
        try:
            prior_pids = set()
            launch_start = time.time()
            if _IS_WINDOWS:
                import psutil
                proc_name = info.get("process", "chrome.exe")
                for proc in psutil.process_iter(['pid', 'name']):
                    try:
                        if proc.info['name'] and proc.info['name'].lower() == proc_name.lower():
                            prior_pids.add(proc.pid)
                    except (psutil.NoSuchProcess, psutil.AccessDenied): continue

            subprocess.Popen(
                [path, url], 
                shell=False,
                creationflags=_creation_flags(),
                stdout=subprocess.DEVNULL,
                stderr=subprocess.DEVNULL
            )
            
            # Attempt Ownership Registration
            if _IS_WINDOWS:
                time.sleep(0.5)
                final_pid = _refine_pid_windows(0, info.get("process", "chrome.exe"), prior_pids=prior_pids, launch_start=launch_start, lifecycle="browser")
                if final_pid and rt:
                    rt.register_tracked_process(final_pid, app_name, url)
                    return {"success": True, "message": f"Routed {cap} to {app_name}.", "pid": final_pid, "canonical_name": app_name}

            return {"success": True, "message": f"Launched {cap} in {app_name}."}
        except Exception as e:
            return {"success": False, "message": f"Failed to route {cap} to {app_name}: {e}"}
            
    # For now, just mock media capabilities since KIO is lightweight and doesn't hook into Windows Media APIs
    if cap in ("play", "pause", "next", "previous", "open_project", "open_file", "send_message"):
        return {"success": True, "message": f"Successfully routed '{cap}' to {app_name} (mocked API)."}
        
    return {"success": False, "message": f"Capability {cap} not implemented."}

__all__ = ["launch_app", "execute_capability", "close_app", "search_web", "APP_REGISTRY", "WEB_URLS"]
