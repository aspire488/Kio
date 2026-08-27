"""TerminalProvider — wraps subprocess/pyperclip under ExecutionProvider contract."""

from __future__ import annotations

import logging
import subprocess
import sys
import time
from typing import Any

from mini_kio.core.provider_contract import ExecutionProvider, ProviderHealth, ProviderCapability

logger = logging.getLogger(__name__)


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
        start = time.time()
        _run_kwargs: dict[str, Any] = dict(
            shell=True, capture_output=True, text=True,
            timeout=kwargs.get("timeout", 30),
        )
        # CREATE_NO_WINDOW prevents a visible console flash on Windows.
        if sys.platform == "win32":
            _run_kwargs["creationflags"] = 0x08000000
        try:
            result = subprocess.run(command, **_run_kwargs)
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
