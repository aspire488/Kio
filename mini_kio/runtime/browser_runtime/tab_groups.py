"""Tab groups — organize browser tabs into named groups."""

from __future__ import annotations

import logging
import time
import uuid
from typing import Any

from .events import EventBus
from .types import BrowserEvent, EventType

logger = logging.getLogger("browser_runtime.tab_groups")


class TabGroupManager:
    """Named tab groups for organizing browser tabs across workspaces."""

    def __init__(self, event_bus: EventBus) -> None:
        self._events = event_bus
        self._groups: dict[str, dict[str, Any]] = {}

    def create(self, name: str, workspace: str, tab_ids: list[str] | None = None) -> dict[str, Any]:
        group_id = str(uuid.uuid4())[:12]
        self._groups[group_id] = {
            "id": group_id,
            "name": name,
            "workspace": workspace,
            "tab_ids": list(tab_ids or []),
            "collapsed": False,
            "created_at": time.time(),
        }
        self._events.emit_nowait(
            BrowserEvent(type=EventType.TAB_GROUP_CREATED, payload={"group_id": group_id, "name": name, "workspace": workspace})
        )
        return dict(self._groups[group_id])

    def add_tab(self, group_id: str, tab_id: str) -> bool:
        group = self._groups.get(group_id)
        if group is None:
            return False
        if tab_id not in group["tab_ids"]:
            group["tab_ids"].append(tab_id)
        return True

    def remove_tab(self, group_id: str, tab_id: str) -> bool:
        group = self._groups.get(group_id)
        if group is None:
            return False
        if tab_id in group["tab_ids"]:
            group["tab_ids"].remove(tab_id)
        return True

    def list_by_workspace(self, workspace: str) -> list[dict[str, Any]]:
        return [dict(g) for g in self._groups.values() if g["workspace"] == workspace]

    def list_all(self) -> list[dict[str, Any]]:
        return [dict(g) for g in self._groups.values()]

    def remove(self, group_id: str) -> bool:
        group = self._groups.pop(group_id, None)
        if group is None:
            return False
        self._events.emit_nowait(
            BrowserEvent(type=EventType.TAB_GROUP_REMOVED, payload={"group_id": group_id})
        )
        return True

    def collapse(self, group_id: str) -> bool:
        group = self._groups.get(group_id)
        if group is None:
            return False
        group["collapsed"] = True
        self._events.emit_nowait(
            BrowserEvent(type=EventType.TAB_GROUP_COLLAPSED, payload={"group_id": group_id})
        )
        return True

    def expand(self, group_id: str) -> bool:
        group = self._groups.get(group_id)
        if group is None:
            return False
        group["collapsed"] = False
        self._events.emit_nowait(
            BrowserEvent(type=EventType.TAB_GROUP_EXPANDED, payload={"group_id": group_id})
        )
        return True
