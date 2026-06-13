import logging
from datetime import datetime, timezone
from typing import Optional

from mini_kio.backend.models import PendingActionModel
from mini_kio.backend.db import db_session
from mini_kio.llm.conversation_context import PendingAction

logger = logging.getLogger(__name__)

# Pending actions older than this are considered stale and ignored.
_PENDING_ACTION_TTL_SECONDS = 3600  # 1 hour


class PendingActionRepository:
    def save(self, session_id: str, pending_action: PendingAction) -> PendingActionModel:
        with db_session() as db:
            existing = (
                db.query(PendingActionModel)
                .filter(PendingActionModel.session_id == session_id, PendingActionModel.executed == False)
                .order_by(PendingActionModel.created_at.desc())
                .first()
            )
            if existing:
                existing.action_type = pending_action.action_type
                existing.query = pending_action.query
                existing.topic = pending_action.topic
                existing.executed = pending_action.executed
                existing.created_at = datetime.now(timezone.utc)
                db.flush()
                return existing

            pending_model = PendingActionModel(
                session_id=session_id,
                action_type=pending_action.action_type,
                query=pending_action.query,
                topic=pending_action.topic,
                executed=pending_action.executed,
            )
            db.add(pending_model)
            db.flush()
            return pending_model

    def load(self, session_id: str) -> Optional[PendingActionModel]:
        with db_session() as db:
            cutoff = datetime.now(timezone.utc).timestamp() - _PENDING_ACTION_TTL_SECONDS
            return (
                db.query(PendingActionModel)
                .filter(
                    PendingActionModel.session_id == session_id,
                    PendingActionModel.executed == False,
                    PendingActionModel.created_at >= datetime.fromtimestamp(cutoff, tz=timezone.utc),
                )
                .order_by(PendingActionModel.created_at.desc())
                .first()
            )

    def clear_expired(self, session_id: str) -> int:
        with db_session() as db:
            cutoff = datetime.now(timezone.utc).timestamp() - _PENDING_ACTION_TTL_SECONDS
            result = (
                db.query(PendingActionModel)
                .filter(
                    PendingActionModel.session_id == session_id,
                    PendingActionModel.created_at < datetime.fromtimestamp(cutoff, tz=timezone.utc),
                )
                .delete()
            )
            return result

    def mark_executed(self, session_id: str) -> Optional[PendingActionModel]:
        with db_session() as db:
            pending = (
                db.query(PendingActionModel)
                .filter(PendingActionModel.session_id == session_id, PendingActionModel.executed == False)
                .order_by(PendingActionModel.created_at.desc())
                .first()
            )
            if pending:
                pending.executed = True
                db.flush()
            return pending

    def delete(self, session_id: str):
        with db_session() as db:
            db.query(PendingActionModel).filter(PendingActionModel.session_id == session_id).delete()
