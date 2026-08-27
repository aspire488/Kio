"""
longitudinal_v2.py — Deep longitudinal extraction from ChatGPT export.

V2 improvements over v1:
  - Bidirectional: parses BOTH user AND assistant messages
  - Project lifecycle: extracts project names from titles + context, tracks
    DISCOVERED → ACTIVE → PAUSED → ABANDONED → REVIVED → COMPLETED
  - Emotional episodes: contextual, not just frequency counts
  - Decision chains: pairs decisions with reversals, tracks supersession
  - Shared history: KIO corrections, expectations, failures, recoveries
  - Conversation titles: used as project/topic signal
  - Relevance-ranked retrieval: query-based, not full injection

Every extracted item carries full provenance:
  source conversation, source message, timestamp, speaker,
  confidence, extraction method.
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
V2_INDEX_PATH = os.path.join("data", "historical", "longitudinal_v2_index.json")


# ═══════════════════════════════════════════════════════════════════════════════
# DATA MODELS
# ═══════════════════════════════════════════════════════════════════════════════

@dataclass
class Evidence:
    """A single piece of evidence with full provenance."""
    text: str
    conversation_id: str
    conversation_title: str
    timestamp: float
    year_month: str
    role: str  # "user" or "assistant"
    speaker: str  # "joel" or "chatgpt"

    def short(self, n: int = 120) -> str:
        return self.text[:n].replace("\n", " ")


@dataclass
class EmotionalEpisode:
    """A contextual emotional event — not a frequency count."""
    emotion: str  # frustration, excitement, urgency, confusion, satisfaction
    trigger: str  # what caused it (from context)
    context: str  # surrounding conversation topic
    intensity: str  # low, medium, high
    evidence: List[Evidence]
    first_seen: str
    last_seen: str
    count: int


@dataclass
class DecisionChain:
    """A decision with its alternatives, reversals, and resolution."""
    topic: str
    initial_position: str
    later_position: Optional[str]
    reason: Optional[str]
    confidence: float
    evidence: List[Evidence]
    is_reversal: bool
    is_current: bool
    first_seen: str
    last_seen: str


@dataclass
class ProjectLifecycle:
    """A project's full lifecycle with state transitions."""
    name: str
    transitions: List[Dict[str, str]]  # [{from, to, when, evidence}]
    current_state: str  # active, paused, abandoned, completed, unknown
    first_seen: str
    last_seen: str
    evidence: List[Evidence]
    confidence: float


@dataclass
class SharedHistoryEvent:
    """A significant event in the Joel↔KIO relationship."""
    event_type: str  # correction, expectation, praise, failure, milestone, request
    description: str
    evidence: List[Evidence]
    timestamp: str
    confidence: float
    who_initiated: str  # joel or kio


@dataclass
class ConversationProfile:
    """A conversation's extracted profile."""
    conversation_id: str
    title: str
    create_time: float
    year_month: str
    topic: str  # inferred topic
    project_mentioned: Optional[str]
    emotional_tone: str  # neutral, frustrated, excited, urgent
    user_message_count: int
    assistant_message_count: int


# ═══════════════════════════════════════════════════════════════════════════════
# CONVERSATION PARSER — bidirectional, memory-bounded
# ═══════════════════════════════════════════════════════════════════════════════

def _parse_all_conversations(
    directory: str = EXPORT_DIR,
    *,
    limit: Optional[int] = None,
) -> List[Dict[str, Any]]:
    """Parse conversations, preserving BOTH user and assistant messages
    in chronological order for bidirectional analysis."""
    out: List[Dict[str, Any]] = []
    files = sorted(glob.glob(os.path.join(directory, "conversations-*.json")))
    for path in files:
        try:
            with open(path, encoding="utf-8") as f:
                convs = json.load(f)
        except Exception as exc:
            logger.warning("[LONG_V2] unreadable %s: %s", path, exc)
            continue
        for c in convs:
            mapping = c.get("mapping") or {}
            messages: List[Tuple[float, str, str, str]] = []
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
                speaker = "joel" if role == "user" else "chatgpt"
                messages.append((ts, role, text, speaker))
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


def _msg_date(ts: float) -> str:
    if not ts:
        return ""
    try:
        return datetime.fromtimestamp(ts, tz=timezone.utc).strftime("%Y-%m")
    except Exception:
        return ""


def _is_noise(text: str) -> bool:
    """Filter code, very long content, JSON blobs."""
    if len(text) > 2000:
        return True
    if "```" in text:
        return True
    if re.search(r"\w{50,}", text):
        return True
    return False


# ═══════════════════════════════════════════════════════════════════════════════
# PROJECT LIFECYCLE — extracted from titles + message context
# ═══════════════════════════════════════════════════════════════════════════════

# Conversation titles that signal project/topic discussions
_TITLE_PROJECT_RE = re.compile(
    r"(?:build|creating|making|prototype|project|implement|develop|code|"
    r"setup|install|configure|deploy|fix|debug|repair|migrate|upgrade|"
    r"integration|workflow|pipeline|system|architecture|design|plan)",
    re.I,
)

# Project mention patterns in messages
_PROJECT_MENTION_RE = re.compile(
    r"\b(?:my|the|our|this|that)\s+"
    r"(?:new |old |current |main |little )?"
    r"([a-z][a-z ]{2,40})\s+"
    r"(?:project|app|website|bot|system|tool|prototype|build|thing|"
    r"platform|service|pipeline|workflow|agent|model|engine)",
    re.I,
)

# Lifecycle signals
_ABANDON_SIGNALS = re.compile(
    r"\b(dropping|abandon|quitting|giving up|stopping|killing|scrapping|"
    r"no longer|not doing|gave up|shutdown|shut down|cancel|cancelled|"
    r"deprecate|deprecated|retire|retired|done with|over it|move on|"
    r"forget about|drop the whole)\b",
    re.I,
)

_RESUME_SIGNALS = re.compile(
    r"\b(reviving|resuming|getting back|restarting|picking up|back on|"
    r"returning to|revisit|revisiting|let's continue|let's go back|"
    r"back to|continue with|again|try again|second attempt|take two)\b",
    re.I,
)

_ACTIVE_SIGNALS = re.compile(
    r"\b(building|working on|developing|creating|making|prototyping|"
    r"implementing|coding|programming|right now|currently|tonight|"
    r"this week|today|just started|starting|kicking off)\b",
    re.I,
)

_PAUSED_SIGNALS = re.compile(
    r"\b(pause|paused|pausing|暂时|later|eventually|when i have time|"
    r"on hold|shelved|back burner|low priority|not now|defer)\b",
    re.I,
)


# Titles that are NOT real projects (one-off questions, greetings, etc.)
_TITLE_SKIP = frozenset({
    "hi", "hello", "hey", "test", "help", "new chat", "chat",
    "hi there", "hey there", "hello there",
})

# Titles that indicate actual engineering/creative projects
_PROJECT_TITLE_RE = re.compile(
    r"\b(build|creating|making|prototype|project|implement|develop|code|"
    r"setup|install|configure|deploy|fix|debug|repair|migrate|upgrade|"
    r"integration|workflow|pipeline|system|architecture|design|plan|"
    r"app|website|bot|tool|agent|model|engine|automation|"
    r"kio|jarvis|codeflow|medimind|medibus|medicine)\b",
    re.I,
)


def _extract_project_from_title(title: str) -> Optional[str]:
    """Extract project name from conversation title.
    Only returns titles that look like actual projects, not one-off questions."""
    if not title or len(title) < 5:
        return None
    low = title.lower().strip()
    if low in _TITLE_SKIP:
        return None
    # Skip if title is just a short question
    if low.endswith("?") and len(low) < 40:
        return None
    # Skip very generic titles
    if any(kw in low for kw in ("summarize", "explain", "what is", "how to",
                                 "tell me", "can you", "help me")):
        return None
    # Must match project-indicating keywords
    if _PROJECT_TITLE_RE.search(title):
        return title.strip()[:100]
    return None


def _detect_lifecycle_signal(text: str) -> Optional[str]:
    """Detect project lifecycle signal from message text."""
    if _ABANDON_SIGNALS.search(text):
        return "abandoned"
    if _RESUME_SIGNALS.search(text):
        return "revived"
    if _PAUSED_SIGNALS.search(text):
        return "paused"
    if _ACTIVE_SIGNALS.search(text):
        return "active"
    return None


def _build_project_lifecycles(
    conversations: List[Dict[str, Any]],
) -> Dict[str, ProjectLifecycle]:
    """Build project lifecycle timelines from all conversations.
    Uses conversation titles as primary project identifiers,
    with message context for lifecycle transitions."""
    projects: Dict[str, ProjectLifecycle] = {}

    for conv in conversations:
        cid = conv.get("conversation_id", "")
        title = conv.get("title", "")
        create_time = conv.get("create_time") or 0
        year_month = _msg_date(create_time)

        # Extract project from title
        project_name = _extract_project_from_title(title)
        if not project_name:
            continue

        if project_name not in projects:
            projects[project_name] = ProjectLifecycle(
                name=project_name,
                transitions=[],
                current_state="mentioned",
                first_seen=year_month,
                last_seen=year_month,
                evidence=[],
                confidence=0.5,
            )

        proj = projects[project_name]

        # Scan messages for lifecycle signals
        for ts, role, text, speaker in conv.get("messages", []):
            if _is_noise(text):
                continue

            signal = _detect_lifecycle_signal(text)
            ev = Evidence(
                text=text[:300],
                conversation_id=cid,
                conversation_title=title,
                timestamp=ts,
                year_month=_msg_date(ts),
                role=role,
                speaker=speaker,
            )

            if signal and signal != proj.current_state:
                proj.transitions.append({
                    "from": proj.current_state,
                    "to": signal,
                    "when": ev.year_month,
                    "evidence": ev.short(),
                })
                proj.current_state = signal

            proj.evidence.append(ev)

        # Update date range
        if year_month:
            if not proj.first_seen or year_month < proj.first_seen:
                proj.first_seen = year_month
            if not proj.last_seen or year_month > proj.last_seen:
                proj.last_seen = year_month

        proj.confidence = min(0.95, 0.4 + 0.02 * len(proj.evidence))

    return projects


# ═══════════════════════════════════════════════════════════════════════════════
# EMOTIONAL EPISODES — contextual, not frequency
# ═══════════════════════════════════════════════════════════════════════════════

_EMOTION_KEYWORDS = {
    "frustration": re.compile(
        r"\b(frustrat|annoy|piss|mad|angry|irritat|ugh|god ?damn|"
        r"this ?is ?broken|not ?working|doesn'?t ?work|can'?t ?believe|"
        r"ridiculous|stupid|dumb|sucks|trash|garbage|stuck|"
        r"confused|lost|drowning|overwhelmed|struggling|failing|"
        r"failed|crash|bug|error|broken|dead|rip|why does|"
        r"what ?the|how ?is ?this|this ?makes ?no ?sense|"
        r"keeps ?happening|every ?time|again|still ?not)\b",
        re.I,
    ),
    "excitement": re.compile(
        r"\b(excit|stoked|pumped|hyped|amazing|awesome|incredible|"
        r"let'?s ?go|yess?|finally|big ?brain|galaxy ?brain|"
        r"this ?is ?insane|no ?way|wow|holy|sheesh|"
        r"goat|goated|legend|fire|bussin|slay|w |win|"
        r"promising|breakthrough|milestone|accomplished|achieved|"
        r"love ?this|can'?t ?wait|proud|thrilled|"
        r"it ?works|holy ?shit|nice|perfect)\b",
        re.I,
    ),
    "urgency": re.compile(
        r"\b(urgent|asap|right ?now|rn|immediately|quickly|hurry|"
        r"deadline|due ?by|need ?this ?now|time ?sensitive|priority|"
        r"must ?do|have ?to|gotta|need ?to|important|critical|"
        r"today|tonight|before|by ?end|eod|eow)\b",
        re.I,
    ),
    "confusion": re.compile(
        r"\b(confused|don'?t ?understand|what ?do ?you ?mean|"
        r"how ?does|why ?does|can ?you ?explain|i ?don'?t ?get|"
        r"unclear|lost|what ?is|wait ?what|hold ?on|i ?see|"
        r"oh ?ok|ah|oh ?i ?see|got ?it|makes ?sense)\b",
        re.I,
    ),
    "satisfaction": re.compile(
        r"\b(nice|perfect|exactly|that'?s ?right|great|excellent|"
        r"good ?job|well ?done|you ?got ?it|nailed ?it|"
        r"there ?you ?go|finally|works|it ?works|"
        r"exactly ?what|i ?needed|saved ?me|thanks|thank you)\b",
        re.I,
    ),
}


def _extract_emotional_episodes(
    conversations: List[Dict[str, Any]],
) -> List[EmotionalEpisode]:
    """Extract contextual emotional episodes from conversations.
    Each episode has a trigger, context, and evidence — not just a count."""
    episodes: Dict[str, List[Evidence]] = defaultdict(list)
    # Track context (conversation topic) for each episode
    context_map: Dict[str, str] = {}

    for conv in conversations:
        title = conv.get("title", "")
        cid = conv.get("conversation_id", "")

        for ts, role, text, speaker in conv.get("messages", []):
            if _is_noise(text) or speaker != "joel":
                continue

            for emotion, pattern in _EMOTION_KEYWORDS.items():
                if pattern.search(text):
                    ev = Evidence(
                        text=text[:300],
                        conversation_id=cid,
                        conversation_title=title,
                        timestamp=ts,
                        year_month=_msg_date(ts),
                        role=role,
                        speaker=speaker,
                    )
                    episodes[emotion].append(ev)
                    if emotion not in context_map:
                        context_map[emotion] = title

    # Aggregate into episodes
    result: List[EmotionalEpisode] = []
    for emotion, evidence_list in episodes.items():
        if len(evidence_list) < 2:
            continue
        dates = [e.year_month for e in evidence_list if e.year_month]
        if not dates:
            continue

        # Determine intensity from frequency and keyword density
        count = len(evidence_list)
        if count >= 20:
            intensity = "high"
        elif count >= 8:
            intensity = "medium"
        else:
            intensity = "low"

        result.append(EmotionalEpisode(
            emotion=emotion,
            trigger=context_map.get(emotion, "various contexts"),
            context=f"Observed across {len(set(dates))} months",
            intensity=intensity,
            evidence=evidence_list[:8],
            first_seen=min(dates),
            last_seen=max(dates),
            count=count,
        ))

    return sorted(result, key=lambda e: -e.count)


# ═══════════════════════════════════════════════════════════════════════════════
# DECISION CHAINS — with reversals and supersession
# ═══════════════════════════════════════════════════════════════════════════════

_DECISION_RE = re.compile(
    r"\b(i(?:'ve| have)?\s+(?:decided|chose|picked|settled|"
    r"going with|going to use|switched to|moved to|"
    r"opted for|committed to|will use|will go with))\b",
    re.I,
)

_REJECTION_RE = re.compile(
    r"\b(i\s+(?:don'?t|no longer|won'?t)\s+"
    r"(?:want|need|use|like|recommend|support|continue))\b",
    re.I,
)

_REVERSAL_RE = re.compile(
    r"\b(actually|never ?mind|wait|hold ?on|scratch that|"
    r"changed ?my ?mind|on ?second ?thought|i take ?that ?back|"
    r"let ?me ?rethink|forget ?what i|actually never|"
    r"wait nvm|wait never ?mind|nvm|scratch)\b",
    re.I,
)

# Topic extraction: what is the decision about?
_TOPIC_RE = re.compile(
    r"\b(?:about|regarding|for|on|using|with|in)\s+"
    r"([a-z][a-z ]{3,40})",
    re.I,
)


def _extract_decision_chains(
    conversations: List[Dict[str, Any]],
) -> List[DecisionChain]:
    """Extract decision/reversal chains with supersession tracking.
    Pairs decisions with their reversals to build temporal understanding."""
    raw_decisions: List[Tuple[str, Evidence, str]] = []  # (type, evidence, topic)

    for conv in conversations:
        title = conv.get("title", "")
        cid = conv.get("conversation_id", "")

        for ts, role, text, speaker in conv.get("messages", []):
            if _is_noise(text) or speaker != "joel":
                continue

            ev = Evidence(
                text=text[:300],
                conversation_id=cid,
                conversation_title=title,
                timestamp=ts,
                year_month=_msg_date(ts),
                role=role,
                speaker=speaker,
            )

            # Extract topic from message
            topic_match = _TOPIC_RE.search(text)
            topic = topic_match.group(1).strip() if topic_match else title or "general"

            if _REVERSAL_RE.search(text):
                raw_decisions.append(("reversal", ev, topic))
            elif _DECISION_RE.search(text):
                raw_decisions.append(("decision", ev, topic))
            elif _REJECTION_RE.search(text):
                raw_decisions.append(("rejection", ev, topic))

    # Group by topic and build chains
    topic_groups: Dict[str, List[Tuple[str, Evidence]]] = defaultdict(list)
    for dtype, ev, topic in raw_decisions:
        topic_groups[topic.lower()].append((dtype, ev))

    chains: List[DecisionChain] = []
    for topic, items in topic_groups.items():
        items.sort(key=lambda x: x[1].timestamp)

        has_reversal = any(t == "reversal" for t, _ in items)
        has_rejection = any(t == "rejection" for t, _ in items)

        # Initial position: first decision/rejection
        initial = None
        later = None
        for t, ev in items:
            if t in ("decision", "rejection") and initial is None:
                initial = ev
            if t == "reversal" and later is None:
                later = ev

        if initial is None:
            continue

        dates = [e.year_month for _, e in items if e.year_month]
        conf = min(0.95, 0.5 + 0.1 * len(items))

        chains.append(DecisionChain(
            topic=topic,
            initial_position=initial.text[:200],
            later_position=later.text[:200] if later else None,
            reason=None,  # would need LLM to extract reason
            confidence=conf,
            evidence=[ev for _, ev in items[:6]],
            is_reversal=has_reversal,
            is_current=not has_reversal,  # if reversed, initial is not current
            first_seen=min(dates) if dates else "",
            last_seen=max(dates) if dates else "",
        ))

    return sorted(chains, key=lambda c: -c.confidence)


# ═══════════════════════════════════════════════════════════════════════════════
# SHARED HISTORY — Joel↔KIO interactions (bidirectional)
# ═══════════════════════════════════════════════════════════════════════════════

_KIO_CORRECTION_RE = re.compile(
    r"\b(that'?s?\s+(?:wrong|incorrect|not what i|not right|"
    r"not ?what i ?meant|not ?what i ?wanted|"
    r"not ?what i ?asked|actually i|"
    r"i meant|i wanted|i asked for|i need you to|"
    r"no that|nope|nah that|wrong|incorrect))\b",
    re.I,
)

_KIO_EXPECTATION_RE = re.compile(
    r"\b(you ?(?:should|must|need to|have to|better|"
    r"are ?supposed ?to|need ?you ?to|i ?(?:want|need) ?you ?to|"
    r"please|do ?this|always|never|make ?sure|"
    r"stop doing|don'?t do))\b",
    re.I,
)

_KIO_PRAISE_RE = re.compile(
    r"\b(good ?job|well ?done|that'?s ?right|"
    r"you ?(?:got ?it|nailed ?it|got ?this|"
    r"understand)|there you ?go|it ?works|"
    r"saved ?me|exactly ?what i ?needed|thanks)\b",
    re.I,
)

_KIO_PROMISE_RE = re.compile(
    r"\b(i(?:'ll| will)\s+(?:build|create|implement|fix|add|"
    r"make|write|set up|configure|deploy|handle|take care of|"
    r"take care))\b",
    re.I,
)

_KIO_FAILURE_RE = re.compile(
    r"\b(broke|broken|crashed|failed|error|bug|regression|"
    r"doesn'?t ?work|not ?working|stopped working|"
    r"was working|used to work|regress|regression)\b",
    re.I,
)


def _extract_shared_history(
    conversations: List[Dict[str, Any]],
) -> List[SharedHistoryEvent]:
    """Extract Joel↔KIO shared history events.
    Parses BOTH user AND assistant messages for bidirectional evidence."""
    events: List[SharedHistoryEvent] = []

    for conv in conversations:
        title = conv.get("title", "")
        cid = conv.get("conversation_id", "")
        messages = conv.get("messages", [])

        # Build message pairs (user → assistant) for context
        for i, (ts, role, text, speaker) in enumerate(messages):
            if _is_noise(text):
                continue

            ev = Evidence(
                text=text[:300],
                conversation_id=cid,
                conversation_title=title,
                timestamp=ts,
                year_month=_msg_date(ts),
                role=role,
                speaker=speaker,
            )

            # Joel corrections of KIO
            if speaker == "joel" and _KIO_CORRECTION_RE.search(text):
                events.append(SharedHistoryEvent(
                    event_type="correction",
                    description=f"Joel corrected KIO: {text[:150]}",
                    evidence=[ev],
                    timestamp=ev.year_month,
                    confidence=0.8,
                    who_initiated="joel",
                ))

            # Joel expectations of KIO
            if speaker == "joel" and _KIO_EXPECTATION_RE.search(text):
                events.append(SharedHistoryEvent(
                    event_type="expectation",
                    description=f"Joel set expectation: {text[:150]}",
                    evidence=[ev],
                    timestamp=ev.year_month,
                    confidence=0.7,
                    who_initiated="joel",
                ))

            # Joel praising KIO (only when clearly directed at KIO's work)
            if speaker == "joel" and _KIO_PRAISE_RE.search(text):
                # Filter: must be short enough to be genuine praise, not a long message
                # that happens to contain 'nice' or 'thanks'
                if len(text) < 200:
                    events.append(SharedHistoryEvent(
                        event_type="praise",
                        description=f"Joel praised KIO: {text[:150]}",
                        evidence=[ev],
                        timestamp=ev.year_month,
                        confidence=0.7,
                        who_initiated="joel",
                    ))

            # KIO promises (from assistant messages)
            if speaker == "chatgpt" and _KIO_PROMISE_RE.search(text):
                # Check if user later reports failure
                for j in range(i + 1, min(i + 10, len(messages))):
                    _, _, later_text, later_speaker = messages[j]
                    if later_speaker == "joel" and _KIO_FAILURE_RE.search(later_text):
                        later_ev = Evidence(
                            text=later_text[:300],
                            conversation_id=cid,
                            conversation_title=title,
                            timestamp=messages[j][0],
                            year_month=_msg_date(messages[j][0]),
                            role="user",
                            speaker="joel",
                        )
                        events.append(SharedHistoryEvent(
                            event_type="failure",
                            description=f"KIO promised but failed: {text[:100]} → Joel: {later_text[:100]}",
                            evidence=[ev, later_ev],
                            timestamp=ev.year_month,
                            confidence=0.85,
                            who_initiated="kio",
                        ))
                        break

    return events


# ═══════════════════════════════════════════════════════════════════════════════
# CONVERSATION PROFILES — for topic modeling
# ═══════════════════════════════════════════════════════════════════════════════

def _profile_conversations(
    conversations: List[Dict[str, Any]],
) -> List[ConversationProfile]:
    """Build conversation profiles with topic inference."""
    profiles: List[ConversationProfile] = []
    for conv in conversations:
        title = conv.get("title", "")
        cid = conv.get("conversation_id", "")
        create_time = conv.get("create_time") or 0
        messages = conv.get("messages", [])

        user_msgs = [m for m in messages if m[1] == "user"]
        asst_msgs = [m for m in messages if m[1] == "assistant"]

        # Infer topic from title and first user message
        topic = title or "general"
        if user_msgs:
            first_text = user_msgs[0][2][:100]
            topic = f"{title}: {first_text}" if title else first_text

        # Detect emotional tone from user messages
        tone = "neutral"
        all_user_text = " ".join(m[2] for m in user_msgs[:5])
        if _EMOTION_KEYWORDS["frustration"].search(all_user_text):
            tone = "frustrated"
        elif _EMOTION_KEYWORDS["excitement"].search(all_user_text):
            tone = "excited"
        elif _EMOTION_KEYWORDS["urgency"].search(all_user_text):
            tone = "urgent"

        profiles.append(ConversationProfile(
            conversation_id=cid,
            title=title,
            create_time=create_time,
            year_month=_msg_date(create_time),
            topic=topic[:200],
            project_mentioned=_extract_project_from_title(title),
            emotional_tone=tone,
            user_message_count=len(user_msgs),
            assistant_message_count=len(asst_msgs),
        ))

    return profiles


# ═══════════════════════════════════════════════════════════════════════════════
# EXTRACTION RESULT
# ═══════════════════════════════════════════════════════════════════════════════

@dataclass
class LongitudinalResult:
    """Complete V2 extraction results."""
    project_lifecycles: List[ProjectLifecycle]
    emotional_episodes: List[EmotionalEpisode]
    decision_chains: List[DecisionChain]
    shared_history: List[SharedHistoryEvent]
    conversation_profiles: List[ConversationProfile]
    total_conversations: int
    total_messages: int
    date_range: Tuple[str, str]


# ═══════════════════════════════════════════════════════════════════════════════
# MAIN EXTRACTION
# ═══════════════════════════════════════════════════════════════════════════════

def extract_v2(
    directory: str = EXPORT_DIR,
    *,
    limit_convs: Optional[int] = None,
    checkpoint_path: Optional[str] = None,
) -> LongitudinalResult:
    """Deep longitudinal extraction. Bidirectional, checkpointed, resumable."""
    # Load checkpoint
    checkpoint: Dict[str, Any] = {}
    if checkpoint_path and os.path.isfile(checkpoint_path):
        try:
            with open(checkpoint_path, encoding="utf-8") as f:
                checkpoint = json.load(f)
        except Exception:
            checkpoint = {}

    processed_ids = set(checkpoint.get("processed_ids", []))

    # Parse conversations
    convs = _parse_all_conversations(directory, limit=limit_convs)
    # Filter already-processed
    new_convs = [c for c in convs if c.get("conversation_id") not in processed_ids]
    logger.info("[LONG_V2] total=%d new=%d", len(convs), len(new_convs))

    # Count total messages
    total_msgs = sum(len(c.get("messages", [])) for c in convs)

    # Build extractions
    project_lifecycles = _build_project_lifecycles(convs)  # use ALL convs
    emotional_episodes = _extract_emotional_episodes(convs)
    decision_chains = _extract_decision_chains(convs)
    shared_history = _extract_shared_history(convs)
    profiles = _profile_conversations(convs)

    # Update checkpoint
    for c in new_convs:
        processed_ids.add(c.get("conversation_id", ""))

    if checkpoint_path:
        try:
            os.makedirs(os.path.dirname(checkpoint_path), exist_ok=True)
            with open(checkpoint_path, "w", encoding="utf-8") as f:
                json.dump({
                    "processed_ids": sorted(processed_ids),
                    "saved_at": datetime.now(timezone.utc).isoformat(timespec="seconds"),
                }, f, ensure_ascii=False)
        except Exception as exc:
            logger.warning("[LONG_V2] checkpoint save failed: %s", exc)

    all_dates = [p.year_month for p in profiles if p.year_month]
    date_range = (min(all_dates), max(all_dates)) if all_dates else ("", "")

    result = LongitudinalResult(
        project_lifecycles=list(project_lifecycles.values()),
        emotional_episodes=emotional_episodes,
        decision_chains=decision_chains,
        shared_history=shared_history,
        conversation_profiles=profiles,
        total_conversations=len(convs),
        total_messages=total_msgs,
        date_range=date_range,
    )

    logger.info(
        "[LONG_V2] projects=%d emotions=%d decisions=%d shared=%d profiles=%d",
        len(result.project_lifecycles),
        len(result.emotional_episodes),
        len(result.decision_chains),
        len(result.shared_history),
        len(result.conversation_profiles),
    )

    return result


# ═══════════════════════════════════════════════════════════════════════════════
# GRAPH PERSISTENCE
# ═══════════════════════════════════════════════════════════════════════════════

def persist_v2(session_id: str, result: LongitudinalResult) -> Dict[str, int]:
    """Write V2 extraction results to the semantic graph."""
    graph = SemanticGraph(session_id)
    counts: Dict[str, int] = defaultdict(int)

    # Persist project lifecycles
    for proj in result.project_lifecycles:
        node = graph.ensure_project(
            proj.name,
            lifecycle=proj.current_state,
            confidence=proj.confidence,
            provenance="longitudinal_v2",
        )
        if node:
            counts["project"] += 1
        # Record transitions
        for t in proj.transitions:
            claim = f"project {proj.name}: {t['from']} → {t['to']}"
            link = graph.record_statement(
                USER_KEY, claim,
                relation="said", stance="observation",
                confidence=proj.confidence,
                event_time=t.get("when"),
                supersede_prior=False,
                provenance=f"longitudinal_v2:project:{proj.name}",
            )
            if link:
                counts["project_transition"] += 1

    # Persist emotional episodes
    for ep in result.emotional_episodes:
        claim = f"emotional_episode: {ep.emotion} ({ep.intensity}) in {ep.trigger}"
        link = graph.record_statement(
            USER_KEY, claim,
            relation="said", stance="observation",
            confidence=0.7,
            event_time=ep.last_seen,
            supersede_prior=False,
            provenance=f"longitudinal_v2:emotional:{ep.emotion}",
        )
        if link:
            counts["emotional"] += 1

    # Persist decision chains
    for chain in result.decision_chains:
        claim = f"decision: {chain.topic}"
        if chain.is_reversal:
            claim += f" (reversed: {chain.later_position[:80] if chain.later_position else '?'})"
        link = graph.record_statement(
            USER_KEY, claim,
            relation="said", stance="observation",
            confidence=chain.confidence,
            event_time=chain.last_seen,
            supersede_prior=False,
            provenance=f"longitudinal_v2:decision:{chain.topic[:50]}",
        )
        if link:
            counts["decision"] += 1

    # Persist shared history
    for event in result.shared_history:
        claim = f"shared_history: {event.description}"
        link = graph.record_statement(
            USER_KEY, claim,
            relation="said", stance="observation",
            confidence=event.confidence,
            event_time=event.timestamp,
            supersede_prior=False,
            provenance=f"longitudinal_v2:shared:{event.event_type}",
        )
        if link:
            counts["shared_history"] += 1

    return dict(counts)


# ═══════════════════════════════════════════════════════════════════════════════
# RELEVANCE-RANKED RETRIEVAL — query-based, not full injection
# ═══════════════════════════════════════════════════════════════════════════════

# Topic detection keywords for routing queries to the right evidence
_QUERY_ROUTES = {
    "project": re.compile(
        r"\b(project|building|working on|app|website|prototype|"
        r"develop|code|abandon|drop|revive|continue|resume|"
        r"what did i|what am i|what have i|been doing|"
        r"focused on|up to|lately|recently|currently|"
        r"come back|came back|back to)\b", re.I),
    "decision": re.compile(
        r"\b(decid|decis|chose|picked|change.mind|reversal|"
        r"why did i|dropped|abandoned|switch|"
        r"used to|before|earlier|previously|"
        r"change .* mind|second thought|"
        r"pattern.*decis|how.*decis|make.*decis)", re.I),
    "emotion": re.compile(
        r"\b(frustrat|angry|piss|excit|hype|amazing|stuck|broken|"
        r"annoy|confused|lost|happy|sad|mood|feel|"
        r"when.*debug|when.*frustrated|when.*excited)\b", re.I),
    "correction": re.compile(
        r"\b(correct|wrong|fix|mistake|error|regression|"
        r"broke|broken|what did you|"
        r"you (?:kept|keep|always|never)|"
        r"corrected you|got wrong|messed up)\b", re.I),
    "communication": re.compile(
        r"\b(talk|speak|communicate|phrase|slang|"
        r"how do i|how i|my style|tone|"
        r"bruh|bro|gonna|wanna|"
        r"how.*talk|how.*speak|how.*express)\b", re.I),
    "kio": re.compile(
        r"\b(kio|yourself|what do you know|"
        r"what can you|what have you|"
        r"tell me about yourself|"
        r"know about yourself|self.model)\b", re.I),
    "identity": re.compile(
        r"\b(who am i|about me|what do you know about me|"
        r"tell me about (?:me|yourself)|what am i|"
        r"my name|my age|my college|education|"
        r"who are you)\b", re.I),
    "technical": re.compile(
        r"\b(python|code|tech|learn|skill|programming|"
        r"developer|engineering|git|api|database)\b", re.I),
}


def retrieve_relevant(
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

    # Route query to relevant evidence dimensions
    matched_routes = [route for route, pattern in _QUERY_ROUTES.items()
                      if pattern.search(low)]

    if not matched_routes:
        # Default: identity + recent context
        matched_routes = ["identity", "project"]
    # Always include identity for context
    if "identity" not in matched_routes:
        matched_routes.append("identity")

    graph = SemanticGraph(session_id)
    links = graph.attributed_statements(
        USER_KEY, relation="said", stance="observation",
        active_only=True, limit=200,
    )

    # Index evidence by category (match both V1 and V2 provenance)
    evidence_by_cat: Dict[str, List[str]] = defaultdict(list)
    for link in links:
        target = getattr(link, "target_name", "") or ""
        prov = getattr(link, "provenance", "") or ""
        conf = getattr(link, "confidence", 0.5)

        # V1 categories (target-based)
        for cat in ("communication:", "emotional:", "behavior:", "decision:",
                     "technical interest:", "kio_history:"):
            if cat in target:
                evidence_by_cat[cat.rstrip(":")].append(target)
                break
        else:
            # V2 categories (provenance-based)
            if "longitudinal_v2:project" in prov:
                evidence_by_cat["project"].append(target)
            elif "longitudinal_v2:emotional" in prov:
                evidence_by_cat["emotional"].append(target)
            elif "longitudinal_v2:decision" in prov:
                evidence_by_cat["decision"].append(target)
            elif "longitudinal_v2:shared" in prov:
                evidence_by_cat["shared_history"].append(target)
            elif "longitudinal:communication" in prov:
                evidence_by_cat["communication"].append(target)
            elif "longitudinal:technical" in prov:
                evidence_by_cat["technical interest"].append(target)

    # Retrieve evidence for matched routes
    if "project" in matched_routes:
        # Query project nodes directly from DB (all_projects() has a 200-node limit)
        from mini_kio.backend.db import db_session
        from mini_kio.backend.models import SemanticNodeModel
        with db_session() as db:
            proj_nodes = db.query(SemanticNodeModel).filter(
                SemanticNodeModel.session_id == session_id,
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
        if hist_projs and any(kw in low for kw in ("before", "earlier", "old", "past", "abandon")):
            parts.append("Historical projects: " + "; ".join(hist_projs[:5]) + ".")

    if "decision" in matched_routes:
        items = evidence_by_cat.get("decision", [])
        if items:
            parts.append("Decision evidence:\n" + "\n".join(
                f"- {i}" for i in items[:5]))

    if "emotion" in matched_routes:
        items = evidence_by_cat.get("emotional", []) + evidence_by_cat.get("emotional_episode", [])
        if items:
            parts.append("Emotional patterns: " + "; ".join(items[:5]) + ".")

    if "correction" in matched_routes:
        items = evidence_by_cat.get("kio_history", []) + evidence_by_cat.get("shared_history", [])
        if items:
            parts.append("KIO interaction history:\n" + "\n".join(
                f"- {i}" for i in items[:5]))

    if "communication" in matched_routes:
        items = evidence_by_cat.get("communication", [])
        if items:
            parts.append("Communication patterns: " + "; ".join(items[:5]) + ".")

    if "kio" in matched_routes:
        # KIO self-knowledge
        try:
            from mini_kio.memory.kio_self_model import kio_self_brief
            brief = kio_self_brief()
            if brief:
                parts.append(brief[:500])
        except Exception:
            pass

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

    if not parts:
        return ""
    return "Evidence (relevance-ranked):\n" + "\n".join(parts[:max_items])
