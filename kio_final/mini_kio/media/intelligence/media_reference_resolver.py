"""
media_reference_resolver.py
KIO Media Intelligence Layer — Reference Resolver
Resolves pronouns, variants, continuations into concrete ResolvedEntity.
Requires MediaEntityMemory. Produces ResolvedEntity ready for MediaManager.
"""

from __future__ import annotations

import re
from dataclasses import dataclass, field
from enum import Enum
from typing import Any, Dict, List, Optional, Tuple

from mini_kio.media.media_context import MediaContext
from mini_kio.media.media_intelligence_models import (
    EntityType, MediaProvider, ResolvedEntity
)


# ─────────────────────────── enums ───────────────────────────

class ReferenceType(str, Enum):
    PRONOUN       = "pronoun"        # him, her, them, it, this, that
    ORDINAL       = "ordinal"        # first one, second one
    CONTINUATION  = "continuation"   # another one, next one
    VARIANT       = "variant"        # remix, live, original, acoustic
    REPLAY        = "replay"         # play that again, replay
    TEMPORAL      = "temporal"       # yesterday, last week
    MOOD          = "mood"           # chill, hype, sad
    ACTIVITY      = "activity"       # gym, study, coding
    SIMILAR       = "similar"        # something similar, like this
    EXPLICIT      = "explicit"       # no reference needed — direct name
    UNKNOWN       = "unknown"


class VariantType(str, Enum):
    REMIX    = "remix"
    LIVE     = "live"
    ACOUSTIC = "acoustic"
    ORIGINAL = "original"
    CLEAN    = "clean"
    EXPLICIT = "explicit"
    EXTENDED = "extended"
    RADIO    = "radio edit"
    COVER    = "cover"
    UNKNOWN  = "unknown"


# ─────────────────────────── dataclasses ───────────────────────────

@dataclass
class ReferenceResolution:
    reference_type: ReferenceType
    resolved_entity: Optional[ResolvedEntity]
    confidence: float                          # 0.0 – 1.0
    query_override: Optional[str] = None       # search query to pass to provider
    variant: Optional[VariantType] = None
    mood: Optional[str] = None
    activity: Optional[str] = None
    temporal_hint: Optional[str] = None
    ambiguous: bool = False
    reason: str = ""

    @property
    def success(self) -> bool:
        return self.resolved_entity is not None or self.query_override is not None


# ─────────────────────────── pattern tables ───────────────────────────

# Pronoun → meaning
_PRONOUN_PATTERNS: List[Tuple[re.Pattern, str]] = [
    (re.compile(r"\b(him|his)\b",        re.I), "artist_male"),
    (re.compile(r"\b(her|she|hers)\b",   re.I), "artist_female"),
    (re.compile(r"\b(them|their|they)\b",re.I), "artist_group"),
    (re.compile(r"\b(it|that one|this one|that song|that track|that video|that trailer)\b", re.I), "last_entity"),
    (re.compile(r"\b(this|that)\b",      re.I), "last_entity"),
]

# Variant keywords
_VARIANT_MAP: Dict[str, VariantType] = {
    "remix":        VariantType.REMIX,
    "remixed":      VariantType.REMIX,
    "live":         VariantType.LIVE,
    "live version": VariantType.LIVE,
    "acoustic":     VariantType.ACOUSTIC,
    "acoustic version": VariantType.ACOUSTIC,
    "original":     VariantType.ORIGINAL,
    "original version": VariantType.ORIGINAL,
    "clean":        VariantType.CLEAN,
    "clean version": VariantType.CLEAN,
    "explicit":     VariantType.EXPLICIT,
    "extended":     VariantType.EXTENDED,
    "extended mix": VariantType.EXTENDED,
    "radio edit":   VariantType.RADIO,
    "cover":        VariantType.COVER,
}

# Mood keywords
_MOOD_MAP: Dict[str, str] = {
    "chill": "chill", "chilling": "chill", "relaxing": "chill", "relaxed": "chill",
    "calm": "calm", "peaceful": "calm",
    "sad": "sad", "melancholy": "sad", "emotional": "sad",
    "happy": "happy", "upbeat": "happy", "energetic": "energetic",
    "hype": "hype", "hyped": "hype", "pump up": "hype",
    "focus": "focus", "focused": "focus",
    "romantic": "romantic", "love": "romantic",
    "angry": "angry", "aggressive": "angry",
    "party": "party",
}

# Activity keywords
_ACTIVITY_MAP: Dict[str, str] = {
    "gym": "gym", "workout": "gym", "exercise": "gym", "training": "gym",
    "study": "study", "studying": "study", "coding": "study", "work": "study",
    "sleep": "sleep", "sleeping": "sleep", "night": "sleep",
    "running": "running", "run": "running", "jogging": "running",
    "driving": "driving", "drive": "driving", "road trip": "driving",
    "meditation": "meditation", "meditate": "meditation", "yoga": "meditation",
    "gaming": "gaming", "game": "gaming",
    "party": "party", "dancing": "party", "dance": "party",
}

# Temporal keywords
_TEMPORAL_MAP: Dict[re.Pattern, str] = {
    re.compile(r"\byesterday\b",            re.I): "yesterday",
    re.compile(r"\blast night\b",           re.I): "last_night",
    re.compile(r"\blast week\b",            re.I): "last_week",
    re.compile(r"\bearlier\b",              re.I): "earlier_today",
    re.compile(r"\bthis morning\b",         re.I): "this_morning",
    re.compile(r"\ba (while|bit) ago\b",    re.I): "earlier_today",
}

# Continuation patterns
_CONTINUATION_PATTERNS = [
    re.compile(r"\b(another one|another song|next one|one more|more like (this|that))\b", re.I),
    re.compile(r"\b(play more|more by (him|her|them))\b", re.I),
    re.compile(r"\b(continue|resume|keep going)\b", re.I),
    re.compile(r"\b(play (again|that again|it again|same (song|track)))\b", re.I),
]

# Ordinal patterns
_ORDINAL_MAP: Dict[re.Pattern, int] = {
    re.compile(r"\b(first one|#?1|number one|the first)\b",  re.I): 0,
    re.compile(r"\b(second one|#?2|number two|the second)\b",re.I): 1,
    re.compile(r"\b(third one|#?3|number three|the third)\b",re.I): 2,
    re.compile(r"\b(fourth one|#?4|number four|the fourth)\b",re.I): 3,
    re.compile(r"\b(fifth one|#?5|number five|the fifth)\b", re.I): 4,
}

# Most popular / top track patterns
_POPULAR_PATTERNS = re.compile(
    r"\b(most popular|most famous|biggest hit|top (song|track|hit)|best song)\b", re.I
)

# "by him/her/them" pattern  →  artist reference
_BY_PRONOUN = re.compile(r"\bby (him|her|them|the (band|group|artist))\b", re.I)


# ─────────────────────────── resolver ───────────────────────────

class MediaReferenceResolver:
    """
    Resolves reference-laden user utterances into concrete entities.

    Usage:
        resolver = MediaReferenceResolver(memory)
        result   = resolver.resolve("play the live version")
        if result.success:
            entity = result.resolved_entity   # pass to MediaManager
    """

    def __init__(self, media_context: MediaContext):
        self._media_context = media_context
        self._candidate_pool: List[ResolvedEntity] = []   # set by intelligence layer

    def set_candidate_pool(self, candidates: List[ResolvedEntity]) -> None:
        """Intelligence layer feeds recent search results for ordinal resolution."""
        self._candidate_pool = candidates

    # ── public entry point ────────────────────────────────────

    def resolve(self, utterance: str) -> ReferenceResolution:
        """
        Main resolution pipeline.
        Returns ReferenceResolution. Caller checks .success before acting.
        """
        text = utterance.strip()

        # Priority order matters — most specific first
        result = (
            self._try_replay(text)
            or self._try_variant(text)
            or self._try_temporal(text)
            or self._try_ordinal(text)
            or self._try_continuation(text)
            or self._try_popular(text)
            or self._try_pronoun(text)
            or self._try_mood(text)
            or self._try_activity(text)
        )

        if result:
            return result

        return ReferenceResolution(
            reference_type=ReferenceType.UNKNOWN,
            resolved_entity=None,
            confidence=0.0,
            reason="no reference pattern matched",
        )

    # ── resolution steps ──────────────────────────────────────

    def _try_replay(self, text: str) -> Optional[ReferenceResolution]:
        patterns = [
            re.compile(r"\bplay (that |it |the same )?(again|once more)\b", re.I),
            re.compile(r"\breplay\b", re.I),
            re.compile(r"\bplay (that (song|track|video|one))\b", re.I),
        ]
        if not any(p.search(text) for p in patterns):
            return None
        entity = self._media_context.get_last_entity()
        if not entity:
            return ReferenceResolution(
                reference_type=ReferenceType.REPLAY,
                resolved_entity=None,
                confidence=0.3,
                reason="replay requested but no last entity in memory",
            )
        return ReferenceResolution(
            reference_type=ReferenceType.REPLAY,
            resolved_entity=entity,
            confidence=0.97,
            reason=f"replay last entity: {entity.name}",
        )

    def _try_variant(self, text: str) -> Optional[ReferenceResolution]:
        text_lower = text.lower()
        matched_variant: Optional[VariantType] = None
        for phrase, vtype in sorted(_VARIANT_MAP.items(), key=lambda x: -len(x[0])):
            if phrase in text_lower:
                matched_variant = vtype
                break
        if not matched_variant:
            return None

        base_entity = self._media_context.get_last_entity() or self._media_context.get_last_entity()
        if not base_entity:
            return ReferenceResolution(
                reference_type=ReferenceType.VARIANT,
                resolved_entity=None,
                confidence=0.4,
                variant=matched_variant,
                query_override=None,
                reason=f"variant '{matched_variant}' requested but no base track in memory",
            )

        query = f"{base_entity.name} {matched_variant.value}"
        if artist := base_entity.metadata.get("artist"):
            query = f"{artist} {base_entity.name} {matched_variant.value}"

        return ReferenceResolution(
            reference_type=ReferenceType.VARIANT,
            resolved_entity=None,   # needs provider search with query_override
            confidence=0.9,
            variant=matched_variant,
            query_override=query,
            reason=f"variant of '{base_entity.name}': {matched_variant.value}",
        )

    def _try_temporal(self, text: str) -> Optional[ReferenceResolution]:
        for pattern, hint in _TEMPORAL_MAP.items():
            if pattern.search(text):
                sessions = []
                sessions = [] # Stubbed for Wave 1: No direct access to historical sessions from MediaContext/MemoryStore
                # if hint == "yesterday":
                #     sessions = self._media_context.get_sessions_from_yesterday() # Not yet implemented in MediaContext
                # elif hint == "last_night":
                #     sessions = self._media_context.get_sessions_from_yesterday() # Not yet implemented in MediaContext
                # elif hint in ("earlier_today", "this_morning"):
                #     import time
                #     cutoff = time.time() - 3600 * 12
                #     sessions = [ # Not yet implemented in MediaContext
                #         s for s in self._media_context.get_recent_sessions(50)
                #         if s.started_at >= cutoff
                #     ]
                entity = sessions[0].entity if sessions else None
                return ReferenceResolution(
                    reference_type=ReferenceType.TEMPORAL,
                    resolved_entity=entity,
                    confidence=0.85 if entity else 0.4,
                    temporal_hint=hint,
                    reason=f"temporal reference '{hint}', found {len(sessions)} sessions",
                )
        return None

    def _try_ordinal(self, text: str) -> Optional[ReferenceResolution]:
        for pattern, idx in _ORDINAL_MAP.items():
            if pattern.search(text):
                if idx < len(self._candidate_pool):
                    entity = self._candidate_pool[idx]
                    return ReferenceResolution(
                        reference_type=ReferenceType.ORDINAL,
                        resolved_entity=entity,
                        confidence=0.95,
                        reason=f"ordinal[{idx}] from candidate pool",
                    )
                return ReferenceResolution(
                    reference_type=ReferenceType.ORDINAL,
                    resolved_entity=None,
                    confidence=0.3,
                    reason=f"ordinal[{idx}] requested but pool has {len(self._candidate_pool)} candidates",
                )
        return None

    def _try_continuation(self, text: str) -> Optional[ReferenceResolution]:
        is_continuation = any(p.search(text) for p in _CONTINUATION_PATTERNS)
        if not is_continuation:
            return None

        # Check "by him/her/them" pronoun
        by_match = _BY_PRONOUN.search(text)
        artist = None
        if by_match:
            artist = self._media_context.get_last_artist()

        if not artist:
            artist = self._media_context.get_last_artist()

        if not artist:
            return ReferenceResolution(
                reference_type=ReferenceType.CONTINUATION,
                resolved_entity=None,
                confidence=0.3,
                reason="continuation but no last artist in memory",
            )

        query = f"{artist}"
        # Prefer "another song by" phrasing for provider search
        return ReferenceResolution(
            reference_type=ReferenceType.CONTINUATION,
            resolved_entity=None,
            confidence=0.88,
            query_override=query,
            reason=f"continuation: another track by {artist}",
        )

    def _try_popular(self, text: str) -> Optional[ReferenceResolution]:
        if not _POPULAR_PATTERNS.search(text):
            return None
        artist = self._media_context.get_last_artist()
        if not artist:
            return ReferenceResolution(
                reference_type=ReferenceType.CONTINUATION,
                resolved_entity=None,
                confidence=0.3,
                reason="popular song requested but no artist context",
            )
        query = f"{artist} most popular song"
        return ReferenceResolution(
            reference_type=ReferenceType.CONTINUATION,
            resolved_entity=None,
            confidence=0.85,
            query_override=query,
            reason=f"most popular by {artist}",
        )

    def _try_pronoun(self, text: str) -> Optional[ReferenceResolution]:
        for pattern, meaning in _PRONOUN_PATTERNS:
            if pattern.search(text):
                if meaning == "last_entity":
                    entity = self._media_context.get_last_entity()
                    return ReferenceResolution(
                        reference_type=ReferenceType.PRONOUN,
                        resolved_entity=entity,
                        confidence=0.85 if entity else 0.2,
                        reason=f"pronoun '{meaning}' → last entity",
                    )
                # artist pronoun — "play more by him"
                artist = self._media_context.get_last_artist()
                if artist:
                    return ReferenceResolution(
                        reference_type=ReferenceType.PRONOUN,
                        resolved_entity=None,
                        confidence=0.82,
                        query_override=artist,
                        reason=f"pronoun → artist: {artist}",
                    )
        return None

    def _try_mood(self, text: str) -> Optional[ReferenceResolution]:
        text_lower = text.lower()
        for kw, mood in _MOOD_MAP.items():
            if kw in text_lower:
                self._media_context.set_mood(mood)
                return ReferenceResolution(
                    reference_type=ReferenceType.MOOD,
                    resolved_entity=None,
                    confidence=0.8,
                    mood=mood,
                    query_override=f"{mood} music playlist",
                    reason=f"mood detected: {mood}",
                )
        return None

    def _try_activity(self, text: str) -> Optional[ReferenceResolution]:
        text_lower = text.lower()
        for kw, activity in _ACTIVITY_MAP.items():
            if kw in text_lower:
                self._media_context.set_activity(activity)
                return ReferenceResolution(
                    reference_type=ReferenceType.ACTIVITY,
                    resolved_entity=None,
                    confidence=0.8,
                    activity=activity,
                    query_override=f"{activity} music playlist",
                    reason=f"activity detected: {activity}",
                )
        return None


# ─────────────────────────── tests ───────────────────────────

import unittest, time

class TestMediaReferenceResolver(unittest.TestCase):

    def setUp(self):
        # Create a mock MediaContext for testing
        class MockMediaContext:
            def __init__(self):
                self._last_resolved_entity = None
                self._current_mood = None
                self._current_activity = None
                # Mimic existing MediaContext properties for fallback in get_last_artist
                self.current_artist = ""

            def get_last_entity(self):
                return self._last_resolved_entity
            def set_last_entity(self, entity):
                self._last_resolved_entity = entity
            def get_last_artist(self):
                if self._last_resolved_entity and self._last_resolved_entity.entity_type == EntityType.MUSIC_ARTIST:
                    return self._last_resolved_entity.name
                if self._last_resolved_entity and self._last_resolved_entity.metadata.get("artist"):
                    return self._last_resolved_entity.metadata.get("artist")
                return self.current_artist

            def set_mood(self, mood):
                self._current_mood = mood
            def get_mood(self):
                return self._current_mood
            def set_activity(self, activity):
                self._current_activity = activity
            def get_activity(self):
                return self._current_activity
            def get_sessions_from_yesterday(self): # Stubbed for Wave 1
                return []
            def get_recent_sessions(self, n): # Stubbed for Wave 1
                return []

        self.mock_media_context = MockMediaContext()
        self.resolver = MediaReferenceResolver(self.mock_media_context)

    def _push_track(self, name="Believer", artist="Imagine Dragons"):
        # This helper now directly sets the last entity in the mock MediaContext.
        e = ResolvedEntity(name=name, entity_type=EntityType.SONG,
                           provider=MediaProvider.SPOTIFY,
                           metadata={"artist": artist})
        self.mock_media_context.set_last_entity(e)
        # Manually update current_artist in mock for fallback testing if needed
        self.mock_media_context.current_artist = artist
        return e

    # replay
    def test_replay_with_memory(self):
        self._push_track()
        r = self.resolver.resolve("play that again")
        self.assertTrue(r.success)
        self.assertEqual(r.reference_type, ReferenceType.REPLAY)
        self.assertEqual(r.resolved_entity.name, "Believer")

    def test_replay_no_memory(self):
        r = self.resolver.resolve("play it again")
        self.assertFalse(r.success)
        self.assertEqual(r.reference_type, ReferenceType.REPLAY)

    # variant
    def test_live_version(self):
        self._push_track()
        r = self.resolver.resolve("play the live version")
        self.assertEqual(r.reference_type, ReferenceType.VARIANT)
        self.assertEqual(r.variant, VariantType.LIVE)
        self.assertIn("live", r.query_override)

    def test_remix(self):
        self._push_track()
        r = self.resolver.resolve("play the remix")
        self.assertEqual(r.variant, VariantType.REMIX)

    def test_acoustic(self):
        self._push_track()
        r = self.resolver.resolve("play acoustic version")
        self.assertEqual(r.variant, VariantType.ACOUSTIC)

    def test_original(self):
        self._push_track()
        r = self.resolver.resolve("play the original version")
        self.assertEqual(r.variant, VariantType.ORIGINAL)

    def test_variant_no_memory(self):
        r = self.resolver.resolve("play the live version")
        self.assertEqual(r.reference_type, ReferenceType.VARIANT)
        self.assertFalse(r.success)   # no query_override without base

    # continuation
    def test_another_song_by_him(self):
        self._push_track()
        r = self.resolver.resolve("play another song by him")
        self.assertEqual(r.reference_type, ReferenceType.CONTINUATION)
        self.assertIn("Imagine Dragons", r.query_override)

    def test_another_one(self):
        self._push_track()
        r = self.resolver.resolve("play another one")
        self.assertTrue(r.success)

    def test_continuation_no_artist(self):
        r = self.resolver.resolve("play another one")
        self.assertFalse(r.success)

    # most popular
    def test_most_popular(self):
        self._push_track()
        r = self.resolver.resolve("play his most popular song")
        self.assertIsNotNone(r.query_override)
        self.assertIn("most popular", r.query_override)

    # pronoun → last entity
    def test_pronoun_it(self):
        self._push_track()
        r = self.resolver.resolve("play it")
        self.assertEqual(r.reference_type, ReferenceType.PRONOUN)

    def test_pronoun_that_song(self):
        self._push_track()
        r = self.resolver.resolve("play that song")
        self.assertTrue(r.success)

    # temporal
    # def test_yesterday(self):
    #     from media_entity_memory import MediaSession
    #     e = ResolvedEntity(name="Thunder", entity_type=EntityType.SONG,
    #                        provider=MediaProvider.SPOTIFY,
    #                        metadata={"artist": "Imagine Dragons"})
    #     yesterday = time.time() - 86400 - 3600
    #     self.mem._history.append(MediaSession(session_id="yy", entity=e, started_at=yesterday))
    #     r = self.resolver.resolve("play what I listened to yesterday")
    #     self.assertEqual(r.reference_type, ReferenceType.TEMPORAL)
    #     self.assertEqual(r.temporal_hint, "yesterday")

    # mood
    def test_mood_chill(self):
        r = self.resolver.resolve("play some chill music")
        self.assertEqual(r.reference_type, ReferenceType.MOOD)
        self.assertEqual(r.mood, "chill")

    def test_mood_gym(self):
        # gym is activity not mood
        r = self.resolver.resolve("play gym music")
        self.assertEqual(r.reference_type, ReferenceType.ACTIVITY)
        self.assertEqual(r.activity, "gym")

    def test_activity_coding(self):
        r = self.resolver.resolve("play coding music")
        self.assertEqual(r.activity, "study")

    def test_activity_study(self):
        r = self.resolver.resolve("play study music")
        self.assertEqual(r.activity, "study")

    # ordinal
    def test_ordinal_first(self):
        candidates = [
            ResolvedEntity("A", EntityType.SONG, MediaProvider.SPOTIFY),
            ResolvedEntity("B", EntityType.SONG, MediaProvider.SPOTIFY),
        ]
        self.resolver.set_candidate_pool(candidates)
        r = self.resolver.resolve("play the first one")
        self.assertEqual(r.resolved_entity.name, "A")

    def test_ordinal_second(self):
        candidates = [
            ResolvedEntity("A", EntityType.SONG, MediaProvider.SPOTIFY),
            ResolvedEntity("B", EntityType.SONG, MediaProvider.SPOTIFY),
        ]
        self.resolver.set_candidate_pool(candidates)
        r = self.resolver.resolve("play the second one")
        self.assertEqual(r.resolved_entity.name, "B")

    def test_ordinal_out_of_range(self):
        self.resolver.set_candidate_pool([])
        r = self.resolver.resolve("play the first one")
        self.assertFalse(r.success)

    # unknown
    def test_unknown_utterance(self):
        r = self.resolver.resolve("xyzzy plugh")
        self.assertEqual(r.reference_type, ReferenceType.UNKNOWN)
        self.assertFalse(r.success)


if __name__ == "__main__":
    unittest.main()
