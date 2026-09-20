"""TerminalProvider — wraps subprocess/pyperclip under ExecutionProvider contract."""

from __future__ import annotations

import logging
import subprocess
import sys
import time
from typing import Any

from mini_kio.core.provider_contract import ExecutionProvider, ProviderHealth, ProviderCapability
from mini_kio.core.win_spawn import no_window

logger = logging.getLogger(__name__)

_SAFE_COMMANDS = frozenset({
    "dir", "cd", "echo", "type", "whoami", "hostname", "date", "time",
    "ipconfig", "systeminfo", "tasklist", "netstat", "nslookup", "ping",
    "tracert", "path", "set", "ver", "vol", "tree", "where", "which",
    "ls", "pwd", "cat", "head", "tail", "grep", "wc", "uname", "df",
    "du", "ps", "top", "id", "groups", "env", "printenv", "uptime",
    "find", "file", "stat", "diff", "sort", "uniq", "cut", "awk",
    "sed", "tr", "xargs", "date", "cal", "free", "lscpu",
})

_BLOCKED_PATTERNS = (
    "rm -rf", "rmdir /s", "del /f", "format ", "shutdown",
    "reboot", "halt", "init 0", "mkfs", "dd if=",
    "> /dev/", "chmod 777", "chown", "passwd",
    "reg delete", "reg add", "bcdedit", "diskpart",
)


def _is_safe_command(command: str) -> bool:
    cmd = command.strip().lower()
    if any(bad in cmd for bad in _BLOCKED_PATTERNS):
        return False
    first_word = cmd.split()[0].split("/")[-1].split("\\")[-1].replace(".exe", "")
    return first_word in _SAFE_COMMANDS


class TerminalProvider(ExecutionProvider):
    def id(self) -> str:
        return "terminal"

    def capabilities(self) -> list[ProviderCapability]:
        return [
            ProviderCapability(name="run_command", category="system_command", timeout_s=30, ram_budget_mb=20),
            ProviderCapability(name="clipboard_copy", category="system_action", timeout_s=5, ram_budget_mb=5),
            ProviderCapability(name="clipboard_paste", category="system_action", timeout_s=5, ram_budget_mb=5),
        ]

    def health(self) -> ProviderHealth:
        return ProviderHealth.HEALTHY

    def execute(self, action: str, target: str, **kwargs: Any) -> dict[str, Any]:
        if action == "run_command":
            return self._run(target, **kwargs)
        elif action == "clipboard_copy":
            return self._copy(target)
        elif action == "clipboard_paste":
            return self._paste()
        return {"success": False, "message": f"TerminalProvider: unknown action {action}"}

    def _run(self, command: str, **kwargs: Any) -> dict[str, Any]:
        if not _is_safe_command(command):
            return {
                "success": False,
                "message": f"Command not in safe list: {command.split()[0]}. "
                           f"Allowed: {', '.join(sorted(_SAFE_COMMANDS))}",
            }
        start = time.time()
        if sys.platform == "win32":
            args = ["cmd.exe", "/c", command]
            # CREATE_NO_WINDOW is mandatory here: KIO runs console-less, so a
            # bare Popen of cmd.exe pops a visible console window.  The old
            # 0x00100000 was CREATE_BREAKAWAY_FROM_JOB, which does NOT
            # suppress the window.  Output is now captured and the real exit
            # code is reported instead of an unconditional success.
            try:
                result = subprocess.run(
                    args, capture_output=True, text=True,
                    timeout=kwargs.get("timeout", 30),
                    **no_window(),
                )
            except subprocess.TimeoutExpired:
                return {"success": False, "message": "Command timed out"}
            except Exception as exc:
                return {"success": False, "message": str(exc)}
            elapsed = int((time.time() - start) * 1000)
            output = (result.stdout or "").strip() or (result.stderr or "").strip()
            return {
                "success": result.returncode == 0,
                "message": output,
                "stdout": result.stdout, "stderr": result.stderr,
                "exit_code": result.returncode, "elapsed_ms": elapsed,
            }
        else:
            import shlex
            try:
                args = shlex.split(command)
            except ValueError:
                args = command
            _run_kwargs = dict(
                capture_output=True, text=True,
                timeout=kwargs.get("timeout", 30),
            )
            try:
                result = subprocess.run(args, **_run_kwargs)
                elapsed = int((time.time() - start) * 1000)
                return {
                    "success": result.returncode == 0,
                    "message": result.stdout.strip() or result.stderr.strip(),
                    "stdout": result.stdout, "stderr": result.stderr,
                    "exit_code": result.returncode, "elapsed_ms": elapsed,
                }
            except subprocess.TimeoutExpired:
                return {"success": False, "message": "Command timed out"}
            except Exception as exc:
                return {"success": False, "message": str(exc)}

    def _copy(self, text: str) -> dict[str, Any]:
        try:
            import pyperclip
            pyperclip.copy(text)
            return {"success": True, "message": "Copied to clipboard."}
        except Exception as exc:
            return {"success": False, "message": f"Copy failed: {exc}"}

    def _paste(self) -> dict[str, Any]:
        try:
            import pyperclip
            text = pyperclip.paste()
            return {"success": True, "message": "Pasted from clipboard.", "text": text}
        except Exception as exc:
            return {"success": False, "message": f"Paste failed: {exc}"}

    def verify(self, action: str, result: dict[str, Any]) -> dict[str, Any]:
        result.setdefault("probe_used", "terminal_action")
        if result.get("success"):
            result.setdefault("verification_status", "passed")
            result.setdefault("outcome_class", "SUCCESS")
        else:
            result.setdefault("verification_status", "failed")
            result.setdefault("outcome_class", "FAILURE")
        return result
