"""Media subsystem contracts — formalizes the behavior traced during
discovery. Every media provider must conform to these interfaces so
the pipeline can route, verify, and recover uniformly.

Contracts enforced:
  1. Content-type intent scoring (MediaType → provider priority)
  2. Playback verification (identity gate + play state loop)
  3. Session lifecycle (register → play → verify → update → cleanup)
  4. Provider capabilities (what each provider can and cannot do)
"""

from __future__ import annotations

import enum
from abc import ABC, abstractmethod
from dataclasses import dataclass, field
from typing import Any, Optional


class MediaType(enum.Enum):
    """Content types detected from user queries."""
    MUSIC = "music"
    VIDEO = "video"
    NEWS = "news"
    PODCAST = "podcast"
    RADIO = "radio"
    PLAYLIST = "playlist"
    UNKNOWN = "unknown"


class PlaybackState(enum.Enum):
    """Playback states tracked during verification."""
    IDLE = "idle"
    BUFFERING = "buffering"
    PLAYING = "playing"
    PAUSED = "paused"
    STOPPED = "stopped"
    ERROR = "error"


class ProviderTier(enum.Enum):
    """Provider priority tiers — lower number = higher priority."""
    PRIMARY = 1      # YouTube, Spotify (full verification)
    SECONDARY = 2    # Browser, LocalMedia (partial verification)
    FALLBACK = 3     # Any web source (no verification)


@dataclass
class ContentIntent:
    """Parsed content-type intent from user query."""
    media_type: MediaType
    query: str
    confidence: float  # 0.0-1.0
    platform_hint: Optional[str] = None  # e.g., "youtube", "spotify"
    is_explicit: bool = False  # user said "play X on Y"


@dataclass
class PlaybackVerification:
    """Result of playback verification."""
    state: PlaybackState
    identity_match: bool  # did the right content play?
    position_s: float = 0.0  # current position in seconds
    duration_s: float = 0.0  # total duration
    probe_used: str = "unknown"
    error_message: Optional[str] = None


@dataclass
class MediaSession:
    """Tracks an active media session."""
    session_id: str
    user_id: int
    media_type: MediaType
    platform: str
    query: str
    state: PlaybackState = PlaybackState.IDLE
    current_index: int = 0
    queue: list[dict[str, Any]] = field(default_factory=list)
    metadata: dict[str, Any] = field(default_factory=dict)


class MediaProvider(ABC):
    """Contract that every media provider must implement.

    Providers are ranked by ContentIntent scoring. The pipeline picks the
    highest-priority provider that supports the requested MediaType and
    passes playback verification.
    """

    @abstractmethod
    def id(self) -> str:
        """Unique provider identifier (e.g., 'youtube', 'spotify')."""
        ...

    @abstractmethod
    def tier(self) -> ProviderTier:
        """Priority tier for provider selection."""
        ...

    @abstractmethod
    def supported_types(self) -> list[MediaType]:
        """Content types this provider can handle."""
        ...

    @abstractmethod
    def search(self, query: str, media_type: MediaType, limit: int = 5) -> list[dict[str, Any]]:
        """Search for content. Returns list of candidates with at minimum:
        - title: str
        - url: str
        - duration_s: float (optional)
        - thumbnail: str (optional)
        """
        ...

    @abstractmethod
    def play(self, candidate: dict[str, Any], session: MediaSession) -> dict[str, Any]:
        """Start playback of a candidate. Returns:
        - success: bool
        - message: str
        - session updates (state, metadata)
        """
        ...

    def verify_playback(self, session: MediaSession) -> PlaybackVerification:
        """Verify playback is actually happening. Default: no verification."""
        return PlaybackVerification(
            state=PlaybackState.PLAYING,
            identity_match=True,
            probe_used="default-no-verify",
        )

    def pause(self, session: MediaSession) -> dict[str, Any]:
        return {"success": False, "message": f"Pause not supported by {self.id()}"}

    def resume(self, session: MediaSession) -> dict[str, Any]:
        return {"success": False, "message": f"Resume not supported by {self.id()}"}

    def next_track(self, session: MediaSession) -> dict[str, Any]:
        return {"success": False, "message": f"Next not supported by {self.id()}"}

    def prev_track(self, session: MediaSession) -> dict[str, Any]:
        return {"success": False, "message": f"Prev not supported by {self.id()}"}

    def set_volume(self, level: int, session: MediaSession) -> dict[str, Any]:
        return {"success": False, "message": f"Volume not supported by {self.id()}"}

    def get_position(self, session: MediaSession) -> dict[str, Any]:
        return {"position_s": 0, "duration_s": 0}

    def health(self) -> dict[str, Any]:
        return {"status": "healthy", "provider": self.id()}


# ── Content-type intent scoring ────────────────────────────────────────────

# Priority mapping: MediaType → ordered list of provider IDs.
# The pipeline tries providers in order; first healthy one wins.
CONTENT_TYPE_PRIORITY: dict[MediaType, list[str]] = {
    MediaType.MUSIC: ["youtube", "browser", "local"],
    MediaType.VIDEO: ["youtube", "browser"],
    MediaType.NEWS: ["youtube", "browser"],  # YouTube news channels + web
    MediaType.PODCAST: ["youtube", "browser"],
    MediaType.RADIO: ["youtube", "browser"],  # YouTube hosts radio/livestream content
    MediaType.PLAYLIST: ["youtube", "browser"],
    MediaType.UNKNOWN: ["youtube", "browser", "local"],
}

# Scoring weights for content-type intent detection.
# Higher weight = stronger signal that the query matches this type.
MEDIA_TYPE_KEYWORDS: dict[MediaType, list[str]] = {
    MediaType.MUSIC: [
        "song", "track", "album", "artist", "band", "singer",
        "playlist", "music", "listen", "play", "hear", "audio",
        "spotify", "soundcloud", "beats", "tune", "melody",
    ],
    MediaType.VIDEO: [
        "video", "watch", "movie", "film", "clip", "youtube",
        "tutorial", "episode", "series", "stream", "recording",
    ],
    MediaType.NEWS: [
        "news", "headline", "breaking", "today", "latest",
        "current events", "update", "report", "press",
    ],
    MediaType.PODCAST: [
        "podcast", "episode", "interview", "talk", "show",
        "episode", "series", "episode",
    ],
    MediaType.RADIO: [
        "radio", "station", "fm", "am", "live stream",
    ],
}


def score_content_intent(query: str) -> ContentIntent:
    """Score a user query against all media types and return the best match.

    This is the universal content-type intent abstraction. It replaces
    the ad-hoc keyword matching in _detect_media_type with a weighted
    scoring system that considers:
    1. Keyword density (how many type-specific words appear)
    2. Platform hints (user said "on youtube")
    3. Explicit markers (user said "play" = music default)
    """
    ql = query.lower()
    scores: dict[MediaType, float] = {}

    for media_type, keywords in MEDIA_TYPE_KEYWORDS.items():
        # Keyword density: count matching words, normalize by query length
        matches = sum(1 for kw in keywords if kw in ql)
        word_count = max(len(ql.split()), 1)
        density = matches / word_count if word_count > 0 else 0
        scores[media_type] = matches + density * 2  # density gets 2x weight

    # Platform hint bonus: "on youtube" boosts video/news
    platform_hints = {
        "youtube": [MediaType.VIDEO, MediaType.NEWS],
        "spotify": [MediaType.MUSIC, MediaType.PODCAST],
        "soundcloud": [MediaType.MUSIC],
    }
    for platform, types in platform_hints.items():
        if platform in ql:
            for t in types:
                scores[t] = scores.get(t, 0) + 3  # strong bonus

    # Explicit marker: "play X" without other type words = music
    if "play" in ql and all(s < 2 for s in scores.values()):
        scores[MediaType.MUSIC] = scores.get(MediaType.MUSIC, 0) + 2

    if not scores or max(scores.values()) == 0:
        return ContentIntent(
            media_type=MediaType.UNKNOWN,
            query=query,
            confidence=0.0,
        )

    best_type = max(scores, key=lambda k: scores[k])
    total = sum(scores.values())
    confidence = scores[best_type] / total if total > 0 else 0.0

    # Detect explicit platform
    platform_hint = None
    for platform in platform_hints:
        if platform in ql:
            platform_hint = platform
            break

    return ContentIntent(
        media_type=best_type,
        query=query,
        confidence=min(confidence, 1.0),
        platform_hint=platform_hint,
        is_explicit=platform_hint is not None,
    )
