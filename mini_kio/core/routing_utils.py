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
import os
import shutil
import subprocess
import tempfile
import time
import psutil
from typing import Optional, Dict, Any
from mini_kio.core.config import DEFAULT_BROWSER
from mini_kio.core.app_operator import (
    APP_REGISTRY,
    _find_in_registry,
    _resolve_path,
    _find_installed_app,
    _web_url_for_open,
)  # _find_in_registry is used at module level below
from mini_kio.core.capability_registry import get_capability_registry

logger = logging.getLogger(__name__)

_BROWSER_REGISTRY = None

def get_browser_registry():
    global _BROWSER_REGISTRY
    if _BROWSER_REGISTRY is None:
        from mini_kio.browser.browser_session_registry import BrowserSessionRegistry
        _BROWSER_REGISTRY = BrowserSessionRegistry()
    return _BROWSER_REGISTRY


_KIO_BROWSER_PROFILE_DIR: str = os.path.join(
    tempfile.gettempdir(), "kio_browser_profiles"
)


def _cleanup_orphaned_profiles() -> None:
    """Remove leftover KIO browser temp profiles from abnormal shutdowns."""
    if os.path.isdir(_KIO_BROWSER_PROFILE_DIR):
        try:
            for name in os.listdir(_KIO_BROWSER_PROFILE_DIR):
                path = os.path.join(_KIO_BROWSER_PROFILE_DIR, name)
                if name.startswith("kio_") and os.path.isdir(path):
                    try:
                        shutil.rmtree(path, ignore_errors=True)
                        logger.info("[CAPABILITY] Cleaned orphaned profile: %s", name)
                    except Exception:
                        pass
        except Exception as exc:
            logger.warning("[CAPABILITY] Orphan cleanup error: %s", exc)


# Startup: Clean orphaned browser profiles from previous sessions
_cleanup_orphaned_profiles()


def register_browser_capability(canonical_target: str, browser: str, url: str, browser_pid: Optional[int] = None, temp_profile_dir: Optional[str] = None) -> str:
    """Register a browser capability session after successful launch."""
    cap_reg = get_capability_registry()
    return cap_reg.register(canonical_target, browser, url, browser_pid=browser_pid, temp_profile_dir=temp_profile_dir)


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
        "temp_profile_dir": entry.temp_profile_dir,
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


def _cleanup_browser_profile(temp_profile_dir: Optional[str]) -> None:
    """Remove a KIO browser temp profile directory."""
    if temp_profile_dir and os.path.isdir(temp_profile_dir):
        try:
            shutil.rmtree(temp_profile_dir, ignore_errors=True)
            logger.info("[CAPABILITY] Cleaned up browser profile: %s", temp_profile_dir)
        except Exception as exc:
            logger.warning("[CAPABILITY] Failed to clean up profile %s: %s", temp_profile_dir, exc)


def close_browser_capability(cap_info: dict) -> bool:
    """Actually close a browser capability by terminating its process.

    SAFETY GATE:
    If no temp_profile_dir is found, this session is likely sharing the user's
    main Chrome session. TERMINATION IS BLOCKED to prevent killing all user tabs.
    """
    browser_pid = cap_info.get("browser_pid")
    target = cap_info.get("canonical_target", "unknown")
    temp_profile_dir = cap_info.get("temp_profile_dir")

    # SAFETY CHECK: Non-isolated session protection
    if not temp_profile_dir:
        logger.warning("[CAPABILITY] Blocked close for '%s' — no isolated profile (risk to main session).", target)
        return False

    if browser_pid is None:
        logger.info("[CAPABILITY] No PID for '%s' — nothing to close.", target)
        return False

    logger.info("[CAPABILITY] Closing browser capability '%s' (pid %s)", target, browser_pid)
    # ... taskkill logic remains the same ...
    proc = subprocess.run(
        ["taskkill", "/T", "/F", "/PID", str(browser_pid)],
        capture_output=True, text=True, timeout=10,
    )
    if proc.returncode == 0:
        logger.info("[CAPABILITY] Successfully terminated pid %s for '%s'", browser_pid, target)
    elif "not found" in (proc.stderr or "").lower():
        logger.info("[CAPABILITY] Process %s for '%s' already exited", browser_pid, target)
    else:
        logger.warning("[CAPABILITY] taskkill for %s (%s): %s", target, browser_pid, proc.stderr)

    # Post-close verification: verify process death before returning success
    try:
        if psutil.pid_exists(browser_pid):
            # Brief wait for OS to reflect termination
            for _ in range(5):
                time.sleep(0.2)
                if not psutil.pid_exists(browser_pid):
                    break
            
            if psutil.pid_exists(browser_pid):
                logger.error("[CAPABILITY] Verification failed: PID %s for '%s' still alive", browser_pid, target)
                return False
    except Exception as exc:
        logger.warning("[CAPABILITY] Verification error for PID %s: %s", browser_pid, exc)

    _cleanup_browser_profile(temp_profile_dir)
    return True


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

def probe_registered_app(name: str) -> bool:
    """True when `name` is an explicit APP_REGISTRY entry that is launchable.

    A registered entry is evidence of installation even when no exe path
    resolves (URI-launched apps like Microsoft Store / Settings / Photos,
    system apps, UWP entries).
    """
    info = _find_in_registry(name)
    if info:
        if info.get("uri") or info.get("system") or info.get("uwp_packages"):
            return True
        path = _resolve_path(info)
        return path is not None
    return False


def probe_app_existence(name: str) -> bool:
    """Check if an app is installed on the system (native target resolution):
    registered APP_REGISTRY entry OR generic installed-app discovery."""
    return probe_registered_app(name) or _find_installed_app(name) is not None

def get_browser_routing(target: str, browser_name: Optional[str] = None) -> Dict[str, Any]:
    """
    Canonical target-kind resolution for open/launch requests.

    Decision order (Part II — NATIVE-FIRST):
      1. REGISTERED native application — explicit APP_REGISTRY entry that
         resolves (path / URI / system / UWP). Exact-identity only.
      2. GENERIC installed-app discovery — arbitrary installed applications
         without a registry entry (Start Menu / App Paths / PATH /
         WindowsApps). An installed desktop app wins over its website for a
         default "open X" (GitHub Desktop over github.com, WhatsApp over
         web.whatsapp.com). Generic containment matches are safe: the request
         name is a substring of a real installed app's name, never a
         synthesized domain.
      3. Explicit web target — known web app / explicit URL / dotted domain
         only, as the FALLBACK when no native app exists. NO single-word .com
         synthesis here: the classifier must never turn an app-like name into
         a made-up domain while an installed app might exist.
      4. not found — truthful "couldn't find X installed" (the execution path
         may still single-word-synthesize as a last resort AFTER its own
         discovery step, keeping classifier and executor consistent).

    Web is a fallback, not the default: a default application request prefers
    an installed/discoverable native application when one exists. Explicit web
    intent ("open X in Chrome", "on the web") is handled upstream by the
    classifier before this resolver runs.
    """
    browser = (browser_name or DEFAULT_BROWSER).lower()
    target_lower = target.lower().strip()
    
    reg = get_browser_registry()
    canonical_target = reg.canonicalize(target_lower)
    
    # 1. Registered native application (exact APP_REGISTRY identity).
    if probe_registered_app(canonical_target):
        logger.info(f"[ROUTING] Registered native app found for {canonical_target}, native route.")
        return {
            "route_type": "native",
            "action": "open_app",
            "target": canonical_target
        }
    
    # 2. GENERIC installed-app discovery — an installed desktop app wins over
    #    its website for a default "open X". Runs BEFORE web-target resolution
    #    so "Open GitHub" opens GitHub Desktop and "Open WhatsApp" opens the
    #    WhatsApp app when installed, and only falls to the website when no
    #    native app exists.
    if _find_installed_app(canonical_target) is not None:
        logger.info(f"[ROUTING] Generic discovery found for {canonical_target}, native route.")
        return {
            "route_type": "native",
            "action": "open_app",
            "target": canonical_target
        }

    # 3. Web only for EXPLICIT web targets: known web app, explicit URL, or
    #    dotted domain. Single-word .com synthesis is deliberately NOT applied
    #    here (default flag) — native discovery above already proved no
    #    installed app exists. Multi-word names ("da vinci resolve",
    #    "microsoft store") are never synthesized into .com domains at all.
    #
    #    DUAL-MODALITY check: when a name has BOTH a registered native identity
    #    and a web alias (e.g. "telegram" is a native app AND web.telegram.org),
    #    but the native app is not installed, opening the web version is a
    #    FALLBACK — it must go through the executor (launch_app) which attaches
    #    the explicit disclosure, never a silent browser_fallback.
    url = reg.get_url(canonical_target) or _web_url_for_open(target_lower)
    if url:
        if _find_in_registry(canonical_target) is not None:
            logger.info(
                f"[ROUTING] {canonical_target} has native identity but is not installed; "
                f"routing through executor for disclosed web fallback: {url}"
            )
            return {
                "route_type": "not_found",
                "action": "open_app",
                "target": canonical_target,
                "web_fallback_url": url,
            }
        logger.info(f"[ROUTING] No registered native app for {canonical_target}, explicit web target: {url}")
        return {
            "route_type": "browser_fallback",
            "action": "execute_capability",
            "target": f"{browser}::open_url::{url}::{canonical_target}",
            "browser": browser,
            "canonical_target": canonical_target
        }

    # 4. Truthful not-found — the pipeline routes this to the native open path
    #    which reports "couldn't find X installed" without opening a website.
    logger.info(f"[ROUTING] No installed app or web target for {canonical_target}, not_found route.")
    return {
        "route_type": "not_found",
        "action": "open_app",
        "target": canonical_target
    }
