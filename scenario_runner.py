"""
Gate 1.5 Scenario Runner

Bootstraps the KIO runtime and executes hardening scenarios defined in scenario_cases.json.
Uses operator mocks to ensure deterministic behavior and prevent actual system side-effects.
"""

from __future__ import annotations

import json
import logging
import os
import sys
import time
from pathlib import Path
from typing import Any

# Add project root and kio_final to path
_ROOT = Path(__file__).resolve().parent
if str(_ROOT) not in sys.path:
    sys.path.insert(0, str(_ROOT))

_KIO_FINAL = _ROOT / "kio_final"
if str(_KIO_FINAL) not in sys.path:
    sys.path.insert(0, str(_KIO_FINAL))

from mini_kio.core.runtime import (
    bootstrap_runtime,
    dispatch_channel_input,
    get_runtime_snapshot,
    get_runtime_integrity_snapshot,
)
import mini_kio.core.execution_boundary as boundary

# ---------------------------------------------------------------------------
# Operator Mocks
# ---------------------------------------------------------------------------

def mock_operator(name: str) -> Any:
    """Return a mock function for an operator."""
    def _mock(*args, **kwargs):
        target = args[0] if args else "none"
        if target == "fail_me":
            return {"success": False, "message": f"Mock {name} failed as requested"}
        return {"success": True, "message": f"Mock {name} executed for {target}"}
    return _mock


def apply_mocks():
    """Monkeypatch operators in execution_boundary to prevent real side-effects."""
    # We intercept at the _load_handler level or individual operator imports
    # Intercepting _load_handler is cleanest
    original_load_handler = boundary._load_handler
    
    def mocked_load_handler(action: str):
        # We still want to validate that the action is known
        handler, canonical = original_load_handler(action)
        # Return a mock instead of the real handler
        return mock_operator(canonical), canonical

    boundary._load_handler = mocked_load_handler
    print("[RUNNER] Operator mocks applied.")


# ---------------------------------------------------------------------------
# Runner Logic
# ---------------------------------------------------------------------------

class ScenarioRunner:
    def __init__(self, cases_path: str = "scenario_cases.json"):
        self.cases_path = Path(cases_path)
        self.results = []
        self.stats = {
            "total": 0,
            "passed": 0,
            "failed": 0,
            "skipped": 0,
        }

    def run(self):
        if not self.cases_path.exists():
            print(f"Error: {self.cases_path} not found.")
            return

        with open(self.cases_path, "r", encoding="utf-8") as f:
            cases = json.load(f)

        print(f"[RUNNER] Starting Gate 1.5 hardening: {len(cases)} scenarios")
        apply_mocks()
        
        # Bootstrap runtime once
        runtime = bootstrap_runtime()
        
        for case in cases:
            self.stats["total"] += 1
            result = self._run_case(case)
            self.results.append(result)
            
            if result["passed"]:
                self.stats["passed"] += 1
                print(f"  [PASS] {case['id']}: {case['input']}")
            else:
                self.stats["failed"] += 1
                print(f"  [FAIL] {case['id']}: {case['input']} -> {result['error']}")

        self._save_results()
        self._generate_report()

    def _run_case(self, case: dict) -> dict:
        scenario_id = case["id"]
        input_text = case["input"]
        expected = case["expected"]
        
        # Execute via runtime channel handoff
        # Use a fresh start for multi-step to avoid inter-step delay issues if any
        start_time = time.monotonic()
        outcome = dispatch_channel_input(input_text, channel="scenario_test")
        elapsed = (time.monotonic() - start_time) * 1000
        
        passed = True
        error = ""
        
        # Verification Logic
        try:
            # Check runtime snapshot fields
            if "runtime" in expected:
                snap = get_runtime_snapshot()
                for key, val in expected["runtime"].items():
                    if snap.get(key) != val:
                        raise AssertionError(f"Expected runtime.{key}={val}, got {snap.get(key)}")

            # Check integrity snapshot fields
            if "integrity" in expected:
                int_snap = get_runtime_integrity_snapshot()
                for key, val in expected["integrity"].items():
                    if int_snap.get(key) != val:
                        raise AssertionError(f"Expected integrity.{key}={val}, got {int_snap.get(key)}")

            # Check top-level success
            if "success" in expected:
                if outcome.get("success") != expected["success"]:
                    raise AssertionError(f"Expected success={expected['success']}, got {outcome.get('success')}")
            
            # Check message contains
            if "message_contains" in expected:
                msg = str(outcome.get("message", "")).lower()
                if expected["message_contains"].lower() not in msg:
                    raise AssertionError(f"Message '{msg}' does not contain '{expected['message_contains']}'")
            
            # Check blocked state
            if "blocked" in expected:
                is_blocked = outcome.get("blocked", False)
                if is_blocked != expected["blocked"]:
                    raise AssertionError(f"Expected blocked={expected['blocked']}, got {is_blocked}")

            # Check action/target if single step
            if "action" in expected or "target" in expected:
                # For single steps, we might need to peek into the results if multi-step logic was triggered
                # but usually it's in the top level if handle_command returned execute_action result
                # Wait, handle_command returns execute_action result directly for single steps.
                if "action" in expected:
                    if outcome.get("action") != expected["action"]:
                        raise AssertionError(f"Expected action={expected['action']}, got {outcome.get('action')}")
                if "target" in expected:
                    if outcome.get("target") != expected["target"]:
                        raise AssertionError(f"Expected target={expected['target']}, got {outcome.get('target')}")

            # Check results count for multi-step
            if "results_count" in expected:
                results = outcome.get("results", [])
                if len(results) != expected["results_count"]:
                    raise AssertionError(f"Expected {expected['results_count']} steps, got {len(results)}")

        except AssertionError as e:
            passed = False
            error = str(e)
        except Exception as e:
            passed = False
            error = f"Runtime Error: {str(e)}"

        return {
            "id": scenario_id,
            "category": case["category"],
            "input": input_text,
            "passed": passed,
            "error": error,
            "outcome": outcome,
            "elapsed_ms": int(elapsed),
            "runtime_snap": get_runtime_snapshot(),
        }

    def _save_results(self):
        results_path = Path("scenario_results.json")
        with open(results_path, "w", encoding="utf-8") as f:
            json.dump({
                "stats": self.stats,
                "timestamp": time.strftime("%Y-%m-%d %H:%M:%S"),
                "results": self.results
            }, f, indent=2)
        print(f"[RUNNER] Results saved to {results_path}")

    def _generate_report(self):
        from scenario_report_generator import generate_markdown_report
        generate_markdown_report("scenario_results.json", "SCENARIO_REPORT.md")


if __name__ == "__main__":
    runner = ScenarioRunner()
    runner.run()
