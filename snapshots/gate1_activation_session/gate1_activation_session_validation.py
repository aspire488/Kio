"""
Gate 1 — Activation session stabilization validation (offline).

Run from kio_final/:
  python snapshots/gate1_activation_session/gate1_activation_session_validation.py
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


def test_release_transitions_to_idle() -> None:
    from mini_kio.core.activation import ActivationState, get_activation_snapshot, release_activation, submit_activation_signal
    from mini_kio.core.runtime import bootstrap_runtime, set_runtime_observer_enabled
    from mini_kio.observers.camera_activation_observer import OBSERVER_NAME

    bootstrap_runtime()
    set_runtime_observer_enabled(OBSERVER_NAME, True)
    submit_activation_signal(OBSERVER_NAME, "manual")
    assert get_activation_snapshot()["state"] == ActivationState.ACTIVE
    release_activation("test_release")
    assert get_activation_snapshot()["state"] == ActivationState.IDLE


def test_lazy_session_timeout() -> None:
    from mini_kio.core.activation import ActivationState, get_activation_snapshot, submit_activation_signal, touch_activation_session
    from mini_kio.core.runtime import bootstrap_runtime, set_runtime_observer_enabled
    from mini_kio.observers.camera_activation_observer import OBSERVER_NAME

    runtime = bootstrap_runtime()
    set_runtime_observer_enabled(OBSERVER_NAME, True)
    submit_activation_signal(OBSERVER_NAME, "manual")
    runtime.activation_session_timeout_s = 1
    # Simulate expired session (started well before timeout window).
    runtime.activation_started_at_ms = -60_000
    assert touch_activation_session() is True
    assert get_activation_snapshot()["state"] == ActivationState.IDLE


def test_snapshot_includes_remaining_ms() -> None:
    from mini_kio.core.activation import submit_activation_signal
    from mini_kio.core.runtime import bootstrap_runtime, set_runtime_observer_enabled
    from mini_kio.observers.camera_activation_observer import OBSERVER_NAME

    bootstrap_runtime()
    set_runtime_observer_enabled(OBSERVER_NAME, True)
    submit_activation_signal(OBSERVER_NAME, "manual")
    snap = __import__("mini_kio.core.activation", fromlist=["get_activation_snapshot"]).get_activation_snapshot()
    assert snap.get("remaining_ms") is not None
    assert int(snap["remaining_ms"]) >= 0


def test_signal_rejected_while_active() -> None:
    from mini_kio.core.activation import submit_activation_signal
    from mini_kio.core.runtime import bootstrap_runtime, set_runtime_observer_enabled
    from mini_kio.observers.camera_activation_observer import OBSERVER_NAME

    bootstrap_runtime()
    set_runtime_observer_enabled(OBSERVER_NAME, True)
    submit_activation_signal(OBSERVER_NAME, "manual")
    res = submit_activation_signal(OBSERVER_NAME, "manual")
    assert res.get("success") is False


def test_force_release_on_shutdown() -> None:
    from mini_kio.core.activation import ActivationState, force_release_activation, submit_activation_signal
    from mini_kio.core.runtime import bootstrap_runtime, set_runtime_observer_enabled
    from mini_kio.observers.camera_activation_observer import OBSERVER_NAME

    runtime = bootstrap_runtime()
    set_runtime_observer_enabled(OBSERVER_NAME, True)
    submit_activation_signal(OBSERVER_NAME, "manual")
    runtime.request_shutdown()
    force_release_activation("runtime_shutdown")
    assert runtime.activation_state == ActivationState.IDLE


def test_releasing_state_exists() -> None:
    from mini_kio.core.activation import ActivationState

    assert ActivationState.RELEASING == "activation_releasing"


def main() -> int:
    tests = [
        ("release transitions to idle", test_release_transitions_to_idle),
        ("lazy session timeout", test_lazy_session_timeout),
        ("snapshot includes remaining_ms", test_snapshot_includes_remaining_ms),
        ("signal rejected while active", test_signal_rejected_while_active),
        ("force release on shutdown", test_force_release_on_shutdown),
        ("releasing state exists", test_releasing_state_exists),
    ]
    results = [_run(name, fn) for name, fn in tests]
    passed = sum(1 for r in results if r.passed)
    print(json.dumps({"passed": passed, "total": len(results), "results": [r.__dict__ for r in results]}, indent=2))
    return 0 if passed == len(results) else 1


if __name__ == "__main__":
    raise SystemExit(main())
