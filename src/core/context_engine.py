"""
Context Engine - Understand system and user context.
"""

from __future__ import annotations

import logging
import threading
import time
from typing import Any

logger = logging.getLogger(__name__)

_user_idle = False
_last_user_activity = time.time()


def get_idle_time() -> float:
    """Get seconds since last user activity."""
    return time.time() - _last_user_activity


def is_user_idle(threshold_seconds: float = 300.0) -> bool:
    """Check if user has been idle for threshold time."""
    return get_idle_time() > threshold_seconds


def record_user_activity() -> None:
    """Record user activity timestamp."""
    global _last_user_activity
    _last_user_activity = time.time()
    global _user_idle
    _user_idle = False


def on_activation(event: Any = None) -> None:
    """Handle ACTIVATE_KIO event."""
    record_user_activity()
    logger.debug("User activated KIO")


def start_context_monitoring() -> None:
    """Start context monitoring thread."""
    from . import event_bus

    event_bus.subscribe("ACTIVATE_KIO", on_activation)
    event_bus.subscribe("USER_IDLE", on_user_idle)
    event_bus.subscribe("USER_RETURNED", on_user_returned)

    thread = threading.Thread(target=_context_loop, daemon=True, name="kio-context")
    thread.start()
    logger.info("Context engine started")


def _context_loop() -> None:
    """Background context monitoring."""
    global _user_idle

    IDLE_THRESHOLD = 300.0

    while True:
        time.sleep(30)

        idle_time = get_idle_time()

        if idle_time > IDLE_THRESHOLD and not _user_idle:
            _user_idle = True
            logger.info(f"User idle for {idle_time:.0f}s")


def on_user_idle(event: Any = None) -> None:
    """Handle user becoming idle."""
    logger.info("User is now idle")


def on_user_returned(event: Any = None) -> None:
    """Handle user returning."""
    record_user_activity()
    from . import event_bus

    event_bus.publish(
        "PROACTIVE_MESSAGE", "Welcome back! Let me know if you need anything."
    )


def get_context_summary() -> dict:
    """Get current context summary."""
    return {
        "idle_time": get_idle_time(),
        "is_idle": is_user_idle(),
    }


__all__ = [
    "start_context_monitoring",
    "get_context_summary",
    "get_idle_time",
    "is_user_idle",
    "record_user_activity",
]
