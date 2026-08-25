"""
media_intelligence.py
KIO Media Intelligence Layer — Main Orchestrator

Single entry point. Routes every media utterance through:
  1. Follow-up detection
  2. Opportunity detection
  3. Reference resolution
  4. Recommendation generation
  5. Offer management

Returns MediaIntelligenceResult to MediaManager.
MediaManager executes playback / transport / provider search.
"""

from __future__ import annotations

import re
import time
from dataclasses import dataclass, field
from enum import Enum
from typing import Any, Dict, List, Optional

from mini_kio.media.intelligence.media_entity_memory import MediaEntityMemory
from mini_kio.media.media_intelligence_models import (
    EntityType, MediaProvider, ResolvedEntity, HistoricalMediaSession
)
from mini_kio.memory.memory_store import MemoryStore
from mini_kio.media.intelligence.media_offer_manager import (
    MediaOffer, MediaOfferManager, OfferTrigger
)
from mini_kio.media.intelligence.media_opportunity_engine import (
    DetectedOpportunity, MediaOpportunityEngine, OpportunityCheckResult
)
from mini_kio.media.intelligence.media_recommendation_engine import (
    MediaRecommendationEngine, RecommendationResult, RecommendationStrategy
)
from mini_kio.media.intelligence.media_reference_resolver import (
    MediaReferenceResolver, ReferenceResolution, ReferenceType, VariantType
)
from mini_kio.media.intelligence.media_followup_engine import (
    FollowUpResolution, FollowUpType, MediaFollowUpEngine, TransportCommand
)
from mini_kio.media.intelligence.media_preference_model import MediaPreferenceModel


# ─────────────────────────── enums ───────────────────────────

class IntelligenceAction(str, Enum):
    PLAY_ENTITY       = "play_entity"        # play a specific resolved entity
    SEARCH_AND_PLAY   = "search_and_play"    # execute search_query → play top result
    TRANSPORT         = "transport"          # send TransportCommand to playback engine
    VOLUME            = "volume"             # adjust volume
    PRESENT_OFFER     = "present_offer"      # show offer to user, await response
    PRESENT_RESULTS   = "present_results"    # show search results, await selection
    ACCEPT_OFFER      = "accept_offer"       # user said yes → play offer entity
    REJECT_OFFER      = "reject_offer"       # user said no → do nothing
    QUEUE_ADD         = "queue_add"          # add to playback queue
    NO_ACTION         = "no_action"          # nothing to do (already handled / error)
    CLARIFY           = "clarify"            # need more info from user


# ─────────────────────────── dataclasses ───────────────────────────

@dataclass
class MediaIntelligenceResult:
    """
    Returned to MediaManager for execution.
    MediaManager checks .action and dispatches accordingly.
    """
    action: IntelligenceAction

    # PLAY_ENTITY
    entity: Optional[ResolvedEntity] = None

    # SEARCH_AND_PLAY
    search_query: str = ""
    provider_hint: Optional[MediaProvider] = None

    # TRANSPORT
    transport_command: Optional[TransportCommand] = None

    # VOLUME
    volume_delta: Optional[int] = None       # +10, -10, or absolute 0-100

    # PRESENT_OFFER
    offer: Optional[MediaOffer] = None

    # PRESENT_RESULTS
    candidates: List[ResolvedEntity] = field(default_factory=list)

    # Meta
    confidence: float = 1.0
    display_text: str = ""          # text to show user before/after action
    followup_hint: str = ""         # what we expect next (for context)
    source_utterance: str = ""
    processing_ms: float = 0.0

    def __str__(self) -> str:
        return (f"MediaIntelligenceResult(action={self.action.value}, "
                f"entity={self.entity.name if self.entity else None}, "
                f"query='{self.search_query}', confidence={self.confidence:.2f})")


# ─────────────────────────── direct play patterns ───────────────────────────

# "play X" where X is a direct name (not a reference)
_DIRECT_PLAY = re.compile(
    r"^(play|stream|put on|start)\s+(?!the |a |another |some )"
    r"(?!something |more |what |what I|music|songs?|tracks?)"
    r"(.+)$",
    re.I
)

# Music control shorthands
_RESUME_PATTERNS = re.compile(r"\b(resume|continue|unpause|play on)\b", re.I)
_CONTINUE_MUSIC  = re.compile(r"\b(continue music|resume music|keep playing)\b", re.I)


# ─────────────────────────── main class ───────────────────────────

class MediaIntelligence:
    """
    Orchestrates all media intelligence modules.

    Integration:
        mi = MediaIntelligence()
        result = mi.process("play another song by him")
        # MediaManager reads result.action and executes

    After provider returns results:
        mi.on_provider_results(results, original_result)
        # call this to update context / generate offers
    """

    def __init__(
        self,
        persist_path: Optional[str] = None,
        memory: Optional[MediaEntityMemory] = None,
        memory_store: Optional[MemoryStore] = None,
    ):
        self.memory       = memory or MediaEntityMemory(persist_path=persist_path)
        self._memory_store = memory_store or MemoryStore(session_id="media_intelligence")
        self.offers       = MediaOfferManager(self._memory_store)
        self.resolver     = MediaReferenceResolver(self.memory)
        self.prefs        = MediaPreferenceModel(self.memory)
        self.recommender  = MediaRecommendationEngine(self.memory, self.resolver, self.prefs)
        self.opportunity  = MediaOpportunityEngine(self.memory)
        self.followup     = MediaFollowUpEngine(self.memory, self.offers)
        self._last_result: Optional[MediaIntelligenceResult] = None

    # ── main entry ────────────────────────────────────────────

    def process(self, utterance: str) -> MediaIntelligenceResult:
        t0 = time.time()
        result = self._route(utterance)
        result.source_utterance = utterance
        result.processing_ms    = (time.time() - t0) * 1000
        self._last_result        = result
        self.followup.push_turn(
            utterance=utterance,
            resolved_entity=result.entity,
            candidates=result.candidates,
        )
        return result

    # ── routing pipeline ──────────────────────────────────────

    def _route(self, utterance: str) -> MediaIntelligenceResult:
        text = utterance.strip()

        # ── Stage 1: Follow-up detection ──────────────────────
        fu = self.followup.resolve_followup(text)

        if fu.is_follow_up:
            return self._handle_followup(fu, text)

        # ── Stage 2: Opportunity detection ────────────────────
        opp_result = self._check_opportunity(text)
        if opp_result:
            return opp_result

        # ── Stage 3: Direct play command ──────────────────────
        direct = self._try_direct_play(text)
        if direct:
            return direct

        # ── Stage 4: Reference-based resolution ───────────────
        ref = self.resolver.resolve(text)
        if ref.success:
            return self._handle_reference(ref, text)

        # ── Stage 5: Recommendation ───────────────────────────
        rec = self.recommender.recommend(text)
        if rec.request.effective_query():
            return MediaIntelligenceResult(
                action=IntelligenceAction.SEARCH_AND_PLAY,
                search_query=rec.request.effective_query(),
                provider_hint=rec.request.provider_hint,
                confidence=rec.confidence,
                display_text=f"Finding {rec.request.effective_query()}...",
            )

        # ── Stage 6: Fallback ─────────────────────────────────
        return MediaIntelligenceResult(
            action=IntelligenceAction.CLARIFY,
            confidence=0.2,
            display_text="Not sure what to play. Can you be more specific?",
        )

    # ── follow-up handler ─────────────────────────────────────

    def _handle_followup(
        self, fu: FollowUpResolution, utterance: str
    ) -> MediaIntelligenceResult:

        if fu.follow_up_type == FollowUpType.OFFER_RESPONSE:
            if fu.offer_response:
                # Retrieve what was accepted
                active = self.offers.get_active_offer()
                if active:
                    accepted = self.offers.accept_active_offer()
                    entity   = self.offers.get_accepted_entity(accepted) if accepted else None
                    if entity:
                        return MediaIntelligenceResult(
                            action=IntelligenceAction.ACCEPT_OFFER,
                            entity=entity,
                            confidence=0.99,
                            display_text=f"Playing {entity.name}.",
                        )
                return MediaIntelligenceResult(
                    action=IntelligenceAction.ACCEPT_OFFER,
                    confidence=0.7,
                    display_text="Playing it.",
                )
            else:
                return MediaIntelligenceResult(
                    action=IntelligenceAction.REJECT_OFFER,
                    confidence=0.99,
                    display_text="OK, skipping.",
                )

        if fu.follow_up_type == FollowUpType.REJECTION:
            # User rejected the current media. Find and play the next candidate.
            ctx = self._media_context
            current_id = ctx.current_media_id
            rejected = list(ctx.rejected_media_ids)
            if current_id and current_id not in rejected:
                rejected.append(current_id)
            ctx.rejected_media_ids = rejected
            # Preserve the original query context for re-search
            original_query = ctx.current_rejection_query or ctx.pending_media_query or ctx.last_query
            original_mood = ctx.current_rejection_mood or ctx.get_mood() or ""
            original_activity = ctx.current_rejection_activity or ctx.get_activity() or ""
            # Check if we have available candidates to try next
            if ctx.available_candidates and not ctx.candidate_pool_exhausted:
                for candidate in ctx.available_candidates:
                    cid = getattr(candidate, 'video_id', '') or getattr(candidate, 'name', '') or str(candidate)
                    if cid not in rejected:
                        # Play this next candidate
                        entity = candidate if isinstance(candidate, type(ctx.get_last_entity())) else None
                        if entity:
                            return MediaIntelligenceResult(
                                action=IntelligenceAction.PLAY_ENTITY,
                                entity=entity,
                                confidence=0.90,
                                display_text=f"Playing {entity.name}.",
                                source_utterance=utterance,
                            )
                        # If not a ResolvedEntity, use search
                        break
            # No more candidates — do a broader search
            if original_query:
                # Broader query: add "popular" or "best" to get different results
                broader_query = f"popular {original_query}" if original_query else ""
                return MediaIntelligenceResult(
                    action=IntelligenceAction.SEARCH_AND_PLAY,
                    search_query=broader_query or original_query,
                    confidence=0.80,
                    display_text="Finding something else...",
                    source_utterance=utterance,
                )
            return MediaIntelligenceResult(
                action=IntelligenceAction.SEARCH_AND_PLAY,
                search_query="popular trending",
                confidence=0.60,
                display_text="Finding something else...",
                source_utterance=utterance,
            )

        if fu.follow_up_type == FollowUpType.TRANSPORT:
            return MediaIntelligenceResult(
                action=IntelligenceAction.TRANSPORT,
                transport_command=fu.transport_command,
                confidence=fu.confidence,
            )

        if fu.follow_up_type == FollowUpType.VOLUME:
            delta = MediaFollowUpEngine.parse_volume_delta(utterance)
            return MediaIntelligenceResult(
                action=IntelligenceAction.VOLUME,
                volume_delta=delta,
                confidence=0.95,
            )

        if fu.follow_up_type == FollowUpType.ORDINAL_SELECTION:
            if fu.resolved_entity:
                return MediaIntelligenceResult(
                    action=IntelligenceAction.PLAY_ENTITY,
                    entity=fu.resolved_entity,
                    confidence=fu.confidence,
                    display_text=f"Playing {fu.resolved_entity.name}.",
                )
            return MediaIntelligenceResult(
                action=IntelligenceAction.CLARIFY,
                confidence=0.3,
                display_text="Which one? I don't have a list right now.",
            )

        if fu.follow_up_type == FollowUpType.CONTINUATION:
            query = fu.query_override or ""
            if query:
                return MediaIntelligenceResult(
                    action=IntelligenceAction.SEARCH_AND_PLAY,
                    search_query=query,
                    confidence=fu.confidence,
                    display_text=f"Finding more like that...",
                )

        if fu.follow_up_type == FollowUpType.QUEUE_OP:
            entity = fu.resolved_entity or self.memory.get_last_entity()
            return MediaIntelligenceResult(
                action=IntelligenceAction.QUEUE_ADD,
                entity=entity,
                confidence=0.90,
                display_text=f"Added to queue." if entity else "Nothing to queue.",
            )

        # Ambiguous follow-up — return clarify
        return MediaIntelligenceResult(
            action=IntelligenceAction.CLARIFY,
            confidence=0.4,
            display_text="Could you clarify what you'd like?",
        )

    # ── opportunity handler ───────────────────────────────────

    def _check_opportunity(self, text: str) -> Optional[MediaIntelligenceResult]:
        # Score query ("Did Messi score?")
        score_opp = self.opportunity.detect_score_query(text)
        if score_opp:
            return MediaIntelligenceResult(
                action=IntelligenceAction.SEARCH_AND_PLAY,
                search_query=score_opp.search_query,
                provider_hint=score_opp.provider_hint,
                confidence=score_opp.confidence,
                display_text=f"Checking for {score_opp.entity_name} highlights...",
                followup_hint="opportunity_pending",
            )

        # New content query ("Anything new from Marvel?")
        new_opp = self.opportunity.detect_new_content_query(text)
        if new_opp:
            return MediaIntelligenceResult(
                action=IntelligenceAction.SEARCH_AND_PLAY,
                search_query=new_opp.search_query,
                provider_hint=new_opp.provider_hint,
                confidence=new_opp.confidence,
                display_text=f"Looking for new content from {new_opp.entity_name}...",
                followup_hint="opportunity_pending",
            )

        # Availability query ("Has the Spider-Man trailer released?")
        opp = self.opportunity.detect(text)
        if opp:
            return MediaIntelligenceResult(
                action=IntelligenceAction.SEARCH_AND_PLAY,
                search_query=opp.search_query,
                provider_hint=opp.provider_hint,
                confidence=opp.confidence,
                display_text=opp.to_display_question(),
                followup_hint="opportunity_pending",
            )

        return None

    # ── direct play handler ───────────────────────────────────

    def _try_direct_play(self, text: str) -> Optional[MediaIntelligenceResult]:
        # Resume / continue
        if _CONTINUE_MUSIC.search(text) or _RESUME_PATTERNS.search(text):
            return MediaIntelligenceResult(
                action=IntelligenceAction.TRANSPORT,
                transport_command=TransportCommand.RESUME,
                confidence=0.98,
            )

        m = _DIRECT_PLAY.match(text)
        if m:
            query = m.group(2).strip()
            # Determine provider hint from query content
            provider = self._infer_provider_from_query(query)
            return MediaIntelligenceResult(
                action=IntelligenceAction.SEARCH_AND_PLAY,
                search_query=query,
                provider_hint=provider,
                confidence=0.90,
                display_text=f"Searching for {query}...",
            )
        return None

    def _infer_provider_from_query(self, query: str) -> MediaProvider:
        text = query.lower()
        video_keywords = ["trailer", "highlights", "video", "interview", "clip",
                          "livestream", "live stream", "gameplay", "reaction"]
        if any(kw in text for kw in video_keywords):
            return MediaProvider.YOUTUBE
        return self.prefs.get_preferred_provider() or MediaProvider.SPOTIFY

    # ── reference handler ─────────────────────────────────────

    def _handle_reference(
        self, ref: ReferenceResolution, utterance: str
    ) -> MediaIntelligenceResult:
        # Direct entity resolve
        if ref.resolved_entity and not ref.query_override:
            return MediaIntelligenceResult(
                action=IntelligenceAction.PLAY_ENTITY,
                entity=ref.resolved_entity,
                confidence=ref.confidence,
                display_text=f"Playing {ref.resolved_entity.name}.",
            )

        # Query override (variant, continuation, etc.)
        if ref.query_override:
            provider = (
                MediaProvider.SPOTIFY if ref.reference_type in (
                    ReferenceType.MOOD, ReferenceType.ACTIVITY, ReferenceType.CONTINUATION
                ) else self.prefs.get_preferred_provider()
            )
            return MediaIntelligenceResult(
                action=IntelligenceAction.SEARCH_AND_PLAY,
                search_query=ref.query_override,
                provider_hint=provider,
                confidence=ref.confidence,
                display_text=f"Finding {ref.query_override}...",
            )

        return MediaIntelligenceResult(
            action=IntelligenceAction.CLARIFY,
            confidence=0.3,
            display_text="I understood the reference but couldn't find what to play.",
        )

    # ── post-provider hooks ───────────────────────────────────

    def on_provider_results(
        self,
        entities: List[ResolvedEntity],
        original_result: MediaIntelligenceResult,
    ) -> Optional[MediaOffer]:
        """
        Call after provider search returns results.
        If result was an opportunity check, create offer.
        Returns offer if created, else None.
        """
        if original_result.followup_hint == "opportunity_pending" and entities:
            # Build minimal opportunity for result construction
            opp = DetectedOpportunity(
                opportunity_type=__import__("media_opportunity_engine").OpportunityType.ARTIST_NEWS,
                entity_name=original_result.search_query,
                entity_type=EntityType.UNKNOWN,
                confidence=original_result.confidence,
                search_query=original_result.search_query,
            )
            check = self.opportunity.build_result(opp, entities)
            return self.opportunity.create_offer(check, self.offers)
        return None

    def on_session_ended(self, session: HistoricalMediaSession) -> None:
        """Call when playback session ends. Updates memory + preferences."""
        self.memory.push_session(session)
        self.prefs.ingest_session(session)
        self.memory.save()

    # ── utility ───────────────────────────────────────────────

    def get_last_result(self) -> Optional[MediaIntelligenceResult]:
        return self._last_result

    def cleanup(self) -> None:
        self.memory.cleanup_expired()
        self.offers.expire_stale()


# ─────────────────────────── tests ───────────────────────────

import unittest

class TestMediaIntelligence(unittest.TestCase):

    def setUp(self):
        self.mi = MediaIntelligence()

    def _push_track(self, name="Believer", artist="Imagine Dragons"):
        e = ResolvedEntity(name=name, entity_type=EntityType.SONG,
                           provider=MediaProvider.SPOTIFY,
                           metadata={"artist": artist})
        s = HistoricalMediaSession(session_id=f"s_{name}", entity=e)
        self.mi.memory.push_session(s)
        self.mi.prefs.ingest_session(s)
        return e

    # direct play
    def test_play_believer(self):
        r = self.mi.process("play Believer")
        self.assertEqual(r.action, IntelligenceAction.SEARCH_AND_PLAY)
        self.assertIn("Believer", r.search_query)

    def test_play_thunder(self):
        r = self.mi.process("play Thunder")
        self.assertEqual(r.action, IntelligenceAction.SEARCH_AND_PLAY)

    def test_play_trailer(self):
        r = self.mi.process("play the Spider-Man trailer")
        self.assertEqual(r.action, IntelligenceAction.SEARCH_AND_PLAY)
        self.assertEqual(r.provider_hint, MediaProvider.YOUTUBE)

    def test_play_highlights(self):
        r = self.mi.process("play Messi highlights")
        self.assertEqual(r.provider_hint, MediaProvider.YOUTUBE)

    # reference resolution
    def test_another_song_by_him(self):
        self._push_track()
        r = self.mi.process("play another song by him")
        self.assertIn(r.action, [IntelligenceAction.SEARCH_AND_PLAY, IntelligenceAction.PLAY_ENTITY])
        if r.search_query:
            self.assertIn("Imagine Dragons", r.search_query)

    def test_live_version(self):
        self._push_track()
        r = self.mi.process("play the live version")
        self.assertEqual(r.action, IntelligenceAction.SEARCH_AND_PLAY)
        self.assertIn("live", r.search_query)

    def test_remix(self):
        self._push_track()
        r = self.mi.process("play the remix")
        self.assertIn("remix", r.search_query)

    def test_play_again(self):
        self._push_track()
        r = self.mi.process("play that again")
        self.assertIn(r.action, [IntelligenceAction.PLAY_ENTITY, IntelligenceAction.SEARCH_AND_PLAY])

    def test_play_yesterday(self):
        import time
        from mini_kio.media.media_intelligence_models import HistoricalMediaSession
        e = ResolvedEntity("Thunder", EntityType.SONG, MediaProvider.SPOTIFY,
                           metadata={"artist": "Imagine Dragons"})
        yesterday = time.time() - 86400 - 1800
        self.mi.memory._history.append(HistoricalMediaSession("yy", entity=e, started_at=yesterday))
        r = self.mi.process("play what I listened to yesterday")
        self.assertNotEqual(r.action, IntelligenceAction.CLARIFY)

    def test_continue_music(self):
        r = self.mi.process("continue music")
        self.assertEqual(r.action, IntelligenceAction.TRANSPORT)
        self.assertEqual(r.transport_command, TransportCommand.RESUME)

    def test_resume(self):
        r = self.mi.process("resume")
        self.assertEqual(r.transport_command, TransportCommand.RESUME)

    # mood / activity
    def test_chill_music(self):
        r = self.mi.process("play chill music")
        self.assertEqual(r.action, IntelligenceAction.SEARCH_AND_PLAY)
        self.assertIn("chill", r.search_query)

    def test_gym_music(self):
        r = self.mi.process("play gym music")
        self.assertEqual(r.action, IntelligenceAction.SEARCH_AND_PLAY)
        self.assertIn("gym", r.search_query)

    def test_study_music(self):
        r = self.mi.process("play study music")
        self.assertEqual(r.action, IntelligenceAction.SEARCH_AND_PLAY)

    def test_coding_music(self):
        r = self.mi.process("play coding music")
        self.assertEqual(r.action, IntelligenceAction.SEARCH_AND_PLAY)

    # opportunity detection
    def test_spider_man_trailer_released(self):
        r = self.mi.process("Has the Spider-Man trailer released?")
        self.assertEqual(r.action, IntelligenceAction.SEARCH_AND_PLAY)
        self.assertIn("trailer", r.search_query)

    def test_messi_score(self):
        r = self.mi.process("Did Messi score yesterday?")
        self.assertEqual(r.action, IntelligenceAction.SEARCH_AND_PLAY)
        self.assertIn("Messi", r.search_query)

    def test_anything_new_marvel(self):
        r = self.mi.process("Anything new from Marvel?")
        self.assertEqual(r.action, IntelligenceAction.SEARCH_AND_PLAY)
        self.assertIn("Marvel", r.search_query)

    # transport
    def test_pause(self):
        r = self.mi.process("pause")
        self.assertEqual(r.action, IntelligenceAction.TRANSPORT)
        self.assertEqual(r.transport_command, TransportCommand.PAUSE)

    def test_next(self):
        r = self.mi.process("next song")
        self.assertEqual(r.transport_command, TransportCommand.NEXT)

    def test_stop(self):
        r = self.mi.process("stop music")
        self.assertEqual(r.transport_command, TransportCommand.STOP)

    # volume
    def test_louder(self):
        r = self.mi.process("louder")
        self.assertEqual(r.action, IntelligenceAction.VOLUME)
        self.assertEqual(r.volume_delta, +10)

    def test_quieter(self):
        r = self.mi.process("turn it down")
        self.assertEqual(r.action, IntelligenceAction.VOLUME)
        self.assertEqual(r.volume_delta, -10)

    # offer flow
    def test_offer_accept_flow(self):
        e = ResolvedEntity("Spider-Man Trailer", EntityType.MOVIE, MediaProvider.YOUTUBE)
        offer = self.mi.offers.create_single_offer(e, OfferTrigger.TRAILER_RELEASED, "test")
        r = self.mi.process("yes")
        self.assertEqual(r.action, IntelligenceAction.ACCEPT_OFFER)

    def test_offer_reject_flow(self):
        e = ResolvedEntity("Spider-Man Trailer", EntityType.MOVIE, MediaProvider.YOUTUBE)
        self.mi.offers.create_single_offer(e, OfferTrigger.TRAILER_RELEASED, "test")
        r = self.mi.process("no")
        self.assertEqual(r.action, IntelligenceAction.REJECT_OFFER)

    # similarity
    def test_something_similar(self):
        self._push_track()
        r = self.mi.process("play something similar")
        self.assertEqual(r.action, IntelligenceAction.SEARCH_AND_PLAY)

    # meta
    def test_result_has_processing_ms(self):
        r = self.mi.process("play Believer")
        self.assertGreater(r.processing_ms, 0)

    def test_result_has_source_utterance(self):
        r = self.mi.process("play Thunder")
        self.assertEqual(r.source_utterance, "play Thunder")


if __name__ == "__main__":
    unittest.main()
