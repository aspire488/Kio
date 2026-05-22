"""
Minimal runtime-owned execution handoff for Gate 0 stabilization.

This module is intentionally small. It centralizes side-effect dispatch for
the current prototype runtime without introducing planner/verifier systems.
"""

from __future__ import annotations

import logging
import time
from typing import Any, Callable

from mini_kio.core.runtime import (
    RamBudgetError,
    emit_runtime_trace,
    get_runtime_snapshot,
    record_runtime_integrity_warning,
    remember_runtime_context,
)
from mini_kio.core.operator_protocol import ActionRegistryEntry
from mini_kio.core.app_operator import (
    launch_app, close_app, search_web, execute_capability, APP_OPERATOR_DESCRIPTOR
)
from mini_kio.core.browser_operator import (
    play_youtube, search_youtube, BROWSER_OPERATOR_DESCRIPTOR
)
from mini_kio.core.file_operator import (
    open_folder, FILE_OPERATOR_DESCRIPTOR
)
from mini_kio.core.system_operator import (
    lock_system, shutdown_system, restart_system, SYSTEM_OPERATOR_DESCRIPTOR
)

logger = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# Static Action Registry
# ---------------------------------------------------------------------------

STATIC_ACTION_TABLE: dict[str, ActionRegistryEntry] = {
    "open_app": {
        "handler": launch_app,
        "canonical_name": "open_app",
        "category": "external_open",
        "descriptor": APP_OPERATOR_DESCRIPTOR
    },
    "close_app": {
        "handler": close_app,
        "canonical_name": "close_app",
        "category": "external_control",
        "descriptor": APP_OPERATOR_DESCRIPTOR
    },
    "search_web": {
        "handler": search_web,
        "canonical_name": "search_web",
        "category": "external_open",
        "descriptor": APP_OPERATOR_DESCRIPTOR
    },
    "open_folder": {
        "handler": open_folder,
        "canonical_name": "open_folder",
        "category": "external_open",
        "descriptor": FILE_OPERATOR_DESCRIPTOR
    },
    "play_youtube": {
        "handler": play_youtube,
        "canonical_name": "play_youtube",
        "category": "external_open",
        "descriptor": BROWSER_OPERATOR_DESCRIPTOR
    },
    "search_youtube": {
        "handler": search_youtube,
        "canonical_name": "search_youtube",
        "category": "external_open",
        "descriptor": BROWSER_OPERATOR_DESCRIPTOR
    },
    "lock_system": {
        "handler": lock_system,
        "canonical_name": "lock_system",
        "category": "system_control",
        "descriptor": SYSTEM_OPERATOR_DESCRIPTOR
    },
    "shutdown_system": {
        "handler": shutdown_system,
        "canonical_name": "shutdown_system",
        "category": "destructive_system",
        "descriptor": SYSTEM_OPERATOR_DESCRIPTOR
    },
    "restart_system": {
        "handler": restart_system,
        "canonical_name": "restart_system",
        "category": "destructive_system",
        "descriptor": SYSTEM_OPERATOR_DESCRIPTOR
    },
    "execute_capability": {
        "handler": execute_capability,
        "canonical_name": "execute_capability",
        "category": "external_control",
        "descriptor": APP_OPERATOR_DESCRIPTOR
    }
}

_ACTION_MAP: dict[str, str] = {
    "open": "open_app",
    "open_app": "open_app",
    "close": "close_app",
    "close_app": "close_app",
    "search": "search_web",
    "search_web": "search_web",
    "folder": "open_folder",
    "open_folder": "open_folder",
    "play": "play_youtube",
    "play_youtube": "play_youtube",
    "youtube_play": "play_youtube",
    "search_youtube": "search_youtube",
    "lock": "lock_system",
    "lock_system": "lock_system",
    "shutdown": "shutdown_system",
    "shutdown_system": "shutdown_system",
    "restart": "restart_system",
    "restart_system": "restart_system",
    "execute_capability": "execute_capability"
}

_BLOCKED_ACTIONS: frozenset[str] = frozenset(
    {"shutdown", "shutdown_system", "restart", "restart_system"}
)

_VERIFICATION_PROBES: dict[str, Callable[[dict[str, Any]], dict[str, Any]]] = {}


def _process_liveness_probe(result: dict[str, Any]) -> dict[str, Any]:
    """Verify that a launched process is actually running in the system."""
    pid = result.get("pid")
    if pid is None:
        result["verification_status"] = "failed"
        result["failure_class"] = "missing_pid"
        return result

    import platform
    import subprocess
    if platform.system() == "Windows":
        try:
            r = subprocess.run(
                ["tasklist", "/FI", f"PID eq {pid}", "/NH"],
                capture_output=True,
                text=True,
                timeout=1,
            )
            if str(pid) in r.stdout:
                result["verification_status"] = "passed"
            else:
                result["verification_status"] = "failed"
                result["failure_class"] = "pid_not_found"
        except Exception:
            result["verification_status"] = "probe_error"
    else:
        import os
        try:
            os.kill(int(pid), 0)
            result["verification_status"] = "passed"
        except (OSError, ProcessLookupError):
            result["verification_status"] = "failed"
            result["failure_class"] = "pid_not_found"

    result["verification_mode"] = "process_liveness"
    return result


def _process_exit_probe(result: dict[str, Any]) -> dict[str, Any]:
    """Verify that a targeted PID has actually exited."""
    pid = result.get("pid")
    if pid is None:
        # Fallback for image-name kills
        if result.get("success"):
            result["verification_status"] = "passed"
        else:
            result["verification_status"] = "failed"
        result["verification_mode"] = "image_exit_check"
        return result

    import platform
    import subprocess
    import time

    # Allow 1.5s grace period for exit
    deadline = time.time() + 1.5
    alive = True
    while time.time() < deadline:
        if platform.system() == "Windows":
            try:
                r = subprocess.run(
                    ["tasklist", "/FI", f"PID eq {pid}", "/NH"],
                    capture_output=True, text=True, timeout=1,
                )
                if str(pid) not in r.stdout:
                    alive = False
                    break
            except Exception:
                pass
        else:
            import os
            try:
                os.kill(int(pid), 0)
            except (OSError, ProcessLookupError):
                alive = False
                break
        time.sleep(0.3)

    if not alive:
        result["verification_status"] = "passed"
    else:
        result["verification_status"] = "failed"
        result["failure_class"] = "process_persists"

    result["verification_mode"] = "process_exit"
    return result


def register_verification_probe(
    action: str, probe: Callable[[dict[str, Any]], dict[str, Any]]
) -> None:
    """Register a deterministic diagnostic probe for an action."""
    _VERIFICATION_PROBES[action] = probe


register_verification_probe("open_app", _process_liveness_probe)
register_verification_probe("close_app", _process_exit_probe)


def _default_probe(result: dict[str, Any]) -> dict[str, Any]:
    """Default pass-through probe for Phase 1 groundwork."""
    result["verification_mode"] = "boundary_probe"
    return result


def classify_action(action: str) -> str:
    """Return the minimal category for an action name."""
    canonical = _ACTION_MAP.get(action)
    if canonical:
        entry = STATIC_ACTION_TABLE.get(canonical)
        if entry:
            return entry["category"]
    return "unknown"


def _load_handler(action: str) -> tuple[Callable[..., dict], str, dict[str, Any]]:
    """
    Resolve an action to a concrete operator function and its descriptor.

    Returns:
        (handler, canonical_action_name, descriptor)
    """
    canonical = _ACTION_MAP.get(action)
    if not canonical:
        raise ValueError(f"Unknown action: {action}")

    entry = STATIC_ACTION_TABLE.get(canonical)
    if not entry:
        raise ValueError(f"Action mapped to non-existent entry: {action} -> {canonical}")

    return entry["handler"], entry["canonical_name"], entry["descriptor"]


def _normalize_result(
    result: dict | None,
    *,
    action: str,
    target: str,
    category: str,
    elapsed_ms: int,
    handler_name: str | None = None,
    descriptor: dict[str, Any] | None = None,
) -> dict[str, Any]:
    if not isinstance(result, dict):
        return {
            "success": False,
            "message": "Operator returned invalid result",
            "action": action,
            "target": target,
            "category": category,
            "elapsed_ms": elapsed_ms,
            "handler": handler_name or "",
            "tool_version": descriptor.get("tool_version", "unknown") if descriptor else "unknown",
        }

    normalized: dict[str, Any] = {
        "success": bool(result.get("success")),
        "message": str(result.get("message", "")),
        "action": action,
        "target": target,
        "category": category,
        "elapsed_ms": elapsed_ms,
        "handler": handler_name or "",
        "tool_version": descriptor.get("tool_version", "unknown") if descriptor else "unknown",
    }

    for key, value in result.items():
        if key not in normalized:
            normalized[key] = value

    if not normalized["message"]:
        normalized["message"] = "Done." if normalized["success"] else "Command failed."

    return normalized


def _apply_verification(result: dict[str, Any]) -> dict[str, Any]:
    """Attach a minimal runtime-owned verification classification."""
    blocked = bool(result.get("blocked"))
    success = bool(result.get("success"))
    message = str(result.get("message", ""))

    if blocked:
        verification_status = "blocked"
        outcome_class = "blocked"
        failure_class = "blocked_action"
    elif success:
        verification_status = "passed"
        outcome_class = "success"
        failure_class = ""
    elif message == "Operator returned invalid result":
        verification_status = "failed"
        outcome_class = "failure"
        failure_class = "invalid_operator_result"
    elif message.startswith("Execution failed:"):
        verification_status = "failed"
        outcome_class = "failure"
        failure_class = "operator_exception"
    else:
        verification_status = "failed"
        outcome_class = "failure"
        failure_class = "operator_reported_failure"

    result["verified"] = verification_status == "passed"
    result["verification_status"] = verification_status
    result["verification_mode"] = "boundary_outcome_check"
    result["outcome_class"] = outcome_class
    result["failure_class"] = failure_class
    return result


def _log_execution_event(event: str, **fields: Any) -> None:
    emit_runtime_trace(event, **fields)


def execute_action(action: str, target: str = "") -> dict[str, Any]:
    """
    Execute an action through one runtime-owned handoff.

    Responsibilities:
      1. Receive action request
      2. Resolve handler and descriptor
      3. Perform minimal action classification
      4. Deterministic RAM capacity check via descriptor
      5. Block clearly destructive actions during Gate 0
      6. Invoke the operator
      7. Normalize the result shape including version telemetry
    """
    category = classify_action(action)
    start = time.monotonic()

    try:
        handler, canonical_action, descriptor = _load_handler(action)
    except ValueError as val_exc:
        elapsed_ms = int((time.monotonic() - start) * 1000)
        return _apply_verification({
            "success": False,
            "message": str(val_exc),
            "action": action,
            "target": target,
            "category": category,
            "elapsed_ms": elapsed_ms,
            "failure_class": "unknown_action",
        })

    # Gate 2.4: Deterministic RAM check using descriptor
    try:
        from mini_kio.core.runtime import get_runtime
        rt = get_runtime()
        if rt:
            budget = float(descriptor.get("ram_budget_mb", 10.0))
            rt.resource_guard.check_capacity(budget)
    except RamBudgetError as ram_exc:
        elapsed_ms = int((time.monotonic() - start) * 1000)
        logger.error("[EXEC] RAM capacity check failed for %s: %s", descriptor.get("tool_name"), ram_exc)
        return _apply_verification({
            "success": False,
            "message": f"Resource Limit: {ram_exc}",
            "action": action,
            "target": target,
            "category": category,
            "elapsed_ms": elapsed_ms,
            "failure_class": "ram_budget_exceeded",
        })

    runtime_snapshot = get_runtime_snapshot()
    _log_execution_event(
        "exec_dispatch",
        action=action,
        category=category,
        target=target,
        tool=descriptor.get("tool_name"),
        version=descriptor.get("tool_version"),
        runtime=runtime_snapshot,
    )

    if action in _BLOCKED_ACTIONS:
        elapsed_ms = int((time.monotonic() - start) * 1000)
        blocked_result = {
            "success": False,
            "message": (
                f"Blocked {action} during Gate 0 stabilization. "
                "Destructive actions are not allowed through the runtime boundary yet."
            ),
            "action": action,
            "target": target,
            "category": category,
            "blocked": True,
            "elapsed_ms": elapsed_ms,
            "handler": "",
            "tool_version": descriptor.get("tool_version", "unknown"),
        }
        _log_execution_event(
            "exec_blocked",
            action=action,
            category=category,
            target=target,
            elapsed_ms=elapsed_ms,
            verification_status="blocked",
            outcome_class="blocked",
            failure_class="blocked_action",
            runtime=runtime_snapshot,
        )
        remember_runtime_context(
            "execution",
            {
                "action": action,
                "target": target,
                "verification_status": "blocked",
                "outcome_class": "blocked",
            },
        )
        return _apply_verification(blocked_result)

    try:
        handler_name = f"{handler.__module__}.{handler.__name__}"
        _log_execution_event(
            "exec_operator_dispatch",
            action=canonical_action,
            category=classify_action(canonical_action),
            target=target,
            handler=handler_name,
            tool=descriptor.get("tool_name"),
            version=descriptor.get("tool_version"),
            runtime=runtime_snapshot,
        )

        # Step 2: PID-Aware Close Retrieval
        pid_for_close = None
        if canonical_action == "close_app":
            try:
                import mini_kio.core.runtime as runtime
                from mini_kio.core.app_operator import APP_REGISTRY

                # Resolve canonical name for lookup
                lookup_name = target.lower().strip()
                for k, info in APP_REGISTRY.items():
                    if lookup_name == k or lookup_name in info.get("aliases", []):
                        lookup_name = k
                        break
                
                emit_runtime_trace("DEBUG_boundary_close_lookup_start", target=target, canonical=lookup_name)

                current_runtime = runtime.get_runtime()
                if current_runtime:
                    current_runtime.prune_tracked_processes()
                    entry = current_runtime.get_tracked_process(lookup_name)
                    if entry:
                        pid_for_close = entry.get("pid")
                        emit_runtime_trace("DEBUG_boundary_close_pid_found", pid=pid_for_close)
                    else:
                        emit_runtime_trace("DEBUG_boundary_close_pid_not_found", lookup_name=lookup_name)
                else:
                    emit_runtime_trace("DEBUG_boundary_no_runtime_for_lookup")
            except Exception as pid_lookup_exc:
                logger.warning("PID lookup failed for close: %s", pid_lookup_exc)

        if canonical_action == "lock_system":
            result = handler()
        elif canonical_action == "close_app" and pid_for_close is not None:
            result = handler(target, pid=pid_for_close)
        else:
            result = handler(target)
        elapsed_ms = int((time.monotonic() - start) * 1000)
        normalized = _normalize_result(
            result,
            action=canonical_action,
            target=target,
            category=classify_action(canonical_action),
            elapsed_ms=elapsed_ms,
            handler_name=handler_name,
            descriptor=descriptor,
        )

        # Phase 1 Groundwork: Diagnostic Probe
        if normalized.get("success"):
            probe = _VERIFICATION_PROBES.get(canonical_action, _default_probe)
            try:
                # Deterministic probe execution (Phase 1: default_probe only)
                normalized = probe(normalized)
            except Exception as probe_exc:
                logger.warning(
                    "Verification probe failed for %s: %s", canonical_action, probe_exc
                )
                normalized["verification_status"] = "probe_error"
                normalized["probe_error"] = str(probe_exc)

        verified_result = _apply_verification(normalized)

        # Step 1: Process Registration
        if canonical_action == "open_app" and verified_result.get("success"):
            pid = verified_result.get("pid")
            emit_runtime_trace("DEBUG_boundary_reg_check", pid=pid, action=canonical_action)
            if pid:
                try:
                    import mini_kio.core.runtime as runtime
                    # Use canonical name if returned by operator, else fallback to target
                    reg_name = verified_result.get("canonical_name", target.lower().strip())
                    emit_runtime_trace("DEBUG_boundary_reg_start", pid=pid, reg_name=reg_name)
                    current_runtime = runtime.get_runtime()
                    if current_runtime:
                        current_runtime.register_tracked_process(
                            pid=int(pid),
                            name=reg_name,
                            target=target,
                        )
                    else:
                        emit_runtime_trace("DEBUG_boundary_no_runtime_for_reg")
                except Exception as reg_exc:
                    logger.warning("Failed to register tracked process: %s", reg_exc)

        _log_execution_event(
            "exec_result",
            action=verified_result["action"],
            category=verified_result["category"],
            target=verified_result["target"],
            elapsed_ms=verified_result["elapsed_ms"],
            success=verified_result["success"],
            blocked=verified_result.get("blocked", False),
            handler=verified_result["handler"],
            verification_status=verified_result["verification_status"],
            outcome_class=verified_result["outcome_class"],
            failure_class=verified_result["failure_class"],
            runtime=runtime_snapshot,
        )
        if (
            not verified_result["success"]
            and not verified_result.get("blocked", False)
        ):
            record_runtime_integrity_warning(
                "execution_failure",
                {
                    "action": verified_result["action"],
                    "target": verified_result["target"],
                    "failure_class": verified_result["failure_class"],
                },
            )
        remember_runtime_context(
            "execution",
            {
                "action": verified_result["action"],
                "target": verified_result["target"],
                "verification_status": verified_result["verification_status"],
                "outcome_class": verified_result["outcome_class"],
                "success": verified_result["success"],
            },
        )
        return verified_result
    except Exception as exc:
        elapsed_ms = int((time.monotonic() - start) * 1000)
        logger.error("[EXEC] action=%s failed: %s", action, exc)
        _log_execution_event(
            "exec_failure",
            action=action,
            category=category,
            target=target,
            elapsed_ms=elapsed_ms,
            error=str(exc)[:120],
            runtime=runtime_snapshot,
        )
        record_runtime_integrity_warning(
            "execution_failure",
            {
                "action": action,
                "target": target,
                "failure_class": "operator_exception",
                "error": str(exc)[:120],
            },
        )
        failure_result = _apply_verification({
            "success": False,
            "message": f"Execution failed: {str(exc)[:120]}",
            "action": action,
            "target": target,
            "category": category,
            "elapsed_ms": elapsed_ms,
            "handler": "",
        })
        remember_runtime_context(
            "execution",
            {
                "action": failure_result["action"],
                "target": failure_result["target"],
                "verification_status": failure_result["verification_status"],
                "outcome_class": failure_result["outcome_class"],
                "success": failure_result["success"],
                "error": str(exc)[:120],
            },
        )
        return failure_result


__all__ = ["classify_action", "execute_action"]
