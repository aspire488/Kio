from __future__ import annotations
from dataclasses import dataclass, field
from enum import Enum, auto
from typing import Optional
import time


class TopicType(str, Enum):
    MOVIES = "MOVIES"
    TV = "TV"
    GAMING = "GAMING"
    SPORTS = "SPORTS"
    MUSIC = "MUSIC"
    BOOKS = "BOOKS"
    PEOPLE = "PEOPLE"
    TECH = "TECH"
    NEWS = "NEWS"
    UNKNOWN = "UNKNOWN"


class ArtifactType(str, Enum):
    TRAILER = "trailer"
    TEASER = "teaser"
    INTERVIEW = "interview"
    GAMEPLAY = "gameplay"
    HIGHLIGHTS = "highlights"
    STANDINGS = "standings"
    FIXTURES = "fixtures"
    RESULTS = "results"
    MUSIC_VIDEO = "music_video"
    REVEAL = "reveal"
    DEVELOPER_UPDATE = "developer_update"
    LIVE_PERFORMANCE = "live_performance"
    BEST_SCENES = "best_scenes"
    BEHIND_THE_SCENES = "behind_the_scenes"
    ENDING_EXPLAINED = "ending_explained"
    DOCUMENTARY = "documentary"
    RECAP = "recap"
    CLIPS = "clips"
    BLOOPERS = "bloopers"
    ANALYSIS = "analysis"
    TACTICAL_BREAKDOWN = "tactical_breakdown"
    PRESS_CONFERENCE = "press_conference"
    MATCH_ANALYSIS = "match_analysis"
    ONBOARD_FOOTAGE = "onboard_footage"
    TEAM_RADIO = "team_radio"
    ACOUSTIC_VERSION = "acoustic_version"
    LYRICS_VIDEO = "lyrics_video"
    CONCERT_FOOTAGE = "concert_footage"
    PRODUCTION_UPDATE = "production_update"
    SET_FOOTAGE = "set_footage"
    EPISODE_PREVIEW = "episode_preview"
    VOICE_ACTOR_INTERVIEW = "voice_actor_interview"
    LATEST_VIDEO = "latest_video"
    PROJECT_BREAKDOWN = "project_breakdown"
    BEST_MOMENTS = "best_moments"
    GOAL_COMPILATION = "goal_compilation"
    AUDIOBOOK = "audiobook"
    BOOK_REVIEW = "book_review"
    BOOK_SUMMARY = "book_summary"
    ADAPTATION_TRAILER = "adaptation_trailer"
    AUTHOR_INTERVIEW = "author_interview"
    READING = "reading"
    SOUNDTRACK = "soundtrack"
    COMPOSER_INTERVIEW = "composer_interview"


class SportsMode(str, Enum):
    RESULTS = "RESULTS"
    FIXTURES = "FIXTURES"
    STANDINGS = "STANDINGS"
    HIGHLIGHTS = "HIGHLIGHTS"
    GENERAL = "GENERAL"


class EventStatus(str, Enum):
    COMPLETED = "completed"
    UPCOMING = "upcoming"
    LIVE = "live"
    UNKNOWN = "unknown"


@dataclass
class EventRecord:
    entity_a: str
    entity_b: str
    score_a: Optional[int] = None
    score_b: Optional[int] = None
    event_type: str = "match"
    competition: str = ""
    status: EventStatus = EventStatus.UNKNOWN
    timestamp: float = field(default_factory=time.time)
    confidence: float = 0.0
    raw_text: str = ""

    def is_valid(self) -> bool:
        if not self.entity_a or not self.entity_b:
            return False
        if len(self.entity_a) < 2 or len(self.entity_b) < 2:
            return False
        # reject obvious garbage
        filler = {"a", "an", "the", "in", "at", "vs", "and", "or", "of", "to"}
        if self.entity_a.lower() in filler or self.entity_b.lower() in filler:
            return False
        return self.confidence >= 0.4

    def display(self) -> str:
        if self.score_a is not None and self.score_b is not None:
            return f"{self.entity_a} {self.score_a}-{self.score_b} {self.entity_b}"
        return f"{self.entity_a} vs {self.entity_b}"


@dataclass
class ArtifactRecord:
    artifact_type: ArtifactType
    topic: TopicType
    subject: str
    url: Optional[str] = None
    title: str = ""
    timestamp: float = field(default_factory=time.time)
    confidence: float = 1.0
    source: str = ""

    def is_valid(self) -> bool:
        return bool(self.subject) and self.confidence >= 0.3


@dataclass
class RelationshipRecord:
    """A semantic entity relationship: subject --predicate--> object.

    Canonical representation of attribution/membership facts extracted from
    evidence ("Annihilation --directed_by--> Alex Garland", "Nvidia
    --led_by--> Jensen Huang", "Stephen Curry --plays_for--> Golden State
    Warriors"). Predicates come from the closed semantic vocabulary in
    relationship_extractor.py — every surface form (founder/CEO/leader/
    president, developer/studio/maker, artist/singer/band, ...) folds into an
    existing canonical family; there is never a per-entity or per-role code
    path.
    """
    subject: str
    predicate: str
    object: str
    confidence: float = 1.0
    timestamp: float = field(default_factory=time.time)
    evidence: str = ""
    source: str = ""
    session_id: str = ""

    def is_valid(self) -> bool:
        if not self.subject or not self.predicate or not self.object:
            return False
        if len(self.subject) < 2 or len(self.object) < 2:
            return False
        # The relationship must connect TWO DISTINCT entities — a self-loop
        # ("X directed X") is never evidence, it is a scan artifact.
        if self.subject.strip().lower() == self.object.strip().lower():
            return False
        _filler = {"a", "an", "the", "in", "at", "of", "to", "by", "and",
                   "or", "with", "for", "is", "are", "was", "were", "it",
                   "this", "that", "he", "she", "they", "him", "her"}
        if self.object.strip().lower() in _filler:
            return False
        return self.confidence >= 0.5

    def inverse_predicate(self) -> Optional[str]:
        """Canonical inverse predicate (directed_by <-> directed_work)."""
        _INV = {
            "directed_by": "directed_work",
            "written_by": "wrote_work",
            "developed_by": "developed_work",
            "published_by": "published_work",
            "manufactured_by": "manufactured_work",
            "composed_by": "composed_work",
            "produced_by": "produced_work",
            "created_by": "created_work",
            "performed_by": "performed_work",
            "founded_by": "founded_org",
            "led_by": "led_org",
            "owned_by": "owned_org",
            "starring": "starred_in",
            "narrated_by": "narrated_work",
            "voiced_by": "voiced_work",
            "plays_for": "has_player",
            "member_of": "has_member",
            "works_at": "employs",
            # inverses of the above, so inverse_predicate() is idempotent
            "directed_work": "directed_by",
            "wrote_work": "written_by",
            "developed_work": "developed_by",
            "published_work": "published_by",
            "manufactured_work": "manufactured_by",
            "composed_work": "composed_by",
            "produced_work": "produced_by",
            "created_work": "created_by",
            "performed_work": "performed_by",
            "founded_org": "founded_by",
            "led_org": "led_by",
            "owned_org": "owned_by",
            "starred_in": "starring",
            "narrated_work": "narrated_by",
            "voiced_work": "voiced_by",
            "has_player": "plays_for",
            "has_member": "member_of",
            "employs": "works_at",
        }
        return _INV.get(self.predicate)


@dataclass
class IntelligenceResult:
    topic: TopicType
    sports_mode: Optional[SportsMode] = None
    events: list[EventRecord] = field(default_factory=list)
    artifacts: list[ArtifactRecord] = field(default_factory=list)
    response_text: str = ""
    subject: str = ""
    confidence: float = 0.0
    source: str = ""
    timestamp: float = field(default_factory=time.time)
    followup_options: list[str] = field(default_factory=list)
    side_effect_result: Optional[dict] = None
