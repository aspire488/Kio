"""
companion/model.py — Persistent Companion Model.

The cognitive representation that sits between raw evidence and LLM reasoning.
Each Belief carries epistemic level, confidence, temporal scope, and full
provenance. The model evolves through consolidation, not accumulation.

This is the bridge between "retrieved memories" and "understanding."
"""

from __future__ import annotations

import json
import logging
import uuid
from dataclasses import dataclass, field, asdict
from datetime import datetime, timezone
from enum import Enum
from typing import Any, Dict, List, Optional

logger = logging.getLogger(__name__)


# ── Epistemic Levels ──────────────────────────────────────────────────────

class EpistemicLevel(str, Enum):
    """How confident are we in this belief and where did it come from?"""
    FACT = "fact"               # Directly stated by user or verified by runtime
    OBSERVATION = "observation" # Pattern observed across multiple interactions
    INFERENCE = "inference"     # Derived from 3+ observations by consolidation
    HYPOTHESIS = "hypothesis"   # Speculative, low evidence


class TemporalScope(str, Enum):
    """How stable is this belief over time?"""
    STABLE = "stable"           # Core traits, rarely change (confidence >= 0.8, 3+ months)
    EVOLVING = "evolving"       # Current preferences, goals (weeks/months)
    TEMPORARY = "temporary"     # Current state, mood, focus (hours/days)
    HISTORICAL = "historical"   # Superseded, kept for reference


class BeliefStatus(str, Enum):
    """Lifecycle status of a belief."""
    ACTIVE = "active"
    SUPERSEDED = "superseded"
    RETRACTED = "retracted"


class BeliefCategory(str, Enum):
    """What dimension of the user/self/relationship does this belief address?"""
    # User model
    TRAIT = "trait"
    PREFERENCE = "preference"
    VALUE = "value"
    GOAL = "goal"
    PATTERN = "pattern"
    COMMUNICATION = "communication"
    EMOTIONAL = "emotional"
    STRENGTH = "strength"
    WEAKNESS = "weakness"
    SKILL = "skill"
    PROJECT = "project"
    RELATIONSHIP = "relationship"
    STATE = "state"
    
    # Self model
    SELF_CAPABILITY = "self_capability"
    SELF_FAILURE = "self_failure"
    SELF_LEARNING = "self_learning"
    SELF_EVOLUTION = "self_evolution"
    
    # Relationship model
    RELATIONSHIP_PATTERN = "relationship_pattern"
    TRUST_SIGNAL = "trust_signal"
    FRICTION_POINT = "friction_point"
    COLLABORATION_PATTERN = "collaboration_pattern"
    EXPECTATION = "expectation"


# ── Belief ────────────────────────────────────────────────────────────────

@dataclass
class Belief:
    """A single belief in the companion model.
    
    Every belief carries its epistemic level, confidence, temporal scope,
    supporting evidence, and full provenance. Beliefs evolve through
    consolidation, not accumulation.
    """
    id: str = field(default_factory=lambda: str(uuid.uuid4())[:12])
    subject: str = ""                    # What this is about (e.g., "communication_style")
    proposition: str = ""                # The belief content (e.g., "Joel prefers terse responses when debugging")
    category: str = BeliefCategory.TRAIT
    epistemic_level: str = EpistemicLevel.OBSERVATION
    confidence: float = 0.5              # 0.0-1.0, evolves
    temporal_scope: str = TemporalScope.EVOLVING
    created_at: str = ""
    updated_at: str = ""
    last_reinforced_at: str = ""
    supporting_observations: List[str] = field(default_factory=list)  # observation IDs
    contradictory_observations: List[str] = field(default_factory=list)
    supersedes: Optional[str] = None     # ID of belief this replaces
    superseded_by: Optional[str] = None  # ID of belief that replaces this
    status: str = BeliefStatus.ACTIVE
    source_type: str = ""                # "live_interaction", "archive", "consolidation", "founder_canonical"
    notes: str = ""
    context: str = ""                    # When/where this applies ("when debugging", "generally")
    
    def __post_init__(self):
        now = _now_iso()
        if not self.created_at:
            self.created_at = now
        if not self.updated_at:
            self.updated_at = now
        if not self.last_reinforced_at:
            self.last_reinforced_at = now
    
    def to_dict(self) -> dict:
        return asdict(self)
    
    @classmethod
    def from_dict(cls, d: dict) -> "Belief":
        # Filter to only known fields
        known = {f.name for f in cls.__dataclass_fields__.values()}
        return cls(**{k: v for k, v in d.items() if k in known})
    
    @property
    def is_current(self) -> bool:
        return self.status == BeliefStatus.ACTIVE
    
    @property
    def is_historical(self) -> bool:
        return self.status == BeliefStatus.SUPERSEDED
    
    def reinforce(self, delta: float = 0.05) -> None:
        """Strengthen this belief with new supporting evidence."""
        self.confidence = min(1.0, self.confidence + delta)
        self.last_reinforced_at = _now_iso()
        self.updated_at = _now_iso()
    
    def weaken(self, delta: float = 0.1) -> None:
        """Weaken this belief due to contradictory evidence."""
        self.confidence = max(0.0, self.confidence - delta)
        self.updated_at = _now_iso()
    
    def supersede(self, successor_id: str) -> None:
        """Mark this belief as superseded by a newer one."""
        self.status = BeliefStatus.SUPERSEDED
        self.superseded_by = successor_id
        self.temporal_scope = TemporalScope.HISTORICAL
        self.updated_at = _now_iso()
    
    def decay(self, days_since_reinforcement: int) -> None:
        """Apply temporal decay for unreinforced beliefs."""
        if days_since_reinforcement > 90:
            self.confidence = max(0.1, self.confidence - 0.01 * (days_since_reinforcement // 30))
            self.updated_at = _now_iso()


def _now_iso() -> str:
    return datetime.now(timezone.utc).isoformat(timespec="seconds")


# ── CompanionModel ────────────────────────────────────────────────────────

@dataclass
class CompanionModel:
    """The persistent cognitive model of Joel + KIO + their relationship.
    
    This is the single source of truth for KIO's understanding. It replaces
    the evidence-dump approach with a structured, evolving model.
    
    The model is small enough (~50-200 beliefs) to fit in LLM context.
    It is loaded in full for companion queries, projected with epistemic
    markup, and the LLM reasons over it.
    """
    session_id: str = ""
    beliefs: List[Belief] = field(default_factory=list)
    
    # Metadata
    model_version: int = 1
    last_consolidated: str = ""
    total_observations_processed: int = 0
    created_at: str = ""
    updated_at: str = ""
    
    def __post_init__(self):
        now = _now_iso()
        if not self.created_at:
            self.created_at = now
        if not self.updated_at:
            self.updated_at = now
    
    # ── Query Methods ──────────────────────────────────────────────────
    
    def active_beliefs(self, category: Optional[str] = None) -> List[Belief]:
        """Get all active (non-superseded) beliefs, optionally filtered by category."""
        result = [b for b in self.beliefs if b.status == BeliefStatus.ACTIVE]
        if category:
            result = [b for b in result if b.category == category]
        return sorted(result, key=lambda b: -b.confidence)
    
    def beliefs_by_epistemic(self, level: str) -> List[Belief]:
        """Get active beliefs at a specific epistemic level."""
        return [b for b in self.active_beliefs() if b.epistemic_level == level]
    
    def contradictions(self) -> List[Dict[str, Any]]:
        """Find beliefs that contradict each other."""
        pairs = []
        active = self.active_beliefs()
        for i, b1 in enumerate(active):
            for b2 in active[i+1:]:
                if (b1.subject == b2.subject and 
                    b1.category == b2.category and
                    b1.id in (b2.contradictory_observations or []) or
                    b2.id in (b1.contradictory_observations or [])):
                    pairs.append({"belief_a": b1, "belief_b": b2})
        return pairs
    
    def historical_beliefs(self) -> List[Belief]:
        """Get superseded beliefs for temporal reasoning."""
        return [b for b in self.beliefs if b.status == BeliefStatus.SUPERSEDED]
    
    def find_by_subject(self, subject: str) -> List[Belief]:
        """Find all beliefs about a subject."""
        subject_low = subject.lower()
        return [b for b in self.active_beliefs() 
                if subject_low in b.subject.lower() or subject_low in b.proposition.lower()]
    
    def find_similar(self, proposition: str, category: Optional[str] = None) -> Optional[Belief]:
        """Find the most similar active belief to a given proposition.
        
        Uses semantic matching (sentence-transformers) when available,
        falls back to token overlap otherwise.
        """
        beliefs = self.active_beliefs(category=category)
        if not beliefs:
            return None
        
        # Try semantic matching first
        try:
            from mini_kio.companion.semantic import find_semantically_similar, is_available
            if is_available():
                candidates = [(b.proposition, 0.0) for b in beliefs]
                results = find_semantically_similar(
                    proposition, candidates, threshold=0.2, top_k=1
                )
                if results:
                    idx, score = results[0]
                    if score > 0.25:
                        return beliefs[idx]
        except ImportError:
            pass
        
        # Fallback: token overlap
        prop_tokens = set(proposition.lower().split())
        best_score = 0.0
        best_belief = None
        
        for b in beliefs:
            b_tokens = set(b.proposition.lower().split())
            if not b_tokens or not prop_tokens:
                continue
            overlap = len(prop_tokens & b_tokens) / max(len(prop_tokens), 1)
            if overlap > best_score and overlap > 0.3:
                best_score = overlap
                best_belief = b
        
        return best_belief
    
    # ── Mutation Methods ───────────────────────────────────────────────
    
    def add_belief(self, belief: Belief) -> Belief:
        """Add a new belief to the model."""
        self.beliefs.append(belief)
        self.updated_at = _now_iso()
        return belief
    
    def update_belief(self, belief_id: str, **kwargs) -> Optional[Belief]:
        """Update fields on an existing belief."""
        for b in self.beliefs:
            if b.id == belief_id:
                for k, v in kwargs.items():
                    if hasattr(b, k):
                        setattr(b, k, v)
                b.updated_at = _now_iso()
                self.updated_at = _now_iso()
                return b
        return None
    
    def get_belief(self, belief_id: str) -> Optional[Belief]:
        """Get a belief by ID."""
        for b in self.beliefs:
            if b.id == belief_id:
                return b
        return None
    
    def replace_belief(self, old_id: str, new_belief: Belief) -> Belief:
        """Supersede an old belief with a new one. Preserves history."""
        old = self.get_belief(old_id)
        if old:
            old.supersede(new_belief.id)
            new_belief.supersedes = old_id
            new_belief.supporting_observations = list(
                set(old.supporting_observations + new_belief.supporting_observations)
            )
        self.add_belief(new_belief)
        return new_belief
    
    # ── Projection ─────────────────────────────────────────────────────
    
    def stats(self) -> Dict[str, Any]:
        """Model statistics for monitoring."""
        active = self.active_beliefs()
        return {
            "total_beliefs": len(self.beliefs),
            "active_beliefs": len(active),
            "historical_beliefs": len(self.historical_beliefs()),
            "by_epistemic": {
                level: len([b for b in active if b.epistemic_level == level])
                for level in EpistemicLevel
            },
            "by_category": {},
            "avg_confidence": sum(b.confidence for b in active) / max(len(active), 1),
            "contradictions": len(self.contradictions()),
            "total_observations": self.total_observations_processed,
        }

    def prune(self, confidence_threshold: float = 0.15, max_beliefs: int = 200) -> int:
        """Prune low-confidence stale beliefs and enforce size limit.

        Never prunes:
        - FACT beliefs
        - operational_rule beliefs
        - beliefs with recent supporting observations

        Returns number of beliefs pruned.
        """
        pruned = 0
        now = _now_iso()

        # Sort active beliefs by confidence (ascending) for pruning candidates
        active = self.active_beliefs()
        if len(active) <= max_beliefs:
            # Only prune very low confidence beliefs
            for b in active:
                if b.epistemic_level == EpistemicLevel.FACT:
                    continue
                if "operational_rule" in (b.notes or ""):
                    continue
                if b.confidence < confidence_threshold:
                    b.status = BeliefStatus.RETRACTED
                    b.updated_at = now
                    pruned += 1
        else:
            # Over limit: prune lowest confidence non-essential beliefs
            prunable = [b for b in active
                        if b.epistemic_level != EpistemicLevel.FACT
                        and "operational_rule" not in (b.notes or "")]
            prunable.sort(key=lambda b: b.confidence)
            excess = len(active) - max_beliefs
            for b in prunable[:excess]:
                b.status = BeliefStatus.RETRACTED
                b.updated_at = now
                pruned += 1

        if pruned:
            logger.info("[MODEL] Pruned %d beliefs (threshold=%.2f, max=%d)",
                        pruned, confidence_threshold, max_beliefs)
        return pruned


# ── Persistence ───────────────────────────────────────────────────────────

def save_model(model: CompanionModel) -> None:
    """Persist the companion model to SQLite via ORM."""
    try:
        from mini_kio.backend.db import db_session, init_db
        from mini_kio.backend.models import CompanionModelRecord
        init_db()
        model.updated_at = _now_iso()
        data = {
            "session_id": model.session_id,
            "beliefs": [b.to_dict() for b in model.beliefs],
            "model_version": model.model_version,
            "last_consolidated": model.last_consolidated,
            "total_observations_processed": model.total_observations_processed,
            "created_at": model.created_at,
            "updated_at": model.updated_at,
        }
        json_str = json.dumps(data, ensure_ascii=False)
        with db_session() as db:
            existing = db.query(CompanionModelRecord).filter(
                CompanionModelRecord.session_id == model.session_id
            ).first()
            if existing:
                existing.model_json = json_str
                existing.updated_at = datetime.now(timezone.utc)
            else:
                db.add(CompanionModelRecord(
                    session_id=model.session_id,
                    model_json=json_str,
                ))
    except Exception as exc:
        logger.warning("[COMPANION] Failed to save model: %s", exc)


def load_model(session_id: str) -> CompanionModel:
    """Load the companion model from SQLite. Returns empty model if not found."""
    try:
        from mini_kio.backend.db import db_session, init_db
        from mini_kio.backend.models import CompanionModelRecord
        init_db()
        with db_session() as db:
            row = db.query(CompanionModelRecord).filter(
                CompanionModelRecord.session_id == session_id
            ).first()
            if row and row.model_json:
                data = json.loads(row.model_json)
                model = CompanionModel(
                    session_id=data.get("session_id", session_id),
                    beliefs=[Belief.from_dict(b) for b in data.get("beliefs", [])],
                    model_version=data.get("model_version", 1),
                    last_consolidated=data.get("last_consolidated", ""),
                    total_observations_processed=data.get("total_observations_processed", 0),
                    created_at=data.get("created_at", ""),
                    updated_at=data.get("updated_at", ""),
                )
                return model
    except Exception as exc:
        logger.warning("[COMPANION] Failed to load model: %s", exc)
    
    return CompanionModel(session_id=session_id)


def get_or_create_model(session_id: str) -> CompanionModel:
    """Get existing model or create a new one."""
    model = load_model(session_id)
    if not model.beliefs and not model.created_at:
        model = CompanionModel(session_id=session_id)
        save_model(model)
    return model
