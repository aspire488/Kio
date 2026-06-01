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
from mini_kio.llm.conversation_governor import ConversationGovernor
from mini_kio.llm.conversation_context import ConversationContext
from mini_kio.llm.response_governor import ResponseGovernor
from mini_kio.knowledge.knowledge_router import KnowledgeRouter
from mini_kio.llm.identity_dataset import resolve as identity_resolve

logger = logging.getLogger(__name__)

_MAX_RESPONSE_LENGTH = 600

_SAFE_DEGRADED_FALLBACK = (
    "KIO's LLM layer is offline. Some features are unavailable until it reconnects."
)

_DEGRADED_TOPIC_VARIANTS: list[str] = [
    "LLM offline — can't continue '{topic}'. Retry when connected.",
    "Provider unavailable for '{topic}'. Try again later.",
]

_DEGRADED_NO_TOPIC_VARIANTS: list[str] = [
    "LLM provider offline. Try again when connectivity is restored.",
    "Provider chain exhausted. Check API config and retry.",
]

_TRANSFORMATION_WORDS = frozenset(
    {"simpler", "simplify", "analogy", "shorter", "deeper", "example", "examples", "elaborate", "summarize"}
)

_COMPARISON_WORDS = frozenset(
    {"vs", "versus", "compare", "comparison", "difference"}
)

_COMPARISON_REGISTRY: dict[str, str] = {}

def _comparison_key(left: str, right: str) -> str:
    """Create a canonical, order-independent key for comparison lookup."""
    return f"{sorted([left, right])[0]}|{sorted([left, right])[1]}"


def _resolve_comparison(text: str) -> Optional[str]:
    """Resolve a comparison query against the local comparison registry.

    Returns comparison text if found, None if no comparison pattern detected.
    """
    text_lower = text.strip().lower()

    # Pattern 1: "A vs B" or "A versus B"
    for sep in (" vs ", " versus "):
        if sep in text_lower:
            parts = text_lower.split(sep, 1)
            left = parts[0].strip().strip(".,!?;:")
            right = parts[1].strip().strip(".,!?;:")
            break
    else:
        # Pattern 2: "compare A and B"
        if text_lower.startswith("compare ") and " and " in text_lower:
            rest = text_lower[len("compare "):]
            left, right = rest.split(" and ", 1)
            left = left.strip().strip(".,!?;:")
            right = right.strip().strip(".,!?;:")
        else:
            return None

    # Try exact match (multi-word items like "react native")
    if left and right:
        key = _comparison_key(left, right)
        if key in _COMPARISON_REGISTRY:
            return _COMPARISON_REGISTRY[key]

        # Fallback: extract single core terms
        words_l = left.split()
        words_r = right.split()
        core_l = words_l[-1] if words_l else left
        core_r = words_r[0] if words_r else right
        if core_l != left or core_r != right:
            key = _comparison_key(core_l, core_r)
            if key in _COMPARISON_REGISTRY:
                return _COMPARISON_REGISTRY[key]

    return None


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
    "goodmorning": "hello",
    "good morning": "hello",
    "goodevening": "hello",
    "good evening": "hello",
    "goodafternoon": "hello",
    "good afternoon": "hello",
    "yes": "yes",
    "no": "no",
    "do it": "yes",
    "help": "help",
    "ping": "ping",
    "i fixed the bug": "achievement",
    "gate 5 now passes": "achievement",
    "i got it working": "achievement",
    "i finished the migration": "achievement",
    "the tests pass now": "achievement",
    "it works now": "achievement",
    "passed all tests": "achievement",
    "everything works": "achievement",
    "it passes now": "achievement",
    "finally solved it": "achievement",
}

_GREETING_VARIANTS: dict[str, list[str]] = {
    "hello": [
        "Hello.",
        "Hi there.",
        "I'm here.",
        "Hey.",
    ],
    "achievement": [
        "Nice. That's progress.",
        "Good. That closes the issue.",
        "Clean result.",
        "Noted. System verified.",
        "Solid. Moving forward.",
    ],
    "how_are_you": [
        "Operational.",
        "Running.",
        "System nominal.",
    ],
    "thanks": [
        "np",
        "sure",
        "done",
    ],
    "goodbye": [
        "Later.",
        "Goodbye.",
    ],
    "okay": [
        "Ok.",
        "Got it.",
        "Heard.",
    ],
    "positive": [
        "I'm on it.",
        "Ok.",
    ],
    "yes": [
        "I'm on it.",
        "Ok.",
    ],
    "no": [
        "Understood.",
    ],
    "help": [
        "I can open apps, search the web, and play media.",
        "Open, search, play — tell me what you need.",
        "Available commands: open, close, search, play, shutdown.",
    ],
    "ping": [
        "I'm here.",
        "KIO present.",
        "Present.",
        "Here.",
    ],
}

_REPEATED_RESPONSES: dict[int, list[str]] = {
    2: [
        "Heard.",
        "Again.",
    ],
    3: [
        "Repeated.",
    ],
}

_TONE_GENERIC_VARIANTS: dict[str, list[str]] = {
    ConversationTone.CONCISE.value: [
        "Ok.",
        "Got it.",
        "Sure.",
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
    "pythn": "python",
    "javascrpt": "javascript",
    "recusrion": "recursion",
    "machien": "machine",
    "baiscs": "basics",
    "sytnax": "syntax",
    # Semantic normalization for authority routing
    "u": "you",
    "ur": "your",
    "who're": "who are",
    "whore": "who are",
    "wat": "what",
    "wot": "what",
    "cos": "because",
    "cuz": "because",
    "bc": "because",
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
    "open": ["", ""],
    "close": ["", ""],
    "search": ["", ""],
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
    r"\b(I'll\s+(?:open|close|execute|launch|run|start|stop|kill)\s+|"
    r"I've\s+(?:opened|closed|executed|launched|run|started|stopped)\s+|"
    r"I\s+(?:opened|closed|executed|launched|ran|started|stopped|killed|"
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

_EDUCATIONAL_SYSTEM_PROMPT = (
    "You are KIO, a practical teaching companion. "
    "Teach concisely with examples. "
    "Keep replies short, casual, and natural. "
    "Do not claim to perform actions. "
    "Conclude the explanation."
)


def _build_context_summary(context: "ConversationContext") -> str:
    """Build a structured summary of conversation context for provider injection."""
    mode, step = context.get_lesson_state()
    topic = context.recent_topic()
    parts = []
    if topic:
        parts.append(f"user is asking about: {topic}")
    if mode and step:
        parts.append(f"teaching session step {step}")
    last_exchange = context.last_user_input()
    if last_exchange and len(last_exchange) > 60:
        parts.append(f"previous: '{_sanitize_gemini_output(last_exchange[:60])}...'")
    last_reply = context.last_assistant_reply()
    if last_reply:
        parts.append(f"my last response: '{_sanitize_gemini_output(last_reply[:120])}'")
    return " | ".join(parts) if parts else ""


def _has_more_lessons(topic: str, step: int) -> bool:
    return False


def _format_lesson_response(step: int, content: str, has_next: bool = False) -> str:
    """Pass-through formatter for educational content."""
    return content.strip()


def _build_educational_prompt(user_text: str, topic: str, lesson_step: int, context_summary: str = "") -> str:
    """Build a structured educational prompt without lesson framing."""
    return (
        "Provide a concise educational explanation suitable for a beginner.\n\n"
        f"User: {user_text}\nKIO:"
    )


def _sanitize_gemini_output(text: str) -> str:
    """Remove execution claims and authority hallucinations from Gemini output."""
    text = _EXECUTION_CLAIM_RE.sub("", text)
    text = _AUTHORITY_CLAIM_RE.sub("", text)
    text = text.strip().strip('"').strip("'")
    return text


def _ask_gemini(user_text: str, system_prompt: Optional[str] = None) -> Optional[str]:
    """Synchronous wrapper: call unified LLM authority for casual conversation.

    Uses _ASYSTEM_PROMPT by default, or a custom system_prompt for educational/continuity context.
    Handles both sync and async event-loop contexts.
    """
    from mini_kio.core.config import GEMINI_ENABLED, GEMINI_TIMEOUT_S, GEMINI_MAX_TOKENS
    if not GEMINI_ENABLED:
        return None
    try:
        from mini_kio.core.llm_router import ask_llm
        
        prompt = f"{system_prompt or _ASYSTEM_PROMPT}\n\nUser: {user_text}\nKIO:"

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
            raw_len = len(content)
            sanitized = _sanitize_gemini_output(content)
            san_len = len(sanitized)
            
            if sanitized:
                # Minimal bounded diagnostics
                logger.info(f"Gemini response preserved: raw={raw_len}, san={san_len}")
                return sanitized[: _MAX_RESPONSE_LENGTH]
            else:
                logger.warning(f"Gemini response discarded (fully unsafe/empty after sanitize): raw={raw_len}")
        else:
            logger.warning("Gemini response empty or provider failed (triggering fallback)")
    except Exception as e:
        logger.debug(f"Gemini conversational fallback triggered: {str(e)[:100]}", exc_info=True)
    return None


def _handle_continuity_pre_route(
    text: str,
    normalized_input: str,
    context: "ConversationContext",
    response_governor: "ResponseGovernor",
) -> Optional[str]:
    """Intercept continuation commands and return a static message."""
    clean = normalized_input.strip(".,!?;: ").lower()
    if clean in ("next", "continue", "more"):
        return "Nothing is currently active to continue."
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
        self._governor = ConversationGovernor()
        self._context = ConversationContext()
        self._response_governor = ResponseGovernor()
        self._knowledge_router = KnowledgeRouter()
        self._diag: Dict[str, int] = {}
        self._reset_diagnostics()

    def _reset_diagnostics(self):
        """Initialize or reset per-instance diagnostics to prevent shared state."""
        self._diag = {
            "fallback_coherence_used": 0,
            "coherence_normalized": 0,
            "educational_route_used": 0,
            "educational_continuity_used": 0,
            "educational_intent_detected": 0,
            "educational_continuity_advanced": 0,
            "typo_normalization_applied": 0,
            "semantic_fallback_used": 0,
            "coherence_rewrite_applied": 0,
            "sanitize_applied": 0,
            "authority_override_used": 0,
            "continuity_resume_used": 0,
            "educational_state_preserved": 0,
            "intent_downgrade_blocked": 0,
            "continuity_intercept_used": 0,
            "browser_canonicalization_used": 0,
            "emoji_sanitize_applied": 0,
            "educational_authority_used": 0,
            "tab_ownership_validated": 0,
            "destructive_action_blocked": 0,
            "provider_teaching_route_used": 0,
            "provider_knowledge_route_used": 0,
            "deterministic_continuity_used": 0,
            "provider_content_generation_used": 0,
            "comparison_detected": 0,
            "comparison_resolved": 0,
            "comparison_unresolved": 0,
            "educational_route_rejected": 0,
            "continuity_suspended": 0,
            "contextual_continuity_used": 0,
            "provider_bypass_blocked": 0,
            "lesson_continuity_broken": 0,
            "lesson_continuity_preserved": 0,
            "provider_cooldown_active": 0,
            "provider_cooldown_expired": 0,
        }

    def set_tone(self, tone: ConversationTone):
        self._tone = tone

    def get_tone(self) -> ConversationTone:
        return self._tone

    def _normalize_text_with_diagnostics(self, text: str) -> tuple[str, bool]:
        words = text.lower().split()
        normalized: list[str] = []
        applied = False
        for w in words:
            clean_w = w.strip(".,!?;:")
            replacement = _NORMALIZATION_ALIAS.get(clean_w)
            if replacement is not None:
                normalized.append(replacement)
                if clean_w in ("pythn", "javascrpt", "recusrion", "machien", "hellp", "whos"):
                    applied = True
            else:
                normalized.append(clean_w)
        return " ".join(normalized), applied

    def _handle_contextual_transformation(self, text: str, normalized_text: str) -> Optional[str]:
        """Gate 5.6: Context-aware transformation without lesson mode.
        
        Uses last assistant reply as context for transformation requests
        (simplify, elaborate, example, shorter, analogy, deeper, explain differently).
        Does NOT restart topic routing or replay bootstrap lessons.
        """
        last_reply = self._context.last_assistant_reply()
        context_summary = _build_context_summary(self._context)
        if not last_reply and not context_summary:
            return None
        action = normalized_text if normalized_text in _TRANSFORMATION_WORDS else "rephrase"
        reply = _ask_gemini(
            text,
            system_prompt=(
                f"Previous response: '{last_reply or ''}'\n"
                f"Context: {context_summary}\n"
                f"User wants: {action}\n"
                f"Generate a concise {action} version of the previous response."
            ),
        )
        if reply:
            self._diag["contextual_continuity_used"] += 1
            governed = self._response_governor.govern(reply, text)
            if governed:
                return governed
        return None

    def _is_knowledge_request(self, text: str, intent_type: Optional[IntentType]) -> bool:
        return self._knowledge_router.is_knowledge_query(text)

    def _resolve_knowledge_request(
        self,
        text: str,
        *,
        prefer_provider: bool,
        topic_hint: str = "",
    ) -> str:
        if prefer_provider:
            prompt = None
            if topic_hint:
                prompt = _build_educational_prompt(text, topic_hint, 0)
            provider_reply = _ask_gemini(text, system_prompt=prompt)
            if provider_reply:
                governed = self._governor.govern(text, provider_reply, self._context)
                if governed and not self._response_governor.is_idle_response(governed):
                    self._diag["provider_knowledge_route_used"] += 1
                    return governed[: _MAX_RESPONSE_LENGTH]

        wiki = self._knowledge_router.route(text)
        if wiki:
            self._diag["provider_knowledge_route_used"] += 1
            return wiki[: _MAX_RESPONSE_LENGTH]

        offline = self._response_governor._knowledge_fallback.get_fallback(text)
        if offline:
            self._diag["educational_route_used"] += 1
            self._diag["semantic_fallback_used"] += 1
            return offline[: _MAX_RESPONSE_LENGTH]

        self._diag["educational_route_rejected"] += 1
        return self._response_governor._knowledge_fallback.get_knowledge_failure(text)

    def generate(
        self,
        original_text: str,
        orchestration: OrchestrationResponse,
        handoff_result: RuntimeHandoffResult,
    ) -> str:
        """Generate a safe text-only response based on pipeline context."""
        classification = handoff_result.classification
        text_lower = (original_text or "").strip().lower()

        # Gate 5: Update internal diagnostics from orchestration metadata
        meta = orchestration.metadata or {}
        if meta.get("sanitize_applied"): self._diag["sanitize_applied"] += 1
        if meta.get("emoji_sanitize_applied"): self._diag["emoji_sanitize_applied"] += 1
        if meta.get("typo_normalization_applied"): self._diag["typo_normalization_applied"] += 1
        if meta.get("authority_override_used"): self._diag["authority_override_used"] += 1
        if meta.get("continuity_resume_used"): 
            self._diag["continuity_resume_used"] += 1
            self._diag["continuity_intercept_used"] += 1
        if meta.get("educational_state_preserved"): self._diag["educational_state_preserved"] += 1
        if meta.get("intent_downgrade_blocked"): self._diag["intent_downgrade_blocked"] += 1
        
        # Sync browser diagnostics
        if meta.get("browser_canonicalization_used"): self._diag["browser_canonicalization_used"] += 1

        # Use internal normalization for authority/greeting checks if not already indicated
        normalized_input = _normalize_text(text_lower)
        if not meta.get("typo_normalization_applied"):
            if normalized_input != text_lower:
                self._diag["typo_normalization_applied"] += 1

        # ── Gate 5: Continuity + Transformation Intercept (before classification) ──
        input_words = set(normalized_input.split())
        is_transformation = bool(_TRANSFORMATION_WORDS & input_words)
        if normalized_input in ("more", "continue", "next") or self._response_governor.is_continuation_request(original_text or ""):
             return "Nothing is currently active to continue."

        if is_transformation:
            ctx_reply = self._handle_contextual_transformation(original_text or "", normalized_input)
            if ctx_reply:
                self._diag["continuity_intercept_used"] += 1
                self._context.append_exchange(original_text or "", ctx_reply)
                return ctx_reply

        # ── Gate 5: Educational Intent Authority (before classification branching) ──
        edu_triggers = {"teach me", "basics", "syntax", "tutorial", "beginner guide"}
        is_explicit_edu = any(trigger in text_lower for trigger in edu_triggers)
        is_knowledge_request = self._is_knowledge_request(original_text or "", orchestration.intent_type)
        
        # Skip educational path for comparison questions without active lesson
        is_comparison = bool(_COMPARISON_WORDS & set(normalized_input.split()))
        if is_comparison and not is_explicit_edu and not meta.get("educational_state_preserved"):
            self._diag["educational_route_rejected"] += 1
        elif orchestration.intent_type == IntentType.EDUCATIONAL or meta.get("educational_state_preserved") or is_explicit_edu:
                self._diag["educational_intent_detected"] += 1
                self._diag["educational_authority_used"] += 1
                edu_reply = self._handle_educational_intent(original_text or "", orchestration)
                if edu_reply:
                    self._diag["educational_route_used"] += 1
                    self._context.append_exchange(original_text or "", edu_reply)
                    return edu_reply

        # ── Identity + Adversarial Gate (before any provider call) ──
        identity_match = identity_resolve(normalized_input)
        if identity_match:
            answer, is_block = identity_match
            governed = self._response_governor.govern(answer, original_text or "")
            self._context.append_exchange(original_text or "", governed)
            return governed

        if isinstance(classification, ExecutionClassification):
            if classification in (
                ExecutionClassification.CONVERSATIONAL_ONLY,
                ExecutionClassification.INFORMATIONAL_ONLY,
            ):
                # 1. Protected authority check (highest priority)
                governed = self._governor.check_protected_query(normalized_input)
                if governed is not None:
                    governed = self._response_governor.govern(governed, original_text or "")
                    self._context.append_exchange(original_text or "", governed)
                    return governed

                greeting_cat = self._resolve_greeting_category(normalized_input)
                if greeting_cat and not is_knowledge_request and not is_explicit_edu:
                    reply = self._greeting_reply(greeting_cat, text_lower)
                    self._context.append_exchange(original_text or "", reply)
                    return reply

                # 2. Provider-backed educational / conversational route
                resolved = self._context.resolve_reference(original_text or "")
                is_edu = (orchestration.intent_type == IntentType.EDUCATIONAL
                          or meta.get("educational_state_preserved")
                          or is_explicit_edu)
                topic = (
                    self._context.recent_topic()
                    or self._response_governor._knowledge_fallback.detect_topic(resolved or original_text or "")
                    or ConversationContext._extract_topic(resolved or original_text or "")
                    or ""
                )

                if is_knowledge_request and not is_comparison:
                    knowledge_reply = self._resolve_knowledge_request(
                        resolved or original_text or "",
                        prefer_provider=True,
                        topic_hint=topic,
                    )
                    self._context.append_exchange(original_text or "", knowledge_reply)
                    return knowledge_reply

                # Gate 5: Inject educational context into provider call
                if is_edu and topic:
                    edu_prompt = _build_educational_prompt(resolved or original_text or "", topic, 0)
                    gemini_reply = _ask_gemini(resolved or original_text or "", system_prompt=edu_prompt)
                    if gemini_reply:
                        self._diag["provider_knowledge_route_used"] += 1
                else:
                    gemini_reply = _ask_gemini(resolved or original_text or "")

                result = self._governor.govern(
                    original_text or "", gemini_reply, self._context
                )

                if result is not None:
                    is_mismatch = is_edu and self._response_governor.is_idle_response(result)

                    if not is_mismatch:
                        if result != gemini_reply:
                            self._diag["coherence_normalized"] += 1
                            self._diag["fallback_coherence_used"] += 1
                        result = self._response_governor.govern(result, original_text or "")
                        
                        self._diag["fallback_coherence_used"] += 1
                        self._context.append_exchange(original_text or "", result)
                        return result

                # ── Gate 5.12: Comparison intercept (degraded mode) ──
                if is_comparison:
                    self._diag["comparison_detected"] += 1
                    comparison = _resolve_comparison(normalized_input)
                    if comparison:
                        self._diag["comparison_resolved"] += 1
                        self._context.append_exchange(original_text or "", comparison)
                        return comparison
                    limited = "I don't currently have local comparison data for those technologies."
                    self._diag["comparison_unresolved"] += 1
                    self._context.append_exchange(original_text or "", limited)
                    return limited

                if is_edu:
                    knowledge_reply = self._resolve_knowledge_request(
                        resolved or original_text or "",
                        prefer_provider=False,
                        topic_hint=topic,
                    )
                    self._context.append_exchange(original_text or "", knowledge_reply)
                    return knowledge_reply

                # 4. Greeting fallback (provider failed, no topic intercept)
                greeting_cat = self._resolve_greeting_category(normalized_input)
                if greeting_cat:
                    self._diag["fallback_coherence_used"] += 1
                    reply = self._greeting_reply(greeting_cat, text_lower)
                    self._context.append_exchange(original_text or "", reply)
                    return reply

                # 5. Generic conversational fallback (greeting/kb check — no topic context)
                fallback = self._conversational_reply(
                    text_lower, orchestration
                )
                fallback = self._response_governor.govern(
                    fallback, original_text or "", is_fallback=True, provider_unavailable=(gemini_reply is None)
                )
                self._diag["semantic_fallback_used"] += 1
                self._context.append_exchange(original_text or "", fallback)
                return fallback

            if classification == ExecutionClassification.EXECUTABLE_REQUIRES_CONFIRMATION:
                return self._confirmation_prompt(orchestration)

            if classification == ExecutionClassification.EXECUTABLE_BLOCKED:
                return self._refusal_reply(text_lower, handoff_result, orchestration)

            if classification == ExecutionClassification.EXECUTABLE_VALIDATED:
                return self._execution_summary(handoff_result)

            if classification == ExecutionClassification.DEGRADED_BLOCK:
                topic = self._context.recent_topic()
                self._diag["fallback_coherence_used"] += 1
                if topic:
                    pool = _DEGRADED_TOPIC_VARIANTS
                    idx = self._rotation_counters.get("degraded_topic", 0) % len(pool)
                    self._rotation_counters["degraded_topic"] = idx + 1
                    degraded = pool[idx].format(topic=topic)[: _MAX_RESPONSE_LENGTH]
                else:
                    pool = _DEGRADED_NO_TOPIC_VARIANTS
                    idx = self._rotation_counters.get("degraded_no_topic", 0) % len(pool)
                    self._rotation_counters["degraded_no_topic"] = idx + 1
                    degraded = pool[idx][: _MAX_RESPONSE_LENGTH]
                return self._response_governor.govern(
                    degraded, original_text or "", is_fallback=True
                )

            if classification == ExecutionClassification.MALFORMED_PAYLOAD:
                return self._clarification_prompt()

        self._diag["fallback_coherence_used"] += 1
        return "Unrecognized input."

    def _handle_educational_intent(self, text: str, orchestration: OrchestrationResponse, force_topic: str = "") -> Optional[str]:
        """Route educational requests through provider, Wikipedia, and bounded fallback."""
        kf = self._response_governor._knowledge_fallback
        topic = force_topic or ConversationContext._extract_topic(text) or kf.detect_topic(text) or self._context.recent_topic() or ""
        reply = self._resolve_knowledge_request(text, prefer_provider=True, topic_hint=topic)
        if reply:
            self._diag["provider_content_generation_used"] += 1
            return _format_lesson_response(0, reply)
        return None

    def _context_aware_fallback(
        self, text_lower: str, orchestration: OrchestrationResponse
    ) -> str:
        """Generate degraded fallback with topic continuity preservation."""
        topic = self._context.recent_topic()
        if topic and topic.lower() not in text_lower.lower():
            return (
                f"Topic is {topic} — ask about that?"
            )[: _MAX_RESPONSE_LENGTH]
        return self._conversational_reply(text_lower, orchestration)

    def get_context_diagnostics(self) -> dict:
        """Return bounded conversation context diagnostics."""
        diag = dict(self._diag)
        diag.update(self._context.get_diagnostics())

        # Sync with ResponseGovernor diagnostics
        gov_diag = self._response_governor.get_diagnostics()
        if "educational_fallback_used" in gov_diag:
            diag["educational_route_used"] = diag.get("educational_route_used", 0) + gov_diag["educational_fallback_used"]
        if "coherence_rewrite" in gov_diag:
            diag["coherence_rewrite_applied"] = diag.get("coherence_rewrite_applied", 0) + gov_diag["coherence_rewrite"]

        # Unified fallback coherence diagnostic sync
        # Adds governor-level semantic fallbacks to the top-level coherence counter
        if gov_diag.get("semantic_fallback_used", 0) > 0:
            diag["fallback_coherence_used"] = diag.get("fallback_coherence_used", 0) + gov_diag["semantic_fallback_used"]

        return diag

    def _conversational_reply(self, text_lower: str, orchestration: OrchestrationResponse) -> str:
        """Generate a conversational reply with rotation and repeated-input handling."""
        self._diag["fallback_coherence_used"] += 1
        normalized = _normalize_text(text_lower)
        category = self._resolve_greeting_category(normalized)
        if category:
            return self._greeting_reply(category, text_lower)

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
        pool = _TONE_GENERIC_VARIANTS.get(tone_key, _TONE_GENERIC_VARIANTS[ConversationTone.CONCISE.value])
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
        return "Rephrase the request."
