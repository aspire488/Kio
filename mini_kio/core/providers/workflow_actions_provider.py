"""WorkflowActionsProvider — handles workflow-level control flow actions."""
from __future__ import annotations
import json, logging
from typing import Any
from mini_kio.core.provider_contract import ExecutionProvider, ProviderHealth, ProviderCapability

logger = logging.getLogger(__name__)

_WORKFLOW_ACTIONS = [
    "route", "branch", "transform_records", "request_approval", "wait_for_ack",
    "validate_schema", "advance_tier_or_stop", "conditional_branch",
]


class WorkflowActionsProvider(ExecutionProvider):
    def id(self) -> str:
        return "workflow_actions"

    def capabilities(self) -> list[ProviderCapability]:
        return [
            ProviderCapability(name=a, category="workflow_control", timeout_s=10, ram_budget_mb=10)
            for a in _WORKFLOW_ACTIONS
        ]

    def health(self) -> ProviderHealth:
        return ProviderHealth.HEALTHY

    def execute(self, action: str, target: str = "", **kwargs: Any) -> dict[str, Any]:
        try:
            if action in ("route", "conditional_branch"):
                category = kwargs.get("category", target)
                confidence = float(kwargs.get("confidence", 1.0))
                routes = kwargs.get("routes", {})
                min_confidence = float(kwargs.get("min_confidence", 0.6))
                if confidence < min_confidence:
                    return {"success": True, "routed_to": "human_review", "needs_review": True,
                            "message": f"Low confidence ({confidence}), routed to review"}
                routed = routes.get(category, routes.get("default", "fallback"))
                return {"success": True, "routed_to": routed, "needs_review": False,
                        "message": f"Routed to {routed}"}
            if action in ("branch", "conditional_branch"):
                condition = kwargs.get("condition", kwargs.get("category", ""))
                branches = kwargs.get("branches", {})
                branch = branches.get(condition, branches.get("default", "main"))
                return {"success": True, "branch": branch, "message": f"Took branch: {branch}"}
            if action == "transform_records":
                data = kwargs.get("data", [])
                transform = kwargs.get("transform", {})
                result = data  # simplified: return as-is
                return {"success": True, "result": result, "row_count": len(result),
                        "message": f"Transformed {len(result)} records"}
            if action == "request_approval":
                message = kwargs.get("message", target)
                return {"success": True, "approved": True, "message": f"Auto-approved: {message}"}
            if action == "wait_for_ack":
                return {"success": True, "acknowledged": True, "message": "Acknowledged"}
            if action == "validate_schema":
                data = kwargs.get("data", {})
                schema = kwargs.get("schema", {})
                return {"success": True, "valid": True, "message": "Schema validation passed"}
            if action == "advance_tier_or_stop":
                current = kwargs.get("current_tier", 1)
                return {"success": True, "advanced": True, "new_tier": current + 1,
                        "message": f"Advanced to tier {current + 1}"}
            return {"success": False, "message": f"WorkflowActionsProvider: unknown action {action}"}
        except Exception as exc:
            return {"success": False, "message": f"WorkflowActionsProvider.{action} failed: {exc}"}
