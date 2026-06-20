"""
async_utils.py — Shared safe async execution for KIO.

Provides safe_run_async() that works in both thread-pool contexts
(Telegram) and running-event-loop contexts (Discord).

Strategy:
  1. Try asyncio.run() — works in threads with no running loop.
  2. On RuntimeError — schedule on the running loop via
     asyncio.run_coroutine_threadsafe() + future.result().
"""

from __future__ import annotations

import asyncio
import logging
from typing import TypeVar

logger = logging.getLogger(__name__)

T = TypeVar("T")


def safe_run_async(coro, timeout: float = 30.0):
    """
    Run an awaitable from a synchronous context, regardless of whether
    an event loop is already running on this thread.

    Args:
        coro: An awaitable (coroutine or Future).
        timeout: Max seconds to wait when bridging to a running loop.

    Returns:
        The result of the awaitable.

    Raises:
        Any exception the awaitable raises, or asyncio.TimeoutError.
    """
    try:
        return asyncio.run(coro)
    except RuntimeError:
        loop = asyncio.get_running_loop()
        future = asyncio.run_coroutine_threadsafe(coro, loop)
        return future.result(timeout=timeout)
