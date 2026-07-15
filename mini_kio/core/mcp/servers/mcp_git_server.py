#!/usr/bin/env python3
"""MCP Git Server — status/log/diff/branch/clone/show over JSON-RPC 2.0 stdio."""

from __future__ import annotations

import os
import subprocess
from pathlib import Path

from mini_kio.core.mcp.servers.base import BaseMCPServer


class GitMCPServer(BaseMCPServer):
    def __init__(self) -> None:
        super().__init__("git", "Git Server", "1.0.0")
        self.register_tool("status", self._status, {"path": {"type": "string"}})
        self.register_tool("log", self._log, {"path": {"type": "string"}, "count": {"type": "integer"}})
        self.register_tool("diff", self._diff, {"path": {"type": "string"}, "staged": {"type": "boolean"}})
        self.register_tool("branch", self._branch, {"path": {"type": "string"}})
        self.register_tool("clone", self._clone, {"url": {"type": "string"}, "path": {"type": "string"}})
        self.register_tool("show", self._show, {"path": {"type": "string"}, "rev": {"type": "string"}})

    def _git(self, cwd: str, *args: str) -> tuple[int, str, str]:
        result = subprocess.run(["git"] + list(args), capture_output=True, text=True, cwd=cwd, timeout=30)
        return result.returncode, result.stdout, result.stderr

    def _status(self, path: str) -> dict:
        rc, out, err = self._git(path, "status", "--porcelain")
        if rc != 0:
            return {"success": False, "message": f"Git error: {err}", "path": path}
        lines = [l for l in out.splitlines() if l.strip()]
        return {"success": True, "message": f"Status: {len(lines)} changes", "changes": len(lines), "path": path}

    def _log(self, path: str, count: int = 10) -> dict:
        rc, out, err = self._git(path, "log", f"--max-count={count}", "--oneline")
        if rc != 0:
            return {"success": False, "message": f"Git error: {err}", "path": path}
        commits = [l.strip() for l in out.splitlines() if l.strip()]
        return {"success": True, "message": f"{len(commits)} commits", "commits": commits, "path": path}

    def _diff(self, path: str, staged: bool = False) -> dict:
        args = ["diff"]
        if staged:
            args.append("--cached")
        rc, out, err = self._git(path, *args)
        if rc != 0:
            return {"success": False, "message": f"Git error: {err}"}
        return {"success": True, "message": f"Diff: {len(out)} chars", "diff": out, "path": path, "staged": staged}

    def _branch(self, path: str) -> dict:
        rc, out, err = self._git(path, "branch", "-a")
        if rc != 0:
            return {"success": False, "message": f"Git error: {err}"}
        branches = [l.strip() for l in out.splitlines() if l.strip()]
        return {"success": True, "message": f"{len(branches)} branches", "branches": branches, "path": path}

    def _clone(self, url: str, path: str) -> dict:
        rc, out, err = self._git(os.path.dirname(path) if os.path.sep in path else ".", "clone", url, path)
        if rc != 0:
            return {"success": False, "message": f"Clone failed: {err}"}
        return {"success": True, "message": f"Cloned {url} to {path}", "url": url, "path": path}

    def _show(self, path: str, rev: str = "HEAD") -> dict:
        rc, out, err = self._git(path, "show", rev, "--no-patch", "--format=%H%n%an%n%ae%n%aI%n%s")
        if rc != 0:
            return {"success": False, "message": f"Git error: {err}"}
        lines = [l.strip() for l in out.splitlines() if l.strip()]
        return {"success": True, "message": f"Commit {lines[0] if lines else rev}",
                "commit": lines[0] if len(lines) > 0 else "", "author": lines[1] if len(lines) > 1 else "",
                "email": lines[2] if len(lines) > 2 else "",
                "date": lines[3] if len(lines) > 3 else "",
                "subject": lines[4] if len(lines) > 4 else "", "path": path, "rev": rev}


if __name__ == "__main__":
    import logging
    logging.basicConfig(level=logging.WARNING)
    server = GitMCPServer()
    server.run()
