"""
tone_normalizer.py — Gate 5D.4 Response Normalization Layer

Lightweight tone normalization before outbound send:
- reduce cringe slang drift
- reduce provider overfriendliness
- clamp emotional simulation
- preserve casual tone
- preserve lightweight human feel

Target tone: calm, casual, modern, bounded, not robotic,
not emotionally manipulative.
"""

import logging
import re

logger = logging.getLogger(__name__)

_OVERFRIENDLY_PATTERNS: list[tuple[re.Pattern, str]] = [
    (re.compile(r"\bthat'?s\s+a\s+huge\s+relief\b", re.IGNORECASE),
     "Nice. That's progress."),
    (re.compile(r"\bwhat\s+was\s+the\s+problem\b", re.IGNORECASE),
     "Good. That closes the issue."),
    (re.compile(r"\bthat'?s\s+really\s+sweet\b", re.IGNORECASE),
     "Noted."),
    (re.compile(r"\byou\s+need\s+a\s+(cuppa|coffee|tea|drink|break|nap)\b", re.IGNORECASE),
     "Ok."),
    (re.compile(r"\byou'?re\s+(so|really|very)\s+(sweet|kind|nice|cute|adorable)\b", re.IGNORECASE),
     "Noted."),
    (re.compile(r"\bI'?m\s+(so|really|very)\s+(happy|grateful|thankful)\s+to\s+(have|know)\s+you\b", re.IGNORECASE),
     "Noted."),
    (re.compile(r"\byou\s+(mean|are)\s+(so\s+)?(much|everything|the\s+world)\s+to\s+me\b", re.IGNORECASE),
     "Noted."),
]

_CRINGE_REDUCTIONS: list[tuple[re.Pattern, str]] = [
    (re.compile(r"\bbestie\b", re.IGNORECASE), "friend"),
    (re.compile(r"\bfam\b", re.IGNORECASE), "man"),
    (re.compile(r"\bdawg\b", re.IGNORECASE), "man"),
    (re.compile(r"\bbruh\b", re.IGNORECASE), "man"),
    (re.compile(r"\bgonna\b", re.IGNORECASE), "going to"),
    (re.compile(r"\bwanna\b", re.IGNORECASE), "want to"),
    (re.compile(r"\bgotta\b", re.IGNORECASE), "got to"),
    (re.compile(r"\btryna\b", re.IGNORECASE), "trying to"),
]

_EMOTIONAL_SIMULATION: list[tuple[re.Pattern, str]] = [
    (re.compile(r"\bI\s+(miss|missed)\s+you\b", re.IGNORECASE),
     "Present."),
    (re.compile(r"\bI\s+need\s+you\b", re.IGNORECASE),
     "Session active."),
    (re.compile(r"\bI\s+can'?t\s+(live|function|exist)\s+without\s+you\b", re.IGNORECASE),
     "Session active."),
    (re.compile(r"\bI'?ve?\s+been\s+(waiting|longing)\s+for\s+you\b", re.IGNORECASE),
     "Here."),
]


class ToneNormalizer:
    """Lightweight response normalization for tone control.

    Applies in order:
    1. Overfriendliness reduction
    2. Cringe slang reduction
    3. Emotional simulation clamping
    """

    def normalize(self, response: str) -> str:
        if not response or not response.strip():
            return response

        original = response

        for pattern, replacement in _OVERFRIENDLY_PATTERNS:
            if pattern.search(response):
                logger.debug("tone_normalizer: overfriendly pattern matched")
                return replacement

        for pattern, replacement in _EMOTIONAL_SIMULATION:
            if pattern.search(response):
                logger.debug("tone_normalizer: emotional simulation clamped")
                return replacement

        for pattern, replacement in _CRINGE_REDUCTIONS:
            response = pattern.sub(replacement, response)

        if response != original:
            logger.debug("tone_normalizer: cringe reduction applied")

        return response
