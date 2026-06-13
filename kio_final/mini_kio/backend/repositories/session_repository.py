import logging
from datetime import datetime, timezone
from typing import Optional, List, Tuple

from sqlalchemy.orm import Session as DBSession

from mini_kio.backend.models import SessionModel, MessageModel
from mini_kio.backend.db import db_session

logger = logging.getLogger(__name__)


class SessionRepository:
    def get_or_create(self, session_id: str) -> SessionModel:
        with db_session() as db:
            session = db.query(SessionModel).filter(SessionModel.session_id == session_id).first()
            if session:
                session.updated_at = datetime.now(timezone.utc)
                return session
            session = SessionModel(session_id=session_id)
            db.add(session)
            db.flush()
            return session

    def update_topic(self, session_id: str, topic: Optional[str]):
        with db_session() as db:
            session = db.query(SessionModel).filter(SessionModel.session_id == session_id).first()
            if session:
                session.active_topic = topic
                session.updated_at = datetime.now(timezone.utc)

    def update_objective(self, session_id: str, objective: Optional[str]):
        with db_session() as db:
            session = db.query(SessionModel).filter(SessionModel.session_id == session_id).first()
            if session:
                session.active_objective = objective
                session.updated_at = datetime.now(timezone.utc)

    def update_mode(self, session_id: str, mode: str):
        with db_session() as db:
            session = db.query(SessionModel).filter(SessionModel.session_id == session_id).first()
            if session:
                session.session_mode = mode
                session.updated_at = datetime.now(timezone.utc)

    def load_exchanges(self, session_id: str, max_pairs: int = 10) -> List[Tuple[str, str]]:
        with db_session() as db:
            messages = (
                db.query(MessageModel)
                .filter(MessageModel.session_id == session_id)
                .order_by(MessageModel.id)
                .all()
            )
        exchanges = []
        user_msg = None
        for msg in messages:
            if msg.role == "user":
                user_msg = msg.content
            elif msg.role == "assistant" and user_msg is not None:
                exchanges.append((user_msg, msg.content))
                user_msg = None
        return exchanges[-max_pairs:]

    def clear_session(self, session_id: str):
        with db_session() as db:
            db.query(SessionModel).filter(SessionModel.session_id == session_id).delete()
            db.query(MessageModel).filter(MessageModel.session_id == session_id).delete()
