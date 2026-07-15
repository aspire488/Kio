from dataclasses import dataclass, field
from enum import Enum
from typing import Optional, Dict, Any, List
from .intent_models import IntentClassification, IntentType


class OrchestrationState(Enum):
    CONVERSATIONAL = "conversational"
    AWAITING_CONFIRMATION = "awaiting_confirmation"
    EXECUTABLE_READY = "executable_ready"
    REFUSED = "refused"
    DEGRADED = "degraded"
    CLARIFYING = "clarifying"


class ConversationTone(Enum):
    NEUTRAL = "neutral"
    CONCISE = "concise"
    HELPFUL = "helpful"


@dataclass(frozen=True)
class PendingAction:
    action: str
    target: str
    classification: IntentClassification
    requires_confirmation: bool = True
    reason: Optional[str] = None
    provider: Optional[str] = None
    media_type: Optional[str] = None


@dataclass(frozen=True)
class OrchestrationResponse:
    state: OrchestrationState
    response_text: str
    intent_type: IntentType = IntentType.UNKNOWN
    pending_action: Optional[PendingAction] = None
    metadata: Dict[str, Any] = field(default_factory=dict)
    errors: List[str] = field(default_factory=list)
    CONVERSATIONAL = "conversational"
    AWAITING_CONFIRMATION = "awaiting_confirmation"
    EXECUTABLE_READY = "executable_ready"
    REFUSED = "refused"
    DEGRADED = "degraded"
    CLARIFYING = "clarifying"


@dataclass(frozen=True)
class OrchestrationResponse:
    state: OrchestrationState
    response_text: str
    intent_type: IntentType = IntentType.UNKNOWN
    pending_action: Optional[PendingAction] = None
    metadata: Dict[str, Any] = field(default_factory=dict)
    errors: List[str] = field(default_factory=list)
