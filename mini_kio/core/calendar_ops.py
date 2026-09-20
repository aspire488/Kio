"""Calendar operations — ICS-based local calendar provider.

Reads/writes standard .ics files. Compatible with Google Calendar,
Outlook, Apple Calendar (import/export). No external API needed for local use.
"""

from __future__ import annotations

import os
import time
import uuid
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Any


_ICS_DIR = Path(os.path.expanduser("~")) / ".kio" / "calendar"
_DEFAULT_ICS = _ICS_DIR / "kio_calendar.ics"


def _ensure_dir():
    _ICS_DIR.mkdir(parents=True, exist_ok=True)


def _parse_ics_dt(dt_str: str) -> datetime | None:
    """Parse ICS datetime string (local or UTC)."""
    for fmt in ("%Y%m%dT%H%M%S", "%Y%m%dT%H%M%SZ", "%Y-%m-%dT%H:%M:%S", "%Y-%m-%d %H:%M:%S"):
        try:
            return datetime.strptime(dt_str, fmt)
        except ValueError:
            continue
    return None


def _format_ics_dt(dt: datetime) -> str:
    return dt.strftime("%Y%m%dT%H%M%S")


def _parse_ics_file(path: Path | None = None) -> list[dict]:
    """Parse an ICS file into a list of event dicts."""
    path = path or _DEFAULT_ICS
    if not path.exists():
        return []

    events = []
    current: dict[str, Any] | None = None
    in_event = False

    for line in path.read_text(encoding="utf-8", errors="replace").splitlines():
        line = line.strip()
        if line == "BEGIN:VEVENT":
            in_event = True
            current = {}
        elif line == "END:VEVENT":
            in_event = False
            if current:
                events.append(current)
            current = None
        elif in_event and current is not None:
            if ":" in line:
                key, _, val = line.partition(":")
                key = key.split(";")[0]
                if key == "SUMMARY":
                    current["title"] = val
                elif key == "DTSTART":
                    current["start"] = val
                    dt = _parse_ics_dt(val.replace("Z", ""))
                    if dt:
                        current["start_dt"] = dt.isoformat()
                elif key == "DTEND":
                    current["end"] = val
                    dt = _parse_ics_dt(val.replace("Z", ""))
                    if dt:
                        current["end_dt"] = dt.isoformat()
                elif key == "LOCATION":
                    current["location"] = val
                elif key == "DESCRIPTION":
                    current["description"] = val
                elif key == "UID":
                    current["uid"] = val
                elif key == "STATUS":
                    current["status"] = val

    return events


def _write_ics(events: list[dict], path: Path | None = None) -> None:
    """Write events to an ICS file."""
    path = path or _DEFAULT_ICS
    _ensure_dir()
    lines = [
        "BEGIN:VCALENDAR",
        "VERSION:2.0",
        "PRODID:-//KIO//Calendar//EN",
        "CALSCALE:GREGORIAN",
    ]
    for ev in events:
        lines.append("BEGIN:VEVENT")
        lines.append(f"UID:{ev.get('uid', str(uuid.uuid4()))}")
        lines.append(f"SUMMARY:{ev.get('title', 'Untitled')}")
        if ev.get("start"):
            lines.append(f"DTSTART:{ev['start']}")
        if ev.get("end"):
            lines.append(f"DTEND:{ev['end']}")
        if ev.get("location"):
            lines.append(f"LOCATION:{ev['location']}")
        if ev.get("description"):
            lines.append(f"DESCRIPTION:{ev['description']}")
        if ev.get("status"):
            lines.append(f"STATUS:{ev['status']}")
        lines.append("END:VEVENT")
    lines.append("END:VCALENDAR")

    path.write_text("\r\n".join(lines) + "\r\n", encoding="utf-8")


def today_events(window: int = 8) -> dict[str, Any]:
    """Get today's events within a time window (hours from now)."""
    events = _parse_ics_file()
    now = datetime.now()
    start = now
    end = now + timedelta(hours=window)

    today = []
    for ev in events:
        ev_start = _parse_ics_dt(ev.get("start", "").replace("Z", ""))
        if ev_start and start <= ev_start <= end:
            today.append(ev)
        elif ev_start and ev_start.date() == now.date():
            today.append(ev)

    return {"success": True, "events": today, "count": len(today),
            "window_hours": window, "date": now.strftime("%Y-%m-%d"),
            "message": f"{len(today)} events today (next {window}h)"}


def get_event(event_id: str) -> dict[str, Any]:
    """Get a specific event by UID."""
    events = _parse_ics_file()
    for ev in events:
        if ev.get("uid") == event_id:
            return {"success": True, "event": ev, "message": f"Found event: {ev.get('title')}"}
    return {"success": False, "message": f"Event not found: {event_id}"}


def upcoming_within(minutes: int = 60) -> dict[str, Any]:
    """Get events within the next N minutes."""
    events = _parse_ics_file()
    now = datetime.now()
    end = now + timedelta(minutes=minutes)

    upcoming = []
    for ev in events:
        ev_start = _parse_ics_dt(ev.get("start", "").replace("Z", ""))
        if ev_start and now <= ev_start <= end:
            upcoming.append(ev)

    return {"success": True, "events": upcoming, "count": len(upcoming),
            "minutes": minutes,
            "message": f"{len(upcoming)} events in next {minutes} minutes"}


def run_command(title: str = "", start: str = "", end: str = "",
                location: str = "", default_min: int = 60,
                **kwargs) -> dict[str, Any]:
    """Create a calendar event (run_command/create_event action).

    start/end: ISO format datetime strings, or will use now + default_min.
    """
    _ensure_dir()
    now = datetime.now()

    if start:
        dt_start = _parse_ics_dt(start) or now
    else:
        dt_start = now

    if end:
        dt_end = _parse_ics_dt(end) or (dt_start + timedelta(minutes=default_min))
    else:
        dt_end = dt_start + timedelta(minutes=default_min)

    uid = str(uuid.uuid4())
    event = {
        "uid": uid,
        "title": title or "Untitled Event",
        "start": _format_ics_dt(dt_start),
        "end": _format_ics_dt(dt_end),
        "location": location,
        "status": "CONFIRMED",
    }

    events = _parse_ics_file()
    events.append(event)
    _write_ics(events)

    return {"success": True, "event": event, "uid": uid,
            "message": f"Created event: {title} ({dt_start.strftime('%Y-%m-%d %H:%M')})"}


def list_events() -> dict[str, Any]:
    """List all events in the calendar."""
    events = _parse_ics_file()
    return {"success": True, "events": events, "count": len(events),
            "message": f"{len(events)} events in calendar"}


def create_event(title: str = "", start: str = "", end: str = "",
                 location: str = "", **kwargs) -> dict[str, Any]:
    """Create event — alias for run_command."""
    return run_command(title=title, start=start, end=end, location=location)
