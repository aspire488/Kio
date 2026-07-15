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

        return {"success": False, "message": f"WorkflowProvider: unknown action {action}"}

    def verify(self, action: str, result: dict[str, Any]) -> dict[str, Any]:
        result.setdefault("probe_used", "workflow_action")
        if result.get("success"):
            result.setdefault("verification_status", "passed")
            result.setdefault("outcome_class", "SUCCESS")
        else:
            result.setdefault("verification_status", "failed")
            result.setdefault("outcome_class", "FAILURE")
        return result
