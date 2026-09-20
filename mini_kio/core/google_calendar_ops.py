"""Google Calendar backend — Calendar API v3 via the existing Google OAuth credential.

This is the *Google* backend of KIO's calendar capability. KIO owns the
capability semantics; Google owns the external implementation. The local ICS
backend (`calendar_ops.py`) is untouched and remains the default.

Backend selection lives in the calendar capability branch of the capability
router (`app_operator.execute_capability`) — this module is only the Google
implementation and never decides on its own when it runs.

Auth: reuses the ONE existing Google OAuth client/credential
(`google_oauth.get_calendar_service()`). No second auth path.
"""

from __future__ import annotations

import logging
from datetime import datetime, timedelta, timezone
from typing import Any

logger = logging.getLogger(__name__)

BACKEND = "google"


def _iso(value: str) -> str:
    """Normalize a datetime string to RFC3339, which the Calendar API requires."""
    if not value:
        return ""
    text = str(value).strip()
    if text.endswith("Z"):
        return text[:-1] + "+00:00"
    try:
        parsed = datetime.fromisoformat(text)
    except ValueError:
        return text
    if parsed.tzinfo is None:
        parsed = parsed.astimezone()
    return parsed.isoformat()


def _event_summary(event: dict[str, Any]) -> dict[str, Any]:
    """Reduce a Calendar API event to the shape the local backend returns."""
    start = event.get("start", {}) or {}
    end = event.get("end", {}) or {}
    return {
        "uid": event.get("id", ""),
        "title": event.get("summary", "") or "(no title)",
        "start": start.get("dateTime") or start.get("date") or "",
        "end": end.get("dateTime") or end.get("date") or "",
        "location": event.get("location", "") or "",
        "status": event.get("status", ""),
        "html_link": event.get("htmlLink", ""),
        "calendar_id": event.get("_calendar_id", ""),
    }


def _service():
    from mini_kio.core.google_oauth import get_calendar_service
    return get_calendar_service()


def list_calendars() -> dict[str, Any]:
    """List the calendars on the authorized account."""
    try:
        service = _service()
        result = service.calendarList().list().execute()
        items = result.get("items", [])
        calendars = [{
            "id": c.get("id", ""),
            "summary": c.get("summary", ""),
            "primary": bool(c.get("primary")),
            "time_zone": c.get("timeZone", ""),
            "access_role": c.get("accessRole", ""),
        } for c in items]
        return {"success": True, "calendars": calendars, "count": len(calendars),
                "message": f"{len(calendars)} calendars available"}
    except Exception as exc:
        logger.warning("[GOOGLE_CALENDAR] list_calendars failed: %s", exc)
        return {"success": False, "message": f"Google Calendar list_calendars failed: {exc}"}


def list_events(calendar_id: str = "primary", max_results: int = 25,
                time_min: str = "", time_max: str = "", query: str = "") -> dict[str, Any]:
    """List events from Google Calendar."""
    try:
        service = _service()
        params: dict[str, Any] = {
            "calendarId": calendar_id or "primary",
            "maxResults": int(max_results),
            "singleEvents": True,
            "orderBy": "startTime",
        }
        now = datetime.now(timezone.utc)
        params["timeMin"] = _iso(time_min) if time_min else now.isoformat()
        if time_max:
            params["timeMax"] = _iso(time_max)
        if query:
            params["q"] = query
        result = service.events().list(**params).execute()
        events = []
        for item in result.get("items", []):
            item["_calendar_id"] = params["calendarId"]
            events.append(_event_summary(item))
        return {"success": True, "events": events, "count": len(events),
                "backend": BACKEND, "calendar_id": params["calendarId"],
                "message": f"{len(events)} events from Google Calendar"}
    except Exception as exc:
        logger.warning("[GOOGLE_CALENDAR] list_events failed: %s", exc)
        return {"success": False, "message": f"Google Calendar list_events failed: {exc}"}


def today_events(window: int = 8) -> dict[str, Any]:
    """Today's Google Calendar events within a window of hours from now."""
    now = datetime.now(timezone.utc)
    start = now - timedelta(minutes=now.minute, seconds=now.second)
    end = now + timedelta(hours=int(window))
    result = list_events(calendar_id="primary", max_results=50,
                         time_min=start.isoformat(), time_max=end.isoformat())
    if not result.get("success"):
        return result
    return {"success": True, "events": result.get("events", []),
            "count": result.get("count", 0), "window_hours": int(window),
            "date": datetime.now().strftime("%Y-%m-%d"), "backend": BACKEND,
            "message": f"{result.get('count', 0)} events today (next {window}h) from Google Calendar"}


def upcoming_within(minutes: int = 60) -> dict[str, Any]:
    """Google Calendar events in the next N minutes."""
    now = datetime.now(timezone.utc)
    end = now + timedelta(minutes=int(minutes))
    result = list_events(calendar_id="primary", max_results=25,
                         time_min=now.isoformat(), time_max=end.isoformat())
    if not result.get("success"):
        return result
    return {"success": True, "events": result.get("events", []),
            "count": result.get("count", 0), "minutes": int(minutes), "backend": BACKEND,
            "message": f"{result.get('count', 0)} events in next {minutes} minutes from Google Calendar"}


def get_event(event_id: str, calendar_id: str = "primary") -> dict[str, Any]:
    """Fetch one Google Calendar event by id.

    A deleted (non-recurring) event is NOT a 404: the Calendar API returns it
    with status "cancelled". Reporting that as "found" would make every
    delete-then-verify check pass when the event is in fact gone, so a
    cancelled event is reported as not found.
    """
    if not event_id:
        return {"success": False, "message": "get_event: missing event id"}
    try:
        service = _service()
        item = service.events().get(calendarId=calendar_id or "primary",
                                    eventId=event_id).execute()
        item["_calendar_id"] = calendar_id or "primary"
        if str(item.get("status", "")).lower() == "cancelled":
            return {"success": False, "cancelled": True, "event_id": event_id,
                    "event": _event_summary(item), "backend": BACKEND,
                    "message": f"Event {event_id} is cancelled (deleted)"}
        return {"success": True, "event": _event_summary(item), "backend": BACKEND,
                "message": f"Found event: {item.get('summary', event_id)}"}
    except Exception as exc:
        logger.warning("[GOOGLE_CALENDAR] get_event failed: %s", exc)
        return {"success": False, "message": f"Google Calendar get_event failed: {exc}"}


def create_event(title: str = "", start: str = "", end: str = "",
                 location: str = "", description: str = "",
                 calendar_id: str = "primary", default_min: int = 60,
                 attendees: list[str] | None = None) -> dict[str, Any]:
    """Create a Google Calendar event."""
    if not title:
        return {"success": False, "message": "create_event: missing title"}
    try:
        if not start:
            start = datetime.now().astimezone().isoformat()
        if not end:
            try:
                start_dt = datetime.fromisoformat(_iso(start))
                end = (start_dt + timedelta(minutes=int(default_min))).isoformat()
            except ValueError:
                end = (datetime.now().astimezone() + timedelta(minutes=int(default_min))).isoformat()
        body: dict[str, Any] = {
            "summary": title,
            "start": {"dateTime": _iso(start)},
            "end": {"dateTime": _iso(end)},
        }
        if location:
            body["location"] = location
        if description:
            body["description"] = description
        if attendees:
            body["attendees"] = [{"email": a} for a in attendees if a]
        service = _service()
        created = service.events().insert(calendarId=calendar_id or "primary",
                                          body=body).execute()
        created["_calendar_id"] = calendar_id or "primary"
        return {"success": True, "event": _event_summary(created),
                "event_id": created.get("id", ""), "backend": BACKEND,
                "message": f"Created Google Calendar event: {title}"}
    except Exception as exc:
        logger.warning("[GOOGLE_CALENDAR] create_event failed: %s", exc)
        return {"success": False, "message": f"Google Calendar create_event failed: {exc}"}


def update_event(event_id: str, calendar_id: str = "primary", **fields: Any) -> dict[str, Any]:
    """Patch a Google Calendar event. Only supplied fields are changed."""
    if not event_id:
        return {"success": False, "message": "update_event: missing event id"}
    body: dict[str, Any] = {}
    if fields.get("title"):
        body["summary"] = fields["title"]
    if fields.get("location"):
        body["location"] = fields["location"]
    if fields.get("description"):
        body["description"] = fields["description"]
    if fields.get("start"):
        body["start"] = {"dateTime": _iso(fields["start"])}
    if fields.get("end"):
        body["end"] = {"dateTime": _iso(fields["end"])}
    if not body:
        return {"success": False, "message": "update_event: no updatable fields supplied"}
    try:
        service = _service()
        updated = service.events().patch(calendarId=calendar_id or "primary",
                                         eventId=event_id, body=body).execute()
        updated["_calendar_id"] = calendar_id or "primary"
        return {"success": True, "event": _event_summary(updated), "backend": BACKEND,
                "message": f"Updated Google Calendar event: {updated.get('summary', event_id)}"}
    except Exception as exc:
        logger.warning("[GOOGLE_CALENDAR] update_event failed: %s", exc)
        return {"success": False, "message": f"Google Calendar update_event failed: {exc}"}


def delete_event(event_id: str, calendar_id: str = "primary") -> dict[str, Any]:
    """Delete a Google Calendar event."""
    if not event_id:
        return {"success": False, "message": "delete_event: missing event id"}
    try:
        service = _service()
        service.events().delete(calendarId=calendar_id or "primary",
                                eventId=event_id).execute()
        return {"success": True, "deleted": event_id, "backend": BACKEND,
                "message": f"Deleted Google Calendar event: {event_id}"}
    except Exception as exc:
        logger.warning("[GOOGLE_CALENDAR] delete_event failed: %s", exc)
        return {"success": False, "message": f"Google Calendar delete_event failed: {exc}"}


def search_events(query: str, calendar_id: str = "primary",
                  max_results: int = 25) -> dict[str, Any]:
    """Search Google Calendar events by free-text query."""
    if not query:
        return {"success": False, "message": "search_events: missing query"}
    return list_events(calendar_id=calendar_id, max_results=max_results, query=query)


GOOGLE_CALENDAR_ACTIONS: dict[str, Any] = {
    "list_calendars": list_calendars,
    "list_events": list_events,
    "today_events": today_events,
    "upcoming_within": upcoming_within,
    "get_event": get_event,
    "create_event": create_event,
    "update_event": update_event,
    "delete_event": delete_event,
    "search_events": search_events,
}

__all__ = list(GOOGLE_CALENDAR_ACTIONS) + ["BACKEND", "GOOGLE_CALENDAR_ACTIONS"]
