"""
companion/relationship.py — Relationship Intelligence.

Tracks how Joel and KIO work together:
- collaboration patterns
- trust signals
- friction points
- successful interactions
- failed interactions
- recurring misunderstandings
- KIO's recurring mistakes with Joel
- how Joel responds to KIO behaviors
- communication conventions
"""

from __future__ import annotations

import logging
import re
from dataclasses import dataclass, field
from typing import List, Optional

from mini_kio.companion.model import (
    Belief, CompanionModel, EpistemicLevel, BeliefCategory,
    TemporalScope, save_model, _now_iso,
)
from mini_kio.companion.observations import Observation

logger = logging.getLogger(__name__)


# ── Relationship Pattern Detection ────────────────────────────────────────

_FRICTION_PATTERNS = re.compile(
    r"\b(too (?:long|verbose|much|detailed|complicated)|"
    r"stop (?:doing|giving|making|saying|explaining|writing|talking|"
    r"providing|offering|generating|producing|attaching|sending)|"
    r"don'?t (?:do that|ever|always)|"
    r"not (?:what i|like that)|"
    r"wrong|incorrect|bad|terrible|ridiculous|"
    r"i (?:don'?t |no longer )(?:want|need|like)|"
    r"can you (?:just|simply))\b",
    re.I,
)

_SUCCESS_PATTERNS = re.compile(
    r"\b(nice|perfect|exactly|good|great|works|solved|fixed|"
    r"you got it|nailed|there you go|saved|thanks|"
    r"that (?:works|helped|solved|was right))\b",
    re.I,
)

_TRUST_SIGNALS = re.compile(
    r"\b(trust|rely|depend|count on|you (?:always|usually|typically)|"
    r"good (?:at|with)|you (?:know|understand|get))\b",
    re.I,
)


@dataclass
class RelationshipPattern:
    """A tracked relationship pattern."""
    pattern_type: str  # "friction", "success", "trust", "adaptation", "mistake"
    description: str
    count: int = 1
    first_seen: str = ""
    last_seen: str = ""
    confidence: float = 0.5
    context: str = ""


def extract_relationship_observations(
    user_text: str,
    kio_reply: str,
    session_id: str = "",
    context: Optional[dict] = None,
) -> List[Observation]:
    """Extract relationship-relevant observations from an exchange."""
    observations = []
    low = (user_text or "").lower()
    ctx = context or {}
    
    # Friction detection
    if _FRICTION_PATTERNS.search(low):
        observations.append(Observation(
            source="relationship",
            category="friction_point",
            content=f"Friction detected: {user_text[:300]}",
            context=ctx.get("conversation_topic", ""),
            confidence=0.7,
            metadata={"pattern_type": "friction"},
        ))
    
    # Success detection
    if _SUCCESS_PATTERNS.search(low) and len(low) < 200:
        observations.append(Observation(
            source="relationship",
            category="collaboration_pattern",
            content=f"Successful interaction: {user_text[:200]}",
            context=ctx.get("conversation_topic", ""),
            confidence=0.7,
            metadata={"pattern_type": "success"},
        ))
    
    # Trust signal detection
    if _TRUST_SIGNALS.search(low):
        observations.append(Observation(
            source="relationship",
            category="trust_signal",
            content=f"Trust signal: {user_text[:200]}",
            context=ctx.get("conversation_topic", ""),
            confidence=0.65,
            metadata={"pattern_type": "trust"},
        ))
    
    # Communication convention detection
    if len(user_text) < 15 and user_text.strip().endswith((".", "!", "?")):
        observations.append(Observation(
            source="relationship",
            category="collaboration_pattern",
            content=f"Concise communication pattern: '{user_text[:50]}'",
            context=ctx.get("conversation_topic", ""),
            confidence=0.4,
            metadata={"pattern_type": "communication_convention"},
        ))
    
    # Detect KIO behavior adaptation
    if kio_reply:
        # Was KIO's response notably concise?
        if len(kio_reply) < 100 and len(user_text) < 50:
            observations.append(Observation(
                source="relationship",
                category="collaboration_pattern",
                content="Brief exchange pattern: short message, short response",
                context=ctx.get("conversation_topic", ""),
                confidence=0.35,
                metadata={"pattern_type": "brevity_cycle"},
            ))
    
    # Detect multi-turn frustration escalation
    if _FRICTION_PATTERNS.search(low):
        # Check if frustration is escalating (short, emphatic)
        exclamation_count = user_text.count("!")
        if exclamation_count >= 2 or len(user_text) < 30:
            observations.append(Observation(
                source="relationship",
                category="friction_point",
                content=f"Escalating friction: emphatic short message '{user_text[:100]}'",
                context=ctx.get("conversation_topic", ""),
                confidence=0.6,
                metadata={"pattern_type": "escalation", "intensity": "high"},
            ))
    
    return observations


def consolidate_relationship(
    model: CompanionModel,
    observations: List[Observation],
) -> None:
    """Consolidate relationship observations into model beliefs."""
    for obs in observations:
        if obs.category in ("friction_point", "collaboration_pattern", "trust_signal"):
            _consolidate_pattern(model, obs)


def _consolidate_pattern(model: CompanionModel, obs: Observation) -> None:
    """Consolidate a single relationship pattern."""
    pattern_type = obs.metadata.get("pattern_type", "")
    
    # Find existing relationship beliefs that match
    existing = None
    for b in model.active_beliefs():
        if (b.category.startswith("relationship") and 
            pattern_type and pattern_type in b.notes):
            existing = b
            break
    
    if existing:
        # Reinforce existing pattern
        existing.reinforce(0.03)
        existing.notes = f"{existing.notes}; reinforced"
        logger.debug("[RELATIONSHIP] Reinforced pattern: %s", existing.proposition[:60])
    else:
        # Create new relationship belief
        category_map = {
            "friction": BeliefCategory.FRICTION_POINT,
            "success": BeliefCategory.COLLABORATION_PATTERN,
            "trust": BeliefCategory.TRUST_SIGNAL,
            "adaptation": BeliefCategory.COLLABORATION_PATTERN,
            "mistake": BeliefCategory.FRICTION_POINT,
            "communication_convention": BeliefCategory.COLLABORATION_PATTERN,
            "brevity_cycle": BeliefCategory.COLLABORATION_PATTERN,
            "escalation": BeliefCategory.FRICTION_POINT,
        }
        
        belief = Belief(
            subject="relationship",
            proposition=obs.content[:300],
            category=category_map.get(pattern_type, BeliefCategory.RELATIONSHIP_PATTERN),
            epistemic_level=EpistemicLevel.OBSERVATION,
            confidence=obs.confidence,
            temporal_scope=TemporalScope.EVOLVING,
            supporting_observations=[obs.id],
            source_type="live_interaction",
            context=obs.context,
            notes=f"pattern_type:{pattern_type}",
        )
        model.add_belief(belief)
        logger.debug("[RELATIONSHIP] Created pattern: %s", belief.proposition[:60])


def get_relationship_summary(model: CompanionModel) -> str:
    """Generate a natural-language relationship summary for the model."""
    rel_beliefs = [b for b in model.active_beliefs() if b.category in (
        "friction_point", "collaboration_pattern", "trust_signal", "relationship_pattern",
    )]
    
    friction = [b for b in rel_beliefs if b.category == BeliefCategory.FRICTION_POINT]
    success = [b for b in rel_beliefs if b.category == BeliefCategory.COLLABORATION_PATTERN]
    trust = [b for b in rel_beliefs if b.category == BeliefCategory.TRUST_SIGNAL]
    
    parts = []
    
    if friction:
        parts.append(f"Friction patterns ({len(friction)}): " + 
                     "; ".join(b.proposition[:80] for b in friction[:3]))
    
    if success:
        parts.append(f"Successful patterns ({len(success)}): " +
                     "; ".join(b.proposition[:80] for b in success[:3]))
    
    if trust:
        parts.append(f"Trust signals ({len(trust)}): " +
                     "; ".join(b.proposition[:80] for b in trust[:3]))
    
    return "\n".join(parts) if parts else ""
