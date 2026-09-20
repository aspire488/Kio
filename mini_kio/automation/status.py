"""Status tracking for automation templates and runs."""

from __future__ import annotations

import logging
import time
from typing import Any

logger = logging.getLogger(__name__)


class RuntimeCapabilityChecker:
    """Checks which capabilities are available at the current runtime moment.

    Unlike CapabilityResolver (static provider check), this checks the
    actual runtime state: browser connected? GitHub MCP alive? LLM configured?
    """

    def check_all(self) -> dict[str, dict[str, Any]]:
        """Check all capability groups and return status for each."""
        result: dict[str, dict[str, Any]] = {}

        # Browser
        result["browser"] = self._check_browser()
        # GitHub
        result["github"] = self._check_github()
        # LLM
        result["ai_reasoning"] = self._check_llm()
        # Email
        result["email"] = self._check_email()
        # Calendar
        result["calendar"] = self._check_calendar()
        # Communication
        result["communication"] = self._check_communication()
        # Filesystem (always available)
        result["filesystem"] = {"available": True, "reason": "local filesystem"}
        # Workflow (always available)
        result["workflow"] = {"available": True, "reason": "deterministic transform"}
        # Memory (always available)
        result["memory"] = {"available": True, "reason": "in-memory store"}
        # Artifact
        result["artifact"] = self._check_artifact()
        # Media
        result["media"] = self._check_media()
        # HTTP
        result["http"] = self._check_http()
        # Monitoring
        result["monitoring"] = self._check_monitoring()
        # Code project
        result["code_project"] = self._check_code_project()
        # MCP tool
        result["mcp_tool"] = self._check_mcp()

        return result

    def _check_browser(self) -> dict[str, Any]:
        try:
            from mini_kio.core.command_router import _use_browser_runtime
            if _use_browser_runtime():
                return {"available": True, "reason": "BrowserRuntime connected"}
        except Exception:
            pass
        try:
            from mini_kio.core.command_router import _get_connector
            conn = _get_connector()
            if conn is not None and conn.is_connected():
                return {"available": True, "reason": "Browser Connector connected"}
        except Exception:
            pass
        return {"available": False, "reason": "No browser backend connected"}

    def _check_github(self) -> dict[str, Any]:
        try:
            from mini_kio.core.config import MCP_SERVER_CONFIGS
            for cfg in (MCP_SERVER_CONFIGS or []):
                if cfg.get("server_id") == "github":
                    return {"available": True, "reason": "GitHub MCP configured"}
        except Exception:
            pass
        return {"available": False, "reason": "GitHub MCP server not configured"}

    def _check_llm(self) -> dict[str, Any]:
        try:
            from mini_kio.core.providers.ai_reasoning_provider import llm_capability_available
            available, detail = llm_capability_available()
            if available:
                return {"available": True, "reason": detail}
            return {"available": False, "reason": detail}
        except Exception as exc:
            return {"available": False, "reason": f"LLM chain not inspectable: {exc}"}

    def _check_email(self) -> dict[str, Any]:
        try:
            from mini_kio.core.credential_vault import get_credential_vault
            vault = get_credential_vault()
            cred = vault.get_credential("email_oauth") if hasattr(vault, "get_credential") else None
            if cred:
                return {"available": True, "reason": "Email OAuth configured"}
        except Exception:
            pass
        return {"available": False, "reason": "Email OAuth not configured"}

    def _check_calendar(self) -> dict[str, Any]:
        return {"available": False, "reason": "Calendar provider not implemented"}

    def _check_communication(self) -> dict[str, Any]:
        try:
            from mini_kio.core.config import TELEGRAM_TOKEN, DISCORD_BOT_TOKEN
            channels = []
            if TELEGRAM_TOKEN:
                channels.append("telegram")
            if DISCORD_BOT_TOKEN:
                channels.append("discord")
            if channels:
                return {"available": True, "reason": f"Channels: {', '.join(channels)}"}
        except Exception:
            pass
        return {"available": False, "reason": "No communication channels configured"}

    def _check_artifact(self) -> dict[str, Any]:
        # Artifact generation depends on libraries being installed
        try:
            import docx  # noqa: F401
            return {"available": True, "reason": "python-docx available"}
        except ImportError:
            pass
        return {"available": False, "reason": "Document generation libraries not installed"}

    def _check_media(self) -> dict[str, Any]:
        return {"available": False, "reason": "Media provider not implemented"}

    def _check_http(self) -> dict[str, Any]:
        try:
            import requests  # noqa: F401
            return {"available": True, "reason": "requests library available"}
        except ImportError:
            pass
        return {"available": False, "reason": "HTTP client not available"}

    def _check_monitoring(self) -> dict[str, Any]:
        try:
            from mini_kio.monitoring.watches import poll_watches
            return {"available": True, "reason": "Watch poller available"}
        except Exception:
            pass
        return {"available": False, "reason": "Monitoring infrastructure not ready"}

    def _check_code_project(self) -> dict[str, Any]:
        return {"available": True, "reason": "Terminal and filesystem available"}

    def _check_mcp(self) -> dict[str, Any]:
        try:
            from mini_kio.core.config import MCP_RUNTIME_ENABLED
            if MCP_RUNTIME_ENABLED:
                return {"available": True, "reason": "MCP runtime enabled"}
        except Exception:
            pass
        return {"available": False, "reason": "MCP runtime not enabled"}


class StatusRegistry:
    """Per-template status tracking.

    Tracks:
    - structurally_valid: YAML parsed and validated
    - runtime_proven: actually executed successfully at least once
    - candidate: not yet validated
    - blocked: missing provider/credential/capability
    - failed: last execution failed
    - deprecated: superseded by another template

    Plus: trigger_status, capability_status, credential_status,
    verification_status, last_runtime_test, failure_reason.
    """

    def __init__(self) -> None:
        self._statuses: dict[str, dict[str, Any]] = {}

    def get_status(self, template_id: str) -> dict[str, Any]:
        """Get the current status of a template."""
        if template_id not in self._statuses:
            return {
                "execution_status": "candidate",
                "trigger_status": "not_implemented",
                "capability_status": "unknown",
                "credential_status": "unknown",
                "verification_status": "unknown",
                "last_runtime_test": None,
                "failure_reason": None,
            }
        return dict(self._statuses[template_id])

    def set_status(
        self,
        template_id: str,
        execution_status: str | None = None,
        trigger_status: str | None = None,
        capability_status: str | None = None,
        credential_status: str | None = None,
        verification_status: str | None = None,
        last_runtime_test: float | None = None,
        failure_reason: str | None = None,
    ) -> None:
        """Update the status of a template."""
        if template_id not in self._statuses:
            self._statuses[template_id] = {
                "execution_status": "candidate",
                "trigger_status": "not_implemented",
                "capability_status": "unknown",
                "credential_status": "unknown",
                "verification_status": "unknown",
                "last_runtime_test": None,
                "failure_reason": None,
            }

        status = self._statuses[template_id]
        if execution_status is not None:
            status["execution_status"] = execution_status
        if trigger_status is not None:
            status["trigger_status"] = trigger_status
        if capability_status is not None:
            status["capability_status"] = capability_status
        if credential_status is not None:
            status["credential_status"] = credential_status
        if verification_status is not None:
            status["verification_status"] = verification_status
        if last_runtime_test is not None:
            status["last_runtime_test"] = last_runtime_test
        if failure_reason is not None:
            status["failure_reason"] = failure_reason

    def record_success(self, template_id: str) -> None:
        """Record a successful execution."""
        self.set_status(
            template_id,
            execution_status="runtime_proven",
            last_runtime_test=time.time(),
            failure_reason=None,
        )

    def record_failure(self, template_id: str, reason: str) -> None:
        """Record a failed execution."""
        self.set_status(
            template_id,
            execution_status="failed",
            last_runtime_test=time.time(),
            failure_reason=reason,
        )

    def record_blocked(self, template_id: str, reason: str) -> None:
        """Record that a template is blocked."""
        self.set_status(
            template_id,
            execution_status="blocked",
            failure_reason=reason,
        )

    def all_statuses(self) -> dict[str, dict[str, Any]]:
        """Get all template statuses."""
        return dict(self._statuses)

    def summary(self) -> dict[str, int]:
        """Get a summary count of statuses."""
        counts: dict[str, int] = {}
        for status in self._statuses.values():
            exec_status = status.get("execution_status", "candidate")
            counts[exec_status] = counts.get(exec_status, 0) + 1
        return counts
