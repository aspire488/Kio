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
