"""Tool execution: schema validation, retries, parallel calls, cancellation,
timeout -- sitting on top of the registry and per-server connections."""

from __future__ import annotations

import asyncio
import logging
import time
from typing import Any

from . import jsonrpc
from .exceptions import ToolExecutionError, ToolNotFoundError, ToolValidationError
from .registry import ToolRegistry
from .types import ToolCallRequest, ToolCallResult, ToolSchema

logger = logging.getLogger("mcp_runtime.executor")

# Minimal JSON-Schema-subset validator: enough to catch missing required
# fields and gross type mismatches without pulling in a third-party lib.
_TYPE_MAP = {
    "string": str,
    "number": (int, float),
    "integer": int,
    "boolean": bool,
    "object": dict,
    "array": list,
}


def validate_arguments(schema: ToolSchema, arguments: dict[str, Any]) -> list[str]:
    errors: list[str] = []
    props: dict[str, Any] = schema.input_schema.get("properties", {}) if schema.input_schema else {}
    required: list[str] = schema.input_schema.get("required", []) if schema.input_schema else []

    for field_name in required:
        if field_name not in arguments:
            errors.append(f"missing required argument '{field_name}'")

    for key, value in arguments.items():
        prop_schema = props.get(key)
        if prop_schema is None:
            continue
        expected_type = prop_schema.get("type")
        py_type = _TYPE_MAP.get(expected_type)
        if py_type is not None:
            if expected_type == "number" and isinstance(value, bool):
                errors.append(f"argument '{key}' expected type 'number', got bool")
            elif not isinstance(value, py_type):
                errors.append(
                    f"argument '{key}' expected type '{expected_type}', got '{type(value).__name__}'"
                )
        enum_values = prop_schema.get("enum")
        if enum_values is not None and value not in enum_values:
            errors.append(f"argument '{key}' must be one of {enum_values}, got {value!r}")

    return errors


class ToolExecutor:
    """Executes tool calls against MCPServerConnection instances resolved
    via a ToolRegistry, adding validation, retry, and concurrency control."""

    def __init__(self, registry: ToolRegistry, connections_provider, default_timeout_s: float = 30.0) -> None:
        """`connections_provider` is a callable (server_id: str) ->
        MCPServerConnection, injected so ToolExecutor has no direct
        dependency on the runtime's connection dict."""
        self._registry = registry
        self._connections_provider = connections_provider
        self._default_timeout_s = default_timeout_s
        self._in_flight: dict[str, asyncio.Task] = {}

    async def call(self, request: ToolCallRequest) -> ToolCallResult:
        descriptor = self._registry.resolve(request.tool_name, request.server_id)
        validation_errors = validate_arguments(descriptor.schema, request.arguments)
        if validation_errors:
            raise ToolValidationError(
                f"validation failed for tool '{descriptor.qualified_name}': {'; '.join(validation_errors)}"
            )

        connection = self._connections_provider(descriptor.server_id)
        if connection is None:
            raise ToolExecutionError(f"no active connection for server '{descriptor.server_id}'")

        timeout_s = request.timeout_s or self._default_timeout_s
        attempts = 0
        last_error: str | None = None
        start = time.perf_counter()

        max_tries = max(1, request.max_retries + 1)
        for attempt in range(1, max_tries + 1):
            attempts = attempt
            key = request.idempotency_key or f"{descriptor.qualified_name}:{time.perf_counter()}"
            task = asyncio.create_task(connection.call_tool(descriptor.schema.name, request.arguments, timeout_s=timeout_s))
            self._in_flight[key] = task
            try:
                response = await task
                if response.is_error:
                    last_error = jsonrpc.error_summary(response)
                    logger.warning("tool call error (attempt %d/%d): %s", attempt, max_tries, last_error)
                    if attempt < max_tries:
                        await asyncio.sleep(min(2 ** (attempt - 1), 8))
                        continue
                    return ToolCallResult(
                        success=False, tool_name=descriptor.schema.name, server_id=descriptor.server_id,
                        error=last_error, duration_ms=(time.perf_counter() - start) * 1000, attempts=attempts,
                        is_error=True,
                    )

                content = self._extract_content(response.result)
                return ToolCallResult(
                    success=True, tool_name=descriptor.schema.name, server_id=descriptor.server_id,
                    content=content, duration_ms=(time.perf_counter() - start) * 1000, attempts=attempts,
                )
            except asyncio.CancelledError:
                raise
            except Exception as exc:  # noqa: BLE001
                last_error = str(exc)
                logger.warning("tool call exception (attempt %d/%d): %s", attempt, max_tries, exc)
                if attempt < max_tries:
                    await asyncio.sleep(min(2 ** (attempt - 1), 8))
                    continue
                return ToolCallResult(
                    success=False, tool_name=descriptor.schema.name, server_id=descriptor.server_id,
                    error=last_error, duration_ms=(time.perf_counter() - start) * 1000, attempts=attempts,
                    is_error=True,
                )
            finally:
                self._in_flight.pop(key, None)

        return ToolCallResult(
            success=False, tool_name=descriptor.schema.name, server_id=descriptor.server_id,
            error=last_error or "unknown failure", duration_ms=(time.perf_counter() - start) * 1000,
            attempts=attempts, is_error=True,
        )

    async def call_many(self, requests: list[ToolCallRequest]) -> list[ToolCallResult]:
        """Executes multiple tool calls concurrently and returns results in
        the same order as the input requests. A failure in one call does not
        cancel the others."""
        tasks = [asyncio.create_task(self._call_safe(r)) for r in requests]
        return await asyncio.gather(*tasks)

    async def _call_safe(self, request: ToolCallRequest) -> ToolCallResult:
        try:
            return await self.call(request)
        except (ToolNotFoundError, ToolValidationError) as exc:
            return ToolCallResult(
                success=False, tool_name=request.tool_name, server_id=request.server_id or "unknown",
                error=str(exc), is_error=True,
            )

    def cancel(self, idempotency_key: str) -> bool:
        task = self._in_flight.get(idempotency_key)
        if task is None or task.done():
            return False
        task.cancel()
        return True

    def cancel_all(self) -> int:
        count = 0
        for task in list(self._in_flight.values()):
            if not task.done():
                task.cancel()
                count += 1
        return count

    @staticmethod
    def _extract_content(result: Any) -> Any:
        if isinstance(result, dict) and "content" in result:
            return result["content"]
        return result
