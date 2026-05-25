from dataclasses import dataclass, field
from enum import Enum
from typing import List, Dict, Any, Optional
import time


class ContextType(Enum):
    CONVERSATIONAL = "conversational"
    PREFERENCE = "preference"
    SYSTEM_FEEDBACK = "system_feedback"
    IMPORTED_HISTORY = "imported_history"
    AUDIT_LOG = "audit_log"
    TEMPORARY = "temporary"


class ContextPartition(Enum):
    CONVERSATIONAL = "conversational"
    IMPORTED = "imported"
    SYSTEM = "system"
    TEMPORARY = "temporary"


CONTEXT_TYPE_TO_PARTITION: Dict[ContextType, ContextPartition] = {
    ContextType.CONVERSATIONAL: ContextPartition.CONVERSATIONAL,
    ContextType.PREFERENCE: ContextPartition.CONVERSATIONAL,
    ContextType.IMPORTED_HISTORY: ContextPartition.IMPORTED,
    ContextType.SYSTEM_FEEDBACK: ContextPartition.SYSTEM,
    ContextType.AUDIT_LOG: ContextPartition.SYSTEM,
    ContextType.TEMPORARY: ContextPartition.TEMPORARY,
}

PARTITION_PRECEDENCE: Dict[ContextPartition, int] = {
    ContextPartition.SYSTEM: 0,
    ContextPartition.CONVERSATIONAL: 1,
    ContextPartition.IMPORTED: 2,
    ContextPartition.TEMPORARY: 3,
}

PARTITION_NAMES = [p.value for p in ContextPartition]


@dataclass(frozen=True)
class ContextEntry:
    content: str
    entry_type: ContextType
    timestamp: float = field(default_factory=time.time)
    sequence: int = 0
    priority: int = 1
    tags: List[str] = field(default_factory=list)
    metadata: Dict[str, Any] = field(default_factory=dict)

    @property
    def size(self) -> int:
        return len(self.content)


@dataclass(frozen=True)
class ContextSnapshot:
    entries: List[ContextEntry]
    total_size: int
    count: int
    timestamp: float = field(default_factory=time.time)


@dataclass(frozen=True)
class ImportEntry:
    timestamp: int
    role: str
    text: str
    source: str = "external_memory"


@dataclass(frozen=True)
class IngestResult:
    ingested_count: int
    rejected_count: int
    errors: List[str] = field(default_factory=list)


@dataclass(frozen=True)
class AssembledContext:
    text: str
    entry_count: int
    total_chars: int
    partitions_used: List[str]
    truncated: bool


PROFILE_CATEGORIES = frozenset({
    "preferences",
    "identity",
    "habits",
    "projects",
    "relationships",
    "system_preferences",
})

MAX_PROFILE_ENTRIES_PER_CATEGORY = 50
MAX_PROFILE_VALUE_LENGTH = 500


@dataclass(frozen=True)
class ProfileSummary:
    text: str
    categories_used: List[str]
    entries_count: int
    total_chars: int
    truncated: bool


@dataclass(frozen=True)
class ScoredEntry:
    entry: ContextEntry
    score: float


@dataclass(frozen=True)
class ContextDiagnostics:
    total_entries: int
    total_size: int
    conversational_entries: int
    imported_entries: int
    system_entries: int
    temporary_entries: int
    profile_categories: int
    integrity_healthy: bool
