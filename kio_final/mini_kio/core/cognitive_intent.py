"""
cognitive_intent.py — Cognitive Intent Classification

Replaces query_classifier.py with a richer intent system.
14 intent values spanning cognition, agent, vision, media, device, followup.
"""

import logging
import re
from enum import Enum
from typing import Optional

logger = logging.getLogger(__name__)


class CognitiveIntent(Enum):
    CHAT = "chat"
    FACTUAL_QA = "factual_qa"
    REASONING = "reasoning"
    PLANNING = "planning"
    ARCHITECTURE = "architecture"
    CODING = "coding"
    DEBUGGING = "debugging"
    AGENT = "agent"
    VISION = "vision"
    OCR = "ocr"
    SCREEN_ANALYSIS = "screen_analysis"
    MEDIA = "media"
    DEVICE = "device"
    FOLLOWUP = "followup"


_MEDIA_VERBS = frozenset({
    "play", "pause", "resume", "next", "previous", "stop",
    "watch", "listen",
})

_DEVICE_VERBS = frozenset({
    "open", "close", "launch", "switch", "focus", "minimize", "maximize",
})

_AGENT_KW = re.compile(
    r"\b(login|sign\s+in|sign\s+up|register|submit|fill|upload|download|"
    r"scroll|click|type|enter|navigate|go\s+to)\b",
    re.I,
)

_ARCHITECTURE_KW = re.compile(
    r"\b(design\s+(a|an|the|this|my|our)\s+(\w+\s+)*(system|architecture|framework|component|module|service|"
    r"ownership|tracking|pattern|solution|model|interface|protocol|browser|ownership|tracking)|"
    r"architect(ure)?\s+(for|of|a|an)|"
    r"system\s+design|"
    r"component\s+diagram|"
    r"architecture\s+pattern|"
    r"ownership\s+model|"
    r"module\s+structure|"
    r"class\s+hierarchy|"
    r"data\s+flow|"
    r"api\s+design)\b",
    re.I,
)

_CODING_KW = re.compile(
    r"\b(code|program|function|script|implement|"
    r"write\s+(a\s+)?(python|js|java|rust|go|ruby|php|script|function|program|class)|"
    r"create\s+(a\s+)?(function|script|program|module))\b",
    re.I,
)

_DEBUGGING_KW = re.compile(
    r"\b(debug|fix|bug|error|exception|traceback|stack\s+trace|crash|"
    r"segfault|null\s+pointer|index\s+out\s+of\s+bounds)\b",
    re.I,
)

_REASONING_KW = re.compile(
    r"\b(why|how\s+(does|do|can|would|should|could|will)|"
    r"explain|reason|what\s+(is|are)\s+the\s+(difference|cause|reason)|"
    r"what\s+would\s+happen|"
    r"compare|contrast|analyze|analyse)\b",
    re.I,
)

_PLANNING_KW = re.compile(
    r"\b(plan|strategy|roadmap|steps\s+to|"
    r"how\s+to\s+(build|create|make|implement|design|architect|set\s+up)|"
    r"blueprint|workflow|timeline|schedule|milestone)\b",
    re.I,
)

_VISION_KW = re.compile(
    r"\b(image|picture|photo|screenshot|screen\s+shot|snapshot|"
    r"see\s+(what|the)|look\s+at\s+(this|the|that)|"
    r"what\s+(is|does)\s+this\s+(image|picture|photo|screenshot)|"
    r"upload|attached\s+(image|picture|photo))\b",
    re.I,
)

_SCREEN_KW = re.compile(
    r"\b(screenshot|screen\s+analysis|what\s+is\s+on\s+(this|the)\s+(screen|display)|"
    r"analyze\s+(this|the)\s+(screen|screenshot|display)|"
    r"what\s+do\s+you\s+see|"
    r"describe\s+(this|the)\s+(screen|screenshot))\b",
    re.I,
)

_OCR_KW = re.compile(
    r"\b(ocr|text\s+(in|from|inside|within)\s+(this|the)\s+(image|picture|photo|screenshot)|"
    r"extract\s+text|read\s+(the\s+)?text|"
    r"what\s+(does|is)\s+this\s+(say|written))\b",
    re.I,
)

_REF_VOCAB = frozenset({
    "who", "what", "when", "where", "why", "how", "which", "whose",
    "is", "are", "was", "were", "be", "been", "being", "am",
    "do", "does", "did", "done", "doing",
    "can", "could", "will", "would", "shall", "should", "may", "might", "must",
    "has", "have", "had",
    "i", "you", "he", "she", "it", "we", "they",
    "me", "him", "her", "us", "them",
    "my", "your", "his", "its", "our", "their",
    "mine", "yours", "hers", "theirs",
    "this", "that", "these", "those",
    "a", "an", "the",
    "in", "on", "at", "to", "for", "of", "with", "by", "from", "about",
    "up", "down", "over", "under", "around", "through", "into", "onto",
    "during", "before", "after", "between", "among",
    "and", "or", "but", "so", "if", "then", "than", "because",
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
    "not", "no", "yes", "ok", "okay", "sure", "please", "pls",
    "more", "again", "also", "too", "very", "just", "only", "now",
    "here", "there",
    "next", "previous", "last",
    "first", "second", "third",
    "some", "any", "all", "every", "each", "both", "few", "many", "much",
    "already", "ever", "never", "always", "still", "yet",
    "me", "yourself", "myself", "itself",
    "something", "anything", "everything", "nothing",
    "someone", "anyone", "everyone", "nobody",
})


def _is_pure_reference(text: str) -> bool:
    lower = text.strip().lower()
    words = lower.split()
    if not words:
        return False
    return all(w in _REF_VOCAB for w in words)


def _has_agent_pattern(text: str) -> bool:
    """Detect multi-step browser automation intent (AGENT)."""
    lower = text.lower().strip()
    words = lower.split()
    first_word = words[0] if words else ""
    if first_word in _DEVICE_VERBS:
        rest = " ".join(words[1:])
        # "open X and Y" / "launch X and Y" / "open X, login, Y"
        if re.search(r"\b(and|then|,\s*(login|search|go|click|type|find))\b", rest, re.I):
            return True
        if _AGENT_KW.search(rest):
            return True
        return False
    if _AGENT_KW.search(lower):
        words_after_kw = len(lower.split())
        if words_after_kw >= 3:
            return True
    return False


def classify_intent(text: str) -> CognitiveIntent:
    """Classify user input into CognitiveIntent.

    Deterministic multi-stage classification:
      1. Media command verbs
      2. Device command verbs
      3. Followup (short pure-reference queries)
      4. Agent (multi-step browser automation)
      5. Architecture / System design
      6. Coding
      7. Debugging
      8. Screen analysis
      9. OCR
      10. Vision
      11. Reasoning
      12. Planning
      13. Default: factual_qa if interrogative, else chat
    """
    stripped = text.strip()
    if not stripped:
        return CognitiveIntent.CHAT

    lower = stripped.lower()
    words = lower.split()
    first_word = words[0] if words else ""

    # 1. Media commands
    if first_word in _MEDIA_VERBS:
        return CognitiveIntent.MEDIA

    # 2. Agent (multi-step) — checked before Device so "open github and login" routes to AGENT
    if _has_agent_pattern(lower):
        return CognitiveIntent.AGENT

    # 3. Device commands (single-action only)
    if first_word in _DEVICE_VERBS:
        return CognitiveIntent.DEVICE

    # 4. Followup (short pure-reference queries)
    if len(words) < 5 and _is_pure_reference(stripped):
        return CognitiveIntent.FOLLOWUP

    # 5. Architecture / System design
    if _ARCHITECTURE_KW.search(lower):
        return CognitiveIntent.ARCHITECTURE

    # 6. Coding
    if _CODING_KW.search(lower):
        return CognitiveIntent.CODING

    # 7. Debugging
    if _DEBUGGING_KW.search(lower):
        return CognitiveIntent.DEBUGGING

    # 8. Screen analysis
    if _SCREEN_KW.search(lower):
        return CognitiveIntent.SCREEN_ANALYSIS

    # 9. OCR
    if _OCR_KW.search(lower):
        return CognitiveIntent.OCR

    # 10. Vision (image questions)
    if _VISION_KW.search(lower):
        return CognitiveIntent.VISION

    # 11. Reasoning
    if _REASONING_KW.search(lower):
        return CognitiveIntent.REASONING

    # 12. Planning
    if _PLANNING_KW.search(lower):
        return CognitiveIntent.PLANNING

    # 13. Default
    if re.match(r"^(who|what|when|where|why|how)\b", lower):
        return CognitiveIntent.FACTUAL_QA

    return CognitiveIntent.CHAT
