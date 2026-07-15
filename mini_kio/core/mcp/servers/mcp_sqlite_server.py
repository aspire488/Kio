#!/usr/bin/env python3
"""MCP SQLite Server — query/execute/tables/schema over JSON-RPC 2.0 stdio."""

from __future__ import annotations

import sqlite3
from pathlib import Path

from mini_kio.core.mcp.servers.base import BaseMCPServer


class SQLiteMCPServer(BaseMCPServer):
    def __init__(self) -> None:
        super().__init__("sqlite", "SQLite Server", "1.0.0")
        self.register_tool("query", self._query, {"sql": {"type": "string"}, "path": {"type": "string"}})
        self.register_tool("execute", self._execute, {"sql": {"type": "string"}, "path": {"type": "string"}})
        self.register_tool("tables", self._tables, {"path": {"type": "string"}})
        self.register_tool("schema", self._schema, {"path": {"type": "string"}, "table": {"type": "string"}})
        self._connections: dict[str, sqlite3.Connection] = {}

    def _connect(self, path: str) -> sqlite3.Connection:
        if path not in self._connections:
            p = Path(path)
            p.parent.mkdir(parents=True, exist_ok=True)
            conn = sqlite3.connect(str(p))
            conn.row_factory = sqlite3.Row
            self._connections[path] = conn
        return self._connections[path]

    def _query(self, sql: str, path: str = ":memory:") -> dict:
        conn = self._connect(path)
        try:
            cur = conn.execute(sql)
            rows = [dict(row) for row in cur.fetchall()]
            return {"success": True, "rows": rows, "count": len(rows), "sql": sql, "path": path}
        except Exception as exc:
            return {"success": False, "message": str(exc), "sql": sql, "path": path}

    def _execute(self, sql: str, path: str = ":memory:") -> dict:
        conn = self._connect(path)
        try:
            cur = conn.execute(sql)
            conn.commit()
            return {"success": True, "changes": conn.total_changes, "last_row_id": cur.lastrowid,
                    "sql": sql, "path": path}
        except Exception as exc:
            return {"success": False, "message": str(exc), "sql": sql, "path": path}

    def _tables(self, path: str = ":memory:") -> dict:
        conn = self._connect(path)
        try:
            cur = conn.execute("SELECT name FROM sqlite_master WHERE type='table' ORDER BY name")
            tables = [row[0] for row in cur.fetchall()]
            return {"success": True, "tables": tables, "count": len(tables), "path": path}
        except Exception as exc:
            return {"success": False, "message": str(exc), "path": path}

    def _schema(self, path: str = ":memory:", table: str = "") -> dict:
        conn = self._connect(path)
        try:
            cur = conn.execute(f"SELECT sql FROM sqlite_master WHERE type='table' AND name=?", (table,))
            row = cur.fetchone()
            if row:
                return {"success": True, "schema": row[0], "table": table, "path": path}
            return {"success": False, "message": f"Table not found: {table}", "table": table, "path": path}
        except Exception as exc:
            return {"success": False, "message": str(exc), "table": table, "path": path}


if __name__ == "__main__":
    import logging
    logging.basicConfig(level=logging.WARNING)
    server = SQLiteMCPServer()
    server.run()
