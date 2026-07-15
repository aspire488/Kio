"""Planner abstraction."""

import abc
from typing import Any

class Planner(abc.ABC):
    """Creates and validates execution plans."""

    @abc.abstractmethod
    def create_plan(self) -> Any:
        """Create a new execution plan."""
        ...

    @abc.abstractmethod
    def validate_plan(self, plan: Any) -> bool:
        """Validate the given plan. Returns True if valid."""
        ...
