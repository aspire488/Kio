"""
conversation_context.py — Gate 5D.3 Bounded Runtime-Only Conversational Continuity

HARD CONSTRAINTS:
- Bounded exchange count (max 10)
- Automatic pruning only
- No persistence
- No async/background systems
- Provider-agnostic
"""

import logging
import re
from enum import Enum
from typing import Optional

logger = logging.getLogger(__name__)


class SessionMode(Enum):
    CONVERSATIONAL = "conversational"
    EXECUTION = "execution"
    EDUCATIONAL = "educational"

_MAX_EXCHANGES = 10

_EXTRACT_TOPIC_PREFIXES = [
    "what is ", "what are ", "tell me about ", "what does ", "what do ",
    "what's ", "whats ", "explain ", "define ", "teach me ",
    "who created ", "who is ", "who made ", "who wrote ",
]

_PRONOMINAL_STOPWORDS = frozenset({
    "it", "this", "that", "they", "them", "he", "she", "him", "her",
    "you", "me", "we", "us", "i", "my", "your", "his", "her", "its",
    "our", "their", "mine", "yours", "theirs",
})

_KNOWN_ENTITIES = frozenset({
    "python", "javascript", "typescript", "java", "rust", "go",
    "ruby", "php", "swift", "kotlin", "scala", "r", "matlab",
    "linux", "windows", "macos", "ubuntu", "debian", "fedora",
    "git", "docker", "kubernetes", "vscode", "chrome",
})

_PRONOUN_REF_PATTERNS = [
    (re.compile(
        r"^(is|does|can|will|was|were|are|has|have|had|should|could|would)\s+"
        r"(it|this|that|they|he|she)\s+", re.IGNORECASE
    ), lambda m, topic: f"{m.group(1)} {topic} "),
    (re.compile(r"^what\s+about\s+(it|this|that|them)\s*", re.IGNORECASE),
     lambda m, topic: f"What about {topic} "),
    (re.compile(r"^tell\s+me\s+(more\s+)?about\s+(it|this|that|them)\s*", re.IGNORECASE),
     lambda m, topic: f"Tell me {m.group(1) or ''}about {topic} "),
    (re.compile(r"^(it|this|that)\s*$", re.IGNORECASE),
     lambda m, topic: f"Tell me about {topic}"),
]


class ConversationContext:
    """Bounded runtime-only conversational continuity.

    Tracks recent exchanges and topics without persistence.
    Automatically prunes beyond MAX_EXCHANGES (10).
    Provider-agnostic — works identically with any LLM backend.
    """

    def __init__(self):
        self._exchanges: list[tuple[str, str]] = []
        self._topic_stack: list[str] = []
        self._lesson_mode: bool = False
        self._lesson_step: int = 0
        self._session_mode: SessionMode = SessionMode.CONVERSATIONAL
        self._diag: dict[str, int] = {
            "context_reference_resolved": 0,
            "conversational_context_pruned": 0,
        }

    def append_exchange(self, user_text: str, reply: str) -> None:
        topic = self._extract_topic(user_text)
        if topic:
            self._topic_stack.append(topic)
        self._exchanges.append((user_text, reply))
        self.prune()

    def set_lesson_state(self, mode: bool, step: int) -> None:
        pass

    def get_lesson_state(self) -> tuple[bool, int]:
        return False, 0

    def get_session_mode(self) -> SessionMode:
        return self._session_mode

    def set_session_mode(self, mode: SessionMode) -> None:
        self._session_mode = mode

    def recent_topic(self) -> Optional[str]:
        if self._topic_stack:
            return self._topic_stack[-1]
        return None

    def resolve_reference(self, text: str) -> str:
        topic = self.recent_topic()
        if not topic:
            return text

        stripped = text.strip()
        if not stripped:
            return text

        for pattern, repl_fn in _PRONOUN_REF_PATTERNS:
            m = pattern.match(stripped)
            if m:
                prefix = repl_fn(m, topic)
                rest = stripped[m.end():]
                result = prefix + rest
                self._diag["context_reference_resolved"] += 1
                logger.debug(f"context: resolved '{stripped[:40]}' -> '{result[:60]}'")
                if result.strip():
                    return result
                return text

        # "Why X" follow-up resolution
        why_match = re.match(
            r"^why\s+(is|does|do|are|was|were|did|can|could|would|should)\s+"
            r"(.+?)\s*\??\s*$", stripped, re.IGNORECASE
        )
        if why_match:
            verb = why_match.group(1)
            x = why_match.group(2).strip().strip(".,!?;:")
            result = f"What is {topic} and why {verb} {x}"
            self._diag["context_reference_resolved"] += 1
            logger.debug(f"context: resolved 'why X' -> '{result}'")
            return result

        # Single-word follow-up continuity
        if " " not in stripped and len(stripped) > 1:
            # Skip if it's a known command or stopword
            if stripped.lower() not in _PRONOMINAL_STOPWORDS and stripped.lower() not in ("hi", "hello", "bye", "thanks", "ok", "okay"):
                # Capitalized words are likely entities (Portugal, Barcelona)
                if stripped[0].isupper() or len(stripped) > 4:
                    result = f"Tell me about {stripped} in the context of {topic}"
                    self._diag["context_reference_resolved"] += 1
                    logger.debug(f"context: resolved follow-up '{stripped}' -> '{result}'")
                    return result

        return text

    def prune(self) -> None:
        while len(self._exchanges) > _MAX_EXCHANGES:
            self._exchanges.pop(0)
            self._diag["conversational_context_pruned"] += 1
        while len(self._topic_stack) > _MAX_EXCHANGES:
            self._topic_stack.pop(0)

    def clear(self) -> None:
        self._exchanges.clear()
        self._topic_stack.clear()
        self._lesson_mode = False
        self._lesson_step = 0

    def clear_topic_stack(self) -> None:
        self._topic_stack.clear()

    def exchange_count(self) -> int:
        return len(self._exchanges)

    def get_diagnostics(self) -> dict[str, int]:
        return dict(self._diag)

    def last_user_input(self) -> Optional[str]:
        if self._exchanges:
            return self._exchanges[-1][0]
        return None

    def last_assistant_reply(self) -> Optional[str]:
        if self._exchanges:
            return self._exchanges[-1][1]
        return None

    @staticmethod
    def _extract_topic(text: str) -> Optional[str]:
        lower = text.lower().strip().strip(".,!?;:")
        if not lower:
            return None

        for prefix in _EXTRACT_TOPIC_PREFIXES:
            if lower.startswith(prefix):
                topic = text[len(prefix):].strip().strip(".,!?;:")
                if topic and len(topic) < 60 and topic.lower() not in _PRONOMINAL_STOPWORDS:
                    return topic

        m = re.search(
            r"(?:what|how)\s+(?:is|are|does|do)\s+(.+?)\s+"
            r"(?:work|mean|do|used|look\s+like)", lower
        )
        if m:
            topic = m.group(1).strip()
            if topic.lower() not in _PRONOMINAL_STOPWORDS:
                return topic

        m = re.search(r"tell\s+me\s+more\s+about\s+(.+)", lower)
        if m:
            topic = m.group(1).strip()
            if topic.lower() not in _PRONOMINAL_STOPWORDS:
                return topic

        # Extract topic from "why X" patterns
        why_match = re.search(
            r"^why\s+(is|does|do|are|was|were|did|can|could|would|should)\s+"
            r"(.+?)\s*\??\s*$", lower
        )
        if why_match:
            topic = why_match.group(2).strip().strip(".,!?;:")
            if topic and topic.lower() not in _PRONOMINAL_STOPWORDS and len(topic) < 60:
                return topic

        words = lower.split()
        for word in words:
            clean = word.strip(".,!?;:'\"")
            if clean in _KNOWN_ENTITIES:
                return clean

        original_words = text.split()
        for i, word in enumerate(original_words):
            if i == 0:
                continue
            clean = word.strip(".,!?;:'\"")
            if clean and clean[0].isupper() and len(clean) > 1 \
                    and clean.lower() not in _PRONOMINAL_STOPWORDS:
                return clean

        return None
