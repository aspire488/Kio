import logging
from datetime import datetime, timezone
from typing import Optional, List, Dict

from mini_kio.backend.models import WatchModel
from mini_kio.backend.db import db_session

logger = logging.getLogger(__name__)


class WatchRepository:
    def add(self, target: str, kind: str, chat_id: str, channel: str = "telegram",
            user_id: str = "", last_seen_key: Optional[str] = None) -> WatchModel:
        with db_session() as db:
            existing = (
                db.query(WatchModel)
                .filter(WatchModel.target == target,
                        WatchModel.chat_id == chat_id,
                        WatchModel.active.is_(True))
                .first()
            )
            if existing:
                if last_seen_key:
                    existing.last_seen_key = last_seen_key
                    existing.last_seen_ts = datetime.now(timezone.utc)
                return existing
            watch = WatchModel(
                target=target, kind=kind, chat_id=chat_id, channel=channel,
                user_id=user_id, active=True, last_seen_key=last_seen_key,
                last_seen_ts=datetime.now(timezone.utc),
            )
            db.add(watch)
            db.flush()
            return watch

    def deactivate(self, target: str, chat_id: str) -> bool:
        with db_session() as db:
            rows = (
                db.query(WatchModel)
                .filter(WatchModel.target == target,
                        WatchModel.chat_id == chat_id,
                        WatchModel.active.is_(True))
                .all()
            )
            for row in rows:
                row.active = False
            return len(rows) > 0

    def list_active(self, chat_id: str) -> List[Dict]:
        with db_session() as db:
            rows = (
                db.query(WatchModel)
                .filter(WatchModel.chat_id == chat_id, WatchModel.active.is_(True))
                .order_by(WatchModel.id)
                .all()
            )
            return [
                {"target": r.target, "kind": r.kind, "last_seen_key": r.last_seen_key}
                for r in rows
            ]

    def all_active(self) -> List[WatchModel]:
        with db_session() as db:
            return (
                db.query(WatchModel)
                .filter(WatchModel.active.is_(True))
                .all()
            )

    def update_last_seen(self, watch_id: int, last_seen_key: str):
        with db_session() as db:
            row = db.query(WatchModel).filter(WatchModel.id == watch_id).first()
            if row:
                row.last_seen_key = last_seen_key
                row.last_seen_ts = datetime.now(timezone.utc)