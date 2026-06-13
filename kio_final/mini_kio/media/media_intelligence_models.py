from __future__ import annotations

import time
from dataclasses import dataclass, field, asdict
from enum import Enum
from typing import Any, Dict, List, Optional


# ─────────────────────────── enums ───────────────────────────

class EntityType(str, Enum):
    MOVIE        = "movie"
    TV_SHOW      = "tv_show"
    ACTOR        = "actor"
    MUSIC_ARTIST = "music_artist"
    SONG         = "song"
    ALBUM        = "album"
    PLAYLIST     = "playlist"
    SPORTS_PLAYER = "sports_player"
    SPORTS_TEAM  = "sports_team"
    GAME         = "game"
    YOUTUBER     = "youtuber"
    STREAMER     = "streamer"
    BRAND        = "brand"
    COMPANY      = "company"
    UNKNOWN      = "unknown"


class MediaProvider(str, Enum):
    SPOTIFY  = "spotify"
    YOUTUBE  = "youtube"
    BROWSER  = "browser"
    UNKNOWN  = "unknown"


# ─────────────────────────── dataclasses ───────────────────────────

@dataclass
class ResolvedEntity:
    name: str
    entity_type: EntityType
    provider: MediaProvider = MediaProvider.UNKNOWN
    provider_id: Optional[str] = None      # spotify track id, youtube video id, etc.
    url: Optional[str] = None
    metadata: Dict[str, Any] = field(default_factory=dict)
    confidence: float = 1.0
    resolved_at: float = field(default_factory=time.time)

    def to_dict(self) -> Dict:
        d = asdict(self)
        d["entity_type"] = self.entity_type.value
        d["provider"] = self.provider.value
        return d

    @classmethod
    def from_dict(cls, d: Dict) -> "ResolvedEntity":
        d = dict(d)
        d["entity_type"] = EntityType(d.get("entity_type", "unknown"))
        d["provider"] = MediaProvider(d.get("provider", "unknown"))
        return cls(**d)


@dataclass
class HistoricalMediaSession:
    """Snapshot of a playback moment for historical tracking."""
    session_id: str
    entity: ResolvedEntity
    started_at: float = field(default_factory=time.time)
    ended_at: Optional[float] = None
    position_seconds: float = 0.0
    completed: bool = False
    mood: Optional[str] = None
    activity: Optional[str] = None

    def duration(self) -> float:
        end = self.ended_at or time.time()
        return end - self.started_at

    def to_dict(self) -> Dict:
        d = asdict(self)
        d["entity"] = self.entity.to_dict()
        return d

    @classmethod
    def from_dict(cls, d: Dict) -> "HistoricalMediaSession":
        d = dict(d)
        d["entity"] = ResolvedEntity.from_dict(d["entity"])
        return cls(**d)
