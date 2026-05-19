"""
Gate 1 — Minimal activation detection validation (offline).

Run from kio_final/:
  python snapshots/gate1_activation_detection/gate1_activation_detection_validation.py
"""

from __future__ import annotations

import ast
import json
import sys
from dataclasses import dataclass
from pathlib import Path
from typing import Callable
from unittest.mock import patch

_ROOT = Path(__file__).resolve().parents[2]
if str(_ROOT) not in sys.path:
    sys.path.insert(0, str(_ROOT))


@dataclass
class ValResult:
    name: str
    passed: bool
    details: str = ""


def _run(name: str, fn: Callable[[], None]) -> ValResult:
    try:
        fn()
        return ValResult(name, True)
    except AssertionError as exc:
        return ValResult(name, False, str(exc))
    except Exception as exc:
        return ValResult(name, False, f"{type(exc).__name__}: {exc}")


def _dark_center_frame():
    import numpy as np

    frame = np.full((240, 320, 3), 180, dtype=np.uint8)
    frame[80:160, 100:220] = 35
    return frame


def _uniform_frame():
    import numpy as np

    return np.full((240, 320, 3), 150, dtype=np.uint8)


def test_heuristic_detects_dark_center() -> None:
    from mini_kio.core.activation_detection import analyze_frame_heuristic

    result = analyze_frame_heuristic(_dark_center_frame())
    assert result.get("is_candidate") is True
    assert float(result.get("delta", 0)) >= 12.0


def test_heuristic_rejects_uniform_frame() -> None:
    from mini_kio.core.activation_detection import analyze_frame_heuristic

    result = analyze_frame_heuristic(_uniform_frame())
    assert result.get("is_candidate") is False


def test_poll_fails_without_camera() -> None:
    from mini_kio.core.activation_detection import poll_activation_candidate
    from mini_kio.core.runtime import bootstrap_runtime
    from mini_kio.observers.camera_activation_observer import OBSERVER_NAME

    bootstrap_runtime()
    res = poll_activation_candidate(OBSERVER_NAME, emit_signal=False)
    assert res.get("success") is False


def test_candidate_signal_emits_activation() -> None:
    from mini_kio.core.activation import ActivationState, get_activation_snapshot
    from mini_kio.core.activation_detection import poll_activation_candidate
    from mini_kio.core.runtime import bootstrap_runtime, set_runtime_observer_enabled
    from mini_kio.observers.camera_activation_observer import OBSERVER_NAME

    bootstrap_runtime()
    set_runtime_observer_enabled(OBSERVER_NAME, True)

    def _fake_capture(analyzer):
        return {
            "success": True,
            "analysis": analyzer(_dark_center_frame()),
            "width": 320,
            "height": 240,
        }

    with patch("mini_kio.core.camera_runtime.capture_and_analyze", side_effect=_fake_capture):
        res = poll_activation_candidate(OBSERVER_NAME, emit_signal=True)

    assert res.get("candidate") is True
    assert res.get("signal_emitted") is True
    assert get_activation_snapshot()["state"] == ActivationState.ACTIVE


def test_candidate_cooldown_suppresses_second_signal() -> None:
    from mini_kio.core.activation_detection import poll_activation_candidate
    from mini_kio.core.runtime import bootstrap_runtime, set_runtime_observer_enabled
    from mini_kio.observers.camera_activation_observer import OBSERVER_NAME

    bootstrap_runtime()
    set_runtime_observer_enabled(OBSERVER_NAME, True)

    def _fake_capture(analyzer):
        return {"success": True, "analysis": analyzer(_dark_center_frame())}

    with patch("mini_kio.core.camera_runtime.capture_and_analyze", side_effect=_fake_capture):
        first = poll_activation_candidate(OBSERVER_NAME, emit_signal=True)
        second = poll_activation_candidate(OBSERVER_NAME, emit_signal=True)

    assert first.get("signal_emitted") is True
    assert second.get("candidate") is True
    assert second.get("signal_emitted") is False


def test_no_ml_imports_in_detection_module() -> None:
    import mini_kio.core.activation_detection as mod

    tree = ast.parse(Path(mod.__file__).read_text(encoding="utf-8"))
    banned = {"mediapipe", "tensorflow", "torch", "yolo", "ultralytics"}
    for node in ast.walk(tree):
        if isinstance(node, ast.Import):
            for alias in node.names:
                assert alias.name.split(".")[0] not in banned
        elif isinstance(node, ast.ImportFrom) and node.module:
            assert node.module.split(".")[0] not in banned


def main() -> int:
    tests = [
        ("heuristic detects dark center", test_heuristic_detects_dark_center),
        ("heuristic rejects uniform frame", test_heuristic_rejects_uniform_frame),
        ("poll fails without camera", test_poll_fails_without_camera),
        ("candidate signal emits activation", test_candidate_signal_emits_activation),
        ("cooldown suppresses second signal", test_candidate_cooldown_suppresses_second_signal),
        ("no ML imports in detection", test_no_ml_imports_in_detection_module),
    ]
    results = [_run(name, fn) for name, fn in tests]
    passed = sum(1 for r in results if r.passed)
    print(json.dumps({"passed": passed, "total": len(results), "results": [r.__dict__ for r in results]}, indent=2))
    return 0 if passed == len(results) else 1


if __name__ == "__main__":
    raise SystemExit(main())
