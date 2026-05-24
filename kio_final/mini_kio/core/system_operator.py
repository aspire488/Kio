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

from mini_kio.core.operator_protocol import OperatorDescriptor

logger = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# Operator Descriptor
# ---------------------------------------------------------------------------

SYSTEM_OPERATOR_DESCRIPTOR: OperatorDescriptor = {
    "tool_name": "system_operator",
    "tool_version": "1.0.0",
    "ram_budget_mb": 2.0,
    "timeout_seconds": 10,
    "side_effect": True,
    "lifecycle_type": "stateless",
    "supported_actions": ["lock_system", "shutdown_system", "restart_system", "recovery_runtime"]
}

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
        # rundll32 may return non-zero even on success
        logger.info("[SYSTEM] workstation locked")
        return {"success": True, "message": "Locked"}

    except subprocess.TimeoutExpired:
        # Timeout likely means it's running — treat as success
        logger.info("[SYSTEM] lock timeout (normal)")
        return {"success": True, "message": "Locked"}

    except Exception as e:
        logger.exception(f"[SYSTEM] lock error: {e}")
        return {"success": False, "message": f"Lock failed: {str(e)[:80]}"}


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
