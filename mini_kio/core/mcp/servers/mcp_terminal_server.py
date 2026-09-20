#!/usr/bin/env python3
"""MCP Terminal Server — run/run_piped/which over JSON-RPC 2.0 stdio."""

from __future__ import annotations

import os
import re
import shlex
import shutil
import subprocess as sp
import sys
from pathlib import Path

from mini_kio.core.mcp.servers.base import BaseMCPServer

# ── Command safety blocklist ─────────────────────────────────────────────────
# Patterns that must NEVER be executed by KIO. These are destructive,
# privilege-escalating, or could damage the host system.
_BLOCKED_PATTERNS: list[re.Pattern] = [
    re.compile(r"\brm\s+-rf\s+/\b", re.I),            # rm -rf /
    re.compile(r"\brm\s+-rf\s+~", re.I),               # rm -rf ~
    re.compile(r"\bformat\s+[a-zA-Z]", re.I),          # format C:
    re.compile(r"\bdel\s+/[sS]\s+/[qQ]", re.I),       # del /s /q (recursive force)
    re.compile(r"\brmdir\s+/s\s+/q", re.I),            # rmdir /s /q
    re.compile(r"\bshutdown\b", re.I),                  # shutdown
    re.compile(r"\breboot\b", re.I),                    # reboot
    re.compile(r"\bsudo\b", re.I),                      # sudo
    re.compile(r"\bchmod\s+777\b", re.I),               # chmod 777
    re.compile(r"\bchown\b", re.I),                     # chown
    re.compile(r"\bmkfs\b", re.I),                      # mkfs
    re.compile(r"\bdd\s+if=", re.I),                    # dd if=
    re.compile(r"\bcurl\b.*\|\s*sh\b", re.I),          # curl | sh
    re.compile(r"\bcurl\b.*\|\s*bash\b", re.I),        # curl | bash
    re.compile(r"\bwget\b.*\|\s*sh\b", re.I),          # wget | sh
    re.compile(r"\bwget\b.*\|\s*bash\b", re.I),        # wget | bash
    re.compile(r"\bInvoke-WebRequest\b.*\|\s*Invoke-Expression\b", re.I),  # IWR | IEX
    re.compile(r"\biwr\b.*\|\s*iex\b", re.I),          # iwr | iex
    re.compile(r"\bSet-ExecutionPolicy\b.*\bUnrestricted\b", re.I),
    re.compile(r"\bSet-ExecutionPolicy\b.*\bBypass\b", re.I),
    re.compile(r"\bREG\s+DELETE\b", re.I),              # reg delete
    re.compile(r"\btaskkill\b.*\b/F\b", re.I),         # taskkill /F
    re.compile(r"\bGet-Process\b.*\bStop-Process\b", re.I),
    re.compile(r"\bRemove-Item\b.*-Recurse\b.*-Force\b.*\\\\", re.I),  # rm -rf \\path
    re.compile(r"\bgit\s+push\s+.*--force\b", re.I),   # git push --force
    re.compile(r"\bgit\s+reset\s+--hard\b", re.I),     # git reset --hard
]

_DANGEROUS_MSG = (
    "This command was blocked for safety. KIO will not execute commands "
    "that could damage your system, delete critical data, or escalate privileges."
)


class TerminalMCPServer(BaseMCPServer):
    def __init__(self) -> None:
        super().__init__("terminal", "Terminal Server", "1.0.0")
        self.register_tool("run", self._run, {"command": {"type": "string"}})
        self.register_tool("run_piped", self._run_piped, {"commands": {"type": "array"}})
        self.register_tool("which", self._which, {"executable": {"type": "string"}})

    @staticmethod
    def _check_blocked(command: str) -> str | None:
        """Return an error message if the command matches a blocked pattern."""
        for pat in _BLOCKED_PATTERNS:
            if pat.search(command):
                return _DANGEROUS_MSG
        return None

    # CREATE_NO_WINDOW prevents a visible console window on Windows.
    _WIN_FLAGS = 0x08000000 if sys.platform == "win32" else 0

    def _run(self, command: str) -> dict:
        blocked = self._check_blocked(command)
        if blocked:
            return {"success": False, "message": blocked, "command": command, "exit_code": -1}
        try:
            import shlex
            args = shlex.split(command)
            _kw: dict = dict(capture_output=True, text=True, timeout=30)
            if self._WIN_FLAGS:
                _kw["creationflags"] = self._WIN_FLAGS
            result = sp.run(args, **_kw)
            return {"success": result.returncode == 0, "stdout": result.stdout, "stderr": result.stderr,
                    "exit_code": result.returncode, "command": command}
        except sp.TimeoutExpired:
            return {"success": False, "message": "Command timed out", "command": command, "exit_code": -1}
        except Exception as exc:
            return {"success": False, "message": str(exc), "command": command, "exit_code": -1}

    def _run_piped(self, commands: list) -> dict:
        if not commands:
            return {"success": False, "message": "No commands provided", "commands": []}
        for cmd in commands:
            blocked = self._check_blocked(str(cmd))
            if blocked:
                return {"success": False, "message": blocked, "commands": commands}
        import shlex
        cmds = [str(c) for c in commands]
        pipes = []
        try:
            for i, cmd in enumerate(cmds):
                stdin = pipes[-1].stdout if pipes else None
                args = shlex.split(cmd)
                _popen_kw: dict = dict(stdin=stdin, stdout=sp.PIPE, stderr=sp.PIPE, text=True)
                if self._WIN_FLAGS:
                    _popen_kw["creationflags"] = self._WIN_FLAGS
                p = sp.Popen(args, **_popen_kw)
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
