import logging
from typing import Optional, Dict, Any, List
from mini_kio.llm.conversation_context import ConversationContext, PendingAction
from mini_kio.memory.memory_store import MemoryStore
from mini_kio.backend.repositories import (
    MemoryRepository,
    FactRepository,
    TraceRepository,
    SessionRepository,
    PendingActionRepository,
)
from mini_kio.backend.db import init_db
from mini_kio.llm.trace_context import TraceContext
from mini_kio.core.runtime import emit_runtime_trace

logger = logging.getLogger(__name__)

class SessionState:
    """
    Single source of truth for runtime conversational state.
    
    Owns repositories (the only owner of DB access), context, memory access,
    and transient session properties. Resolvers MUST NOT open databases directly.
    """
    def __init__(self, session_id: str = "default"):
        init_db()
        self.session_id = session_id
        self.context = ConversationContext()
        self._memory_repo = MemoryRepository()
        self._fact_repo = FactRepository()
        self._trace_repo = TraceRepository()
        self._session_repo = SessionRepository()
        self._pending_action_repo = PendingActionRepository()
        # MemoryStore is a backward-compat shim that shares our repos
        self.memory = MemoryStore(session_id=session_id, memory_repo=self._memory_repo, fact_repo=self._fact_repo)
        
        # Session metadata
        session_model = self._session_repo.get_or_create(session_id)
        self._active_objective: Optional[str] = session_model.active_objective
        self._active_topic: Optional[str] = session_model.active_topic
        self._session_mode: str = session_model.session_mode or "conversational"
        self.rotation_counters: Dict[str, int] = {}
        
        # Hydrate context from memory on initialization
        self.context.sync_from_memory(self.memory)
        self._load_pending_action()

    def _load_pending_action(self) -> None:
        # Clear stale records before loading
        try:
            self._pending_action_repo.clear_expired(self.session_id)
        except Exception:
            logger.debug("Failed to clear expired pending actions", exc_info=True)
        pending_model = self._pending_action_repo.load(self.session_id)
        if pending_model:
            self.context.set_pending_search(pending_model.query, pending_model.topic)
            if pending_model.executed:
                self.context.mark_pending_executed()
            # Traceability: pending action loaded from DB
            try:
                emit_runtime_trace("continuity_loaded", query=pending_model.query, source="pending_action_db", session_id=self.session_id)
            except Exception:
                logger.debug("emit_runtime_trace failed in _load_pending_action", exc_info=True)

    @property
    def pending_action(self) -> Optional[PendingAction]:
        return self.context.get_pending_action()

    def set_pending_search(self, query: str, topic: str = ""):
        self.context.set_pending_search(query, topic)
        pending = self.context.get_pending_action()
        if pending:
            self._pending_action_repo.save(self.session_id, pending)
            try:
                emit_runtime_trace("continuity_created", query=pending.query, source="session_set_pending_search", session_id=self.session_id)
            except Exception:
                logger.debug("emit_runtime_trace failed in set_pending_search", exc_info=True)

    def clear_pending_action(self):
        self.context.clear_pending_action()
        self._pending_action_repo.delete(self.session_id)

    def mark_pending_executed(self):
        self.context.mark_pending_executed()
        self._pending_action_repo.mark_executed(self.session_id)
        try:
            emit_runtime_trace("continuity_executed", session_id=self.session_id)
        except Exception:
            logger.debug("emit_runtime_trace failed in mark_pending_executed", exc_info=True)

    def has_pending_action(self) -> bool:
        return self.context.has_pending_action()

    def recent_topic(self) -> Optional[str]:
        return self.context.recent_topic() or self._active_topic

    def set_active_topic(self, topic: str):
        self._active_topic = topic
        self._session_repo.update_topic(self.session_id, topic)

    def set_active_objective(self, objective: str):
        self._active_objective = objective
        self._session_repo.update_objective(self.session_id, objective)

    def set_session_mode(self, mode: str):
        self._session_mode = mode
        self._session_repo.update_mode(self.session_id, mode)

    def get_all_facts(self) -> Dict[str, str]:
        return self.memory.get_all_facts()

    def append_message(self, role: str, content: str):
        """Append to memory store."""
        self.memory.append(role, content)

    def append_exchange(self, user_text: str, reply: str):
        """Update conversational context window."""
        self.context.append_exchange(user_text, reply)

    def get_history_window(self, n: int = 10) -> List[tuple[str, str]]:
        """Get the recent conversation window."""
        return self.context._exchanges[-n:] if self.context._exchanges else []

    def persist_trace(self, trace: TraceContext):
        """Persist an execution trace to the database."""
        self._trace_repo.save(self.session_id, trace)

    def get_recent_traces(self, limit: int = 10) -> List[Any]:
        """Retrieve recent traces for this session."""
        return self._trace_repo.get_recent(self.session_id, limit)
