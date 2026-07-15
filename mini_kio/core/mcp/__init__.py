"""MCP Foundation — Client, registry, provider, and local MCP server implementations."""

from mini_kio.core.mcp.client import MCPClient
from mini_kio.core.mcp.registry import MCPServerRegistry
from mini_kio.core.mcp.provider import MCPExecutionProvider


def register_all_mcp_servers() -> None:
    from mini_kio.core.provider_registry import get_provider_registry
    registry = get_provider_registry()
    server_registry = MCPServerRegistry()
    client = MCPClient(server_registry, execute_timeout_s=15.0)
    server_registry.discover()
    client.start()
    local_servers = ("filesystem", "git", "terminal", "sqlite")
    external_servers = ("docker", "github", "postgres", "redis")
    for server_type in local_servers + external_servers:
        try:
            provider = MCPExecutionProvider(server_type, client, server_registry)
            provider._refresh_capabilities()
            registry.register(provider)
        except Exception as exc:
            import logging
            logging.getLogger(__name__).warning(
                "Failed to register MCP provider %s: %s", server_type, exc
            )


__all__ = ["MCPClient", "MCPServerRegistry", "MCPExecutionProvider", "register_all_mcp_servers"]
