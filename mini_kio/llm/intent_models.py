from dataclasses import dataclass, field
from enum import Enum
from typing import List, Optional


class IntentType(Enum):
    CONVERSATIONAL = "conversational"
    INFORMATIONAL = "informational"
    EDUCATIONAL = "educational"
    EXECUTABLE = "executable"
    UNSAFE = "unsafe"
    UNKNOWN = "unknown"
    MATH = "math"
    REASONING = "reasoning"
    SYSTEM_STATE = "system_state"
    MEMORY = "memory"
    IDENTITY = "identity"


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
    
    # Gate 5 stabilization diagnostics
    sanitize_applied: bool = False
    emoji_sanitize_applied: bool = False
    typo_normalization_applied: bool = False
    authority_override_used: bool = False
    continuity_resume_used: bool = False
    educational_state_preserved: bool = False
    intent_downgrade_blocked: bool = False
    browser_canonicalization_used: bool = False
