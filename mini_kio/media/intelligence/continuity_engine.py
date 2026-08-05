from __future__ import annotations
import re
from dataclasses import dataclass
from typing import Optional, Callable, Any
from mini_kio.media.intelligence.media_intelligence_models import TopicType, ArtifactType, EventRecord, ArtifactRecord
from mini_kio.media.intelligence.context_store import ContextStore
from mini_kio.media.intelligence.artifact_memory import ArtifactMemory, parse_artifact_type, default_artifact_for_topic
from mini_kio.media.intelligence.topic_classifier import classify_topic


# ── followup query patterns ────────────────────────────────────────────────────

_PLAY_IT = re.compile(r"^play\s*(it|this|that)?$", re.I)
_PLAY_AGAIN = re.compile(r"(play (it |this |that )?again|replay|repeat this|another one)", re.I)
_SHOW_IT = re.compile(r"^show\s*(it|this|that)?$", re.I)
_TELL_MORE = re.compile(r"(tell me more|more info|more details|expand|elaborate)", re.I)
_WHAT_HAPPENED = re.compile(r"what happened (in |about )?(the )?(.*?)(match|game|result)?", re.I)
_SHOW_ARTIFACT = re.compile(
    r"(?:show|get|find|play|latest|recent|current)?\s*(?:the\s+)?(trailer|teaser|gameplay|highlights|standings|fixtures|results|interview|music video|mv|video|reveal|table|scores|schedule|analysis|tactical|recap|clips|blooper|behind.the.scenes|best.scenes|ending.explained|press.conference|goal.compilation|onboard|team.radio|concert|acoustic|lyrics|walkthrough|audiobook|book.review|book.summary|author.interview|reading)",
    re.I,
)
_PRONOUNS = re.compile(r"^(it|that|this|them|those|him|he|she)$", re.I)
_PRONOUN_IN_QUERY = re.compile(r"\b(it|that|this|them|those|him|he|she|his|her|their)\b", re.I)


@dataclass
class ResolutionResult:
    resolved: bool
    action: str  # "play", "show", "search", "respond", "none"
    subject: Optional[str] = None
    artifact_type: Optional[ArtifactType] = None
    artifact_record: Optional[ArtifactRecord] = None
    event_record: Optional[EventRecord] = None
    topic: Optional[TopicType] = None
    response_text: Optional[str] = None
    confidence: float = 0.0
    source: str = "none"  # pending|event|artifact|session|search


class ContinuityEngine:
    """
    Deterministic followup resolution.
    Priority:
      1. explicit pending action
      2. recent event memory
      3. artifact memory
      4. session topic memory
      5. fresh search (caller must implement)
    Never searches first.
    """

    def __init__(
        self,
        context: ContextStore,
        artifact_memory: ArtifactMemory,
        pending_action_resolver: Optional[Callable[[str], Optional[dict]]] = None,
    ) -> None:
        self.ctx = context
        self.art = artifact_memory
        self._pending = pending_action_resolver  # injected from CommandRouter

    # ── public API ─────────────────────────────────────────────────────────────

    def _has_different_entity(self, q: str) -> bool:
        """Check if query mentions a different named entity than current context.

        Prevents patterns like "what happened during the French Revolution?" from
        being treated as a followup when the current context is about something
        else entirely (e.g. "Believer by Imagine Dragons").
        """
        current = self.ctx.recent_subject()
        if not current:
            return False
        current_lower = current.lower()
        # Words that commonly start sentences/questions — not entity indicators
        _start_words = {"what", "when", "where", "who", "why", "how", "which",
                        "whom", "whose", "is", "are", "was", "were", "do", "does",
                        "did", "can", "could", "will", "would", "shall", "should",
                        "may", "might", "tell", "show", "please", "explain",
                        "describe", "define", "now", "so", "then", "but", "and",
                        "the", "a", "an", "of", "for", "with", "about", "at", "in",
                        "on", "from", "by", "to", "or", "not", "no", "get", "got",
                        "go", "went", "see", "watch", "listen", "play", "want",
                        "know", "there", "this", "that"}
        words = q.split()
        cap_words = set()
        for w in words:
            wc = w.strip(".,!?;:'\"")
            if wc and wc[0].isupper() and wc.lower() not in _start_words:
                cap_words.add(wc.lower())
        if not cap_words:
            # All-lowercase input — check if query has substantive words beyond
            # artifact/freshness/start words that don't overlap with current subject.
            _artifact_kws = {"trailer","teaser","gameplay","highlights","standings","fixtures","results",
                             "interview","music","video","mv","reveal","table","scores","schedule",
                             "analysis","tactical","recap","clips","blooper","behind","scenes","best",
                             "ending","explained","press","conference","goal","compilation","onboard",
                             "team","radio","concert","acoustic","lyrics","walkthrough","audiobook",
                             "book","review","summary","author","reading"}
            _freshness = {"latest","updates","news","recent","current","today","any","group",
                          "leader","leading","qualified","eliminated"}
            query_words = {w.strip(".,!?;:'\"").lower() for w in words}
            content = query_words - _start_words - _artifact_kws - _freshness
            if content and not any(cw in current_lower for cw in content):
                return True
            return False  # No clear entity reference — safe to treat as followup
        # If any capitalized word is NOT part of current subject, it's a new entity
        for cw in cap_words:
            if cw not in current_lower:
                return True
        return False

    def is_followup(self, query: str) -> bool:
        q = query.strip()
        if _PLAY_IT.match(q) or _PLAY_AGAIN.search(q):
            return True
        if _SHOW_IT.match(q):
            return True
        if _TELL_MORE.search(q):
            return True
        if _WHAT_HAPPENED.search(q):
            if self._has_different_entity(q):
                return False
            return True
        if _SHOW_ARTIFACT.search(q):
            if self._has_different_entity(q):
                return False
            return True
        if _PRONOUNS.match(q):
            return True
        if _PRONOUN_IN_QUERY.search(q):
            return True
        # bare artifact keyword with no new subject
        artifact = parse_artifact_type(q)
        if artifact:
            classification = classify_topic(q)
            if classification.confidence < 0.4:
                return True
        return False

    def resolve_followup(self, query: str) -> ResolutionResult:
        q = query.strip().lower()

        # ── priority 1: pending action ─────────────────────────────────────────
        if self._pending:
            pending = self._pending(query)
            if pending:
                return ResolutionResult(
                    resolved=True,
                    action=pending.get("action", "respond"),
                    subject=pending.get("subject"),
                    topic=pending.get("topic"),
                    confidence=1.0,
                    source="pending",
                )

        # ── priority 2: event memory ───────────────────────────────────────────
        entity_hint = self._extract_entity_hint(query)
        event = self.ctx.best_event(entity_hint)

        if event and event.confidence >= 0.5:
            # "show highlights" / "what happened"
            if _WHAT_HAPPENED.search(query) or "highlights" in q:
                return ResolutionResult(
                    resolved=True,
                    action="show",
                    subject=event.display(),
                    artifact_type=ArtifactType.HIGHLIGHTS,
                    event_record=event,
                    topic=TopicType.SPORTS,
                    confidence=event.confidence,
                    source="event",
                )
            # "show standings" / "show fixtures" / "show results" / "show analysis"
            artifact_type = parse_artifact_type(q)
            if artifact_type in (ArtifactType.STANDINGS, ArtifactType.FIXTURES, ArtifactType.RESULTS,
                                ArtifactType.ANALYSIS, ArtifactType.MATCH_ANALYSIS, ArtifactType.TACTICAL_BREAKDOWN):
                return ResolutionResult(
                    resolved=True,
                    action="show",
                    subject=event.competition or event.display(),
                    artifact_type=artifact_type,
                    event_record=event,
                    topic=TopicType.SPORTS,
                    confidence=event.confidence,
                    source="event",
                )

        # ── priority 3: artifact memory ────────────────────────────────────────
        topic = self.ctx.recent_topic()
        subject = self.ctx.recent_subject()
        artifact_type = parse_artifact_type(q)

        if not artifact_type:
            # "play it" / "show it" → default for topic
            if topic and (_PLAY_IT.match(query) or _SHOW_IT.match(query)):
                artifact_type = default_artifact_for_topic(topic)

        if artifact_type:
            record = self.art.resolve_artifact(artifact_type, subject=subject, topic=topic)
            if record:
                return ResolutionResult(
                    resolved=True,
                    action="play" if artifact_type in (ArtifactType.TRAILER, ArtifactType.GAMEPLAY, ArtifactType.MUSIC_VIDEO, ArtifactType.HIGHLIGHTS) else "show",
                    subject=record.subject,
                    artifact_type=artifact_type,
                    artifact_record=record,
                    topic=record.topic,
                    confidence=record.confidence,
                    source="artifact",
                )
            # artifact type known but no stored URL yet → still resolve subject
            if subject and artifact_type:
                return ResolutionResult(
                    resolved=True,
                    action="search",
                    subject=subject,
                    artifact_type=artifact_type,
                    topic=topic,
                    confidence=0.7,
                    source="artifact",
                )

        # ── priority 4: session topic + subject ───────────────────────────────
        if topic and subject:
            if _PLAY_AGAIN.search(query):
                 return ResolutionResult(
                    resolved=True,
                    action="play",
                    subject=subject,
                    topic=topic,
                    confidence=1.0,
                    source="continuity",
                )
            if _TELL_MORE.search(query):
                return ResolutionResult(
                    resolved=True,
                    action="search",
                    subject=subject,
                    topic=topic,
                    confidence=0.6,
                    source="session",
                )
            if _PLAY_IT.match(query) or _SHOW_IT.match(query):
                default = default_artifact_for_topic(topic)
                return ResolutionResult(
                    resolved=True,
                    action="search",
                    subject=subject,
                    artifact_type=default,
                    topic=topic,
                    confidence=0.5,
                    source="session",
                )

        # ── priority 5: fallback to search ────────────────────────────────────
        return ResolutionResult(
            resolved=False,
            action="search",
            confidence=0.0,
            source="search",
        )

    def resolve_reference(self, query: str) -> ResolutionResult:
        """Resolve pronoun references like 'it', 'that', 'this'."""
        if not _PRONOUNS.match(query.strip()):
            return ResolutionResult(resolved=False, action="none")
        topic = self.ctx.recent_topic()
        subject = self.ctx.recent_subject()
        if subject and topic:
            default = default_artifact_for_topic(topic)
            return ResolutionResult(
                resolved=True,
                action="play",
                subject=subject,
                artifact_type=default,
                topic=topic,
                confidence=0.8,
                source="session",
            )
        return ResolutionResult(resolved=False, action="search")

    def resolve_artifact_request(
        self,
        query: str,
        topic: Optional[TopicType] = None,
        subject: Optional[str] = None,
    ) -> ResolutionResult:
        """Direct artifact resolution for known topic+subject."""
        q = query.lower()
        artifact_type = parse_artifact_type(q)
        if not artifact_type:
            if topic:
                artifact_type = default_artifact_for_topic(topic)

        resolved_topic = topic or self.ctx.recent_topic()
        resolved_subject = subject or self.ctx.recent_subject()

        if artifact_type and resolved_subject:
            record = self.art.resolve_artifact(artifact_type, subject=resolved_subject, topic=resolved_topic)
            if record:
                return ResolutionResult(
                    resolved=True,
                    action="play",
                    subject=record.subject,
                    artifact_type=artifact_type,
                    artifact_record=record,
                    topic=record.topic,
                    confidence=record.confidence,
                    source="artifact",
                )
            return ResolutionResult(
                resolved=True,
                action="search",
                subject=resolved_subject,
                artifact_type=artifact_type,
                topic=resolved_topic,
                confidence=0.7,
                source="session",
            )

        return ResolutionResult(resolved=False, action="search")

    # ── helpers ───────────────────────────────────────────────────────────────

    def _extract_entity_hint(self, query: str) -> Optional[str]:
        m = _WHAT_HAPPENED.search(query)
        if m:
            hint = m.group(3)
            if hint:
                return hint.strip()
        return None

    def update_context(
        self,
        query: str,
        topic: TopicType,
        subject: str,
        confidence: float = 1.0,
    ) -> None:
        """Call after each successful resolution to update session state."""
        self.ctx.add_topic(topic, confidence)
        self.ctx.set_subject(subject, topic, confidence)
