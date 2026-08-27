"""
user_progress.py — Shared user-facing progress/status bus
===========================================================

A tiny, thread-safe channel through which LONG-RUNNING operations (today:
presentation generation) publish concise user-facing status lines like
"Researching the topic…". Transports (Telegram bot, Discord, ...) subscribe a
listener and render ONE replaceable/updateable status message; they never see
internal vocabulary (operators, classifiers, OOXML, providers).

The bus is deliberately passive: nothing is published unless an operation
explicitly calls begin()/publish(), so every other feature is unaffected.
"""

from __future__ import annotations

import logging
import threading
from typing import Callable, Optional

logger = logging.getLogger("mini_kio.core.user_progress")


class ProgressBus:
    """Thread-safe status channel with a single listener slot.

    begin() must be called from the worker thread that runs the operation;
    publish() emits the latest status; end() clears the session so late
    publishes are inert. The listener is invoked synchronously from the
    publishing thread — transports must hop back to their own event loop
    (e.g. asyncio.run_coroutine_threadsafe) inside the listener.
    """

    def __init__(self) -> None:
        self._lock = threading.Lock()
        self._active = False
        self._listener: Optional[Callable[[str], None]] = None
        self._last: Optional[str] = None

    def begin(self, op: str = "task") -> None:
        with self._lock:
            self._active = True
            self._last = None
        logger.debug("[USER_PROGRESS] begin op=%s", op)

    def publish(self, status: str) -> None:
        with self._lock:
            if not self._active:
                return
            self._last = status
            listener = self._listener
        if listener is not None:
            try:
                listener(status)
            except Exception as exc:  # noqa: BLE001 - a broken listener never breaks the op
                logger.debug("[USER_PROGRESS] listener failed: %s", exc)

    def end(self) -> None:
        with self._lock:
            self._active = False
            self._listener = None

    def set_listener(self, cb: Optional[Callable[[str], None]]) -> None:
        with self._lock:
            self._listener = cb

    def is_active(self) -> bool:
        with self._lock:
            return self._active

    def last(self) -> Optional[str]:
        with self._lock:
            return self._last


# ── module-level singleton (the shared mechanism) ───────────────────────────
bus = ProgressBus()


def begin(op: str = "task") -> None:
    bus.begin(op)


def publish(status: str) -> None:
    bus.publish(status)


def end() -> None:
    bus.end()


def set_listener(cb: Optional[Callable[[str], None]]) -> None:
    bus.set_listener(cb)


def is_active() -> bool:
    return bus.is_active()
