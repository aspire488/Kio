"""Executor abstraction."""

import abc
from typing import Any

class Executor(abc.ABC):
    """Runs and aborts execution tasks."""

    @abc.abstractmethod
    def run(self, task: Any) -> Any:
        """Run the given task and return its result."""
        ...

    @abc.abstractmethod
    def abort(self, task: Any) -> None:
        """Abort the given running task."""
        ...
