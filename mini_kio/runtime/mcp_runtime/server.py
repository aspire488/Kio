"""A single MCP server connection: JSON-RPC request/response correlation,
initialize handshake, notifications, cancellation, and process supervision
(restart, reconnect, schema reload, crash recovery)."""

from __future__ import annotations

import asyncio
import logging
import time
from typing import Any, Awaitable, Callable, Optional

from . import jsonrpc
from .exceptions import (
    InitializationError,
    ProtocolError,
    RequestCancelledError,
    RequestTimeoutError,
    ServerCrashedError,
    ServerNotConnectedError,
    ToolExecutionError,
)
from .transport import StdioTransport
from .types import JSONRPCNotification, JSONRPCRequest, JSONRPCResponse, ServerConfig, ServerState, ToolSchema

logger = logging.getLogger("mcp_runtime.server")

CrashHandler = Callable[[str], Awaitable[None]]
NotificationHandler = Callable[[str, dict[str, Any]], Awaitable[None]]


class _PendingRequest:
    __slots__ = ("future", "sent_at", "method")

    def __init__(self, future: asyncio.Future, method: str) -> None:
        self.future = future
        self.sent_at = time.perf_counter()
        self.method = method


class MCPServerConnection:
    """Owns one StdioTransport and the JSON-RPC session layered on it."""

    def __init__(self, config: ServerConfig) -> None:
        self._config = config
        self._transport = StdioTransport(config)
        self._transport.set_line_handler(self._handle_line)
        self._transport.set_exit_handler(self._handle_exit)

        self._id_gen = jsonrpc.IdGenerator()
        self._pending: dict[int, _PendingRequest] = {}
        self._state = ServerState.STOPPED
        self._started_at: Optional[float] = None
        self._restart_count = 0
        self._failure_count = 0
        self._last_error: Optional[str] = None
        self._latency_ewma_ms = 0.0
        self._server_capabilities: dict[str, Any] = {}
        self._crash_handlers: list[CrashHandler] = []
        self._notification_handlers: list[NotificationHandler] = []
        self._lock = asyncio.Lock()

    @property
    def server_id(self) -> str:
        return self._config.server_id

    @property
    def state(self) -> ServerState:
        return self._state

    @property
    def pending_count(self) -> int:
        return len(self._pending)

    @property
    def restart_count(self) -> int:
        return self._restart_count

    @property
    def failure_count(self) -> int:
        return self._failure_count

    @property
    def latency_ms_ewma(self) -> float:
        return self._latency_ewma_ms

    @property
    def last_error(self) -> Optional[str]:
        return self._last_error

    @property
    def uptime_s(self) -> float:
        return time.time() - self._started_at if self._started_at else 0.0

    def on_crash(self, handler: CrashHandler) -> None:
        self._crash_handlers.append(handler)

    def on_notification(self, handler: NotificationHandler) -> None:
        self._notification_handlers.append(handler)

    # -- connection lifecycle ---------------------------------------------

    async def connect(self) -> list[ToolSchema]:
        async with self._lock:
            self._state = ServerState.STARTING
            await self._transport.start()
            self._started_at = time.time()
            self._state = ServerState.INITIALIZING
            try:
                await self._initialize_handshake()
            except Exception as exc:  # noqa: BLE001
                self._state = ServerState.CRASHED
                self._last_error = str(exc)
                raise InitializationError(f"initialize handshake failed for '{self.server_id}': {exc}") from exc

            tools = await self._discover_tools()
            self._state = ServerState.READY
            return tools

    async def _initialize_handshake(self) -> None:
        params = {
            "protocolVersion": self._config.protocol_version,
            "capabilities": {},
            "clientInfo": {"name": self._config.client_name, "version": self._config.client_version},
        }
        response = await self._request("initialize", params, timeout_s=self._config.request_timeout_s)
        if response.is_error:
            raise InitializationError(jsonrpc.error_summary(response))
        result = response.result or {}
        self._server_capabilities = result.get("capabilities", {})
        await self._notify("notifications/initialized", {})

    async def _discover_tools(self) -> list[ToolSchema]:
        response = await self._request("tools/list", {}, timeout_s=self._config.request_timeout_s)
        if response.is_error:
            raise InitializationError(f"tools/list failed: {jsonrpc.error_summary(response)}")
        raw_tools = (response.result or {}).get("tools", [])
        schemas: list[ToolSchema] = []
        for entry in raw_tools:
            schemas.append(
                ToolSchema(
                    name=entry.get("name", ""),
                    description=entry.get("description", ""),
                    input_schema=entry.get("inputSchema", {}),
                )
            )
        return schemas

    async def reload_schema(self) -> list[ToolSchema]:
        if self._state != ServerState.READY:
            raise ServerNotConnectedError(f"server '{self.server_id}' is not ready (state={self._state})")
        return await self._discover_tools()

    async def disconnect(self) -> None:
        async with self._lock:
            self._state = ServerState.SHUTTING_DOWN
            try:
                if self._transport.is_running:
                    try:
                        await self._request("shutdown", {}, timeout_s=5.0)
                    except (RequestTimeoutError, ProtocolError, ServerCrashedError):
                        pass
            finally:
                await self._transport.stop()
                self._fail_all_pending("server shutting down")
                self._state = ServerState.STOPPED

    async def restart(self) -> list[ToolSchema]:
        logger.warning("restarting server '%s'", self.server_id)
        self._state = ServerState.RECONNECTING
        try:
            await self._transport.stop()
        except Exception:  # noqa: BLE001
            logger.exception("error stopping transport during restart of %s", self.server_id)
        self._fail_all_pending("server restarting")
        self._restart_count += 1
        backoff = min(self._config.restart_backoff_base_s * (2 ** (self._restart_count - 1)), 30.0)
        await asyncio.sleep(backoff)
        return await self.connect()

    async def _handle_exit(self, code: int) -> None:
        if self._state in (ServerState.SHUTTING_DOWN, ServerState.STOPPED):
            return
        logger.error("server '%s' exited unexpectedly with code %s", self.server_id, code)
        self._state = ServerState.CRASHED
        self._failure_count += 1
        self._last_error = f"process exited with code {code}"
        self._fail_all_pending(self._last_error)
        for handler in self._crash_handlers:
            try:
                await handler(self.server_id)
            except Exception:  # noqa: BLE001
                logger.exception("crash handler raised for %s", self.server_id)

    def _fail_all_pending(self, reason: str) -> None:
        for req_id, pending in list(self._pending.items()):
            if not pending.future.done():
                pending.future.set_exception(ServerCrashedError(reason))
            self._pending.pop(req_id, None)

    # -- message pump -------------------------------------------------------

    async def _handle_line(self, raw: str) -> None:
        try:
            message = jsonrpc.parse_incoming(raw)
        except ProtocolError:
            logger.warning("malformed message from server '%s': %s", self.server_id, raw[:200])
            return

        if isinstance(message, list):
            for item in message:
                await self._dispatch(item)
        else:
            await self._dispatch(message)

    async def _dispatch(self, message) -> None:
        if isinstance(message, JSONRPCResponse):
            self._resolve_response(message)
        elif isinstance(message, JSONRPCNotification):
            for handler in self._notification_handlers:
                try:
                    await handler(message.method, message.params)
                except Exception:  # noqa: BLE001
                    logger.exception("notification handler raised for %s", self.server_id)
        elif isinstance(message, JSONRPCRequest):
            logger.debug("server-initiated request '%s' ignored (no server-to-client handler configured)", message.method)

    def _resolve_response(self, response: JSONRPCResponse) -> None:
        if response.id is None:
            return
        pending = self._pending.pop(int(response.id), None) if isinstance(response.id, (int, str)) else None
        if pending is None:
            logger.debug("received response for unknown/expired request id=%s on %s", response.id, self.server_id)
            return
        latency_ms = (time.perf_counter() - pending.sent_at) * 1000
        self._latency_ewma_ms = latency_ms if self._latency_ewma_ms == 0 else (0.8 * self._latency_ewma_ms + 0.2 * latency_ms)
        if not pending.future.done():
            pending.future.set_result(response)

    # -- outgoing calls -------------------------------------------------------

    async def _request(self, method: str, params: dict[str, Any], *, timeout_s: float) -> JSONRPCResponse:
        if not self._transport.is_running and method != "initialize":
            raise ServerNotConnectedError(f"server '{self.server_id}' transport is not running")

        request_id = self._id_gen.next()
        future: asyncio.Future[JSONRPCResponse] = asyncio.get_event_loop().create_future()
        self._pending[request_id] = _PendingRequest(future, method)

        message = JSONRPCRequest(method=method, params=params, id=request_id)
        try:
            await self._transport.write(jsonrpc.serialize(message))
        except Exception:
            self._pending.pop(request_id, None)
            raise

        try:
            return await asyncio.wait_for(future, timeout=timeout_s)
        except asyncio.TimeoutError as exc:
            self._pending.pop(request_id, None)
            await self._cancel_remote(request_id)
            raise RequestTimeoutError(f"'{method}' on '{self.server_id}' timed out after {timeout_s}s") from exc
        except asyncio.CancelledError:
            self._pending.pop(request_id, None)
            raise RequestCancelledError(f"'{method}' on '{self.server_id}' was cancelled") from None

    async def _notify(self, method: str, params: dict[str, Any]) -> None:
        message = JSONRPCNotification(method=method, params=params)
        await self._transport.write(jsonrpc.serialize(message))

    async def _cancel_remote(self, request_id: int) -> None:
        try:
            await self._notify("notifications/cancelled", {"requestId": request_id})
        except Exception:  # noqa: BLE001
            logger.debug("failed to send cancellation notice to %s for request %s", self.server_id, request_id)

    async def call_tool(self, tool_name: str, arguments: dict[str, Any], *, timeout_s: float) -> JSONRPCResponse:
        if self._state != ServerState.READY:
            raise ServerNotConnectedError(f"server '{self.server_id}' is not ready (state={self._state})")
        params = {"name": tool_name, "arguments": arguments}
        response = await self._request("tools/call", params, timeout_s=timeout_s)
        return response

    @property
    def capabilities(self) -> dict[str, Any]:
        return dict(self._server_capabilities)

    @property
    def pid(self) -> Optional[int]:
        return self._transport.pid

    def recent_stderr(self) -> list[str]:
        return self._transport.recent_stderr()
