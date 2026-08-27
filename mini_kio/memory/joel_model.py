"""
joel_model.py — Evidence-backed Joel model synthesized from longitudinal
extraction. Answers the questions:
  - How does Joel communicate?
  - How does Joel express frustration/excitement/urgency?
  - How does Joel make decisions?
  - What does Joel repeatedly care about?
  - What has changed over time?
  - What evidence supports each conclusion?

Every claim in this model is BACKED BY EVIDENCE from the ChatGPT export.
The LLM composes these data points into natural responses. These are DATA,
not personality labels.
"""

from __future__ import annotations

import logging
from typing import Dict, List, Optional

from mini_kio.semantic.graph import SemanticGraph, USER_KEY

logger = logging.getLogger(__name__)


def _get_evidence(
    session_id: str,
    category_prefix: str,
    limit: int = 50,
) -> List[Dict[str, str]]:
    """Retrieve evidence from the semantic graph by provenance prefix."""
    graph = SemanticGraph(session_id)
    links = graph.attributed_statements(
        USER_KEY, relation="said", stance="observation",
        active_only=True, limit=200,
    )
    items: List[Dict[str, str]] = []
    for link in links:
        target = getattr(link, "target_name", "") or ""
        provenance = getattr(link, "provenance", "") or ""
        if category_prefix in provenance or target.startswith(category_prefix.split(":")[0] + ":"):
            # Extract the description from the target
            for prefix in (category_prefix.split(":")[0] + ":",):
                if target.startswith(prefix):
                    desc = target[len(prefix):].strip()
                    break
            else:
                desc = target
            items.append({
                "description": desc,
                "provenance": provenance,
                "confidence": str(getattr(link, "confidence", 0.5)),
            })
            if len(items) >= limit:
                break
    return items


def joel_communication_style(session_id: str) -> str:
    """Evidence-backed communication style for conversational injection.
    Returns structured data the LLM can compose naturally."""
    items = _get_evidence(session_id, "communication:")
    if not items:
        return ""
    lines = ["Joel's communication patterns (evidence-backed):"]
    for item in items:
        lines.append(f"- {item['description']}")
    return "\n".join(lines)


def joel_emotional_patterns(session_id: str) -> str:
    """Evidence-backed emotional expression patterns."""
    items = _get_evidence(session_id, "emotional:")
    if not items:
        return ""
    lines = ["Joel's emotional expression (evidence-backed):"]
    for item in items:
        lines.append(f"- {item['description']}")
    return "\n".join(lines)


def joel_behavioral_patterns(session_id: str) -> str:
    """Evidence-backed behavioral patterns."""
    items = _get_evidence(session_id, "behavior:")
    if not items:
        return ""
    lines = ["Joel's behavioral patterns (evidence-backed):"]
    for item in items:
        lines.append(f"- {item['description']}")
    return "\n".join(lines)


def joel_technical_interests(session_id: str) -> str:
    """Evidence-backed technical interests."""
    items = _get_evidence(session_id, "technical interest:")
    if not items:
        return ""
    interests = [item["description"] for item in items]
    return "Joel's technical interests: " + ", ".join(interests[:15]) + "."


def joel_kio_history(session_id: str) -> str:
    """Evidence-backed KIO interaction history."""
    items = _get_evidence(session_id, "kio_history:")
    if not items:
        return ""
    lines = ["Joel-KIO interaction history (evidence-backed):"]
    for item in items:
        lines.append(f"- {item['description']}")
    return "\n".join(lines)


def joel_decision_patterns(session_id: str) -> str:
    """Evidence-backed decision-making patterns."""
    items = _get_evidence(session_id, "behavior:")
    decision_items = [i for i in items if "decision" in i["description"].lower()
                      or "reversal" in i["description"].lower()
                      or "rejection" in i["description"].lower()]
    if not decision_items:
        return ""
    lines = ["Joel's decision patterns (evidence-backed):"]
    for item in decision_items:
        lines.append(f"- {item['description']}")
    return "\n".join(lines)


def joel_projects(session_id: str) -> str:
    """Evidence-backed project lifecycle."""
    from mini_kio.memory.living_model import query_projects
    projects = query_projects(session_id)
    if not projects:
        return ""
    lines = ["Joel's projects (evidence-backed):"]
    for p in projects[:10]:
        state_tag = f" [{p['state']}]" if p.get("state") != "active" else ""
        when = f" (last: {p['when']})" if p.get("when") else ""
        lines.append(f"- {p['text']}{state_tag}{when}")
    return "\n".join(lines)


def joel_full_brief(session_id: str) -> str:
    """Complete Joel model brief for conversational injection.
    Current-first, evidence-backed, structured for LLM composition."""
    parts = []

    # Communication style
    style = joel_communication_style(session_id)
    if style:
        parts.append(style)

    # Emotional patterns
    emotional = joel_emotional_patterns(session_id)
    if emotional:
        parts.append(emotional)

    # Behavioral patterns
    behavioral = joel_behavioral_patterns(session_id)
    if behavioral:
        parts.append(behavioral)

    # Technical interests
    tech = joel_technical_interests(session_id)
    if tech:
        parts.append(tech)

    # Projects
    projects = joel_projects(session_id)
    if projects:
        parts.append(projects)

    # KIO history
    kio = joel_kio_history(session_id)
    if kio:
        parts.append(kio)

    if not parts:
        return ""
    return "Joel model (evidence-backed from ChatGPT history):\n\n" + "\n\n".join(parts)


def joel_contextual_brief(
    session_id: str,
    user_text: str,
    *,
    max_lines: int = 12,
) -> str:
    """Relevance-ranked Joel context for the CURRENT turn.
    Only includes dimensions relevant to the current message.
    Identity + education always; matching patterns when relevant."""
    if not session_id:
        return ""

    low = (user_text or "").lower()
    parts = []

    # Always include identity basics
    from mini_kio.memory.living_model import living_model
    model = living_model(session_id)
    edu = model.get("education", [])
    if edu:
        parts.append("About Joel: " + "; ".join(e["text"] for e in edu[:4]) + ".")

    # Communication patterns (always useful for tone matching)
    style_items = _get_evidence(session_id, "communication:", limit=5)
    if style_items:
        parts.append("Communication: " + "; ".join(
            i["description"].replace("Uses '", "'").replace("' in casual messages", "")
            for i in style_items[:3]
        ) + ".")

    # Emotional patterns (when user seems emotional)
    if any(kw in low for kw in ("frustrat", "angry", "piss", "mad", "stuck", "broken",
                                 "excit", "hype", "amazing", "let's go", "finally",
                                 "urgent", "asap", "right now", "deadline")):
        emotional_items = _get_evidence(session_id, "emotional:", limit=3)
        if emotional_items:
            parts.append("Emotional expression: " + "; ".join(
                i["description"] for i in emotional_items
            ) + ".")

    # Projects (when user asks about projects or work)
    if any(kw in low for kw in ("project", "building", "working on", "code",
                                 "app", "website", "prototype", "develop")):
        projects = joel_projects(session_id)
        if projects:
            parts.append(projects.split("\n", 1)[-1])  # skip header

    # Technical interests (when user asks about tech)
    if any(kw in low for kw in ("python", "code", "tech", "learn", "skill",
                                 "programming", "developer", "engineering")):
        tech = joel_technical_interests(session_id)
        if tech:
            parts.append(tech)

    # KIO history (when user asks about KIO or corrections)
    if any(kw in low for kw in ("kio", "correct", "wrong", "fix", "mistake",
                                 "remember", "before", "history")):
        kio = joel_kio_history(session_id)
        if kio:
            parts.append(kio)

    # Decision patterns (when user asks about decisions)
    if any(kw in low for kw in ("decid", "chose", "picked", "change mind",
                                 "reversal", "why did i", "dropped", "abandoned")):
        decisions = joel_decision_patterns(session_id)
        if decisions:
            parts.append(decisions)

    if len(parts) > max_lines:
        parts = parts[:max_lines]
    if not parts:
        return ""
    return "Personal context (evidence-backed):\n" + "\n".join(parts)
