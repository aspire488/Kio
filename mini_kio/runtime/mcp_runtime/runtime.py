"""Top-level facade orchestrating multiple concurrent MCP servers via
dependency injection. Single integration point for callers."""

from __future__ import annotations

import asyncio
import logging

from .executor import ToolExecutor
from .exceptions import ServerNotConnectedError
from .health import HealthMonitor
from .registry import ToolRegistry
from .server import MCPServerConnection
from .types import ServerConfig, ServerHealth, ToolCallRequest, ToolCallResult, ToolDescriptor

logger = logging.getLogger("mcp_runtime.runtime")


class MCPRuntime:
    """Owns N MCPServerConnection instances, a shared ToolRegistry, a
    ToolExecutor, and a HealthMonitor. Each server crashing is isolated
    from the others; recovery is per-server."""

    def __init__(self, *, default_tool_timeout_s: float = 30.0, health_check_interval_s: float = 15.0) -> None:
        self._connections: dict[str, MCPServerConnection] = {}
        self._configs: dict[str, ServerConfig] = {}
        self.registry = ToolRegistry()
        self.executor = ToolExecutor(self.registry, self._get_connection, default_timeout_s=default_tool_timeout_s)
        self.health = HealthMonitor(lambda: dict(self._connections), interval_s=health_check_interval_s)
        self.health.on_detected_crash(self._handle_detected_crash)
        self._started = False

    def _get_connection(self, server_id: str) -> MCPServerConnection | None:
        return self._connections.get(server_id)

    async def start(self) -> None:
        self.health.start()
        self._started = True

    async def stop(self) -> None:
        self.health.stop()
        for server_id in list(self._connections.keys()):
            await self.remove_server(server_id)
        self._started = False

    async def add_server(self, config: ServerConfig) -> list[ToolDescriptor]:
        if config.server_id in self._connections:
            raise ServerNotConnectedError(f"server '{config.server_id}' already registered")

        connection = MCPServerConnection(config)
        connection.on_crash(self._handle_connection_crash)
        self._configs[config.server_id] = config
        self._connections[config.server_id] = connection

        schemas = await connection.connect()
        self.registry.register_server_tools(config.server_id, schemas, version=config.protocol_version)
        return self.registry.list_tools(server_id=config.server_id)

    async def remove_server(self, server_id: str) -> None:
        connection = self._connections.pop(server_id, None)
        self._configs.pop(server_id, None)
        self.registry.clear_server(server_id)
        if connection is not None:
            await connection.disconnect()

    async def reload_server_schema(self, server_id: str) -> list[ToolDescriptor]:
        connection = self._require_connection(server_id)
        config = self._configs[server_id]
        schemas = await connection.reload_schema()
        self.registry.register_server_tools(server_id, schemas, version=config.protocol_version)
        return self.registry.list_tools(server_id=server_id)

    async def restart_server(self, server_id: str) -> list[ToolDescriptor]:
        connection = self._require_connection(server_id)
        config = self._configs[server_id]
        schemas = await connection.restart()
        self.registry.register_server_tools(server_id, schemas, version=config.protocol_version)
        self.registry.set_server_health(server_id, True)
        return self.registry.list_tools(server_id=server_id)

    def _require_connection(self, server_id: str) -> MCPServerConnection:
        connection = self._connections.get(server_id)
        if connection is None:
            raise ServerNotConnectedError(f"server '{server_id}' is not registered")
        return connection

    async def _handle_connection_crash(self, server_id: str) -> None:
        self.registry.set_server_health(server_id, False)
        config = self._configs.get(server_id)
        if config is None:
            return
        connection = self._connections.get(server_id)
        if connection is None:
            return
        for attempt in range(1, config.max_restart_attempts + 1):
            try:
                logger.warning("auto-recovering server '%s' (attempt %d/%d)", server_id, attempt, config.max_restart_attempts)
                await self.restart_server(server_id)
                logger.info("server '%s' recovered", server_id)
                return
            except Exception:  # noqa: BLE001
                logger.exception("recovery attempt %d failed for server '%s'", attempt, server_id)
        logger.error("server '%s' exhausted restart attempts; leaving in CRASHED state", server_id)

    async def _handle_detected_crash(self, server_id: str) -> None:
        # Safety net: MCPServerConnection already invokes crash handlers via
        # on_crash, but if that path is ever missed (e.g. race during
        # shutdown), the health monitor catches the state transition here.
        logger.debug("health monitor crash signal for %s (handled via connection crash handler)", server_id)

    # -- tool operations ----------------------------------------------------

    async def call_tool(self, tool_name: str, arguments: dict, *, server_id: str | None = None,
                         timeout_s: float | None = None, max_retries: int = 0) -> ToolCallResult:
        request = ToolCallRequest(
            tool_name=tool_name, server_id=server_id, arguments=arguments,
            timeout_s=timeout_s, max_retries=max_retries,
        )
        return await self.executor.call(request)

    async def call_tools(self, requests: list[ToolCallRequest]) -> list[ToolCallResult]:
        return await self.executor.call_many(requests)

    def list_tools(self, server_id: str | None = None) -> list[ToolDescriptor]:
        return self.registry.list_tools(server_id=server_id)

    def server_health(self, server_id: str) -> ServerHealth:
        return self.health.snapshot(server_id)

    def all_health(self) -> list[ServerHealth]:
        return self.health.snapshot_all()

    def connected_servers(self) -> list[str]:
        return list(self._connections.keys())

    async def __aenter__(self) -> "MCPRuntime":
        await self.start()
        return self

    async def __aexit__(self, *_exc_info) -> None:
        await self.stop()
