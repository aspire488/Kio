"""
System Operator - Computer control commands (shutdown, restart, lock).

Key improvements:
1. Proper subprocess.run() with clean error handling
2. Platform detection (Windows vs Unix)
3. No exceptions thrown to caller — always returns result dict
4. Structured responses: {"success": bool, "message": str}
5. Timeout protection on all subprocess calls
"""

from __future__ import annotations

import logging
import platform
import subprocess
from typing import Optional

from mini_kio.core.operator_protocol import OperatorDescriptor

logger = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# Operator Descriptor
# ---------------------------------------------------------------------------

SYSTEM_OPERATOR_DESCRIPTOR: OperatorDescriptor = {
    "tool_name": "system_operator",
    "tool_version": "1.1.0",
    "ram_budget_mb": 2.0,
    "timeout_seconds": 10,
    "side_effect": True,
    "lifecycle_type": "stateless",
    "supported_actions": ["lock_system", "unlock_system", "lock_state", "shutdown_system", "restart_system", "recovery_runtime"]
}


def is_workstation_locked() -> Optional[bool]:
    """Truthful lock-state detection (Windows). Returns True/False or None when
    the state cannot be determined. Never guesses.

    Detection is anchored on the INPUT DESKTOP, not on a single window
    handle:
      - While the workstation is locked, the session's input desktop is the
        secure (Winlogon) desktop. A user-mode process cannot open it as the
        interactive input desktop, so OpenInputDesktop fails.
      - While unlocked, the input desktop is the interactive "Default"
        desktop and OpenInputDesktop succeeds.

    GetForegroundWindow()==0 is deliberately NOT the primary signal: an
    elevated process or a disconnected RDP session can see a NULL foreground
    window even when the session is unlocked, which previously made "unlock"
    report "not locked" while the screen was still locked.
    """
    if not _IS_WINDOWS:
        return None
    try:
        import ctypes
        user32 = ctypes.windll.user32
        # OpenInputDesktop requires DESKTOP_READOBJECTS (0x0001) and
        # DESKTOP_SWITCHDESKTOP (0x0100). Passing only DESKTOP_SWITCHDESKTOP
        # fails with ERROR_ACCESS_DENIED even when unlocked, which would
        # misreport an unlocked machine as locked.
        hdesk = user32.OpenInputDesktop(0, False, 0x0101)
        if hdesk:
            try:
                # Cross-check: the input desktop must be the interactive
                # desktop. A few configurations allow opening the secure
                # desktop handle; a Winlogon/secure name still means locked.
                name = ctypes.create_unicode_buffer(64)
                needed = ctypes.c_ulong()
                if user32.GetUserObjectInformationW(
                    hdesk, 2, name, 128, ctypes.byref(needed)
                ):
                    dname = (name.value or "").lower()
                    if "winlogon" in dname or "secure" in dname:
                        return True
                return False
            finally:
                user32.CloseDesktop(hdesk)
        # OpenInputDesktop failed: the workstation is locked (secure desktop
        # active) or the session has no interactive input desktop (locked /
        # disconnected). Both mean the machine is not in interactive use.
        return True
    except Exception:
        return None


def unlock_system() -> dict:
    """Unlock flow that NEVER bypasses Windows authentication.

    Distinguishes "unlock requested" from "system actually unlocked": only
    real Windows state (verified via is_workstation_locked) may produce an
    UNLOCKED report. While the workstation is verified LOCKED, KIO cannot
    (and must not) defeat a password/PIN/Windows Hello — the OS lock screen
    is the only unlock surface, so the truthful state is
    AUTHENTICATION_REQUIRED with an instruction to sign in. Wake-on-LAN is
    not Windows authentication and is never claimed as an unlock.
    """
    guard = _windows_only("Unlock")
    if guard:
        return guard
    locked = is_workstation_locked()
    logger.info("[SYSTEM] unlock requested (locked=%s)", locked)
    if locked is None:
        return {
            "success": True,
            "message": "I can't confirm whether the computer is unlocked yet.",
            "lock_state": "unknown",
        }
    if locked:
        # OS requires authentication; the lock screen is the unlock surface.
        return {
            "success": True,
            "message": (
                "The screen is locked and Windows requires you to sign in — "
                "I can't unlock it from here. Use your PIN or password to continue."
            ),
            "lock_state": "authentication_required",
        }
    return {
        "success": True,
        "message": "The computer isn't locked.",
        "lock_state": "unlocked",
    }


def lock_state() -> dict:
    """Read-only lock-state query (no side effects).

    Required states: LOCKED / UNLOCKED / UNKNOWN (AUTHENTICATION_REQUIRED is
    the unlock-request semantic; a read-only query reports LOCKED when the
    secure desktop is active).
    """
    guard = _windows_only("Lock state")
    if guard:
        return guard
    locked = is_workstation_locked()
    if locked is None:
        return {"success": True, "message": "I can't confirm the lock state right now.", "lock_state": "unknown"}
    if locked:
        return {"success": True, "message": "Your computer is locked.", "lock_state": "locked"}
    return {"success": True, "message": "Your computer isn't locked.", "lock_state": "unlocked"}

_IS_WINDOWS = platform.system() == "Windows"


def _windows_only(operation: str) -> dict[str, str] | None:
    """Check if operation is supported on current platform."""
    if not _IS_WINDOWS:
        return {"success": False, "message": f"{operation} is only supported on Windows"}
    return None


def shutdown_system(delay: int = 0) -> dict:
    """
    Shutdown the computer.
    
    Args:
        delay: Delay in seconds before shutdown
        
    Returns:
        {"success": bool, "message": str}
    """
    guard = _windows_only("Shutdown")
    if guard:
        return guard

    logger.info(f"[SYSTEM] shutdown requested (delay={delay}s)")

    try:
        result = subprocess.run(
            ["shutdown", "/s", "/t", str(delay)],
            capture_output=True,
            text=True,
            timeout=10,
        )
        if result.returncode == 0:
            logger.info("[SYSTEM] shutdown initiated")
            return {"success": True, "message": f"Shutting down in {delay}s..."}
        else:
            err = result.stderr.strip() or result.stdout.strip()
            logger.error(f"[SYSTEM] shutdown failed: {err}")
            return {"success": False, "message": f"Shutdown failed: {err[:100]}"}

    except subprocess.TimeoutExpired:
        logger.error("[SYSTEM] shutdown command timed out")
        return {"success": False, "message": "Shutdown command timed out"}

    except Exception as e:
        logger.exception(f"[SYSTEM] shutdown error: {e}")
        return {"success": False, "message": f"Shutdown error: {str(e)[:80]}"}


def restart_system(delay: int = 0) -> dict:
    """
    Restart the computer.
    
    Args:
        delay: Delay in seconds before restart
        
    Returns:
        {"success": bool, "message": str}
    """
    guard = _windows_only("Restart")
    if guard:
        return guard

    logger.info(f"[SYSTEM] restart requested (delay={delay}s)")

    try:
        result = subprocess.run(
            ["shutdown", "/r", "/t", str(delay)],
            capture_output=True,
            text=True,
            timeout=10,
        )
        if result.returncode == 0:
            logger.info("[SYSTEM] restart initiated")
            return {"success": True, "message": f"Restarting in {delay}s..."}
        else:
            err = result.stderr.strip() or result.stdout.strip()
            logger.error(f"[SYSTEM] restart failed: {err}")
            return {"success": False, "message": f"Restart failed: {err[:100]}"}

    except subprocess.TimeoutExpired:
        logger.error("[SYSTEM] restart command timed out")
        return {"success": False, "message": "Restart command timed out"}

    except Exception as e:
        logger.exception(f"[SYSTEM] restart error: {e}")
        return {"success": False, "message": f"Restart error: {str(e)[:80]}"}


def lock_system() -> dict:
    """
    Lock the workstation.
    
    Returns:
        {"success": bool, "message": str}
    """
    guard = _windows_only("Lock")
    if guard:
        return guard

    logger.info("[SYSTEM] lock requested")

    try:
        subprocess.run(
            ["rundll32.exe", "user32.dll,LockWorkStation"],
            timeout=5,
            capture_output=True,
        )
    except subprocess.TimeoutExpired:
        logger.warning("[SYSTEM] lock command timed out (normal for rundll32)")
    except Exception as e:
        logger.warning("[SYSTEM] lock command failed: %s", e)

    # Truthfulness: never claim "Locked" without OS confirmation. Poll the
    # authoritative lock state; headless/RDP-disconnected sessions may accept
    # the command yet never show a secure desktop, and claiming success there
    # would be a fabricated result. 4 x 0.75s keeps the action responsive
    # while still covering normal lock latency.
    import time as _time
    for _ in range(4):
        locked = is_workstation_locked()
        if locked:
            logger.info("[SYSTEM] lock confirmed by OS state")
            return {"success": True, "message": "Locked"}
        _time.sleep(0.75)
    logger.warning("[SYSTEM] lock command sent but OS state not confirmed")
    return {
        "success": True,
        "message": "I sent the lock command, but couldn't confirm the screen locked from here.",
        "lock_state": is_workstation_locked(),
    }


def recovery_runtime(target: str = "") -> dict:
    """
    Deterministic manual recovery: clear safety state escalation and integrity warnings.
    
    This resets the runtime from EMERGENCY or DEGRADED back to NORMAL by clearing
    all recorded integrity warnings and resetting counters. This requires explicit
    operator action and is not automatic.
    
    Args:
        target: Unused (present for dispatch contract compatibility)
    
    Returns:
        {"success": bool, "message": str, "cleared_warnings": int, "previous_safety_state": str}
    """
    logger.info("[SYSTEM] recovery requested")
    
    try:
        from mini_kio.core.runtime import manual_runtime_recovery
        result = manual_runtime_recovery()
        if result.get("success"):
            logger.info(f"[SYSTEM] runtime recovery successful: {result.get('message')}")
        else:
            logger.warning(f"[SYSTEM] runtime recovery failed: {result.get('message')}")
        return result
    except Exception as e:
        logger.exception(f"[SYSTEM] recovery error: {e}")
        return {"success": False, "message": f"Recovery failed: {str(e)[:80]}"}


__all__ = ["shutdown_system", "restart_system", "lock_system", "recovery_runtime"]
