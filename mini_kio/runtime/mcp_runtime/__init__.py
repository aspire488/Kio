"""mcp_runtime -- standalone, integration-ready Model Context Protocol runtime.

Exposes MCPRuntime as the primary facade for managing multiple concurrent
MCP servers over stdio JSON-RPC 2.0. Sub-components (MCPServerConnection,
ToolRegistry, ToolExecutor, HealthMonitor, StdioTransport) are
independently importable.
"""

from . import jsonrpc
from .executor import ToolExecutor, validate_arguments
from .exceptions import (
    InitializationError,
    MCPRuntimeError,
    ProtocolError,
    RequestCancelledError,
    RequestTimeoutError,
    ServerCrashedError,
    ServerNotConnectedError,
    ServerStartError,
    ToolExecutionError,
    ToolNotFoundError,
    ToolPermissionError,
    ToolValidationError,
    TransportError,
)
from .health import HealthMonitor
from .logging_utils import configure_logging, log_with_fields
from .registry import ToolRegistry
from .runtime import MCPRuntime
from .server import MCPServerConnection
from .transport import StdioTransport
from .types import (
    JSONRPCNotification,
    JSONRPCRequest,
    JSONRPCResponse,
    ServerConfig,
    ServerHealth,
    ServerState,
    ToolCallRequest,
    ToolCallResult,
    ToolDescriptor,
    ToolSchema,
)

__all__ = [
    "MCPRuntime",
    "MCPServerConnection",
    "ToolRegistry",
    "ToolExecutor",
    "HealthMonitor",
    "StdioTransport",
    "validate_arguments",
    "configure_logging",
    "log_with_fields",
    "jsonrpc",
    "ServerConfig",
    "ServerHealth",
    "ServerState",
    "ToolSchema",
    "ToolDescriptor",
    "ToolCallRequest",
    "ToolCallResult",
    "JSONRPCRequest",
    "JSONRPCResponse",
    "JSONRPCNotification",
    "MCPRuntimeError",
    "TransportError",
    "ServerStartError",
    "ServerCrashedError",
    "ProtocolError",
    "RequestTimeoutError",
    "RequestCancelledError",
    "ToolNotFoundError",
    "ToolValidationError",
    "ToolExecutionError",
    "ToolPermissionError",
    "ServerNotConnectedError",
    "InitializationError",
]

__version__ = "1.0.0"
