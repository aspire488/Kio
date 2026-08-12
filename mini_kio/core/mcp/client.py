"""MCPClient — JSON-RPC 2.0 over stdio with lifecycle, streaming, timeouts, and retry."""

from __future__ import annotations

import json
import logging
import os
import subprocess
import sys
import threading
import time
from typing import Any, Callable

from mini_kio.core.mcp.registry import MCPServerRegistry, MCPServerInfo

logger = logging.getLogger(__name__)

_MCP_DISCOVERY_TIMEOUT_S = 5.0
_MCP_EXECUTE_TIMEOUT_S = 30.0
_MCP_RECONNECT_MAX_ATTEMPTS = 3
_MCP_RESPONSE_TIMEOUT_S = 10.0
_STREAM_CHUNK_TIMEOUT_S = 5.0
_JSONRPC_VERSION = "2.0"

_CAPABILITY_PREFIX_MAP: dict[str, str] = {
    "filesystem": "fs", "git": "git", "terminal": "cmd", "sqlite": "sql",
}

_id_counter: int = 0
_id_lock = threading.Lock()


def _next_id() -> int:
    global _id_counter
    with _id_lock:
        _id_counter += 1
        return _id_counter


def _make_capability_name(server_type: str, tool_name: str) -> str:
    prefix = _CAPABILITY_PREFIX_MAP.get(server_type, server_type)
    return f"{prefix}_{tool_name}"


def _make_request(method: str, params: dict[str, Any] | None = None) -> dict[str, Any]:
    return {"jsonrpc": _JSONRPC_VERSION, "id": _next_id(), "method": method, "params": params or {}}


class MCPError(Exception):
    pass

class MCPConnectionError(MCPError):
    pass

class MCPTimeoutError(MCPError):
    pass

class MCPCancelledError(MCPError):
    pass

class MCPExecutionError(MCPError):
    pass


class _PendingResponse:
    __slots__ = ("event", "holder")
    def __init__(self, event: threading.Event, holder: dict[str, Any]) -> None:
        self.event = event
        self.holder = holder


class _ServerConnection:
    __slots__ = ("proc", "stdout_thread", "response_queue", "shutdown_event", "stdout_lock")
    def __init__(self, proc: subprocess.Popen[str] | None, stdout_thread: threading.Thread | None,
                 response_queue: dict[int, _PendingResponse] | None, shutdown_event: threading.Event) -> None:
        self.proc = proc
        self.stdout_thread = stdout_thread
        self.response_queue = response_queue if response_queue is not None else {}
        self.shutdown_event = shutdown_event
        self.stdout_lock = threading.Lock()


class MCPClient:
    """Thread-safe MCP client. Manages subprocess connections via JSON-RPC over stdio."""

    def __init__(self, server_registry: MCPServerRegistry,
                 discovery_timeout_s: float = _MCP_DISCOVERY_TIMEOUT_S,
                 execute_timeout_s: float = _MCP_EXECUTE_TIMEOUT_S) -> None:
        self._registry = server_registry
        self._discovery_timeout_s = discovery_timeout_s
        self._execute_timeout_s = execute_timeout_s
        self._connections: dict[str, _ServerConnection] = {}
        self._capability_cache: dict[str, tuple[str, str, dict[str, Any]]] = {}
        self._lock = threading.Lock()
        self._closed = False

    def start(self) -> None:
        """Begin MCP server connections WITHOUT blocking the caller.

        Each server handshake (subprocess spawn + JSON-RPC initialize +
        tools/list) can take up to the discovery timeout, and a cold
        Windows boot can stretch a serialized run of all servers well past
        a minute. Every connect now runs on its own daemon thread so KIO's
        bootstrap and the deterministic local command path are never
        blocked waiting on optional MCP infrastructure. Connections are
        recorded on success; tools resolve lazily as each server becomes
        ready, and a tool call against a not-yet-connected server fails
        truthfully (MCPConnectionError) instead of blocking or guessing.
        """
        for info in self._registry.list_servers():
            threading.Thread(
                target=self._connect,
                args=(info,),
                daemon=True,
                name=f"kio-mcp-connect-{info.server_type}",
            ).start()

    def stop(self) -> None:
        with self._lock:
            self._closed = True
            for server_type, conn in list(self._connections.items()):
                self._disconnect(conn, server_type)

    def restart(self, server_type: str) -> bool:
        with self._lock:
            conn = self._connections.get(server_type)
            if conn is not None:
                self._disconnect(conn, server_type)
            info = self._registry.get_server(server_type)
            return self._connect(info) is not None if info else False

    def is_connected(self, server_type: str) -> bool:
        return server_type in self._connections

    def discover_capabilities(self, server_type: str) -> list[dict[str, Any]]:
        conn = self._connections.get(server_type)
        if conn is None:
            raise MCPConnectionError(f"Server not connected: {server_type}")
        try:
            result = self._send_request(conn, "discover", {}, timeout=self._discovery_timeout_s)
            tools = result.get("tools", [])
            with self._lock:
                for tool in tools:
                    cap_name = _make_capability_name(server_type, tool["name"])
                    self._capability_cache[cap_name] = (server_type, tool["name"], tool.get("params", {}))
                    self._registry.map_tool_to_capability(server_type, tool["name"], cap_name)
            return tools
        except Exception as exc:
            logger.warning("MCP discover %s failed: %s", server_type, exc)
            return []

    def all_discovered_capabilities(self) -> dict[str, Any]:
        result = {}
        with self._lock:
            for cap_name, (server_type, tool_name, _) in self._capability_cache.items():
                info = self._registry.get_server(server_type)
                result[cap_name] = {"server_type": server_type, "tool_name": tool_name,
                                    "server_metadata": info.metadata if info else {}}
        return result

    def capability_metadata(self, capability_name: str) -> dict[str, Any] | None:
        with self._lock:
            entry = self._capability_cache.get(capability_name)
            if entry is None:
                return None
            server_type, tool_name, params_schema = entry
            info = self._registry.get_server(server_type)
            return {"server_type": server_type, "tool_name": tool_name,
                    "params_schema": params_schema, "server_metadata": info.metadata if info else {}}

    def execute_tool(self, server_type: str, tool_name: str, params: dict[str, Any] | None = None,
                     *, timeout_s: float | None = None, on_stream: Callable[[dict[str, Any]], None] | None = None,
                     cancel_token: Any = None) -> dict[str, Any]:
        conn = self._connections.get(server_type)
        if conn is None:
            raise MCPConnectionError(f"Server not connected: {server_type}")
        timeout = timeout_s if timeout_s is not None else self._execute_timeout_s
        return self._execute_sync(conn, tool_name, params or {}, timeout, cancel_token)

    def check_health(self, server_type: str) -> dict[str, Any]:
        conn = self._connections.get(server_type)
        if conn is None:
            return {"status": "offline", "server_type": server_type}
        try:
            result = self._send_request(conn, "health", {}, timeout=5.0)
            return {"status": result.get("status", "healthy"), "server_type": server_type,
                    "uptime_s": result.get("uptime_s", -1), "tools_count": result.get("tools_count", -1)}
        except Exception as exc:
            return {"status": "unhealthy", "server_type": server_type, "error": str(exc)}

    def _connect(self, info: MCPServerInfo) -> _ServerConnection | None:
        try:
            server_script = self._resolve_server_script(info.server_type)
            if server_script is None:
                logger.warning("No MCP server script for %s", info.server_type)
                return None
            project_root = os.path.dirname(os.path.dirname(os.path.dirname(os.path.dirname(os.path.dirname(server_script)))))
            env = {**os.environ, "PYTHONUNBUFFERED": "1"}
            existing_path = env.get("PYTHONPATH", "")
            if project_root not in existing_path.split(os.pathsep):
                env["PYTHONPATH"] = project_root + (os.pathsep + existing_path if existing_path else "")
            proc = subprocess.Popen(
                [sys.executable, server_script], stdin=subprocess.PIPE, stdout=subprocess.PIPE,
                stderr=subprocess.PIPE, text=True, cwd=info.working_dir or os.getcwd(),
                env=env,
            )
            conn = _ServerConnection(proc=proc, stdout_thread=None, response_queue=None,
                                      shutdown_event=threading.Event())
            response_queue: dict[int, _PendingResponse] = {}

            def _reader() -> None:
                buf = ""
                while not conn.shutdown_event.is_set():
                    try:
                        line = proc.stdout.readline() if proc.stdout else ""
                        if not line:
                            break
                        buf += line
                        while "\n" in buf:
                            line, buf = buf.split("\n", 1)
                            line = line.strip()
                            if not line:
                                continue
                            try:
                                msg = json.loads(line)
                                self._dispatch_response(msg, response_queue)
                            except json.JSONDecodeError:
                                pass
                    except Exception:
                        break

            conn.stdout_thread = threading.Thread(target=_reader, daemon=True)
            conn.response_queue = response_queue
            conn.stdout_thread.start()

            init_result = self._send_request(conn, "initialize",
                                             {"server_type": info.server_type, "metadata": info.metadata},
                                             timeout=self._discovery_timeout_s)
            info.state = "connected"
            info.metadata.update(init_result.get("metadata", {}))
            info.metadata.update({"pid": proc.pid, "connected_at": time.time()})

            discovered_tools = init_result.get("tools", [])
            self._registry.update_server_tools(info.server_type, discovered_tools)
            for tool in discovered_tools:
                cap_name = _make_capability_name(info.server_type, tool["name"])
                self._capability_cache[cap_name] = (info.server_type, tool["name"], tool.get("params", {}))
                self._registry.map_tool_to_capability(info.server_type, tool["name"], cap_name)

            with self._lock:
                self._connections[info.server_type] = conn
            return conn
        except Exception as exc:
            logger.warning("MCP connection failed for %s: %s", info.server_type, exc)
            self._registry.update_server_state(info.server_type, "error", str(exc))
            return None

    def _disconnect(self, conn: _ServerConnection, server_type: str) -> None:
        conn.shutdown_event.set()
        try:
            req = _make_request("shutdown", {})
            if conn.proc and conn.proc.stdin:
                conn.proc.stdin.write(json.dumps(req) + "\n")
                conn.proc.stdin.flush()
        except Exception:
            pass
        if conn.proc and conn.proc.poll() is None:
            conn.proc.terminate()
            try:
                conn.proc.wait(timeout=3)
            except subprocess.TimeoutExpired:
                conn.proc.kill()
        self._connections.pop(server_type, None)
        self._registry.update_server_state(server_type, "disconnected")

    def _resolve_server_script(self, server_type: str) -> str | None:
        pkg_dir = os.path.dirname(os.path.abspath(__file__))
        script = os.path.join(pkg_dir, "servers", f"mcp_{server_type}_server.py")
        return script if os.path.isfile(script) else None

    def _send_request(self, conn: _ServerConnection, method: str, params: dict[str, Any], timeout: float) -> dict[str, Any]:
        req = _make_request(method, params)
        req_id = req["id"]
        event = threading.Event()
        holder: dict[str, Any] = {"result": None, "error": None}
        with conn.stdout_lock:
            conn.response_queue[req_id] = _PendingResponse(event, holder)
        try:
            if conn.proc and conn.proc.stdin:
                conn.proc.stdin.write(json.dumps(req) + "\n")
                conn.proc.stdin.flush()
            if not event.wait(timeout=timeout):
                with conn.stdout_lock:
                    conn.response_queue.pop(req_id, None)
                raise MCPTimeoutError(f"MCP request '{method}' timed out after {timeout}s")
        except BrokenPipeError:
            raise MCPConnectionError(f"Server pipe broken for method '{method}'")
        if holder["error"]:
            err = holder["error"]
            raise MCPExecutionError(f"MCP error (code={err.get('code', -1)}): {err.get('message', 'unknown')}")
        return holder["result"] or {}

    def _execute_sync(self, conn: _ServerConnection, tool_name: str, params: dict[str, Any],
                      timeout: float, cancel_token: Any) -> dict[str, Any]:
        start = time.monotonic()
        while True:
            elapsed = time.monotonic() - start
            remaining = timeout - elapsed
            if remaining <= 0:
                raise MCPTimeoutError(f"Tool '{tool_name}' timed out after {timeout}s")
            if cancel_token is not None:
                try:
                    if callable(cancel_token) and cancel_token():
                        raise MCPCancelledError(f"Tool '{tool_name}' cancelled")
                except MCPCancelledError:
                    raise
                except Exception:
                    pass
            try:
                return self._send_request(conn, tool_name, params, min(remaining, 2.0))
            except MCPTimeoutError:
                continue

    def _dispatch_response(self, msg: dict[str, Any], response_queue: dict[int, _PendingResponse]) -> None:
        msg_id = msg.get("id")
        if msg_id is None:
            return
        pending = response_queue.pop(msg_id, None)
        if pending is None:
            return
        if "error" in msg:
            pending.holder["error"] = msg["error"]
        else:
            pending.holder["result"] = msg.get("result", {})
        pending.event.set()
