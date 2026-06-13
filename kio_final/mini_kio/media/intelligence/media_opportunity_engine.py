"""
media_opportunity_engine.py
KIO Media Intelligence Layer — Opportunity Engine
Detects proactive media opportunities from user queries + external signals.
Produces MediaOffer via OfferManager. Does NOT call playback directly.
"""

from __future__ import annotations

import re
import time
from dataclasses import dataclass, field
from enum import Enum
from typing import Any, Callable, Dict, List, Optional, Tuple

from mini_kio.media.media_context import MediaContext
from mini_kio.media.media_intelligence_models import (
    EntityType, MediaProvider, ResolvedEntity
)
from mini_kio.media.intelligence.media_offer_manager import (
    MediaOffer, MediaOfferManager, OfferStatus, OfferTrigger
)


# ─────────────────────────── enums ───────────────────────────

class OpportunityType(str, Enum):
    TRAILER     = "trailer"
    HIGHLIGHTS  = "highlights"
    INTERVIEW   = "interview"
    LIVESTREAM  = "livestream"
    NEW_SONG    = "new_song"
    NEW_ALBUM   = "new_album"
    SCORE_NEWS  = "score_news"
    ARTIST_NEWS = "artist_news"
    TRENDING    = "trending"


# ─────────────────────────── detection patterns ───────────────────────────

# Maps (regex, OpportunityType, entity_type)
_OPPORTUNITY_PATTERNS: List[Tuple[re.Pattern, OpportunityType, EntityType]] = [
    # Trailer / movie queries
    (re.compile(r"\b(trailer|teaser|official video|sneak peek)\b", re.I),
     OpportunityType.TRAILER, EntityType.MOVIE),

    # Sports highlights
    (re.compile(r"\b(score[sd]?|goal|goals|highlights?|match recap|game recap)\b", re.I),
     OpportunityType.HIGHLIGHTS, EntityType.SPORTS_PLAYER),

    # Interview
    (re.compile(r"\b(interview|press conference|talk show|behind the scenes|bts)\b", re.I),
     OpportunityType.INTERVIEW, EntityType.ACTOR),

    # Livestream
    (re.compile(r"\b(livestream|live stream|streaming live|going live|live now|watching live)\b", re.I),
     OpportunityType.LIVESTREAM, EntityType.STREAMER),

    # New music
    (re.compile(r"\b(new song|new track|new single|new album|new release|just dropped|released today)\b", re.I),
     OpportunityType.NEW_SONG, EntityType.MUSIC_ARTIST),

    # Score / sports news
    (re.compile(r"\b(did .+ (score|win|lose|play)|match result|final score|who won)\b", re.I),
     OpportunityType.SCORE_NEWS, EntityType.SPORTS_PLAYER),
]

# Entity name extraction — looks for named entities in query
# (Production: replace with NER. This is deterministic fallback.)
_ENTITY_EXTRACTION_PATTERNS: List[Tuple[re.Pattern, EntityType]] = [
    # Movies
    (re.compile(r"\b(spider.?man|marvel|dc|avengers|batman|superman|deadpool|venom)\b", re.I),
     EntityType.MOVIE),
    # Music artists
    (re.compile(r"\b(imagine dragons|ed sheeran|taylor swift|drake|the weeknd|arijit singh|ap dhillon)\b", re.I),
     EntityType.MUSIC_ARTIST),
    # Sports players
    (re.compile(r"\b(messi|ronaldo|mbappé|mbappe|neymar|haaland|de bruyne|kohli|dhoni|lebron|curry)\b", re.I),
     EntityType.SPORTS_PLAYER),
    # Sports teams
    (re.compile(r"\b(barcelona|real madrid|manchester (united|city)|liverpool|chelsea|arsenal|psg|juventus)\b", re.I),
     EntityType.SPORTS_TEAM),
    # YouTubers / streamers
    (re.compile(r"\b(pewdiepie|mr beast|mrbeast|t-series|tseries|carryminati|techno gamerz)\b", re.I),
     EntityType.YOUTUBER),
    # Games
    (re.compile(r"\b(gta|gta vi|gta 6|minecraft|fortnite|valorant|call of duty|cod|elden ring)\b", re.I),
     EntityType.GAME),
]

# Availability question patterns
_AVAILABILITY_PATTERNS = re.compile(
    r"\b(has .+ (released?|dropped?|out|available)|"
    r"is .+ (out|available|live|released?|streaming)|"
    r"did .+ release|"
    r"anything new from|"
    r"what('?s| is) new (from|with|by)|"
    r"latest .+ (video|trailer|song|album|interview)|"
    r"new .+ (video|trailer|song|album|interview))\b",
    re.I,
)


# ─────────────────────────── dataclasses ───────────────────────────

@dataclass
class DetectedOpportunity:
    opportunity_type: OpportunityType
    entity_name: str
    entity_type: EntityType
    confidence: float
    search_query: str
    provider_hint: MediaProvider = MediaProvider.YOUTUBE
    source_utterance: str = ""

    def to_display_question(self) -> str:
        """Before we know if content exists — check phrasing."""
        verb = {
            OpportunityType.TRAILER:    "the trailer released",
            OpportunityType.HIGHLIGHTS: "highlights available",
            OpportunityType.INTERVIEW:  "an interview available",
            OpportunityType.NEW_SONG:   "a new song out",
            OpportunityType.NEW_ALBUM:  "a new album out",
            OpportunityType.SCORE_NEWS: "match highlights available",
        }.get(self.opportunity_type, "content available")
        return f"Let me check if {self.entity_name} has {verb}."


@dataclass
class OpportunityCheckResult:
    opportunity: DetectedOpportunity
    found: bool
    entity: Optional[ResolvedEntity] = None
    candidates: List[ResolvedEntity] = field(default_factory=list)
    answer_text: str = ""    # e.g. "Yes. Official trailer released today."
    checked_at: float = field(default_factory=time.time)


# ─────────────────────────── engine ───────────────────────────

class MediaOpportunityEngine:
    """
    Detects proactive media opportunities from user utterances.
    Does NOT search providers — returns structured OpportunityCheckResult
    with search_query for MediaManager to execute.

    Integration flow:
        1. engine.detect(utterance)  → DetectedOpportunity or None
        2. Caller uses opportunity.search_query to hit provider
        3. If found: engine.build_result(opportunity, found_entities)
        4. engine.create_offer(result, offer_manager) → MediaOffer
        5. Present offer.to_display() to user
        6. On acceptance: MediaManager.play(offer_manager.get_accepted_entity(offer))
    """

    def __init__(self, media_context: MediaContext):
        self._media_context = media_context

    # ── detection ────────────────────────────────────────────

    def detect(self, utterance: str) -> Optional[DetectedOpportunity]:
        """
        Detect if utterance implies a proactive opportunity.
        Returns None if utterance is a direct playback command (not a query).
        """
        text = utterance.strip()

        # Must contain either an availability pattern OR an opportunity keyword
        has_availability = bool(_AVAILABILITY_PATTERNS.search(text))
        opportunity_type, opp_entity_type = self._detect_opportunity_type(text)

        if not (has_availability or opportunity_type):
            return None

        entity_name, entity_type = self._extract_entity(text)
        if not entity_name:
            return None

        # If no direct opportunity type matched, infer from entity type
        if not opportunity_type:
            opportunity_type = self._infer_opportunity_type(entity_type, text)
            opp_entity_type  = entity_type

        search_query    = self._build_search_query(entity_name, opportunity_type)
        provider_hint   = self._pick_provider(opportunity_type)

        return DetectedOpportunity(
            opportunity_type=opportunity_type,
            entity_name=entity_name,
            entity_type=entity_type,
            confidence=self._score_confidence(has_availability, entity_name),
            search_query=search_query,
            provider_hint=provider_hint,
            source_utterance=utterance,
        )

    def detect_score_query(self, utterance: str) -> Optional[DetectedOpportunity]:
        """
        Specifically detect "Did X score?" / "Did X win?" queries.
        Returns opportunity with search_query for highlights.
        """
        text = utterance.strip()
        pattern = re.compile(
            r"\b(did|has)\s+(\w[\w\s]{1,30})\s+(score[sd]?|win|lose|play (yesterday|today)?|"
            r"scored|won)\b",
            re.I
        )
        m = pattern.search(text)
        if not m:
            return None
        entity_name = m.group(2).strip()
        return DetectedOpportunity(
            opportunity_type=OpportunityType.HIGHLIGHTS,
            entity_name=entity_name,
            entity_type=EntityType.SPORTS_PLAYER,
            confidence=0.85,
            search_query=f"{entity_name} highlights today",
            provider_hint=MediaProvider.YOUTUBE,
            source_utterance=utterance,
        )

    def detect_new_content_query(self, utterance: str) -> Optional[DetectedOpportunity]:
        """
        Detect "Anything new from X?" queries.
        Returns multi-result opportunity.
        """
        pattern = re.compile(
            r"\banything new from\b|\bwhat'?s? new (from|with|by)\b|\blatest (from|by)\b",
            re.I
        )
        if not pattern.search(utterance):
            return None
        entity_name, entity_type = self._extract_entity(utterance)
        if not entity_name:
            return None
        return DetectedOpportunity(
            opportunity_type=OpportunityType.ARTIST_NEWS,
            entity_name=entity_name,
            entity_type=entity_type,
            confidence=0.80,
            search_query=f"{entity_name} latest news 2024",
            provider_hint=MediaProvider.YOUTUBE,
            source_utterance=utterance,
        )

    # ── result building ───────────────────────────────────────

    def build_result(
        self,
        opportunity: DetectedOpportunity,
        found_entities: List[ResolvedEntity],
    ) -> OpportunityCheckResult:
        """
        Build check result after provider search returns.
        found_entities: what the provider returned (may be empty).
        """
        found = len(found_entities) > 0
        answer = self._build_answer_text(opportunity, found, found_entities)
        return OpportunityCheckResult(
            opportunity=opportunity,
            found=found,
            entity=found_entities[0] if found_entities else None,
            candidates=found_entities,
            answer_text=answer,
        )

    def create_offer(
        self,
        result: OpportunityCheckResult,
        offer_manager: MediaOfferManager,
    ) -> Optional[MediaOffer]:
        """
        Create offer from a positive check result.
        Returns None if result.found is False.
        """
        if not result.found:
            return None

        trigger = self._opportunity_to_trigger(result.opportunity.opportunity_type)

        if len(result.candidates) > 1:
            return offer_manager.create_multi_offer(
                candidates=result.candidates[:5],
                trigger=trigger,
                description=result.answer_text,
            )
        return offer_manager.create_single_offer(
            entity=result.entity,
            trigger=trigger,
            description=result.answer_text,
        )

    # ── helpers ───────────────────────────────────────────────

    def _detect_opportunity_type(
        self, text: str
    ) -> Tuple[Optional[OpportunityType], Optional[EntityType]]:
        for pattern, otype, etype in _OPPORTUNITY_PATTERNS:
            if pattern.search(text):
                return otype, etype
        return None, None

    def _extract_entity(self, text: str) -> Tuple[str, EntityType]:
        for pattern, etype in _ENTITY_EXTRACTION_PATTERNS:
            m = pattern.search(text)
            if m:
                return m.group(0).strip(), etype
        # Fallback: extract capitalized sequence
        cap = re.findall(r"\b([A-Z][a-z]+(?:\s+[A-Z][a-z]+)*)\b", text)
        if cap:
            return cap[0], EntityType.UNKNOWN
        return "", EntityType.UNKNOWN

    def _infer_opportunity_type(self, entity_type: EntityType, text: str) -> OpportunityType:
        mapping = {
            EntityType.MOVIE:         OpportunityType.TRAILER,
            EntityType.TV_SHOW:       OpportunityType.TRAILER,
            EntityType.MUSIC_ARTIST:  OpportunityType.NEW_SONG,
            EntityType.SPORTS_PLAYER: OpportunityType.HIGHLIGHTS,
            EntityType.SPORTS_TEAM:   OpportunityType.HIGHLIGHTS,
            EntityType.YOUTUBER:      OpportunityType.ARTIST_NEWS,
            EntityType.STREAMER:      OpportunityType.LIVESTREAM,
            EntityType.GAME:          OpportunityType.TRAILER,
        }
        return mapping.get(entity_type, OpportunityType.TRENDING)

    def _build_search_query(self, entity_name: str, opp_type: OpportunityType) -> str:
        suffix = {
            OpportunityType.TRAILER:    "official trailer",
            OpportunityType.HIGHLIGHTS: "highlights",
            OpportunityType.INTERVIEW:  "interview",
            OpportunityType.LIVESTREAM: "livestream",
            OpportunityType.NEW_SONG:   "new song 2024",
            OpportunityType.NEW_ALBUM:  "new album 2024",
            OpportunityType.SCORE_NEWS: "highlights today",
            OpportunityType.ARTIST_NEWS:"latest 2024",
            OpportunityType.TRENDING:   "trending",
        }.get(opp_type, "")
        return f"{entity_name} {suffix}".strip()

    def _pick_provider(self, opp_type: OpportunityType) -> MediaProvider:
        music_types = {OpportunityType.NEW_SONG, OpportunityType.NEW_ALBUM}
        return MediaProvider.SPOTIFY if opp_type in music_types else MediaProvider.YOUTUBE

    def _score_confidence(self, has_availability: bool, entity_name: str) -> float:
        score = 0.6
        if has_availability:
            score += 0.2
        if entity_name:
            score += 0.1
        return min(0.95, score)

    def _build_answer_text(
        self,
        opp: DetectedOpportunity,
        found: bool,
        entities: List[ResolvedEntity],
    ) -> str:
        if not found:
            return f"Nothing found for {opp.entity_name} right now."

        type_text = {
            OpportunityType.TRAILER:    "Official trailer released.",
            OpportunityType.HIGHLIGHTS: "Match highlights available.",
            OpportunityType.INTERVIEW:  "Interview available.",
            OpportunityType.LIVESTREAM: "Currently live.",
            OpportunityType.NEW_SONG:   "New song available.",
            OpportunityType.NEW_ALBUM:  "New album available.",
            OpportunityType.SCORE_NEWS: "Match highlights available.",
            OpportunityType.ARTIST_NEWS: f"Found {len(entities)} item(s).",
        }.get(opp.opportunity_type, "Content available.")

        return f"Yes.\n{type_text}"

    @staticmethod
    def _opportunity_to_trigger(opp_type: OpportunityType) -> OfferTrigger:
        mapping = {
            OpportunityType.TRAILER:     OfferTrigger.TRAILER_RELEASED,
            OpportunityType.HIGHLIGHTS:  OfferTrigger.HIGHLIGHTS_AVAILABLE,
            OpportunityType.INTERVIEW:   OfferTrigger.INTERVIEW_AVAILABLE,
            OpportunityType.LIVESTREAM:  OfferTrigger.LIVESTREAM_LIVE,
            OpportunityType.NEW_SONG:    OfferTrigger.NEW_SONG,
            OpportunityType.NEW_ALBUM:   OfferTrigger.NEW_ALBUM,
            OpportunityType.SCORE_NEWS:  OfferTrigger.HIGHLIGHTS_AVAILABLE,
            OpportunityType.ARTIST_NEWS: OfferTrigger.ARTIST_NEWS,
            OpportunityType.TRENDING:    OfferTrigger.TRENDING_NOW,
        }
        return mapping.get(opp_type, OfferTrigger.USER_QUERY)


# ─────────────────────────── tests ───────────────────────────

import unittest

class TestMediaOpportunityEngine(unittest.TestCase):

    def setUp(self):
        class MockMediaContext:
            def __init__(self):
                self.last_resolved_entity = None
            def get_last_entity(self):
                return self.last_resolved_entity
            def get_last_artist(self):
                return None

        class MockMemoryStore:
            def __init__(self):
                self._facts = {}
            def set_fact(self, key, value):
                self._facts[key] = value
            def get_fact(self, key):
                return self._facts.get(key)
            def get_all_facts(self):
                return self._facts

        self.mock_media_context = MockMediaContext()
        self.mock_memory_store = MockMemoryStore()
        self.eng = MediaOpportunityEngine(self.mock_media_context)
        self.mgr = MediaOfferManager(self.mock_memory_store)

    def _make_entity(self, name, etype=EntityType.MOVIE):
        return ResolvedEntity(name=name, entity_type=etype, provider=MediaProvider.YOUTUBE)

    # detection
    def test_detect_trailer_query(self):
        opp = self.eng.detect("Has the Spider-Man trailer released?")
        self.assertIsNotNone(opp)
        self.assertEqual(opp.opportunity_type, OpportunityType.TRAILER)

    def test_detect_messi_score(self):
        opp = self.eng.detect_score_query("Did Messi score yesterday?")
        self.assertIsNotNone(opp)
        self.assertEqual(opp.opportunity_type, OpportunityType.HIGHLIGHTS)
        self.assertIn("Messi", opp.entity_name)

    def test_detect_highlights_explicit(self):
        opp = self.eng.detect("play Messi highlights")
        # "play" prefix — still has "highlights" keyword
        self.assertIsNotNone(opp)
        self.assertEqual(opp.opportunity_type, OpportunityType.HIGHLIGHTS)

    def test_detect_new_song(self):
        opp = self.eng.detect("Did Ed Sheeran release a new song?")
        self.assertIsNotNone(opp)

    def test_detect_anything_new_marvel(self):
        opp = self.eng.detect_new_content_query("Anything new from Marvel?")
        self.assertIsNotNone(opp)

    def test_detect_returns_none_for_plain_play(self):
        opp = self.eng.detect("play Believer")
        self.assertIsNone(opp)

    def test_detect_gta_trailer(self):
        opp = self.eng.detect("Has the GTA 6 trailer dropped?")
        self.assertIsNotNone(opp)
        self.assertIn("GTA", opp.entity_name)

    def test_detect_livestream(self):
        opp = self.eng.detect("Is MrBeast live streaming right now?")
        self.assertIsNotNone(opp)

    # search query generation
    def test_search_query_trailer(self):
        opp = self.eng.detect("Has the Spider-Man trailer released?")
        self.assertIn("trailer", opp.search_query)

    def test_search_query_highlights(self):
        opp = self.eng.detect_score_query("Did Ronaldo score?")
        self.assertIn("highlights", opp.search_query)

    # provider selection
    def test_provider_trailer_is_youtube(self):
        opp = self.eng.detect("Has the Marvel trailer released?")
        self.assertEqual(opp.provider_hint, MediaProvider.YOUTUBE)

    # build result
    def test_build_result_found(self):
        opp = DetectedOpportunity(
            opportunity_type=OpportunityType.TRAILER,
            entity_name="Spider-Man",
            entity_type=EntityType.MOVIE,
            confidence=0.9,
            search_query="Spider-Man official trailer",
        )
        entities = [self._make_entity("Spider-Man: Brand New Day Trailer")]
        result = self.eng.build_result(opp, entities)
        self.assertTrue(result.found)
        self.assertIn("Yes", result.answer_text)

    def test_build_result_not_found(self):
        opp = DetectedOpportunity(
            opportunity_type=OpportunityType.TRAILER,
            entity_name="Unknown Movie",
            entity_type=EntityType.MOVIE,
            confidence=0.5,
            search_query="Unknown Movie trailer",
        )
        result = self.eng.build_result(opp, [])
        self.assertFalse(result.found)
        self.assertIn("Nothing found", result.answer_text)

    # offer creation
    def test_create_offer_single(self):
        opp = DetectedOpportunity(
            opportunity_type=OpportunityType.TRAILER,
            entity_name="Spider-Man",
            entity_type=EntityType.MOVIE,
            confidence=0.9,
            search_query="Spider-Man trailer",
        )
        entities = [self._make_entity("Spider-Man Trailer")]
        result = self.eng.build_result(opp, entities)
        offer  = self.eng.create_offer(result, self.mgr)
        self.assertIsNotNone(offer)
        self.assertTrue(self.mgr.has_pending_offer())

    def test_create_offer_multi(self):
        opp = DetectedOpportunity(
            opportunity_type=OpportunityType.ARTIST_NEWS,
            entity_name="Marvel",
            entity_type=EntityType.MOVIE,
            confidence=0.9,
            search_query="Marvel latest 2024",
        )
        entities = [
            self._make_entity("Fantastic Four Trailer"),
            self._make_entity("Ironheart Teaser"),
            self._make_entity("Thunderbolts Clip"),
        ]
        result = self.eng.build_result(opp, entities)
        offer  = self.eng.create_offer(result, self.mgr)
        self.assertEqual(len(offer.candidates), 3)

    def test_no_offer_when_not_found(self):
        opp = DetectedOpportunity(
            opportunity_type=OpportunityType.TRAILER,
            entity_name="Unknown",
            entity_type=EntityType.MOVIE,
            confidence=0.5,
            search_query="Unknown trailer",
        )
        result = self.eng.build_result(opp, [])
        offer  = self.eng.create_offer(result, self.mgr)
        self.assertIsNone(offer)

    def test_confidence_scores_reasonable(self):
        opp = self.eng.detect("Has the Spider-Man trailer released?")
        self.assertGreater(opp.confidence, 0.5)
        self.assertLessEqual(opp.confidence, 1.0)


if __name__ == "__main__":
    unittest.main()
