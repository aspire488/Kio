"""Memory operations — real implementations for workflow memory actions.

Uses the existing ~/.kio/memory/ JSON-file store per-key.
No new dependencies. No new engines.
"""

from __future__ import annotations

import json
import os
import time
from pathlib import Path
from typing import Any


_MEM_DIR = Path(os.path.expanduser("~")) / ".kio" / "memory"


def _load_mem(key: str) -> list[dict]:
    f = _MEM_DIR / f"{key}.json"
    if f.exists():
        try:
            return json.loads(f.read_text(encoding="utf-8"))
        except Exception:
            return []
    return []


def _save_mem(key: str, data: list[dict]) -> None:
    _MEM_DIR.mkdir(parents=True, exist_ok=True)
    f = _MEM_DIR / f"{key}.json"
    f.write_text(json.dumps(data, ensure_ascii=False, indent=2), encoding="utf-8")


def filter_new(items: list[dict], key: str = "filter_new",
               since_ts: float | None = None) -> dict[str, Any]:
    """Filter items to only those newer than the last-seen timestamp.

    Each item should have a 'timestamp' or 'id' field.
    Stores the latest timestamp seen for next call.
    """
    entries = _load_mem(key)
    since_ts = since_ts or 0

    new_items = []
    max_ts = since_ts
    for item in items:
        ts = item.get("timestamp", 0)
        if isinstance(ts, (int, float)) and ts > since_ts:
            new_items.append(item)
        elif isinstance(ts, str):
            new_items.append(item)
        else:
            new_items.append(item)
        if isinstance(ts, (int, float)) and ts > max_ts:
            max_ts = ts

    entries.append({"last_seen_ts": max_ts, "filtered_count": len(new_items),
                     "timestamp": time.time()})
    _save_mem(key, entries[-100:])

    return {"success": True, "new_items": new_items, "count": len(new_items),
            "message": f"Filtered {len(new_items)} new items from {len(items)} total"}


def week_activity(key: str = "events") -> dict[str, Any]:
    """Aggregate memory entries from the past 7 days.

    Returns daily counts and activity breakdown.
    """
    now = time.time()
    seven_days_ago = now - (7 * 24 * 3600)
    entries = _load_mem(key)

    daily: dict[str, list[dict]] = {}
    for entry in entries:
        ts = entry.get("timestamp", 0)
        if ts >= seven_days_ago:
            day = time.strftime("%Y-%m-%d", time.localtime(ts))
            daily.setdefault(day, []).append(entry)

    activity = {}
    total = 0
    for day in sorted(daily.keys()):
        count = len(daily[day])
        sources = {}
        for e in daily[day]:
            src = e.get("source", "unknown")
            sources[src] = sources.get(src, 0) + 1
        activity[day] = {"count": count, "sources": sources}
        total += count

    return {"success": True, "activity": activity, "total_entries": total,
            "days_with_activity": len(activity), "period_days": 7,
            "message": f"{total} entries across {len(activity)} days"}


def exclude_recently_contacted(contact_ids: list[str],
                                key: str = "contacts",
                                within_hours: int = 24) -> dict[str, Any]:
    """Exclude contacts that were stored within the last N hours."""
    entries = _load_mem(key)
    cutoff = time.time() - (within_hours * 3600)
    recent = set()
    for entry in entries:
        ts = entry.get("timestamp", 0)
        cid = entry.get("contact_id", entry.get("id", ""))
        if ts >= cutoff and cid:
            recent.add(cid)

    excluded = [cid for cid in contact_ids if cid in recent]
    remaining = [cid for cid in contact_ids if cid not in recent]

    return {"success": True, "excluded": excluded, "remaining": remaining,
            "excluded_count": len(excluded), "remaining_count": len(remaining),
            "message": f"Excluded {len(excluded)} recently contacted from {len(contact_ids)}"}


def apply_field_map(records: list[dict],
                    field_map: dict[str, str] | None = None,
                    transforms: dict[str, str] | None = None) -> dict[str, Any]:
    """Apply field mapping and type transforms to records.

    field_map: {"old_name": "new_name"} — rename fields
    transforms: {"field": "upper|lower|strip|int|float|str"} — type transforms
    """
    if not field_map and not transforms:
        return {"success": True, "mapped": records, "count": len(records),
                "message": "No transforms specified"}

    mapped = []
    for record in records:
        new_record = {}
        for k, v in record.items():
            new_key = field_map.get(k, k) if field_map else k
            if transforms and k in transforms:
                t = transforms[k]
                try:
                    if t == "upper":
                        v = str(v).upper()
                    elif t == "lower":
                        v = str(v).lower()
                    elif t == "strip":
                        v = str(v).strip()
                    elif t == "int":
                        v = int(v)
                    elif t == "float":
                        v = float(v)
                    elif t == "str":
                        v = str(v)
                except (ValueError, TypeError):
                    pass
            new_record[new_key] = v
        mapped.append(new_record)

    return {"success": True, "mapped": mapped, "count": len(mapped),
            "message": f"Mapped {len(mapped)} records"}


def diff_snapshots(snapshot_a: str, snapshot_b: str) -> dict[str, Any]:
    """Compare two memory snapshots and return differences."""
    entries_a = _load_mem(snapshot_a)
    entries_b = _load_mem(snapshot_b)

    contents_a = {e.get("content", ""): e for e in entries_a}
    contents_b = {e.get("content", ""): e for e in entries_b}

    added = [c for c in contents_b if c not in contents_a]
    removed = [c for c in contents_a if c not in contents_b]
    unchanged = [c for c in contents_a if c in contents_b]

    return {"success": True, "added": added, "removed": removed,
            "unchanged_count": len(unchanged),
            "added_count": len(added), "removed_count": len(removed),
            "snapshot_a_count": len(entries_a), "snapshot_b_count": len(entries_b),
            "message": f"Diff: {len(added)} added, {len(removed)} removed, {len(unchanged)} unchanged"}


def state_transition(current_state: str, trigger: str,
                     valid_transitions: dict[str, list[str]] | None = None) -> dict[str, Any]:
    """State machine for monitoring states.

    valid_transitions: {"state_a": ["trigger_1", "trigger_2"]} — which triggers
    are valid from each state. If None, allows all transitions.
    """
    if valid_transitions is None:
        valid_transitions = {
            "ok": ["degraded", "down", "recovered"],
            "degraded": ["down", "recovered", "ok"],
            "down": ["recovered", "degraded"],
            "recovered": ["ok", "degraded"],
        }

    allowed = valid_transitions.get(current_state, [])
    if trigger in allowed:
        new_state = f"{current_state}_{trigger}" if trigger not in ("ok", "recovered") else trigger
        return {"success": True, "from_state": current_state, "trigger": trigger,
                "to_state": new_state, "valid": True,
                "message": f"Transition: {current_state} -> {new_state}"}
    else:
        return {"success": True, "from_state": current_state, "trigger": trigger,
                "to_state": current_state, "valid": False,
                "message": f"Invalid transition: {current_state} --{trigger}--> (blocked). Allowed: {allowed}"}
