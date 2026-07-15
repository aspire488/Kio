"""Browser history tracking — per-workspace page visit log with search."""

from __future__ import annotations

import json
import logging
import time
from pathlib import Path
from typing import Any

from .events import EventBus
from .types import BrowserEvent, EventType

logger = logging.getLogger("browser_runtime.history")


class HistoryManager:
    """Records page visits per workspace with persistence and search."""

    def __init__(self, storage_root: Path, event_bus: EventBus, max_entries: int = 5000) -> None:
        self._storage = storage_root / "history"
        self._storage.mkdir(parents=True, exist_ok=True)
        self._events = event_bus
        self._max_entries = max_entries
        self._entries: dict[str, list[dict[str, Any]]] = {}

    def record_visit(self, workspace: str, url: str, title: str) -> None:
        if workspace not in self._entries:
            self._entries[workspace] = self._load(workspace)
        entry = {
            "url": url[:2000],
            "title": title[:500],
            "visited_at": time.time(),
        }
        self._entries[workspace].append(entry)
        if len(self._entries[workspace]) > self._max_entries:
            self._entries[workspace] = self._entries[workspace][-self._max_entries:]
        self._events.emit_nowait(
            BrowserEvent(type=EventType.HISTORY_PAGE_VISITED, payload={"workspace": workspace, "url": url, "title": title})
        )

    def search(self, workspace: str, query: str, limit: int = 20) -> list[dict[str, Any]]:
        if workspace not in self._entries:
            self._entries[workspace] = self._load(workspace)
        q = query.lower()
        results = [
            e for e in reversed(self._entries[workspace])
            if q in e["url"].lower() or q in e["title"].lower()
        ]
        return results[:limit]

    def recent(self, workspace: str, limit: int = 20) -> list[dict[str, Any]]:
        if workspace not in self._entries:
            self._entries[workspace] = self._load(workspace)
        return list(reversed(self._entries[workspace][-limit:]))

    def clear(self, workspace: str | None = None) -> None:
        if workspace:
            self._entries.pop(workspace, None)
            path = self._workspace_path(workspace)
            if path.exists():
                path.unlink()
        else:
            self._entries.clear()
            for p in self._storage.glob("*.json"):
                p.unlink()
        self._events.emit_nowait(
            BrowserEvent(type=EventType.HISTORY_CLEARED, payload={"workspace": workspace or "all"})
        )

    def flush(self, workspace: str) -> None:
        entries = self._entries.get(workspace)
        if entries is None:
            return
        path = self._workspace_path(workspace)
        with open(path, "w", encoding="utf-8") as f:
            json.dump(entries, f, ensure_ascii=False, default=str)

    def _load(self, workspace: str) -> list[dict[str, Any]]:
        path = self._workspace_path(workspace)
        if not path.exists():
            return []
        try:
            with open(path, "r", encoding="utf-8") as f:
                return json.load(f)
        except Exception as exc:
            logger.warning("Failed to load history for '%s': %s", workspace, exc)
            return []

    def _workspace_path(self, workspace: str) -> Path:
        return self._storage / f"{workspace}.json"
