"""Event bus abstraction for KIO communication layer."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Protocol, runtime_checkable


@dataclass(frozen=True, slots=True)
class Event:
    """Immutable representation of an event occurring within the system.

    Attributes:
        id: Unique identifier for the event.
        source: Identifier of the component emitting the event.
        event_type: String describing the type/category of the event.
        payload: Arbitrary data associated with the event.
        timestamp: Epoch time (float) when the event was emitted.
    """

    id: str
    source: str
    event_type: str
    payload: Any
    timestamp: float


@runtime_checkable
class Publisher(Protocol):
    """Protocol for publishing messages to a destination."""

    def publish(self, message: "Message") -> None:
        """Publish a :class:`Message` instance.

        Implementations should deliver the message to the appropriate
        subscribers or transport.
        """


@runtime_checkable
class Subscriber(Protocol):
    """Protocol for receiving messages from a publisher."""

    def receive(self, message: "Message") -> None:
        """Handle an incoming :class:`Message`.

        Implementations may process, forward, or acknowledge the message.
        """

    def unsubscribe(self) -> None:
        """Unregister the subscriber from its publisher.

        After calling, the subscriber should no longer receive messages.
        """


@runtime_checkable
class EventBus(Protocol):
    """Protocol describing an event bus for publishing and subscribing to events."""

    def publish(self, event: Event) -> None:
        """Publish an :class:`Event` to all relevant subscribers."""

    def subscribe(self, topic: str, subscriber: Subscriber) -> None:
        """Subscribe a :class:`Subscriber` to a specific *topic*.

        The subscriber will receive events whose ``event_type`` matches the topic.
        """

    def unsubscribe(self, topic: str, subscriber: Subscriber) -> None:
        """Remove a subscriber from a given topic."""

    def list_topics(self) -> list[str]:
        """Return a list of all registered topics."""
