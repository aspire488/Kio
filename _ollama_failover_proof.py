"""
Ollama Failover Validation Script.

Patches config to disable all cloud providers, forcing chain to Ollama.
Then runs Steps 2-5: single query, 10 queries, stress test 50 calls.
"""
import os, sys, time, json

# Clear cached modules so config re-initializes
for mod in list(sys.modules.keys()):
    if "mini_kio" in mod:
        del sys.modules[mod]

# Force-disable all cloud providers via config patching
from mini_kio.core import config
config.GEMINI_ENABLED = False
config.GROQ_ENABLED = False
config.CEREBRAS_ENABLED = False
config.SAMBANOVA_ENABLED = False
config.FIREWORKS_ENABLED = False
config.HUGGINGFACE_ENABLED = False
config.OPENROUTER_ENABLED = False
config.TOGETHER_AI_ENABLED = False
config.FREELLMAPI_ENABLED = False
config.OLLAMA_ENABLED = True

import asyncio
from mini_kio.core.llm_router import _get_gateway, ask_llm

g = _get_gateway()
r = g.get_registry()

print("=" * 60)
print("OLLAMA FAILOVER VALIDATION")
print("=" * 60)

# Step 2: Show filtered chain
chain = r.get_providers()
print(f"\nProvider chain after cloud disable ({len(chain)} providers):")
print(f"  {chain}")
print()

# ── Step 3: Single query ────────────────────────────────────────
print("-" * 60)
print("STEP 3 — ask_llm('Who directed Interstellar?')")
print("-" * 60)

r.clear_diagnostics()
start = time.monotonic()
result = asyncio.run(ask_llm("Who directed Interstellar? Answer in one short sentence.", timeout=30.0, max_tokens=128))
elapsed = (time.monotonic() - start) * 1000
print(f"Answer ({elapsed:.0f}ms): {result}")
print()
print("Provider diagnostics:")
for d in r.get_diagnostics():
    print(f"  [{d.event:<30}] {d.provider:<15} {d.detail[:80]}")
print()

# Verify Ollama was the provider
ollama_served = any(d.event == "provider_selected" and d.provider == "ollama" for d in r.get_diagnostics())
print(f"Ollama served the request: {ollama_served}")
print()

# ── Step 4: 10 queries ──────────────────────────────────────────
print("=" * 60)
print("STEP 4 — 10 queries")
print("=" * 60)

queries = [
    "Who directed Interstellar?",
    "Explain quantum tunneling",
    "What is Kubernetes?",
    "Atomic Habits summary",
    "FIFA World Cup overview",
    "Who is Christopher Nolan?",
    "Who is Sung Jinwoo?",
    "What is The Bear TV show about?",
    "GTA VI release date",
    "French Revolution summary",
]

results_table = []

for i, q in enumerate(queries, 1):
    r.clear_diagnostics()
    start = time.monotonic()
    try:
        answer = asyncio.run(ask_llm(q + " Answer in one short sentence.", timeout=30.0, max_tokens=128))
        elapsed_ms = (time.monotonic() - start) * 1000
        provider_used = "unknown"
        for d in r.get_diagnostics():
            if d.event == "provider_selected":
                provider_used = d.provider
        status = "OK" if (answer and len(answer) > 5) else "FAIL"
        results_table.append((i, q[:50], provider_used, f"{elapsed_ms:.0f}ms", status, (answer or "")[:60]))
    except Exception as e:
        elapsed_ms = (time.monotonic() - start) * 1000
        results_table.append((i, q[:50], "ERROR", f"{elapsed_ms:.0f}ms", "EXC", str(e)[:60]))

print()
print(f"{'#':<3} {'Query':<52} {'Provider':<12} {'Latency':<10} {'Status':<6} Response")
print("-" * 140)
for row in results_table:
    print(f"{row[0]:<3} {row[1]:<52} {row[2]:<12} {row[3]:<10} {row[4]:<6} {row[5]}")
print()

# Verify all served by Ollama
used = set(r[2] for r in results_table)
print(f"All queries served by: {used}")
print(f"Ollama only: {used == {'ollama'}}")
print()

# ── Step 5: Stress test — 50 calls ──────────────────────────────
print("=" * 60)
print("STEP 5 — Stress test: 50 sequential calls")
print("=" * 60)

stress_queries = [
    "What is Python?",
    "Explain gravity",
    "Who wrote Hamlet?",
    "What is AI?",
    "Capital of France",
    "What is Docker?",
    "Explain recursion",
    "What is blockchain?",
    "Who is Einstein?",
    "What is Linux?",
] * 5

timeouts = 0
failures = 0
successes = 0
latencies = []
provider_counts = {}

start_time = time.monotonic()

for i, q in enumerate(stress_queries, 1):
    r.clear_diagnostics()
    q_start = time.monotonic()
    try:
        answer = asyncio.run(ask_llm(q + " One sentence.", timeout=30.0, max_tokens=64))
        q_elapsed = (time.monotonic() - q_start) * 1000
        latencies.append(q_elapsed)

        provider_used = "unknown"
        for d in r.get_diagnostics():
            if d.event == "provider_selected":
                provider_used = d.provider
        provider_counts[provider_used] = provider_counts.get(provider_used, 0) + 1

        if answer and len(answer) > 3:
            successes += 1
        else:
            failures += 1
    except asyncio.TimeoutError:
        timeouts += 1
        failures += 1
    except Exception:
        failures += 1

    if i % 10 == 0:
        avg = sum(latencies[-10:]) / max(len(latencies[-10:]), 1)
        print(f"  {i}/50 — ok={successes} fail={failures} timeout={timeouts} avg_ms={avg:.0f}")

total_time = time.monotonic() - start_time

print()
print("Stress Test Results:")
print(f"  Calls:         50")
print(f"  Successes:     {successes}")
print(f"  Failures:      {failures}")
print(f"  Timeouts:      {timeouts}")
print(f"  Total time:    {total_time:.1f}s")
if latencies:
    print(f"  Avg latency:   {sum(latencies)/len(latencies):.0f}ms")
    print(f"  Min latency:   {min(latencies):.0f}ms")
    print(f"  Max latency:   {max(latencies):.0f}ms")
print(f"  Providers:     {provider_counts}")

try:
    import psutil
    proc = psutil.Process()
    mem = proc.memory_info()
    print(f"  Python RSS:    {mem.rss / 1024 / 1024:.1f} MB")
    print(f"  Python VMS:    {mem.vms / 1024 / 1024:.1f} MB")
except ImportError:
    pass

# Final chain integrity
print(f"  Final chain:   {r.get_providers()}")
print(f"  Ollama state:  {r.get_state('ollama').value}")
total_fails = sum(r.get_failure_count(p) for p in r.get_providers())
print(f"  Total fails:   {total_fails}")
print(f"  Chain intact:  {len(r.get_providers()) == 1 and 'ollama' in r.get_providers()}")
print(f"  No crash:      {successes + failures == 50}")
print(f"  No hang:       {total_time < 600}")
print()
print("=" * 60)
print("VALIDATION COMPLETE")
print("=" * 60)
