from __future__ import annotations
import time
from dataclasses import dataclass, field
from typing import Any, Optional
from mini_kio.media.intelligence.media_intelligence_models import EventRecord, ArtifactRecord, RelationshipRecord, TopicType


MAX_ENTRIES = 50


@dataclass
class ContextEntry:
    key: str
    value: Any
    topic: Optional[TopicType] = None
    confidence: float = 1.0
    source: str = ""
    timestamp: float = field(default_factory=time.time)

    def age_seconds(self) -> float:
        return time.time() - self.timestamp


class ContextStore:
    """
    Lightweight in-memory key-value store.
    FIFO eviction at MAX_ENTRIES. Low-confidence entries never override high-confidence.
    """

    def __init__(self, max_entries: int = MAX_ENTRIES) -> None:
        self._store: list[ContextEntry] = []
        self.max_entries = max_entries

        # typed shortcut stores
        self.events: list[EventRecord] = []
        self.artifacts: list[ArtifactRecord] = []
        self.relationships: list[RelationshipRecord] = []
        self.topics: list[tuple[TopicType, float, float]] = []  # (topic, confidence, timestamp)

    # ── generic store ─────────────────────────────────────────────────────────

    def put(
        self,
        key: str,
        value: Any,
        topic: Optional[TopicType] = None,
        confidence: float = 1.0,
        source: str = "",
    ) -> None:
        # update existing
        for i, e in enumerate(self._store):
            if e.key == key:
                if confidence >= e.confidence:
                    self._store[i] = ContextEntry(key, value, topic, confidence, source)
                return
        if len(self._store) >= self.max_entries:
            self._store.pop(0)
        self._store.append(ContextEntry(key, value, topic, confidence, source))

    def get(self, key: str) -> Optional[ContextEntry]:
        for e in reversed(self._store):
            if e.key == key:
                return e
        return None

    def remove(self, key: str) -> None:
        """Drop an entry by key (claim-store lifecycle: consumed claims are
        removed so a later probe cannot resurrect an old conversation's
        proposition)."""
        self._store = [e for e in self._store if e.key != key]

    def get_value(self, key: str, default: Any = None) -> Any:
        e = self.get(key)
        return e.value if e else default

    # ── typed stores ──────────────────────────────────────────────────────────

    def add_event(self, event: EventRecord) -> None:
        if not event.is_valid():
            return
        # update if same entity pair
        for i, e in enumerate(self.events):
            if e.entity_a == event.entity_a and e.entity_b == event.entity_b:
                if event.confidence >= e.confidence:
                    self.events[i] = event
                return
        if len(self.events) >= self.max_entries:
            self.events.pop(0)
        self.events.append(event)

    def add_artifact(self, artifact: ArtifactRecord) -> None:
        if not artifact.is_valid():
            return
        for i, a in enumerate(self.artifacts):
            if a.subject == artifact.subject and a.artifact_type == artifact.artifact_type:
                if artifact.confidence >= a.confidence:
                    self.artifacts[i] = artifact
                return
        if len(self.artifacts) >= self.max_entries:
            self.artifacts.pop(0)
        self.artifacts.append(artifact)

    def add_relationship(self, rel: RelationshipRecord) -> None:
        """Store a semantic relationship triple, deduped by
        (subject, predicate, object); a higher-confidence record replaces the
        older one (newer evidence wins at equal confidence)."""
        if not rel.is_valid():
            return
        for i, r in enumerate(self.relationships):
            if (
                r.subject.lower() == rel.subject.lower()
                and r.predicate == rel.predicate
                and r.object.lower() == rel.object.lower()
            ):
                if rel.confidence > r.confidence or (
                    rel.confidence == r.confidence and rel.timestamp >= r.timestamp
                ):
                    self.relationships[i] = rel
                return
        if len(self.relationships) >= self.max_entries:
            self.relationships.pop(0)
        self.relationships.append(rel)

    def find_relationships(
        self,
        subject: Optional[str] = None,
        predicate: Optional[str] = None,
        object_: Optional[str] = None,
        session_id: Optional[str] = None,
        max_age: Optional[float] = None,
    ) -> list[RelationshipRecord]:
        """Relationship lookup: any subset of (subject, predicate, object,
        session) filters; best (highest confidence, newest) records first."""
        now = time.time()
        out = []
        for r in self.relationships:
            if subject and r.subject.lower() != subject.strip().lower():
                continue
            if predicate and r.predicate != predicate:
                continue
            if object_ and r.object.lower() != object_.strip().lower():
                continue
            if session_id is not None and r.session_id and r.session_id != session_id:
                continue
            if max_age is not None and (now - r.timestamp) > max_age:
                continue
            out.append(r)
        out.sort(key=lambda r: (r.confidence, r.timestamp), reverse=True)
        return out

    def find_relationship(
        self,
        subject: Optional[str] = None,
        predicate: Optional[str] = None,
        object_: Optional[str] = None,
        session_id: Optional[str] = None,
        max_age: Optional[float] = None,
    ) -> Optional[RelationshipRecord]:
        found = self.find_relationships(
            subject=subject, predicate=predicate, object_=object_,
            session_id=session_id, max_age=max_age,
        )
        return found[0] if found else None

    def add_topic(self, topic: TopicType, confidence: float = 1.0) -> None:
        self.topics.append((topic, confidence, time.time()))
        if len(self.topics) > self.max_entries:
            self.topics.pop(0)

    # ── queries ───────────────────────────────────────────────────────────────

    def recent_topic(self, max_age: float = 600) -> Optional[TopicType]:
        """Most recent high-confidence topic within max_age seconds."""
        now = time.time()
        candidates = [
            (t, c, ts) for t, c, ts in reversed(self.topics)
            if (now - ts) <= max_age and c >= 0.5
        ]
        if not candidates:
            return None
        return candidates[0][0]

    def recent_events(self, max_age: float = 3600) -> list[EventRecord]:
        now = time.time()
        return [e for e in self.events if (now - e.timestamp) <= max_age]

    def best_event(self, entity_hint: Optional[str] = None) -> Optional[EventRecord]:
        events = self.recent_events()
        if not events:
            return None
        if entity_hint:
            h = entity_hint.lower()
            filtered = [
                e for e in events
                if h in e.entity_a.lower() or h in e.entity_b.lower()
            ]
            if filtered:
                events = filtered
        completed = [e for e in events if e.status.value == "completed"]
        pool = completed or events
        return max(pool, key=lambda e: (e.confidence, e.timestamp))

    def recent_subject(self) -> Optional[str]:
        return self.get_value("subject")

    def set_subject(self, subject: str, topic: Optional[TopicType] = None, confidence: float = 1.0) -> None:
        self.put("subject", subject, topic=topic, confidence=confidence)

    def clear(self) -> None:
        self._store.clear()
        self.events.clear()
        self.artifacts.clear()
        self.relationships.clear()
        self.topics.clear()
