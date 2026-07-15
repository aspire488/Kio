"""BrowserProvider — wraps browser_operator.py under ExecutionProvider contract."""

from __future__ import annotations

import logging
from typing import Any

from mini_kio.core.provider_contract import (
    ExecutionProvider, ProviderHealth, ProviderCapability,
)
from mini_kio.core.browser_operator import (
    play_youtube, search_youtube, BROWSER_OPERATOR_DESCRIPTOR,
)

logger = logging.getLogger(__name__)
_DESC = BROWSER_OPERATOR_DESCRIPTOR


class BrowserProvider(ExecutionProvider):
    def id(self) -> str:
        return "browser"

    def capabilities(self) -> list[ProviderCapability]:
        return [
            ProviderCapability(name="play_youtube", category="external_open",
                               timeout_s=_DESC.get("timeout_seconds", 10),
                               ram_budget_mb=int(_DESC.get("ram_budget_mb", 8))),
            ProviderCapability(name="search_youtube", category="external_open",
                               timeout_s=_DESC.get("timeout_seconds", 10),
                               ram_budget_mb=int(_DESC.get("ram_budget_mb", 8))),
        ]

    def health(self) -> ProviderHealth:
        return ProviderHealth.HEALTHY

    def execute(self, action: str, target: str, **kwargs: Any) -> dict[str, Any]:
        if action == "play_youtube":
            return dict(play_youtube(target))
        elif action == "search_youtube":
            return dict(search_youtube(target))
        return {"success": False, "message": f"BrowserProvider: unknown action {action}"}

    def verify(self, action: str, result: dict[str, Any]) -> dict[str, Any]:
        result.setdefault("probe_used", "browser_action")
        if result.get("success"):
            result.setdefault("verification_status", "passed")
            result.setdefault("outcome_class", "SUCCESS")
        else:
            result.setdefault("verification_status", "failed")
            result.setdefault("outcome_class", "FAILURE")
        return result
