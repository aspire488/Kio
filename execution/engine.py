"""Execution engine abstraction."""

import abc
from typing import Any

class ExecutionEngine(abc.ABC):
    """Coordinates planning and execution of tasks."""

    @abc.abstractmethod
    def plan(self) -> Any:
        """Generate an execution plan."""
        ...

    @abc.abstractmethod
    def execute(self) -> Any:
        """Execute the prepared plan."""
        ...

    @abc.abstractmethod
    def pause(self) -> None:
        """Pause ongoing execution."""
        ...

    @abc.abstractmethod
    def resume(self) -> None:
        """Resume a paused execution."""
        ...

    @abc.abstractmethod
    def cancel(self) -> None:
        """Cancel the execution and clean up."""
        ...

    @abc.abstractmethod
    def status(self) -> Any:
        """Return current execution status."""
        ...
