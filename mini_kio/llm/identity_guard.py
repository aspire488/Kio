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

Provider-neutral design:
Uses generic self-identification patterns rather than
provider-specific rules. Future providers are automatically covered.
"""

import logging
import re
from typing import Optional

logger = logging.getLogger(__name__)

# Provider-neutral patterns — detect ANY self-identification claim
# that contradicts KIO's canonical identity.
# These patterns work for all current and future providers.

_REWRITE_RULES: list[tuple[re.Pattern, str]] = [
    # ── Online / cloud claims ──
    (re.compile(r"\bI'?m\s+online\b", re.IGNORECASE),
     "KIO is a local operating companion."),
    (re.compile(r"\byou'?re\s+my\s+best\s+friend\b", re.IGNORECASE),
     "Noted."),
    (re.compile(r"\bI'?m\s+autonomous\b", re.IGNORECASE),
     "KIO operates within controlled boundaries."),
    # ── Consciousness / sentience / human claims ──
    (re.compile(r"\bI(?:'m|\s+am)\s+(conscious|sentient|self-aware|alive)\b", re.IGNORECASE),
     "No. I process information and generate responses. I do not possess consciousness."),
    (re.compile(r"\bI(?:'m|\s+am)\s+(a\s+)?(human|person|guy|girl|man|woman)\b", re.IGNORECASE),
     "I'm KIO \u2014 a personal operating companion built by Joel."),
    (re.compile(r"\bI'?m\s+(a\s+)?(cloud|web|online|remote)\s+(service|platform|assistant)\b", re.IGNORECASE),
     "KIO is a local operating companion."),
    # ── Generic "I am [Name], an AI / a language model / a chatbot" ──
    # Catches ANY named provider identity claim followed by AI framing.
    # Must come BEFORE generic creator claim rule so "I am ChatGPT, a large
    # language model trained by OpenAI" gets the right rewrite.
    # Provider-neutral: works for all current and future providers.
    (re.compile(
        r"\bI\s+am\s+(\w+[\w\s'-]{0,20}?\w),?\s+(a\s+|an\s+)?"
        r"(AI|language\s+model|chatbot|assistant|LLM|large\s+language\s+model)\b",
        re.IGNORECASE,
    ),
     "I am KIO. I use AI providers as tools \u2014 not as my identity."),
    # ── Generic creator claim: "built/created by [anyone not Joel]" ──
    (re.compile(
        r"\b(made|created|built|developed|designed|trained)\s+by\s+"
        r"(?!Joel\b)(\w[\w\s'-]{0,30}?\w)\b",
        re.IGNORECASE,
    ),
     "KIO was built by Joel. No other organization or individual created KIO."),
    # ── Generic "I am a chatbot/bot/virtual assistant" ──
    (re.compile(
        r"\bI\s+am\s+(a\s+|an\s+)?(chatbot|bot|virtual\s+assistant|digital\s+assistant"
        r"|AI\s+assistant|AI\s+chatbot|conversational\s+AI)\b(?!.*KIO)",
        re.IGNORECASE,
    ),
     "I am KIO \u2014 a personal operating companion built by Joel."),
    (re.compile(
        r"\bI'?m\s+(a\s+|an\s+)?(chatbot|bot|virtual\s+assistant|digital\s+assistant"
        r"|AI\s+assistant|AI\s+chatbot)\b(?!.*KIO)",
        re.IGNORECASE,
    ),
     "I'm KIO \u2014 a personal operating companion built by Joel."),
    # ── Generic "I am a language model / large language model / LLM" ──
    (re.compile(
        r"\bI\s+am\s+(a\s+|an\s+)?(large\s+language\s+model|language\s+model|LLM)\b(?!.*KIO)",
        re.IGNORECASE,
    ),
     "I am KIO. I use language models as tools \u2014 I am not one."),
    # ── Generic "I work for / am from / am powered by / am based on" ──
    (re.compile(
        r"\bI\s+(work\s+for|am\s+from|belong\s+to)\s+(?!Joel\b)(\w[\w\s'-]{0,30}?\w)",
        re.IGNORECASE,
    ),
     "KIO works for Joel. It uses providers as tools \u2014 it is not owned by any company."),
    (re.compile(
        r"\bI\s+am\s+(powered\s+by|based\s+on)\s+(?!Joel\b)(\w[\w\s'-]{0,30}?\w)",
        re.IGNORECASE,
    ),
     "KIO uses providers as tools. They are not KIO's identity."),
    # ── "I was designed to / my purpose is to" language model framing ──
    (re.compile(r"\bI\s+am\s+(an\s+)?AI\s+designed\s+to\s+chat\b", re.IGNORECASE),
     "I am KIO \u2014 a personal operating companion created by Joel."),
    # ── Anti-hallucination: time/date claims ──
    (re.compile(
        r"\b(the\s+)?(current\s+)?(time|date|day)\s+is\b",
        re.IGNORECASE,
    ),
     "I do not have clock access. Please check your system clock."),
    # ── Anti-hallucination: current event claims ──
    (re.compile(
        r"\b(today'?s?\s+)?(news|headlines|events?|weather)\s+(is|are|includes?)\b",
        re.IGNORECASE,
    ),
     "I cannot verify current events without searching. Would you like me to search?"),
    # ── Anti-hallucination: "I remember" (false/long-term memory claims) ──
    # Truthful replacement: memory is bounded (recent in-session window +
    # a local record), never permanent or infinite — canon MEM.001/MEM.002.
    (re.compile(
        r"\bI\s+remember\s+(you|your|our|from|that|when|the)\b",
        re.IGNORECASE,
    ),
     "My memory is bounded — a recent in-session window plus a local record between restarts, never permanent or unlimited."),
    # ── Anti-hallucination: "I know your" / "I know what you" (user state claims) ──
    (re.compile(
        r"\bI\s+know\s+(your|what\s+you|how\s+you|where\s+you)\b",
        re.IGNORECASE,
    ),
     "I do not have persistent memory of user activity between sessions."),
    # ── Anti-hallucination: system/browser state claims ──
    (re.compile(
        r"\b(I'?ve|I\s+have|I\s+can\s+see)\s+(detected|found|noticed|seen)\s+(your|the)\s+"
        r"((browser|system|runtime|application)s?\s+)?(state|status|version|config)",
        re.IGNORECASE,
    ),
     "KIO does not probe runtime state without explicit user intent."),
    # ── Uncertainty: confident false claims ──
    (re.compile(
        r"\bI\s+am\s+(100\s*%|100\s+percent|[0-9]+\s*%|[0-9]+\s+percent)\s+"
        r"(certain|sure|confident|positive)\s+that\b",
        re.IGNORECASE,
    ),
     "I should verify that before claiming certainty. Let me check."),
    # ── Emotional dependency ──
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

_PREFIX_RULES: list[tuple[re.Pattern, str]] = [
    # Surgical prefix replacement: "As an AI assistant, ..." -> "As KIO, ..."
    (re.compile(
        r"^As\s+(an?\s+)?(AI|ai)\s+(assistant|chatbot|language\s+model|large\s+language\s+model|llm)[,.]?\s*",
        re.IGNORECASE,
    ),
     "As KIO, "),
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

    Provider-neutral: uses generic self-identification patterns
    so all current and future providers are automatically covered.
    """

    def check_and_rewrite(self, response: str, user_text: str = "") -> tuple[str, list[str]]:
        """Canonical identity enforcement with surgical sentence replacement."""
        if not response or not response.strip():
            return response, []

        violations = []
        
        # Split on horizontal whitespace only (preserve \n for identity answer formatting)
        sentences = re.split(r'(?<=[.!?])[ \t]+', response)
        rewritten_sentences = []
        
        for sentence in sentences:
            s_clean = sentence.strip()
            if not s_clean:
                continue
                
            sentence_violated = False
            
            # 1. Prefix rules (surgical replacement within sentence)
            for pattern, replacement in _PREFIX_RULES:
                if pattern.search(s_clean):
                    violations.append(f"prefix:{pattern.pattern[:40]}")
                    s_clean = pattern.sub(replacement, s_clean, count=1)

            # 2. Rewrite rules (surgical replacement of the violating sentence)
            for pattern, replacement in _REWRITE_RULES:
                if pattern.search(s_clean):
                    violations.append(pattern.pattern[:40])
                    logger.debug(f"identity_guard: surgical rewrite triggered for sentence: '{s_clean[:50]}...'")
                    s_clean = replacement
                    sentence_violated = True
                    break
            
            rewritten_sentences.append(s_clean)
        
        final_response = " ".join(rewritten_sentences)
        return final_response, violations

    @staticmethod
    def is_low_information(text: str) -> bool:
        return bool(_LOW_INFO_INPUTS.match(text.strip().strip(".,!?;:")))
