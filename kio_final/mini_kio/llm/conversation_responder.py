"""
conversation_responder.py — KIO Orchestrator (Refactored)

The entry point for KIO's backend execution pipeline.
Decomposed into dedicated resolvers for Math, Identity, Memory, Search, etc.
Authoritative state management via SessionState.
"""

import asyncio
import logging
import re
from typing import Optional, Dict

from mini_kio.runtime.runtime_contracts import ExecutionClassification, RuntimeHandoffResult
from mini_kio.llm.conversation_models import OrchestrationResponse, ConversationTone
from mini_kio.llm.intent_models import IntentType
from mini_kio.llm.intent_classifier import IntentClassifier
from mini_kio.llm.identity_guard import IdentityGuard
from mini_kio.llm.session_state import SessionState
from mini_kio.llm.trace_context import TraceContext
from mini_kio.llm.llm_ops import ask_llm_sync, _sanitize_llm_output as _sanitize_gemini_output, _EXECUTION_CLAIM_RE, _AUTHORITY_CLAIM_RE
from mini_kio.llm.llm_constants import _ASYSTEM_PROMPT, _MAX_RESPONSE_LENGTH
from mini_kio.core.freshness_classifier import is_confirmation
from mini_kio.llm.conversation_governor import ConversationGovernor

from mini_kio.resolvers import (
    MemoryResolver, IdentityResolver, MathResolver, 
    SystemStateResolver, ReasoningResolver, KnowledgeResolver
)

logger = logging.getLogger(__name__)

# Shim for legacy tests
def _ask_gemini(user_text: str, system_prompt: Optional[str] = None) -> Optional[str]:
    return ask_llm_sync(user_text, system_prompt=system_prompt)

def _handle_continuity_pre_route(text: str, state: SessionState, handoff=None, orch=None) -> Optional[str]:
    return None

_EXECUTION_CLOSINGS = {
    "open": [""],
    "close": ["Ready for the next task.", "Standing by."],
    "search": ["Anything else I can find for you?", "Let me know if you need more info."],
    "generic": ["Let me know if you need anything else.", "Standing by."],
}

def _synthesize(header: str, detail: str = "", closing: str = "") -> str:
    parts = [header]
    if detail: parts.append(detail)
    if closing: parts.append(closing)
    return " ".join(parts)

# Pre-defined rotation variants for common execution results
_OPEN_VARIANTS = ["Opened {0}", "Launched {0}", "Starting {0}", "Got it, {0} is opening."]
_CLOSE_VARIANTS = ["Closed {0}", "Killed {0}", "Stopped {0}", "Shutting down {0}."]
_SEARCH_VARIANTS = ["Searching for {0}", "Finding {0}", "Looking up {0}."]
_TYPE_VARIANTS = ["Typed {0}", "Wrote {0}", "Sent keys for {0}."]

# Constants for backward compatibility with tests
_DEGRADED_NO_TOPIC_VARIANTS = [
    "LLM provider offline. Try again when connectivity is restored.",
    "Provider chain exhausted. Check API config and retry.",
]

def _truncate_safe(text: str, max_len: int = _MAX_RESPONSE_LENGTH) -> str:
    if not text or len(text) <= max_len:
        return text
    return text[:max_len].strip()


class ConversationResponder:
    """
    KIO Backend Orchestrator.
    
    Refactored from God Object to decoupled pipeline manager.
    Maintains the name 'ConversationResponder' for backward compatibility with 100+ tests.
    """
    
    def __init__(self, session_id: str = "default"):
        self._state = SessionState(session_id=session_id)
        self._classifier = IntentClassifier()
        self._identity_guard = IdentityGuard()
        self._tone = ConversationTone.NEUTRAL
        self._governor_instance = ConversationGovernor()
        
        # Initialize Resolvers
        self._resolvers: Dict[IntentType, object] = {
            IntentType.MEMORY: MemoryResolver(),
            IntentType.IDENTITY: IdentityResolver(),
            IntentType.MATH: MathResolver(),
            IntentType.SYSTEM_STATE: SystemStateResolver(),
            IntentType.REASONING: ReasoningResolver(),
            IntentType.INFORMATIONAL: KnowledgeResolver(),
        }
        
        # Fallback resolvers
        self._identity_resolver = IdentityResolver()
        self._memory_resolver = MemoryResolver()
        self._knowledge_resolver = KnowledgeResolver()
        self._system_state_resolver = SystemStateResolver()
        
        self._trace = TraceContext("init")
        self._diag: Dict[str, int] = {}
        self._reset_diagnostics()

    @property
    def _governor(self):
        return self._governor_instance
        
    @_governor.setter
    def _governor(self, value):
        self._governor_instance = value

    @property
    def _input_counters(self):
        if not hasattr(self, '_input_counters_dict'):
            self._input_counters_dict = {}
        return self._input_counters_dict

    @_input_counters.setter
    def _input_counters(self, value):
        self._input_counters_dict = value

    @property
    def _rotation_counters(self):
        return self._state.rotation_counters

    def _reset_diagnostics(self):
        self._diag = {
            "fallback_coherence_used": 0,
            "provider_knowledge_route_used": 0,
            "coherence_normalized": 0,
            "educational_route_used": 0,
            "educational_authority_used": 0,
            "educational_intent_detected": 0,
            "continuity_intercept_used": 0,
            "typo_normalization_applied": 0,
            "coherence_rewrite_applied": 0,
            "semantic_fallback_used": 0,
        }

    def set_tone(self, tone: ConversationTone):
        self._tone = tone
        self._governor_instance.set_tone(tone)

    def get_tone(self) -> ConversationTone:
        return self._tone

    @property
    def _context(self):
        return self._state.context

    @property
    def _memory(self):
        return self._state.memory

    @_memory.setter
    def _memory(self, value):
        self._state.memory = value

    def _build_bounded_prompt(self, user_text: str, system_prompt: Optional[str] = None) -> str:
        """Build a bounded system prompt using session state."""
        parts = [system_prompt or _ASYSTEM_PROMPT]
        
        # 1. Facts
        facts = self._state.get_all_facts()
        if facts:
            fact_lines = [f"- {k}: {v}" for k, v in facts.items()]
            parts.append("\nRelevant User Facts:\n" + "\n".join(fact_lines))
        
        # 2. Pending Actions
        pending = self._state.pending_action
        if pending and not pending.executed:
             parts.append(f"\nActive Task: Awaiting confirmation for {pending.action_type} '{pending.query}'")
             
        # 3. History window
        history = self._state.get_history_window(10)
        if history:
            history_lines = [f"User: {u}\nKIO: {r}" for u, r in history]
            parts.append("\nRecent Conversation:\n" + "\n".join(history_lines))
            
        parts.append(f"\nCurrent User Input: {user_text}")
        return "\n\n".join(parts)

    def _generic_response(self) -> str:
        """Fallback for generic responses when LLM is unavailable (rotates)."""
        if self._tone == ConversationTone.CONCISE:
            return "N/A."
        idx = self._state.rotation_counters.get("generic", 0) % len(_DEGRADED_NO_TOPIC_VARIANTS)
        self._state.rotation_counters["generic"] = idx + 1
        return _DEGRADED_NO_TOPIC_VARIANTS[idx]

    def _generic(self) -> str:
        """Shim for legacy tests."""
        return self._generic_response()

    def _resolve_knowledge_request(self, text: str, prefer_provider: bool = False) -> Optional[str]:
        """Backward-compat wrapper: delegates to KnowledgeResolver."""
        trace = TraceContext()
        return self._knowledge_resolver.resolve(text, self._state, trace)

    def generate(
        self,
        original_text: str,
        orchestration: OrchestrationResponse,
        handoff_result: RuntimeHandoffResult,
    ) -> str:
        """
        Unified execution pipeline.
        Classification -> State Hydration -> Dispatch -> Guard -> Output
        """
        trace = TraceContext()
        text = (original_text or "").strip()
        trace.detected_intent = orchestration.intent_type
        classification = handoff_result.classification
        
        # P0: Persist user message immediately
        self._state.append_message("user", text)
        
        # P1: Identity always wins — pre-check before intent-mapped resolvers
        id_reply = self._identity_resolver.resolve(text, self._state, trace)
        if id_reply:
            return self._finalize_response(text, id_reply, trace)
        
        # 1. Contextual / Pending Confirmation
        if self._state.has_pending_action():
            pending = self._state.pending_action
            if pending and pending.action_type == "search" and is_confirmation(text.lower()):
                trace.add_step("Orchestrator: executing pending search")
                res = self._knowledge_resolver.resolve(pending.query, self._state, trace)
                if res:
                    self._state.mark_pending_executed()
                    return self._finalize_response(text, res, trace)

        # 2. Intent-mapped Resolvers (Higher Priority)
        resolver = self._resolvers.get(orchestration.intent_type)
        if resolver:
            trace.selected_resolver = type(resolver).__name__
            reply = resolver.resolve(text, self._state, trace)
            if reply:
                return self._finalize_response(text, reply, trace)

        # 3. Execution Classification Handling (Gate 3 legacy logic)
        if classification == ExecutionClassification.EXECUTABLE_REQUIRES_CONFIRMATION:
            return self._finalize_response(text, self._confirmation_prompt(orchestration), trace)

        if classification == ExecutionClassification.EXECUTABLE_BLOCKED:
            return self._finalize_response(text, self._refusal_reply(text, handoff_result, orchestration), trace)

        if classification == ExecutionClassification.EXECUTABLE_VALIDATED:
            return self._finalize_response(text, self._execution_summary(handoff_result), trace)

        if classification == ExecutionClassification.MALFORMED_PAYLOAD:
            return self._finalize_response(text, "Rephrase the request.", trace)

        if classification == ExecutionClassification.DEGRADED_BLOCK:
            return self._finalize_response(text, self._degraded_fallback(), trace)

        # 4. Deterministic Fallbacks
        # Greetings/Identity (redundant with P1 but kept for backward compat)
        reply = self._identity_resolver.resolve(text, self._state, trace)
        if reply:
            return self._finalize_response(text, reply, trace)
            
        # Memory recall
        reply = self._memory_resolver.resolve(text, self._state, trace)
        if reply:
            return self._finalize_response(text, reply, trace)

        # 5. Search Fallback (Knowledge)
        reply = self._knowledge_resolver.resolve(text, self._state, trace)
        if reply:
            self._diag["provider_knowledge_route_used"] += 1
            return self._finalize_response(text, reply, trace)

        # 6. Probabilistic Cognition (LLM)
        trace.add_step("Orchestrator: LLM fallback")
        system_prompt = self._build_bounded_prompt(text)
        reply = ask_llm_sync(text, system_prompt=system_prompt)
        
        if not reply:
            self._diag["fallback_coherence_used"] += 1
            # Educational fallback chain: try KnowledgeResolver before giving up
            edu_reply = self._knowledge_resolver.resolve(text, self._state, TraceContext())
            if edu_reply:
                self._diag["educational_route_used"] = self._diag.get("educational_route_used", 0) + 1
                return self._finalize_response(text, edu_reply, trace)
            reply = self._generic_response()
            
        return self._finalize_response(text, reply, trace)

    def _persist_trace(self, trace: TraceContext):
        """Persist execution trace to backend database."""
        try:
            self._state.persist_trace(trace)
        except Exception as e:
            logger.debug(f"Trace persistence skipped: {e}")

    def _confirmation_prompt(self, orchestration: OrchestrationResponse) -> str:
        pending = orchestration.pending_action
        if pending:
            action = pending.action
            target = pending.target
            reason = pending.reason or ""
            if reason:
                return f"I can {action} {target}. Note: {reason}. Shall I proceed?"
            return f"I'm ready to {action} {target}. Shall I proceed?"
        return "I need your confirmation before proceeding. Shall I continue?"

    def _refusal_reply(self, text_lower: str, handoff: RuntimeHandoffResult, orch: OrchestrationResponse) -> str:
        base = handoff.message or "That action was refused for safety reasons."
        if "Runtime Veto" in base:
            return "That action is blocked by runtime safety controls."
        return base

    def _execution_summary(self, handoff: RuntimeHandoffResult) -> str:
        msg = handoff.message or "Action completed."
        
        clean_msg = msg
        if " (pid " in clean_msg:
            clean_msg = re.sub(r" \(pid \d+\)", "", clean_msg)
        
        header = clean_msg
        detail = ""
        cat = ""
        
        low = clean_msg.lower()
        if "opened" in low or "launched" in low or "started" in low:
            target = clean_msg.split()[-1]
            idx = self._state.rotation_counters.get("open", 0) % len(_OPEN_VARIANTS)
            self._state.rotation_counters["open"] = idx + 1
            header = _OPEN_VARIANTS[idx].format(target)
            cat = "open"
        elif "closed" in low or "killed" in low:
            target = clean_msg.split()[-1]
            idx = self._state.rotation_counters.get("close", 0) % len(_CLOSE_VARIANTS)
            self._state.rotation_counters["close"] = idx + 1
            header = _CLOSE_VARIANTS[idx].format(target)
            cat = "close"
        elif "searched" in low:
            target = clean_msg.split(":")[-1].strip() if ":" in clean_msg else clean_msg
            idx = self._state.rotation_counters.get("search", 0) % len(_SEARCH_VARIANTS)
            self._state.rotation_counters["search"] = idx + 1
            header = _SEARCH_VARIANTS[idx].format(target)
            cat = "search"
            
        if not cat:
            return header

        closings = _EXECUTION_CLOSINGS.get(cat, _EXECUTION_CLOSINGS["generic"])
        idx = self._state.rotation_counters.get(f"closing_{cat}", 0) % len(closings)
        self._state.rotation_counters[f"closing_{cat}"] = idx + 1
        closing = closings[idx]
        
        return _finalize_synthesize(header, detail, closing)

    def _degraded_fallback(self) -> str:
        idx = self._state.rotation_counters.get("degraded", 0) % len(_DEGRADED_NO_TOPIC_VARIANTS)
        self._state.rotation_counters["degraded"] = idx + 1
        return _DEGRADED_NO_TOPIC_VARIANTS[idx]

    def _finalize_response(self, user_text: str, reply: str, trace: TraceContext) -> str:
        """Surgical IdentityGuard, State Update, and Trace Persistence."""
        
        # 1. Identity Guard (Always run before user sees output)
        final_reply, violations = self._identity_guard.check_and_rewrite(reply, user_text)
        trace.identity_guard_actions = violations
        
        # 2. Final normalization (truncation)
        final_reply = _truncate_safe(final_reply)
        
        # 3. State Update
        self._state.append_exchange(user_text, final_reply)
        self._state.append_message("assistant", final_reply)
        
        # 4. Diagnostics Update
        if violations:
            self._diag["coherence_normalized"] += 1
            
        # 5. Persist execution trace to backend database
        self._persist_trace(trace)
            
        logger.debug(f"KIO Execution Trace: {trace}")
        return final_reply

    def _resolve_system_state_intent(self, text: str) -> Optional[str]:
        """Backward-compat delegate to SystemStateResolver."""
        return self._system_state_resolver.resolve(text, self._state, self._trace)

    def get_context_diagnostics(self) -> dict:
        """Backward compatibility for diagnostic counters."""
        # Merge internal and state diagnostics
        d = dict(self._diag)
        d.update(self._state.context.get_diagnostics())
        return d

def _finalize_synthesize(header: str, detail: str = "", closing: str = "") -> str:
    # Legacy tests expect "header closing" or "header detail closing" with spaces
    parts = [header]
    if detail: parts.append(detail)
    if closing: parts.append(closing)
    return " ".join(parts)

# Backward-compat re-exports
from mini_kio.resolvers.memory_resolver import _MEMORY_PATTERNS  # noqa: E402, F401
