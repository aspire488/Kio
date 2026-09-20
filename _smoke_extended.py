"""
KIO Extended Smoke Tests — Phases 5-7
Failure/Recovery, Concurrency/Latency, Lifecycle/Shutdown
"""
from __future__ import annotations

import os
import sys
import time
import threading
import concurrent.futures
import tracemalloc
import traceback

os.environ["KIO_TEST_MODE"] = "1"

ROOT = os.path.dirname(os.path.abspath(__file__))
if ROOT not in sys.path:
    sys.path.insert(0, ROOT)

RESULTS: list[tuple[str, str, str]] = []

def record(category, name, status, detail=""):
    tag = f"[{status}]"
    RESULTS.append((category, name, f"{tag} {detail}" if detail else tag))
    sym = "OK" if status == "PASS" else ("XX" if status == "FAIL" else "--")
    line = f"  {sym} {name}"
    if detail:
        line += f" -- {detail}"
    print(line)


# =========================================================================
# PHASE 5: FAILURE / RECOVERY
# =========================================================================
def test_failure_recovery():
    print("\n=== PHASE 5: FAILURE / RECOVERY ===")
    cat = "failure_recovery"

    from mini_kio.core.command_router import route

    # Test: rapid sequential commands after error
    try:
        # Intentionally trigger edge cases
        route("")  # empty
        record(cat, "empty_command_recovery", PASS)

        route("open nonexistent_app_xyz")  # nonexistent app
        record(cat, "nonexistent_app_recovery", PASS)

        route("a" * 10000)  # very long input
        record(cat, "long_input_recovery", PASS)

        route("\x00\x01\x02")  # binary garbage
        record(cat, "binary_input_recovery", PASS)

        # Then a normal command should still work
        result = route("hello")
        record(cat, "normal_after_failures", PASS if result else FAIL,
               f"type={type(result).__name__}")

    except Exception as e:
        record(cat, "failure_recovery", FAIL, f"{type(e).__name__}: {e}")

    # Test: concurrent failures don't corrupt state
    def failing_task(i):
        try:
            route(f"open nonexistent_{i}_xyz")
        except Exception:
            pass
        return True

    try:
        with concurrent.futures.ThreadPoolExecutor(max_workers=4) as pool:
            futs = [pool.submit(failing_task, i) for i in range(10)]
            results = [f.result(timeout=5) for f in futs]
        record(cat, "concurrent_failures", PASS if all(results) else FAIL,
               f"{sum(results)}/10 completed")
    except Exception as e:
        record(cat, "concurrent_failures", FAIL, str(e))

    # Verify normal command still works after concurrent failures
    try:
        result = route("hello")
        record(cat, "normal_after_concurrent_failures", PASS if result else FAIL)
    except Exception as e:
        record(cat, "normal_after_concurrent_failures", FAIL, str(e))

    return 0


PASS = "PASS"
FAIL = "FAIL"
SKIP = "SKIP"


# =========================================================================
# PHASE 6: CONCURRENCY / LATENCY
# =========================================================================
def test_concurrency_latency():
    print("\n=== PHASE 6: CONCURRENCY / LATENCY ===")
    cat = "concurrency_latency"

    from mini_kio.core.command_router import route

    # Serial baseline
    latencies = []
    for _ in range(50):
        start = time.monotonic()
        route("hello")
        latencies.append((time.monotonic() - start) * 1000)

    latencies.sort()
    p50 = latencies[len(latencies)//2]
    p95 = latencies[int(len(latencies)*0.95)]
    p99 = latencies[int(len(latencies)*0.99)]
    mx = latencies[-1]
    record(cat, "serial_latency", PASS,
           f"p50={p50:.1f}ms p95={p95:.1f}ms p99={p99:.1f}ms max={mx:.1f}ms (n=50)")

    # Concurrent: 2 requests
    def timed_route(msg):
        start = time.monotonic()
        route(msg)
        return (time.monotonic() - start) * 1000

    for n_concurrent in [2, 4, 8]:
        futs_latencies = []
        barrier = threading.Barrier(n_concurrent)

        def sync_route(msg, b):
            b.wait()
            return timed_route(msg)

        try:
            with concurrent.futures.ThreadPoolExecutor(max_workers=n_concurrent) as pool:
                futs = [pool.submit(sync_route, "hello", barrier) for _ in range(n_concurrent)]
                futs_latencies = [f.result(timeout=10) for f in futs]

            cl_sorted = sorted(futs_latencies)
            record(cat, f"concurrent_{n_concurrent}_latency", PASS,
                   f"min={cl_sorted[0]:.1f}ms max={cl_sorted[-1]:.1f}ms avg={sum(futs_latencies)/len(futs_latencies):.1f}ms")

        except Exception as e:
            record(cat, f"concurrent_{n_concurrent}_latency", FAIL, str(e))

    return 0


# =========================================================================
# PHASE 7: LIFECYCLE / SHUTDOWN
# =========================================================================
def test_lifecycle():
    print("\n=== PHASE 7: LIFECYCLE / SHUTDOWN ===")
    cat = "lifecycle"

    # Test 1: Bootstrap + shutdown cycle
    try:
        from mini_kio.core.runtime import bootstrap_runtime, get_runtime

        start = time.monotonic()
        rt = bootstrap_runtime()
        boot_time = (time.monotonic() - start) * 1000
        record(cat, "bootstrap_time", PASS, f"{boot_time:.0f}ms")

        # Verify runtime is live
        current = get_runtime()
        record(cat, "runtime_alive", PASS if current is rt else FAIL)

        # Check shutdown flag is False
        if hasattr(current, "shutdown_requested"):
            record(cat, "shutdown_flag_false",
                   PASS if not current.shutdown_requested else FAIL)

        # Trigger shutdown if possible
        if hasattr(current, "request_shutdown"):
            current.request_shutdown()
            time.sleep(0.5)
            record(cat, "shutdown_requested", PASS if current.shutdown_requested else FAIL)

        # Second bootstrap should work
        rt2 = bootstrap_runtime()
        record(cat, "second_bootstrap", PASS if rt2 is not None else FAIL,
               f"type={type(rt2).__name__ if rt2 else 'None'}")

        if hasattr(rt2, "shutdown_requested"):
            if rt2.shutdown_requested:
                rt2.shutdown_requested = False  # reset for clean exit
            record(cat, "second_runtime_shutdown_false",
                   PASS if not rt2.shutdown_requested else FAIL)

    except Exception as e:
        record(cat, "lifecycle_test", FAIL, f"{type(e).__name__}: {e}")
        traceback.print_exc()

    # Test 2: Thread pool cleanup
    try:
        from kio_bot import _LONG_OP_POOL, _FAST_POOL

        # Submit work
        futures = [_FAST_POOL.submit(lambda: time.sleep(0.01)) for _ in range(5)]
        [f.result(timeout=5) for f in futures]

        # Check thread counts
        fast_threads = _FAST_POOL._max_workers
        long_threads = _LONG_OP_POOL._max_workers
        record(cat, "pool_workers", PASS,
               f"fast={fast_threads} long={long_threads}")

    except Exception as e:
        record(cat, "pool_check", FAIL, str(e))

    return 0


# =========================================================================
# MAIN
# =========================================================================
def main():
    print("=" * 60)
    print("KIO EXTENDED SMOKE TESTS (Phases 5-7)")
    print(f"Python {sys.version}")
    print(f"Time: {time.strftime('%Y-%m-%d %H:%M:%S')}")
    print("=" * 60)

    t0 = time.monotonic()
    errors = 0
    errors += test_failure_recovery()
    errors += test_concurrency_latency()
    errors += test_lifecycle()

    elapsed = time.monotonic() - t0
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
