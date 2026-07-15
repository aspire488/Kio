from dataclasses import dataclass, field
from enum import Enum
from typing import Optional, Dict, Any, List


class ExecutionClassification(Enum):
    CONVERSATIONAL_ONLY = "conversational_only"
    INFORMATIONAL_ONLY = "informational_only"
    EXECUTABLE_VALIDATED = "executable_validated"
    EXECUTABLE_BLOCKED = "executable_blocked"
    EXECUTABLE_REQUIRES_CONFIRMATION = "executable_requires_confirmation"
    MALFORMED_PAYLOAD = "malformed_payload"
    DEGRADED_BLOCK = "degraded_block"


@dataclass(frozen=True)
class ExecutionAuditMetadata:
    intent_origin: str
    validation_state: str
    confirmation_state: str
    dispatch_eligibility: bool
    rejection_reason: Optional[str] = None
    execution_classification: Optional[ExecutionClassification] = None
    timestamp: float = field(default_factory=lambda: 0.0) # To be set by handoff


@dataclass(frozen=True)
class RuntimeHandoffResult:
    success: bool
    classification: ExecutionClassification
    message: str
    audit_metadata: ExecutionAuditMetadata
    execution_result: Optional[Dict[str, Any]] = None
