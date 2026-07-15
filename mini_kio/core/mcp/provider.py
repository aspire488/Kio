"""MCPExecutionProvider — wraps an MCP server as an ExecutionProvider."""

from __future__ import annotations

import logging
import time
from typing import Any

from mini_kio.core.provider_contract import ExecutionProvider, ProviderHealth, ProviderCapability
from mini_kio.core.mcp.client import MCPClient, MCPConnectionError, MCPTimeoutError, MCPCancelledError, MCPExecutionError, _make_capability_name
from mini_kio.core.mcp.registry import MCPServerRegistry

logger = logging.getLogger(__name__)


class MCPExecutionProvider(ExecutionProvider):
    def __init__(self, server_type: str, client: MCPClient, registry: MCPServerRegistry) -> None:
        self._server_type = server_type
        self._client = client
        self._registry = registry
        self._capabilities: list[ProviderCapability] = []
        self._health = ProviderHealth.OFFLINE
        self._last_health_check: float = 0

    def id(self) -> str:
        return f"mcp_{self._server_type}"

    def capabilities(self) -> list[ProviderCapability]:
        return self._refresh_capabilities()

    def health(self) -> ProviderHealth:
        now = time.time()
        if now - self._last_health_check > 15.0:
            self._refresh_health()
        return self._health

    def execute(self, action: str, target: str, **kwargs: Any) -> dict[str, Any]:
        info = self._registry.resolve_capability(action)
        if info is None:
            return {"success": False, "message": f"MCPProvider({self._server_type}): unknown capability '{action}'"}
        tool_name = info["tool_name"]
        param_key = self._resolve_target_param(action, tool_name)
        params = {param_key: target, **kwargs}
        try:
            result = self._client.execute_tool(self._server_type, tool_name, params,
                                                timeout_s=kwargs.get("timeout_s"),
                                                cancel_token=kwargs.get("cancel_token"),
                                                on_stream=kwargs.get("on_stream"))
            result.setdefault("data", result)
            ret = {"success": True, "message": result.get("message", ""),
                    "data": result.get("data"), "action": action, "target": target,
                    "tool": tool_name, "server_type": self._server_type}
            try:
                from mini_kio.execution.observations import get_observation_stream
                get_observation_stream().mcp_tool(self._server_type, tool_name, ret)
            except Exception:
                pass
            return ret
        except MCPTimeoutError as exc:
            ret = {"success": False, "message": str(exc), "action": action, "target": target, "failure_class": "timeout"}
            self._emit_mcp_observation(action, tool_name, ret)
            return ret
        except MCPCancelledError as exc:
            ret = {"success": False, "message": str(exc), "action": action, "target": target, "failure_class": "cancelled"}
            self._emit_mcp_observation(action, tool_name, ret)
            return ret
        except (MCPConnectionError, MCPExecutionError) as exc:
            ret = {"success": False, "message": str(exc), "action": action, "target": target, "failure_class": "mcp_error"}
            self._emit_mcp_observation(action, tool_name, ret)
            return ret

    def verify(self, action: str, result: dict[str, Any]) -> dict[str, Any]:
        result.setdefault("probe_used", "mcp_verify")
        if result.get("success"):
            result.setdefault("verification_status", "passed")
            result.setdefault("outcome_class", "SUCCESS")
        else:
            result.setdefault("verification_status", "failed")
            result.setdefault("outcome_class", "FAILURE")
        return result

    def cancel(self, execution_id: str) -> dict[str, Any]:
        return {"success": True, "message": f"Cancelled {execution_id}"}

    def permissions(self) -> dict[str, Any]:
        return self._registry.get_permissions(self._server_type)

    def _resolve_target_param(self, action: str, tool_name: str) -> str:
        if self._server_type == "terminal":
            return "command"
        if self._server_type == "git" and tool_name == "clone":
            return "url"
        meta = self._client.capability_metadata(action)
        if meta and meta.get("params_schema"):
            for p in ("path", "command", "sql", "url", "executable", "query"):
                if p in meta["params_schema"]:
                    return p
        return "path"

    def _refresh_capabilities(self) -> list[ProviderCapability]:
        info = self._registry.get_server(self._server_type)
        if info is None:
            return self._capabilities
        tools = info.tools
        new_caps: list[ProviderCapability] = []
        for tool in tools:
            cap_name = _make_capability_name(self._server_type, tool["name"])
            new_caps.append(ProviderCapability(name=cap_name, category=f"mcp_{self._server_type}"))
        if not new_caps:
            for cap_name, cap_info in self._registry.all_capabilities().items():
                if cap_info.get("server_type") == self._server_type:
                    new_caps.append(ProviderCapability(name=cap_name, category=f"mcp_{self._server_type}"))
        self._capabilities = new_caps
        return self._capabilities

    def _emit_mcp_observation(self, action: str, tool_name: str, result: dict[str, Any]) -> None:
        try:
            from mini_kio.execution.observations import get_observation_stream
            get_observation_stream().mcp_tool(self._server_type, tool_name, result)
        except Exception:
            pass

    def _refresh_health(self) -> None:
        self._last_health_check = time.time()
        try:
            health = self._client.check_health(self._server_type)
            s = health.get("status", "unhealthy")
            self._health = ProviderHealth.HEALTHY if s == "healthy" else ProviderHealth.DEGRADED if s == "degraded" else ProviderHealth.OFFLINE
        except Exception:
            self._health = ProviderHealth.OFFLINE
