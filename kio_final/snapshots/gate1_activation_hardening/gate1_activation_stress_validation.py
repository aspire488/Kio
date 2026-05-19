"""
Gate 1 — Activation stack stress validation (offline).

Run from kio_final/:
  python snapshots/gate1_activation_hardening/gate1_activation_stress_validation.py
"""

from __future__ import annotations

import json
import sys
import time
from dataclasses import dataclass, field
from pathlib import Path
from typing import Callable
from unittest.mock import MagicMock, patch

_ROOT = Path(__file__).resolve().parents[2]
if str(_ROOT) not in sys.path:
    sys.path.insert(0, str(_ROOT))

OBSERVER = "camera_activation"
CYCLES = 25


@dataclass
class ValResult:
    name: str
    passed: bool
    details: str = ""
    metrics: dict = field(default_factory=dict)


def _run(name: str, fn: Callable[[], None]) -> ValResult:
    try:
        metrics: dict = {}
        fn(metrics)
        return ValResult(name, True, metrics=metrics)
    except AssertionError as exc:
        return ValResult(name, False, str(exc))
    except Exception as exc:
        return ValResult(name, False, f"{type(exc).__name__}: {exc}")


def _fresh_runtime():
    import mini_kio.core.runtime as rt
    import mini_kio.core.camera_runtime as cam

    cam._CAMERA_HANDLE = None
    return rt.bootstrap_runtime()


def _enable_observer():
    from mini_kio.core.runtime import set_runtime_observer_enabled

    set_runtime_observer_enabled(OBSERVER, True)


def _dark_frame():
    import numpy as np

    frame = np.full((240, 320, 3), 180, dtype=np.uint8)
    frame[80:160, 100:220] = 35
    return frame


def test_repeated_activation_cycles(metrics: dict) -> None:
    from mini_kio.core.activation import ActivationState, get_activation_snapshot, release_activation, submit_activation_signal

    _fresh_runtime()
    _enable_observer()
    for i in range(CYCLES):
        res = submit_activation_signal(OBSERVER, "manual")
        assert res.get("success"), f"cycle {i} start failed: {res}"
        assert get_activation_snapshot()["state"] == ActivationState.ACTIVE
        release_activation(f"cycle_{i}")
        assert get_activation_snapshot()["state"] == ActivationState.IDLE
    metrics["cycles"] = CYCLES


def test_repeated_full_stack_cycles(metrics: dict) -> None:
    from mini_kio.core.activation import ActivationState, get_activation_snapshot, release_activation
    from mini_kio.core.activation_detection import poll_activation_candidate
    from mini_kio.core.camera_runtime import CameraState, get_camera_snapshot, release_camera_if_open

    release_count = 0

    class _FakeCap:
        def isOpened(self):
            return True

        def read(self):
            return True, _dark_frame()

        def release(self):
            nonlocal release_count
            release_count += 1

    def _fake_open(*_a, device_index=None, **_k):
        import mini_kio.core.camera_runtime as cam

        rt = cam._runtime()
        cam._CAMERA_HANDLE = _FakeCap()
        rt.camera_state = cam.CameraState.OPEN
        rt.camera_frames_polled = 0
        return {
            "success": True,
            "message": "fake open",
            "camera": cam.get_camera_snapshot(),
        }

    with patch("mini_kio.core.camera_runtime._lazy_cv2", return_value=MagicMock()), patch(
        "mini_kio.core.camera_runtime.open_camera", side_effect=_fake_open
    ):
        _fresh_runtime()
        _enable_observer()
        for i in range(10):
            __import__(
                "mini_kio.observers.camera_activation_observer", fromlist=["open_camera_session"]
            ).open_camera_session()
            assert get_camera_snapshot()["state"] == CameraState.OPEN
            poll_activation_candidate(OBSERVER, emit_signal=True)
            assert get_activation_snapshot()["state"] == ActivationState.ACTIVE
            release_activation(f"stack_{i}")
            release_camera_if_open("test")
            assert get_camera_snapshot()["state"] == CameraState.OFF
    metrics["release_calls"] = release_count
    assert release_count >= 10


def test_context_bounded_after_cycles(metrics: dict) -> None:
    from mini_kio.core.activation import release_activation, submit_activation_signal
    from mini_kio.core.runtime import _CURRENT_RUNTIME

    _fresh_runtime()
    _enable_observer()
    for _ in range(CYCLES):
        submit_activation_signal(OBSERVER, "manual")
        release_activation("cycle")
    assert _CURRENT_RUNTIME is not None
    size = len(_CURRENT_RUNTIME.context_items)
    metrics["context_size"] = size
    assert size <= 8, f"context grew unbounded: {size}"


def test_runtime_restart_survival(metrics: dict) -> None:
    from mini_kio.core.activation import ActivationState, get_activation_snapshot, submit_activation_signal
    from mini_kio.core.camera_runtime import CameraState, get_camera_snapshot
    import mini_kio.core.camera_runtime as cam

    _fresh_runtime()
    _enable_observer()
    submit_activation_signal(OBSERVER, "manual")
    cam._CAMERA_HANDLE = MagicMock()

    _fresh_runtime()
    _enable_observer()
    assert get_activation_snapshot()["state"] == ActivationState.IDLE
    assert get_camera_snapshot()["state"] == CameraState.OFF
    assert cam._CAMERA_HANDLE is None
    metrics["rebootstrap"] = True


def test_shutdown_during_active(metrics: dict) -> None:
    from mini_kio.core.activation import ActivationState, get_activation_snapshot, submit_activation_signal

    runtime = _fresh_runtime()
    _enable_observer()
    submit_activation_signal(OBSERVER, "manual")
    runtime.request_shutdown()
    runtime.mark_stopped()
    assert get_activation_snapshot()["state"] == ActivationState.IDLE


def test_observer_disable_during_active(metrics: dict) -> None:
    from mini_kio.core.activation import ActivationState, get_activation_snapshot, submit_activation_signal
    from mini_kio.observers.camera_activation_observer import disable_camera_observer

    _fresh_runtime()
    _enable_observer()
    submit_activation_signal(OBSERVER, "manual")
    disable_camera_observer()
    snap = get_activation_snapshot()
    assert snap["state"] == ActivationState.IDLE


def test_telegram_dispatch_during_active(metrics: dict) -> None:
    from mini_kio.core.activation import submit_activation_signal
    from mini_kio.core.runtime import dispatch_channel_input

    _fresh_runtime()
    _enable_observer()
    submit_activation_signal(OBSERVER, "manual")
    res = dispatch_channel_input("ping", channel="telegram", user_id=1)
    assert res.get("success") is True


def test_rapid_poll_cooldown(metrics: dict) -> None:
    from mini_kio.core.activation_detection import poll_activation_candidate

    def _fake_capture(analyzer):
        return {"success": True, "analysis": analyzer(_dark_frame())}

    with patch("mini_kio.core.camera_runtime.capture_and_analyze", side_effect=_fake_capture):
        _fresh_runtime()
        _enable_observer()
        first = poll_activation_candidate(OBSERVER, emit_signal=True)
        second = poll_activation_candidate(OBSERVER, emit_signal=True)
    assert first.get("signal_emitted") is True
    assert second.get("signal_emitted") is False
    assert second.get("candidate") is True


def test_camera_failure_recovery(metrics: dict) -> None:
    from mini_kio.core.camera_runtime import CameraState, get_camera_snapshot, open_camera, release_camera

    _fresh_runtime()
    _enable_observer()

    def _fail_open(*_a, **_k):
        raise RuntimeError("simulated camera failure")

    with patch("mini_kio.core.camera_runtime._lazy_cv2", return_value=MagicMock()), patch(
        "mini_kio.core.camera_runtime.cv2", create=True
    ):
        import mini_kio.core.camera_runtime as cam

        cam._lazy_cv2 = lambda: MagicMock(VideoCapture=lambda *_: MagicMock(isOpened=lambda: False))
        res = open_camera()
    assert res.get("success") is False
    assert get_camera_snapshot()["state"] in (CameraState.ERROR, CameraState.OFF)
    release_camera("recovery")
    assert get_camera_snapshot()["state"] == CameraState.OFF


def test_no_camera_handle_leak_after_cycles(metrics: dict) -> None:
    import mini_kio.core.camera_runtime as cam
    from mini_kio.core.camera_runtime import release_camera_if_open

    _fresh_runtime()
    cam._CAMERA_HANDLE = MagicMock()
    release_camera_if_open("test")
    assert cam._CAMERA_HANDLE is None


def main() -> int:
    tests = [
        ("repeated activation cycles", test_repeated_activation_cycles),
        ("repeated full stack cycles", test_repeated_full_stack_cycles),
        ("context bounded after cycles", test_context_bounded_after_cycles),
        ("runtime restart survival", test_runtime_restart_survival),
        ("shutdown during active", test_shutdown_during_active),
        ("observer disable during active", test_observer_disable_during_active),
        ("telegram dispatch during active", test_telegram_dispatch_during_active),
        ("rapid poll cooldown", test_rapid_poll_cooldown),
        ("camera failure recovery", test_camera_failure_recovery),
        ("no camera handle leak", test_no_camera_handle_leak_after_cycles),
    ]
    t0 = time.perf_counter()
    results = [_run(name, fn) for name, fn in tests]
    elapsed = time.perf_counter() - t0
    passed = sum(1 for r in results if r.passed)
    report = {
        "passed": passed,
        "total": len(results),
        "elapsed_s": round(elapsed, 2),
        "results": [{**r.__dict__} for r in results],
    }
    print(json.dumps(report, indent=2))
    return 0 if passed == len(results) else 1


if __name__ == "__main__":
    raise SystemExit(main())
