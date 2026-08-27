"""
companion/seed.py — Model Seeding.

Bootstraps the CompanionModel from existing graph evidence.
Run once to populate the model from the current SemanticGraph data.
After seeding, the consolidation engine handles ongoing updates.
"""

from __future__ import annotations

import logging
from typing import List

from mini_kio.companion.model import (
    Belief, CompanionModel, EpistemicLevel, TemporalScope,
    BeliefCategory, save_model, get_or_create_model, _now_iso,
)

logger = logging.getLogger(__name__)


def seed_model(session_id: str) -> CompanionModel:
    """Seed the companion model from existing graph evidence.
    
    This is a one-time operation that bootstraps the model from the
    current SemanticGraph data. After this, the consolidation engine
    handles ongoing updates.
    """
    model = get_or_create_model(session_id)
    
    if len(model.beliefs) >= 10:
        logger.info("[SEED] Model already has %d beliefs, skipping seed", len(model.beliefs))
        return model
    
    seeded = 0
    
    # ── Founder-canonical facts ──
    seeded += _seed_facts(model, session_id)
    
    # ── From living model projection ──
    seeded += _seed_from_living_model(model, session_id)
    
    # ── From graph claims ──
    seeded += _seed_from_graph(model, session_id)
    
    # ── Self-model from codebase ──
    seeded += _seed_self_model(model)
    
    model.model_version = 1
    model.last_consolidated = _now_iso()
    save_model(model)
    
    logger.info("[SEED] Seeded %d beliefs into companion model for %s", seeded, session_id)
    return model


def _seed_facts(model: CompanionModel, session_id: str) -> int:
    """Seed founder-canonical facts."""
    facts = [
        ("education", BeliefCategory.TRAIT, "Joel is an engineering student at SCMS College of Engineering", 1.0),
        ("education", BeliefCategory.TRAIT, "Joel is in semester 3", 1.0),
        ("education", BeliefCategory.TRAIT, "Joel has a CGPA of 8.13", 1.0),
        ("location", BeliefCategory.TRAIT, "Joel is from Kochi, India", 1.0),
        ("identity", BeliefCategory.TRAIT, "Joel designed and built KIO as an independent project", 1.0),
    ]
    
    count = 0
    for subject, category, proposition, confidence in facts:
        belief = Belief(
            subject=subject,
            proposition=proposition,
            category=category,
            epistemic_level=EpistemicLevel.FACT,
            confidence=confidence,
            temporal_scope=TemporalScope.STABLE,
            source_type="founder_canonical",
        )
        model.add_belief(belief)
        count += 1
    
    return count


def _seed_from_living_model(model: CompanionModel, session_id: str) -> int:
    """Seed beliefs from the living model projection."""
    count = 0
    
    try:
        from mini_kio.memory.living_model import living_model
        lm = living_model(session_id)
    except Exception:
        return 0
    
    # Projects
    for proj in lm.get("projects", [])[:8]:
        text = proj.get("text", "")
        state = proj.get("state", "active")
        confidence = 0.7 if state == "active" else 0.5
        
        belief = Belief(
            subject="project",
            proposition=text,
            category=BeliefCategory.PROJECT,
            epistemic_level=EpistemicLevel.OBSERVATION,
            confidence=confidence,
            temporal_scope=TemporalScope.EVOLVING if state == "active" else TemporalScope.HISTORICAL,
            source_type="living_model",
        )
        model.add_belief(belief)
        count += 1
    
    # Preferences
    for pref in lm.get("preferences", [])[:6]:
        text = pref.get("text", "")
        belief = Belief(
            subject="preference",
            proposition=text,
            category=BeliefCategory.PREFERENCE,
            epistemic_level=EpistemicLevel.OBSERVATION,
            confidence=pref.get("confidence_num", 0.6),
            temporal_scope=TemporalScope.EVOLVING,
            source_type="living_model",
        )
        model.add_belief(belief)
        count += 1
    
    # Goals
    for goal in lm.get("goals", [])[:6]:
        text = goal.get("text", "")
        belief = Belief(
            subject="goal",
            proposition=text,
            category=BeliefCategory.GOAL,
            epistemic_level=EpistemicLevel.OBSERVATION,
            confidence=0.65,
            temporal_scope=TemporalScope.EVOLVING,
            source_type="living_model",
        )
        model.add_belief(belief)
        count += 1
    
    # Decisions
    for dec in lm.get("decisions", [])[:4]:
        text = dec.get("text", "")
        belief = Belief(
            subject="decision",
            proposition=text,
            category=BeliefCategory.PATTERN,
            epistemic_level=EpistemicLevel.OBSERVATION,
            confidence=0.6,
            temporal_scope=TemporalScope.EVOLVING,
            source_type="living_model",
        )
        model.add_belief(belief)
        count += 1
    
    return count


def _seed_from_graph(model: CompanionModel, session_id: str) -> int:
    """Seed beliefs from graph attributed statements."""
    count = 0
    
    try:
        from mini_kio.semantic.graph import SemanticGraph, USER_KEY
        graph = SemanticGraph(session_id)
        links = graph.attributed_statements(USER_KEY, active_only=True, limit=100)
    except Exception:
        return 0
    
    for link in links:
        target = (getattr(link, "target_name", "") or "").strip()
        if not target or len(target) < 8:
            continue
        # Skip junk
        low = target.lower()
        if any(x in low for x in ("content_type", "asset_pointer", "fovea", "@type")):
            continue
        if low.startswith(("rule:", "for the ", "for a ")):
            continue
        
        # Determine category from relation
        relation = getattr(link, "relation", "said")
        if relation == "prefers":
            category = BeliefCategory.PREFERENCE
        elif relation == "decides":
            category = BeliefCategory.PATTERN
        elif relation == "wants":
            category = BeliefCategory.GOAL
        else:
            category = BeliefCategory.TRAIT
        
        belief = Belief(
            subject=category.value,
            proposition=target[:300],
            category=category,
            epistemic_level=EpistemicLevel.OBSERVATION,
            confidence=float(getattr(link, "confidence", 0.5) or 0.5),
            temporal_scope=TemporalScope.EVOLVING,
            source_type="graph_evidence",
        )
        model.add_belief(belief)
        count += 1
    
    return count


def _seed_self_model(model: CompanionModel) -> int:
    """Seed KIO's self-model from codebase evidence."""
    beliefs = [
        ("self_capability", BeliefCategory.SELF_CAPABILITY,
         "KIO can open/close desktop apps, search the web, play media, control system, create documents",
         EpistemicLevel.FACT, 0.95),
        ("self_capability", BeliefCategory.SELF_CAPABILITY,
         "KIO has browser automation via Playwright and Chrome extension",
         EpistemicLevel.FACT, 0.9),
        ("self_capability", BeliefCategory.SELF_CAPABILITY,
         "KIO has semantic memory with a living user model",
         EpistemicLevel.FACT, 0.85),
        ("self_limitation", BeliefCategory.SELF_FAILURE,
         "KIO has historically fabricated URLs and resource links when uncertain",
         EpistemicLevel.OBSERVATION, 0.8),
        ("self_limitation", BeliefCategory.SELF_FAILURE,
         "KIO has given verbose responses during debugging when concise ones were needed",
         EpistemicLevel.OBSERVATION, 0.75),
        ("self_learning", BeliefCategory.SELF_LEARNING,
         "KIO now avoids fabricating URLs and says 'let me look that up' instead",
         EpistemicLevel.OBSERVATION, 0.8),
        ("self_evolution", BeliefCategory.SELF_EVOLUTION,
         "KIO's responses have become more concise and action-oriented over time",
         EpistemicLevel.HYPOTHESIS, 0.5),
    ]
    
    count = 0
    for subject, category, proposition, epistemic, confidence in beliefs:
        belief = Belief(
            subject=subject,
            proposition=proposition,
            category=category,
            epistemic_level=epistemic,
            confidence=confidence,
            temporal_scope=TemporalScope.STABLE if epistemic == EpistemicLevel.FACT else TemporalScope.EVOLVING,
            source_type="founder_canonical" if epistemic == EpistemicLevel.FACT else "codebase_analysis",
        )
        model.add_belief(belief)
        count += 1
    
    # Relationship beliefs
    rel_beliefs = [
        ("relationship_pattern", BeliefCategory.RELATIONSHIP_PATTERN,
         "Joel prefers direct criticism over excessive reassurance",
         EpistemicLevel.OBSERVATION, 0.7),
        ("relationship_pattern", BeliefCategory.RELATIONSHIP_PATTERN,
         "Joel values KIO's independent judgment and disagrees with blind agreement",
         EpistemicLevel.OBSERVATION, 0.75),
        ("collaboration_pattern", BeliefCategory.COLLABORATION_PATTERN,
         "Joel and KIO work best when KIO provides concrete actions, not abstract explanations",
         EpistemicLevel.INFERENCE, 0.65),
    ]
    
    for subject, category, proposition, epistemic, confidence in rel_beliefs:
        belief = Belief(
            subject=subject,
            proposition=proposition,
            category=category,
            epistemic_level=epistemic,
            confidence=confidence,
            temporal_scope=TemporalScope.EVOLVING,
            source_type="founder_canonical",
        )
        model.add_belief(belief)
        count += 1
    
    return count
