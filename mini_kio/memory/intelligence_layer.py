"""
intelligence_layer.py — Unified evidence-backed intelligence layer for KIO.

This module provides:
1. Communication style evidence (contextual, not keyword frequency)
2. Emotional episodes (with triggers, context, resolution)
3. KIO correction detection (bidirectional, semantic)
4. Shared history relationships (with supersession chains)
5. Project lifecycle validation (real projects vs one-off questions)
6. Relevance-ranked retrieval for all categories
7. Evidence-backed self-model queries

Every query returns STRUCTURED EVIDENCE the LLM can compose naturally.
These are DATA, not personality labels.

Key design decisions:
- Provenance prefix 'intellayer:' marks all persisted evidence
- Shared history only includes genuine Joel↔KIO interactions
  (not conversation titles or third-party content)
- Emotional episodes use 'emotion' field (not 'category')
- Communication evidence is persisted to graph as 'communication:' nodes
"""

from __future__ import annotations

import glob
import json
import logging
import os
import re
from collections import defaultdict
from dataclasses import dataclass
from datetime import datetime, timezone
from typing import Any, Dict, List, Optional, Tuple

from mini_kio.semantic.graph import SemanticGraph, USER_KEY, KIO_KEY
from mini_kio.backend.db import db_session
from mini_kio.backend.models import SemanticNodeModel, SemanticLinkModel

logger = logging.getLogger(__name__)

EXPORT_DIR = os.path.join("data", "historical", "chatgpt_export_2026-06-12")
PROVENANCE = "intellayer"

# Module-level cache: extraction results computed once, reused across queries
_extraction_cache: Dict[str, Any] = {}
_CACHE_TTL = 3600  # 1 hour
_cache_ts: float = 0


# ═══════════════════════════════════════════════════════════════════════════════
# CONVERSATION PARSER
# ═══════════════════════════════════════════════════════════════════════════════
def _parse_conversations(directory: str = EXPORT_DIR) -> List[Dict[str, Any]]:
    out: List[Dict[str, Any]] = []
    files = sorted(glob.glob(os.path.join(directory, "conversations-*.json")))
    for path in files:
        try:
            with open(path, encoding="utf-8") as f:
                convs = json.load(f)
        except Exception:
            continue
        for c in convs:
            mapping = c.get("mapping") or {}
            messages = []
            for m in mapping.values():
                msg = m.get("message") or {}
                author = msg.get("author") or {}
                if not isinstance(author, dict):
                    continue
                role = (author.get("role") or "").lower()
                if role not in ("user", "assistant"):
                    continue
                content = msg.get("content") or {}
                if content.get("content_type") != "text":
                    continue
                parts = content.get("parts") or []
                text = "".join(p for p in parts if isinstance(p, str)).strip()
                if not text:
                    continue
                ts = 0.0
                try:
                    ts = float(msg.get("create_time") or 0)
                except (TypeError, ValueError):
                    ts = 0.0
                messages.append((ts, role, text, "joel" if role == "user" else "chatgpt"))
            if messages:
                messages.sort(key=lambda x: x[0])
                out.append({
                    "conversation_id": c.get("conversation_id") or c.get("id") or "",
                    "title": (c.get("title") or "").strip(),
                    "create_time": c.get("create_time"),
                    "messages": messages,
                })
    return out


def _msg_date(ts: float) -> str:
    if not ts:
        return ""
    try:
        return datetime.fromtimestamp(ts, tz=timezone.utc).strftime("%Y-%m")
    except Exception:
        return ""


def _is_noise(text: str) -> bool:
    """Filter out code blocks, very long text, and unbroken strings."""
    return len(text) > 2000 or "```" in text or bool(re.search(r"\w{50,}", text))


def _is_third_party(text: str, title: str) -> bool:
    """Detect content that is about a third party, not Joel↔KIO interaction.
    Examples: 'Write a message to a friend...' is a writing request, not praise.
    """
    tp_signals = [
        r"\bwrite (?:a |an |me )?(?:message|letter|note|essay|paragraph|email)",
        r"\bwrite (?:about|on|a )",
        r"\bgive me (?:a |an )?(?:summary|overview|explanation)",
        r"\bexplain (?:what|how|why)",
        r"\btell me about\b",
        r"\bwhat is\b",
        r"\bdefine\b",
        r"\btranslat(?:e|ion)\b",
        r"\bparaphrase\b",
        r"\brewrite\b",
        r"\bcorrect (?:this|the following)\b",
        r"\bproofread\b",
        r"\bsummarize\b",
    ]
    low = text.lower().strip()
    # If the message is a third-party content request, not a personal statement
    for pat in tp_signals:
        if re.search(pat, low, re.I):
            return True
    return False


# ═══════════════════════════════════════════════════════════════════════════════
# 1. COMMUNICATION STYLE — contextual evidence
# ═══════════════════════════════════════════════════════════════════════════════

def extract_communication_style(conversations: List[Dict]) -> Dict[str, Any]:
    """Extract contextual communication evidence from conversations.
    Returns structured evidence about HOW Joel communicates, not just WHAT words."""
    patterns = {
        "directness": [],       # short direct messages vs verbose explanations
        "verbosity": [],        # message length distribution
        "request_style": [],    # how Joel asks for things
        "correction_style": [], # how Joel corrects
        "approval_style": [],   # how Joel approves
        "rejection_style": [],  # how Joel rejects
        "urgency_markers": [],  # how urgency is expressed
        "humor_markers": [],    # humor usage
        "technical_shorthand": [],  # technical abbreviations
    }

    for conv in conversations:
        title = conv.get("title", "")
        cid = conv.get("conversation_id", "")
        msgs = conv.get("messages", [])

        user_msgs = [(ts, text) for ts, role, text, speaker in msgs if speaker == "joel"]

        for i, (ts, text) in enumerate(user_msgs):
            if _is_noise(text) or _is_third_party(text, title):
                continue

            year_month = _msg_date(ts)
            low = text.lower()
            msg_len = len(text)

            # Directness: short messages (< 50 chars) are direct
            if msg_len < 50:
                patterns["directness"].append({
                    "evidence": text[:150],
                    "context": title,
                    "when": year_month,
                    "length": msg_len,
                })

            # Verbosity: long messages (> 200 chars) are verbose
            if msg_len > 200:
                patterns["verbosity"].append({
                    "evidence": text[:150],
                    "context": title,
                    "when": year_month,
                    "length": msg_len,
                })

            # Request style
            if re.search(r"\b(can you|i need|help me|make|create|write|build|fix|do this)\b", low):
                patterns["request_style"].append({
                    "evidence": text[:150],
                    "context": title,
                    "when": year_month,
                })

            # Correction style
            if re.search(r"\b(no|wrong|not what i|actually|wait|hold on|scratch|nvm)\b", low):
                patterns["correction_style"].append({
                    "evidence": text[:150],
                    "context": title,
                    "when": year_month,
                })

            # Approval style
            if re.search(r"\b(nice|perfect|exactly|thanks|good|great|awesome|works|it works)\b", low):
                patterns["approval_style"].append({
                    "evidence": text[:150],
                    "context": title,
                    "when": year_month,
                })

            # Rejection style
            if re.search(r"\b(don'?t|never|stop|i don'?t want|i won'?t|nah|nope|not happening)\b", low):
                patterns["rejection_style"].append({
                    "evidence": text[:150],
                    "context": title,
                    "when": year_month,
                })

            # Urgency markers
            if re.search(r"\b(now|asap|urgent|deadline|rn|right now|today|tonight|hurry)\b", low):
                patterns["urgency_markers"].append({
                    "evidence": text[:150],
                    "context": title,
                    "when": year_month,
                })

            # Humor
            if re.search(r"\b(lol|lmao|haha|joke|funny|bruh|sheesh|dead)\b", low):
                patterns["humor_markers"].append({
                    "evidence": text[:150],
                    "context": title,
                    "when": year_month,
                })

            # Technical shorthand
            if re.search(r"\b(api|db|env|cfg|refactor|debug|deploy|build|commit|merge|pr|issue|bug)\b", low):
                patterns["technical_shorthand"].append({
                    "evidence": text[:150],
                    "context": title,
                    "when": year_month,
                })

    # Aggregate into summary
    summary = {}
    for category, items in patterns.items():
        if not items:
            continue
        dates = [item["when"] for item in items if item.get("when")]
        summary[category] = {
            "count": len(items),
            "first_seen": min(dates) if dates else "",
            "last_seen": max(dates) if dates else "",
            "samples": [item["evidence"] for item in items[:3]],
            "confidence": min(0.95, 0.4 + 0.05 * len(items)),
        }

    return {"patterns": summary}


def persist_communication_evidence(conversations: List[Dict], session_id: str = "tg_default") -> int:
    """Persist communication style evidence into the semantic graph as nodes.
    Returns count of persisted evidence points."""
    style = extract_communication_style(conversations)
    patterns = style.get("patterns", {})

    graph = SemanticGraph(session_id)
    persisted = 0

    for category, data in patterns.items():
        count = data.get("count", 0)
        confidence = data.get("confidence", 0.5)
        first = data.get("first_seen", "")
        last = data.get("last_seen", "")
        samples = data.get("samples", [])

        label = f"communication: {category} ({count} occurrences, {first} to {last})"
        key = f"communication:{category}"

        graph.ensure_node(
            kind="communication_pattern",
            name=label,
            description=f"Communication style evidence: {category}. {count} observed instances from {first} to {last}.",
            meta={
                "category": category,
                "count": count,
                "confidence": confidence,
                "first_seen": first,
                "last_seen": last,
                "samples": samples,
            },
        )
        graph.record_statement(
            USER_KEY,
            label,
            stance="observation",
            confidence=confidence,
            provenance=f"{PROVENANCE}:communication",
        )
        persisted += 1

    return persisted


# ═══════════════════════════════════════════════════════════════════════════════
# 2. EMOTIONAL EPISODES — contextual, not frequency
# ═══════════════════════════════════════════════════════════════════════════════

_EMOTION_SIGNALS = {
    "frustration": re.compile(
        r"\b(frustrat|annoy|piss|mad|angry|irritat|ugh|god ?damn|"
        r"this ?is ?broken|not ?working|doesn'?t ?work|can'?t ?believe|"
        r"ridiculous|stupid|dumb|sucks|trash|garbage|stuck|"
        r"confused|lost|overwhelmed|struggling|failing|"
        r"failed|crash|bug|error|broken|dead|rip|why does|"
        r"what ?the|how ?is ?this|this ?makes ?no ?sense|"
        r"keeps ?happening|every ?time|still ?not)\b", re.I),
    "excitement": re.compile(
        r"\b(excit|stoked|pumped|hyped|amazing|awesome|incredible|"
        r"let'?s ?go|yess?|finally|big ?brain|galaxy ?brain|"
        r"this ?is ?insane|no ?way|wow|holy|sheesh|"
        r"goat|goated|legend|fire|bussin|slay|w |win|"
        r"promising|breakthrough|milestone|accomplished|achieved|"
        r"love ?this|can'?t ?wait|proud|thrilled|"
        r"it ?works|holy ?shit|nice|perfect)\b", re.I),
    "urgency": re.compile(
        r"\b(urgent|asap|right ?now|rn|immediately|quickly|hurry|"
        r"deadline|due ?by|need ?this ?now|time ?sensitive|priority|"
        r"must ?do|have ?to|gotta|need ?to|important|critical|"
        r"today|tonight|before|by ?end|eod|eow)\b", re.I),
    "confusion": re.compile(
        r"\b(confused|don'?t ?understand|what ?do ?you ?mean|"
        r"how ?does|why ?does|can ?you ?explain|i ?don'?t ?get|"
        r"unclear|lost|what ?is|wait ?what|hold ?on)\b", re.I),
    "satisfaction": re.compile(
        r"\b(nice|perfect|exactly|that'?s ?right|great|excellent|"
        r"good ?job|well ?done|you ?got ?it|nailed ?it|"
        r"there ?you ?go|finally|works|it ?works|"
        r"exactly ?what|i ?needed|saved ?me|thanks|thank you)\b", re.I),
}


def extract_emotional_episodes(conversations: List[Dict]) -> List[Dict]:
    """Extract contextual emotional episodes with triggers and context.
    Each episode has: emotion, trigger, context, intensity, evidence.
    NOT personality labels — these are conversational context signals."""
    episodes = []

    for conv in conversations:
        title = conv.get("title", "")
        cid = conv.get("conversation_id", "")
        msgs = conv.get("messages", [])

        # Build turn context (what was discussed before the emotional expression)
        context_buffer = []

        for ts, role, text, speaker in msgs:
            if _is_noise(text) or _is_third_party(text, title):
                if speaker == "chatgpt" and len(text) < 500:
                    context_buffer.append(text[:200])
                continue

            year_month = _msg_date(ts)

            # Only extract from Joel's messages
            if speaker != "joel":
                if len(text) < 500:
                    context_buffer.append(text[:200])
                continue

            low = text.lower()

            for emotion, pattern in _EMOTION_SIGNALS.items():
                if pattern.search(low):
                    matches = pattern.findall(low)
                    msg_len = len(text)
                    intensity = "low"
                    if len(matches) >= 3 or msg_len > 300:
                        intensity = "high"
                    elif len(matches) >= 2 or msg_len > 150:
                        intensity = "medium"

                    # Get trigger context (what was being discussed)
                    trigger = title or "unknown context"
                    if context_buffer:
                        trigger = context_buffer[-1][:100]

                    episodes.append({
                        "emotion": emotion,
                        "trigger": trigger,
                        "context": title,
                        "intensity": intensity,
                        "evidence": text[:200],
                        "conversation_id": cid,
                        "when": year_month,
                        "confidence": 0.7 if intensity == "high" else 0.5,
                    })

            # Add user message to context buffer
            context_buffer.append(text[:200])
            if len(context_buffer) > 5:
                context_buffer.pop(0)

    return episodes


# ═══════════════════════════════════════════════════════════════════════════════
# 3. KIO CORRECTION DETECTION — bidirectional, semantic
# ═══════════════════════════════════════════════════════════════════════════════

# Broad correction patterns (not just narrow regex)
_CORRECTION_PATTERNS = re.compile(
    r"\b(no|wrong|not what i|actually|wait|hold on|scratch|nvm|"
    r"that'?s not|you misunderstood|i already told you|"
    r"don'?t do that|not like that|forget that|"
    r"you'?re missing|i don'?t want|we already decided|"
    r"stop doing|change that|fix that|redo|"
    r"i meant|i wanted|i asked for|i need you to|"
    r"not ?what i ?meant|not ?what i ?wanted|not ?what i ?asked|"
    r"wrong approach|bad idea|doesn'?t make sense)\b", re.I
)

# Expectation patterns — Joel tells KIO how it should behave
_EXPECTATION_PATTERNS = re.compile(
    r"you (?:should|must|need to|have to|better|are supposed to|need you to|"
    r"please|always|never|make sure|stop doing|do not do|"
    r"this is how|this should|make it|KIO should|KIO must|KIO needs to)", re.I
)

# Genuine praise patterns — only matched when Joel directly approves KIO's work
# Must be short (< 200 chars) AND directly reference KIO's output
_PRAISE_PATTERNS = re.compile(
    r"\b(good ?job|well ?done|that'?s ?right|"
    r"you ?(?:got ?it|nailed ?it|got ?this|"
    r"understand|are ?right)|there you ?go|it ?works|"
    r"saved ?me|exactly ?what i ?needed|"
    r"this ?is ?exactly|love ?it|nice work|"
    r"respect|props|kudos)\b", re.I
)

# Failure patterns — KIO failed at something
_FAILURE_PATTERNS = re.compile(
    r"\b(broke|broken|crashed|failed|error|bug|regression|"
    r"doesn'?t ?work|not ?working|stopped working|"
    r"was working|used to work|regress|"
    r"this ?broke|that ?broke|you ?broke|"
    r"not ?what ?i|wrong|incorrect)\b", re.I
)

# Promise patterns (KIO promised to do something)
_PROMISE_PATTERNS = re.compile(
    r"\b(i(?:'ll| will)\s+(?:build|create|implement|fix|add|"
    r"make|write|set up|configure|deploy|handle|take care of|"
    r"take care|do this|work on))\b", re.I
)


def extract_kio_corrections(conversations: List[Dict]) -> List[Dict]:
    """Extract KIO correction chains: Joel corrects KIO, KIO fails, KIO promises.
    Bidirectional: parses BOTH user AND assistant messages.

    Key quality filter: correction/praise/failure must be about KIO's actual work,
    NOT about third-party content requests or conversation titles."""
    events = []

    for conv in conversations:
        title = conv.get("title", "")
        cid = conv.get("conversation_id", "")
        msgs = conv.get("messages", [])

        for i, (ts, role, text, speaker) in enumerate(msgs):
            if _is_noise(text):
                continue

            year_month = _msg_date(ts)

            # Joel corrections of KIO — must be genuinely about KIO's behavior
            if speaker == "joel" and _CORRECTION_PATTERNS.search(text):
                # Filter: skip if this is clearly a third-party content request
                if _is_third_party(text, title):
                    continue
                # Filter out role-play requests ("I'll be u", "you be me", etc.)
                is_roleplay = bool(re.search(
                    r"\b(i(?:'ll| will) be (?:u|you|chatgpt|kio)|"
                    r"you(?:'ll| will| be) (?:be )?(?:me|human|user)|"
                    r"remember i'?m (?:u|you|chatgpt|kio)|"
                    r"say (?:that|chatgpt|kio) is|"
                    r"no say|no ur|no you'?re|"
                    r"talk to (?:u|you) as|"
                    r"pretend (?:i'?m|you'?re)|"
                    r"role.?play|you(?:'re| are) (?:a |the )?human)",
                    text.lower()))
                if is_roleplay:
                    continue
                # Filter out code snippets (contain =, print, if (z), etc.)
                if re.search(r"\b(print\s*\(|if \(|else:|def |import |while \(|for .* in)", text):
                    continue
                # Filter out third-party contexts (not about KIO)
                third_party_ctx = any(kw in title.lower() for kw in (
                    "instagram", "jee", "keam", "cusat", "vit", "cbse",
                    "football", "efootball", "cricket", "anime", "movie",
                    "dragon", "gaming", "phone", "laptop", "samsung",
                    "gmail", "vpn", "ban", "account"))
                if third_party_ctx and "kio" not in text.lower():
                    continue
                # Must be substantive (> 15 chars) — filter out bare "No"
                if len(text.strip()) <= 15:
                    continue
                # Additional filter: correction should reference KIO or be
                # in context where KIO just acted (preceded by assistant msg)
                is_kio_context = False
                prev_asst_text = ""
                if i > 0:
                    prev_speaker = msgs[i-1][3]  # speaker field
                    prev_asst_text = msgs[i-1][2] if prev_speaker == "chatgpt" else ""
                    if prev_speaker == "chatgpt" and len(prev_asst_text) > 100:
                        is_kio_context = True
                mentions_kio_or_you = "kio" in text.lower() or "you" in text.lower()
                if mentions_kio_or_you or is_kio_context:
                    # Confidence boost if preceded by substantive assistant response
                    conf = 0.85 if is_kio_context and len(prev_asst_text) > 50 else 0.7
                    events.append({
                        "type": "correction",
                        "who": "joel",
                        "description": text[:200],
                        "context": title,
                        "when": year_month,
                        "confidence": conf,
                        "conversation_id": cid,
                    })

            # Joel expectations of KIO
            if speaker == "joel" and _EXPECTATION_PATTERNS.search(text):
                if _is_third_party(text, title):
                    continue
                events.append({
                    "type": "expectation",
                    "who": "joel",
                    "description": text[:200],
                    "context": title,
                    "when": year_month,
                    "confidence": 0.7,
                    "conversation_id": cid,
                })

            # Joel praising KIO -- must be SHORT and directly about KIO's output
            # Filter out: goodbyes, farewells, generic pleasantries
            if speaker == "joel" and _PRAISE_PATTERNS.search(text) and len(text) < 80:
                if _is_third_party(text, title):
                    continue
                low_t = text.lower()
                # Must directly address KIO ('you') and NOT be a farewell
                has_address = any(kw in low_t for kw in ("you ", "you're", "you got", "kio"))
                is_farewell = bool(re.search(
                    r"\b(bye|goodbye|see you|good night|good morning|take care|talk later|\bthank\b)",
                    low_t))
                if has_address and not is_farewell:
                    events.append({
                        "type": "praise",
                        "who": "joel",
                        "description": text[:200],
                        "context": title,
                        "when": year_month,
                        "confidence": 0.8,
                        "conversation_id": cid,
                    })

            # KIO promises (from assistant messages)
            if speaker == "chatgpt" and _PROMISE_PATTERNS.search(text):
                # Check if user later reports failure
                for j in range(i + 1, min(i + 10, len(msgs))):
                    _, _, later_text, later_speaker = msgs[j]
                    if later_speaker == "joel" and _FAILURE_PATTERNS.search(later_text):
                        events.append({
                            "type": "failure",
                            "who": "kio",
                            "description": f"KIO promised: {text[:100]} -> Joel: {later_text[:100]}",
                            "context": title,
                            "when": year_month,
                            "confidence": 0.85,
                            "conversation_id": cid,
                        })
                        break

            # KIO failures detected in user messages (preceded by assistant msg)
            if speaker == "joel" and _FAILURE_PATTERNS.search(text):
                if i > 0:
                    prev_ts, prev_role, prev_text, prev_speaker = msgs[i - 1]
                    if prev_speaker == "chatgpt":
                        events.append({
                            "type": "failure",
                            "who": "kio",
                            "description": f"KIO did: {prev_text[:100]} -> Joel: {text[:100]}",
                            "context": title,
                            "when": year_month,
                            "confidence": 0.8,
                            "conversation_id": cid,
                        })

    return events


# ═══════════════════════════════════════════════════════════════════════════════
# 4. SHARED HISTORY RELATIONSHIPS — with supersession chains
# ═══════════════════════════════════════════════════════════════════════════════

def _months_apart(d1: str, d2: str) -> int:
    """Estimate months between two year-month strings."""
    if not d1 or not d2:
        return 999
    try:
        y1, m1 = map(int, d1.split("-"))
        y2, m2 = map(int, d2.split("-"))
        return abs((y2 - y1) * 12 + (m2 - m1))
    except Exception:
        return 999


def extract_shared_history(conversations: List[Dict]) -> List[Dict]:
    """Extract Joel-KIO shared history with relationship chains.
    Builds chronological evidence of how the relationship evolved.
    Only includes genuine Joel↔KIO interactions, not third-party content."""
    events = extract_kio_corrections(conversations)

    # Sort chronologically
    events.sort(key=lambda e: e.get("when", ""))

    # Build relationship chains
    chains = []
    current_chain = None

    for event in events:
        etype = event["type"]

        # Start new chain on correction or failure
        if etype in ("correction", "failure"):
            if current_chain:
                chains.append(current_chain)
            current_chain = {
                "trigger": etype,
                "events": [event],
                "context": event["context"],
                "start_when": event["when"],
                "end_when": event["when"],
            }
        elif current_chain:
            # Extend chain with related events within 1 month
            if event["when"] <= current_chain["end_when"] or \
               _months_apart(event["when"], current_chain["end_when"]) <= 1:
                current_chain["events"].append(event)
                current_chain["end_when"] = event["when"]
            else:
                chains.append(current_chain)
                current_chain = {
                    "trigger": etype,
                    "events": [event],
                    "context": event["context"],
                    "start_when": event["when"],
                    "end_when": event["when"],
                }

    if current_chain:
        chains.append(current_chain)

    return chains


# ═══════════════════════════════════════════════════════════════════════════════
# 5. PROJECT LIFECYCLE VALIDATION
# ═══════════════════════════════════════════════════════════════════════════════

def validate_project_lifecycles() -> List[Dict]:
    """Validate existing project nodes in the graph.
    Check lifecycle transitions, detect anomalies, compute confidence."""
    with db_session() as db:
        projects = db.query(SemanticNodeModel).filter(
            SemanticNodeModel.session_id == "tg_default",
            SemanticNodeModel.kind == "project",
        ).all()

    validated = []
    for p in projects:
        meta = p.meta_json or {}
        lifecycle = meta.get("lifecycle", "mentioned")
        history = meta.get("status_history", [])

        # Compute confidence based on evidence
        confidence = 0.5
        if history:
            confidence = min(0.95, 0.4 + 0.1 * len(history))
        if lifecycle in ("active", "building"):
            confidence = min(0.95, confidence + 0.1)

        # Detect anomalies
        anomalies = []
        if len(history) > 5:
            anomalies.append(f"many transitions ({len(history)})")
        if lifecycle == "mentioned" and not history:
            anomalies.append("no transitions from mentioned")

        validated.append({
            "name": p.name,
            "lifecycle": lifecycle,
            "status": p.status,
            "transitions": len(history),
            "confidence": confidence,
            "anomalies": anomalies,
            "first_seen": meta.get("created_at", ""),
            "last_seen": meta.get("last_activity", ""),
        })

    return sorted(validated, key=lambda x: -x["confidence"])


# ═══════════════════════════════════════════════════════════════════════════════
# 6. RELEVANCE-RANKED RETRIEVAL
# ═══════════════════════════════════════════════════════════════════════════════

# Semantic query routing
_QUERY_ROUTES = {
    "project": re.compile(
        r"\b(project|building|working on|app|website|prototype|"
        r"develop|code|abandon|drop|revive|continue|resume|"
        r"what did i|what am i|what have i|been doing|"
        r"focused on|up to|lately|recently|currently|"
        r"come back|came back|back to|"
        r"completely (?:drop|stop|quit|abandon)|"
        r"stuff (?:i|have|did).*?(?:drop|stop|quit|abandon)|"
        r"what.*?(?:drop|abandon|quit|stop|gave up))", re.I),
    "decision": re.compile(
        r"\b(decid|decis|chose|picked|change.?mind|reversal|"
        r"why did i|dropped|abandoned|switch|"
        r"used to|before|earlier|previously|"
        r"change .* mind|second thought|"
        r"pattern.*decis|how.*decis|make.*decis|"
        r"changed my mind|mind about)", re.I),
    "emotion": re.compile(
        r"\b(frustrat|angry|piss|excit|hype|amazing|stuck|broken|"
        r"annoy|confused|lost|happy|sad|mood|feel|"
        r"when.*debug|when.*frustrated|when.*excited)", re.I),
    "correction": re.compile(
        r"\b(correct|wrong|fix|mistake|error|regression|"
        r"broke|broken|what did you|"
        r"you (?:kept|keep|always|never)|"
        r"corrected you|got wrong|messed up)\b", re.I),
    "communication": re.compile(
        r"\b(talk|speak|communicate|phrase|slang|"
        r"how do i|how i|my style|tone|"
        r"bruh|bro|gonna|wanna|"
        r"how.*talk|how.*speak|how.*express|"
        r"when.*(?:debug|fail|broken|stuck|frustrat)|"
        r"what (?:am i|like|i am) (?:like )?when|"
        r"what.*(?:like|am i) when.*(?:debug|fail|stuck|broken|frustrat)|"
        r"how (?:do i|i) (?:usually |normally )?(?:talk|communicate|express|react))\b", re.I),
    "kio": re.compile(
        r"\b(kio|yourself|what do you know|"
        r"what can you|what have you|"
        r"tell me about yourself|"
        r"know about yourself|self.model)\b", re.I),
    "identity": re.compile(
        r"\b(who am i|about me|what do you know about me|"
        r"tell me about (?:me|yourself)|what am i|"
        r"my name|my age|my college|education|"
        r"who are you|"
        r"what do (?:u|you) (?:know|think) (?:about |abt )?(?:me|myself)|"
        r"what (?:u|you) know about me|"
        r"know about me|"
        r"what.*(?:know|think).*about me|"
        r"what.*(?:like|am i|personality|behavior))\b", re.I),
    "technical": re.compile(
        r"\b(python|code|tech|learn|skill|programming|"
        r"developer|engineering|git|api|database)\b", re.I),
    "relationship": re.compile(
        r"\b(relationship|how.*work together|how.*interact|"
        r"how.*communicate|how.*talk|history|"
        r"how have you changed|how.*evolved)\b", re.I),
}


def _cached_extraction() -> Dict[str, Any]:
    """Return cached extraction results (computed once per hour)."""
    global _cache_ts
    import time
    now = time.time()
    if _extraction_cache and (now - _cache_ts) < _CACHE_TTL:
        return _extraction_cache
    try:
        convs = _parse_conversations()
        _extraction_cache["corrections"] = extract_kio_corrections(convs)
        _extraction_cache["emotional"] = extract_emotional_episodes(convs)
        _extraction_cache["shared_history"] = extract_shared_history(convs)
        _cache_ts = now
        logger.info("[INTELLAYER] Extraction cache refreshed: %d corrections, %d emotional, %d shared",
                     len(_extraction_cache["corrections"]),
                     len(_extraction_cache["emotional"]),
                     len(_extraction_cache["shared_history"]))
    except Exception as exc:
        logger.warning("[INTELLAYER] Extraction cache refresh failed: %s", exc)
    return _extraction_cache


def retrieve_intelligence(
    session_id: str,
    user_text: str,
    *,
    max_items: int = 15,
) -> str:
    """Relevance-ranked retrieval: given a user message, retrieve ONLY
    the evidence relevant to that query. Different questions retrieve
    different evidence. Not full injection."""
    low = (user_text or "").lower()
    parts: List[str] = []

    # Longitudinal evidence is ALWAYS stored under tg_default.
    # The caller's session_id is for per-session context; the archive
    # evidence lives in the canonical tg_default graph.
    evidence_session = "tg_default"

    # Route query to relevant evidence dimensions
    matched_routes = [route for route, pattern in _QUERY_ROUTES.items()
                      if pattern.search(low)]

    if not matched_routes:
        matched_routes = ["identity", "project"]

    # Route priority: identity must override kio when user asks about themselves
    # "what do you know about me" = asking about JOEL, not KIO
    if "identity" in matched_routes and "kio" in matched_routes:
        matched_routes.remove("kio")
    # "what do you know about yourself" = asking about KIO
    if any(kw in low for kw in ("yourself", "your self", "you know about you")):
        if "kio" not in matched_routes:
            matched_routes.append("kio")
        if "identity" in matched_routes:
            matched_routes.remove("identity")

    # Always include identity for context (if not already present)
    if "identity" not in matched_routes:
        matched_routes.append("identity")

    graph = SemanticGraph(evidence_session)

    # Index evidence by category from graph
    links = graph.attributed_statements(
        USER_KEY, relation="said", stance="observation",
        active_only=True, limit=500,
    )

    evidence_by_cat: Dict[str, List[str]] = defaultdict(list)
    for link in links:
        target = getattr(link, "target_name", "") or ""
        prov = getattr(link, "provenance", "") or ""

        # V1 categories (from longitudinal_extractor)
        for cat in ("communication:", "emotional:", "behavior:", "decision:",
                     "technical interest:", "kio_history:"):
            if cat in target:
                evidence_by_cat[cat.rstrip(":")].append(target)
                break
        else:
            # V2 categories (from longitudinal_v2)
            if "longitudinal_v2:project" in prov:
                evidence_by_cat["project"].append(target)
            elif "longitudinal_v2:emotional" in prov:
                evidence_by_cat["emotional"].append(target)
            elif "longitudinal_v2:decision" in prov:
                evidence_by_cat["decision"].append(target)
            elif "longitudinal_v2:shared" in prov:
                evidence_by_cat["shared_history"].append(target)
            # Intelligence layer categories
            elif "intellayer:communication" in prov:
                evidence_by_cat["communication"].append(target)
            elif "intellayer:" in prov:
                # Categorize by the node kind or content
                if "correction" in target.lower():
                    evidence_by_cat["correction"].append(target)
                elif "praise" in target.lower():
                    evidence_by_cat["praise"].append(target)
                elif "failure" in target.lower():
                    evidence_by_cat["failure"].append(target)
                elif "expectation" in target.lower():
                    evidence_by_cat["expectation"].append(target)
                elif "communication" in target.lower():
                    evidence_by_cat["communication"].append(target)
                else:
                    evidence_by_cat["shared_history"].append(target)

    # Also query emotional episodes from graph
    emo_links = graph.attributed_statements(
        USER_KEY, relation="said", stance="observation",
        active_only=True, limit=500,
    )
    for link in emo_links:
        target = getattr(link, "target_name", "") or ""
        prov = getattr(link, "provenance", "") or ""
        if "longitudinal_v2:emotional" in prov or "intellayer:emotional" in prov:
            if target not in evidence_by_cat["emotional"]:
                evidence_by_cat["emotional"].append(target)

    # Retrieve evidence for matched routes
    if "project" in matched_routes:
        with db_session() as db:
            proj_nodes = db.query(SemanticNodeModel).filter(
                SemanticNodeModel.session_id == evidence_session,
                SemanticNodeModel.kind == "project",
                SemanticNodeModel.status == "active",
            ).order_by(SemanticNodeModel.id.desc()).limit(30).all()
        active_projs = []
        hist_projs = []
        for pn in proj_nodes:
            meta = pn.meta_json or {}
            lc = meta.get("lifecycle", "mentioned")
            label = f"{pn.name} ({lc})"
            if lc in ("active", "building", "planning", "researching", "mentioned"):
                active_projs.append(label)
            elif lc in ("abandoned", "completed"):
                hist_projs.append(label)
        if active_projs:
            parts.append("Active projects: " + "; ".join(active_projs[:5]) + ".")
        # Show historical projects when user asks about past/dropped/abandoned
        show_hist = any(kw in low for kw in (
            "before", "earlier", "old", "past", "abandon",
            "drop", "stopped", "quit", "gave up", "no longer",
            "used to", "what.*dropped", "completely"))
        if hist_projs and show_hist:
            parts.append("Historical/abandoned projects: " + "; ".join(hist_projs[:5]) + ".")

    if "decision" in matched_routes:
        items = evidence_by_cat.get("decision", [])
        if items:
            parts.append("Decision evidence:\n" + "\n".join(
                f"- {i}" for i in items[:5]))
        else:
            # Fallback: query decision links from graph by provenance
            try:
                graph = SemanticGraph(evidence_session)
                decision_links = graph.attributed_statements(
                    USER_KEY, relation="said", stance="observation",
                    active_only=True, limit=200,
                )
                dec_lines = []
                for link in decision_links:
                    prov = getattr(link, "provenance", "") or ""
                    target = getattr(link, "target_name", "") or ""
                    if "longitudinal_v2:decision" in prov:
                        dec_lines.append(target)
                if dec_lines:
                    parts.append("Decision history:\n" + "\n".join(
                        f"- {d}" for d in dec_lines[:5]))
            except Exception:
                pass

    if "emotion" in matched_routes:
        # Use cached extraction for fresh emotional episode evidence
        cache = _cached_extraction()
        episodes = cache.get("emotional", [])
        # Aggregate by emotion type
        emo_counts: Dict[str, int] = defaultdict(int)
        for ep in episodes:
            emo_counts[ep.get("emotion", "unknown")] += 1
        if emo_counts:
            emo_summary = "; ".join(
                f"{em}: {cnt} episodes"
                for em, cnt in sorted(emo_counts.items(), key=lambda x: -x[1])[:5])
            parts.append(f"Emotional patterns (from {len(episodes)} episodes): {emo_summary}.")
        # Also include high-intensity samples
        high_intensity = [ep for ep in episodes if ep.get("intensity") == "high"][:2]
        for ep in high_intensity:
            parts.append(f"  High-intensity {ep.get('emotion', '')}: \"{ep.get('evidence', '')[:80]}\"")

    if "correction" in matched_routes:
        # Use cached extraction for fresh correction evidence
        cache = _cached_extraction()
        corrections = cache.get("corrections", [])
        genuine_corrections = [c for c in corrections if c.get("type") == "correction"][:5]
        genuine_failures = [c for c in corrections if c.get("type") == "failure"][:5]
        genuine_expectations = [c for c in corrections if c.get("type") == "expectation"][:3]

        if genuine_corrections:
            parts.append("Joel corrections of KIO:\n" + "\n".join(
                f"- [{c.get('context', '')[:40]}] {c.get('description', '')[:100]}"
                for c in genuine_corrections))
        if genuine_failures:
            parts.append("KIO failures:\n" + "\n".join(
                f"- [{f.get('context', '')[:40]}] {f.get('description', '')[:100]}"
                for f in genuine_failures))
        if genuine_expectations:
            parts.append("Joel expectations of KIO:\n" + "\n".join(
                f"- {e.get('description', '')[:100]}"
                for e in genuine_expectations))

    if "communication" in matched_routes:
        # Prefer contextual communication patterns from graph nodes
        # over V1 word-frequency patterns
        try:
            with db_session() as db:
                comm_nodes = db.query(SemanticNodeModel).filter(
                    SemanticNodeModel.session_id == evidence_session,
                    SemanticNodeModel.kind == "communication_pattern",
                ).all()
            if comm_nodes:
                comm_lines = []
                for cn in comm_nodes[:9]:
                    meta = cn.meta_json or {}
                    count = meta.get("count", 0)
                    cat = meta.get("category", "")
                    conf = meta.get("confidence", 0)
                    samples = meta.get("samples", [])
                    sample_text = samples[0][:60] if samples else ""
                    comm_lines.append(f"{cat}: {count} instances (conf {conf:.0%}) {sample_text}")
                if comm_lines:
                    parts.append("Communication style (from longitudinal evidence):\n" + "\n".join(
                        f"- {l}" for l in comm_lines))
        except Exception:
            pass

    # KIO self-model is injected by _build_bounded_prompt section 5b
    # Do NOT duplicate it here

    if "identity" in matched_routes:
        from mini_kio.memory.living_model import living_model
        model = living_model(session_id)
        edu = model.get("education", [])
        if edu:
            parts.append("About Joel: " + "; ".join(
                e["text"] for e in edu[:4]) + ".")

    if "technical" in matched_routes:
        items = evidence_by_cat.get("technical interest", [])
        if items:
            parts.append("Technical interests: " + ", ".join(items[:10]) + ".")

    if "relationship" in matched_routes:
        # Use cached extraction for genuine shared history
        cache = _cached_extraction()
        sh_events = cache.get("shared_history", [])
        # Show relationship chains (corrections + failures + expectations)
        genuine_sh = []
        for chain in sh_events:
            if chain.get("trigger") in ("correction", "failure"):
                ctx = chain.get("context", "")[:40]
                evts = chain.get("events", [])
                if evts:
                    desc = evts[0].get("description", "")[:80]
                    genuine_sh.append(f"[{ctx}] {chain['trigger']}: {desc}")
        if genuine_sh:
            parts.append("Relationship history (corrections/failures):\n" + "\n".join(
                f"- {s}" for s in genuine_sh[:5]))
        # Also show genuine praise from cache
        corrections = cache.get("corrections", [])
        genuine_praise = [c for c in corrections if c.get("type") == "praise"][:3]
        if genuine_praise:
            parts.append("Joel approval of KIO:\n" + "\n".join(
                f"- [{p.get('context', '')[:30]}] {p.get('description', '')[:80]}"
                for p in genuine_praise))

    if not parts:
        return ""
    return "Evidence (relevance-ranked):\n" + "\n".join(parts[:max_items])


# ═══════════════════════════════════════════════════════════════════════════════
# 7. EVIDENCE-BACKED SELF-MODEL QUERIES
# ═══════════════════════════════════════════════════════════════════════════════

def query_self_model(session_id: str, question: str) -> str:
    """Answer KIO self-model questions with evidence."""
    low = question.lower()

    if any(kw in low for kw in ("what have you gotten wrong", "what did you get wrong",
                                  "what mistakes", "what failures")):
        graph = SemanticGraph(session_id)
        links = graph.attributed_statements(
            USER_KEY, relation="said", stance="observation",
            active_only=True, limit=200,
        )
        failures = []
        for link in links:
            target = getattr(link, "target_name", "") or ""
            prov = getattr(link, "provenance", "") or ""
            if "shared_history: KIO promised but failed" in target or "failure" in prov.lower():
                failures.append(target)
        if failures:
            return "KIO failure history (evidence-backed):\n" + "\n".join(
                f"- {f}" for f in failures[:5])
        return "No recorded KIO failures found in evidence."

    if any(kw in low for kw in ("what have i corrected", "what did i correct",
                                  "corrections")):
        graph = SemanticGraph(session_id)
        links = graph.attributed_statements(
            USER_KEY, relation="said", stance="observation",
            active_only=True, limit=200,
        )
        corrections = []
        for link in links:
            target = getattr(link, "target_name", "") or ""
            if "shared_history: Joel corrected" in target or "correction" in target.lower():
                corrections.append(target)
        if corrections:
            return "Joel correction history (evidence-backed):\n" + "\n".join(
                f"- {c}" for c in corrections[:5])
        return "No recorded Joel corrections found in evidence."

    if any(kw in low for kw in ("how have you changed", "what has changed",
                                  "how has kio evolved")):
        try:
            from mini_kio.memory.kio_self_model import kio_self_brief
            return kio_self_brief()
        except Exception:
            return "KIO self-model under construction."

    return ""
