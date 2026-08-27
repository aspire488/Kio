"""
reminders.py — General TIME-SCHEDULED NOTIFICATION primitive
(monitoring companion: watches observe CHANGE, reminders observe TIME).

One mechanism, one persistence table, one delivery path (the same outbound
poller that delivers watch notifications):

    remind me in 2 hours to X   -> persist (payload X, due = now + 2h)
    remind me at 5pm to X       -> persist (payload X, due = next 5pm)
    remind me tomorrow at 9 to X-> persist (payload X, due = tomorrow 9am)
    cancel my reminders         -> deactivate
    what reminders do I have    -> list

The runtime poller calls poll_reminders() on the same tick as poll_watches();
a due reminder is pushed through send_telegram_message and marked delivered.
Never a new scheduler — the SAME daemon loop, the SAME delivery, the SAME
per-user chat_id sink as the watch primitive.
"""

import logging
import re
from datetime import datetime, timedelta, timezone

from mini_kio.backend.repositories.reminder_repository import ReminderRepository
from mini_kio.monitoring.watches import send_telegram_message

logger = logging.getLogger(__name__)

_repo = ReminderRepository()

# Relative: "in 2 hours", "in 45 minutes", "in 3 days", "in a week",
# "in half an hour"
_REL_RE = re.compile(
    r"\bin\s+(?:(?P<half>half\s+an\s+hour)|(?P<one>an?\s+"
    r"(?P<one_unit>minute|hour|day|week))|"
    r"(?P<num>\d+(?:\.\d+)?)\s*(?P<unit>seconds?|minutes?|hours?|days?|weeks?))\b",
    re.I,
)

# Absolute clock: "at 5pm", "at 17:30", "at 9:15 am"
_AT_RE = re.compile(r"\bat\s+(\d{1,2})(?::(\d{2}))?\s*(am|pm)?\b", re.I)

# Day qualifiers: "tomorrow at 9", "tonight at 8", "tomorrow morning"
_DAY_RE = re.compile(r"\b(tomorrow|tonight)\b", re.I)

_UNIT_SECONDS = {
    "second": 1, "seconds": 1,
    "minute": 60, "minutes": 60,
    "hour": 3600, "hours": 3600,
    "day": 86400, "days": 86400,
    "week": 604800, "weeks": 604800,
}


def _parse_due(query: str, now=None):
    """Parse a time expression into an aware UTC datetime. Returns None when
    the query carries no usable trigger time."""
    now = now or datetime.now(timezone.utc)
    low = query.lower()

    m = _REL_RE.search(low)
    if m:
        if m.group("half"):
            return now + timedelta(minutes=30)
        if m.group("one"):
            return now + timedelta(seconds=_UNIT_SECONDS.get(m.group("one_unit"), 3600))
        num = float(m.group("num"))
        unit = (m.group("unit") or "minutes").rstrip("s") + "s"
        return now + timedelta(seconds=int(num * _UNIT_SECONDS.get(unit, 60)))

    day = _DAY_RE.search(low)
    day_delta = 1 if day and day.group(1) == "tomorrow" else 0

    am = _AT_RE.search(low)
    if am:
        hour = int(am.group(1))
        minute = int(am.group(2) or 0)
        suffix = (am.group(3) or "").lower()
        if suffix == "am" and hour == 12:
            hour = 0
        elif suffix == "pm" and hour != 12:
            hour += 12
        elif not suffix and hour < 8:
            hour += 12
        due = now.replace(hour=hour, minute=minute, second=0, microsecond=0)
        due += timedelta(days=day_delta)
        if due <= now:
            due += timedelta(days=1)
        return due

    if day:
        due = now.replace(hour=9, minute=0, second=0, microsecond=0) + timedelta(days=day_delta)
        if "afternoon" in low:
            due = due.replace(hour=14)
        elif "evening" in low or "night" in low:
            due = due.replace(hour=19)
        return due

    return None


def _extract_payload(query: str) -> str:
    """The reminder payload: whatever the user wants to be told. Strips the
    leading 'remind me ... to' scaffolding and trailing filler."""
    low = query.lower()
    for marker in (" to ", " about ", " that "):
        idx = low.rfind(marker)
        if idx != -1:
            return re.sub(r"\s*(please|\.|!|\?)?\s*$", "", query[idx + len(marker):].strip(), flags=re.I)
    for pat in (_REL_RE, _AT_RE):
        m = pat.search(query)
        if m:
            return re.sub(r"\s*(please|\.|!|\?)?\s*$", "", query[m.end():].strip(), flags=re.I)
    return ""


def _extract_reminder_command(query: str):
    """Returns (sub_action, target_text) for the reminder family:
       remind me in 2 hours to X      -> ("add", X)
       cancel my reminders            -> ("cancel", "")
       cancel the reminder about X    -> ("cancel", X)
       what reminders do I have       -> ("list", "")
    """
    low = query.lower().strip()
    # CANCEL must be checked before LIST: "cancel my reminders" contains the
    # words "my reminders" and a bare list catch-all would swallow it. The
    # cancel family has its own leading verb; list forms never carry one.
    if re.search(r"cancel\s+(?:my\s+|the\s+|that\s+|this\s+|all\s+(?:my\s+|the\s+)?)?reminders?|delete\s+(?:my\s+|the\s+|that\s+|this\s+|all\s+(?:my\s+|the\s+)?)?reminders?|remove\s+(?:my\s+|the\s+|that\s+|this\s+|all\s+(?:my\s+|the\s+)?)?reminders?|stop\s+(?:my\s+|the\s+|that\s+|this\s+|all\s+(?:my\s+|the\s+)?)?reminders?", low):
        m = re.search(r"(?:about|for)\s+(.+?)\s*$", low)
        return "cancel", (m.group(1).strip() if m else "")
    if re.search(r"what\s+reminders\s+do\s+i\s+have|list\s+my\s+reminders|show\s+my\s+reminders|what\s+are\s+my\s+reminders", low):
        return "list", ""
    if re.search(r"^\s*(?:please\s+|hey\s+|hey\s+kio\s+|can\s+you\s+|could\s+you\s+|will\s+you\s+)?remind\s+me\b", low):
        return "add", _extract_payload(query)
    return None, ""


def looks_like_reminder(query: str) -> bool:
    """Routing hook: True for the remind/cancel/list family. An 'add' needs a
    usable trigger time — 'remind me to call Sarah' with no when is a
    conversational incomplete request, not a schedulable reminder."""
    action, target = _extract_reminder_command(query)
    if action == "list":
        return True
    if action == "cancel":
        return True
    if action == "add":
        return bool(target) and _parse_due(query) is not None
    return False


def _describe_due(due_at) -> str:
    delta = due_at - datetime.now(timezone.utc)
    mins = int(delta.total_seconds() // 60)
    if mins <= 1:
        return "right now"
    if mins < 60:
        return "in %d minutes" % mins
    hrs = mins // 60
    if hrs < 48:
        return "in %d hours" % hrs
    return "in %d days" % (hrs // 24)


def reminder_answer(query: str, ctx=None, decision=None) -> dict:
    """Canonical time-notification owner: 'remind me in 2 hours to X' /
    'cancel my reminders' / 'what reminders do I have'. Persists to the
    reminders table; the background poller does the actual push."""
    action, target = _extract_reminder_command(query)

    chat_id = "terminal"
    channel = getattr(decision, "channel", "") or ""
    user_id = str(getattr(decision, "user_id", 0) or 0)
    if decision is not None and channel == "telegram" and user_id:
        chat_id = user_id

    if action == "list":
        rows = _repo.list_active(chat_id)
        if not rows:
            return {"success": True, "message": "You don't have any reminders set right now.",
                    "type": "reminder", "action": "list", "reminders": []}
        def _fmt(row):
            try:
                from datetime import datetime
                due = datetime.fromisoformat(row["due_at"])
                if due.tzinfo is None:
                    due = due.replace(tzinfo=timezone.utc)
                return "%s (%s)" % (row["text"], _describe_due(due))
            except Exception:
                return "%s (%s)" % (row["text"], row["due_at"])
        parts = [_fmt(r) for r in rows]
        return {"success": True,
                "message": "Your reminders: " + "; ".join(parts) + ".",
                "type": "reminder", "action": "list", "reminders": rows}

    if action == "cancel":
        if target:
            n = _repo.deactivate_by_text(target, chat_id)
            return {"success": n > 0,
                    "message": ("Cancelled %d reminder(s) about %s." % (n, target)) if n else ("No reminder about %s was set." % target),
                    "type": "reminder", "action": "cancel", "target": target, "cancelled": n}
        n = _repo.deactivate_by_text("", chat_id)
        return {"success": True,
                "message": "All reminders cancelled." if n else "You don't have any reminders set.",
                "type": "reminder", "action": "cancel", "cancelled": n}

    if action == "add":
        if not target:
            return {"success": False,
                    "message": "What should I remind you about? Like 'remind me in 2 hours to call Sarah'.",
                    "type": "reminder", "action": "add"}
        due = _parse_due(query)
        if due is None:
            return {"success": False,
                    "message": "When should I remind you? Like 'in 2 hours', 'at 5pm', or 'tomorrow at 9'.",
                    "type": "reminder", "action": "add"}
        _repo.add(target, due, chat_id, channel=channel, user_id=user_id)
        return {"success": True,
                "message": "Done — I'll remind you %s: %s." % (_describe_due(due), target),
                "type": "reminder", "action": "add", "target": target, "due_at": due.isoformat()}

    return {"success": False,
            "message": "Tell me what to remind you about — like 'remind me in 2 hours to call Sarah'.",
            "type": "reminder"}


def poll_reminders() -> dict:
    """Deliver every due reminder through the outbound channel and mark it
    delivered. Returns {checked, delivered}."""
    checked, delivered = 0, 0
    for reminder in _repo.due():
        checked += 1
        text = "Reminder: " + reminder.text
        if send_telegram_message(reminder.chat_id, text):
            delivered += 1
            _repo.mark_delivered(reminder.id)
            # Buffer as away event for return-surfacing
            try:
                from mini_kio.core.activation import record_away_event
                record_away_event(
                    source="reminder",
                    description=f"Reminder delivered: {reminder.text[:80]}",
                    urgency="medium",
                )
            except Exception:
                pass
            logger.info("[REMINDER_POLL] id=%s due=%s delivered=%s",
                        reminder.id, reminder.due_at, delivered)
    return {"checked": checked, "delivered": delivered}
