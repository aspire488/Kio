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
"""

from __future__ import annotations

import glob
import logging
import os
import platform
import shutil
import subprocess
import time
import urllib.parse
import webbrowser
from pathlib import Path
from typing import Optional, Dict, Any

logger = logging.getLogger(__name__)

_IS_WINDOWS = platform.system() == "Windows"


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


# ---------------------------------------------------------------------------
# APP_REGISTRY
# ---------------------------------------------------------------------------

APP_REGISTRY: Dict[str, Dict[str, Any]] = {
    "chrome": {
        "exe": "chrome.exe",
        "process": "chrome.exe",
        "paths": [
            r"C:\Program Files\Google\Chrome\Application\chrome.exe",
            r"C:\Program Files (x86)\Google\Chrome\Application\chrome.exe",
        ],
    },
    "edge": {
        "exe": "msedge.exe",
        "process": "msedge.exe",
        "paths": [
            r"C:\Program Files (x86)\Microsoft\Edge\Application\msedge.exe",
            r"C:\Program Files\Microsoft\Edge\Application\msedge.exe",
        ],
    },
    "firefox": {
        "exe": "firefox.exe",
        "process": "firefox.exe",
        "paths": [
            r"C:\Program Files\Mozilla Firefox\firefox.exe",
            r"C:\Program Files (x86)\Mozilla Firefox\firefox.exe",
        ],
    },
    "vscode": {
        "exe": "Code.exe",
        "process": "Code.exe",
        "cli": "code",
        "dynamic_resolver": "_resolve_vscode_path",   # resolved at call time
    },
    "code": {
        "exe": "Code.exe",
        "process": "Code.exe",
        "cli": "code",
        "dynamic_resolver": "_resolve_vscode_path",
    },
    "notepad": {
        "exe": "notepad.exe",
        "process": "notepad.exe",
        "system": True,
    },
    "calculator": {
        "exe": "calc.exe",
        "process": "calc.exe",
        "aliases": ["calc"],
        "system": True,
    },
    "calc": {
        "exe": "calc.exe",
        "process": "calc.exe",
        "system": True,
    },
    "explorer": {
        "exe": "explorer.exe",
        "process": "explorer.exe",
        "system": True,
    },
    "cmd": {
        "exe": "cmd.exe",
        "process": "cmd.exe",
        "system": True,
    },
    "powershell": {
        "exe": "powershell.exe",
        "process": "powershell.exe",
        "system": True,
    },
    "paint": {
        "exe": "mspaint.exe",
        "process": "mspaint.exe",
        "system": True,
    },
    "capcut": {
        "exe": "CapCut.exe",
        "process": "CapCut.exe",
        "paths": [
            r"C:\Program Files\CapCut\CapCut.exe",
            r"C:\Program Files (x86)\CapCut\CapCut.exe",
        ],
    },
    "vlc": {
        "exe": "vlc.exe",
        "process": "vlc.exe",
        "paths": [
            r"C:\Program Files\VideoLAN\VLC\vlc.exe",
            r"C:\Program Files (x86)\VideoLAN\VLC\vlc.exe",
        ],
    },
    # BUG-05 FIX: Spotify — resolved dynamically, no %USERNAME% literal
    "spotify": {
        "exe": "Spotify.exe",
        "process": "Spotify.exe",
        "dynamic_resolver": "_resolve_spotify_path",
    },
    # BUG-06 FIX: Discord — resolved via glob, no app-* literal path
    "discord": {
        "exe": "Discord.exe",
        "process": "Discord.exe",
        "dynamic_resolver": "_resolve_discord_path",
    },
}

# Web apps — opened directly in the default browser
WEB_URLS: Dict[str, str] = {
    "youtube":      "https://youtube.com",
    "whatsapp":     "https://web.whatsapp.com",
    "whatsapp web": "https://web.whatsapp.com",
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
}


# ---------------------------------------------------------------------------
# Public API
# ---------------------------------------------------------------------------

def launch_app(name: str) -> dict:
    """Launch an application by name.  Returns {"success": bool, "message": str}."""
    key = name.lower().strip()
    logger.info(f"[APP] launch_app: {key!r}")

    # 1. Web URL
    if key in WEB_URLS:
        return _open_url(WEB_URLS[key], key)

    # 2. Registry
    info = _find_in_registry(key)
    if info:
        return _launch_from_info(info, key)

    # 3. Discovery
    return _discover_and_launch(key)


def close_app(name: str) -> dict:
    """Kill an application.  Returns {"success": bool, "message": str}."""
    key = name.lower().strip()
    logger.info(f"[APP] close_app: {key!r}")

    if not _IS_WINDOWS:
        return _pkill(key)

    info = _find_in_registry(key)
    process = info.get("process", f"{key}.exe") if info else f"{key}.exe"

    try:
        result = subprocess.run(
            ["taskkill", "/IM", process, "/F"],
            capture_output=True, text=True, timeout=6,
        )
        if result.returncode == 0:
            logger.info(f"[APP] killed: {process}")
            return {"success": True, "message": f"Closed {name}"}
        logger.warning(f"[APP] taskkill rc={result.returncode} for {process}")
        return {"success": False, "message": f"{name} is not running or could not be closed"}
    except subprocess.TimeoutExpired:
        return {"success": False, "message": f"Timeout closing {name}"}
    except Exception as exc:
        return {"success": False, "message": f"Cannot close {name}: {str(exc)[:80]}"}


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
        return {"success": True, "message": f"Opened {label}"}
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


def _launch_from_info(info: Dict, name: str) -> dict:
    path = _resolve_path(info)
    if not path:
        return {"success": False, "message": f"Cannot find {name} — is it installed?"}

    if os.path.isabs(path) and not Path(path).exists():
        return {"success": False, "message": f"Cannot find {name} at {path}"}

    try:
        # Safe launch via cmd start — no shell=True
        subprocess.Popen(
            ["cmd", "/c", "start", "", path],
            shell=False,
            creationflags=_creation_flags(),
        )
        logger.info(f"[APP] launched: {path}")
        return {"success": True, "message": f"Opened {name}"}
    except FileNotFoundError:
        return {"success": False, "message": f"Cannot find {name}"}
    except Exception as exc:
        return {"success": False, "message": f"Failed to open {name}: {str(exc)[:80]}"}


def _discover_and_launch(name: str) -> dict:
    """Try 'where', shutil.which, then shell-free Popen as last resort."""
    exe = name if name.endswith(".exe") else f"{name}.exe"

    if _IS_WINDOWS:
        try:
            r = subprocess.run(
                ["where", exe], capture_output=True, text=True, timeout=3,
            )
            if r.returncode == 0:
                path = r.stdout.strip().splitlines()[0]
                subprocess.Popen(["cmd", "/c", "start", "", path], shell=False, creationflags=_creation_flags())
                return {"success": True, "message": f"Opened {name}"}
        except Exception:
            pass

    found = shutil.which(exe)
    if found:
        try:
            subprocess.Popen(["cmd", "/c", "start", "", found], shell=False, creationflags=_creation_flags())
            return {"success": True, "message": f"Opened {name}"}
        except Exception:
            pass

    # Absolute last resort — launch by name via cmd start
    try:
        subprocess.Popen(["cmd", "/c", "start", "", name], shell=False, creationflags=_creation_flags())
        return {"success": True, "message": f"Opened {name}"}
    except Exception as exc:
        return {"success": False, "message": f"Cannot find or open: {name}"}


def _pkill(name: str) -> dict:
    try:
        subprocess.run(["pkill", "-f", name], timeout=4)
        return {"success": True, "message": f"Closed {name}"}
    except Exception as exc:
        return {"success": False, "message": f"Cannot close {name}: {str(exc)[:80]}"}


def _creation_flags() -> int:
    return 0x00000008 if _IS_WINDOWS else 0  # DETACHED_PROCESS


__all__ = ["launch_app", "close_app", "search_web", "APP_REGISTRY", "WEB_URLS"]
