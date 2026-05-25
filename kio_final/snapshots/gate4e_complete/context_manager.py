import time
import json
import os
from typing import List, Optional, Dict, Any, Tuple
from .context_models import (
    ContextType, ContextPartition, ContextEntry, ContextSnapshot,
    AssembledContext, ProfileSummary, ScoredEntry, ContextDiagnostics,
    CONTEXT_TYPE_TO_PARTITION, PARTITION_PRECEDENCE,
    PARTITION_NAMES, PROFILE_CATEGORIES,
    MAX_PROFILE_ENTRIES_PER_CATEGORY, MAX_PROFILE_VALUE_LENGTH,
)
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

    MAX_SYSTEM_ENTRIES = 100
    MAX_SYSTEM_SIZE_CHARS = 50000

    MAX_TEMP_ENTRIES = 20
    MAX_TEMP_SIZE_CHARS = 10000
    TEMP_TTL_S = 300

    MAX_SNAPSHOT_SIZE = 5 * 1024 * 1024

    def __init__(self):
        self._entries: List[ContextEntry] = []
        self._imported_entries: List[ContextEntry] = []
        self._system_entries: List[ContextEntry] = []
        self._temporary_entries: List[ContextEntry] = []
        self._sanitizer = ContextSanitizer()
        self._total_size = 0
        self._import_total_size = 0
        self._system_total_size = 0
        self._temporary_total_size = 0
        self._sequence_counter = 0
        self._import_sequence_counter = 0
        self._system_sequence_counter = 0
        self._temporary_sequence_counter = 0
        self._profile: Dict[str, Dict[str, str]] = {
            cat: {} for cat in PROFILE_CATEGORIES
        }

    # ── Partition helpers ──────────────────────────────────────────────

    @staticmethod
    def _partition_for(entry_type: ContextType) -> ContextPartition:
        return CONTEXT_TYPE_TO_PARTITION.get(entry_type, ContextPartition.CONVERSATIONAL)

    def _entries_for(self, partition: ContextPartition) -> List[ContextEntry]:
        if partition == ContextPartition.CONVERSATIONAL:
            return self._entries
        if partition == ContextPartition.IMPORTED:
            return self._imported_entries
        if partition == ContextPartition.SYSTEM:
            return self._system_entries
        if partition == ContextPartition.TEMPORARY:
            return self._temporary_entries
        return self._entries

    def _total_size_for(self, partition: ContextPartition) -> int:
        if partition == ContextPartition.CONVERSATIONAL:
            return self._total_size
        if partition == ContextPartition.IMPORTED:
            return self._import_total_size
        if partition == ContextPartition.SYSTEM:
            return self._system_total_size
        if partition == ContextPartition.TEMPORARY:
            return self._temporary_total_size
        return 0

    def _set_total_size_for(self, partition: ContextPartition, value: int):
        if partition == ContextPartition.CONVERSATIONAL:
            self._total_size = value
        elif partition == ContextPartition.IMPORTED:
            self._import_total_size = value
        elif partition == ContextPartition.SYSTEM:
            self._system_total_size = value
        elif partition == ContextPartition.TEMPORARY:
            self._temporary_total_size = value

    def _sequence_for(self, partition: ContextPartition) -> int:
        if partition == ContextPartition.CONVERSATIONAL:
            self._sequence_counter += 1
            return self._sequence_counter
        if partition == ContextPartition.IMPORTED:
            self._import_sequence_counter += 1
            return self._import_sequence_counter
        if partition == ContextPartition.SYSTEM:
            self._system_sequence_counter += 1
            return self._system_sequence_counter
        if partition == ContextPartition.TEMPORARY:
            self._temporary_sequence_counter += 1
            return self._temporary_sequence_counter
        self._sequence_counter += 1
        return self._sequence_counter

    def _set_sequence_counter(self, partition: ContextPartition, value: int):
        if partition == ContextPartition.CONVERSATIONAL:
            self._sequence_counter = value
        elif partition == ContextPartition.IMPORTED:
            self._import_sequence_counter = value
        elif partition == ContextPartition.SYSTEM:
            self._system_sequence_counter = value
        elif partition == ContextPartition.TEMPORARY:
            self._temporary_sequence_counter = value

    def _enforce_partition_boundaries(self, partition: ContextPartition):
        entries = self._entries_for(partition)
        if partition == ContextPartition.CONVERSATIONAL:
            max_entries = self.MAX_ENTRIES
            max_size = self.MAX_TOTAL_SIZE_CHARS
        elif partition == ContextPartition.IMPORTED:
            max_entries = self.MAX_IMPORT_ENTRIES
            max_size = self.MAX_IMPORT_ENTRIES * self.MAX_IMPORT_ENTRY_SIZE
        elif partition == ContextPartition.SYSTEM:
            max_entries = self.MAX_SYSTEM_ENTRIES
            max_size = self.MAX_SYSTEM_SIZE_CHARS
        elif partition == ContextPartition.TEMPORARY:
            max_entries = self.MAX_TEMP_ENTRIES
            max_size = self.MAX_TEMP_SIZE_CHARS
        else:
            return

        total_size = self._total_size_for(partition)
        while len(entries) > max_entries:
            evicted = entries.pop(0)
            total_size -= evicted.size

        while total_size > max_size and entries:
            evicted = entries.pop(0)
            total_size -= evicted.size

        self._set_total_size_for(partition, total_size)

    def _prune_partition_expired(self, partition: ContextPartition):
        if partition == ContextPartition.SYSTEM:
            return
        if partition == ContextPartition.CONVERSATIONAL:
            ttl = self.TTL_S
        elif partition == ContextPartition.IMPORTED:
            if self.IMPORT_TTL_S is None:
                return
            ttl = self.IMPORT_TTL_S
        elif partition == ContextPartition.TEMPORARY:
            ttl = self.TEMP_TTL_S
        else:
            return

        current_time = time.time()
        entries = self._entries_for(partition)
        valid = []
        new_size = 0
        for e in entries:
            if current_time - e.timestamp < ttl:
                valid.append(e)
                new_size += e.size
        entries.clear()
        entries.extend(valid)
        self._set_total_size_for(partition, new_size)

    # ── Prioritization ─────────────────────────────────────────────────

    @staticmethod
    def _prioritize_key(
        entry: ContextEntry,
        keyword_lower: Optional[str] = None,
        tag: Optional[str] = None,
    ) -> Tuple[int, int, float, int]:
        kw_match = 0 if (keyword_lower is not None and keyword_lower in entry.content.lower()) else 1
        tag_match = 0 if (tag is not None and tag in entry.tags) else 1
        return (kw_match, tag_match, -entry.timestamp, -entry.sequence)

    @staticmethod
    def _partition_sort_key(entry: ContextEntry) -> Tuple[int, float, int]:
        part = CONTEXT_TYPE_TO_PARTITION.get(entry.entry_type, ContextPartition.CONVERSATIONAL)
        precedence = PARTITION_PRECEDENCE.get(part, 99)
        return (precedence, -entry.timestamp, -entry.sequence)

    # ── Public API: entry management ────────────────────────────────────

    def add_entry(self, content: str, entry_type: ContextType, priority: int = 1, tags: List[str] = None, metadata: Dict[str, Any] = None) -> bool:
        is_safe, sanitized_content, errors = self._sanitizer.sanitize(content)
        if not is_safe:
            return False

        if not isinstance(tags, list):
            tags = []
        else:
            tags = [t for t in tags if isinstance(t, str)]
        if not isinstance(metadata, dict):
            metadata = {}

        partition = self._partition_for(entry_type)
        seq = self._sequence_for(partition)
        entry = ContextEntry(
            content=sanitized_content,
            entry_type=entry_type,
            priority=priority,
            sequence=seq,
            tags=tags,
            metadata=metadata
        )

        entries_list = self._entries_for(partition)
        entries_list.append(entry)
        total = self._total_size_for(partition) + entry.size
        self._set_total_size_for(partition, total)

        self._enforce_partition_boundaries(partition)
        return True

    def add_temporary_entry(self, content: str, tags: List[str] = None, metadata: Dict[str, Any] = None) -> bool:
        return self.add_entry(content, ContextType.TEMPORARY, tags=tags or [], metadata=metadata or {})

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

            tags = [role, source]

            meta = {"role": role, "source": source}

            profile_tags = entry.get("profile_tags")
            if isinstance(profile_tags, list):
                valid_tags = []
                for pt in profile_tags:
                    if isinstance(pt, str) and pt.count(".") == 1:
                        cat, key = pt.split(".", 1)
                        if cat in PROFILE_CATEGORIES and key.strip():
                            valid_tags.append(pt)
                meta["profile_tags"] = valid_tags
                tags.extend(f"profile:{t}" for t in valid_tags)

            context_entry = ContextEntry(
                content=sanitized_text,
                entry_type=ContextType.IMPORTED_HISTORY,
                timestamp=float(timestamp),
                sequence=self._import_sequence_counter,
                tags=tags,
                metadata=meta,
            )

            self._imported_entries.append(context_entry)
            self._import_total_size += context_entry.size
            ingested += 1

        self._enforce_partition_boundaries(ContextPartition.IMPORTED)
        return ingested

    def clear_session(self):
        self._entries = []
        self._total_size = 0
        self._temporary_entries = []
        self._temporary_total_size = 0

    def clear_imported(self):
        self._imported_entries = []
        self._import_total_size = 0

    def clear_system(self):
        self._system_entries = []
        self._system_total_size = 0
        self._system_sequence_counter = 0

    def clear_temporary(self):
        self._temporary_entries = []
        self._temporary_total_size = 0
        self._temporary_sequence_counter = 0

    # ── Public API: retrieval ───────────────────────────────────────────

    def get_snapshot(
        self,
        limit: int = 10,
        entry_type: Optional[ContextType] = None,
        keyword: Optional[str] = None,
        tag: Optional[str] = None,
        max_age_s: Optional[float] = None,
    ) -> ContextSnapshot:
        self._prune_partition_expired(ContextPartition.CONVERSATIONAL)

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

    def get_imported_snapshot(
        self,
        limit: int = 10,
        keyword: Optional[str] = None,
        tag: Optional[str] = None,
        max_age_s: Optional[float] = None,
    ) -> ContextSnapshot:
        self._prune_partition_expired(ContextPartition.IMPORTED)

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

    def get_partition_snapshot(
        self,
        partition: ContextPartition,
        limit: int = 10,
        keyword: Optional[str] = None,
        tag: Optional[str] = None,
    ) -> ContextSnapshot:
        self._prune_partition_expired(partition)

        entries = list(self._entries_for(partition))

        if keyword:
            kw_lower = keyword.lower()
            entries = [e for e in entries if kw_lower in e.content.lower()]

        if tag:
            entries = [e for e in entries if tag in e.tags]

        kw_lower = keyword.lower() if keyword else None
        ordered = sorted(entries, key=lambda e: self._prioritize_key(e, kw_lower, tag))

        snapshot_entries = ordered[:limit]
        total_size = sum(e.size for e in snapshot_entries)

        return ContextSnapshot(
            entries=snapshot_entries,
            total_size=total_size,
            count=len(snapshot_entries)
        )

    # ── Scored retrieval ─────────────────────────────────────────────────

    def search_imported(
        self,
        keywords: List[str],
        limit: int = 10,
    ) -> List[ScoredEntry]:
        self._prune_partition_expired(ContextPartition.IMPORTED)

        valid_keywords = [kw for kw in keywords if isinstance(kw, str) and kw.strip()]
        if not valid_keywords:
            return []

        kw_lower = [kw.lower() for kw in valid_keywords]

        scored: List[ScoredEntry] = []
        for entry in self._imported_entries:
            content_lower = entry.content.lower()
            if not all(kw in content_lower for kw in kw_lower):
                continue
            count = sum(content_lower.count(kw) for kw in kw_lower)
            score = count / max(1, len(entry.content))
            scored.append(ScoredEntry(entry=entry, score=score))

        scored.sort(key=lambda s: (-s.score, -s.entry.timestamp, -s.entry.sequence))
        return scored[:limit]

    def assemble_context_window(
        self,
        limit: int = 20,
        max_total_chars: int = 10000,
        partitions: Optional[List[str]] = None,
        include_timestamps: bool = False,
    ) -> AssembledContext:
        if partitions is None:
            partitions = ["system", "conversational", "imported", "temporary"]

        for p in partitions:
            part = ContextPartition(p)
            self._prune_partition_expired(part)

        merged: List[ContextEntry] = []
        for pname in partitions:
            part = ContextPartition(pname)
            part_entries = sorted(self._entries_for(part), key=self._partition_sort_key)
            merged.extend(part_entries)

        if not merged:
            return AssembledContext(
                text="",
                entry_count=0,
                total_chars=0,
                partitions_used=list(partitions),
                truncated=False,
            )

        selected: List[ContextEntry] = merged[:limit]

        lines: List[str] = []
        for e in selected:
            pname = CONTEXT_TYPE_TO_PARTITION.get(e.entry_type, ContextPartition.CONVERSATIONAL).value
            if include_timestamps:
                ts = time.strftime("%Y-%m-%d %H:%M:%S", time.localtime(e.timestamp))
                lines.append(f"[{pname}] {ts}: {e.content}")
            else:
                lines.append(f"[{pname}] {e.content}")

        full_text = "\n".join(lines)
        total_chars = len(full_text)
        truncated = False

        if total_chars > max_total_chars:
            lines.clear()
            running = 0
            for e in selected:
                pname = CONTEXT_TYPE_TO_PARTITION.get(e.entry_type, ContextPartition.CONVERSATIONAL).value
                if include_timestamps:
                    ts = time.strftime("%Y-%m-%d %H:%M:%S", time.localtime(e.timestamp))
                    line = f"[{pname}] {ts}: {e.content}"
                else:
                    line = f"[{pname}] {e.content}"
                line_len = len(line) + (1 if lines else 0)
                if running + line_len > max_total_chars:
                    truncated = True
                    break
                lines.append(line)
                running += line_len
            full_text = "\n".join(lines)
            total_chars = running

        return AssembledContext(
            text=full_text,
            entry_count=len(selected),
            total_chars=total_chars,
            partitions_used=list(partitions),
            truncated=truncated,
        )

    # ── Public API: profile ──────────────────────────────────────────────

    def set_profile(self, category: str, key: str, value: str) -> bool:
        if category not in PROFILE_CATEGORIES:
            return False
        if not isinstance(value, str) or not value.strip():
            return False
        if len(value) > MAX_PROFILE_VALUE_LENGTH:
            value = value[:MAX_PROFILE_VALUE_LENGTH]
        entries = self._profile[category]
        if len(entries) >= MAX_PROFILE_ENTRIES_PER_CATEGORY and key not in entries:
            return False
        entries[key] = value
        return True

    def get_profile(self, category: str, key: str) -> Optional[str]:
        if category not in PROFILE_CATEGORIES:
            return None
        return self._profile[category].get(key)

    def get_profile_category(self, category: str) -> Dict[str, str]:
        if category not in PROFILE_CATEGORIES:
            return {}
        return dict(self._profile[category])

    def clear_profile_category(self, category: str) -> bool:
        if category not in PROFILE_CATEGORIES:
            return False
        self._profile[category].clear()
        return True

    def clear_profile(self):
        for cat in PROFILE_CATEGORIES:
            self._profile[cat].clear()

    def get_preferred_name(self) -> Optional[str]:
        return self._profile["identity"].get("name")

    def get_preferred_tone(self) -> Optional[str]:
        return self._profile["preferences"].get("tone")

    def get_recurring_projects(self) -> List[str]:
        raw = self._profile["projects"].get("recurring", "")
        if not raw:
            return []
        return [p.strip() for p in raw.split(",") if p.strip()]

    def get_preferred_tools(self) -> List[str]:
        raw = self._profile["preferences"].get("tools", "")
        if not raw:
            return []
        return [t.strip() for t in raw.split(",") if t.strip()]

    def get_recurring_topics(self) -> List[str]:
        raw = self._profile["habits"].get("topics", "")
        if not raw:
            return []
        return [t.strip() for t in raw.split(",") if t.strip()]

    def assemble_profile_summary(self, max_total_chars: int = 2000) -> ProfileSummary:
        lines: List[str] = []
        cat_order = [
            "identity", "preferences", "projects", "habits",
            "relationships", "system_preferences",
        ]
        used_categories: List[str] = []

        for cat in cat_order:
            if cat not in PROFILE_CATEGORIES:
                continue
            entries = self._profile[cat]
            if not entries:
                continue
            used_categories.append(cat)
            lines.append(f"[{cat}]")
            for key in sorted(entries.keys()):
                val = entries[key]
                lines.append(f"  {key}: {val}")

        full_text = "\n".join(lines)
        total_chars = len(full_text)
        truncated = False

        if total_chars > max_total_chars:
            clipped: List[str] = []
            running = 0
            for line in lines:
                line_len = len(line) + (1 if clipped else 0)
                if running + line_len > max_total_chars:
                    truncated = True
                    break
                clipped.append(line)
                running += line_len
            full_text = "\n".join(clipped)
            total_chars = running
            entry_count = sum(1 for line in clipped if line.startswith("  "))
        else:
            entry_count = sum(1 for line in lines if line.startswith("  "))

        return ProfileSummary(
            text=full_text,
            categories_used=used_categories,
            entries_count=entry_count,
            total_chars=total_chars,
            truncated=truncated,
        )

    # ── Public API: persistence ─────────────────────────────────────────

    def save_context_snapshot(self, path: str) -> None:
        partitions_data = {}
        for pname in PARTITION_NAMES:
            part = ContextPartition(pname)
            entries = self._entries_for(part)
            partitions_data[pname] = [self._entry_to_dict(e) for e in entries]

        profile_data = {
            cat: dict(entries) for cat, entries in self._profile.items()
        }

        snapshot = {
            "version": 3,
            "timestamp": time.time(),
            "partitions": partitions_data,
            "profile": profile_data,
            "counts": {p: len(partitions_data[p]) for p in PARTITION_NAMES},
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

        version = data.get("version", 1)

        if version == 1:
            self._load_v1_snapshot(data)
        elif version == 2:
            self._load_v2_snapshot(data)
        elif version == 3:
            self._load_v3_snapshot(data)
        else:
            raise ValueError(f"Unsupported snapshot version: {version}")

    def _load_v1_snapshot(self, data: Dict[str, Any]) -> None:
        if "entries" not in data:
            raise ValueError("Snapshot missing 'entries' field")

        self._entries = []
        self._imported_entries = []
        self._system_entries = []
        self._temporary_entries = []
        self._total_size = 0
        self._import_total_size = 0
        self._system_total_size = 0
        self._temporary_total_size = 0
        self._sequence_counter = 0
        self._import_sequence_counter = 0
        self._system_sequence_counter = 0
        self._temporary_sequence_counter = 0

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

        self._enforce_partition_boundaries(ContextPartition.CONVERSATIONAL)
        self._enforce_partition_boundaries(ContextPartition.IMPORTED)

    def _load_v2_snapshot(self, data: Dict[str, Any]) -> None:
        self._entries = []
        self._imported_entries = []
        self._system_entries = []
        self._temporary_entries = []
        self._total_size = 0
        self._import_total_size = 0
        self._system_total_size = 0
        self._temporary_total_size = 0
        self._sequence_counter = 0
        self._import_sequence_counter = 0
        self._system_sequence_counter = 0
        self._temporary_sequence_counter = 0

        partitions_data = data.get("partitions")
        if not isinstance(partitions_data, dict):
            raise ValueError("Snapshot missing 'partitions' field")

        for pname, entry_list in partitions_data.items():
            if pname not in PARTITION_NAMES:
                raise ValueError(f"Unknown partition type: {pname}")

            if not isinstance(entry_list, list):
                raise ValueError(f"Partition '{pname}' must be a list")

            part = ContextPartition(pname)
            entries = self._entries_for(part)
            max_seq = 0

            for entry_data in entry_list:
                entry = self._dict_to_entry(entry_data)
                if entry is not None:
                    entries.append(entry)
                    total = self._total_size_for(part) + entry.size
                    self._set_total_size_for(part, total)
                    if entry.sequence > max_seq:
                        max_seq = entry.sequence

            if max_seq > 0:
                self._set_sequence_counter(part, max_seq)
            self._enforce_partition_boundaries(part)

    def _load_v3_snapshot(self, data: Dict[str, Any]) -> None:
        self._load_v2_snapshot(data)

        profile_data = data.get("profile")
        if not isinstance(profile_data, dict):
            return

        for cat in PROFILE_CATEGORIES:
            self._profile[cat].clear()

        for cat, entries in profile_data.items():
            if cat not in PROFILE_CATEGORIES:
                continue
            if not isinstance(entries, dict):
                continue
            for key, val in entries.items():
                if not isinstance(key, str) or not isinstance(val, str):
                    continue
                if len(self._profile[cat]) >= MAX_PROFILE_ENTRIES_PER_CATEGORY:
                    break
                self._profile[cat][key] = val[:MAX_PROFILE_VALUE_LENGTH]

    # ── Serialization helpers ───────────────────────────────────────────

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

    # ── Operational introspection ────────────────────────────────────────

    def validate_integrity(self) -> List[str]:
        warnings: List[str] = []
        for part in ContextPartition:
            entries = list(self._entries_for(part))
            computed = sum(e.size for e in entries)
            stored = self._total_size_for(part)
            if computed != stored:
                warnings.append(
                    f"Partition '{part.value}' size mismatch: stored={stored}, computed={computed}"
                )
        return warnings

    def get_diagnostics(self) -> ContextDiagnostics:
        conv = len(self._entries_for(ContextPartition.CONVERSATIONAL))
        imp = len(self._entries_for(ContextPartition.IMPORTED))
        sys = len(self._entries_for(ContextPartition.SYSTEM))
        tmp = len(self._entries_for(ContextPartition.TEMPORARY))
        total_size = sum(self._total_size_for(p) for p in ContextPartition)
        profile_cats = sum(1 for v in self._profile.values() if v)
        warnings = self.validate_integrity()
        return ContextDiagnostics(
            total_entries=conv + imp + sys + tmp,
            total_size=total_size,
            conversational_entries=conv,
            imported_entries=imp,
            system_entries=sys,
            temporary_entries=tmp,
            profile_categories=profile_cats,
            integrity_healthy=len(warnings) == 0,
        )

    # ── Legacy boundary enforcement (delegates to partition enforcement) ─

    def _enforce_boundaries(self):
        self._enforce_partition_boundaries(ContextPartition.CONVERSATIONAL)

    def _enforce_import_boundaries(self):
        self._enforce_partition_boundaries(ContextPartition.IMPORTED)

    def _prune_expired(self):
        self._prune_partition_expired(ContextPartition.CONVERSATIONAL)

    def _prune_imported_expired(self):
        self._prune_partition_expired(ContextPartition.IMPORTED)
