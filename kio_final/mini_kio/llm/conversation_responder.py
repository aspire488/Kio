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
from typing import Optional, Dict
from mini_kio.runtime.runtime_contracts import ExecutionClassification, RuntimeHandoffResult
from mini_kio.llm.conversation_models import OrchestrationResponse, OrchestrationState, ConversationTone
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

_GREETING_CATEGORY: dict[str, str] = {
    "hello": "hello",
    "hi": "hello",
    "hey": "hello",
    "yo": "hello",
    "wassup": "hello",
    "what's up": "hello",
    "whats up": "hello",
    "how are you": "how_are_you",
    "how are you doing": "how_are_you",
    "bye": "goodbye",
    "bue": "goodbye",
    "goodbye": "goodbye",
    "thanks": "thanks",
    "thank you": "thanks",
    "okay": "okay",
    "ok": "okay",
    "cool": "positive",
    "nice": "positive",
    "good": "positive",
    "yes": "yes",
    "no": "no",
    "do it": "yes",
    "help": "help",
    "ping": "ping",
}

_GREETING_VARIANTS: dict[str, list[str]] = {
    "hello": [
        "Hello! How can I help you today?",
        "Hi there! What can I do for you?",
        "Hey! How can I assist?",
        "Hello!",
        "Hi!",
    ],
    "how_are_you": [
        "I'm functioning within normal parameters. How can I help?",
        "Doing well! What can I assist you with?",
        "All systems good. What do you need?",
        "Running smoothly. How can I help you?",
    ],
    "thanks": [
        "You're welcome!",
        "Happy to help!",
        "Anytime!",
        "Glad I could help!",
    ],
    "goodbye": [
        "Goodbye! Feel free to come back anytime.",
        "Goodbye!",
        "See you later!",
        "Take care!",
    ],
    "okay": [
        "Got it. Let me know if you need anything else.",
        "Got it.",
        "Noted.",
        "Understood.",
    ],
    "positive": [
        "Thanks! Is there anything else I can help with?",
        "Glad you think so! What would you like to do?",
        "Great! What's next?",
        "Awesome! Let me know what you need.",
    ],
    "yes": [
        "Okay. What would you like me to do?",
        "Alright. What do you need?",
    ],
    "no": [
        "Alright. Let me know if you change your mind.",
        "No problem. I'll be here if you need me.",
    ],
    "help": [
        "I can open apps, search the web, play media, and more. Try 'open chrome' or 'search python tutorials'.",
        "Ask me to open apps, search Google, play YouTube videos, or run multi-step commands.",
    ],
    "ping": [
        "KIO online.",
        "KIO online. All systems operational.",
    ],
}

_REPEATED_RESPONSES: dict[int, str] = {
    2: "Hello again!",
    3: "You're greeting me a lot. How can I help?",
}

_TONE_GENERIC: dict[str, str] = {
    ConversationTone.NEUTRAL.value: "I understand. Is there anything else I can help you with?",
    ConversationTone.CONCISE.value: "Got it.",
    ConversationTone.HELPFUL.value: "Sure! Is there anything else I can help you with?",
}


class ConversationResponder:
    """
    Safe text-only response generator for Gate 3 orchestration.

    HARD CONTAINMENT:
    - No tool execution, no action dispatch, no operator access
    - Text-only output with bounded length
    - No prompt leakage, no raw exception leakage
    """

    def __init__(self):
        self._rotation_counters: Dict[str, int] = {}
        self._input_counters: Dict[str, int] = {}
        self._tone: ConversationTone = ConversationTone.NEUTRAL

    def set_tone(self, tone: ConversationTone):
        self._tone = tone

    def get_tone(self) -> ConversationTone:
        return self._tone

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
            if classification in (
                ExecutionClassification.CONVERSATIONAL_ONLY,
                ExecutionClassification.INFORMATIONAL_ONLY,
            ):
                return self._conversational_reply(text_lower, orchestration)

            if classification == ExecutionClassification.EXECUTABLE_REQUIRES_CONFIRMATION:
                return self._confirmation_prompt(orchestration)

            if classification == ExecutionClassification.EXECUTABLE_BLOCKED:
                return self._refusal_reply(text_lower, handoff_result, orchestration)

            if classification == ExecutionClassification.EXECUTABLE_VALIDATED:
                return self._execution_summary(handoff_result)

            if classification == ExecutionClassification.DEGRADED_BLOCK:
                return _SAFE_DEGRADED_FALLBACK

            if classification == ExecutionClassification.MALFORMED_PAYLOAD:
                return self._clarification_prompt()

        return "I'm not sure how to respond to that."

    def _conversational_reply(self, text_lower: str, orchestration: OrchestrationResponse) -> str:
        """Generate a conversational reply with rotation and repeated-input handling."""
        category = self._resolve_greeting_category(text_lower)
        if category:
            return self._greeting_reply(category, text_lower)

        sorted_keys = sorted(_KNOWLEDGE_BASE.keys(), key=len, reverse=True)
        for key in sorted_keys:
            if key in text_lower:
                return _KNOWLEDGE_BASE[key][: _MAX_RESPONSE_LENGTH]

        return self._generic_response()

    def _resolve_greeting_category(self, text_lower: str) -> Optional[str]:
        """Check if input matches a greeting category."""
        for key, category in _GREETING_CATEGORY.items():
            if text_lower == key or text_lower == key.strip(".") or text_lower == key + "?":
                return category
        return None

    def _greeting_reply(self, category: str, text_lower: str) -> str:
        """Generate a greeting response with rotation and repeated-input handling."""
        repeat_count = self._input_counters.get(text_lower, 0)
        self._input_counters[text_lower] = repeat_count + 1

        if repeat_count >= 1:
            repeated = _REPEATED_RESPONSES.get(repeat_count + 1)
            if repeated:
                return repeated

        variants = _GREETING_VARIANTS.get(category)
        if not variants:
            return self._generic_response()

        idx = self._rotation_counters.get(category, 0) % len(variants)
        self._rotation_counters[category] = idx + 1
        return variants[idx]

    def _generic_response(self) -> str:
        """Return tone-adjusted generic response."""
        return _TONE_GENERIC.get(self._tone.value, _TONE_GENERIC[ConversationTone.NEUTRAL.value])

    def _confirmation_prompt(self, orchestration: OrchestrationResponse) -> str:
        """Generate a safe confirmation prompt (non-variant, safety-critical)."""
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
        """Wrap a refusal message safely (non-variant, safety-critical)."""
        base = handoff_result.message or "That action was refused for safety reasons."
        if "Runtime Veto" in base:
            return "That action is blocked by runtime safety controls."
        return base[: _MAX_RESPONSE_LENGTH]

    def _execution_summary(self, handoff_result: RuntimeHandoffResult) -> str:
        """Summarize execution result from handoff."""
        msg = handoff_result.message or "Action completed."
        return msg[: _MAX_RESPONSE_LENGTH]

    def _clarification_prompt(self) -> str:
        """Generate a safe clarification prompt (non-variant, safety-critical)."""
        return "I didn't quite understand that. Could you rephrase or try 'help' for examples?"
