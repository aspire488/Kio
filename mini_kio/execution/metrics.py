"""Metrics collector — execution latency, success/failure rates, retry stats.

Tracks all execution metrics for providers, workflows, and MCP tools.
Emits observations through the observation stream.
Thread-safe singleton.
"""

from __future__ import annotations

import logging
import threading
import time
from collections import defaultdict
from typing import Any

logger = logging.getLogger("mini_kio.execution.metrics")


class MetricsCollector:
    _instance: MetricsCollector | None = None
    _lock = threading.Lock()

    def __new__(cls) -> MetricsCollector:
        if cls._instance is None:
            with cls._lock:
                if cls._instance is None:
                    cls._instance = super().__new__(cls)
                    cls._instance._initialized = False
        return cls._instance

    def __init__(self) -> None:
        if getattr(self, '_initialized', False):
            return
        self._initialized = True
        self._lock = threading.Lock()
        self._executions: dict[str, list[dict[str, Any]]] = defaultdict(list)
        self._workflow_metrics: dict[str, list[dict[str, Any]]] = defaultdict(list)
        self._provider_latency: dict[str, list[float]] = defaultdict(list)
        self._capability_latency: dict[str, list[float]] = defaultdict(list)
        self._retry_counts: dict[str, int] = defaultdict(int)
        self._error_counts: dict[str, dict[str, int]] = defaultdict(lambda: defaultdict(int))

    def record_execution(self, action: str, target: str, success: bool,
                          elapsed_ms: float, provider: str = "") -> None:
        with self._lock:
            self._executions[action].append({
                "success": success, "elapsed_ms": elapsed_ms,
                "provider": provider, "timestamp": time.time(),
            })
            self._capability_latency[action].append(elapsed_ms)
            if provider:
                self._provider_latency[provider].append(elapsed_ms)
            if not success:
                self._error_counts[action]["total"] += 1

    def record_retry(self, action: str) -> None:
        with self._lock:
            self._retry_counts[action] += 1

    def record_workflow(self, wf_id: str, name: str, status: str,
                         duration_ms: float, steps: int) -> None:
        with self._lock:
            self._workflow_metrics[name].append({
                "id": wf_id, "status": status, "duration_ms": duration_ms,
                "steps": steps, "timestamp": time.time(),
            })

    def get_provider_latency(self, provider: str) -> dict[str, Any]:
        with self._lock:
            latencies = self._provider_latency.get(provider, [])
            if not latencies:
                return {"avg_ms": 0, "min_ms": 0, "max_ms": 0, "count": 0}
            return {
                "avg_ms": round(sum(latencies) / len(latencies), 1),
                "min_ms": round(min(latencies), 1),
                "max_ms": round(max(latencies), 1),
                "count": len(latencies),
            }

    def get_capability_latency(self, capability: str) -> dict[str, Any]:
        with self._lock:
            latencies = self._capability_latency.get(capability, [])
            if not latencies:
                return {"avg_ms": 0, "min_ms": 0, "max_ms": 0, "count": 0}
            return {
                "avg_ms": round(sum(latencies) / len(latencies), 1),
                "min_ms": round(min(latencies), 1),
                "max_ms": round(max(latencies), 1),
                "count": len(latencies),
            }

    def get_success_rate(self, action: str) -> float:
        with self._lock:
            entries = self._executions.get(action, [])
            if not entries:
                return 1.0
            successes = sum(1 for e in entries if e["success"])
            return successes / len(entries)

    def get_retry_count(self, action: str) -> int:
        with self._lock:
            return self._retry_counts.get(action, 0)

    def get_summary(self) -> dict[str, Any]:
        with self._lock:
            total_execs = sum(len(v) for v in self._executions.values())
            total_successes = sum(sum(1 for e in v if e["success"]) for v in self._executions.values())
            return {
                "total_executions": total_execs,
                "total_successes": total_successes,
                "total_failures": total_execs - total_successes,
                "success_rate": round(total_successes / total_execs, 4) if total_execs else 1.0,
                "capabilities_tracked": len(self._executions),
                "providers_tracked": len(self._provider_latency),
                "workflows_tracked": len(self._workflow_metrics),
                "total_retries": sum(self._retry_counts.values()),
            }

    def get_provider_stats(self) -> dict[str, Any]:
        with self._lock:
            return {p: self.get_provider_latency(p) for p in self._provider_latency}

    def get_capability_stats(self) -> dict[str, Any]:
        with self._lock:
            return {c: {**self.get_capability_latency(c),
                        "success_rate": round(self.get_success_rate(c), 4),
                        "retries": self._retry_counts.get(c, 0)}
                    for c in list(self._executions.keys())}

    def reset(self) -> None:
        with self._lock:
            self._executions.clear()
            self._workflow_metrics.clear()
            self._provider_latency.clear()
            self._capability_latency.clear()
            self._retry_counts.clear()
            self._error_counts.clear()


def get_metrics_collector() -> MetricsCollector:
    return MetricsCollector()


def reset_metrics_collector() -> None:
    MetricsCollector._instance = None
