"""Runtime context interfaces.

Defines the abstraction for accessing runtime state and registry.
"""

from __future__ import annotations

import abc
from dataclasses import dataclass
from enum import Enum, auto
from typing import Protocol, runtime_checkable, Any

@runtime_checkable
class RuntimeContext(Protocol):
    """Interface exposing runtime components.

    Implementations provide access to the current :class:`RuntimeState` and
    a :class:`RuntimeRegistry` for component lookup.
    """

    @property
    def state(self) -> "RuntimeState":
        """Current runtime state."""
        ...

    @property
    def registry(self) -> "RuntimeRegistry":
        """Registry of runtime components."""
        ...

class RuntimeState(Enum):
    """Possible lifecycle states of the runtime."""
    INITIALIZING = auto()
    RUNNING = auto()
    SHUTTING_DOWN = auto()
    TERMINATED = auto()

# ponytail: No concrete implementation needed; concrete classes will implement these protocols.
