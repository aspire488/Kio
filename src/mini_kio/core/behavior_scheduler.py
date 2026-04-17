"""
Behavior Scheduler - Run periodic checks and proactive behaviors.
"""

from __future__ import annotations

import logging
import threading
import time
from typing import Any

logger = logging.getLogger(__name__)

_running = False


def start_scheduler() -> None:
    """Start the behavior scheduler."""
    global _running
    _running = True

    thread = threading.Thread(target=_scheduler_loop, daemon=True, name="kio-scheduler")
    thread.start()
    logger.info("Behavior scheduler started")


def stop_scheduler() -> None:
    """Stop the behavior scheduler."""
    global _running
    _running = False


def _scheduler_loop() -> None:
    """Background scheduler loop."""
    global _running

    while _running:
        time.sleep(60)

        if not _running:
            break

        _run_periodic_tasks()


def _run_periodic_tasks() -> None:
    """Run periodic tasks."""
    from .context_engine import get_context_summary

    try:
        context = get_context_summary()
        logger.debug(f"Context: {context}")
    except Exception as e:
        logger.error(f"Periodic task error: {e}")


def schedule_proactive_message(message: str) -> None:
    """Schedule a proactive message."""
    from . import event_bus

    event_bus.publish("PROACTIVE_MESSAGE", message)


__all__ = ["start_scheduler", "stop_scheduler", "schedule_proactive_message"]
