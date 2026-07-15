from __future__ import annotations
import time
from typing import Optional
from mini_kio.media.intelligence.media_intelligence_models import ArtifactRecord, ArtifactType, TopicType

# ── artifact request → ArtifactType mapping ───────────────────────────────────

_ARTIFACT_ALIASES: dict[str, ArtifactType] = {
    # trailers / teasers
    "trailer": ArtifactType.TRAILER,
    "teaser": ArtifactType.TEASER,
    "reveal": ArtifactType.TEASER,
    "reveal trailer": ArtifactType.TRAILER,
    # interviews
    "interview": ArtifactType.INTERVIEW,
    "press conference": ArtifactType.PRESS_CONFERENCE,
    "director interview": ArtifactType.INTERVIEW,
    "cast interview": ArtifactType.INTERVIEW,
    # gaming
    "gameplay": ArtifactType.GAMEPLAY,
    "walkthrough": ArtifactType.GAMEPLAY,
    "developer update": ArtifactType.DEVELOPER_UPDATE,
    "dev update": ArtifactType.DEVELOPER_UPDATE,
    "patch notes": ArtifactType.DEVELOPER_UPDATE,
    # sports
    "highlights": ArtifactType.HIGHLIGHTS,
    "match highlights": ArtifactType.HIGHLIGHTS,
    "game highlights": ArtifactType.HIGHLIGHTS,
    "goal compilation": ArtifactType.GOAL_COMPILATION,
    "goal compilations": ArtifactType.GOAL_COMPILATION,
    "standings": ArtifactType.STANDINGS,
    "table": ArtifactType.STANDINGS,
    "fixtures": ArtifactType.FIXTURES,
    "schedule": ArtifactType.FIXTURES,
    "upcoming matches": ArtifactType.FIXTURES,
    "results": ArtifactType.RESULTS,
    "scores": ArtifactType.RESULTS,
    "analysis": ArtifactType.ANALYSIS,
    "match analysis": ArtifactType.MATCH_ANALYSIS,
    "tactical": ArtifactType.TACTICAL_BREAKDOWN,
    "tactical breakdown": ArtifactType.TACTICAL_BREAKDOWN,
    # movies / TV
    "best scenes": ArtifactType.BEST_SCENES,
    "best scene": ArtifactType.BEST_SCENES,
    "behind the scenes": ArtifactType.BEHIND_THE_SCENES,
    "behind-the-scenes": ArtifactType.BEHIND_THE_SCENES,
    "bts": ArtifactType.BEHIND_THE_SCENES,
    "ending explained": ArtifactType.ENDING_EXPLAINED,
    "blooper": ArtifactType.BLOOPERS,
    "bloopers": ArtifactType.BLOOPERS,
    "backstage": ArtifactType.BEHIND_THE_SCENES,
    "making of": ArtifactType.BEHIND_THE_SCENES,
    "behind-the-scenes footage": ArtifactType.BEHIND_THE_SCENES,
    "clips": ArtifactType.CLIPS,
    "clip": ArtifactType.CLIPS,
    "recap": ArtifactType.RECAP,
    "recaps": ArtifactType.RECAP,
    "documentary": ArtifactType.DOCUMENTARY,
    "production update": ArtifactType.PRODUCTION_UPDATE,
    "production updates": ArtifactType.PRODUCTION_UPDATE,
    "set footage": ArtifactType.SET_FOOTAGE,
    "episode preview": ArtifactType.EPISODE_PREVIEW,
    # music
    "music video": ArtifactType.MUSIC_VIDEO,
    "mv": ArtifactType.MUSIC_VIDEO,
    "video": ArtifactType.MUSIC_VIDEO,
    "live performance": ArtifactType.LIVE_PERFORMANCE,
    "acoustic": ArtifactType.ACOUSTIC_VERSION,
    "acoustic version": ArtifactType.ACOUSTIC_VERSION,
    "lyrics": ArtifactType.LYRICS_VIDEO,
    "lyrics video": ArtifactType.LYRICS_VIDEO,
    "concert": ArtifactType.CONCERT_FOOTAGE,
    "concert footage": ArtifactType.CONCERT_FOOTAGE,
    # F1 / athletes
    "onboard": ArtifactType.ONBOARD_FOOTAGE,
    "onboard footage": ArtifactType.ONBOARD_FOOTAGE,
    "team radio": ArtifactType.TEAM_RADIO,
    "voice actor": ArtifactType.VOICE_ACTOR_INTERVIEW,
    "voice actor interview": ArtifactType.VOICE_ACTOR_INTERVIEW,
    # creators
    "latest video": ArtifactType.LATEST_VIDEO,
    "project breakdown": ArtifactType.PROJECT_BREAKDOWN,
    "best moments": ArtifactType.BEST_MOMENTS,
    # books
    "audiobook": ArtifactType.AUDIOBOOK,
    "audio book": ArtifactType.AUDIOBOOK,
    "book review": ArtifactType.BOOK_REVIEW,
    "reviews": ArtifactType.BOOK_REVIEW,
    "book summary": ArtifactType.BOOK_SUMMARY,
    "summary": ArtifactType.BOOK_SUMMARY,
    "adaptation trailer": ArtifactType.ADAPTATION_TRAILER,
    "movie adaptation": ArtifactType.ADAPTATION_TRAILER,
    "author interview": ArtifactType.AUTHOR_INTERVIEW,
    "writer interview": ArtifactType.AUTHOR_INTERVIEW,
    "reading": ArtifactType.READING,
    "read by": ArtifactType.READING,
    "excerpt": ArtifactType.READING,
    "soundtrack": ArtifactType.SOUNDTRACK,
    "music": ArtifactType.SOUNDTRACK,
    "score": ArtifactType.SOUNDTRACK,
    "background score": ArtifactType.SOUNDTRACK,
    "ost": ArtifactType.SOUNDTRACK,
    "original soundtrack": ArtifactType.SOUNDTRACK,
    "composer interview": ArtifactType.COMPOSER_INTERVIEW,
    "music interview": ArtifactType.COMPOSER_INTERVIEW,
}

# default artifact per topic (used for "play it" / "show it")
_TOPIC_DEFAULT_ARTIFACT: dict[TopicType, ArtifactType] = {
    TopicType.MOVIES: ArtifactType.BEST_SCENES,
    TopicType.TV: ArtifactType.CLIPS,
    TopicType.GAMING: ArtifactType.GAMEPLAY,
    TopicType.SPORTS: ArtifactType.HIGHLIGHTS,
    TopicType.MUSIC: ArtifactType.MUSIC_VIDEO,
    TopicType.TECH: ArtifactType.TRAILER,
    TopicType.NEWS: ArtifactType.HIGHLIGHTS,
    TopicType.BOOKS: ArtifactType.AUDIOBOOK,
}


class ArtifactMemory:
    """In-memory store for resolved artifacts. Max 100 entries, FIFO eviction."""

    MAX_SIZE = 100

    def __init__(self) -> None:
        self._store: list[ArtifactRecord] = []

    def store_artifact(self, record: ArtifactRecord) -> None:
        if not record.is_valid():
            return
        # update if same subject+type exists
        for i, r in enumerate(self._store):
            if r.subject.lower() == record.subject.lower() and r.artifact_type == record.artifact_type:
                if record.confidence >= r.confidence:
                    self._store[i] = record
                return
        if len(self._store) >= self.MAX_SIZE:
            self._store.pop(0)  # FIFO
        self._store.append(record)

    def resolve_artifact(
        self,
        artifact_type: ArtifactType,
        subject: Optional[str] = None,
        topic: Optional[TopicType] = None,
    ) -> Optional[ArtifactRecord]:
        candidates = [r for r in self._store if r.artifact_type == artifact_type]
        if subject:
            exact = [r for r in candidates if subject.lower() in r.subject.lower()]
            if exact:
                candidates = exact
        if topic:
            topic_match = [r for r in candidates if r.topic == topic]
            if topic_match:
                candidates = topic_match
        return self.best_match(candidates)

    def best_match(self, candidates: list[ArtifactRecord]) -> Optional[ArtifactRecord]:
        if not candidates:
            return None
        return max(candidates, key=lambda r: (r.confidence, r.timestamp))

    def resolve_from_query(
        self,
        query: str,
        topic: Optional[TopicType] = None,
        subject: Optional[str] = None,
    ) -> Optional[ArtifactRecord]:
        q = query.lower().strip()
        artifact_type = parse_artifact_type(q)
        if artifact_type:
            return self.resolve_artifact(artifact_type, subject=subject, topic=topic)
        # "play it" / "show it" → default for topic
        if topic and ("play it" in q or "show it" in q or q in ("play", "show")):
            default_type = _TOPIC_DEFAULT_ARTIFACT.get(topic)
            if default_type:
                return self.resolve_artifact(default_type, subject=subject, topic=topic)
        return None

    def get_by_subject(self, subject: str) -> list[ArtifactRecord]:
        s = subject.lower()
        return [r for r in self._store if s in r.subject.lower()]

    def get_by_topic(self, topic: TopicType) -> list[ArtifactRecord]:
        return [r for r in self._store if r.topic == topic]

    def clear(self) -> None:
        self._store.clear()


def parse_artifact_type(query: str) -> Optional[ArtifactType]:
    q = query.lower().strip()
    # longest match first
    for alias in sorted(_ARTIFACT_ALIASES.keys(), key=len, reverse=True):
        if alias in q:
            return _ARTIFACT_ALIASES[alias]
    return None


def default_artifact_for_topic(topic: TopicType) -> Optional[ArtifactType]:
    return _TOPIC_DEFAULT_ARTIFACT.get(topic)
