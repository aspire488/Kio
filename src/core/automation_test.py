"""
Automation Full Test - Verify all KIO automation components.
"""

from __future__ import annotations

import logging
import os
import subprocess
import threading
from pathlib import Path

logger = logging.getLogger(__name__)

TEST_LOG_PATH = "debug/kio_test_log.txt"


def _write_log(msg: str) -> None:
    """Write to debug log file."""
    try:
        Path("debug").mkdir(exist_ok=True)
        with open(TEST_LOG_PATH, "a") as f:
            f.write(msg + "\n")
    except Exception:
        pass


def _run_simple_command(cmd: str) -> dict:
    """Test simple open command."""
    from core.system_skills import launch_application

    try:
        result = launch_application(cmd)
        return {"success": result.get("success", False), "message": str(result)}
    except Exception as e:
        return {"success": False, "message": str(e)}


def _run_search_command(cmd: str) -> dict:
    """Test web search using action_executor."""
    from core.task_engine import run

    try:
        result = run(cmd)
        return {"success": result.get("success", False), "message": str(result)}
    except Exception as e:
        return {"success": False, "message": str(e)}


def _run_system_status() -> dict:
    """Test system status command."""
    from core.system_skills import get_system_info

    try:
        result = get_system_info()
        return {"success": result.get("success", False), "message": str(result)}
    except Exception as e:
        return {"success": False, "message": str(e)}


def _run_gui_automation(cmd: str) -> dict:
    """Test GUI automation (type in notepad)."""
    from core.task_engine import run

    try:
        result = run(cmd)
        return {"success": result.get("success", False), "message": str(result)}
    except Exception as e:
        return {"success": False, "message": str(e)}


def automation_full_test() -> dict:
    """Run complete automation test suite."""
    results = []
    _write_log("=" * 50)
    _write_log("KIO AUTOMATION SELF TEST")
    _write_log("=" * 50)

    # TEST 1: Simple command - open chrome
    print("TEST 1: open chrome")
    _write_log("TEST 1: open chrome")
    try:
        r = _run_simple_command("chrome")
        if r.get("success"):
            print("TEST 1: PASS")
            _write_log("TEST 1: PASS")
            results.append(("TEST 1: open chrome", "PASS"))
        else:
            print(f"TEST 1: FAIL - {r.get('message', 'unknown')}")
            _write_log(f"TEST 1: FAIL - {r.get('message', 'unknown')}")
            results.append(("TEST 1: open chrome", "FAIL"))
    except Exception as e:
        print(f"TEST 1: FAIL - {e}")
        _write_log(f"TEST 1: FAIL - {e}")
        results.append(("TEST 1: open chrome", "FAIL"))

    # TEST 2: Web search (action executor)
    print("TEST 2: search laliga table")
    _write_log("TEST 2: search laliga table")
    try:
        r = _run_search_command("open chrome and search laliga table")
        if r.get("success"):
            print("TEST 2: PASS")
            _write_log("TEST 2: PASS")
            results.append(("TEST 2: search laliga table", "PASS"))
        else:
            print(f"TEST 2: FAIL - {r.get('message', 'unknown')}")
            _write_log(f"TEST 2: FAIL - {r.get('message', 'unknown')}")
            results.append(("TEST 2: search laliga table", "FAIL"))
    except Exception as e:
        print(f"TEST 2: FAIL - {e}")
        _write_log(f"TEST 2: FAIL - {e}")
        results.append(("TEST 2: search laliga table", "FAIL"))

    # TEST 3: System status
    print("TEST 3: system status")
    _write_log("TEST 3: system status")
    try:
        r = _run_system_status()
        if r.get("success"):
            print("TEST 3: PASS")
            _write_log("TEST 3: PASS")
            results.append(("TEST 3: system status", "PASS"))
        else:
            print(f"TEST 3: FAIL - {r.get('message', 'unknown')}")
            _write_log(f"TEST 3: FAIL - {r.get('message', 'unknown')}")
            results.append(("TEST 3: system status", "FAIL"))
    except Exception as e:
        print(f"TEST 3: FAIL - {e}")
        _write_log(f"TEST 3: FAIL - {e}")
        results.append(("TEST 3: system status", "FAIL"))

    # TEST 4: GUI automation (notepad)
    print("TEST 4: notepad automation")
    _write_log("TEST 4: notepad automation")
    try:
        r = _run_gui_automation("open notepad and type hello world then close notepad")
        if r.get("success"):
            print("TEST 4: PASS")
            _write_log("TEST 4: PASS")
            results.append(("TEST 4: notepad automation", "PASS"))
        else:
            print(f"TEST 4: FAIL - {r.get('message', 'unknown')}")
            _write_log(f"TEST 4: FAIL - {r.get('message', 'unknown')}")
            results.append(("TEST 4: notepad automation", "FAIL"))
    except Exception as e:
        print(f"TEST 4: FAIL - {e}")
        _write_log(f"TEST 4: FAIL - {e}")
        results.append(("TEST 4: notepad automation", "FAIL"))

    # TEST 5: WhatsApp message
    print("TEST 5: whatsapp message")
    _write_log("TEST 5: whatsapp message")
    try:
        r = _run_search_command("open whatsapp and send Thankss to ADITYA(Mallia)🤓")
        if r.get("success"):
            print("TEST 5: PASS")
            _write_log("TEST 5: PASS")
            results.append(("TEST 5: whatsapp message", "PASS"))
        else:
            print(f"TEST 5: FAIL - {r.get('message', 'unknown')}")
            _write_log(f"TEST 5: FAIL - {r.get('message', 'unknown')}")
            results.append(("TEST 5: whatsapp message", "FAIL"))
    except Exception as e:
        print(f"TEST 5: FAIL - {e}")
        _write_log(f"TEST 5: FAIL - {e}")
        results.append(("TEST 5: whatsapp message", "FAIL"))

    # TEST 6: Chrome multi-search
    print("TEST 6: chrome search IPL points table")
    _write_log("TEST 6: chrome search IPL points table")
    try:
        r = _run_search_command("open chrome and search IPL points table")
        if r.get("success"):
            print("TEST 6: PASS")
            _write_log("TEST 6: PASS")
            results.append(("TEST 6: chrome search IPL points table", "PASS"))
        else:
            print(f"TEST 6: FAIL - {r.get('message', 'unknown')}")
            _write_log(f"TEST 6: FAIL - {r.get('message', 'unknown')}")
            results.append(("TEST 6: chrome search IPL points table", "FAIL"))
    except Exception as e:
        print(f"TEST 6: FAIL - {e}")
        _write_log(f"TEST 6: FAIL - {e}")
        results.append(("TEST 6: chrome search IPL points table", "FAIL"))

    # Summary
    passed = sum(1 for _, status in results if status == "PASS")
    total = len(results)

    print()
    print("=" * 50)
    print("KIO AUTOMATION SELF TEST COMPLETE")
    if passed == total:
        print("ALL TESTS PASSED")
    else:
        print(f"FAILED: {total - passed}/{total} tests")
    print("=" * 50)

    _write_log("=" * 50)
    _write_log(f"RESULTS: {passed}/{total} PASSED")
    if passed == total:
        _write_log("ALL TESTS PASSED")
    else:
        _write_log(f"FAILED: {total - passed}/{total} tests")
    _write_log("=" * 50)

    return {
        "success": passed == total,
        "passed": passed,
        "total": total,
        "results": results,
    }


def run_startup_test() -> None:
    """Run automation test after startup (non-blocking)."""

    def run_test():
        import time

        time.sleep(5)  # Wait for system to stabilize
        automation_full_test()

    thread = threading.Thread(target=run_test, daemon=True, name="kio-self-test")
    thread.start()


__all__ = ["automation_full_test", "run_startup_test"]
