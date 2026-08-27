"""
companion/situation.py — Situation Model.

Temporary current-state cognition that combines:
- CompanionModel (persistent beliefs)
- Current conversation context
- Relationship patterns
- Self-model
- External context

This is NOT persisted as permanent memory. It's assembled per-interaction
and provides the reasoning context for the LLM.

SituationModel = what KIO understands RIGHT NOW about the current situation.
"""

from __future__ import annotations

import logging
import re
from dataclasses import dataclass, field
from typing import Any, Dict, List, Optional

from mini_kio.companion.model import (
    Belief, CompanionModel, EpistemicLevel, BeliefCategory,
    load_model,
)

logger = logging.getLogger(__name__)


@dataclass
class SituationModel:
    """Temporary reasoning context for the current interaction."""
    
    # What is the user trying to do right now?
    current_objective: str = ""
    
    # What context/domain is this about?
    domain: str = ""  # "debugging", "architecture", "exploration", "companion", etc.
    
    # Active constraints
    constraints: List[str] = field(default_factory=list)
    
    # Relevant user beliefs
    user_beliefs: List[Belief] = field(default_factory=list)
    
    # Relevant self-model beliefs
    self_beliefs: List[Belief] = field(default_factory=list)
    
    # Relevant relationship patterns
    relationship_beliefs: List[Belief] = field(default_factory=list)
    
    # Uncertainty markers
    uncertainties: List[str] = field(default_factory=list)
    
    # Detected tensions or contradictions relevant here
    tensions: List[str] = field(default_factory=list)
    
    # Open loops related to this context
    open_loops: List[str] = field(default_factory=list)
    
    # Consequences of possible actions
    consequence_hints: List[str] = field(default_factory=list)
    
    # Detected urgency
    urgency: str = "normal"
    
    # Communication style recommendation based on context
    recommended_style: str = ""
    
    # Raw metadata
    metadata: Dict[str, Any] = field(default_factory=dict)
    
    def is_empty(self) -> bool:
        return not any([
            self.current_objective, self.domain, self.constraints,
            self.user_beliefs, self.self_beliefs, self.relationship_beliefs,
            self.uncertainties, self.tensions, self.open_loops,
            self.consequence_hints,
        ])


# ── Domain Detection ──────────────────────────────────────────────────────

_DOMAIN_PATTERNS = {
    "debugging": re.compile(
        r"\b(debug|error|fix|bug|broken|crash|fail|traceback|exception|"
        r"issue|problem|stuck|not working|doesn'?t work)\b", re.I
    ),
    "architecture": re.compile(
        r"\b(architect|design|structure|pattern|framework|system|"
        r"component|module|layer|pipeline|infrastructure)\b", re.I
    ),
    "implementation": re.compile(
        r"\b(implement|build|create|code|write|develop|make|add|"
        r"feature|function|class|module|setup|configure)\b", re.I
    ),
    "exploration": re.compile(
        r"\b(research|explore|investigate|look into|find|search|"
        r"discover|compare|evaluate|assess|review|analyze)\b", re.I
    ),
    "companion": re.compile(
        r"\b(what do you know|know about me|how do i|what am i|"
        r"describe me|my (?:strength|weakness|pattern|style)|"
        r"our (?:relationship|working)|what have you learned)\b", re.I
    ),
    "self_reflection": re.compile(
        r"\b(your (?:weakness|strength|capability|limitation)|"
        r"what (?:are you|have you) (?:bad|good|learned|evolved)|"
        r"how (?:are you|have you) (?:different|changed|improved)|"
        r"self[- ]?model)\b", re.I
    ),
    "decision": re.compile(
        r"\b(should i|should we|which|choose|decide|recommend|"
        r"suggest|prefer|better (?:option|approach|way)|"
        r"what (?:would|should|do))\b", re.I
    ),
    "temporal": re.compile(
        r"\b(how have i|how have you|changed|evolved|before|"
        r"previously|earlier|history|past|used to|back then|"
        r"since we started|over time)\b", re.I
    ),
}

_STYLE_RECOMMENDATIONS = {
    "debugging": "concise, action-first, no unnecessary explanation",
    "architecture": "thorough, tradeoff-aware, challenge weak reasoning",
    "implementation": "direct, executable, code-first",
    "exploration": "broad, comparative, exploratory",
    "companion": "natural, evidence-backed, honest about uncertainty",
    "self_reflection": "honest, specific, grounded in actual failures",
    "decision": "rigorous, consequence-aware, disagreement when warranted",
    "temporal": "historical vs current distinction, supersession-aware",
}


def build_situation_model(
    user_text: str,
    conversation_history: List[tuple] = None,
    session_id: str = "",
    companion_model: Optional[CompanionModel] = None,
) -> SituationModel:
    """Build a SituationModel for the current interaction.
    
    This is the main entry point for situation modeling.
    Assembles context from multiple sources into a coherent
    reasoning context for the current turn.
    """
    situation = SituationModel()
    
    # Load companion model if not provided
    if companion_model is None:
        companion_model = load_model(session_id)
    
    if not companion_model or not companion_model.active_beliefs():
        return situation
    
    # 1. Detect domain
    situation.domain = _detect_domain(user_text)
    
    # 2. Detect urgency
    situation.urgency = _detect_urgency(user_text)
    
    # 3. Detect current objective
    situation.current_objective = _extract_objective(user_text)
    
    # 4. Retrieve relevant beliefs by domain + semantic matching
    situation.user_beliefs = _retrieve_user_beliefs(user_text, companion_model, situation.domain)
    situation.self_beliefs = _retrieve_self_beliefs(companion_model, situation.domain)
    situation.relationship_beliefs = _retrieve_relationship_beliefs(companion_model, situation.domain)
    
    # 5. Detect tensions
    situation.tensions = _detect_tensions(companion_model, user_text)
    
    # 6. Detect uncertainties
    situation.uncertainties = _detect_uncertainties(companion_model, user_text)
    
    # 7. Detect open loops (from conversation history + model)
    if conversation_history:
        situation.open_loops = _detect_open_loops(conversation_history)
    model_loops = _detect_model_open_loops(companion_model, user_text)
    situation.open_loops.extend(model_loops)
    
    # 8. Recommend communication style
    situation.recommended_style = _STYLE_RECOMMENDATIONS.get(situation.domain, "")
    
    return situation


def _detect_domain(text: str) -> str:
    """Detect the primary domain of the user's message."""
    scores = {}
    for domain, pattern in _DOMAIN_PATTERNS.items():
        matches = pattern.findall(text)
        if matches:
            scores[domain] = len(matches)
    
    if scores:
        return max(scores, key=scores.get)
    
    # Default: companion for personal questions, implementation for commands
    low = text.lower().strip()
    if low.endswith("?"):
        return "companion"
    return "implementation"


def _detect_urgency(text: str) -> str:
    """Detect urgency from user message."""
    urgent_patterns = re.compile(
        r"\b(urgent|asap|now|immediately|quickly|fast|hurry|deadline|"
        r"emergency|critical|broken|crash|production)\b", re.I
    )
    if urgent_patterns.search(text):
        return "high"
    
    frustrated = re.compile(
        r"\b(frustrated|annoyed|pissed|angry|ugh|god ?damn|"
        r"this is (?:broken|ridiculous|stupid))\b", re.I
    )
    if frustrated.search(text):
        return "elevated"
    
    return "normal"


def _extract_objective(text: str) -> str:
    """Extract the user's current objective from their message."""
    # Simple extraction: the core request
    text = text.strip()
    
    # Remove common prefixes
    for prefix in ["can you ", "could you ", "please ", "i want to ", "i need to ",
                   "help me ", "let's ", "lets "]:
        if text.lower().startswith(prefix):
            text = text[len(prefix):]
            break
    
    # Remove question framing
    for suffix in ["?", ".", "!"]:
        text = text.rstrip(suffix).strip()
    
    return text[:200] if text else ""


def _retrieve_user_beliefs(
    user_text: str, model: CompanionModel, domain: str
) -> List[Belief]:
    """Retrieve user beliefs relevant to the current situation."""
    relevant = []
    
    for belief in model.active_beliefs():
        if belief.category.startswith("self_") or belief.category.startswith("relationship"):
            continue
        
        score = _belief_relevance_score(belief, user_text, domain)
        if score > 0.2:
            relevant.append(belief)
    
    # Sort by relevance * confidence
    relevant.sort(key=lambda b: _belief_relevance_score(b, user_text, domain) * b.confidence, reverse=True)
    return relevant[:10]


def _retrieve_self_beliefs(model: CompanionModel, domain: str) -> List[Belief]:
    """Retrieve self-model beliefs relevant to the current domain."""
    self_beliefs = [b for b in model.active_beliefs() if b.category.startswith("self_")]
    
    # Domain-relevant self-beliefs
    domain_keywords = {
        "debugging": {"self_failure", "self_learning", "self_capability"},
        "architecture": {"self_failure", "self_learning", "self_capability", "self_evolution"},
        "implementation": {"self_failure", "self_learning", "self_capability"},
        "companion": {"self_failure", "self_learning", "self_evolution"},
        "self_reflection": {"self_failure", "self_learning", "self_evolution", "self_capability"},
    }
    
    relevant_categories = domain_keywords.get(domain, {"self_failure", "self_learning"})
    
    return [
        b for b in self_beliefs
        if b.category in relevant_categories
    ][:6]


def _retrieve_relationship_beliefs(model: CompanionModel, domain: str) -> List[Belief]:
    """Retrieve relationship beliefs relevant to the current domain."""
    return [
        b for b in model.active_beliefs()
        if b.category.startswith("relationship")
    ][:5]


def _detect_tensions(model: CompanionModel, user_text: str) -> List[str]:
    """Detect unresolved tensions relevant to this interaction."""
    tensions = []
    
    for pair in model.contradictions():
        b1, b2 = pair["belief_a"], pair["belief_b"]
        # Check if either belief is relevant to the current text
        text_tokens = set(user_text.lower().split())
        b1_tokens = set(b1.proposition.lower().split())
        b2_tokens = set(b2.proposition.lower().split())
        
        if (text_tokens & b1_tokens) or (text_tokens & b2_tokens):
            tensions.append(
                f"Unresolved: [{b1.confidence:.2f}] {b1.proposition[:80]} vs "
                f"[{b2.confidence:.2f}] {b2.proposition[:80]}"
            )
    
    return tensions[:3]


def _detect_uncertainties(model: CompanionModel, user_text: str) -> List[str]:
    """Identify areas of uncertainty relevant to the current query."""
    uncertainties = []
    
    for belief in model.active_beliefs():
        if belief.confidence < 0.4:
            text_tokens = set(user_text.lower().split())
            belief_tokens = set(belief.proposition.lower().split())
            if text_tokens & belief_tokens:
                uncertainties.append(
                    f"Low confidence ({belief.confidence:.2f}): {belief.proposition[:80]}"
                )
    
    return uncertainties[:3]


def _detect_open_loops(conversation_history: List[tuple]) -> List[str]:
    """Detect open loops from conversation history."""
    loops = []
    
    for user_msg, kio_msg in conversation_history[-10:]:
        if kio_msg and "?" in kio_msg:
            loops.append(f"Open question: {kio_msg[:100]}")
    
    return loops[:3]


def _detect_model_open_loops(model: CompanionModel, user_text: str) -> List[str]:
    """Detect open loops from the companion model's initiative beliefs."""
    loops = []
    for b in model.active_beliefs():
        if b.category == BeliefCategory.GOAL and b.confidence >= 0.4:
            text_tokens = set(user_text.lower().split())
            belief_tokens = set(b.proposition.lower().split())
            stopwords = {"i", "you", "me", "my", "the", "a", "an", "is", "to", "of", "in"}
            overlap = len((text_tokens - stopwords) & (belief_tokens - stopwords)) / max(len(text_tokens - stopwords), 1)
            if overlap > 0.1:
                loops.append(f"Open goal: {b.proposition[:100]}")
    return loops[:3]


def _belief_relevance_score(belief: Belief, user_text: str, domain: str) -> float:
    """Score how relevant a belief is to the current situation."""
    text_tokens = set(user_text.lower().split())
    belief_tokens = set(belief.proposition.lower().split())
    
    # Token overlap
    stopwords = {"i", "you", "me", "my", "your", "the", "a", "an", "is", "are",
                 "was", "to", "of", "in", "on", "for", "with", "about", "from"}
    content_text = text_tokens - stopwords
    content_belief = belief_tokens - stopwords
    
    if not content_text or not content_belief:
        overlap = 0
    else:
        overlap = len(content_text & content_belief) / max(len(content_text), 1)
    
    # Domain boost
    domain_boost = 1.0
    domain_categories = {
        "debugging": {"self_failure", "self_learning", "communication", "pattern"},
        "architecture": {"self_failure", "self_learning", "strength", "weakness", "skill"},
        "companion": {"trait", "preference", "value", "goal", "pattern", "emotional"},
        "decision": {"preference", "value", "goal", "pattern", "strength", "weakness"},
        "temporal": {"trait", "preference", "value", "goal"},
    }
    if belief.category in domain_categories.get(domain, set()):
        domain_boost = 1.5
    
    return overlap * domain_boost


def project_situation_model(situation: SituationModel) -> str:
    """Project the SituationModel into text for LLM consumption."""
    if situation.is_empty():
        return ""
    
    parts = []
    
    parts.append(f"SITUATION: {situation.domain.upper()}")
    
    if situation.current_objective:
        parts.append(f"Objective: {situation.current_objective}")
    
    if situation.urgency != "normal":
        parts.append(f"Urgency: {situation.urgency}")
    
    if situation.recommended_style:
        parts.append(f"Response style: {situation.recommended_style}")
    
    if situation.user_beliefs:
        parts.append("\nRelevant understanding:")
        for b in situation.user_beliefs[:5]:
            prefix = {"fact": "[F]", "observation": "[O]", "inference": "[I]", "hypothesis": "[H]"}.get(b.epistemic_level, "[?]")
            parts.append(f"  {prefix} [{b.confidence:.2f}] {b.proposition[:150]}")
    
    if situation.self_beliefs:
        parts.append("\nKIO self-awareness:")
        for b in situation.self_beliefs[:3]:
            parts.append(f"  - {b.proposition[:120]}")
    
    if situation.relationship_beliefs:
        parts.append("\nRelationship context:")
        for b in situation.relationship_beliefs[:3]:
            parts.append(f"  - {b.proposition[:120]}")
    
    if situation.tensions:
        parts.append("\nTensions:")
        for t in situation.tensions:
            parts.append(f"  ! {t}")
    
    if situation.uncertainties:
        parts.append("\nUncertainties:")
        for u in situation.uncertainties:
            parts.append(f"  ? {u}")
    
    if situation.open_loops:
        parts.append("\nOpen loops:")
        for lo in situation.open_loops:
            parts.append(f"  -> {lo}")
    
    return "\n".join(parts)
