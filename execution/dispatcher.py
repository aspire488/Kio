"""Dispatcher abstraction."""

import abc
from typing import Any

class Dispatcher(abc.ABC):
    """Dispatches execution events to appropriate handlers."""

    @abc.abstractmethod
    def dispatch(self, message: Any) -> None:
        """Dispatch a single message or command."""
        ...

    @abc.abstractmethod
    def broadcast(self, message: Any) -> None:
        """Broadcast a message to all listeners."""
        ...
