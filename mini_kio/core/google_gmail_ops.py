"""Google Gmail backend — Gmail API v1 via the existing Google OAuth credential.

KIO owns the email capability; Google owns the external implementation.
Uses the same OAuth client/account and the centralized scope registry
(`google_oauth.GOOGLE_SCOPES["gmail"]`). No second auth path.

Scope note: the `gmail` scope (gmail.modify) must be present on the stored
grant. It is requested through `google_oauth.ACTIVE_SCOPES`.
"""

from __future__ import annotations

import base64
import logging
from email.mime.text import MIMEText
from typing import Any

logger = logging.getLogger(__name__)

BACKEND = "google_gmail"


def _service():
    from mini_kio.core.google_oauth import get_gmail_service
    return get_gmail_service()


def _message_summary(msg: dict[str, Any]) -> dict[str, Any]:
    """Extract key fields from a Gmail message resource."""
    headers = {h["name"].lower(): h["value"] for h in (msg.get("payload", {}).get("headers", []) or [])}
    label_ids = msg.get("labelIds", [])
    return {
        "id": msg.get("id", ""),
        "thread_id": msg.get("threadId", ""),
        "subject": headers.get("subject", ""),
        "from": headers.get("from", ""),
        "to": headers.get("to", ""),
        "date": headers.get("date", ""),
        "snippet": msg.get("snippet", ""),
        "label_ids": label_ids,
        "is_unread": "UNREAD" in label_ids,
        "is_starred": "STARRED" in label_ids,
        "has_attachments": any(
            part.get("filename") for part in _iterate_parts(msg.get("payload", {}))
        ),
    }


def _iterate_parts(payload: dict) -> list[dict]:
    """Recursively iterate through message parts."""
    parts = []
    if payload.get("parts"):
        for part in payload["parts"]:
            parts.append(part)
            parts.extend(_iterate_parts(part))
    return parts


def _get_body_text(payload: dict) -> str:
    """Extract plain text body from a Gmail message payload."""
    if payload.get("mimeType") == "text/plain" and payload.get("body", {}).get("data"):
        return base64.urlsafe_b64decode(payload["body"]["data"]).decode("utf-8", errors="replace")
    for part in (payload.get("parts") or []):
        text = _get_body_text(part)
        if text:
            return text
    return ""


def _scope_error(exc: Exception) -> str:
    text = str(exc)
    if "insufficient" in text.lower() or "PERMISSION_DENIED" in text or "403" in text:
        return (
            "Google Gmail scope not granted on the stored credential — "
            "run the OAuth consent once to add the gmail scope "
            "(existing client/credential; no new OAuth identity). "
            f"Detail: {text[:200]}"
        )
    return f"Google Gmail API failed: {text[:300]}"


def list_messages(query: str = "", max_results: int = 25, label_ids: list[str] | None = None,
                  folder: str = "") -> dict[str, Any]:
    """List messages in the inbox (or matching a query).

    Args:
        query: Gmail search query string (same syntax as Gmail search bar).
        max_results: Maximum messages to return.
        label_ids: Filter by label IDs (e.g. ["INBOX"]).
        folder: Convenience alias: "inbox", "sent", "starred", "drafts", "trash".
    """
    try:
        service = _service()
        params: dict[str, Any] = {"userId": "me", "maxResults": int(max_results)}
        if query:
            params["q"] = query
        if label_ids:
            params["labelIds"] = label_ids
        elif folder:
            folder_map = {
                "inbox": "INBOX", "sent": "SENT", "starred": "STARRED",
                "drafts": "DRAFT", "trash": "TRASH", "spam": "SPAM",
            }
            label = folder_map.get(folder.lower(), folder.upper())
            params["labelIds"] = [label]
        result = service.users().messages().list(**params).execute()
        message_ids = result.get("messages", [])
        messages = []
        for mid in message_ids[:int(max_results)]:
            try:
                msg = service.users().messages().get(
                    userId="me", id=mid["id"], format="metadata",
                    metadataHeaders=["From", "To", "Subject", "Date"],
                ).execute()
                messages.append(_message_summary(msg))
            except Exception:
                messages.append({"id": mid["id"], "thread_id": mid.get("threadId", "")})
        return {
            "success": True, "messages": messages, "count": len(messages),
            "next_page_token": result.get("nextPageToken", ""),
            "total_estimate": result.get("resultSizeEstimate", 0),
            "backend": BACKEND,
            "message": f"{len(messages)} messages",
        }
    except Exception as exc:
        logger.warning("[GOOGLE_GMAIL] list_messages failed: %s", exc)
        return {"success": False, "message": _scope_error(exc)}


def get_message(message_id: str, format: str = "full") -> dict[str, Any]:
    """Fetch one Gmail message by ID.

    Args:
        message_id: The Gmail message ID.
        format: "full", "metadata", "minimal", or "raw".
    """
    if not message_id:
        return {"success": False, "message": "get_message: missing message_id"}
    try:
        service = _service()
        msg = service.users().messages().get(
            userId="me", id=message_id, format=format,
        ).execute()
        summary = _message_summary(msg)
        body_text = ""
        if format in ("full", "raw"):
            body_text = _get_body_text(msg.get("payload", {}))
        summary["body"] = body_text
        summary["snippet"] = msg.get("snippet", "")
        return {
            "success": True, "message": summary, "backend": BACKEND,
            "message_text": f"Message: {summary.get('subject', message_id)}",
        }
    except Exception as exc:
        logger.warning("[GOOGLE_GMAIL] get_message failed: %s", exc)
        return {"success": False, "message": _scope_error(exc)}


def send_message(to: str, subject: str, body: str,
                 cc: str = "", bcc: str = "") -> dict[str, Any]:
    """Send a Gmail message.

    Args:
        to: Recipient email address(es), comma-separated.
        subject: Message subject.
        body: Plain text body.
        cc: Optional CC address(es).
        bcc: Optional BCC address(es).
    """
    if not to or not subject:
        return {"success": False, "message": "send_message: need to and subject"}
    try:
        message = MIMEText(body)
        message["to"] = to
        message["subject"] = subject
        if cc:
            message["cc"] = cc
        if bcc:
            message["bcc"] = bcc
        raw = base64.urlsafe_b64encode(message.as_bytes()).decode("ascii")
        service = _service()
        sent = service.users().messages().send(
            userId="me", body={"raw": raw},
        ).execute()
        return {
            "success": True, "message_id": sent.get("id", ""),
            "thread_id": sent.get("threadId", ""), "backend": BACKEND,
            "message": f"Sent email to {to}: {subject}",
        }
    except Exception as exc:
        logger.warning("[GOOGLE_GMAIL] send_message failed: %s", exc)
        return {"success": False, "message": _scope_error(exc)}


def search_messages(query: str, max_results: int = 25) -> dict[str, Any]:
    """Search messages using Gmail query syntax."""
    if not query:
        return {"success": False, "message": "search_messages: missing query"}
    return list_messages(query=query, max_results=max_results)


def list_labels() -> dict[str, Any]:
    """List all Gmail labels."""
    try:
        service = _service()
        result = service.users().labels().list(userId="me").execute()
        labels = [
            {"id": l.get("id", ""), "name": l.get("name", ""), "type": l.get("type", "")}
            for l in result.get("labels", [])
        ]
        return {
            "success": True, "labels": labels, "count": len(labels),
            "backend": BACKEND,
            "message": f"{len(labels)} labels",
        }
    except Exception as exc:
        logger.warning("[GOOGLE_GMAIL] list_labels failed: %s", exc)
        return {"success": False, "message": _scope_error(exc)}


def trash_message(message_id: str) -> dict[str, Any]:
    """Move a message to trash."""
    if not message_id:
        return {"success": False, "message": "trash_message: missing message_id"}
    try:
        service = _service()
        result = service.users().messages().trash(userId="me", id=message_id).execute()
        return {
            "success": True, "message_id": result.get("id", ""),
            "backend": BACKEND,
            "message": f"Trashed message {message_id}",
        }
    except Exception as exc:
        logger.warning("[GOOGLE_GMAIL] trash_message failed: %s", exc)
        return {"success": False, "message": _scope_error(exc)}


def untrash_message(message_id: str) -> dict[str, Any]:
    """Restore a message from trash."""
    if not message_id:
        return {"success": False, "message": "untrash_message: missing message_id"}
    try:
        service = _service()
        result = service.users().messages().untrash(userId="me", id=message_id).execute()
        return {
            "success": True, "message_id": result.get("id", ""),
            "backend": BACKEND,
            "message": f"Restored message {message_id} from trash",
        }
    except Exception as exc:
        logger.warning("[GOOGLE_GMAIL] untrash_message failed: %s", exc)
        return {"success": False, "message": _scope_error(exc)}


def modify_labels(message_id: str, add_labels: list[str] | None = None,
                  remove_labels: list[str] | None = None) -> dict[str, Any]:
    """Add/remove labels from a message."""
    if not message_id:
        return {"success": False, "message": "modify_labels: missing message_id"}
    body: dict[str, Any] = {}
    if add_labels:
        body["addLabelIds"] = add_labels
    if remove_labels:
        body["removeLabelIds"] = remove_labels
    if not body:
        return {"success": False, "message": "modify_labels: no label changes specified"}
    try:
        service = _service()
        result = service.users().messages().modify(
            userId="me", id=message_id, body=body,
        ).execute()
        return {
            "success": True, "message_id": result.get("id", ""),
            "label_ids": result.get("labelIds", []), "backend": BACKEND,
            "message": f"Modified labels on message {message_id}",
        }
    except Exception as exc:
        logger.warning("[GOOGLE_GMAIL] modify_labels failed: %s", exc)
        return {"success": False, "message": _scope_error(exc)}


GOOGLE_GMAIL_ACTIONS: dict[str, Any] = {
    "list_messages": list_messages,
    "get_message": get_message,
    "send_message": send_message,
    "search_messages": search_messages,
    "list_labels": list_labels,
    "trash_message": trash_message,
    "untrash_message": untrash_message,
    "modify_labels": modify_labels,
}

__all__ = list(GOOGLE_GMAIL_ACTIONS) + ["BACKEND", "GOOGLE_GMAIL_ACTIONS"]
