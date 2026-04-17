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

logger = logging.getLogger(__name__)

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


__all__ = ["shutdown_system", "restart_system", "lock_system"]
