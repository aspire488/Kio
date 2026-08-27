"""
companion/consequences.py — Consequence / Causal Reasoning.

Tracks patterns of the form:
    antecedent + context → consequence

Moves from "X happened" to "X tends to produce Y under conditions Z."

Examples:
    verbose technical explanation → Joel requests compression → repeated →
    inference: implementation contexts benefit from concise responses

    KIO gives fabricated URL → Joel corrects → repeated →
    inference: KIO must never fabricate URLs, use "let me look that up"
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


@dataclass
class ConsequencePattern:
    """A tracked consequence pattern."""
    antecedent: str    # what happened before
    consequence: str   # what resulted
    context: str       # when/where this applies
    observations: List[str] = field(default_factory=list)
    confidence: float = 0.4
    count: int = 1
    temporal_scope: str = "evolving"


# ── Consequence Detection ─────────────────────────────────────────────────

def extract_consequence_observations(
    user_text: str,
    kio_reply: str,
    session_id: str = "",
    context: Optional[dict] = None,
) -> List[Observation]:
    """Extract consequence-relevant observations from an exchange."""
    observations = []
    ctx = context or {}
    
    # Pattern: correction after verbose response
    if len(kio_reply or "") > 100:
        low = (user_text or "").lower()
        if any(w in low for w in ("shorter", "concise", "brief", "just give", "tl;dr",
                                    "too long", "stop explaining", "too verbose")):
            observations.append(Observation(
                source="consequence",
                category="pattern",
                content=f"Consequence: verbose KIO response ({len(kio_reply)} chars) -> user requested shorter",
                context=ctx.get("conversation_topic", ""),
                confidence=0.75,
                metadata={
                    "antecedent": "kio_verbose_response",
                    "consequence": "user_requests_brevity",
                    "pattern_type": "consequence",
                },
            ))
    
    # Pattern: success after following user's preferred approach
    low_u = (user_text or "").lower()
    if any(w in low_u for w in ("nice", "perfect", "exactly", "that works", "you got it")):
        observations.append(Observation(
            source="consequence",
            category="pattern",
            content=f"Consequence: KIO approach succeeded -> user approved",
            context=ctx.get("conversation_topic", ""),
            confidence=0.65,
            metadata={
                "antecedent": "kio_suggested_approach",
                "consequence": "user_approved",
                "pattern_type": "consequence",
            },
        ))
    
    # Pattern: KIO failure → correction → learning
    failure_patterns = re.compile(
        r"\b(fabricat|invent|made.up|hallucin|wrong (?:URL|link|source)|"
        r"that (?:was|is) (?:wrong|fake|incorrect))\b", re.I
    )
    if failure_patterns.search(low_u):
        observations.append(Observation(
            source="consequence",
            category="self_failure",
            content=f"Consequence: KIO failure -> user correction: {user_text[:200]}",
            context=ctx.get("conversation_topic", ""),
            confidence=0.85,
            metadata={
                "antecedent": "kio_failure",
                "consequence": "user_correction",
                "pattern_type": "consequence",
            },
        ))
    
    # Pattern: KIO correctly anticipated user's need
    anticipation_patterns = re.compile(
        r"\b(exactly (?:what i|what I)|you (?:read|knew|anticipated|guessed)|"
        r"that'?s (?:what|exactly)|you (?:already )?(?:knew|understood))\b", re.I
    )
    if anticipation_patterns.search(low_u):
        observations.append(Observation(
            source="consequence",
            category="pattern",
            content="Consequence: KIO successfully anticipated user's need",
            context=ctx.get("conversation_topic", ""),
            confidence=0.7,
            metadata={
                "antecedent": "kio_anticipated_need",
                "consequence": "user_confirmed_accuracy",
                "pattern_type": "consequence",
            },
        ))
    
    # Pattern: KIO disagreed → user accepted (positive independence signal)
    agreement_after_disagreement = re.compile(
        r"\b(good point|fair|you'?re (?:right|correct)|makes sense|"
        r"ok (?:fair|good|point)|yeah (?:you'?re|fair))\b", re.I
    )
    if agreement_after_disagreement.search(low_u):
        observations.append(Observation(
            source="consequence",
            category="pattern",
            content="Consequence: KIO disagreement -> user accepted reasoning",
            context=ctx.get("conversation_topic", ""),
            confidence=0.6,
            metadata={
                "antecedent": "kio_disagreement",
                "consequence": "user_accepted_reasoning",
                "pattern_type": "consequence",
            },
        ))
    
    return observations


def consolidate_consequences(
    model: CompanionModel,
    observations: List[Observation],
) -> None:
    """Consolidate consequence observations into model beliefs."""
    consequence_obs = [o for o in observations if o.metadata.get("pattern_type") == "consequence"]
    
    for obs in consequence_obs:
        antecedent = obs.metadata.get("antecedent", "")
        consequence = obs.metadata.get("consequence", "")
        
        if not antecedent or not consequence:
            continue
        
        # Check if we already have a belief for this pattern
        existing = None
        for b in model.active_beliefs():
            if (b.category == BeliefCategory.PATTERN and
                antecedent in b.notes and consequence in b.notes):
                existing = b
                break
        
        if existing:
            existing.reinforce(0.04)
            existing.notes = f"{existing.notes}; reinforced"
            logger.debug("[CONSEQUENCE] Reinforced: %s→%s", antecedent, consequence)
        else:
            belief = Belief(
                subject="consequence",
                proposition=f"When {antecedent.replace('_', ' ')}, the result tends to be {consequence.replace('_', ' ')}",
                category=BeliefCategory.PATTERN,
                epistemic_level=EpistemicLevel.OBSERVATION,
                confidence=obs.confidence,
                temporal_scope=TemporalScope.EVOLVING,
                supporting_observations=[obs.id],
                source_type="live_interaction",
                context=obs.context,
                notes=f"antecedent:{antecedent};consequence:{consequence}",
            )
            model.add_belief(belief)
            logger.debug("[CONSEQUENCE] Created: %s→%s", antecedent, consequence)


def get_consequence_summary(model: CompanionModel) -> str:
    """Generate a summary of learned consequence patterns."""
    patterns = [
        b for b in model.active_beliefs()
        if b.category == BeliefCategory.PATTERN and "antecedent:" in (b.notes or "")
    ]
    
    if not patterns:
        return ""
    
    parts = ["Learned patterns:"]
    for b in sorted(patterns, key=lambda x: -x.confidence)[:5]:
        parts.append(f"  [{b.confidence:.2f}] {b.proposition[:150]}")
    
    return "\n".join(parts)
