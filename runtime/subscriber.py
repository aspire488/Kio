from __future__ import annotations

from abc import ABC, abstractmethod
from typing import Protocol

from .observation import Observation


class Subscriber(Protocol):
    """Protocol for observation consumers."""

    def receive(self, observation: Observation) -> None:
        """Process a single observation. Must not raise to avoid bus disruption."""
        ...

    def supports(self, observation: Observation) -> bool:
        """Return True if this subscriber is interested in the observation."""
        ...

    def priority(self) -> int:
        """Higher numbers indicate higher priority; bus delivers in descending order."""
        ...
