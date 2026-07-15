"""Window groups — named groups of browser windows across instances."""

from __future__ import annotations

import logging
import time
import uuid
from typing import Any

from .events import EventBus
from .types import BrowserEvent, EventType

logger = logging.getLogger("browser_runtime.window_groups")


class WindowGroupManager:
    """Named groups of browser windows across instances for multi-window workflows."""

    def __init__(self, event_bus: EventBus) -> None:
        self._events = event_bus
        self._groups: dict[str, dict[str, Any]] = {}

    def create(self, name: str, instance_ids: list[str] | None = None) -> dict[str, Any]:
        group_id = str(uuid.uuid4())[:12]
        self._groups[group_id] = {
            "id": group_id,
            "name": name,
            "instance_ids": list(instance_ids or []),
            "created_at": time.time(),
        }
        self._events.emit_nowait(
            BrowserEvent(type=EventType.WINDOW_GROUP_CREATED, payload={"group_id": group_id, "name": name})
        )
        return dict(self._groups[group_id])

    def add_instance(self, group_id: str, instance_id: str) -> bool:
        g = self._groups.get(group_id)
        if g is None:
            return False
        if instance_id not in g["instance_ids"]:
            g["instance_ids"].append(instance_id)
        return True

    def remove_instance(self, group_id: str, instance_id: str) -> bool:
        g = self._groups.get(group_id)
        if g is None:
            return False
        if instance_id in g["instance_ids"]:
            g["instance_ids"].remove(instance_id)
        return True

    def list_all(self) -> list[dict[str, Any]]:
        return [dict(g) for g in self._groups.values()]

    def remove(self, group_id: str) -> bool:
        g = self._groups.pop(group_id, None)
        if g is None:
            return False
        self._events.emit_nowait(
            BrowserEvent(type=EventType.WINDOW_GROUP_REMOVED, payload={"group_id": group_id})
        )
        return True
