"""Lifecycle manager interface.

Defines start/stop hooks for the runtime.
"""

from __future__ import annotations

import abc
from typing import Protocol, runtime_checkable

@runtime_checkable
class LifecycleManager(Protocol):
    """Interface for controlling the runtime lifecycle.

    Implementations should provide async or sync ``start``/``stop`` methods.
    """

    def start(self) -> None:
        """Begin runtime operation."""
        ...

    def stop(self) -> None:
        """Gracefully shut down the runtime."""
        ...

# ponytail: No event loop handling; concrete manager may choose async if needed.
