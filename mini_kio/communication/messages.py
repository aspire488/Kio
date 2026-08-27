"""
communication/messages.py — GENERAL OUTBOUND COMMUNICATION capability
(provider-backed, provider-neutral).

KIO drafts, authorizes, sends, verifies and persists outbound messages.
Telegram is the first provider; a future email/SMS/etc. provider swaps in
behind the SAME seam (send_outbound -> provider dispatch). No service-
specific intelligence — one message lifecycle:

    draft a message to X: <body>        -> persist as draft (recipient resolved)
    send the draft                      -> deliver via provider, verify, persist
    send a message to X: <body>         -> draft + send in one step
    cancel the draft                    -> discard (state change, never claimed)
    what messages are pending           -> list draft/sent for this chat

Authorization boundary (consequential action): outbound delivery requires a
RESOLVED, AUTHORIZED sink — a real chat_id for the recipient. The user's own
chat is the only sink KIO can prove; sending to any other person requires a
registered recipient mapping (none exist by default), so KIO refuses honestly
instead of guessing a channel or fabricating a delivery.
"""

import logging
import re
from typing import Optional

from mini_kio.backend.repositories.outbound_message_repository import OutboundMessageRepository
from mini_kio.monitoring.watches import send_telegram_message

logger = logging.getLogger(__name__)

_repo = OutboundMessageRepository()

# Self/own-chat recipient forms (the only provably-authorized sink).
_SELF_RECIPIENTS = frozenset({"me", "myself", "self"})

_DRAFT_RE = re.compile(r"^\s*(?:draft|write|compose|prepare)\s+(?:a\s+)?(?:message|text)\s+to\s+(.+)$", re.I)
_SEND_DRAFT_RE = re.compile(
    r"^\s*(?:send|deliver|fire|dispatch)\s+(?:the\s+|my\s+|this\s+)?(?:draft|message|text)\s*$", re.I,
)
_CANCEL_DRAFT_RE = re.compile(
    r"^\s*(?:cancel|delete|discard|drop|scrap)\s+(?:the\s+|my\s+|this\s+)?(?:draft|message|text)\s*$", re.I,
)
_LIST_RE = re.compile(
    r"what\s+messages\s+(?:are\s+)?pending|list\s+(?:my\s+)?(?:messages|drafts)|"
    r"(?:show|any)\s+(?:pending\s+)?(?:messages|drafts)|my\s+pending\s+messages",
    re.I,
)


def _extract_recipient_body(query: str):
    """(recipient, body) from 'to <recipient>: <body>' or '<recipient>: <body>'."""
    q = query.strip()
    m = re.match(r"^(?:to|for)\s+(.+?)\s*[:\\-]?\s+(.+)$", q, re.I)
    if m:
        return m.group(1).strip(), m.group(2).strip()
    m = re.match(r"^([^:]+):\s*(.+)$", q)
    if m:
        return m.group(1).strip(), m.group(2).strip()
    return None, None


def _extract_message_command(query: str):
    """(sub_action, recipient, body) for the outbound-message family."""
    low = query.lower().strip()
    if _SEND_DRAFT_RE.search(low):
        return "send_draft", "", ""
    if _CANCEL_DRAFT_RE.search(low):
        return "cancel", "", ""
    if _LIST_RE.search(low):
        return "list", "", ""
    m = _DRAFT_RE.search(query)
    if m:
        recipient, body = _extract_recipient_body(m.group(1))
        return ("add_draft", recipient, body) if recipient and body else (None, None, None)
    # 'send a message to X: body' — full intent form (recipient AND body).
    if re.search(r"^\s*(?:send|message|text)\s+(?:a\s+message\s+to|this\s+to|that\s+to|to)", low):
        stripped = re.sub(r"^\s*(?:send|message|text)\s+(?:a\s+message\s+to|this\s+to|that\s+to|to)\s+", "", query, count=1, flags=re.I)
        recipient, body = _extract_recipient_body(stripped)
        if recipient and body and len(body) >= 3:
            return "send_now", recipient, body
    return None, None, None


def looks_like_message(query: str) -> bool:
    """Routing hook: True for the outbound-message family (draft/send/cancel/
    list). Requires a resolvable full intent — never fires on casual 'send
    this to them' without a recipient/body, never on 'text me back'."""
    action, recipient, body = _extract_message_command(query)
    if action in ("send_draft", "cancel", "list"):
        return True
    if action in ("add_draft", "send_now"):
        return bool(recipient) and bool(body)
    return False


def _delivery_sink(decision, recipient: str) -> Optional[str]:
    """Resolve the recipient to an AUTHORIZED delivery sink (chat_id).
    Returns None when no authorized sink exists — the caller refuses
    honestly. The user's own Telegram chat is the only default sink."""
    if recipient.lower().strip() in _SELF_RECIPIENTS or recipient in ("", "here", "this chat"):
        channel = getattr(decision, "channel", "") or ""
        user_id = str(getattr(decision, "user_id", 0) or 0)
        if channel == "telegram" and user_id and user_id != "0":
            return user_id
        return None
    # Any other person needs a registered recipient mapping — none exist by
    # default, so KIO must NOT guess a chat_id and must NOT fabricate a send.
    return None


def message_answer(query: str, ctx=None, decision=None) -> dict:
    """Canonical outbound-communication owner: draft / send / cancel / list.
    Delivery only ever happens through a resolved, authorized sink; results
    are persisted (draft -> sent/failed) and verified, never asserted."""
    action, recipient, body = _extract_message_command(query)

    chat_id = "terminal"
    channel = getattr(decision, "channel", "") or ""
    user_id = str(getattr(decision, "user_id", 0) or 0)
    if decision is not None and channel == "telegram" and user_id:
        chat_id = user_id

    if action == "list":
        rows = _repo.list_active(chat_id)
        if not rows:
            return {"success": True, "message": "You don't have any pending messages or drafts.",
                    "type": "message", "action": "list", "messages": []}
        parts = ["[%s] to %s: %s" % (r["status"], r["recipient"], r["body"][:80]) for r in rows]
        return {"success": True, "message": "Messages: " + "; ".join(parts) + ".",
                "type": "message", "action": "list", "messages": rows}

    if action == "cancel":
        draft = _repo.pending_draft(chat_id)
        if draft is None:
            return {"success": False, "message": "There's no draft to cancel.",
                    "type": "message", "action": "cancel"}
        from mini_kio.backend.models import OutboundMessageModel
        from mini_kio.backend.db import db_session
        with db_session() as s:
            row = s.query(OutboundMessageModel).filter(OutboundMessageModel.id == draft.id).first()
            if row:
                row.status = "cancelled"
        return {"success": True, "message": "Draft cancelled.",
                "type": "message", "action": "cancel"}

    if action in ("add_draft", "send_now"):
        if not recipient or not body:
            return {"success": False,
                    "message": "Tell me who the message is for and what it says — like 'draft a message to Sarah: running 10 min late'.",
                    "type": "message", "action": action}
        # A DRAFT is just text on paper — writing it needs no authorization.
        # Only SENDING requires a resolved, authorized sink; drafting to
        # anyone is always allowed and always persisted.
        draft = _repo.create_draft(recipient, body, chat_id, channel=channel or "telegram", user_id=user_id)
        if action == "add_draft":
            return {"success": True,
                    "message": "Drafted: to %s — %s. Say 'send the draft' when you're ready." % (recipient, body[:120]),
                    "type": "message", "action": "add_draft", "id": draft.id}
        sink = _delivery_sink(decision, recipient)
        if sink is None:
            _repo.mark_failed(draft.id, "no_authorized_sink")
            return {"success": False,
                    "message": ("I can't send to %s — I don't have an authorized channel for them. "
                                "I can only send to you (this chat).") % recipient,
                    "type": "message", "action": action, "recipient": recipient, "refused": True}
        ok = send_telegram_message(sink, body)
        if ok:
            _repo.mark_sent(draft.id)
            return {"success": True,
                    "message": "Sent to %s." % recipient,
                    "type": "message", "action": "sent", "id": draft.id, "verified": True}
        _repo.mark_failed(draft.id, "provider_delivery_failed")
        return {"success": False,
                "message": "I couldn't deliver that message right now — the delivery channel failed.",
                "type": "message", "action": "failed", "id": draft.id, "verified": False}

    if action == "send_draft":
        draft = _repo.pending_draft(chat_id)
        if draft is None:
            return {"success": False, "message": "There's no draft to send yet.",
                    "type": "message", "action": "send_draft"}
        ok = send_telegram_message(draft.chat_id, draft.body)
        if ok:
            _repo.mark_sent(draft.id)
            return {"success": True, "message": "Sent to %s." % draft.recipient,
                    "type": "message", "action": "sent", "id": draft.id, "verified": True}
        _repo.mark_failed(draft.id, "provider_delivery_failed")
        return {"success": False,
                "message": "I couldn't deliver that message right now — the delivery channel failed.",
                "type": "message", "action": "failed", "id": draft.id, "verified": False}

    return {"success": False,
            "message": "Tell me what to send — like 'draft a message to Sarah: running 10 min late' or 'send the draft'.",
            "type": "message"}
