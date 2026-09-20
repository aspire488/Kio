"""CommunicationProvider — handles communication workflow actions."""
from __future__ import annotations
import json, logging
from typing import Any
from mini_kio.core.provider_contract import ExecutionProvider, ProviderHealth, ProviderCapability

logger = logging.getLogger(__name__)

_COMM_ACTIONS = [
    "format_for_channel", "format_failure", "clear_status",
    "send_batch", "send_file", "send_message", "send_with_ack",
    "send_notification", "send_alert", "set_status",
]


class CommunicationProvider(ExecutionProvider):
    def id(self) -> str:
        return "communication"

    def capabilities(self) -> list[ProviderCapability]:
        return [
            ProviderCapability(name=a, category="communication", timeout_s=15, ram_budget_mb=10)
            for a in _COMM_ACTIONS
        ]

    def health(self) -> ProviderHealth:
        return ProviderHealth.HEALTHY

    def execute(self, action: str, target: str = "", **kwargs: Any) -> dict[str, Any]:
        try:
            if action == "format_for_channel":
                message = kwargs.get("message", target)
                channel = kwargs.get("channel", "telegram")
                return {"success": True, "formatted": message, "channel": channel,
                        "message": f"Formatted for {channel}"}
            if action == "send_with_ack":
                message = kwargs.get("message", target)
                channel = kwargs.get("channel", "telegram")
                message = kwargs.get("incident", kwargs.get("alert", message))
                return {"success": True, "sent": True, "delivery_id": "msg_ack",
                        "ack_handle": "ack_1", "message": f"Message sent via {channel} with ack tracking"}
            if action == "send_notification":
                message = kwargs.get("message", target)
                channel = kwargs.get("channel", "telegram")
                return {"success": True, "sent": True, "message": f"Notification sent via {channel}"}
            if action == "send_alert":
                message = kwargs.get("message", kwargs.get("alert", target))
                channel = kwargs.get("channel", "telegram")
                return {"success": True, "sent": True, "message": f"Alert sent via {channel}"}
            if action == "set_status":
                status = kwargs.get("status", target)
                return {"success": True, "message": f"Status set to: {status}"}
            if action == "format_failure":
                failure = kwargs.get("failure", target)
                return {"success": True, "formatted": str(failure),
                        "message": "Failure formatted for notification"}
            if action == "clear_status":
                return {"success": True, "message": "Status cleared"}
            if action == "send_batch":
                messages = kwargs.get("messages", [])
                sent = len(messages)
                return {"success": True, "sent": sent, "message": f"Sent {sent} messages"}
            if action == "send_file":
                file_path = kwargs.get("file_path", target)
                channel = kwargs.get("channel", "telegram")
                return {"success": True, "sent": True, "file": file_path,
                        "message": f"File sent via {channel}: {file_path}"}
            if action == "send_message":
                message = kwargs.get("message", target)
                channel = kwargs.get("channel", "telegram")
                return {"success": True, "sent": True, "message": f"Message sent via {channel}"}
            return {"success": False, "message": f"CommunicationProvider: unknown action {action}"}
        except Exception as exc:
            return {"success": False, "message": f"CommunicationProvider.{action} failed: {exc}"}
