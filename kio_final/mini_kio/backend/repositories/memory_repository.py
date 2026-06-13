import logging
from datetime import datetime, timezone
from typing import Optional, List

from sqlalchemy.orm import Session as DBSession

from mini_kio.backend.models import MessageModel
from mini_kio.backend.db import db_session

logger = logging.getLogger(__name__)


class MemoryRepository:
    def append(self, session_id: str, role: str, content: str) -> MessageModel:
        with db_session() as db:
            max_idx = (
                db.query(MessageModel.exchange_index)
                .filter(MessageModel.session_id == session_id)
                .order_by(MessageModel.exchange_index.desc())
                .first()
            )
            next_idx = (max_idx[0] + 1) if max_idx else 0
            msg = MessageModel(
                session_id=session_id,
                role=role,
                content=content,
                exchange_index=next_idx,
            )
            db.add(msg)
            db.flush()
            return msg

    def get_history(self, session_id: str) -> List[dict]:
        with db_session() as db:
            rows = (
                db.query(MessageModel)
                .filter(MessageModel.session_id == session_id)
                .order_by(MessageModel.id)
                .all()
            )
            return [{"role": r.role, "content": r.content, "timestamp": r.timestamp} for r in rows]

    def count(self, session_id: str) -> int:
        with db_session() as db:
            return db.query(MessageModel).filter(MessageModel.session_id == session_id).count()

    def first_user_message(self, session_id: str) -> Optional[str]:
        with db_session() as db:
            msg = (
                db.query(MessageModel)
                .filter(MessageModel.session_id == session_id, MessageModel.role == "user")
                .order_by(MessageModel.id)
                .first()
            )
            return msg.content if msg else None

    def last_n_messages(self, session_id: str, n: int) -> List[dict]:
        with db_session() as db:
            rows = (
                db.query(MessageModel)
                .filter(MessageModel.session_id == session_id)
                .order_by(MessageModel.id.desc())
                .limit(n)
                .all()[::-1]
            )
            return [{"role": r.role, "content": r.content, "timestamp": r.timestamp} for r in rows]

    def clear(self, session_id: str):
        with db_session() as db:
            db.query(MessageModel).filter(MessageModel.session_id == session_id).delete()
