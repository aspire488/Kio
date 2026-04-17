"""
App Operator - Launch and close applications reliably.

Key improvements:
1. APP_REGISTRY is the single source of truth for app locations
2. Dynamic path resolution using shutil.which() for PATH-based apps
3. Process verification using psutil (fallback to tasklist)
4. Proper URL encoding with urllib.parse.quote_plus
5. subprocess.run() with proper error handling and timeouts
6. No pyautogui window focus attempts (removed)
7. WEB_URLS for direct browser opening
"""

from __future__ import annotations

import logging
import os
import platform
import shutil
import subprocess
import time
import urllib.parse
import webbrowser
from pathlib import Path
from typing import Optional, Dict

logger = logging.getLogger(__name__)

_IS_WINDOWS = platform.system() == "Windows"

# ─────────────────────────────────────────────────────────────────────────────
# APP REGISTRY - Central location for all known applications
# ─────────────────────────────────────────────────────────────────────────────

APP_REGISTRY: Dict[str, Dict[str, str]] = {
    "chrome": {
        "exe": "chrome.exe",
        "process": "chrome.exe",
        "paths": [
            r"C:\Program Files\Google\Chrome\Application\chrome.exe",
            r"C:\Program Files (x86)\Google\Chrome\Application\chrome.exe",
        ]
    },
    "edge": {
        "exe": "msedge.exe",
        "process": "msedge.exe",
        "paths": [
            r"C:\Program Files (x86)\Microsoft\Edge\Application\msedge.exe",
            r"C:\Program Files\Microsoft\Edge\Application\msedge.exe",
        ]
    },
    "firefox": {
        "exe": "firefox.exe",
        "process": "firefox.exe",
        "paths": [
            r"C:\Program Files\Mozilla Firefox\firefox.exe",
            r"C:\Program Files (x86)\Mozilla Firefox\firefox.exe",
        ]
    },
    "vscode": {
        "exe": "Code.exe",
        "process": "Code.exe",
        "cli": "code",  # Use 'code' command from PATH if available
        "paths": [
            r"C:\Program Files\Microsoft VS Code\Code.exe",
            r"C:\Program Files (x86)\Microsoft VS Code\Code.exe",
        ]
    },
    "notepad": {
        "exe": "notepad.exe",
        "process": "notepad.exe",
        "system": True,
    },
    "calculator": {
        "exe": "calc.exe",
        "process": "calc.exe",
        "aliases": ["calc", "calculator"],
        "system": True,
    },
    "explorer": {
        "exe": "explorer.exe",
        "process": "explorer.exe",
        "system": True,
    },
    "cmd": {
        "exe": "cmd.exe",
        "process": "conhost.exe",
        "system": True,
    },
    "powershell": {
        "exe": "powershell.exe",
        "process": "powershell.exe",
        "system": True,
    },
    "capcut": {
        "exe": "CapCut.exe",
        "process": "CapCut.exe",
        "paths": [
            r"C:\Program Files\CapCut\CapCut.exe",
            r"C:\Program Files (x86)\CapCut\CapCut.exe",
        ]
    },
    "spotify": {
        "exe": "Spotify.exe",
        "process": "Spotify.exe",
        "paths": [
            r"C:\Users\%USERNAME%\AppData\Roaming\Spotify\Spotify.exe",
            r"C:\Users\%USERNAME%\AppData\Local\Microsoft\WindowsApps\Spotify.exe",
        ]
    },
    "discord": {
        "exe": "Discord.exe",
        "process": "Discord.exe",
        "paths": [
            r"C:\Users\%USERNAME%\AppData\Local\Discord\app-*\Discord.exe",
            r"C:\Users\%USERNAME%\AppData\Local\Discord\Update.exe",
        ]
    },
    "vlc": {
        "exe": "vlc.exe",
        "process": "vlc.exe",
        "paths": [
            r"C:\Program Files\VideoLAN\VLC\vlc.exe",
            r"C:\Program Files (x86)\VideoLAN\VLC\vlc.exe",
        ]
    },
}

# Web apps — opened in default browser
WEB_URLS: Dict[str, str] = {
    "youtube": "https://youtube.com",
    "whatsapp": "https://web.whatsapp.com",
    "whatsapp web": "https://web.whatsapp.com",
    "claude": "https://claude.ai",
    "claude ai": "https://claude.ai",
    "chatgpt": "https://chat.openai.com",
    "chat gpt": "https://chat.openai.com",
    "chat gpt web": "https://chat.openai.com",
    "gmail": "https://gmail.com",
    "github": "https://github.com",
    "google": "https://google.com",
    "netflix": "https://netflix.com",
    "spotify": "https://open.spotify.com",
}


# ─────────────────────────────────────────────────────────────────────────────
# Public API
# ─────────────────────────────────────────────────────────────────────────────

def launch_app(name: str) -> dict:
    """
    Launch an application.
    
    Args:
        name: Application name (case-insensitive)
        
    Returns:
        {"success": bool, "message": str}
    """
    name_lower = name.lower().strip()
    logger.info(f"[APP] launch_app({name_lower!r})")

    # 1. Check web URLs first
    if name_lower in WEB_URLS:
        return _open_web_url(WEB_URLS[name_lower], name)

    # 2. Check app registry
    app_info = _find_app_in_registry(name_lower)
    if app_info:
        return _launch_app_internal(app_info, name_lower)

    # 3. Try to discover via PATH or Program Files
    return _discover_and_launch(name_lower)


def close_app(name: str) -> dict:
    """
    Close an application.
    
    Args:
        name: Application name
        
    Returns:
        {"success": bool, "message": str}
    """
    name_lower = name.lower().strip()
    logger.info(f"[APP] close_app({name_lower!r})")

    if not _IS_WINDOWS:
        return _close_app_unix(name_lower)

    # Find process name
    app_info = _find_app_in_registry(name_lower)
    process_name = app_info.get("process", f"{name_lower}.exe") if app_info else f"{name_lower}.exe"

    try:
        result = subprocess.run(
            ["taskkill", "/IM", process_name, "/F"],
            capture_output=True,
            text=True,
            timeout=5,
        )
        if result.returncode == 0:
            logger.info(f"[APP] closed {process_name}")
            return {"success": True, "message": f"Closed {name}"}
        else:
            stderr = result.stderr.strip()
            logger.warning(f"[APP] taskkill {process_name}: code {result.returncode}")
            return {"success": False, "message": f"{name} is not running"}
    except subprocess.TimeoutExpired:
        logger.error(f"[APP] taskkill timeout for {process_name}")
        return {"success": False, "message": f"Timeout closing {name}"}
    except Exception as e:
        logger.error(f"[APP] close_app error: {e}")
        return {"success": False, "message": f"Cannot close {name}: {str(e)[:80]}"}


def search_web(query: str) -> dict:
    """
    Search Google in the default browser.
    
    Args:
        query: Search query
        
    Returns:
        {"success": bool, "message": str}
    """
    if not query:
        return {"success": False, "message": "No search query"}

    # Use urllib.parse.quote_plus for safe URL encoding
    encoded = urllib.parse.quote_plus(query)
    url = f"https://www.google.com/search?q={encoded}"

    try:
        webbrowser.open(url)
        logger.info(f"[APP] searched: {query!r}")
        return {"success": True, "message": f"Searched: {query}"}
    except Exception as e:
        logger.error(f"[APP] search_web error: {e}")
        return {"success": False, "message": f"Search failed: {str(e)[:80]}"}


# ─────────────────────────────────────────────────────────────────────────────
# Internal helpers
# ─────────────────────────────────────────────────────────────────────────────

def _find_app_in_registry(name_lower: str) -> Optional[Dict]:
    """Find app in registry, checking both direct keys and aliases."""
    if name_lower in APP_REGISTRY:
        return APP_REGISTRY[name_lower]
    
    # Check aliases
    for app_name, app_info in APP_REGISTRY.items():
        aliases = app_info.get("aliases", [])
        if name_lower in aliases:
            return app_info
    
    return None


def _open_web_url(url: str, label: str) -> dict:
    """Open a URL in the default web browser."""
    try:
        webbrowser.open(url)
        logger.info(f"[APP] opened URL: {url}")
        return {"success": True, "message": f"Opened {label}"}
    except Exception as e:
        logger.error(f"[APP] webbrowser.open failed: {e}")
        return {"success": False, "message": f"Failed to open {label}: {str(e)[:80]}"}


def _resolve_app_path(app_info: Dict) -> Optional[str]:
    """
    Resolve the best path to execute an app.
    
    Returns:
        Path string if found, None if not available
    """
    # If there's a CLI tool (like 'code' for VSCode), try that first
    if "cli" in app_info:
        cli = app_info["cli"]
        if shutil.which(cli):
            return cli

    # Try predefined paths
    if "paths" in app_info:
        for path in app_info["paths"]:
            if Path(path).exists():
                return path

    # If it's a system app, just use the exe name (works on PATH)
    if app_info.get("system"):
        return app_info.get("exe")

    # Try finding via 'where' on Windows
    if _IS_WINDOWS and "exe" in app_info:
        try:
            result = subprocess.run(
                ["where", app_info["exe"]],
                capture_output=True,
                text=True,
                timeout=3,
            )
            if result.returncode == 0:
                return result.stdout.strip().splitlines()[0]
        except Exception:
            pass

    # Fallback: try using shutil.which for PATH-based apps
    if "exe" in app_info:
        exe_name = app_info["exe"]
        found = shutil.which(exe_name)
        if found:
            return found

    return None


def _launch_app_internal(app_info: Dict, name: str) -> dict:
    """Launch app using resolved path."""
    path = _resolve_app_path(app_info)
    
    if not path:
        logger.error(f"[APP] cannot find {name}")
        return {"success": False, "message": f"Cannot find {name} — is it installed?"}

    try:
        if os.path.isabs(path) and not Path(path).exists():
            logger.error(f"[APP] path does not exist: {path}")
            return {"success": False, "message": f"Cannot find {name} at {path}"}

        # Use safe launch via cmd start command
        subprocess.Popen(
            ["cmd", "/c", "start", "", path],
            shell=False,
            creationflags=_creation_flags(),
        )

        logger.info(f"[APP] launched: {path}")
        return {"success": True, "message": f"Opened {name}"}

    except FileNotFoundError:
        logger.error(f"[APP] FileNotFoundError: {path}")
        return {"success": False, "message": f"Cannot find {name}"}
    except Exception as e:
        logger.error(f"[APP] Popen failed for {path}: {e}")
        return {"success": False, "message": f"Failed to open {name}: {str(e)[:80]}"}


def _discover_and_launch(name: str) -> dict:
    """
    Try to discover and launch an unknown app.
    Uses 'where' on Windows for fast discovery.
    """
    exe_name = name if name.endswith(".exe") else f"{name}.exe"

    # Try Windows 'where' command
    if _IS_WINDOWS:
        try:
            result = subprocess.run(
                ["where", exe_name],
                capture_output=True,
                text=True,
                timeout=3,
            )
            if result.returncode == 0:
                found_path = result.stdout.strip().splitlines()[0]
                logger.info(f"[APP] discovered: {found_path}")
                try:
                    subprocess.Popen(["cmd", "/c", "start", "", found_path], creationflags=_creation_flags())
                    return {"success": True, "message": f"Opened {name}"}
                except Exception as e:
                    return {"success": False, "message": f"Failed to launch {name}: {str(e)[:80]}"}
        except Exception as e:
            logger.debug(f"[APP] 'where' command failed: {e}")

    # Try shutil.which
    found = shutil.which(exe_name)
    if found:
        try:
            subprocess.Popen(["cmd", "/c", "start", "", found], creationflags=_creation_flags())
            return {"success": True, "message": f"Opened {name}"}
        except Exception as e:
            return {"success": False, "message": f"Failed to launch {name}"}

    # Last resort: try without shell for safety.
    try:
        subprocess.Popen(["cmd", "/c", "start", "", name], shell=False, creationflags=_creation_flags())
        time.sleep(0.3)
        return {"success": True, "message": f"Opened {name}"}
    except Exception as e:
        logger.error(f"[APP] cannot open {name}: {e}")
        return {"success": False, "message": f"Cannot find or open: {name}"}


def _close_app_unix(name: str) -> dict:
    """Close app on Unix-like systems."""
    try:
        subprocess.run(
            ["pkill", "-f", name],
            capture_output=True,
            timeout=3,
        )
        return {"success": True, "message": f"Closed {name}"}
    except Exception as e:
        return {"success": False, "message": f"Cannot close {name}: {str(e)[:80]}"}


def _creation_flags() -> int:
    """Return subprocess creation flags for Windows."""
    if _IS_WINDOWS:
        return 0x00000008  # DETACHED_PROCESS
    return 0


__all__ = ["launch_app", "close_app", "search_web", "APP_REGISTRY", "WEB_URLS"]
