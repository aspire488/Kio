"""
query_classifier.py — Query Type Classification

Gate 5.7: Classifies user input into QueryType BEFORE any continuity,
entity, or retrieval processing. CHAT/FACTUAL_QA/REASONING/PLANNING/
CODING/DEBUGGING queries bypass ContinuityResolver, MediaIntelligence,
and Exa entirely, routing directly to NVIDIA ask_llm().
"""

import logging
import re
from enum import Enum
from typing import Optional

logger = logging.getLogger(__name__)


class QueryType(Enum):
    CHAT = "chat"
    FACTUAL_QA = "factual_qa"
    REASONING = "reasoning"
    PLANNING = "planning"
    CODING = "coding"
    DEBUGGING = "debugging"
    MEDIA_COMMAND = "media_command"
    DEVICE_COMMAND = "device_command"
    FOLLOWUP = "followup"


# ── Media command verbs (single-word commands) ─────────────────────
_MEDIA_VERBS = frozenset({
    "play", "pause", "resume", "next", "previous", "stop",
    "watch", "listen",
})

# ── Device command verbs (single-word commands) ────────────────────
_DEVICE_VERBS = frozenset({
    "open", "close", "launch", "switch", "focus", "minimize", "maximize",
})

# ── Coding keywords ────────────────────────────────────────────────
_CODING_RE = re.compile(
    r"\b(code|program|function|script|implement|"
    r"write\s+(a\s+)?(python|js|java|rust|go|ruby|php|script|function|program|class)|"
    r"create\s+(a\s+)?(function|script|program|module))\b",
    re.I,
)

# ── Debugging keywords ─────────────────────────────────────────────
_DEBUGGING_RE = re.compile(
    r"\b(debug|fix|bug|error|exception|traceback|stack\s+trace|crash|"
    r"segfault|null\s+pointer|index\s+out\s+of\s+bounds)\b",
    re.I,
)

# ── Reasoning keywords ─────────────────────────────────────────────
_REASONING_RE = re.compile(
    r"\b(why|how\s+(does|do|can|would|should|could|will)|"
    r"explain|reason|what\s+(is|are)\s+the\s+(difference|cause|reason)|"
    r"what\s+would\s+happen|"
    r"compare|contrast|analyze|analyse)\b",
    re.I,
)

# ── Planning keywords ──────────────────────────────────────────────
_PLANNING_RE = re.compile(
    r"\b(plan|strategy|roadmap|steps\s+to|"
    r"how\s+to\s+(build|create|make|implement|design|architect|set\s+up)|"
    r"architecture|blueprint|workflow)\b",
    re.I,
)

# ── Reference-only vocabulary for followup detection ───────────────
# A query whose every word belongs to this set is a followup (no
# standalone subject — pure pronoun/verb reference to previous entity).
_REF_VOCAB = frozenset({
    # interrogatives
    "who", "what", "when", "where", "why", "how", "which", "whose",
    # auxiliaries
    "is", "are", "was", "were", "be", "been", "being", "am",
    "do", "does", "did", "done", "doing",
    "can", "could", "will", "would", "shall", "should", "may", "might", "must",
    "has", "have", "had",
    # pronouns
    "i", "you", "he", "she", "it", "we", "they",
    "me", "him", "her", "us", "them",
    "my", "your", "his", "its", "our", "their",
    "mine", "yours", "hers", "theirs",
    "this", "that", "these", "those",
    # determiners
    "a", "an", "the",
    # prepositions
    "in", "on", "at", "to", "for", "of", "with", "by", "from", "about",
    "up", "down", "over", "under", "around", "through", "into", "onto",
    "during", "before", "after", "between", "among",
    # conjunctions
    "and", "or", "but", "so", "if", "then", "than", "because",
    # common verbs (actions without specific subject)
    "play", "open", "close", "stop", "pause", "resume", "continue",
    "tell", "show", "give", "get", "find", "search", "go", "do", "make",
    "watch", "listen", "launch", "switch", "focus", "minimize", "maximize",
    "start", "end", "begin", "finish", "try", "use",
    "work", "works", "worked", "working",
    "look", "looks", "looked", "seem", "seems", "seemed",
    "say", "says", "said", "see", "sees", "saw", "seen",
    "take", "takes", "took", "taken",
    "directed", "created", "wrote", "made", "sang", "sings", "played", "plays",
    "composed", "produced", "released", "writes", "directs", "creates",
    "act", "acts", "star", "stars", "starred", "starring",
    "sing", "song", "track", "album",
    "know", "want", "need", "like", "think", "mean",
    "call", "called", "named", "known",
    "happen", "happened", "happens",
    "come", "comes", "came",
    # adverbs / modifiers
    "not", "no", "yes", "ok", "okay", "sure", "please", "pls",
    "more", "again", "also", "too", "very", "just", "only", "now",
    "here", "there",
    "next", "previous", "last",
    "first", "second", "third",
    "some", "any", "all", "every", "each", "both", "few", "many", "much",
    "already", "ever", "never", "always", "still", "yet",
    # others
    "me", "yourself", "myself", "itself",
    "something", "anything", "everything", "nothing",
    "someone", "anyone", "everyone", "nobody",
})


def _is_pure_reference(text: str) -> bool:
    """Return True if every word in the query is a reference-only word.

    A pure-reference query has no standalone named entity; it refers
    entirely to the previous context via pronouns, auxiliaries,
    prepositions, and common action verbs.
    """
    lower = text.strip().lower()
    words = lower.split()
    if not words:
        return False
    return all(w in _REF_VOCAB for w in words)


def classify_input(text: str) -> tuple[QueryType, Optional[str]]:
    """Classify user input into QueryType and resolved task_type string.

    Returns:
        (QueryType, task_type_str)
        task_type_str is one of "chat", "coding", "debugging",
        "reasoning", "planning" for LLM types; None otherwise.
    """
    stripped = text.strip()
    if not stripped:
        return QueryType.CHAT, "chat"

    lower = stripped.lower()
    words = lower.split()
    first_word = words[0] if words else ""

    # ── 1. Media commands ──────────────────────────────────────────
    if first_word in _MEDIA_VERBS:
        return QueryType.MEDIA_COMMAND, None

    # ── 2. Device commands ─────────────────────────────────────────
    if first_word in _DEVICE_VERBS:
        return QueryType.DEVICE_COMMAND, None

    # ── 3. Followup detection (short, pure-reference query) ────────
    if len(words) < 5 and _is_pure_reference(stripped):
        return QueryType.FOLLOWUP, None

    # ── 4. Coding ──────────────────────────────────────────────────
    if _CODING_RE.search(lower):
        return QueryType.CODING, "coding"

    # ── 5. Debugging ───────────────────────────────────────────────
    if _DEBUGGING_RE.search(lower):
        return QueryType.DEBUGGING, "debugging"

    # ── 6. Reasoning ───────────────────────────────────────────────
    if _REASONING_RE.search(lower):
        return QueryType.REASONING, "reasoning"

    # ── 7. Planning ────────────────────────────────────────────────
    if _PLANNING_RE.search(lower):
        return QueryType.PLANNING, "planning"

    # ── 8. Default: CHAT (includes factual QA) ─────────────────────
    return QueryType.CHAT, "chat"
