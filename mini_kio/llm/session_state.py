import json
import logging
import time
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
    Single source of truth for ALL runtime conversational state.
    
    Gate 5 unified state: Owns repositories (the only owner of DB access),
    context, memory access, transient session properties, and all
    conversational continuity fields.  ALL subsystems MUST read/write
    this object instead of maintaining private context stores.
    
    Resolvers MUST NOT open databases directly.
    """
    _STATE_FACT_KEY = "conversation_state_json"
    _STATE_TTL_S = 3600  # 60-minute state expiry

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

        # ── Gate 5 unified conversational fields ────────────────────────
        self._active_entity: Optional[str] = None      # current entity (e.g. "Interstellar")
        self._active_domain: Optional[str] = None      # domain value (e.g. "MOVIES")
        self._last_recommendations: list[dict] = []     # recent recommendations shown
        self._last_offers: Optional[dict] = None        # last proactive offers shown
        self._last_action: Optional[str] = None         # last action (e.g. "trailer")
        self._last_action_target: Optional[str] = None  # what the action targeted
        self._updated_at: float = time.time()
        self._created_at: float = time.time()
        
        # Hydrate context from memory on initialization
        self.context.sync_from_memory(self.memory)
        self._load_pending_action()
        self._hydrate_conversation_state()

    def _hydrate_conversation_state(self) -> None:
        """Restore conversational state from persisted JSON fact."""
        try:
            raw = self._fact_repo.get_fact(self.session_id, self._STATE_FACT_KEY)
            if raw:
                data = json.loads(raw)
                self._active_entity = data.get("active_entity")
                self._active_domain = data.get("active_domain")
                self._last_recommendations = data.get("last_recommendations", [])
                self._last_offers = data.get("last_offers")
                self._last_action = data.get("last_action")
                self._last_action_target = data.get("last_action_target")
                self._updated_at = data.get("updated_at", time.time())
                # Check TTL
                age = time.time() - self._updated_at
                if age > self._STATE_TTL_S:
                    logger.info("ConversationState TTL expired (age=%.0fs), resetting", age)
                    self._clear_conversation_state()
                    return
                logger.info(
                    "ConversationState restored: entity=%s domain=%s action=%s age=%.0fs",
                    self._active_entity, self._active_domain, self._last_action, age
                )
        except Exception as e:
            logger.warning("Failed to hydrate conversation state: %s", e)

    def _persist_conversation_state(self) -> None:
        """Save conversational state as JSON fact."""
        try:
            data = self._conversation_state_to_dict()
            self._fact_repo.set_fact(self.session_id, self._STATE_FACT_KEY, json.dumps(data))
            self._updated_at = time.time()
        except Exception as e:
            logger.warning("Failed to persist conversation state: %s", e)

    def _clear_conversation_state(self) -> None:
        """Reset all conversational state fields."""
        self._active_entity = None
        self._active_domain = None
        self._last_recommendations = []
        self._last_offers = None
        self._last_action = None
        self._last_action_target = None
        self._updated_at = time.time()

    def _conversation_state_to_dict(self) -> dict:
        return {
            "active_entity": self._active_entity,
            "active_domain": self._active_domain,
            "last_recommendations": self._last_recommendations,
            "last_offers": self._last_offers,
            "last_action": self._last_action,
            "last_action_target": self._last_action_target,
            "updated_at": self._updated_at,
        }

    # ── unified conversational field accessors ─────────────────────────

    @property
    def active_entity(self) -> Optional[str]:
        return self._active_entity

    @active_entity.setter
    def active_entity(self, value: Optional[str]) -> None:
        self._active_entity = value
        self._persist_conversation_state()

    @property
    def active_domain(self) -> Optional[str]:
        return self._active_domain

    @active_domain.setter
    def active_domain(self, value: Optional[str]) -> None:
        self._active_domain = value
        self._persist_conversation_state()

    @property
    def last_recommendations(self) -> list[dict]:
        return self._last_recommendations

    @last_recommendations.setter
    def last_recommendations(self, value: list[dict]) -> None:
        self._last_recommendations = value[-10:]  # keep last 10
        self._persist_conversation_state()

    @property
    def last_offers(self) -> Optional[dict]:
        return self._last_offers

    @last_offers.setter
    def last_offers(self, value: Optional[dict]) -> None:
        self._last_offers = value
        self._persist_conversation_state()

    @property
    def last_action(self) -> Optional[str]:
        return self._last_action

    @last_action.setter
    def last_action(self, value: Optional[str]) -> None:
        self._last_action = value
        self._persist_conversation_state()

    @property
    def last_action_target(self) -> Optional[str]:
        return self._last_action_target

    @last_action_target.setter
    def last_action_target(self, value: Optional[str]) -> None:
        self._last_action_target = value
        self._persist_conversation_state()

    def set_entity_and_domain(self, entity: str, domain: str) -> None:
        """Set entity and domain atomically (single persist)."""
        self._active_entity = entity
        self._active_domain = domain
        self._persist_conversation_state()

    @property
    def state_ttl_remaining(self) -> float:
        """Seconds until TTL expiry (0 = expired)."""
        return max(0.0, self._STATE_TTL_S - (time.time() - self._updated_at))

    def refresh_ttl(self) -> None:
        """Touch TTL timestamp."""
        self._updated_at = time.time()

    def is_state_expired(self) -> bool:
        return time.time() - self._updated_at > self._STATE_TTL_S

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
        """Update conversational context window and persist user message to DB."""
        self.context.append_exchange(user_text, reply)
        # Persist user message so history survives restarts (assistant is
        # persisted separately by conversation_responder / kio_orchestrator)
        self.append_message("user", user_text)

    def get_history_window(self, n: int = 10) -> List[tuple[str, str]]:
        """Get the recent conversation window."""
        return self.context._exchanges[-n:] if self.context._exchanges else []

    def persist_trace(self, trace: TraceContext):
        """Persist an execution trace to the database."""
        self._trace_repo.save(self.session_id, trace)

    def get_recent_traces(self, limit: int = 10) -> List[Any]:
        """Retrieve recent traces for this session."""
        return self._trace_repo.get_recent(self.session_id, limit)
