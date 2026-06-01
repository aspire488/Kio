"""
routing_utils.py — Centralized Browser/App Routing Utility + Capability Registry

Logic:
1. Probe if native app exists in registry/path
2. IF exists -> Route to Native
3. IF NOT exists -> Route to Browser Fallback
4. Register browser capability session on successful fallback
5. Resolve capability sessions for close operations
"""

import logging
from typing import Optional, Dict, Any
from mini_kio.core.config import DEFAULT_BROWSER
from mini_kio.core.app_operator import APP_REGISTRY, _find_in_registry, _resolve_path, WEB_URLS, _normalize_web_target_to_url
from mini_kio.core.capability_registry import get_capability_registry

logger = logging.getLogger(__name__)

_BROWSER_REGISTRY = None

def get_browser_registry():
    global _BROWSER_REGISTRY
    if _BROWSER_REGISTRY is None:
        from mini_kio.browser.browser_session_registry import BrowserSessionRegistry
        _BROWSER_REGISTRY = BrowserSessionRegistry()
    return _BROWSER_REGISTRY


def register_browser_capability(canonical_target: str, browser: str, url: str, browser_pid: Optional[int] = None) -> str:
    """Register a browser capability session after successful launch."""
    cap_reg = get_capability_registry()
    return cap_reg.register(canonical_target, browser, url, browser_pid=browser_pid)


def resolve_capability_for_close(target: str) -> Optional[Dict[str, Any]]:
    """Resolve a close request against capability registry first.
    
    Returns capability info dict if found and active, None otherwise.
    """
    cap_reg = get_capability_registry()
    entry = cap_reg.resolve_by_target(target)
    if entry is None:
        browser_reg = get_browser_registry()
        url = browser_reg.get_url(target)
        if url:
            entry = cap_reg.resolve_by_target(url)
    if entry is None:
        return None
    return {
        "capability_id": entry.capability_id,
        "canonical_target": entry.canonical_target,
        "browser": entry.browser,
        "url": entry.url,
        "browser_pid": entry.browser_pid,
        "active": entry.active,
    }


def deactivate_capability(target: str) -> bool:
    """Deactivate a capability session by target name."""
    cap_reg = get_capability_registry()
    result = cap_reg.deactivate_by_target(target)
    if not result:
        browser_reg = get_browser_registry()
        url = browser_reg.get_url(target)
        if url:
            result = cap_reg.deactivate_by_target(url)
    return result


def close_browser_capability(cap_info: dict) -> bool:
    """Deactivate a browser capability session WITHOUT killing the browser process.

    Browser tabs share a single process — killing the PID would destroy
    unrelated user tabs (Gmail, YouTube, Notion, etc.).  KIO must never
    terminate a shared browser process.  Only the capability session is
    deactivated; the tab remains open in the user's browser.
    
    Returns False (no process was killed).
    """
    browser_pid = cap_info.get("browser_pid")
    if browser_pid is not None:
        logger.info("[CAPABILITY] Refusing to kill browser PID %s for '%s' — "
                     "browser tabs share a process. Tab remains open.",
                     browser_pid, cap_info.get("canonical_target"))
    return False


def get_latest_capability() -> Optional[Dict[str, Any]]:
    """Return the latest active capability session for context resolution."""
    cap_reg = get_capability_registry()
    entry = cap_reg.get_latest_active()
    if entry is None:
        return None
    return {
        "capability_id": entry.capability_id,
        "canonical_target": entry.canonical_target,
        "browser": entry.browser,
        "url": entry.url,
        "active": entry.active,
    }

def probe_app_existence(name: str) -> bool:
    """Check if an app is registered or resolvable on the system."""
    info = _find_in_registry(name)
    if info:
        path = _resolve_path(info)
        return path is not None
    return False

def get_browser_routing(target: str, browser_name: Optional[str] = None) -> Dict[str, Any]:
    """
    Centralized routing logic: Native app exists? -> Native else Browser.
    """
    browser = (browser_name or DEFAULT_BROWSER).lower()
    target_lower = target.lower().strip()
    
    reg = get_browser_registry()
    # 1. Canonicalize target
    canonical_target = reg.canonicalize(target_lower)
    
    # 2. Check if it's a known native app
    if probe_app_existence(canonical_target):
        logger.info(f"[ROUTING] Native app found for {canonical_target}, using native route.")
        return {
            "route_type": "native",
            "action": "open_app",
            "target": canonical_target
        }
    
    # 3. Check if it's a known web app or explicit URL (use canonical target first)
    url = reg.get_url(canonical_target) or _normalize_web_target_to_url(target_lower)
    if url:
        logger.info(f"[ROUTING] No native app for {canonical_target}, falling back to browser: {browser}")
        return {
            "route_type": "browser_fallback",
            "action": "execute_capability",
            "target": f"{browser}::open_url::{url}::{canonical_target}",
            "browser": browser,
            "canonical_target": canonical_target
        }
    
    # 4. Default fallback (search)
    return {
        "route_type": "search_fallback",
        "action": "search_web",
        "target": target
    }
