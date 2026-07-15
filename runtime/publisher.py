from __future__ import annotations

from abc import ABC, abstractmethod
from typing import Protocol

from .observation import Observation


class Publisher(Protocol):
    """Protocol for publishing observations."""

    def publish(self, observation: Observation) -> None:
        ...

    def flush(self) -> None:
        """Force any buffered observations to be delivered.
        Implementations may be no‑op if they publish immediately.
        """
        ...
