"""
living_model.py — the LIVING USER MODEL: a projection over the canonical
semantic graph, NOT a store.

Answers the questions "who is the user NOW", "what are they building NOW",
"what changed", "what is historical" from evidence (claims + project
lifecycle nodes + temporal metadata + provenance + confidence). Every
projected item carries: text, when (event_time), provenance, confidence
class (explicit | repeated | strong_inference | weak_inference), state
(active | historical).

Current facts (founder-canonical) are seeded ONCE into the graph as
user-attributed claims (provenance="founder-canonical", event_time=now,
confidence=1.0) so they survive restarts, are queryable, correctable and
forgettable like any other memory — and older export material can never
override them (they are the newest, highest-confidence evidence).

selective personal-context injection: personal_context_for(session, text)
returns ONLY the subset relevant to the current turn (identity + education
always, plus matching projects/preferences/goals when the turn references
them), so KIO gets MORE personalization with LESS context noise.
"""

from __future__ import annotations

import logging
import re
from datetime import datetime, timedelta, timezone
from typing import Any, Dict, List, Optional

from mini_kio.semantic.graph import SemanticGraph, USER_KEY

logger = logging.getLogger(__name__)

# ── founder-canonical CURRENT facts (explicitly established; not derived) ──
CURRENT_FACTS = [
    ("engineering student", "education"),
    ("at SCMS college of engineering", "education"),
    ("in semester 3", "education"),
    ("CGPA 8.13", "education"),
]

_PROVENANCE_CANON = "founder-canonical"

_JUNK_START = ("rule:", "wants: to ask", "plans to: do it", "wants: ask you")
_ACTIVE_LIFECYCLE = ("active", "building", "planning", "researching", "paused")
_HISTORICAL_LIFECYCLE = ("completed", "abandoned")
# casual mentions are NEVER active projects: they stay addressable for
# reference resolution but never surface as current work.
_MENTIONED_LIFECYCLE = ("mentioned", "interested")


def seed_current_facts(session_id: str) -> int:
    """Write the canonical current facts once (idempotent by provenance)."""
    if not session_id:
        return 0
    try:
        graph = SemanticGraph(session_id)
    except Exception:
        return 0
    seeded = 0
    now = datetime.now(timezone.utc).isoformat(timespec="seconds")
    existing = {s.target_name.strip().lower()
                for s in graph.attributed_statements(USER_KEY, active_only=True, limit=400)}
    for text, _cat in CURRENT_FACTS:
        claim = f"current: {text}"
        if claim.lower() in existing:
            continue
        try:
            link = graph.record_statement(
                USER_KEY, claim, relation="said", stance="assertion",
                confidence=1.0, event_time=now,
                supersede_prior=False, provenance=_PROVENANCE_CANON,
            )
            if link:
                seeded += 1
        except Exception:
            continue
    return seeded


def _conf_class(conf: float, provenance: str) -> str:
    if provenance == _PROVENANCE_CANON or conf >= 0.9:
        return "explicit"
    if conf >= 0.7:
        return "repeated"
    if conf >= 0.55:
        return "strong_inference"
    return "weak_inference"


def _when(event_time: Optional[str]) -> str:
    if not event_time:
        return ""
    try:
        return event_time[:10]
    except Exception:
        return ""


def _clean(claim: str) -> str:
    for prefix in ("wants: ", "decided: ", "plans to: ", "prefers: ", "current: "):
        if claim.startswith(prefix):
            return claim[len(prefix):].strip()
    return claim


def _is_junk(claim: str) -> bool:
    low = claim.lower().strip()
    # Strip known prefixes for content check (wants: , decided: etc. are not part of the content)
    _content = low
    for _pfx in ("wants: ", "decided: ", "plans to: ", "prefers: ", "current: "):
        if _content.startswith(_pfx):
            _content = _content[len(_pfx):].strip()
            break
    if any(low.startswith(j) for j in _JUNK_START):
        return True
    if any(_content.startswith(j) for j in _JUNK_START):
        return True
    # Ponytail: filter decomposer fragments that start with prepositions / malformed OCR
    if _content.startswith(("for ", "in ", "on ", "at ", "to ", "the ", "a ", "an ", "and ", "but ", "or ", "so ", "if ", "when ", "with ")):
        if len(_content.split()) >= 3 and not _content.startswith("for me"):
            return True
    # Also check raw low for those prefixes (covers non-wants cases)
    if low.startswith(("for ", "in ", "on ", "at ", "to ", "the ", "a ", "an ", "and ", "but ", "or ", "so ", "if ", "when ", "with ")):
        if len(low.split()) >= 3 and not low.startswith("for me"):
            return True
    # Malformed OCR / prompt fragments that polluted graph
    if any(x in low for x in ("pro pt", "youtubr", "whtever", "puase", "a pro pt")):
        return True
    if any(x in _content for x in ("pro pt", "youtubr", "whtever", "puase", "a pro pt")):
        return True
    # Drop/abandon signals are not current goals — they supersede
    if _content.startswith("drop ") or _content.startswith("abandon ") or "drop the whole" in low or "drop the whole" in _content:
        return True
    words = [w for w in low.split() if re.search(r"[a-z0-9]", w)]
    return len(words) <= 2 and all(w in ("do", "it", "that", "this", "later",
                                         "now", "tmrw", "tomorrow", "today") for w in words)


def _user_claims(session_id: str, limit: int = 3000):
    graph = SemanticGraph(session_id)
    return graph.attributed_statements(USER_KEY, active_only=True, limit=limit)


def _projects(session_id: str) -> List[Dict]:
    try:
        graph = SemanticGraph(session_id)
    except Exception:
        return []
    out = []
    for n in graph.all_projects():
        # Ponytail: filter malformed project nodes that are decomposer fragments
        low_name = (n.name or "").lower().strip()
        if low_name.startswith(("drop ", "dropping ", "for the ", "for a ", "a pro pt")):
            continue
        if any(x in low_name for x in ("pro pt", "youtubr", "whtever", "puase")):
            continue
        if len(low_name.split()) <= 2 and low_name in ("aura", "planner"):
            # single-word fragments like "aura" alone are not projects
            continue
        meta = n.meta or {}
        lc = meta.get("lifecycle") or "mentioned"
        if lc in _HISTORICAL_LIFECYCLE:
            state = "historical"
        elif lc in _MENTIONED_LIFECYCLE:
            state = "mentioned"
        else:
            state = "active"
        out.append({
            "name": n.name,
            "lifecycle": lc,
            "last_activity": (meta.get("last_activity") or "")[:10],
            "created": (meta.get("created_at") or "")[:10],
            "confidence": float(meta.get("confidence", 0.5) or 0.5),
            "state": state,
            "history": list(meta.get("status_history") or [])[-4:],
        })
    return out


def living_model(session_id: str) -> Dict[str, List[Dict]]:
    """The living user model projection. Every item: {text, when, confidence,
    provenance, state}."""
    model: Dict[str, List[Dict]] = {
        "identity": [], "education": [], "projects": [], "interests": [],
        "skills": [], "skills_in_development": [], "priorities": [],
        "goals": [], "decisions": [], "preferences": [],
        "challenges": [], "recently_changed": [], "commitments": [],
    }
    if not session_id:
        return model
    try:
        claims = _user_claims(session_id)
        projects = _projects(session_id)
    except Exception:
        return model

    now_ts = datetime.now(timezone.utc).timestamp()

    # Dedup tracker: cleaned text -> True (prevents duplicate entries)
    _seen: Dict[str, bool] = {}

    def _add(cat: str, claim: str, link) -> None:
        if _is_junk(claim):
            return
        cleaned = _clean(claim)
        dedup_key = f"{cat}:{cleaned.lower()}"
        if dedup_key in _seen:
            return
        _seen[dedup_key] = True
        conf = float(getattr(link, "confidence", 0) or 0.5)
        prov = getattr(link, "provenance", "") or ""
        et = getattr(link, "event_time", None)
        when = _when(et)
        ts = 0.0
        if et:
            try:
                dt = datetime.fromisoformat(str(et))
                if dt.tzinfo is None:
                    dt = dt.replace(tzinfo=timezone.utc)
                ts = dt.timestamp()
            except Exception:
                pass
        # Ponytail: currentness via evidence, not 90-day blind window. Use 30 days for non-canon.
        if prov == _PROVENANCE_CANON or ts >= now_ts - 30 * 86400:
            state = "active"
        elif ts and ts < now_ts - 30 * 86400:
            state = "historical"
        else:
            state = "active"
        model[cat].append({
            "text": cleaned, "when": when,
            "confidence": _conf_class(conf, prov),
            "provenance": prov, "state": state,
        })

    for link in claims:
        claim = str(getattr(link, "target_name", "") or "").strip()
        rel = (getattr(link, "relation", "") or "said") or "said"
        low = claim.lower()
        if low.startswith("current:"):
            _add("education", claim, link)
            continue
        if rel == "prefers":
            _add("preferences", claim, link)
        elif rel == "decides":
            _add("decisions", claim, link)
        elif rel == "wants":
            if low.startswith("researching:"):
                _add("interests", claim, link)
            else:
                _add("goals", claim, link)

    # projects (lifecycle is the primary current/historical signal)
    # Supersession: if user decided to drop/abandon a project, mark it historical even if lifecycle still active
    _drop_claims = [c["text"].lower() for c in model["decisions"] + model["goals"] if "drop" in c["text"].lower() or "abandon" in c["text"].lower()]
    for pr in projects:
        # Check if any drop claim mentions this project
        _is_dropped = False
        _pr_low = pr['name'].lower()
        for dc in _drop_claims:
            # If drop claim contains project name tokens or vice versa
            if _pr_low in dc or any(tok in dc for tok in _pr_low.split() if len(tok) >= 4):
                _is_dropped = True
                break
        _state = pr["state"]
        if _is_dropped and _state == "active":
            _state = "historical"
        model["projects"].append({
            "text": f"{pr['name']} ({pr['lifecycle']})",
            "when": pr["last_activity"],
            "confidence": _conf_class(pr["confidence"], ""),
            "provenance": "project-lifecycle",
            "state": _state,
        })

    # recently_changed: recent claims + recent project transitions
    recent_claims = [c for c in model["goals"] + model["decisions"]
                     + model["preferences"] + model["interests"]
                     if c["when"] and c["when"] >= (datetime.now(timezone.utc) - timedelta(days=30)).strftime("%Y-%m-%d")]
    for rc in recent_claims[:8]:
        model["recently_changed"].append(rc)
    for pr in projects:
        for h in (pr.get("history") or []):
            at = (h.get("at") or "")[:10]
            if at and at >= (datetime.now(timezone.utc) - timedelta(days=30)).strftime("%Y-%m-%d"):
                model["recently_changed"].append({
                    "text": f"{pr['name']}: {h.get('from')} → {h.get('to')}",
                    "when": at, "confidence": "explicit",
                    "provenance": "project-lifecycle", "state": "active",
                })
    return model


# ── selective personal context (per-turn injection) ─────────────────────────
_PROJECT_REF_RE = re.compile(
    r"\b(?:my|the|that|this|our)\s+(?:current\s+|active\s+|old\s+|new\s+|"
    r"main\s+|main\s+)?(?:project|prototype|build|app|thing\s+(?:i'?m|i\s+am)\s+building"
    r"|thing\s+(?:i'?m|i\s+am)\s+working\s+on)\b",
    re.I,
)


def _named_project_in(text: str, projects: List[Dict]) -> Optional[Dict]:
    low = text.lower()
    toks = set(re.findall(r"[a-z0-9]+", low))
    toks = {t for t in toks if len(t) >= 4}
    best = None
    for pr in projects:
        pname_raw = pr.get("name") or pr.get("text") or ""
        pname_raw = re.sub(r"\s*\([^)]*\)\s*$", "", pname_raw)  # strip " (lifecycle)"
        pname = re.sub(r"[^a-z0-9]+", "", pname_raw.lower())
        if pname and (pname in re.sub(r"[^a-z0-9]+", "", low) or len(pname) <= 40):
            ptoks = set(re.findall(r"[a-z0-9]+", pname_raw.lower()))
            if toks & ptoks:
                if best is None or len(ptoks & toks) > len(
                        set(re.findall(r"[a-z0-9]+", best.get("name") or best.get("text") or "")) & toks):
                    best = pr
    return best


def personal_context_for(session_id: str, user_text: str, *,
                         max_lines: int = 9) -> str:
    """Relevance-ranked personal context for the CURRENT turn. Identity +
    education always (compact); matching project when the turn references a
    project; relevant preferences/goals only when the turn is about them.
    Historical context is included ONLY when explicitly asked. Returns ""
    when nothing applies."""
    if not session_id:
        return ""
    model = living_model(session_id)
    lines: List[str] = []

    identity = []
    for e in model.get("education", []):
        identity.append(e["text"])
    if identity:
        lines.append("About you (current): " + "; ".join(identity[:4]) + ".")

    low = (user_text or "").lower()
    projects = model.get("projects", [])
    active = [p for p in projects if p["state"] == "active" and (p.get("text") or "").strip()]
    matched = _named_project_in(user_text or "", active) or (
        _named_project_in(user_text or "", projects) if _PROJECT_REF_RE.search(low) else None)
    if matched is None:
        # a NAMED mention ("that ceramic heat exchanger") is itself a
        # reference — search ALL projects (incl. mentioned/historical) so
        # a casual mention stays addressable without ever becoming current.
        matched = _named_project_in(user_text or "", projects)

    ask_current = bool(re.search(r"\b(?:working\s+on|building|projects|doing|"
                                 r"priorities|focused|up\s+to|currently)\b", low))

    if matched:
        label = "Mentioned project" if matched.get("state") == "mentioned" else \
                ("Past project" if matched.get("state") == "historical" else "Active project")
        lines.append(f"{label}: {matched['text']}"
                     + (f" (last activity {matched['when']})" if matched.get("when") else "")
                     + ".")
    elif ask_current and active:
        top = active[:3]
        lines.append("Current projects: " + "; ".join(f"{p['text']}" for p in top) + ".")

    if re.search(r"\b(prefer|like|hate|enjoy|taste|style)\b", low):
        prefs = model.get("preferences", [])[:3]
        if prefs:
            lines.append("Stated preferences: " + "; ".join(p["text"] for p in prefs) + ".")

    if re.search(r"\b(goal|plan|want|trying|priorit)\b", low):
        goals = [g for g in model.get("goals", []) if g["state"] == "active"][:3]
        if goals:
            lines.append("Active goals: " + "; ".join(g["text"] for g in goals) + ".")

    if re.search(r"\b(history|before|earlier|old|used\s+to|past|abandoned|stopped)\b", low):
        hist = [p for p in projects if p["state"] == "historical"][:3]
        old = model.get("goals", []) + model.get("preferences", [])
        old_h = [o for o in old if o["state"] == "historical"][:3]
        parts = [f"{p['text']}" for p in hist] + [o["text"] for o in old_h]
        if parts:
            lines.append("Historical (from earlier): " + "; ".join(parts[:4]) + " — "
                         "treat as past unless the user says otherwise.")

    if len(lines) > max_lines:
        lines = lines[:max_lines]
    if not lines:
        return ""
    return "Personal context:\n" + "\n".join(lines)


def personal_brief(session_id: str, *, max_items: int = 30) -> str:
    """Compact evidence brief for LLM composition (natural profile answers).
    Current-first, historical last, confidence classes explicit."""
    model = living_model(session_id)
    parts: List[str] = []
    order = ["education", "projects", "priorities", "goals", "decisions",
             "preferences", "interests", "recently_changed"]
    for cat in order:
        items = model.get(cat, [])[:6]
        if not items:
            continue
        label = cat.replace("_", " ").title()
        rows = []
        for it in items:
            suffix = ""
            if it["state"] == "historical":
                suffix = " [HISTORICAL]"
            if it["confidence"] in ("strong_inference", "weak_inference"):
                suffix += f" [{it['confidence']}]"
            when = f" ({it['when']})" if it.get("when") else ""
            rows.append(f"- {it['text']}{when}{suffix}")
        parts.append(f"{label}:\n" + "\n".join(rows))
    return "\n\n".join(parts) if parts else ""


# ── intelligent query dimensions ───────────────────────────────────────────
# For "what do you know about me?" / "what am I good at?" / "what are my
# strengths?" — each returns evidence-backed items for a specific dimension.
# The LLM composes these into a natural answer; these are DATA, not answers.

def _collect_items(model: Dict[str, List[Dict]], *cats: str,
                   state_filter: str = "active") -> List[Dict]:
    """Gather items from specified categories, optionally filtered by state."""
    out = []
    for cat in cats:
        for it in model.get(cat, []):
            if state_filter and it.get("state") != state_filter:
                continue
            out.append({"category": cat, **it})
    return out


def query_education(session_id: str) -> List[Dict]:
    """Current academic identity."""
    model = living_model(session_id)
    return _collect_items(model, "education")


def query_projects(session_id: str, state: str = "") -> List[Dict]:
    """Projects filtered by state (active/historical/mentioned) or all."""
    model = living_model(session_id)
    if state:
        return _collect_items(model, "projects", state_filter=state)
    return _collect_items(model, "projects", state_filter="")


def query_strengths(session_id: str) -> List[Dict]:
    """Evidence-backed strengths: infer from repeated patterns, skills,
    successful decisions, and high-confidence items — NOT raw goals.
    Goals are what someone WANTS; strengths are what someone IS GOOD AT."""
    model = living_model(session_id)
    out: List[Dict] = []
    # Direct skills (explicit or inferred)
    for it in model.get("skills", []):
        out.append({"category": "skills", **it})
    for it in model.get("skills_in_development", []):
        out.append({"category": "skills_in_development", **it})
    # Repeated preferences can indicate strengths in taste/judgment
    repeated_prefs = [p for p in model.get("preferences", [])
                      if p.get("confidence") in ("explicit", "repeated")]
    for it in repeated_prefs[:3]:
        out.append({"category": "preferences_as_strength", **it})
    # Decisions with explicit confidence suggest decision-making ability
    explicit_decs = [d for d in model.get("decisions", [])
                     if d.get("confidence") in ("explicit", "repeated")]
    for it in explicit_decs[:3]:
        out.append({"category": "decisions", **it})
    # Interests with high confidence suggest engaged curiosity
    strong_interests = [i for i in model.get("interests", [])
                        if i.get("confidence") in ("explicit", "repeated")]
    for it in strong_interests[:3]:
        out.append({"category": "interests", **it})
    # Do NOT include raw goals — those are aspirations, not strengths
    return out


def query_preferences(session_id: str) -> List[Dict]:
    """Stated preferences and likes."""
    model = living_model(session_id)
    return _collect_items(model, "preferences")


def query_goals(session_id: str, state: str = "active") -> List[Dict]:
    """Goals filtered by state, with quality filtering to exclude fragments
    and low-quality extract artifacts."""
    model = living_model(session_id)
    raw = _collect_items(model, "goals", "priorities", state_filter=state)
    # Quality filter: exclude fragments, preposition-starts, and junk
    out = []
    for it in raw:
        text = (it.get("text") or "").strip()
        low = text.lower()
        # Skip very short fragments
        if len(text) < 10:
            continue
        # Skip fragments starting with prepositions/conjunctions (incomplete extractions)
        if low.startswith(("for ", "in ", "on ", "at ", "to ", "the ", "a ", "an ",
                          "and ", "but ", "or ", "so ", "if ", "when ", "with ")):
            continue
        # Skip chatgpt_export junk patterns
        if low.startswith(("rule:", "wants: to ask", "plans to: do it")):
            continue
        out.append(it)
    # Cap at reasonable number per query
    return out[:15]


def query_decisions(session_id: str) -> List[Dict]:
    """Recorded decisions."""
    model = living_model(session_id)
    return _collect_items(model, "decisions")


def query_interests(session_id: str) -> List[Dict]:
    """Technical interests and research areas."""
    model = living_model(session_id)
    return _collect_items(model, "interests")


def query_recent_changes(session_id: str) -> List[Dict]:
    """What changed recently."""
    model = living_model(session_id)
    return _collect_items(model, "recently_changed")


def query_waiting(session_id: str) -> List[Dict]:
    """Waiting-on items: claims that mention waiting, pending, or blocked."""
    model = living_model(session_id)
    out: List[Dict] = []
    # Scan all claim categories for waiting-on signals
    for cat in ("goals", "decisions", "commitments", "projects"):
        for it in model.get(cat, []):
            text = (it.get("text") or "").lower()
            if any(kw in text for kw in ("waiting", "pending", "blocked", "deferred",
                                          "waiting on", "waiting for")):
                out.append({"category": cat, **it})
    # Also scan raw user claims for 'waiting on' pattern (decomposer format)
    try:
        claims = _user_claims(session_id, limit=200)
        for link in claims:
            target = str(getattr(link, "target_name", "") or "").strip()
            low = target.lower()
            if "waiting" in low and ("on" in low or "for" in low):
                # Check not already captured
                if not any(o["text"] == target for o in out):
                    out.append({
                        "category": "waiting_claim", "text": _clean(target),
                        "when": _when(getattr(link, "event_time", None)),
                        "confidence": "explicit",
                        "provenance": getattr(link, "provenance", ""),
                        "state": "active",
                    })
    except Exception:
        pass
    return out


def query_avoiding(session_id: str) -> List[Dict]:
    """Items the user seems to be avoiding or procrastinating on.
    Inferred from rejections, abandoned goals, and explicit statements."""
    model = living_model(session_id)
    out: List[Dict] = []
    # Historical goals that were abandoned but not explicitly forgotten
    for it in model.get("goals", []):
        if it.get("state") == "historical" and it.get("provenance", "").startswith("decomposer"):
            text = (it.get("text") or "").lower()
            if any(kw in text for kw in ("drop", "abandon", "gave up", "quit", "stop")):
                out.append({"category": "abandoned_goals", **it})
    # Decisions that involved rejection
    for it in model.get("decisions", []):
        text = (it.get("text") or "").lower()
        if any(kw in text for kw in ("drop", "reject", "abandon")):
            out.append({"category": "rejections", **it})
    # Scan raw claims for 'forget' / 'over it' signals
    try:
        claims = _user_claims(session_id, limit=200)
        for link in claims:
            target = str(getattr(link, "target_name", "") or "").strip()
            low = target.lower()
            if any(kw in low for kw in ("forget", "over it", "gave up", "abandoned", "dropped")):
                if not any(o["text"] == _clean(target) for o in out):
                    out.append({
                        "category": "forget_claim", "text": _clean(target),
                        "when": _when(getattr(link, "event_time", None)),
                        "confidence": "explicit",
                        "provenance": getattr(link, "provenance", ""),
                        "state": "active",
                    })
    except Exception:
        pass
    return out


def query_patterns(session_id: str) -> List[Dict]:
    """Observed patterns: repeated themes, recurring decisions, and
    behavioral signals from the evidence. Not fabricated — only surfaced
    when multiple evidence points support the same pattern."""
    model = living_model(session_id)
    out: List[Dict] = []
    # Repeated topics in goals (same theme multiple times)
    goal_texts = [g.get("text", "") for g in model.get("goals", []) if g.get("state") == "active"]
    # Count theme clusters (very basic: look for shared significant words)
    word_goals: Dict[str, List[str]] = {}
    for gt in goal_texts:
        words = set(w for w in re.findall(r"[a-z]{4,}", gt.lower())
                    if w not in ("that", "this", "with", "from", "have", "been", "will", "would", "could", "should", "about"))
        for w in words:
            word_goals.setdefault(w, []).append(gt)
    # Themes with 3+ goals suggest a recurring interest
    for word, goals in sorted(word_goals.items(), key=lambda x: -len(x[1])):
        if len(goals) >= 3:
            out.append({
                "category": "recurring_theme",
                "text": f"Recurring theme: '{word}' appears in {len(goals)} stated goals",
                "confidence": "strong_inference",
                "state": "active",
                "when": "",
                "provenance": "pattern-inference",
            })
    # Decision-making pattern: if user has made multiple explicit decisions
    decisions = [d for d in model.get("decisions", []) if d.get("state") == "active"]
    if len(decisions) >= 2:
        out.append({
            "category": "decision_pattern",
            "text": f"Has made {len(decisions)} explicit recorded decisions",
            "confidence": "explicit",
            "state": "active",
            "when": "",
            "provenance": "pattern-inference",
        })
    return out


def synthesize_about_user(session_id: str) -> str:
    """Natural synthesis for 'what do you know about me?' — not a raw dump.
    Returns structured evidence the LLM can compose naturally.
    Only surfaces categories with meaningful, non-junk items."""
    model = living_model(session_id)
    parts: List[str] = []

    # Current identity (always strongest signal)
    edu = _collect_items(model, "education")
    if edu:
        parts.append("Current identity: " + "; ".join(e["text"] for e in edu[:4]) + ".")

    # Active projects
    active_pr = [p for p in _collect_items(model, "projects") if p.get("state") == "active"]
    if active_pr:
        parts.append("Active projects: " + "; ".join(p["text"] for p in active_pr[:3]) + ".")

    # Goals — only high-confidence active goals, excluding fragments
    goals = [g for g in _collect_items(model, "goals", "priorities")
             if g.get("state") == "active"
             and g.get("confidence") in ("explicit", "repeated")
             and len(g.get("text", "")) > 8]
    if goals:
        parts.append("Current goals: " + "; ".join(g["text"] for g in goals[:3]) + ".")

    # Preferences — only explicit/repeated
    prefs = [p for p in _collect_items(model, "preferences")
             if p.get("confidence") in ("explicit", "repeated")]
    if prefs:
        parts.append("Stated preferences: " + "; ".join(p["text"] for p in prefs[:3]) + ".")

    # Interests — only explicit/repeated
    interests = [i for i in _collect_items(model, "interests")
                 if i.get("confidence") in ("explicit", "repeated")]
    if interests:
        parts.append("Interests: " + "; ".join(i["text"] for i in interests[:3]) + ".")

    # Decisions — only explicit
    decisions = [d for d in _collect_items(model, "decisions")
                 if d.get("confidence") in ("explicit", "repeated")
                 and len(d.get("text", "")) > 8]
    if decisions:
        parts.append("Recent decisions: " + "; ".join(d["text"] for d in decisions[:3]) + ".")

    # Historical (only if explicitly relevant)
    hist_pr = [p for p in _collect_items(model, "projects") if p.get("state") == "historical"]
    if hist_pr:
        parts.append("Previous projects: " + "; ".join(p["text"] for p in hist_pr[:3]) + " [historical].")

    # Historical goals (from chatgpt_export, older than 6 months)
    hist_goals = [g for g in _collect_items(model, "goals")
                  if g.get("state") == "historical"
                  and g.get("provenance", "").startswith("chatgpt_export")]
    if hist_goals:
        parts.append("Earlier interests (historical): " + "; ".join(g["text"] for g in hist_goals[:3]) + " — these are from earlier conversations, not current priorities.")

    if not parts:
        return ""
    return "Evidence-backed user model (current-first, historical-last):\n" + "\n".join(parts)


def capabilities_summary() -> str:
    """Dynamic capability awareness for system prompt injection.
    Queries actual runtime state to determine which capabilities are
    available, degraded, or running — never a static list."""
    # Base capabilities (always available unless explicitly degraded)
    base = [
        "open/close desktop apps",
        "search the web",
        "play media (YouTube, Spotify)",
        "system control (lock, shutdown, restart)",
        "file operations",
        "create documents (docx/xlsx/pptx/pdf)",
        "system status (battery, RAM, CPU, processes)",
        "time/date, arithmetic, unit conversion",
        "reminders",
        "feed watching",
        "semantic memory with living user model",
    ]
    # Dynamic capabilities (depend on runtime state)
    dynamic = []
    try:
        from mini_kio.core.runtime import get_runtime_snapshot
        snap = get_runtime_snapshot()
        if snap:
            browser_ready = bool(snap.get("browser_runtime_ready", False))
            mcp_ready = bool(snap.get("mcp_runtime_ready", False))
            if browser_ready:
                dynamic.append("browser automation (tabs, navigation, interaction)")
            else:
                dynamic.append("browser automation [disconnected — reconnect to use]")
            if mcp_ready:
                dynamic.append("MCP tools (available)")
            else:
                dynamic.append("MCP tools [not connected]")
    except Exception:
        dynamic.append("browser automation [status unknown]")
        dynamic.append("MCP tools [status unknown]")

    all_caps = base + dynamic
    return (
        "KIO capabilities: " + "; ".join(all_caps) + ". "
        "When the user asks for something KIO can do with a tool, USE THE TOOL. "
        "Never say 'I can't' when a capability exists. "
        "If a capability is listed as disconnected/unavailable, say so honestly."
    )


def recall_about_topic(session_id: str, topic: str, limit: int = 8,
                       session_context=None) -> List[Dict]:
    """Search for a specific topic across TWO sources:
    1. Graph claims (durable memory — imported/decomposed statements)
    2. Conversation exchange history (recent discussion — not yet decomposed)

    Returns matching items sorted by relevance.
    Graph claims get provenance metadata; exchange items are marked as
    'conversational' so the LLM knows these are recent discussion, not
    durable facts.

    session_context: optional SessionContext for exchange history access.
    When provided, enables fallback to recent conversation text.
    """
    if not session_id or not topic:
        return []
    topic_low = topic.lower().strip()
    # Extract significant words (min 3 chars, exclude common stop words)
    stop = {"the", "about", "what", "that", "this", "with", "from", "have",
            "were", "was", "been", "being", "does", "doing", "will",
            "would", "could", "should", "tell", "said", "asked"}
    topic_words = [w for w in re.findall(r"[a-z]{3,}", topic_low) if w not in stop]
    if not topic_words:
        return []

    # ── Source 1: Graph claims (durable memory) ──
    scored: List[tuple[float, Dict]] = []
    try:
        claims = _user_claims(session_id, limit=300)
        for link in claims:
            target = str(getattr(link, "target_name", "") or "").strip()
            if not target or len(target) < 5:
                continue
            target_low = target.lower()
            score = 0.0
            if topic_low in target_low:
                score = 1.0
            else:
                matched = sum(1 for w in topic_words if w in target_low)
                if matched > 0:
                    score = matched / len(topic_words) * 0.8
            if score <= 0:
                continue
            conf = float(getattr(link, "confidence", 0) or 0.5)
            prov = getattr(link, "provenance", "") or ""
            et = getattr(link, "event_time", None)
            when = _when(et)
            if when and when >= (datetime.now(timezone.utc) - timedelta(days=90)).strftime("%Y-%m-%d"):
                score *= 1.2
            if prov == _PROVENANCE_CANON:
                score *= 1.5
            score *= (0.5 + conf)
            scored.append((score, {
                "text": _clean(target),
                "when": when,
                "confidence": _conf_class(conf, prov),
                "provenance": prov,
                "state": "active",
                "relation": getattr(link, "relation", ""),
            }))
    except Exception:
        pass

    # ── Source 2: Conversation exchange history (recent discussion) ──
    # These are statements from recent conversation that may not yet be
    # in the graph. Critical for 'what did I just say about X?' queries.
    if session_context is not None:
        try:
            exchanges = session_context.get_history_window(30)  # wider window for recall
            for user_text, kio_reply in exchanges:
                # Search user statements
                for text_block in [user_text]:
                    if not text_block or len(text_block) < 5:
                        continue
                    text_low = text_block.lower()
                    score = 0.0
                    if topic_low in text_low:
                        score = 0.9  # slightly less than graph (not durable)
                    else:
                        matched = sum(1 for w in topic_words if w in text_low)
                        if matched > 0:
                            score = matched / len(topic_words) * 0.7
                    if score <= 0:
                        continue
                    # Truncate long statements for display
                    display = text_block[:200].strip()
                    if len(text_block) > 200:
                        display += "..."
                    scored.append((score, {
                        "text": display,
                        "when": "",
                        "confidence": "explicit",
                        "provenance": "conversation",
                        "state": "active",
                        "relation": "said",
                    }))
        except Exception:
            pass

    scored.sort(key=lambda x: -x[0])
    return [item for _, item in scored[:limit]]


def open_loops_summary(session_id: str) -> str:
    """Compact projection of open loops: waiting-on, blocked, paused,
    pending, unfinished items. Answers 'what's unfinished?' / 'what am I waiting on?'
    from actual graph evidence, not fabricated status."""
    if not session_id:
        return ""
    model = living_model(session_id)
    parts: List[str] = []

    # Waiting-on items (explicitly stated)
    waiting = query_waiting(session_id)
    if waiting:
        items = [w["text"] for w in waiting[:3]]
        # Avoid doubling 'Waiting on: ' prefix if text already contains it
        cleaned = []
        already_prefixed = False
        for item in items:
            low = item.lower().strip()
            if low.startswith("waiting on") or low.startswith("waiting for") or low.startswith("pending") or low.startswith("blocked"):
                cleaned.append(item[0].upper() + item[1:] if item else item)
                already_prefixed = True
            else:
                cleaned.append(item)
        if already_prefixed:
            parts.append("; ".join(cleaned) + ".")
        else:
            parts.append("Waiting on: " + "; ".join(cleaned) + ".")

    # Active goals (what's in progress) — apply quality filter
    _STOP = {"i", "we", "you", "a", "an", "the", "it", "to", "of", "and",
             "for", "on", "in", "is", "at", "my", "me", "be", "do",
             "so", "if", "or", "no", "go", "up", "by", "he", "us"}
    def _open_loop_ok(t: str) -> bool:
        if len(t) < 15:
            return False
        if t[-1] not in ('.', '?', '!'):
            return False
        fl = t.split()[0].lower().rstrip('.,!?') if t.split() else ''
        if fl in _STOP:
            return False
        if t.count(';') >= 2:
            return False
        return True
    active_goals = [g for g in model.get("goals", [])
                   if g.get("state") == "active"
                   and g.get("confidence") in ("explicit", "repeated")
                   and _open_loop_ok(g.get("text", ""))][:3]
    if active_goals:
        parts.append("Active: " + "; ".join(g["text"] for g in active_goals) + ".")

    # Active/failed workflows (real operational state)
    try:
        from mini_kio.execution.workflows import _get_engine
        engine = _get_engine()
        for wf in (engine.list_workflows() or [])[:5]:
            st = (wf.status.value if hasattr(wf, "status") else "") or ""
            if st in ("failed", "pending", "paused"):
                name = wf.name or wf.id or "workflow"
                if st == "failed":
                    parts.append(f"Workflow '{name}' failed.")
                elif st in ("pending", "paused"):
                    parts.append(f"Workflow '{name}' paused/pending.")
    except Exception:
        pass

    # Abandoned/paused items (what was dropped)
    abandoned = [g for g in model.get("goals", [])
                if g.get("state") == "historical"
                and g.get("provenance", "").startswith("decomposer")
                and len(g.get("text", "")) > 10][:2]
    if abandoned:
        parts.append("Previously: " + "; ".join(g["text"] for g in abandoned) + " [no longer active].")

    if not parts:
        return ""
    return "Open loops: " + " ".join(parts)


def runtime_status_summary() -> str:
    try:
        import psutil
        ram = psutil.virtual_memory()
        cpu = psutil.cpu_percent(interval=0.1)
        battery = psutil.sensors_battery()
    except Exception:
        ram = cpu = battery = None
    try:
        from mini_kio.core.runtime import get_runtime_snapshot
        snap = get_runtime_snapshot()
    except Exception:
        snap = None
    state = str((snap or {}).get('state', 'unknown'))
    health = int((snap or {}).get('health_score', 0) or 0)
    browser_ready = bool((snap or {}).get('browser_runtime_ready', False))
    parts = ['KIO: state=' + state + ', health=' + str(health) + '/100']
    if ram:
        parts.append('RAM: ' + str(ram.percent) + '% (' + str(ram.used // (1024**3)) + 'GB/' + str(ram.total // (1024**3)) + 'GB)')
    if cpu is not None:
        parts.append('CPU: ' + str(cpu) + '%')
    if battery:
        plug = 'charging' if battery.power_plugged else 'on battery'
        parts.append('Battery: ' + str(battery.percent) + '% (' + plug + ')')
    if not browser_ready:
        parts.append('Browser: disconnected')
    return ', '.join(parts)


