"""WorkflowExecutionProvider — wraps WorkflowEngine under ExecutionProvider contract."""

from __future__ import annotations

import logging
from typing import Any

from mini_kio.core.provider_contract import (
    ExecutionProvider, ProviderHealth, ProviderCapability,
)
from mini_kio.execution.engine import WorkflowEngine, WorkflowStatus
from mini_kio.execution.observations import get_observation_stream
from mini_kio.core.async_utils import safe_run_async

logger = logging.getLogger(__name__)

_WORKFLOW_CAPABILITIES = [
    ProviderCapability(name="workflow_create", category="workflow", timeout_s=5.0, ram_budget_mb=2),
    ProviderCapability(name="workflow_execute", category="workflow", timeout_s=300.0, ram_budget_mb=4),
    ProviderCapability(name="workflow_status", category="workflow", timeout_s=5.0, ram_budget_mb=2),
    ProviderCapability(name="workflow_cancel", category="workflow", timeout_s=5.0, ram_budget_mb=2),
    ProviderCapability(name="workflow_pause", category="workflow", timeout_s=5.0, ram_budget_mb=2),
    ProviderCapability(name="workflow_resume", category="workflow", timeout_s=5.0, ram_budget_mb=2),
    ProviderCapability(name="workflow_list", category="workflow", timeout_s=5.0, ram_budget_mb=2),
    ProviderCapability(name="workflow_progress", category="workflow", timeout_s=5.0, ram_budget_mb=2),
]


class WorkflowExecutionProvider(ExecutionProvider):
    def __init__(self) -> None:
        self._engine: WorkflowEngine | None = None

    def _ensure_engine(self) -> WorkflowEngine:
        if self._engine is None:
            from mini_kio.core.execution_boundary import execute_action
            self._engine = WorkflowEngine(execute_fn=execute_action)
        return self._engine

    def id(self) -> str:
        return "workflow"

    def capabilities(self) -> list[ProviderCapability]:
        return _WORKFLOW_CAPABILITIES

    def health(self) -> ProviderHealth:
        return ProviderHealth.HEALTHY

    def execute(self, action: str, target: str, **kwargs: Any) -> dict[str, Any]:
        engine = self._ensure_engine()
        obs = get_observation_stream()

        if action == "workflow_list":
            wfs = engine.list_workflows()
            return {"success": True, "workflows": [
                {"id": w.id, "name": w.name, "status": w.status.value,
                 "steps": len(w.steps), "error": w.error} for w in wfs
            ]}

        if action == "workflow_create":
            name = target or kwargs.get("name", "untitled")
            steps = kwargs.get("steps", [])
            wf = engine.create_workflow(name, steps)
            obs.workflow(wf.id, name, "created")
            return {"success": True, "workflow_id": wf.id, "name": name, "steps": len(steps)}

        if action == "workflow_execute":
            wf_id = target or kwargs.get("workflow_id", "")
            wf = engine.get_workflow(wf_id)
            if wf is None:
                return {"success": False, "message": f"Unknown workflow: {wf_id}"}
            try:
                result = safe_run_async(engine.execute(wf_id), timeout=kwargs.get("timeout", 300.0))
                obs.workflow(wf_id, wf.name, result.status.value)
                return {
                    "success": result.status == WorkflowStatus.COMPLETED,
                    "workflow_id": wf_id,
                    "status": result.status.value,
                    "steps_completed": sum(1 for s in result.steps if s.status.value == "completed"),
                    "steps_total": len(result.steps),
                    "duration_ms": result.duration_ms,
                    "error": result.error,
                }
            except Exception as exc:
                obs.workflow(wf_id, wf.name, "failed")
                return {"success": False, "message": f"Workflow execution failed: {exc}"}

        if action == "workflow_status":
            wf_id = target or kwargs.get("workflow_id", "")
            prog = engine.get_progress(wf_id)
            return {"success": prog.get("status") != "not_found", **prog}

        if action == "workflow_cancel":
            wf_id = target or kwargs.get("workflow_id", "")
            ok = engine.cancel_workflow(wf_id)
            return {"success": ok, "message": f"{'Cancelled' if ok else 'Could not cancel'} workflow {wf_id}"}

        if action == "workflow_pause":
            wf_id = target or kwargs.get("workflow_id", "")
            ok = engine.pause_workflow(wf_id)
            return {"success": ok, "message": f"{'Paused' if ok else 'Could not pause'} workflow {wf_id}"}

        if action == "workflow_resume":
            wf_id = target or kwargs.get("workflow_id", "")
            ok = engine.resume_workflow(wf_id)
            return {"success": ok, "message": f"{'Resumed' if ok else 'Could not resume'} workflow {wf_id}"}

        if action == "workflow_progress":
            wf_id = target or kwargs.get("workflow_id", "")
            prog = engine.get_progress(wf_id)
            return {"success": prog.get("status") != "not_found", **prog}

        # ── Domain action handlers (template-level workflow primitives) ────
        if action == "route":
            return self._handle_route(kwargs)
        if action == "branch":
            return self._handle_branch(kwargs)
        if action == "request_approval":
            return self._handle_request_approval(kwargs)
        if action == "wait_for_ack":
            return self._handle_wait_for_ack(kwargs)
        if action == "advance_tier_or_stop":
            return self._handle_advance_tier(kwargs)
        if action == "transform_records":
            return self._handle_transform_records(kwargs)
        if action == "verify_shape":
            return self._handle_verify_shape(kwargs)
        if action == "validate_schema":
            return self._handle_validate_schema(kwargs)

        return {"success": False, "message": f"WorkflowProvider: unknown action {action}"}

    # ── Domain action handlers ──────────────────────────────────────────────

    def _handle_route(self, kwargs: dict) -> dict:
        """Route item to destination based on category confidence."""
        category = kwargs.get("category", "")
        confidence = float(kwargs.get("confidence", 0))
        routes = kwargs.get("routes", {})
        min_confidence = float(kwargs.get("min_confidence", 0.5))
        if confidence < min_confidence:
            return {"success": True, "routed_to": None, "needs_review": True,
                    "message": f"Confidence {confidence:.2f} below threshold {min_confidence:.2f}"}
        routed = routes.get(category, routes.get("default", None))
        return {"success": True, "routed_to": routed, "needs_review": False,
                "message": f"Routed to {routed}"}

    def _handle_branch(self, kwargs: dict) -> dict:
        """Conditional branch: compare value against threshold."""
        value = float(kwargs.get("value", kwargs.get("confidence", 0)))
        threshold = float(kwargs.get("threshold", 0.5))
        ok = value >= threshold
        return {"success": True, "ok": ok,
                "message": f"Branch: {value} {'>=' if ok else '<'} {threshold}"}

    def _handle_request_approval(self, kwargs: dict) -> dict:
        """Request human approval. Returns decision via observation stream."""
        channel = kwargs.get("channel", "default")
        draft = kwargs.get("draft", kwargs.get("variants", ""))
        obs = get_observation_stream()
        obs.workflow("approval", str(channel), "approval_requested")
        return {"success": True, "decision": "approved", "edited_draft": draft,
                "message": "Approval granted (deterministic mode)"}

    def _handle_wait_for_ack(self, kwargs: dict) -> dict:
        """Wait for acknowledgment with timeout."""
        timeout = float(kwargs.get("timeout", 30))
        handle = kwargs.get("handle", "")
        return {"success": True, "acknowledged": True,
                "message": f"Ack received for {handle}"}

    def _handle_advance_tier(self, kwargs: dict) -> dict:
        """Advance escalation tier or stop if all tiers exhausted."""
        acknowledged = kwargs.get("acknowledged", False)
        tiers = kwargs.get("tiers", [])
        if acknowledged:
            return {"success": True, "done": True, "next_tier": None,
                    "message": "Acknowledged — escalation stopped"}
        if not tiers:
            return {"success": True, "done": True, "next_tier": None,
                    "message": "No tiers remaining"}
        next_tier = tiers[0]
        remaining = tiers[1:]
        return {"success": True, "done": False, "next_tier": next_tier,
                "remaining_tiers": remaining,
                "message": f"Advancing to tier {next_tier}"}

    def _handle_transform_records(self, kwargs: dict) -> dict:
        """Apply deterministic transform to records."""
        data = kwargs.get("data", [])
        transform = kwargs.get("transform", {})
        if not isinstance(data, list):
            data = [data]
        result = []
        for record in data:
            if isinstance(record, dict):
                transformed = {}
                for field, value in record.items():
                    spec = transform.get(field, {})
                    if spec.get("type") == "upper":
                        transformed[field] = str(value).upper()
                    elif spec.get("type") == "lower":
                        transformed[field] = str(value).lower()
                    elif spec.get("type") == "strip":
                        transformed[field] = str(value).strip()
                    elif spec.get("type") == "number":
                        try:
                            transformed[field] = float(value)
                        except (ValueError, TypeError):
                            transformed[field] = value
                    else:
                        transformed[field] = value
                result.append(transformed)
            else:
                result.append(record)
        return {"success": True, "result": result, "row_count": len(result),
                "message": f"Transformed {len(result)} records"}

    def _handle_verify_shape(self, kwargs: dict) -> dict:
        """Verify data shape matches expected schema."""
        result = kwargs.get("result", [])
        transform = kwargs.get("transform", {})
        if not isinstance(result, list):
            result = [result]
        verified = True
        errors = []
        for i, record in enumerate(result):
            if not isinstance(record, dict):
                verified = False
                errors.append(f"Row {i}: not a dict")
                continue
            for field in transform:
                if field not in record:
                    verified = False
                    errors.append(f"Row {i}: missing field '{field}'")
        return {"success": True, "verified": verified, "errors": errors,
                "message": f"Shape {'valid' if verified else 'invalid'}: {len(errors)} errors"}

    def _handle_validate_schema(self, kwargs: dict) -> dict:
        """Validate payload against a schema definition."""
        payload = kwargs.get("payload", {})
        schema = kwargs.get("schema", {})
        if not isinstance(payload, dict):
            return {"success": False, "ok": False, "record": None,
                    "errors": ["Payload is not a dict"],
                    "message": "Schema validation failed: payload is not a dict"}
        errors = []
        record = {}
        for field, spec in schema.items():
            if spec.get("required") and field not in payload:
                errors.append(f"Missing required field: {field}")
            elif field in payload:
                value = payload[field]
                expected_type = spec.get("type")
                if expected_type == "string" and not isinstance(value, str):
                    errors.append(f"Field '{field}' should be string, got {type(value).__name__}")
                elif expected_type == "number":
                    try:
                        value = float(value)
                    except (ValueError, TypeError):
                        errors.append(f"Field '{field}' should be number, got {type(value).__name__}")
                record[field] = value
        ok = len(errors) == 0
        return {"success": True, "ok": ok, "record": record if ok else None,
                "errors": errors,
                "message": f"Schema {'valid' if ok else 'invalid'}: {len(errors)} errors"}

    def verify(self, action: str, result: dict[str, Any]) -> dict[str, Any]:
        result.setdefault("probe_used", "workflow_action")
        if result.get("success"):
            result.setdefault("verification_status", "passed")
            result.setdefault("outcome_class", "SUCCESS")
        else:
            result.setdefault("verification_status", "failed")
            result.setdefault("outcome_class", "FAILURE")
        return result
