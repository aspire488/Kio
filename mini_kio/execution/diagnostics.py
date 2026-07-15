"""Diagnostics CLI — view system state, providers, capabilities, and metrics."""

from __future__ import annotations

import argparse
import sys
from typing import Any


def _load_provider_registry():
    try:
        from mini_kio.core.provider_registry import get_provider_registry
        return get_provider_registry()
    except Exception as exc:
        print(f"ERROR loading provider registry: {exc}")
        return None


def _get_providers(reg):
    return list(reg.all_providers())


def _load_metrics():
    try:
        from mini_kio.execution.metrics import get_metrics_collector
        return get_metrics_collector()
    except Exception as exc:
        print(f"ERROR loading metrics: {exc}")
        return None


def _load_workflow_engine():
    try:
        from mini_kio.execution.engine import WorkflowEngine
        from mini_kio.execution.metrics import get_metrics_collector
        return get_metrics_collector()
    except Exception as exc:
        print(f"ERROR loading metrics: {exc}")
        return None


def cmd_providers(args: argparse.Namespace) -> None:
    registry = _load_provider_registry()
    if registry is None:
        sys.exit(1)
    providers = _get_providers(registry)
    if not providers:
        print("No providers registered.")
        return
    print(f"{'Provider':<28} {'Capabilities':<40} {'Health':<10}")
    print("-" * 80)
    for p in providers:
        caps = p.list_capabilities() if hasattr(p, 'list_capabilities') else []
        cap_str = ", ".join(caps[:5])
        if len(caps) > 5:
            cap_str += f" …+{len(caps)-5}"
        health = p.health_check() if hasattr(p, 'health_check') and callable(p.health_check) else "unknown"
        print(f"{p.__class__.__name__:<28} {cap_str:<40} {str(health):<10}")
    print(f"\nTotal: {len(providers)} provider(s)")


def cmd_metrics(args: argparse.Namespace) -> None:
    metrics = _load_metrics()
    if metrics is None:
        sys.exit(1)
    summary = metrics.get_summary()
    print("=== Metrics Summary ===")
    for k, v in summary.items():
        print(f"  {k}: {v}")
    if args.verbose:
        print("\n=== Provider Stats ===")
        for p, s in metrics.get_provider_stats().items():
            print(f"  {p}: avg={s['avg_ms']}ms, min={s['min_ms']}ms, max={s['max_ms']}ms [{s['count']} calls]")
        print("\n=== Capability Stats ===")
        for c, s in metrics.get_capability_stats().items():
            print(f"  {c}: avg={s['avg_ms']}ms, success={s['success_rate']}, retries={s['retries']}")


def cmd_workflows(args: argparse.Namespace) -> None:
    try:
        from mini_kio.execution.engine import WorkflowEngine
        engine = WorkflowEngine()
        wfs = engine.list_workflows()
    except Exception as exc:
        print(f"ERROR: {exc}")
        sys.exit(1)
    if not wfs:
        print("No workflows.")
        return
    for wf in wfs:
        print(f"  [{wf.status.value}] {wf.name} ({wf.id}) — {len(wf.steps)} steps, {wf.duration_ms:.0f}ms")
        if wf.error:
            print(f"    error: {wf.error}")


def cmd_status(args: argparse.Namespace) -> None:
    print("=== Kio Diagnostics ===")
    registry = _load_provider_registry()
    if registry:
        providers = _get_providers(registry)
        print(f"Providers:       {len(providers)}")
        total_caps = sum(len(p.list_capabilities()) for p in providers if hasattr(p, 'list_capabilities'))
        print(f"Capabilities:    {total_caps}")
    metrics = _load_metrics()
    if metrics:
        s = metrics.get_summary()
        print(f"Executions:      {s['total_executions']}")
        print(f"Success rate:    {s['success_rate']*100:.1f}%")
        print(f"Workflows:       {s['workflows_tracked']}")
    print(f"\nPython:          {sys.version.split()[0]}")


def main() -> None:
    parser = argparse.ArgumentParser(description="Kio diagnostics CLI")
    parser.add_argument("-v", "--verbose", action="store_true", help="Verbose output")

    sub = parser.add_subparsers(dest="command", required=True)

    sub.add_parser("providers", help="List all providers with capabilities")
    sub.add_parser("metrics", help="Show execution metrics")
    sub.add_parser("workflows", help="List workflows")
    sub.add_parser("status", help="System status overview")

    args = parser.parse_args()

    if args.command == "providers":
        cmd_providers(args)
    elif args.command == "metrics":
        cmd_metrics(args)
    elif args.command == "workflows":
        cmd_workflows(args)
    elif args.command == "status":
        cmd_status(args)


if __name__ == "__main__":
    main()
