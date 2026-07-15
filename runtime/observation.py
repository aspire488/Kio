from __future__ import annotations

import enum
import uuid
from dataclasses import dataclass, field
from datetime import datetime
from typing import Any, Dict, List, Optional


class ObservationSeverity(enum.Enum):
    DEBUG = enum.auto()
    INFO = enum.auto()
    WARNING = enum.auto()
    ERROR = enum.auto()
    CRITICAL = enum.auto()


class ObservationType(enum.Enum):
    EXECUTION = enum.auto()
    WORKFLOW = enum.auto()
    PROVIDER = enum.auto()
    BROWSER = enum.auto()
    VOICE = enum.auto()
    AVATAR = enum.auto()
    COMMUNICATION = enum.auto()
    SYSTEM = enum.auto()
    CUSTOM = enum.auto()


@dataclass(frozen=True, slots=True)
class Observation:
    """Immutable observation record.

    All fields are optional except the core identifiers; defaults provide sensible
    values for production use.
    """

    id: str = field(default_factory=lambda: str(uuid.uuid4()))
    timestamp: datetime = field(default_factory=datetime.utcnow)
    source: str = ""
    subsystem: str = ""
    provider: str = ""
    action: str = ""
    inputs: Optional[Dict[str, Any]] = None
    outputs: Optional[Dict[str, Any]] = None
    success: bool = True
    duration_ms: Optional[int] = None
    severity: ObservationSeverity = ObservationSeverity.INFO
    metadata: Optional[Dict[str, Any]] = None
    attachments: Optional[List[Any]] = None
    correlation_id: Optional[str] = None
    session_id: Optional[str] = None
    type: ObservationType = ObservationType.CUSTOM
