"""
Minimal activation-candidate detection (Gate 1).

Non-ML heuristic analysis on manually polled frames only. Observers must not
emit activation signals directly — this module may call submit_activation_signal
after runtime gating when a candidate is accepted.
"""

from __future__ import annotations

import logging
import time
from typing import Any, Callable

from mini_kio.core.runtime import emit_runtime_trace, get_runtime_snapshot

logger = logging.getLogger(__name__)

_CENTER_DARKNESS_DELTA = 12.0
_MIN_CENTER_STD = 4.0
_MIN_FRAME_PIXELS = 10_000
_ACTIVATION_CANDIDATE_COOLDOWN_MS = 2000


def _runtime():
    import mini_kio.core.runtime as runtime_module

    return runtime_module._CURRENT_RUNTIME


def _lazy_cv2() -> Any:
    import cv2  # noqa: PLC0415

    return cv2


def analyze_frame_heuristic(frame: Any) -> dict[str, object]:
    """
    Very lightweight center-darkness heuristic (proxy for fist-near-camera).

    Not gesture recognition — only a bounded activation candidate hint.
    """
    cv2 = _lazy_cv2()
    gray = cv2.cvtColor(frame, cv2.COLOR_BGR2GRAY)
    height, width = gray.shape[:2]
    pixels = height * width
    if pixels < _MIN_FRAME_PIXELS:
        return {
            "is_candidate": False,
            "score": 0.0,
            "heuristic": "center_darkness",
            "reason": "frame_too_small",
            "width": width,
            "height": height,
        }

    y1, y2 = int(height * 0.30), int(height * 0.70)
    x1, x2 = int(width * 0.30), int(width * 0.70)
    center = gray[y1:y2, x1:x2]
    center_mean = float(center.mean())
    center_std = float(center.std())
    outer_mean = float(gray.mean())
    delta = outer_mean - center_mean
    score = max(0.0, min(1.0, delta / 40.0))
    is_candidate = (
        delta >= _CENTER_DARKNESS_DELTA and center_std >= _MIN_CENTER_STD
    )

    return {
        "is_candidate": is_candidate,
        "score": round(score, 3),
        "heuristic": "center_darkness",
        "center_mean": round(center_mean, 1),
        "outer_mean": round(outer_mean, 1),
        "center_std": round(center_std, 1),
        "delta": round(delta, 1),
        "width": width,
        "height": height,
    }


def poll_activation_candidate(
    observer_name: str,
    *,
    emit_signal: bool = True,
) -> dict[str, object]:
    """
    Manual bounded poll + heuristic analysis + optional activation signal.

    No background loop. Caller must invoke explicitly while camera is open.
    """
    from mini_kio.core.activation import (
        get_activation_snapshot,
        submit_activation_signal,
        touch_activation_session,
    )
    from mini_kio.core.camera_runtime import capture_and_analyze, get_camera_snapshot

    touch_activation_session()
    capture_result = capture_and_analyze(analyze_frame_heuristic)
    if not capture_result.get("success"):
        return {
            "success": False,
            "message": str(capture_result.get("message", "Capture failed.")),
            "candidate": False,
            "signal_emitted": False,
            "analysis": capture_result.get("analysis"),
            "camera": get_camera_snapshot(),
            "activation": get_activation_snapshot(),
        }

    analysis = capture_result.get("analysis") or {}
    is_candidate = bool(analysis.get("is_candidate"))

    emit_runtime_trace(
        "activation_candidate_polled",
        observer=observer_name,
        is_candidate=is_candidate,
        analysis=analysis,
        runtime=get_runtime_snapshot(),
    )

    if not is_candidate:
        return {
            "success": True,
            "message": "No activation candidate.",
            "candidate": False,
            "signal_emitted": False,
            "analysis": analysis,
            "camera": get_camera_snapshot(),
            "activation": get_activation_snapshot(),
        }

    if not emit_signal:
        return {
            "success": True,
            "message": "Candidate detected (signal not emitted).",
            "candidate": True,
            "signal_emitted": False,
            "analysis": analysis,
            "camera": get_camera_snapshot(),
            "activation": get_activation_snapshot(),
        }

    runtime = _runtime()
    now_ms = int((time.monotonic() - runtime.started_at) * 1000) if runtime else 0
    if runtime is not None and runtime.activation_last_candidate_emitted_ms is not None:
        elapsed = now_ms - runtime.activation_last_candidate_emitted_ms
        if elapsed < _ACTIVATION_CANDIDATE_COOLDOWN_MS:
            emit_runtime_trace(
                "activation_candidate_cooldown",
                observer=observer_name,
                elapsed_ms=elapsed,
                cooldown_ms=_ACTIVATION_CANDIDATE_COOLDOWN_MS,
            )
            return {
                "success": True,
                "message": "Candidate suppressed (cooldown).",
                "candidate": True,
                "signal_emitted": False,
                "analysis": analysis,
                "camera": get_camera_snapshot(),
                "activation": get_activation_snapshot(),
            }

    signal_result = submit_activation_signal(
        observer_name,
        "gesture_candidate",
        detail=analysis,
    )
    emitted = bool(signal_result.get("success"))
    if emitted and runtime is not None:
        runtime.activation_last_candidate_emitted_ms = now_ms

    emit_runtime_trace(
        "activation_candidate_signal",
        observer=observer_name,
        emitted=emitted,
        signal_success=signal_result.get("success"),
        runtime=get_runtime_snapshot(),
    )

    return {
        "success": True,
        "message": (
            "Activation signal emitted."
            if emitted
            else str(signal_result.get("message", "Signal rejected."))
        ),
        "candidate": True,
        "signal_emitted": emitted,
        "analysis": analysis,
        "signal": signal_result,
        "camera": get_camera_snapshot(),
        "activation": get_activation_snapshot(),
    }


__all__ = [
    "analyze_frame_heuristic",
    "poll_activation_candidate",
]
