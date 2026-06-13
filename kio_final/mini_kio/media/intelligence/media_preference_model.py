"""
media_preference_model.py
KIO Media Intelligence Layer — Preference Model
Learns user preferences from play history. Scores candidates.
Feeds into recommendation engine and intelligence routing.
"""

from __future__ import annotations

import math
import time
from collections import defaultdict
from dataclasses import dataclass, field
from typing import Any, Dict, List, Optional, Tuple

from media_entity_memory import (
    EntityType, MediaEntityMemory, MediaProvider, MediaSession, ResolvedEntity
)


# ─────────────────────────── dataclasses ───────────────────────────

@dataclass
class PreferenceScore:
    entity_key: str            # "artist:Imagine Dragons", "genre:rock", etc.
    score: float               # 0.0 – 1.0 normalized
    play_count: int
    last_played: float
    decay_factor: float = 1.0  # applied during scoring

    def decayed_score(self, now: Optional[float] = None) -> float:
        now = now or time.time()
        age_days = (now - self.last_played) / 86400
        decay = math.exp(-0.05 * age_days)   # 5% decay per day
        return self.score * decay * self.decay_factor


@dataclass
class PreferenceSummary:
    top_artists: List[Tuple[str, float]]
    top_genres: List[Tuple[str, float]]
    top_moods: List[Tuple[str, float]]
    top_activities: List[Tuple[str, float]]
    top_providers: List[Tuple[str, float]]
    preferred_entity_types: List[Tuple[str, float]]
    total_sessions: int


@dataclass
class ScoredCandidate:
    entity: ResolvedEntity
    preference_score: float    # 0.0 – 1.0 from preference model
    relevance_score: float     # 0.0 – 1.0 from caller
    final_score: float         # weighted combination
    reasons: List[str] = field(default_factory=list)


# ─────────────────────────── model ───────────────────────────

class MediaPreferenceModel:
    """
    Tracks and scores user preferences from MediaSession history.

    Integration:
        model = MediaPreferenceModel(memory)
        model.rebuild_from_history()           # call at startup
        scores = model.score_candidates(candidates, context_query)
    """

    # Weight config
    ARTIST_WEIGHT   = 0.35
    GENRE_WEIGHT    = 0.20
    MOOD_WEIGHT     = 0.15
    ACTIVITY_WEIGHT = 0.15
    PROVIDER_WEIGHT = 0.05
    TYPE_WEIGHT     = 0.10

    # Scoring blend: preference vs relevance
    PREFERENCE_BLEND = 0.4
    RELEVANCE_BLEND  = 0.6

    def __init__(self, memory: MediaEntityMemory):
        self._mem = memory
        self._artists:    Dict[str, PreferenceScore] = {}
        self._genres:     Dict[str, PreferenceScore] = {}
        self._moods:      Dict[str, PreferenceScore] = {}
        self._activities: Dict[str, PreferenceScore] = {}
        self._providers:  Dict[str, PreferenceScore] = {}
        self._etypes:     Dict[str, PreferenceScore] = {}
        self._total_sessions = 0
        self.rebuild_from_history()

    # ── build / update ────────────────────────────────────────

    def rebuild_from_history(self) -> None:
        """Rebuild preference scores from full session history."""
        self._artists.clear()
        self._genres.clear()
        self._moods.clear()
        self._activities.clear()
        self._providers.clear()
        self._etypes.clear()
        self._total_sessions = 0

        for session in self._mem.get_recent_sessions(500):
            self._ingest_session(session)
        self._normalize_all()

    def ingest_session(self, session: MediaSession) -> None:
        """Call after every completed session for online update."""
        self._ingest_session(session)
        self._normalize_all()
        self._total_sessions += 1

    def _ingest_session(self, session: MediaSession) -> None:
        e = session.entity
        now = session.started_at

        # Artist
        artist = e.metadata.get("artist") or (e.name if e.entity_type == EntityType.MUSIC_ARTIST else None)
        if artist:
            self._bump(self._artists, artist, now, weight=1.0)

        # Genre
        for genre in e.metadata.get("genres", []):
            self._bump(self._genres, genre, now, weight=1.0)

        # Mood
        if session.mood:
            self._bump(self._moods, session.mood, now, weight=1.0)
        if m := self._mem.get_mood():
            self._bump(self._moods, m, now, weight=0.5)

        # Activity
        if session.activity:
            self._bump(self._activities, session.activity, now, weight=1.0)
        if a := self._mem.get_activity():
            self._bump(self._activities, a, now, weight=0.5)

        # Provider
        self._bump(self._providers, e.provider.value, now, weight=1.0)

        # Entity type
        self._bump(self._etypes, e.entity_type.value, now, weight=1.0)

    def _bump(self, store: Dict[str, PreferenceScore], key: str,
              ts: float, weight: float = 1.0) -> None:
        key = key.lower().strip()
        if key not in store:
            store[key] = PreferenceScore(entity_key=key, score=0.0,
                                         play_count=0, last_played=ts)
        ps = store[key]
        ps.play_count += 1
        ps.score      += weight
        ps.last_played = max(ps.last_played, ts)

    def _normalize_all(self) -> None:
        for store in (self._artists, self._genres, self._moods,
                      self._activities, self._providers, self._etypes):
            self._normalize(store)

    @staticmethod
    def _normalize(store: Dict[str, PreferenceScore]) -> None:
        if not store:
            return
        max_score = max(ps.score for ps in store.values()) or 1.0
        for ps in store.values():
            ps.score = ps.score / max_score

    # ── scoring ───────────────────────────────────────────────

    def score_entity(self, entity: ResolvedEntity) -> float:
        """Return preference score 0.0–1.0 for a candidate entity."""
        now = time.time()
        total = 0.0

        artist = entity.metadata.get("artist", "").lower()
        if artist:
            ps = self._artists.get(artist)
            if ps:
                total += self.ARTIST_WEIGHT * ps.decayed_score(now)

        for genre in entity.metadata.get("genres", []):
            ps = self._genres.get(genre.lower())
            if ps:
                total += self.GENRE_WEIGHT * ps.decayed_score(now) / max(1, len(entity.metadata.get("genres", [])))

        ps = self._providers.get(entity.provider.value)
        if ps:
            total += self.PROVIDER_WEIGHT * ps.decayed_score(now)

        ps = self._etypes.get(entity.entity_type.value)
        if ps:
            total += self.TYPE_WEIGHT * ps.decayed_score(now)

        return min(1.0, total)

    def score_candidates(
        self,
        candidates: List[ResolvedEntity],
        relevance_scores: Optional[List[float]] = None,
    ) -> List[ScoredCandidate]:
        """
        Blend preference + relevance scores. Returns sorted list.
        relevance_scores: provider-supplied scores, same order as candidates.
                          If None, defaults to 0.5 for all.
        """
        if relevance_scores is None:
            relevance_scores = [0.5] * len(candidates)

        results: List[ScoredCandidate] = []
        for entity, rel_score in zip(candidates, relevance_scores):
            pref  = self.score_entity(entity)
            final = (self.PREFERENCE_BLEND * pref) + (self.RELEVANCE_BLEND * rel_score)
            reasons = []
            if pref > 0.6:
                reasons.append(f"high preference ({pref:.2f})")
            if rel_score > 0.7:
                reasons.append(f"high relevance ({rel_score:.2f})")
            results.append(ScoredCandidate(
                entity=entity,
                preference_score=pref,
                relevance_score=rel_score,
                final_score=final,
                reasons=reasons,
            ))

        results.sort(key=lambda x: x.final_score, reverse=True)
        return results

    # ── query helpers ─────────────────────────────────────────

    def get_preferred_provider(self) -> Optional[MediaProvider]:
        if not self._providers:
            return None
        best = max(self._providers.values(), key=lambda ps: ps.decayed_score())
        try:
            return MediaProvider(best.entity_key)
        except ValueError:
            return None

    def get_top_artists(self, n: int = 5) -> List[Tuple[str, float]]:
        now = time.time()
        ranked = sorted(self._artists.items(),
                        key=lambda kv: kv[1].decayed_score(now), reverse=True)
        return [(k, v.decayed_score(now)) for k, v in ranked[:n]]

    def get_summary(self) -> PreferenceSummary:
        def top(store: Dict[str, PreferenceScore], n: int = 5):
            now = time.time()
            ranked = sorted(store.items(), key=lambda kv: kv[1].decayed_score(now), reverse=True)
            return [(k, round(v.decayed_score(now), 3)) for k, v in ranked[:n]]

        return PreferenceSummary(
            top_artists=top(self._artists),
            top_genres=top(self._genres),
            top_moods=top(self._moods),
            top_activities=top(self._activities),
            top_providers=top(self._providers),
            preferred_entity_types=top(self._etypes),
            total_sessions=self._total_sessions,
        )


# ─────────────────────────── tests ───────────────────────────

import unittest

class TestMediaPreferenceModel(unittest.TestCase):

    def _setup(self) -> Tuple[MediaEntityMemory, MediaPreferenceModel]:
        mem   = MediaEntityMemory()
        model = MediaPreferenceModel(mem)
        return mem, model

    def _make_session(self, name, artist, genres=None, provider=MediaProvider.SPOTIFY,
                      mood=None, activity=None) -> MediaSession:
        e = ResolvedEntity(
            name=name, entity_type=EntityType.SONG, provider=provider,
            metadata={"artist": artist, "genres": genres or []}
        )
        return MediaSession(session_id=f"s_{name}", entity=e,
                            mood=mood, activity=activity)

    def test_artist_preference_builds(self):
        mem, model = self._setup()
        for i in range(5):
            s = self._make_session(f"Track{i}", "Imagine Dragons")
            mem.push_session(s)
        model.rebuild_from_history()
        top = model.get_top_artists(1)
        self.assertEqual(top[0][0], "imagine dragons")

    def test_score_entity_known_artist(self):
        mem, model = self._setup()
        for i in range(5):
            s = self._make_session(f"T{i}", "Imagine Dragons")
            mem.push_session(s)
        model.rebuild_from_history()
        e = ResolvedEntity("Believer", EntityType.SONG, MediaProvider.SPOTIFY,
                           metadata={"artist": "Imagine Dragons"})
        score = model.score_entity(e)
        self.assertGreater(score, 0.2)

    def test_score_entity_unknown_artist(self):
        mem, model = self._setup()
        e = ResolvedEntity("Random", EntityType.SONG, MediaProvider.SPOTIFY,
                           metadata={"artist": "XYZ Nobody"})
        score = model.score_entity(e)
        self.assertEqual(score, 0.0)

    def test_score_candidates_sorted(self):
        mem, model = self._setup()
        for i in range(10):
            mem.push_session(self._make_session(f"T{i}", "Imagine Dragons"))
        model.rebuild_from_history()

        known   = ResolvedEntity("Believer", EntityType.SONG, MediaProvider.SPOTIFY,
                                 metadata={"artist": "Imagine Dragons"})
        unknown = ResolvedEntity("Other",   EntityType.SONG, MediaProvider.SPOTIFY,
                                 metadata={"artist": "Nobody"})
        ranked = model.score_candidates([unknown, known], [0.5, 0.5])
        self.assertEqual(ranked[0].entity.name, "Believer")

    def test_preferred_provider(self):
        mem, model = self._setup()
        for i in range(5):
            mem.push_session(self._make_session(f"T{i}", "Artist", provider=MediaProvider.SPOTIFY))
        model.rebuild_from_history()
        self.assertEqual(model.get_preferred_provider(), MediaProvider.SPOTIFY)

    def test_mood_tracking(self):
        mem, model = self._setup()
        mem.push_session(self._make_session("T1", "A", mood="chill"))
        mem.push_session(self._make_session("T2", "B", mood="chill"))
        model.rebuild_from_history()
        summary = model.get_summary()
        moods = dict(summary.top_moods)
        self.assertIn("chill", moods)

    def test_ingest_session_online(self):
        mem, model = self._setup()
        s = self._make_session("Thunder", "Imagine Dragons")
        model.ingest_session(s)
        top = model.get_top_artists(3)
        self.assertTrue(any("imagine dragons" in t[0] for t in top))

    def test_summary_structure(self):
        mem, model = self._setup()
        summary = model.get_summary()
        self.assertIsInstance(summary.top_artists, list)
        self.assertIsInstance(summary.top_genres, list)
        self.assertIsInstance(summary.top_moods, list)

    def test_relevance_blend(self):
        mem, model = self._setup()
        e1 = ResolvedEntity("A", EntityType.SONG, MediaProvider.SPOTIFY, metadata={"artist": "X"})
        e2 = ResolvedEntity("B", EntityType.SONG, MediaProvider.SPOTIFY, metadata={"artist": "Y"})
        ranked = model.score_candidates([e1, e2], [0.9, 0.1])
        self.assertEqual(ranked[0].entity.name, "A")  # relevance dominates

    def test_decay_reduces_score(self):
        mem, model = self._setup()
        old_ts = time.time() - 86400 * 30  # 30 days ago
        ps = PreferenceScore(entity_key="test", score=1.0,
                             play_count=10, last_played=old_ts)
        self.assertLess(ps.decayed_score(), 0.3)


if __name__ == "__main__":
    unittest.main()
