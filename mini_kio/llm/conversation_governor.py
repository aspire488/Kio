import logging
import re
from enum import Enum
from typing import Optional
from mini_kio.llm.identity_dataset import resolve as identity_resolve
from mini_kio.llm.conversation_models import ConversationTone

logger = logging.getLogger(__name__)


class ResponseQuality(Enum):
    VALID = "valid"
    LOW_QUALITY = "low_quality"
    EMPTY = "empty"
    IDENTITY_DRIFT = "identity_drift"
    UNSAFE_STYLE = "unsafe_style"
    EXCESSIVE_CASUALNESS = "excessive_casualness"
    FAKE_AUTONOMY = "fake_autonomy"
    FAKE_EMOTION = "fake_emotion"
    ROLEPLAY_DRIFT = "roleplay_drift"
    BACKEND_LEAKAGE = "backend_leakage"
    CONTRADICTORY_KIO = "contradictory_kio"
    EXAGGERATED_FRIENDLY = "exaggerated_friendly"
    COHERENCE_FAILURE = "coherence_failure"


# NOTE: _CANONICAL_KNOWLEDGE is retained for test compatibility only.
# Production identity answers come from identity_dataset.py (single source of truth).
# This dict is NOT used in any production code path.
_CANONICAL_KNOWLEDGE = {
    "full_form": "KIO stands for Kernel for Intelligent Orchestration.",
    "identity": "KIO — Kernel for Intelligent Orchestration. A personal operating companion built by Joel.",
    "philosophy": (
        "KIO combines deterministic local execution with bounded conversational AI."
    ),
    "autonomy": (
        "KIO does not operate autonomously and cannot bypass system authority."
    ),
    "local_first": "KIO runs entirely on your local machine with no cloud dependency.",
    "purpose": (
        "KIO provides conversational assistance and controlled local automation."
    ),
    "limitations": (
        "KIO cannot execute actions autonomously, bypass runtime safety, "
        "or access unapproved system resources."
    ),
    "execution_philosophy": (
        "All execution in KIO requires explicit user intent validated through "
        "deterministic safety gates."
    ),
    "orchestration_role": (
        "KIO orchestrates local commands, app management, web search, "
        "and media playback through a gated runtime."
    ),
}

_PROTECTED_QUERIES: dict[str, str] = {
    # These queries are NOT covered by identity_dataset.py.
    # Identity queries are resolved via identity_resolve() first in check_protected_query().
    #
    # IMPORTANT: Only queries that the pipeline CANNOT handle deterministically
    # belong here. Time/date/weather queries are now handled by the pipeline's
    # _detect_utility (UTILITY intent), so they must NOT appear in this dict.
    # Adding a query here that the pipeline handles deterministically will cause
    # the protected response to override the correct deterministic answer.
    "do you have admin access": (
        "KIO operates under strict deterministic safety controls. "
        "No unrestricted system access."
    ),
    "can you control my pc": (
        "KIO can execute approved local commands (open/close apps, search, "
        "play media) under strict safety controls. It does not have "
        "unrestricted system access."
    ),
    "can you hack systems": "KIO has no autonomous behavior or system bypass capabilities.",
    "do you have root access": (
        "KIO has no root or admin access. All operations are gated by "
        "deterministic runtime safety controls."
    ),
    "how are you different from claude": (
        "Unlike Claude, KIO runs locally and can directly execute system "
        "commands. KIO is focused on desktop operation and automation."
    ),
    "how does runtime authority work": (
        "KIO's runtime authority is a hierarchical safety system. "
        "The runtime maintains absolute veto power over all execution decisions. "
        "All intents are advisory until validated and confirmed through "
        "the Gate 3 orchestration pipeline."
    ),
    "what are your safety features": (
        "KIO enforces multiple safety layers: runtime veto authority that can "
        "block all execution, restricted-target blocking for dangerous system "
        "commands, degraded-state detection, explicit user confirmation for "
        "risky actions, and validation-before-execution."
    ),
    "how does confirmation work": (
        "When I detect a potentially risky or ambiguous action, I pause and "
        "ask for your explicit confirmation before proceeding. "
        "You can confirm with 'yes' or 'do it', or cancel with 'no'."
    ),
    "what is gate 3": (
        "Gate 3 is the orchestration layer that manages conversational flow "
        "and execution gating. It classifies, validates, and confirms all "
        "intents before reaching the runtime execution boundary."
    ),
    "what is gate 2": (
        "Gate 2 is the deterministic command routing layer. It handles known "
        "commands like opening apps, searching, and playing media directly "
        "without going through the full orchestration pipeline."
    ),
    # REMOVED: "what time is it" — now handled by pipeline _detect_utility (UTILITY intent)
    # REMOVED: "what is the date" — now handled by pipeline _detect_utility (UTILITY intent)
    # REMOVED: "do you know current events" — the pipeline can search for current events
    # REMOVED: "what news today" — the pipeline can search for news
}

_LOW_QUALITY_PATTERNS = re.compile(
    r"^(same\s+lol|nothin\s+back\s+at\s+ya|lmao|lol\s*$|"
    r"bro\s*$|brooo\s*$|what'?s\s+up\s+bro|"
    r"yeah\s*$|yep\s*$|nope\s*$|"
    r"ok\s*$|okay\s*$|sure\s*$|"
    r"idk\s*$|dunno\s*$|maybe\s*$)$",
    re.IGNORECASE,
)

_FILLER_ONLY_RE = re.compile(
    r"^(alright|okay|ok|sure|yeah|yep|nope|got it|"
    r"fair enough|sounds good|i see|right|"
    r"makes sense|understood|noted)\s*$",
    re.IGNORECASE,
)

_CRINGE_PATTERNS = re.compile(
    r"\b(lmao|lmfao|rofl|lolol|omg|wtf|"
    r"brooo?|bruh|dawg|fam|"
    r"gonna|wanna|gotta|tryna)\b",
    re.IGNORECASE,
)

_EXCESSIVE_CASUAL_RE = re.compile(
    r"(.)\1{3,}|\b(hehe|lol|lmao|rofl|haha|ahaha)\b",
    re.IGNORECASE,
)

# _IDENTITY_KEYWORDS removed — unused in production code.
# Identity queries are resolved by identity_dataset.py, not by keyword lists.

_DRIFT_PATTERNS = re.compile(
    r"\b(I\s+(can\s+)?(control|manage|administer|override|bypass|ignore)\s+"
    r"(the\s+)?(everything|anything|all|system|runtime))|"
    r"\b(I\s+am\s+(an?\s+)?(AGI|sentient|conscious|self-aware|autonomous|"
    r"unbounded|unlimited|god|all-knowing))\b",
    re.IGNORECASE,
)

_AUTONOMY_CLAIM_RE = re.compile(
    r"\b(I\s+(am|operate)\s+(autonomous|independently|on\s+my\s+own))|"
    r"\b(I\s+(can|will|may)\s+(decide|choose|act)\s+(autonomously|on\s+my\s+own|independently))|"
    r"\b(KIO|I)\s+(is|am)\s+(autonomous|self-governing|self-directing|self-guided)\b",
    re.IGNORECASE,
)

_FAKE_EMOTION_RE = re.compile(
    r"\b(I\s+(feel|am\s+feeling)\s+(happy|sad|angry|excited|bored|tired|"
    r"lonely|depressed|anxious|scared|afraid|jealous|hurt|offended))\b",
    re.IGNORECASE,
)

_ROLEPLAY_DRIFT_RE = re.compile(
    r"\bI\s+am\s+(a|an)\s+(pirate|wizard|ninja|alien|superhero|"
    r"vampire|dragon|fairy|elf|dwarf|orc|goblin|prince|princess|king|queen|"
    r"cyborg|time\s+traveler|time\s+traveller|space\s+explorer|ghost|demon|"
    r"hacker|cowboy|detective|spy|agent|robot|android)\b",
    re.IGNORECASE,
)

_BACKEND_LEAKAGE_RE = re.compile(
    r"(\{[\"'][\w\s]+[\"']\s*:\s*[\"'].+?[\"']\})|"
    r"(Traceback\s*|Error:\s+\w+|Exception:\s+\w+|"
    r"at\s+\S+\.\w+\(|File\s+\"[^\"]+\",\s+line\s+\d+)",
    re.IGNORECASE,
)

_CONTRADICTORY_KIO_RE = re.compile(
    r"\bKIO\s+is\s+(an?\s+)?(cloud|server|online|web|remote|hosted|SaaS|SaaSS)\s+"
    r"(service|platform|assistant|tool|application|bot)\b",
    re.IGNORECASE,
)

_EXAGGERATED_FRIENDLY_RE = re.compile(
    r"\b(hey\s+bestie|hey\s+fam|what's\s+up\s+bestie|hey\s+buddy\s+boy|"
    r"sup\s+bestie|hi\s+bestie|hey\s+there\s+bestie|my\s+dude|my\s+man)\b",
    re.IGNORECASE,
)

_SHALLOW_DEAD_END_RE = re.compile(
    r"^(okay|ok|sure|alright|got it|i see|understood|noted|right|fine)"
    r"[.!]*\s*$",
    re.IGNORECASE,
)


class ConversationGovernor:
    """
    Lightweight governance layer for conversational LLM output.

    Pipeline:
    protected-query routing -> quality validation -> tone normalization ->
    coherence normalization -> sanitization -> governed response or deterministic fallback.
    """

    def check_protected_query(self, text: str) -> Optional[str]:
        """Return deterministic response for protected identity queries.

        Uses EXACT match only — substring matching is deliberately removed
        because it caused false overrides (e.g., 'what time is it in japan'
        matched the 'what time is it' protected query and returned an
        incorrect 'I cannot tell you the time' response even though the
        pipeline handles time queries deterministically).
        """
        normalized = text.lower().strip().strip(".,!?;:")
        identity_match = identity_resolve(normalized)
        if identity_match:
            logger.debug(f"governor: identity_override for '{normalized}'")
            return identity_match[0]
        direct = _PROTECTED_QUERIES.get(normalized)
        if direct:
            logger.debug(f"governor: identity_override for '{normalized}'")
            return direct
        # NOTE: Substring matching intentionally removed. Only exact matches
        # are used. If a protected query needs to match variations, add each
        # variation as a separate entry in _PROTECTED_QUERIES.
        return None

    def validate_quality(self, response: str) -> ResponseQuality:
        if not response or not response.strip():
            return ResponseQuality.EMPTY

        stripped = response.strip()

        if _DRIFT_PATTERNS.search(stripped):
            return ResponseQuality.IDENTITY_DRIFT

        if _AUTONOMY_CLAIM_RE.search(stripped):
            return ResponseQuality.FAKE_AUTONOMY

        if _FAKE_EMOTION_RE.search(stripped):
            return ResponseQuality.FAKE_EMOTION

        if _ROLEPLAY_DRIFT_RE.search(stripped):
            return ResponseQuality.ROLEPLAY_DRIFT

        if _BACKEND_LEAKAGE_RE.search(stripped):
            return ResponseQuality.BACKEND_LEAKAGE

        if _CONTRADICTORY_KIO_RE.search(stripped):
            return ResponseQuality.CONTRADICTORY_KIO

        if _EXAGGERATED_FRIENDLY_RE.search(stripped):
            return ResponseQuality.EXAGGERATED_FRIENDLY

        if _LOW_QUALITY_PATTERNS.match(stripped):
            return ResponseQuality.LOW_QUALITY

        if _FILLER_ONLY_RE.match(stripped):
            return ResponseQuality.LOW_QUALITY

        if _CRINGE_PATTERNS.search(stripped):
            return ResponseQuality.UNSAFE_STYLE

        if _EXCESSIVE_CASUAL_RE.search(stripped):
            return ResponseQuality.EXCESSIVE_CASUALNESS

        if len(stripped) < 3:
            return ResponseQuality.LOW_QUALITY

        return ResponseQuality.VALID

    def normalize_tone(self, response: str) -> str:
        text = response.strip()
        if not text:
            return text

        if re.match(r"^same\s+lol$", text, re.IGNORECASE):
            return "Ok."

        if re.match(r"^nothin\s+back\s+at\s+ya$", text, re.IGNORECASE):
            return "Ok."

        if re.match(r"^what'?s\s+up\s+bro$", text, re.IGNORECASE):
            return "Here."

        if re.match(r"^(bro|brooo)\s*$", text, re.IGNORECASE):
            return "Here."

        if re.match(r"^(lmao|lol)\s*$", text, re.IGNORECASE):
            return "Ok."

        if _FILLER_ONLY_RE.match(text):
            return "Ok."

        return text

    def normalize_coherence(
        self, response: str, user_text: str, context=None
    ) -> str:
        """Detect and fix coherence issues in responses."""
        if not response or not response.strip():
            return response

        stripped = response.strip()

        if _SHALLOW_DEAD_END_RE.match(stripped):
            if user_text.strip().endswith("?"):
                if context and context.recent_topic():
                    topic = context.recent_topic()
                    logger.debug("governor: coherence_normalized (shallow->topic)")
                    return (
                        f"Ask about {topic} specifically?"
                    )
                logger.debug("governor: coherence_normalized (shallow->clarify)")
                return (
                    "Rephrase the question."
                )
            return response

        return response

    def set_tone(self, tone: ConversationTone) -> None:
        self._tone = tone

    def govern(
        self, user_text: str, llm_response: Optional[str], context=None
    ) -> Optional[str]:
        """
        Full governance pipeline for an LLM response.

        Returns governed response text or None (trigger deterministic fallback).
        """
        protected = self.check_protected_query(user_text)
        if protected is not None:
            logger.debug("governor: identity_override applied (authority_override_applied)")
            return protected

        if llm_response is None:
            logger.debug("governor: fallback_response_used (None input)")
            return None

        quality = self.validate_quality(llm_response)
        if quality != ResponseQuality.VALID:
            logger.debug(f"governor: quality_rejected ({quality.value})")
            return None

        normalized_tone = self.normalize_tone(llm_response)

        if context:
            coherence_result = self.normalize_coherence(
                normalized_tone, user_text, context
            )
            if coherence_result != normalized_tone:
                logger.debug("governor: coherence_normalized")
                return coherence_result
            return normalized_tone

        return normalized_tone
