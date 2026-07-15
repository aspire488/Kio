"""Central registry of tools discovered across all connected MCP servers."""

from __future__ import annotations

import logging
import time

from .exceptions import ToolNotFoundError
from .types import ToolDescriptor, ToolSchema

logger = logging.getLogger("mcp_runtime.registry")


class ToolRegistry:
    """Stores ToolDescriptor entries keyed by qualified name
    ('server_id::tool_name') with lookup helpers by bare tool name too."""

    def __init__(self) -> None:
        self._by_qualified: dict[str, ToolDescriptor] = {}
        self._by_bare_name: dict[str, list[str]] = {}

    def register_server_tools(
        self, server_id: str, schemas: list[ToolSchema], *, version: str = "unknown",
        permissions_by_tool: dict[str, list[str]] | None = None,
    ) -> None:
        self.clear_server(server_id)
        permissions_by_tool = permissions_by_tool or {}
        for schema in schemas:
            descriptor = ToolDescriptor(
                server_id=server_id,
                schema=schema,
                version=version,
                permissions=permissions_by_tool.get(schema.name, []),
                registered_at=time.time(),
            )
            self._by_qualified[descriptor.qualified_name] = descriptor
            self._by_bare_name.setdefault(schema.name, []).append(descriptor.qualified_name)
        logger.info("registered %d tools for server %s", len(schemas), server_id)

    def clear_server(self, server_id: str) -> None:
        stale = [q for q, d in self._by_qualified.items() if d.server_id == server_id]
        for q in stale:
            descriptor = self._by_qualified.pop(q, None)
            if descriptor is None:
                continue
            bucket = self._by_bare_name.get(descriptor.schema.name, [])
            if q in bucket:
                bucket.remove(q)
            if not bucket:
                self._by_bare_name.pop(descriptor.schema.name, None)

    def set_server_health(self, server_id: str, healthy: bool) -> None:
        for descriptor in self._by_qualified.values():
            if descriptor.server_id == server_id:
                descriptor.healthy = healthy

    def resolve(self, tool_name: str, server_id: str | None = None) -> ToolDescriptor:
        if server_id is not None:
            qualified = f"{server_id}::{tool_name}"
            descriptor = self._by_qualified.get(qualified)
            if descriptor is None:
                raise ToolNotFoundError(f"tool '{qualified}' not found")
            return descriptor

        if "::" in tool_name:
            descriptor = self._by_qualified.get(tool_name)
            if descriptor is None:
                raise ToolNotFoundError(f"tool '{tool_name}' not found")
            return descriptor

        candidates = self._by_bare_name.get(tool_name, [])
        if not candidates:
            raise ToolNotFoundError(f"tool '{tool_name}' not found on any connected server")
        if len(candidates) > 1:
            servers = ", ".join(c.split("::")[0] for c in candidates)
            raise ToolNotFoundError(
                f"tool name '{tool_name}' is ambiguous across servers [{servers}]; "
                f"specify server_id or use 'server_id::{tool_name}'"
            )
        return self._by_qualified[candidates[0]]

    def list_tools(self, server_id: str | None = None) -> list[ToolDescriptor]:
        tools = list(self._by_qualified.values())
        if server_id is not None:
            tools = [t for t in tools if t.server_id == server_id]
        return tools

    def has_tool(self, tool_name: str, server_id: str | None = None) -> bool:
        try:
            self.resolve(tool_name, server_id)
            return True
        except ToolNotFoundError:
            return False
