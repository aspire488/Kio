"""Scheduler abstraction."""

import abc
from typing import Any

class Scheduler(abc.ABC):
    """Schedules and unschedules execution items."""

    @abc.abstractmethod
    def schedule(self, item: Any) -> None:
        """Schedule an item for execution."""
        ...

    @abc.abstractmethod
    def unschedule(self, item: Any) -> None:
        """Remove a previously scheduled item."""
        ...
