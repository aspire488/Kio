"""
Runtime-owned camera lifecycle (Gate 1 lightweight integration).

Lazy-loads capture backends only on explicit open. No gesture recognition,
no background loops, no frame retention beyond a single poll call.
"""

from __future__ import annotations

import logging
import time
from typing import Any, Callable

from mini_kio.core.config import CAMERA_DEVICE_INDEX, CAMERA_MAX_FRAMES_PER_POLL
from mini_kio.core.runtime import (
    RuntimeState,
    emit_runtime_trace,
    get_runtime_snapshot,
    record_runtime_integrity_warning,
    remember_runtime_context,
)

logger = logging.getLogger(__name__)

_CAMERA_HANDLE: Any = None
_CAMERA_MAX_SESSION_FRAMES = 64


class CameraState:
    """Runtime-owned camera resource states (orthogonal to process lifecycle)."""

    OFF = "camera_off"
    OPENING = "camera_opening"
    OPEN = "camera_open"
    ERROR = "camera_error"


_ALLOWED_CAMERA_TRANSITIONS: dict[str, set[str]] = {
    CameraState.OFF: {CameraState.OPENING},
    CameraState.OPENING: {CameraState.OPEN, CameraState.ERROR, CameraState.OFF},
    CameraState.OPEN: {CameraState.OFF, CameraState.ERROR},
    CameraState.ERROR: {CameraState.OFF, CameraState.OPENING},
}


def _runtime():
    import mini_kio.core.runtime as runtime_module

    return runtime_module._CURRENT_RUNTIME


def _set_camera_state(runtime: Any, next_state: str, *, reason: str, error: str | None = None) -> None:
    current = runtime.camera_state
    if current == next_state:
        return

    allowed = _ALLOWED_CAMERA_TRANSITIONS.get(current, set())
    if next_state not in allowed:
        record_runtime_integrity_warning(
            "invalid_camera_transition",
            {"from_state": current, "to_state": next_state, "reason": reason},
        )
        emit_runtime_trace(
            "camera_invalid_transition",
            from_state=current,
            to_state=next_state,
            reason=reason,
            runtime=get_runtime_snapshot(),
        )
        raise RuntimeError(
            f"Invalid camera transition: {current} -> {next_state} ({reason})"
        )

    runtime.camera_state = next_state
    runtime.camera_last_error = error
    emit_runtime_trace(
        "camera_state_transition",
        from_state=current,
        to_state=next_state,
        reason=reason,
        error=error,
        runtime=get_runtime_snapshot(),
    )
    remember_runtime_context(
        "camera_state",
        {
            "from_state": current,
            "to_state": next_state,
            "reason": reason,
            "error": error,
        },
    )


def _release_handle() -> None:
    global _CAMERA_HANDLE
    if _CAMERA_HANDLE is None:
        return
    try:
        _CAMERA_HANDLE.release()
    except Exception as exc:
        logger.warning("Camera release failed: %s", exc)
    finally:
        _CAMERA_HANDLE = None


def _lazy_cv2() -> Any:
    import cv2  # noqa: PLC0415 — lazy import by design

    return cv2


def _require_camera_observer_ready() -> tuple[bool, str]:
    from mini_kio.observers.camera_activation_observer import OBSERVER_NAME

    runtime = _runtime()
    if runtime is None:
        return False, "Runtime not initialized"
    record = runtime.observers.get(OBSERVER_NAME)
    if record is None:
        return False, f"Observer not registered: {OBSERVER_NAME}"
    if not record.get("enabled"):
        return False, "Camera observer not enabled"
    if record.get("health") != "ready":
        return False, "Camera observer not ready"
    return True, ""


def get_camera_snapshot() -> dict[str, object]:
    """Return current runtime-owned camera state (no frame buffers)."""
    runtime = _runtime()
    if runtime is None:
        return {
            "state": CameraState.OFF,
            "device_index": CAMERA_DEVICE_INDEX,
            "frames_polled": 0,
            "last_error": None,
            "handle_attached": False,
            "max_frames_per_poll": CAMERA_MAX_FRAMES_PER_POLL,
            "max_session_frames": _CAMERA_MAX_SESSION_FRAMES,
        }

    return {
        "state": runtime.camera_state,
        "device_index": runtime.camera_device_index,
        "frames_polled": runtime.camera_frames_polled,
        "last_error": runtime.camera_last_error,
        "handle_attached": _CAMERA_HANDLE is not None,
        "max_frames_per_poll": CAMERA_MAX_FRAMES_PER_POLL,
        "max_session_frames": _CAMERA_MAX_SESSION_FRAMES,
    }


def can_open_camera() -> tuple[bool, str]:
    """Gate explicit camera open requests."""
    runtime = _runtime()
    if runtime is None:
        return False, "Runtime not initialized"
    if runtime.shutdown_requested or runtime.state == RuntimeState.STOPPED:
        return False, "Runtime is not accepting camera open"
    if runtime.camera_state not in (CameraState.OFF, CameraState.ERROR):
        return False, f"Camera not idle: {runtime.camera_state}"
    return _require_camera_observer_ready()


def prepare_camera_groundwork() -> dict[str, object]:
    """Initialize runtime camera fields without opening hardware."""
    _release_handle()
    runtime = _runtime()
    if runtime is None:
        return get_camera_snapshot()

    runtime.camera_state = CameraState.OFF
    runtime.camera_device_index = CAMERA_DEVICE_INDEX
    runtime.camera_last_error = None
    runtime.camera_frames_polled = 0
    emit_runtime_trace(
        "camera_groundwork_prepared",
        camera=get_camera_snapshot(),
        runtime=get_runtime_snapshot(),
    )
    return get_camera_snapshot()


def open_camera(*, device_index: int | None = None) -> dict[str, object]:
    """Explicitly acquire the camera device under runtime ownership."""
    allowed, reason = can_open_camera()
    if not allowed:
        emit_runtime_trace("camera_open_rejected", reason=reason, runtime=get_runtime_snapshot())
        return {"success": False, "message": reason, "camera": get_camera_snapshot()}

    runtime = _runtime()
    assert runtime is not None
    index = CAMERA_DEVICE_INDEX if device_index is None else device_index
    runtime.camera_device_index = index

    try:
        _set_camera_state(runtime, CameraState.OPENING, reason="explicit_open")
    except RuntimeError as exc:
        return {"success": False, "message": str(exc), "camera": get_camera_snapshot()}

    try:
        cv2 = _lazy_cv2()
    except ImportError as exc:
        _set_camera_state(runtime, CameraState.ERROR, reason="cv2_unavailable", error=str(exc))
        return {
            "success": False,
            "message": "OpenCV not available (cv2).",
            "camera": get_camera_snapshot(),
        }

    global _CAMERA_HANDLE
    _release_handle()
    try:
        capture = cv2.VideoCapture(index)
        if not capture.isOpened():
            raise RuntimeError(f"Camera device {index} did not open")
        _CAMERA_HANDLE = capture
        _set_camera_state(runtime, CameraState.OPEN, reason="explicit_open")
        emit_runtime_trace(
            "camera_opened",
            device_index=index,
            camera=get_camera_snapshot(),
            runtime=get_runtime_snapshot(),
        )
        return {
            "success": True,
            "message": f"Camera opened (device {index}).",
            "camera": get_camera_snapshot(),
        }
    except Exception as exc:
        _release_handle()
        _set_camera_state(runtime, CameraState.ERROR, reason="open_failed", error=str(exc)[:120])
        record_runtime_integrity_warning(
            "camera_failure",
            {"action": "open", "device_index": index, "error": str(exc)[:120]},
        )
        return {
            "success": False,
            "message": f"Camera open failed: {str(exc)[:120]}",
            "camera": get_camera_snapshot(),
        }


def release_camera(reason: str = "explicit_release") -> dict[str, object]:
    """Release camera hardware and return to off state."""
    runtime = _runtime()
    if runtime is None:
        return {
            "success": False,
            "message": "Runtime not initialized.",
            "camera": get_camera_snapshot(),
        }

    _release_handle()
    previous = runtime.camera_state
    if previous == CameraState.OFF:
        return {
            "success": True,
            "message": "Camera already off.",
            "camera": get_camera_snapshot(),
        }

    runtime.camera_frames_polled = 0
    runtime.camera_last_error = None
    try:
        if previous != CameraState.OFF:
            _set_camera_state(runtime, CameraState.OFF, reason=reason)
    except RuntimeError:
        runtime.camera_state = CameraState.OFF

    emit_runtime_trace(
        "camera_released",
        reason=reason,
        camera=get_camera_snapshot(),
        runtime=get_runtime_snapshot(),
    )
    return {
        "success": True,
        "message": "Camera released.",
        "camera": get_camera_snapshot(),
    }


def release_camera_if_open(reason: str = "implicit_release") -> dict[str, object]:
    """Idempotent release used during shutdown and session cleanup."""
    runtime = _runtime()
    if _CAMERA_HANDLE is not None:
        if runtime is None:
            _release_handle()
            emit_runtime_trace("camera_orphan_handle_released", reason=reason)
            return {
                "success": True,
                "message": "Orphaned camera handle released.",
                "camera": get_camera_snapshot(),
            }
        return release_camera(reason=reason)
    if runtime is None or runtime.camera_state == CameraState.OFF:
        return {"success": True, "message": "Camera already off.", "camera": get_camera_snapshot()}
    return release_camera(reason=reason)


def capture_and_analyze(
    analyzer: Callable[[Any], dict[str, object]],
) -> dict[str, object]:
    """
    Read one frame, run a lightweight analyzer, discard buffer immediately.

    Used by activation detection; frames are never retained after analysis.
    """
    runtime = _runtime()
    if runtime is None:
        return {
            "success": False,
            "message": "Runtime not initialized.",
            "analysis": None,
        }
    if runtime.camera_state != CameraState.OPEN or _CAMERA_HANDLE is None:
        return {
            "success": False,
            "message": f"Camera not open: {runtime.camera_state}",
            "analysis": None,
        }
    if runtime.camera_frames_polled >= _CAMERA_MAX_SESSION_FRAMES:
        return {
            "success": False,
            "message": "Camera session frame limit reached.",
            "analysis": None,
        }

    frame = None
    try:
        ok, frame = _CAMERA_HANDLE.read()
        if not ok or frame is None:
            _release_handle()
            _set_camera_state(runtime, CameraState.ERROR, reason="capture_failed", error="no frame")
            return {"success": False, "message": "Frame capture failed.", "analysis": None}

        runtime.camera_frames_polled += 1
        analysis = analyzer(frame)
        height, width = frame.shape[:2]
        emit_runtime_trace(
            "camera_frame_analyzed",
            width=width,
            height=height,
            is_candidate=bool(analysis.get("is_candidate")),
            heuristic=analysis.get("heuristic"),
            camera=get_camera_snapshot(),
            runtime=get_runtime_snapshot(),
        )
        return {
            "success": True,
            "message": "Frame analyzed.",
            "analysis": analysis,
            "width": width,
            "height": height,
        }
    except Exception as exc:
        _set_camera_state(runtime, CameraState.ERROR, reason="analyze_exception", error=str(exc)[:120])
        record_runtime_integrity_warning(
            "camera_failure",
            {"action": "analyze", "error": str(exc)[:120]},
        )
        return {
            "success": False,
            "message": f"Frame analysis error: {str(exc)[:120]}",
            "analysis": None,
        }
    finally:
        if frame is not None:
            del frame


def poll_frame() -> dict[str, object]:
    """
    Bounded single-shot frame poll while camera is open.

    Returns frame metadata only; raw pixel buffers are not retained.
    """
    runtime = _runtime()
    if runtime is None:
        return {
            "success": False,
            "message": "Runtime not initialized.",
            "camera": get_camera_snapshot(),
        }
    if runtime.camera_state != CameraState.OPEN or _CAMERA_HANDLE is None:
        return {
            "success": False,
            "message": f"Camera not open: {runtime.camera_state}",
            "camera": get_camera_snapshot(),
        }
    if runtime.camera_frames_polled >= _CAMERA_MAX_SESSION_FRAMES:
        return {
            "success": False,
            "message": "Camera session frame limit reached.",
            "camera": get_camera_snapshot(),
        }

    try:
        frames_read = 0
        width = height = 0
        for _ in range(CAMERA_MAX_FRAMES_PER_POLL):
            ok, frame = _CAMERA_HANDLE.read()
            if not ok or frame is None:
                break
            height, width = frame.shape[:2]
            del frame
            frames_read += 1

        if frames_read == 0:
            _release_handle()
            _set_camera_state(runtime, CameraState.ERROR, reason="poll_failed", error="no frame")
            return {
                "success": False,
                "message": "Frame poll failed.",
                "camera": get_camera_snapshot(),
            }

        runtime.camera_frames_polled += frames_read
        meta = {
            "width": width,
            "height": height,
            "frames_read": frames_read,
            "session_total": runtime.camera_frames_polled,
            "polled_at_ms": int((time.monotonic() - runtime.started_at) * 1000),
        }
        emit_runtime_trace(
            "camera_frame_polled",
            frame=meta,
            camera=get_camera_snapshot(),
            runtime=get_runtime_snapshot(),
        )
        return {
            "success": True,
            "message": "Frame polled.",
            "frame": meta,
            "camera": get_camera_snapshot(),
        }
    except Exception as exc:
        _set_camera_state(runtime, CameraState.ERROR, reason="poll_exception", error=str(exc)[:120])
        record_runtime_integrity_warning(
            "camera_failure",
            {"action": "poll", "error": str(exc)[:120]},
        )
        return {
            "success": False,
            "message": f"Frame poll error: {str(exc)[:120]}",
            "camera": get_camera_snapshot(),
        }


__all__ = [
    "CameraState",
    "can_open_camera",
    "capture_and_analyze",
    "get_camera_snapshot",
    "open_camera",
    "poll_frame",
    "prepare_camera_groundwork",
    "release_camera",
    "release_camera_if_open",
]
