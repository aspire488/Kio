#!/usr/bin/env python3
"""Trace end-to-end pipeline latency for a freshness query."""
from __future__ import annotations
import time, sys, os
from pathlib import Path
from dotenv import load_dotenv
load_dotenv()
sys.stdout.reconfigure(encoding="utf-8")

# Patch before importing pipeline
_original_ask = None
_timings = {}

def _patched_ask(*args, **kwargs):
    t0 = time.monotonic()
    result = _original_ask(*args, **kwargs)
    elapsed = time.monotonic() - t0
    _timings['llm_total'] = _timings.get('llm_total', 0) + elapsed
    _timings['llm_calls'] = _timings.get('llm_calls', 0) + 1
    print(f"  [LLM] call #{_timings['llm_calls']}: {elapsed:.2f}s")
    return result

from mini_kio.llm import llm_ops
_original_ask = llm_ops.ask_llm_sync
llm_ops.ask_llm_sync = _patched_ask

# Patch knowledge router
_original_route = None
def _patched_route(*args, **kwargs):
    t0 = time.monotonic()
    result = _original_route(*args, **kwargs)
    elapsed = time.monotonic() - t0
    _timings['search_total'] = _timings.get('search_total', 0) + elapsed
    _timings['search_calls'] = _timings.get('search_calls', 0) + 1
    print(f"  [SEARCH] call #{_timings['search_calls']}: {elapsed:.2f}s")
    return result

from mini_kio.knowledge import retrieval_router
_original_route = retrieval_router.KnowledgeRouter.route_for_topic
retrieval_router.KnowledgeRouter.route_for_topic = _patched_route

# Patch semantic ingestion
_original_ingest = None
def _patched_ingest(*args, **kwargs):
    t0 = time.monotonic()
    result = _original_ingest(*args, **kwargs)
    elapsed = time.monotonic() - t0
    _timings['semantic_total'] = _timings.get('semantic_total', 0) + elapsed
    _timings['semantic_calls'] = _timings.get('semantic_calls', 0) + 1
    print(f"  [SEMANTIC] ingest #{_timings['semantic_calls']}: {elapsed:.2f}s")
    return result

from mini_kio.semantic import intelligence as _sem
_original_ingest = _sem.ingest_turn
_sem.ingest_turn = _patched_ingest

from mini_kio.core.pipeline import Pipeline

print("=" * 60)
print("PIPELINE LATENCY TRACE")
print("=" * 60)

query = sys.argv[1] if len(sys.argv) > 1 else "What happened in the news today?"
print(f"\nQuery: {query!r}\n")

t_start = time.monotonic()
p = Pipeline()
result = p.run(query, session_id="latency_test")
t_end = time.monotonic()

total = t_end - t_start
print(f"\n{'='*60}")
print(f"RESULTS:")
print(f"  Total pipeline: {total:.2f}s")
print(f"  LLM calls: {_timings.get('llm_calls', 0)}")
print(f"  LLM total: {_timings.get('llm_total', 0):.2f}s")
print(f"  Search calls: {_timings.get('search_calls', 0)}")
print(f"  Search total: {_timings.get('search_total', 0):.2f}s")
print(f"  Semantic calls: {_timings.get('semantic_calls', 0)}")
print(f"  Semantic total: {_timings.get('semantic_total', 0):.2f}s")
print(f"  Response: {(result.get('message', '') or '')[:200]!r}")
print(f"  Success: {result.get('success')}")
