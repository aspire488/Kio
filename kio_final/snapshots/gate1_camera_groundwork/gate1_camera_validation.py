"""
Gate 1 — Lightweight camera integration validation (offline).

Run from kio_final/:
  python snapshots/gate1_camera_groundwork/gate1_camera_validation.py
"""

from __future__ import annotations

import ast
import json
import sys
from dataclasses import dataclass
from pathlib import Path
from typing import Callable

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


def test_camera_off_after_bootstrap() -> None:
    from mini_kio.core.camera_runtime import CameraState, get_camera_snapshot
    from mini_kio.core.runtime import bootstrap_runtime

    bootstrap_runtime()
    assert get_camera_snapshot()["state"] == CameraState.OFF


def test_open_rejected_when_observer_disabled() -> None:
    from mini_kio.core.camera_runtime import open_camera
    from mini_kio.core.runtime import bootstrap_runtime

    bootstrap_runtime()
    res = open_camera()
    assert res.get("success") is False


def test_poll_rejected_when_off() -> None:
    from mini_kio.core.camera_runtime import poll_frame
    from mini_kio.core.runtime import bootstrap_runtime

    bootstrap_runtime()
    res = poll_frame()
    assert res.get("success") is False


def test_release_idempotent_when_off() -> None:
    from mini_kio.core.camera_runtime import CameraState, get_camera_snapshot, release_camera
    from mini_kio.core.runtime import bootstrap_runtime

    bootstrap_runtime()
    res = release_camera()
    assert res.get("success") is True
    assert get_camera_snapshot()["state"] == CameraState.OFF


def test_shutdown_releases_camera() -> None:
    from mini_kio.core.camera_runtime import CameraState, get_camera_snapshot
    from mini_kio.core.runtime import bootstrap_runtime

    runtime = bootstrap_runtime()
    runtime.camera_state = "camera_open"  # simulate open without hardware
    runtime.request_shutdown()
    runtime.mark_stopped()
    assert get_camera_snapshot()["state"] == CameraState.OFF


def test_no_cv2_at_observer_import() -> None:
    import mini_kio.observers.camera_activation_observer as mod

    tree = ast.parse(Path(mod.__file__).read_text(encoding="utf-8"))
    banned = {"cv2", "mediapipe"}
    for node in ast.walk(tree):
        if isinstance(node, ast.Import):
            for alias in node.names:
                assert alias.name.split(".")[0] not in banned
        elif isinstance(node, ast.ImportFrom) and node.module:
            assert node.module.split(".")[0] not in banned


def test_cv2_lazy_in_camera_runtime() -> None:
    import mini_kio.core.camera_runtime as mod

    tree = ast.parse(Path(mod.__file__).read_text(encoding="utf-8"))
    for node in tree.body:
        if isinstance(node, ast.Import):
            for alias in node.names:
                assert alias.name != "cv2"
        elif isinstance(node, ast.ImportFrom):
            assert (node.module or "").split(".")[0] != "cv2"


def main() -> int:
    tests = [
        ("camera off after bootstrap", test_camera_off_after_bootstrap),
        ("open rejected when observer disabled", test_open_rejected_when_observer_disabled),
        ("poll rejected when off", test_poll_rejected_when_off),
        ("release idempotent when off", test_release_idempotent_when_off),
        ("shutdown releases camera", test_shutdown_releases_camera),
        ("no cv2 at observer import", test_no_cv2_at_observer_import),
        ("cv2 lazy in camera_runtime", test_cv2_lazy_in_camera_runtime),
    ]
    results = [_run(name, fn) for name, fn in tests]
    passed = sum(1 for r in results if r.passed)
    print(json.dumps({"passed": passed, "total": len(results), "results": [r.__dict__ for r in results]}, indent=2))
    return 0 if passed == len(results) else 1


if __name__ == "__main__":
    raise SystemExit(main())
