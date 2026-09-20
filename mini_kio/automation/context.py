"""Execution context for a single automation run."""

from __future__ import annotations

import time
import uuid
from dataclasses import dataclass, field
from typing import Any


@dataclass
class StepResult:
    """Result of executing a single step."""
    step_id: str
    success: bool
    outputs: dict[str, Any] = field(default_factory=dict)
    error: str | None = None
    elapsed_ms: float = 0.0
    retry_count: int = 0
    verification_passed: bool | None = None
    blocked: bool = False
    blocking_reason: str | None = None

    def to_dict(self) -> dict[str, Any]:
        return {
            "step_id": self.step_id,
            "success": self.success,
            "outputs": self.outputs,
            "error": self.error,
            "elapsed_ms": self.elapsed_ms,
            "retry_count": self.retry_count,
            "verification_passed": self.verification_passed,
            "blocked": self.blocked,
            "blocking_reason": self.blocking_reason,
        }


@dataclass
class AutomationExecutionContext:
    """Mutable state for one automation execution run.

    Holds resolved inputs, step outputs, and execution metadata.
    Thread-safe: all mutations go through _lock.
    """
    run_id: str = field(default_factory=lambda: f"auto_{uuid.uuid4().hex[:12]}")
    template_id: str = ""
    started_at: float = field(default_factory=time.time)
    completed_at: float = 0.0
    status: str = "pending"  # pending, running, completed, failed, blocked
    inputs: dict[str, Any] = field(default_factory=dict)
    config: dict[str, Any] = field(default_factory=dict)
    trigger_data: dict[str, Any] = field(default_factory=dict)
    step_results: dict[str, StepResult] = field(default_factory=dict)
    step_outputs: dict[str, dict[str, Any]] = field(default_factory=dict)
    final_outputs: dict[str, Any] = field(default_factory=dict)
    error: str | None = None
    security_classification: str = "read_only"
    user_confirmation_required: bool = False
    capabilities_available: list[str] = field(default_factory=list)
    capabilities_missing: list[str] = field(default_factory=list)
    credentials_status: dict[str, str] = field(default_factory=dict)
    verification_results: list[dict[str, Any]] = field(default_factory=list)

    def set_step_output(self, step_id: str, output_name: str, value: Any) -> None:
        """Store a step output for reference resolution by downstream steps."""
        if step_id not in self.step_outputs:
            self.step_outputs[step_id] = {}
        self.step_outputs[step_id][output_name] = value

    def resolve_ref(self, ref: str) -> Any:
        """Resolve a {{ steps.X.output_name }} or {{ inputs.X }} or {{ config.X }} reference.

        Returns the resolved value, or the raw reference string if unresolvable.
        """
        import re
        m = re.match(r"^steps\.([a-z0-9_]+)\.([a-z0-9_]+)$", ref)
        if m:
            step_id, output_name = m.group(1), m.group(2)
            step_out = self.step_outputs.get(step_id, {})
            if output_name in step_out:
                return step_out[output_name]
            return f"{{{{ steps.{step_id}.{output_name} }}}}"

        m = re.match(r"^inputs\.([a-z0-9_]+)$", ref)
        if m:
            key = m.group(1)
            return self.inputs.get(key, self.config.get(key, f"{{{{ inputs.{key} }}}}"))

        m = re.match(r"^config\.([a-z0-9_]+)$", ref)
        if m:
            key = m.group(1)
            return self.config.get(key, f"{{{{ config.{key} }}}}")

        m = re.match(r"^trigger\.([a-z0-9_]+)$", ref)
        if m:
            key = m.group(1)
            return self.trigger_data.get(key, f"{{{{ trigger.{key} }}}}")

        return f"{{{{ {ref} }}}}"

    def resolve_value(self, value: Any) -> Any:
        """Recursively resolve all {{ }} references in a value."""
        import re
        if isinstance(value, str):
            # Full-match single reference: return raw value (no string wrapping)
            full = re.fullmatch(r"\{\{\s*([a-z0-9_]+(?:\.[a-z0-9_]+)*)\s*\}\}", value.strip())
            if full:
                return self.resolve_ref(full.group(1))
            # Embedded references: substitute inline
            def _sub(m: re.Match) -> str:
                resolved = self.resolve_ref(m.group(1))
                return str(resolved) if not isinstance(resolved, (dict, list)) else str(resolved)
            return re.sub(r"\{\{\s*([a-z0-9_]+(?:\.[a-z0-9_]+)*)\s*\}\}", _sub, value)
        if isinstance(value, dict):
            return {k: self.resolve_value(v) for k, v in value.items()}
        if isinstance(value, list):
            return [self.resolve_value(v) for v in value]
        return value

    def mark_complete(self, success: bool, error: str | None = None) -> None:
        self.completed_at = time.time()
        self.status = "completed" if success else "failed"
        self.error = error

    @property
    def duration_ms(self) -> float:
        end = self.completed_at if self.completed_at else time.time()
        return (end - self.started_at) * 1000

    def to_dict(self) -> dict[str, Any]:
        return {
            "run_id": self.run_id,
            "template_id": self.template_id,
            "status": self.status,
            "duration_ms": self.duration_ms,
            "step_results": {k: v.to_dict() for k, v in self.step_results.items()},
            "final_outputs": self.final_outputs,
            "error": self.error,
            "capabilities_available": self.capabilities_available,
            "capabilities_missing": self.capabilities_missing,
            "credentials_status": self.credentials_status,
            "verification_results": self.verification_results,
        }
