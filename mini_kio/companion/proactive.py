"""
companion/proactive.py — Proactive Initiative Surfacing.

KIO identifies internally when it should proactively mention:
- unresolved goals
- open questions
- commitments
- relevant context from past interactions
- useful follow-ups

Design principles:
- Rate-limited: never more than 1 proactive item per 3 messages
- Relevance-based: only surface when contextually relevant
- Confidence-aware: only surface when confidence > 0.5
- Suppressible: user can say "stop reminding me"
- Context-aware: only when situation matches the open loop

This is NOT autonomous messaging. This is controlled initiative evaluation
that runs during the normal response path.
"""

from __future__ import annotations

import logging
import re
from dataclasses import dataclass, field
from datetime import datetime, timezone
from typing import Any, Dict, List, Optional

from mini_kio.companion.model import (
    Belief, CompanionModel, EpistemicLevel, BeliefCategory,
    load_model,
)

logger = logging.getLogger(__name__)


# Rate limiting
_last_proactive_time: Dict[str, float] = {}
_proactive_cooldown_messages = 3  # minimum messages between proactive items


@dataclass
class ProactiveItem:
    """A proactive item to potentially surface."""
    description: str
    kind: str  # "goal", "commitment", "question", "follow_up", "risk", "pattern"
    confidence: float = 0.5
    relevance_score: float = 0.0
    source_belief_id: str = ""


def evaluate_proactive_items(
    user_text: str,
    session_id: str = "",
    message_count: int = 0,
    companion_model: Optional[CompanionModel] = None,
) -> Optional[str]:
    """Evaluate whether KIO should proactively surface any open items.

    Returns a proactive message if one should be surfaced, None otherwise.
    """
    if companion_model is None:
        companion_model = load_model(session_id)

    if not companion_model or not companion_model.active_beliefs():
        return None

    # Rate limiting: check cooldown
    now = datetime.now(timezone.utc).timestamp()
    last_time = _last_proactive_time.get(session_id, 0)
    if now - last_time < _proactive_cooldown_messages * 10:
        return None

    # Find relevant open items
    items = _find_relevant_items(user_text, companion_model)

    if not items:
        return None

    # Take the highest relevance item
    best = items[0]
    if best.relevance_score < 0.3 or best.confidence < 0.4:
        return None

    # Surface the item naturally
    message = _format_proactive(best, user_text)
    if message:
        _last_proactive_time[session_id] = now

    return message


def _find_relevant_items(
    user_text: str, model: CompanionModel
) -> List[ProactiveItem]:
    """Find proactive items relevant to the current context."""
    items = []
    text_tokens = set(user_text.lower().split())
    stopwords = {"i", "you", "me", "my", "the", "a", "an", "is", "to", "of", "in", "on", "for"}
    content_tokens = text_tokens - stopwords

    # Check open goals/initiative beliefs
    for b in model.active_beliefs():
        if b.category == BeliefCategory.GOAL and b.confidence >= 0.4:
            belief_tokens = set(b.proposition.lower().split()) - stopwords
            overlap = len(content_tokens & belief_tokens) / max(len(content_tokens), 1)

            if overlap > 0.15:
                items.append(ProactiveItem(
                    description=b.proposition[:200],
                    kind="goal",
                    confidence=b.confidence,
                    relevance_score=overlap * b.confidence,
                    source_belief_id=b.id,
                ))

    # Check relationship friction patterns that match current context
    for b in model.active_beliefs():
        if b.category == BeliefCategory.FRICTION_POINT and b.confidence >= 0.5:
            belief_tokens = set(b.proposition.lower().split()) - stopwords
            overlap = len(content_tokens & belief_tokens) / max(len(content_tokens), 1)
            if overlap > 0.2:
                items.append(ProactiveItem(
                    description=b.proposition[:200],
                    kind="pattern",
                    confidence=b.confidence,
                    relevance_score=overlap * b.confidence * 0.7,
                    source_belief_id=b.id,
                ))

    # Check self-model failure patterns
    for b in model.active_beliefs():
        if b.category == "self_failure" and b.confidence >= 0.6:
            if "operational_rule" in (b.notes or ""):
                belief_tokens = set(b.proposition.lower().split()) - stopwords
                overlap = len(content_tokens & belief_tokens) / max(len(content_tokens), 1)
                if overlap > 0.15:
                    items.append(ProactiveItem(
                        description=b.proposition[:200],
                        kind="self_awareness",
                        confidence=b.confidence,
                        relevance_score=overlap * b.confidence * 0.6,
                        source_belief_id=b.id,
                    ))

    # Check consequence patterns
    for b in model.active_beliefs():
        if b.category == BeliefCategory.PATTERN and "consequence" in (b.notes or ""):
            if b.confidence >= 0.5:
                belief_tokens = set(b.proposition.lower().split()) - stopwords
                overlap = len(content_tokens & belief_tokens) / max(len(content_tokens), 1)
                if overlap > 0.15:
                    items.append(ProactiveItem(
                        description=b.proposition[:200],
                        kind="consequence",
                        confidence=b.confidence,
                        relevance_score=overlap * b.confidence * 0.5,
                        source_belief_id=b.id,
                    ))

    # Sort by relevance score
    items.sort(key=lambda x: -x.relevance_score)
    return items[:3]


def _format_proactive(item: ProactiveItem, user_text: str) -> str:
    """Format a proactive item as a natural message."""
    templates = {
        "goal": [
            "By the way, you mentioned wanting to {desc}. Still on your mind?",
            "Related to what you said before: {desc}. Relevant here?",
        ],
        "commitment": [
            "Quick follow-up: {desc}. Want me to pick that up?",
        ],
        "pattern": [
            "I noticed this relates to a pattern we've hit before: {desc}. Want to avoid it?",
            "This reminds me of a recurring friction point: {desc}. Shall I adjust?",
        ],
        "self_awareness": [
            "Self-check: I have a known failure mode here: {desc}. I'll be careful.",
        ],
        "consequence": [
            "Based on past experience, {desc}. Just flagging it.",
        ],
        "risk": [
            "Heads up: {desc}. Worth considering.",
        ],
    }

    kind_templates = templates.get(item.kind, templates["goal"])
    template = kind_templates[0]

    # Simplify the description for natural insertion
    desc = item.description
    # Remove leading phrases
    for prefix in ["Joel corrected KIO: ", "KIO failure detected: ",
                   "Joel expressed frustration: ", "Consequence: "]:
        if desc.startswith(prefix):
            desc = desc[len(prefix):]
            break

    try:
        return template.format(desc=desc[:150])
    except (KeyError, IndexError):
        return None


def suppress_proactive(session_id: str, item_kind: str = "") -> None:
    """Suppress proactive surfacing for a session (user said 'stop reminding')."""
    # Set cooldown to a long time
    _last_proactive_time[session_id] = datetime.now(timezone.utc).timestamp() + 3600


def is_available() -> bool:
    """Check if proactive evaluation is available."""
    return True  # Always available (pure logic, no external deps)
