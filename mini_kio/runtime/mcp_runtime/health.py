"""Health monitoring across all connected MCP servers."""

from __future__ import annotations

import asyncio
import logging
from typing import Awaitable, Callable

from .types import ServerHealth, ServerState

logger = logging.getLogger("mcp_runtime.health")

CrashCallback = Callable[[str], Awaitable[None]]


class HealthMonitor:
    """Periodically snapshots health for every registered connection and
    triggers a crash callback when a server flips to CRASHED between
    checks (as a safety net alongside MCPServerConnection's own crash
    handler)."""

    def __init__(self, connections_provider, *, interval_s: float = 15.0) -> None:
        """`connections_provider` returns dict[server_id, MCPServerConnection]."""
        self._connections_provider = connections_provider
        self._interval_s = interval_s
        self._task: asyncio.Task | None = None
        self._last_state: dict[str, ServerState] = {}
        self._crash_callbacks: list[CrashCallback] = []

    def on_detected_crash(self, callback: CrashCallback) -> None:
        self._crash_callbacks.append(callback)

    def start(self) -> None:
        if self._task is None or self._task.done():
            self._task = asyncio.create_task(self._loop())

    def stop(self) -> None:
        if self._task is not None:
            self._task.cancel()
            self._task = None

    async def _loop(self) -> None:
        try:
            while True:
                await asyncio.sleep(self._interval_s)
                await self._check_all()
        except asyncio.CancelledError:
            return

    async def _check_all(self) -> None:
        connections = self._connections_provider()
        for server_id, connection in connections.items():
            previous = self._last_state.get(server_id)
            current = connection.state
            self._last_state[server_id] = current
            if previous is not None and previous != ServerState.CRASHED and current == ServerState.CRASHED:
                logger.warning("health monitor detected crash transition for server %s", server_id)
                for cb in self._crash_callbacks:
                    try:
                        await cb(server_id)
                    except Exception:  # noqa: BLE001
                        logger.exception("crash callback raised for %s", server_id)

    def snapshot(self, server_id: str) -> ServerHealth:
        connections = self._connections_provider()
        connection = connections.get(server_id)
        if connection is None:
            return ServerHealth(
                server_id=server_id, state=ServerState.STOPPED, uptime_s=0.0,
                latency_ms_ewma=0.0, pending_requests=0, restart_count=0, failure_count=0,
                last_error="server not registered",
            )
        return ServerHealth(
            server_id=server_id,
            state=connection.state,
            uptime_s=connection.uptime_s,
            latency_ms_ewma=connection.latency_ms_ewma,
            pending_requests=connection.pending_count,
            restart_count=connection.restart_count,
            failure_count=connection.failure_count,
            last_error=connection.last_error,
        )

    def snapshot_all(self) -> list[ServerHealth]:
        connections = self._connections_provider()
        return [self.snapshot(server_id) for server_id in connections]
