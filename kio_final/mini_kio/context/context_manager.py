import time
from typing import List, Optional, Dict, Any
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

    def __init__(self):
        self._entries: List[ContextEntry] = []
        self._imported_entries: List[ContextEntry] = []
        self._sanitizer = ContextSanitizer()
        self._total_size = 0
        self._import_total_size = 0
        self._sequence_counter = 0
        self._import_sequence_counter = 0

    def add_entry(self, content: str, entry_type: ContextType, priority: int = 1, tags: List[str] = None, metadata: Dict[str, Any] = None) -> bool:
        """
        Adds a sanitized entry to context.
        Enforces count and size boundaries via eviction.
        """
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

    def get_snapshot(self, limit: int = 10, entry_type: Optional[ContextType] = None) -> ContextSnapshot:
        """
        Retrieves a deterministic snapshot of recent/high-priority context.
        Ordered newest first.
        """
        self._prune_expired()

        filtered = self._entries
        if entry_type:
            filtered = [e for e in filtered if e.entry_type == entry_type]

        ordered = sorted(filtered, key=lambda x: (x.timestamp, x.sequence), reverse=True)

        snapshot_entries = ordered[:limit]
        total_size = sum(e.size for e in snapshot_entries)

        return ContextSnapshot(
            entries=snapshot_entries,
            total_size=total_size,
            count=len(snapshot_entries)
        )

    def clear_session(self):
        """Wipes all session-scoped context."""
        self._entries = []
        self._total_size = 0

    def ingest_imported_history(self, entries: List[Dict[str, Any]]) -> int:
        """
        Ingest a list of normalized imported history dicts.
        Each dict must have: timestamp (int), role (str), text (str).
        Returns number of entries successfully ingested.
        """
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
    ) -> ContextSnapshot:
        """
        Retrieve imported history with optional keyword/tag filtering.
        Ordered newest first.
        No semantic search — keyword is plain substring match only.
        """
        filtered = self._imported_entries

        if keyword:
            keyword_lower = keyword.lower()
            filtered = [e for e in filtered if keyword_lower in e.content.lower()]

        if tag:
            filtered = [e for e in filtered if tag in e.tags]

        ordered = sorted(filtered, key=lambda x: (x.timestamp, x.sequence), reverse=True)

        snapshot_entries = ordered[:limit]
        total_size = sum(e.size for e in snapshot_entries)

        return ContextSnapshot(
            entries=snapshot_entries,
            total_size=total_size,
            count=len(snapshot_entries)
        )

    def clear_imported(self):
        """Wipes all imported history entries."""
        self._imported_entries = []
        self._import_total_size = 0
        self._import_sequence_counter = 0

    def _enforce_boundaries(self):
        """Deterministic FIFO eviction for session context."""
        while len(self._entries) > self.MAX_ENTRIES:
            evicted = self._entries.pop(0)
            self._total_size -= evicted.size

        while self._total_size > self.MAX_TOTAL_SIZE_CHARS and self._entries:
            evicted = self._entries.pop(0)
            self._total_size -= evicted.size

    def _enforce_import_boundaries(self):
        """Deterministic FIFO eviction for imported history."""
        while len(self._imported_entries) > self.MAX_IMPORT_ENTRIES:
            evicted = self._imported_entries.pop(0)
            self._import_total_size -= evicted.size

    def _prune_expired(self):
        """Removes entries older than TTL."""
        current_time = time.time()
        valid_entries = []
        new_total_size = 0

        for e in self._entries:
            if current_time - e.timestamp < self.TTL_S:
                valid_entries.append(e)
                new_total_size += e.size

        self._entries = valid_entries
        self._total_size = new_total_size
