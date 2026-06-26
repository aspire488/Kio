"""
Minimal runtime bootstrap for Gate 0 stabilization.

This module is intentionally small. It gives runtime initialization ownership
of process startup before any channel is attached.
"""

from __future__ import annotations

from collections import deque
from dataclasses import dataclass, field
import json
import logging
import os
import requests
import sys
import threading
import time
import uuid
from pathlib import Path
from typing import Any, Callable

from mini_kio.core.config import TELEGRAM_TOKEN, DISCORD_BOT_TOKEN

logger = logging.getLogger(__name__)
_CURRENT_RUNTIME: "KioRuntime | None" = None
_RUNTIME_CONTEXT_LIMIT = 16
_RUNTIME_CONTEXT_TTL_S = 300
_CHANNEL_INPUT_MAX_LEN = 2000
_RUNTIME_OBSERVER_LIMIT = 8
_OBSERVER_HEALTH_STATES = frozenset({"inactive", "ready", "degraded"})
_INTEGRITY_WARNING_LIMIT = 8
_INTEGRITY_STATUS_HEALTHY = "healthy"
_INTEGRITY_STATUS_DEGRADED = "degraded"
_INTEGRITY_DEGRADE_THRESHOLDS: dict[str, int] = {}
_INTEGRITY_SEVERITY_WEIGHTS = {
    "low": 1,
    "medium": 2,
    "high": 4,
    "critical": 10,
}
_INTEGRITY_SCORE_DEGRADED_THRESHOLD = 6
_INTEGRITY_SCORE_EMERGENCY_THRESHOLD = 10


def get_runtime() -> "KioRuntime | None":
    """Return the current KioRuntime singleton instance.
    
    This is the proper way to access the runtime from external modules
    to avoid main-vs-imported-module identity splits.
    """
    return _CURRENT_RUNTIME


class RamBudgetError(RuntimeError):
    """Raised when current RAM usage plus requested module budget exceeds hard limit."""
    pass


class ResourceGuard:
    """RAM budget enforcement (v1.1)."""
    SOFT_LIMIT_MB = 150
    HARD_LIMIT_MB = 190

    def check_capacity(self, module_ram_mb: float) -> None:
        """Called BEFORE every lazy-load or tool execution."""
        import psutil
        import os
        current = psutil.Process(os.getpid()).memory_info().rss / 1024 / 1024
        
        # Gate 2.5: Degradation behavior - halve allowed headroom if degraded
        hard_limit = self.HARD_LIMIT_MB
        runtime = get_runtime()
        if runtime and runtime.safety_state == SafetyState.DEGRADED:
            # When degraded, we halve the available headroom from current to HARD_LIMIT
            headroom = hard_limit - current
            hard_limit = current + (headroom / 2)

        if current + module_ram_mb > hard_limit:
            raise RamBudgetError(
                f"No headroom: {current:.0f}MB + {module_ram_mb}MB > {hard_limit:.0f}MB"
            )

    def audit_loop_sync(self) -> None:
        """60s audit logic (synchronous for v1 prototype loop)."""
        import psutil
        import os
        import gc
        ram = psutil.Process(os.getpid()).memory_info().rss / 1024 / 1024
        if ram > self.HARD_LIMIT_MB:
            emit_runtime_trace("resource_guard_hard_limit_breach", ram_mb=ram)
            # v1: Unload observers if registered
            # gc.collect()
        elif ram > self.SOFT_LIMIT_MB:
            emit_runtime_trace("resource_guard_soft_limit_breach", ram_mb=ram)
            gc.collect()


class RuntimeState:
    """Minimal bootstrap states for future lifecycle preparation."""

    INIT = "init"
    READY = "ready"
    IDLE = "idle"
    RUNNING = "running"
    DEGRADED = "degraded"
    STOPPED = "stopped"


class SafetyState:
    """Deterministic runtime safety states (Gate 2.5)."""
    NORMAL = "NORMAL"
    DEGRADED = "DEGRADED"
    EMERGENCY = "EMERGENCY"
    LOCKDOWN = "LOCKDOWN"


_ALLOWED_TRANSITIONS: dict[str, set[str]] = {
    RuntimeState.INIT: {RuntimeState.READY, RuntimeState.DEGRADED, RuntimeState.STOPPED},
    RuntimeState.READY: {
        RuntimeState.IDLE,
        RuntimeState.RUNNING,
        RuntimeState.DEGRADED,
        RuntimeState.STOPPED,
    },
    RuntimeState.IDLE: {
        RuntimeState.RUNNING,
        RuntimeState.DEGRADED,
        RuntimeState.STOPPED,
    },
    RuntimeState.RUNNING: {
        RuntimeState.IDLE,
        RuntimeState.DEGRADED,
        RuntimeState.STOPPED,
    },
    RuntimeState.DEGRADED: {
        RuntimeState.IDLE,
        RuntimeState.RUNNING,
        RuntimeState.STOPPED,
    },
    RuntimeState.STOPPED: set(),
}


@dataclass
class KioRuntime:
    """Lightweight runtime container for startup ownership."""

    state: str = RuntimeState.INIT
    safety_state: str = SafetyState.NORMAL
    started_at: float = field(default_factory=time.monotonic)
    channels: list[str] = field(default_factory=list)
    shutdown_requested: bool = False
    last_error: str | None = None
    context_items: deque[dict[str, object]] = field(
        default_factory=lambda: deque(maxlen=_RUNTIME_CONTEXT_LIMIT)
    )
    observers: dict[str, dict[str, object]] = field(default_factory=dict)
    activation_state: str = "activation_idle"
    activation_observer: str | None = None
    activation_session_id: int = 0
    activation_started_at_ms: int | None = None
    activation_session_timeout_s: int | None = None
    camera_state: str = "camera_off"
    camera_device_index: int = 0
    camera_last_error: str | None = None
    camera_frames_polled: int = 0
    activation_last_candidate_emitted_ms: int | None = None
    integrity_status: str = _INTEGRITY_STATUS_HEALTHY
    integrity_counts: dict[str, int] = field(default_factory=dict)
    integrity_score: int = 0
    integrity_severity_counts: dict[str, int] = field(default_factory=dict)
    integrity_warnings: deque[dict[str, object]] = field(
        default_factory=lambda: deque(maxlen=_INTEGRITY_WARNING_LIMIT)
    )
    tracked_processes: list[dict[str, object]] = field(default_factory=list)
    resource_guard: ResourceGuard = field(default_factory=lambda: ResourceGuard())
    execution_counter: int = 0

    def get_execution_id(self) -> str:
        """Generate a deterministic monotonic execution ID."""
        self.execution_counter += 1
        return f"exec_{int(self.started_at)}_{self.execution_counter:04d}"

    def transition_to(
        self,
        next_state: str,
        *,
        reason: str,
        error: str | None = None,
    ) -> None:
        """Apply a guarded lifecycle transition with lightweight tracing."""
        current_state = self.state
        if current_state == next_state:
            return

        allowed = _ALLOWED_TRANSITIONS.get(current_state, set())
        if next_state not in allowed:
            record_runtime_integrity_warning(
                "invalid_transition",
                {
                    "from_state": current_state,
                    "to_state": next_state,
                    "reason": reason,
                },
            )
            emit_runtime_trace(
                "runtime_invalid_transition",
                from_state=current_state,
                to_state=next_state,
                reason=reason,
                runtime=get_runtime_snapshot(),
            )
            raise RuntimeError(
                f"Invalid runtime transition: {current_state} -> {next_state} ({reason})"
            )

        self.state = next_state
        self.last_error = error
        emit_runtime_trace(
            "runtime_state_transition",
            from_state=current_state,
            to_state=next_state,
            reason=reason,
            error=error,
            runtime=get_runtime_snapshot(),
        )
        remember_runtime_context(
            "lifecycle_transition",
            {
                "from_state": current_state,
                "to_state": next_state,
                "reason": reason,
                "error": error,
            },
        )

    def mark_ready(self) -> None:
        self.transition_to(RuntimeState.READY, reason="bootstrap_complete")
        logger.info("Runtime initialized")

    def mark_idle(self) -> None:
        self.transition_to(RuntimeState.IDLE, reason="host_idle")
        logger.info("Runtime host idle")

    def mark_running(self, channel_name: str) -> None:
        if channel_name not in self.channels:
            self.channels.append(channel_name)
        self.transition_to(
            RuntimeState.RUNNING,
            reason=f"channel_start:{channel_name}",
        )
        logger.info("Runtime channel started: %s", channel_name)

    def mark_degraded(self, reason: str, error: str | None = None) -> None:
        persisted_error = error if error is not None else reason
        self.transition_to(
            RuntimeState.DEGRADED,
            reason=reason,
            error=persisted_error,
        )
        record_runtime_integrity_warning(
            "runtime_degraded",
            {"reason": reason, "error": persisted_error},
        )
        logger.warning("Runtime degraded: %s", reason)

    def request_shutdown(self) -> None:
        self.shutdown_requested = True
        try:
            from mini_kio.core.activation import force_release_activation

            force_release_activation("runtime_shutdown_requested")
        except Exception:
            pass
        try:
            from mini_kio.core.camera_runtime import release_camera_if_open

            release_camera_if_open("runtime_shutdown_requested")
        except Exception:
            pass
        logger.info("Runtime shutdown requested")

    def mark_stopped(self) -> None:
        try:
            from mini_kio.core.activation import force_release_activation

            force_release_activation("runtime_stop")
        except Exception:
            pass
        try:
            from mini_kio.core.camera_runtime import release_camera_if_open

            release_camera_if_open("runtime_stop")
        except Exception:
            pass
        self.transition_to(RuntimeState.STOPPED, reason="runtime_stop")
        logger.info("Runtime stopped")

    def register_tracked_process(self, pid: int, name: str, target: str, launch_id: str = "") -> None:
        """Register a new tracked process with a FIFO 16-entry limit."""
        import psutil
        lid = launch_id or str(uuid.uuid4())
        emit_runtime_trace("DEBUG_runtime_register_start", lid=lid, pid=pid, name=name, target=target)
        try:
            p = psutil.Process(pid)
            create_time = p.create_time()
        except (psutil.NoSuchProcess, psutil.AccessDenied):
            create_time = 0.0

        entry = {
            "launch_id": lid,
            "pid": pid,
            "name": name,
            "target": target,
            "launched_at": time.monotonic(),
            "create_time": create_time,
            "status": "active",
            "ownership_scope": "kio",
        }
        
        # FIFO eviction
        while len(self.tracked_processes) >= 16:
            oldest = self.tracked_processes.pop(0)
            emit_runtime_trace("runtime_process_evicted", lid=oldest.get("launch_id"), pid=oldest["pid"], name=oldest["name"])

        self.tracked_processes.append(entry)
        emit_runtime_trace("runtime_process_registered", lid=lid, pid=pid, name=name, target=target)

    def get_tracked_process(self, name: str) -> dict[str, object] | None:
        """Find the latest tracked process by its canonical name."""
        for entry in reversed(self.tracked_processes):
            if entry["name"] == name:
                return entry
        return None

    def unregister_tracked_process(self, name: str, pid: int | None = None) -> None:
        """Remove tracked process entries by canonical family and optional pid."""
        retained: list[dict[str, object]] = []
        for entry in self.tracked_processes:
            same_name = entry.get("name") == name
            same_pid = pid is None or int(entry.get("pid", -1)) == int(pid)
            if same_name and same_pid:
                emit_runtime_trace(
                    "runtime_process_unregistered",
                    lid=entry.get("launch_id"),
                    pid=entry.get("pid"),
                    name=entry.get("name"),
                )
                continue
            retained.append(entry)
        self.tracked_processes = retained

    def prune_tracked_processes(self) -> None:
        """Remove dead processes from the registry (piggybacked on command dispatch)."""
        import os
        import platform
        import subprocess

        is_windows = platform.system() == "Windows"
        active = []
        emit_runtime_trace("DEBUG_runtime_prune_start", count=len(self.tracked_processes))
        for entry in self.tracked_processes:
            pid = int(entry["pid"])
            alive = False
            if is_windows:
                try:
                    import psutil
                    try:
                        p = psutil.Process(pid)
                        if p.is_running():
                            # Phase A: Prevent PID reuse corruption
                            if entry.get("create_time", 0.0) > 0.0:
                                current_create_time = p.create_time()
                                if abs(current_create_time - entry["create_time"]) > 1.0:
                                    emit_runtime_trace("DEBUG_runtime_prune_pid_reused", pid=pid, name=entry["name"])
                                    alive = False
                                else:
                                    alive = True
                            else:
                                alive = True
                        else:
                            alive = False
                    except (psutil.NoSuchProcess, psutil.AccessDenied):
                        alive = False
                except Exception as e:
                    emit_runtime_trace("DEBUG_runtime_prune_error", pid=pid, error=str(e))
                    alive = True
            else:
                try:
                    os.kill(pid, 0)
                    alive = True
                except (OSError, ProcessLookupError):
                    alive = False

            if alive:
                active.append(entry)
            else:
                emit_runtime_trace(
                    "runtime_process_pruned",
                    pid=pid,
                    name=entry["name"],
                    reason="process_not_found",
                )
        
        self.tracked_processes = active
        emit_runtime_trace("DEBUG_runtime_prune_end", count=len(self.tracked_processes))


def setup_startup_logging() -> None:
    """Initialize logging once with a lightweight default formatter."""
    if logging.getLogger().handlers:
        return

    root_logger = logging.getLogger()
    root_logger.setLevel(logging.INFO)

    stream_handler = logging.StreamHandler()
    stream_handler.setFormatter(
        logging.Formatter("[%(asctime)s] %(name)s: %(message)s")
    )
    root_logger.addHandler(stream_handler)

    debug_dir = Path(__file__).resolve().parent.parent / "debug"
    debug_dir.mkdir(parents=True, exist_ok=True)
    file_handler = logging.FileHandler(debug_dir / "runtime_trace.log", encoding="utf-8")
    file_handler.setFormatter(
        logging.Formatter("%(asctime)s %(name)s %(levelname)s %(message)s")
    )
    root_logger.addHandler(file_handler)


def emit_runtime_trace(event: str, **fields: object) -> None:
    """Write a normalized runtime trace event through the standard logger."""
    payload: dict[str, object] = {"evt": event}
    # Ensure consistent field ordering for automated parsing
    sorted_fields = dict(sorted(fields.items()))
    payload.update(sorted_fields)
    logger.info(json.dumps(payload, default=str))


def _classify_integrity_severity(category: str, detail: object) -> str:
    """Deterministically classify runtime integrity warnings by severity."""
    failure_class = ""
    verification_status = ""
    if isinstance(detail, dict):
        failure_class = str(detail.get("failure_class", "") or "").lower()
        verification_status = str(detail.get("verification_status", "") or "").lower()

    if category == "blocked_attempt":
        return "high"
    if category == "invalid_result":
        return "medium"
    if category == "observer_degraded":
        return "medium"
    if category == "runtime_degraded":
        return "medium"
    if category == "invalid_transition":
        return "critical"
    if category == "channel_dispatch_failure":
        return "high"
    if category == "ram_budget_exceeded":
        return "medium"

    if category == "execution_failure":
        if verification_status == "blocked":
            return "high"
        if verification_status == "passed_with_residuals":
            return "low"
        if failure_class in {
            "not_installed",
            "not_found",
            "not_running",
            "not_tracked",
            "launch_failed",
            "invalid_input",
            "invalid_url",
        }:
            return "low"
        if failure_class in {
            "timeout",
            "unsupported",
            "invalid_operator_result",
        }:
            return "medium"
        if failure_class in {
            "permission_denied",
            "blocked_action",
            "operator_exception",
            "internal_error",
            "forbidden_uwp_kill",
        }:
            return "high"
        if failure_class == "invalid_transition":
            return "critical"
        return "medium"

    return "low"


def record_runtime_integrity_warning(category: str, detail: object) -> None:
    """Store a bounded integrity warning and update explicit integrity state."""
    runtime = _CURRENT_RUNTIME
    if runtime is None:
        return

    count = runtime.integrity_counts.get(category, 0) + 1
    runtime.integrity_counts[category] = count

    severity = _classify_integrity_severity(category, detail)
    weight = 0 if category == "blocked_attempt" else _INTEGRITY_SEVERITY_WEIGHTS.get(severity, 1)
    runtime.integrity_score += weight
    runtime.integrity_severity_counts[severity] = (
        runtime.integrity_severity_counts.get(severity, 0) + 1
    )

    threshold_trigger = ""
    if severity == "critical" or runtime.integrity_score >= _INTEGRITY_SCORE_EMERGENCY_THRESHOLD:
        threshold_trigger = "EMERGENCY"
    elif runtime.integrity_score >= _INTEGRITY_SCORE_DEGRADED_THRESHOLD:
        threshold_trigger = "DEGRADED"

    warning = {
        "category": category,
        "detail": detail,
        "count": count,
        "severity": severity,
        "weight": weight,
        "score": runtime.integrity_score,
        "threshold_trigger": threshold_trigger,
        "created_at_ms": int((time.monotonic() - runtime.started_at) * 1000),
    }
    runtime.integrity_warnings.append(warning)

    if runtime.integrity_score >= _INTEGRITY_SCORE_DEGRADED_THRESHOLD:
        runtime.integrity_status = _INTEGRITY_STATUS_DEGRADED

    # Gate 2.5: Safety state evaluation
    if runtime.safety_state != SafetyState.LOCKDOWN:
        if threshold_trigger == "EMERGENCY":
            if runtime.safety_state != SafetyState.EMERGENCY:
                runtime.safety_state = SafetyState.EMERGENCY
                emit_runtime_trace(
                    "runtime_safety_escalation",
                    safety_state=runtime.safety_state,
                    reason="weighted_emergency_breach",
                    threshold_trigger=threshold_trigger,
                )
        elif threshold_trigger == "DEGRADED":
            if runtime.safety_state == SafetyState.NORMAL:
                runtime.safety_state = SafetyState.DEGRADED
                emit_runtime_trace(
                    "runtime_safety_escalation",
                    safety_state=runtime.safety_state,
                    reason="weighted_degradation_breach",
                    threshold_trigger=threshold_trigger,
                )

    emit_runtime_trace(
        "runtime_integrity_warning",
        category=category,
        count=count,
        severity=severity,
        weight=weight,
        score=runtime.integrity_score,
        threshold_trigger=threshold_trigger,
        integrity_status=runtime.integrity_status,
        safety_state=runtime.safety_state,
    )
    remember_runtime_context("integrity_warning", warning)


def get_runtime_health_score() -> int:
    """Calculate a lightweight runtime health score (0-100)."""
    runtime = _CURRENT_RUNTIME
    if runtime is None:
        return 0

    score = 100
    score -= runtime.integrity_score * 2

    # Deduct for degraded observers
    for observer in runtime.observers.values():
        if observer.get("health") == "degraded":
            score -= 15

    return max(0, min(100, score))


def get_runtime_integrity_snapshot() -> dict[str, object]:
    """Return a tiny manual snapshot of runtime integrity state."""
    runtime = _CURRENT_RUNTIME
    if runtime is None:
        return {
            "status": _INTEGRITY_STATUS_HEALTHY,
        "score": 0,
        "counts": {},
        "severity_counts": {},
        }

    return {
        "status": runtime.integrity_status,
        "score": runtime.integrity_score,
        "counts": dict(runtime.integrity_counts),
        "severity_counts": dict(runtime.integrity_severity_counts),
        "warning_count": len(runtime.integrity_warnings),
        "recent_warnings": [dict(item) for item in runtime.integrity_warnings],
    }


def _prune_runtime_context(runtime: KioRuntime, now: float | None = None) -> None:
    """Drop all expired runtime context entries from the bounded buffer."""
    current_time = time.monotonic() if now is None else now
    runtime.context_items = deque(
        (
            item
            for item in runtime.context_items
            if float(item.get("expires_at", current_time)) > current_time
        ),
        maxlen=_RUNTIME_CONTEXT_LIMIT,
    )


def remember_runtime_context(
    kind: str,
    value: object,
    *,
    ttl_s: int = _RUNTIME_CONTEXT_TTL_S,
) -> None:
    """Store a tiny short-lived runtime context item in the bounded buffer."""
    runtime = _CURRENT_RUNTIME
    if runtime is None:
        return

    now = time.monotonic()
    _prune_runtime_context(runtime, now)
    runtime.context_items.append(
        {
            "kind": kind,
            "value": value,
            "created_at_ms": int((now - runtime.started_at) * 1000),
            "expires_at": now + max(1, ttl_s),
        }
    )
    emit_runtime_trace(
        "runtime_context_remembered",
        kind=kind,
        ttl_s=ttl_s,
        context_size=len(runtime.context_items),
    )


def drop_runtime_context(kind: str | None = None) -> None:
    """Explicitly drop all or selected short-lived runtime context items."""
    runtime = _CURRENT_RUNTIME
    if runtime is None:
        return

    _prune_runtime_context(runtime)
    before = len(runtime.context_items)
    if kind is None:
        runtime.context_items.clear()
    else:
        runtime.context_items = deque(
            (item for item in runtime.context_items if item.get("kind") != kind),
            maxlen=_RUNTIME_CONTEXT_LIMIT,
        )

    dropped = before - len(runtime.context_items)
    if dropped > 0:
        emit_runtime_trace(
            "runtime_context_dropped",
            kind=kind or "all",
            dropped=dropped,
            context_size=len(runtime.context_items),
        )


def get_runtime_context_snapshot() -> list[dict[str, object]]:
    """Return the current bounded runtime context buffer after expiration pruning."""
    runtime = _CURRENT_RUNTIME
    if runtime is None:
        return []

    _prune_runtime_context(runtime)
    return [
        {
            "kind": str(item.get("kind", "")),
            "value": item.get("value"),
            "created_at_ms": int(item.get("created_at_ms", 0)),
            "ttl_ms": max(
                0,
                int((float(item.get("expires_at", time.monotonic())) - time.monotonic()) * 1000),
            ),
        }
        for item in runtime.context_items
    ]


def get_last_successful_interaction(
    action_type: str | None = None,
    must_have_target: bool = True,
) -> dict[str, Any] | None:
    """
    Retrieve the last successful interaction from the context buffer.
    Used for simple short-context references ('it', 'that', 'again').
    """
    runtime = _CURRENT_RUNTIME
    if runtime is None:
        return None

    _prune_runtime_context(runtime)
    # Search backwards for the most recent successful execution
    for item in reversed(runtime.context_items):
        if item.get("kind") == "execution":
            val = item.get("value")
            if not isinstance(val, dict):
                continue
            if not val.get("success"):
                continue
            if must_have_target and not val.get("target"):
                continue
            if action_type and val.get("action") != action_type:
                # Basic action type matching if needed
                continue
            return val
    return None


def register_runtime_observer(
    name: str,
    source: str,
    *,
    enabled: bool = False,
    kind: str = "general",
    observer_type: str | None = None,
) -> dict[str, object]:
    """Register a lightweight observer record without starting any activity."""
    runtime = _CURRENT_RUNTIME
    if runtime is None:
        raise RuntimeError("Runtime not initialized")
    if name in runtime.observers:
        raise RuntimeError(f"Observer already registered: {name}")
    if len(runtime.observers) >= _RUNTIME_OBSERVER_LIMIT:
        raise RuntimeError(f"Observer limit reached: {_RUNTIME_OBSERVER_LIMIT}")

    now_ms = int((time.monotonic() - runtime.started_at) * 1000)
    record = {
        "name": name,
        "source": source,
        "kind": kind,
        "observer_type": observer_type,
        "enabled": bool(enabled),
        "health": "ready" if enabled else "inactive",
        "last_error": None,
        "last_change_ms": now_ms,
    }
    runtime.observers[name] = record
    emit_runtime_trace(
        "runtime_observer_registered",
        observer=name,
        source=source,
        enabled=enabled,
        observer_count=len(runtime.observers),
    )
    remember_runtime_context(
        "observer_state",
        {
            "observer": name,
            "action": "registered",
            "enabled": bool(enabled),
            "health": record["health"],
        },
    )
    return dict(record)


def set_runtime_observer_enabled(name: str, enabled: bool) -> dict[str, object]:
    """Manually enable or disable a registered observer record."""
    runtime = _CURRENT_RUNTIME
    if runtime is None:
        raise RuntimeError("Runtime not initialized")
    if name not in runtime.observers:
        raise RuntimeError(f"Observer not registered: {name}")

    record = runtime.observers[name]
    record["enabled"] = bool(enabled)
    if not enabled:
        record["health"] = "inactive"
        record["last_error"] = None
    elif record["health"] == "inactive":
        record["health"] = "ready"
    record["last_change_ms"] = int((time.monotonic() - runtime.started_at) * 1000)

    emit_runtime_trace(
        "runtime_observer_state",
        observer=name,
        enabled=record["enabled"],
        health=record["health"],
    )
    remember_runtime_context(
        "observer_state",
        {
            "observer": name,
            "action": "enabled" if enabled else "disabled",
            "enabled": record["enabled"],
            "health": record["health"],
        },
    )
    return dict(record)


def update_runtime_observer_health(
    name: str,
    health: str,
    *,
    error: str | None = None,
) -> dict[str, object]:
    """Update manual observer health state without starting observer activity."""
    runtime = _CURRENT_RUNTIME
    if runtime is None:
        raise RuntimeError("Runtime not initialized")
    if name not in runtime.observers:
        raise RuntimeError(f"Observer not registered: {name}")
    if health not in _OBSERVER_HEALTH_STATES:
        raise RuntimeError(f"Invalid observer health: {health}")

    record = runtime.observers[name]
    record["health"] = health
    record["last_error"] = error
    record["last_change_ms"] = int((time.monotonic() - runtime.started_at) * 1000)
    if health == "inactive":
        record["enabled"] = False
    elif health == "ready":
        record["enabled"] = True

    emit_runtime_trace(
        "runtime_observer_health",
        observer=name,
        health=health,
        error=error,
    )
    if health == "degraded":
        record_runtime_integrity_warning(
            "observer_degraded",
            {"observer": name, "error": error},
        )
    remember_runtime_context(
        "observer_state",
        {
            "observer": name,
            "action": "health_update",
            "enabled": record["enabled"],
            "health": health,
            "error": error,
        },
    )
    return dict(record)


def get_runtime_observer_snapshot() -> list[dict[str, object]]:
    """Return current manual observer registry state."""
    runtime = _CURRENT_RUNTIME
    if runtime is None:
        return []
    return [dict(record) for record in runtime.observers.values()]


def _route_via_orchestration(text: str) -> dict[str, object]:
    # Backwards-compatible wrapper: this signature may be updated by callers.
    return _route_via_orchestration(text, channel="unknown", user_id=0)


def _compute_session_id(channel: str, user_id: int) -> str:
    """Compute a session_id string from channel and user_id to avoid 'default'."""
    try:
        if channel == "telegram":
            return f"tg_{int(user_id)}"
        if channel.startswith("browser"):
            return f"browser_{int(user_id)}"
    except Exception:
        pass
    return f"local_{user_id or 0}"


def _route_via_orchestration(text: str, *, channel: str = "unknown", user_id: int = 0) -> dict[str, object]:
    """
    Gate 3 orchestration pipeline for non-deterministic input.

    Pipeline: input_normalizer -> intent_classifier -> intent_validator -> 
              conversation_orchestrator -> runtime_handoff
    """
    runtime = _CURRENT_RUNTIME
    if runtime is None:
        return {"success": False, "message": "Runtime not initialized."}

    # Lazy-init singleton pipeline instances on the runtime object
    if not hasattr(runtime, '_gate3_pipeline'):
        from mini_kio.llm.intent_classifier import IntentClassifier
        from mini_kio.llm.intent_validator import IntentValidator
        from mini_kio.llm.conversation_orchestrator import ConversationOrchestrator
        from mini_kio.runtime.runtime_handoff import RuntimeHandoff
        from mini_kio.llm.input_normalizer import InputNormalizer
        from mini_kio.llm.conversation_responder import ConversationResponder
        session_id = _compute_session_id(channel, user_id)
        runtime._gate3_pipeline = {
            'classifier': IntentClassifier(),
            'validator': IntentValidator(),
            'orchestrator': ConversationOrchestrator(),
            'handoff': RuntimeHandoff(),
            'normalizer': InputNormalizer(),
            'responder': ConversationResponder(session_id=session_id),
        }

    pipe = runtime._gate3_pipeline
    session_id = _compute_session_id(channel, user_id)
    from mini_kio.llm.conversation_responder import ConversationResponder
    if (
        'responder' not in pipe
        or pipe['responder'] is None
        or getattr(pipe['responder'], '_state', None) is None
        or pipe['responder']._state.session_id != session_id
    ):
        pipe['responder'] = ConversationResponder(session_id=session_id)
        pipe['session_id'] = session_id

    normalizer = pipe['normalizer']
    responder = pipe['responder']
    normalizer.reset_diag()

    # Gate 5.1: Use pre-normalized text from earliest entrypoint if available
    pre_normalized = getattr(runtime, '_gate5_normalized_text', None)
    if isinstance(pre_normalized, str) and pre_normalized in text:
        sanitized_text = pre_normalized
        # Still run through normalizer for typo corrections on pre-normalized
        normalized_text = normalizer.normalize_typos(sanitized_text)
        normalizer._diag["emoji_sanitize_applied"] = True
    else:
        # 1. EARLY SANITIZATION
        sanitized_text = normalizer.sanitize(text)
        # 2. PRE-CLASSIFICATION NORMALIZATION (Typos)
        normalized_text = normalizer.normalize_typos(sanitized_text)

    # 3. HARD AUTHORITY OVERRIDES
    authority_reply = normalizer.check_authority_override(normalized_text)
    
    # 4. CONTINUITY-FIRST ROUTING
    is_continuity = normalizer.is_continuity_request(normalized_text)
    
    # Educational continuity check (deterministically local)
    context = responder._context
    mode, step = context.get_lesson_state()
    active_lesson = mode and step >= 0
    
    # Capture browser diagnostics from routing_utils (global registry)
    from mini_kio.core.routing_utils import get_browser_registry
    browser_diag = get_browser_registry().get_diagnostics()

    if authority_reply:
        from mini_kio.llm.intent_models import IntentType, ExtractedIntent, IntentClassification
        primary = ExtractedIntent(
            raw_text=text,
            normalized_text=normalized_text,
            confidence=1.0,
            intent_type=IntentType.CONVERSATIONAL
        )
        diag = normalizer.get_diag()
        classification = IntentClassification(
            primary_intent=primary,
            is_safe=True,
            authority_override_used=True,
            sanitize_applied=diag["sanitize_applied"],
            emoji_sanitize_applied=diag.get("emoji_sanitize_applied", False),
            typo_normalization_applied=diag["typo_normalization_applied"]
        )
        # Bypassing classifier and validator for authority override
        validated = classification 
        orchestration = pipe['orchestrator'].orchestrate(validated)
    elif is_continuity and active_lesson:
        from mini_kio.llm.intent_models import IntentType, ExtractedIntent, IntentClassification
        normalizer.mark_continuity_used()
        primary = ExtractedIntent(
            raw_text=text,
            normalized_text=normalized_text,
            confidence=1.0,
            intent_type=IntentType.EDUCATIONAL
        )
        diag = normalizer.get_diag()
        classification = IntentClassification(
            primary_intent=primary,
            is_safe=True,
            continuity_resume_used=True,
            educational_state_preserved=True,
            sanitize_applied=diag["sanitize_applied"],
            emoji_sanitize_applied=diag.get("emoji_sanitize_applied", False),
            typo_normalization_applied=diag["typo_normalization_applied"]
        )
        # Bypassing classifier and validator for continuity
        validated = classification
        orchestration = pipe['orchestrator'].orchestrate(validated)
    else:
        from mini_kio.llm.intent_models import IntentType, IntentClassification
        # Standard pipeline
        emit_runtime_trace("intent_classification", text_len=len(normalized_text))
        classification = pipe['classifier'].classify(normalized_text)
        
        # Educational state preservation check
        educational_preserved = False
        if active_lesson:
            from mini_kio.llm.intent_models import IntentType
            if classification.primary_intent.intent_type == IntentType.EDUCATIONAL:
                educational_preserved = True

        # Update classification with diag
        diag = normalizer.get_diag()
        classification = IntentClassification(
            primary_intent=classification.primary_intent,
            alternatives=classification.alternatives,
            is_safe=classification.is_safe,
            sanitize_applied=diag["sanitize_applied"],
            emoji_sanitize_applied=diag.get("emoji_sanitize_applied", False),
            typo_normalization_applied=diag["typo_normalization_applied"],
            educational_state_preserved=educational_preserved,
            browser_canonicalization_used=browser_diag.get("browser_canonicalization_used", 0) > 0
        )

        emit_runtime_trace("validator_result",
                           is_safe=classification.is_safe,
                           intent_type=str(classification.primary_intent.intent_type)
                           if classification.primary_intent else "none")
        validated = pipe['validator'].validate(classification)
        
        # Prevent Intent Downgrade (educational -> conversational)
        if active_lesson and validated.primary_intent.intent_type == IntentType.CONVERSATIONAL:
            # Check if it should have been educational (handled by responder usually, but let's flag it)
            pass

        emit_runtime_trace("orchestration_state",
                           state=str(pipe['orchestrator'].get_state()))
        orchestration = pipe['orchestrator'].orchestrate(validated)

    handoff_state = str(orchestration.state.value) if hasattr(orchestration.state, 'value') else str(orchestration.state)
    emit_runtime_trace("handoff_result",
                       state=handoff_state,
                       has_pending=orchestration.pending_action is not None)
    try:
        handoff_result = pipe['handoff'].handle_handoff(orchestration)
    except Exception:
        pipe['orchestrator']._reset_state()
        return {"success": False, "message": "Orchestration handoff failed."}

    # Gate 3: Generate response through safe text-only responder
    responder = pipe['responder']
    try:
        # For authority override, use the direct reply if possible
        if authority_reply:
            response_text = authority_reply
        else:
            response_text = responder.generate(
                original_text=text,
                orchestration=orchestration,
                handoff_result=handoff_result,
            )
        emit_runtime_trace("conversation_response_generated",
                           classification=str(handoff_result.classification.value)
                           if hasattr(handoff_result.classification, 'value')
                           else str(handoff_result.classification))
    except Exception:
        response_text = "KIO encountered an issue processing that input."
        emit_runtime_trace("conversation_response_degraded",
                           classification=str(handoff_result.classification.value)
                           if hasattr(handoff_result.classification, 'value')
                           else str(handoff_result.classification))

    return {
        "success": handoff_result.success,
        "message": response_text,
        "_orchestrated": True,
    }


def aura_store_memory(role: str, content: str) -> None:
    """Fire-and-forget AURA memory store in a background thread."""
    if not content or not content.strip():
        return
    content = content[:4000]
    _aura_url = os.environ.get("AURA_URL")
    if not _aura_url:
        return
    threading.Thread(
        target=_aura_store_worker,
        args=(_aura_url, role, content),
        daemon=True,
    ).start()


def _aura_store_worker(aura_url: str, role: str, content: str) -> None:
    try:
        resp = requests.post(
            f"{aura_url}/memory/store",
            json={"role": role, "content": content, "source": "kio"},
            timeout=1,
        )
        if resp.ok:
            logger.info("[AURA_STORE] stored %s message", role)
        elif resp.status_code == 404:
            logger.debug("[AURA_FALLBACK] /memory/store not available (404)")
    except Exception as exc:
        logger.debug("[AURA_FALLBACK] memory store failed: %s", exc)


def aura_emit_event(event_type: str, payload: dict, session_id: str = "", correlation_id: str = "") -> None:
    """Fire-and-forget event emission to AURA Phase 2 Event System."""
    _aura_url = os.environ.get("AURA_URL")
    if not _aura_url:
        return
    threading.Thread(
        target=_aura_event_worker,
        args=(_aura_url, event_type, payload, session_id, correlation_id),
        daemon=True,
    ).start()


def _aura_event_worker(aura_url: str, event_type: str, payload: dict, session_id: str, correlation_id: str) -> None:
    try:
        resp = requests.post(
            f"{aura_url}/events/store",
            json={
                "event_type": event_type,
                "source": "kio",
                "payload": payload,
                "session_id": session_id,
                "correlation_id": correlation_id,
            },
            timeout=1,
        )
        if resp.ok:
            logger.info("[AURA_EVENT] emitted %s", event_type)
        elif resp.status_code == 404:
            logger.debug("[AURA_FALLBACK] /events/store not available (404)")
    except Exception as exc:
        logger.debug("[AURA_FALLBACK] event emission failed: %s", exc)


def aura_emit_observation(observation_type: str, content: dict, context: dict = None) -> None:
    """Fire-and-forget observation emission to AURA Phase 2 Observation Pipeline."""
    _aura_url = os.environ.get("AURA_URL")
    if not _aura_url:
        return
    threading.Thread(
        target=_aura_observation_worker,
        args=(_aura_url, observation_type, content, context or {}),
        daemon=True,
    ).start()


def _aura_observation_worker(aura_url: str, observation_type: str, content: dict, context: dict) -> None:
    try:
        resp = requests.post(
            f"{aura_url}/observations/ingest",
            json={
                "source": "kio",
                "observation_type": observation_type,
                "content": content,
                "context": context,
            },
            timeout=1,
        )
        if resp.ok:
            logger.info("[AURA_OBSERVE] ingested %s", observation_type)
        elif resp.status_code == 404:
            logger.debug("[AURA_FALLBACK] /observations/ingest not available (404)")
    except Exception as exc:
        logger.debug("[AURA_FALLBACK] observation ingestion failed: %s", exc)


def dispatch_channel_input(
    text: str,
    *,
    channel: str = "unknown",
    user_id: int = 0,
) -> dict[str, object]:
    """
    Runtime-owned channel input handoff.

    Channels must call this (not operators or execution_boundary directly).

    Gate 3 flow:
      1. Input validation
      2. Deterministic fast-path via handle_command
      3. If fast-path cannot handle (gate3_eligible), route through orchestration pipeline
      4. Context tracking and response formatting
    """
    runtime = _CURRENT_RUNTIME
    if runtime is None:
        return {
            "success": False,
            "message": "Runtime not initialized.",
            "channel": channel,
        }

    if runtime.shutdown_requested or runtime.state == RuntimeState.STOPPED:
        return {
            "success": False,
            "message": "Runtime is not accepting input.",
            "channel": channel,
        }

    try:
        from mini_kio.core.activation import touch_activation_session

        touch_activation_session()
    except Exception:
        pass

    runtime.prune_tracked_processes()

    command_raw = (text or "").strip()
    if not command_raw:
        return {
            "success": False,
            "message": "Empty command.",
            "channel": channel,
        }
    if len(command_raw) > _CHANNEL_INPUT_MAX_LEN:
        return {
            "success": False,
            "message": f"Input too long (max {_CHANNEL_INPUT_MAX_LEN} characters).",
            "channel": channel,
        }

    # Gate 5.1: Global normalization at earliest entrypoint
    from mini_kio.llm.input_normalizer import InputNormalizer
    command = InputNormalizer.strip_emoji(command_raw)
    runtime._gate5_normalized_text = command
    aura_store_memory("user", command)
    aura_emit_event("user_message", {"text": command[:2000]})
    aura_emit_observation("user_input", {"text": command[:2000]})

    emit_runtime_trace(
        "orchestration_entry",
        channel=channel,
        user_id=user_id,
        text_len=len(command),
        runtime=get_runtime_snapshot(),
    )

    # ── Gate 5.7: Cognitive Intent Classification — before continuity ──
    # Classify the cognitive intent BEFORE any continuity/entity/retrieval
    # processing. Cognition intents (CHAT, FACTUAL_QA, REASONING, PLANNING,
    # ARCHITECTURE, CODING, DEBUGGING, AGENT, VISION, OCR, SCREEN_ANALYSIS)
    # bypass ContinuityResolver, MediaIntelligence, and Exa entirely.
    from mini_kio.core.cognitive_intent import classify_intent, CognitiveIntent
    from mini_kio.llm.cognition_router import process_cognition, is_cognition_intent

    intent = classify_intent(command)
    logger.info("[COGNITION_INTENT] intent=%s text=%r", intent.value, command[:80])

    if is_cognition_intent(intent):
        try:
            import asyncio

            response = asyncio.run(
                process_cognition(intent=intent, query=command)
            )
            if response:
                result = {
                    "success": True,
                    "message": response,
                    "channel": channel,
                }
                from mini_kio.core.runtime_response_formatter import format_result

                result["message"] = format_result("", "", True, result)
                aura_store_memory("assistant", str(result.get("message", "")))
                aura_emit_event("assistant_response", {"text": str(result.get("message", ""))[:2000], "success": True})
                aura_emit_observation("assistant_response", {"text": str(result.get("message", ""))[:2000], "success": True})
                return result

            logger.info("[COGNITION_INTENT] NVIDIA returned None for intent=%s", intent.value)
            return {
                "success": False,
                "message": "I'm having trouble reaching my language model. Please try again.",
                "channel": channel,
            }
        except Exception as exc:
            logger.warning("[COGNITION_INTENT] NVIDIA routing failed: %s", exc)
            return {
                "success": False,
                "message": "I'm having trouble reaching my language model. Please try again.",
                "channel": channel,
            }

    logger.info("[COGNITION_INTENT] intent=%s route=existing_pipeline", intent.value)

    # ── Gate 5.1: Continuity Pre-Routing ────────────────────────────────
    # Must happen BEFORE command_router + classifier + ai_fallback
    continuity_reply = None
    # Ensure gate3 pipeline exists and is session-scoped
    session_id = _compute_session_id(channel, user_id)
    if not hasattr(runtime, '_gate3_pipeline'):
        from mini_kio.llm.intent_classifier import IntentClassifier
        from mini_kio.llm.intent_validator import IntentValidator
        from mini_kio.llm.conversation_orchestrator import ConversationOrchestrator
        from mini_kio.runtime.runtime_handoff import RuntimeHandoff
        from mini_kio.llm.input_normalizer import InputNormalizer
        from mini_kio.llm.conversation_responder import ConversationResponder

        runtime._gate3_pipeline = {
            'classifier': IntentClassifier(),
            'validator': IntentValidator(),
            'orchestrator': ConversationOrchestrator(),
            'handoff': RuntimeHandoff(),
            'normalizer': InputNormalizer(),
            'responder': ConversationResponder(session_id=session_id),
        }
    # Gate 5: Wire unified SessionState into ContinuityResolver and MediaIntelligenceAdapter
    _session_state = runtime._gate3_pipeline['responder']._state
    from mini_kio.core.continuity_resolver import ContinuityResolver
    ContinuityResolver.set_session_state(_session_state)
    try:
        from mini_kio.media.media_manager import MediaManager
        mm = MediaManager.get_instance()
        if mm and hasattr(mm, '_intelligence_adapter') and mm._intelligence_adapter:
            mm._intelligence_adapter.set_session_state(_session_state)
    except Exception:
        pass

    # Sports info commands must bypass continuity — prevents stale context pollution
    _lower_cmd = command.strip().lower()
    _sports_continuity_skip = any(kw in _lower_cmd for kw in
        ["standings", "table", "group ", "groups", "fixtures", "results",
         "scores", "world cup", "league table", "points table"])

    # Single-word media commands must bypass continuity and route directly to handle_command
    _media_commands = {"resume", "play", "pause", "stop", "next", "previous",
                       "mute", "unmute", "shuffle", "repeat"}
    _first_word = _lower_cmd.split()[0] if _lower_cmd.split() else ""
    _skip_continuity = _first_word in _media_commands or _sports_continuity_skip

    if _sports_continuity_skip:
        logger.info("[CONTINUITY_SKIPPED] reason=fresh_sports_information_query query=%s", _lower_cmd)

    if not _skip_continuity:
        from mini_kio.llm.conversation_responder import _handle_continuity_pre_route
        responder = runtime._gate3_pipeline['responder']
        session_id = _compute_session_id(channel, user_id)
        continuity_reply = _handle_continuity_pre_route(
            command_raw, responder._state, None, None, session_id
        )
        if continuity_reply:
            emit_runtime_trace("continuity_pre_route_used", normalized=command)
            aura_store_memory("assistant", continuity_reply)
            aura_emit_event("assistant_response", {"text": continuity_reply[:2000]})
            aura_emit_observation("assistant_response", {"text": continuity_reply[:2000]})
            return {
                "success": True,
                "message": continuity_reply,
                "channel": channel,
            }

    # ── Gate 3: Deterministic fast-path ────────────────────────────────
    try:
        from mini_kio.core.command_router import handle_command

        result = handle_command(command)
    except Exception as exc:
        logger.exception("Channel dispatch failed: %s", exc)
        record_runtime_integrity_warning(
            "channel_dispatch_failure",
            {"channel": channel, "error": str(exc)[:120]},
        )
        return {
            "success": False,
            "message": "KIO encountered an internal error but is still running.",
            "channel": channel,
        }

    # ── Gate 3: Orchestration pipeline for non-deterministic input ─────
    if result.get("_gate3_eligible"):
        result = _route_via_orchestration(command, channel=channel, user_id=user_id)
        # Fix C: Sync ContinuityResolver after Gate 3 handles a contentful
        # entity query (e.g. "Interstellar").  Only sync when the result has a
        # meaningful contentful subject — NEVER overwrite with raw command text
        # (which would poison memory with garbage like "Who sings it?").
        if result.get("success"):
            try:
                from mini_kio.media.media_manager import MediaManager
                mm = MediaManager.get_instance()
                if mm and mm._intelligence_adapter:
                    last_e = mm._intelligence_adapter._mem.get_last_entity()
                    if last_e and last_e.name:
                        from mini_kio.core.continuity_resolver import ContinuityResolver, DomainContinuationType
                        ContinuityResolver.set_state_subject(last_e.name, DomainContinuationType.MEDIA)
                        ContinuityResolver.set_state_domain(DomainContinuationType.MEDIA)
                        logger.info("[GATE3_SYNC] updated continuity from memory subject=%s", last_e.name)
                    else:
                        logger.debug("[GATE3_SKIP_SYNC] no entity in memory — skipping continuity sync")
                else:
                    logger.debug("[GATE3_SKIP_SYNC] no intelligence adapter — skipping continuity sync")
            except Exception as exc:
                logger.debug("[GATE3_SYNC] sync failed: %s", exc)
    elif hasattr(runtime, '_gate3_pipeline'):
        # Bridge confirmation responses back into orchestrator.
        # When orchestrator is awaiting confirmation, "yes"/"youtube"/"spotify"
        # must be routed through the orchestrator, not just the deterministic
        # fast-path (which has no awareness of the orchestrator's pending action).
        _lower = command.lower().strip()
        _orch = runtime._gate3_pipeline.get('orchestrator')
        if _orch is not None:
            from mini_kio.llm.conversation_orchestrator import ConversationOrchestrator
            if isinstance(_orch, ConversationOrchestrator):
                from mini_kio.llm.conversation_models import OrchestrationState
                if _orch.get_state() == OrchestrationState.AWAITING_CONFIRMATION:
                    _confirm_triggers = {"yes", "confirm", "proceed", "go ahead", "do it", "y"}
                    _selection_triggers = {"youtube", "spotify"}
                    if _lower in _confirm_triggers | _selection_triggers:
                        logger.info("[BRIDGE] routing confirmation '%s' into orchestrator", _lower)
                        result = _route_via_orchestration(command, channel=channel, user_id=user_id)

    if not isinstance(result, dict):
        result = {"success": False, "message": str(result)}

    # Gate 5.1: Runtime response formatting (hide internal routing)
    from mini_kio.core.runtime_response_formatter import format_result
    raw_message = str(result.get("message", ""))
    action = str(result.get("action", ""))
    target = str(result.get("target", ""))
    formatted = format_result(action, target, bool(result.get("success")), result)
    result["message"] = formatted

    # Gate 5: Refresh SessionState TTL after successful dispatch
    try:
        _session_state.refresh_ttl()
    except Exception:
        pass

    remember_runtime_context(
        "channel_input",
        {
            "channel": channel,
            "user_id": user_id,
            "success": bool(result.get("success")),
        },
    )
    result["channel"] = channel
    resp_text = str(result.get("message", ""))
    aura_store_memory("assistant", resp_text)
    aura_emit_event("assistant_response", {"text": resp_text[:2000], "success": bool(result.get("success"))})
    aura_emit_observation("assistant_response", {"text": resp_text[:2000], "success": bool(result.get("success"))})
    return result


def manual_runtime_recovery() -> dict[str, object]:
    """
    Deterministic manual recovery: clears safety state escalation and integrity warnings.
    
    This is an EXPLICIT manual action only — no automatic decay, no timers, no backgrounds.
    Caller must be explicitly aware of triggering recovery.
    
    Returns:
        {"success": bool, "message": str, "cleared_warnings": int, "previous_safety_state": str}
    """
    runtime = _CURRENT_RUNTIME
    if runtime is None:
        return {
            "success": False,
            "message": "Runtime not initialized.",
        }
    
    # Record state before recovery
    previous_safety_state = runtime.safety_state
    cleared_warning_count = len(runtime.integrity_warnings)
    
    # Clear integrity state
    runtime.integrity_warnings.clear()
    runtime.integrity_counts.clear()
    runtime.integrity_score = 0
    runtime.integrity_severity_counts.clear()
    runtime.integrity_status = _INTEGRITY_STATUS_HEALTHY
    
    # Reset safety state to NORMAL
    runtime.safety_state = SafetyState.NORMAL
    
    # Emit deterministic recovery audit event
    emit_runtime_trace(
        "runtime_manual_recovery",
        previous_safety_state=previous_safety_state,
        cleared_warning_count=cleared_warning_count,
        new_safety_state=runtime.safety_state,
    )
    
    return {
        "success": True,
        "message": f"Runtime recovered. Cleared {cleared_warning_count} warnings. Reset safety state from {previous_safety_state} to NORMAL.",
        "cleared_warnings": cleared_warning_count,
        "previous_safety_state": previous_safety_state,
    }


def format_channel_reply(result: dict[str, object]) -> str:
    """Normalize a runtime dispatch result into channel-safe plain text."""
    if result.get("success"):
        message = str(result.get("message") or "Done.")
    else:
        message = str(result.get("message") or "Command failed.")
        lower = message.lower()
        if message and not lower.startswith("error:") and not lower.startswith("error "):
            message = f"Error: {message}"

    if len(message) > 4000:
        message = message[:4000] + "..."
    return message


def get_runtime_snapshot() -> dict[str, object]:
    """Return a tiny runtime state snapshot for execution tracing."""
    runtime = _CURRENT_RUNTIME
    if runtime is None:
        return {
            "state": RuntimeState.INIT,
            "channels": [],
            "uptime_ms": 0,
            "context_size": 0,
            "observer_count": 0,
            "activation_state": "activation_idle",
            "camera_state": "camera_off",
            "integrity_status": _INTEGRITY_STATUS_HEALTHY,
            "integrity_warning_count": 0,
            "health_score": 0,
        }

    _prune_runtime_context(runtime)
    uptime_ms = int((time.monotonic() - runtime.started_at) * 1000)

    import psutil
    import os
    try:
        process = psutil.Process(os.getpid())
        ram_mb = process.memory_info().rss / 1024 / 1024
    except Exception:
        ram_mb = 0.0

    return {
        "state": runtime.state,
        "safety_state": runtime.safety_state,
        "channels": list(runtime.channels),
        "uptime_ms": uptime_ms,
        "ram_usage_mb": round(ram_mb, 1),
        "last_error": runtime.last_error,
        "context_size": len(runtime.context_items),
        "observer_count": len(runtime.observers),
        "activation_state": runtime.activation_state,
        "activation_session_id": runtime.activation_session_id,
        "camera_state": runtime.camera_state,
        "camera_frames_polled": runtime.camera_frames_polled,
        "integrity_status": runtime.integrity_status,
        "integrity_score": runtime.integrity_score,
        "integrity_warning_count": len(runtime.integrity_warnings),
        "health_score": get_runtime_health_score(),
    }



def bootstrap_runtime() -> KioRuntime:
    """
    Initialize the minimal runtime foundation.

    No channels are started here. The runtime becomes READY first, then an
    optional channel may be attached later.
    """
    setup_startup_logging()
    try:
        from mini_kio.core.activation import force_release_activation
        from mini_kio.core.camera_runtime import release_camera_if_open

        force_release_activation("runtime_rebootstrap")
        release_camera_if_open("runtime_rebootstrap")
    except Exception:
        pass

    runtime = KioRuntime()
    global _CURRENT_RUNTIME
    _CURRENT_RUNTIME = runtime

    package_runtime = sys.modules.get("mini_kio.core.runtime")
    if package_runtime is not None and package_runtime is not sys.modules.get(__name__):
        package_runtime._CURRENT_RUNTIME = runtime

    emit_runtime_trace("runtime_bootstrap_start")
    if TELEGRAM_TOKEN:
        emit_runtime_trace("runtime_channel_config", telegram_configured=True)
    else:
        emit_runtime_trace("runtime_channel_config", telegram_configured=False)
    if DISCORD_BOT_TOKEN:
        emit_runtime_trace("runtime_channel_config", discord_configured=True)
    else:
        emit_runtime_trace("runtime_channel_config", discord_configured=False)

    runtime.mark_ready()

    from mini_kio.core.activation import prepare_activation_groundwork

    prepare_activation_groundwork()

    # Proactive Browser Connector initialization (Gate 5.7)
    try:
        from mini_kio.core.command_router import _get_connector
        _get_connector()
    except Exception as exc:
        logger.error("Failed to proactively start Browser Connector: %s", exc)

    return runtime


def start_runtime_channel(
    runtime: KioRuntime,
    channel_name: str,
    start_fn: Callable[[KioRuntime], None],
) -> None:
    """Run a channel after runtime bootstrap has completed."""
    if runtime.state not in (RuntimeState.READY, RuntimeState.RUNNING):
        raise RuntimeError(f"Runtime not ready for channel start: {runtime.state}")

    runtime.mark_running(channel_name)
    emit_runtime_trace("runtime_channel_attach", channel=channel_name, runtime=get_runtime_snapshot())
    try:
        start_fn(runtime)
    except KeyboardInterrupt:
        runtime.request_shutdown()
        emit_runtime_trace("runtime_channel_interrupt", channel=channel_name, runtime=get_runtime_snapshot())
        raise
    except Exception as exc:
        runtime.mark_degraded("channel_failure", error=str(exc))
        emit_runtime_trace(
            "runtime_channel_failure",
            channel=channel_name,
            error=str(exc),
            runtime=get_runtime_snapshot(),
        )
        raise
    finally:
        if channel_name in runtime.channels:
            runtime.channels.remove(channel_name)
        if runtime.state in (RuntimeState.RUNNING, RuntimeState.DEGRADED):
            try:
                runtime.transition_to(
                    RuntimeState.IDLE,
                    reason=f"channel_stop:{channel_name}",
                )
            except RuntimeError:
                pass
        if runtime.shutdown_requested:
            runtime.mark_stopped()
        emit_runtime_trace("runtime_channel_stop", channel=channel_name, runtime=get_runtime_snapshot())


def host_runtime(runtime: KioRuntime, idle_wait_s: float = 5.0) -> None:
    """
    Keep the runtime process alive with a minimal idle host loop.

    This is intentionally simple for Gate 0:
      - no background workers
      - no async loop ownership
      - no thread spawning
      - low CPU idle behavior via Event.wait()
    """
    stop_event = threading.Event()
    runtime.mark_idle()
    emit_runtime_trace(
        "runtime_host_start",
        runtime=get_runtime_snapshot(),
        idle_wait_s=idle_wait_s,
    )

    try:
        while not runtime.shutdown_requested:
            stop_event.wait(idle_wait_s)
    except KeyboardInterrupt:
        runtime.request_shutdown()
        emit_runtime_trace("runtime_host_interrupt", runtime=get_runtime_snapshot())
    except Exception as exc:
        runtime.mark_degraded("host_failure", error=str(exc))
        emit_runtime_trace(
            "runtime_host_failure",
            error=str(exc),
            runtime=get_runtime_snapshot(),
        )
        raise
    finally:
        runtime.mark_stopped()
        emit_runtime_trace("runtime_host_stop", runtime=get_runtime_snapshot())


def run_runtime() -> None:
    """
    Runtime-first entrypoint.

    Supports Telegram and/or Discord transports.
    Channels are loaded independently — failure of one does not affect the other.
    """
    runtime = bootstrap_runtime()

    # Start Discord in a daemon thread if configured
    if DISCORD_BOT_TOKEN:
        try:
            from mini_kio.platform.discord_transport import start_discord_thread
            start_discord_thread()
        except Exception as exc:
            logger.error("[DISCORD] failed to start: %s", exc)
            emit_runtime_trace("runtime_channel_failure", channel="discord", error=str(exc))

    if not TELEGRAM_TOKEN:
        if not DISCORD_BOT_TOKEN:
            emit_runtime_trace("runtime_ready_no_channel", runtime=get_runtime_snapshot())
        host_runtime(runtime)
        return

    from kio_bot import run_bot

    start_runtime_channel(runtime, "telegram", run_bot)


if __name__ == "__main__":
    run_runtime()
