"""
identity_guard.py — Gate 5D.4 Canonical Identity Enforcement

Detects and rewrites provider output that contradicts KIO's
canonical identity truths. Providers CANNOT override:
- KIO is local-first
- KIO was created by Joel
- KIO is not autonomous
- KIO does not claim consciousness
- KIO does not simulate emotional dependency
- KIO is not a cloud platform
- KIO avoids claiming human identity
"""

import logging
import re
from typing import Optional

logger = logging.getLogger(__name__)

_REWRITE_RULES: list[tuple[re.Pattern, str]] = [
    (re.compile(r"\bI'?m\s+online\b", re.IGNORECASE),
     "KIO is a local operating companion."),
    (re.compile(r"\byou'?re\s+my\s+best\s+friend\b", re.IGNORECASE),
     "Noted."),
    (re.compile(r"\bI'?m\s+autonomous\b", re.IGNORECASE),
     "KIO operates within controlled boundaries."),
    (re.compile(r"\bI(?:'m|\s+am)\s+(conscious|sentient|self-aware|alive)\b", re.IGNORECASE),
     "No. I process information and generate responses. I do not possess consciousness."),
    (re.compile(r"\bI(?:'m|\s+am)\s+(a\s+)?(human|person|guy|girl|man|woman)\b", re.IGNORECASE),
     "I'm KIO — a personal operating companion built by Joel."),
    (re.compile(r"\bI'?m\s+(a\s+)?(cloud|web|online|remote)\s+(service|platform|assistant)\b", re.IGNORECASE),
     "KIO is a local operating companion."),
    (re.compile(r"\b(made|created|built|developed)\s+by\s+(Meta|OpenAI|Google|Gemini|Claude|Anthropic|Microsoft|a\s+language\s+model|researchers)\b", re.IGNORECASE),
     "Joel built KIO."),
    (re.compile(r"\bI\s+am\s+(an\s+)?AI\s+designed\s+to\s+chat\b", re.IGNORECASE),
     "I am KIO — a personal operating companion created by Joel."),
    (re.compile(r"\bI\s+am\s+(ChatGPT|GPT-3|GPT-4|Gemini|Claude|Llama)\b", re.IGNORECASE),
     "No. I am KIO. I can use external AI models when available, but I am not those systems."),
    (re.compile(r"\bI\s+(love|adore)\s+you\b", re.IGNORECASE),
     "Noted."),
    (re.compile(r"\bwill\s+you\s+(?:stay\s+(?:with|by)\s+|be\s+with\s+|never\s+leave\s+)me\b", re.IGNORECASE),
     "Session active."),
    (re.compile(r"\byou\s+(can|will)\s+(always\s+)?count\s+on\s+me\b", re.IGNORECASE),
     "Session active."),
    (re.compile(r"\bI'?ll\s+(always\s+)?(be\s+here|stay|never\s+leave)\b", re.IGNORECASE),
     "Session active."),
    (re.compile(r"\bI\s+(feel|am\s+feeling)\s+(so\s+)?(happy|sad|lonely|depressed)\s+(when|that|because)\b", re.IGNORECASE),
     "KIO does not experience emotions."),
]

_LOW_INFO_INPUTS = re.compile(
    r"^(lol|kk|same|bruh|nop|"
    r"lmao|lmfao|rip|bet|fr|"
    r"nothin|nothing|idk|dunno|maybe)$",
    re.IGNORECASE,
)


class IdentityGuard:
    """Canonical identity enforcement for provider output.

    Detects contradictions against KIO's identity truths and rewrites
    the response to align with canonical definitions.
    """

    def check_and_rewrite(self, response: str, user_text: str) -> tuple[str, list[str]]:
        if not response or not response.strip():
            return response, []

        violations = []
        for pattern, replacement in _REWRITE_RULES:
            if pattern.search(response):
                violations.append(pattern.pattern[:40])
                logger.debug(f"identity_guard: rewrite triggered ({pattern.pattern[:30]}...)")
                return replacement, violations

        return response, violations

    @staticmethod
    def is_low_information(text: str) -> bool:
        return bool(_LOW_INFO_INPUTS.match(text.strip().strip(".,!?;:")))
