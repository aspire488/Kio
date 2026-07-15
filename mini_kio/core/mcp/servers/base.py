"""BaseMCPServer — stdin/stdout JSON-RPC 2.0 event loop for subprocess MCP servers."""

from __future__ import annotations

import json
import logging
import sys
import traceback
from typing import Any, Callable

logger = logging.getLogger(__name__)


class BaseMCPServer:
    """Base class for MCP servers running over stdin/stdout JSON-RPC 2.0."""

    def __init__(self, server_type: str, display_name: str, version: str = "1.0.0") -> None:
        self.server_type = server_type
        self.display_name = display_name
        self.version = version
        self._tools: dict[str, dict[str, Any]] = {}
        self._handlers: dict[str, Callable[..., dict[str, Any]]] = {}
        self._metadata: dict[str, Any] = {}

    def register_tool(self, name: str, handler: Callable[..., dict[str, Any]], params: dict[str, Any] | None = None) -> None:
        self._tools[name] = {"name": name, "params": params or {}}
        self._handlers[name] = handler

    def get_metadata(self) -> dict[str, Any]:
        return {"server_type": self.server_type, "display_name": self.display_name, "version": self.version,
                "tools_count": len(self._tools), **self._metadata}

    def run(self) -> None:
        """Main event loop: read JSON-RPC requests from stdin, write responses to stdout."""
        for line in sys.stdin:
            line = line.strip()
            if not line:
                continue
            try:
                request = json.loads(line)
                response = self._handle_request(request)
            except json.JSONDecodeError:
                response = self._error_response(None, -32700, "Parse error")
            except Exception as exc:
                response = self._error_response(None, -32603, f"Internal error: {exc}")
            sys.stdout.write(json.dumps(response) + "\n")
            sys.stdout.flush()

    def initialize(self, params: dict[str, Any]) -> dict[str, Any]:
        self._metadata.update(params.get("metadata", {}))
        return {"status": "ok", "metadata": self.get_metadata(), "tools": list(self._tools.values())}

    def health(self) -> dict[str, Any]:
        return {"status": "healthy", "server_type": self.server_type, "uptime_s": 0,
                "tools_count": len(self._tools)}

    def shutdown(self) -> dict[str, Any]:
        sys.exit(0)

    def _handle_request(self, request: dict[str, Any]) -> dict[str, Any]:
        req_id = request.get("id")
        method = request.get("method", "")
        params = request.get("params", {})
        if method == "initialize":
            return self._success_response(req_id, self.initialize(params))
        elif method == "health":
            return self._success_response(req_id, self.health())
        elif method == "shutdown":
            result = self.shutdown()
            return self._success_response(req_id, result)
        elif method in self._handlers:
            try:
                result = self._handlers[method](**params)
                return self._success_response(req_id, result)
            except Exception as exc:
                logger.error("Tool %s failed: %s\n%s", method, exc, traceback.format_exc())
                return self._error_response(req_id, -32000, str(exc))
        else:
            return self._error_response(req_id, -32601, f"Method not found: {method}")

    def _success_response(self, req_id: Any, result: dict[str, Any]) -> dict[str, Any]:
        return {"jsonrpc": "2.0", "id": req_id, "result": result}

    def _error_response(self, req_id: Any, code: int, message: str) -> dict[str, Any]:
        return {"jsonrpc": "2.0", "id": req_id, "error": {"code": code, "message": message}}
