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
