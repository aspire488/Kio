"""Async structured event bus for browser_runtime."""

from __future__ import annotations

import asyncio
import logging
from typing import Awaitable, Callable, Union

from .types import BrowserEvent, EventType

logger = logging.getLogger("browser_runtime.events")

Handler = Union[Callable[[BrowserEvent], None], Callable[[BrowserEvent], Awaitable[None]]]


class EventBus:
    """Publish/subscribe bus for BrowserEvent objects.

    Handlers may be sync or async callables. Subscriptions can target a
    specific EventType or all events (subscribe_all). Handler exceptions are
    caught and logged so one bad subscriber cannot break emission.
    """

    def __init__(self) -> None:
        self._handlers: dict[EventType, list[Handler]] = {}
        self._global_handlers: list[Handler] = []
        self._history: list[BrowserEvent] = []
        self._history_limit = 500
        self._lock = asyncio.Lock()

    def subscribe(self, event_type: EventType, handler: Handler) -> Callable[[], None]:
        self._handlers.setdefault(event_type, []).append(handler)

        def unsubscribe() -> None:
            handlers = self._handlers.get(event_type, [])
            if handler in handlers:
                handlers.remove(handler)

        return unsubscribe

    def subscribe_all(self, handler: Handler) -> Callable[[], None]:
        self._global_handlers.append(handler)

        def unsubscribe() -> None:
            if handler in self._global_handlers:
                self._global_handlers.remove(handler)

        return unsubscribe

    async def emit(self, event: BrowserEvent) -> None:
        async with self._lock:
            self._history.append(event)
            if len(self._history) > self._history_limit:
                self._history.pop(0)

        targets = list(self._handlers.get(event.type, [])) + list(self._global_handlers)
        for handler in targets:
            try:
                result = handler(event)
                if asyncio.iscoroutine(result):
                    await result
            except Exception:  # noqa: BLE001 - a subscriber must never break the bus
                logger.exception("Event handler raised for event type=%s", event.type)

    def emit_nowait(self, event: BrowserEvent) -> None:
        asyncio.create_task(self.emit(event))

    def history(self, event_type: EventType | None = None) -> list[BrowserEvent]:
        if event_type is None:
            return list(self._history)
        return [e for e in self._history if e.type == event_type]
