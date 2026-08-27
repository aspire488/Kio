import logging
from typing import Optional, Dict, List

from mini_kio.backend.models import BriefModel
from mini_kio.backend.db import db_session

logger = logging.getLogger(__name__)


class BriefRepository:
    def upsert(self, session_id: str, topic_key: str, topic: str,
               content: str, sources: List[Dict]) -> BriefModel:
        with db_session() as db:
            existing = (
                db.query(BriefModel)
                .filter(BriefModel.session_id == session_id,
                        BriefModel.topic_key == topic_key)
                .order_by(BriefModel.id.desc())
                .first()
            )
            if existing:
                existing.topic = topic
                existing.content = content
                existing.sources_json = sources
                return existing
            brief = BriefModel(
                session_id=session_id, topic_key=topic_key, topic=topic,
                content=content, sources_json=sources,
            )
            db.add(brief)
            db.flush()
            return brief

    def get(self, session_id: str, topic_key: str) -> Optional[BriefModel]:
        with db_session() as db:
            return (
                db.query(BriefModel)
                .filter(BriefModel.session_id == session_id,
                        BriefModel.topic_key == topic_key)
                .order_by(BriefModel.id.desc())
                .first()
            )

    def list_topics(self, session_id: str) -> List[Dict]:
        with db_session() as db:
            rows = (
                db.query(BriefModel)
                .filter(BriefModel.session_id == session_id)
                .order_by(BriefModel.updated_at.desc())
                .all()
            )
            seen = set()
            out = []
            for r in rows:
                if r.topic_key in seen:
                    continue
                seen.add(r.topic_key)
                out.append({"topic": r.topic, "topic_key": r.topic_key,
                            "updated_at": r.updated_at.isoformat() if r.updated_at else ""})
            return out