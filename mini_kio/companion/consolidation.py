"""
companion/consolidation.py — Consolidation Engine (Phase 3).

The core learning mechanism. Processes observations into beliefs:
- Reinforces existing beliefs with new evidence
- Detects contradictions
- Generates inferences from patterns (including self-model, relationship, consequences)
- Manages temporal decay
- Updates self-model with behavioral rules
- Generates operational guidance from accumulated failures/learnings

This is what turns memory into cognition.
"""

from __future__ import annotations

import logging
import re
from collections import Counter
from datetime import datetime, timedelta, timezone
from typing import Any, Dict, List, Optional, Tuple

from mini_kio.companion.model import (
    Belief, CompanionModel, EpistemicLevel, TemporalScope, BeliefStatus,
    BeliefCategory, save_model, _now_iso,
)
from mini_kio.companion.observations import Observation

logger = logging.getLogger(__name__)

# Minimum observations to generate an inference
INFERENCE_THRESHOLD = 3
# Lower threshold for self-model/relationship (more sensitive)
SELF_INFER_THRESHOLD = 2
# Confidence boost for reinforcement
REINFORCEMENT_DELTA = 0.05
# Confidence penalty for contradiction
CONTRADICTION_DELTA = 0.15
# Days without reinforcement before decay starts
DECAY_THRESHOLD_DAYS = 90
# Decay rate per 30-day period
DECAY_RATE = 0.02


def consolidate(model: CompanionModel, observations: List[Observation]) -> CompanionModel:
    """Run consolidation on the model with new observations.

    This is the core learning loop:
    1. Match observations to existing beliefs
    2. Reinforce/contradict/supersede as appropriate
    3. Create new beliefs for emerging patterns
    4. Detect contradictions
    5. Generate inferences from accumulated evidence
    6. Generate self-model behavioral rules
    7. Generate consequence patterns
    8. Apply temporal decay
    9. Update temporal scopes
    """
    if not observations:
        return model

    model.total_observations_processed += len(observations)

    for obs in observations:
        _process_observation(model, obs)

    # Process relationship, consequence, and initiative observations
    try:
        from mini_kio.companion.relationship import consolidate_relationship
        consolidate_relationship(model, observations)
    except Exception:
        pass

    try:
        from mini_kio.companion.consequences import consolidate_consequences
        consolidate_consequences(model, observations)
    except Exception:
        pass

    try:
        from mini_kio.companion.initiative import consolidate_initiative
        consolidate_initiative(model, observations)
    except Exception:
        pass

    _detect_and_flag_contradictions(model)
    _generate_inferences(model)
    _generate_self_model_rules(model)
    _generate_consequence_inferences(model)
    _generate_relationship_inferences(model)
    _apply_temporal_decay(model)
    _update_temporal_scopes(model)
    
    # Prune low-confidence stale beliefs (every consolidation cycle)
    model.prune(confidence_threshold=0.15, max_beliefs=200)
    
    model.last_consolidated = _now_iso()
    model.updated_at = _now_iso()

    save_model(model)
    return model


def _process_observation(model: CompanionModel, obs: Observation) -> None:
    """Process a single observation against the model."""

    # Try to find a matching existing belief
    existing = model.find_similar(obs.content, category=obs.category)

    if existing and existing.status == BeliefStatus.ACTIVE:
        # Check if this observation supports or contradicts
        if _is_contradictory(existing, obs):
            _handle_contradiction(model, existing, obs)
        elif _is_supporting(existing, obs):
            _handle_reinforcement(model, existing, obs)
        else:
            # Related but different — might be a new belief
            _create_belief_from_observation(model, obs)
    else:
        # No matching belief — create new
        _create_belief_from_observation(model, obs)


def _is_contradictory(belief: Belief, obs: Observation) -> bool:
    """Check if an observation contradicts a belief."""
    negation_words = {"not", "don't", "doesn't", "didn't", "won't", "can't",
                      "never", "no", "hate", "dislike", "stop", "avoid"}

    belief_neg = any(w in belief.proposition.lower().split() for w in negation_words)
    obs_neg = any(w in obs.content.lower().split() for w in negation_words)

    # Contradiction type 1: negation mismatch
    if belief_neg != obs_neg:
        belief_tokens = set(belief.proposition.lower().split()) - {"i", "you", "the", "a", "an", "is", "are", "was"}
        obs_tokens = set(obs.content.lower().split()) - {"i", "you", "the", "a", "an", "is", "are", "was"}
        overlap = len(belief_tokens & obs_tokens)
        if overlap >= 2:
            return True

    # Contradiction type 2: opposing adjectives/adverbs about same topic
    opposing_pairs = [
        ("concise", "detailed"), ("short", "long"), ("simple", "complex"),
        ("prefer", "hate"), ("like", "dislike"), ("love", "hate"),
        ("yes", "no"), ("always", "never"), ("more", "less"),
        ("verbose", "brief"), ("verbose", "concise"),
    ]
    belief_low = belief.proposition.lower()
    obs_low = obs.content.lower()
    for word_a, word_b in opposing_pairs:
        if (word_a in belief_low and word_b in obs_low) or \
           (word_b in belief_low and word_a in obs_low):
            belief_content = set(belief_low.split()) - {"i", "you", "the", "a", "an", "is", "are", "was", "do", "does", "did"}
            obs_content = set(obs_low.split()) - {"i", "you", "the", "a", "an", "is", "are", "was", "do", "does", "did"}
            if len(belief_content & obs_content) >= 1:
                return True

    return False


def _is_supporting(belief: Belief, obs: Observation) -> bool:
    """Check if an observation supports a belief."""
    belief_tokens = set(belief.proposition.lower().split())
    obs_tokens = set(obs.content.lower().split())
    overlap = len(belief_tokens & obs_tokens)
    total = max(len(belief_tokens), len(obs_tokens))
    return overlap / max(total, 1) > 0.3


def _handle_reinforcement(model: CompanionModel, belief: Belief, obs: Observation) -> None:
    """Reinforce an existing belief with new evidence."""
    belief.reinforce(REINFORCEMENT_DELTA)
    if obs.id not in belief.supporting_observations:
        belief.supporting_observations.append(obs.id)
    belief.updated_at = _now_iso()
    logger.debug("[CONSOLIDATE] Reinforced belief %s: %s", belief.id, belief.proposition[:60])


def _handle_contradiction(model: CompanionModel, belief: Belief, obs: Observation) -> None:
    """Handle a contradictory observation."""
    belief.weaken(CONTRADICTION_DELTA)
    if obs.id not in belief.contradictory_observations:
        belief.contradictory_observations.append(obs.id)
    belief.updated_at = _now_iso()
    logger.debug("[CONSOLIDATE] Contradicted belief %s: %s", belief.id, belief.proposition[:60])

    # Always create a belief for the contradictory evidence
    existing_contradictions = [b for b in model.active_beliefs()
                               if b.id in belief.contradictory_observations]
    already_tracked = any(obs.content[:100] in (b.proposition or "")[:100]
                          for b in existing_contradictions)
    if not already_tracked:
        new_belief = Belief(
            subject=belief.subject,
            proposition=obs.content[:300],
            category=belief.category,
            epistemic_level=EpistemicLevel.OBSERVATION,
            confidence=obs.confidence,
            temporal_scope=TemporalScope.EVOLVING,
            supporting_observations=[obs.id],
            source_type="live_interaction",
            context=obs.context,
            contradictory_observations=[belief.id],
        )
        model.add_belief(new_belief)
        logger.info("[CONSOLIDATE] Created contradictory belief %s", new_belief.id)

    # If confidence drops low enough, supersede the old belief
    if belief.confidence < 0.3 and len(belief.contradictory_observations) >= 2:
        new_beliefs = [b for b in model.active_beliefs()
                       if b.id in belief.contradictory_observations]
        if new_beliefs:
            strongest = max(new_beliefs, key=lambda b: b.confidence)
            model.replace_belief(belief.id, strongest)
            logger.info("[CONSOLIDATE] Superseded belief %s with %s", belief.id, strongest.id)


def _create_belief_from_observation(model: CompanionModel, obs: Observation) -> None:
    """Create a new belief from an observation.
    
    Raises threshold to 0.55 to prevent noise observations from
    creating beliefs. Also deduplicates: if a near-duplicate belief
    already exists, reinforces it instead of creating a new one.
    """
    if obs.confidence < 0.55:
        return

    # Dedup: check if a nearly identical belief already exists
    for existing in model.active_beliefs():
        if existing.category != obs.category:
            continue
        # Check content overlap
        existing_tokens = set(existing.proposition.lower().split())
        obs_tokens = set(obs.content[:300].lower().split())
        if existing_tokens and obs_tokens:
            overlap = len(existing_tokens & obs_tokens) / max(len(obs_tokens), 1)
            if overlap > 0.7:  # Very similar content
                # Reinforce instead of creating duplicate
                existing.reinforce(0.03)
                if obs.id not in existing.supporting_observations:
                    existing.supporting_observations.append(obs.id)
                existing.updated_at = _now_iso()
                logger.debug("[CONSOLIDATE] Dedup: reinforced existing %s instead of creating new", existing.id)
                return

    belief = Belief(
        subject=obs.category,
        proposition=obs.content[:300],
        category=obs.category,
        epistemic_level=EpistemicLevel.OBSERVATION,
        confidence=obs.confidence,
        temporal_scope=TemporalScope.EVOLVING,
        supporting_observations=[obs.id],
        source_type="live_interaction",
        context=obs.context,
    )
    model.add_belief(belief)
    logger.debug("[CONSOLIDATE] Created belief %s: %s", belief.id, belief.proposition[:60])


def _detect_and_flag_contradictions(model: CompanionModel) -> None:
    """Scan for pairs of active beliefs that contradict each other."""
    active = model.active_beliefs()
    for i, b1 in enumerate(active):
        for b2 in active[i+1:]:
            if b1.category != b2.category:
                continue
            if b1.subject != b2.subject:
                continue
            negation_words = {"not", "don't", "doesn't", "never", "no", "hate", "stop"}
            b1_neg = any(w in b1.proposition.lower().split() for w in negation_words)
            b2_neg = any(w in b2.proposition.lower().split() for w in negation_words)
            if b1_neg != b2_neg:
                if b2.id not in b1.contradictory_observations:
                    b1.contradictory_observations.append(b2.id)
                if b1.id not in b2.contradictory_observations:
                    b2.contradictory_observations.append(b1.id)


def _generate_inferences(model: CompanionModel) -> None:
    """Generate inference-level beliefs from accumulated observations."""
    by_category: Dict[str, List[Belief]] = {}
    for b in model.active_beliefs():
        by_category.setdefault(b.category, []).append(b)

    for category, beliefs in by_category.items():
        # Use lower threshold for self-model and relationship categories
        threshold = SELF_INFER_THRESHOLD if (
            category.startswith("self_") or category.startswith("relationship")
        ) else INFERENCE_THRESHOLD

        obs_beliefs = [b for b in beliefs if b.epistemic_level in (EpistemicLevel.OBSERVATION, EpistemicLevel.FACT)]
        if len(obs_beliefs) < threshold:
            continue

        existing_inferences = [b for b in beliefs if b.epistemic_level == EpistemicLevel.INFERENCE]
        if existing_inferences:
            for inf in existing_inferences:
                supporting = len(inf.supporting_observations)
                new_conf = min(0.85, 0.4 + 0.05 * supporting)
                inf.confidence = max(inf.confidence, new_conf)
                inf.updated_at = _now_iso()
        else:
            top_obs = sorted(obs_beliefs, key=lambda b: -b.confidence)[:5]
            propositions = [b.proposition[:100] for b in top_obs]
            summary = _synthesize_proposition(propositions, category)

            if summary:
                inference = Belief(
                    subject=f"inferred_{category}",
                    proposition=summary,
                    category=category,
                    epistemic_level=EpistemicLevel.INFERENCE,
                    confidence=min(0.75, 0.4 + 0.05 * len(obs_beliefs)),
                    temporal_scope=TemporalScope.EVOLVING,
                    supporting_observations=[b.id for b in top_obs],
                    source_type="consolidation",
                    notes=f"Generated from {len(obs_beliefs)} observations",
                )
                model.add_belief(inference)
                logger.info("[CONSOLIDATE] Generated inference for %s: %s", category, summary[:80])


def _synthesize_proposition(propositions: List[str], category: str) -> str:
    """Create a synthesized proposition from multiple observations.
    
    Uses the highest-confidence observation as the base and annotates
    with the number of supporting observations. Avoids keyword extraction
    which produces garbage like '[Pattern: joel] Joel is...' 
    """
    if not propositions:
        return ""

    # Use the first (highest confidence) proposition as the base
    base = propositions[0]
    
    # If there are multiple propositions, find the most meaningful
    # one (longest, most content-rich) rather than always using the first
    if len(propositions) > 1:
        # Prefer propositions that contain meaningful content words
        meaningful = [p for p in propositions if len(p) > 30 and any(
            w in p.lower() for w in ('prefer', 'value', 'tends', 'pattern',
            'working', 'learned', 'corrected', 'adjusted', 'behavior'))]
        if meaningful:
            base = meaningful[0]
    
    # Add confidence context if multiple observations support this
    if len(propositions) >= 3:
        return f"Synthesized from {len(propositions)} observations: {base}"
    return base


def _generate_self_model_rules(model: CompanionModel) -> None:
    """Generate operational behavioral rules from accumulated self-failures and learnings.

    Key insight: semantic matching merges similar corrections into ONE reinforced belief.
    So we classify failures into FAILURE MODES and use supporting_observations count
    as evidence weight, not distinct belief count.

    Failure modes:
    - verbosity: verbose, long, essays, explaining, detailed, explanation
    - fabrication: fabricated, URL, fake, invented, hallucinated
    - over_engineering: over-engineered, complex, abstraction, unnecessary
    - incorrect: wrong, incorrect, mistake, confused
    - other: anything else
    """
    self_beliefs = [b for b in model.active_beliefs() if b.category.startswith("self_")]
    failures = [b for b in self_beliefs if b.category == "self_failure"]
    learnings = [b for b in self_beliefs if b.category == "self_learning"]

    # Classify failures into modes
    failure_modes = {
        "verbosity": {"verbose", "long", "essays", "explaining", "detailed",
                       "explanation", "excessive", "wordy", "over", "bloated"},
        "fabrication": {"fabricated", "url", "fake", "invented", "hallucinated",
                          "link", "source", "reference", "made.up"},
        "over_engineering": {"over-engineered", "complex", "abstraction",
                                "unnecessary", "complicated", "elaborate"},
        "incorrect": {"wrong", "incorrect", "mistake", "confused", "error"},
    }

    # Count evidence per mode (supporting_observations = evidence weight)
    mode_evidence: Dict[str, int] = Counter()
    mode_beliefs: Dict[str, List[Belief]] = {}
    for b in failures:
        prop_lower = b.proposition.lower()
        evidence_weight = max(1, len(b.supporting_observations))
        classified = False
        for mode, keywords in failure_modes.items():
            if any(kw in prop_lower for kw in keywords):
                mode_evidence[mode] += evidence_weight
                mode_beliefs.setdefault(mode, []).append(b)
                classified = True
                break
        if not classified:
            mode_evidence["other"] += evidence_weight
            mode_beliefs.setdefault("other", []).append(b)

    # Generate rules from modes with sufficient evidence
    for mode, evidence_count in mode_evidence.items():
        if evidence_count < 2:
            continue
        if mode == "other":
            continue  # Don't generate rules for unclassified failures

        mode_beliefs_list = mode_beliefs[mode]
        rule = _mode_to_rule(mode, mode_beliefs_list)
        if not rule:
            continue

        # Check if rule already exists
        existing = model.find_similar(rule, category="self_failure")
        if existing and "operational_rule" in (existing.notes or ""):
            # Reinforce existing rule
            existing.reinforce(0.03)
            existing.updated_at = _now_iso()
            continue

        belief = Belief(
            subject="operational_rule",
            proposition=rule,
            category="self_failure",
            epistemic_level=EpistemicLevel.INFERENCE,
            confidence=min(0.8, 0.3 + 0.05 * evidence_count),
            temporal_scope=TemporalScope.EVOLVING,
            supporting_observations=[b.id for b in mode_beliefs_list[:5]],
            source_type="consolidation",
            notes=f"operational_rule;failure_mode:{mode}",
        )
        model.add_belief(belief)
        logger.info("[SELF-RULE] Generated %s rule: %s", mode, rule[:80])

    # Generate learning rules from self_learning beliefs
    if learnings:
        learning_evidence = sum(max(1, len(b.supporting_observations)) for b in learnings)
        if learning_evidence >= 2:
            # Use the actual learning content from the highest-confidence beliefs
            # Instead of keyword extraction (which produces garbage), synthesize
            # a meaningful rule from the best learning observation
            top_learnings = sorted(learnings, key=lambda b: -b.confidence)[:3]
            # Extract actionable content from the learning beliefs
            actionable_parts = []
            for b in top_learnings:
                # Strip the "KIO should adjust behavior: " prefix if present
                content = b.proposition
                for prefix in ["KIO should adjust behavior: ", "KIO should ", "KIO learned: "]:
                    if content.lower().startswith(prefix.lower()):
                        content = content[len(prefix):]
                        break
                if len(content) > 20:  # Only use meaningful content
                    actionable_parts.append(content.strip()[:100])
            
            if actionable_parts:
                rule = f"Learned from corrections: {actionable_parts[0]}. Apply when the user explicitly requests a behavioral adjustment."
                existing = model.find_similar(rule, category="self_learning")
                if not existing or "operational_rule" not in (existing.notes or ""):
                    belief = Belief(
                        subject="operational_rule",
                        proposition=rule,
                        category="self_learning",
                        epistemic_level=EpistemicLevel.INFERENCE,
                        confidence=min(0.8, 0.3 + 0.05 * learning_evidence),
                        temporal_scope=TemporalScope.EVOLVING,
                        supporting_observations=[b.id for b in learnings[:5]],
                        source_type="consolidation",
                        notes="operational_rule",
                    )
                    model.add_belief(belief)
                    logger.info("[SELF-RULE] Generated learning rule: %s", rule[:80])


def _mode_to_rule(mode: str, beliefs: List[Belief]) -> str:
    """Convert a failure mode into an operational rule."""
    rules = {
        "verbosity": "KIO tends toward unnecessary verbosity. Before responding, check if concise actionable output is more appropriate. Default to brief unless detail is explicitly requested.",
        "fabrication": "KIO has a pattern of fabricating URLs/links/sources when uncertain. Always say 'let me look that up' or 'I'm not sure about that URL' instead of guessing.",
        "over_engineering": "KIO tends to over-engineer solutions. Prefer the simplest working implementation. Challenge added complexity before proposing it.",
        "incorrect": "KIO has made factual errors. Verify claims before stating them. Express uncertainty when evidence is insufficient.",
    }
    return rules.get(mode, "")


def _generate_consequence_inferences(model: CompanionModel) -> None:
    """Generate higher-level consequence inferences from repeated patterns."""
    patterns = [b for b in model.active_beliefs()
                if b.category == BeliefCategory.PATTERN and "antecedent:" in (b.notes or "")]

    # If we have 2+ consequence patterns about the same antecedent, generate an inference
    antecedent_groups: Dict[str, List[Belief]] = {}
    for p in patterns:
        parts = p.notes.split(";")
        for part in parts:
            if part.startswith("antecedent:"):
                ant = part.split(":", 1)[1]
                antecedent_groups.setdefault(ant, []).append(p)

    for antecedent, group in antecedent_groups.items():
        if len(group) >= 2 and not any(
            b.epistemic_level == EpistemicLevel.INFERENCE and antecedent in (b.notes or "")
            for b in model.active_beliefs()
        ):
            # Generate inference about this antecedent pattern
            consequences = [p.notes.split("consequence:")[1].split(";")[0].strip()
                           for p in group if "consequence:" in (p.notes or "")]
            if consequences:
                rule = f"When {antecedent.replace('_', ' ')} occurs, the typical outcome is {', '.join(set(consequences)).replace('_', ' ')}"
                belief = Belief(
                    subject="consequence_inference",
                    proposition=rule,
                    category=BeliefCategory.PATTERN,
                    epistemic_level=EpistemicLevel.INFERENCE,
                    confidence=min(0.75, 0.3 + 0.1 * len(group)),
                    temporal_scope=TemporalScope.EVOLVING,
                    supporting_observations=[p.id for p in group],
                    source_type="consolidation",
                    notes=f"consequence_inference;antecedent:{antecedent}",
                )
                model.add_belief(belief)
                logger.info("[CONSEQUENCE-INFER] Generated: %s", rule[:80])


def _generate_relationship_inferences(model: CompanionModel) -> None:
    """Generate relationship-level inferences from friction + success patterns."""
    friction = [b for b in model.active_beliefs() if b.category == BeliefCategory.FRICTION_POINT]
    success = [b for b in model.active_beliefs() if b.category == BeliefCategory.COLLABORATION_PATTERN]

    if len(friction) >= SELF_INFER_THRESHOLD:
        # Find common friction triggers
        friction_words = Counter()
        for b in friction:
            for word in b.proposition.lower().split():
                if len(word) > 3:
                    friction_words[word] += 1
        common = [w for w, c in friction_words.most_common(5) if c >= 2]
        if common:
            rule = f"Recurring friction pattern in KIO-Joel interaction: {', '.join(common)}"
            existing = model.find_similar(rule, category=BeliefCategory.RELATIONSHIP_PATTERN)
            if not existing:
                belief = Belief(
                    subject="relationship_inference",
                    proposition=rule,
                    category=BeliefCategory.RELATIONSHIP_PATTERN,
                    epistemic_level=EpistemicLevel.INFERENCE,
                    confidence=min(0.75, 0.3 + 0.1 * len(friction)),
                    temporal_scope=TemporalScope.EVOLVING,
                    supporting_observations=[b.id for b in friction[:5]],
                    source_type="consolidation",
                    notes="relationship_inference;type:friction",
                )
                model.add_belief(belief)
                logger.info("[REL-INFER] Generated friction pattern: %s", rule[:80])

    if len(success) >= SELF_INFER_THRESHOLD:
        success_words = Counter()
        for b in success:
            for word in b.proposition.lower().split():
                if len(word) > 3:
                    success_words[word] += 1
        common = [w for w, c in success_words.most_common(5) if c >= 2]
        if common:
            rule = f"Successful interaction pattern: {', '.join(common)}"
            existing = model.find_similar(rule, category=BeliefCategory.RELATIONSHIP_PATTERN)
            if not existing:
                belief = Belief(
                    subject="relationship_inference",
                    proposition=rule,
                    category=BeliefCategory.COLLABORATION_PATTERN,
                    epistemic_level=EpistemicLevel.INFERENCE,
                    confidence=min(0.75, 0.3 + 0.1 * len(success)),
                    temporal_scope=TemporalScope.EVOLVING,
                    supporting_observations=[b.id for b in success[:5]],
                    source_type="consolidation",
                    notes="relationship_inference;type:success",
                )
                model.add_belief(belief)
                logger.info("[REL-INFER] Generated success pattern: %s", rule[:80])


def _apply_temporal_decay(model: CompanionModel) -> None:
    """Apply temporal decay to beliefs that haven't been reinforced."""
    now = datetime.now(timezone.utc)

    for belief in model.active_beliefs():
        if belief.epistemic_level == EpistemicLevel.FACT:
            continue
        # Don't decay operational rules — they're derived, not raw
        if "operational_rule" in (belief.notes or ""):
            continue

        try:
            last_reinforced = datetime.fromisoformat(belief.last_reinforced_at.replace("Z", "+00:00"))
            days_old = (now - last_reinforced).days

            if days_old > DECAY_THRESHOLD_DAYS:
                periods = days_old // 30
                decay = DECAY_RATE * periods
                belief.confidence = max(0.1, belief.confidence - decay)
                belief.updated_at = _now_iso()
        except (ValueError, TypeError):
            pass


def _update_temporal_scopes(model: CompanionModel) -> None:
    """Update temporal scopes based on confidence and age."""
    for belief in model.active_beliefs():
        if belief.epistemic_level == EpistemicLevel.FACT:
            belief.temporal_scope = TemporalScope.STABLE
        elif "operational_rule" in (belief.notes or ""):
            belief.temporal_scope = TemporalScope.EVOLVING
        elif belief.confidence >= 0.8 and belief.epistemic_level == EpistemicLevel.OBSERVATION:
            belief.temporal_scope = TemporalScope.STABLE
        elif belief.confidence < 0.4:
            belief.temporal_scope = TemporalScope.TEMPORARY
        elif belief.status == BeliefStatus.SUPERSEDED:
            belief.temporal_scope = TemporalScope.HISTORICAL
        else:
            belief.temporal_scope = TemporalScope.EVOLVING


# ── Convenience: consolidate from raw exchange ────────────────────────────

def consolidate_exchange(
    model: CompanionModel,
    user_text: str,
    kio_reply: str,
    session_id: str = "",
    context: Optional[Dict[str, Any]] = None,
) -> CompanionModel:
    """Extract observations from an exchange and consolidate them into the model.

    This is the main entry point for the post-interaction learning loop.
    """
    from mini_kio.companion.observations import extract_observations

    observations = extract_observations(user_text, kio_reply, session_id, context)
    if observations:
        model = consolidate(model, observations)
        logger.info("[CONSOLIDATE] Processed %d observations, model now has %d beliefs",
                     len(observations), len(model.active_beliefs()))
    return model
