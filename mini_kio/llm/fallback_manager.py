"""
fallback_manager.py — Gate 5D.4 Repetition Suppression & Offline Fallback

Features:
- Recent response tracking (last 8)
- Similarity-based repetition detection
- Fallback diversification with rotation
- Low-information micro-response pool
- Bounded offline fallback pool with identity preservation
"""

import logging
import re
from typing import Optional

logger = logging.getLogger(__name__)

_MICRO_RESPONSES = [
    "Ok.",
    "Got it.",
    "Heard.",
    "Noted.",
    "Go on.",
    "Sure.",
    "K.",
]

_FALLBACK_POOL = [
    "LLM provider unavailable. Try again when connected.",
    "Provider chain exhausted. Check API config and retry.",
    "I can't process that right now. The LLM layer is offline.",
    "Network issue or provider outage. Please try again later.",
]

_QUESTION_AWARE_POOL = [
    "I don't have an answer for that right now — providers are offline.",
    "Can't answer questions at the moment. LLM layer is down.",
    "Question received but all providers are unavailable.",
    "Sorry — knowledge queries are degraded. Retry when connected.",
]

_OFFLINE_FALLBACK_POOL = [
    "LLM provider offline. Reconnect to resume conversational features.",
    "Provider connection lost. Retry when online.",
]

_LOW_INFO_PATTERN = re.compile(
    r"^(lol|kk|same|bruh|nop|"
    r"lmao|lmfao|rip|bet|fr|"
    r"nothin|nothing|idk|dunno|maybe)$",
    re.IGNORECASE,
)

_NORMALIZE_RE = re.compile(r"[^a-z0-9\s]")
_MULTISPACE_RE = re.compile(r"\s+")


def _normalize(text: str) -> str:
    """Simple normalized form for similarity comparison."""
    t = text.lower()
    t = _NORMALIZE_RE.sub("", t)
    t = _MULTISPACE_RE.sub(" ", t).strip()
    return t


class FallbackManager:
    """Tracks recent responses and suppresses repetition.

    Attributes:
        max_history: Number of recent responses to track (default 8)
    """

    def __init__(self, max_history: int = 8):
        self._recent: list[str] = []
        self._max_history = max_history
        self._micro_idx = 0
        self._fallback_idx = 0
        self._offline_idx = 0
        self._question_fallback_idx = 0

    def record(self, response: str) -> None:
        self._recent.append(response)
        if len(self._recent) > self._max_history:
            self._recent.pop(0)

    def is_repetitive(self, response: str) -> bool:
        if len(self._recent) < 2:
            return False
        norm = _normalize(response)
        for prev in self._recent[-3:]:
            if _normalize(prev) == norm:
                return True
        return False

    def get_micro_response(self) -> str:
        r = _MICRO_RESPONSES[self._micro_idx]
        self._micro_idx = (self._micro_idx + 1) % len(_MICRO_RESPONSES)
        return r

    def get_fallback(self) -> str:
        r = _FALLBACK_POOL[self._fallback_idx]
        self._fallback_idx = (self._fallback_idx + 1) % len(_FALLBACK_POOL)
        return r

    def get_question_fallback(self) -> str:
        r = _QUESTION_AWARE_POOL[self._question_fallback_idx]
        self._question_fallback_idx = (self._question_fallback_idx + 1) % len(_QUESTION_AWARE_POOL)
        return r

    def get_offline_fallback(self) -> str:
        r = _OFFLINE_FALLBACK_POOL[self._offline_idx]
        self._offline_idx = (self._offline_idx + 1) % len(_OFFLINE_FALLBACK_POOL)
        return r

    @staticmethod
    def is_low_information(text: str) -> bool:
        return bool(_LOW_INFO_PATTERN.match(text.strip().strip(".,!?;:")))

    def recent_count(self) -> int:
        return len(self._recent)
