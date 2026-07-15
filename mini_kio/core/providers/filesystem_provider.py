"""FilesystemProvider — wraps file_operator.py under ExecutionProvider contract."""

from __future__ import annotations

import logging
from typing import Any

from mini_kio.core.provider_contract import ExecutionProvider, ProviderHealth, ProviderCapability
from mini_kio.core.file_operator import open_folder, create_file, list_directory

logger = logging.getLogger(__name__)


class FilesystemProvider(ExecutionProvider):
    def id(self) -> str:
        return "filesystem"

    def capabilities(self) -> list[ProviderCapability]:
        return [
            ProviderCapability(name="open_folder", category="external_open", timeout_s=10, ram_budget_mb=5),
        ]

    def health(self) -> ProviderHealth:
        return ProviderHealth.HEALTHY

    def execute(self, action: str, target: str, **kwargs: Any) -> dict[str, Any]:
        if action == "open_folder":
            return dict(open_folder(target))
        return {"success": False, "message": f"FilesystemProvider: unknown action {action}"}

    def verify(self, action: str, result: dict[str, Any]) -> dict[str, Any]:
        result.setdefault("probe_used", "filesystem_action")
        result.setdefault("verification_status", "passed" if result.get("success") else "failed")
        result.setdefault("outcome_class", "SUCCESS" if result.get("success") else "FAILURE")
        return result
