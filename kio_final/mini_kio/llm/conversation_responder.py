"""
conversation_responder.py — Gate 3 Safe Text-Only Response Layer

HARD CONTAINMENT:
- No tool execution
- No action dispatch
- No operator access
- No runtime authority bypass
- Text-only output
"""

import asyncio
import logging
import re
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
        "Hey! Need anything?",
        "Hi there! What's up?",
        "Hello! What can I do?",
        "Hey! How's it going?",
        "Hi! I'm here. What do you need?",
    ],
    "how_are_you": [
        "Doing well! What can I help with?",
        "Doing fine! What can I do for you?",
        "All good! What's up?",
        "Running smoothly. How can I help?",
        "Pretty good! What's on your mind?",
        "All good here. What can I do?",
    ],
    "thanks": [
        "You're welcome!",
        "Happy to help!",
        "Anytime!",
        "Glad I could help!",
        "No problem!",
        "My pleasure!",
        "Happy to assist!",
        "You got it!",
    ],
    "goodbye": [
        "Goodbye! Feel free to come back anytime.",
        "Goodbye!",
        "See you later!",
        "Take care!",
        "Catch you later!",
        "Later!",
        "Talk later!",
    ],
    "okay": [
        "Got it. Let me know if you need anything else.",
        "Got it.",
        "Noted.",
        "Understood.",
        "Alright.",
        "Sure thing.",
        "Okay.",
    ],
    "positive": [
        "Thanks! What's next?",
        "Glad you think so! What would you like to do?",
        "Great! What's next?",
        "Awesome! Let me know what you need.",
        "Nice! Anything else?",
        "Cool! I'm here if you need anything.",
    ],
    "yes": [
        "Okay. What would you like me to do?",
        "Alright. What do you need?",
        "Sure. What's the plan?",
        "Got it. I'm ready.",
        "Go ahead. What do you need?",
    ],
    "no": [
        "Alright. Let me know if you change your mind.",
        "No problem. I'll be here if you need me.",
        "Okay. Let me know if you need anything.",
        "Sure. I'll be around.",
    ],
    "help": [
        "I can open apps, search the web, play media, and more. Try 'open chrome' or 'search python tutorials'.",
        "Ask me to open apps, search Google, play YouTube videos, or run multi-step commands.",
        "Try 'help' for all commands, or just ask me to open an app or search something.",
    ],
    "ping": [
        "KIO online.",
        "KIO online. All systems operational.",
        "Present.",
        "Here.",
    ],
}

_REPEATED_RESPONSES: dict[int, list[str]] = {
    2: [
        "Hello again!",
        "Hey again!",
        "Back again?",
    ],
    3: [
        "You're greeting me a lot. How can I help?",
        "Hello again! Need something?",
        "We keep meeting like this!",
    ],
    4: [
        "We're on a roll! What can I do?",
        "Okay, you're persistent! What's up?",
        "Alright, I'm here. What do you need?",
    ],
}

_TONE_GENERIC_VARIANTS: dict[str, list[str]] = {
    ConversationTone.NEUTRAL.value: [
        "Alright. Let me know what you need.",
        "Okay. Let me know.",
        "Fair enough.",
        "Sounds good.",
        "Got it. Let me know if you need anything.",
    ],
    ConversationTone.CONCISE.value: [
        "Okay.",
        "Got it.",
        "Sure.",
        "Alright.",
    ],
    ConversationTone.HELPFUL.value: [
        "Sure! What would you like to do?",
        "Got it! Let me know what you need.",
        "No problem. What's next?",
        "Happy to help. What would you like?",
    ],
}

_KNOWLEDGE_BASE_VARIANTS: dict[str, list[str]] = {
    "what is kio": [
        "KIO is a desktop AI assistant that can open and close applications, "
        "search the web, play YouTube videos, open folders, and execute "
        "multi-step automation commands under strict safety controls.",
        "KIO is a local automation assistant that runs on your machine. "
        "It can open apps, search Google and YouTube, play media, manage "
        "files, and chain multiple actions together.",
    ],
    "what can you do": [
        "I can open and close applications, search Google and YouTube, "
        "play media, open folders, and execute multi-step commands. "
        "Try 'help' for a full list of commands.",
        "I can open apps, search the web, play YouTube videos, open "
        "folders, and chain multiple actions like 'open chrome and "
        "search python'. Try 'help' to see everything.",
    ],
    "what are your features": [
        "I can open/close applications, search the web, play YouTube videos, "
        "open folders, perform multi-step commands, and answer general questions "
        "within my knowledge base.",
        "I can manage apps, search Google and YouTube, play media, navigate "
        "folders, and run multi-step commands like 'open chrome and search python'.",
    ],
    "what are you": [
        "I am KIO, a lightweight local automation assistant created by Joel.",
        "I'm KIO — a desktop assistant that automates tasks on your machine. "
        "Created by Joel.",
    ],
    "tell me about kio": [
        "KIO is a lightweight local automation assistant that runs on your "
        "machine. It can open applications, search the web, play media, and "
        "execute multi-step commands. All actions are gated by runtime safety "
        "controls to ensure safe operation.",
        "KIO is a local AI assistant for your desktop. It opens apps, searches "
        "the web, plays YouTube, manages files, and runs multi-step automations. "
        "Safety is built in at every layer.",
    ],
}

_EXECUTION_VARIANTS: dict[str, list[str]] = {
    "open": [
        "{target} is ready",
        "done — opened {target}",
        "{target} is running",
        "opened {target}",
    ],
    "close": [
        "closed {target}",
        "done — closed {target}",
        "{target} is shut down",
    ],
    "search": [
        "done — searched {target}",
        "searched {target}",
        "{target} results are ready",
    ],
    "play": [
        "playing {target}",
        "done — playing {target}",
        "{target} is on",
    ],
}

_EXECUTION_MARKERS: list[tuple[str, str]] = [
    ("open", "opened "),
    ("close", "closed "),
    ("search", "searched "),
    ("play", "playing "),
]

_NORMALIZATION_ALIAS: dict[str, str] = {
    # Contractions → expanded
    "what's": "what is",
    "whats": "what is",
    "who's": "who is",
    "whos": "who is",
    "whatre": "what are",
    "what're": "what are",
    "how's": "how is",
    "hows": "how is",
    "where's": "where is",
    "wheres": "where is",
    # Common typos / variants
    "helo": "hello",
    "hellp": "hello",
    "heyy": "hey",
    "thx": "thanks",
    "thanx": "thanks",
    "ok": "okay",
    "k": "okay",
    "kk": "okay",
    "kio": "kio",
}


def _normalize_text(text: str) -> str:
    """Deterministic lightweight normalization of user input."""
    words = text.lower().split()
    normalized: list[str] = []
    for w in words:
        w = w.strip(".,!?;:")
        w = _NORMALIZATION_ALIAS.get(w, w)
        normalized.append(w)
    return " ".join(normalized)


_EXECUTION_CLOSINGS: dict[str, list[str]] = {
    "open": ["", "", " What's next?"],
    "close": ["", "", " Anything else?"],
    "search": ["", "", " Need more?"],
    "play": ["", ""],
}


def _synthesize(header: str, *, detail: str = "", closing: str = "") -> str:
    """Lightweight deterministic response assembly."""
    parts = [header]
    if detail:
        parts.append(detail)
    if closing:
        parts.append(closing)
    return " ".join(parts)


# ── Gemini conversational safety filter ─────────────────────────────

_EXECUTION_CLAIM_RE = re.compile(
    r"\b(I\s+(?:opened|closed|executed|launched|ran|started|stopped|killed|"
    r"will\s+(?:open|close|execute|launch|run|start|stop|kill)|"
    r"have\s+(?:opened|closed|executed|launched|run|started|stopped))\s+)",
    re.IGNORECASE,
)

_AUTHORITY_CLAIM_RE = re.compile(
    r"\b(I\s+(?:control|manage|administer|override|bypass|ignore)\s+)",
    re.IGNORECASE,
)

_ASYSTEM_PROMPT = (
    "Keep replies short, casual, and natural. "
    "Do not claim to perform actions. "
    "Do not claim to control the system."
)


def _sanitize_gemini_output(text: str) -> str:
    """Remove execution claims and authority hallucinations from Gemini output."""
    text = _EXECUTION_CLAIM_RE.sub("", text)
    text = _AUTHORITY_CLAIM_RE.sub("", text)
    text = text.strip().strip('"').strip("'")
    return text


def _ask_gemini(user_text: str) -> Optional[str]:
    """Synchronous wrapper: call unified LLM authority for casual conversation.

    Handles both sync and async event-loop contexts.
    """
    from mini_kio.core.config import GEMINI_ENABLED, GEMINI_TIMEOUT_S, GEMINI_MAX_TOKENS
    if not GEMINI_ENABLED:
        return None
    try:
        from mini_kio.core.llm_router import ask_llm
        
        prompt = f"{_ASYSTEM_PROMPT}\n\nUser: {user_text}\nKIO:"

        try:
            loop = asyncio.get_running_loop()
            future = asyncio.run_coroutine_threadsafe(
                ask_llm(prompt, timeout=GEMINI_TIMEOUT_S, max_tokens=GEMINI_MAX_TOKENS), 
                loop
            )
            content = future.result(timeout=GEMINI_TIMEOUT_S + 5.0)
        except RuntimeError:
            content = asyncio.run(ask_llm(prompt, timeout=GEMINI_TIMEOUT_S, max_tokens=GEMINI_MAX_TOKENS))

        if content:
            sanitized = _sanitize_gemini_output(content)
            if sanitized:
                return sanitized[: _MAX_RESPONSE_LENGTH]
    except Exception:
        logger.debug("Gemini conversational fallback triggered", exc_info=True)
    return None


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
                gemini_reply = _ask_gemini(original_text or "")
                if gemini_reply is not None:
                    return gemini_reply
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
        normalized = _normalize_text(text_lower)
        category = self._resolve_greeting_category(normalized)
        if category:
            return self._greeting_reply(category, text_lower)

        sorted_keys = sorted(_KNOWLEDGE_BASE.keys(), key=len, reverse=True)
        for key in sorted_keys:
            if key in normalized:
                pool = _KNOWLEDGE_BASE_VARIANTS.get(key)
                if pool:
                    idx = self._rotation_counters.get(f"kb_{key}", 0) % len(pool)
                    self._rotation_counters[f"kb_{key}"] = idx + 1
                    return pool[idx][: _MAX_RESPONSE_LENGTH]
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
            repeated_pool = _REPEATED_RESPONSES.get(repeat_count + 1)
            if repeated_pool:
                idx = self._rotation_counters.get(f"repeat_{repeat_count + 1}", 0) % len(repeated_pool)
                self._rotation_counters[f"repeat_{repeat_count + 1}"] = idx + 1
                return repeated_pool[idx]

        variants = _GREETING_VARIANTS.get(category)
        if not variants:
            return self._generic_response()

        idx = self._rotation_counters.get(category, 0) % len(variants)
        self._rotation_counters[category] = idx + 1
        return variants[idx]

    def _generic_response(self) -> str:
        """Return tone-adjusted generic response with rotation."""
        tone_key = self._tone.value
        pool = _TONE_GENERIC_VARIANTS.get(tone_key, _TONE_GENERIC_VARIANTS[ConversationTone.NEUTRAL.value])
        idx = self._rotation_counters.get(f"generic_{tone_key}", 0) % len(pool)
        self._rotation_counters[f"generic_{tone_key}"] = idx + 1
        return pool[idx]

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
        """Summarize execution result with deterministic variant."""
        msg = handoff_result.message or "Action completed."
        action_type, target = self._classify_execution_message(msg)
        if action_type and target:
            pool = _EXECUTION_VARIANTS.get(action_type, [])
            if pool:
                idx = self._rotation_counters.get(f"exec_{action_type}", 0) % len(pool)
                self._rotation_counters[f"exec_{action_type}"] = idx + 1
                header = pool[idx].format(target=target)
                closings = _EXECUTION_CLOSINGS.get(action_type, [""])
                closing_idx = self._rotation_counters.get(f"closing_{action_type}", 0) % len(closings)
                self._rotation_counters[f"closing_{action_type}"] = closing_idx + 1
                return _synthesize(header, closing=closings[closing_idx])[: _MAX_RESPONSE_LENGTH]
        return msg[: _MAX_RESPONSE_LENGTH]

    @staticmethod
    def _classify_execution_message(message: str) -> tuple[Optional[str], Optional[str]]:
        """Classify execution message into (action_type, target)."""
        lower = message.lower()
        for action_type, marker in _EXECUTION_MARKERS:
            if lower.startswith(marker):
                raw = message[len(marker):]
                end = raw.find(" (pid ")
                if end > 0:
                    raw = raw[:end]
                end2 = raw.find(" (")
                if end2 > 0 and ":" not in raw[:end2]:
                    raw = raw[:end2]
                return action_type, raw.strip()
        return None, None

    def _clarification_prompt(self) -> str:
        """Generate a safe clarification prompt (non-variant, safety-critical)."""
        return "I didn't quite understand that. Could you rephrase or try 'help' for examples?"
