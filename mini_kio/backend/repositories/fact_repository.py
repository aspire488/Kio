import logging
from typing import Optional, Dict

from sqlalchemy.orm import Session as DBSession

from mini_kio.backend.models import FactModel
from mini_kio.backend.db import db_session

logger = logging.getLogger(__name__)


class FactRepository:
    def set_fact(self, session_id: str, key: str, value: str):
        with db_session() as db:
            existing = (
                db.query(FactModel)
                .filter(FactModel.session_id == session_id, FactModel.fact_key == key)
                .order_by(FactModel.id.desc())
                .first()
            )
            if existing and existing.fact_value == value:
                return
            if existing:
                logger.info(f"FactRepository: Conflict for '{key}': '{existing.fact_value}' -> '{value}'")
            fact = FactModel(session_id=session_id, fact_key=key, fact_value=value)
            db.add(fact)
            db.flush()

    def get_fact(self, session_id: str, key: str) -> Optional[str]:
        with db_session() as db:
            fact = (
                db.query(FactModel)
                .filter(FactModel.session_id == session_id, FactModel.fact_key == key)
                .order_by(FactModel.id.desc())
                .first()
            )
            return fact.fact_value if fact else None

    def get_all_facts(self, session_id: str) -> Dict[str, str]:
        with db_session() as db:
            rows = (
                db.query(FactModel)
                .filter(FactModel.session_id == session_id)
                .order_by(FactModel.id)
                .all()
            )
            result = {}
            for row in rows:
                result[row.fact_key] = row.fact_value
            return result

    def clear_facts(self, session_id: str):
        with db_session() as db:
            db.query(FactModel).filter(FactModel.session_id == session_id).delete()
