"""MCP Redis Server — in-memory data store operations.

Run: python -m mini_kio.core.mcp.servers.mcp_redis_server

Requires: pip install redis

Environment:
  REDIS_HOST (default localhost), REDIS_PORT (default 6379), REDIS_DB (default 0), REDIS_PASSWORD

Tools:
  redis_get        — get a key
  redis_set        — set a key
  redis_delete     — delete key(s)
  redis_exists     — check if key exists
  redis_keys       — find keys by pattern
  redis_expire     — set TTL on key
  redis_incr       — increment a key
  redis_lpush      — push to list head
  redis_rpush      — push to list tail
  redis_lrange     — get list range
  redis_sadd       — add to set
  redis_smembers   — get set members
  redis_hget       — get hash field
  redis_hset       — set hash field
  redis_hgetall    — get all hash fields
  redis_info       — server info/stats
"""

from __future__ import annotations

import logging
import os
import sys
from typing import Any

logger = logging.getLogger(__name__)

_REDIS_CONFIG = {
    "host": os.environ.get("REDIS_HOST", "localhost"),
    "port": int(os.environ.get("REDIS_PORT", "6379")),
    "db": int(os.environ.get("REDIS_DB", "0")),
    "password": os.environ.get("REDIS_PASSWORD") or None,
}


def _get_client():
    try:
        import redis
    except ImportError:
        return None
    try:
        return redis.Redis(**_REDIS_CONFIG)
    except Exception as exc:
        logger.warning("Redis connection failed: %s", exc)
        return None


def _with_client(method: str, *args, **kwargs) -> dict[str, Any]:
    client = _get_client()
    if client is None:
        return {"success": False, "error": "Redis not available (install redis-py and set REDIS_* env vars)"}
    try:
        result = getattr(client, method)(*args, **kwargs)
        return {"success": True, "result": result}
    except Exception as exc:
        return {"success": False, "error": str(exc)}
    finally:
        client.close()


def redis_get(key: str) -> dict[str, Any]:
    return _with_client("get", key)


def redis_set(key: str, value: str, ttl_s: int | None = None) -> dict[str, Any]:
    if ttl_s:
        return _with_client("setex", key, ttl_s, value)
    return _with_client("set", key, value)


def redis_delete(key: str) -> dict[str, Any]:
    return _with_client("delete", key)


def redis_exists(key: str) -> dict[str, Any]:
    return _with_client("exists", key)


def redis_keys(pattern: str = "*") -> dict[str, Any]:
    return _with_client("keys", pattern)


def redis_expire(key: str, ttl_s: int) -> dict[str, Any]:
    return _with_client("expire", key, ttl_s)


def redis_incr(key: str, amount: int = 1) -> dict[str, Any]:
    return _with_client("incrby", key, amount)


def redis_lpush(key: str, *values: str) -> dict[str, Any]:
    return _with_client("lpush", key, *values)


def redis_rpush(key: str, *values: str) -> dict[str, Any]:
    return _with_client("rpush", key, *values)


def redis_lrange(key: str, start: int = 0, stop: int = -1) -> dict[str, Any]:
    return _with_client("lrange", key, start, stop)


def redis_sadd(key: str, *members: str) -> dict[str, Any]:
    return _with_client("sadd", key, *members)


def redis_smembers(key: str) -> dict[str, Any]:
    return _with_client("smembers", key)


def redis_hget(key: str, field: str) -> dict[str, Any]:
    return _with_client("hget", key, field)


def redis_hset(key: str, field: str, value: str) -> dict[str, Any]:
    return _with_client("hset", key, field, value)


def redis_hgetall(key: str) -> dict[str, Any]:
    return _with_client("hgetall", key)


def redis_info() -> dict[str, Any]:
    return _with_client("info")


if __name__ == "__main__":
    logging.basicConfig(level=logging.WARNING)
    from mini_kio.core.mcp.servers.base import BaseMCPServer
    server = BaseMCPServer("redis", "Redis MCP Server", version="1.0.0")
    server.register_tool("redis_get", redis_get, {"key": {"type": "string"}})
    server.register_tool("redis_set", redis_set, {"key": {"type": "string"}, "value": {"type": "string"}, "ttl_s": {"type": "integer", "default": None}})
    server.register_tool("redis_delete", redis_delete, {"key": {"type": "string"}})
    server.register_tool("redis_exists", redis_exists, {"key": {"type": "string"}})
    server.register_tool("redis_keys", redis_keys, {"pattern": {"type": "string", "default": "*"}})
    server.register_tool("redis_expire", redis_expire, {"key": {"type": "string"}, "ttl_s": {"type": "integer"}})
    server.register_tool("redis_incr", redis_incr, {"key": {"type": "string"}, "amount": {"type": "integer", "default": 1}})
    server.register_tool("redis_lpush", redis_lpush, {"key": {"type": "string"}, "values": {"type": "array"}})
    server.register_tool("redis_rpush", redis_rpush, {"key": {"type": "string"}, "values": {"type": "array"}})
    server.register_tool("redis_lrange", redis_lrange, {"key": {"type": "string"}, "start": {"type": "integer", "default": 0}, "stop": {"type": "integer", "default": -1}})
    server.register_tool("redis_sadd", redis_sadd, {"key": {"type": "string"}, "members": {"type": "array"}})
    server.register_tool("redis_smembers", redis_smembers, {"key": {"type": "string"}})
    server.register_tool("redis_hget", redis_hget, {"key": {"type": "string"}, "field": {"type": "string"}})
    server.register_tool("redis_hset", redis_hset, {"key": {"type": "string"}, "field": {"type": "string"}, "value": {"type": "string"}})
    server.register_tool("redis_hgetall", redis_hgetall, {"key": {"type": "string"}})
    server.register_tool("redis_info", redis_info)
    server.run()
