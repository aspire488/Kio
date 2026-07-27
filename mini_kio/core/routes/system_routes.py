"""
system_routes.py — System command handlers for KIO.

Extracted from command_router._route_builtin (Work Item 2 of Foundation Stream A).
Owned by: mini_kio/core/routes/
"""

from __future__ import annotations

import logging
from typing import Any, Optional

from mini_kio.core.execution_boundary import execute_action

logger = logging.getLogger(__name__)


def _show_help() -> dict:
    return {
        "success": True,
        "message": (
            "KIO Commands\n"
            "─────────────────────────────────\n"
            "open <app>             open chrome / calculator / notepad / vscode\n"
            "open <folder>          open downloads folder / desktop / documents\n"
            "close <app>            close chrome\n"
            "search <query>         search Google\n"
            "play <query>           play on YouTube\n"
            "open chrome and search <query>   multi-step\n"
            "open chrome and play <query>     multi-step\n"
            "shutdown / restart / lock\n"
            "ping                   check KIO status\n"
            "help                   show this message"
        ),
    }


def _log_route(event: str, **fields: Any) -> None:
    payload: dict[str, Any] = {"evt": event}
    payload.update(fields)
    logger.info(__import__("json").dumps(payload, default=str))


def _route_system(command: str, lower: str, lower_clean: str) -> Optional[dict]:
    """System, utility, and telemetry commands."""

    # ── SYSTEM ────────────────────────────────────────────────────────
    if lower in ("shutdown", "shutdown computer", "shut down"):
        return execute_action("shutdown_system")
    if lower in ("restart", "restart computer"):
        return execute_action("restart_system")
    if lower in ("lock", "lock computer"):
        return execute_action("lock_system")
    if lower in ("recovery", "recover", "recover runtime", "reset safety"):
        _log_route("route", intent="recovery_runtime")
        return execute_action("recovery_runtime")

    # ── UTILITY ───────────────────────────────────────────────────────
    if lower in ("ping", "Ping", "PING"):
        return {"success": True, "message": "KIO online!"}

    # ── TELEMETRY ─────────────────────────────────────────────────────
    if any(x in lower for x in ("uptime", "how long have you been running")):
        from mini_kio.core.runtime import get_runtime_snapshot
        snap = get_runtime_snapshot()
        uptime_s = snap.get("uptime_ms", 0) // 1000
        if uptime_s > 3600:
            m = (uptime_s % 3600) // 60
            msg = f"Uptime: {uptime_s // 3600}h {m}m."
        elif uptime_s > 60:
            msg = f"Uptime: {uptime_s // 60}m."
        else:
            msg = f"Uptime: {uptime_s}s."
        return {"success": True, "message": msg}
    if any(x in lower for x in ("ram usage", "memory usage", "how much ram")):
        from mini_kio.core.runtime import get_runtime_snapshot
        return {"success": True, "message": f"Current RAM usage: {get_runtime_snapshot().get('ram_usage_mb', 0)}MB."}
    if any(x in lower for x in ("cpu", "processor")):
        return {"success": True, "message": "CPU metrics are currently unavailable."}
    if lower == "status":
        from mini_kio.core.runtime import get_runtime, get_runtime_snapshot, get_runtime_health_score, get_runtime_integrity_snapshot
        rt = get_runtime()
        if rt is None:
            return {"success": True, "message": "Runtime: offline"}
        snap = get_runtime_snapshot()
        health = get_runtime_health_score()
        integrity = get_runtime_integrity_snapshot()
        return {"success": True, "message": f"Safety state: {rt.safety_state}\nIntegrity score: {health}\nIntegrity status: {integrity.get('status', 'unknown')}\nUptime: {snap.get('uptime_ms', 0)}ms\nObservers: {snap.get('observer_count', 0)}"}
    if "help" in lower:
        return _show_help()

    return None
