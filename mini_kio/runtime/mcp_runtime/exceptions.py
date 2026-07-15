"""Exception hierarchy for mcp_runtime."""

from __future__ import annotations


class MCPRuntimeError(Exception):
    """Base exception for all mcp_runtime errors."""


class TransportError(MCPRuntimeError):
    """Raised for transport-level (process/pipe) failures."""


class ServerStartError(TransportError):
    """Raised when an MCP server process fails to start."""


class ServerCrashedError(TransportError):
    """Raised when an MCP server process exits unexpectedly."""


class ProtocolError(MCPRuntimeError):
    """Raised for malformed JSON-RPC messages."""


class RequestTimeoutError(MCPRuntimeError):
    """Raised when a JSON-RPC request does not receive a response in time."""


class RequestCancelledError(MCPRuntimeError):
    """Raised when a pending request is cancelled before completion."""


class ToolNotFoundError(MCPRuntimeError):
    """Raised when a requested tool is not present in the registry."""


class ToolValidationError(MCPRuntimeError):
    """Raised when tool call parameters fail schema validation."""


class ToolExecutionError(MCPRuntimeError):
    """Raised when a tool call returns a JSON-RPC error response."""


class ToolPermissionError(MCPRuntimeError):
    """Raised when a tool call is blocked by permission policy."""


class ServerNotConnectedError(MCPRuntimeError):
    """Raised when an operation targets a server that is not connected."""


class InitializationError(MCPRuntimeError):
    """Raised when the MCP initialize handshake fails."""
