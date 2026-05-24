from dataclasses import dataclass, field
from enum import Enum
from typing import List, Optional


class IntentType(Enum):
    CONVERSATIONAL = "conversational"
    INFORMATIONAL = "informational"
    EXECUTABLE = "executable"
    UNSAFE = "unsafe"
    UNKNOWN = "unknown"


@dataclass(frozen=True)
class ValidationResult:
    is_valid: bool
    errors: List[str] = field(default_factory=list)
    warnings: List[str] = field(default_factory=list)


@dataclass(frozen=True)
class ExtractedIntent:
    raw_text: str
    normalized_text: str
    confidence: float
    intent_type: IntentType
    proposed_action: Optional[str] = None
    proposed_target: Optional[str] = None
    validation_errors: List[str] = field(default_factory=list)


@dataclass(frozen=True)
class IntentClassification:
    primary_intent: ExtractedIntent
    alternatives: List[ExtractedIntent] = field(default_factory=list)
    is_safe: bool = False
