"""Browser bookmark management — create, list, search, remove, organize."""

from __future__ import annotations

import json
import logging
import time
import uuid
from pathlib import Path
from typing import Any

from .events import EventBus
from .types import BrowserEvent, EventType

logger = logging.getLogger("browser_runtime.bookmarks")


class BookmarkManager:
    """Persistent bookmark storage per-workspace with folder organization."""

    def __init__(self, storage_root: Path, event_bus: EventBus) -> None:
        self._file = storage_root / "bookmarks.json"
        self._events = event_bus
        self._bookmarks: dict[str, list[dict[str, Any]]] = {}
        self._load()

    def create(self, workspace: str, url: str, title: str, folder: str = "") -> dict[str, Any]:
        if workspace not in self._bookmarks:
            self._bookmarks[workspace] = []
        bm = {
            "id": str(uuid.uuid4())[:12],
            "url": url[:2000],
            "title": title[:500],
            "folder": folder,
            "created_at": time.time(),
        }
        self._bookmarks[workspace].append(bm)
        self._save()
        self._events.emit_nowait(
            BrowserEvent(type=EventType.BOOKMARK_CREATED, payload={"workspace": workspace, "url": url, "title": title, "folder": folder})
        )
        return bm

    def list_all(self, workspace: str) -> list[dict[str, Any]]:
        return list(self._bookmarks.get(workspace, []))

    def list_folder(self, workspace: str, folder: str) -> list[dict[str, Any]]:
        return [b for b in self._bookmarks.get(workspace, []) if b.get("folder") == folder]

    def folders(self, workspace: str) -> list[str]:
        seen: set[str] = set()
        for b in self._bookmarks.get(workspace, []):
            f = b.get("folder", "")
            if f:
                seen.add(f)
        return sorted(seen)

    def remove(self, bookmark_id: str) -> bool:
        for workspace, bms in self._bookmarks.items():
            for i, bm in enumerate(bms):
                if bm["id"] == bookmark_id:
                    bms.pop(i)
                    self._save()
                    self._events.emit_nowait(
                        BrowserEvent(type=EventType.BOOKMARK_REMOVED, payload={"id": bookmark_id, "workspace": workspace})
                    )
                    return True
        return False

    def search(self, query: str, workspace: str | None = None) -> list[dict[str, Any]]:
        q = query.lower()
        results = []
        for ws, bms in self._bookmarks.items():
            if workspace and ws != workspace:
                continue
            for bm in bms:
                if q in bm["url"].lower() or q in bm["title"].lower() or q in bm.get("folder", "").lower():
                    results.append({**bm, "workspace": ws})
        return results

    def _load(self) -> None:
        if not self._file.exists():
            return
        try:
            with open(self._file, "r", encoding="utf-8") as f:
                self._bookmarks = json.load(f)
        except Exception as exc:
            logger.warning("Failed to load bookmarks: %s", exc)

    def _save(self) -> None:
        try:
            with open(self._file, "w", encoding="utf-8") as f:
                json.dump(self._bookmarks, f, ensure_ascii=False, default=str)
        except Exception as exc:
            logger.warning("Failed to save bookmarks: %s", exc)
