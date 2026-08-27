"""
proactive_evaluator.py — Broad Proactive Intelligence Evaluator

Evaluates opportunities across the FULL KIO capability surface to decide
whether intervention is warranted. Reasons about:

  - Watcher/reminder events
  - System state changes
  - Browser/MCP task completions
  - Project lifecycle transitions
  - Dependency/blocker resolution
  - Recurring workflow state changes
  - Long-running operation attention needs

Possible outcomes: ACT | NOTIFY | WAIT | WATCH | SILENCE

SILENCE is the DEFAULT and FREQUENT result. KIO must not be annoying.

Design rules:
  - Uses canonical state (runtime, watchers, reminders, graph) — NO separate
    proactivity database
  - Historical data NEVER independently causes proactive action
  - Imported historical data NEVER independently triggers notification
  - The evaluator REASONS about interruption cost before surfacing anything
  - One-shot evaluation per call; no polling loops, no autonomous action
"""

from __future__ import annotations

import logging
import time
from dataclasses import dataclass, field
from enum import Enum
from typing import Any, Dict, List, Optional

logger = logging.getLogger(__name__)


class ProactiveOutcome(Enum):
    """Possible evaluator decisions."""
    ACT = "act"           # Take autonomous action (rare, bounded)
    NOTIFY = "notify"     # Surface a notification to the user
    WAIT = "wait"         # Something is approaching but not yet actionable
    WATCH = "watch"       # Monitor a condition for future evaluation
    SILENCE = "silence"   # Do nothing (most common result)


class InterventionUrgency(Enum):
    """Urgency classification for intervention opportunities."""
    CRITICAL = "critical"   # Safety, data loss, blocking error
    HIGH = "high"           # Time-sensitive, user waiting on it
    MEDIUM = "medium"       # Meaningful but not urgent
    LOW = "low"             # Nice to know, no rush
    NONE = "none"           # Not worth interrupting


@dataclass
class ProactiveOpportunity:
    """A detected opportunity for proactive intervention."""
    source: str               # What generated this (watcher, reminder, runtime, etc.)
    description: str          # Human-readable description
    urgency: InterventionUrgency
    confidence: float         # 0.0-1.0: how confident we are this is real
    interruption_cost: float  # 0.0-1.0: how disruptive the interruption is
    value: float              # 0.0-1.0: how valuable the intervention is
    metadata: Dict[str, Any] = field(default_factory=dict)


@dataclass
class ProactiveDecision:
    """The evaluator's decision for a given opportunity."""
    outcome: ProactiveOutcome
    opportunity: Optional[ProactiveOpportunity] = None
    reason: str = ""


# ── Interruption cost baselines ────────────────────────────────────────
# Different source types have different inherent interruption costs.
_SOURCE_INTERRUPTION_COST: Dict[str, float] = {
    "watcher_change": 0.2,      # Something the user explicitly asked to watch
    "reminder_due": 0.1,        # User explicitly set a reminder
    "task_completed": 0.3,      # A background task finished
    "project_transition": 0.4,  # Project lifecycle changed
    "system_event": 0.3,        # System state change
    "dependency_resolved": 0.2, # A blocker disappeared
    "long_operation": 0.25,     # A long-running op needs attention
    "recurring_workflow": 0.35, # A recurring pattern reached a state
}

# ── Value baselines ────────────────────────────────────────────────────
_SOURCE_VALUE: Dict[str, float] = {
    "watcher_change": 0.8,      # High value: user explicitly wants to know
    "reminder_due": 0.9,        # Very high: user set this intentionally
    "task_completed": 0.5,      # Moderate: useful but not critical
    "project_transition": 0.4,  # Low-moderate: informational
    "system_event": 0.3,        # Low: usually noise
    "dependency_resolved": 0.6, # Moderate-high: unblocks work
    "long_operation": 0.5,      # Moderate: user may be waiting
    "recurring_workflow": 0.3,  # Low: informational
}


def _cooldown_reasonable(source: str, last_notified: Dict[str, float],
                         cooldown_s: float = 1800.0) -> bool:
    """Check if enough time has passed since last notification from this source."""
    last = last_notified.get(source, 0.0)
    return (time.time() - last) >= cooldown_s


class ProactiveEvaluator:
    """Evaluates whether any available event deserves proactive intervention.

    Usage:
        evaluator = ProactiveEvaluator()
        decision = evaluator.evaluate(opportunities)
        if decision.outcome == ProactiveOutcome.NOTIFY:
            # Surface notification to user
        # Otherwise: SILENCE (do nothing)
    """

    def __init__(self):
        self._last_notified: Dict[str, float] = {}
        self._stats: Dict[str, int] = {
            "evaluated": 0,
            "silenced": 0,
            "notified": 0,
            "waited": 0,
            "watched": 0,
        }

    def evaluate(self, opportunities: List[ProactiveOpportunity],
                 *, user_engaged: bool = False,
                 recent_notification_count: int = 0) -> ProactiveDecision:
        """Evaluate a list of opportunities and return the best decision.

        Args:
            opportunities: Detected opportunities from the capability surface.
            user_engaged: Whether the user is actively in conversation (suppresses
                          low-urgency notifications to avoid disruption).
            recent_notification_count: How many notifications sent recently
                                       (for cooldown/duplication gating).

        Returns:
            ProactiveDecision with the best outcome and reasoning.
        """
        self._stats["evaluated"] += 1

        if not opportunities:
            self._stats["silenced"] += 1
            return ProactiveDecision(
                outcome=ProactiveOutcome.SILENCE,
                reason="no opportunities detected",
            )

        # Score each opportunity
        scored: List[tuple[float, ProactiveOpportunity]] = []
        for opp in opportunities:
            score = self._score_opportunity(
                opp, user_engaged=user_engaged,
                recent_notification_count=recent_notification_count,
            )
            if score > 0:
                scored.append((score, opp))

        if not scored:
            self._stats["silenced"] += 1
            return ProactiveDecision(
                outcome=ProactiveOutcome.SILENCE,
                reason="all opportunities scored below threshold",
            )

        # Pick the highest-scored opportunity
        scored.sort(key=lambda x: x[0], reverse=True)
        best_score, best_opp = scored[0]

        # Apply decision logic
        decision = self._decide(best_opp, best_score, user_engaged)
        stat_key = decision.outcome.value
        if stat_key == "silence":
            stat_key = "silenced"
        else:
            stat_key = stat_key + "d"
        self._stats[stat_key] = self._stats.get(stat_key, 0) + 1
        return decision

    def _score_opportunity(self, opp: ProactiveOpportunity, *,
                           user_engaged: bool,
                           recent_notification_count: int) -> float:
        """Score an opportunity for intervention value.

        Returns 0.0 if the opportunity should be suppressed.
        """
        # Historical data NEVER independently causes proactive action
        if opp.metadata.get("provenance") in ("historical", "import", "chatgpt_export"):
            return 0.0

        # Cooldown check: don't re-notify for the same source too quickly
        if not _cooldown_reasonable(opp.source, self._last_notified):
            return 0.0

        # Duplication check: suppress if very similar notification was recent
        if recent_notification_count >= 3:
            return 0.0

        # User engagement gating: suppress low-urgency when user is active
        if user_engaged and opp.urgency in (InterventionUrgency.LOW, InterventionUrgency.NONE):
            return 0.0

        # Score = value * confidence * (1 - interruption_cost)
        # Urgency multiplier
        urgency_mult = {
            InterventionUrgency.CRITICAL: 2.0,
            InterventionUrgency.HIGH: 1.5,
            InterventionUrgency.MEDIUM: 1.0,
            InterventionUrgency.LOW: 0.5,
            InterventionUrgency.NONE: 0.0,
        }.get(opp.urgency, 0.0)

        raw = opp.value * opp.confidence * (1.0 - opp.interruption_cost) * urgency_mult
        return max(raw, 0.0)

    def _decide(self, opp: ProactiveOpportunity, score: float,
                user_engaged: bool) -> ProactiveDecision:
        """Map score + urgency to a concrete decision."""
        # Critical: always surface
        if opp.urgency == InterventionUrgency.CRITICAL:
            return ProactiveDecision(
                outcome=ProactiveOutcome.NOTIFY,
                opportunity=opp,
                reason=f"critical urgency: {opp.description}",
            )

        # High urgency: notify unless user is deeply engaged
        if opp.urgency == InterventionUrgency.HIGH:
            if user_engaged and opp.value < 0.7:
                return ProactiveDecision(
                    outcome=ProactiveOutcome.WAIT,
                    opportunity=opp,
                    reason="high urgency but user engaged; deferring",
                )
            return ProactiveDecision(
                outcome=ProactiveOutcome.NOTIFY,
                opportunity=opp,
                reason=f"high urgency: {opp.description}",
            )

        # Medium: notify only if score is strong and user isn't active
        if opp.urgency == InterventionUrgency.MEDIUM:
            if score >= 0.3 and not user_engaged:
                return ProactiveDecision(
                    outcome=ProactiveOutcome.NOTIFY,
                    opportunity=opp,
                    reason=f"medium urgency, score {score:.2f}: {opp.description}",
                )
            return ProactiveDecision(
                outcome=ProactiveOutcome.WAIT,
                opportunity=opp,
                reason="medium urgency, deferring to better timing",
            )

        # Low: only if very strong score and user is idle
        if opp.urgency == InterventionUrgency.LOW:
            if score >= 0.5 and not user_engaged:
                return ProactiveDecision(
                    outcome=ProactiveOutcome.NOTIFY,
                    opportunity=opp,
                    reason=f"low urgency but high value ({score:.2f}): {opp.description}",
                )
            return ProactiveDecision(
                outcome=ProactiveOutcome.WATCH,
                opportunity=opp,
                reason="low urgency, watching for better timing",
            )

        # None: always silence
        return ProactiveDecision(
            outcome=ProactiveOutcome.SILENCE,
            reason="no actionable urgency",
        )

    def record_notification(self, source: str) -> None:
        """Record that a notification was sent from this source (for cooldown)."""
        self._last_notified[source] = time.time()

    def get_stats(self) -> Dict[str, int]:
        return dict(self._stats)

    def collect_opportunities_from_runtime(self, runtime_context: Optional[Dict] = None,
                                           session_id: str = "") -> List[ProactiveOpportunity]:
        """Collect opportunities from the current KIO runtime state.

        This scans available state across the capability surface:
        - Pending reminders that are due
        - Watcher changes
        - Pending dependencies
        - Long-running operations
        - Project lifecycle transitions

        Returns a list of opportunities (may be empty = SILENCE is correct).
        """
        opportunities: List[ProactiveOpportunity] = []

        # 1. Check for due reminders
        try:
            from mini_kio.backend.models import ReminderModel
            from mini_kio.backend.db import db_session, init_db
            init_db()
            now = __import__('datetime').datetime.now(__import__('datetime').timezone.utc)
            with db_session() as db:
                due = (
                    db.query(ReminderModel)
                    .filter(
                        ReminderModel.active == True,  # noqa: E712
                        ReminderModel.delivered_at.is_(None),
                        ReminderModel.due_at <= now,
                    )
                    .limit(5)
                    .all()
                )
                for r in due:
                    opp = ProactiveOpportunity(
                        source="reminder_due",
                        description=f"Reminder due: {r.text[:100]}",
                        urgency=InterventionUrgency.HIGH,
                        confidence=1.0,
                        interruption_cost=_SOURCE_INTERRUPTION_COST["reminder_due"],
                        value=_SOURCE_VALUE["reminder_due"],
                        metadata={"reminder_id": r.id, "text": r.text, "chat_id": r.chat_id},
                    )
                    opportunities.append(opp)
        except Exception as exc:
            logger.debug("[PROACTIVE] reminder scan failed: %s", exc)

        # 2. Check for active watches with changes
        try:
            from mini_kio.backend.models import WatchModel
            from mini_kio.backend.db import db_session, init_db
            init_db()
            with db_session() as db:
                active_watches = (
                    db.query(WatchModel)
                    .filter(WatchModel.active == True)  # noqa: E712
                    .limit(10)
                    .all()
                )
                for w in active_watches:
                    # Check if there's been a recent change (last_seen_ts is recent)
                    if w.last_seen_ts:
                        age_minutes = (__import__('datetime').datetime.now(__import__('datetime').timezone.utc) - w.last_seen_ts).total_seconds() / 60
                        if age_minutes < 30:
                            opp = ProactiveOpportunity(
                                source="watcher_change",
                                description=f"Watched target '{w.target}' has recent activity",
                                urgency=InterventionUrgency.MEDIUM,
                                confidence=0.7,
                                interruption_cost=_SOURCE_INTERRUPTION_COST["watcher_change"],
                                value=_SOURCE_VALUE["watcher_change"],
                                metadata={"watch_id": w.id, "target": w.target, "chat_id": w.chat_id},
                            )
                            opportunities.append(opp)
        except Exception as exc:
            logger.debug("[PROACTIVE] watch scan failed: %s", exc)

        # 3. Check for runtime state changes (degraded → healthy, browser reconnection)
        try:
            from mini_kio.core.runtime import get_runtime_snapshot
            snap = get_runtime_snapshot()
            if snap:
                health = int(snap.get("health_score", 0) or 0)
                integrity = str(snap.get("integrity_status", "unknown"))
                browser_ready = bool(snap.get("browser_runtime_ready", False))
                # Store previous state for comparison (module-level)
                global _PREV_RUNTIME_STATE
                prev = _PREV_RUNTIME_STATE.copy() if _PREV_RUNTIME_STATE else {}
                _PREV_RUNTIME_STATE = {
                    "health": health, "integrity": integrity,
                    "browser_ready": browser_ready,
                }
                if prev:
                    # Browser reconnection
                    if not prev.get("browser_ready") and browser_ready:
                        opp = ProactiveOpportunity(
                            source="system_event",
                            description="Browser connection recovered",
                            urgency=InterventionUrgency.MEDIUM,
                            confidence=0.9,
                            interruption_cost=0.2,
                            value=0.6,
                        )
                        opportunities.append(opp)
                    # Integrity degraded
                    elif prev.get("integrity") == "healthy" and integrity != "healthy":
                        opp = ProactiveOpportunity(
                            source="system_event",
                            description=f"Runtime integrity changed to {integrity}",
                            urgency=InterventionUrgency.HIGH,
                            confidence=0.8,
                            interruption_cost=0.3,
                            value=0.5,
                        )
                        opportunities.append(opp)
                    # Recovery from degraded
                    elif prev.get("integrity") != "healthy" and integrity == "healthy":
                        opp = ProactiveOpportunity(
                            source="system_event",
                            description="Runtime recovered to healthy",
                            urgency=InterventionUrgency.LOW,
                            confidence=0.9,
                            interruption_cost=0.1,
                            value=0.3,
                        )
                        opportunities.append(opp)
        except Exception as exc:
            logger.debug("[PROACTIVE] runtime scan failed: %s", exc)

        return opportunities


# Module-level state for tracking runtime changes across poll ticks
_PREV_RUNTIME_STATE: Dict[str, object] = {}
