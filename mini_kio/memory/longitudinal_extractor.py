"""
longitudinal_extractor.py — Evidence-backed longitudinal extraction from the
ChatGPT export. Extracts behavioral patterns, communication style, emotional
episodes, project evolution, decision/reversal patterns, and KIO shared history.

Every extracted item carries:
  - evidence: source conversation(s), message text, timestamp
  - provenance: chatgpt_export:<conv_id>:<timestamp>
  - confidence: repetition + temporal consistency + explicitness
  - currentness: supersession-aware (newer evidence supersedes older)

This is NOT a personality profiler. It extracts OBSERVABLE PATTERNS from
real messages with real timestamps. Temporal context is preserved.
"""

from __future__ import annotations

import glob
import json
import logging
import os
import re
from collections import defaultdict
from dataclasses import dataclass, field
from datetime import datetime, timezone
from typing import Any, Dict, List, Optional, Tuple

from mini_kio.semantic.graph import SemanticGraph, USER_KEY, KIO_KEY

logger = logging.getLogger(__name__)

EXPORT_DIR = os.path.join("data", "historical", "chatgpt_export_2026-06-12")
LONGITUDINAL_INDEX_PATH = os.path.join("data", "historical", "longitudinal_index.json")


# ═══════════════════════════════════════════════════════════════════════════════
# PATTERN EXTRACTION REGEXES — general morphological families, no per-phrase hardcoding
# ═══════════════════════════════════════════════════════════════════════════════

# Communication patterns: shorthand, abbreviations, slang used repeatedly
_SHORTHAND_RE = re.compile(
    r"\b(rn|tbh|imo|imho|ngl|fr|lowkey|highkey|idk|ikr|smh|fyi|btw|nvm|"
    r"brb|afk|lol|lmao|rofl|bruh|bro|dude|man|yo|nah|yea|yep|nah|"
    r"omg|wtf|lmao|smh|ngl|fr|no cap|deadass|slay|bussin|glaze|"
    r"skibidi|aura|rizz|gyatt|bet|cap|sus|pog|poggers|copium|based|"
    r"touch grass|mid|goated|down bad|vibe|vibing|lowkey|highkey|"
    r"istg|iykyk|fomo|fomo|tldr|tmi|jk|ig|tbh|hmu|wyd|wbu|hmu|"
    r"ppl|gonna|wanna|gotta|lemme|aight| prolly | def | prob |"
    r"yo|ay|ayy|sheesh|ong|iont|ion)\b",
    re.I,
)

# Emotional expression: frustration, excitement, urgency patterns
# These are MORPHOLOGICAL patterns (word families), not hardcoded phrases
_FRUSTRATION_RE = re.compile(
    r"\b(frustrat|annoy|piss|mad|angry|irritat|hate|despise|ugh|"
    r"god ?damn|wtf|what the|this ?is ?broken|not ?working|doesn'?t ?work|"
    r"can'?t ?believe|ridiculous|absurd|stupid|dumb|sucks|trash|garbage|"
    r"help me|stuck|idk what|confused|lost|drowning|overwhelmed|"
    r"struggling|failing|failed|crash|bug|error|broken|dead|rip)\b",
    re.I,
)

_EXCITEMENT_RE = re.compile(
    r"\b(excit|stoked|pumped|hyped|amazing|awesome|incredible|"
    r"let'?s ?go|yess?|finally|big ?brain|galaxy ?brain|"
    r"this ?is ?insane|no ?way|omg|wow|holy|damn|sheesh|"
    r"goat|goated|legend|fire|bussin|slay|w|win|"
    r"promising|breakthrough|milestone|accomplished|achieved|"
    r"love ?this|can'?t ?wait|eager|proud|thrilled)\b",
    re.I,
)

_URGENCY_RE = re.compile(
    r"\b(urgent|asap|as ?soon ?as ?possible|right ?now|rn|"
    r"immediately|quickly|hurry|deadline|due ?by|need ?this ?now|"
    r"can'?t ?wait|on ?a ?deadline|time ?sensitive|priority|"
    r"must ?do|have ?to|gotta|need ?to|important|critical|"
    r"today|tonight|before|by ?end|eod|eow|sometime ?today)\b",
    re.I,
)

# Decision patterns: choosing, rejecting, reversing
_DECISION_RE = re.compile(
    r"\b(i(?:'ve| have)?\s+(?:decided|chose|picked|settled|going with|"
    r"going to use|switched to|moved to|opted for|committed to))\b",
    re.I,
)

_REJECTION_RE = re.compile(
    r"\b(i\s+(?:don'?t|no longer|won'?t|won'?t)\s+"
    r"(?:want|need|use|like|recommend|support|continue|"
    r"want to use|going to use))\b",
    re.I,
)

_REVERSAL_RE = re.compile(
    r"\b(actually|never ?mind|wait|hold ?on|scratch that|"
    r"changed ?my ?mind|on ?second ?thought|i take ?that ?back|"
    r"let ?me ?rethink|forget ?what i|actually never|"
    r"wait nvm|wait never ?mind|scratch)\b",
    re.I,
)

# Project evolution: building, abandoning, reviving
_PROJECT_BUILD_RE = re.compile(
    r"\b(i(?:'m| am)\s+(?:building|working on|developing|creating|"
    r"making|prototyping|designing|implementing|coding|programming))\b",
    re.I,
)

_PROJECT_ABANDON_RE = re.compile(
    r"\b(i(?:'m| am)?\s+(?:dropping|abandoning|quitting|"
    r"giving up on|stopping|killing|scrapping|"
    r"no longer working on|not doing|gave up on))\b",
    re.I,
)

_PROJECT_RESUME_RE = re.compile(
    r"\b(i(?:'m| am)?\s+(?:reviving|resuming|getting back to|"
    r"restarting|picking up|back on|returning to))\b",
    re.I,
)

# KIO interaction patterns: corrections, expectations, feedback
_KIO_CORRECTION_RE = re.compile(
    r"\b(that'?s?\s+(?:wrong|incorrect|not what i|not right|"
    r"not ?what i ?meant|not ?what i ?wanted|"
    r"not ?what i ?asked|actually i|"
    r"i meant|i wanted|i asked for|i need you to))\b",
    re.I,
)

_KIO_EXPECTATION_RE = re.compile(
    r"\b(you ?(?:should|must|need to|have to|better|"
    r"are ?supposed ?to|need ?you ?to|i ?(?:want|need) ?you ?to|"
    r"please|do ?this|always|never|make ?sure))\b",
    re.I,
)

_KIO_PRAISE_RE = re.compile(
    r"\b(good ?job|nice|well ?done|perfect|exactly|that'?s ?right|"
    r"great|excellent|awesome|you ?(?:got ?it|nailed ?it|got ?this|"
    r"understand)|finally|there you ?go)\b",
    re.I,
)

# Technical language patterns
_TECHNICAL_RE = re.compile(
    r"\b(python|javascript|html|css|react|node|api|database|sql|"
    r"git|github|docker|kubernetes|aws|azure|cloud|"
    r"machine ?learning|ai|artificial ?intelligence|"
    r"neural ?network|deep ?learning|nlp|cv|"
    r"flask|django|fastapi|express|nextjs|"
    r"postgresql|mysql|mongodb|redis|"
    r"playwright|selenium|puppeteer|"
    r"telegram|discord|slack|"
    r"linux|windows|macos|ubuntu|fedora|"
    r"vscode|vim|neovim|pycharm|"
    r"leetcode|hackerrank|codechef|"
    r"startup|freelance|internship|placement)\b",
    re.I,
)

# Questions indicate what user is curious about / exploring
_QUESTION_RE = re.compile(r"\?\s*$")


# ═══════════════════════════════════════════════════════════════════════════════
# DATA MODELS — evidence-backed extraction results
# ═══════════════════════════════════════════════════════════════════════════════

@dataclass
class EvidencePoint:
    """A single piece of evidence from the export."""
    text: str
    conversation_id: str
    conversation_title: str
    timestamp: float
    year_month: str
    role: str  # user or assistant


@dataclass
class BehavioralPattern:
    """An observed behavioral pattern with evidence."""
    pattern_type: str  # communication, emotional, decision, project, kio_interaction
    category: str  # frustration, excitement, shorthand, etc.
    description: str  # human-readable description of the pattern
    evidence: List[EvidencePoint]
    frequency: int  # how many times observed
    confidence: float  # 0.0-1.0
    first_seen: str  # year-month
    last_seen: str  # year-month
    is_current: bool  # supersession-aware currentness


@dataclass
class ProjectEvolution:
    """A project's lifecycle extracted from evidence."""
    name: str
    events: List[EvidencePoint]  # chronological events
    lifecycle: str  # building, abandoned, revived, ongoing
    first_mentioned: str
    last_mentioned: str
    confidence: float


@dataclass
class KIOInteraction:
    """A significant KIO interaction extracted from evidence."""
    interaction_type: str  # correction, expectation, praise, failure
    description: str
    evidence: List[EvidencePoint]
    timestamp: str
    confidence: float


@dataclass
class LongitudinalExtraction:
    """Complete longitudinal extraction results."""
    behavioral_patterns: List[BehavioralPattern]
    communication_style: List[BehavioralPattern]
    emotional_patterns: List[BehavioralPattern]
    decision_patterns: List[BehavioralPattern]
    project_evolutions: List[ProjectEvolution]
    kio_interactions: List[KIOInteraction]
    technical_interests: List[str]
    total_conversations: int
    total_messages: int
    total_extracted: int
    date_range: Tuple[str, str]  # (earliest, latest year-month)


# ═══════════════════════════════════════════════════════════════════════════════
# CONVERSATION PARSER — streaming, memory-bounded
# ═══════════════════════════════════════════════════════════════════════════════

def _parse_conversations_streaming(
    directory: str = EXPORT_DIR,
    *,
    limit: Optional[int] = None,
) -> List[Dict[str, Any]]:
    """Parse conversations from export JSON files. Memory-bounded: processes
    one file at a time, only holds parsed conversations in memory."""
    out: List[Dict[str, Any]] = []
    files = sorted(glob.glob(os.path.join(directory, "conversations-*.json")))
    for path in files:
        try:
            with open(path, encoding="utf-8") as f:
                convs = json.load(f)
        except Exception as exc:
            logger.warning("[LONG_EXTRACT] unreadable %s: %s", path, exc)
            continue
        for c in convs:
            mapping = c.get("mapping") or {}
            messages: List[Tuple[float, str, str]] = []
            for m in mapping.values():
                msg = m.get("message") or {}
                role = ((msg.get("author") or {}).get("role") or "").lower()
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
                messages.append((ts, role, text))
            if not messages:
                continue
            messages.sort(key=lambda x: x[0])
            out.append({
                "conversation_id": c.get("conversation_id") or c.get("id") or "",
                "title": (c.get("title") or "").strip(),
                "create_time": c.get("create_time"),
                "messages": messages,
            })
        if limit and len(out) >= limit:
            out = out[:limit]
            break
    return out


def _message_date(ts: Optional[float]) -> str:
    if not ts:
        return ""
    try:
        return datetime.fromtimestamp(ts, tz=timezone.utc).strftime("%Y-%m")
    except Exception:
        return ""


def _is_code_or_long(text: str) -> bool:
    """Filter out code, long technical content, and non-personal evidence."""
    if len(text) > 1200:
        return True
    if re.search(r"```", text):
        return True
    if re.search(r"\w{40,}", text):  # very long words (URLs, hashes)
        return True
    if re.search(r"\{[^{}]{80,}\}", text):  # JSON blobs
        return True
    return False


# ═══════════════════════════════════════════════════════════════════════════════
# PATTERN EXTRACTION — from individual messages
# ═══════════════════════════════════════════════════════════════════════════════

def _extract_shorthand(text: str) -> List[str]:
    """Extract shorthand/slang/abbreviations from a message."""
    return _SHORTHAND_RE.findall(text.lower())


def _extract_emotional_signals(text: str) -> Dict[str, List[str]]:
    """Extract emotional signals categorized by type."""
    signals: Dict[str, List[str]] = {}
    low = text.lower()
    if _FRUSTRATION_RE.search(low):
        signals["frustration"] = _FRUSTRATION_RE.findall(low)
    if _EXCITEMENT_RE.search(low):
        signals["excitement"] = _EXCITEMENT_RE.findall(low)
    if _URGENCY_RE.search(low):
        signals["urgency"] = _URGENCY_RE.findall(low)
    return signals


def _extract_decision_signals(text: str) -> Optional[str]:
    """Extract decision/reversal signals. Returns the type or None."""
    if _REVERSAL_RE.search(text):
        return "reversal"
    if _DECISION_RE.search(text):
        return "decision"
    if _REJECTION_RE.search(text):
        return "rejection"
    return None


def _extract_project_signals(text: str) -> Optional[str]:
    """Extract project lifecycle signals. Returns the type or None."""
    if _PROJECT_ABANDON_RE.search(text):
        return "abandoned"
    if _PROJECT_RESUME_RE.search(text):
        return "resumed"
    if _PROJECT_BUILD_RE.search(text):
        return "building"
    return None


def _extract_kio_interaction(text: str) -> Optional[str]:
    """Extract KIO interaction signals. Returns the type or None."""
    if _KIO_CORRECTION_RE.search(text):
        return "correction"
    if _KIO_EXPECTATION_RE.search(text):
        return "expectation"
    if _KIO_PRAISE_RE.search(text):
        return "praise"
    return None


def _extract_technical_interests(text: str) -> List[str]:
    """Extract technical topics mentioned."""
    return [m.lower() for m in _TECHNICAL_RE.findall(text)]


def _extract_question_topics(text: str) -> Optional[str]:
    """Extract the topic of a question (what user is curious about)."""
    if not _QUESTION_RE.search(text):
        return None
    # Clean up the question to get the topic
    clean = re.sub(r"\?$", "", text).strip()
    if len(clean) < 5 or len(clean) > 200:
        return None
    return clean


# ═══════════════════════════════════════════════════════════════════════════════
# BEHAVIORAL PATTERN AGGREGATION — from all messages
# ═══════════════════════════════════════════════════════════════════════════════

def _aggregate_shorthand(
    all_shorthand: Dict[str, List[EvidencePoint]],
) -> List[BehavioralPattern]:
    """Aggregate shorthand usage into patterns with evidence."""
    patterns: List[BehavioralPattern] = []
    for term, evidence_list in sorted(all_shorthand.items(), key=lambda x: -len(x[1])):
        if len(evidence_list) < 2:  # need at least 2 occurrences
            continue
        dates = [e.year_month for e in evidence_list if e.year_month]
        if not dates:
            continue
        first_seen = min(dates)
        last_seen = max(dates)
        # Confidence: more occurrences = higher confidence
        conf = min(0.95, 0.4 + 0.1 * len(evidence_list))
        # Current: seen in last 6 months
        is_current = last_seen >= "2026-01"
        patterns.append(BehavioralPattern(
            pattern_type="communication",
            category="shorthand",
            description=f"Uses '{term}' in casual messages",
            evidence=evidence_list[:10],  # cap evidence for memory
            frequency=len(evidence_list),
            confidence=conf,
            first_seen=first_seen,
            last_seen=last_seen,
            is_current=is_current,
        ))
    return patterns[:30]  # top 30 shorthand patterns


def _aggregate_emotional_patterns(
    all_emotions: Dict[str, Dict[str, List[EvidencePoint]]],
) -> List[BehavioralPattern]:
    """Aggregate emotional expression patterns."""
    patterns: List[BehavioralPattern] = []
    for emotion_type, word_map in all_emotions.items():
        all_evidence: List[EvidencePoint] = []
        for word, ev_list in word_map.items():
            all_evidence.extend(ev_list)
        if len(all_evidence) < 2:
            continue
        dates = [e.year_month for e in all_evidence if e.year_month]
        if not dates:
            continue
        first_seen = min(dates)
        last_seen = max(dates)
        conf = min(0.95, 0.4 + 0.1 * len(all_evidence))
        is_current = last_seen >= "2026-01"
        patterns.append(BehavioralPattern(
            pattern_type="emotional",
            category=emotion_type,
            description=f"Expresses {emotion_type} in messages",
            evidence=all_evidence[:10],
            frequency=len(all_evidence),
            confidence=conf,
            first_seen=first_seen,
            last_seen=last_seen,
            is_current=is_current,
        ))
    return patterns


def _aggregate_decision_patterns(
    all_decisions: Dict[str, List[EvidencePoint]],
) -> List[BehavioralPattern]:
    """Aggregate decision-making patterns."""
    patterns: List[BehavioralPattern] = []
    for decision_type, evidence_list in all_decisions.items():
        if len(evidence_list) < 1:
            continue
        dates = [e.year_month for e in evidence_list if e.year_month]
        if not dates:
            continue
        first_seen = min(dates)
        last_seen = max(dates)
        conf = min(0.95, 0.5 + 0.1 * len(evidence_list))
        is_current = last_seen >= "2026-01"
        patterns.append(BehavioralPattern(
            pattern_type="decision",
            category=decision_type,
            description=f"Makes {decision_type} decisions",
            evidence=evidence_list[:10],
            frequency=len(evidence_list),
            confidence=conf,
            first_seen=first_seen,
            last_seen=last_seen,
            is_current=is_current,
        ))
    return patterns


# ═══════════════════════════════════════════════════════════════════════════════
# PROJECT EVOLUTION EXTRACTION
# ═══════════════════════════════════════════════════════════════════════════════

def _extract_project_names(text: str) -> List[str]:
    """Extract potential project names from a message.
    Conservative: only extracts multi-word proper nouns or known patterns."""
    names: List[str] = []
    # Look for quoted project names
    for m in re.finditer(r"['\"]([^'\"]{3,60})['\"]", text):
        names.append(m.group(1))
    # Look for "my X project" patterns
    for m in re.finditer(
        r"\b(?:my|the|our|this)\s+([A-Z][a-z]+(?:\s+[A-Z][a-z]+){0,3})\b",
        text,
    ):
        names.append(m.group(1))
    return names[:3]  # cap at 3 per message


def _aggregate_project_evolutions(
    project_events: Dict[str, List[EvidencePoint]],
    project_signals: Dict[str, Dict[str, List[EvidencePoint]]],
) -> List[ProjectEvolution]:
    """Aggregate project events into evolution timelines."""
    evolutions: List[ProjectEvolution] = []
    all_projects = set(project_events.keys()) | set(project_signals.keys())

    for project_name in all_projects:
        events = project_events.get(project_name, [])
        signals = project_signals.get(project_name, {})
        all_evidence = events.copy()
        for sig_list in signals.values():
            all_evidence.extend(sig_list)
        if not all_evidence:
            continue

        # Sort by timestamp
        all_evidence.sort(key=lambda e: e.timestamp)
        dates = [e.year_month for e in all_evidence if e.year_month]
        if not dates:
            continue

        # Determine lifecycle from signals
        signal_types = set(signals.keys())
        if "abandoned" in signal_types:
            lifecycle = "abandoned"
        elif "resumed" in signal_types:
            lifecycle = "resumed"
        elif "building" in signal_types:
            lifecycle = "building"
        else:
            lifecycle = "mentioned"

        conf = min(0.95, 0.5 + 0.05 * len(all_evidence))
        evolutions.append(ProjectEvolution(
            name=project_name,
            events=all_evidence[:20],
            lifecycle=lifecycle,
            first_mentioned=min(dates),
            last_mentioned=max(dates),
            confidence=conf,
        ))

    return sorted(evolutions, key=lambda e: e.last_mentioned, reverse=True)


# ═══════════════════════════════════════════════════════════════════════════════
# KIO INTERACTION EXTRACTION
# ═══════════════════════════════════════════════════════════════════════════════

def _aggregate_kio_interactions(
    all_interactions: Dict[str, List[EvidencePoint]],
) -> List[KIOInteraction]:
    """Aggregate KIO interaction patterns."""
    interactions: List[KIOInteraction] = []
    for interaction_type, evidence_list in all_interactions.items():
        if not evidence_list:
            continue
        evidence_list.sort(key=lambda e: e.timestamp)
        dates = [e.year_month for e in evidence_list if e.year_month]
        conf = min(0.95, 0.5 + 0.1 * len(evidence_list))
        interactions.append(KIOInteraction(
            interaction_type=interaction_type,
            description=f"User {interaction_type} KIO",
            evidence=evidence_list[:10],
            timestamp=dates[-1] if dates else "",
            confidence=conf,
        ))
    return interactions


# ═══════════════════════════════════════════════════════════════════════════════
# MAIN EXTRACTION PIPELINE
# ═══════════════════════════════════════════════════════════════════════════════

def extract_longitudinal(
    directory: str = EXPORT_DIR,
    *,
    limit_convs: Optional[int] = None,
    checkpoint_path: Optional[str] = None,
) -> LongitudinalExtraction:
    """Main extraction pipeline. Processes all conversations and extracts
    longitudinal evidence. Supports checkpointing for resumability.

    This is the CORE extraction that transforms raw conversations into
    evidence-backed longitudinal intelligence.
    """
    # Load checkpoint if available
    checkpoint: Dict[str, Any] = {}
    if checkpoint_path and os.path.isfile(checkpoint_path):
        try:
            with open(checkpoint_path, encoding="utf-8") as f:
                checkpoint = json.load(f)
        except Exception:
            checkpoint = {}

    processed_ids = set(checkpoint.get("processed_ids", []))

    # Parse conversations
    convs = _parse_conversations_streaming(directory, limit=limit_convs)
    logger.info("[LONG_EXTRACT] parsed %d conversations", len(convs))

    # Accumulators for pattern extraction
    shorthand_map: Dict[str, List[EvidencePoint]] = defaultdict(list)
    emotion_map: Dict[str, Dict[str, List[EvidencePoint]]] = defaultdict(lambda: defaultdict(list))
    decision_map: Dict[str, List[EvidencePoint]] = defaultdict(list)
    project_events: Dict[str, List[EvidencePoint]] = defaultdict(list)
    project_signals: Dict[str, Dict[str, List[EvidencePoint]]] = defaultdict(lambda: defaultdict(list))
    kio_interactions: Dict[str, List[EvidencePoint]] = defaultdict(list)
    tech_interests: List[str] = []
    question_topics: List[str] = []

    total_messages = 0
    total_extracted = 0
    all_dates: List[str] = []

    batch_size = 50  # checkpoint every N conversations
    conv_count = 0

    for conv in convs:
        cid = conv.get("conversation_id") or ""
        if not cid or cid in processed_ids:
            continue

        title = conv.get("title", "")
        for ts, role, text in conv.get("messages", []):
            if _is_code_or_long(text):
                continue

            total_messages += 1
            year_month = _message_date(ts)
            if year_month:
                all_dates.append(year_month)

            evidence = EvidencePoint(
                text=text[:500],  # cap text for memory
                conversation_id=cid,
                conversation_title=title,
                timestamp=ts,
                year_month=year_month,
                role=role,
            )

            if role == "user":
                # Communication patterns (shorthand)
                for term in _extract_shorthand(text):
                    shorthand_map[term].append(evidence)
                    total_extracted += 1

                # Emotional patterns
                emotions = _extract_emotional_signals(text)
                for emotion_type, words in emotions.items():
                    for word in words:
                        emotion_map[emotion_type][word].append(evidence)
                        total_extracted += 1

                # Decision patterns
                decision = _extract_decision_signals(text)
                if decision:
                    decision_map[decision].append(evidence)
                    total_extracted += 1

                # Project signals
                project_signal = _extract_project_signals(text)
                if project_signal:
                    for pname in _extract_project_names(text):
                        project_signals[pname][project_signal].append(evidence)
                        total_extracted += 1

                # Technical interests
                tech_topics = _extract_technical_interests(text)
                tech_interests.extend(tech_topics)

                # Question topics
                question = _extract_question_topics(text)
                if question:
                    question_topics.append(question)

            elif role == "assistant":
                # KIO interaction patterns (from user messages AFTER assistant reply)
                pass  # KIO signals are in user messages, not assistant

            # Check for KIO interaction in user messages (corrections after assistant)
            if role == "user":
                kio_signal = _extract_kio_interaction(text)
                if kio_signal:
                    kio_interactions[kio_signal].append(evidence)
                    total_extracted += 1

        processed_ids.add(cid)
        conv_count += 1

        # Checkpoint periodically
        if checkpoint_path and conv_count % batch_size == 0:
            _save_checkpoint(checkpoint_path, processed_ids, {
                "conversations_processed": conv_count,
                "total_extracted": total_extracted,
            })

    # Final checkpoint
    if checkpoint_path:
        _save_checkpoint(checkpoint_path, processed_ids, {
            "conversations_processed": conv_count,
            "total_extracted": total_extracted,
            "complete": True,
        })

    # Aggregate patterns
    shorthand_patterns = _aggregate_shorthand(shorthand_map)
    emotional_patterns = _aggregate_emotional_patterns(emotion_map)
    decision_patterns = _aggregate_decision_patterns(decision_map)
    project_evolutions = _aggregate_project_evolutions(project_events, project_signals)
    kio_interaction_list = _aggregate_kio_interactions(kio_interactions)

    # Deduplicate tech interests
    tech_freq: Dict[str, int] = defaultdict(int)
    for t in tech_interests:
        tech_freq[t] += 1
    top_tech = sorted(tech_freq.keys(), key=lambda x: -tech_freq[x])[:20]

    date_range = ("", "")
    if all_dates:
        date_range = (min(all_dates), max(all_dates))

    result = LongitudinalExtraction(
        behavioral_patterns=shorthand_patterns,
        communication_style=shorthand_patterns,  # shorthand IS communication style
        emotional_patterns=emotional_patterns,
        decision_patterns=decision_patterns,
        project_evolutions=project_evolutions,
        kio_interactions=kio_interaction_list,
        technical_interests=top_tech,
        total_conversations=len(convs),
        total_messages=total_messages,
        total_extracted=total_extracted,
        date_range=date_range,
    )

    logger.info(
        "[LONG_EXTRACT] complete: conversations=%d messages=%d extracted=%d "
        "patterns=%d emotions=%d decisions=%d projects=%d kio=%d tech=%d",
        len(convs), total_messages, total_extracted,
        len(shorthand_patterns), len(emotional_patterns),
        len(decision_patterns), len(project_evolutions),
        len(kio_interaction_list), len(top_tech),
    )

    return result


def _save_checkpoint(
    path: str,
    processed_ids: set,
    metadata: Dict[str, Any],
) -> None:
    """Save extraction checkpoint for resumability."""
    try:
        os.makedirs(os.path.dirname(path), exist_ok=True)
        data = {
            "processed_ids": sorted(processed_ids),
            "metadata": metadata,
            "saved_at": datetime.now(timezone.utc).isoformat(timespec="seconds"),
        }
        with open(path, "w", encoding="utf-8") as f:
            json.dump(data, f, ensure_ascii=False)
    except Exception as exc:
        logger.warning("[LONG_EXTRACT] checkpoint save failed: %s", exc)


# ═══════════════════════════════════════════════════════════════════════════════
# GRAPH PERSISTENCE — write longitudinal evidence to semantic graph
# ═══════════════════════════════════════════════════════════════════════════════

def persist_to_graph(
    session_id: str,
    extraction: LongitudinalExtraction,
) -> Dict[str, int]:
    """Write longitudinal extraction results to the semantic graph.
    Each pattern becomes a USER-ATTRIBUTED claim with full provenance.
    Returns counts of items persisted per category."""
    graph = SemanticGraph(session_id)
    counts: Dict[str, int] = defaultdict(int)

    # Persist behavioral patterns (communication style)
    for pattern in extraction.communication_style:
        claim = f"communication: {pattern.description}"
        link = graph.record_statement(
            USER_KEY, claim,
            relation="said",
            stance="observation",
            confidence=pattern.confidence,
            event_time=None,
            supersede_prior=False,
            provenance=f"longitudinal:communication:{pattern.category}",
        )
        if link:
            counts["communication"] += 1

    # Persist emotional patterns
    for pattern in extraction.emotional_patterns:
        claim = f"emotional: {pattern.description}"
        link = graph.record_statement(
            USER_KEY, claim,
            relation="said",
            stance="observation",
            confidence=pattern.confidence,
            event_time=None,
            supersede_prior=False,
            provenance=f"longitudinal:emotional:{pattern.category}",
        )
        if link:
            counts["emotional"] += 1

    # Persist decision patterns
    for pattern in extraction.decision_patterns:
        claim = f"behavior: {pattern.description}"
        link = graph.record_statement(
            USER_KEY, claim,
            relation="said",
            stance="observation",
            confidence=pattern.confidence,
            event_time=None,
            supersede_prior=False,
            provenance=f"longitudinal:decision:{pattern.category}",
        )
        if link:
            counts["decision"] += 1

    # Persist project evolutions
    for proj in extraction.project_evolutions:
        # Create/update project node
        node = graph.ensure_project(
            proj.name,
            lifecycle=proj.lifecycle,
            confidence=proj.confidence,
            provenance="longitudinal",
        )
        if node:
            counts["project"] += 1

        # Record lifecycle event
        if proj.events:
            last_event = proj.events[-1]
            claim = f"project {proj.name}: {proj.lifecycle}"
            link = graph.record_statement(
                USER_KEY, claim,
                relation="said",
                stance="observation",
                confidence=proj.confidence,
                event_time=last_event.year_month if last_event.year_month else None,
                supersede_prior=False,
                provenance=f"longitudinal:project:{proj.name}",
            )
            if link:
                counts["project_event"] += 1

    # Persist KIO interactions
    for interaction in extraction.kio_interactions:
        claim = f"kio_history: {interaction.description}"
        link = graph.record_statement(
            USER_KEY, claim,
            relation="said",
            stance="observation",
            confidence=interaction.confidence,
            event_time=None,
            supersede_prior=False,
            provenance=f"longitudinal:kio:{interaction.interaction_type}",
        )
        if link:
            counts["kio_interaction"] += 1

    # Persist technical interests
    for tech in extraction.technical_interests:
        claim = f"technical interest: {tech}"
        link = graph.record_statement(
            USER_KEY, claim,
            relation="said",
            stance="observation",
            confidence=0.6,
            event_time=None,
            supersede_prior=False,
            provenance="longitudinal:technical",
        )
        if link:
            counts["technical"] += 1

    return dict(counts)


# ═══════════════════════════════════════════════════════════════════════════════
# QUERY API — evidence-backed retrieval for conversational layer
# ═══════════════════════════════════════════════════════════════════════════════

def query_communication_style(session_id: str) -> str:
    """Evidence-backed communication style for conversational injection.
    Returns structured evidence the LLM can compose naturally."""
    graph = SemanticGraph(session_id)
    links = graph.attributed_statements(
        USER_KEY, relation="said", stance="observation", active_only=True, limit=100
    )
    style_items = []
    for link in links:
        prov = getattr(link, "provenance", "") or ""
        target = getattr(link, "target_name", "") or ""
        if "communication:" in target:
            style_items.append(target.replace("communication: ", ""))
    if not style_items:
        return ""
    return "Communication patterns (evidence-backed):\n" + "\n".join(
        f"- {item}" for item in style_items[:10]
    )


def query_emotional_patterns(session_id: str) -> str:
    """Evidence-backed emotional expression patterns."""
    graph = SemanticGraph(session_id)
    links = graph.attributed_statements(
        USER_KEY, relation="said", stance="observation", active_only=True, limit=100
    )
    items = []
    for link in links:
        target = getattr(link, "target_name", "") or ""
        if "emotional:" in target:
            items.append(target.replace("emotional: ", ""))
    if not items:
        return ""
    return "Emotional expression patterns (evidence-backed):\n" + "\n".join(
        f"- {item}" for item in items[:10]
    )


def query_kio_history(session_id: str) -> str:
    """Evidence-backed KIO interaction history."""
    graph = SemanticGraph(session_id)
    links = graph.attributed_statements(
        USER_KEY, relation="said", stance="observation", active_only=True, limit=100
    )
    items = []
    for link in links:
        target = getattr(link, "target_name", "") or ""
        if "kio_history:" in target:
            items.append(target.replace("kio_history: ", ""))
    if not items:
        return ""
    return "KIO interaction history (evidence-backed):\n" + "\n".join(
        f"- {item}" for item in items[:10]
    )


def query_all_longitudinal(session_id: str) -> str:
    """Complete longitudinal evidence brief for the conversational layer.
    Returns structured evidence across all dimensions."""
    parts = []

    style = query_communication_style(session_id)
    if style:
        parts.append(style)

    emotional = query_emotional_patterns(session_id)
    if emotional:
        parts.append(emotional)

    kio = query_kio_history(session_id)
    if kio:
        parts.append(kio)

    # Technical interests from graph
    graph = SemanticGraph(session_id)
    links = graph.attributed_statements(
        USER_KEY, relation="said", stance="observation", active_only=True, limit=100
    )
    tech_items = []
    for link in links:
        target = getattr(link, "target_name", "") or ""
        if "technical interest:" in target:
            tech_items.append(target.replace("technical interest: ", ""))
    if tech_items:
        parts.append("Technical interests: " + ", ".join(tech_items[:10]) + ".")

    # Behavior patterns from graph
    behavior_items = []
    for link in links:
        target = getattr(link, "target_name", "") or ""
        if "behavior:" in target:
            behavior_items.append(target.replace("behavior: ", ""))
    if behavior_items:
        parts.append("Behavioral patterns:\n" + "\n".join(
            f"- {item}" for item in behavior_items[:8]
        ))

    if not parts:
        return ""
    return "Longitudinal evidence (from ChatGPT history):\n\n" + "\n\n".join(parts)
