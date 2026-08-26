"""
media_recommendation_engine.py
KIO Media Intelligence Layer — Recommendation Engine
Generates ranked media recommendations from context + preferences.
Plugs into MediaManager for provider search dispatch.
"""

from __future__ import annotations

import re
import time
from dataclasses import dataclass, field
from enum import Enum
from typing import Any, Callable, Dict, List, Optional, Tuple

from mini_kio.media.intelligence.media_entity_memory import (
    EntityType, MediaEntityMemory, MediaProvider, ResolvedEntity
)
from mini_kio.media.intelligence.media_preference_model import MediaPreferenceModel, ScoredCandidate
from mini_kio.media.intelligence.media_reference_resolver import (
    MediaReferenceResolver, ReferenceResolution, ReferenceType
)


# ─────────────────────────── enums ───────────────────────────

class RecommendationStrategy(str, Enum):
    SIMILAR_ARTIST      = "similar_artist"
    SIMILAR_GENRE       = "similar_genre"
    MOOD_MATCH          = "mood_match"
    ACTIVITY_MATCH      = "activity_match"
    CONTINUATION        = "continuation"
    HISTORY_BASED       = "history_based"
    TRENDING            = "trending"
    EXPLICIT_QUERY      = "explicit_query"


# ─────────────────────────── dataclasses ───────────────────────────

@dataclass
class RecommendationRequest:
    utterance: str
    strategy: RecommendationStrategy
    seed_entity: Optional[ResolvedEntity] = None
    seed_artist: Optional[str] = None
    seed_mood: Optional[str] = None
    seed_activity: Optional[str] = None
    search_query: str = ""
    provider_hint: Optional[MediaProvider] = None
    max_results: int = 5

    def effective_query(self) -> str:
        if self.search_query:
            return self.search_query
        if self.seed_entity:
            return self.seed_entity.name
        if self.seed_artist:
            return self.seed_artist
        if self.seed_mood:
            return f"{self.seed_mood} music"
        if self.seed_activity:
            return f"{self.seed_activity} playlist"
        return ""


@dataclass
class RecommendationResult:
    request: RecommendationRequest
    candidates: List[ScoredCandidate]
    strategy_used: RecommendationStrategy
    confidence: float
    generated_at: float = field(default_factory=time.time)
    fallback_used: bool = False

    @property
    def top(self) -> Optional[ScoredCandidate]:
        return self.candidates[0] if self.candidates else None

    def best_entity(self) -> Optional[ResolvedEntity]:
        return self.top.entity if self.top else None


# ─────────────────────────── similar-artist seed map ───────────────────────────
# Static fallback — in production this would hit a music graph API.
_SIMILAR_ARTISTS: Dict[str, List[str]] = {
    "imagine dragons":  ["OneRepublic", "Bastille", "Maroon 5", "Coldplay"],
    "ed sheeran":       ["Sam Smith", "James Arthur", "Lewis Capaldi", "Shawn Mendes"],
    "the weeknd":       ["Drake", "Post Malone", "6LACK", "Bryson Tiller"],
    "drake":            ["Lil Wayne", "Nicki Minaj", "Travis Scott", "J. Cole"],
    "taylor swift":     ["Olivia Rodrigo", "Katy Perry", "Ariana Grande", "Selena Gomez"],
    "billie eilish":    ["Halsey", "Clairo", "Lorde", "Gracie Abrams"],
    "coldplay":         ["Imagine Dragons", "U2", "Muse", "Snow Patrol"],
    "eminem":           ["Logic", "Machine Gun Kelly", "NF", "Joyner Lucas"],
    "arijit singh":     ["Atif Aslam", "Armaan Malik", "Jubin Nautiyal", "Darshan Raval"],
    "ap dhillon":       ["Shubh", "Karan Aujla", "Diljit Dosanjh", "Sidhu Moosewala"],
}

# Mood → search query templates
_MOOD_QUERIES: Dict[str, List[str]] = {
    "chill":      ["chill vibes playlist", "lofi chill beats", "calm music mix"],
    "hype":       ["hype songs 2024", "pump up playlist", "high energy hits"],
    "sad":        ["sad songs playlist", "emotional music", "heartbreak playlist"],
    "happy":      ["feel good songs", "happy music playlist", "upbeat hits"],
    "focus":      ["focus music deep work", "concentration playlist", "study beats"],
    "romantic":   ["romantic songs playlist", "love songs", "date night music"],
    "angry":      ["aggressive music playlist", "metal workout", "hard rock mix"],
    "calm":       ["peaceful music", "ambient sounds", "relaxing instrumental"],
}

# Activity → search query templates
_ACTIVITY_QUERIES: Dict[str, List[str]] = {
    "gym":        ["gym workout playlist", "beast mode music", "high tempo gym songs"],
    "study":      ["study music lofi", "focus playlist coding", "study with me beats"],
    "sleep":      ["sleep music", "sleep sounds calm", "relaxing bedtime playlist"],
    "running":    ["running playlist 2024", "jogging motivation songs", "cardio music"],
    "driving":    ["driving songs road trip", "car music playlist", "highway beats"],
    "gaming":     ["gaming music playlist", "epic gaming soundtrack", "game background music"],
    "party":      ["party hits 2024", "dance party playlist", "banger songs"],
    "meditation": ["meditation music", "zen sounds", "mindfulness playlist"],
}


# ─────────────────────────── engine ───────────────────────────

class MediaRecommendationEngine:
    """
    Generates RecommendationRequest from utterance + context.
    Does NOT call providers directly — returns request with search_query
    for MediaManager / MediaIntelligence to dispatch.

    Integration:
        engine = MediaRecommendationEngine(memory, resolver, preference_model)
        result = engine.recommend("play something similar")
        query  = result.request.effective_query()
        # → pass query to MediaManager.search(query, provider=result.request.provider_hint)
    """

    def __init__(
        self,
        memory: MediaEntityMemory,
        resolver: MediaReferenceResolver,
        preference_model: MediaPreferenceModel,
    ):
        self._mem   = memory
        self._res   = resolver
        self._prefs = preference_model

    # ── public entry ─────────────────────────────────────────

    def recommend(self, utterance: str) -> RecommendationResult:
        """
        Derive recommendation strategy + query from utterance.
        Falls back through strategy chain until something works.
        """
        # Step 1: reference resolution
        ref = self._res.resolve(utterance)

        # Step 2: pick strategy
        request = self._build_request(utterance, ref)

        # Step 3: score existing candidates if any
        candidates = self._build_candidates_from_history(request)

        return RecommendationResult(
            request=request,
            candidates=candidates,
            strategy_used=request.strategy,
            confidence=self._estimate_confidence(request, candidates),
        )

    # ── request building ──────────────────────────────────────

    def _build_request(self, utterance: str, ref: ReferenceResolution) -> RecommendationRequest:
        text = utterance.lower()

        # Similar to last track or watch next
        if re.search(r"\b(something similar|more like (this|that)|similar)\b", text):
            return self._similar_request(utterance)
        if re.search(r"\b(what should i (watch|listen to?)\s+(next|today)|what to (watch|listen)|(watch|listen) next|next to (watch|listen))\b", text):
            return self._next_request(utterance)

        # Mood
        if ref.reference_type == ReferenceType.MOOD and ref.mood:
            return RecommendationRequest(
                utterance=utterance,
                strategy=RecommendationStrategy.MOOD_MATCH,
                seed_mood=ref.mood,
                search_query=self._mood_query(ref.mood),
                provider_hint=MediaProvider.SPOTIFY,
            )

        # Activity
        if ref.reference_type == ReferenceType.ACTIVITY and ref.activity:
            return RecommendationRequest(
                utterance=utterance,
                strategy=RecommendationStrategy.ACTIVITY_MATCH,
                seed_activity=ref.activity,
                search_query=self._activity_query(ref.activity),
                provider_hint=MediaProvider.SPOTIFY,
            )

        # Continuation (another by artist)
        if ref.reference_type == ReferenceType.CONTINUATION:
            artist = ref.query_override or self._mem.get_last_artist()
            return RecommendationRequest(
                utterance=utterance,
                strategy=RecommendationStrategy.CONTINUATION,
                seed_artist=artist,
                search_query=f"{artist} popular songs" if artist else "",
                provider_hint=self._prefs.get_preferred_provider(),
            )

        # History-based ("what I listened to yesterday")
        if ref.reference_type == ReferenceType.TEMPORAL:
            sessions = self._mem.get_sessions_from_yesterday()
            if sessions:
                seed = sessions[0].entity
                return RecommendationRequest(
                    utterance=utterance,
                    strategy=RecommendationStrategy.HISTORY_BASED,
                    seed_entity=seed,
                    search_query=seed.name,
                    provider_hint=seed.provider if seed.provider != MediaProvider.UNKNOWN else None,
                )

        # Explicit query override from reference
        if ref.query_override:
            return RecommendationRequest(
                utterance=utterance,
                strategy=RecommendationStrategy.EXPLICIT_QUERY,
                search_query=ref.query_override,
                provider_hint=self._prefs.get_preferred_provider(),
            )

        # Fallback: history-based on top artist
        top_artists = self._prefs.get_top_artists(1)
        if top_artists:
            artist = top_artists[0][0]
            return RecommendationRequest(
                utterance=utterance,
                strategy=RecommendationStrategy.HISTORY_BASED,
                seed_artist=artist,
                search_query=f"{artist} top songs",
                provider_hint=self._prefs.get_preferred_provider(),
            )

        # Final fallback: use the utterance itself as a search query
        # rather than hardcoding "trending music 2024"
        _query = utterance.strip() if utterance else "popular music"
        return RecommendationRequest(
            utterance=utterance,
            strategy=RecommendationStrategy.TRENDING,
            search_query=_query,
        )

    def _next_request(self, utterance: str) -> RecommendationRequest:
        """Handle 'what should I watch/listen to next' patterns."""
        last = self._mem.get_last_entity()
        if last:
            if last.entity_type in (EntityType.MOVIE, EntityType.TV_SHOW):
                return RecommendationRequest(
                    utterance=utterance,
                    strategy=RecommendationStrategy.SIMILAR_GENRE,
                    seed_entity=last,
                    search_query=f"movies like {last.name} similar films recommendations",
                    provider_hint=MediaProvider.UNKNOWN,
                )
            if last.entity_type == EntityType.SONG:
                artist = last.metadata.get("artist", "")
                similar_list = _SIMILAR_ARTISTS.get(artist.lower(), [])
                query = f"{similar_list[0]} top songs" if similar_list else f"music similar to {last.name} songs"
                return RecommendationRequest(
                    utterance=utterance,
                    strategy=RecommendationStrategy.SIMILAR_ARTIST,
                    seed_entity=last,
                    seed_artist=artist,
                    search_query=query,
                    provider_hint=MediaProvider.SPOTIFY,
                )
            if last.entity_type in (EntityType.BOOK, EntityType.AUTHOR):
                return RecommendationRequest(
                    utterance=utterance,
                    strategy=RecommendationStrategy.SIMILAR_GENRE,
                    seed_entity=last,
                    search_query=f"books like {last.name} similar reads recommendations",
                    provider_hint=MediaProvider.UNKNOWN,
                )
            if last.entity_type == EntityType.GAME:
                return RecommendationRequest(
                    utterance=utterance,
                    strategy=RecommendationStrategy.SIMILAR_GENRE,
                    seed_entity=last,
                    search_query=f"games like {last.name} similar titles recommendations",
                    provider_hint=MediaProvider.UNKNOWN,
                )
            if last.entity_type in (EntityType.SPORTS_PLAYER, EntityType.SPORTS_TEAM):
                return RecommendationRequest(
                    utterance=utterance,
                    strategy=RecommendationStrategy.SIMILAR_GENRE,
                    seed_entity=last,
                    search_query=f"sports {last.name} similar teams recommendations",
                    provider_hint=MediaProvider.UNKNOWN,
                )
        return RecommendationRequest(
            utterance=utterance,
            strategy=RecommendationStrategy.TRENDING,
            search_query="trending movies 2026",
        )

    def _similar_request(self, utterance: str) -> RecommendationRequest:
        last = self._mem.get_last_track() or self._mem.get_last_entity()
        artist = None
        query  = "trending popular music 2026"

        if last:
            if last.entity_type in (EntityType.MOVIE, EntityType.TV_SHOW):
                return RecommendationRequest(
                    utterance=utterance,
                    strategy=RecommendationStrategy.SIMILAR_GENRE,
                    seed_entity=last,
                    search_query=f"movies like {last.name} similar films recommendations",
                    provider_hint=MediaProvider.UNKNOWN,
                )
            if last.entity_type in (EntityType.BOOK, EntityType.AUTHOR):
                return RecommendationRequest(
                    utterance=utterance,
                    strategy=RecommendationStrategy.SIMILAR_GENRE,
                    seed_entity=last,
                    search_query=f"books like {last.name} similar reads recommendations",
                    provider_hint=MediaProvider.UNKNOWN,
                )
            if last.entity_type == EntityType.GAME:
                return RecommendationRequest(
                    utterance=utterance,
                    strategy=RecommendationStrategy.SIMILAR_GENRE,
                    seed_entity=last,
                    search_query=f"games like {last.name} similar titles recommendations",
                    provider_hint=MediaProvider.UNKNOWN,
                )
            if last.entity_type in (EntityType.SPORTS_PLAYER, EntityType.SPORTS_TEAM):
                return RecommendationRequest(
                    utterance=utterance,
                    strategy=RecommendationStrategy.SIMILAR_GENRE,
                    seed_entity=last,
                    search_query=f"sports {last.name} similar teams recommendations",
                    provider_hint=MediaProvider.UNKNOWN,
                )
            artist = last.metadata.get("artist", "")
            if artist:
                similar_list = _SIMILAR_ARTISTS.get(artist.lower(), [])
                if similar_list:
                    query = f"{similar_list[0]} top songs"
                else:
                    query = f"{artist} related artists music"
            else:
                # Use entity name as seed
                name = last.name if last else ""
                query = f"music similar to {name} songs" if name else "trending popular music 2026"

        return RecommendationRequest(
            utterance=utterance,
            strategy=RecommendationStrategy.SIMILAR_ARTIST,
            seed_entity=last,
            seed_artist=artist,
            search_query=query,
            provider_hint=self._prefs.get_preferred_provider(),
        )

    # ── candidate building from history ──────────────────────

    def _build_candidates_from_history(
        self, request: RecommendationRequest
    ) -> List[ScoredCandidate]:
        if request.strategy == RecommendationStrategy.HISTORY_BASED:
            sessions = self._mem.get_recent_sessions(20)
            entities = [s.entity for s in sessions if s.entity]
            # dedupe by name
            seen: set = set()
            unique: List[ResolvedEntity] = []
            for e in entities:
                if e.name not in seen:
                    seen.add(e.name)
                    unique.append(e)
            return self._prefs.score_candidates(unique[:request.max_results])

        return []   # provider search needed — MediaManager handles this

    # ── query helpers ─────────────────────────────────────────

    @staticmethod
    def _mood_query(mood: str) -> str:
        queries = _MOOD_QUERIES.get(mood, [f"{mood} music"])
        return queries[0]

    @staticmethod
    def _activity_query(activity: str) -> str:
        queries = _ACTIVITY_QUERIES.get(activity, [f"{activity} music"])
        return queries[0]

    @staticmethod
    def _estimate_confidence(
        request: RecommendationRequest, candidates: List[ScoredCandidate]
    ) -> float:
        if candidates:
            return min(0.95, candidates[0].final_score + 0.1)
        if request.search_query:
            return 0.75
        return 0.40

    # ── similar artists ───────────────────────────────────────

    @staticmethod
    def get_similar_artists(artist: str) -> List[str]:
        return _SIMILAR_ARTISTS.get(artist.lower(), [])


# ─────────────────────────── tests ───────────────────────────

import unittest

class TestMediaRecommendationEngine(unittest.TestCase):

    def setUp(self):
        self.mem   = MediaEntityMemory()
        self.res   = MediaReferenceResolver(self.mem)
        self.prefs = MediaPreferenceModel(self.mem)
        self.eng   = MediaRecommendationEngine(self.mem, self.res, self.prefs)

    def _push_track(self, name="Believer", artist="Imagine Dragons"):
        from mini_kio.media.media_intelligence_models import HistoricalMediaSession
        e = ResolvedEntity(name=name, entity_type=EntityType.SONG,
                           provider=MediaProvider.SPOTIFY,
                           metadata={"artist": artist})
        s = HistoricalMediaSession(session_id=f"s_{name}", entity=e)
        self.mem.push_session(s)
        self.prefs.ingest_session(s)

    def test_similar_with_known_artist(self):
        self._push_track()
        r = self.eng.recommend("play something similar")
        self.assertEqual(r.strategy_used, RecommendationStrategy.SIMILAR_ARTIST)
        self.assertIn("OneRepublic", r.request.search_query)   # similar to Imagine Dragons

    def test_similar_no_history(self):
        r = self.eng.recommend("play something similar")
        self.assertIsNotNone(r.request.effective_query())

    def test_mood_chill(self):
        r = self.eng.recommend("play chill music")
        self.assertEqual(r.strategy_used, RecommendationStrategy.MOOD_MATCH)
        self.assertIn("chill", r.request.search_query)

    def test_mood_hype(self):
        r = self.eng.recommend("play hype songs")
        self.assertEqual(r.strategy_used, RecommendationStrategy.MOOD_MATCH)

    def test_activity_gym(self):
        r = self.eng.recommend("play gym music")
        self.assertEqual(r.strategy_used, RecommendationStrategy.ACTIVITY_MATCH)
        self.assertIn("gym", r.request.search_query)

    def test_activity_study(self):
        r = self.eng.recommend("play study music")
        self.assertEqual(r.strategy_used, RecommendationStrategy.ACTIVITY_MATCH)

    def test_activity_coding(self):
        r = self.eng.recommend("play coding music")
        self.assertEqual(r.strategy_used, RecommendationStrategy.ACTIVITY_MATCH)

    def test_continuation_by_him(self):
        self._push_track()
        r = self.eng.recommend("play another song by him")
        self.assertEqual(r.strategy_used, RecommendationStrategy.CONTINUATION)
        self.assertIn("Imagine Dragons", r.request.search_query)

    def test_continuation_another_one(self):
        self._push_track()
        r = self.eng.recommend("play another one")
        self.assertEqual(r.strategy_used, RecommendationStrategy.CONTINUATION)

    def test_history_yesterday(self):
        import time
        from mini_kio.media.media_intelligence_models import HistoricalMediaSession
        e = ResolvedEntity("Thunder", EntityType.SONG, MediaProvider.SPOTIFY,
                           metadata={"artist": "Imagine Dragons"})
        yesterday = time.time() - 86400 - 1800
        self.mem._history.append(HistoricalMediaSession(session_id="yy", entity=e, started_at=yesterday))
        r = self.eng.recommend("play what I listened to yesterday")
        self.assertEqual(r.strategy_used, RecommendationStrategy.HISTORY_BASED)
        self.assertEqual(r.request.seed_entity.name, "Thunder")

    def test_similar_artists_known(self):
        similar = MediaRecommendationEngine.get_similar_artists("Imagine Dragons")
        self.assertIn("Coldplay", similar)

    def test_similar_artists_unknown(self):
        similar = MediaRecommendationEngine.get_similar_artists("NonExistentArtist")
        self.assertEqual(similar, [])

    def test_effective_query_from_mood(self):
        r = self.eng.recommend("play relaxing music")
        q = r.request.effective_query()
        self.assertTrue(len(q) > 0)

    def test_confidence_with_candidates(self):
        self._push_track("Believer", "Imagine Dragons")
        self._push_track("Thunder",  "Imagine Dragons")
        r = self.eng.recommend("play what I listened to yesterday")
        # confidence > 0 even with no yesterday sessions
        self.assertGreaterEqual(r.confidence, 0.0)

    def test_fallback_trending(self):
        # No history, no context → trending
        r = self.eng.recommend("play some music")
        self.assertIsNotNone(r.request.effective_query())


if __name__ == "__main__":
    unittest.main()
