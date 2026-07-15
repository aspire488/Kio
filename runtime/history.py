from __future__ import annotations

import collections
import threading
from typing import Dict, List

from .observation import Observation, ObservationSeverity


class History:
    """Thread‑safe bounded FIFO history with simple statistics."""

    def __init__(self, capacity: int = 1000):
        self._capacity = capacity
        self._deque: collections.deque[Observation] = collections.deque(maxlen=capacity)
        self._lock = threading.Lock()
        self._stats: Dict[str, Dict[str, int]] = {
            "provider": {},
            "subsystem": {},
            "severity": {},
        }

    def add(self, observation: Observation) -> None:
        with self._lock:
            self._deque.append(observation)
            # update provider count
            prov = observation.provider or "<none>"
            self._stats["provider"][prov] = self._stats["provider"].get(prov, 0) + 1
            # subsystem count
            sub = observation.subsystem or "<none>"
            self._stats["subsystem"][sub] = self._stats["subsystem"].get(sub, 0) + 1
            # severity count
            sev = observation.severity.name
            self._stats["severity"][sev] = self._stats["severity"].get(sev, 0) + 1

    def get_all(self) -> List[Observation]:
        with self._lock:
            return list(self._deque)

    def clear(self) -> None:
        with self._lock:
            self._deque.clear()
            for cat in self._stats:
                self._stats[cat].clear()

    def statistics(self) -> Dict[str, Dict[str, int]]:
        with self._lock:
            # shallow copy to avoid mutation outside lock
            return {k: dict(v) for k, v in self._stats.items()}
