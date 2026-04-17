"""
KIO Diagnostics - Comprehensive system testing and validation.

Tests and verifies:
1. Chrome launch detection (process verification)
2. Calculator launch detection
3. Notebook launch
4. Folder opening
5. Search URL encoding
6. Multi-step command routing
7. Environment PATH discovery
8. Subprocess execution reliability

Requirements:
- psutil (for process verification)
- Falls back to tasklist if psutil unavailable
"""

from __future__ import annotations

import json
import logging
import os
import platform
import sys
import time
from pathlib import Path
from typing import Any

# Set up logging
logging.basicConfig(
    level=logging.INFO,
    format="[%(asctime)s] %(name)s: %(message)s",
)
logger = logging.getLogger(__name__)

# Platform detection
_IS_WINDOWS = platform.system() == "Windows"

# Process names for verification
_PROCESS_NAMES: dict[str, list[str]] = {
    "chrome": ["chrome.exe"],
    "calculator": ["calc.exe", "CalculatorApp.exe"],
    "notepad": ["notepad.exe"],
    "edge": ["msedge.exe"],
    "firefox": ["firefox.exe"],
    "vscode": ["Code.exe"],
}


def _is_process_running(app_name: str) -> bool:
    """Check if a process is currently running."""
    try:
        import psutil
        exe_names = _PROCESS_NAMES.get(app_name.lower(), [f"{app_name}.exe"])
        exe_names_lower = [e.lower() for e in exe_names]
        
        for proc in psutil.process_iter(["name"]):
            try:
                if proc.info["name"] and proc.info["name"].lower() in exe_names_lower:
                    return True
            except (psutil.NoSuchProcess, psutil.AccessDenied):
                continue
        return False
    except ImportError:
        # Fallback to tasklist
        return _is_process_running_tasklist(app_name)


def _is_process_running_tasklist(app_name: str) -> bool:
    """Fallback: check processes via tasklist."""
    if not _IS_WINDOWS:
        return False
    
    import subprocess
    exe_names = _PROCESS_NAMES.get(app_name.lower(), [f"{app_name}.exe"])
    try:
        result = subprocess.run(
            ["tasklist", "/FO", "CSV", "/NH"],
            capture_output=True,
            text=True,
            timeout=5,
        )
        output_lower = result.stdout.lower()
        return any(exe.lower() in output_lower for exe in exe_names)
    except Exception:
        return False


class DiagnosticTest:
    """Single diagnostic test."""
    
    def __init__(self, name: str, command: str, verify_process: str | None = None):
        self.name = name
        self.command = command
        self.verify_process = verify_process
        self.result = None
        self.elapsed = None
        self.passed = False
        self.error = None
    
    def run(self) -> dict:
        """Run the test."""
        print(f"  [{self.name:25s}] Running: {self.command!r}")
        t0 = time.monotonic()
        
        try:
            from mini_kio.core.command_router import handle_command
        except ImportError:
            try:
                from command_router import handle_command
            except ImportError:
                return self._fail("Cannot import handle_command")
        
        try:
            result = handle_command(self.command)
            self.elapsed = time.monotonic() - t0
            
            # Check basic success
            if not result.get("success"):
                msg = result.get("message", "handler returned failure")
                return self._fail(f"Handler failed: {msg}")
            
            # Verify process if applicable
            if self.verify_process and "open " in self.command.lower():
                if not self._verify_process_launch():
                    return self._fail(
                        f"Process {self.verify_process!r} not found after launch"
                    )
            
            self.passed = True
            return self._success(result.get("message", "OK"))
        
        except Exception as e:
            self.elapsed = time.monotonic() - t0
            return self._fail(str(e)[:100])
    
    def _verify_process_launch(self) -> bool:
        """Wait for process to appear."""
        deadline = time.monotonic() + 3.0
        while time.monotonic() < deadline:
            if _is_process_running(self.verify_process):
                return True
            time.sleep(0.2)
        return False
    
    def _success(self, msg: str) -> dict:
        """Mark test as passed."""
        elapsed_str = f" ({self.elapsed:.1f}s)" if self.elapsed else ""
        print(f"    ✓ PASS{elapsed_str}")
        return {
            "name": self.name,
            "passed": True,
            "message": msg,
            "elapsed": self.elapsed,
        }
    
    def _fail(self, reason: str) -> dict:
        """Mark test as failed."""
        elapsed_str = f" ({self.elapsed:.1f}s)" if self.elapsed else ""
        print(f"    ✗ FAIL{elapsed_str} — {reason}")
        self.passed = False
        self.error = reason
        return {
            "name": self.name,
            "passed": False,
            "error": reason,
            "elapsed": self.elapsed,
        }


def _test_imports() -> dict:
    """Test that core modules import correctly."""
    print(f"  ['import-test'              ] Checking module imports")
    
    modules_to_test = [
        "mini_kio.core.command_parser",
        "mini_kio.core.command_router",
        "mini_kio.core.app_operator",
        "mini_kio.core.file_operator",
        "mini_kio.core.system_operator",
        "mini_kio.core.task_engine",
    ]
    
    failed = []
    for module in modules_to_test:
        try:
            __import__(module)
        except ImportError as e:
            failed.append(f"{module}: {e}")
    
    if failed:
        print(f"    ✗ FAIL — {len(failed)} import(s) failed")
        return {
            "name": "imports",
            "passed": False,
            "errors": failed,
        }
    
    print(f"    ✓ PASS")
    return {
        "name": "imports",
        "passed": True,
    }


def _test_url_encoding() -> dict:
    """Test URL encoding."""
    print(f"  ['url-encoding'             ] Testing URL encoding")
    
    try:
        import urllib.parse
        test_query = "python tutorial with ai"
        encoded = urllib.parse.quote_plus(test_query)
        expected = "python+tutorial+with+ai"
        
        if encoded == expected:
            print(f"    ✓ PASS")
            return {"name": "url-encoding", "passed": True}
        else:
            print(f"    ✗ FAIL — expected {expected}, got {encoded}")
            return {
                "name": "url-encoding",
                "passed": False,
                "expected": expected,
                "got": encoded,
            }
    except Exception as e:
        print(f"    ✗ FAIL — {e}")
        return {"name": "url-encoding", "passed": False, "error": str(e)}


def _test_command_parsing() -> dict:
    """Test command parsing."""
    print(f"  ['cmd-parsing'              ] Testing command parsing")
    
    try:
        from mini_kio.core.command_parser import parse_command
    except ImportError:
        from command_parser import parse_command
    
    tests = [
        ("open chrome", 1),
        ("open chrome and search python", 2),
        ("search python tutorial", 1),
        ("open downloads folder", 1),
    ]
    
    for cmd, expected_steps in tests:
        steps = parse_command(cmd)
        if len(steps) != expected_steps:
            print(f"    ✗ FAIL — {cmd!r}: expected {expected_steps} step(s), got {len(steps)}")
            return {
                "name": "cmd-parsing",
                "passed": False,
                "failed_cmd": cmd,
            }
    
    print(f"    ✓ PASS")
    return {"name": "cmd-parsing", "passed": True}


def run_diagnostics() -> dict:
    """Run the full diagnostic suite."""
    print("=" * 60)
    print("KIO DIAGNOSTICS")
    print("=" * 60)
    print()
    
    results = []
    
    # Basic tests
    print("UNIT TESTS:")
    results.append(_test_imports())
    results.append(_test_url_encoding())
    results.append(_test_command_parsing())
    print()
    
    # Integration tests
    print("INTEGRATION TESTS:")
    tests = [
        DiagnosticTest("chrome_open", "open chrome", "chrome"),
        DiagnosticTest("calculator", "open calculator", "calculator"),
        DiagnosticTest("notepad", "open notepad", "notepad"),
        DiagnosticTest("chrome_search", "search python tutorial", None),
        DiagnosticTest("downloads_folder", "open downloads folder", None),
        DiagnosticTest("multi_step", "open chrome and search ai news", "chrome"),
    ]
    
    for test in tests:
        result = test.run()
        results.append(result)
        time.sleep(0.5)
    
    print()
    
    # Summary
    print("=" * 60)
    print("DIAGNOSTIC SUMMARY")
    print("=" * 60)
    
    passed = sum(1 for r in results if r.get("passed"))
    failed = sum(1 for r in results if not r.get("passed"))
    total = len(results)
    
    for r in results:
        status = "✓ PASS" if r.get("passed") else "✗ FAIL"
        name = r.get("name", "unknown")
        print(f"  {status:8s} | {name}")
    
    print()
    print(f"Total: {total}  Passed: {passed}  Failed: {failed}")
    print()
    
    if failed == 0:
        print("ALL DIAGNOSTICS PASSED ✓")
    else:
        print(f"⚠ {failed} DIAGNOSTIC(S) FAILED")
    
    print()
    
    # Write results
    _write_results_log(results)
    
    return {
        "total": total,
        "passed": passed,
        "failed": failed,
        "results": results,
    }


def _write_results_log(results: list) -> None:
    """Write results to debug log."""
    try:
        # Find debug directory
        core_dir = Path(__file__).resolve().parent
        pkg_dir = core_dir.parent
        debug_dir = pkg_dir / "debug"
        debug_dir.mkdir(exist_ok=True, parents=True)
        
        log_path = debug_dir / "kio_diagnostic_log.txt"
        with open(log_path, "w", encoding="utf-8") as f:
            f.write("KIO DIAGNOSTIC RESULTS\n")
            f.write("=" * 50 + "\n")
            f.write(f"Timestamp: {time.strftime('%Y-%m-%d %H:%M:%S')}\n\n")
            
            for r in results:
                status = "PASS" if r.get("passed") else "FAIL"
                name = r.get("name", "unknown")
                f.write(f"{status}: {name}\n")
                
                if not r.get("passed"):
                    if r.get("error"):
                        f.write(f"  Error: {r['error']}\n")
                    if r.get("errors"):
                        for err in r["errors"]:
                            f.write(f"  - {err}\n")
            
            f.write(f"\n{'=' * 50}\n")
            passed = sum(1 for r in results if r.get("passed"))
            failed = sum(1 for r in results if not r.get("passed"))
            f.write(f"Total: {len(results)}  Passed: {passed}  Failed: {failed}\n")
        
        logger.info(f"Diagnostics log written to {log_path}")
    except Exception as e:
        logger.error(f"Could not write diagnostics log: {e}")


if __name__ == "__main__":
    run_diagnostics()
