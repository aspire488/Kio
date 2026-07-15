#!/usr/bin/env python3
"""MCP Filesystem Server — read/write/list/search/info/exists over JSON-RPC 2.0 stdio."""

from __future__ import annotations

import os
import stat
import time
from datetime import datetime, timezone
from pathlib import Path

from mini_kio.core.mcp.servers.base import BaseMCPServer


class FilesystemMCPServer(BaseMCPServer):
    def __init__(self) -> None:
        super().__init__("filesystem", "Filesystem Server", "1.0.0")
        self.register_tool("read", self._read, {"path": {"type": "string"}})
        self.register_tool("write", self._write, {"path": {"type": "string"}, "content": {"type": "string"}})
        self.register_tool("list", self._list, {"path": {"type": "string"}})
        self.register_tool("search", self._search, {"pattern": {"type": "string"}, "path": {"type": "string"}})
        self.register_tool("info", self._info, {"path": {"type": "string"}})
        self.register_tool("exists", self._exists, {"path": {"type": "string"}})

    def _read(self, path: str) -> dict:
        p = Path(path)
        if not p.exists():
            return {"success": False, "message": f"Path not found: {path}", "exists": False}
        if p.is_dir():
            return {"success": False, "message": f"Path is a directory: {path}", "is_dir": True}
        content = p.read_text(encoding="utf-8", errors="replace")
        return {"success": True, "message": f"Read {len(content)} chars", "content": content, "path": str(p),
                "size": len(content)}

    def _write(self, path: str, content: str) -> dict:
        p = Path(path)
        p.parent.mkdir(parents=True, exist_ok=True)
        p.write_text(content, encoding="utf-8")
        return {"success": True, "message": f"Written {len(content)} chars to {path}", "path": str(p), "size": len(content)}

    def _list(self, path: str) -> dict:
        p = Path(path)
        if not p.exists():
            return {"success": False, "message": f"Path not found: {path}"}
        if not p.is_dir():
            return {"success": False, "message": f"Path is not a directory: {path}"}
        entries = []
        for child in sorted(p.iterdir()):
            try:
                st = child.stat()
                entries.append({"name": child.name, "is_dir": child.is_dir(), "size": st.st_size,
                                "modified": datetime.fromtimestamp(st.st_mtime, tz=timezone.utc).isoformat()})
            except OSError:
                entries.append({"name": child.name, "is_dir": False, "size": 0, "modified": ""})
        return {"success": True, "message": f"Listed {len(entries)} entries", "entries": entries, "path": str(p)}

    def _search(self, pattern: str, path: str = ".") -> dict:
        root = Path(path)
        if not root.exists():
            return {"success": False, "message": f"Path not found: {path}"}
        matches = [str(p) for p in root.rglob(pattern)]
        return {"success": True, "message": f"Found {len(matches)} matches", "matches": matches, "pattern": pattern}

    def _info(self, path: str) -> dict:
        p = Path(path)
        if not p.exists():
            return {"success": False, "message": f"Path not found: {path}", "exists": False}
        st = p.stat()
        return {"success": True, "path": str(p), "exists": True, "is_dir": p.is_dir(), "is_file": p.is_file(),
                "is_symlink": p.is_symlink(), "size": st.st_size,
                "created": datetime.fromtimestamp(st.st_ctime, tz=timezone.utc).isoformat(),
                "modified": datetime.fromtimestamp(st.st_mtime, tz=timezone.utc).isoformat(),
                "permissions": stat.filemode(st.st_mode)}

    def _exists(self, path: str) -> dict:
        p = Path(path)
        exists = p.exists()
        return {"success": True, "exists": exists, "path": str(p), "is_dir": p.is_dir() if exists else False}


if __name__ == "__main__":
    import logging
    logging.basicConfig(level=logging.WARNING)
    server = FilesystemMCPServer()
    server.run()
