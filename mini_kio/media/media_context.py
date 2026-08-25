from __future__ import annotations

import time
from dataclasses import dataclass, field
from typing import Optional

from mini_kio.media.media_session import MediaCandidate
from mini_kio.media.media_intelligence_models import ResolvedEntity, EntityType, MediaArtifactType

MAX_RECENT_EVENTS = 5


@dataclass
class MediaContext:
    current_song: str = ""
    current_artist: str = ""
    current_album: str = ""
    current_video: str = ""
    current_trailer: str = ""
    current_tutorial: str = ""
    current_topic: str = ""
    current_playlist: str = ""
    current_podcast: str = ""
    current_audiobook: str = ""
    last_query: str = ""
    last_provider: str = ""
    last_media_type: str = ""
    last_candidates: list[MediaCandidate] = field(default_factory=list)
    last_selected_candidate: Optional[MediaCandidate] = None

    # New fields for intelligence context (Rule 1)
    topic: Optional[str] = None
    entity: Optional[str] = None
    event: Optional[str] = None
    match_status: Optional[str] = None
    last_completed_match: Optional[str] = None
    media_candidate: Optional[str] = None

    last_resolved_entity: Optional[ResolvedEntity] = None
    current_mood: Optional[str] = None
    current_activity: Optional[str] = None

    # Recent surfaced events from information queries (for follow-up resolution)
    recent_events: list[dict] = field(default_factory=list)

    # Sports intelligence mode: STANDINGS / FIXTURES / RESULTS / HIGHLIGHTS / GENERAL
    sports_mode: str = ""

    # Source quality metadata for retrieval provenance
    source_provider: Optional[str] = None
    source_confidence: float = 0.0
    source_event_type: Optional[str] = None

    # Pending media context for follow-up resolution
    pending_media_query: str = ""
    pending_action: str = ""
    artifact_type: Optional[str] = None
    pending_media_topic: str = ""

    # Rejection tracking: when user says "nah" / "not this" / "next",
    # exclude the current candidate and play the next best.
    rejected_media_ids: list[str] = field(default_factory=list)
    played_media_ids: list[str] = field(default_factory=list)
    current_media_id: str = ""
    current_rejection_query: str = ""  # the original query context for re-rejection
    current_rejection_mood: str = ""
    current_rejection_activity: str = ""
    available_candidates: list = field(default_factory=list)
    candidate_pool_exhausted: bool = False

    def set_current(self, candidate: MediaCandidate):
        self.last_selected_candidate = candidate
        mt = candidate.media_type
        if mt in ("music", "music_video"):
            self.current_song = candidate.title
            if candidate.artist:
                self.current_artist = candidate.artist
        elif mt in ("movie_trailer", "tv_trailer"):
            self.current_trailer = candidate.title
        elif mt == "tutorial":
            self.current_tutorial = candidate.title
        elif mt == "educational":
            self.current_tutorial = candidate.title
            self.current_topic = candidate.title
        elif mt == "podcast":
            self.current_podcast = candidate.title
        elif mt == "audiobook":
            self.current_audiobook = candidate.title
        else:
            self.current_video = candidate.title
        self.last_provider = candidate.provider
        self.last_media_type = mt

    # Mimic MediaEntityMemory functionalities for intelligence context
    def set_last_entity(self, entity: ResolvedEntity) -> None:
        self.last_resolved_entity = entity

    def get_last_entity(self) -> Optional[ResolvedEntity]:
        return self.last_resolved_entity

    def get_last_artist(self) -> Optional[str]:
        if self.last_resolved_entity and self.last_resolved_entity.entity_type == EntityType.MUSIC_ARTIST:
            return self.last_resolved_entity.name
        if self.last_resolved_entity and self.last_resolved_entity.metadata.get("artist"):
            return self.last_resolved_entity.metadata.get("artist")
        return self.current_artist  # Fallback to existing current_artist

    def set_mood(self, mood: str) -> None:
        self.current_mood = mood

    def get_mood(self) -> Optional[str]:
        return self.current_mood

    def set_activity(self, activity: str) -> None:
        self.current_activity = activity

    def get_activity(self) -> Optional[str]:
        return self.current_activity

    def store_event(self, event: dict) -> None:
        self.recent_events.append(event)
        if len(self.recent_events) > MAX_RECENT_EVENTS:
            self.recent_events.pop(0)

    def resolve_reference(self, text: str) -> Optional[str]:
        tl = text.lower().strip()
        if tl in ("it", "this", "that"):
            if self.last_selected_candidate:
                return self.last_selected_candidate.title
            if self.current_song:
                return self.current_song
            if self.current_video:
                return self.current_video
            if self.current_trailer:
                return self.current_trailer
            if self.current_tutorial:
                return self.current_tutorial
            if self.last_resolved_entity: # New: use last resolved entity
                return self.last_resolved_entity.name
            return None

        if tl in ("another one", "another song", "play another"):
            if self.current_song:
                return f"more like {self.current_song}"
            if self.current_artist:
                return f"more by {self.current_artist}"
            if self.last_resolved_entity and self.last_resolved_entity.entity_type == EntityType.MUSIC_ARTIST:
                return f"more by {self.last_resolved_entity.name}"
            return None

        if tl in ("more like this", "similar", "similar music"):
            if self.current_song:
                return f"similar to {self.current_song}"
            if self.current_artist:
                return f"similar to {self.current_artist}"
            if self.last_resolved_entity: # New: use last resolved entity
                return f"similar to {self.last_resolved_entity.name}"
            return None

        if tl.startswith("another song by ") or tl.startswith("another by "):
            artist = tl.replace("another song by ", "").replace("another by ", "").strip()
            if artist:
                if artist in ("him", "her", "them", "it", "that guy", "that girl", "that band"):
                    if self.current_artist:
                        return f"{self.current_artist} songs"
                    if self.last_resolved_entity and self.last_resolved_entity.entity_type == EntityType.MUSIC_ARTIST:
                        return f"{self.last_resolved_entity.name} songs"
                    return None
                return f"{artist} songs"
            if self.current_artist:
                return f"{self.current_artist} songs"
            if self.last_resolved_entity and self.last_resolved_entity.entity_type == EntityType.MUSIC_ARTIST:
                return f"{self.last_resolved_entity.name} songs"
            return None

        for prefix in ("play ", "watch ", "show "):
            if tl.startswith(prefix):
                rest = tl[len(prefix):].strip()
                resolved = self.resolve_reference(rest)
                if resolved != rest:
                    return resolved

        return text

    def get_provider_for_reference(self) -> str:
        return self.last_provider

    def get_media_type_for_reference(self) -> str:
        return self.last_media_type

    def get_topic(self) -> str:
        if self.current_topic:
            return self.current_topic
        if self.current_song:
            return self.current_song
        if self.current_video:
            return self.current_video
        if self.current_trailer:
            return self.current_trailer
        if self.last_resolved_entity: # New: use last resolved entity
            return self.last_resolved_entity.name
        return ""

    def to_dict(self) -> dict:
        d = {
            "current_song": self.current_song,
            "current_artist": self.current_artist,
            "current_album": self.current_album,
            "current_video": self.current_video,
            "current_trailer": self.current_trailer,
            "current_tutorial": self.current_tutorial,
            "current_topic": self.current_topic,
            "current_playlist": self.current_playlist,
            "current_podcast": self.current_podcast,
            "current_audiobook": self.current_audiobook,
            "last_query": self.last_query,
            "last_provider": self.last_provider,
            "last_media_type": self.last_media_type,
            "topic": self.topic,
            "entity": self.entity,
            "event": self.event,
            "match_status": self.match_status,
            "last_completed_match": self.last_completed_match,
            "media_candidate": self.media_candidate,
            "last_resolved_entity": self.last_resolved_entity.to_dict() if self.last_resolved_entity else None,
            "current_mood": self.current_mood,
            "current_activity": self.current_activity,
            "recent_events": self.recent_events,
            "source_provider": self.source_provider,
            "source_confidence": self.source_confidence,
            "source_event_type": self.source_event_type,
            "pending_media_query": self.pending_media_query,
            "pending_action": self.pending_action,
            "artifact_type": self.artifact_type,
            "pending_media_topic": self.pending_media_topic,
        }
        return d
