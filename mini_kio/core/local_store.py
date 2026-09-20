"""Local store operations — task tracker, CRM, and ticket store.

Clean provider boundary: local JSON-backed, swappable to external APIs later.
No fake data. Real CRUD with search and filtering.
"""

from __future__ import annotations

import json
import os
import time
import uuid
from pathlib import Path
from typing import Any


_STORE_DIR = Path(os.path.expanduser("~")) / ".kio" / "stores"


def _ensure_dir():
    _STORE_DIR.mkdir(parents=True, exist_ok=True)


def _load(name: str) -> list[dict]:
    f = _STORE_DIR / f"{name}.json"
    if f.exists():
        try:
            return json.loads(f.read_text(encoding="utf-8"))
        except Exception:
            return []
    return []


def _save(name: str, data: list[dict]) -> None:
    _ensure_dir()
    f = _STORE_DIR / f"{name}.json"
    f.write_text(json.dumps(data, ensure_ascii=False, indent=2), encoding="utf-8")


# ── Task Tracker ─────────────────────────────────────────────────────────────

def task_create(title: str, description: str = "", priority: str = "medium",
                due: str = "", tags: list[str] | None = None,
                **kwargs) -> dict[str, Any]:
    """Create a task with optional priority, due date, and tags."""
    _ensure_dir()
    tasks = _load("tasks")
    uid = str(uuid.uuid4())[:8]
    task = {
        "id": uid,
        "title": title,
        "description": description,
        "priority": priority,
        "status": "pending",
        "due": due,
        "tags": tags or [],
        "created_at": time.time(),
        "updated_at": time.time(),
    }
    tasks.append(task)
    _save("tasks", tasks)
    return {"success": True, "task": task, "message": f"Task created: {uid} — {title}"}


def task_list(status: str = "pending", priority: str | None = None,
              tag: str | None = None, limit: int = 50) -> dict[str, Any]:
    """List tasks with optional filters."""
    tasks = _load("tasks")
    filtered = []
    for t in tasks:
        if status and t.get("status") != status:
            continue
        if priority and t.get("priority") != priority:
            continue
        if tag and tag not in t.get("tags", []):
            continue
        filtered.append(t)
        if len(filtered) >= limit:
            break

    return {"success": True, "tasks": filtered, "count": len(filtered),
            "total": len(tasks), "message": f"{len(filtered)} tasks (status={status})"}


def task_update(task_id: str, **fields) -> dict[str, Any]:
    """Update a task by ID."""
    tasks = _load("tasks")
    for i, t in enumerate(tasks):
        if t.get("id") == task_id:
            for k, v in fields.items():
                if k in ("title", "description", "priority", "status", "due", "tags"):
                    t[k] = v
            t["updated_at"] = time.time()
            tasks[i] = t
            _save("tasks", tasks)
            return {"success": True, "task": t, "message": f"Task {task_id} updated"}
    return {"success": False, "message": f"Task not found: {task_id}"}


def task_complete(task_id: str) -> dict[str, Any]:
    """Mark a task as complete."""
    return task_update(task_id, status="complete")


def task_delete(task_id: str) -> dict[str, Any]:
    """Delete a task by ID."""
    tasks = _load("tasks")
    before = len(tasks)
    tasks = [t for t in tasks if t.get("id") != task_id]
    if len(tasks) < before:
        _save("tasks", tasks)
        return {"success": True, "message": f"Task {task_id} deleted"}
    return {"success": False, "message": f"Task not found: {task_id}"}


def task_search(query: str) -> dict[str, Any]:
    """Full-text search across task title, description, and tags."""
    tasks = _load("tasks")
    q = query.lower()
    results = []
    for t in tasks:
        text = (t.get("title", "") + " " + t.get("description", "") +
                " " + " ".join(t.get("tags", []))).lower()
        if q in text:
            results.append(t)
    return {"success": True, "tasks": results, "count": len(results),
            "query": query, "message": f"{len(results)} tasks match '{query}'"}


# ── CRM ──────────────────────────────────────────────────────────────────────

def crm_add(name: str, email: str = "", phone: str = "",
            company: str = "", notes: str = "",
            tags: list[str] | None = None, **kwargs) -> dict[str, Any]:
    """Add a contact to the CRM."""
    _ensure_dir()
    contacts = _load("crm")
    uid = str(uuid.uuid4())[:8]
    contact = {
        "id": uid,
        "name": name,
        "email": email,
        "phone": phone,
        "company": company,
        "notes": notes,
        "tags": tags or [],
        "created_at": time.time(),
        "updated_at": time.time(),
    }
    contacts.append(contact)
    _save("crm", contacts)
    return {"success": True, "contact": contact, "message": f"Contact added: {name}"}


def crm_list(company: str | None = None, tag: str | None = None,
             limit: int = 50) -> dict[str, Any]:
    """List CRM contacts with optional filters."""
    contacts = _load("crm")
    filtered = []
    for c in contacts:
        if company and c.get("company", "").lower() != company.lower():
            continue
        if tag and tag not in c.get("tags", []):
            continue
        filtered.append(c)
        if len(filtered) >= limit:
            break
    return {"success": True, "contacts": filtered, "count": len(filtered),
            "total": len(contacts), "message": f"{len(filtered)} contacts"}


def crm_search(query: str) -> dict[str, Any]:
    """Search CRM contacts by name, email, company, or notes."""
    contacts = _load("crm")
    q = query.lower()
    results = []
    for c in contacts:
        text = (c.get("name", "") + " " + c.get("email", "") + " " +
                c.get("company", "") + " " + c.get("notes", "")).lower()
        if q in text:
            results.append(c)
    return {"success": True, "contacts": results, "count": len(results),
            "query": query, "message": f"{len(results)} contacts match '{query}'"}


def crm_update(contact_id: str, **fields) -> dict[str, Any]:
    """Update a CRM contact by ID."""
    contacts = _load("crm")
    for i, c in enumerate(contacts):
        if c.get("id") == contact_id:
            for k, v in fields.items():
                if k in ("name", "email", "phone", "company", "notes", "tags"):
                    c[k] = v
            c["updated_at"] = time.time()
            contacts[i] = c
            _save("crm", contacts)
            return {"success": True, "contact": c, "message": f"Contact {contact_id} updated"}
    return {"success": False, "message": f"Contact not found: {contact_id}"}


# ── Tickets ──────────────────────────────────────────────────────────────────

def ticket_create(subject: str, body: str = "", status: str = "open",
                  priority: str = "medium", assignee: str = "",
                  tags: list[str] | None = None, **kwargs) -> dict[str, Any]:
    """Create a support ticket."""
    _ensure_dir()
    tickets = _load("tickets")
    uid = f"TKT-{str(uuid.uuid4())[:6].upper()}"
    ticket = {
        "id": uid,
        "subject": subject,
        "body": body,
        "status": status,
        "priority": priority,
        "assignee": assignee,
        "tags": tags or [],
        "created_at": time.time(),
        "updated_at": time.time(),
        "comments": [],
    }
    tickets.append(ticket)
    _save("tickets", tickets)
    return {"success": True, "ticket": ticket, "message": f"Ticket created: {uid} — {subject}"}


def ticket_list(status: str = "open", priority: str | None = None,
                limit: int = 50) -> dict[str, Any]:
    """List tickets with optional filters."""
    tickets = _load("tickets")
    filtered = []
    for t in tickets:
        if status and t.get("status") != status:
            continue
        if priority and t.get("priority") != priority:
            continue
        filtered.append(t)
        if len(filtered) >= limit:
            break
    return {"success": True, "tickets": filtered, "count": len(filtered),
            "total": len(tickets), "message": f"{len(filtered)} tickets"}


def ticket_update(ticket_id: str, **fields) -> dict[str, Any]:
    """Update a ticket by ID."""
    tickets = _load("tickets")
    for i, t in enumerate(tickets):
        if t.get("id") == ticket_id:
            for k, v in fields.items():
                if k in ("subject", "body", "status", "priority", "assignee", "tags"):
                    t[k] = v
            t["updated_at"] = time.time()
            tickets[i] = t
            _save("tickets", tickets)
            return {"success": True, "ticket": t, "message": f"Ticket {ticket_id} updated"}
    return {"success": False, "message": f"Ticket not found: {ticket_id}"}


def ticket_comment(ticket_id: str, author: str, body: str) -> dict[str, Any]:
    """Add a comment to a ticket."""
    tickets = _load("tickets")
    for i, t in enumerate(tickets):
        if t.get("id") == ticket_id:
            t.setdefault("comments", []).append({
                "author": author,
                "body": body,
                "timestamp": time.time(),
            })
            t["updated_at"] = time.time()
            tickets[i] = t
            _save("tickets", tickets)
            return {"success": True, "ticket": t,
                    "message": f"Comment added to {ticket_id}"}
    return {"success": False, "message": f"Ticket not found: {ticket_id}"}


def ticket_close(ticket_id: str) -> dict[str, Any]:
    """Close a ticket."""
    return ticket_update(ticket_id, status="closed")
