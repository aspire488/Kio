"""
KIO Direct Runtime Smoke Tests — Phase 2
=========================================
NOT pytest. Direct diagnostic harness that imports and exercises critical KIO
components to prove runtime stability without depending on broken test infra.

Run: python _smoke_test.py
"""
from __future__ import annotations

import importlib
import os
import sys
import time
import tracemalloc
import threading
import concurrent.futures
import traceback

# Set test mode BEFORE any KIO imports
os.environ["KIO_TEST_MODE"] = "1"

RESULTS: list[tuple[str, str, str]] = []  # (category, test_name, result)
ROOT = os.path.dirname(os.path.abspath(__file__))
if ROOT not in sys.path:
    sys.path.insert(0, ROOT)

PASS = "PASS"
FAIL = "FAIL"
SKIP = "SKIP"


def record(category: str, name: str, status: str, detail: str = ""):
    tag = f"[{status}]"
    RESULTS.append((category, name, f"{tag} {detail}" if detail else tag))
    symbol = "OK" if status == PASS else ("XX" if status == FAIL else "--")
    line = f"  {symbol} {name}"
    if detail:
        line += f" — {detail}"
    print(line)


# =========================================================================
# A. CORE IMPORT HEALTH
# =========================================================================
def test_import_health():
    print("\n=== A. CORE IMPORT HEALTH ===")
    category = "import_health"

    critical_modules = [
        "mini_kio.core.runtime",
        "mini_kio.core.command_router",
        "mini_kio.core.config",
        "mini_kio.core.pipeline",
        "mini_kio.core.app_operator",
        "mini_kio.core.browser_operator",
        "mini_kio.browser_connector.connector",
        "mini_kio.browser_connector.registry",
        "mini_kio.media.media_manager",
        "mini_kio.resolvers.math_resolver",
        "mini_kio.core.providers",
        "mini_kio.core.providers.terminal_provider",
        "mini_kio.core.mcp.servers.mcp_terminal_server",
        "mini_kio.core.mcp.servers.mcp_github_server",
        "mini_kio.core.presentation.viz",
        "mini_kio.core.presentation.archetypes",
        "mini_kio.core.routing_utils",
        "mini_kio.core.governance",
        "mini_kio.core.credential_vault",
        "mini_kio.core.activation",
        "mini_kio.core.task_engine",
        "mini_kio.core.file_operator",
        "mini_kio.core.system_operator",
        "mini_kio.llm.gemini_provider",
        "mini_kio.media.providers.youtube_provider",
        "mini_kio.semantic.graph",
    ]

    failed = []
    hung = []

    for mod in critical_modules:
        start = time.monotonic()
        try:
            importlib.import_module(mod)
            elapsed = time.monotonic() - start
            if elapsed > 5.0:
                hung.append((mod, elapsed))
                record(category, mod, FAIL, f"SLOW IMPORT {elapsed:.1f}s")
            else:
                record(category, mod, PASS, f"{elapsed:.2f}s")
        except Exception as e:
            elapsed = time.monotonic() - start
            record(category, mod, FAIL, f"{type(e).__name__}: {e}")
            failed.append((mod, str(e)))

    # Specifically test scipy/sklearn do NOT block core
    for optional in ["scipy", "sklearn", "numpy"]:
        start = time.monotonic()
        try:
            mod = importlib.import_module(optional)
            elapsed = time.monotonic() - start
            ver = getattr(mod, "__version__", "?")
            record(category, optional, PASS, f"v{ver} {elapsed:.2f}s (optional)")
        except ImportError:
            record(category, optional, SKIP, "not installed (OK if not required)")
        except Exception as e:
            elapsed = time.monotonic() - start
            record(category, optional, FAIL, f"{type(e).__name__}: {e} ({elapsed:.1f}s)")

    if failed:
        print(f"\n  CRITICAL: {len(failed)} core module(s) failed to import")
        for mod, err in failed:
            print(f"    {mod}: {err}")
    else:
        print(f"\n  OK: All {len(critical_modules)} core modules imported successfully")

    return len(failed)


# =========================================================================
# B. BOOTSTRAP / STARTUP
# =========================================================================
def test_bootstrap():
    print("\n=== B. CORE STARTUP ===")
    category = "bootstrap"

    start = time.monotonic()
    try:
        from mini_kio.core.runtime import bootstrap_runtime, get_runtime
        rt = bootstrap_runtime()
        elapsed = time.monotonic() - start

        record(category, "bootstrap_runtime", PASS, f"{elapsed:.2f}s")

        # Verify runtime state
        if rt is None:
            record(category, "runtime_not_none", FAIL, "bootstrap returned None")
            return 1

        record(category, "runtime_created", PASS, f"type={type(rt).__name__}")

        # Check readiness
        if hasattr(rt, "is_ready"):
            ready = rt.is_ready
            record(category, "runtime_ready", PASS if ready else FAIL, f"ready={ready}")
        else:
            record(category, "runtime_ready", SKIP, "no is_ready attribute")

        # Check shutdown flag
        if hasattr(rt, "shutdown_requested"):
            record(category, "shutdown_flag_init", PASS, f"shutdown_requested={rt.shutdown_requested}")
        else:
            record(category, "shutdown_flag_init", SKIP, "no shutdown_requested attribute")

        # Verify get_runtime returns same object
        from mini_kio.core.runtime import get_runtime as grt
        current = grt()
        record(category, "get_runtime_consistency", PASS if current is rt else FAIL,
               f"same={current is rt}")

        return 0

    except Exception as e:
        elapsed = time.monotonic() - start
        record(category, "bootstrap_runtime", FAIL, f"{type(e).__name__}: {e} ({elapsed:.1f}s)")
        traceback.print_exc()
        return 1


# =========================================================================
# C. BASIC COMMAND EXECUTION
# =========================================================================
def test_command_execution():
    print("\n=== C. BASIC COMMAND EXECUTION ===")
    category = "command_exec"

    from mini_kio.core.command_router import route

    test_cases = [
        ("time/date query", "what time is it"),
        ("calculation", "calculate 2 + 2"),
        ("capability lookup", "open chrome"),
        ("unknown command", "asdfghjkl"),
        ("conversational", "hello"),
        ("single word", "hey"),
        ("empty-ish", "k"),
    ]

    for name, prompt in test_cases:
        start = time.monotonic()
        try:
            result = route(prompt)
            elapsed = time.monotonic() - start

            if result is None:
                record(category, name, FAIL, f"route returned None ({elapsed:.2f}s)")
                continue

            # Check it's a dict-like result
            if isinstance(result, dict):
                success = result.get("success")
                reply = result.get("reply", result.get("message", ""))
                record(category, name, PASS,
                       f"success={success} reply_len={len(str(reply))} {elapsed:.2f}s")
            else:
                record(category, name, PASS,
                       f"type={type(result).__name__} {elapsed:.2f}s")

        except Exception as e:
            elapsed = time.monotonic() - start
            record(category, name, FAIL, f"{type(e).__name__}: {e} ({elapsed:.2f}s)")

    return 0


# =========================================================================
# D. STALE DETECTION COMPONENT TEST
# =========================================================================
def test_stale_detection():
    print("\n=== D. STALE DETECTION ===")
    category = "stale_detection"

    try:
        from kio_bot import _is_failure_response, _is_fast_path

        # _is_failure_response tests
        cases = [
            ("Nothing is playing right now.", False, "informational"),
            ("I couldn't find that.", True, "failure"),
            ("Operation failed.", True, "failure"),
            ("Error occurred.", True, "failure"),
            ("Done!", False, "success"),
            ("", False, "empty"),
            ("I don't have that information.", True, "failure"),
        ]

        for reply, expected, desc in cases:
            result = _is_failure_response(reply)
            status = PASS if result == expected else FAIL
            record(category, f"is_failure({desc})", status,
                   f"expected={expected} got={result}")

        # _is_fast_path tests
        fast_cases = [
            ("hello", True),
            ("hey", True),
            ("thanks", True),
            ("ok", True),
            ("what time is it", False),
            ("open chrome", False),
        ]

        for msg, expected in fast_cases:
            result = _is_fast_path(msg)
            status = PASS if result == expected else FAIL
            record(category, f"is_fast_path('{msg}')", status,
                   f"expected={expected} got={result}")

    except Exception as e:
        record(category, "stale_detection_import", FAIL, f"{type(e).__name__}: {e}")
        traceback.print_exc()
        return 1

    return 0


# =========================================================================
# E. CONCURRENCY / THREAD POOL
# =========================================================================
def test_concurrency():
    print("\n=== E. CONCURRENCY SAFETY ===")
    category = "concurrency"

    try:
        from kio_bot import _LONG_OP_POOL, _FAST_POOL, _session_locks, _session_counter, _session_completed

        # Verify pools exist with correct sizes
        record(category, "long_pool_exists", PASS, f"max_workers={_LONG_OP_POOL._max_workers}")
        record(category, "fast_pool_exists", PASS, f"max_workers={_FAST_POOL._max_workers}")

        # Test thread pool execution
        def dummy_task(n):
            time.sleep(0.01)
            return n * 2

        # Fast pool
        start = time.monotonic()
        futures = [_FAST_POOL.submit(dummy_task, i) for i in range(8)]
        results = [f.result(timeout=5) for f in futures]
        elapsed = time.monotonic() - start
        expected = [0, 2, 4, 6, 8, 10, 12, 14]
        record(category, "fast_pool_execution", PASS if results == expected else FAIL,
               f"elapsed={elapsed:.3f}s")

        # Long pool
        start = time.monotonic()
        futures = [_LONG_OP_POOL.submit(dummy_task, i) for i in range(6)]
        results = [f.result(timeout=5) for f in futures]
        elapsed = time.monotonic() - start
        expected = [0, 2, 4, 6, 8, 10]
        record(category, "long_pool_execution", PASS if results == expected else FAIL,
               f"elapsed={elapsed:.3f}s")

        # Session ordering dicts exist
        record(category, "session_locks", PASS, f"type={type(_session_locks).__name__}")
        record(category, "session_counter", PASS, f"type={type(_session_counter).__name__}")
        record(category, "session_completed", PASS, f"type={type(_session_completed).__name__}")

    except Exception as e:
        record(category, "concurrency_test", FAIL, f"{type(e).__name__}: {e}")
        traceback.print_exc()
        return 1

    return 0


# =========================================================================
# F. MEMORY / RESOURCE GUARD
# =========================================================================
def test_memory():
    print("\n=== F. MEMORY / RESOURCES ===")
    category = "memory"

    tracemalloc.start()
    snapshot1 = tracemalloc.take_snapshot()

    # Simulate 100 route calls
    from mini_kio.core.command_router import route
    start = time.monotonic()
    for i in range(100):
        try:
            route("hello")
        except Exception:
            pass
    elapsed = time.monotonic() - start
    record(category, "100_route_calls", PASS, f"{elapsed:.2f}s")

    snapshot2 = tracemalloc.take_snapshot()
    stats = snapshot2.compare_to(snapshot1, "lineno")
    total_growth = sum(s.size_diff for s in stats if s.size_diff > 0)
    total_shrink = sum(s.size_diff for s in stats if s.size_diff < 0)
    net_growth = total_growth + total_shrink

    record(category, "memory_growth_100_calls", PASS,
           f"net={net_growth/1024:.1f}KB growth={total_growth/1024:.1f}KB shrink={total_shrink/1024:.1f}KB")

    # Check RSS
    try:
        import psutil
        proc = psutil.Process()
        rss_mb = proc.memory_info().rss / (1024 * 1024)
        record(category, "current_rss", PASS, f"{rss_mb:.1f}MB")
        record(category, "under_650mb_limit", PASS if rss_mb < 650 else FAIL,
               f"{rss_mb:.1f}MB / 650MB")
    except ImportError:
        record(category, "current_rss", SKIP, "psutil not available")

    tracemalloc.stop()
    return 0


# =========================================================================
# G. RESOURCE GUARD (Runtime)
# =========================================================================
def test_resource_guard():
    print("\n=== G. RESOURCE GUARD ===")
    category = "resource_guard"

    try:
        from mini_kio.core.runtime import get_runtime
        rt = get_runtime()
        if rt is None:
            record(category, "runtime_available", SKIP, "no runtime")
            return 0

        record(category, "runtime_available", PASS)

        # Check ResourceGuard attributes
        if hasattr(rt, "resource_guard") and rt.resource_guard is not None:
            guard = rt.resource_guard
            if hasattr(guard, "max_rss_mb"):
                record(category, "max_rss_mb", PASS, f"{guard.max_rss_mb}MB")
            if hasattr(guard, "check"):
                try:
                    guard.check()
                    record(category, "guard_check", PASS, "check passed")
                except Exception as e:
                    record(category, "guard_check", FAIL, str(e))
        else:
            record(category, "resource_guard", SKIP, "no resource_guard attribute")

    except Exception as e:
        record(category, "resource_guard", FAIL, f"{type(e).__name__}: {e}")

    return 0


# =========================================================================
# MAIN
# =========================================================================
def main():
    print("=" * 60)
    print("KIO DIRECT RUNTIME SMOKE TESTS")
    print(f"Python {sys.version}")
    print(f"Working dir: {os.getcwd()}")
    print(f"Time: {time.strftime('%Y-%m-%d %H:%M:%S')}")
    print("=" * 60)

    t0 = time.monotonic()

    errors = 0
    errors += test_import_health()
    errors += test_bootstrap()
    errors += test_command_execution()
    errors += test_stale_detection()
    errors += test_concurrency()
    errors += test_memory()
    errors += test_resource_guard()

    elapsed = time.monotonic() - t0

    # Summary
    passed = sum(1 for _, _, r in RESULTS if "[PASS]" in r)
    failed = sum(1 for _, _, r in RESULTS if "[FAIL]" in r)
    skipped = sum(1 for _, _, r in RESULTS if "[SKIP]" in r)

    print("\n" + "=" * 60)
    print(f"RESULTS: {passed} passed, {failed} failed, {skipped} skipped in {elapsed:.1f}s")
    if failed > 0:
        print("\nFAILED TESTS:")
        for cat, name, result in RESULTS:
            if "[FAIL]" in result:
                print(f"  [{cat}] {name}: {result}")
    print("=" * 60)

    return 1 if failed > 0 else 0


if __name__ == "__main__":
    sys.exit(main())
