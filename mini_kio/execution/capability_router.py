"""CapabilityRouter — Authoritative backend selector for KIO execution fabric.

Selects the best execution backend for a given capability based on
availability, health, and capability matching. Eliminates duplicated
routing logic scattered across command_router.py and operators.

Backend priority per capability type:
  browser_* → BrowserRuntime > BrowserConnector > MCP > webbrowser
  open_*    → DesktopProvider > MCP
  fs_*      → MCP (FilesystemServer)
  git_*     → MCP (GitServer)
  cmd_*     → TerminalProvider > MCP (TerminalServer)
  sql_*     → MCP (SQLiteServer)
  media_*   → MediaManager (hardware)
  system_*  → SystemProvider
"""

from __future__ import annotations

import logging
from typing import Any

from mini_kio.core.provider_registry import get_provider_registry
from mini_kio.core.execution_boundary import execute_action, classify_action

logger = logging.getLogger(__name__)


class CapabilityRouter:
    """Singleton authoritative backend selector.
    
    Resolves the best backend for a capability and delegates execution.
    """

    _instance: CapabilityRouter | None = None

    def __new__(cls) -> CapabilityRouter:
        if cls._instance is None:
            cls._instance = super().__new__(cls)
        return cls._instance

    def resolve(self, action: str, target: str = "") -> dict[str, Any]:
        """Resolve and execute an action through the best available backend.
        
        1. Determines capability category from action name
        2. Queries ProviderRegistry for matching provider
        3. Routes to best backend
        4. Returns normalized execution result
        """
        category = classify_action(action)
        registry = get_provider_registry()

        # 1. Check ProviderRegistry for direct capability match
        provider = registry.get_provider(action)
        if provider is not None and provider.health().value in ("healthy", "degraded"):
            return execute_action(action, target)

        # 2. Check for MCP-backed capabilities
        if action.startswith(("fs_", "git_", "cmd_", "sql_")):
            mcp_provider = registry.get_provider_by_id(f"mcp_{action.split('_')[0]}")
            if mcp_provider is not None:
                return execute_action(action, target)

        # 3. Category-based fallback routing
        if category == "mcp_filesystem":
            return execute_action(action, target)
        elif category == "mcp_git":
            return execute_action(action, target)
        elif category == "mcp_terminal":
            return execute_action(action, target)
        elif category == "mcp_sqlite":
            return execute_action(action, target)

        # 4. Direct execute_action fallback — let execution_boundary resolve
        return execute_action(action, target)

    def best_backend(self, capability: str) -> dict[str, Any]:
        """Return metadata about the best backend for a capability without executing."""
        registry = get_provider_registry()
        provider = registry.get_provider(capability)
        if provider is not None:
            return {
                "provider": provider.id(),
                "health": provider.health().value,
                "capabilities": [c.name for c in provider.capabilities()],
                "available": True,
            }
        return {
            "provider": None,
            "health": "unavailable",
            "capabilities": [],
            "available": False,
        }

    def all_backends(self) -> dict[str, list[dict[str, Any]]]:
        """Return all available backends with their capabilities."""
        registry = get_provider_registry()
        backends: dict[str, list[dict[str, Any]]] = {}
        for provider in registry.all_providers():
            backends[provider.id()] = [
                {
                    "name": c.name,
                    "category": c.category,
                    "timeout_s": c.timeout_s,
                }
                for c in provider.capabilities()
            ]
        return backends


def get_capability_router() -> CapabilityRouter:
    return CapabilityRouter()


def reset_capability_router() -> None:
    CapabilityRouter._instance = None
