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
    MAX_TOTAL_SIZE_CHARS = 50000 # ~50KB char limit for RAM safety
    TTL_S = 3600 # 1 hour TTL for short-term context

    def __init__(self):
        self._entries: List[ContextEntry] = []
        self._sanitizer = ContextSanitizer()
        self._total_size = 0
        self._sequence_counter = 0

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
            
        # Deterministic ordering: Newest first (using timestamp and sequence for stability)
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

    def _enforce_boundaries(self):
        """Deterministic eviction (FIFO) to stay within RAM and count limits."""
        # 1. Count Limit
        while len(self._entries) > self.MAX_ENTRIES:
            evicted = self._entries.pop(0)
            self._total_size -= evicted.size

        # 2. Size Limit
        while self._total_size > self.MAX_TOTAL_SIZE_CHARS and self._entries:
            evicted = self._entries.pop(0)
            self._total_size -= evicted.size

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
