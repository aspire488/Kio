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

# Web apps — opened directly in the default browser
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
        return _normalize_public_result("launch", canonical, result, start_time)

    # 2. Web URL
    if key in WEB_URLS:
        result = _open_url(WEB_URLS[key], key)
        return _normalize_public_result("launch", key, result, start_time)

    # 2b. Deterministic web domain aliases
    if key in WEB_DOMAIN_ALIASES:
        result = _open_url(WEB_DOMAIN_ALIASES[key], key)
        return _normalize_public_result("launch", key, result, start_time)

    normalized_url = _normalize_web_target_to_url(key)
    if normalized_url is not None:
        result = _open_url(normalized_url, key)
        return _normalize_public_result("launch", key, result, start_time)

    # 3. Discovery
    result = _discover_and_launch(key)
    if "canonical_name" not in result:
        result["canonical_name"] = key
    return _normalize_public_result("launch", result.get("canonical_name", key), result, start_time)


def close_app(name: str, pid: Optional[int] = None) -> dict:
    """Kill an application.  Returns {"success": bool, "message": str}."""
    key = name.lower().strip()
    # Gate 5: Strip capability compound suffix for browser canonical matching
    if "::" in key:
        key = key.split("::")[0]
    start_time = time.time()
    logger.info(f"[APP] close_app: {key!r} (pid override: {pid})")

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
        return matches[-1][1]
    except Exception:
        return None


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

    if residual_pid is None:
        payload = {
            "success": True,
            "message": f"Closed {name} (pid {pid})",
            "pid": pid,
            "primary_termination_attempted": True,
            "force_kill_attempted": force_attempted,
            "verified_terminated": True,
            "verification_status": "passed",
        }
        if info and info.get("lifecycle") == "uwp":
            payload["message"] = f"Closed {name}. Core process terminated, but UWP shell may persist."
        return payload

    stderr_lower = (graceful_result.stderr or "").lower()
    if lifecycle == "uwp":
        message = f"Closed {name}. Core process terminated, but UWP shell may persist."
    elif key == "explorer" or lifecycle == "launcher":
        message = f"Closed {name}. Explorer shell may persist after the window closes."
    elif lifecycle == "browser":
        message = f"Closed {name}. Primary browser process terminated, but helper processes may persist."
    elif "not found" in stderr_lower or "not running" in stderr_lower:
        message = f"{name} was already closed."
    else:
        message = f"Close requested for {name}, but {name} is still running."

    return {
        "success": True,
        "message": message,
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
        verified_started = _verify_process_started_windows(proc_name, timeout_s=4, uwp_packages=uwp_packages)
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
            if _verify_process_started_windows(proc_name, timeout_s=3, uwp_packages=uwp_packages):
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

            proc = subprocess.Popen(["cmd", "/c", "start", target_url], shell=False)
            
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

        # Prefer BrowserRuntime over subprocess when available
        if rt and rt.browser_runtime:
            from mini_kio.core.browser_operator import _br_run_async
            _ws = getattr(rt, '_browser_default_workspace', 'default')
            try:
                info = _br_run_async(rt.browser_runtime.new_tab(_ws, url=url))
                if info:
                    from mini_kio.core.routing_utils import register_browser_capability
                    register_browser_capability(friendly_name, app_name, url)
                    return _normalize_public_result(
                        "execute_capability", f"{app_name}::{friendly_name}",
                        {"success": True, "message": f"Opened {friendly_name.capitalize()} in {app_name.capitalize()}.",
                         "verification_mode": "noop", "capability_name": friendly_name.capitalize(), "browser": app_name},
                        start_time)
            except Exception:
                pass  # Fall through to subprocess if BrowserRuntime fails

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
                    return _normalize_public_result("execute_capability", f"{app_name}::{friendly_name}", {"success": True, "message": f"Opened {friendly_name.capitalize()} in {app_name.capitalize()}.", "pid": final_pid, "canonical_name": app_name, "verification_mode": "noop", "capability_name": friendly_name.capitalize(), "browser": app_name}, start_time)

                try:
                    import psutil
                    if rt and psutil.pid_exists(proc.pid):
                        rt.register_tracked_process(proc.pid, app_name, url)
                        from mini_kio.core.routing_utils import register_browser_capability
                        register_browser_capability(friendly_name, app_name, url, browser_pid=proc.pid)
                        return _normalize_public_result("execute_capability", f"{app_name}::{friendly_name}", {"success": True, "message": f"Opened {friendly_name.capitalize()} in {app_name.capitalize()}.", "pid": proc.pid, "canonical_name": app_name, "verification_mode": "noop", "capability_name": friendly_name.capitalize(), "browser": app_name}, start_time)
                except Exception:
                    pass

            return _normalize_public_result("execute_capability", f"{app_name}::{friendly_name}", {"success": True, "message": f"Opened {friendly_name.capitalize()} in {app_name.capitalize()}.", "pid": proc.pid, "verification_mode": "noop", "capability_name": friendly_name.capitalize(), "browser": app_name}, start_time)
        except Exception as e:
            return _normalize_public_result("execute_capability", f"{app_name}::{friendly_name}", {"success": False, "message": f"Failed to route {cap} to {app_name}: {e}"}, start_time)
    # For now, just mock media capabilities since KIO is lightweight and doesn't hook into Windows Media APIs
    if cap in ("play", "pause", "next", "previous", "open_project", "open_file", "send_message"):
        return _normalize_public_result("execute_capability", target, {"success": True, "message": f"Successfully routed '{cap}' to {app_name} (mocked API)."}, start_time)
        
    return _normalize_public_result("execute_capability", target, {"success": False, "message": f"Capability {cap} not implemented."}, start_time)

__all__ = ["launch_app", "execute_capability", "close_app", "search_web", "APP_REGISTRY", "WEB_URLS"]
