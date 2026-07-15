"""Execution workflow engine — multi-step, parallel, checkpoints, retries, progress."""

from __future__ import annotations

import asyncio
import logging
import time
import uuid
from dataclasses import dataclass, field
from enum import Enum
from typing import Any, Callable

logger = logging.getLogger("mini_kio.execution.engine")


class WorkflowStatus(Enum):
    PENDING = "pending"
    RUNNING = "running"
    COMPLETED = "completed"
    FAILED = "failed"
    CANCELLED = "cancelled"
    PAUSED = "paused"
    ROLLED_BACK = "rolled_back"


class StepStatus(Enum):
    PENDING = "pending"
    RUNNING = "running"
    COMPLETED = "completed"
    FAILED = "failed"
    SKIPPED = "skipped"
    CANCELLED = "cancelled"


@dataclass
class WorkflowStep:
    id: str = field(default_factory=lambda: str(uuid.uuid4())[:8])
    name: str = ""
    action: str = ""
    target: str = ""
    params: dict[str, Any] = field(default_factory=dict)
    status: StepStatus = StepStatus.PENDING
    result: dict[str, Any] | None = None
    error: str | None = None
    started_at: float = 0.0
    completed_at: float = 0.0
    duration_ms: float = 0.0
    retry_count: int = 0
    max_retries: int = 2
    depends_on: list[str] = field(default_factory=list)
    timeout_s: float = 60.0
    checkpoint_id: str | None = None
    condition: str | None = None
    rollback_action: str | None = None
    rollback_target: str = ""
    rollback_params: dict[str, Any] = field(default_factory=dict)
    approval_required: bool = False
    approved: bool = False
    skipped: bool = False


@dataclass
class WorkflowExecution:
    id: str = field(default_factory=lambda: f"wf_{uuid.uuid4().hex[:12]}")
    name: str = ""
    status: WorkflowStatus = WorkflowStatus.PENDING
    steps: list[WorkflowStep] = field(default_factory=list)
    created_at: float = field(default_factory=time.time)
    started_at: float = 0.0
    completed_at: float = 0.0
    duration_ms: float = 0.0
    error: str | None = None
    context: dict[str, Any] = field(default_factory=dict)
    checkpoint_ids: list[str] = field(default_factory=list)
    parallel_groups: list[list[str]] = field(default_factory=list)
    approval_pending: list[str] = field(default_factory=list)
    rollback_steps: list[dict[str, Any]] = field(default_factory=list)
    persistence_path: str | None = None


class WorkflowEngine:
    """Executes multi-step workflows with parallel steps, retries, and checkpointing.

    Steps within the same parallel group run concurrently.
    Steps with dependencies wait for their upstream steps to complete.
    """

    def __init__(self, execute_fn: Callable[..., dict[str, Any]] | None = None) -> None:
        self._execute_fn = execute_fn
        self._executions: dict[str, WorkflowExecution] = {}
        self._progress_callbacks: list[Callable] = []

    def set_executor(self, fn: Callable[..., dict[str, Any]]) -> None:
        self._execute_fn = fn

    def on_progress(self, callback: Callable) -> None:
        self._progress_callbacks.append(callback)

    def create_workflow(self, name: str, steps: list[dict[str, Any]]) -> WorkflowExecution:
        wf = WorkflowExecution(name=name)
        for s in steps:
            step = WorkflowStep(
                name=s.get("name", s.get("action", "step")),
                action=s["action"],
                target=s.get("target", ""),
                params=s.get("params", {}),
                max_retries=s.get("max_retries", 2),
                depends_on=s.get("depends_on", []),
                timeout_s=s.get("timeout_s", 60.0),
                condition=s.get("condition"),
                rollback_action=s.get("rollback_action"),
                rollback_target=s.get("rollback_target", ""),
                rollback_params=s.get("rollback_params", {}),
                approval_required=s.get("approval_required", False),
            )
            wf.steps.append(step)
            if step.approval_required:
                wf.approval_pending.append(step.id)
        self._executions[wf.id] = wf
        return wf

    def get_workflow(self, wf_id: str) -> WorkflowExecution | None:
        return self._executions.get(wf_id)

    def list_workflows(self) -> list[WorkflowExecution]:
        return list(self._executions.values())

    def cancel_workflow(self, wf_id: str) -> bool:
        wf = self._executions.get(wf_id)
        if wf is None or wf.status not in (WorkflowStatus.PENDING, WorkflowStatus.RUNNING):
            return False
        wf.status = WorkflowStatus.CANCELLED
        for step in wf.steps:
            if step.status in (StepStatus.PENDING, StepStatus.RUNNING):
                step.status = StepStatus.CANCELLED
        wf.completed_at = time.time()
        return True

    def pause_workflow(self, wf_id: str) -> bool:
        wf = self._executions.get(wf_id)
        if wf is None or wf.status != WorkflowStatus.RUNNING:
            return False
        wf.status = WorkflowStatus.PAUSED
        return True

    def resume_workflow(self, wf_id: str) -> bool:
        wf = self._executions.get(wf_id)
        if wf is None or wf.status != WorkflowStatus.PAUSED:
            return False
        wf.status = WorkflowStatus.RUNNING
        return True

    async def execute(self, wf_id: str) -> WorkflowExecution:
        wf = self._executions.get(wf_id)
        if wf is None:
            raise ValueError(f"Unknown workflow: {wf_id}")
        if self._execute_fn is None:
            raise RuntimeError("No executor set. Call set_executor() first.")

        wf.status = WorkflowStatus.RUNNING
        wf.started_at = time.time()
        logger.info("Workflow '%s' started (%d steps)", wf.name, len(wf.steps))

        step_map: dict[str, WorkflowStep] = {s.id: s for s in wf.steps}
        completed: set[str] = set()
        skipped: set[str] = set()
        executed_rollbacks: list[dict[str, Any]] = []

        try:
            while len(completed) + len(skipped) < len(wf.steps):
                if wf.status == WorkflowStatus.CANCELLED:
                    break
                if wf.status == WorkflowStatus.PAUSED:
                    await asyncio.sleep(0.5)
                    continue

                ready = []
                for step in wf.steps:
                    if step.id in completed or step.id in skipped or step.status == StepStatus.RUNNING:
                        continue
                    if not all(dep in completed for dep in step.depends_on):
                        continue
                    if step.approval_required and not step.approved:
                        if step.id not in wf.approval_pending:
                            wf.approval_pending.append(step.id)
                        continue
                    if step.condition:
                        passed = self._evaluate_condition(step.condition, wf.context)
                        if not passed:
                            step.status = StepStatus.SKIPPED
                            step.skipped = True
                            skipped.add(step.id)
                            continue
                    ready.append(step)

                if not ready and len(completed) + len(skipped) < len(wf.steps):
                    pending_approval = [s for s in wf.steps if s.approval_required and not s.approved and s.id not in completed]
                    blocked = [s for s in wf.steps if s.id not in completed and s.id not in skipped]
                    deps = [s.id for s in blocked if not all(d in completed for d in s.depends_on)]
                    if not pending_approval and deps:
                        logger.warning("Workflow deadlocked — steps %s waiting on uncompleted deps", deps)
                        wf.error = f"Deadlock: steps {deps} waiting on uncompleted dependencies"
                        wf.status = WorkflowStatus.FAILED
                        break
                    await asyncio.sleep(0.1)
                    continue

                # Execute ready steps (parallel if multiple)
                tasks = [self._execute_step(wf, step) for step in ready]
                results = await asyncio.gather(*tasks, return_exceptions=True)

                for step, result in zip(ready, results):
                    if isinstance(result, Exception):
                        step.status = StepStatus.FAILED
                        step.error = str(result)
                    elif isinstance(result, dict) and not result.get("success", True):
                        step.status = StepStatus.FAILED
                        step.error = result.get("message", "Unknown error")
                        step.result = result
                    else:
                        step.status = StepStatus.COMPLETED
                        step.result = result if isinstance(result, dict) else {"success": True}
                        if result and isinstance(result, dict):
                            wf.context.update(result)

                    if step.status == StepStatus.COMPLETED:
                        completed.add(step.id)
                    else:
                        skipped.add(step.id)

                    if step.rollback_action and step.status == StepStatus.COMPLETED:
                        wf.rollback_steps.append({
                            "action": step.rollback_action,
                            "target": step.rollback_target,
                            "params": step.rollback_params,
                        })
                    self._notify_progress(wf, step)
                    self._save_checkpoint(wf)

            # Final status
            failed = [s for s in wf.steps if s.status == StepStatus.FAILED]
            if failed:
                wf.status = WorkflowStatus.FAILED
                wf.error = f"{len(failed)} step(s) failed: {', '.join(s.name for s in failed[:3])}"
                await self._rollback(wf, executed_rollbacks)
            elif wf.status != WorkflowStatus.CANCELLED:
                wf.status = WorkflowStatus.COMPLETED
                logger.info("Workflow '%s' completed (%d/%d steps)", wf.name,
                            len(completed), len(wf.steps))
            self._persist(wf)

        except asyncio.CancelledError:
            wf.status = WorkflowStatus.CANCELLED
            await self._rollback(wf, executed_rollbacks)
        except Exception as exc:
            wf.status = WorkflowStatus.FAILED
            wf.error = str(exc)
            logger.exception("Workflow '%s' failed: %s", wf.name, exc)
            await self._rollback(wf, executed_rollbacks)

        wf.completed_at = time.time()
        wf.duration_ms = (wf.completed_at - wf.started_at) * 1000
        self._persist(wf)
        return wf

    def approve_step(self, step_id: str) -> bool:
        for wf in self._executions.values():
            for step in wf.steps:
                if step.id == step_id:
                    step.approved = True
                    step.approval_required = False
                    if step_id in wf.approval_pending:
                        wf.approval_pending.remove(step_id)
                    return True
        return False

    def reject_step(self, step_id: str) -> bool:
        for wf in self._executions.values():
            for step in wf.steps:
                if step.id == step_id:
                    step.status = StepStatus.SKIPPED
                    step.skipped = True
                    step.approval_required = False
                    if step_id in wf.approval_pending:
                        wf.approval_pending.remove(step_id)
                    return True
        return False

    def _evaluate_condition(self, condition: str, context: dict[str, Any]) -> bool:
        if condition.startswith("context."):
            key = condition[8:]
            return bool(context.get(key))
        if condition.startswith("not context."):
            key = condition[12:]
            return not bool(context.get(key))
        if condition == "true":
            return True
        if condition == "false":
            return False
        return True

    async def _rollback(self, wf: WorkflowExecution, executed: list[dict[str, Any]]) -> None:
        if not wf.rollback_steps:
            return
        logger.info("Rolling back %d step(s) for workflow '%s'", len(wf.rollback_steps), wf.name)
        for rb in reversed(wf.rollback_steps):
            try:
                if self._execute_fn:
                    self._execute_fn(rb["action"], rb["target"], **rb.get("params", {}))
                executed.append(rb)
            except Exception as exc:
                logger.warning("Rollback step '%s' failed: %s", rb["action"], exc)
        wf.status = WorkflowStatus.ROLLED_BACK

    def _save_checkpoint(self, wf: WorkflowExecution) -> None:
        cp_id = f"cp_{wf.id}_{int(time.time())}"
        if cp_id not in wf.checkpoint_ids:
            wf.checkpoint_ids.append(cp_id)

    def _persist(self, wf: WorkflowExecution) -> None:
        import json
        path = wf.persistence_path
        if path is None:
            return
        try:
            data = {
                "id": wf.id, "name": wf.name, "status": wf.status.value,
                "error": wf.error, "duration_ms": wf.duration_ms,
                "checkpoint_ids": wf.checkpoint_ids,
                "steps": [
                    {"id": s.id, "name": s.name, "action": s.action, "target": s.target,
                     "status": s.status.value, "error": s.error, "duration_ms": s.duration_ms,
                     "retry_count": s.retry_count}
                    for s in wf.steps
                ],
            }
            with open(path, "w", encoding="utf-8") as f:
                json.dump(data, f, ensure_ascii=False, default=str)
        except Exception as exc:
            logger.warning("Failed to persist workflow '%s': %s", wf.id, exc)

    def load_persisted(self, path: str) -> WorkflowExecution | None:
        import json
        try:
            with open(path, "r", encoding="utf-8") as f:
                data = json.load(f)
        except Exception as exc:
            logger.warning("Failed to load workflow from '%s': %s", path, exc)
            return None
        wf = WorkflowExecution(
            id=data.get("id", f"wf_{uuid.uuid4().hex[:12]}"),
            name=data.get("name", "recovered"),
            persistence_path=path,
        )
        for sd in data.get("steps", []):
            step = WorkflowStep(
                id=sd.get("id", str(uuid.uuid4())[:8]),
                name=sd.get("name", ""),
                action=sd.get("action", ""),
                target=sd.get("target", ""),
                status=StepStatus(sd.get("status", "pending")),
            )
            wf.steps.append(step)
        self._executions[wf.id] = wf
        return wf

    async def execute_stream(self, wf_id: str):
        """Async generator yielding progress updates during execution."""
        execute_task = asyncio.create_task(self.execute(wf_id))
        wf = self._executions.get(wf_id)
        while not execute_task.done():
            if wf:
                yield self.get_progress(wf_id)
            await asyncio.sleep(0.5)
        yield self.get_progress(wf_id)
        await execute_task

    def execution_graph(self, wf_id: str) -> dict[str, Any]:
        wf = self._executions.get(wf_id)
        if wf is None:
            return {"status": "not_found"}
        nodes = []
        edges = []
        for step in wf.steps:
            nodes.append({
                "id": step.id, "name": step.name, "action": step.action,
                "status": step.status.value, "duration_ms": step.duration_ms,
            })
            for dep in step.depends_on:
                edges.append({"from": dep, "to": step.id})
        return {
            "workflow_id": wf.id, "name": wf.name, "status": wf.status.value,
            "nodes": nodes, "edges": edges,
        }

    async def _execute_step(self, wf: WorkflowExecution, step: WorkflowStep) -> dict[str, Any]:
        step.status = StepStatus.RUNNING
        step.started_at = time.time()
        logger.info("  Step '%s' (%s %s)", step.name, step.action, step.target)

        last_error: Exception | None = None
        for attempt in range(1 + step.max_retries):
            try:
                result = await asyncio.wait_for(
                    self._run_step(step),
                    timeout=step.timeout_s,
                )
                step.retry_count = attempt
                step.duration_ms = (time.time() - step.started_at) * 1000
                step.completed_at = time.time()
                return result
            except asyncio.TimeoutError:
                last_error = TimeoutError(f"Step timed out after {step.timeout_s}s")
                logger.warning("  Step '%s' timeout (attempt %d/%d)", step.name, attempt + 1, step.max_retries + 1)
            except Exception as exc:
                last_error = exc
                logger.warning("  Step '%s' failed (attempt %d/%d): %s", step.name, attempt + 1,
                               step.max_retries + 1, exc)
            if attempt < step.max_retries:
                await asyncio.sleep(min(2 ** attempt, 10))

        step.error = str(last_error)
        step.duration_ms = (time.time() - step.started_at) * 1000
        step.completed_at = time.time()
        return {"success": False, "message": str(last_error)}

    async def _run_step(self, step: WorkflowStep) -> dict[str, Any]:
        if self._execute_fn is None:
            return {"success": False, "message": "No executor"}
        loop = asyncio.get_event_loop()
        return await loop.run_in_executor(
            None, self._execute_fn, step.action, step.target, **step.params
        )

    def _notify_progress(self, wf: WorkflowExecution, step: WorkflowStep) -> None:
        completed = sum(1 for s in wf.steps if s.status == StepStatus.COMPLETED)
        total = len(wf.steps)
        for cb in self._progress_callbacks:
            try:
                cb({
                    "workflow_id": wf.id,
                    "workflow_name": wf.name,
                    "step_name": step.name,
                    "step_status": step.status.value,
                    "progress": f"{completed}/{total}",
                    "percent": int(completed / total * 100) if total else 0,
                })
            except Exception:
                pass

    def get_progress(self, wf_id: str) -> dict[str, Any]:
        wf = self._executions.get(wf_id)
        if wf is None:
            return {"status": "not_found"}
        completed = sum(1 for s in wf.steps if s.status == StepStatus.COMPLETED)
        total = len(wf.steps)
        failed = sum(1 for s in wf.steps if s.status == StepStatus.FAILED)
        return {
            "workflow_id": wf.id,
            "name": wf.name,
            "status": wf.status.value,
            "steps_completed": completed,
            "steps_total": total,
            "steps_failed": failed,
            "progress_percent": int(completed / total * 100) if total else 0,
            "duration_ms": wf.duration_ms,
            "error": wf.error,
        }
