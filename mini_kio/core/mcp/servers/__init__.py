"""MCP server implementations — each runs as a stdio subprocess serving JSON-RPC 2.0.

Local servers (auto-registered): filesystem, git, terminal, sqlite
External servers (auto-registered if available): docker, github, postgres, redis
"""

_SERVER_MODULES: dict[str, str] = {
    "filesystem": "mini_kio.core.mcp.servers.mcp_filesystem_server",
    "git": "mini_kio.core.mcp.servers.mcp_git_server",
    "terminal": "mini_kio.core.mcp.servers.mcp_terminal_server",
    "sqlite": "mini_kio.core.mcp.servers.mcp_sqlite_server",
    "docker": "mini_kio.core.mcp.servers.mcp_docker_server",
    "github": "mini_kio.core.mcp.servers.mcp_github_server",
    "postgres": "mini_kio.core.mcp.servers.mcp_postgres_server",
    "redis": "mini_kio.core.mcp.servers.mcp_redis_server",
}

_SERVER_ARGS: dict[str, list[str]] = {
    "filesystem": [],
    "git": [],
    "terminal": [],
    "sqlite": [],
    "docker": [],
    "github": [],
    "postgres": [],
    "redis": [],
}


def get_server_module(server_type: str) -> str | None:
    return _SERVER_MODULES.get(server_type)


def get_server_args(server_type: str) -> list[str]:
    return _SERVER_ARGS.get(server_type, [])


def list_servers() -> list[str]:
    return list(_SERVER_MODULES.keys())
