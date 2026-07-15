from __future__ import annotations

import threading
from concurrent.futures import ThreadPoolExecutor
from typing import Iterable, List

from .history import History
from .observation import Observation
from .subscriber import Subscriber


class ObservationBus:
    """Central hub for publishing observations to registered subscribers.

    * Thread‑safe registration and publishing.
    * Non‑blocking delivery – each subscriber runs in its own worker thread.
    * Fault tolerant – exceptions in one subscriber are isolated.
    """

    def __init__(self, history_capacity: int = 1000, max_workers: int | None = None):
        self._subscribers: List[Subscriber] = []
        self._sub_lock = threading.Lock()
        self._history = History(capacity=history_capacity)
        self._executor = ThreadPoolExecutor(max_workers=max_workers)

    # Subscription management -------------------------------------------------
    def register(self, subscriber: Subscriber) -> None:
        with self._sub_lock:
            if subscriber not in self._subscribers:
                # Insert based on priority (higher first)
                self._subscribers.append(subscriber)
                self._subscribers.sort(key=lambda s: s.priority(), reverse=True)

    def unregister(self, subscriber: Subscriber) -> None:
        with self._sub_lock:
            if subscriber in self._subscribers:
                self._subscribers.remove(subscriber)

    # Alias methods expected by spec
    subscribe = register
    unsubscribe = unregister

    # Publishing ---------------------------------------------------------------
    def publish(self, observation: Observation) -> None:
        """Publish a single observation.

        The observation is recorded in history and then delivered to all
        interested subscribers in parallel. Errors in a subscriber are caught
        and logged to ``stderr`` to avoid affecting others.
        """
        self._history.add(observation)
        # Snapshot subscriber list to avoid holding lock during delivery
        with self._sub_lock:
            subs = list(self._subscribers)
        for sub in subs:
            if sub.supports(observation):
                # Dispatch asynchronously; isolate failures.
                self._executor.submit(self._safe_deliver, sub, observation)

    def publish_many(self, observations: Iterable[Observation]) -> None:
        for obs in observations:
            self.publish(obs)

    def _safe_deliver(self, subscriber: Subscriber, observation: Observation) -> None:
        try:
            subscriber.receive(observation)
        except Exception as exc:  # pragma: no cover – defensive
            import sys
            print(f"Subscriber {subscriber!r} raised {exc}", file=sys.stderr)

    # History & statistics ----------------------------------------------------
    def history(self) -> List[Observation]:
        return self._history.get_all()

    def clear(self) -> None:
        self._history.clear()

    def statistics(self) -> dict:
        stats = self._history.statistics()
        stats["total"] = len(self._history.get_all())
        return stats
