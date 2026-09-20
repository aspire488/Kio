"""AutomationEngine — orchestrator for all 63 canonical YAML workflows.

Single entry point. Ties together:
- TemplateStore (load/validate YAML)
- CapabilityResolver (map capabilities to providers)
- CredentialChecker (check credential availability)
- SecurityBridge (enforce security classification)
- VerificationBridge (verify observable side effects)
- StepRunner (execute steps through execution_boundary)
- StatusRegistry (track per-template status)
- RuntimeCapabilityChecker (runtime availability)

No second runtime. No second NLU. No second security system. No second
credential vault. No second MCP gateway. No second event bus.
"""

from __future__ import annotations

import logging
import time
from pathlib import Path
from typing import Any

from mini_kio.automation.template_store import TemplateStore, TemplateRecord
from mini_kio.automation.context import AutomationExecutionContext, StepResult
from mini_kio.automation.capability_resolver import CapabilityResolver, CredentialChecker
from mini_kio.automation.step_runner import StepRunner
from mini_kio.automation.bridges import SecurityBridge, VerificationBridge, CredentialBridge
from mini_kio.automation.status import StatusRegistry, RuntimeCapabilityChecker

logger = logging.getLogger(__name__)


class AutomationEngine:
    """Generic automation engine for all 63 KIO canonical YAML templates.

    ONE engine, not 63 individual implementations. Every step routes through
    the existing KIO execution_boundary.py. Every credential goes through
    CredentialVault. Every security check enforces the YAML classification
    against KIO policy.

    Usage:
        engine = AutomationEngine()
        engine.load_templates()
        result = await engine.execute("browser.structured_extract", inputs={...})
    """

    def __init__(self, library_root: Path | None = None) -> None:
        self._store = TemplateStore(library_root)
        self._cap_resolver = CapabilityResolver()
        self._cred_checker = CredentialChecker()
        self._cred_bridge = CredentialBridge()
        self._sec_bridge = SecurityBridge()
        self._ver_bridge = VerificationBridge()
        self._step_runner = StepRunner()
        self._status = StatusRegistry()
        self._rt_checker = RuntimeCapabilityChecker()
        self._loaded = False

    # ── Loading ──────────────────────────────────────────────────────

    def load_templates(self) -> int:
        """Load all YAML templates from the library.

        Returns count of successfully loaded templates.
        """
        count = self._store.load()
        self._loaded = True

        # Initialize status for each loaded template
        for record in self._store.all_records():
            tid = record.template_id
            current = self._status.get_status(tid)
            if current["execution_status"] == "candidate":
                # Check capabilities and credentials
                caps = record.capabilities_required
                missing = self._cap_resolver.get_missing_capabilities(caps)
                if missing:
                    reason = self._cap_resolver.get_blocking_reason(missing)
                    self._status.record_blocked(tid, reason)
                    self._status.set_status(
                        tid,
                        capability_status="missing",
                        credential_status="checked",
                    )
                else:
                    self._status.set_status(
                        tid,
                        execution_status="structurally_valid",
                        capability_status="available",
                    )

        logger.info(
            "[ENGINE] loaded %d templates, %d blocked, %d errors",
            count,
            len([t for t in self._store.all_records()
                 if self._status.get_status(t.template_id)["execution_status"] == "blocked"]),
            len(self._store.load_errors),
        )
        return count

    # ── Query ────────────────────────────────────────────────────────

    @property
    def template_count(self) -> int:
        return self._store.count

    def list_templates(self) -> list[str]:
        return self._store.list_ids()

    def get_template(self, template_id: str) -> TemplateRecord | None:
        return self._store.get(template_id)

    def get_status(self, template_id: str) -> dict[str, Any]:
        return self._status.get_status(template_id)

    def all_statuses(self) -> dict[str, dict[str, Any]]:
        return self._status.all_statuses()

    def status_summary(self) -> dict[str, Any]:
        """Summary of all template statuses."""
        counts = self._status.summary()
        rt_caps = self._rt_checker.check_all()
        return {
            "total_templates": self._store.count,
            "loaded": self._loaded,
            "statuses": counts,
            "runtime_capabilities": {
                k: v["available"] for k, v in rt_caps.items()
            },
            "load_errors": len(self._store.load_errors),
        }

    def runtime_capabilities(self) -> dict[str, dict[str, Any]]:
        """Full runtime capability check."""
        return self._rt_checker.check_all()

    # ── Execution ────────────────────────────────────────────────────

    async def execute(
        self,
        template_id: str,
        inputs: dict[str, Any] | None = None,
        config: dict[str, Any] | None = None,
        trigger_data: dict[str, Any] | None = None,
    ) -> dict[str, Any]:
        """Execute an automation template by ID.

        Returns execution result dict with:
        - success: bool
        - run_id: str
        - template_id: str
        - outputs: dict
        - steps: list of step results
        - duration_ms: float
        - error: str (if failed)
        - blocked: bool
        - blocking_reason: str (if blocked)
        """
        record = self._store.get(template_id)
        if record is None:
            return {
                "success": False,
                "error": f"Template not found: {template_id}",
                "blocked": False,
            }

        # Create execution context
        ctx = AutomationExecutionContext(
            template_id=template_id,
            inputs=inputs or {},
            config=self._build_config(record, config or {}),
            trigger_data=trigger_data or {},
            security_classification=record.security_classification,
            user_confirmation_required=record.user_confirmation_required,
        )

        # Pre-flight checks
        preflight = self._preflight(record, ctx)
        if not preflight["success"]:
            ctx.mark_complete(False, preflight.get("error"))
            self._status.record_failure(template_id, preflight.get("error", "preflight failed"))
            return {
                "success": False,
                "run_id": ctx.run_id,
                "template_id": template_id,
                "error": preflight.get("error"),
                "blocked": preflight.get("blocked", False),
                "blocking_reason": preflight.get("blocking_reason"),
                "duration_ms": ctx.duration_ms,
                "steps": [],
                "outputs": {},
            }

        # Execute steps in DAG order
        ctx.status = "running"
        steps = record.steps
        step_results: list[dict[str, Any]] = []
        completed_steps: set[str] = set()
        all_success = True

        try:
            while len(completed_steps) < len(steps):
                # Find ready steps (all deps completed)
                ready = []
                for step in steps:
                    sid = step["id"]
                    if sid in completed_steps:
                        continue
                    deps = step.get("depends_on", [])
                    if all(d in completed_steps for d in deps):
                        ready.append(step)

                if not ready:
                    # Deadlock or all remaining steps blocked
                    remaining = [s["id"] for s in steps if s["id"] not in completed_steps]
                    if remaining:
                        ctx.mark_complete(False, f"Deadlock: steps {remaining} have unresolvable dependencies")
                        all_success = False
                    break

                # Execute ready steps (sequentially for now; parallel later)
                for step in ready:
                    sid = step["id"]

                    # Check step-level security
                    sec_check = self._sec_bridge.check_step_security(
                        step, ctx.security_classification
                    )
                    if not sec_check["permitted"]:
                        result = StepResult(
                            step_id=sid,
                            success=False,
                            error=sec_check["reason"],
                            blocked=True,
                            blocking_reason=sec_check["reason"],
                        )
                        ctx.step_results[sid] = result
                        step_results.append(result.to_dict())
                        completed_steps.add(sid)
                        all_success = False
                        continue

                    # Evaluate 'when' gate
                    when_expr = step.get("when")
                    if when_expr and not self._evaluate_when(when_expr, ctx):
                        result = StepResult(step_id=sid, success=True, outputs={})
                        ctx.step_results[sid] = result
                        step_results.append(result.to_dict())
                        completed_steps.add(sid)
                        continue

                    # Execute the step
                    result = self._step_runner.execute_step(step, ctx)
                    ctx.step_results[sid] = result

                    # Store outputs for downstream reference resolution
                    for out_name, out_value in result.outputs.items():
                        ctx.set_step_output(sid, out_name, out_value)

                    step_results.append(result.to_dict())

                    if result.success:
                        completed_steps.add(sid)
                        # Run verification
                        ver_result = self._ver_bridge.verify_step(
                            step, result.outputs, record.verification
                        )
                        ctx.verification_results.append(ver_result)
                        if not ver_result["passed"]:
                            result.verification_passed = False
                            if ver_result.get("abort"):
                                all_success = False
                                ctx.mark_complete(False, f"Verification failed for step {sid}")
                                break
                    else:
                        completed_steps.add(sid)
                        all_success = False

                        # Check on_error fallback
                        on_error = step.get("on_error", {})
                        fallback = on_error.get("fallback", "abort")
                        if fallback == "skip":
                            continue  # Skip and continue
                        elif fallback == "abort":
                            ctx.mark_complete(False, f"Step {sid} failed: {result.error}")
                            break
                        elif fallback == "notify":
                            # Continue but log the failure
                            logger.warning(
                                "[ENGINE] step %s failed (notify fallback): %s",
                                sid, result.error,
                            )
                            continue

                if ctx.status == "failed":
                    break

            # Collect final outputs
            if all_success:
                ctx.final_outputs = self._collect_outputs(record, ctx)
                ctx.mark_complete(True)
                self._status.record_success(template_id)
            else:
                self._status.record_failure(template_id, ctx.error or "execution failed")

        except Exception as exc:
            ctx.mark_complete(False, str(exc))
            self._status.record_failure(template_id, str(exc))
            logger.exception("[ENGINE] template %s execution failed", template_id)

        return {
            "success": ctx.status == "completed",
            "run_id": ctx.run_id,
            "template_id": template_id,
            "outputs": ctx.final_outputs,
            "steps": step_results,
            "duration_ms": ctx.duration_ms,
            "error": ctx.error,
            "blocked": False,
            "verification_results": ctx.verification_results,
        }

    # ── Internal helpers ─────────────────────────────────────────────

    def _preflight(self, record: TemplateRecord, ctx: AutomationExecutionContext) -> dict[str, Any]:
        """Pre-flight checks before execution."""
        # 1. Security classification validation
        sec_check = self._sec_bridge.check_template_security(record.template)
        if sec_check["warnings"]:
            for w in sec_check["warnings"]:
                logger.warning("[ENGINE] security: %s", w)
        ctx.user_confirmation_required = sec_check["requires_confirmation"]

        # 2. Capability availability
        caps = record.capabilities_required
        cap_status = self._cap_resolver.check_capabilities(caps)
        ctx.capabilities_available = [c for c, ok in cap_status.items() if ok]
        ctx.capabilities_missing = [c for c, ok in cap_status.items() if not ok]

        if ctx.capabilities_missing:
            reason = self._cap_resolver.get_blocking_reason(ctx.capabilities_missing)
            return {
                "success": False,
                "error": reason,
                "blocked": True,
                "blocking_reason": reason,
            }

        # 3. Credential availability
        cred_status = self._cred_bridge.resolve_credentials(record.credentials_required)
        ctx.credentials_status = {k: v["status"] for k, v in cred_status.items()}

        failed_creds = {k: v for k, v in cred_status.items() if v["status"] not in ("available",)}
        if failed_creds:
            reason = self._cred_bridge.get_blocking_reason(failed_creds)
            return {
                "success": False,
                "error": reason,
                "blocked": True,
                "blocking_reason": reason,
            }

        return {"success": True}

    def _build_config(
        self, record: TemplateRecord, user_config: dict[str, Any]
    ) -> dict[str, Any]:
        """Merge template defaults with user-provided config."""
        config = {}
        for cfg_item in record.config:
            name = cfg_item.get("name", "")
            default = cfg_item.get("default")
            if name in user_config:
                config[name] = user_config[name]
            elif default is not None:
                config[name] = default
        return config

    def _evaluate_when(self, expr: str, ctx: AutomationExecutionContext) -> bool:
        """Evaluate a step 'when' gate expression."""
        import re
        # Simple expressions: "{{ config.X }} != none", "{{ steps.X.Y }} == true"
        # Resolve references first
        resolved = ctx.resolve_value(expr)
        if isinstance(resolved, bool):
            return resolved
        if isinstance(resolved, str):
            return resolved.lower() not in ("false", "none", "no", "0", "")
        return bool(resolved)

    def _collect_outputs(
        self, record: TemplateRecord, ctx: AutomationExecutionContext
    ) -> dict[str, Any]:
        """Collect final outputs from the template's output declarations."""
        outputs = {}
        for out_spec in record.outputs:
            name = out_spec.get("name", "")
            from_ref = out_spec.get("from", "")
            if from_ref:
                outputs[name] = ctx.resolve_value(from_ref)
            else:
                outputs[name] = None
        return outputs


def create_automation_engine(
    library_root: Path | None = None,
) -> AutomationEngine:
    """Factory function to create a fully initialized AutomationEngine.

    Usage:
        engine = create_automation_engine()
        count = engine.template_count
        result = await engine.execute("data.json_transform", inputs={...})
    """
    engine = AutomationEngine(library_root)
    engine.load_templates()
    return engine
