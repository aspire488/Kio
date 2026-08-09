from __future__ import annotations

import time
from dataclasses import dataclass, field
from typing import Optional

from mini_kio.media.media_state import MediaState, PlayerType, MediaType


@dataclass
class MediaSession:
    player: PlayerType
    source: str = "browser"
    tab_id: Optional[int] = None
    process_id: Optional[int] = None
    title: str = ""
    artist: str = ""
    album: str = ""
    media_type: MediaType = MediaType.UNKNOWN
    state: MediaState = MediaState.IDLE
    volume: float = 0.7
    query: str = ""
    url: str = ""
    created_at: float = field(default_factory=time.time)
    updated_at: float = field(default_factory=time.time)
    domain_hint: str = ""
    duration_s: float = 0.0
    position_s: float = 0.0
    is_livestream: bool = False
    muted: bool = False

    def touch(self):
        self.updated_at = time.time()

    def to_dict(self) -> dict:
        return {
            "player": self.player.value,
            "source": self.source,
            "tab_id": self.tab_id,
            "process_id": self.process_id,
            "title": self.title,
            "artist": self.artist,
            "album": self.album,
            "media_type": self.media_type.value,
            "state": self.state.value,
            "volume": self.volume,
            "query": self.query,
            "url": self.url,
            "domain_hint": self.domain_hint,
            "duration_s": self.duration_s,
            "position_s": self.position_s,
            "is_livestream": self.is_livestream,
            "muted": self.muted,
            "created_at": self.created_at,
            "updated_at": self.updated_at,
        }


@dataclass
class MediaCandidate:
    title: str
    url: str = ""
    source: str = ""
    media_type: MediaType = MediaType.UNKNOWN
    confidence: float = 0.0
    provider: str = ""
    artist: str = ""
    duration_s: float = 0.0
    reason: str = ""
    metadata: dict = field(default_factory=dict)

    def to_dict(self) -> dict:
        return {
            "title": self.title,
            "url": self.url,
            "source": self.source,
            "media_type": self.media_type.value,
            "confidence": self.confidence,
            "provider": self.provider,
            "artist": self.artist,
            "reason": self.reason,
        }


def user_facing_media_label(query: str) -> str:
    """A natural label for user-facing media text.

    The media contract: users express INTENT ("Play Never Gonna Give You Up")
    and KIO handles RESOLUTION internally. A YouTube URL/video ID is an
    internal execution artifact and must never be echoed back as though the
    user asked for it. This helper returns the natural query when it looks
    like intent, and "" for a URL/domain-shaped input so the caller can fall
    back to a resolved page title or "the requested media".

    The pipeline lowercases the query before it reaches the provider, so the
    label is title-cased for display ("never gonna give you up" ->
    "Never Gonna Give You Up"). The capitalization is word-first-letter only
    (not str.title(), which mangles apostrophes: "don't" -> "Don'T").
    """
    q = (query or "").strip()
    if not q:
        return ""
    if q.startswith(("http://", "https://", "www.")):
        return ""
    if "youtube.com" in q or "youtu.be" in q:
        return ""
    return " ".join(w[:1].upper() + w[1:] for w in q.split())


@dataclass
class MediaResult:
    success: bool
    message: str = ""
    session: Optional[MediaSession] = None
    candidates: list[MediaCandidate] = field(default_factory=list)
    error: str = ""
    player: str = ""
    # Truthful-fallback contract: when True, the provider ALREADY resolved the
    # exact media (exact video id / tab), so a playback failure must NOT fall
    # back to another provider (e.g. opening a generic search page). MediaManager
    # stops its provider chain and reports the failure as-is.
    no_fallback: bool = False

    def to_dict(self) -> dict:
        d = {"success": self.success, "message": self.message, "player": self.player}
        if self.session:
            d["session"] = self.session.to_dict()
        if self.candidates:
            d["candidates"] = [c.to_dict() for c in self.candidates]
        if self.error:
            d["error"] = self.error
        return d
