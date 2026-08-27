"""
companion/projection.py — Model Projection (Phase 3).

Serializes the CompanionModel into text suitable for LLM consumption,
combining:
A. User Model — what KIO knows about Joel
B. KIO Self Model — what KIO knows about itself
C. Relationship/Situation — what's happening between them
D. External World — current information from the outside

With epistemic markup so the LLM knows what it's reasoning over.
"""

from __future__ import annotations

import logging
import re
from typing import List, Optional

from mini_kio.companion.model import (
    Belief, CompanionModel, EpistemicLevel, TemporalScope, BeliefStatus,
    BeliefCategory, load_model,
)

logger = logging.getLogger(__name__)

# Epistemic prefixes for natural language
_EPISTEMIC_PREFIX = {
    EpistemicLevel.FACT: "[fact]",
    EpistemicLevel.OBSERVATION: "[observation]",
    EpistemicLevel.INFERENCE: "[inference]",
    EpistemicLevel.HYPOTHESIS: "[hypothesis]",
}


def project_model(
    model: CompanionModel,
    user_text: str = "",
    max_beliefs: int = 40,
) -> str:
    """Project the companion model into text for LLM consumption.

    This is the core function that replaces the evidence dump.
    It selects relevant beliefs and formats them with epistemic markup
    so the LLM can reason over a coherent model.
    """
    if not model or not model.active_beliefs():
        return ""

    parts = []

    # ── Model Overview ──
    stats = model.stats()
    parts.append(f"COMPANION MODEL (v{model.model_version}, {stats['active_beliefs']} active beliefs, "
                 f"avg confidence: {stats['avg_confidence']:.2f})")

    # ── Contradictions (only meaningful ones: both beliefs > 0.4 confidence) ──
    # Skip contradictions for compact projections (non-personal queries)
    _compact = max_beliefs <= 10
    if not _compact:
        contradictions = model.contradictions()
        meaningful = [p for p in contradictions
                      if p["belief_a"].confidence > 0.4 and p["belief_b"].confidence > 0.4]
        if meaningful:
            parts.append("\nCONTRADICTIONS (unresolved):")
            for pair in meaningful[:2]:
                b1, b2 = pair["belief_a"], pair["belief_b"]
                parts.append(f"  - [{b1.confidence:.2f}] {b1.proposition[:100]}")
                parts.append(f"  - [{b2.confidence:.2f}] {b2.proposition[:100]}")

    # ── Facts (highest confidence, always include, limited by max_beliefs) ──
    facts = [b for b in model.active_beliefs() if b.epistemic_level == EpistemicLevel.FACT]
    if facts:
        if _compact:
            # In compact mode, skip stale/temporal academic facts
            _stale_re = re.compile(
                r"cgpa|semester|engineering student|gpa|grade|"
                r"academic|college|university",
                re.IGNORECASE,
            )
            facts = [b for b in facts if not _stale_re.search(b.proposition)]
        if facts:
            parts.append("\nFACTS (directly established):")
            _fact_limit = 3 if _compact else 5
            for b in facts[:_fact_limit]:
                parts.append(f"  {_format_belief(b)}")

    # ── Observations (what KIO has noticed, deduplicated) ──
    observations = [b for b in model.active_beliefs() if b.epistemic_level == EpistemicLevel.OBSERVATION]
    if observations:
        parts.append("\nOBSERVATIONS (patterns I've noticed):")
        seen_content = set()
        obs_count = 0
        _obs_limit = 2 if _compact else 6
        for b in observations:
            if obs_count >= _obs_limit:
                break
            short = b.proposition[:80]
            if short in seen_content:
                continue
            seen_content.add(short)
            parts.append(f"  {_format_belief(b)}")
            obs_count += 1

    # ── Inferences (derived understanding) ──
    # Skip inferences in compact mode to avoid noise
    if not _compact:
        inferences = [b for b in model.active_beliefs() if b.epistemic_level == EpistemicLevel.INFERENCE]
        if inferences:
            parts.append("\nINFERENCES (derived from multiple observations):")
            for b in inferences[:4]:
                parts.append(f"  {_format_belief(b)}")

    # ── Hypotheses (low confidence, speculative) ──
    # Skip hypotheses in compact mode
    if not _compact:
        hypotheses = [b for b in model.active_beliefs() if b.epistemic_level == EpistemicLevel.HYPOTHESIS]
        if hypotheses:
            parts.append("\nHYPOTHESES (speculative, low evidence):")
            for b in hypotheses[:2]:
                parts.append(f"  {_format_belief(b)}")

    # ── Self-Model with Behavior Guidance (compact, deduplicated) ──
    self_beliefs = [b for b in model.active_beliefs() if b.category.startswith("self_")]
    if self_beliefs:
        # Operational rules (behavioral guidance) — highest priority
        operational = [b for b in self_beliefs if "operational_rule" in (b.notes or "")]
        failures_op = [b for b in operational if b.category == "self_failure"]
        learnings_op = [b for b in operational if b.category == "self_learning"]

        # Also include high-confidence raw failures/learnings as guidance
        failures_raw = [b for b in self_beliefs if b.category == "self_failure" and b.confidence > 0.6 and "operational_rule" not in (b.notes or "")]
        learnings_raw = [b for b in self_beliefs if b.category == "self_learning" and b.confidence > 0.6 and "operational_rule" not in (b.notes or "")]

        all_failures = failures_op + failures_raw[:2]
        all_learnings = learnings_op + learnings_raw[:2]

        if all_failures or all_learnings:
            parts.append("\nKIO BEHAVIOR GUIDANCE:")
            seen_guidance = set()
            for b in all_failures[:3]:
                short = b.proposition[:80]
                if short not in seen_guidance:
                    seen_guidance.add(short)
                    parts.append(f"  - AVOID: {b.proposition[:120]}")
            for b in all_learnings[:3]:
                short = b.proposition[:80]
                if short not in seen_guidance:
                    seen_guidance.add(short)
                    parts.append(f"  - APPLY: {b.proposition[:120]}")

        # Non-operational self-beliefs (compact)
        non_operational = [b for b in self_beliefs if "operational_rule" not in (b.notes or "")]
        if non_operational:
            parts.append("\nKIO SELF:")
            for b in non_operational[:3]:
                parts.append(f"  {_format_belief(b)}")

    # ── Relationship Model (compact) ──
    rel_beliefs = [b for b in model.active_beliefs()
                   if b.category in (BeliefCategory.FRICTION_POINT,
                                      BeliefCategory.COLLABORATION_PATTERN,
                                      BeliefCategory.TRUST_SIGNAL,
                                      BeliefCategory.RELATIONSHIP_PATTERN)]
    if rel_beliefs:
        parts.append("\nRELATIONSHIP:")
        for b in rel_beliefs[:4]:
            parts.append(f"  {_format_belief(b)}")

    # ── Consequence Patterns (compact) ──
    cons_beliefs = [b for b in model.active_beliefs()
                    if b.category == BeliefCategory.PATTERN and "consequence" in (b.notes or "")]
    if cons_beliefs:
        parts.append("\nCONSEQUENCES:")
        for b in cons_beliefs[:3]:
            parts.append(f"  [{b.confidence:.2f}] {b.proposition[:120]}")

    # ── Historical Changes (for temporal questions, filtered for noise) ──
    historical = model.historical_beliefs()
    if historical:
        superseded = [b for b in historical if b.superseded_by
                      and not any(p in b.proposition.lower() for p in
                                  ["asked a question about:", "sent a very short",
                                   "sent a detailed message", "gave a detailed response"])]
        if superseded:
            parts.append("\nCHANGES OVER TIME:")
            for b in superseded[:3]:
                parts.append(f"  [was] {b.proposition[:100]}")
                successor = model.get_belief(b.superseded_by)
                if successor:
                    parts.append(f"  [now] {successor.proposition[:100]}")

    # ── Uncertainty ──
    low_confidence = [b for b in model.active_beliefs() if b.confidence < 0.4]
    if low_confidence:
        parts.append("\nUNCERTAINTY (low confidence):")
        for b in low_confidence[:3]:
            parts.append(f"  - {b.proposition[:80]} (confidence: {b.confidence:.2f})")

    if len(parts) <= 1:
        return ""

    return "\n".join(parts)


def _format_belief(belief: Belief) -> str:
    """Format a single belief with epistemic marker and metadata."""
    prefix = _EPISTEMIC_PREFIX.get(belief.epistemic_level, "[?]")
    conf = f"{belief.confidence:.2f}"
    scope = belief.temporal_scope

    scope_marker = ""
    if scope == TemporalScope.HISTORICAL:
        scope_marker = " [historical]"
    elif scope == TemporalScope.TEMPORARY:
        scope_marker = " [temporary]"

    context_marker = ""
    if belief.context:
        context_marker = f" (when: {belief.context})"

    return f"{prefix} [{conf}]{scope_marker} {belief.proposition[:200]}{context_marker}"


def project_situation(
    model: CompanionModel,
    user_text: str,
    conversation_history: List[tuple] = None,
    session_id: str = "",
) -> str:
    """Project a situation-aware model for reasoning about the current context.

    Combines 4 worlds:
    A. User Model (beliefs about Joel)
    B. KIO Self Model (capabilities, failures, learnings)
    C. Situation/Relationship (current context)
    D. External World (if needed)
    """
    parts = []

    # Build the SituationModel
    try:
        from mini_kio.companion.situation import build_situation_model, project_situation_model
        situation = build_situation_model(
            user_text, conversation_history, session_id, model
        )
        situation_text = project_situation_model(situation)
        if situation_text:
            parts.append(situation_text)
    except Exception:
        pass

    # World A: User Model + Self Model + Relationship + Consequences
    # Context-aware projection: for non-personal queries, only include the
    # most relevant beliefs to avoid dumping stale CGPA/profile facts into
    # technical/external queries. Full model only for explicit personal/
    # companion queries.
    _is_personal = False
    if user_text:
        _personal_re = (
            r"(?:what\s+do\s+you\s+know\s+(?:about\s+)?me"
            r"|what\s+have\s+you\s+(?:learned|noticed)"
            r"|how\s+(?:have|do)\s+we\s+(?:work|get)"
            r"|what\s+(?:mistakes|strengths|weaknesses)"
            r"|what\s+(?:should|do\s+you\s+actively)"
            r"|remember\s+(?:about|when|what)"
            r"|continue\s+(?:working\s+on|kio)"
            r"|how\s+have\s+(?:we|our)"
            r"|what\s+(?:are\s+your|is\s+kio)"
            r"|what\s+(?:projects|decisions|patterns)"
            r"|what\s+do\s+you\s+(?:think|feel|believe)"
            r"|tell\s+me\s+about\s+(?:yourself|us|our)"
            r")"
        )
        _is_personal = bool(re.search(_personal_re, user_text.lower()))

    if _is_personal:
        # Personal/companion query: full model projection
        base = project_model(model, user_text, max_beliefs=30)
    else:
        # Technical/external query: minimal projection — only style
        # preferences and self-model guidance, never profile dumps.
        base = project_model(model, user_text, max_beliefs=8)
    if base:
        parts.append(base)

    # World C: Situation-relevant beliefs (only for personal queries)
    if _is_personal and user_text:
        relevant = _find_situation_relevant(model, user_text)
        if relevant:
            parts.append("\nSITUATION-RELEVANT BELIEFS:")
            for b in relevant[:8]:
                parts.append(f"  {_format_belief(b)}")

    # World D: External information (if needed)
    try:
        from mini_kio.companion.external_world import detect_external_need, select_and_execute_tool, integrate_external_result
        need = detect_external_need(user_text)
        if need and need.confidence > 0.5:
            result = select_and_execute_tool(need, session_id)
            if result:
                external_text = integrate_external_result(result, user_text)
                if external_text:
                    parts.append("\n" + external_text)
    except Exception:
        pass

    # Proactive items
    try:
        from mini_kio.companion.proactive import evaluate_proactive_items
        proactive = evaluate_proactive_items(user_text, session_id, companion_model=model)
        if proactive:
            parts.append(f"\nPROACTIVE NOTE: {proactive}")
    except Exception:
        pass

    # Conversation context
    if conversation_history:
        parts.append("\nRECENT CONTEXT:")
        for user_msg, kio_msg in conversation_history[-5:]:
            parts.append(f"  User: {user_msg[:100]}")
            parts.append(f"  KIO: {kio_msg[:100]}")

    # Reasoning guidance
    parts.append("""
REASONING INSTRUCTIONS:
- Use the beliefs above as your understanding. Do NOT fabricate additional claims.
- When stating something as a fact, use the [fact] beliefs only.
- When inferring, note it as an inference from observed patterns.
- When uncertain, say so honestly.
- If beliefs conflict, acknowledge the contradiction.
- You have independent judgment: disagree when warranted.
- Apply KIO BEHAVIOR GUIDANCE: avoid known mistakes, apply learned behaviors.
- If EXTERNAL INFORMATION is provided, use it as current context (not permanent truth).
- The model is your understanding, not a script. Reason from it naturally.""")

    return "\n\n".join(parts)


def _find_situation_relevant(model: CompanionModel, user_text: str) -> List[Belief]:
    """Find beliefs relevant to a specific situation/question."""
    text_tokens = set(user_text.lower().split())
    stopwords = {"i", "you", "me", "my", "your", "the", "a", "an", "is", "are",
                 "was", "were", "be", "been", "being", "do", "does", "did",
                 "have", "has", "had", "will", "would", "could", "should",
                 "what", "how", "why", "when", "where", "who", "which",
                 "that", "this", "these", "those", "it", "its", "to", "of",
                 "in", "on", "at", "for", "with", "about", "from", "by"}
    text_tokens -= stopwords
    if not text_tokens:
        text_tokens = set(user_text.lower().split())

    scored = []
    for b in model.active_beliefs():
        b_tokens = set(b.proposition.lower().split())
        if not b_tokens:
            continue
        overlap = len(text_tokens & b_tokens)
        partial = 0
        for bt in b_tokens:
            if len(bt) < 4:
                continue
            for t in text_tokens:
                if len(t) >= 3 and (t in bt or bt in t):
                    partial += 1
                    break
        total_score = overlap + partial * 0.3
        intent_boost = 1.0
        query_lower = user_text.lower()
        if any(w in query_lower for w in ("build", "project", "app", "create", "make")):
            if b.category in ("project", "goal", "skill", "strength"):
                intent_boost = 1.3
        if any(w in query_lower for w in ("prefer", "like", "style", "how")):
            if b.category in ("preference", "communication", "pattern"):
                intent_boost = 1.3
        if total_score >= 0.3:
            score = total_score * b.confidence * intent_boost
            scored.append((score, b))

    scored.sort(key=lambda x: -x[0])
    return [b for _, b in scored[:10]]


# ── Convenience ──

def get_model_projection(session_id: str, user_text: str = "") -> str:
    """Load model and project it for a specific query. Main entry point."""
    model = load_model(session_id)
    if not model or not model.active_beliefs():
        return ""
    return project_model(model, user_text)


def get_situation_projection(session_id: str, user_text: str = "", conversation_history=None) -> str:
    """Load model and project with full situation context. Used for companion queries."""
    model = load_model(session_id)
    if not model or not model.active_beliefs():
        return ""
    return project_situation(model, user_text, conversation_history, session_id)
