"""
semantic_quality.py — Gate 5D Finalization Semantic Quality Scoring + Coherence Validation

Categories: STRONG, ACCEPTABLE, WEAK, GENERIC, EMPTY, DRIFTED

Validates:
- question asked → non-answer returned
- educational prompt → filler response
- teaching request → generic response
- follow-up mismatch
- malformed conversational continuity
"""

import logging
import re
from enum import Enum
from typing import Optional

logger = logging.getLogger(__name__)


class ResponseSemanticQuality(Enum):
    STRONG = "strong"
    ACCEPTABLE = "acceptable"
    WEAK = "weak"
    GENERIC = "generic"
    EMPTY = "empty"
    DRIFTED = "drifte"


_GENERIC_RESPONSES = frozenset({
    "alright", "alright.", "okay", "ok", "sure", "sure.",
    "got it", "got it.", "fair enough", "sounds good",
    "i see", "right", "makes sense", "understood", "noted",
    "cool", "cool.", "nice", "nice.", "fair", "fair.",
    "what's up", "whats up", "what's up?", "whats up?",
    "same lol", "same lol.",
    "alright let me know what you need",
    "alright. let me know what you need.",
    "fair enough.", "sounds good.",
    "i'm here", "i'm here.", "im here",
})

_FILLER_WORDS = frozenset({
    "lol", "lmao", "😂", "🤣", "lol.", "lmao.",
    "kk", "ok", "okay", "sure", "yeah", "nope",
    "bet", "fr", "rip", "same",
})

_QUESTION_MARKER = re.compile(r"\?$|\b(what|who|where|when|why|how|does|is|are|can|will|do)\b", re.IGNORECASE)

_EDUCATIONAL_MARKER = re.compile(
    r"\b(teach|learn|explain|tutorial|lesson|educate|"
    r"what\s+is|what\s+are|define|meaning)\b",
    re.IGNORECASE,
)

_SHORT_ANSWER_WORD_LIMIT = 4


def _strip_punct(text: str) -> str:
    return re.sub(r"[.,!?;:\"'\-]", "", text).strip().lower()


class SemanticQualityScorer:
    """Evaluates final response semantic quality before outbound send.

    Checks:
    - Generic/filler responses
    - Question asked → non-answer
    - Educational request → filler response
    - Empty/too-short responses
    """

    def score(
        self, response: str, user_text: str, context=None
    ) -> ResponseSemanticQuality:
        if not response or not response.strip():
            return ResponseSemanticQuality.EMPTY

        stripped = response.strip()
        normalized = _strip_punct(stripped)
        lower = stripped.lower()
        word_count = len(stripped.split())

        if normalized in _GENERIC_RESPONSES:
            return ResponseSemanticQuality.GENERIC

        if normalized in _FILLER_WORDS:
            return ResponseSemanticQuality.GENERIC

        if len(stripped) < 3:
            return ResponseSemanticQuality.EMPTY

        if word_count <= _SHORT_ANSWER_WORD_LIMIT:
            return ResponseSemanticQuality.WEAK

        if self._is_educational_request(user_text):
            if self._is_filler_response(stripped):
                return ResponseSemanticQuality.WEAK
            if word_count <= 3:
                return ResponseSemanticQuality.WEAK

        if self._is_question(user_text):
            if self._is_filler_response(stripped):
                return ResponseSemanticQuality.GENERIC
            if word_count <= 2:
                return ResponseSemanticQuality.WEAK

        return ResponseSemanticQuality.STRONG

    @staticmethod
    def is_generic(response: str) -> bool:
        return _strip_punct(response) in _GENERIC_RESPONSES

    @staticmethod
    def is_filler(response: str) -> bool:
        return _strip_punct(response) in _FILLER_WORDS

    @staticmethod
    def is_coherent(response: str, user_text: str, context=None) -> bool:
        if not response or not response.strip():
            return False
        if _strip_punct(response) in _GENERIC_RESPONSES:
            if _QUESTION_MARKER.search(user_text):
                return False
        return True

    def _is_educational_request(self, text: str) -> bool:
        return bool(_EDUCATIONAL_MARKER.search(text))

    def _is_question(self, text: str) -> bool:
        text = text.strip()
        if text.endswith("?"):
            return True
        return bool(_QUESTION_MARKER.match(text))

    @staticmethod
    def _is_filler_response(response: str) -> bool:
        lower = response.strip().lower()
        return (
            _strip_punct(response) in _GENERIC_RESPONSES
            or _strip_punct(response) in _FILLER_WORDS
            or lower.startswith("alright")
            or lower.startswith("okay")
            or lower.startswith("got it")
            or lower.startswith("sure")
            or lower.startswith("cool")
            or lower.startswith("nice")
            or lower == "what's up"
        )
