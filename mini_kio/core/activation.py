"""
Runtime-owned activation governance (Gate 1).

Observers may emit signals; only the runtime may change activation state.
Session lifecycle: idle → active → releasing → idle. No background timer threads.
"""

from __future__ import annotations

import logging
import time
from typing import Any

from mini_kio.core.config import ACTIVATION_SESSION_TIMEOUT_S
from mini_kio.core.runtime import (
    RuntimeState,
    emit_runtime_trace,
    get_runtime_snapshot,
    record_runtime_integrity_warning,
    register_runtime_observer,
    remember_runtime_context,
)

logger = logging.getLogger(__name__)

_ACTIVATION_OBSERVER_KIND = "activation"
_ACTIVATION_SIGNAL_TYPES = frozenset({"manual", "test", "gesture_candidate"})


class ActivationState:
    """Interaction-session activation states (orthogonal to process lifecycle)."""

    IDLE = "activation_idle"
    ACTIVE = "activation_active"
    RELEASING = "activation_releasing"


_ALLOWED_ACTIVATION_TRANSITIONS: dict[str, set[str]] = {
    ActivationState.IDLE: {ActivationState.ACTIVE},
    ActivationState.ACTIVE: {ActivationState.RELEASING},
    ActivationState.RELEASING: {ActivationState.IDLE},
}


def _runtime():
    import mini_kio.core.runtime as runtime_module

    return runtime_module._CURRENT_RUNTIME


def _session_timeout_ms(runtime: Any) -> int:
    timeout_s = getattr(runtime, "activation_session_timeout_s", None)
    if timeout_s is None:
        timeout_s = ACTIVATION_SESSION_TIMEOUT_S
    return max(1, int(timeout_s)) * 1000


def _session_elapsed_ms(runtime: Any) -> int | None:
    if runtime.activation_started_at_ms is None:
        return None
    now_ms = int((time.monotonic() - runtime.started_at) * 1000)
    return max(0, now_ms - int(runtime.activation_started_at_ms))


def _transition_activation(
    runtime: Any,
    next_state: str,
    *,
    reason: str,
    observer: str | None = None,
) -> None:
    current = runtime.activation_state
    if current == next_state:
        return

    allowed = _ALLOWED_ACTIVATION_TRANSITIONS.get(current, set())
    if next_state not in allowed:
        record_runtime_integrity_warning(
            "invalid_activation_transition",
            {
                "from_state": current,
                "to_state": next_state,
                "reason": reason,
            },
        )
        emit_runtime_trace(
            "activation_invalid_transition",
            from_state=current,
            to_state=next_state,
            reason=reason,
            runtime=get_runtime_snapshot(),
        )
        raise RuntimeError(
            f"Invalid activation transition: {current} -> {next_state} ({reason})"
        )

    runtime.activation_state = next_state
    if next_state == ActivationState.ACTIVE:
        runtime.activation_session_id += 1
        runtime.activation_observer = observer
        runtime.activation_started_at_ms = int(
            (time.monotonic() - runtime.started_at) * 1000
        )
    elif next_state == ActivationState.IDLE:
        runtime.activation_observer = None
        runtime.activation_started_at_ms = None
        runtime.activation_last_candidate_emitted_ms = None

    emit_runtime_trace(
        "activation_state_transition",
        from_state=current,
        to_state=next_state,
        reason=reason,
        observer=observer or runtime.activation_observer,
        session_id=runtime.activation_session_id,
        runtime=get_runtime_snapshot(),
    )
    remember_runtime_context(
        "activation_state",
        {
            "from_state": current,
            "to_state": next_state,
            "reason": reason,
            "observer": observer or runtime.activation_observer,
            "session_id": runtime.activation_session_id,
        },
    )


def _perform_activation_cleanup(reason: str) -> None:
    """Bounded session cleanup; does not change activation state."""
    try:
        from mini_kio.core.camera_runtime import release_camera_if_open

        release_camera_if_open(f"activation_{reason}")
    except Exception as exc:
        logger.warning("Activation cleanup partial failure: %s", exc)
    remember_runtime_context(
        "activation_cleanup",
        {"reason": reason},
        ttl_s=60,
    )
    emit_runtime_trace("activation_session_cleanup", reason=reason)


def touch_activation_session() -> bool:
    """
    Lazy session timeout check (no background thread).

    Returns True if an active session was expired and released.
    """
    runtime = _runtime()
    if runtime is None or runtime.activation_state != ActivationState.ACTIVE:
        return False

    elapsed = _session_elapsed_ms(runtime)
    if elapsed is None:
        return False
    if elapsed < _session_timeout_ms(runtime):
        return False

    emit_runtime_trace(
        "activation_session_timeout",
        elapsed_ms=elapsed,
        timeout_ms=_session_timeout_ms(runtime),
        session_id=runtime.activation_session_id,
    )
    _execute_activation_release("session_timeout")
    return True


def get_activation_snapshot() -> dict[str, object]:
    """Return current activation governance state after lazy timeout check."""
    runtime = _runtime()
    if runtime is None:
        return {
            "state": ActivationState.IDLE,
            "observer": None,
            "session_id": 0,
            "started_at_ms": None,
            "elapsed_ms": None,
            "remaining_ms": None,
            "session_timeout_s": ACTIVATION_SESSION_TIMEOUT_S,
        }

    touch_activation_session()
    elapsed = _session_elapsed_ms(runtime)
    timeout_ms = _session_timeout_ms(runtime)
    remaining = None
    if runtime.activation_state == ActivationState.ACTIVE and elapsed is not None:
        remaining = max(0, timeout_ms - elapsed)

    return {
        "state": runtime.activation_state,
        "observer": runtime.activation_observer,
        "session_id": runtime.activation_session_id,
        "started_at_ms": runtime.activation_started_at_ms,
        "elapsed_ms": elapsed,
        "remaining_ms": remaining,
        "session_timeout_s": int(timeout_ms / 1000),
    }


def can_accept_activation_signal(observer_name: str, signal_type: str) -> tuple[bool, str]:
    """Gate activation signals before runtime state changes."""
    touch_activation_session()
    runtime = _runtime()
    if runtime is None:
        return False, "Runtime not initialized"
    if runtime.shutdown_requested or runtime.state == RuntimeState.STOPPED:
        return False, "Runtime is not accepting activation"
    if runtime.activation_state != ActivationState.IDLE:
        return False, f"Activation not idle: {runtime.activation_state}"
    if signal_type not in _ACTIVATION_SIGNAL_TYPES:
        return False, f"Unsupported signal type: {signal_type}"

    record = runtime.observers.get(observer_name)
    if record is None:
        return False, f"Observer not registered: {observer_name}"
    if record.get("kind") != _ACTIVATION_OBSERVER_KIND:
        return False, f"Observer is not an activation observer: {observer_name}"
    if not record.get("enabled"):
        return False, f"Observer not enabled: {observer_name}"
    if record.get("health") != "ready":
        return False, f"Observer not ready: {observer_name}"

    return True, ""


def register_activation_observer(
    name: str,
    source: str,
    *,
    observer_type: str,
    enabled: bool = False,
) -> dict[str, object]:
    """Register a disabled-by-default activation observer surface."""
    record = register_runtime_observer(
        name,
        source,
        enabled=enabled,
        kind=_ACTIVATION_OBSERVER_KIND,
        observer_type=observer_type,
    )
    emit_runtime_trace(
        "activation_observer_registered",
        observer=name,
        observer_type=observer_type,
        enabled=enabled,
    )
    return record


def submit_activation_signal(
    observer_name: str,
    signal_type: str,
    *,
    detail: object | None = None,
) -> dict[str, object]:
    """Accept an activation signal; runtime transitions to active when allowed."""
    allowed, reason = can_accept_activation_signal(observer_name, signal_type)
    if not allowed:
        emit_runtime_trace(
            "activation_signal_rejected",
            observer=observer_name,
            signal_type=signal_type,
            reason=reason,
            runtime=get_runtime_snapshot(),
        )
        return {
            "success": False,
            "message": reason,
            "activation": get_activation_snapshot(),
        }

    runtime = _runtime()
    assert runtime is not None

    emit_runtime_trace(
        "activation_signal_received",
        observer=observer_name,
        signal_type=signal_type,
        detail=detail,
        runtime=get_runtime_snapshot(),
    )

    try:
        _transition_activation(
            runtime,
            ActivationState.ACTIVE,
            reason=f"signal:{signal_type}",
            observer=observer_name,
        )
    except RuntimeError as exc:
        return {
            "success": False,
            "message": str(exc),
            "activation": get_activation_snapshot(),
        }

    emit_runtime_trace(
        "activation_session_started",
        observer=observer_name,
        session_id=runtime.activation_session_id,
        timeout_s=int(_session_timeout_ms(runtime) / 1000),
    )
    return {
        "success": True,
        "message": "Activation session started.",
        "activation": get_activation_snapshot(),
    }


def _execute_activation_release(reason: str) -> dict[str, object]:
    """Core release path without re-entering timeout checks."""
    runtime = _runtime()
    if runtime is None:
        return {
            "success": False,
            "message": "Runtime not initialized.",
            "activation": get_activation_snapshot(),
        }

    state = runtime.activation_state
    if state == ActivationState.IDLE:
        return {
            "success": True,
            "message": "Activation already idle.",
            "activation": get_activation_snapshot(),
        }

    if state == ActivationState.RELEASING:
        _perform_activation_cleanup(reason)
        _transition_activation(runtime, ActivationState.IDLE, reason=f"{reason}_complete")
        return {
            "success": True,
            "message": "Activation session release completed.",
            "activation": get_activation_snapshot(),
        }

    emit_runtime_trace(
        "activation_session_releasing",
        reason=reason,
        session_id=runtime.activation_session_id,
        elapsed_ms=_session_elapsed_ms(runtime),
    )
    _transition_activation(runtime, ActivationState.RELEASING, reason=reason)
    _perform_activation_cleanup(reason)
    _transition_activation(runtime, ActivationState.IDLE, reason=f"{reason}_complete")

    return {
        "success": True,
        "message": "Activation session ended.",
        "activation": get_activation_snapshot(),
    }


def release_activation(reason: str = "manual_release") -> dict[str, object]:
    """End session via releasing → cleanup → idle."""
    return _execute_activation_release(reason)


def force_release_activation(reason: str = "runtime_shutdown") -> dict[str, object]:
    """Release any non-idle activation session during shutdown (idempotent)."""
    runtime = _runtime()
    if runtime is None:
        return {"success": True, "message": "No runtime.", "activation": get_activation_snapshot()}
    if runtime.activation_state == ActivationState.IDLE:
        return {
            "success": True,
            "message": "Activation already idle.",
            "activation": get_activation_snapshot(),
        }
    return release_activation(reason=reason)


def prepare_activation_groundwork() -> dict[str, object]:
    """Register prepared activation observers without starting any sensing loops."""
    from mini_kio.observers.camera_activation_observer import (
        register_camera_activation_observer,
    )
    from mini_kio.core.camera_runtime import prepare_camera_groundwork

    runtime = _runtime()
    if runtime is not None:
        runtime.activation_session_timeout_s = ACTIVATION_SESSION_TIMEOUT_S

    camera = register_camera_activation_observer()
    cam_snap = prepare_camera_groundwork()
    snapshot = get_activation_snapshot()
    emit_runtime_trace(
        "activation_groundwork_prepared",
        observers=[camera.get("name")],
        activation=snapshot,
        camera=cam_snap,
        runtime=get_runtime_snapshot(),
    )
    return {"camera_observer": camera, "activation": snapshot, "camera": cam_snap}


# ── Away-event accumulation ──────────────────────────────────────────────
# While the user is away (IDLE state), meaningful events accumulate here.
# On return (ACTIVE transition), the accumulated events are surfaced.
# This is NOT a new store — it's a transient buffer that lives in memory
# and is cleared after being surfaced.
_AWAY_EVENTS: list[dict] = []
_AWAY_EVENT_LIMIT = 10


def record_away_event(source: str, description: str, *,
                      urgency: str = "medium", metadata: dict | None = None) -> None:
    """Record a meaningful event that occurred while the user was away.
    Called by watchers, reminders, workflow completions, system events, etc.
    Events accumulate until the user returns, then get surfaced."""
    runtime = _runtime()
    if runtime is None:
        return
    # Only accumulate when user is not actively engaged
    if runtime.activation_state == ActivationState.ACTIVE:
        return
    import datetime as _dt
    _AWAY_EVENTS.append({
        "source": source,
        "description": description,
        "urgency": urgency,
        "timestamp": _dt.datetime.now(_dt.timezone.utc).isoformat(timespec="seconds"),
        "metadata": metadata or {},
    })
    # Bounded: never accumulate too many
    if len(_AWAY_EVENTS) > _AWAY_EVENT_LIMIT:
        _AWAY_EVENTS.pop(0)


def consume_away_events() -> list[dict]:
    """Retrieve and clear accumulated away events.
    Called when the user returns (ACTIVE transition) so KIO can surface
    meaningful activity that occurred while they were away."""
    events = list(_AWAY_EVENTS)
    _AWAY_EVENTS.clear()
    return events


def has_away_events() -> bool:
    """Check if there are pending away events to surface."""
    return len(_AWAY_EVENTS) > 0


__all__ = [
    "ActivationState",
    "can_accept_activation_signal",
    "consume_away_events",
    "force_release_activation",
    "get_activation_snapshot",
    "has_away_events",
    "prepare_activation_groundwork",
    "record_away_event",
    "register_activation_observer",
    "release_activation",
    "submit_activation_signal",
    "touch_activation_session",
]
