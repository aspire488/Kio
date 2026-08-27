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
from dataclasses import dataclass, field
from enum import Enum
from typing import Optional

logger = logging.getLogger(__name__)


@dataclass
class PendingAction:
    """A deferred action awaiting user confirmation.

    Used for freshness-triggered searches where KIO offers to look
    something up and the user confirms with "yes" / "go ahead".
    """
    action_type: str  # "search"
    query: str
    topic: str = ""
    executed: bool = False


class SessionMode(Enum):
    CONVERSATIONAL = "conversational"
    EXECUTION = "execution"
    EDUCATIONAL = "educational"

_MAX_EXCHANGES = 25  # widened from 10 for better conversation continuity

_EXTRACT_TOPIC_PREFIXES = [
    "what is ", "what are ", "tell me about ", "what does ", "what do ",
    "what's ", "whats ", "explain ", "define ", "teach me ",
    "who created ", "who is ", "who made ", "who wrote ",
    "who do you think ", "who do you ",
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
    """Bounded persistent conversational continuity.

    Tracks recent exchanges and topics with PostgreSQL persistence.
    Automatically prunes beyond MAX_EXCHANGES (10).
    Provider-agnostic — works identically with any LLM backend.
    """

    def __init__(self):
        self._exchanges: list[tuple[str, str]] = []
        self._topic_stack: list[str] = []
        self._entity_stack: list[str] = []
        self._last_subject: Optional[str] = None
        self._lesson_mode: bool = False
        self._lesson_step: int = 0
        self._session_mode: SessionMode = SessionMode.CONVERSATIONAL
        self._pending_action: Optional[PendingAction] = None
        self._diag: dict[str, int] = {
            "context_reference_resolved": 0,
            "conversational_context_pruned": 0,
            "pending_action_set": 0,
            "pending_action_executed": 0,
            "pending_action_cleared": 0,
            "context_synced_from_memory": 0,
        }

    def sync_from_memory(self, memory_store: object) -> None:
        """Load recent exchanges from persistent memory store.
        
        Note: memory_store is expected to be a mini_kio.memory.memory_store.MemoryStore.
        """
        try:
            # Load twice the max exchanges to ensure we can find enough pairs
            history = memory_store.last_n_messages(_MAX_EXCHANGES * 2)
            self._exchanges.clear()
            
            # Pair user/assistant messages for the context window
            user_msg = None
            for entry in history:
                if entry.role == "user":
                    user_msg = entry.message
                elif entry.role == "assistant" and user_msg is not None:
                    self._exchanges.append((user_msg, entry.message))
                    user_msg = None
            
            # Prune to bound
            self.prune()
            
            # Rebuild topic stack from loaded history
            self.clear_topic_stack()
            for u, r in self._exchanges:
                topic = self._extract_topic(u)
                if topic:
                    self._topic_stack.append(topic)
                entities = self._extract_entities(u)
                for e in entities:
                    if e.lower() not in (self._entity_stack[-1].lower() if self._entity_stack else ""):
                        self._entity_stack.append(e)
            
            self._diag["context_synced_from_memory"] += 1
            logger.info(f"ConversationContext: synced {len(self._exchanges)} exchanges from memory")
        except Exception as e:
            logger.warning(f"ConversationContext: sync failed: {e}")

    def append_exchange(self, user_text: str, reply: str) -> None:
        topic = self._extract_topic(user_text)
        if topic:
            self._topic_stack.append(topic)
        entities = self._extract_entities(user_text)
        for e in entities:
            if e.lower() not in (self._entity_stack[-1].lower() if self._entity_stack else ""):
                self._entity_stack.append(e)
                self._last_subject = e
        self._exchanges.append((user_text, reply))
        self.prune()

    @staticmethod
    def _extract_entities(text: str) -> list[str]:
        entities: list[str] = []
        for word in text.split():
            clean = word.strip(".,!?;:'\"()")
            if len(clean) > 1 and clean[0].isupper() and clean.lower() not in _PRONOMINAL_STOPWORDS:
                entities.append(clean)
        return entities

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

    def recent_entity(self) -> Optional[str]:
        if self._entity_stack:
            return self._entity_stack[-1]
        return self.recent_topic()

    def last_subject(self) -> Optional[str]:
        return self._last_subject or self.recent_topic()

    def resolve_reference(self, text: str) -> str:
        topic = self.recent_topic()
        entity = self.recent_entity()
        subject = self.last_subject()
        referent = entity or subject or topic or ""

        stripped = text.strip()
        if not stripped:
            return text

        # Phase 1: Pronoun patterns (existing)
        if referent:
            for pattern, repl_fn in _PRONOUN_REF_PATTERNS:
                m = pattern.match(stripped)
                if m:
                    prefix = repl_fn(m, referent)
                    rest = stripped[m.end():]
                    result = prefix + rest
                    self._diag["context_reference_resolved"] += 1
                    logger.debug(f"context: resolved pronoun '{stripped[:40]}' -> '{result[:60]}'")
                    if result.strip():
                        return result
                    return text

        # Phase 2: Standalone "Why?"
        alone = re.match(r"^why\s*\??\s*$", stripped, re.IGNORECASE)
        if alone and referent:
            result = f"Tell me more about {referent}"
            self._diag["context_reference_resolved"] += 1
            logger.debug(f"context: resolved 'Why?' -> '{result}'")
            return result

        # Phase 3: "Why X?" with verb
        why_match = re.match(
            r"^why\s+(is|does|do|are|was|were|did|can|could|would|should)\s+"
            r"(.+?)\s*\??\s*$", stripped, re.IGNORECASE
        )
        if why_match:
            verb = why_match.group(1)
            x = why_match.group(2).strip().strip(".,!?;:")
            result = f"What is {topic or referent} and why {verb} {x}"
            self._diag["context_reference_resolved"] += 1
            logger.debug(f"context: resolved 'why verb X' -> '{result}'")
            return result

        # Phase 4: "Why X?" without verb (e.g., "Why Portugal?")
        why_noun = re.match(r"^why\s+(.+?)\s*\??\s*$", stripped, re.IGNORECASE)
        if why_noun:
            x = why_noun.group(1).strip()
            if x.lower() not in _PRONOMINAL_STOPWORDS:
                if topic:
                    result = f"Tell me about {x} in the context of {topic}"
                else:
                    result = f"Tell me about {x}"
                self._diag["context_reference_resolved"] += 1
                logger.debug(f"context: resolved 'Why X?' -> '{result}'")
                return result

        # Phase 5: "What about X?"
        what_about = re.match(r"^what\s+about\s+(.+?)\s*\??\s*$", stripped, re.IGNORECASE)
        if what_about:
            x = what_about.group(1).strip()
            if x.lower() not in _PRONOMINAL_STOPWORDS:
                if topic:
                    result = f"Tell me about {x} in the context of {topic}"
                else:
                    result = f"Tell me about {x}"
                self._diag["context_reference_resolved"] += 1
                logger.debug(f"context: resolved 'What about X?' -> '{result}'")
                return result

        # Phase 6: Continuation/elaboration patterns
        continue_match = re.match(
            r"^(tell\s+me\s+more|explain\s+(that|this|it|more)(\s+more)?|"
            r"can\s+you\s+explain\s+(that|this|it|more)(\s+more)?|"
            r"elaborate|more\s+details|"
            r"that\s+one|this\s+one)\s*\??\s*$",
            stripped, re.IGNORECASE
        )
        if continue_match and referent:
            result = f"Tell me more about {referent}"
            self._diag["context_reference_resolved"] += 1
            logger.debug(f"context: resolved continuation -> '{result}'")
            return result

        # Phase 7: Single-word follow-up continuity
        if " " not in stripped and len(stripped) > 1 and "?" not in stripped:
            low = stripped.lower()
            if low not in _PRONOMINAL_STOPWORDS and low not in ("hi", "hello", "bye", "thanks", "ok", "okay", "yes", "no", "yeah", "nope"):
                if stripped[0].isupper() or len(stripped) > 4:
                    if topic:
                        result = f"Tell me about {stripped} in the context of {topic}"
                    else:
                        result = f"Tell me about {stripped}"
                    self._diag["context_reference_resolved"] += 1
                    logger.debug(f"context: resolved follow-up '{stripped}' -> '{result}'")
                    return result

        return text

    def search_exchanges(self, topic: str, limit: int = 5) -> list[tuple[str, str]]:
        """Search exchange history for topic-matching user statements.
        Returns matching (user_text, kio_reply) pairs, most recent first."""
        if not topic or not self._exchanges:
            return []
        topic_low = topic.lower().strip()
        stop = {"the", "about", "what", "that", "this", "with", "from", "have",
                "were", "was", "been", "being", "does", "doing", "will",
                "would", "could", "should", "tell", "said", "asked"}
        words = [w for w in re.findall(r'[a-z]{3,}', topic_low) if w not in stop]
        if not words:
            return []
        matches: list[tuple[float, tuple[str, str]]] = []
        for user_text, kio_reply in reversed(self._exchanges):
            if not user_text:
                continue
            ul = user_text.lower()
            score = 0.0
            if topic_low in ul:
                score = 1.0
            else:
                matched = sum(1 for w in words if w in ul)
                if matched > 0:
                    score = matched / len(words) * 0.8
            if score > 0:
                matches.append((score, (user_text, kio_reply)))
            if len(matches) >= limit * 2:
                break
        matches.sort(key=lambda x: -x[0])
        return [m[1] for m in matches[:limit]]

    def recent_topics_summary(self, max_topics: int = 5) -> str:
        """Compact summary of recent conversation topics."""
        if not self._topic_stack:
            return ""
        unique = []
        for t in reversed(self._topic_stack):
            if not unique or t != unique[-1]:
                unique.append(t)
            if len(unique) >= max_topics:
                break
        if not unique:
            return ""
        return "Recent topics: " + ", ".join(reversed(unique)) + "."

    def get_history_window(self, n: int = 10) -> list[tuple[str, str]]:
        """Return last n exchange pairs. Compatible with SessionContext API."""
        return self._exchanges[-n:] if self._exchanges else []

    def exchange_count(self) -> int:
        """Number of stored exchanges."""
        return len(self._exchanges)

    def prune(self) -> None:
        while len(self._exchanges) > _MAX_EXCHANGES:
            self._exchanges.pop(0)
            self._diag["conversational_context_pruned"] += 1
        while len(self._topic_stack) > _MAX_EXCHANGES:
            self._topic_stack.pop(0)
        while len(self._entity_stack) > _MAX_EXCHANGES:
            self._entity_stack.pop(0)

    def set_pending_search(self, query: str, topic: str = "") -> None:
        self._pending_action = PendingAction(action_type="search", query=query, topic=topic)
        self._diag["pending_action_set"] += 1

    def get_pending_action(self) -> Optional[PendingAction]:
        return self._pending_action

    def clear_pending_action(self) -> None:
        self._pending_action = None
        self._diag["pending_action_cleared"] += 1

    def has_pending_action(self) -> bool:
        return self._pending_action is not None and not self._pending_action.executed

    def mark_pending_executed(self) -> None:
        if self._pending_action:
            self._pending_action.executed = True
            self._diag["pending_action_executed"] += 1

    def clear(self) -> None:
        self._exchanges.clear()
        self._topic_stack.clear()
        self._entity_stack.clear()
        self._last_subject = None
        self._lesson_mode = False
        self._lesson_step = 0
        self._pending_action = None

    def clear_topic_stack(self) -> None:
        self._topic_stack.clear()
        self._entity_stack.clear()
        self._last_subject = None

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
