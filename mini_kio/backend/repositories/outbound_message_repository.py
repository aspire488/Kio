import logging
from datetime import datetime, timezone
from typing import List, Dict, Optional

from mini_kio.backend.models import OutboundMessageModel
from mini_kio.backend.db import db_session

logger = logging.getLogger(__name__)


class OutboundMessageRepository:
    """Persistence for the general outbound-communication capability
    (draft -> sent/failed lifecycle). One table for every provider; the
    provider only changes HOW a message is delivered, never the record."""

    def create_draft(self, recipient: str, body: str, chat_id: str,
                     channel: str = "telegram", user_id: str = "") -> OutboundMessageModel:
        with db_session() as db:
            msg = OutboundMessageModel(
                recipient=recipient, channel=channel, body=body,
                status="draft", chat_id=chat_id, user_id=user_id,
            )
            db.add(msg)
            db.flush()
            return msg

    def pending_draft(self, chat_id: str) -> Optional[OutboundMessageModel]:
        with db_session() as db:
            return (
                db.query(OutboundMessageModel)
                .filter(OutboundMessageModel.chat_id == chat_id,
                        OutboundMessageModel.status == "draft")
                .order_by(OutboundMessageModel.created_at.desc())
                .first()
            )

    def list_active(self, chat_id: str) -> List[Dict]:
        with db_session() as db:
            rows = (
                db.query(OutboundMessageModel)
                .filter(OutboundMessageModel.chat_id == chat_id,
                        OutboundMessageModel.status.in_(("draft", "sent")))
                .order_by(OutboundMessageModel.created_at.desc())
                .limit(10)
                .all()
            )
            return [
                {"id": r.id, "recipient": r.recipient, "channel": r.channel,
                 "body": r.body, "status": r.status}
                for r in rows
            ]

    def mark_sent(self, message_id: int):
        with db_session() as db:
            row = db.query(OutboundMessageModel).filter(OutboundMessageModel.id == message_id).first()
            if row:
                row.status = "sent"
                row.sent_at = datetime.now(timezone.utc)
                row.failure_reason = None

    def mark_failed(self, message_id: int, reason: str):
        with db_session() as db:
            row = db.query(OutboundMessageModel).filter(OutboundMessageModel.id == message_id).first()
            if row:
                row.status = "failed"
                row.failure_reason = reason[:480]
