"""AURA Integration APIs — Clean boundary between KIO execution and AURA cognition.

These APIs expose execution results as observations that AURA consumes.
KIO does NOT implement memory, reasoning, planning, or learning.
KIO emits structured observations that AURA processes.

Every module in KIO uses these interfaces to communicate with AURA.
When AURA is absent, all calls return graceful defaults — never crash.
"""

from __future__ import annotations

import logging
from typing import Any

logger = logging.getLogger(__name__)


def observe(event_type: str, data: dict[str, Any], context: dict[str, Any] | None = None) -> None:
    """Emit an observation from KIO to AURA.

    Observations are structured events that describe what happened during execution.
    AURA consumes these for memory, reasoning, and planning.
    """
    try:
        from mini_kio.core.runtime import aura_emit_observation
        aura_emit_observation(event_type, data, context=context or {})
    except Exception as exc:
        logger.debug("Observation emission skipped: %s", exc)


# =========================================================================
# Request interfaces — KIO asks AURA for cognitive services
# =========================================================================

def request_plan(goal: str, context: dict[str, Any] | None = None) -> None:
    """Request AURA to create a plan for a given goal."""
    observe("aura.request.plan", {"goal": goal, "context": context or {}})


def request_memory(query: str, scope: str = "recent") -> None:
    """Request AURA to retrieve relevant memory for context resolution."""
    observe("aura.request.memory", {"query": query, "scope": scope})


def request_reasoning(query: str, context: dict[str, Any] | None = None) -> None:
    """Request AURA to reason about a situation."""
    observe("aura.request.reasoning", {"query": query, "context": context or {}})


def request_decision(context: dict[str, Any]) -> None:
    """Request AURA to make a decision about an ambiguous execution path."""
    observe("aura.request.decision", {"context": context})


def request_goal(goal: str, priority: str = "normal") -> None:
    """Request AURA to adopt a high-level goal."""
    observe("aura.request.goal", {"goal": goal, "priority": priority})


def request_world_state(query: str | None = None) -> dict[str, Any]:
    """Request AURA's current world model. Returns graceful default if AURA absent."""
    observe("aura.request.world_state", {"query": query or ""})
    return {"success": False, "message": "AURA not available", "state": {}}


def request_preferences(domain: str = "") -> dict[str, Any]:
    """Request AURA's learned preferences for a domain."""
    observe("aura.request.preferences", {"domain": domain})
    return {"success": False, "message": "AURA not available", "preferences": {}}


def request_learning(observation: dict[str, Any]) -> None:
    """Request AURA to learn from an execution observation."""
    observe("aura.request.learning", {"observation": observation})


def request_reflection(context: dict[str, Any]) -> None:
    """Request AURA to reflect on recent execution and suggest improvements."""
    observe("aura.request.reflection", {"context": context})


def request_project(name: str, context: dict[str, Any] | None = None) -> None:
    """Request AURA to create or update a project."""
    observe("aura.request.project", {"name": name, "context": context or {}})


def request_relationships(entity: str) -> None:
    """Request AURA to return relationships for an entity."""
    observe("aura.request.relationships", {"entity": entity})


def request_world_model(domain: str = "") -> None:
    """Request AURA to build/update a world model for a domain."""
    observe("aura.request.world_model", {"domain": domain})


# =========================================================================
# Registration interfaces — KIO reports data to AURA
# =========================================================================

def register_preference(key: str, value: Any) -> None:
    """Register a user preference learned during execution."""
    observe("aura.preference.registered", {"key": key, "value": value})


# =========================================================================
# Report interfaces — KIO sends execution results to AURA
# =========================================================================

def report_execution(result: dict[str, Any]) -> None:
    """Report an execution result to AURA for memory and learning."""
    event_type = "execution.completed" if result.get("success") else "execution.failed"
    if result.get("blocked"):
        event_type = "execution.blocked"
    observe(
        event_type,
        {
            "action": result.get("action", ""),
            "target": result.get("target", ""),
            "status": result.get("outcome_class", ""),
            "message": str(result.get("message", ""))[:500],
        },
        context={
            "source": "execution_fabric",
            "elapsed_ms": result.get("elapsed_ms", 0),
            "provider": result.get("handler", ""),
        },
    )


def report_success(action: str, target: str, details: dict[str, Any] | None = None) -> None:
    """Report a successful execution to AURA."""
    observe(
        "execution.completed",
        {
            "action": action,
            "target": target,
            "status": "SUCCESS",
            **(details or {}),
        },
        context={"source": "execution_fabric"},
    )


def report_failure(
    action: str,
    target: str,
    reason: str,
    failure_class: str = "",
    details: dict[str, Any] | None = None,
) -> None:
    """Report a failed execution to AURA."""
    observe(
        "execution.failed",
        {
            "action": action,
            "target": target,
            "status": "FAILED",
            "reason": reason,
            "failure_class": failure_class,
            **(details or {}),
        },
        context={"source": "execution_fabric"},
    )


def emit_execution_result(result: dict[str, Any]) -> None:
    """Emit a full execution result observation."""
    report_execution(result)


def emit_failure(action: str, target: str, reason: str, **details: Any) -> None:
    """Emit a failure observation."""
    report_failure(action, target, reason, details=details or None)


def emit_success(action: str, target: str, **details: Any) -> None:
    """Emit a success observation."""
    report_success(action, target, details=details or None)


def emit_world_change(change_type: str, data: dict[str, Any]) -> None:
    """Emit a world state change observation."""
    observe(
        "world.changed",
        {"change_type": change_type, "data": data},
        context={"source": "execution_fabric"},
    )


__all__ = [
    "observe", "request_plan", "request_memory", "request_reasoning",
    "request_decision", "request_goal", "request_world_state",
    "request_preferences", "request_learning", "request_reflection",
    "request_project", "request_relationships", "request_world_model",
    "register_preference", "report_execution", "report_success",
    "report_failure", "emit_execution_result", "emit_failure",
    "emit_success", "emit_world_change",
]
