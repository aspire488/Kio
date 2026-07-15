"""
knowledge_fallback.py - bounded offline knowledge fallback for KIO.

This module intentionally does not carry a local general-purpose encyclopedia.
It only preserves small offline answers for KIO identity, runtime, capabilities,
and a truthful failure path for everything else.
"""

import logging
import re
from typing import Optional

logger = logging.getLogger(__name__)

_KNOWLEDGE_PATTERNS = [
    re.compile(r"^\s*what\s+is\s+.+", re.IGNORECASE),
    re.compile(r"^\s*what\s+are\s+.+", re.IGNORECASE),
    re.compile(r"^\s*what\s+do\s+.+", re.IGNORECASE),
    re.compile(r"^\s*what\s+does\s+.+", re.IGNORECASE),
    re.compile(r"^\s*who\s+is\s+.+", re.IGNORECASE),
    re.compile(r"^\s*who\s+created\s+.+", re.IGNORECASE),
    re.compile(r"^\s*who\s+wrote\s+.+", re.IGNORECASE),
    re.compile(r"^\s*who\s+made\s+.+", re.IGNORECASE),
    re.compile(r"^\s*explain\s+.+", re.IGNORECASE),
    re.compile(r"^\s*tell\s+me\s+about\s+.+", re.IGNORECASE),
    re.compile(r"^\s*define\s+.+", re.IGNORECASE),
    re.compile(r"^\s*how\s+does\s+.+\s+work\s*\??\s*$", re.IGNORECASE),
]

_EDUCATIONAL_PATTERNS = [
    re.compile(r"\bteach\s+me\b", re.IGNORECASE),
    re.compile(r"\btutorial\b", re.IGNORECASE),
    re.compile(r"\bbasics\b", re.IGNORECASE),
    re.compile(r"\blearn\b", re.IGNORECASE),
]

_NON_KNOWLEDGE_PATTERNS = [
    re.compile(r"^\s*what\s+is\s+the\s+weather\b", re.IGNORECASE),
    re.compile(r"^\s*what\s+is\s+the\s+temperature\b", re.IGNORECASE),
    re.compile(r"^\s*what\s+is\s+the\s+time\b", re.IGNORECASE),
    re.compile(r"^\s*what\s+is\s+the\s+date\b", re.IGNORECASE),
]

_OFFLINE_KNOWLEDGE: dict[str, str] = {
    "kio": (
        "KIO — Kernel for Intelligent Orchestration.\n\n"
        "A personal operating companion built by Joel.\n\n"
        "I help with desktop automation, system operations and conversational assistance."
    ),
    "joel": "Joel built KIO.",
    "capabilities": (
        "I can open and close applications, search Google and YouTube, "
        "play media, open folders, and execute multi-step commands."
    ),
    "runtime authority": (
        "KIO's runtime authority is a hierarchical safety system. "
        "The runtime maintains absolute veto power over all execution decisions. "
        "All intents are advisory until validated and confirmed through "
        "the Gate 3 orchestration pipeline."
    ),
    "confirmation": (
        "When I detect a potentially risky or ambiguous action, I pause and "
        "ask for your explicit confirmation before proceeding. "
        "You can confirm with 'yes' or 'do it', or cancel with 'no'."
    ),
    "safety": (
        "KIO enforces multiple safety layers: runtime veto authority that can "
        "block all execution, restricted-target blocking for dangerous system "
        "commands, degraded-state detection, explicit user confirmation for "
        "risky actions, and validation-before-execution."
    ),
    "limitations": (
        "I require API connectivity to language model providers for conversation "
        "and knowledge queries. Offline, I can still identify myself, "
        "execute deterministic commands, and provide safety information."
    ),
}

_OFFLINE_FAILURE = "I couldn't retrieve information for that topic right now."


class KnowledgeFallback:
    """Small offline fallback for KIO-specific knowledge only."""

    def detect_topic(self, user_text: str) -> Optional[str]:
        lower = (user_text or "").lower().strip().strip(".,!?;:")
        if not lower:
            return None

        # Creator query detection
        creator_patterns = re.compile(
            r"^(who\s+(created|built|made)\s+(you|kio))", re.IGNORECASE
        )
        if creator_patterns.match(user_text or ""):
            return "joel"

        # Identity queries -> return KIO identity
        identity_patterns = re.compile(
            r"^(who\s+are\s+you|what\s+(are|is|exactly\s+are)\s+you|what's\s+your\s+name|"
            r"what\s+is\s+your\s+name|are\s+you\s+(chatgpt|gemini|openai|chat\s*gpt))",
            re.IGNORECASE
        )
        if identity_patterns.match(user_text or ""):
            return "kio"

        checks = [
            ("runtime authority", ("runtime authority", "runtime safety", "safety controls")),
            ("confirmation", ("confirmation", "confirm", "confirmations")),
            ("safety", ("safety", "safe", "runtime veto")),
            ("capabilities", ("what can you do", "capabilities", "features")),
            ("limitations", ("limitations", "can't you do", "cannot do", "what can't")),
            ("joel", ("joel",)),
            ("kio", ("kio",)),
        ]
        for topic, needles in checks:
            if any(needle in lower for needle in needles):
                return topic
        return None

    def get_fallback(self, user_text: str) -> Optional[str]:
        topic = self.detect_topic(user_text)
        if topic:
            reply = _OFFLINE_KNOWLEDGE.get(topic)
            if reply:
                logger.debug("knowledge_fallback: offline answer for '%s'", topic)
                return reply
        return None

    def get_knowledge_failure(self, user_text: str = "") -> str:
        return _OFFLINE_FAILURE

    def get_continuation(self, user_text: str) -> Optional[str]:
        return None

    def is_knowledge_request(self, user_text: str) -> bool:
        text = (user_text or "").strip()
        if not text:
            return False
        if any(pattern.search(text) for pattern in _NON_KNOWLEDGE_PATTERNS):
            return False
        return any(pattern.search(text) for pattern in _KNOWLEDGE_PATTERNS)

    def is_educational_request(self, user_text: str) -> bool:
        text = (user_text or "").strip()
        if not text:
            return False
        if self.is_knowledge_request(text):
            return True
        return any(pattern.search(text) for pattern in _EDUCATIONAL_PATTERNS)

    def is_continuation_request(self, user_text: str) -> bool:
        text = (user_text or "").strip().lower()
        return text in {
            "next",
            "continue",
            "more",
            "go on",
            "tell me more",
            "keep going",
            "what else",
        }

    def is_bootstrap_topic(self, text: str) -> bool:
        return self.detect_topic(text) is not None

    def get_lesson_at_step(self, topic: str, step: int) -> Optional[str]:
        return None

    def clear_lesson(self, topic: str = "malayalam") -> None:
        return None

    def _detect_active_lesson(self) -> Optional[str]:
        return None
