"""Typed data structures shared across mcp_runtime."""

from __future__ import annotations

import time
from dataclasses import dataclass, field
from enum import Enum
from typing import Any, Optional, Union

JSONRPCId = Union[str, int]


class ServerState(str, Enum):
    STOPPED = "stopped"
    STARTING = "starting"
    INITIALIZING = "initializing"
    READY = "ready"
    RECONNECTING = "reconnecting"
    CRASHED = "crashed"
    SHUTTING_DOWN = "shutting_down"


@dataclass(slots=True)
class ServerConfig:
    server_id: str
    command: str
    args: list[str] = field(default_factory=list)
    env: dict[str, str] = field(default_factory=dict)
    cwd: Optional[str] = None
    request_timeout_s: float = 30.0
    max_restart_attempts: int = 3
    restart_backoff_base_s: float = 1.0
    health_check_interval_s: float = 15.0
    client_name: str = "mcp_runtime"
    client_version: str = "1.0.0"
    protocol_version: str = "2024-11-05"


@dataclass(slots=True)
class ToolSchema:
    name: str
    description: str = ""
    input_schema: dict[str, Any] = field(default_factory=dict)


@dataclass(slots=True)
class ToolDescriptor:
    server_id: str
    schema: ToolSchema
    version: str = "unknown"
    permissions: list[str] = field(default_factory=list)
    healthy: bool = True
    registered_at: float = field(default_factory=time.time)

    @property
    def qualified_name(self) -> str:
        return f"{self.server_id}::{self.schema.name}"


@dataclass(slots=True)
class ToolCallRequest:
    tool_name: str
    server_id: Optional[str] = None
    arguments: dict[str, Any] = field(default_factory=dict)
    timeout_s: Optional[float] = None
    max_retries: int = 0
    idempotency_key: Optional[str] = None


@dataclass(slots=True)
class ToolCallResult:
    success: bool
    tool_name: str
    server_id: str
    content: Any = None
    error: Optional[str] = None
    duration_ms: float = 0.0
    attempts: int = 1
    is_error: bool = False


@dataclass(slots=True)
class ServerHealth:
    server_id: str
    state: ServerState
    uptime_s: float
    latency_ms_ewma: float
    pending_requests: int
    restart_count: int
    failure_count: int
    last_error: Optional[str] = None
    checked_at: float = field(default_factory=time.time)


@dataclass(slots=True)
class JSONRPCRequest:
    method: str
    params: dict[str, Any] = field(default_factory=dict)
    id: Optional[JSONRPCId] = None
    jsonrpc: str = "2.0"

    def to_dict(self) -> dict[str, Any]:
        d: dict[str, Any] = {"jsonrpc": self.jsonrpc, "method": self.method}
        if self.params:
            d["params"] = self.params
        if self.id is not None:
            d["id"] = self.id
        return d


@dataclass(slots=True)
class JSONRPCResponse:
    id: Optional[JSONRPCId]
    result: Any = None
    error: Optional[dict[str, Any]] = None
    jsonrpc: str = "2.0"

    @property
    def is_error(self) -> bool:
        return self.error is not None


@dataclass(slots=True)
class JSONRPCNotification:
    method: str
    params: dict[str, Any] = field(default_factory=dict)
    jsonrpc: str = "2.0"

    def to_dict(self) -> dict[str, Any]:
        d: dict[str, Any] = {"jsonrpc": self.jsonrpc, "method": self.method}
        if self.params:
            d["params"] = self.params
        return d
