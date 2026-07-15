"""SystemProvider — wraps system_operator.py under ExecutionProvider contract."""

from __future__ import annotations

import logging
from typing import Any

from mini_kio.core.provider_contract import ExecutionProvider, ProviderHealth, ProviderCapability
from mini_kio.core.system_operator import lock_system, shutdown_system, restart_system, recovery_runtime

logger = logging.getLogger(__name__)


class SystemProvider(ExecutionProvider):
    def id(self) -> str:
        return "system"

    def capabilities(self) -> list[ProviderCapability]:
        return [
            ProviderCapability(name="lock_system", category="system_control", timeout_s=10, ram_budget_mb=2),
            ProviderCapability(name="shutdown_system", category="destructive_system", timeout_s=10, ram_budget_mb=2),
            ProviderCapability(name="restart_system", category="destructive_system", timeout_s=10, ram_budget_mb=2),
            ProviderCapability(name="recovery_runtime", category="system_control", timeout_s=10, ram_budget_mb=2),
        ]

    def health(self) -> ProviderHealth:
        return ProviderHealth.HEALTHY

    def execute(self, action: str, target: str = "", **kwargs: Any) -> dict[str, Any]:
        if action == "lock_system":
            return dict(lock_system())
        elif action == "shutdown_system":
            return dict(shutdown_system(kwargs.get("delay", 0)))
        elif action == "restart_system":
            return dict(restart_system(kwargs.get("delay", 0)))
        elif action == "recovery_runtime":
            return dict(recovery_runtime(target))
        return {"success": False, "message": f"SystemProvider: unknown action {action}"}

    def verify(self, action: str, result: dict[str, Any]) -> dict[str, Any]:
        result.setdefault("probe_used", "system_control")
        result.setdefault("verification_status", "passed" if result.get("success") else "failed")
        result.setdefault("outcome_class", "SUCCESS" if result.get("success") else "FAILURE")
        return result
