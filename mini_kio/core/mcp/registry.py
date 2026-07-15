"""MCPServerRegistry — server lifecycle, capability mapping, and dynamic discovery."""

from __future__ import annotations

import logging
from dataclasses import dataclass, field
from typing import Any

logger = logging.getLogger(__name__)


@dataclass
class MCPServerInfo:
    server_type: str
    display_name: str
    version: str = "1.0.0"
    state: str = "pending"
    error_message: str = ""
    working_dir: str | None = None
    metadata: dict[str, Any] = field(default_factory=dict)
    tools: list[dict[str, Any]] = field(default_factory=list)
    _capability_map: dict[str, str] = field(default_factory=dict)

    def tool_capabilities(self) -> list[str]:
        return list(self._capability_map.values())

    def map_tool(self, tool_name: str, capability: str) -> None:
        self._capability_map[tool_name] = capability


class MCPServerRegistry:
    def __init__(self) -> None:
        self._servers: dict[str, MCPServerInfo] = {}
        self._capability_map: dict[str, dict[str, Any]] = {}

    def register_server(self, info: MCPServerInfo) -> None:
        self._servers[info.server_type] = info

    def unregister_server(self, server_type: str) -> None:
        info = self._servers.pop(server_type, None)
        if info is not None:
            for cap in info.tool_capabilities():
                self._capability_map.pop(cap, None)

    def get_server(self, server_type: str) -> MCPServerInfo | None:
        return self._servers.get(server_type)

    def list_servers(self) -> list[MCPServerInfo]:
        return list(self._servers.values())

    def server_count(self) -> int:
        return len(self._servers)

    def connected_count(self) -> int:
        return sum(1 for s in self._servers.values() if s.state == "connected")

    def update_server_state(self, server_type: str, state: str, error_message: str = "") -> None:
        info = self._servers.get(server_type)
        if info is not None:
            info.state = state
            info.error_message = error_message

    def update_server_tools(self, server_type: str, tools: list[dict[str, Any]]) -> None:
        info = self._servers.get(server_type)
        if info is not None:
            info.tools = tools

    def map_tool_to_capability(self, server_type: str, tool_name: str, capability_name: str) -> None:
        info = self._servers.get(server_type)
        if info is not None:
            info.map_tool(tool_name, capability_name)
        self._capability_map[capability_name] = {"server_type": server_type, "tool_name": tool_name}

    def resolve_capability(self, capability_name: str) -> dict[str, Any] | None:
        return self._capability_map.get(capability_name)

    def server_for_capability(self, capability_name: str) -> str | None:
        entry = self._capability_map.get(capability_name)
        return entry["server_type"] if entry else None

    def all_capabilities(self) -> dict[str, dict[str, Any]]:
        return dict(self._capability_map)

    def discover(self) -> int:
        from mini_kio.core.mcp.servers import list_servers as get_server_list
        known = get_server_list()
        for stype in known:
            if stype not in self._servers:
                display = stype.capitalize()
                self.register_server(MCPServerInfo(server_type=stype, display_name=display))
        return len(self._servers)

    def get_permissions(self, server_type: str) -> dict[str, Any]:
        base = {"requires_filesystem_access": False, "requires_network_access": False,
                "requires_shell_access": False, "requires_database_access": False}
        if server_type in ("filesystem", "git", "sqlite"):
            base["requires_filesystem_access"] = True
        if server_type in ("git", "github"):
            base["requires_network_access"] = True
        if server_type in ("terminal", "docker"):
            base["requires_shell_access"] = True
        if server_type in ("sqlite", "postgres"):
            base["requires_database_access"] = True
        if server_type in ("docker", "postgres", "redis", "github"):
            base["requires_network_access"] = True
        return base


_registry_instance: MCPServerRegistry | None = None


def get_mcp_server_registry() -> MCPServerRegistry:
    global _registry_instance
    if _registry_instance is None:
        _registry_instance = MCPServerRegistry()
    return _registry_instance


def reset_mcp_server_registry() -> None:
    global _registry_instance
    _registry_instance = None
