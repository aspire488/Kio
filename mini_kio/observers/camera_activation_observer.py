"""
Camera activation observer — runtime-attached, explicitly enabled.

Provides observer registration and thin wrappers into runtime-owned camera APIs.
No gesture recognition, no autonomous capture loops.
"""

from __future__ import annotations

from typing import Any

from mini_kio.core.runtime import set_runtime_observer_enabled, update_runtime_observer_health

OBSERVER_NAME = "camera_activation"
OBSERVER_SOURCE = "camera"
OBSERVER_TYPE = "camera"


def register_camera_activation_observer(*, enabled: bool = False) -> dict[str, Any]:
    """Register the camera activation observer surface (disabled by default)."""
    from mini_kio.core.activation import register_activation_observer

    return register_activation_observer(
        OBSERVER_NAME,
        OBSERVER_SOURCE,
        observer_type=OBSERVER_TYPE,
        enabled=enabled,
    )


def enable_camera_observer() -> dict[str, Any]:
    """Manually enable the camera observer without opening hardware."""
    return set_runtime_observer_enabled(OBSERVER_NAME, True)


def disable_camera_observer() -> dict[str, Any]:
    """Disable observer, end activation session, and release camera hardware."""
    from mini_kio.core.activation import force_release_activation
    from mini_kio.core.camera_runtime import release_camera_if_open

    force_release_activation("observer_disabled")
    release_camera_if_open("observer_disabled")
    return set_runtime_observer_enabled(OBSERVER_NAME, False)


def open_camera_session(*, device_index: int | None = None) -> dict[str, Any]:
    """Open camera under runtime ownership (requires observer enabled)."""
    from mini_kio.core.camera_runtime import open_camera

    result = open_camera(device_index=device_index)
    if result.get("success"):
        update_runtime_observer_health(OBSERVER_NAME, "ready")
    else:
        update_runtime_observer_health(
            OBSERVER_NAME,
            "degraded",
            error=str(result.get("message", ""))[:120],
        )
    return result


def close_camera_session(reason: str = "session_close") -> dict[str, Any]:
    """Release camera and keep observer enabled for future sessions."""
    from mini_kio.core.camera_runtime import release_camera

    result = release_camera(reason=reason)
    update_runtime_observer_health(OBSERVER_NAME, "ready")
    return result


def poll_camera_frame() -> dict[str, Any]:
    """Bounded frame poll — metadata only, no gesture processing."""
    from mini_kio.core.camera_runtime import poll_frame

    return poll_frame()


def poll_activation_candidate(*, emit_signal: bool = True) -> dict[str, Any]:
    """
    Manual poll + lightweight heuristic + optional gesture_candidate signal.

    Detection does not run automatically; call only while camera session is open.
    """
    from mini_kio.core.activation_detection import poll_activation_candidate as _poll

    return _poll(OBSERVER_NAME, emit_signal=emit_signal)


def describe_prepared_capabilities() -> dict[str, str]:
    """Document the controlled camera flow for future fist activation."""
    return {
        "observer": OBSERVER_NAME,
        "mode": "runtime_owned_camera",
        "open": "open_camera_session() after enable_camera_observer()",
        "poll": "poll_camera_frame() — metadata only",
        "detect": "poll_activation_candidate() — heuristic + optional signal",
        "close": "close_camera_session()",
        "signal": "gesture_candidate via runtime submit_activation_signal()",
        "note": "Never open camera on boot; never auto-poll; no ML pipelines.",
    }
