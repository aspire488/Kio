"""CapabilityCache — TTL-based caching for MCP tool capabilities."""

from __future__ import annotations

import time
from typing import Any


class CapabilityCache:
    """TTL-based cache for capability metadata. Thread-safe for single-threaded use."""

    def __init__(self, ttl_s: float = 60.0) -> None:
        self._data: dict[str, tuple[float, Any]] = {}
        self._ttl_s = ttl_s

    def get(self, key: str) -> Any | None:
        entry = self._data.get(key)
        if entry is None:
            return None
        expires_at, value = entry
        if time.monotonic() > expires_at:
            del self._data[key]
            return None
        return value

    def set(self, key: str, value: Any) -> None:
        self._data[key] = (time.monotonic() + self._ttl_s, value)

    def invalidate(self, key: str) -> None:
        self._data.pop(key, None)

    def clear(self) -> None:
        self._data.clear()

    def size(self) -> int:
        now = time.monotonic()
        expired = [k for k, (t, _) in self._data.items() if now > t]
        for k in expired:
            del self._data[k]
        return len(self._data)
