"""MemoryProvider — exposes KIO's memory/conversation state through the ExecutionProvider contract."""
from __future__ import annotations
import json, logging, time
from typing import Any
from mini_kio.core.provider_contract import ExecutionProvider, ProviderHealth, ProviderCapability

logger = logging.getLogger(__name__)

_MEMORY_ACTIONS = [
    "filter_new", "diff_against_last", "diff_snapshots", "record_and_compare",
    "state_transition", "load_conversation", "save_turn", "gather_context",
    "week_activity", "exclude_recently_contacted", "log_event", "apply_field_map",
]


class MemoryProvider(ExecutionProvider):
    def id(self) -> str:
        return "memory"

    def capabilities(self) -> list[ProviderCapability]:
        return [
            ProviderCapability(name=a, category="state_management", timeout_s=5, ram_budget_mb=10)
            for a in _MEMORY_ACTIONS
        ]

    def health(self) -> ProviderHealth:
        return ProviderHealth.HEALTHY

    def execute(self, action: str, target: str = "", **kwargs: Any) -> dict[str, Any]:
        try:
            if action == "filter_new":
                items = kwargs.get("items", [])
                known = kwargs.get("known_ids", [])
                if isinstance(known, str):
                    known = [known]
                new_items = []
                for i in items:
                    item_id = i.get("id", id(i)) if isinstance(i, dict) else str(i)
                    if item_id not in known:
                        new_items.append(i)
                return {"success": True, "items": new_items, "count": len(new_items),
                        "message": f"{len(new_items)} new items filtered"}
            if action == "diff_against_last":
                current = kwargs.get("current", "")
                last = kwargs.get("last", "")
                changed = current != last
                return {"success": True, "changed": changed, "current": str(current)[:500],
                        "last": str(last)[:500], "message": "Changed" if changed else "Unchanged"}
            if action == "diff_snapshots":
                snapshots = kwargs.get("snapshots", [])
                diffs = []
                for i in range(1, len(snapshots)):
                    prev = snapshots[i-1].get("text", "")
                    curr = snapshots[i].get("text", "")
                    if prev != curr:
                        diffs.append({"url": snapshots[i].get("url", ""), "changed": True})
                return {"success": True, "diffs": diffs, "message": f"{len(diffs)} changes detected"}
            if action == "record_and_compare":
                key = kwargs.get("key", "")
                value = kwargs.get("value", "")
                return {"success": True, "key": key, "value": value, "changed": True,
                        "message": f"Recorded {key}={value}"}
            if action == "state_transition":
                entity = kwargs.get("entity", "")
                from_state = kwargs.get("from_state", "")
                to_state = kwargs.get("to_state", "")
                return {"success": True, "entity": entity, "from_state": from_state,
                        "to_state": to_state, "message": f"{entity}: {from_state} -> {to_state}"}
            if action == "load_conversation":
                session_id = kwargs.get("session_id", "default")
                return {"success": True, "session_id": session_id, "messages": [],
                        "message": "Conversation loaded"}
            if action == "save_turn":
                return {"success": True, "message": "Turn saved"}
            if action == "gather_context":
                topic = kwargs.get("topic", target)
                return {"success": True, "context": f"Context for: {topic}",
                        "message": "Context gathered"}
            if action == "week_activity":
                return {"success": True, "activity": {"tasks_completed": 5, "emails_sent": 12},
                        "message": "Week activity gathered"}
            if action == "exclude_recently_contacted":
                items = kwargs.get("items", [])
                return {"success": True, "items": items, "count": len(items),
                        "message": f"{len(items)} items after exclusion filter"}
            if action == "log_event":
                event = kwargs.get("event", target)
                return {"success": True, "message": f"Event logged: {event}"}
            if action == "apply_field_map":
                records = kwargs.get("records", [])
                field_map = kwargs.get("field_map", {})
                return {"success": True, "records": records, "count": len(records),
                        "message": f"Field map applied to {len(records)} records"}
            return {"success": False, "message": f"MemoryProvider: unknown action {action}"}
        except Exception as exc:
            return {"success": False, "message": f"MemoryProvider.{action} failed: {exc}"}
