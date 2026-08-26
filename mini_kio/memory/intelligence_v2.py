"""
intelligence_v2.py — Evidence-composition intelligence layer for KIO.

Replaces intelligence_layer.py with:
1. Salience-scored evidence retrieval (not flat injection)
2. Temporal trajectory analysis (linear trend by month)
3. Live feedback loop (corrections/approvals/frustration detection)
4. Entity relationship linking (episodes ↔ projects, corrections ↔ claims)

Reads from the semantic graph only. Does NOT re-parse raw export.
"""

from __future__ import annotations

import logging
import math
import re
from collections import defaultdict
from dataclasses import dataclass, field
from datetime import datetime, timezone
from typing import Any, Dict, List, Optional, Tuple

from mini_kio.semantic.graph import SemanticGraph, SemanticNode, SemanticLink, USER_KEY, KIO_KEY
from mini_kio.backend.db import db_session
from mini_kio.backend.models import SemanticNodeModel, SemanticLinkModel

logger = logging.getLogger(__name__)

PROVENANCE = "intelliv2"


# ── salience signals ──────────────────────────────────────────────────────

_EMOTION_RE = re.compile(
    r"\b(frustrat|annoy|piss|mad|angry|irritat|ugh|broken|not ?working|"
    r"excit|stoked|pumped|hyped|amazing|awesome|let'?s ?go|yess?|finally|"
    r"urgent|asap|deadline|today|tonight|"
    r"confused|don'?t ?understand|lost|"
    r"nice|perfect|exactly|great|thanks|works)\b", re.I
)

_CORRECTION_RE = re.compile(
    r"\b(no|wrong|not what i|actually|wait|hold on|scratch|nvm|"
    r"that'?s not|you misunderstood|don'?t do that|not like that|"
    r"stop doing|change that|fix that|redo|i meant|i wanted|i asked)\b", re.I
)

_APPROVAL_RE = re.compile(
    r"\b(nice|perfect|exactly|that'?s ?right|good ?job|well ?done|"
    r"you ?got ?it|nailed ?it|there ?you ?go|it ?works|"
    r"exactly ?what i ?needed|saved ?me|thanks|thank you|"
    r"love ?it|respect|props|kudos)\b", re.I
)

_FRUSTRATION_RE = re.compile(
    r"\b(frustrat|annoy|piss|mad|angry|irritat|ugh|god ?damn|"
    r"this ?is ?broken|not ?working|doesn'?t ?work|ridiculous|stupid|"
    r"sucks|trash|garbage|stuck|keeps ?happening|every ?time|still ?not|"
    r"what ?the|how ?is ?this|why does)\b", re.I
)


@dataclass
class Evidence:
    """A single piece of evidence from the graph."""
    text: str
    category: str          # correction, emotion, project, communication, etc.
    source: str            # graph key or 'live:*'
    timestamp: str = ""    # ISO or year-month
    confidence: float = 0.5
    salience: float = 0.0  # computed score
    meta: Dict[str, Any] = field(default_factory=dict)


def _now_iso() -> str:
    return datetime.now(timezone.utc).isoformat(timespec="seconds")


def _parse_timestamp(ts: str) -> Optional[datetime]:
    """Parse ISO or year-month string to datetime."""
    if not ts:
        return None
    try:
        return datetime.fromisoformat(ts.replace("Z", "+00:00"))
    except (ValueError, TypeError):
        pass
    try:
        return datetime.strptime(ts[:7], "%Y-%m").replace(tzinfo=timezone.utc)
    except (ValueError, TypeError):
        return None


def _keywords(text: str) -> set:
    """Extract meaningful keywords from text."""
    stop = frozenset(
        "a an the and or but so if then than to of for with about on at in from by "
        "i you me my your we our he she him his her it its this that what why how "
        "when where who which there here now just really very like want would will "
        "can could should shall may not no yes ok okay please tell say said says "
        "think believe know wants something anything everything".split()
    )
    return {w for w in re.findall(r"[a-z]{3,}", text.lower()) if w not in stop}


# ═══════════════════════════════════════════════════════════════════════════════
# 1. EVIDENCE COMPOSITION
# ═══════════════════════════════════════════════════════════════════════════════

def _score_salience(ev: Evidence, query_kw: set, now: datetime) -> float:
    """Score evidence by recency, topic overlap, and type relevance."""
    score = 0.0

    # Recency: exponential decay, half-life 60 days
    ts = _parse_timestamp(ev.timestamp)
    if ts and now:
        days_old = max(0, (now - ts).total_seconds() / 86400)
        recency = math.exp(-0.693 * days_old / 60)  # half-life 60d
        score += recency * 0.5

    # Topic overlap: Jaccard-like but favoring query coverage
    if query_kw and ev.text:
        ev_kw = _keywords(ev.text)
        if ev_kw:
            overlap = len(query_kw & ev_kw) / max(len(query_kw), 1)
            score += overlap * 0.35

    # Category relevance boost (corrections and emotions score higher)
    cat_boost = {
        "correction": 0.15, "failure": 0.15, "expectation": 0.12,
        "emotion": 0.12, "praise": 0.10, "project": 0.10,
        "communication": 0.08, "identity": 0.08,
    }
    score += cat_boost.get(ev.category, 0.05)

    # Confidence factor
    score *= max(0.3, ev.confidence)

    return round(score, 4)


# Query routing patterns
_ROUTES = {
    "project": re.compile(
        r"\b(project|building|working on|app|website|prototype|"
        r"develop|code|abandon|drop|revive|continue|resume|"
        r"what did i|what am i|what have i|been doing|"
        r"focused on|up to|lately|recently|currently)\b", re.I),
    "emotion": re.compile(
        r"\b(frustrat|angry|piss|excit|hype|amazing|stuck|broken|"
        r"annoy|confused|lost|happy|sad|mood|feel|"
        r"when.*debug|when.*frustrated|when.*excited)\b", re.I),
    "correction": re.compile(
        r"\b(correct|wrong|fix|mistake|error|regression|"
        r"broke|broken|what did you|you (?:kept|keep|always|never)|"
        r"corrected you|got wrong|messed up)\b", re.I),
    "communication": re.compile(
        r"\b(talk|speak|communicate|phrase|slang|"
        r"how do i|how i|my style|tone|"
        r"how.*talk|how.*speak|how.*express)\b", re.I),
    "identity": re.compile(
        r"\b(who am i|about me|what do you know about me|"
        r"tell me about me|what am i|my name|my age|my college)\b", re.I),
    "kio": re.compile(
        r"\b(kio|yourself|what do you know|what can you|"
        r"tell me about yourself|self.model)\b", re.I),
    "decision": re.compile(
        r"\b(decid|decis|chose|picked|change.?mind|reversal|"
        r"why did i|dropped|abandoned|switch|"
        r"used to|before|earlier|previously)\b", re.I),
    "technical": re.compile(
        r"\b(python|code|tech|learn|skill|programming|"
        r"developer|engineering|git|api|database)\b", re.I),
    "relationship": re.compile(
        r"\b(relationship|how.*work together|how.*interact|"
        r"history|how have you changed|how.*evolved)\b", re.I),
}


def _evidence_from_graph(graph: SemanticGraph) -> List[Evidence]:
    """Pull all evidence nodes from the graph as Evidence objects."""
    evidence: List[Evidence] = []
    seen_keys: set = set()

    # Statements attributed to user — query both live session and archive_v3
    links = graph.attributed_statements(
        USER_KEY, relation="said",
        active_only=True, limit=2000,
    )
    # Also pull archive_v3 links directly
    try:
        from sqlalchemy import or_
        with db_session() as db:
            archive_links = db.query(SemanticLinkModel).filter(
                SemanticLinkModel.session_id == "archive_v3",
                SemanticLinkModel.status == "active",
            ).limit(2000).all()
            # Convert to SemanticLink objects
            nodes_map = graph._nodes_for(archive_links)
            archive_sem_links = [SemanticLink.from_model(r, nodes_map) for r in archive_links]
            links = links + archive_sem_links
    except Exception:
        pass
    for link in links:
        target = link.target_name or ""
        prov = link.provenance or ""
        key = f"{prov}:{target}"
        if key in seen_keys:
            continue
        seen_keys.add(key)

        cat = _categorize_link(target, prov)
        evidence.append(Evidence(
            text=target, category=cat,
            source=link.target_key or target,
            timestamp=_extract_timestamp_from_meta(prov, target),
            confidence=link.confidence or 0.5,
        ))

    # Direct graph nodes: read description + meta_json for evidence
    # Query both the live session AND archive_v3 (ChatGPT export data)
    try:
        from sqlalchemy import or_
        with db_session() as db:
            rows = db.query(SemanticNodeModel).filter(
                SemanticNodeModel.status == "active",
                or_(
                    SemanticNodeModel.session_id == graph.session_id,
                    SemanticNodeModel.session_id == "archive_v3",
                ),
            ).order_by(SemanticNodeModel.id.desc()).limit(1000).all()
    except Exception:
        rows = []

    for row in rows:
        node = SemanticNode.from_model(row)
        key = node.key or ""
        if key in seen_keys:
            continue
        seen_keys.add(key)

        # Parse meta_json for category and evidence
        import json as _json
        meta = {}
        try:
            meta = _json.loads(row.meta_json) if row.meta_json else {}
        except Exception:
            pass

        # Category from meta_json (archive_v3 stores it there)
        cat = meta.get("category", "")
        subcat = meta.get("subcategory", "")

        # Evidence text: prefer description, fallback to name
        text = row.description or node.name or ""
        # Truncate long evidence
        if len(text) > 500:
            text = text[:500] + "..."

        # Timestamp from meta or created_at
        date_range = meta.get("date_range", [])
        ts = ""
        if date_range and len(date_range) >= 2:
            ts = date_range[-1]  # use end of range
        elif row.created_at:
            ts = str(row.created_at)[:10]

        confidence = meta.get("confidence", 0.5)

        evidence.append(Evidence(
            text=text, category=cat or "claim",
            source=key, timestamp=ts,
            confidence=float(confidence),
            meta={**meta, "subcategory": subcat, "node_name": node.name or ""},
        ))

    return evidence


def _categorize_link(target_name: str, provenance: str) -> str:
    """Determine category from link target name and provenance."""
    low_target = (target_name or "").lower()
    low_prov = (provenance or "").lower()

    if "longitudinal_v2:project" in low_prov or "project" in low_target:
        return "project"
    if "longitudinal_v2:emotional" in low_prov or "intellayer:emotional" in low_prov:
        return "emotion"
    if "longitudinal_v2:decision" in low_prov:
        return "decision"
    if "longitudinal_v2:shared" in low_prov:
        return "shared_history"
    if "intellayer:communication" in low_prov or "communication" in low_target:
        return "communication"
    if "live:" in low_prov:
        return low_prov.split("live:")[-1].split(",")[0] or "live_interaction"

    # Content-based fallback
    if any(w in low_target for w in ("correct", "wrong", "fix", "not like that")):
        return "correction"
    if any(w in low_target for w in ("perfect", "great", "works", "nailed")):
        return "praise"
    if any(w in low_target for w in ("broken", "failed", "error", "crash")):
        return "failure"
    if any(w in low_target for w in ("expect", "should", "must", "need you to")):
        return "expectation"
    return "shared_history"


def _extract_timestamp_from_meta(provenance: str, target: str) -> str:
    """Try to extract a timestamp from provenance or target string."""
    # Look for year-month pattern in target text
    m = re.search(r"(\d{4}-\d{2})", target)
    if m:
        return m.group(1)
    return ""


class IntelligenceV2:
    """Evidence-composition intelligence for a session."""

    def __init__(self, session_id: str):
        self.session_id = session_id or "tg_default"
        self._graph = SemanticGraph(self.session_id)
        self._cache: Optional[Tuple[float, List[Evidence]]] = None
        self._CACHE_TTL = 300  # 5 min, not 1 hour
        self._interaction_buffer: List[Dict[str, Any]] = []

    def query(self, user_text: str, *, max_items: int = 15) -> str:
        """Retrieve relevance-ranked evidence for a user message.

        Returns tiered output:
          - PRIMARY: top 5 most salient evidence items
          - CONTEXT: remaining relevant items (up to max_items)
        """
        if not user_text or not user_text.strip():
            return ""

        now = datetime.now(timezone.utc)
        query_kw = _keywords(user_text)
        low = user_text.lower()

        # Route detection
        matched = [r for r, pat in _ROUTES.items() if pat.search(low)]
        if not matched:
            # Default to identity only — do NOT inject project context for
            # queries that don't mention projects/work. The LLM should reason
            # from the user's actual intent, not from injected project data.
            matched = ["identity"]

        # Identity vs kio disambiguation
        if "identity" in matched and "kio" in matched:
            if any(kw in low for kw in ("yourself", "your self")):
                matched.remove("identity")
            else:
                matched.remove("kio")

        # Always include identity as background context
        if "identity" not in matched:
            matched.append("identity")

        # Load evidence (cached)
        all_evidence = self._get_evidence()

        # Filter to relevant categories. Only include 'project' when the user
        # is actually asking about projects/work — NOT for emotional queries,
        # boredom, social messages, or general conversation. Injecting project
        # data into every query causes the LLM to recommend projects for
        # "I'm bored", "I'm tired", etc. — the LLM should reason from the
        # user's actual intent, not from injected project context.
        relevant_cats = set(matched)
        if "project" in matched:
            relevant_cats.add("project")
        candidates = [ev for ev in all_evidence if ev.category in relevant_cats]

        # Score and sort
        for ev in candidates:
            ev.salience = _score_salience(ev, query_kw, now)
        candidates.sort(key=lambda e: -e.salience)

        # Tiered output
        primary = candidates[:5]
        context = candidates[5:max_items]

        parts: List[str] = []

        # Route-specific special handling (project DB, etc.)
        if "project" in matched:
            proj_text = self._format_projects(low)
            if proj_text:
                parts.append(proj_text)

        if primary:
            parts.append("Primary evidence (most relevant):")
            for ev in primary:
                parts.append(f"  [{ev.category}] {ev.text[:150]}")

        if context:
            parts.append("Additional context:")
            for ev in context:
                parts.append(f"  [{ev.category}] {ev.text[:120]}")

        # Identity background
        if "identity" in matched and not any(ev.category == "identity" for ev in primary):
            parts.append(self._format_identity())

        return "\n".join(parts) if parts else ""

    def _get_evidence(self) -> List[Evidence]:
        """Load evidence from graph with short TTL cache."""
        import time
        now = time.time()
        if self._cache and (now - self._cache[0]) < self._CACHE_TTL:
            return self._cache[1]
        try:
            evidence = _evidence_from_graph(self._graph)
            self._cache = (now, evidence)
        except Exception as exc:
            logger.warning("[INTELLIV2] Evidence load failed: %s", exc)
            evidence = self._cache[1] if self._cache else []
        return evidence

    def _invalidate_cache(self):
        self._cache = None

    def _format_projects(self, low: str) -> str:
        """Format active projects from graph."""
        try:
            projects = self._graph.active_projects()
        except Exception:
            return ""
        if not projects:
            return ""

        lines = []
        for p in projects[:5]:
            meta = p.meta or {}
            lc = meta.get("lifecycle", "mentioned")
            obj = meta.get("objective", "")
            line = f"{p.name} ({lc})"
            if obj:
                line += f": {obj[:80]}"
            lines.append(line)

        # Show historical if user asks about past/dropped
        show_hist = any(kw in low for kw in (
            "before", "earlier", "old", "past", "abandon",
            "drop", "stopped", "quit", "used to"))
        if show_hist:
            all_projs = self._graph.all_projects()
            for p in all_projs:
                meta = p.meta or {}
                lc = meta.get("lifecycle", "mentioned")
                if lc in ("abandoned", "completed"):
                    lines.append(f"  [historical] {p.name} ({lc})")

        return "Projects: " + "; ".join(lines[:8]) + "."

    def _format_identity(self) -> str:
        """Format identity background from living model."""
        try:
            from mini_kio.memory.living_model import living_model
            model = living_model(self.session_id)
            edu = model.get("education", [])
            if edu:
                return "About Joel: " + "; ".join(
                    e["text"] for e in edu[:4]) + "."
        except Exception:
            pass
        return ""

    # ═══════════════════════════════════════════════════════════════════════
    # 2. TEMPORAL REASONING
    # ═══════════════════════════════════════════════════════════════════════

    def trajectory(self, category: str) -> Dict[str, Any]:
        """Compute trend direction for evidence in a category.

        Groups evidence by month, fits a linear trend.
        Returns: {direction: 'increasing'|'decreasing'|'stable',
                  slope: float, months: int, sample_count: int}
        """
        evidence = self._get_evidence()
        cat_evidence = [ev for ev in evidence if ev.category == category]

        if len(cat_evidence) < 3:
            return {"direction": "insufficient_data", "slope": 0.0,
                    "months": 0, "sample_count": len(cat_evidence)}

        # Group by month
        monthly: Dict[str, int] = defaultdict(int)
        for ev in cat_evidence:
            ts = _parse_timestamp(ev.timestamp)
            if ts:
                month_key = ts.strftime("%Y-%m")
                monthly[month_key] += 1

        if len(monthly) < 2:
            return {"direction": "insufficient_data", "slope": 0.0,
                    "months": len(monthly), "sample_count": len(cat_evidence)}

        # Sort months and compute linear regression
        sorted_months = sorted(monthly.keys())
        counts = [monthly[m] for m in sorted_months]
        n = len(counts)
        x_vals = list(range(n))
        x_mean = sum(x_vals) / n
        y_mean = sum(counts) / n

        num = sum((x - x_mean) * (y - y_mean) for x, y in zip(x_vals, counts))
        den = sum((x - x_mean) ** 2 for x in x_vals)
        slope = num / den if den > 0 else 0.0

        # Determine direction
        if slope > 0.15:
            direction = "increasing"
        elif slope < -0.15:
            direction = "decreasing"
        else:
            direction = "stable"

        return {
            "direction": direction,
            "slope": round(slope, 3),
            "months": n,
            "sample_count": len(cat_evidence),
            "first_month": sorted_months[0],
            "last_month": sorted_months[-1],
        }

    # ═══════════════════════════════════════════════════════════════════════
    # 3. FEEDBACK LOOP
    # ═══════════════════════════════════════════════════════════════════════

    def record(self, user_text: str, kio_reply: str, timestamp: str = "") -> Optional[Dict[str, Any]]:
        """Record a live interaction and detect feedback signals.

        Detects: corrections, approvals, frustration.
        Persists to graph with provenance 'live:*'.
        Returns the detected feedback type (or None).
        """
        if not user_text:
            return None

        ts = timestamp or _now_iso()
        low = user_text.lower()

        feedback = self._detect_feedback(low)
        if not feedback:
            return None

        # Persist the interaction
        feedback_provenance = f"live:{feedback['type']},{ts}"

        self._graph.ensure_node(
            kind="live_interaction",
            name=user_text[:200],
            description=f"Live {feedback['type']}: {user_text[:200]}",
            meta={
                "feedback_type": feedback["type"],
                "user_text": user_text[:500],
                "kio_reply": (kio_reply or "")[:500],
                "timestamp": ts,
                "confidence": feedback["confidence"],
                "signals": feedback["signals"],
            },
        )

        self._graph.record_statement(
            USER_KEY,
            user_text[:200],
            stance=feedback["stance"],
            confidence=feedback["confidence"],
            provenance=feedback_provenance,
        )

        # Link emotional episodes to active project
        if feedback["type"] in ("frustration", "excitement"):
            self._link_to_active_project(user_text[:200], feedback["type"], ts)

        # Link corrections to preceding KIO claim
        if feedback["type"] == "correction":
            self._link_correction_to_claim(user_text[:200], ts)

        self._invalidate_cache()
        return feedback

    def _detect_feedback(self, low: str) -> Optional[Dict[str, Any]]:
        """Detect feedback signals in user text."""
        # Correction detection
        if _CORRECTION_RE.search(low):
            signals = _CORRECTION_RE.findall(low)
            return {
                "type": "correction",
                "stance": "assertion",
                "confidence": min(0.95, 0.6 + 0.1 * len(signals)),
                "signals": signals[:5],
            }

        # Approval detection
        if _APPROVAL_RE.search(low) and len(low) < 150:
            # Must be short and directed at KIO
            has_address = any(kw in low for kw in ("you", "kio", "this works", "it works"))
            if has_address:
                signals = _APPROVAL_RE.findall(low)
                return {
                    "type": "approval",
                    "stance": "assertion",
                    "confidence": min(0.9, 0.5 + 0.1 * len(signals)),
                    "signals": signals[:5],
                }

        # Frustration detection
        if _FRUSTRATION_RE.search(low):
            signals = _FRUSTRATION_RE.findall(low)
            intensity = "high" if len(signals) >= 3 else "medium" if len(signals) >= 2 else "low"
            return {
                "type": "frustration",
                "stance": "observation",
                "confidence": min(0.9, 0.5 + 0.15 * len(signals)),
                "signals": signals[:5],
                "intensity": intensity,
            }

        return None

    def _link_to_active_project(self, text: str, emotion_type: str, timestamp: str):
        """Link an emotional episode to the currently active project."""
        try:
            active = self._graph.active_projects()
            if not active:
                return
            project = active[0]  # most recently active
            self._graph.record_statement(
                USER_KEY,
                f"{emotion_type} about {project.name}: {text[:100]}",
                about_key=project.key,
                stance="observation",
                confidence=0.7,
                provenance=f"{PROVENANCE}:emotion_link",
                supersede_prior=False,
            )
        except Exception as exc:
            logger.debug("[INTELLIV2] Failed to link emotion to project: %s", exc)

    def _link_correction_to_claim(self, correction_text: str, timestamp: str):
        """Link a correction to the most recent KIO claim it addresses."""
        try:
            # Find the most recent KIO statement
            links = self._graph.attributed_statements(
                KIO_KEY, relation="said", active_only=True, limit=10,
            )
            if not links:
                return
            # Link correction to most recent KIO claim
            self._graph.add_link(
                USER_KEY, links[0].target_key, "relates_to",
                attributed_to=USER_KEY, stance="observation",
                confidence=0.6, provenance=f"{PROVENANCE}:correction_link",
            )
        except Exception as exc:
            logger.debug("[INTELLIV2] Failed to link correction: %s", exc)

    # ═══════════════════════════════════════════════════════════════════════
    # 4. ENTITY RELATIONSHIPS (exposed for external use)
    # ═══════════════════════════════════════════════════════════════════════

    def link_emotion_to_project(self, emotion_text: str, project_name: str,
                                 emotion_type: str = "emotion"):
        """Explicitly link an emotional episode to a named project."""
        try:
            project = self._graph.ensure_project(project_name)
            self._graph.record_statement(
                USER_KEY,
                f"{emotion_type}: {emotion_text[:150]}",
                about_key=project.key,
                stance="observation",
                confidence=0.7,
                provenance=f"{PROVENANCE}:emotion_link",
                supersede_prior=False,
            )
            self._invalidate_cache()
        except Exception as exc:
            logger.warning("[INTELLIV2] Failed to link emotion to project: %s", exc)

    def link_correction_to_claim(self, correction_text: str, claim_key: str):
        """Explicitly link a correction to a specific KIO claim."""
        try:
            self._graph.add_link(
                USER_KEY, claim_key, "relates_to",
                attributed_to=USER_KEY, stance="observation",
                confidence=0.7,
                provenance=f"{PROVENANCE}:correction_link",
            )
            self._invalidate_cache()
        except Exception as exc:
            logger.warning("[INTELLIV2] Failed to link correction: %s", exc)
