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
import re
import shutil
import subprocess

import time
import urllib.parse
import webbrowser
import ctypes
from pathlib import Path
from typing import Optional, Dict, Any

from mini_kio.core.operator_protocol import OperatorDescriptor

logger = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# Operator Descriptor
# ---------------------------------------------------------------------------

APP_OPERATOR_DESCRIPTOR: OperatorDescriptor = {
    "tool_name": "app_operator",
    "tool_version": "1.1.0",
    "ram_budget_mb": 12.0,
    "timeout_seconds": 15,
    "side_effect": True,
    "lifecycle_type": "multi",
    "supported_actions": ["open_app", "close_app", "search_web", "execute_capability"]
}

_IS_WINDOWS = platform.system() == "Windows"
_RESTRICTED_CANONICAL_TARGETS = {
    "explorer",
    "cmd",
    "powershell",
    "terminal",
    "taskmgr",
    "regedit",
    "services",
}


# ---------------------------------------------------------------------------
# Internal Normalization Helpers
# ---------------------------------------------------------------------------

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
        "aliases": ["file explorer"],
        "system": True,
    },
    "terminal": {
        "lifecycle": "launcher",
        "exe": "wt.exe",
        "process": "WindowsTerminal.exe",
        "aliases": ["terminal", "console"],
        "paths": ["wt.exe", "powershell.exe", "cmd.exe"],
        "system": True,
    },
    "cmd": {
        "lifecycle": "launcher",
        "exe": "cmd.exe",
        "process": "cmd.exe",
        "aliases": ["command prompt"],
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
    "word": {
        "lifecycle": "standard",
        "exe": "WINWORD.EXE",
        "process": "WINWORD.EXE",
        "aliases": ["microsoft word", "ms word"],
        "system": True,
    },
    "excel": {
        "lifecycle": "standard",
        "exe": "EXCEL.EXE",
        "process": "EXCEL.EXE",
        "aliases": ["microsoft excel", "ms excel"],
        "system": True,
    },
    "powerpoint": {
        "lifecycle": "standard",
        "exe": "POWERPNT.EXE",
        "process": "POWERPNT.EXE",
        "aliases": ["microsoft powerpoint", "ms powerpoint", "ppt"],
        "system": True,
    },
    "snipping tool": {
        "lifecycle": "uwp",
        "exe": "SnippingTool.exe",
        "process": "SnippingTool.exe",
        "aliases": ["snippingtool"],
        "system": True,
    },
    "microsoft store": {
        "lifecycle": "uwp",
        "exe": "WinStore.App.exe",
        "process": "WinStore.App.exe",
        "uri": "ms-windows-store://home",
        "aliases": ["store", "windows store", "ms store"],
        "uwp_packages": ["WinStore.App.exe", "ApplicationFrameHost.exe"],
    },
    "settings": {
        "lifecycle": "uwp",
        "exe": "SystemSettings.exe",
        "process": "SystemSettings.exe",
        "uri": "ms-settings:",
        "aliases": ["windows settings", "system settings"],
        "uwp_packages": ["SystemSettings.exe", "ApplicationFrameHost.exe"],
    },
    "photos": {
        "lifecycle": "uwp",
        "exe": "PhotosApp.exe",
        "process": "PhotosApp.exe",
        "uri": "ms-photos:",
        "aliases": ["microsoft photos", "windows photos"],
        "uwp_packages": ["PhotosApp.exe", "ApplicationFrameHost.exe"],
    },
}

# ---------------------------------------------------------------------------
# Generic installed-application discovery (system-level, no hard-coded list)
# ---------------------------------------------------------------------------
# Sources (bounded, read-only):
#   1. App Paths registry (HKLM + HKCU "...\CurrentVersion\App Paths\<name>.exe")
#   2. Start Menu shortcuts (.lnk) under user + common Programs
#   3. shutil.which / `where` for the executable name
#   4. WindowsApps aliases
# Result is a launch descriptor {"kind": "exe"|"shortcut"|"uri", "target", "display"}.


def _discovery_key(name: str) -> str:
    """Normalize a name for generic identity matching (case + non-alnum)."""
    return re.sub(r"[^a-z0-9]+", "", (name or "").lower())


def _discovery_match(name: str, candidate: str) -> bool:
    """Generic identity match with a length guard so short fragments never over-match."""
    a, b = _discovery_key(name), _discovery_key(candidate)
    if not a or not b:
        return False
    if a == b:
        return True
    if len(a) >= 4 and len(b) >= 4:
        return a in b or b in a
    return False


# --- App Paths discovery cache (avoids repeated registry walks) ---
_APP_PATHS_CACHE: dict = {"ts": 0.0, "results": {}}
_APP_PATHS_CACHE_TTL = 300.0  # 5 minutes


def _app_paths_discovery(name: str) -> Optional[str]:
    """Find an installed executable through the App Paths registry."""
    if not _IS_WINDOWS:
        return None
    # Check cache first (avoids repeated registry enumeration per classification)
    now = time.time()
    cache = _APP_PATHS_CACHE
    if now - cache["ts"] < _APP_PATHS_CACHE_TTL and name in cache["results"]:
        return cache["results"][name]
    result = _app_paths_discovery_uncached(name)
    # Store in cache (both found and not-found)
    if now - cache["ts"] >= _APP_PATHS_CACHE_TTL:
        cache["ts"] = now
        cache["results"].clear()
    cache["results"][name] = result
    return result


def _app_paths_discovery_uncached(name: str) -> Optional[str]:
    """Inner registry walk — uncached."""
    try:
        import winreg
    except Exception:
        return None
    key_path = r"SOFTWARE\Microsoft\Windows\CurrentVersion\App Paths"
    for hive in (winreg.HKEY_LOCAL_MACHINE, winreg.HKEY_CURRENT_USER):
        try:
            with winreg.OpenKey(hive, key_path) as base:
                i = 0
                while True:
                    try:
                        sub = winreg.EnumKey(base, i)
                    except OSError:
                        break
                    i += 1
                    if _discovery_match(name, sub.replace(".exe", "")):
                        try:
                            with winreg.OpenKey(base, sub) as key:
                                val, _ = winreg.QueryValueEx(key, None)
                            if val and os.path.isfile(val):
                                return val
                        except OSError:
                            continue
        except OSError:
            continue
    return None


# --- Start Menu discovery cache (avoids repeated os.walk per classification) ---
_START_MENU_CACHE: dict = {"ts": 0.0, "results": {}}
_START_MENU_CACHE_TTL = 300.0  # 5 minutes


def _start_menu_discovery(name: str) -> Optional[str]:
    """Find a Start Menu .lnk shortcut matching the requested name (bounded walk)."""
    if not _IS_WINDOWS:
        return None
    # Check cache first (avoids repeated os.walk per classification call)
    now = time.time()
    cache = _START_MENU_CACHE
    if now - cache["ts"] < _START_MENU_CACHE_TTL and name in cache["results"]:
        return cache["results"][name]
    result = _start_menu_discovery_uncached(name)
    # Store in cache (both found and not-found)
    if now - cache["ts"] >= _START_MENU_CACHE_TTL:
        cache["ts"] = now
        cache["results"].clear()
    cache["results"][name] = result
    return result


def _start_menu_discovery_uncached(name: str) -> Optional[str]:
    """Inner Start Menu walk — uncached, bounded."""
    roots = [
        os.path.join(os.environ.get("APPDATA", ""), "Microsoft", "Windows", "Start Menu", "Programs"),
        os.path.join(os.environ.get("ProgramData", ""), "Microsoft", "Windows", "Start Menu", "Programs"),
    ]
    for root in roots:
        if not root or not os.path.isdir(root):
            continue
        try:
            for dirpath, _dirs, files in os.walk(root):
                if dirpath[len(root):].count(os.sep) > 4:
                    continue
                for f in files:
                    if not f.lower().endswith(".lnk"):
                        continue
                    stem = os.path.splitext(f)[0]
                    if _discovery_match(name, stem):
                        return os.path.join(dirpath, f)
        except (PermissionError, OSError):
            continue
    return None


def _windows_apps_alias(name: str) -> Optional[str]:
    """Resolve a WindowsApps app-execution alias (Store/UWP) if present."""
    local = os.environ.get("LOCALAPPDATA", "")
    if not local:
        return None
    base = os.path.join(local, "Microsoft", "WindowsApps")
    if not os.path.isdir(base):
        return None
    for exe_name in (name, name + ".exe"):
        candidate = exe_name if exe_name.endswith(".exe") else exe_name + ".exe"
        if os.path.isfile(os.path.join(base, candidate)):
            return os.path.join(base, candidate)
    return None


# Generic UWP (Store) app discovery via Get-StartApps — cached, bounded.
# This is what makes "open camera" resolve the NATIVE Windows Camera app
# (Microsoft.WindowsCamera) instead of synthesizing camera.com: UWP apps are
# not registered in App Paths, have no Start-Menu .lnk, and their WindowsApps
# aliases are not always materialized as files.
_UWP_APPS_CACHE: dict = {"ts": 0.0, "apps": [], "failed_ts": 0.0}
_UWP_APPS_CACHE_TTL = 120.0
_UWP_APPS_FAIL_RETRY = 30.0


def _uwp_start_apps() -> list[tuple[str, str]]:
    """Installed Start-apps as (display_name, AUMID) pairs, cached 120s.

    Failures are also cached (shorter retry window) so a single hung/failed
    PowerShell call can never become a retry storm on the open-app hot path.
    """
    import time as _t
    now = _t.time()
    if now - _UWP_APPS_CACHE["ts"] < _UWP_APPS_CACHE_TTL and _UWP_APPS_CACHE["apps"]:
        return list(_UWP_APPS_CACHE["apps"])
    if _UWP_APPS_CACHE["failed_ts"] and now - _UWP_APPS_CACHE["failed_ts"] < _UWP_APPS_FAIL_RETRY:
        return list(_UWP_APPS_CACHE["apps"])
    apps: list[tuple[str, str]] = []
    failed = False
    try:
        r = subprocess.run(
            ["powershell", "-NoProfile", "-Command",
             "Get-StartApps | ForEach-Object { $_.Name + '|' + $_.AppID }"],
            capture_output=True, text=True, timeout=10, encoding="utf-8", errors="replace",
        )
        for line in (r.stdout or "").splitlines():
            line = line.strip()
            if "|" in line:
                display, aumid = line.split("|", 1)
                display, aumid = display.strip(), aumid.strip()
                if display and aumid:
                    apps.append((display, aumid))
    except Exception:
        apps = []
        failed = True
    _UWP_APPS_CACHE["ts"] = _t.time()
    _UWP_APPS_CACHE["apps"] = apps
    _UWP_APPS_CACHE["failed_ts"] = _t.time() if failed else 0.0
    return list(apps)


def _uwp_app_discovery(name: str) -> Optional[Dict]:
    """Resolve a UWP/Store app by display-name match (generic, cached).

    Returns {"kind": "uwp", "target": <AUMID>, "display": <display>} or None.
    Containment matching reuses the same guarded identity matcher as the rest
    of discovery (>=4 chars), so "camera" resolves Windows Camera but a short
    fragment never over-matches. No application-specific branches.
    """
    if not _IS_WINDOWS or not name:
        return None
    norm = name.lower().strip()
    if len(norm) < 3:
        return None
    best: Optional[tuple[int, str, str]] = None
    for display, aumid in _uwp_start_apps():
        if _discovery_match(norm, display):
            score = -abs(len(display) - len(norm))  # closer length wins
            if best is None or score > best[0]:
                best = (score, display, aumid)
    if best:
        return {"kind": "uwp", "target": best[2], "display": best[1], "name": name.strip()}
    return None


# --- _find_installed_app result cache ---
_FIND_INSTALLED_CACHE: dict = {"ts": 0.0, "results": {}}
_FIND_INSTALLED_CACHE_TTL = 300.0  # 5 minutes


def _find_installed_app(name: str) -> Optional[Dict]:
    """Generic Windows installed-application discovery (no hard-coded list).

    Returns a launch descriptor or None. Arbitrary installed GUI apps are
    discoverable through the same mechanism. UWP/Store apps resolve through
    the Start-apps AUMID source, keeping native-first true for apps that have
    no exe path, registry entry, or Start-Menu shortcut.
    """
    if not _IS_WINDOWS or not name:
        return None
    norm = name.lower().strip()
    # Check top-level cache first
    now = time.time()
    cache = _FIND_INSTALLED_CACHE
    if now - cache["ts"] < _FIND_INSTALLED_CACHE_TTL and norm in cache["results"]:
        return cache["results"][norm]
    result = _find_installed_app_uncached(name, norm)
    # Store in cache
    if now - cache["ts"] >= _FIND_INSTALLED_CACHE_TTL:
        cache["ts"] = now
        cache["results"].clear()
    cache["results"][norm] = result
    return result


def _find_installed_app_uncached(name: str, norm: str) -> Optional[Dict]:
    """Inner discovery — uncached."""
    exe = _app_paths_discovery(norm)
    if exe:
        return {"kind": "exe", "target": exe, "display": name.strip()}
    lnk = _start_menu_discovery(norm)
    if lnk:
        return {"kind": "shortcut", "target": lnk, "display": name.strip()}
    for exe_name in (norm, norm + ".exe"):
        found = shutil.which(exe_name)
        if found:
            return {"kind": "exe", "target": found, "display": name.strip()}
    alias = _windows_apps_alias(norm)
    if alias:
        return {"kind": "exe", "target": alias, "display": name.strip()}
    # Native-first must stay true for UWP apps (Camera, Photos, Store...) that
    # never materialize an exe/lnk/alias — resolve their AUMID and launch the
    # native app instead of silently opening the website.
    uwp = _uwp_app_discovery(norm)
    if uwp:
        return uwp
    return None


# ---------------------------------------------------------------------------
# Installed-application inventory (generic, bounded, read-only)
# ---------------------------------------------------------------------------
# "What apps do I have?" must reflect the real machine — not a curated list.
# Sources (all authoritative, all bounded):
#   1. Uninstall registry (HKLM + HKCU, 32- and 64-bit views)
#   2. Start Menu .lnk stems (user + common Programs)
#   3. WindowsApps execution aliases
# Result is a deduplicated, sorted list of display names, capped at `limit`.
# Reading is side-effect free and fast (registry enumerations only; the
# Start-Menu walk is depth-bounded exactly like _start_menu_discovery).


_INSTALLED_APP_SKIP_SUFFIXES = (
    ".lnk", ".txt", ".url", ".log", ".rtf", ".html", ".htm", ".pdf",
)


def _uninstall_registry_names() -> set[str]:
    """DisplayName values from the Uninstall registry views (bounded)."""
    if not _IS_WINDOWS:
        return set()
    names: set[str] = set()
    try:
        import winreg
    except Exception:
        return names
    paths = (
        (winreg.HKEY_LOCAL_MACHINE, r"SOFTWARE\Microsoft\Windows\CurrentVersion\Uninstall"),
        (winreg.HKEY_LOCAL_MACHINE, r"SOFTWARE\WOW6432Node\Microsoft\Windows\CurrentVersion\Uninstall"),
        (winreg.HKEY_CURRENT_USER, r"SOFTWARE\Microsoft\Windows\CurrentVersion\Uninstall"),
    )
    for hive, path in paths:
        try:
            with winreg.OpenKey(hive, path) as base:
                i = 0
                while True:
                    try:
                        sub = winreg.EnumKey(base, i)
                    except OSError:
                        break
                    i += 1
                    try:
                        with winreg.OpenKey(base, sub) as key:
                            val, _ = winreg.QueryValueEx(key, "DisplayName")
                        val = (val or "").strip()
                        if val and not val.lower().startswith(("kb", "update for ", "security update")):
                            names.add(val)
                    except OSError:
                        continue
        except OSError:
            continue
    return names


def _start_menu_app_stems() -> set[str]:
    """App names from Start Menu shortcut stems (user + common, bounded)."""
    if not _IS_WINDOWS:
        return set()
    stems: set[str] = set()
    roots = [
        os.path.join(os.environ.get("APPDATA", ""), "Microsoft", "Windows", "Start Menu", "Programs"),
        os.path.join(os.environ.get("ProgramData", ""), "Microsoft", "Windows", "Start Menu", "Programs"),
    ]
    for root in roots:
        if not root or not os.path.isdir(root):
            continue
        try:
            for dirpath, _dirs, files in os.walk(root):
                if dirpath[len(root):].count(os.sep) > 4:
                    continue
                for f in files:
                    low = f.lower()
                    if not low.endswith(".lnk"):
                        continue
                    stem = os.path.splitext(f)[0].strip()
                    if stem and not stem.lower().startswith(("uninstall", "readme")):
                        stems.add(stem)
        except (PermissionError, OSError):
            continue
    return stems


def list_installed_apps(limit: int = 40) -> list[str]:
    """Generic installed-application inventory.

    Merges authoritative Windows sources (Uninstall registry, Start Menu
    shortcuts, WindowsApps aliases), deduplicates, sorts, and caps at
    `limit`. No hard-coded application list — arbitrary installed apps
    appear. Returns [] when discovery is unavailable (never fabricated).
    """
    names = _uninstall_registry_names()
    names |= _start_menu_app_stems()
    if _IS_WINDOWS:
        local = os.environ.get("LOCALAPPDATA", "")
        base = os.path.join(local, "Microsoft", "WindowsApps")
        if os.path.isdir(base):
            try:
                for f in os.listdir(base):
                    low = f.lower()
                    if low.endswith(".exe") and not low.startswith("desktopappinstaller"):
                        names.add(os.path.splitext(f)[0])
            except OSError:
                pass
    ordered = sorted(names, key=lambda s: s.lower())
    return ordered[:max(1, int(limit))]


def _launch_discovered(desc: Dict, name: str) -> dict:
    """Launch a generic discovered application (exe path or .lnk shortcut).

    On success the process is registered with the runtime under the requested
    name so a subsequent "Close it" resolves to this app (never the browser
    host or an unrelated process).
    """
    kind = desc.get("kind")
    target = desc.get("target", "")
    result = None
    if kind == "uwp" and target:
        # Launch a UWP/Store app by AUMID (e.g. Windows Camera). explorer.exe
        # shell:AppsFolder\<AUMID> is the canonical, dependency-free launch
        # mechanism. The app runs under ApplicationFrameHost, so PID capture is
        # not meaningful — verification_mode stays honest ("shell").
        try:
            subprocess.Popen(["explorer.exe", f"shell:AppsFolder\\{target}"])
            result = {"success": True, "message": f"Opened {name}", "verification_mode": "shell"}
        except Exception as exc:
            return {"success": False, "message": f"Failed to open {name}: {str(exc)[:80]}"}
    elif kind == "shortcut" and target:
        try:
            os.startfile(target)
            result = {"success": True, "message": f"Opened {name}", "verification_mode": "shell"}
        except Exception as exc:
            return {"success": False, "message": f"Failed to open {name}: {str(exc)[:80]}"}
    elif kind == "exe" and target:
        result = _launch_path(target, name)
    else:
        return {"success": False, "message": f"Failed to open {name}."}

    # Bounded ownership registration: track the resolved pid so "Close it"
    # targets exactly this application.
    if result and result.get("success") and isinstance(result.get("pid"), int):
        try:
            from mini_kio.core.runtime import get_runtime
            rt = get_runtime()
            if rt:
                rt.register_tracked_process(int(result["pid"]), name.lower().strip())
        except Exception:
            pass
    return result


# ---------------------------------------------------------------------------
# Web apps — opened directly in the default browser
# ---------------------------------------------------------------------------
WEB_URLS: Dict[str, str] = {
    "youtube":      "https://youtube.com",
    "whatsapp":     "https://web.whatsapp.com",
    "whatsapp web": "https://web.whatsapp.com",
    "telegram":     "https://web.telegram.org",
    "instagram":    "https://instagram.com",
    "claude":       "https://claude.ai",
    "claude ai":    "https://claude.ai",
    "gemini":       "https://gemini.google.com/app",
    "chatgpt":      "https://chat.openai.com",
    "gmail":        "https://gmail.com",
    "github":       "https://github.com",
    "google":       "https://google.com",
    "netflix":      "https://netflix.com",
}

WEB_DOMAIN_ALIASES: Dict[str, str] = {
    "google photos": "https://photos.google.com",
    "google drive": "https://drive.google.com",
    "google docs": "https://docs.google.com",
    "google sheets": "https://sheets.google.com",
    "google maps": "https://maps.google.com",
    "google calendar": "https://calendar.google.com",
    "google keep": "https://keep.google.com",
    "google translate": "https://translate.google.com",
    "google classroom": "https://classroom.google.com",
    "chat qwen ai": "https://chat.qwen.ai",
    "figma": "https://figma.com",
    "notion": "https://notion.so",
}

_ALLOWED_WEB_TLDS = {"com", "ai", "org", "io", "dev", "app"}
_SAFE_DOMAIN_LABEL_RE = re.compile(r"^[a-z0-9][a-z0-9-]*$")
_SAFE_SYNTHETIC_DOMAIN_LABEL_RE = re.compile(r"^[a-z0-9-]{1,63}$")
_SAFE_EXPLICIT_DOMAIN_RE = re.compile(
    r"^[a-z0-9](?:[a-z0-9-]*[a-z0-9])?(?:\.[a-z0-9](?:[a-z0-9-]*[a-z0-9])?)+$"
)
_SAFE_URL_PATH_RE = re.compile(r"^[a-z0-9._~:@%+\-=]+(?:/[a-z0-9._~:@%+\-=]+)*$")
_SAFE_SINGLE_PATH_SEGMENT_RE = re.compile(r"^[a-z0-9._-]+$")
_RESERVED_SYNTHETIC_WEB_LABELS = {
    "localhost",
    "explorer",
    "desktop",
    "downloads",
    "documents",
    "pictures",
    "music",
    "videos",
    "control",
    "cmd",
    "powershell",
    "terminal",
    "appdata",
}

# ---------------------------------------------------------------------------
# Verified multi-word web-entity resolution (generic, bounded, cached)
# ---------------------------------------------------------------------------
# "Open Stack Overflow" (native absent) must resolve to stackoverflow.com —
# its canonical web presence — WITHOUT opening parked/for-sale/domain-echo
# squatter pages. DNS presence alone cannot distinguish (davinciresolve.com
# resolves too), so the collapsed <brand>.com is accepted only when the
# homepage verifies the brand: a readable title containing the natural phrase,
# OR an anti-bot wall (Cloudflare challenge / 403 / timeout) in front of a
# DNS-present host (the recognizable-web-entity case the directive requires).
# Parked pages serve readable "for sale"/domain-echo pages and are rejected.
# Every lookup is time-bounded and cached; multi-word names that fail stay a
# truthful failure — never a fabricated URL.

_WEB_DNS_CACHE: Dict[str, bool] = {}
_WEB_TITLE_CACHE: Dict[str, Optional[str]] = {}

_PARKED_TITLE_MARKERS = (
    "for sale", "premium domain", "buy this domain", "domain is for sale",
    "parked", "sedo", "afternic", "hugedomains", "this domain", "squat",
    "domain marketplace",
)
_ANTIBOT_TITLE_MARKERS = (
    "just a moment", "attention required", "checking your browser",
    "verify you are human", "enable javascript", "captcha",
    "access denied", "not available", "security check",
)


def _brand_domain_resolves(host: str) -> bool:
    """Bounded DNS presence check for a candidate brand host (cached)."""
    if host in _WEB_DNS_CACHE:
        return _WEB_DNS_CACHE[host]
    ok = False
    try:
        import socket
        infos = socket.getaddrinfo(host, 443, proto=socket.IPPROTO_TCP)
        ok = bool(infos)
    except Exception:
        ok = False
    _WEB_DNS_CACHE[host] = ok
    return ok


def _brand_page_title(url: str) -> Optional[str]:
    """Bounded homepage <title> fetch (4s hard timeout, cached).

    None means the title could not be read (anti-bot wall, 403, timeout) —
    the caller then falls back to the DNS-present recognizable-entity rule.
    """
    if url in _WEB_TITLE_CACHE:
        return _WEB_TITLE_CACHE[url]
    title = None
    try:
        import urllib.request
        req = urllib.request.Request(url, headers={
            "User-Agent": (
                "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
                "AppleWebKit/537.36 (KHTML, like Gecko) Chrome/126.0 Safari/537.36"
            ),
            "Accept": "text/html",
        })
        with urllib.request.urlopen(req, timeout=4.0) as resp:
            html = resp.read(150000).decode("utf-8", "ignore")
        m = re.search(r"<title[^>]*>(.*?)</title>", html, re.I | re.S)
        if m:
            title = re.sub(r"\s+", " ", m.group(1)).strip()[:200]
    except Exception:
        title = None
    _WEB_TITLE_CACHE[url] = title
    return title


def _phrase_in_title(words, title: str) -> bool:
    """True when the title contains the natural phrase words as WHOLE tokens
    in order. Token matching (not substring matching) so a parked domain echo
    like "davinciresolve.com" can never satisfy "da vinci resolve" — the
    title tokens are [davinciresolve, com], and "da"/"vinci" are not tokens.
    """
    tokens = re.sub(r"[^a-z0-9 ]+", " ", (title or "").lower()).split()
    idx = 0
    for w in words:
        found = False
        for i in range(idx, len(tokens)):
            if tokens[i] == w:
                idx = i + 1
                found = True
                break
        if not found:
            return False
    return True


_BRAND_SEARCH_INDICATORS = frozenset({
    "best", "top", "latest", "near", "under", "cheap",
    "who", "what", "where", "when", "why", "how",
    "in", "on", "at", "for", "with", "by", "to", "of",
    "some", "thing", "something", "anything", "about", "vs",
})


def _verified_brand_domain(name: str) -> Optional[str]:
    """Resolve a recognizable multi-word web entity to its canonical web
    presence (e.g. "stack overflow" -> https://stackoverflow.com) with
    verification. Returns a URL or None (truthful failure).

    Guards (deterministic): 2-3 ASCII alphanumeric words, no search-shaped
    words, collapsed label is a safe single label, not reserved, not a
    registry alias, not an internal host. Verification (bounded, cached):
    DNS presence + homepage title check that rejects parked/for-sale pages
    and accepts real sites (including Cloudflare-walled ones).
    """
    normalized = " ".join((name or "").lower().strip().split())
    if not normalized or " " not in normalized:
        return None
    parts = normalized.split()
    if not (2 <= len(parts) <= 3):
        return None
    if set(parts) & _BRAND_SEARCH_INDICATORS:
        return None
    if not all(p.isascii() and p.isalnum() for p in parts):
        return None
    collapsed = normalized.replace(" ", "")
    if not _can_synthesize_single_label_domain(collapsed):
        return None
    # Deterministic in unit tests: no live DNS/HTTP (slow + flaky). Real
    # synthesis is exercised in live validation and via the dedicated tests
    # below that mock the network probes.
    if os.environ.get("KIO_TEST_MODE") == "1":
        return None
    host = f"{collapsed}.com"
    if not _brand_domain_resolves(host):
        return None
    url = f"https://{host}"
    title = _brand_page_title(url)
    if title is None:
        # Unreadable but DNS-present: a live recognizable web entity behind an
        # anti-bot wall (e.g. stackoverflow.com). Parked pages serve readable
        # pages precisely so the domain can be sold, so this is a safe signal.
        return url
    low = title.lower()
    if any(m in low for m in _PARKED_TITLE_MARKERS):
        return None
    if _phrase_in_title(parts, title):
        return url
    # Domain echo (title is basically the domain: "davinciresolve.com").
    echo = re.sub(r"[^a-z0-9]+", "", low)
    if echo == collapsed or (echo.startswith(collapsed) and len(echo) <= len(collapsed) + 4):
        return None
    return None

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

def _normalize_public_result(action: str, target: str, result: Dict[str, Any], start_time: float) -> Dict[str, Any]:
    """Normalize public API results to the deterministic target shape.

    Target shape:
    {
      "success": bool,
      "message": str,
      "action": str,
      "target": str,
      "elapsed_ms": int,
      "failure_class": str,
      "pid": int | None
    }
    """
    if not isinstance(result, dict):
        result = {"success": False, "message": str(result)}

    out: Dict[str, Any] = dict(result)
    # Ensure core fields
    out.setdefault("success", bool(out.get("success", False)))
    out.setdefault("message", out.get("message", ""))

    # Action and target
    out["action"] = action
    out["target"] = out.get("canonical_name") or target

    # Elapsed ms telemetry
    try:
        out["elapsed_ms"] = int((time.time() - float(start_time)) * 1000)
    except Exception:
        out["elapsed_ms"] = 0

    # PID normalization
    pid = out.get("pid")
    out["pid"] = int(pid) if isinstance(pid, int) else None

    # Failure class deterministic mapping
    if "failure_class" in out:
        # preserve any explicit classification
        pass
    else:
        if out.get("success"):
            out["failure_class"] = ""
        else:
            msg = (out.get("message", "") or "").lower()
            if "timeout" in msg:
                out["failure_class"] = "timeout"
            elif "cannot find" in msg or "not found" in msg or "is it installed" in msg or "cannot find or open" in msg:
                out["failure_class"] = "not_installed"
            elif "ownership not tracked" in msg or "ownership not tracked" in msg or "not tracked" in msg:
                out["failure_class"] = "not_tracked"
            elif "refusing to kill" in msg or "refusing" in msg:
                out["failure_class"] = "forbidden_uwp_kill"
            elif "failed to launch" in msg or "failed to open" in msg or "failed to route" in msg or "failed to" in msg:
                out["failure_class"] = "launch_failed"
            elif "permission" in msg or "access denied" in msg:
                out["failure_class"] = "permission_denied"
            elif "unsupported" in msg or "not implemented" in msg or "does not support" in msg:
                out["failure_class"] = "unsupported"
            elif "invalid" in msg:
                out["failure_class"] = "invalid_input"
            elif "already closed" in msg or "not running" in msg:
                out["failure_class"] = "not_running"
            else:
                out["failure_class"] = "internal_error"

    return out

def _web_url_for_open(name: str, *, allow_single_word_synthesis: bool = False) -> Optional[str]:
    """Resolve a URL for an OPEN request without silent domain substitution.

    Returns a URL only when the request is explicitly web-shaped:
      - known web app alias (WEB_URLS / WEB_DOMAIN_ALIASES)
      - explicit http(s) URL
      - dotted domain with an allowed TLD
      - single-word domain-like label ("chatgpt" -> chatgpt.com) — only when
        `allow_single_word_synthesis=True` (callers check generic app discovery
        FIRST, so an installed single-word app is never hijacked to its .com
        website).

    Arbitrary multi-word names ("da vinci resolve", "microsoft store") are
    NEVER turned into .com domains here — that silent substitution is the
    app-open bug this fixes. Multi-word web synthesis remains available only
    for explicit web-intent phrases ("open X in chrome", "go to X").
    """
    normalized = " ".join((name or "").lower().strip().split())
    if not normalized:
        return None
    if normalized in WEB_URLS:
        return WEB_URLS[normalized]
    if normalized in WEB_DOMAIN_ALIASES:
        return WEB_DOMAIN_ALIASES[normalized]
    if normalized.startswith(("http://", "https://")):
        return normalized
    if _SAFE_EXPLICIT_DOMAIN_RE.fullmatch(normalized):
        parts = normalized.split(".")
        if len(parts) >= 2 and parts[-1] in _ALLOWED_WEB_TLDS:
            return f"https://{normalized}"
        return None
    if _contains_forbidden_web_chars(normalized) or _is_internal_or_local_web_target(normalized):
        return None
    if allow_single_word_synthesis and _can_synthesize_single_label_domain(normalized):
        return f"https://{normalized}.com"
    return None


def _web_fallback_url(name: str, *, allow_synthesis: bool = True) -> Optional[str]:
    """Resolve the legitimate web version for a not-found / failed-launch fallback.

    Two distinct call sites:

    NOT-FOUND fallback (allow_synthesis=True, default): the native application
    was proved absent by OS discovery. Single-word .com synthesis is permitted
    (canonical <name>.com IS the standard web presence of that product), and
    multi-word recognizable web entities ("stack overflow" ->
    stackoverflow.com) are resolved through VERIFIED brand-domain synthesis —
    never a fabricated URL.

    LAUNCH-FAILED fallback (allow_synthesis=False): the native application
    EXISTS but could not be launched. Here a synthesized <name>.com is a
    fabricated URL, not a "web version of the app" — so only KNOWN web
    versions (WEB_URLS / WEB_DOMAIN_ALIASES / explicit URL / dotted domain)
    qualify. The caller reports the truthful "found but couldn't launch"
    when no known web version exists.

    Shared guards: reserved labels (explorer, cmd, powershell, terminal,
    appdata, ...) and internal hosts stay blocked; verification rejects
    parked/for-sale/domain-echo pages.
    """
    normalized = " ".join((name or "").lower().strip().split())
    if not normalized:
        return None
    if normalized in WEB_URLS:
        return WEB_URLS[normalized]
    if normalized in WEB_DOMAIN_ALIASES:
        return WEB_DOMAIN_ALIASES[normalized]
    if normalized.startswith(("http://", "https://")):
        return normalized
    if _SAFE_EXPLICIT_DOMAIN_RE.fullmatch(normalized):
        parts = normalized.split(".")
        if len(parts) >= 2 and parts[-1] in _ALLOWED_WEB_TLDS:
            return f"https://{normalized}"
        return None
    # Injection/unsafe-char guard: spaces are a legitimate multi-word input for
    # the verified synthesis path below, so only truly dangerous characters
    # short-circuit here.
    if _contains_dangerous_web_chars(normalized) or _is_internal_or_local_web_target(normalized):
        return None
    if allow_synthesis:
        if normalized.isascii() and normalized not in _RESERVED_SYNTHETIC_WEB_LABELS:
            if _SAFE_SYNTHETIC_DOMAIN_LABEL_RE.fullmatch(normalized):
                return f"https://{normalized}.com"
        # Verified multi-word web entity ("stack overflow" -> stackoverflow.com)
        # only after the native app was proved absent; parked pages rejected.
        verified = _verified_brand_domain(normalized)
        if verified is not None:
            return verified
    return None


def _web_fallback_result(
    key: str, name: str, start_time: float, *, reason: str = "not_found"
) -> Optional[Dict]:
    """Open the legitimate web version of an unavailable native application.

    UX RULE (2026-08-10 directive): a SUCCESSFUL open gets a short natural
    confirmation ("Opened Stack Overflow.") — the user asked for the target
    and got it; internal native-vs-web modality stays structured metadata so
    a later "close it" still resolves to the correct web target. Fallback
    reasoning is exposed only when it explains a FAILURE (launch_failed).

    reason="not_found":    the native app is not installed / not discoverable.
    reason="launch_failed": the native app exists but could not be launched.

    Returns a normalized public launch result (success) with modality
    "web_fallback", or None when no legitimate web target exists (the caller
    then reports the truthful native-only failure).

    allow_synthesis is disabled for launch_failed so a native app that EXISTS
    but failed to launch only falls back to a KNOWN web version — never a
    fabricated <name>.com.
    """
    web_url = _web_fallback_url(key, allow_synthesis=(reason != "launch_failed"))
    if web_url is None:
        return None
    result = _open_url(web_url, key)
    if not result.get("success"):
        return None
    result["modality"] = "web_fallback"
    try:
        from mini_kio.core.target_ref import display_target_name
        display = display_target_name(key)
    except Exception:
        display = name.strip() or key
    if reason == "launch_failed":
        result["message"] = (
            f"I couldn't launch the installed {name} app, "
            f"so I opened its web version in your browser."
        )
    else:
        result["message"] = f"Opened {display}."
    return _normalize_public_result("launch", key, result, start_time)


def launch_app(name: str) -> dict:
    """Launch an application by name.  Returns {"success": bool, "message": str, "pid": int, "canonical_name": str}."""
    start_time = time.time()
    key = name.lower().strip()
    logger.info(f"[APP] launch_app: {key!r}")

    # Safety: Restricted targets must reject before ANY execution logic or discovery.
    norm_key = key[:-4] if key.endswith(".exe") else key
    if norm_key in _RESTRICTED_CANONICAL_TARGETS:
        return _normalize_public_result(
            "launch",
            key,
            {
                "success": False,
                "message": f"{name} is restricted for safety.",
                "failure_class": "restricted_target",
                "pid": None,
            },
            start_time,
        )

    # 1. Registered native app (path / URI / system / UWP entry) — the entry
    #    itself is evidence of installation even without a resolvable path
    #    (e.g. Microsoft Store launches via its protocol URI). Exact identity.
    info = _find_in_registry(key)
    if info and (
        info.get("uri") or info.get("system") or info.get("uwp_packages")
        or _resolve_path(info) is not None
    ):
        canonical = key
        for k, v in APP_REGISTRY.items():
            if v == info:
                canonical = k
                break
        result = _launch_from_info(info, key)
        if result.get("success"):
            result["canonical_name"] = canonical
            return _normalize_public_result("launch", canonical, result, start_time)
        # E. Native app found but launch failed — if a legitimate web version
        #    exists, disclose the fallback; otherwise report the native
        #    failure truthfully ("found but couldn't launch", never a
        #    misleading "not installed").
        fallback = _web_fallback_result(key, name, start_time, reason="launch_failed")
        if fallback is not None:
            return fallback
        result = {"success": False, "message": f"I found {name} installed, but I couldn't launch it."}
        result["canonical_name"] = canonical
        return _normalize_public_result("launch", canonical, result, start_time)

    # 2. GENERIC installed-application discovery (arbitrary apps, no registry).
    #    NATIVE-FIRST: an installed desktop app wins over its website for a
    #    default open ("open github" -> GitHub Desktop when installed). Web
    #    remains the fallback, never the default. Runs before web-target
    #    resolution so an installed single-word app (e.g. "winrar") is never
    #    hijacked to its .com website.
    discovered = _find_installed_app(key)
    if discovered:
        result = _launch_discovered(discovered, key)
        if result.get("success"):
            result["canonical_name"] = key
            return _normalize_public_result("launch", key, result, start_time)
        # E. Discovered app found but launch failed — disclosed web fallback;
        #    otherwise report truthfully (found but couldn't launch).
        fallback = _web_fallback_result(key, name, start_time, reason="launch_failed")
        if fallback is not None:
            return fallback
        result = {"success": False, "message": f"I found {name} installed, but I couldn't launch it."}
        result["canonical_name"] = key
        return _normalize_public_result("launch", key, result, start_time)

    # 3. Explicit web target (KNOWN web apps / URL / dotted domain only) — the
    #    FALLBACK after both registry and generic native discovery proved no
    #    installed app exists. Dual-modality names (a registered native
    #    identity ALSO exists, e.g. "telegram"): this web open is a FALLBACK
    #    and must be disclosed — never presented as opening the application.
    normalized_url = _web_url_for_open(key, allow_single_word_synthesis=False)
    if normalized_url is not None:
        result = _open_url(normalized_url, key)
        # Dual-modality: registered native identity also exists (e.g. telegram)
        # but is unavailable, so this web open is a modality fallback. The
        # short "Opened X." confirmation stays (UX rule) while modality is
        # recorded so "close it" resolves to the correct web target. A failed
        # _open_url keeps its truthful failure message.
        if _find_in_registry(key) is not None and result.get("success"):
            result["modality"] = "web_fallback"
            try:
                from mini_kio.core.target_ref import display_target_name
                result["message"] = f"Opened {display_target_name(key)}."
            except Exception:
                result["message"] = f"Opened {name.strip()}."
        return _normalize_public_result("launch", key, result, start_time)

    # 4. Native application unavailable → DISCLOSED web fallback (FUNDAMENTAL
    #    INVARIANT). Never hide a modality fallback: when a legitimate web
    #    version is available, open it but explicitly disclose that the native
    #    app was not found. Single-word .com synthesis is only applied HERE —
    #    after discovery proved no native app exists — so an installed
    #    single-word app is never hijacked. Multi-word names are never
    #    synthesized into fabricated domains.
    fallback = _web_fallback_result(key, name, start_time)
    if fallback is not None:
        return fallback

    # 5. Truthful failure — neither a native app nor a usable web version.
    return _normalize_public_result(
        "launch",
        key,
        {
            "success": False,
            "message": (
                f"I couldn't find {name} installed on your computer, "
                f"and I couldn't find a usable web version either."
            ),
            "failure_class": "not_installed",
            "pid": None,
        },
        start_time,
    )


def _close_web_target(name: str, key: str, start_time: float) -> dict:
    """Close a web-app browser session at TAB scope (BC-1/BC-2 fix).

    Never terminates the host browser process. Resolution order:
      1. Active capability session (KIO-opened web app) -> close its tab/session.
      2. Browser connector tab close by friendly name.
      3. Truthful failure (no blind process kill, no ownership refusal).
    """
    from mini_kio.core.target_ref import parse_target, display_target_name
    display = display_target_name(key)
    ref = parse_target(key)
    resolve_name = ref.name or key

    # 1) Active capability session (the capability registry is the authoritative
    #    store for web-app sessions; routing_utils owns the isolated-profile
    #    safety gate).
    try:
        from mini_kio.core.routing_utils import (
            resolve_capability_for_close,
            close_browser_capability,
            deactivate_capability,
        )
        cap = resolve_capability_for_close(resolve_name)
        if cap:
            url = cap.get("url", "") or ""
            conn_ok = False
            try:
                from mini_kio.core.command_router import _get_connector
                from mini_kio.core.async_utils import safe_run_async
                conn = _get_connector()
                if conn is not None and conn.is_connected():
                    result = safe_run_async(conn.close_tab(resolve_name or url))
                    conn_ok = bool(getattr(result, "success", False))
            except Exception as exc:
                logger.warning("[APP] web tab close via connector failed: %s", exc)
            if conn_ok or close_browser_capability(cap):
                try:
                    deactivate_capability(resolve_name)
                except Exception:
                    pass
                return _normalize_public_result(
                    "close", key,
                    {"success": True, "message": f"Closed {display}.",
                     "capability_closed": True, "capability_name": display},
                    start_time,
                )
            return _normalize_public_result(
                "close", key,
                {"success": False, "message": f"Couldn't close {display}.",
                 "failure_class": "capability_close_failed"},
                start_time,
            )
    except Exception as exc:
        logger.warning("[APP] capability close lookup failed for %s: %s", key, exc)

    # 2) Browser connector tab close by friendly name (covers manually-opened
    #    tabs that never created a capability session).
    try:
        from mini_kio.core.command_router import _get_connector
        from mini_kio.core.async_utils import safe_run_async
        conn = _get_connector()
        if conn is not None and conn.is_connected():
            result = safe_run_async(conn.close_tab(resolve_name or key))
            if getattr(result, "success", False):
                return _normalize_public_result(
                    "close", key,
                    {"success": True, "message": f"Closed {display}.",
                     "capability_closed": True, "capability_name": display},
                    start_time,
                )
    except Exception as exc:
        logger.warning("[APP] web tab close via connector failed (2): %s", exc)

    # 3) Truthful failure — the target is a web app with no open tab. Do NOT
    #    claim success, do NOT refuse with ownership language, and NEVER
    #    escalate to the host browser process.
    return _normalize_public_result(
        "close", key,
        {"success": False, "message": f"Couldn't find {display} open in the browser.",
         "failure_class": "not_running"},
        start_time,
    )


def _find_existing_web_target(conn, url: str, friendly_name: str):
    """Return a truthy marker when an existing usable web target satisfies the
    same entity+modality request (duplicate prevention).

    Checks (1) the capability registry for an ACTIVE session with the same
    canonical target, then (2) live connector tabs whose URL or title matches.
    Returns None when no existing target is found — the caller then opens a new
    one. Identity is canonical (same entity + same web modality), never a raw
    string match against "chrome".
    """
    try:
        from mini_kio.core.capability_registry import get_capability_registry
        entry = get_capability_registry().resolve_by_target(friendly_name)
        if entry is not None and getattr(entry, "active", True):
            return entry
    except Exception:
        pass
    if conn is None:
        return None
    try:
        from mini_kio.core.async_utils import safe_run_async
        tabs_result = safe_run_async(conn.list_tabs())
        if not getattr(tabs_result, "success", False):
            return None
        tabs = getattr(tabs_result, "tabs", None) or []
        url_norm = (url or "").rstrip("/").lower()
        fname = (friendly_name or "").lower()
        for t in tabs:
            t_url = ((getattr(t, "url", "") or "") or "").rstrip("/").lower()
            t_title = (getattr(t, "title", "") or "").lower()
            if url_norm and (url_norm in t_url or t_url in url_norm):
                return t
            if fname and len(fname) >= 3 and (fname in t_title or fname in t_url):
                return t
    except Exception:
        pass
    return None


def _count_web_tabs(conn, url: str, friendly_name: str) -> Optional[int]:
    """Count live tabs matching the web target (URL or entity identity).

    Single bounded list_tabs call; None when the count cannot be determined
    (connector unreadable) so callers can skip count-based verification without
    inventing evidence.
    """
    try:
        from mini_kio.core.async_utils import safe_run_async
        tabs_result = safe_run_async(conn.list_tabs())
        if not getattr(tabs_result, "success", False):
            return None
        tabs = getattr(tabs_result, "tabs", None) or []
        url_norm = (url or "").rstrip("/").lower()
        fname = (friendly_name or "").lower()
        count = 0
        for t in tabs:
            t_url = ((getattr(t, "url", "") or "") or "").rstrip("/").lower()
            t_title = (getattr(t, "title", "") or "").lower()
            if url_norm and (url_norm in t_url or t_url in url_norm):
                count += 1
            elif fname and len(fname) >= 3 and (fname in t_title or fname in t_url):
                count += 1
        return count
    except Exception as exc:
        logger.debug("[APP] tab count unavailable: %s", exc)
        return None


def _verify_web_tab_opened(conn, url: str, friendly_name: str, before_count: Optional[int] = None) -> bool:
    """Bounded tab-identity verification after opening a web URL (BC-4).

    The connector ACK proves the extension received the open; this strengthens
    success by confirming a tab whose URL/title matches actually exists. Single
    bounded list_tabs call — never a polling loop.

    before_count (explicit additional-instance requests only): when the number
    of matching tabs was sampled BEFORE the open, require the count to have
    increased by exactly one — a genuine new tab was created, not a refresh/
    reuse of the existing one.
    """
    try:
        from mini_kio.core.async_utils import safe_run_async
        tabs_result = safe_run_async(conn.list_tabs())
        if not getattr(tabs_result, "success", False):
            return False
        tabs = getattr(tabs_result, "tabs", None) or []
        url_norm = (url or "").rstrip("/").lower()
        fname = (friendly_name or "").lower()
        count = 0
        for t in tabs:
            t_url = ((getattr(t, "url", "") or "") or "").rstrip("/").lower()
            t_title = (getattr(t, "title", "") or "").lower()
            if url_norm and (url_norm in t_url or t_url in url_norm):
                count += 1
            elif fname and (fname in t_title or fname in t_url):
                count += 1
        if before_count is not None:
            # Exactly one more matching tab than before the open proves a
            # fresh tab was created (never a refresh of the existing one).
            return count == before_count + 1
        return count > 0
    except Exception as exc:
        logger.debug("[APP] tab-identity verification unavailable: %s", exc)
        return False


def _visible_browser_window_count(proc_name: str) -> int:
    """Count visible top-level windows owned by the given browser process name.

    Chrome/Edge/Firefox attach every window to ONE browser process, so a new
    window is visible only as an extra top-level HWND — never as an extra PID.
    Returns -1 when the platform cannot verify (callers must then avoid
    claiming a new window). Bounded: one EnumWindows pass, no polling here.
    """
    if not _IS_WINDOWS or not proc_name:
        return -1
    try:
        import psutil
        from ctypes import wintypes
        user32 = ctypes.windll.user32
        owned: set[int] = set()
        for p in psutil.process_iter(["pid", "name"]):
            try:
                if p.info["name"] and p.info["name"].lower() == proc_name.lower():
                    owned.add(p.info["pid"])
            except (psutil.NoSuchProcess, psutil.AccessDenied):
                continue
        if not owned:
            return 0
        count = 0
        EnumWindowsProc = ctypes.WINFUNCTYPE(
            ctypes.c_bool, wintypes.HWND, wintypes.LPARAM
        )

        def _cb(hwnd, _lparam):
            nonlocal count
            if not user32.IsWindowVisible(hwnd):
                return True
            pid = wintypes.DWORD()
            user32.GetWindowThreadProcessId(hwnd, ctypes.byref(pid))
            if pid.value in owned:
                count += 1
            return True

        user32.EnumWindows(EnumWindowsProc(_cb), 0)
        return count
    except Exception:
        return -1


# System/shell/security binaries that must NEVER be terminated by the
# close-all-applications scope. Same filtering philosophy as the desktop
# observation layer plus the restricted-target gate. Browsers ARE user
# applications and are included in the close scope; system chrome is not.
def _close_all_forbidden_exes() -> frozenset[str]:
    from mini_kio.core.desktop_state import _SYSTEM_SHELL_EXES, _SKIP_WRAPPER_EXES
    # Case-normalized to lowercase: window observation lowercases process image
    # names ("windowsterminal.exe"), so a mixed-case entry like
    # "WindowsTerminal.exe" would never match and the shell could be
    # terminated (live-found: close-all closed the terminal while explorer.exe
    # survived). Lowercasing every entry makes the protection deterministic
    # for explorer.exe and every other system shell.
    return frozenset(f.lower() for f in (
        _SYSTEM_SHELL_EXES | _SKIP_WRAPPER_EXES | frozenset({
            "winlogon.exe", "csrss.exe", "lsass.exe", "services.exe", "smss.exe",
            "svchost.exe", "fontdrvhost.exe", "dwm.exe", "wininit.exe",
            "MsMpEng.exe", "NisSrv.exe", "SecurityHealthService.exe",
            "WdNisSvc.exe", "MsSense.exe",
        })
    ))


def _fmt_close_all_names(names: list[str]) -> str:
    """['A', 'B', 'C'] -> 'A, B, and C'; ['A', 'B'] -> 'A and B'."""
    if not names:
        return ""
    if len(names) == 1:
        return names[0]
    if len(names) == 2:
        return f"{names[0]} and {names[1]}"
    return ", ".join(names[:-1]) + f", and {names[-1]}"


def close_all_user_apps() -> dict:
    """Close every user-session application currently showing a window.

    Semantic representation: CLOSE / SCOPE=ALL_APPLICATIONS (current user
    session). Implemented generically on the existing desktop-observation
    and application-control architecture — never routed through browser
    discovery, never a blind system-wide process sweep.

    Safety: Windows system processes, services, shell components, drivers,
    security software and KIO itself (including KIO's own child processes)
    are never terminated. After the close pass the desktop is re-observed
    and the report is truthful: exactly what closed, what couldn't close,
    and what remains open.
    """
    from mini_kio.core.desktop_state import observe_native_windows

    # 1. Observe the desktop: visible user-app windows with owning pids.
    windows, ok = observe_native_windows()
    if not ok:
        return {"success": False, "message": "I couldn't read the desktop to close applications."}
    if not windows:
        return {"success": True, "message": "Nothing was open to close.", "closed": [], "remaining": []}

    forbidden = _close_all_forbidden_exes()
    self_pid = os.getpid()
    # KIO's own process family (the bot, MCP server children) must survive.
    kio_family: set[int] = {self_pid}
    try:
        import psutil
        proc = psutil.Process(self_pid)
        kio_family |= {c.pid for c in proc.children(recursive=True)}
    except Exception:
        pass

    targets: dict[int, str] = {}  # pid -> app display name (dedupe by pid)
    for w in windows:
        pid = int(w.get("pid", 0) or 0)
        base = str(w.get("base") or "").lower()
        if pid <= 0 or pid in kio_family:
            continue
        # EXPLORER SHELL GUARD (user directive, 2026-08-12): File Explorer
        # (explorer.exe) is the Windows desktop shell and must NEVER be
        # targeted by close-all — even as a fallback for an unrecognized
        # variant. Belt-and-suspenders on top of the case-normalized shell
        # set and the restricted-target gate below.
        if base == "explorer":
            continue
        if base and (base + ".exe") in forbidden:
            continue
        if base and base in _RESTRICTED_CANONICAL_TARGETS:
            continue
        targets.setdefault(pid, str(w.get("app") or w.get("base") or "Application"))

    if not targets:
        return {"success": True, "message": "Nothing open that I should close.", "closed": [], "remaining": []}

    # 2. Close each target at its own application scope (graceful-first,
    #    verified — the same canonical owner a single close uses).
    closed: list[str] = []
    failed: list[str] = []
    for pid, app in targets.items():
        try:
            result = close_app(app, pid=pid)
            if result.get("success"):
                closed.append(app)
            else:
                failed.append(app)
        except Exception as exc:
            logger.warning("[APP] close-all step failed for %s (%s): %s", app, pid, exc)
            failed.append(app)

    # 3. Re-observe and report truthfully: what actually closed vs remains.
    remaining: list[str] = []
    windows2, ok2 = observe_native_windows()
    if ok2:
        seen: set[int] = set()
        for w in windows2:
            pid = int(w.get("pid", 0) or 0)
            if pid in seen or pid <= 0 or pid in kio_family:
                continue
            base = str(w.get("base") or "").lower()
            # Same shell/explorer guards as the close pass — explorer.exe must
            # never surface as "closed" or as a targetable leftover.
            if base == "explorer":
                continue
            if base and (base + ".exe") in forbidden:
                continue
            if base and base in _RESTRICTED_CANONICAL_TARGETS:
                continue
            seen.add(pid)
            remaining.append(str(w.get("app") or w.get("base") or "Application"))

    parts: list[str] = []
    if closed:
        parts.append("Closed " + _fmt_close_all_names(closed) + ".")
    if failed:
        parts.append("Couldn't close " + _fmt_close_all_names(failed) + ".")
    if remaining:
        parts.append("Still open: " + _fmt_close_all_names(remaining) + ".")
    message = " ".join(parts) if parts else "Done."
    return {
        "success": not failed,
        "message": message,
        "closed": closed,
        "failed": failed,
        "remaining": remaining,
    }


def close_app(name: str, pid: Optional[int] = None) -> dict:
    """Kill an application.  Returns {"success": bool, "message": str}."""
    key = name.lower().strip()
    start_time = time.time()
    logger.info(f"[APP] close_app: {key!r} (pid override: {pid})")

    # ── BC-1/BC-2: TAB-SCOPE close for capability-serialized / web-app targets ──
    # A serialized capability target ("chrome::open_url::https://...::chatgpt")
    # or a plain web-app name ("chatgpt", "telegram" when no native app is
    # registered) is a BROWSER TAB/SESSION, not a host browser process. It must
    # NEVER be collapsed into the browser process and killed (that was the
    # "Close it closed all of Chrome" bug). Route it to the web-target close
    # path which closes at TAB scope with a bounded fallback and truthful
    # failure when no tab exists.
    from mini_kio.core.target_ref import parse_target, safe_target_name
    _ref = parse_target(key)
    _info = _find_in_registry(key)
    _is_web_scope = ("::" in key) or (_ref.kind in ("webapp", "tab") and not _info)
    if _is_web_scope:
        return _close_web_target(name, key, start_time)

    info = _find_in_registry(key)
    canonical = key
    if info:
        for registry_key, registry_info in APP_REGISTRY.items():
            if registry_info is info:
                canonical = registry_key
                break

    norm_canonical = canonical[:-4] if canonical.endswith(".exe") else canonical
    if norm_canonical in _RESTRICTED_CANONICAL_TARGETS:
        return _normalize_public_result(
            "close",
            canonical,
            {
                "success": False,
                "message": f"{name} is restricted for safety." if canonical != "explorer" else "Explorer shell control is restricted for safety.",
                "pid": None,
                "failure_class": "restricted_shell_control" if canonical == "explorer" else "restricted_target",
            },
            start_time,
        )

    if not _IS_WINDOWS:
        return _normalize_public_result("close", key, _pkill(key), start_time)

    # Priority 1: Targeted PID termination (Tree-Aware)
    if pid is not None:
        try:
            import psutil
            try:
                p = psutil.Process(pid)
                if p.name().lower() == "applicationframehost.exe":
                    return _normalize_public_result("close", key, {"success": False, "message": f"Refusing to kill UWP wrapper (ApplicationFrameHost). Close the app manually if needed."}, start_time)
            except (psutil.NoSuchProcess, psutil.AccessDenied):
                pass

            termination = _terminate_with_verification(name, key, pid, info)
            if termination.get("verified_terminated"):
                _graceful_uwp_close(pid, name)
            
            # Prune from runtime registry
            try:
                from mini_kio.core.runtime import get_runtime
                rt = get_runtime()
                if rt:
                    rt.unregister_tracked_process(canonical, pid=pid)
            except Exception:
                pass
                
            return _normalize_public_result("close", key, termination, start_time)

        except subprocess.TimeoutExpired:
            return _normalize_public_result("close", key, {"success": False, "message": f"Timeout closing {name} (pid {pid})", "pid": pid}, start_time)
        except Exception as exc:
            logger.error(f"[APP] Error closing pid {pid}: {exc}")
            return _normalize_public_result("close", key, {"success": False, "message": f"Error closing {name}: {exc}", "pid": pid}, start_time)

    # Phase 2: STRICT Ownership lookup via Runtime Registry
    # No wildcard fallback (/IM) for non-system apps to respect ownership isolation.
    # No recovery lookup using psutil.process_iter — only close what KIO opened.
    try:
        from mini_kio.core.runtime import get_runtime
        rt = get_runtime()
        if rt:
            tracked = rt.get_tracked_process(canonical)
            if tracked and isinstance(tracked.get("pid"), int):
                tracked_pid = int(tracked["pid"])
                logger.info(f"[APP] close_app using tracked pid {tracked_pid} for {key}")
                return close_app(name, pid=tracked_pid)
    except Exception:
        pass

    # Generic process-discovery fallback (BUG 6): ANY registered app — browser
    # or not — may be running without a KIO-tracked PID (opened manually, by
    # another tool, or a singleton that outlived its tracker entry). The user
    # explicitly asked to close it, so discover the matching process by the
    # registry's own process names (helper-safe: browser helpers carry a
    # --type= marker and are skipped; UWP wrappers are excluded) and terminate
    # it with tree-aware verification. Restricted targets are already gated
    # above; UNREGISTERED apps keep the strict ownership refusal so KIO never
    # blind-kills an arbitrary process it does not model.
    if info:
        discovered_pid = _find_matching_process_pid(key, info)
        if discovered_pid is not None:
            logger.info("[APP] close_app process-discovery fallback: discovered %s pid=%d", key, discovered_pid)
            return close_app(name, pid=discovered_pid)
        # Registered app, no matching NATIVE process. If this name ALSO has a
        # legitimate web version (dual-modality, e.g. Telegram) that KIO may
        # have opened through the disclosed web fallback, the close must
        # resolve to the WEB TARGET — never a false "wasn't running" while a
        # web session exists. _close_web_target truthfully reports "not open
        # in the browser" when no such session exists.
        #
        # MODALITY CONSISTENCY: mirror launch_app's fallback rules exactly.
        #   - INSTALLED registered app (path/URI/system/UWP resolves): launch
        #     only ever fell back to a KNOWN web version (launch_failed uses
        #     allow_synthesis=False) — so close checks known web versions only.
        #     A synthesized <name>.com (vlc.com, vscode.com) is NOT a web
        #     version launch would have opened for an installed native app.
        #   - NOT-installed registered name: launch may have opened the
        #     disclosed not-found fallback (which may synthesize .com) — so
        #     close must resolve to that same web scope.
        installed = bool(
            info.get("uri") or info.get("system") or info.get("uwp_packages")
            or _resolve_path(info) is not None
        )
        if _web_fallback_url(key, allow_synthesis=not installed) is not None:
            logger.info("[APP] close_app dual-modality web scope: %s", key)
            return _close_web_target(name, key, start_time)
        # Registered app, no matching process anywhere -> it is simply not
        # running. Report that truthfully instead of claiming ownership
        # refusal (which would be misleading) or a false close.
        logger.info("[APP] close_not_running target=%s", key)
        return _normalize_public_result(
            "close",
            key,
            {
                "success": False,
                "message": f"{name} wasn't running.",
                "pid": None,
                "failure_class": "not_running",
            },
            start_time,
        )

    # Generic discovered-app fallback (Part IV): an application KIO launched
    # through generic installed-app discovery (no APP_REGISTRY entry) must still
    # be closable at its own scope. The runtime registration from
    # _launch_discovered already covers tracked pids; this covers apps whose
    # tracked entry was lost (e.g. process restart) by matching the discovered
    # executable name — never a blind system-wide sweep, never the browser host.
    #
    # Both discovery kinds are handled: exe paths AND Start Menu shortcuts
    # (shortcut-installed apps like Cursor must close at native scope, never
    # fall through to a synthesized <name>.com web scope).
    try:
        from mini_kio.core.runtime import get_runtime
        rt = get_runtime()
        if rt:
            tracked = rt.get_tracked_process(key)
            if tracked and isinstance(tracked.get("pid"), int):
                return close_app(name, pid=int(tracked["pid"]))
        discovered = _find_installed_app(key)
        if discovered:
            # UWP/Store apps (Camera, Photos, ...) run under their REAL image
            # name (WindowsCamera.exe), never the AUMID. Match running image
            # names by the request key (bounded containment, >=4 chars, same
            # guard as generic discovery; ApplicationFrameHost wrapper excluded)
            # so "close the camera" actually closes the running camera.
            if discovered.get("kind") == "uwp":
                import psutil as _psutil
                norm_key = re.sub(r"[^a-z0-9]", "", key.lower())
                for _proc in _psutil.process_iter(["pid", "name"]):
                    try:
                        _img = re.sub(
                            r"[^a-z0-9]", "",
                            (_proc.info.get("name") or "").lower(),
                        )
                        # Empty/unreadable image names must NEVER match ("" is a
                        # substring of every key — that made the close target an
                        # unrelated elevated process instead of the camera).
                        if not _img or len(_img) < 4:
                            continue
                        if _img in ("applicationframehost", "dllhost", "explorer"):
                            continue
                        # Request name must be contained IN the image name
                        # ("camera" -> windowscamera.exe): only the real app
                        # process matches, never an unrelated short-name
                        # process the request name merely contains.
                        if len(norm_key) >= 4 and norm_key in _img:
                            logger.info("[APP] close_app UWP fallback: %s pid=%d", key, _proc.info["pid"])
                            return close_app(name, pid=int(_proc.info["pid"]))
                    except (_psutil.NoSuchProcess, _psutil.AccessDenied):
                        continue
            exe_base = Path(discovered["target"]).stem.lower()
            pseudo_info = {"lifecycle": "standard", "process": exe_base + ".exe"}
            discovered_pid = _find_matching_process_pid(key, pseudo_info)
            if discovered_pid is not None:
                logger.info("[APP] close_app discovered-app fallback: %s pid=%d", key, discovered_pid)
                return close_app(name, pid=discovered_pid)
            # Native app IS installed but not running — report that truthfully
            # at native scope. A disclosed web fallback only ever opens when
            # the native app is absent, so an installed app must NOT fall
            # through to a synthesized web scope ("close cursor" after
            # "open cursor" must never become a cursor.com browser close).
            logger.info("[APP] close_app discovered-not-running target=%s", key)
            return _normalize_public_result(
                "close",
                key,
                {
                    "success": False,
                    "message": f"{name} wasn't running.",
                    "pid": None,
                    "failure_class": "not_running",
                },
                start_time,
            )
    except Exception:
        pass

    # Web-fallback modality consistency: when the native application was never
    # found but a legitimate web version exists (the same disclosed fallback
    # launch_app uses), "Close it" must resolve to the WEB TARGET at tab scope
    # — never an ownership refusal ("I didn't open it"), never a process kill.
    try:
        if _web_fallback_url(key) is not None:
            logger.info("[APP] close_app web-fallback scope: %s", key)
            return _close_web_target(name, key, start_time)
    except Exception:
        pass

    # No ownership found -> Refuse to close arbitrary processes
    logger.info("[APP] close_refused target=%s reason=not_tracked", key)
    return _normalize_public_result(
        "close",
        key,
        {
            "success": False,
            "message": f"I didn't open {name}, so I can't close it for you.",
            "pid": None,
            "failure_class": "not_tracked",
        },
        start_time,
    )


def _register_browser_session(action: str, url: str) -> None:
    """Register a lightweight session record for a browser_operator action."""
    try:
        from mini_kio.core.routing_utils import get_browser_registry
        get_browser_registry().create_session(action, url)
    except Exception as exc:
        logger.warning("[BROWSER_SESSION] Registration error: %s", exc)


def _safe_webbrowser_open(url: str) -> bool:
    if os.environ.get("KIO_TEST_MODE") == "1":
        logger.info("[TEST MODE] Blocked webbrowser.open(%s)", url)
        return True
    from mini_kio.core.command_router import _get_connector
    from mini_kio.core.async_utils import safe_run_async
    conn = _get_connector()
    if conn:
        try:
            result = safe_run_async(conn.open_tab(url))
            if getattr(result, "success", False):
                return True
            logger.debug("[CONNECTOR] open_tab failed or reported failure, falling back to system browser: %s", result)
        except Exception as exc:
            logger.debug("[CONNECTOR] open_tab failed, falling back to system browser: %s", exc)
    else:
        if config.BROWSER_CONNECTOR_ENABLED:
            logger.debug("[CONNECTOR] connector configured but unavailable, falling back to system browser")
    return webbrowser.open(url)


def search_web(query: str) -> dict:
    """Open a Google search.  Returns {"success": bool, "message": str}."""
    start_time = time.time()
    if not query:
        return _normalize_public_result("search", query or "", {"success": False, "message": "No search query"}, start_time)
    encoded = urllib.parse.quote_plus(query)
    url = f"https://www.google.com/search?q={encoded}"
    try:
        _safe_webbrowser_open(url)
        logger.info(f"[APP] search: {query!r}")
        _register_browser_session("search_web", url)
        return _normalize_public_result("search", query, {"success": True, "message": f"Searched: {query}"}, start_time)
    except Exception as exc:
        return _normalize_public_result("search", query, {"success": False, "message": f"Search failed: {str(exc)[:80]}"}, start_time)


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
        _safe_webbrowser_open(url)
        _register_browser_session("open_url", url)
        # Use "Launched" for URIs without PID tracking; request noop verification
        return {"success": True, "message": f"Launched {label} in browser.", "verification_mode": "noop"}
    except Exception as exc:
        return {"success": False, "message": f"Failed to open {label}: {str(exc)[:80]}"}


def _contains_forbidden_web_chars(value: str) -> bool:
    return any(c in value for c in [' ', '&', '|', ';', '$', '(', ')', '`', '\\', '\0', '\n', '\r', '\t'])


def _contains_dangerous_web_chars(value: str) -> bool:
    """True for shell/URL-injection characters but NOT spaces — spaces are a
    legitimate multi-word input for verified brand-domain synthesis
    ("stack overflow" -> stackoverflow.com)."""
    return any(c in value for c in ['&', '|', ';', '$', '(', ')', '`', '\\', '\0', '\n', '\r', '\t'])


def _is_registry_alias(key: str) -> bool:
    if key in APP_REGISTRY:
        return True
    for info in APP_REGISTRY.values():
        if key in info.get("aliases", []):
            return True
    return False


def _is_internal_or_local_web_target(value: str) -> bool:
    normalized = value.lower().strip()
    if not normalized:
        return False
    if normalized == "::1":
        return True

    host = normalized
    if "/" in host:
        host = host.split("/", 1)[0]
    if host.startswith("localhost:"):
        return True
    if host == "localhost" or host.endswith(".localhost"):
        return True
    if host.startswith("127."):
        return True
    if host.startswith("10."):
        return True
    if host.startswith("192.168."):
        return True
    if host.startswith("169.254."):
        return True
    return False


def _can_synthesize_single_label_domain(label: str) -> bool:
    normalized = label.lower().strip()
    if not normalized or not normalized.isascii():
        return False
    if normalized in _RESERVED_SYNTHETIC_WEB_LABELS:
        return False
    if _is_registry_alias(normalized) or _is_internal_or_local_web_target(normalized):
        return False
    return bool(_SAFE_SYNTHETIC_DOMAIN_LABEL_RE.fullmatch(normalized))


def _explicit_web_url_for_open(name: str) -> Optional[str]:
    """Resolve the web target for an EXPLICIT web-intent open request.

    "open X in Chrome" / "open X on the web" / "open X website" explicitly
    ask for the web version of X. Unlike default opens (native-first), the
    registry-alias guard must NOT block single-word <name>.com synthesis
    here: the user explicitly requested the website even when a native app
    exists. Known web aliases, explicit URLs, dotted domains and reserved/
    internal-host guards still apply.
    """
    normalized = " ".join((name or "").lower().strip().split())
    if not normalized:
        return None
    if normalized in WEB_URLS:
        return WEB_URLS[normalized]
    if normalized in WEB_DOMAIN_ALIASES:
        return WEB_DOMAIN_ALIASES[normalized]
    if normalized.startswith(("http://", "https://")):
        return normalized
    if _SAFE_EXPLICIT_DOMAIN_RE.fullmatch(normalized):
        parts = normalized.split(".")
        if len(parts) >= 2 and parts[-1] in _ALLOWED_WEB_TLDS:
            return f"https://{normalized}"
        return None
    # Multi-word domain inference ("stack overflow" -> stackoverflow.com)
    # only for 2-3 word site-like names, never search queries. Must run
    # BEFORE the forbidden-char check (which rejects spaces).
    if " " in normalized:
        parts = normalized.split()
        if 2 <= len(parts) <= 3:
            _SEARCH_INDICATORS = {
                "best", "top", "latest", "near", "under", "cheap",
                "who", "what", "where", "when", "why", "how",
                "in", "on", "at", "for", "with", "by", "to", "of",
                "some", "thing", "something", "anything",
            }
            if not (set(parts) & _SEARCH_INDICATORS):
                collapsed = normalized.replace(" ", "")
                if _SAFE_SYNTHETIC_DOMAIN_LABEL_RE.fullmatch(collapsed) \
                   and collapsed not in _RESERVED_SYNTHETIC_WEB_LABELS:
                    return f"https://{collapsed}.com"
        return None
    if _contains_forbidden_web_chars(normalized) or _is_internal_or_local_web_target(normalized):
        return None
    if (
        "://" in normalized
        or ".." in normalized
        or "//" in normalized
        or normalized.startswith((".", "/"))
    ):
        return None
    # Explicit web intent: single-word <name>.com synthesis is permitted even
    # for registry aliases (installed native apps) — the user asked for the
    # website. Reserved labels and internal hosts remain blocked above.
    if _SAFE_SYNTHETIC_DOMAIN_LABEL_RE.fullmatch(normalized) \
       and normalized not in _RESERVED_SYNTHETIC_WEB_LABELS:
        return f"https://{normalized}.com"
    return None


def _normalize_web_target_to_url(target: str) -> Optional[str]:
    normalized = " ".join(target.lower().strip().split())
    if not normalized:
        return None
    if normalized in WEB_URLS:
        return WEB_URLS[normalized]
    if normalized in WEB_DOMAIN_ALIASES:
        return WEB_DOMAIN_ALIASES[normalized]

    # Multi-word domain inference: "stack overflow" → "stackoverflow.com"
    # Must happen before forbidden-char check (which rejects spaces).
    # Only collapses 2-3 word targets that look like site names,
    # NOT search queries (4+ words, or 3 words with question/preposition words).
    if " " in normalized:
        parts = normalized.split()
        word_count = len(parts)
        # Never collapse 4+ word targets — they are search queries
        if 2 <= word_count <= 3:
            # Skip if any word is a search/query indicator
            _SEARCH_INDICATORS = {
                "best", "top", "latest", "near", "under", "cheap",
                "who", "what", "where", "when", "why", "how",
                "in", "on", "at", "for", "with", "by", "to", "of",
                "some", "thing", "something", "anything",
            }
            if not (set(parts) & _SEARCH_INDICATORS):
                collapsed = normalized.replace(" ", "")
                if _can_synthesize_single_label_domain(collapsed):
                    url = f"https://{collapsed}.com"
                    if not _contains_forbidden_web_chars(collapsed) and \
                       not _is_internal_or_local_web_target(collapsed):
                        return url

    if _contains_forbidden_web_chars(normalized):
        return None
    if _is_internal_or_local_web_target(normalized):
        return None

    if normalized.startswith(("http://", "https://")):
        return normalized
    if (
        "://" in normalized
        or ".." in normalized
        or "//" in normalized
        or normalized.startswith((".", "/"))
    ):
        return None
    if _can_synthesize_single_label_domain(normalized):
        return f"https://{normalized}.com"
    if _SAFE_EXPLICIT_DOMAIN_RE.fullmatch(normalized):
        domain_parts = normalized.split(".")
        if len(domain_parts) >= 2 and domain_parts[-1] in _ALLOWED_WEB_TLDS:
            return f"https://{normalized}"
        return None
    if normalized.count("/") != 1 or normalized.endswith("/"):
        return None

    domain_candidate, path = normalized.split("/", 1)
    if (
        not domain_candidate
        or not path
        or _is_internal_or_local_web_target(domain_candidate)
        or not _SAFE_SINGLE_PATH_SEGMENT_RE.fullmatch(path)
    ):
        return None
    if path in _ALLOWED_WEB_TLDS and _can_synthesize_single_label_domain(domain_candidate):
        return None

    base_url: Optional[str] = None
    if domain_candidate in WEB_URLS:
        base_url = WEB_URLS[domain_candidate]
    elif domain_candidate in WEB_DOMAIN_ALIASES:
        base_url = WEB_DOMAIN_ALIASES[domain_candidate]
    elif _SAFE_EXPLICIT_DOMAIN_RE.fullmatch(domain_candidate):
        domain_parts = domain_candidate.split(".")
        if len(domain_parts) >= 2 and domain_parts[-1] in _ALLOWED_WEB_TLDS:
            base_url = f"https://{domain_candidate}"
    elif _can_synthesize_single_label_domain(domain_candidate):
        base_url = f"https://{domain_candidate}.com"

    if base_url is None:
        return None
    return f"{base_url.rstrip('/')}/{path}"


def _matching_process_names(key: str, info: Optional[Dict]) -> set[str]:
    names: set[str] = set()
    if info:
        proc_name = str(info.get("process") or "").lower()
        if proc_name:
            names.add(proc_name if proc_name.endswith(".exe") else f"{proc_name}.exe")
        for package_name in info.get("uwp_packages", []):
            normalized = str(package_name).lower()
            if normalized:
                names.add(normalized if normalized.endswith(".exe") else f"{normalized}.exe")
        if info.get("lifecycle") == "uwp":
            names.discard("applicationframehost.exe")
    if not names and key:
        names.add(key if key.endswith(".exe") else f"{key}.exe")
    return names


def _find_matching_process_pid(key: str, info: Optional[Dict], *, exclude: set[int] | None = None) -> Optional[int]:
    if not _IS_WINDOWS:
        return None
    exclude = exclude or set()
    names = _matching_process_names(key, info)
    try:
        import psutil

        # PERFORMANCE (system-level): the base scan must NOT fetch 'cmdline'
        # for every process. psutil.process_iter with cmdline costs ~1s on a
        # busy desktop vs ~0.01s without; cmdline is only needed for browser
        # helper-root detection, which happens per-pid lazily below
        # (_proc_is_browser_helper fetches it on demand). This single change
        # removes the shared open/close/verify latency bottleneck.
        matches: list[tuple[float, int]] = []
        for proc in psutil.process_iter(['pid', 'name', 'create_time']):
            try:
                proc_name = (proc.info.get("name") or "").lower()
                if proc.info['pid'] in exclude or proc_name not in names:
                    continue
                matches.append((float(proc.info.get("create_time") or 0.0), int(proc.info['pid'])))
            except (psutil.NoSuchProcess, psutil.AccessDenied, ValueError):
                continue
        if not matches:
            return None
        matches.sort()
        # Browser lifecycle: helpers (renderers, gpu, utility) share the image
        # name and vastly outnumber the root process. Picking the newest match
        # would terminate a child and leave the browser running. Prefer the
        # interactive root: the process whose command line has no --type= child
        # marker and which owns a visible main window (headless instances and
        # helper roots have none).
        if info and info.get("lifecycle") == "browser":
            windowed_root: Optional[int] = None
            bare_root: Optional[int] = None
            for create_time, proc_pid in reversed(matches):
                if _proc_is_browser_helper(proc_pid):
                    continue
                if bare_root is None:
                    bare_root = proc_pid
                if _proc_has_main_window(proc_pid):
                    windowed_root = proc_pid
                    break
            if windowed_root is not None:
                return windowed_root
            if bare_root is not None:
                return bare_root
        return matches[-1][1]
    except Exception:
        return None


def _proc_is_browser_helper(pid: int) -> bool:
    """True if the given pid is a browser helper (has a --type= marker)."""
    try:
        import psutil
        proc = psutil.Process(pid)
        cmdline = proc.cmdline() or []
        return any(str(a).startswith("--type=") for a in cmdline)
    except Exception:
        return False


def _proc_has_main_window(pid: int) -> bool:
    """True if the given pid owns at least one visible top-level window."""
    if not _IS_WINDOWS:
        return False
    try:
        import ctypes
        from ctypes import wintypes

        user32 = ctypes.windll.user32
        found = []

        @ctypes.WINFUNCTYPE(wintypes.BOOL, wintypes.HWND, wintypes.LPARAM)
        def _enum_cb(hwnd, _lparam):
            window_pid = wintypes.DWORD()
            user32.GetWindowThreadProcessId(hwnd, ctypes.byref(window_pid))
            if window_pid.value == pid and user32.IsWindowVisible(hwnd):
                found.append(True)
                return False
            return True

        user32.EnumWindows(_enum_cb, 0)
        return bool(found)
    except Exception:
        return False


def _pid_is_alive(pid: Optional[int]) -> bool:
    if pid is None:
        return False
    try:
        import psutil

        proc = psutil.Process(int(pid))
        return proc.is_running() and proc.status() != psutil.STATUS_ZOMBIE
    except (psutil.NoSuchProcess, psutil.AccessDenied, ValueError):
        return False


def _verification_residual_pid(target_pid: Optional[int], key: str, info: Optional[Dict]) -> Optional[int]:
    if _pid_is_alive(target_pid):
        return int(target_pid)
    exclude = {int(target_pid)} if isinstance(target_pid, int) else set()
    return _find_matching_process_pid(key, info, exclude=exclude)


def _wait_for_termination_verification(target_pid: Optional[int], key: str, info: Optional[Dict], *, attempts: int) -> Optional[int]:
    for _ in range(attempts):
        residual_pid = _verification_residual_pid(target_pid, key, info)
        if residual_pid is None:
            return None
        time.sleep(0.4)
    return _verification_residual_pid(target_pid, key, info)


def _run_taskkill(pid: int, *, force: bool) -> subprocess.CompletedProcess[str]:
    cmd = ["taskkill"]
    if force:
        cmd.append("/F")
    cmd.extend(["/T", "/PID", str(pid)])
    return subprocess.run(cmd, capture_output=True, text=True, timeout=6)


def _terminate_with_verification(name: str, key: str, pid: int, info: Optional[Dict]) -> dict:
    graceful_result = _run_taskkill(pid, force=False)
    residual_pid = _wait_for_termination_verification(pid, key, info, attempts=4)

    force_attempted = False
    terminated_pid = pid
    lifecycle = str(info.get("lifecycle") if info else "")
    if residual_pid is not None:
        force_attempted = True
        terminated_pid = residual_pid
        logger.info(f"[APP] residual detected after graceful close for {key}; forcing pid {residual_pid}")
        _run_taskkill(residual_pid, force=True)
        residual_pid = _wait_for_termination_verification(residual_pid, key, info, attempts=3)
        if residual_pid is not None and lifecycle == "browser":
            time.sleep(0.8)
            residual_pid = _verification_residual_pid(residual_pid, key, info)

    # BUG 7: outcome classes. The message must never contradict the structured
    # outcome ("Closed X. ... but helper processes may persist" claimed success
    # while stating the close was incomplete). Implementation detail lives in
    # structured fields (outcome_class / verification_status / residual_pid);
    # the user-facing message is concise and truthful.
    if residual_pid is None:
        return {
            "success": True,
            "message": f"Closed {name}.",
            "pid": pid,
            "primary_termination_attempted": True,
            "force_kill_attempted": force_attempted,
            "verified_terminated": True,
            "verification_status": "passed",
            "outcome_class": "SUCCESS",
            "failure_class": "",
        }

    stderr_lower = (graceful_result.stderr or "").lower()
    if "not found" in stderr_lower or "not running" in stderr_lower:
        return {
            "success": False,
            "message": f"{name} wasn't running.",
            "pid": pid,
            "primary_termination_attempted": True,
            "force_kill_attempted": force_attempted,
            "verified_terminated": False,
            "verification_status": "not_running",
            "outcome_class": "NOT_RUNNING",
            "failure_class": "not_running",
        }

    # Primary process (and its verified tree) is gone but same-family processes
    # remain (browser helpers, UWP shell). This is a PARTIAL outcome: the app
    # the user asked to close is closed, but background components persist.
    return {
        "success": True,
        "message": f"Closed {name}.",
        "pid": pid,
        "residual_pid": residual_pid,
        "terminated_pid": terminated_pid,
        "primary_termination_attempted": True,
        "force_kill_attempted": force_attempted,
        "verified_terminated": False,
        "verification_status": "passed_with_residuals",
        "outcome_class": "SUCCESS_WITH_RESIDUALS",
        "failure_class": "residual_processes",
    }


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


def _verify_process_started_windows(proc_name: str, timeout_s: int = 1.5, uwp_packages: list[str] | None = None) -> bool:
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
        time.sleep(0.2)
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
            deadline = launch_start + 1.5
            
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

            deadline = launch_start + 1.5
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


def _launch_uri(uri: str, name: str, info: Dict) -> dict:
    """Launch a UWP app via protocol URI (e.g. ms-windows-store://home)."""
    launch_start = time.time()
    prior_pids: set[int] = set()
    proc_name = info.get("process") or ""
    uwp_packages = info.get("uwp_packages", [])
    lifecycle = info.get("lifecycle", "standard")
    try:
        import psutil
        target_names = {proc_name.lower()} if proc_name else set()
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
    pid = 0
    try:
        os.startfile(uri)
    except AttributeError:
        try:
            proc = subprocess.Popen(
                ["cmd", "/c", "start", "", uri],
                shell=False,
                creationflags=_creation_flags(),
                stdout=subprocess.DEVNULL,
                stderr=subprocess.DEVNULL,
            )
            pid = proc.pid
        except Exception as exc:
            return {"success": False, "message": f"Failed to open {name}: {str(exc)[:80]}"}
    except Exception as exc:
        return {"success": False, "message": f"Failed to open {name}: {str(exc)[:80]}"}

    if _IS_WINDOWS and proc_name:
        verified_started = _verify_process_started_windows(proc_name, timeout_s=2, uwp_packages=uwp_packages)
        latest_pid = _find_matching_process_pid(name.lower(), info, exclude=prior_pids)
        if verified_started and latest_pid is None:
            latest_pid = _find_matching_process_pid(name.lower(), info)
        if verified_started or latest_pid is not None:
            final_pid = latest_pid
            if final_pid is None:
                final_pid = _refine_pid_windows(pid, proc_name, prior_pids=prior_pids, launch_start=launch_start, uwp_packages=uwp_packages, lifecycle=lifecycle)
            if final_pid is None:
                return {"success": True, "message": f"Launched {name} (ownership not tracked)."}
            return {"success": True, "message": f"Opened {name}", "pid": final_pid}
        else:
            return {"success": False, "message": f"Failed to launch {name}.", "pid": pid}
    return {"success": True, "message": f"Opened {name}", "pid": pid}


def _activate_launched_window(pid: int) -> None:
    """Bring a freshly launched app's window to the SCREEN (never just the
    taskbar). Launching an exe opens the window in the background; without an
    explicit foreground activation the user only sees the taskbar flash.
    Bounded: one short wait + one activation attempt, never a polling loop.
    """
    if not _IS_WINDOWS or not pid:
        return
    try:
        time.sleep(0.3)
        from mini_kio.platform.window_activation import activate_window
        activate_window(int(pid))
    except Exception:
        pass


def _launch_from_info(info: Dict, name: str) -> dict:
    # URI-launched apps (e.g. Microsoft Store, Settings, Photos)
    uri = info.get("uri")
    if uri:
        return _launch_uri(uri, name, info)
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
                launch_cmd.extend([
                    "--no-first-run",
                    "--disable-extensions",
                ])
            except Exception as exc:
                logger.debug(f"[APP] unable to prepare chrome launch args: {exc}")

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
        logger.info(f"[APP] launched: {path} (initial pid: {pid})")

        # Lightweight verification: poll for process presence by image name
        proc_name = info.get("process") or Path(path).name
        uwp_packages = info.get("uwp_packages", [])
        lifecycle = info.get("lifecycle", "standard")
        
        # BROWSER LIFECYCLE (Gate 2.5 Stabilization): Browser launches are non-trackable
        res_extra = {}
        if lifecycle == "browser":
            res_extra["verification_mode"] = "noop"

        if _IS_WINDOWS:
            if _verify_process_started_windows(proc_name, timeout_s=2, uwp_packages=uwp_packages):
                # Refine PID to handle launchers/aliases
                final_pid = _refine_pid_windows(pid, proc_name, prior_pids=prior_pids, launch_start=launch_start, uwp_packages=uwp_packages, lifecycle=lifecycle)
                if final_pid is None:
                    logger.warning(f"[APP] Ownership refinement failed for: {proc_name}")
                    # Honest capability response: successful launch but untracked
                    out = {"success": True, "message": f"Launched {name} (ownership not tracked)."}
                    out.update(res_extra)
                    return out
                logger.info(f"[DEBUG_APP] final_pid refined: {final_pid}")
                out = {"success": True, "message": f"Opened {name}", "pid": final_pid}
                out.update(res_extra)
                _activate_launched_window(final_pid)
                return out
            else:
                logger.warning(f"[APP] launch verification failed for: {proc_name}")
                return {"success": False, "message": f"Failed to launch {name}.", "pid": pid}
        else:
            # Non-windows: best-effort via Popen status
            out = {"success": True, "message": f"Opened {name}", "pid": pid}
            out.update(res_extra)
            return out
    except FileNotFoundError:
        return {"success": False, "message": f"Cannot find {name}"}
    except Exception as exc:
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

    # Absolute last resort — launch by name (no verified path).
    # Use os.startfile on Windows (no visible console window) or direct
    # Popen with CREATE_NO_WINDOW.  The old "cmd /c start" always opened
    # a visible terminal window during normal Telegram operation.
    try:
        if _IS_WINDOWS:
            os.startfile(name)
        else:
            subprocess.Popen([name], shell=False)
        # Best-effort verification
        if _IS_WINDOWS and _verify_process_started_windows(f"{name}.exe", timeout_s=2):
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
            if _verify_process_started_windows(proc_name, timeout_s=2):
                final_pid = _refine_pid_windows(pid, proc_name)
                if final_pid is None:
                    # Honest capability response: successful launch but untracked
                    return {"success": True, "message": f"Launched {name} (ownership not tracked)."}
                _activate_launched_window(final_pid)
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
    # CREATE_NO_WINDOW prevents the child process from opening a visible
    # console window.  DETACHED_PROCESS (0x00000008) only detaches from the
    # parent console but still allows the child to create its own window —
    # which is the root cause of the unwanted terminal window during normal
    # Telegram operation.  CREATE_NO_WINDOW (0x08000000) suppresses it.
    return 0x08000000 if _IS_WINDOWS else 0  # CREATE_NO_WINDOW



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
    # ── Google cloud services (OAuth / API-key backed) ──
    "gmail":     ["list_messages", "get_message", "send_message", "search_messages",
                   "list_labels", "trash_message", "untrash_message", "modify_labels"],
    "calendar":  ["list_calendars", "list_events", "today_events", "upcoming_within",
                   "get_event", "create_event", "update_event", "delete_event", "search_events"],
    "drive":     ["list_files", "search_files", "get_metadata", "create_folder",
                   "upload_file", "download_file", "rename_file", "move_file", "delete_file"],
    "contacts":  ["list_contacts", "search_contacts", "get_contact",
                   "create_contact", "update_contact", "delete_contact"],
    "photos":    ["list_albums", "get_album", "create_album", "list_media",
                   "search_media", "get_media", "upload_media",
                   "create_picker_session", "list_picked_items"],
    # ── Workflow-declared capabilities routed through provider registry ──
    "browser":   ["fetch_region", "extract_price", "extract_records",
                   "snapshot_sources", "crawl_extract", "open_url", "search"],
    "mcp_tool":  ["call", "create_page", "create_task", "crm_get", "crm_upsert",
                   "due_tasks", "find_stale_leads", "get_page", "list_changed",
                   "upsert", "upsert_ticket"],
    "media":     ["transcribe", "generate_image", "process_video", "publish",
                   "text_to_speech", "transcode_variants", "verify_posts"],
    "http":      ["fetch", "poll", "post"],
    "github":    ["search_repos", "get_repo", "list_issues", "create_issue",
                   "list_prs", "get_contents", "list_branches", "list_commits",
                   "create_gist"],
}

# Google ops modules — lazily imported to keep startup fast.
_GOOGLE_OPS_MODULES: dict[str, str] = {
    "gmail":     "mini_kio.core.google_gmail_ops",
    "calendar":  "mini_kio.core.google_calendar_ops",
    "drive":     "mini_kio.core.google_drive_ops",
    "contacts":  "mini_kio.core.google_people_ops",
    "photos":    "mini_kio.core.google_photos_ops",
}


def _dispatch_google_capability(app_name: str, action: str, args_str: str) -> dict:
    """Route a Google service action to the correct ops module.

    Returns the ops module's result dict, or an error if the module/action
    is not found.
    """
    import importlib
    import json

    module_path = _GOOGLE_OPS_MODULES.get(app_name)
    if not module_path:
        return {"success": False, "message": f"Unknown Google service: {app_name}"}

    try:
        mod = importlib.import_module(module_path)
    except Exception as exc:
        return {"success": False, "message": f"Failed to load {module_path}: {exc}"}

    # Build the actions dict from the module's exported ACTIONS dict
    actions_attr = f"GOOGLE_{app_name.upper()}_ACTIONS"
    if app_name == "contacts":
        actions_attr = "GOOGLE_PEOPLE_ACTIONS"
    actions = getattr(mod, actions_attr, None)
    if actions is None:
        # Fallback: try all-caps variant
        actions = getattr(mod, f"GOOGLE_{app_name.upper()}_ACTIONS", {})

    handler = actions.get(action) if actions else None
    if handler is None:
        return {"success": False, "message": f"{app_name} does not support '{action}'."}

    # Parse the JSON args string into keyword arguments
    kwargs = {}
    if args_str:
        try:
            kwargs = json.loads(args_str)
        except (json.JSONDecodeError, TypeError):
            # If not JSON, pass as a positional string argument
            kwargs = {}

    try:
        return handler(**kwargs)
    except TypeError as exc:
        return {"success": False, "message": f"{app_name}.{action} argument error: {exc}"}
    except Exception as exc:
        return {"success": False, "message": f"{app_name}.{action} failed: {exc}"}

def execute_capability(target: str) -> dict:
    start_time = time.time()
    parts = target.split("::", 3)
    if len(parts) < 2:
        return _normalize_public_result("execute_capability", target, {"success": False, "message": "Invalid capability routing format."}, start_time)
    
    app_name, cap = parts[0], parts[1]
    args = parts[2] if len(parts) >= 3 else ""
    friendly_name = parts[3] if len(parts) == 4 else args
    
    caps = APP_CAPABILITIES.get(app_name, [])
    if cap not in caps:
        return _normalize_public_result("execute_capability", target, {"success": False, "message": f"{app_name} does not support '{cap}'."}, start_time)
        
    logger.info(f"[CAPABILITY] Routing {cap} to {app_name} with args: {args} (friendly: {friendly_name})")

    # ── Google cloud service dispatch ────────────────────────────────────
    # Gmail, Calendar, Drive, People, Photos, Places all route through their
    # dedicated ops modules via _dispatch_google_capability.  This is the
    # single entry point for every Google service action.
    if app_name in _GOOGLE_OPS_MODULES:
        result = _dispatch_google_capability(app_name, cap, args)
        return _normalize_public_result(
            "execute_capability", f"{app_name}::{cap}", result, start_time)

    # ── Workflow capability dispatch through provider registry ─────────
    # browser, mcp_tool, media, http, github all route through the
    # ProviderRegistry.  The step_runner builds a JSON-args target; we
    # parse it and delegate to the matching registered provider.
    _WORKFLOW_DISPATCH = {
        "browser", "mcp_tool", "media", "http", "github",
        "ai_reasoning", "terminal", "code_project",
    }
    if app_name in _WORKFLOW_DISPATCH:
        import json as _json
        from mini_kio.core.provider_registry import get_provider_registry
        registry = get_provider_registry()
        # For browser: the step_runner puts the action in cap; for others
        # it may be the actual provider action name.
        provider = registry.get_provider(cap)
        if provider is None:
            provider = registry.get_provider(app_name)
        if provider is not None:
            try:
                kwargs = _json.loads(args) if args else {}
            except (_json.JSONDecodeError, TypeError):
                kwargs = {}
            try:
                result = provider.execute(cap, target=cap, **kwargs)
            except Exception as exc:
                result = {"success": False, "message": f"{app_name}.{cap} failed: {exc}"}
            return _normalize_public_result(
                "execute_capability", f"{app_name}::{cap}", result, start_time)
        else:
            return _normalize_public_result(
                "execute_capability", f"{app_name}::{cap}",
                {"success": False, "message": f"No provider registered for {app_name}/{cap}"},
                start_time)

    from mini_kio.core.runtime import get_runtime
    rt = get_runtime()
    
    if cap == "play" and app_name == "spotify":
        query = urllib.parse.quote(args)
        target_url = f"spotify:search:{args}"
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

            # Use os.startfile for URLs — avoids visible console window.
            try:
                os.startfile(target_url)
                proc = type('Obj', (), {'pid': 0})()  # sentinel for ownership check
            except Exception:
                proc = subprocess.Popen(["cmd", "/c", "start", target_url], shell=False, creationflags=_creation_flags())
            
            # Attempt Bounded Ownership Registration
            if _IS_WINDOWS and info:
                time.sleep(1.0) # Wait for URI to trigger
                final_pid = _refine_pid_windows(proc.pid, info.get("process", "Spotify.exe"), prior_pids=prior_pids, launch_start=launch_start, lifecycle="electron")
                if final_pid and rt:
                    rt.register_tracked_process(final_pid, app_name, target_url)
                    from mini_kio.core.routing_utils import register_browser_capability
                    register_browser_capability(friendly_name, app_name, target_url, browser_pid=final_pid)
                    return _normalize_public_result("execute_capability", f"spotify::{friendly_name}", {"success": True, "message": f"Playing {friendly_name} on Spotify.", "pid": final_pid, "canonical_name": "spotify", "capability_name": friendly_name.capitalize()}, start_time)

            return _normalize_public_result("execute_capability", f"spotify::{friendly_name}", {"success": True, "message": f"Launched Spotify search for {friendly_name}.", "capability_name": friendly_name.capitalize()}, start_time)

        except Exception:
            # Fallback to web
                _safe_webbrowser_open(f"https://open.spotify.com/search/{query}")
                return _normalize_public_result("execute_capability", f"spotify::{friendly_name}", {"success": True, "message": f"Launched {friendly_name} search on Spotify Web.", "capability_name": friendly_name.capitalize()}, start_time)

    if cap in ("search", "open_url", "youtube") or (cap == "play" and app_name == "youtube"):
        if cap == "search":
            url = f"https://www.google.com/search?q={urllib.parse.quote_plus(args)}"
        elif cap == "youtube" or (cap == "play" and app_name == "youtube"):
            url = f"https://www.youtube.com/results?search_query={urllib.parse.quote_plus(args)}"
        else:
            if args.lower() in WEB_URLS:
                url = WEB_URLS[args.lower()]
            else:
                url = args if args.startswith("http") else "https://" + args

            # Explicit additional-instance markers: the coordinator appends
            # "::new" (another/new TAB) or "::newwindow" (a NEW WINDOW) to the
            # friendly name when the user asked for an additional instance —
            # such a request must skip duplicate prevention and really create
            # a new instance of the requested KIND, while keeping the entity.
            force_new = False
            force_new_window = False
            if isinstance(friendly_name, str) and friendly_name.endswith("::newwindow"):
                force_new = True
                force_new_window = True
                friendly_name = friendly_name[:-11]  # "::newwindow" is 11 chars
            elif isinstance(friendly_name, str) and friendly_name.endswith("::new"):
                force_new = True
                friendly_name = friendly_name[:-5]

            # A NEW WINDOW cannot be created through the Connector (its
            # open_tab is tab-scoped). Route it to the browser binary launch
            # with --new-window so a genuinely separate window is created.
            if force_new_window:
                info = _find_in_registry(app_name)
                if not info:
                    return _normalize_public_result("execute_capability", target, {"success": False, "message": f"Browser {app_name} not found in registry."}, start_time)
                path = _resolve_path(info)
                if not path:
                    return _normalize_public_result("execute_capability", target, {"success": False, "message": f"Browser {app_name} path not found."}, start_time)
                try:
                    from mini_kio.core.runtime import get_runtime
                    rt = get_runtime()
                    # Chrome/Firefox/Brave/Edge all accept --new-window on every
                    # platform; only passing it on Windows would make the
                    # success message untruthful elsewhere (browser could reuse
                    # an existing window while we claim a new one was opened).
                    # Bounded window-creation verification (truthfulness): only
                    # claim a genuinely separate window when one is observed.
                    # Chrome/Edge/Firefox all attach new windows to the browser
                    # process, so window-HANDLE counts (never PID counts) are
                    # the evidence. Poll briefly; never wait out a timeout.
                    proc_name = str(info.get("process") or "chrome.exe")
                    win_before = _visible_browser_window_count(proc_name)
                    chrome_args = [path, "--new-window", url]
                    proc = subprocess.Popen(
                        chrome_args, shell=False,
                        creationflags=_creation_flags(),
                        stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL,
                    )
                    if rt:
                        rt.register_tracked_process(proc.pid, app_name, url)
                    from mini_kio.core.routing_utils import register_browser_capability
                    register_browser_capability(friendly_name, app_name, url, browser_pid=proc.pid)
                    from mini_kio.core.target_ref import display_target_name
                    display = display_target_name(friendly_name)
                    browser_display = display_target_name(app_name)
                    confirmed = False
                    if win_before >= 0:
                        for _ in range(4):
                            time.sleep(0.6)
                            if _visible_browser_window_count(proc_name) > win_before:
                                confirmed = True
                                break
                    if confirmed:
                        message = f"Opened {display} in a new {browser_display} window."
                        verification = "window_identity"
                    else:
                        message = (
                            f"Opened {display} in {browser_display}; I couldn't confirm "
                            f"it got its own window (it may have opened as a tab)."
                        )
                        verification = "window_unverified"
                    return _normalize_public_result(
                        "execute_capability", f"{app_name}::{friendly_name}",
                        {"success": True, "message": message,
                         "pid": proc.pid, "canonical_name": app_name,
                         "verification_mode": verification, "capability_name": display,
                         "browser": app_name, "instance": "window"},
                        start_time)
                except Exception as exc:
                    return _normalize_public_result(
                        "execute_capability", f"{app_name}::{friendly_name}",
                        {"success": False, "message": f"Couldn't open {friendly_name} in a new window.", "failure_class": "launch_failed"},
                        start_time)

            # Prefer Browser Connector ONLY for the browser it actually serves
            # (the connector is the DEFAULT_BROWSER's extension). An explicit
            # non-default browser (edge/comet/firefox/brave) must NEVER be
            # silently opened in the default browser first (live-found
            # 2026-08-12: "open youtube in comet" opened a Chrome tab AND
            # launched Comet). Non-default browsers go straight to their own
            # binary below.
            from mini_kio.core.async_utils import safe_run_async
            from mini_kio.core.command_router import _get_connector
            from mini_kio.core.config import DEFAULT_BROWSER
            conn = _get_connector()
            if conn and conn.is_connected() and app_name.lower() == DEFAULT_BROWSER.lower():
                # Duplicate prevention (canonical): a default "open X" must not
                # create another equivalent web target when one already exists
                # (active capability session or live tab with the same URL /
                # identity) — focus the existing one instead. Explicit
                # "another/new tab" requests skip this.
                existing = None if force_new else _find_existing_web_target(conn, url, friendly_name)
                if existing:
                    focused = False
                    try:
                        focus_res = safe_run_async(conn.focus_tab(friendly_name or url))
                        focused = bool(getattr(focus_res, "success", False))
                    except Exception:
                        pass
                    from mini_kio.core.target_ref import display_target_name
                    display = display_target_name(friendly_name)
                    msg = f"{display} is already open — I focused it." if focused else f"{display} is already open."
                    return _normalize_public_result(
                        "execute_capability", f"{app_name}::{friendly_name}",
                        {"success": True, "message": msg,
                         "capability_name": display, "browser": app_name},
                        start_time)
                try:
                    # An explicit additional-instance request must open a
                    # GENUINELY NEW tab — force_new skips the connector's own
                    # same-domain dedup, which otherwise navigates/refreshes
                    # the existing tab instead of creating one (the
                    # "Open a new Telegram tab" bug).
                    before_count = _count_web_tabs(conn, url, friendly_name) if force_new else None
                    result = safe_run_async(conn.open_tab(url, force_new=force_new))
                    if result.success:
                        from mini_kio.core.routing_utils import register_browser_capability
                        register_browser_capability(friendly_name, app_name, url)
                        # BC-4: the extension ACK confirms the tab was created;
                        # strengthen with a bounded tab-identity check so success
                        # is verified (never pure assertion). For explicit new-
                        # instance requests, verify the target count increased
                        # by exactly ONE — existence alone cannot distinguish a
                        # freshly created tab from the pre-existing one.
                        verified = _verify_web_tab_opened(conn, url, friendly_name, before_count=before_count)
                        from mini_kio.core.target_ref import display_target_name
                        # instance="tab" lets the context referent remember the
                        # CREATED INSTANCE KIND so a later "close it" closes the
                        # tab — never the native app of the same name.
                        return _normalize_public_result(
                            "execute_capability", f"{app_name}::{friendly_name}",
                            {"success": True, "message": f"Opened {display_target_name(friendly_name)} in {display_target_name(app_name)}.",
                             "verification_mode": "tab_identity" if verified else "noop",
                             "verification_status": "passed" if verified else "unverified",
                             "capability_name": display_target_name(friendly_name), "browser": app_name,
                             "instance": "tab"},
                            start_time)
                except Exception as exc:
                    logger.debug("[CONNECTOR] execute_capability open_tab failed, falling back: %s", exc)

        info = _find_in_registry(app_name)
        if not info:
            return _normalize_public_result("execute_capability", target, {"success": False, "message": f"Browser {app_name} not found in registry."}, start_time)
        
        path = _resolve_path(info)
        if not path:
            return _normalize_public_result("execute_capability", target, {"success": False, "message": f"Browser {app_name} path not found."}, start_time)
        
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

            chrome_args = [path]
            chrome_args.append(url)

            proc = subprocess.Popen(
                chrome_args, 
                shell=False,
                creationflags=_creation_flags(),
                stdout=subprocess.DEVNULL,
                stderr=subprocess.DEVNULL
            )
            
            if _IS_WINDOWS:
                time.sleep(0.5)
                final_pid = _refine_pid_windows(proc.pid, info.get("process", "chrome.exe"), prior_pids=prior_pids, launch_start=launch_start, lifecycle="browser")
                if final_pid and rt:
                    rt.register_tracked_process(final_pid, app_name, url)
                    from mini_kio.core.routing_utils import register_browser_capability
                    register_browser_capability(friendly_name, app_name, url, browser_pid=final_pid)
                    from mini_kio.core.target_ref import display_target_name
                    return _normalize_public_result("execute_capability", f"{app_name}::{friendly_name}", {"success": True, "message": f"Opened {display_target_name(friendly_name)} in {display_target_name(app_name)}.", "pid": final_pid, "canonical_name": app_name, "verification_mode": "noop", "capability_name": display_target_name(friendly_name), "browser": app_name}, start_time)
                try:
                    import psutil
                    if rt and psutil.pid_exists(proc.pid):
                        rt.register_tracked_process(proc.pid, app_name, url)
                        from mini_kio.core.routing_utils import register_browser_capability
                        register_browser_capability(friendly_name, app_name, url, browser_pid=proc.pid)
                        from mini_kio.core.target_ref import display_target_name
                        return _normalize_public_result("execute_capability", f"{app_name}::{friendly_name}", {"success": True, "message": f"Opened {display_target_name(friendly_name)} in {display_target_name(app_name)}.", "pid": proc.pid, "canonical_name": app_name, "verification_mode": "noop", "capability_name": display_target_name(friendly_name), "browser": app_name}, start_time)
                except Exception:
                    pass

            from mini_kio.core.target_ref import display_target_name
            return _normalize_public_result("execute_capability", f"{app_name}::{friendly_name}", {"success": True, "message": f"Opened {display_target_name(friendly_name)} in {display_target_name(app_name)}.", "pid": proc.pid, "verification_mode": "noop", "capability_name": display_target_name(friendly_name), "browser": app_name}, start_time)
        except Exception as e:
            return _normalize_public_result("execute_capability", f"{app_name}::{friendly_name}", {"success": False, "message": f"Failed to route {cap} to {app_name}: {e}"}, start_time)
    # For now, just mock media capabilities since KIO is lightweight and doesn't hook into Windows Media APIs
    if cap in ("play", "pause", "next", "previous", "open_project", "open_file"):
        return _normalize_public_result("execute_capability", target, {"success": True, "message": f"Successfully routed '{cap}' to {app_name} (mocked API)."}, start_time)
    # send_message is a REAL outbound-communication capability, never a mock:
    # route it through the canonical communication seam (draft/send/verify/
    # persist) instead of claiming a fake delivery. The seam resolves the
    # authorized sink and honestly reports delivery or refusal.
    if cap == "send_message":
        try:
            from mini_kio.communication.messages import message_answer
            result = message_answer("send a message to me: %s" % args, decision=None)
            return _normalize_public_result(
                "execute_capability", target,
                {"success": bool(result.get("success")), "message": result.get("message", "Message not sent.")},
                start_time,
            )
        except Exception as exc:
            return _normalize_public_result("execute_capability", target,
                                            {"success": False, "message": f"Message capability unavailable: {exc}"}, start_time)
        
    return _normalize_public_result("execute_capability", target, {"success": False, "message": f"Capability {cap} not implemented."}, start_time)

__all__ = ["launch_app", "execute_capability", "close_app", "search_web", "APP_REGISTRY", "WEB_URLS"]
