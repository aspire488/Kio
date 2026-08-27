#!/usr/bin/env python3
"""MCP Terminal Server — run/run_piped/which over JSON-RPC 2.0 stdio."""

from __future__ import annotations

import os
import shutil
import subprocess as sp
import sys
from pathlib import Path

from mini_kio.core.mcp.servers.base import BaseMCPServer


class TerminalMCPServer(BaseMCPServer):
    def __init__(self) -> None:
        super().__init__("terminal", "Terminal Server", "1.0.0")
        self.register_tool("run", self._run, {"command": {"type": "string"}})
        self.register_tool("run_piped", self._run_piped, {"commands": {"type": "array"}})
        self.register_tool("which", self._which, {"executable": {"type": "string"}})

    # CREATE_NO_WINDOW prevents a visible console window on Windows.
    _WIN_FLAGS = 0x08000000 if sys.platform == "win32" else 0

    def _run(self, command: str) -> dict:
        try:
            _kw: dict = dict(capture_output=True, text=True, shell=True, timeout=30)
            if self._WIN_FLAGS:
                _kw["creationflags"] = self._WIN_FLAGS
            result = sp.run(command, **_kw)
            return {"success": result.returncode == 0, "stdout": result.stdout, "stderr": result.stderr,
                    "exit_code": result.returncode, "command": command}
        except sp.TimeoutExpired:
            return {"success": False, "message": "Command timed out", "command": command, "exit_code": -1}
        except Exception as exc:
            return {"success": False, "message": str(exc), "command": command, "exit_code": -1}

    def _run_piped(self, commands: list) -> dict:
        if not commands:
            return {"success": False, "message": "No commands provided", "commands": []}
        cmds = [str(c) for c in commands]
        pipes = []
        try:
            for i, cmd in enumerate(cmds):
                stdin = pipes[-1].stdout if pipes else None
                _popen_kw: dict = dict(stdin=stdin, stdout=sp.PIPE, stderr=sp.PIPE, shell=True, text=True)
                if self._WIN_FLAGS:
                    _popen_kw["creationflags"] = self._WIN_FLAGS
                p = sp.Popen(cmd, **_popen_kw)
                pipes.append(p)
                if stdin:
                    stdin.close()
            stdout, stderr = pipes[-1].communicate(timeout=60)
            return {"success": True, "stdout": stdout, "stderr": stderr,
                    "exit_code": pipes[-1].returncode or 0, "commands": cmds}
        except sp.TimeoutExpired:
            for p in pipes:
                p.kill()
            return {"success": False, "message": "Pipeline timed out", "commands": cmds}
        except Exception as exc:
            return {"success": False, "message": str(exc), "commands": cmds}

    def _which(self, executable: str) -> dict:
        path = shutil.which(executable)
        return {"success": path is not None, "found": path is not None, "path": path or "", "executable": executable}


if __name__ == "__main__":
    import logging
    logging.basicConfig(level=logging.WARNING)
    server = TerminalMCPServer()
    server.run()
