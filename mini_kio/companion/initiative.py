"""
companion/initiative.py — Proactive Initiative Tracking.

Identifies internally:
- unresolved goals
- unfinished decisions
- recurring problems
- commitments
- follow-ups
- risks
- opportunities
- contradictions
- repeated pain points
- promises KIO made
- improvements KIO still owes

This is the foundation for proactive companionship.
KIO can eventually say: "Last time we left X unresolved."
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
class OpenLoop:
    """An unresolved item that KIO should track."""
    id: str = ""
    description: str = ""
    kind: str = ""  # "goal", "commitment", "question", "decision", "risk", "improvement"
    created_at: str = ""
    last_referenced: str = ""
    status: str = "open"  # "open", "resolved", "abandoned"
    confidence: float = 0.5
    related_beliefs: List[str] = field(default_factory=list)


# ── Open Loop Detection ───────────────────────────────────────────────────

_COMMITMENT_PATTERNS = re.compile(
    r"\b(i'?ll (?:fix|update|improve|add|change|look into|investigate|"
    r"check|try|make sure|ensure|handle|address|resolve)|"
    r"(?:let me|i(?:'ll| will)) (?:fix|update|improve|add|change|"
    r"investigate|check|try|handle|address|resolve)|"
    r"(?:next time|i'?ll (?:remember|make sure|try))|"
    r"(?:from now on|i'?ll (?:start|begin|stop))|"
    r"(?:i (?:promise|guarantee))\b)",
    re.I,
)

_UNRESOLVED_QUESTION_PATTERNS = re.compile(
    r"\b(should we|should i|what (?:about|if|do you think)|"
    r"how should|what'?s (?:the best|better)|"
    r"(?:need|want) to (?:decide|figure out|determine|choose))\b",
    re.I,
)

_GOAL_PATTERNS = re.compile(
    r"\b(i (?:want to|need to|plan to|aim to|going to|trying to)|"
    r"(?:my (?:goal|plan|objective|target))|"
    r"(?:eventually|long.term|someday|ultimately))\b",
    re.I,
)


def extract_initiative_observations(
    user_text: str,
    kio_reply: str,
    session_id: str = "",
    context: Optional[dict] = None,
) -> List[Observation]:
    """Extract initiative-relevant observations from an exchange."""
    observations = []
    ctx = context or {}
    
    # Commitment detection (from KIO)
    if kio_reply and _COMMITMENT_PATTERNS.search(kio_reply.lower()):
        observations.append(Observation(
            source="initiative",
            category="goal",
            content=f"KIO commitment: {kio_reply[:200]}",
            context=ctx.get("conversation_topic", ""),
            confidence=0.7,
            metadata={"loop_type": "commitment"},
        ))
    
    # Unresolved question detection
    if user_text and _UNRESOLVED_QUESTION_PATTERNS.search(user_text):
        observations.append(Observation(
            source="initiative",
            category="goal",
            content=f"Open question: {user_text[:200]}",
            context=ctx.get("conversation_topic", ""),
            confidence=0.6,
            metadata={"loop_type": "question"},
        ))
    
    # Goal detection (from user) - unresolved
    if user_text and _GOAL_PATTERNS.search(user_text):
        # Check if KIO resolved it in the same exchange
        resolved = False
        if kio_reply:
            resolution_patterns = re.compile(
                r"\b(done|completed|fixed|resolved|implemented|added|"
                r"created|set up|configured|installed)\b", re.I
            )
            if resolution_patterns.search(kio_reply.lower()):
                resolved = True
        if not resolved:
            observations.append(Observation(
                source="initiative",
                category="goal",
                content=f"Unresolved goal stated: {user_text[:200]}",
                context=ctx.get("conversation_topic", ""),
                confidence=0.6,
                metadata={"loop_type": "goal"},
            ))
    
    return observations


def consolidate_initiative(
    model: CompanionModel,
    observations: List[Observation],
) -> None:
    """Consolidate initiative observations into the model."""
    for obs in observations:
        loop_type = obs.metadata.get("loop_type", "")
        
        if not loop_type:
            continue
        
        # Check for existing similar belief
        existing = None
        for b in model.active_beliefs():
            if (b.category in (BeliefCategory.GOAL,) and
                loop_type in (b.notes or "")):
                # Check token overlap for same item
                obs_tokens = set(obs.content.lower().split())
                b_tokens = set(b.proposition.lower().split())
                if len(obs_tokens & b_tokens) / max(len(obs_tokens), 1) > 0.3:
                    existing = b
                    break
        
        if existing:
            existing.reinforce(0.02)
        else:
            belief = Belief(
                subject="initiative",
                proposition=obs.content[:300],
                category=BeliefCategory.GOAL,
                epistemic_level=EpistemicLevel.OBSERVATION,
                confidence=obs.confidence,
                temporal_scope=TemporalScope.EVOLVING,
                supporting_observations=[obs.id],
                source_type="live_interaction",
                context=obs.context,
                notes=f"loop_type:{loop_type}",
            )
            model.add_belief(belief)
            logger.debug("[INITIATIVE] Tracked: %s", belief.proposition[:60])


def get_open_loops(model: CompanionModel) -> List[dict]:
    """Get all open (unresolved) initiative items."""
    loops = []
    
    for b in model.active_beliefs():
        if b.category == BeliefCategory.GOAL and b.confidence >= 0.3:
            loop_type = ""
            if b.notes:
                for part in b.notes.split(";"):
                    if part.startswith("loop_type:"):
                        loop_type = part.split(":", 1)[1]
            
            loops.append({
                "description": b.proposition,
                "type": loop_type,
                "confidence": b.confidence,
                "created": b.created_at,
            })
    
    return sorted(loops, key=lambda x: -x["confidence"])


def get_initiative_summary(model: CompanionModel) -> str:
    """Generate a summary of open loops for the model."""
    loops = get_open_loops(model)
    
    if not loops:
        return ""
    
    parts = ["Open loops:"]
    for lo in loops[:5]:
        parts.append(f"  -> [{lo['type']}] {lo['description'][:100]}")
    
    return "\n".join(parts)
