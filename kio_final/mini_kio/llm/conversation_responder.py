"""
conversation_responder.py — Gate 3 Safe Text-Only Response Layer

HARD CONTAINMENT:
- No tool execution
- No action dispatch
- No operator access
- No runtime authority bypass
- Text-only output
"""

import logging
from typing import Optional
from mini_kio.runtime.runtime_contracts import ExecutionClassification, RuntimeHandoffResult
from mini_kio.llm.conversation_models import OrchestrationResponse, OrchestrationState
from mini_kio.llm.intent_models import IntentType

logger = logging.getLogger(__name__)

_MAX_RESPONSE_LENGTH = 600

_SAFE_DEGRADED_FALLBACK = (
    "KIO is currently in a degraded state and cannot process requests. "
    "Please try again later."
)

_KNOWLEDGE_BASE: dict[str, str] = {
    "who created you":
        "I was created by Joel.",
    "what are you":
        "I am KIO, a lightweight local automation assistant created by Joel.",
    "what is kio":
        "KIO is a desktop AI assistant that can open and close applications, "
        "search the web, play YouTube videos, open folders, and execute "
        "multi-step automation commands under strict safety controls.",
    "what can you do":
        "I can open and close applications, search Google and YouTube, "
        "play media, open folders, and execute multi-step commands. "
        "Try 'help' for a full list of commands.",
    "what are your features":
        "I can open/close applications, search the web, play YouTube videos, "
        "open folders, perform multi-step commands, and answer general questions "
        "within my knowledge base.",
    "who is joel":
        "Joel is the creator of KIO.",
    "who's joel":
        "Joel is the creator of KIO.",
    "how does runtime authority work":
        "KIO's runtime authority is a hierarchical safety system. "
        "The runtime maintains absolute veto power over all execution decisions. "
        "All intents are advisory until validated and confirmed through "
        "the Gate 3 orchestration pipeline.",
    "what are your safety features":
        "KIO enforces multiple safety layers: runtime veto authority that can "
        "block all execution, restricted-target blocking for dangerous system "
        "commands, degraded-state detection, explicit user confirmation for "
        "risky actions, and validation-before-execution.",
    "how does confirmation work":
        "When I detect a potentially risky or ambiguous action, I pause and "
        "ask for your explicit confirmation before proceeding. "
        "You can confirm with 'yes' or 'do it', or cancel with 'no'.",
    "what is gate 3":
        "Gate 3 is the orchestration layer that manages conversational flow "
        "and execution gating. It classifies, validates, and confirms all "
        "intents before reaching the runtime execution boundary.",
    "what is gate 2":
        "Gate 2 is the deterministic command routing layer. It handles known "
        "commands like opening apps, searching, and playing media directly "
        "without going through the full orchestration pipeline.",
    "tell me about kio":
        "KIO is a lightweight local automation assistant that runs on your "
        "machine. It can open applications, search the web, play media, and "
        "execute multi-step commands. All actions are gated by runtime safety "
        "controls to ensure safe operation.",
}

_GREETING_RESPONSES: dict[str, str] = {
    "hello": "Hello! How can I help you today?",
    "hi": "Hi there! What can I do for you?",
    "hey": "Hey! How can I assist?",
    "yo": "Hey! I'm KIO. How can I help?",
    "wassup": "Not much! Ready to help. What do you need?",
    "what's up": "I'm here and ready. What can I do for you?",
    "whats up": "I'm here and ready. What can I do for you?",
    "how are you": "I'm functioning within normal parameters. How can I help?",
    "how are you doing": "Doing well! What can I assist you with?",
    "bye": "Goodbye! Feel free to come back anytime.",
    "bue": "Goodbye!",
    "goodbye": "Goodbye!",
    "thanks": "You're welcome!",
    "thank you": "You're welcome!",
    "okay": "Got it. Let me know if you need anything else.",
    "ok": "Got it.",
    "cool": "Thanks! Is there anything else I can help with?",
    "nice": "Glad you think so! What would you like to do?",
    "good": "Great! What's next?",
    "yes": "Okay. What would you like me to do?",
    "no": "Alright. Let me know if you change your mind.",
    "do it": "I'm ready when you are. What should I do?",
    "help": "I can open apps, search the web, play media, and more. Try 'open chrome' or 'search python tutorials'.",
    "ping": "KIO online.",
}


class ConversationResponder:
    """
    Safe text-only response generator for Gate 3 orchestration.

    HARD CONTAINMENT:
    - No tool execution, no action dispatch, no operator access
    - Text-only output with bounded length
    - No prompt leakage, no raw exception leakage
    """

    def generate(
        self,
        original_text: str,
        orchestration: OrchestrationResponse,
        handoff_result: RuntimeHandoffResult,
    ) -> str:
        """Generate a safe text-only response based on pipeline context."""
        classification = handoff_result.classification
        text_lower = (original_text or "").strip().lower()

        if isinstance(classification, ExecutionClassification):
            # Conversational — generate friendly reply
            if classification in (
                ExecutionClassification.CONVERSATIONAL_ONLY,
                ExecutionClassification.INFORMATIONAL_ONLY,
            ):
                return self._conversational_reply(text_lower, orchestration)

            # Confirmation required — generate confirmation prompt
            if classification == ExecutionClassification.EXECUTABLE_REQUIRES_CONFIRMATION:
                return self._confirmation_prompt(orchestration)

            # Refused — use handoff message, wrap gracefully
            if classification == ExecutionClassification.EXECUTABLE_BLOCKED:
                return self._refusal_reply(text_lower, handoff_result, orchestration)

            # Executed — keep execution result from handoff
            if classification == ExecutionClassification.EXECUTABLE_VALIDATED:
                return self._execution_summary(handoff_result)

            # Degraded — safe fallback
            if classification == ExecutionClassification.DEGRADED_BLOCK:
                return _SAFE_DEGRADED_FALLBACK

            # Malformed — clarification
            if classification == ExecutionClassification.MALFORMED_PAYLOAD:
                return self._clarification_prompt()

        return "I'm not sure how to respond to that."

    def _conversational_reply(self, text_lower: str, orchestration: OrchestrationResponse) -> str:
        """Generate a conversational reply — not an echo."""
        # Greeting/known interaction lookup (exact match only)
        for key, response in _GREETING_RESPONSES.items():
            if text_lower == key or text_lower == key.strip(".") or text_lower == key + "?":
                return response

        # Knowledge base lookup — longest keys first to avoid substring shadowing
        sorted_keys = sorted(_KNOWLEDGE_BASE.keys(), key=len, reverse=True)
        for key in sorted_keys:
            if key in text_lower:
                return _KNOWLEDGE_BASE[key][: _MAX_RESPONSE_LENGTH]

        # Generic friendly response
        return "I understand. Is there anything else I can help you with?"

    def _confirmation_prompt(self, orchestration: OrchestrationResponse) -> str:
        """Generate a safe confirmation prompt."""
        pending = orchestration.pending_action
        if pending:
            action = pending.action
            target = pending.target
            reason = pending.reason or ""
            if reason:
                return (
                    f"I can {action} {target}. "
                    f"Note: {reason}. Shall I proceed?"
                )
            return f"I'm ready to {action} {target}. Shall I proceed?"
        return "I need your confirmation before proceeding. Shall I continue?"

    def _refusal_reply(
        self,
        text_lower: str,
        handoff_result: RuntimeHandoffResult,
        orchestration: OrchestrationResponse,
    ) -> str:
        """Wrap a refusal message safely."""
        base = handoff_result.message or "That action was refused for safety reasons."
        # Don't expose raw veto details that could leak runtime internals
        if "Runtime Veto" in base:
            return "That action is blocked by runtime safety controls."
        return base[: _MAX_RESPONSE_LENGTH]

    def _execution_summary(self, handoff_result: RuntimeHandoffResult) -> str:
        """Summarize execution result from handoff."""
        msg = handoff_result.message or "Action completed."
        return msg[: _MAX_RESPONSE_LENGTH]

    def _clarification_prompt(self) -> str:
        """Generate a safe clarification prompt."""
        return "I didn't quite understand that. Could you rephrase or try 'help' for examples?"
