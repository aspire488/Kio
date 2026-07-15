"""Pub/Sub protocol abstraction for KIO communication layer."""

from __future__ import annotations

from typing import Protocol, runtime_checkable


@runtime_checkable
class PubSub(Protocol):
    """Protocol defining a simple publish/subscribe registry."""

    def register(self, topic: str, subscriber: "Subscriber") -> None:
        """Register *subscriber* to receive messages for *topic*.

        Implementations should store the association for later broadcast.
        """

    def unregister(self, topic: str, subscriber: "Subscriber") -> None:
        """Remove *subscriber* from *topic*.

        After this call, the subscriber will no longer receive broadcasts for the topic.
        """

    def broadcast(self, topic: str, message: "Message") -> None:
        """Broadcast *message* to all subscribers registered under *topic*.

        No return value; implementations may handle delivery errors internally.
        """
