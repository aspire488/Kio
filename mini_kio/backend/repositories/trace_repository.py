import logging
from datetime import datetime, timezone
from typing import Optional, List

from mini_kio.backend.models import TraceModel
from mini_kio.backend.db import db_session
from mini_kio.llm.trace_context import TraceContext

logger = logging.getLogger(__name__)


class TraceRepository:
    def save(self, session_id: str, trace: TraceContext):
        with db_session() as db:
            model = TraceModel(
                session_id=session_id,
                detected_intent=trace.detected_intent.value if trace.detected_intent else None,
                selected_resolver=trace.selected_resolver,
                confidence_score=trace.confidence_score,
                execution_path=trace.execution_path,
                search_providers_used=trace.search_providers_used,
                memory_retrieved=trace.memory_retrieved,
                identity_guard_actions=trace.identity_guard_actions,
                metadata_json=trace.metadata,
            )
            db.add(model)
            db.flush()

    def get_recent(self, session_id: str, limit: int = 10) -> List[TraceModel]:
        with db_session() as db:
            return (
                db.query(TraceModel)
                .filter(TraceModel.session_id == session_id)
                .order_by(TraceModel.id.desc())
                .limit(limit)
                .all()
            )

    def clear_traces(self, session_id: str):
        with db_session() as db:
            db.query(TraceModel).filter(TraceModel.session_id == session_id).delete()
