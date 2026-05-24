"""
operator_protocol.py — KIO Operator Protocol Definitions
=========================================================
Minimal deterministic metadata for operator admission and lifecycle control.
"""

from __future__ import annotations
from typing import TypedDict, List, Any, Callable

class OperatorDescriptor(TypedDict):
    """Deterministic metadata for a KIO operator."""
    tool_name: str
    tool_version: str
    ram_budget_mb: float
    timeout_seconds: int
    side_effect: bool
    lifecycle_type: str
    supported_actions: List[str]

class ActionRegistryEntry(TypedDict):
    """Static entry for the action registry."""
    handler: Callable[..., dict[str, Any]]
    canonical_name: str
    category: str
    descriptor: OperatorDescriptor

# ---------------------------------------------------------------------------
# Deterministic Outcome Taxonomy (Gate 2.5)
# ---------------------------------------------------------------------------
OUTCOME_SUCCESS = "SUCCESS"
OUTCOME_FAILURE = "FAILURE"
OUTCOME_BLOCKED = "BLOCKED"
OUTCOME_DEGRADED = "DEGRADED"
OUTCOME_INVALID_RESULT = "INVALID_RESULT"
OUTCOME_TIMEOUT = "TIMEOUT"

# ---------------------------------------------------------------------------
# Deterministic Failure Taxonomy (Gate 2.5)
# ---------------------------------------------------------------------------
FAILURE_OPERATOR_EXCEPTION = "operator_exception"
FAILURE_RAM_EXCEEDED = "ram_budget_exceeded"
FAILURE_INVALID_RESULT = "invalid_operator_result"
FAILURE_BLOCKED_ACTION = "blocked_action"
FAILURE_UNKNOWN_ACTION = "unknown_action"
FAILURE_VERIFICATION_FAILED = "verification_failed"
FAILURE_TIMEOUT = "timeout"
