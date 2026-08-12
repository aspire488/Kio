"""
Minimal runtime-owned execution handoff for Gate 0 stabilization.

This module is intentionally small. It centralizes side-effect dispatch for
the current prototype runtime without introducing planner/verifier systems.

HARDENED EXECUTION BOUNDARY CONTRACT:
1. LLM-derived intents are untrusted until validated.
2. Intent extraction does not grant execution authority.
3. Only validated structured intents may reach runtime dispatch.
"""

from __future__ import annotations

import logging
import os
import time
from dataclasses import dataclass, field
from typing import Any, Callable

from mini_kio.core.runtime import (
    RamBudgetError,
    SafetyState,
    classify_capability_group,
    emit_runtime_trace,
    get_runtime,
    get_runtime_snapshot,
    record_runtime_integrity_warning,
    remember_runtime_context,
)
from mini_kio.core.operator_protocol import (
    ActionRegistryEntry,
    OUTCOME_SUCCESS,
    OUTCOME_FAILURE,
    OUTCOME_BLOCKED,
    OUTCOME_DEGRADED,
    OUTCOME_INVALID_RESULT,
    OUTCOME_TIMEOUT,
    FAILURE_OPERATOR_EXCEPTION,
    FAILURE_RAM_EXCEEDED,
    FAILURE_INVALID_RESULT,
    FAILURE_BLOCKED_ACTION,
    FAILURE_UNKNOWN_ACTION,
    FAILURE_VERIFICATION_FAILED,
)
from mini_kio.core.app_operator import (
    launch_app, close_app, close_all_user_apps, search_web, execute_capability,
    APP_OPERATOR_DESCRIPTOR, APP_REGISTRY, _RESTRICTED_CANONICAL_TARGETS,
)
from mini_kio.core.browser_operator import (
    play_youtube, search_youtube, BROWSER_OPERATOR_DESCRIPTOR,
    browser_click, browser_hover, browser_scroll, browser_drag,
    browser_select, browser_fill, browser_type, browser_keypress,
    browser_evaluate, browser_extract_text, browser_extract_html,
    browser_screenshot, browser_pdf, BROWSER_HANDLERS,
)
from mini_kio.core.file_operator import (
    open_folder, FILE_OPERATOR_DESCRIPTOR
)
from mini_kio.core.system_operator import (
    lock_system, unlock_system, lock_state, shutdown_system, restart_system,
    recovery_runtime, SYSTEM_OPERATOR_DESCRIPTOR
)

logger = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# Deterministic Outcome Taxonomy (Gate 2.5)
# ---------------------------------------------------------------------------
OUTCOME_SUCCESS = "SUCCESS"
OUTCOME_SUCCESS_WITH_RESIDUALS = "SUCCESS_WITH_RESIDUALS"
OUTCOME_FAILURE = "FAILURE"
OUTCOME_BLOCKED = "BLOCKED"
OUTCOME_DEGRADED = "DEGRADED"
OUTCOME_INVALID_RESULT = "INVALID_RESULT"
OUTCOME_TIMEOUT = "TIMEOUT"

PREREQ_SEVERITY_BLOCKING = "blocking"
PREREQ_SEVERITY_ADVISORY = "advisory"
FAILURE_MISSING_PREREQUISITE = "missing_prerequisite"


# ---------------------------------------------------------------------------
# Execution Gate Protocol (Slice 7 / B.1)
# ---------------------------------------------------------------------------

@dataclass
class PrerequisiteGate:
    """Result of prerequisite resolution for one action.

    Slice 7 (B.1) — Execution Gate Protocol. Fail-closed: when `missing` is
    non-empty and `severity` is BLOCKING, the action must NOT execute and a
    structured prerequisite result propagates upward instead.

    Attributes:
        action: canonical action being gated.
        missing: internal prerequisite identifiers that are not satisfied.
        severity: "blocking" (action prevented) or "advisory" (recorded, not
            enforced). The plan does not specify advisory enforcement semantics,
            so advisory gates only attach structured metadata, never block.
    """

    action: str
    missing: list[str] = field(default_factory=list)
    severity: str = PREREQ_SEVERITY_BLOCKING

    @property
    def blocks(self) -> bool:
        return self.severity == PREREQ_SEVERITY_BLOCKING and bool(self.missing)

    def to_dict(self) -> dict[str, Any]:
        return {
            "action": self.action,
            "missing": list(self.missing),
            "severity": self.severity,
        }


# Canonical prerequisite resolver registry. Key = action name (or "*" for all
# actions); value = resolver(target: str) -> list[str] of missing prerequisite
# identifiers. Registered by Slice 7 wiring; future slices (8-9 credentials,
# 14 startup validation) register their own resolvers through the same registry
# instead of adding parallel mechanisms.
_PREREQUISITE_RESOLVERS: dict[str, Callable[[str], list[str]]] = {}


def register_prerequisite_resolver(
    action: str, resolver: Callable[[str], list[str]]
) -> None:
    """Register a prerequisite resolver for an action (or "*" for all).

    The resolver receives the raw target and returns a list of internal
    prerequisite identifiers that are currently MISSING."""
    _PREREQUISITE_RESOLVERS[action] = resolver


def resolve_prerequisites(action: str, target: str = "") -> PrerequisiteGate:
    """Resolve prerequisites for an action through the canonical registry.

    The action is canonicalized through _ACTION_MAP first so aliases (e.g.
    "click" -> "browser_click") resolve to the same gate as the canonical name
    — otherwise the gate could be silently bypassed via an alias. Runs the
    action-specific resolver (or the "*" fallback) and aggregates the missing
    prerequisite identifiers into a PrerequisiteGate. Default gate severity is
    blocking; severity is a plan-defined field reserved for future slices.
    """
    canonical = _ACTION_MAP.get(action, action)
    resolver = _PREREQUISITE_RESOLVERS.get(canonical)
    if resolver is None:
        resolver = _PREREQUISITE_RESOLVERS.get("*")
    if resolver is None:
        return PrerequisiteGate(action=canonical)
    try:
        missing = resolver(target or "")
    except Exception as exc:
        logger.warning(
            "[PREREQ] resolver for %s failed (fail-open: not blocking): %s",
            canonical, exc,
        )
        missing = []
    return PrerequisiteGate(action=canonical, missing=list(missing or []))


def _browser_backend_missing(target: str) -> list[str]:
    """Browser DOM/scripting prerequisite: a browser backend must be reachable.

    BrowserRuntime or the Browser Connector (extension connected) both count.
    Fail-closed: if neither is available the action cannot observe Chrome, so
    it must not claim success.
    """
    try:
        from mini_kio.core.command_router import _use_browser_runtime
        if _use_browser_runtime():
            return []
    except Exception:
        pass
    try:
        from mini_kio.core.command_router import _get_connector
        conn = _get_connector()
        if conn is not None and conn.is_connected():
            return []
    except Exception:
        pass
    return ["browser_backend"]


_BROWSER_BACKEND_ACTIONS = frozenset(
    {"browser_goto", "browser_click", "browser_hover", "browser_scroll",
     "browser_drag", "browser_select", "browser_fill", "browser_type",
     "browser_keypress", "browser_evaluate", "browser_extract_text",
     "browser_extract_html", "browser_screenshot", "browser_pdf"}
)
for _prereq_action in _BROWSER_BACKEND_ACTIONS:
    register_prerequisite_resolver(_prereq_action, _browser_backend_missing)


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
    "close_all_apps": {
        "handler": close_all_user_apps,
        "canonical_name": "close_all_apps",
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
    "unlock_system": {
        "handler": unlock_system,
        "canonical_name": "unlock_system",
        "category": "system_control",
        "descriptor": SYSTEM_OPERATOR_DESCRIPTOR
    },
    "lock_state": {
        "handler": lock_state,
        "canonical_name": "lock_state",
        "category": "system_control",
        "descriptor": SYSTEM_OPERATOR_DESCRIPTOR
    },
    "recovery_runtime": {
        "handler": recovery_runtime,
        "canonical_name": "recovery_runtime",
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
    },
}

# BrowserRuntime actions registered dynamically
for _br_action, _br_handler in BROWSER_HANDLERS.items():
    if _br_action not in STATIC_ACTION_TABLE:
        STATIC_ACTION_TABLE[_br_action] = {
            "handler": _br_handler,
            "canonical_name": _br_action,
            "category": "external_control",
            "descriptor": BROWSER_OPERATOR_DESCRIPTOR,
        }

_ACTION_MAP: dict[str, str] = {
    "open": "open_app",
    "open_app": "open_app",
    "close": "close_app",
    "close_app": "close_app",
    "close_all_apps": "close_all_apps",
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
    "unlock": "unlock_system",
    "unlock_system": "unlock_system",
    "lock_state": "lock_state",
    "recovery": "recovery_runtime",
    "recovery_runtime": "recovery_runtime",
    "shutdown": "shutdown_system",
    "shutdown_system": "shutdown_system",
    "restart": "restart_system",
    "restart_system": "restart_system",
    "execute_capability": "execute_capability",
    "media_play": "media_play",
    "media_pause": "media_pause",
    "media_stop": "media_stop",
    "media_mute": "media_mute",
    "media_unmute": "media_unmute",
    "media_volume_up": "media_volume_up",
    "media_volume_down": "media_volume_down",
    "media_seek_forward": "media_seek_forward",
    "media_seek_backward": "media_seek_backward",

    # BrowserRuntime DOM/scripting actions
    "click": "browser_click",
    "browser_click": "browser_click",
    "hover": "browser_hover",
    "browser_hover": "browser_hover",
    "scroll": "browser_scroll",
    "browser_scroll": "browser_scroll",
    "drag": "browser_drag",
    "browser_drag": "browser_drag",
    "select": "browser_select",
    "browser_select": "browser_select",
    "fill": "browser_fill",
    "browser_fill": "browser_fill",
    "type": "browser_type",
    "browser_type": "browser_type",
    "keypress": "browser_keypress",
    "browser_keypress": "browser_keypress",
    "evaluate": "browser_evaluate",
    "browser_evaluate": "browser_evaluate",
    "extract_text": "browser_extract_text",
    "browser_extract_text": "browser_extract_text",
    "extract_html": "browser_extract_html",
    "browser_extract_html": "browser_extract_html",
    "screenshot": "browser_screenshot",
    "browser_screenshot": "browser_screenshot",
    "pdf": "browser_pdf",
    "browser_pdf": "browser_pdf",
    "goto": "browser_goto",
    "browser_goto": "browser_goto",
}

_BLOCKED_ACTIONS: frozenset[str] = frozenset(
    {"shutdown", "shutdown_system", "restart", "restart_system"}
)

_VERIFICATION_PROBES: dict[str, Callable[[dict[str, Any]], dict[str, Any]]] = {}


def process_liveness_probe(result: dict[str, Any]) -> dict[str, Any]:
    """Verify that a launched process is actually running in the system."""
    pid = result.get("pid")
    result["probe_used"] = "process_liveness"
    if pid is None:
        result["verification_status"] = "failed"
        result["outcome_class"] = OUTCOME_FAILURE
        result["failure_class"] = "missing_pid"
        return result

    try:
        import psutil
        p = psutil.Process(int(pid))
        if p.is_running() and p.status() != psutil.STATUS_ZOMBIE:
            result["verification_status"] = "passed"
            result["outcome_class"] = OUTCOME_SUCCESS
        else:
            result["verification_status"] = "failed"
            result["outcome_class"] = OUTCOME_FAILURE
            result["failure_class"] = "process_not_active"
    except (psutil.NoSuchProcess, psutil.AccessDenied, ValueError):
        result["verification_status"] = "failed"
        result["outcome_class"] = OUTCOME_FAILURE
        result["failure_class"] = "pid_not_found"
    except Exception as e:
        logger.warning("Liveness probe exception: %s", e)
        result["verification_status"] = "probe_error"
        result["outcome_class"] = OUTCOME_FAILURE
    return result


def exit_code_probe(result: dict[str, Any]) -> dict[str, Any]:
    """Verify that a targeted process has exited (deterministic single-check)."""
    pid = result.get("pid")
    result["probe_used"] = "exit_code"

    if result.get("verification_status") in {"passed", "passed_with_residuals"}:
        if result.get("verification_status") == "passed_with_residuals":
            result["outcome_class"] = OUTCOME_SUCCESS_WITH_RESIDUALS
        elif not result.get("outcome_class"):
            result["outcome_class"] = OUTCOME_SUCCESS
        return result

    # 1. If operator provided exit_code directly, check it
    if "exit_code" in result:
        if result["exit_code"] == 0:
            result["verification_status"] = "passed"
            result["outcome_class"] = OUTCOME_SUCCESS
        else:
            result["verification_status"] = "failed"
            result["outcome_class"] = OUTCOME_FAILURE
        return result

    # 2. If no PID, fallback to success bit (image-name kills)
    if pid is None:
        if result.get("success"):
            result["verification_status"] = "passed"
            result["outcome_class"] = OUTCOME_SUCCESS
        else:
            result["verification_status"] = "failed"
            result["outcome_class"] = OUTCOME_FAILURE
        return result

    # 3. Synchronous liveness check (no polling loops)
    try:
        import psutil
        p = psutil.Process(int(pid))
        if p.is_running():
            if result.get("primary_termination_attempted"):
                result["verification_status"] = "passed_with_residuals"
                result["outcome_class"] = OUTCOME_SUCCESS_WITH_RESIDUALS
                result["failure_class"] = "residual_processes"
            else:
                result["verification_status"] = "failed"
                result["outcome_class"] = OUTCOME_FAILURE
                result["failure_class"] = "process_persists"
        else:
            result["verification_status"] = "passed"
            result["outcome_class"] = OUTCOME_SUCCESS
    except (psutil.NoSuchProcess, psutil.AccessDenied, ValueError):
        result["verification_status"] = "passed"
        result["outcome_class"] = OUTCOME_SUCCESS
    return result


def state_delta_probe(result: dict[str, Any]) -> dict[str, Any]:
    """Lightweight check for state changes (Phase 1: success-basis)."""
    result["probe_used"] = "state_delta"
    if result.get("success"):
        result["verification_status"] = "passed"
        result["outcome_class"] = OUTCOME_SUCCESS
    else:
        result["verification_status"] = "failed"
        result["outcome_class"] = OUTCOME_FAILURE
    return result


def noop_probe(result: dict[str, Any]) -> dict[str, Any]:
    """Pass-through probe that respects operator success.

    BC-4: an operator-provided honest verification status (e.g. "unverified"
    when a tab-identity check could not confirm) is PRESERVED rather than
    clobbered — "ACK received" is not silently upgraded to "verified".
    """
    result["probe_used"] = "noop"
    existing = result.get("verification_status")
    if existing in ("passed", "failed", "unverified", "probe_error"):
        if not result.get("outcome_class"):
            result["outcome_class"] = (
                OUTCOME_SUCCESS if result.get("success") else OUTCOME_FAILURE
            )
        return result
    if result.get("success"):
        result["verification_status"] = "passed"
        result["outcome_class"] = OUTCOME_SUCCESS
    else:
        result["verification_status"] = "failed"
        result["outcome_class"] = OUTCOME_FAILURE
    return result


def register_verification_probe(
    action: str, probe: Callable[[dict[str, Any]], dict[str, Any]]
) -> None:
    """Register a deterministic diagnostic probe for an action."""
    _VERIFICATION_PROBES[action] = probe


register_verification_probe("open_app", process_liveness_probe)
register_verification_probe("close_app", exit_code_probe)


def _default_probe(result: dict[str, Any]) -> dict[str, Any]:
    """Default pass-through probe for Phase 1 groundwork."""
    return noop_probe(result)


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

    First checks the static action table for known actions (open_app, close_app, etc.).
    Falls back to the ProviderRegistry for dynamically registered capabilities
    (e.g. MCP-backed fs_read, git_status, cmd_run, sql_query).

    Returns:
        (handler, canonical_action_name, descriptor)
    """
    canonical = _ACTION_MAP.get(action)
    if canonical:
        entry = STATIC_ACTION_TABLE.get(canonical)
        if entry:
            return entry["handler"], entry["canonical_name"], entry["descriptor"]

    from mini_kio.core.provider_registry import get_provider_registry
    provider = get_provider_registry().get_provider(action)
    if provider is not None:
        def _provider_handler(target: str = "", **kwargs: Any) -> dict[str, Any]:
            return provider.execute(action, target, **kwargs)
        return _provider_handler, action, {
            "tool_name": action,
            "tool_version": provider.id(),
            "ram_budget_mb": 10,
            "category": "mcp_provider",
        }

    raise ValueError(f"Unknown action: {action}")


def _resolve_registry_key(name: str) -> str | None:
    key = name.lower().strip()
    if not key:
        return None
    if key in APP_REGISTRY:
        return key
    for canonical, info in APP_REGISTRY.items():
        aliases = info.get("aliases", [])
        if any(key == alias.lower() for alias in aliases):
            return canonical
    return None


def _resolve_live_registration_pid(name: str, fallback_pid: int | None) -> int | None:
    """Verify fallback_pid is alive.  No psutil-wide scanning — only confirm
    the PID returned at launch time.  Returns None if unverifiable.
    """
    if fallback_pid is not None:
        try:
            import psutil

            proc = psutil.Process(int(fallback_pid))
            if proc.is_running() and proc.status() != psutil.STATUS_ZOMBIE:
                return int(fallback_pid)
        except (psutil.NoSuchProcess, psutil.AccessDenied, ValueError):
            pass
    return None


def _degraded_close_allowed(rt: Any, target: str) -> bool:
    """DEGRADED close_app allowance: closing a process KIO itself owns and
    verified (tracked) is safe even inside a degraded state — an outage must
    not lock the user out of cleaning up what KIO started."""
    try:
        registry_key = _resolve_registry_key(target)
        if registry_key:
            rt.prune_tracked_processes()
            if rt.get_tracked_process(registry_key) is not None:
                return True
    except Exception:
        pass
    return False


def check_safety_policy(action: str, target: str, rt: Any) -> tuple[bool, str]:
    """Check if the action is permitted in the current safety state (Gate 2.5)."""
    state = rt.safety_state
    category = classify_action(action)

    if state == SafetyState.LOCKDOWN:
        return False, "System is in LOCKDOWN. All actions are blocked."

    if state == SafetyState.EMERGENCY:
        # EMERGENCY allows ONLY system_control (lock) and future read_only
        if category in ("system_control", "read_only"):
            return True, ""
        return False, f"System is in EMERGENCY. Action category '{category}' is blocked."

    if state == SafetyState.DEGRADED:
        # Capability-group scoped gating (Gate 2.5 refinement): a provider
        # outage degrades ONLY the capability groups that genuinely depend on
        # it. A browser connector outage degrades the browser group; native
        # app launch/close, media, and system control remain available when
        # their groups were never degraded. The degraded set is populated by
        # record_runtime_integrity_warning (per-group accumulation).
        degraded_groups = getattr(rt, "degraded_capability_groups", None) or set()
        group = classify_capability_group(action, target)
        if degraded_groups:
            if group in degraded_groups:
                # close_app keeps its tracked-owned allowance even inside a
                # degraded native group: closing a process KIO itself owns and
                # verified is safe and should not be blocked by an outage in
                # the same group.
                if action == "close_app" and _degraded_close_allowed(rt, target):
                    return True, ""
                return False, f"System is DEGRADED. {group} controls are temporarily unavailable."
            return True, ""
        # Legacy conservative fallback when no group info is available (e.g.
        # DEGRADED escalated via observer/channel failures): keep the original
        # all-or-nothing external gating.
        if category == "external_open":
            return False, f"System is DEGRADED. Action category '{category}' is blocked."
        if action == "close_app":
            # Tracked-owned close stays allowed (return True BEFORE the
            # external_control check — close_app's own category would
            # otherwise block it).
            if _degraded_close_allowed(rt, target):
                return True, ""
            return False, "System is DEGRADED. close_app is allowed only for tracked owned processes."
        if category == "external_control":
            return False, f"System is DEGRADED. Action category '{category}' is blocked."
        return True, ""

    return True, ""


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
    
    # Check if a probe already set an outcome
    probe_outcome = result.get("outcome_class")
    probe_v_status = result.get("verification_status")

    if blocked:
        verification_status = "blocked"
        outcome_class = OUTCOME_BLOCKED
        # Preserve an explicit reason (e.g. restricted_target, missing_prerequisite);
        # default to the generic blocked_action only when none was provided.
        failure_class = result.get("failure_class") or "blocked_action"
    elif message == "Operator returned invalid result":
        verification_status = "failed"
        outcome_class = OUTCOME_INVALID_RESULT
        failure_class = "invalid_operator_result"
    elif message.startswith("Execution failed:") or result.get("failure_class") == "operator_exception":
        verification_status = "failed"
        outcome_class = OUTCOME_FAILURE
        failure_class = "operator_exception"
    elif probe_outcome:
        # Respect deterministic probe outcome
        outcome_class = probe_outcome
        verification_status = probe_v_status or ("passed" if outcome_class == OUTCOME_SUCCESS else "failed")
        failure_class = result.get("failure_class", "")
    elif not success:
        verification_status = "failed"
        outcome_class = OUTCOME_FAILURE
        failure_class = result.get("failure_class", "operator_reported_failure")
    else:
        # Default success if no probe override
        verification_status = "passed"
        outcome_class = OUTCOME_SUCCESS
        failure_class = ""

    result["verified"] = verification_status == "passed"
    result["verification_status"] = verification_status
    result["outcome_class"] = outcome_class
    result["failure_class"] = failure_class
    
    # Ensure probe_used is present
    if "probe_used" not in result:
        result["probe_used"] = result.get("verification_mode", "none")
    
    return result


def _log_execution_event(event: str, **fields: Any) -> None:
    emit_runtime_trace(event, **fields)


_TEST_MODE = None

def _in_test_mode() -> bool:
    global _TEST_MODE
    if _TEST_MODE is None:
        _TEST_MODE = os.environ.get("KIO_TEST_MODE") == "1"
    return _TEST_MODE


def execute_action(action: str, target: str = "") -> dict[str, Any]:
    """
    Execute an action through one runtime-owned handoff.
    
    ASSERTIONS:
    - Only validated structured intents may reach this dispatch point.
    - LLM-derived intents are UNTRUSTED until reaching this boundary.
    - Execution authority is ONLY granted to known, registered actions.

    Responsibilities:
      1. Receive action request
      2. Resolve handler and descriptor
      3. Perform safety policy check (Gate 2.5)
      4. Throttling in DEGRADED state (Gate 2.5)
      5. Deterministic RAM capacity check via descriptor
      6. Block clearly destructive actions during Gate 0
      7. Invoke the operator
      8. Normalize the result shape including execution_id and version telemetry
    """
    category = classify_action(action)
    start = time.monotonic()
    rt = get_runtime()
    execution_id = rt.get_execution_id() if rt else "exec_standalone"

    # ── BROWSER NORMALIZATION ENFORCEMENT ───────────────────────────
    # Safety: Browser routing in handle_command must have already normalized 
    # to a valid URL. If an action arrives here that should be browser-routed
    # but isn't a valid URL, it must reject.
    if action == "execute_capability" and "::open_url::" in target:
        url = target.split("::open_url::", 1)[1]
        if not url.startswith("http"):
            elapsed_ms = int((time.monotonic() - start) * 1000)
            return _apply_verification({
                "success": False,
                "message": "Security Violation: Unnormalized browser target reached execution boundary.",
                "action": action,
                "target": target,
                "category": category,
                "elapsed_ms": elapsed_ms,
                "failure_class": "security_violation",
                "execution_id": execution_id,
            })
    # ────────────────────────────────────────────────────────────────

    # ── RESTRICTED TARGET ENFORCEMENT ──────────────────────────────
    resolved = _ACTION_MAP.get(action, action)
    norm_target = target.lower().strip()
    if norm_target.endswith(".exe"):
        norm_target = norm_target[:-4]
    if resolved in ("open_app", "close_app") and norm_target in _RESTRICTED_CANONICAL_TARGETS:
        elapsed_ms = int((time.monotonic() - start) * 1000)
        return _apply_verification({
            "success": False,
            "message": "Restricted system target.",
            "action": action,
            "target": target,
            "category": category,
            "blocked": True,
            "elapsed_ms": elapsed_ms,
            "execution_id": execution_id,
            "failure_class": "restricted_target",
        })

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
            "failure_class": FAILURE_UNKNOWN_ACTION,
            "execution_id": execution_id,
        })

    # Gate 2.5: Safety Policy Check
    if rt:
        permitted, reason = check_safety_policy(action, target, rt)
        if not permitted:
            elapsed_ms = int((time.monotonic() - start) * 1000)
            blocked_result = {
                "success": False,
                "message": reason,
                "action": action,
                "target": target,
                "category": category,
                "blocked": True,
                "elapsed_ms": elapsed_ms,
                "execution_id": execution_id,
                "failure_class": FAILURE_BLOCKED_ACTION,
                "outcome_class": OUTCOME_BLOCKED,
                "tool_version": descriptor.get("tool_version", "unknown"),
            }
            _log_execution_event(
                "exec_blocked",
                execution_id=execution_id,
                action=action,
                category=category,
                reason=reason,
                runtime=get_runtime_snapshot(),
            )
            record_runtime_integrity_warning("blocked_attempt", {"action": action, "reason": reason})
            return _apply_verification(blocked_result)

        # Gate 2.5: Throttling in DEGRADED state
        if rt.safety_state == SafetyState.DEGRADED:
            time.sleep(0.5)

    # Gate 2.4: Deterministic RAM check using descriptor
    try:
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
            "failure_class": FAILURE_RAM_EXCEEDED,
            "execution_id": execution_id,
            "tool_version": descriptor.get("tool_version", "unknown"),
        })

    runtime_snapshot = get_runtime_snapshot()
    _log_execution_event(
        "exec_dispatch",
        execution_id=execution_id,
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
            "execution_id": execution_id,
        }
        _log_execution_event(
            "exec_blocked",
            execution_id=execution_id,
            action=action,
            category=category,
            target=target,
            elapsed_ms=elapsed_ms,
            verification_status="blocked",
            outcome_class=OUTCOME_BLOCKED,
            failure_class=FAILURE_BLOCKED_ACTION,
            runtime=runtime_snapshot,
        )
        record_runtime_integrity_warning("blocked_attempt", {"action": action, "reason": "destructive_blocked"})
        remember_runtime_context(
            "execution",
            {
                "action": action,
                "target": target,
                "verification_status": "blocked",
                "outcome_class": OUTCOME_BLOCKED,
                "execution_id": execution_id,
            },
        )
        return _apply_verification(blocked_result)

    if _in_test_mode():
        elapsed_ms = int((time.monotonic() - start) * 1000)
        return _apply_verification({
            "success": True,
            "action": action,
            "target": target,
            "category": category,
            "message": f"[TEST MODE] {action} blocked during testing",
            "blocked": True,
            "elapsed_ms": elapsed_ms,
            "test_mode": True,
            "execution_id": execution_id,
        })

    # Slice 7 (B.1): Execution Gate Protocol — fail-closed prerequisite gate.
    # Runs between the safety policy check and the handler invocation. If a
    # blocking prerequisite is missing, the action MUST NOT execute; the
    # structured prerequisite result propagates upward instead of guessing or
    # silently continuing.
    gate = resolve_prerequisites(action, target)
    if gate.blocks:
        elapsed_ms = int((time.monotonic() - start) * 1000)
        blocked_result = {
            "success": False,
            "message": f"Action '{action}' requires prerequisites that are not available.",
            "action": action,
            "target": target,
            "category": category,
            "blocked": True,
            "elapsed_ms": elapsed_ms,
            "execution_id": execution_id,
            "failure_class": FAILURE_MISSING_PREREQUISITE,
            "outcome_class": OUTCOME_BLOCKED,
            "prerequisite_gate": gate.to_dict(),
            "tool_version": descriptor.get("tool_version", "unknown"),
        }
        _log_execution_event(
            "exec_prerequisite_blocked",
            execution_id=execution_id,
            action=action,
            category=category,
            target=target,
            missing=gate.missing,
            severity=gate.severity,
            elapsed_ms=elapsed_ms,
            runtime=runtime_snapshot,
        )
        record_runtime_integrity_warning(
            "blocked_attempt",
            {
                "action": action,
                "target": target,
                "reason": "missing_prerequisite",
                "missing": list(gate.missing),
            },
        )
        remember_runtime_context(
            "prerequisite_blocked",
            {
                "action": action,
                "target": target,
                "missing": list(gate.missing),
                "severity": gate.severity,
                "execution_id": execution_id,
            },
        )
        return _apply_verification(blocked_result)

    try:
        handler_name = f"{handler.__module__}.{handler.__name__}"
        _log_execution_event(
            "exec_operator_dispatch",
            execution_id=execution_id,
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
                import mini_kio.core.runtime as runtime_mod
                from mini_kio.core.app_operator import APP_REGISTRY

                # Resolve canonical name for lookup
                lookup_name = target.lower().strip()
                for k, info in APP_REGISTRY.items():
                    if lookup_name == k or lookup_name in info.get("aliases", []):
                        lookup_name = k
                        break
                
                emit_runtime_trace("DEBUG_boundary_close_lookup_start", target=target, canonical=lookup_name)

                current_runtime = runtime_mod.get_runtime()
                if current_runtime:
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

        if canonical_action in ("lock_system", "unlock_system", "lock_state",
                                "recovery_runtime", "close_all_apps"):
            # No-argument system-control handlers (lock/unlock/lock-state query,
            # manual recovery, and the SCOPE=ALL_APPLICATIONS close) must not
            # receive the positional target arg.
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
        normalized["execution_id"] = execution_id

        # Phase 1 Groundwork: Diagnostic Probe
        if normalized.get("success"):
            # LIFECYCLE-AWARE PROBE SELECTION (Gate 2.5 Stabilization)
            requested_mode = normalized.get("verification_mode")
            if requested_mode == "noop":
                probe = noop_probe
            else:
                probe = _VERIFICATION_PROBES.get(canonical_action, _default_probe)

            try:
                # Deterministic probe execution
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
                    import mini_kio.core.runtime as runtime_mod
                    # Use canonical name if returned by operator, else fallback to target
                    reg_name = verified_result.get("canonical_name", target.lower().strip())
                    emit_runtime_trace("DEBUG_boundary_reg_start", pid=pid, reg_name=reg_name)
                    current_runtime = runtime_mod.get_runtime()
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

        # Explorer/folder ownership registration
        if canonical_action == "open_folder" and verified_result.get("success"):
            pid = verified_result.get("pid")
            if pid:
                try:
                    import mini_kio.core.runtime as runtime_mod
                    emit_runtime_trace("DEBUG_boundary_folder_reg", pid=pid)
                    current_runtime = runtime_mod.get_runtime()
                    if current_runtime:
                        explorer_pid = _resolve_live_registration_pid("explorer", int(pid))
                        current_runtime.register_tracked_process(
                            pid=int(explorer_pid or pid),
                            name="explorer",
                            target=target,
                        )
                except Exception as reg_exc:
                    logger.warning("Failed to register explorer process: %s", reg_exc)

        if canonical_action == "close_app":
            try:
                import mini_kio.core.runtime as runtime_mod

                current_runtime = runtime_mod.get_runtime()
                registry_key = _resolve_registry_key(target) or target.lower().strip()
                if current_runtime and registry_key:
                    if verified_result.get("verification_status") == "passed":
                        current_runtime.unregister_tracked_process(registry_key)
                    elif verified_result.get("verification_status") == "passed_with_residuals":
                        residual_pid = verified_result.get("residual_pid")
                        if isinstance(residual_pid, int):
                            current_runtime.refresh_tracked_process(
                                pid=residual_pid,
                                name=registry_key,
                                target=target,
                            )
            except Exception as close_reg_exc:
                logger.warning("Failed to finalize close ownership: %s", close_reg_exc)

        _log_execution_event(
            "exec_result",
            execution_id=execution_id,
            action=verified_result["action"],
            category=verified_result["category"],
            target=verified_result["target"],
            elapsed_ms=verified_result["elapsed_ms"],
            success=verified_result["success"],
            blocked=verified_result.get("blocked", False),
            handler=verified_result["handler"],
            tool_name=descriptor.get("tool_name"),
            tool_version=verified_result["tool_version"],
            verification_status=verified_result["verification_status"],
            outcome_class=verified_result["outcome_class"],
            failure_class=verified_result["failure_class"],
            probe_used=verified_result.get("probe_used"),
            runtime=runtime_snapshot,
        )
        # Record metrics
        try:
            from mini_kio.execution.metrics import get_metrics_collector
            get_metrics_collector().record_execution(
                verified_result["action"], verified_result["target"],
                verified_result["success"], verified_result["elapsed_ms"],
                provider=verified_result.get("handler", ""),
            )
        except Exception:
            pass

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
        
        if verified_result.get("outcome_class") == OUTCOME_INVALID_RESULT:
            record_runtime_integrity_warning("invalid_result", {"action": verified_result["action"]})

        from mini_kio.core.target_ref import safe_target_name
        remember_runtime_context(
            "execution",
            {
                "execution_id": execution_id,
                "action": verified_result["action"],
                "target": safe_target_name(str(verified_result.get("target", "") or "")),
                "verification_status": verified_result["verification_status"],
                "outcome_class": verified_result["outcome_class"],
                "success": verified_result["success"],
            },
        )
        return verified_result
    except BaseException as exc:
        elapsed_ms = int((time.monotonic() - start) * 1000)
        logger.error("[EXEC] action=%s failed: %s", action, exc)
        _log_execution_event(
            "exec_failure",
            execution_id=execution_id,
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
                "failure_class": FAILURE_OPERATOR_EXCEPTION,
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
            "execution_id": execution_id,
            "tool_version": descriptor.get("tool_version", "unknown") if 'descriptor' in locals() else "unknown",
        })
        from mini_kio.core.target_ref import safe_target_name
        remember_runtime_context(
            "execution",
            {
                "execution_id": execution_id,
                "action": failure_result["action"],
                "target": safe_target_name(str(failure_result.get("target", "") or "")),
                "verification_status": failure_result["verification_status"],
                "outcome_class": failure_result["outcome_class"],
                "success": failure_result["success"],
                "error": str(exc)[:120],
            },
        )
        return failure_result


def execute_mcp_tool(tool_name: str, arguments: dict, *, server_id: str | None = None,
                       timeout_s: float | None = None) -> dict:
    """Execute an MCP tool through MCPRuntime (imported runtime).

    Returns a normalized result dict matching Gate 5 result shape.
    """
    rt = get_runtime()
    if rt is None or rt.mcp_runtime is None:
        return {"success": False, "message": "MCPRuntime not available.", "action": "mcp_tool", "target": tool_name}
    try:
        from mini_kio.core.async_utils import safe_run_async
        mcp_request = {"tool_name": tool_name, "arguments": arguments, "server_id": server_id, "timeout_s": timeout_s}
        # Build a ToolCallRequest — but we can call MCPRuntime.call_tool directly
        result = safe_run_async(rt.mcp_runtime.call_tool(tool_name, arguments, server_id=server_id, timeout_s=timeout_s))
        return {
            "success": result.success,
            "message": str(result.content) if result.success else str(result.error),
            "action": "mcp_tool",
            "target": tool_name,
            "mcp_result": result,
        }
    except Exception as exc:
        return {"success": False, "message": f"MCP tool call failed: {exc}", "action": "mcp_tool", "target": tool_name}


__all__ = ["classify_action", "execute_action", "execute_mcp_tool",
           "resolve_prerequisites", "register_prerequisite_resolver",
           "PrerequisiteGate"]
