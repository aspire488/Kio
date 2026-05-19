"""
Gate 1 — Activation-path preparation validation (offline).

Run from kio_final/:
  python snapshots/gate1_activation_preparation/gate1_activation_validation.py
"""

from __future__ import annotations

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


def test_bootstrap_prepares_camera_observer() -> None:
    from mini_kio.core.runtime import bootstrap_runtime, get_runtime_observer_snapshot
    from mini_kio.observers.camera_activation_observer import OBSERVER_NAME

    bootstrap_runtime()
    observers = {o["name"]: o for o in get_runtime_observer_snapshot()}
    assert OBSERVER_NAME in observers
    rec = observers[OBSERVER_NAME]
    assert rec.get("kind") == "activation"
    assert rec.get("observer_type") == "camera"
    assert rec.get("enabled") is False


def test_activation_starts_idle() -> None:
    from mini_kio.core.activation import ActivationState, get_activation_snapshot
    from mini_kio.core.runtime import bootstrap_runtime

    bootstrap_runtime()
    snap = get_activation_snapshot()
    assert snap["state"] == ActivationState.IDLE


def test_signal_rejected_when_observer_disabled() -> None:
    from mini_kio.core.activation import submit_activation_signal
    from mini_kio.core.runtime import bootstrap_runtime
    from mini_kio.observers.camera_activation_observer import OBSERVER_NAME

    bootstrap_runtime()
    res = submit_activation_signal(OBSERVER_NAME, "manual")
    assert res.get("success") is False


def test_manual_activation_flow() -> None:
    from mini_kio.core.activation import (
        ActivationState,
        get_activation_snapshot,
        release_activation,
        submit_activation_signal,
    )
    from mini_kio.core.runtime import bootstrap_runtime, set_runtime_observer_enabled
    from mini_kio.observers.camera_activation_observer import OBSERVER_NAME

    bootstrap_runtime()
    set_runtime_observer_enabled(OBSERVER_NAME, True)
    res = submit_activation_signal(OBSERVER_NAME, "manual")
    assert res.get("success") is True
    assert get_activation_snapshot()["state"] == ActivationState.ACTIVE
    end = release_activation("test_release")
    assert end.get("success") is True
    assert get_activation_snapshot()["state"] == ActivationState.IDLE


def test_signal_rejected_when_already_active() -> None:
    from mini_kio.core.activation import submit_activation_signal
    from mini_kio.core.runtime import bootstrap_runtime, set_runtime_observer_enabled
    from mini_kio.observers.camera_activation_observer import OBSERVER_NAME

    bootstrap_runtime()
    set_runtime_observer_enabled(OBSERVER_NAME, True)
    submit_activation_signal(OBSERVER_NAME, "manual")
    res = submit_activation_signal(OBSERVER_NAME, "manual")
    assert res.get("success") is False


def test_activation_blocked_after_shutdown() -> None:
    from mini_kio.core.activation import submit_activation_signal
    from mini_kio.core.runtime import bootstrap_runtime, set_runtime_observer_enabled
    from mini_kio.observers.camera_activation_observer import OBSERVER_NAME

    runtime = bootstrap_runtime()
    set_runtime_observer_enabled(OBSERVER_NAME, True)
    runtime.request_shutdown()
    runtime.mark_stopped()
    res = submit_activation_signal(OBSERVER_NAME, "manual")
    assert res.get("success") is False


def test_camera_stub_has_no_cv_import() -> None:
    import ast
    import mini_kio.observers.camera_activation_observer as mod

    tree = ast.parse(Path(mod.__file__).read_text(encoding="utf-8"))
    banned = {"cv2", "opencv", "mediapipe"}
    for node in ast.walk(tree):
        if isinstance(node, ast.Import):
            for alias in node.names:
                assert alias.name.split(".")[0] not in banned
        elif isinstance(node, ast.ImportFrom) and node.module:
            assert node.module.split(".")[0] not in banned


def main() -> int:
    tests = [
        ("bootstrap prepares camera observer", test_bootstrap_prepares_camera_observer),
        ("activation starts idle", test_activation_starts_idle),
        ("signal rejected when disabled", test_signal_rejected_when_observer_disabled),
        ("manual activation flow", test_manual_activation_flow),
        ("signal rejected when active", test_signal_rejected_when_already_active),
        ("activation blocked after shutdown", test_activation_blocked_after_shutdown),
        ("camera stub has no cv import", test_camera_stub_has_no_cv_import),
    ]
    results = [_run(name, fn) for name, fn in tests]
    passed = sum(1 for r in results if r.passed)
    print(json.dumps({"passed": passed, "total": len(results), "results": [r.__dict__ for r in results]}, indent=2))
    return 0 if passed == len(results) else 1


if __name__ == "__main__":
    raise SystemExit(main())
