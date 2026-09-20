"""
CHECK 4 — 650MB resource ceiling test.
Runs representative KIO workload and measures peak RSS.
"""
import os, sys, time, threading, concurrent.futures, tracemalloc
import psutil

os.environ["KIO_TEST_MODE"] = "1"
ROOT = os.path.dirname(os.path.abspath(__file__))
if ROOT not in sys.path:
    sys.path.insert(0, ROOT)

process = psutil.Process(os.getpid())

def rss_mb():
    return process.memory_info().rss / (1024 * 1024)

print("=" * 60)
print("CHECK 4 — 650MB RESOURCE CEILING TEST")
print("=" * 60)

# Baseline
rss_start = rss_mb()
print(f"Baseline RSS: {rss_start:.1f} MB")

# Phase 1: Bootstrap
from mini_kio.core.runtime import bootstrap_runtime, get_runtime
rt = bootstrap_runtime()
rss_after_bootstrap = rss_mb()
print(f"After bootstrap: {rss_after_bootstrap:.1f} MB (+{rss_after_bootstrap - rss_start:.1f})")

# Phase 2: Route 500 commands
from mini_kio.core.command_router import route
for i in range(500):
    route("hello")
rss_after_500 = rss_mb()
print(f"After 500 commands: {rss_after_500:.1f} MB (+{rss_after_500 - rss_start:.1f})")

# Phase 3: Concurrent load
def concurrent_route(msg):
    for _ in range(50):
        route(msg)
        route(f"open notepad_{_}")
        route("a" * 1000)

barrier = threading.Barrier(8)
def sync_route(msg, b):
    b.wait()
    for _ in range(50):
        route(msg)
    return True

futures = []
with concurrent.futures.ThreadPoolExecutor(max_workers=8) as pool:
    for i in range(8):
        futures.append(pool.submit(sync_route, f"hello_{i}", barrier))
    results = [f.result(timeout=30) for f in futures]
rss_after_concurrent = rss_mb()
print(f"After 8x50 concurrent: {rss_after_concurrent:.1f} MB (+{rss_after_concurrent - rss_start:.1f})")

# Phase 4: Failure/recovery
for i in range(200):
    route("")
    route(f"open nonexistent_{i}_xyz")
    route("a" * 5000)
    route("\x00\x01\x02")
rss_after_failures = rss_mb()
print(f"After 800 failures: {rss_after_failures:.1f} MB (+{rss_after_failures - rss_start:.1f})")

# Phase 5: Memory/state operations
for i in range(100):
    route("what time is it")
    route("hello")
    route("what's up")
rss_after_state = rss_mb()
print(f"After 300 state ops: {rss_after_state:.1f} MB (+{rss_after_state - rss_start:.1f})")

# Phase 6: Long running - 2000 mixed commands
mixed = ["hello", "open notepad", "what time is it", "play music on spotify",
         "close notepad", "search web python", "a" * 2000, "", "open nonexistent"]
for i in range(2000):
    route(mixed[i % len(mixed)])
rss_after_mixed = rss_mb()
print(f"After 2000 mixed: {rss_after_mixed:.1f} MB (+{rss_after_mixed - rss_start:.1f})")

# Peak measurement
rss_final = rss_mb()
peak_rss = max(rss_start, rss_after_bootstrap, rss_after_500, rss_after_concurrent,
               rss_after_failures, rss_after_state, rss_after_mixed, rss_final)

print(f"\n{'='*60}")
print(f"SUMMARY")
print(f"  Initial RSS:       {rss_start:.1f} MB")
print(f"  Final RSS:         {rss_final:.1f} MB")
print(f"  Peak RSS:          {peak_rss:.1f} MB")
print(f"  Net growth:        {rss_final - rss_start:.1f} MB")
print(f"  650MB ceiling:     {'PASS' if peak_rss <= 650 else 'FAIL'}")
print(f"  Headroom:          {650 - peak_rss:.1f} MB")
print(f"  CPU percent:       {process.cpu_percent(interval=0.1):.1f}%")
print(f"  Thread count:      {threading.active_count()}")
print(f"{'='*60}")
