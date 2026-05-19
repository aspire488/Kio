"""
Gate 1 — Telegram interaction stabilization validation (offline).

Run from kio_final/:
  python snapshots/gate1_interaction_stabilization/gate1_telegram_validation.py
"""

from __future__ import annotations

import json
import sys
import time
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


def test_bootstrap_lifecycle() -> None:
    from mini_kio.core.runtime import (
        RuntimeState,
        bootstrap_runtime,
        get_runtime_snapshot,
    )

    runtime = bootstrap_runtime()
    snap = get_runtime_snapshot()
    assert snap["state"] == RuntimeState.READY, snap


def test_channel_simulated_lifecycle() -> None:
    from mini_kio.core.runtime import (
        RuntimeState,
        KioRuntime,
        bootstrap_runtime,
        start_runtime_channel,
    )

    runtime = bootstrap_runtime()

    def noop_channel(rt: KioRuntime) -> None:
        assert rt.state == RuntimeState.RUNNING
        rt.request_shutdown()

    start_runtime_channel(runtime, "telegram", noop_channel)
    assert runtime.state == RuntimeState.STOPPED
    assert runtime.shutdown_requested
    assert "telegram" not in runtime.channels


def test_dispatch_oversized_input() -> None:
    from mini_kio.core.runtime import bootstrap_runtime, dispatch_channel_input

    bootstrap_runtime()
    res = dispatch_channel_input("x" * 3000, channel="telegram", user_id=1)
    assert res.get("success") is False
    assert "too long" in str(res.get("message", "")).lower()


def test_dispatch_normal_command() -> None:
    from mini_kio.core.runtime import bootstrap_runtime, dispatch_channel_input

    bootstrap_runtime()
    res = dispatch_channel_input("ping", channel="telegram", user_id=1)
    assert res.get("success") is True
    assert "online" in str(res.get("message", "")).lower()


def test_dispatch_unknown_command() -> None:
    from mini_kio.core.runtime import bootstrap_runtime, dispatch_channel_input, format_channel_reply

    bootstrap_runtime()
    res = dispatch_channel_input("xyzzy_plugh_unknown_42", channel="telegram", user_id=1)
    reply = format_channel_reply(res)
    assert res.get("success") is False
    assert reply


def test_dispatch_blocked_destructive() -> None:
    from mini_kio.core.runtime import bootstrap_runtime, dispatch_channel_input

    bootstrap_runtime()
    res = dispatch_channel_input("shutdown", channel="telegram", user_id=1)
    assert res.get("success") is False
    msg = str(res.get("message", "")).lower()
    assert "block" in msg or "not allowed" in msg


def test_dispatch_malformed_input() -> None:
    from mini_kio.core.runtime import bootstrap_runtime, dispatch_channel_input

    bootstrap_runtime()
    for bad in ("", "   ", "\n\t"):
        res = dispatch_channel_input(bad, channel="telegram", user_id=1)
        assert res.get("success") is False
        assert "empty" in str(res.get("message", "")).lower()


def test_dispatch_without_runtime() -> None:
    import mini_kio.core.runtime as rt

    rt._CURRENT_RUNTIME = None
    res = rt.dispatch_channel_input("ping", channel="telegram", user_id=1)
    assert res.get("success") is False
    assert "not initialized" in str(res.get("message", "")).lower()


def test_dispatch_after_shutdown() -> None:
    from mini_kio.core.runtime import bootstrap_runtime, dispatch_channel_input

    runtime = bootstrap_runtime()
    runtime.request_shutdown()
    runtime.mark_stopped()
    res = dispatch_channel_input("ping", channel="telegram", user_id=1)
    assert res.get("success") is False
    assert "not accepting" in str(res.get("message", "")).lower()


def test_runtime_restart_bootstrap() -> None:
    from mini_kio.core.runtime import RuntimeState, bootstrap_runtime

    r1 = bootstrap_runtime()
    r1.request_shutdown()
    r1.mark_stopped()
    r2 = bootstrap_runtime()
    assert r2.state == RuntimeState.READY
    res = __import__("mini_kio.core.runtime", fromlist=["dispatch_channel_input"]).dispatch_channel_input(
        "ping", channel="telegram", user_id=1
    )
    assert res.get("success") is True


def test_route_compat() -> None:
    from mini_kio.core.runtime import bootstrap_runtime
    from mini_kio.core.command_router import route

    bootstrap_runtime()
    reply = route("ping", user_id=99)
    assert isinstance(reply, str)
    assert reply


def test_context_ttl_prune() -> None:
    from mini_kio.core.runtime import (
        bootstrap_runtime,
        remember_runtime_context,
        get_runtime_context_snapshot,
        _prune_runtime_context,
    )

    runtime = bootstrap_runtime()
    remember_runtime_context("short", {"v": 1}, ttl_s=1)
    time.sleep(1.05)
    remember_runtime_context("long", {"v": 2}, ttl_s=300)
    _prune_runtime_context(runtime)
    kinds = [item["kind"] for item in get_runtime_context_snapshot()]
    assert "short" not in kinds, kinds
    assert "long" in kinds, kinds


def test_trace_events_on_dispatch() -> None:
    from mini_kio.core.runtime import bootstrap_runtime, dispatch_channel_input

    bootstrap_runtime()
    dispatch_channel_input("ping", channel="telegram", user_id=1)
    log_path = Path(__file__).resolve().parents[2] / "mini_kio" / "debug" / "runtime_trace.log"
    if not log_path.exists():
        return
    tail = log_path.read_text(encoding="utf-8", errors="replace")[-8000:]
    assert "runtime_channel_input" in tail


def test_execution_boundary_trace() -> None:
    from mini_kio.core.runtime import bootstrap_runtime
    from mini_kio.core.execution_boundary import execute_action

    bootstrap_runtime()
    res = execute_action("open_app", "notepad")
    assert "success" in res
    assert "verification_status" in res


def main() -> int:
    tests = [
        ("bootstrap lifecycle", test_bootstrap_lifecycle),
        ("channel simulated lifecycle", test_channel_simulated_lifecycle),
        ("dispatch oversized input", test_dispatch_oversized_input),
        ("dispatch normal command", test_dispatch_normal_command),
        ("dispatch unknown command", test_dispatch_unknown_command),
        ("dispatch blocked destructive", test_dispatch_blocked_destructive),
        ("dispatch malformed input", test_dispatch_malformed_input),
        ("dispatch without runtime", test_dispatch_without_runtime),
        ("dispatch after shutdown", test_dispatch_after_shutdown),
        ("runtime restart bootstrap", test_runtime_restart_bootstrap),
        ("route compat wrapper", test_route_compat),
        ("context TTL prune", test_context_ttl_prune),
        ("trace on dispatch", test_trace_events_on_dispatch),
        ("execution boundary shape", test_execution_boundary_trace),
    ]
    results = [_run(name, fn) for name, fn in tests]
    passed = sum(1 for r in results if r.passed)
    print(json.dumps({"passed": passed, "total": len(results), "results": [r.__dict__ for r in results]}, indent=2))
    return 0 if passed == len(results) else 1


if __name__ == "__main__":
    raise SystemExit(main())
