"""MCP PostgreSQL Server — SQL database operations via psycopg2.

Run: python -m mini_kio.core.mcp.servers.mcp_postgres_server

Requires: pip install psycopg2-binary

Environment:
  PG_HOST, PG_PORT (default 5432), PG_DB, PG_USER, PG_PASSWORD

Tools:
  pg_list_tables    — list tables in database
  pg_list_schema    — describe table columns
  pg_query          — execute SELECT query
  pg_execute        — execute INSERT/UPDATE/DELETE
"""

from __future__ import annotations

import logging
import os
import sys
from typing import Any

logger = logging.getLogger(__name__)

_PG_CONFIG = {
    "host": os.environ.get("PG_HOST", "localhost"),
    "port": int(os.environ.get("PG_PORT", "5432")),
    "dbname": os.environ.get("PG_DB", ""),
    "user": os.environ.get("PG_USER", ""),
    "password": os.environ.get("PG_PASSWORD", ""),
}


def _get_connection():
    try:
        import psycopg2
    except ImportError:
        return None
    if not _PG_CONFIG["dbname"] or not _PG_CONFIG["user"]:
        return None
    try:
        return psycopg2.connect( **_PG_CONFIG)
    except Exception as exc:
        logger.warning("PostgreSQL connection failed: %s", exc)
        return None


def _execute(sql: str, params: tuple | None = None) -> dict[str, Any]:
    conn = _get_connection()
    if conn is None:
        return {"success": False, "error": "PostgreSQL not available (install psycopg2-binary and set PG_* env vars)"}
    try:
        with conn:
            with conn.cursor() as cur:
                cur.execute(sql, params)
                if cur.description:
                    cols = [d[0] for d in cur.description]
                    rows = [dict(zip(cols, row)) for row in cur.fetchall()]
                    return {"success": True, "columns": cols, "rows": rows, "count": len(rows)}
                return {"success": True, "rows_affected": cur.rowcount}
    except Exception as exc:
        return {"success": False, "error": str(exc)}
    finally:
        conn.close()


def pg_list_tables(schema: str = "public") -> dict[str, Any]:
    return _execute(
        "SELECT table_name, table_type FROM information_schema.tables WHERE table_schema = %s ORDER BY table_name",
        (schema,)
    )


def pg_list_schema(table: str, schema: str = "public") -> dict[str, Any]:
    return _execute(
        "SELECT column_name, data_type, is_nullable, column_default FROM information_schema.columns "
        "WHERE table_schema = %s AND table_name = %s ORDER BY ordinal_position",
        (schema, table)
    )


def pg_query(sql: str, params: list | None = None) -> dict[str, Any]:
    safe_sql = sql.strip().upper()
    if not safe_sql.startswith("SELECT") and not safe_sql.startswith("WITH"):
        return {"success": False, "error": "Only SELECT/WITH queries allowed via pg_query. Use pg_execute for modifications."}
    return _execute(sql, tuple(params) if params else None)


def pg_execute(sql: str, params: list | None = None) -> dict[str, Any]:
    return _execute(sql, tuple(params) if params else None)


if __name__ == "__main__":
    logging.basicConfig(level=logging.WARNING)
    from mini_kio.core.mcp.servers.base import BaseMCPServer
    server = BaseMCPServer("postgres", "PostgreSQL MCP Server", version="1.0.0")
    server.register_tool("pg_list_tables", pg_list_tables, {"schema": {"type": "string", "default": "public"}})
    server.register_tool("pg_list_schema", pg_list_schema, {"table": {"type": "string"}, "schema": {"type": "string", "default": "public"}})
    server.register_tool("pg_query", pg_query, {"sql": {"type": "string"}, "params": {"type": "array", "default": None}})
    server.register_tool("pg_execute", pg_execute, {"sql": {"type": "string"}, "params": {"type": "array", "default": None}})
    server.run()
