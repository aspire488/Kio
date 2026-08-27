import logging
from datetime import datetime, timezone
from typing import List, Dict

from mini_kio.backend.models import ReminderModel
from mini_kio.backend.db import db_session

logger = logging.getLogger(__name__)


class ReminderRepository:
    """Persistence for the time-scheduled notification primitive (same table
    pattern as the watch repository — one DB, one delivery sink)."""

    def add(self, text: str, due_at, chat_id: str, channel: str = "telegram",
            user_id: str = "") -> ReminderModel:
        with db_session() as db:
            reminder = ReminderModel(
                text=text, due_at=due_at, chat_id=chat_id, channel=channel,
                user_id=user_id, active=True,
            )
            db.add(reminder)
            db.flush()
            return reminder

    def deactivate(self, reminder_id: int) -> bool:
        with db_session() as db:
            row = db.query(ReminderModel).filter(ReminderModel.id == reminder_id).first()
            if row:
                row.active = False
                return True
            return False

    def deactivate_by_text(self, text: str, chat_id: str) -> int:
        with db_session() as db:
            rows = (
                db.query(ReminderModel)
                .filter(ReminderModel.chat_id == chat_id,
                        ReminderModel.active.is_(True))
                .all()
            )
            terms = {t for t in text.lower().split() if len(t) > 3}
            cancelled = 0
            for row in rows:
                if not terms or any(t in (row.text or "").lower() for t in terms):
                    row.active = False
                    cancelled += 1
            return cancelled

    def list_active(self, chat_id: str) -> List[Dict]:
        with db_session() as db:
            rows = (
                db.query(ReminderModel)
                .filter(ReminderModel.chat_id == chat_id, ReminderModel.active.is_(True))
                .order_by(ReminderModel.due_at)
                .all()
            )
            return [
                {"id": r.id, "text": r.text, "due_at": r.due_at.isoformat() if r.due_at else None}
                for r in rows
            ]

    def due(self, now=None) -> List[ReminderModel]:
        from datetime import datetime, timezone
        now = now or datetime.now(timezone.utc)
        with db_session() as db:
            return (
                db.query(ReminderModel)
                .filter(ReminderModel.active.is_(True),
                        ReminderModel.due_at <= now)
                .order_by(ReminderModel.due_at)
                .all()
            )

    def mark_delivered(self, reminder_id: int):
        from datetime import datetime, timezone
        with db_session() as db:
            row = db.query(ReminderModel).filter(ReminderModel.id == reminder_id).first()
            if row:
                row.active = False
                row.delivered_at = datetime.now(timezone.utc)
