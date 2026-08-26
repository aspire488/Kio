"""
proactive.py — general proactive evaluation over the canonical graph.

One mechanism, ONE outbound push path (the same Telegram sink as watches and
reminders). Evaluates the user's ACTIVE goals (wants/decides claims attributed
to the user in the canonical graph) and decides notify / silence with an
explicit reason:

  - the goal is old enough (age threshold)
  - the user has NOT re-engaged since (no newer user statement after it)
  - the goal was never notified before (one notification per goal, ever)

Silence is a normal, frequent result. No domain rules: any goal — personal,
project, arbitrary — goes through the same decision. The 'notified' marker
lives in the goal claim node's meta (graph state, not a new store).

poll_proactive() runs in the same daemon loop as poll_watches/poll_reminders.
"""

from __future__ import annotations

import logging
import time
from datetime import datetime, timedelta, timezone
from typing import Dict, List, Optional

from mini_kio.semantic.graph import SemanticGraph, USER_KEY
from mini_kio.monitoring.watches import send_telegram_message

logger = logging.getLogger(__name__)

MIN_AGE_S = 24 * 3600        # a goal younger than this is not stale
MIN_CONFIDENCE = 0.5
_MAX_CANDIDATES = 2          # never flood: at most this many notifications/tick

# Module-level state for tracking runtime changes across poll ticks
_PREV_RUNTIME_STATE: Dict = {}


# Sessions to evaluate (the founder's real conversation surface today).
DEFAULT_SESSIONS = ("tg_2146008061",)


def _ts_of(link) -> Optional[float]:
    et = getattr(link, "event_time", None)
    if et:
        try:
            dt = datetime.fromisoformat(str(et))
            if dt.tzinfo is None:
                dt = dt.replace(tzinfo=timezone.utc)
            return dt.timestamp()
        except Exception:
            pass
    ct = getattr(link, "created_at", None)
    if ct:
        try:
            # created_at is persisted as UTC; a NAIVE datetime must be
            # interpreted as UTC — treating it as local time shifts every
            # age by the local-UTC offset (live: on a UTC+5:30 machine a
            # goal "engaged 5 minutes ago" appeared 5.5h in the past and
            # the workflow completion gate misfired).
            if hasattr(ct, "timestamp"):
                if ct.tzinfo is None:
                    ct = ct.replace(tzinfo=timezone.utc)
                return ct.timestamp()
        except Exception:
            pass
    return None


def _goal_label(link) -> str:
    name = (getattr(link, "target_name", "") or "").strip()
    # strip the relation scaffolding ("plans to: X" -> "X") for a natural
    # notification; the stored claim keeps its full form.
    for prefix in ("wants: ", "decided: ", "plans to: "):
        if name.startswith(prefix):
            return name[len(prefix):].strip()
    return name


def _is_historical(link) -> bool:
    """Imported ChatGPT history is EVIDENCE, not current intent: a claim
    whose provenance is a chatgpt_export source must never drive proactive
    notifications. Only goals stated in live conversation qualify."""
    prov = getattr(link, "provenance", "") or ""
    return prov.startswith("chatgpt_export:")


_STALE_PROJECT_LIFECYCLE = ("active", "building", "planning", "researching", "paused")


# ── capability-aware opportunity sources ────────────────────────────────────
# Proactivity is a DECISION LAYER over real observations, not a reminder bot.
# Besides stale goals/projects it evaluates the state of capabilities KIO
# actually owns: workflow engine state (failed / awaiting approval /
# completed) and explicit user waiting states. Every candidate still passes
# the same gates: re-engagement, cooldown, value, interruption cost. The
# workflow marker lives on the WorkflowExecution.context (state on the
# canonical object, never a new store).

def _workflow_opportunities(now_ts: float, latest_user_ts: float) -> List[Dict]:
    """Real workflow-engine state -> notify candidates.

      FAILED          -> high value (error details worth surfacing)
      approval_pending-> high value (blocked on the user)
      COMPLETED       -> only when the user has NOT been active since it
                         finished ("the workflow finished while you were
                         away"; an active user already saw the run reply)

    Never fabricates a workflow: reads the actual engine instance. Returns
    [] when no engine exists (nothing created = nothing to surface).
    """
    try:
        from mini_kio.execution.workflows import _get_engine
        engine = _get_engine()
        wfs = engine.list_workflows()
    except Exception:
        return []
    out: List[Dict] = []
    for wf in wfs:
        st = (wf.status.value if hasattr(wf, "status") else "") or ""
        if not st:
            continue
        if bool((wf.context or {}).get("proactive_notified")):
            continue
        created = getattr(wf, "created_at", 0) or 0
        if not created or now_ts - created < MIN_AGE_S:
            # fresh workflows still have the user's attention; no need to
            # surface them (and never spam a just-created workflow)
            continue
        if st == "failed":
            out.append({"kind": "workflow", "subkind": "failed",
                        "name": wf.name or wf.id, "age_h": round((now_ts - created) / 3600, 1),
                        "value": 0.9, "wf": wf})
        elif st in ("pending", "paused", "running"):
            pending = [stp.name for stp in getattr(wf, "steps", [])
                       if getattr(stp, "approval_required", False) and not getattr(stp, "approved", False)]
            if pending and st != "running":
                out.append({"kind": "workflow", "subkind": "approval",
                            "name": wf.name or wf.id, "age_h": round((now_ts - created) / 3600, 1),
                            "value": 0.85, "steps": pending, "wf": wf})
            elif pending and st == "running":
                # still executing; only surface when it actually blocks
                pass
        elif st == "completed":
            completed_at = getattr(wf, "completed_at", 0) or 0
            if completed_at and completed_at > latest_user_ts:
                out.append({"kind": "workflow", "subkind": "completed",
                            "name": wf.name or wf.id, "age_h": round((now_ts - created) / 3600, 1),
                            "value": 0.7, "wf": wf})
    out.sort(key=lambda c: -c["value"])
    return out


def _wait_state_candidates(graph, latest_user_ts) -> List[Dict]:
    """Explicit user waiting states ("I'm waiting for X") from user claims.
    A waiting state is RECORDED as a candidate but the default decision is
    DEFER (wait for the awaited thing to actually resolve) — surfacing it
    would just be noise. The evaluator's reason makes the distinction."""
    out: List[Dict] = []
    try:
        claims = graph.attributed_statements(USER_KEY, active_only=True, limit=200)
    except Exception:
        return out
    import re as _re
    for l in claims:
        t = str(getattr(l, "target_name", "") or "").strip()
        low = t.lower()
        if "wait" not in low and "hold on" not in low:
            continue
        m = _re.search(r"waiting\s+(?:for|on)\s+(.+)$", low)
        if not m:
            continue
        subject = m.group(1).strip()[:80]
        if not subject:
            continue
        out.append({"kind": "wait", "subject": subject, "decision": "defer",
                    "reason": "waiting_state_unresolved"})
    return out


def _stale_project_candidates(graph, latest_user_ts, now_ts) -> List[Dict]:
    """Project-aware opportunity class: a project that was being actively
    worked on (building/active/planning/researching/paused) but has had no
    activity for a while AND the user has not engaged since. Same gates as
    goals: imported history can never trigger (project nodes only come from
    live lifecycle statements — provenance 'decomposer'), one notification
    ever (proactive_notified marker), never interrupt recent engagement.
    Silence is the normal result."""
    out = []
    try:
        projects = graph.all_projects()
    except Exception:
        return out
    for n in projects:
        meta = n.meta or {}
        lc = meta.get("lifecycle") or "mentioned"
        if lc not in _STALE_PROJECT_LIFECYCLE:
            continue
        last = meta.get("last_activity") or ""
        try:
            ts = datetime.fromisoformat(str(last)).timestamp()
        except Exception:
            continue
        if now_ts - ts < MIN_AGE_S:
            continue
        # recent user engagement after the last activity = do not interrupt
        if latest_user_ts > ts:
            continue
        if bool(meta.get("proactive_notified")):
            continue
        out.append({
            "kind": "project", "name": n.name, "lifecycle": lc,
            "age_h": round((now_ts - ts) / 3600, 1),
        })
    return out


def evaluate(session_id: str, *, now=None, min_age_s: float = MIN_AGE_S) -> List[Dict]:
    """Return decisions (notify or silence with a reason) for the session's
    stale user goals AND stale active projects. Pure decision logic — no
    side effects."""
    now = now or datetime.now(timezone.utc)
    out: List[Dict] = []
    try:
        graph = SemanticGraph(session_id)
    except Exception as exc:
        return [{"session": session_id, "decision": "silence",
                 "reason": f"graph_unavailable:{exc}"}]
    goals = graph.attributed_statements(USER_KEY, active_only=True, limit=120)

    # newest user activity after a goal = re-engagement
    latest_user_ts = 0.0
    for g in goals:
        t = _ts_of(g)
        if t and t > latest_user_ts:
            latest_user_ts = t

    now_ts = now.timestamp()
    # capability-aware candidates FIRST (specific, actionable, current).
    # evaluate() is PURE decision logic — the marker is written only after
    # successful delivery in poll_proactive (a failed send must NOT swallow
    # the opportunity permanently).
    for wf_opp in _workflow_opportunities(now_ts, latest_user_ts):
        if len(out) >= _MAX_CANDIDATES:
            break
        out.append({
            "session": session_id, "decision": "notify",
            "kind": "workflow", "subkind": wf_opp["subkind"],
            "goal": wf_opp["name"], "age_h": wf_opp["age_h"],
            "confidence": wf_opp["value"], "workflow_steps": wf_opp.get("steps", []),
        })
    # waiting states are DEFER by design (recorded, not pushed)
    for w in _wait_state_candidates(graph, latest_user_ts):
        out.append({"session": session_id, "decision": "defer",
                    "kind": "wait", "goal": w["subject"], "confidence": 0.5,
                    "reason": w["reason"]})
    if not goals and not out:
        return [{"session": session_id, "decision": "silence",
                 "reason": "no_goals"}]
    if not goals:
        for pr in _stale_project_candidates(graph, latest_user_ts, now_ts):
            if len(out) >= _MAX_CANDIDATES:
                break
            out.append({
                "session": session_id, "decision": "notify",
                "kind": "project", "goal": pr["name"], "lifecycle": pr["lifecycle"],
                "age_h": pr["age_h"], "confidence": 0.8,
            })
        if not out:
            return [{"session": session_id, "decision": "silence",
                     "reason": "no_goals"}]
        return out
    if len(out) >= _MAX_CANDIDATES:
        return out
    for g in goals:
        rel = (getattr(g, "relation", "") or "")
        if rel not in ("wants", "decides"):
            continue
        if _is_historical(g):
            continue
        label = _goal_label(g)
        if label.startswith(("rule:", "wants: to ask", "plans to: do it")):
            continue
        conf = float(getattr(g, "confidence", 0) or 0)
        if conf < MIN_CONFIDENCE:
            continue
        t = _ts_of(g)
        if not t:
            continue
        age = now_ts - t
        if age < min_age_s:
            continue
        # re-engagement check: a newer user statement after the goal means
        # the user has been back — do not interrupt.
        if latest_user_ts > t:
            continue
        node = graph.get_node(g.target_id)
        notified = bool((node.meta or {}).get("proactive_notified")) if node else False
        if notified:
            continue
        out.append({
            "session": session_id,
            "decision": "notify",
            "goal": label,
            "age_h": round(age / 3600, 1),
            "confidence": conf,
        })
    for pr in _stale_project_candidates(graph, latest_user_ts, now_ts):
        if len(out) >= _MAX_CANDIDATES:
            break
        out.append({
            "session": session_id, "decision": "notify",
            "kind": "project", "goal": pr["name"], "lifecycle": pr["lifecycle"],
            "age_h": pr["age_h"], "confidence": 0.8,
        })
    if not out:
        return [{"session": session_id, "decision": "silence",
                 "reason": "no_stale_goal_or_project"}]
    return out


# ── Interaction-aware suppression ──────────────────────────────────────
# When a user message was received recently, proactive notifications would
# appear as "dual responses" — the user sees their conversational reply PLUS
# an unrelated proactive notification. Suppress proactive sends when the
# user has been active within the last SUPPRESSION_WINDOW_S seconds.
_SUPPRESSION_WINDOW_S = 30  # seconds after last user interaction
_last_user_interaction_ts: float = 0.0

def mark_user_interaction() -> None:
    """Called from the pipeline when a user message is processed."""
    global _last_user_interaction_ts
    _last_user_interaction_ts = time.time()

def _is_user_recently_active() -> bool:
    """True when the user sent a message within the suppression window."""
    import time as _time
    return (_time.time() - _last_user_interaction_ts) < _SUPPRESSION_WINDOW_S


def poll_proactive(*, sessions: tuple = DEFAULT_SESSIONS) -> Dict:
    """Evaluate every configured session and push notifications for the
    top candidates. Returns {evaluated, notified, decisions}."""
    # Interaction-aware suppression: skip proactive sends when the user
    # recently interacted (prevents "dual response" appearance).
    if _is_user_recently_active():
        logger.info("[PROACTIVE] suppressed: user recently active")
        return {"evaluated": 0, "notified": 0, "decisions": [], "suppressed": True}
    evaluated = 0
    notified = 0
    decisions: List[Dict] = []
    for sid in sessions:
        for decision in evaluate(sid)[: _MAX_CANDIDATES]:
            evaluated += 1
            decisions.append(decision)
            if decision.get("decision") != "notify":
                continue
            goal = str(decision.get("goal") or "")
            age_h = decision.get("age_h", 0)
            if decision.get("kind") == "workflow":
                sub = decision.get("subkind") or ""
                if sub == "failed":
                    text = (
                        f"Hey — the '{goal}' workflow failed. I have the "
                        f"error details if you want them."
                    )
                elif sub == "approval":
                    steps = decision.get("workflow_steps") or []
                    text = (
                        f"The '{goal}' workflow is waiting on your approval"
                        + (f" for: {', '.join(steps)}." if steps else ".")
                        + " Say the word and it continues."
                    )
                else:
                    text = (
                        f"The '{goal}' workflow finished while you were away. "
                        f"All steps done."
                    )
            elif decision.get("kind") == "project":
                text = (
                    f"Hey — the '{goal}' build went quiet (~{age_h:.0f}h ago). "
                    f"Still working on it, or parked?"
                )
            else:
                text = (
                    f"Hey — you mentioned wanting to {goal} a while back "
                    f"(~{age_h:.0f}h ago). Still on the table, or parked?"
                )
            # delivery sink: the session's own chat id (user id from session key)
            chat_id = sid.split("_", 1)[1] if "_" in sid else sid
            if send_telegram_message(chat_id, text):
                notified += 1
                try:
                    graph = SemanticGraph(sid)
                    if decision.get("kind") == "workflow":
                        # marker lives on the WorkflowExecution.context (state
                        # on the canonical object) — written only after a
                        # CONFIRMED delivery so a failed send re-surfaces.
                        from mini_kio.execution.workflows import _get_engine
                        _eng = _get_engine()
                        for _wf in _eng.list_workflows():
                            if (_wf.name or _wf.id) == goal:
                                _wf.context["proactive_notified"] = datetime.now(
                                    timezone.utc
                                ).isoformat(timespec="seconds")
                                break
                    elif decision.get("kind") == "project":
                        # marker lives on the project node
                        for n in graph.all_projects():
                            if n.name == goal:
                                meta = dict(n.meta or {})
                                meta["proactive_notified"] = datetime.now(
                                    timezone.utc
                                ).isoformat(timespec="seconds")
                                graph.set_node_meta(n.id, meta)
                                break
                    else:
                        goals = graph.attributed_statements(USER_KEY, active_only=True, limit=120)
                        for g in goals:
                            if _goal_label(g) == goal:
                                node = graph.get_node(g.target_id)
                                if node:
                                    meta = dict(node.meta or {})
                                    meta["proactive_notified"] = datetime.now(
                                        timezone.utc
                                    ).isoformat(timespec="seconds")
                                    graph.set_node_meta(g.target_id, meta)
                                break
                except Exception as exc:
                    logger.warning("[PROACTIVE] marker write failed: %s", exc)
    # Away-event buffering: when the user is NOT actively engaged, record
    # meaningful events so they can be surfaced on return (companion behavior).
    # This is ADDITIVE — the Telegram push still fires for high-value events;
    # the away buffer captures events that would otherwise be lost when the
    # user is not at the keyboard.
    try:
        from mini_kio.core.activation import record_away_event
        for d in decisions:
            dec = d.get("decision", "")
            if dec not in ("notify", "defer"):
                continue
            kind = d.get("kind", "goal")
            goal = d.get("goal", "")
            sub = d.get("subkind", "")
            if kind == "workflow":
                desc = f"Workflow '{goal}' {sub}." if sub else f"Workflow '{goal}' event."
            elif kind == "project":
                desc = f"Project '{goal}' ({d.get('lifecycle', '')}) has been inactive for ~{d.get('age_h', 0):.0f}h."
            else:
                desc = f"Goal '{goal}' pending (~{d.get('age_h', 0):.0f}h old)."
            record_away_event(
                source=f"proactive:{kind}",
                description=desc,
                urgency="high" if kind == "workflow" and sub == "failed" else "medium",
            )
    except Exception:
        pass

    # Runtime state change detection (browser reconnect, integrity changes)
    # — same daemon, same loop, different trigger class.
    try:
        from mini_kio.core.runtime import get_runtime_snapshot
        snap = get_runtime_snapshot()
        if snap:
            browser_ready = bool(snap.get("browser_runtime_ready", False))
            integrity = str(snap.get("integrity_status", "unknown"))
            global _PREV_RUNTIME_STATE
            prev = _PREV_RUNTIME_STATE.copy() if _PREV_RUNTIME_STATE else {}
            _PREV_RUNTIME_STATE = {
                "browser_ready": browser_ready, "integrity": integrity,
            }
            if prev:
                from mini_kio.core.activation import record_away_event
                if not prev.get("browser_ready") and browser_ready:
                    record_away_event(
                        source="runtime",
                        description="Browser connection recovered.",
                        urgency="medium",
                    )
                elif prev.get("integrity") != "healthy" and integrity == "healthy":
                    record_away_event(
                        source="runtime",
                        description="KIO runtime recovered to healthy.",
                        urgency="low",
                    )
    except Exception:
        pass

    logger.info("[PROACTIVE] evaluated=%d notified=%d", evaluated, notified)
    return {"evaluated": evaluated, "notified": notified, "decisions": decisions}
