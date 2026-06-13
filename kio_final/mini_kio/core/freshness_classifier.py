"""
freshness_classifier.py — Deterministic Freshness Query Classifier

Classifies queries by how urgently they need live/current information.
Used by conversation_responder.py to enforce search routing.

Output levels:
- NONE: No freshness indicators — local knowledge is sufficient
- OPTIONAL: May benefit from fresh data — search if convenient
- REQUIRED: Must search — provider-memory answers are not acceptable
"""

from __future__ import annotations

import re
from enum import Enum


class FreshnessLevel(Enum):
    NONE = "none"
    OPTIONAL = "optional"
    REQUIRED = "required"


_REQUIRED_KEYWORDS: tuple[str, ...] = (
    "latest", "today", "current",
    "news", "winner", "winning", "ranking", "rankings",
    "score", "scores", "scoring",
    "version", "release",
    "weather", "forecast",
    "stock", "stocks", "market", "markets",
    "schedule", "schedules",
    "standings",
    "live", "breaking",
    "ceo", "ceos",
    "internship", "internships",
    "job", "jobs", "hire", "hiring",
    "election", "elections",
    "champion", "champions", "championship",
    "tournament",
)

_OPTIONAL_KEYWORDS: tuple[str, ...] = (
    "recent", "recently",
    "update", "updates", "updated",
    "announcement", "announcements",
    "newest", "new",
    "trending", "trend",
    "this week", "this month", "this year",
)

_TIME_REF_PATTERNS: tuple[re.Pattern, ...] = (
    re.compile(r"\b\d{4}\b"),                           # year like 2024, 2025
    re.compile(r"\b(202[0-9]|203[0-9])\b"),             # current-era years
    re.compile(r"\b(winter|spring|summer|fall|autumn)\s+\d{4}\b", re.IGNORECASE),
)

_CONFIRMATION_WORDS: frozenset = frozenset({
    "yes", "yeah", "yep", "sure", "ok", "okay",
    "do it", "go ahead", "please", "pls",
    "search", "look it up", "find it",
})

_EDUCATIONAL_PREFIXES: tuple[str, ...] = (
    "explain", "what is", "what are", "what does", "what do",
    "define", "teach", "how does", "how do",
    "who is", "who was", "who are", "who were",
    "how to", "how do i", "how can i",
)

# Strong freshness keywords that bypass the educational guard entirely.
# Even if the query starts with "explain", these keywords always trigger REQUIRED.
_STRONG_FRESHNESS: tuple[str, ...] = (
    "latest",
    "today",
    "current",
)

_GENERAL_CONCEPT_PREFIXES: tuple[str, ...] = (
    "what is a ",
    "what is an ",
    "explain how ",
    "teach me about ",
)


def classify(text: str) -> FreshnessLevel:
    """Classify a query by freshness requirement.

    Returns FreshnessLevel.REQUIRED if the query contains strong
    freshness indicators (latest, today, news, score, etc.),
    FreshnessLevel.OPTIONAL for weaker indicators (recent, update),
    and FreshnessLevel.NONE otherwise.

    Educational/technical queries (starting with "explain", "what is", etc.)
    are not classified as REQUIRED unless the freshness indicator is a
    strong indicator (latest, today, current) or is in the second half
    of the query.
    """
    if not text or not text.strip():
        return FreshnessLevel.NONE

    lower = text.lower().strip()
    words = lower.split()

    # General concept queries ("what is a ceo", "explain how elections work")
    # are always NONE regardless of freshness keywords
    if any(lower.startswith(prefix) for prefix in _GENERAL_CONCEPT_PREFIXES):
        return FreshnessLevel.NONE

    # Detect educational/technical query prefix
    starts_with_edu = any(lower.startswith(prefix) for prefix in _EDUCATIONAL_PREFIXES)

    # Check REQUIRED keywords
    for kw in _REQUIRED_KEYWORDS:
        if " " in kw:
            if kw in lower:
                if starts_with_edu:
                    # Strong freshness keywords bypass the guard entirely
                    if kw in _STRONG_FRESHNESS:
                        return FreshnessLevel.REQUIRED
                    # For other keywords on educational queries, check position
                    idx = lower.find(kw)
                    word_end = idx + len(kw)
                    if word_end < len(lower) * 0.6:
                        continue
                return FreshnessLevel.REQUIRED
        elif kw in words:
            if starts_with_edu:
                # Strong freshness keywords bypass the guard entirely
                if kw in _STRONG_FRESHNESS:
                    return FreshnessLevel.REQUIRED
                # For other keywords on educational queries, check position
                kw_idx = words.index(kw)
                if kw_idx < len(words) // 2:
                    continue
            return FreshnessLevel.REQUIRED

    # Check time references (years, seasons) — REQUIRED if they reference future/current
    for pat in _TIME_REF_PATTERNS:
        if pat.search(lower):
            return FreshnessLevel.REQUIRED

    # Check OPTIONAL keywords
    for kw in _OPTIONAL_KEYWORDS:
        if " " in kw:
            if kw in lower:
                return FreshnessLevel.OPTIONAL
        elif kw in words:
            return FreshnessLevel.OPTIONAL

    return FreshnessLevel.NONE


def is_confirmation(text: str) -> bool:
    """Check if user input is confirming a pending action."""
    if not text or not text.strip():
        return False
    lower = text.lower().strip().strip(".,!?;:")
    return lower in _CONFIRMATION_WORDS


def requires_freshness(text: str) -> bool:
    """Convenience: returns True if classification is REQUIRED."""
    return classify(text) == FreshnessLevel.REQUIRED
