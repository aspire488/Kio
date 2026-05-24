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
import sys
import threading
import time
from pathlib import Path
from typing import Any, Callable

from mini_kio.core.config import TELEGRAM_TOKEN

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

    def register_tracked_process(self, pid: int, name: str, target: str) -> None:
        """Register a new tracked process with a FIFO 16-entry limit."""
        emit_runtime_trace("DEBUG_runtime_register_start", pid=pid, name=name, target=target)
        import psutil
        try:
            p = psutil.Process(pid)
            create_time = p.create_time()
        except (psutil.NoSuchProcess, psutil.AccessDenied):
            create_time = 0.0

        entry = {
            "pid": pid,
            "name": name,
            "target": target,
            "launched_at": time.monotonic(),
            "create_time": create_time,
            "status": "active",
        }
        self.tracked_processes = [
            existing for existing in self.tracked_processes
            if existing.get("name") != name
        ]
        # FIFO eviction
        while len(self.tracked_processes) >= 16:
            oldest = self.tracked_processes.pop(0)
            emit_runtime_trace("runtime_process_evicted", pid=oldest["pid"], name=oldest["name"])

        self.tracked_processes.append(entry)
        emit_runtime_trace("runtime_process_registered", pid=pid, name=name, target=target)
        emit_runtime_trace("DEBUG_runtime_registry_size", size=len(self.tracked_processes), contents=[(e["pid"], e["name"]) for e in self.tracked_processes])

    def refresh_tracked_process(self, pid: int, name: str, target: str) -> None:
        """Refresh or replace an existing tracked process entry for a canonical family."""
        emit_runtime_trace("DEBUG_runtime_refresh_start", pid=pid, name=name, target=target)
        self.unregister_tracked_process(name)
        self.register_tracked_process(pid=pid, name=name, target=target)

    def get_tracked_process(self, name: str) -> dict[str, object] | None:
        """Find a tracked process by its canonical name."""
        emit_runtime_trace("DEBUG_runtime_lookup_start", lookup_name=name, registry_size=len(self.tracked_processes))
        for entry in reversed(self.tracked_processes):
            if entry["name"] == name:
                emit_runtime_trace("DEBUG_runtime_lookup_hit", pid=entry["pid"], name=name)
                return entry
        emit_runtime_trace("DEBUG_runtime_lookup_miss", lookup_name=name)
        return None

    def unregister_tracked_process(self, name: str, pid: int | None = None) -> None:
        """Remove tracked process entries by canonical family and optional pid."""
        emit_runtime_trace("DEBUG_runtime_unregister_start", name=name, pid=pid)
        retained: list[dict[str, object]] = []
        for entry in self.tracked_processes:
            same_name = entry.get("name") == name
            same_pid = pid is None or int(entry.get("pid", -1)) == int(pid)
            if same_name and same_pid:
                emit_runtime_trace(
                    "runtime_process_unregistered",
                    pid=entry.get("pid"),
                    name=entry.get("name"),
                    reason="verified_close",
                )
                continue
            retained.append(entry)
        self.tracked_processes = retained
        emit_runtime_trace("DEBUG_runtime_unregister_end", name=name, pid=pid, count=len(self.tracked_processes))

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
    """
    Gate 3 orchestration pipeline for non-deterministic input.

    Pipeline: intent_classifier -> intent_validator -> conversation_orchestrator -> runtime_handoff
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
        runtime._gate3_pipeline = {
            'classifier': IntentClassifier(),
            'validator': IntentValidator(),
            'orchestrator': ConversationOrchestrator(),
            'handoff': RuntimeHandoff(),
        }

    pipe = runtime._gate3_pipeline

    emit_runtime_trace("intent_classification", text_len=len(text))
    classification = pipe['classifier'].classify(text)

    emit_runtime_trace("validator_result",
                       is_safe=classification.is_safe,
                       intent_type=str(classification.primary_intent.intent_type)
                       if classification.primary_intent else "none")
    validated = pipe['validator'].validate(classification)

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
    from mini_kio.llm.conversation_responder import ConversationResponder
    responder = ConversationResponder()
    try:
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

    command = (text or "").strip()
    if not command:
        return {
            "success": False,
            "message": "Empty command.",
            "channel": channel,
        }
    if len(command) > _CHANNEL_INPUT_MAX_LEN:
        return {
            "success": False,
            "message": f"Input too long (max {_CHANNEL_INPUT_MAX_LEN} characters).",
            "channel": channel,
        }

    emit_runtime_trace(
        "orchestration_entry",
        channel=channel,
        user_id=user_id,
        text_len=len(command),
        runtime=get_runtime_snapshot(),
    )

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
        result = _route_via_orchestration(command)

    if not isinstance(result, dict):
        result = {"success": False, "message": str(result)}

    remember_runtime_context(
        "channel_input",
        {
            "channel": channel,
            "user_id": user_id,
            "success": bool(result.get("success")),
        },
    )
    result["channel"] = channel
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
    return {
        "state": runtime.state,
        "safety_state": runtime.safety_state,
        "channels": list(runtime.channels),
        "uptime_ms": uptime_ms,
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

    runtime.mark_ready()

    from mini_kio.core.activation import prepare_activation_groundwork

    prepare_activation_groundwork()
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

    Telegram remains a prototype channel and is loaded only after runtime
    bootstrap chooses to attach it.
    """
    runtime = bootstrap_runtime()

    if not TELEGRAM_TOKEN:
        emit_runtime_trace("runtime_ready_no_channel", runtime=get_runtime_snapshot())
        host_runtime(runtime)
        return

    from kio_bot import run_bot

    start_runtime_channel(runtime, "telegram", run_bot)


if __name__ == "__main__":
    run_runtime()
