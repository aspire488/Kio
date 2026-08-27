"""
profile.py — the personal profile as a GRAPH QUERY, not a store.

"What do you remember about me?" is a query over user-attributed claims in
the canonical Node/Link graph. Preferences, decisions, goals, rejections and
durable facts are the SAME substrate with universal metadata (event_time,
confidence, status, provenance). No profile table, no per-user rules.

profile_block(session_id) -> compact prompt projection:
  - only ACTIVE user-attributed claims (forgotten/superseded drop out)
  - grouped by the canonical relation vocabulary (prefers / decides /
    wants / said)
  - each line carries its recency ("told me 2026-05") so the model can
    distinguish "Joel said this in June 2026" from "Joel currently prefers
    this" — older history is never presented as current fact
  - bounded (top-N by confidence then recency) so it never dumps history
"""

from __future__ import annotations

import logging
from typing import Dict, List, Optional, Tuple

from mini_kio.semantic.graph import SemanticGraph, USER_KEY

logger = logging.getLogger(__name__)

_LABELS = {
    "prefers": "Preferences",
    "decides": "Decisions",
    "wants": "Goals",
    "recommends": "Recommendations",
    "said": "Things you told me",
}

_MAX_LINES = 18  # bounded: a compact block, never a history dump
_GROUP_CAP = 6


def _strip_prefix(claim: str) -> str:
    """Remove the 'relation: ' scaffolding added at import time so the block
    reads naturally inside its grouped section."""
    for prefix in ("prefers: ", "decided: ", "wants: ", "recommends: "):
        if claim.startswith(prefix):
            return claim[len(prefix):].strip()
    return claim


def _when(event_time: Optional[str]) -> str:
    if not event_time:
        return ""
    try:
        return event_time[:7]  # YYYY-MM
    except Exception:
        return ""


def _score(link) -> float:
    conf = float(getattr(link, "confidence", 0) or 0.5)
    when = _when(getattr(link, "event_time", None))
    recency_bonus = 0.15 if when and when >= "2026-01" else 0.0
    return conf + recency_bonus


def profile_block(session_id: str, *, max_lines: int = _MAX_LINES) -> str:
    """Compact 'About you' prompt projection from the canonical graph.

    Returns "" when the graph holds no user-attributed evidence.
    """
    if not session_id:
        return ""
    try:
        graph = SemanticGraph(session_id)
        links = graph.attributed_statements(USER_KEY, active_only=True, limit=200)
    except Exception as exc:
        logger.debug("[PROFILE] unavailable: %s", exc)
        return ""
    if not links:
        return ""

    # dedupe by claim text (same claim may appear with several dates).
    # "rule: ..." items (the noisy durable-instruction family from the
    # historical import) stay queryable in the graph but never surface in
    # the prompt projection — the profile is preferences/decisions/goals.
    best: Dict[str, object] = {}
    for link in links:
        claim = (getattr(link, "target_name", "") or "").strip()
        if not claim or claim.startswith("rule: "):
            continue
        existing = best.get(claim)
        if existing is None or _score(link) > _score(existing):
            best[claim] = link
    links = sorted(best.values(), key=_score, reverse=True)

    groups: Dict[str, List[Tuple[str, str]]] = {}
    for link in links:
        rel = (getattr(link, "relation", "") or "said") or "said"
        label = _LABELS.get(rel, "Things you told me")
        when = _when(getattr(link, "event_time", None))
        item = (_strip_prefix(getattr(link, "target_name", "") or ""), when)
        groups.setdefault(label, []).append(item)

    lines: List[str] = []
    for label in ("Preferences", "Decisions", "Goals", "Recommendations",
                  "Things you told me"):
        items = groups.get(label)
        if not items:
            continue
        body = []
        for claim, when in items[: _GROUP_CAP]:
            body.append(f"- {claim}" + (f" (told me {when})" if when else ""))
        if body:
            lines.append(f"{label}:\n" + "\n".join(body))
        if len(lines) >= max_lines // 2:
            break

    if not lines:
        return ""
    return "Known facts (newer overrides older):\n" + "\n".join(lines)


def recall_about_user(session_id: str, kind: str = "") -> List[str]:
    """Raw recall lines for 'what do you remember about me' style queries.

    kind filters by relation: 'prefer' | 'decide' | 'want' | 'said' | ''.
    Returns claim texts with their date suffix, newest first.
    """
    if not session_id:
        return []
    try:
        graph = SemanticGraph(session_id)
        links = graph.attributed_statements(USER_KEY, active_only=True, limit=100)
    except Exception:
        return []
    out: List[str] = []
    for link in links:
        rel = (getattr(link, "relation", "") or "said") or "said"
        if kind == "prefer" and rel not in ("prefers",):
            continue
        if kind == "decide" and rel not in ("decides",):
            continue
        if kind == "want" and rel not in ("wants",):
            continue
        claim = (getattr(link, "target_name", "") or "").strip()
        when = _when(getattr(link, "event_time", None))
        out.append(claim + (f" ({when})" if when else ""))
    return out
