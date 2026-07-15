"""Communication protocol for internal API.

Defines abstract messaging between components, such as events or commands.
"""

from __future__ import annotations
from typing import Protocol, Any, Mapping


class Communicator(Protocol):
    """Interface for sending and receiving messages within KIO."""

    def send(self, channel: str, payload: Any) -> None: ...
    """Send *payload* on *channel* to interested listeners."""

    def receive(self, channel: str) -> Any: ...
    """Blocking receive of the next message from *channel*; returns payload."""
