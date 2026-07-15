"""JSON-RPC 2.0 message construction and parsing, including batch support."""

from __future__ import annotations

import itertools
import json
from typing import Any, Union

from .exceptions import ProtocolError
from .types import JSONRPCNotification, JSONRPCRequest, JSONRPCResponse

Message = Union[JSONRPCRequest, JSONRPCNotification]

_PARSE_ERROR = -32700
_INVALID_REQUEST = -32600
_METHOD_NOT_FOUND = -32601
_INVALID_PARAMS = -32602
_INTERNAL_ERROR = -32603


class IdGenerator:
    """Thread-unsafe (single event loop) monotonic id generator."""

    def __init__(self) -> None:
        self._counter = itertools.count(1)

    def next(self) -> int:
        return next(self._counter)


def serialize(message: Message | list[Message]) -> str:
    if isinstance(message, list):
        return json.dumps([m.to_dict() for m in message], separators=(",", ":"))
    return json.dumps(message.to_dict(), separators=(",", ":"))


def parse_incoming(raw: str) -> Union[JSONRPCResponse, JSONRPCRequest, JSONRPCNotification, list]:
    """Parses a single JSON-RPC line into the appropriate typed object.
    Handles requests, notifications, responses (success or error), and
    batches (a JSON array of any mixture of the above)."""
    try:
        data = json.loads(raw)
    except json.JSONDecodeError as exc:
        raise ProtocolError(f"invalid JSON: {exc}") from exc

    if isinstance(data, list):
        if not data:
            raise ProtocolError("empty batch")
        return [_parse_object(item) for item in data]

    if not isinstance(data, dict):
        raise ProtocolError(f"expected object or array at top level, got {type(data).__name__}")

    return _parse_object(data)


def _parse_object(data: dict[str, Any]) -> Union[JSONRPCResponse, JSONRPCRequest, JSONRPCNotification]:
    if not isinstance(data, dict):
        raise ProtocolError(f"batch item must be an object, got {type(data).__name__}")

    if data.get("jsonrpc") != "2.0":
        raise ProtocolError(f"unsupported or missing jsonrpc version: {data.get('jsonrpc')!r}")

    has_result = "result" in data
    has_error = "error" in data
    has_method = "method" in data

    if has_result or has_error:
        return JSONRPCResponse(id=data.get("id"), result=data.get("result"), error=data.get("error"))

    if has_method:
        method = data["method"]
        params = data.get("params", {}) or {}
        if "id" in data:
            return JSONRPCRequest(method=method, params=params, id=data["id"])
        return JSONRPCNotification(method=method, params=params)

    raise ProtocolError(f"message is neither request, notification, nor response: {data!r}")


def make_error_dict(code: int, message: str, data: Any = None) -> dict[str, Any]:
    err: dict[str, Any] = {"code": code, "message": message}
    if data is not None:
        err["data"] = data
    return err


def error_summary(response: JSONRPCResponse) -> str:
    if not response.is_error or response.error is None:
        return ""
    code = response.error.get("code", "?")
    message = response.error.get("message", "unknown error")
    return f"[{code}] {message}"
