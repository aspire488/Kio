from __future__ import annotations

"""Message abstraction for KIO communication layer."""

from dataclasses import dataclass
from enum import Enum
from typing import Any


class MessagePriority(Enum):
    """Priority levels for messages.

    The ordering reflects increasing urgency.
    """

    LOW = 1
    NORMAL = 2
    HIGH = 3
    CRITICAL = 4


@dataclass(frozen=True, slots=True)
class Message:
    """Immutable representation of a communication message.

    Attributes:
        id: Unique identifier for the message.
        sender: Identifier of the sender component.
        receiver: Identifier of the intended receiver component.
        topic: Topic or channel the message belongs to.
        payload: Arbitrary content carried by the message.
        timestamp: Epoch time (float) when the message was created.
    """

    id: str
    sender: str
    receiver: str
    topic: str
    payload: Any
    timestamp: float
