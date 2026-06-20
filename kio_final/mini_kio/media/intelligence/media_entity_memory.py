"""
media_entity_memory.py
KIO Media Intelligence Layer — Entity Memory
Stores resolved entities, sessions, history with TTL.
Plugs into existing MediaContext / MediaManager.
"""

from __future__ import annotations

import json
import time
import threading
from dataclasses import dataclass, field
from enum import Enum
from pathlib import Path
from typing import Any, Dict, List, Optional
from collections import deque

from mini_kio.media.media_intelligence_models import (
    EntityType, MediaProvider, ResolvedEntity, HistoricalMediaSession
)


# ─────────────────────────── enums ───────────────────────────







# ─────────────────────────── dataclasses ───────────────────────────







@dataclass
class MemoryEntry:
    key: str
    value: Any
    created_at: float = field(default_factory=time.time)
    ttl_seconds: float = 3600.0        # default 1 hour

    def is_expired(self) -> bool:
        return time.time() > self.created_at + self.ttl_seconds

    def to_dict(self) -> Dict:
        return {
            "key": self.key,
            "value": self.value,
            "created_at": self.created_at,
            "ttl_seconds": self.ttl_seconds,
        }

    @classmethod
    def from_dict(cls, d: Dict) -> "MemoryEntry":
        return cls(**d)


# ─────────────────────────── main class ───────────────────────────

class MediaEntityMemory:
    """
    Central KV + history store for media intelligence.
    Thread-safe. Persistent to JSON. TTL-aware.

    Integration: instantiate once, pass into MediaIntelligence, ReferenceResolver, etc.
    """

    # TTL constants (seconds)
    TTL_LAST_TRACK       = 86400      # 24h
    TTL_LAST_ARTIST      = 86400
    TTL_LAST_ALBUM       = 86400
    TTL_LAST_VIDEO       = 86400
    TTL_LAST_PLAYLIST    = 86400
    TTL_LAST_SESSION     = 3600       # 1h  — "that song" reference window
    TTL_OFFER            = 300        # 5m  — pending offers expire fast
    TTL_MOOD             = 7200       # 2h
    TTL_ACTIVITY         = 7200
    TTL_RECOMMENDATION   = 1800       # 30m
    HISTORY_MAX          = 500        # max sessions kept

    def __init__(self, persist_path: Optional[str] = None):
        self._store: Dict[str, MemoryEntry] = {}
        self._history: deque[HistoricalMediaSession] = deque(maxlen=self.HISTORY_MAX)
        self._lock = threading.RLock()
        self._persist_path = Path(persist_path) if persist_path else None
        if self._persist_path and self._persist_path.exists():
            self._load()

    # ── core KV ──────────────────────────────────────────────

    def set(self, key: str, value: Any, ttl: float = 3600.0) -> None:
        with self._lock:
            self._store[key] = MemoryEntry(key=key, value=value, ttl_seconds=ttl)

    def get(self, key: str, default: Any = None) -> Any:
        with self._lock:
            entry = self._store.get(key)
            if entry is None:
                return default
            if entry.is_expired():
                del self._store[key]
                return default
            return entry.value

    def delete(self, key: str) -> None:
        with self._lock:
            self._store.pop(key, None)

    def exists(self, key: str) -> bool:
        return self.get(key) is not None

    # ── typed entity shortcuts ────────────────────────────────

    def set_last_entity(self, entity: ResolvedEntity) -> None:
        """Update all relevant last_* keys from a single entity."""
        with self._lock:
            et = entity.entity_type
            
            # PHASE 4: Context Isolation
            # ONLY update last_entity if it's a clear media entity
            # Browser apps (Telegram, Chrome) or general companies should NOT overwrite the "Reference Subject"
            media_entities = {
                EntityType.SONG, EntityType.ALBUM, EntityType.MUSIC_ARTIST,
                EntityType.MOVIE, EntityType.TV_SHOW, EntityType.ACTOR,
                EntityType.SPORTS_PLAYER, EntityType.SPORTS_TEAM,
                EntityType.GAME, EntityType.PLAYLIST, EntityType.YOUTUBER,
                EntityType.STREAMER, EntityType.BOOK, EntityType.AUTHOR,
                EntityType.UNKNOWN,
            }
            
            if et in media_entities:
                self.set("last_entity", entity.to_dict(), self.TTL_LAST_SESSION)
                print(f"[MEDIA_CONTEXT] entity={entity.name}") # Required log
            
            if et == EntityType.SONG:
                self.set("last_track", entity.to_dict(), self.TTL_LAST_TRACK)
                if artist := entity.metadata.get("artist"):
                    self.set("last_artist", artist, self.TTL_LAST_ARTIST)
                if album := entity.metadata.get("album"):
                    self.set("last_album", album, self.TTL_LAST_ALBUM)
            elif et in (EntityType.MOVIE, EntityType.TV_SHOW, EntityType.YOUTUBER,
                        EntityType.STREAMER, EntityType.GAME):
                self.set("last_video", entity.to_dict(), self.TTL_LAST_VIDEO)
            elif et == EntityType.ALBUM:
                self.set("last_album", entity.to_dict(), self.TTL_LAST_ALBUM)
            elif et == EntityType.PLAYLIST:
                self.set("last_playlist", entity.to_dict(), self.TTL_LAST_PLAYLIST)
            elif et == EntityType.MUSIC_ARTIST:
                self.set("last_artist", entity.to_dict(), self.TTL_LAST_ARTIST)

    def get_last_entity(self) -> Optional[ResolvedEntity]:
        d = self.get("last_entity")
        return ResolvedEntity.from_dict(d) if d else None

    def get_last_track(self) -> Optional[ResolvedEntity]:
        d = self.get("last_track")
        return ResolvedEntity.from_dict(d) if d else None

    def get_last_artist(self) -> Optional[str]:
        v = self.get("last_artist")
        if isinstance(v, dict):
            return v.get("name")
        return v

    def get_last_album(self) -> Optional[str]:
        v = self.get("last_album")
        if isinstance(v, dict):
            return v.get("name")
        return v

    def get_last_video(self) -> Optional[ResolvedEntity]:
        d = self.get("last_video")
        return ResolvedEntity.from_dict(d) if d else None

    def get_last_playlist(self) -> Optional[ResolvedEntity]:
        d = self.get("last_playlist")
        return ResolvedEntity.from_dict(d) if d else None

    # ── mood / activity ───────────────────────────────────────

    def set_mood(self, mood: str) -> None:
        self.set("last_mood", mood, self.TTL_MOOD)

    def get_mood(self) -> Optional[str]:
        return self.get("last_mood")

    def set_activity(self, activity: str) -> None:
        self.set("last_activity", activity, self.TTL_ACTIVITY)

    def get_activity(self) -> Optional[str]:
        return self.get("last_activity")

    # ── session history ───────────────────────────────────────

    def push_session(self, session: HistoricalMediaSession) -> None:
        with self._lock:
            self._history.appendleft(session)
            self.set_last_entity(session.entity)
            self.set("last_session_id", session.session_id, self.TTL_LAST_SESSION)

    def get_recent_sessions(self, n: int = 20) -> List[HistoricalMediaSession]:
        with self._lock:
            return list(self._history)[:n]

    def get_sessions_from_yesterday(self) -> List[HistoricalMediaSession]:
        now = time.time()
        yesterday_start = now - 86400 * 2
        yesterday_end   = now - 86400
        with self._lock:
            return [
                s for s in self._history
                if yesterday_start <= s.started_at <= yesterday_end
            ]

    def get_sessions_by_artist(self, artist: str) -> List[HistoricalMediaSession]:
        artist_lower = artist.lower()
        with self._lock:
            return [
                s for s in self._history
                if s.entity.metadata.get("artist", "").lower() == artist_lower
                or s.entity.name.lower() == artist_lower
            ]

    # ── cleanup ───────────────────────────────────────────────

    def cleanup_expired(self) -> int:
        with self._lock:
            expired = [k for k, v in self._store.items() if v.is_expired()]
            for k in expired:
                del self._store[k]
            return len(expired)

    def flush(self) -> None:
        """Wipe all in-memory store (keep history)."""
        with self._lock:
            self._store.clear()

    # ── persistence ───────────────────────────────────────────

    def save(self) -> None:
        if not self._persist_path:
            return
        with self._lock:
            data = {
                "store":   {k: v.to_dict() for k, v in self._store.items()},
                "history": [s.to_dict() for s in self._history],
            }
        self._persist_path.write_text(json.dumps(data, indent=2))

    def _load(self) -> None:
        try:
            data = json.loads(self._persist_path.read_text())
            for k, v in data.get("store", {}).items():
                entry = MemoryEntry.from_dict(v)
                if not entry.is_expired():
                    self._store[k] = entry
            for s in data.get("history", []):
                try:
                    self._history.append(HistoricalMediaSession.from_dict(s))
                except Exception:
                    pass
        except Exception:
            pass   # corrupt file → start fresh


# ─────────────────────────── tests ───────────────────────────

import unittest

class TestMediaEntityMemory(unittest.TestCase):

    def setUp(self):
        self.mem = MediaEntityMemory()

    def _make_entity(self, name="Believer", etype=EntityType.SONG, artist="Imagine Dragons"):
        return ResolvedEntity(
            name=name,
            entity_type=etype,
            provider=MediaProvider.SPOTIFY,
            metadata={"artist": artist, "album": "Evolve"},
        )

    def test_set_get_basic(self):
        self.mem.set("foo", "bar", ttl=60)
        self.assertEqual(self.mem.get("foo"), "bar")

    def test_expired_returns_default(self):
        self.mem.set("x", "y", ttl=-1)   # already expired
        self.assertIsNone(self.mem.get("x"))

    def test_set_last_entity_song(self):
        e = self._make_entity()
        self.mem.set_last_entity(e)
        self.assertEqual(self.mem.get_last_track().name, "Believer")
        self.assertEqual(self.mem.get_last_artist(), "Imagine Dragons")

    def test_set_last_entity_artist(self):
        e = self._make_entity(name="Imagine Dragons", etype=EntityType.MUSIC_ARTIST, artist="")
        self.mem.set_last_entity(e)
        self.assertIsNotNone(self.mem.get_last_entity())

    def test_session_history(self):
        e = self._make_entity()
        s = HistoricalMediaSession(session_id="s1", entity=e)
        self.mem.push_session(s)
        recent = self.mem.get_recent_sessions(5)
        self.assertEqual(len(recent), 1)
        self.assertEqual(recent[0].session_id, "s1")

    def test_sessions_yesterday(self):
        e = self._make_entity()
        yesterday = time.time() - 86400 - 1800
        s = HistoricalMediaSession(session_id="y1", entity=e, started_at=yesterday)
        self.mem._history.append(s)
        results = self.mem.get_sessions_from_yesterday()
        self.assertEqual(len(results), 1)

    def test_cleanup_expired(self):
        self.mem.set("a", 1, ttl=60)
        self.mem.set("b", 2, ttl=-1)
        removed = self.mem.cleanup_expired()
        self.assertEqual(removed, 1)
        self.assertEqual(self.mem.get("a"), 1)

    def test_mood_activity(self):
        self.mem.set_mood("chill")
        self.mem.set_activity("studying")
        self.assertEqual(self.mem.get_mood(), "chill")
        self.assertEqual(self.mem.get_activity(), "studying")

    def test_delete(self):
        self.mem.set("z", 99)
        self.mem.delete("z")
        self.assertIsNone(self.mem.get("z"))

    def test_exists(self):
        self.mem.set("k", "v")
        self.assertTrue(self.mem.exists("k"))
        self.assertFalse(self.mem.exists("nonexistent"))

    def test_persist_roundtrip(self, tmp_path_str="/tmp/test_media_mem.json"):
        mem1 = MediaEntityMemory(persist_path=tmp_path_str)
        mem1.set("key1", "val1", ttl=3600)
        e = self._make_entity()
        mem1.push_session(HistoricalMediaSession(session_id="s_persist", entity=e))
        mem1.save()

        mem2 = MediaEntityMemory(persist_path=tmp_path_str)
        self.assertEqual(mem2.get("key1"), "val1")
        self.assertEqual(len(mem2.get_recent_sessions(5)), 1)

        import os; os.unlink(tmp_path_str)

    def test_get_sessions_by_artist(self):
        e1 = self._make_entity("Believer", EntityType.SONG, "Imagine Dragons")
        e2 = self._make_entity("Thunder",  EntityType.SONG, "Imagine Dragons")
        e3 = self._make_entity("Shape of You", EntityType.SONG, "Ed Sheeran")
        for i, e in enumerate([e1, e2, e3]):
            self.mem.push_session(HistoricalMediaSession(session_id=f"s{i}", entity=e))
        results = self.mem.get_sessions_by_artist("Imagine Dragons")
        self.assertEqual(len(results), 2)


if __name__ == "__main__":
    unittest.main()
