import logging
import re
from typing import Optional, Dict, List
from mini_kio.runtime.runtime_contracts import ExecutionClassification, RuntimeHandoffResult
from mini_kio.llm.conversation_models import OrchestrationResponse, OrchestrationState, ConversationTone
from mini_kio.llm.intent_models import IntentType
from mini_kio.llm.intent_classifier import IntentClassifier
from mini_kio.llm.identity_guard import IdentityGuard
from mini_kio.llm.session_state import SessionState
from mini_kio.llm.trace_context import TraceContext
from mini_kio.llm.llm_ops import ask_llm_sync, _sanitize_llm_output
from mini_kio.resolvers import (
    MemoryResolver, IdentityResolver, MathResolver, 
    SystemStateResolver, ReasoningResolver, KnowledgeResolver
)

logger = logging.getLogger(__name__)

class KIOOrchestrator:
    """
    KIO Backend Orchestrator.
    
    Manages the execution pipeline from input to response.
    """
    
    def __init__(self, session_id: str = "default"):
        self.state = SessionState(session_id=session_id)
        self.classifier = IntentClassifier()
        self.identity_guard = IdentityGuard()
        
        # Initialize Resolvers
        self.resolvers = {
            IntentType.MEMORY: MemoryResolver(), # Note: IntentType needs updating if MEMORY isn't there
            IntentType.IDENTITY: IdentityResolver(), # Same here
            IntentType.MATH: MathResolver(),
            IntentType.SYSTEM_STATE: SystemStateResolver(),
            IntentType.REASONING: ReasoningResolver(),
            IntentType.INFORMATIONAL: KnowledgeResolver(),
        }
        
        # Fallback resolvers that don't map 1:1 to IntentType
        self.identity_resolver = IdentityResolver()
        self.memory_resolver = MemoryResolver()
        self.knowledge_resolver = KnowledgeResolver()

    def _build_bounded_prompt(self, user_text: str, system_prompt: Optional[str] = None) -> str:
        """Build a bounded system prompt."""
        # Use existing logic from responder
        from mini_kio.llm.conversation_responder import _ASYSTEM_PROMPT
        parts = [system_prompt or _ASYSTEM_PROMPT]
        
        # 1. Facts
        facts = self.state.get_all_facts()
        if facts:
            fact_lines = [f"- {k}: {v}" for k, v in facts.items()]
            parts.append("\nRelevant User Facts:\n" + "\n".join(fact_lines))
        
        # 2. Pending Actions
        pending = self.state.pending_action
        if pending and not pending.executed:
             parts.append(f"\nActive Task: Awaiting confirmation for {pending.action_type} '{pending.query}'")
             
        # 3. History window
        history = self.state.get_history_window(10)
        if history:
            history_lines = [f"User: {u}\nKIO: {r}" for u, r in history]
            parts.append("\nRecent Conversation:\n" + "\n".join(history_lines))
            
        parts.append(f"\nCurrent User Input: {user_text}")
        return "\n\n".join(parts)

    def generate(
        self,
        original_text: str,
        orchestration: OrchestrationResponse,
        handoff_result: RuntimeHandoffResult,
    ) -> str:
        """Core pipeline implementation."""
        trace = TraceContext()
        text = (original_text or "").strip()
        trace.detected_intent = orchestration.intent_type
        
        # 1. State Hydration (already done in __init__ or passed in)
        # In the future, we might hydrate from a specific context
        
        # P0: Persist user message immediately
        self.state.append_message("user", text)
        
        # 2. Sequential Resolver Execution
        
        # ── A. Contextual/Pending Actions ──
        if self.state.has_pending_action():
            # ... handle pending confirmation ...
            pass # (Omitted for brevity in this draft, but will implement)

        # ── B. Intent-mapped Resolvers ──
        resolver = self.resolvers.get(orchestration.intent_type)
        if resolver:
            trace.selected_resolver = type(resolver).__name__
            reply = resolver.resolve(text, self.state, trace)
            if reply:
                return self._finalize_response(text, reply, trace)

        # ── C. Deterministic Fallbacks (Greetings, Memory Patterns) ──
        # Try identity/greeting if not already handled
        reply = self.identity_resolver.resolve(text, self.state, trace)
        if reply:
            return self._finalize_response(text, reply, trace)
            
        # Try memory patterns
        reply = self.memory_resolver.resolve(text, self.state, trace)
        if reply:
            return self._finalize_response(text, reply, trace)

        # ── D. Search Fallback (Knowledge) ──
        reply = self.knowledge_resolver.resolve(text, self.state, trace)
        if reply:
            return self._finalize_response(text, reply, trace)

        # ── E. Probabilistic Cognition (LLM) ──
        trace.add_step("Orchestrator: falling back to LLM cognition")
        bounded_prompt = self._build_bounded_prompt(text)
        reply = ask_llm_sync(text, system_prompt=bounded_prompt)
        
        if not reply:
            reply = "I'm having trouble connecting to my provider right now."
            
        return self._finalize_response(text, reply, trace)

    def _finalize_response(self, user_text: str, reply: str, trace: TraceContext) -> str:
        """Formatting, IdentityGuard, and State Update."""
        
        # 1. Identity Guard
        trace.add_step("Orchestrator: applying IdentityGuard")
        final_reply, violations = self.identity_guard.check_and_rewrite(reply, user_text)
        trace.identity_guard_actions = violations
        
        # 2. State Update
        self.state.append_exchange(user_text, final_reply)
        self.state.append_message("assistant", final_reply)
        
        # 3. Log trace for observability
        logger.debug(f"KIO Trace: {trace}")
        
        return final_reply
