"""
media_followup_engine.py
KIO Media Intelligence Layer — Follow-up Engine
Handles multi-turn conversations. Chains context across turns.
Detects when an utterance is a follow-up vs new intent.
"""

from __future__ import annotations

import re
import time
from dataclasses import dataclass, field
from enum import Enum
from typing import Any, Dict, List, Optional, Tuple

from mini_kio.media.media_context import MediaContext
from mini_kio.media.media_intelligence_models import (
    EntityType, MediaProvider, ResolvedEntity
)
from mini_kio.media.intelligence.media_offer_manager import MediaOffer, MediaOfferManager, OfferStatus, OfferTrigger


# ─────────────────────────── enums ───────────────────────────

class FollowUpType(str, Enum):
    OFFER_RESPONSE       = "offer_response"      # yes/no to pending offer
    ORDINAL_SELECTION    = "ordinal_selection"    # "play the second one"
    CONTINUATION         = "continuation"         # "another one"
    REPLAY               = "replay"               # "play that again"
    VARIANT              = "variant"              # "play the remix"
    VOLUME               = "volume"               # "louder"
    TRANSPORT            = "transport"            # "pause", "next", "stop"
    QUEUE_OP             = "queue_op"             # "add to queue"
    NEW_QUERY            = "new_query"            # fresh intent, not a follow-up
    AMBIGUOUS            = "ambiguous"


class TransportCommand(str, Enum):
    PLAY     = "play"
    PAUSE    = "pause"
    RESUME   = "resume"
    STOP     = "stop"
    NEXT     = "next"
    PREVIOUS = "previous"
    SHUFFLE  = "shuffle"
    REPEAT   = "repeat"
    MUTE     = "mute"
    UNMUTE   = "unmute"
    SEEK     = "seek"


# ─────────────────────────── dataclasses ───────────────────────────

@dataclass
class TurnContext:
    """State for one conversation turn."""
    utterance: str
    timestamp: float = field(default_factory=time.time)
    resolved_entity: Optional[ResolvedEntity] = None
    offer_pending: bool = False
    candidates: List[ResolvedEntity] = field(default_factory=list)
    intent_label: str = ""


@dataclass
class FollowUpResolution:
    follow_up_type: FollowUpType
    is_follow_up: bool
    transport_command: Optional[TransportCommand] = None
    resolved_entity: Optional[ResolvedEntity] = None
    query_override: Optional[str] = None
    offer_response: Optional[bool] = None     # True=accept, False=reject
    ordinal_index: Optional[int] = None
    confidence: float = 1.0
    reason: str = ""

    @property
    def needs_playback(self) -> bool:
        return self.resolved_entity is not None or self.query_override is not None

    @property
    def needs_transport(self) -> bool:
        return self.transport_command is not None


# ─────────────────────────── pattern tables ───────────────────────────

_TRANSPORT_MAP: Dict[re.Pattern, TransportCommand] = {
    re.compile(r"\b(pause|hold on|wait|stop music for now)\b", re.I): TransportCommand.PAUSE,
    re.compile(r"\b(resume|continue|unpause|play again|keep going)\b", re.I): TransportCommand.RESUME,
    re.compile(r"\b(stop|stop music|stop playing|turn off music)\b", re.I): TransportCommand.STOP,
    re.compile(r"\b(next|next song|skip|skip this|next track)\b", re.I): TransportCommand.NEXT,
    re.compile(r"\b(previous|prev|back|go back|last song)\b", re.I): TransportCommand.PREVIOUS,
    re.compile(r"\b(shuffle|shuffle mode|random)\b", re.I): TransportCommand.SHUFFLE,
    re.compile(r"\b(repeat|loop|repeat this|loop this)\b", re.I): TransportCommand.REPEAT,
    re.compile(r"\b(mute|silence|quiet)\b", re.I): TransportCommand.MUTE,
    re.compile(r"\b(unmute|restore sound)\b", re.I): TransportCommand.UNMUTE,
}

_VOLUME_PATTERNS = [
    re.compile(r"\b(louder|volume up|turn (it |the volume )?up|increase volume)\b", re.I),
    re.compile(r"\b(quieter|softer|volume down|turn (it |the volume )?down|lower (the )?volume)\b", re.I),
    re.compile(r"\bset volume to (\d+)\b", re.I),
    re.compile(r"\b(\d+)%? volume\b", re.I),
]

_QUEUE_PATTERNS = re.compile(
    r"\b(add to queue|queue (it|this|that)|add this|add that|play (this|it) next)\b", re.I
)

_CONTINUATION_PATTERNS = re.compile(
    r"\b(another one|next one|one more|play more|more like (this|that)|another song|another track)\b", re.I
)

_ORDINAL_PATTERNS: Dict[re.Pattern, int] = {
    re.compile(r"\b(first( one)?|number (one|1)|#?1|the first)\b",  re.I): 0,
    re.compile(r"\b(second( one)?|number (two|2)|#?2|the second)\b",re.I): 1,
    re.compile(r"\b(third( one)?|number (three|3)|#?3|the third)\b",re.I): 2,
    re.compile(r"\b(fourth( one)?|number (four|4)|#?4|the fourth)\b",re.I): 3,
    re.compile(r"\b(fifth( one)?|number (five|5)|#?5|the fifth)\b", re.I): 4,
}

_AFFIRMATIVES = {"yes", "yeah", "yep", "sure", "ok", "okay", "play it", "play",
                 "go ahead", "yup", "do it", "absolutely"}
_NEGATIVES    = {"no", "nope", "nah", "skip", "not now", "pass", "no thanks",
                 "never mind", "cancel", "forget it"}


# ─────────────────────────── engine ───────────────────────────

class MediaFollowUpEngine:
    """
    Detects whether a new utterance is a follow-up to prior context
    and resolves it accordingly.

    Integration:
        engine = MediaFollowUpEngine(memory, offer_manager)

        # Before routing to intelligence:
        resolution = engine.resolve_followup(utterance)
        if resolution.is_follow_up:
            handle_followup(resolution)
        else:
            route_to_intelligence(utterance)

    Call engine.push_turn() after every processed turn to maintain context.
    """

    # Context window — how old a turn can be to still count as context (seconds)
    CONTEXT_WINDOW_SECONDS = 120

    def __init__(
        self,
        media_context: MediaContext,
        offer_manager: MediaOfferManager,
    ):
        self._media_context = media_context
        self._offers  = offer_manager
        self._history: List[TurnContext] = []
        self._max_history = 10

    # ── push context ──────────────────────────────────────────

    def push_turn(
        self,
        utterance: str,
        resolved_entity: Optional[ResolvedEntity] = None,
        candidates: Optional[List[ResolvedEntity]] = None,
        intent_label: str = "",
    ) -> None:
        ctx = TurnContext(
            utterance=utterance,
            resolved_entity=resolved_entity,
            offer_pending=self._offers.has_pending_offer(),
            candidates=candidates or [],
            intent_label=intent_label,
        )
        self._history.append(ctx)
        if len(self._history) > self._max_history:
            self._history.pop(0)

    # ── main resolution ───────────────────────────────────────

    def resolve_followup(self, utterance: str) -> FollowUpResolution:
        """
        Classify utterance as follow-up or new intent.
        Returns FollowUpResolution — caller acts on .follow_up_type.
        """
        text = utterance.strip()

        # 1. Pending offer check — highest priority
        if self._offers.has_pending_offer():
            offer_result = self._try_offer_response(text)
            if offer_result:
                return offer_result

        # 2. Transport commands
        transport_result = self._try_transport(text)
        if transport_result:
            return transport_result

        # 3. Volume
        if self._is_volume_command(text):
            return FollowUpResolution(
                follow_up_type=FollowUpType.VOLUME,
                is_follow_up=True,
                confidence=0.95,
                reason="volume command",
            )

        # 4. Queue operation
        if _QUEUE_PATTERNS.search(text):
            entity = self._media_context.get_last_entity()
            return FollowUpResolution(
                follow_up_type=FollowUpType.QUEUE_OP,
                is_follow_up=True,
                resolved_entity=entity,
                confidence=0.90,
                reason="queue operation on last entity",
            )

        # 5. Ordinal selection (refers to prior candidate list)
        ordinal_result = self._try_ordinal(text)
        if ordinal_result:
            return ordinal_result

        # 6. Continuation
        if _CONTINUATION_PATTERNS.search(text):
            artist = self._media_context.get_last_artist()
            return FollowUpResolution(
                follow_up_type=FollowUpType.CONTINUATION,
                is_follow_up=True,
                query_override=f"{artist} popular songs" if artist else None,
                confidence=0.85 if artist else 0.40,
                reason=f"continuation, artist={artist}",
            )

        # 7. Check if utterance is contextually short (likely follow-up)
        if self._is_contextually_dependent(text):
            return FollowUpResolution(
                follow_up_type=FollowUpType.AMBIGUOUS,
                is_follow_up=True,
                confidence=0.55,
                reason="short utterance likely contextual",
            )

        # Not a follow-up
        return FollowUpResolution(
            follow_up_type=FollowUpType.NEW_QUERY,
            is_follow_up=False,
            confidence=0.85,
            reason="new intent detected",
        )

    # ── resolution helpers ────────────────────────────────────

    def _try_offer_response(self, text: str) -> Optional[FollowUpResolution]:
        result = self._offers.parse_response(text)
        if result is True:
            offer  = None  # already accepted by parse_response
            return FollowUpResolution(
                follow_up_type=FollowUpType.OFFER_RESPONSE,
                is_follow_up=True,
                offer_response=True,
                confidence=0.99,
                reason="offer accepted",
            )
        if result is False:
            return FollowUpResolution(
                follow_up_type=FollowUpType.OFFER_RESPONSE,
                is_follow_up=True,
                offer_response=False,
                confidence=0.99,
                reason="offer rejected",
            )
        return None

    def _try_transport(self, text: str) -> Optional[FollowUpResolution]:
        for pattern, command in _TRANSPORT_MAP.items():
            if pattern.search(text):
                return FollowUpResolution(
                    follow_up_type=FollowUpType.TRANSPORT,
                    is_follow_up=True,
                    transport_command=command,
                    confidence=0.97,
                    reason=f"transport: {command.value}",
                )
        return None

    def _try_ordinal(self, text: str) -> Optional[FollowUpResolution]:
        for pattern, idx in _ORDINAL_PATTERNS.items():
            if pattern.search(text):
                # Get candidates from most recent turn
                recent_candidates = self._get_recent_candidates()
                entity = None
                if idx < len(recent_candidates):
                    entity = recent_candidates[idx]
                return FollowUpResolution(
                    follow_up_type=FollowUpType.ORDINAL_SELECTION,
                    is_follow_up=True,
                    resolved_entity=entity,
                    ordinal_index=idx,
                    confidence=0.92 if entity else 0.4,
                    reason=f"ordinal[{idx}] from recent candidates",
                )
        return None

    def _is_volume_command(self, text: str) -> bool:
        return any(p.search(text) for p in _VOLUME_PATTERNS)

    def _get_recent_candidates(self) -> List[ResolvedEntity]:
        """Return candidates from the most recent context turn."""
        now = time.time()
        for turn in reversed(self._history):
            if now - turn.timestamp <= self.CONTEXT_WINDOW_SECONDS:
                if turn.candidates:
                    return turn.candidates
        return []

    def _get_recent_turn(self) -> Optional[TurnContext]:
        now = time.time()
        for turn in reversed(self._history):
            if now - turn.timestamp <= self.CONTEXT_WINDOW_SECONDS:
                return turn
        return None

    def _is_contextually_dependent(self, text: str) -> bool:
        """Short utterances likely depend on context."""
        words = text.split()
        if len(words) <= 2:
            text_lower = text.lower()
            if (text_lower in _AFFIRMATIVES or
                text_lower in _NEGATIVES or
                any(p.search(text) for p in _ORDINAL_PATTERNS)):
                return True
        return False

    # ── parse volume value ────────────────────────────────────

    @staticmethod
    def parse_volume_delta(utterance: str) -> Optional[int]:
        """
        Returns +10, -10, or absolute 0-100.
        None if not a volume command.
        """
        text = utterance.lower()
        if re.search(r"\b(louder|volume up|turn\s+(?:it\s+|the\s+volume\s+)?up|increase volume)\b", text):
            return +10
        if re.search(r"\b(quieter|softer|volume down|turn\s+(?:it\s+|the\s+volume\s+)?down|lower\s+(?:the\s+)?volume)\b", text):
            return -10
        m = re.search(r"\b(\d+)\s*%?\s*(volume|vol)?\b", text)
        if m:
            return int(m.group(1))
        return None


# ─────────────────────────── tests ───────────────────────────

import unittest

class TestMediaFollowUpEngine(unittest.TestCase):

    def setUp(self):
        class MockMediaContext:
            def __init__(self):
                self._last_resolved_entity = None
                self._last_artist = None # To support get_last_artist() for test
            def get_last_entity(self):
                return self._last_resolved_entity
            def set_last_entity(self, entity):
                self._last_resolved_entity = entity
            def get_last_artist(self):
                return self._last_artist
            def set_last_artist(self, artist): # Used by the mock _push_track_to_memory
                self._last_artist = artist

        class MockMemoryStore: # From MediaOfferManager's updated test
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
        # MediaOfferManager now takes MemoryStore
        self.offers = MediaOfferManager(self.mock_memory_store)
        self.engine = MediaFollowUpEngine(self.mock_media_context, self.offers)

    def _make_entity(self, name="Believer", etype=EntityType.SONG):
        return ResolvedEntity(name=name, entity_type=etype, provider=MediaProvider.SPOTIFY,
                              metadata={"artist": "Imagine Dragons"})

    def _push_track_to_memory(self):
        # This helper now directly sets the last entity in the mock MediaContext.
        e = self._make_entity()
        self.mock_media_context.set_last_entity(e)
        self.mock_media_context.set_last_artist(e.metadata["artist"]) # To make get_last_artist work for the test

    # offer response
    def test_yes_to_offer(self):
        e = self._make_entity("Spider-Man Trailer", EntityType.MOVIE)
        self.offers.create_single_offer(e, OfferTrigger.TRAILER_RELEASED, "test")
        r = self.engine.resolve_followup("yes")
        self.assertTrue(r.is_follow_up)
        self.assertEqual(r.follow_up_type, FollowUpType.OFFER_RESPONSE)
        self.assertTrue(r.offer_response)

    def test_no_to_offer(self):
        e = self._make_entity("Spider-Man Trailer", EntityType.MOVIE)
        self.offers.create_single_offer(e, OfferTrigger.TRAILER_RELEASED, "test")
        r = self.engine.resolve_followup("no")
        self.assertFalse(r.offer_response)

    def test_ok_to_offer(self):
        e = self._make_entity("X", EntityType.MOVIE)
        self.offers.create_single_offer(e, OfferTrigger.TRAILER_RELEASED, "test")
        r = self.engine.resolve_followup("ok")
        self.assertTrue(r.offer_response)

    # transport
    def test_pause(self):
        r = self.engine.resolve_followup("pause")
        self.assertEqual(r.transport_command, TransportCommand.PAUSE)
        self.assertTrue(r.needs_transport)

    def test_resume(self):
        r = self.engine.resolve_followup("resume")
        self.assertEqual(r.transport_command, TransportCommand.RESUME)

    def test_next(self):
        r = self.engine.resolve_followup("next")
        self.assertEqual(r.transport_command, TransportCommand.NEXT)

    def test_stop(self):
        r = self.engine.resolve_followup("stop")
        self.assertEqual(r.transport_command, TransportCommand.STOP)

    def test_previous(self):
        r = self.engine.resolve_followup("go back")
        self.assertEqual(r.transport_command, TransportCommand.PREVIOUS)

    def test_mute(self):
        r = self.engine.resolve_followup("mute")
        self.assertEqual(r.transport_command, TransportCommand.MUTE)

    def test_skip(self):
        r = self.engine.resolve_followup("skip this")
        self.assertEqual(r.transport_command, TransportCommand.NEXT)

    # volume
    def test_louder(self):
        r = self.engine.resolve_followup("louder")
        self.assertEqual(r.follow_up_type, FollowUpType.VOLUME)

    def test_volume_down(self):
        r = self.engine.resolve_followup("turn it down")
        self.assertEqual(r.follow_up_type, FollowUpType.VOLUME)

    def test_parse_volume_up(self):
        self.assertEqual(MediaFollowUpEngine.parse_volume_delta("louder"), +10)

    def test_parse_volume_down(self):
        self.assertEqual(MediaFollowUpEngine.parse_volume_delta("quieter"), -10)

    def test_parse_volume_absolute(self):
        self.assertEqual(MediaFollowUpEngine.parse_volume_delta("set volume to 70"), 70)

    # continuation
    def test_another_one(self):
        self._push_track_to_memory()
        r = self.engine.resolve_followup("another one")
        self.assertEqual(r.follow_up_type, FollowUpType.CONTINUATION)

    def test_one_more(self):
        self._push_track_to_memory()
        r = self.engine.resolve_followup("one more")
        self.assertTrue(r.is_follow_up)

    # ordinal
    def test_ordinal_first_with_candidates(self):
        candidates = [self._make_entity("A"), self._make_entity("B")]
        self.engine.push_turn("search results", candidates=candidates)
        r = self.engine.resolve_followup("play the first one")
        self.assertEqual(r.ordinal_index, 0)
        self.assertEqual(r.resolved_entity.name, "A")

    def test_ordinal_second(self):
        candidates = [self._make_entity("A"), self._make_entity("B")]
        self.engine.push_turn("search results", candidates=candidates)
        r = self.engine.resolve_followup("the second one")
        self.assertEqual(r.ordinal_index, 1)

    def test_ordinal_out_of_range(self):
        r = self.engine.resolve_followup("the first one")
        self.assertEqual(r.ordinal_index, 0)
        self.assertIsNone(r.resolved_entity)

    # queue
    def test_add_to_queue(self):
        self._push_track_to_memory()
        r = self.engine.resolve_followup("add to queue")
        self.assertEqual(r.follow_up_type, FollowUpType.QUEUE_OP)

    # new query
    def test_new_query_not_followup(self):
        r = self.engine.resolve_followup("play Radioactive by Imagine Dragons")
        self.assertFalse(r.is_follow_up)
        self.assertEqual(r.follow_up_type, FollowUpType.NEW_QUERY)

    def test_new_query_complex(self):
        r = self.engine.resolve_followup("has the Spider-Man trailer released?")
        self.assertFalse(r.is_follow_up)

    # shuffle / repeat
    def test_shuffle(self):
        r = self.engine.resolve_followup("shuffle")
        self.assertEqual(r.transport_command, TransportCommand.SHUFFLE)

    def test_repeat(self):
        r = self.engine.resolve_followup("repeat this")
        self.assertEqual(r.transport_command, TransportCommand.REPEAT)

    # context window
    def test_old_context_ignored(self):
        old_ctx = TurnContext(
            utterance="play A",
            timestamp=time.time() - 300,  # 5 min ago
            candidates=[self._make_entity("A")],
        )
        self.engine._history.append(old_ctx)
        r = self.engine.resolve_followup("the first one")
        # No recent candidates → no entity resolved
        self.assertIsNone(r.resolved_entity)


if __name__ == "__main__":
    unittest.main()
