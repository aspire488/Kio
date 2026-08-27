"""
mini_kio/research/briefs.py — Research Briefs (canonical owner)

Gives KIO a durable research thread across sessions: 'research X' runs the
multi-source evidence chain, composes a deterministic brief (no LLM), and
persists it keyed by topic; 'research brief on X' recalls it; 'continue
research on X' re-runs and diffs new sources against the stored one. The
'what did I research' view lists every topic.

Retrieval reuses the canonical RetrievalRouter.retrieve_evidence (Exa ->
Tavily -> Jina -> Wikipedia -> OpenAlex -> DDG -> media) so a research brief
sees the same evidence hierarchy as every other KIO answer.
"""

import logging
import re
from typing import List, Dict, Optional

from mini_kio.backend.repositories.brief_repository import BriefRepository
from mini_kio.intelligence.retrieval_router import RetrievalRouter

logger = logging.getLogger(__name__)

_repo = BriefRepository()
_router = RetrievalRouter()

_RESEARCH_STOP = {"the", "a", "an", "about", "on", "please", "me", "this", "that", "up"}


def _clean_topic(t: str) -> str:
    t = re.sub(r"\s+", " ", t).strip(" .!?;:,-\"'").strip()
    return t if t and t not in _RESEARCH_STOP else ""


def _extract_research_command(query: str):
    """(sub_action, topic):
       research brief on X            -> ("brief", X)
       continue research on X         -> ("continue", X)
       what did i research            -> ("topics", "")
       research X                     -> ("research", X)
    """
    low = query.lower().strip()
    if re.search(r"what\s+did\s+i\s+research|list\s+my\s+research|my\s+research\s+briefs", low):
        return "topics", ""
    m = re.search(r"research\s+brief\s+(?:on|about)\s+(.+?)\s*$", low)
    if m:
        return "brief", _clean_topic(m.group(1))
    m = re.search(r"continue\s+research\s+(?:on|about)\s+(.+?)\s*$", low)
    if m:
        return "continue", _clean_topic(m.group(1))
    m = re.search(r"\bresearch\s+(.+?)\s*$", low)
    if m:
        return "research", _clean_topic(m.group(1))
    return None, ""


def looks_like_research(query: str) -> bool:
    """Routing hook: True for the research/brief/continue-research family."""
    action, topic = _extract_research_command(query)
    if action == "topics":
        return True
    return action in ("research", "brief", "continue") and bool(topic)


def _topic_key(topic: str) -> str:
    return re.sub(r"[^a-z0-9]+", "-", topic.lower()).strip("-")[:120] or "untitled"


def _compose_findings(results) -> List[Dict]:
    findings = []
    seen = set()
    for r in results:
        url = r.url or ""
        if url in seen:
            continue
        seen.add(url)
        findings.append({
            "title": r.title or "",
            "source": r.source or "",
            "url": url,
            "date": getattr(r, "published_date", None) or "",
            "summary": (r.summary or "")[:240],
        })
    return findings


def _render_brief(topic: str, findings: List[Dict]) -> str:
    if not findings:
        return f"Research on {topic}: no sources found right now."
    lines = [f"Research: {topic}", ""]
    for i, f in enumerate(findings, 1):
        parts = [f["source"], f["date"]] if f["date"] else [f["source"]]
        src = ", ".join(p for p in parts if p)
        lines.append(f"{i}. {f['title']} — {f['summary']}")
        if src:
            lines.append(f"   ({src})")
        if f["url"]:
            lines.append(f"   {f['url']}")
    return "\n".join(lines)


def _gather(query: str) -> List[Dict]:
    results = _router.retrieve_evidence(query, max_results=4)
    return _compose_findings(results)


def research_answer(query: str, ctx=None, decision=None) -> dict:
    action, topic = _extract_research_command(query)
    session_id = getattr(decision, "session_id", "") if decision is not None else ""

    if action == "topics":
        rows = _repo.list_topics(session_id) if session_id else []
        if not rows:
            return {"success": True,
                    "message": "You haven't saved any research briefs yet — try 'research quantum computing'.",
                    "type": "research", "action": "topics", "topics": []}
        parts = [f"{r['topic']}" for r in rows]
        return {"success": True,
                "message": "Your research briefs: " + "; ".join(parts) + ".",
                "type": "research", "action": "topics", "topics": rows}

    if not topic:
        return {"success": False,
                "message": "Tell me what to research — like 'research quantum computing'.",
                "type": "research"}

    if action == "brief":
        brief = _repo.get(session_id, _topic_key(topic)) if session_id else None
        if not brief:
            return {"success": False, "topic": topic,
                    "message": f"I don't have a saved brief on {topic} yet — say 'research {topic}'.",
                    "type": "research", "action": "brief"}
        return {"success": True, "topic": topic, "message": brief.content,
                "type": "research", "action": "brief",
                "sources": brief.sources_json or []}

    if action == "continue":
        previous = _repo.get(session_id, _topic_key(topic)) if session_id else None
        prior_urls = {s.get("url", "") for s in (previous.sources_json or [])} if previous else set()
        findings = _gather(topic)
        new_findings = [f for f in findings if f["url"] and f["url"] not in prior_urls]
        if previous:
            _repo.upsert(session_id, _topic_key(topic), topic,
                         _render_brief(topic, findings), findings)
        if new_findings:
            titles = "; ".join(f["title"] for f in new_findings[:3])
            return {"success": True, "topic": topic,
                    "message": f"Since your last brief on {topic}, I found {len(new_findings)} new source(s): {titles}.",
                    "type": "research", "action": "continue",
                    "new_findings": new_findings, "new_count": len(new_findings)}
        return {"success": True, "topic": topic,
                "message": f"No new sources on {topic} since your last brief.",
                "type": "research", "action": "continue", "new_count": 0}

    # action == "research": gather + persist + return the brief
    findings = _gather(topic)
    brief_text = _render_brief(topic, findings)
    saved = False
    if session_id:
        _repo.upsert(session_id, _topic_key(topic), topic, brief_text, findings)
        saved = True
    return {"success": True, "topic": topic, "message": brief_text,
            "type": "research", "action": "research",
            "sources": findings, "source_count": len(findings),
            "saved": saved}