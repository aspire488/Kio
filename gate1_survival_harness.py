"""
Gate 1 Operational Survival Validation Harness.
Performs realistic stress and stability checks on the KIO runtime.
"""

from __future__ import annotations

import json
import logging
import os
import sys
import time
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Callable, Dict, List
from unittest.mock import MagicMock, patch

import psutil

# Add kio_final to sys.path
_ROOT = Path(__file__).resolve().parent / "kio_final"
if str(_ROOT) not in sys.path:
    sys.path.insert(0, str(_ROOT))

from mini_kio.core.runtime import (
    RuntimeState,
    bootstrap_runtime,
    get_runtime_snapshot,
    dispatch_channel_input,
    set_runtime_observer_enabled,
    _CURRENT_RUNTIME,
)
from mini_kio.core.activation import (
    ActivationState,
    get_activation_snapshot,
    release_activation,
    submit_activation_signal,
)
from mini_kio.core.camera_runtime import (
    CameraState,
    get_camera_snapshot,
    release_camera_if_open,
)

# Configuration
OBSERVER = "camera_activation"
CYCLES = 25
TELEGRAM_CHANNEL = "telegram"
TEST_USER_ID = 12345

@dataclass
class ValResult:
    name: str
    passed: bool
    details: str = ""
    metrics: dict = field(default_factory=dict)

class SurvivalHarness:
    def __init__(self):
        self.results: List[ValResult] = []
        self.process = psutil.Process(os.getpid())
        self.initial_rss = self.process.memory_info().rss

    def run_test(self, name: str, fn: Callable[[Dict], None]):
        print(f"Running: {name}...", end="", flush=True)
        try:
            metrics = {}
            t0 = time.perf_counter()
            fn(metrics)
            elapsed = time.perf_counter() - t0
            metrics["elapsed_s"] = round(elapsed, 4)
            metrics["rss_mb"] = round(self.process.memory_info().rss / 1024 / 1024, 2)
            self.results.append(ValResult(name, True, metrics=metrics))
            print(" PASS")
        except AssertionError as exc:
            self.results.append(ValResult(name, False, str(exc)))
            print(" FAIL (Assertion)")
        except Exception as exc:
            self.results.append(ValResult(name, False, f"{type(exc).__name__}: {exc}"))
            print(f" ERROR: {exc}")

    def get_summary(self) -> Dict:
        passed = sum(1 for r in self.results if r.passed)
        return {
            "passed": passed,
            "total": len(self.results),
            "results": [r.__dict__ for r in self.results],
            "final_rss_mb": round(self.process.memory_info().rss / 1024 / 1024, 2),
            "rss_delta_mb": round((self.process.memory_info().rss - self.initial_rss) / 1024 / 1024, 2)
        }

# --- Utility Helpers ---

def _fresh_runtime():
    import mini_kio.core.camera_runtime as cam
    cam._CAMERA_HANDLE = None
    return bootstrap_runtime()

def _enable_observer():
    set_runtime_observer_enabled(OBSERVER, True)

def _dark_frame():
    import numpy as np
    frame = np.full((240, 320, 3), 180, dtype=np.uint8)
    frame[80:160, 100:220] = 35
    return frame

# --- Tests ---

def test_runtime_boot_and_lifecycle(metrics: dict):
    rt = _fresh_runtime()
    snap = get_runtime_snapshot()
    assert snap["state"] == RuntimeState.READY
    
    rt.mark_idle()
    assert get_runtime_snapshot()["state"] == RuntimeState.IDLE
    
    rt.mark_running("test_channel")
    assert get_runtime_snapshot()["state"] == RuntimeState.RUNNING
    
    rt.request_shutdown()
    rt.mark_stopped()
    assert get_runtime_snapshot()["state"] == RuntimeState.STOPPED

def test_telegram_command_flows(metrics: dict):
    _fresh_runtime()
    commands = ["ping", "open chrome", "search python", "play messi", "what are your features"]
    for cmd in commands:
        res = dispatch_channel_input(cmd, channel=TELEGRAM_CHANNEL, user_id=TEST_USER_ID)
        assert res.get("success") is True, f"Command {cmd} failed: {res}"
    metrics["commands_run"] = len(commands)

def test_malformed_chain_rejection(metrics: dict):
    _fresh_runtime()
    bad_chains = [
        "open chrome and and",
        "open and",
        "and search python",
        "open chrome then then",
        "then play messi"
    ]
    for chain in bad_chains:
        res = dispatch_channel_input(chain, channel=TELEGRAM_CHANNEL, user_id=TEST_USER_ID)
        assert res.get("success") is False, f"Malformed chain {chain} was accepted"
        assert "malformed" in str(res.get("message", "")).lower()
    metrics["bad_chains_rejected"] = len(bad_chains)

def test_execution_boundary_enforcement(metrics: dict):
    _fresh_runtime()
    # Test blocked destructive action
    res = dispatch_channel_input("shutdown", channel=TELEGRAM_CHANNEL, user_id=TEST_USER_ID)
    assert res.get("success") is False
    assert "block" in str(res.get("message", "")).lower()
    
    # Test allowed action
    res = dispatch_channel_input("open notepad", channel=TELEGRAM_CHANNEL, user_id=TEST_USER_ID)
    assert res.get("success") is True
    metrics["boundary_verified"] = True

def test_multi_step_correctness(metrics: dict):
    _fresh_runtime()
    chain = "open chrome and search python"
    res = dispatch_channel_input(chain, channel=TELEGRAM_CHANNEL, user_id=TEST_USER_ID)
    assert res.get("success") is True
    assert "Completed 2 step(s)" in res.get("message", "")
    metrics["multi_step_verified"] = True

def test_activation_lifecycle_stress(metrics: dict):
    _fresh_runtime()
    _enable_observer()
    for i in range(CYCLES):
        res = submit_activation_signal(OBSERVER, "manual")
        assert res.get("success"), f"Cycle {i} failed"
        assert get_activation_snapshot()["state"] == ActivationState.ACTIVE
        release_activation(f"stress_{i}")
        assert get_activation_snapshot()["state"] == ActivationState.IDLE
    
    # Check for no zombie sessions
    snap = get_activation_snapshot()
    assert snap["state"] == ActivationState.IDLE
    assert snap["observer"] is None
    metrics["cycles"] = CYCLES

def test_camera_lifecycle_stress(metrics: dict):
    from mini_kio.core.camera_runtime import open_camera, release_camera
    
    class _FakeCap:
        def isOpened(self): return True
        def release(self): pass
        def read(self): return True, _dark_frame()

    with patch("mini_kio.core.camera_runtime._lazy_cv2", return_value=MagicMock()), \
         patch("cv2.VideoCapture", return_value=_FakeCap()):
        _fresh_runtime()
        _enable_observer()
        for i in range(10):
            res = open_camera()
            assert res.get("success"), f"Camera open cycle {i} failed"
            assert get_camera_snapshot()["state"] == CameraState.OPEN
            release_camera(f"stress_{i}")
            assert get_camera_snapshot()["state"] == CameraState.OFF
            
    # Check for no orphan handles
    import mini_kio.core.camera_runtime as cam
    assert cam._CAMERA_HANDLE is None
    metrics["camera_cycles"] = 10

def test_runtime_degradation_recovery(metrics: dict):
    rt = _fresh_runtime()
    rt.mark_degraded("simulated_failure")
    assert get_runtime_snapshot()["state"] == RuntimeState.DEGRADED
    
    # Recovery to running
    rt.mark_running("recovery_channel")
    assert get_runtime_snapshot()["state"] == RuntimeState.RUNNING
    metrics["degradation_recovery"] = True

def test_bounded_memory_behavior(metrics: dict):
    from mini_kio.core.runtime import remember_runtime_context
    import mini_kio.core.runtime as rt
    _fresh_runtime()
    for i in range(100):
        remember_runtime_context("spam", {"i": i}, ttl_s=3600)
    
    size = len(rt._CURRENT_RUNTIME.context_items)
    assert size == 8, f"Context buffer exceeded limit: {size}"
    metrics["buffer_size"] = size

def test_long_idle_behavior(metrics: dict):
    # Simulate time pass and touch activation
    from mini_kio.core.activation import touch_activation_session
    _fresh_runtime()
    _enable_observer()
    submit_activation_signal(OBSERVER, "manual")
    
    # Mock time to exceed timeout
    with patch("time.monotonic", return_value=time.monotonic() + 400):
        expired = touch_activation_session()
        assert expired is True
        assert get_activation_snapshot()["state"] == ActivationState.IDLE
    metrics["idle_expiry_verified"] = True

def main():
    harness = SurvivalHarness()
    
    harness.run_test("Runtime Boot & Lifecycle", test_runtime_boot_and_lifecycle)
    harness.run_test("Telegram Command Flows", test_telegram_command_flows)
    harness.run_test("Malformed Chain Rejection", test_malformed_chain_rejection)
    harness.run_test("Execution Boundary Enforcement", test_execution_boundary_enforcement)
    harness.run_test("Multi-step Correctness", test_multi_step_correctness)
    harness.run_test("Activation Lifecycle Stress", test_activation_lifecycle_stress)
    harness.run_test("Camera Lifecycle Stress", test_camera_lifecycle_stress)
    harness.run_test("Runtime Degradation Recovery", test_runtime_degradation_recovery)
    harness.run_test("Bounded Memory Behavior", test_bounded_memory_behavior)
    harness.run_test("Long Idle Behavior (Timeout)", test_long_idle_behavior)
    
    summary = harness.get_summary()
    print("\n" + "="*50)
    print("GATE 1 SURVIVAL VALIDATION COMPLETE")
    print("="*50)
    print(f"Passed: {summary['passed']}/{summary['total']}")
    print(f"Final RSS: {summary['final_rss_mb']} MB (Delta: {summary['rss_delta_mb']} MB)")
    
    with open("gate1_survival_results.json", "w") as f:
        json.dump(summary, f, indent=2)

if __name__ == "__main__":
    main()
