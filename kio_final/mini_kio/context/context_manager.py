import time
import json
import os
from typing import List, Optional, Dict, Any, Tuple
from .context_models import ContextType, ContextEntry, ContextSnapshot
from .context_sanitizer import ContextSanitizer


class ContextManager:
    """
    Manages lightweight, bounded contextual memory for KIO.
    Strictly follows 'Context is grounding, not authority' doctrine.

    INTEGRATION ASSERTIONS:
    1. Context retrieval cannot grant execution authority.
    2. Context is grounding data, not execution instructions.
    3. Context storage is bounded and sanitized to prevent injection.
    """

    MAX_ENTRIES = 50
    MAX_TOTAL_SIZE_CHARS = 50000
    TTL_S = 3600

    MAX_IMPORT_ENTRIES = 1024
    MAX_IMPORT_ENTRY_SIZE = 4096
    IMPORT_TTL_S = None

    MAX_SNAPSHOT_SIZE = 5 * 1024 * 1024

    def __init__(self):
        self._entries: List[ContextEntry] = []
        self._imported_entries: List[ContextEntry] = []
        self._sanitizer = ContextSanitizer()
        self._total_size = 0
        self._import_total_size = 0
        self._sequence_counter = 0
        self._import_sequence_counter = 0

    @staticmethod
    def _prioritize_key(
        entry: ContextEntry,
        keyword_lower: Optional[str] = None,
        tag: Optional[str] = None,
    ) -> Tuple[int, int, float, int]:
        kw_match = 0 if (keyword_lower is not None and keyword_lower in entry.content.lower()) else 1
        tag_match = 0 if (tag is not None and tag in entry.tags) else 1
        return (kw_match, tag_match, -entry.timestamp, -entry.sequence)

    def add_entry(self, content: str, entry_type: ContextType, priority: int = 1, tags: List[str] = None, metadata: Dict[str, Any] = None) -> bool:
        is_safe, sanitized_content, errors = self._sanitizer.sanitize(content)
        if not is_safe:
            return False

        self._sequence_counter += 1
        entry = ContextEntry(
            content=sanitized_content,
            entry_type=entry_type,
            priority=priority,
            sequence=self._sequence_counter,
            tags=tags or [],
            metadata=metadata or {}
        )

        self._entries.append(entry)
        self._total_size += entry.size

        self._enforce_boundaries()
        return True

    def get_snapshot(
        self,
        limit: int = 10,
        entry_type: Optional[ContextType] = None,
        keyword: Optional[str] = None,
        tag: Optional[str] = None,
        max_age_s: Optional[float] = None,
    ) -> ContextSnapshot:
        self._prune_expired()

        filtered = self._entries

        if entry_type:
            filtered = [e for e in filtered if e.entry_type == entry_type]

        if max_age_s is not None:
            cutoff = time.time() - max_age_s
            filtered = [e for e in filtered if e.timestamp >= cutoff]

        if keyword:
            keyword_lower_filter = keyword.lower()
            filtered = [e for e in filtered if keyword_lower_filter in e.content.lower()]

        if tag:
            filtered = [e for e in filtered if tag in e.tags]

        kw_lower = keyword.lower() if keyword else None
        ordered = sorted(filtered, key=lambda e: self._prioritize_key(e, kw_lower, tag))

        snapshot_entries = ordered[:limit]
        total_size = sum(e.size for e in snapshot_entries)

        return ContextSnapshot(
            entries=snapshot_entries,
            total_size=total_size,
            count=len(snapshot_entries)
        )

    def clear_session(self):
        self._entries = []
        self._total_size = 0

    def ingest_imported_history(self, entries: List[Dict[str, Any]]) -> int:
        ingested = 0
        for entry in entries:
            if not isinstance(entry, dict):
                continue

            text = entry.get("text", "")
            if not isinstance(text, str):
                continue

            if len(text) > self.MAX_IMPORT_ENTRY_SIZE:
                continue

            is_safe, sanitized_text, _ = self._sanitizer.sanitize_import(text, self.MAX_IMPORT_ENTRY_SIZE)
            if not is_safe:
                continue

            if not sanitized_text:
                continue

            self._import_sequence_counter += 1
            timestamp = entry.get("timestamp", 0)
            if not isinstance(timestamp, (int, float)):
                timestamp = 0.0

            role = entry.get("role", "user")
            source = entry.get("source", "external_memory")

            context_entry = ContextEntry(
                content=sanitized_text,
                entry_type=ContextType.IMPORTED_HISTORY,
                timestamp=float(timestamp),
                sequence=self._import_sequence_counter,
                tags=[role, source],
                metadata={"role": role, "source": source}
            )

            self._imported_entries.append(context_entry)
            self._import_total_size += context_entry.size
            ingested += 1

        self._enforce_import_boundaries()
        return ingested

    def get_imported_snapshot(
        self,
        limit: int = 10,
        keyword: Optional[str] = None,
        tag: Optional[str] = None,
        max_age_s: Optional[float] = None,
    ) -> ContextSnapshot:
        self._prune_imported_expired()

        filtered = self._imported_entries

        if max_age_s is not None:
            cutoff = time.time() - max_age_s
            filtered = [e for e in filtered if e.timestamp >= cutoff]

        if keyword:
            keyword_lower_filter = keyword.lower()
            filtered = [e for e in filtered if keyword_lower_filter in e.content.lower()]

        if tag:
            filtered = [e for e in filtered if tag in e.tags]

        kw_lower = keyword.lower() if keyword else None
        ordered = sorted(filtered, key=lambda e: self._prioritize_key(e, kw_lower, tag))

        snapshot_entries = ordered[:limit]
        total_size = sum(e.size for e in snapshot_entries)

        return ContextSnapshot(
            entries=snapshot_entries,
            total_size=total_size,
            count=len(snapshot_entries)
        )

    def clear_imported(self):
        self._imported_entries = []
        self._import_total_size = 0
        self._import_sequence_counter = 0

    def save_context_snapshot(self, path: str) -> None:
        entries_data = [self._entry_to_dict(e) for e in self._entries]
        imported_data = [self._entry_to_dict(e) for e in self._imported_entries]

        snapshot = {
            "version": 1,
            "timestamp": time.time(),
            "entries": entries_data,
            "imported_entries": imported_data,
            "count": len(entries_data),
            "imported_count": len(imported_data),
        }

        with open(path, "w", encoding="utf-8") as f:
            json.dump(snapshot, f, ensure_ascii=False)

    def load_context_snapshot(self, path: str) -> None:
        file_size = os.path.getsize(path)
        if file_size > self.MAX_SNAPSHOT_SIZE:
            raise ValueError(
                f"Snapshot file too large: {file_size} bytes"
                f" (max {self.MAX_SNAPSHOT_SIZE})"
            )

        with open(path, "r", encoding="utf-8") as f:
            data = json.load(f)

        if not isinstance(data, dict):
            raise ValueError("Snapshot must be a JSON object")

        if data.get("version") != 1:
            raise ValueError(f"Unsupported snapshot version: {data.get('version')}")

        if "entries" not in data:
            raise ValueError("Snapshot missing 'entries' field")

        self._entries = []
        self._imported_entries = []
        self._total_size = 0
        self._import_total_size = 0
        self._sequence_counter = 0
        self._import_sequence_counter = 0

        for entry_data in data.get("entries", []):
            entry = self._dict_to_entry(entry_data)
            if entry is not None:
                self._entries.append(entry)
                self._total_size += entry.size
                self._sequence_counter = max(self._sequence_counter, entry.sequence)

        for entry_data in data.get("imported_entries", []):
            entry = self._dict_to_entry(entry_data)
            if entry is not None:
                self._imported_entries.append(entry)
                self._import_total_size += entry.size
                self._import_sequence_counter = max(self._import_sequence_counter, entry.sequence)

        self._enforce_boundaries()
        self._enforce_import_boundaries()

    @staticmethod
    def _entry_to_dict(entry: ContextEntry) -> Dict[str, Any]:
        return {
            "content": entry.content,
            "entry_type": entry.entry_type.value,
            "timestamp": entry.timestamp,
            "sequence": entry.sequence,
            "priority": entry.priority,
            "tags": list(entry.tags),
            "metadata": dict(entry.metadata),
        }

    @staticmethod
    def _dict_to_entry(d: Dict[str, Any]) -> Optional[ContextEntry]:
        try:
            if not isinstance(d, dict):
                return None
            content = d.get("content")
            if not isinstance(content, str):
                return None
            entry_type_val = d.get("entry_type")
            if not isinstance(entry_type_val, str):
                return None
            entry_type = ContextType(entry_type_val)
            timestamp = d.get("timestamp", 0.0)
            if not isinstance(timestamp, (int, float)):
                timestamp = 0.0
            sequence = d.get("sequence", 0)
            if not isinstance(sequence, int):
                sequence = 0
            priority = d.get("priority", 1)
            if not isinstance(priority, int):
                priority = 1
            raw_tags = d.get("tags", [])
            tags = [t for t in raw_tags if isinstance(t, str)] if isinstance(raw_tags, list) else []
            raw_metadata = d.get("metadata", {})
            metadata = dict(raw_metadata) if isinstance(raw_metadata, dict) else {}
            return ContextEntry(
                content=content,
                entry_type=entry_type,
                timestamp=float(timestamp),
                sequence=sequence,
                priority=priority,
                tags=tags,
                metadata=metadata,
            )
        except (ValueError, TypeError, KeyError):
            return None

    def _enforce_boundaries(self):
        while len(self._entries) > self.MAX_ENTRIES:
            evicted = self._entries.pop(0)
            self._total_size -= evicted.size

        while self._total_size > self.MAX_TOTAL_SIZE_CHARS and self._entries:
            evicted = self._entries.pop(0)
            self._total_size -= evicted.size

    def _enforce_import_boundaries(self):
        while len(self._imported_entries) > self.MAX_IMPORT_ENTRIES:
            evicted = self._imported_entries.pop(0)
            self._import_total_size -= evicted.size

    def _prune_expired(self):
        current_time = time.time()
        valid_entries = []
        new_total_size = 0

        for e in self._entries:
            if current_time - e.timestamp < self.TTL_S:
                valid_entries.append(e)
                new_total_size += e.size

        self._entries = valid_entries
        self._total_size = new_total_size

    def _prune_imported_expired(self):
        if self.IMPORT_TTL_S is None:
            return
        current_time = time.time()
        valid_entries = []
        new_total_size = 0

        for e in self._imported_entries:
            if current_time - e.timestamp < self.IMPORT_TTL_S:
                valid_entries.append(e)
                new_total_size += e.size

        self._imported_entries = valid_entries
        self._import_total_size = new_total_size
