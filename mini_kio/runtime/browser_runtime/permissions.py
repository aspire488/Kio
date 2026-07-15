"""Browser permission management — grant/deny/reset camera, mic, location, etc."""

from __future__ import annotations

import logging
from typing import Any

from .events import EventBus
from .types import BrowserEvent, EventType

logger = logging.getLogger("browser_runtime.permissions")

_PERMISSION_MAP = {
    "camera": "camera",
    "microphone": "microphone",
    "location": "geolocation",
    "geolocation": "geolocation",
    "notifications": "notifications",
    "clipboard": "clipboard-read",
    "clipboard-read": "clipboard-read",
    "clipboard-write": "clipboard-write",
    "downloads": "downloads",
}


class PermissionManager:
    """Manages browser permissions per-workspace (camera, mic, location, etc.)."""

    def __init__(self, event_bus: EventBus) -> None:
        self._events = event_bus
        self._grants: dict[str, list[str]] = {}

    def grant(self, workspace: str, permission: str) -> dict[str, Any]:
        mapped = _PERMISSION_MAP.get(permission, permission)
        if workspace not in self._grants:
            self._grants[workspace] = []
        if mapped not in self._grants[workspace]:
            self._grants[workspace].append(mapped)
        self._events.emit_nowait(
            BrowserEvent(type=EventType.PERMISSION_GRANTED, payload={"workspace": workspace, "permission": mapped})
        )
        return {"success": True, "permission": mapped, "state": "granted"}

    def deny(self, workspace: str, permission: str) -> dict[str, Any]:
        mapped = _PERMISSION_MAP.get(permission, permission)
        if workspace not in self._grants:
            self._grants[workspace] = []
        if mapped in self._grants[workspace]:
            self._grants[workspace].remove(mapped)
        self._events.emit_nowait(
            BrowserEvent(type=EventType.PERMISSION_DENIED, payload={"workspace": workspace, "permission": mapped})
        )
        return {"success": True, "permission": mapped, "state": "denied"}

    def reset(self, workspace: str) -> dict[str, Any]:
        self._grants.pop(workspace, None)
        self._events.emit_nowait(
            BrowserEvent(type=EventType.PERMISSION_RESET, payload={"workspace": workspace})
        )
        return {"success": True, "message": f"Permissions reset for workspace '{workspace}'"}

    def list_grants(self, workspace: str) -> list[str]:
        return list(self._grants.get(workspace, []))

    def resolve_context_permissions(self, workspace: str) -> list[str]:
        return self._grants.get(workspace, [])
