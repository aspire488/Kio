"""
media_offer_manager.py
KIO Media Intelligence Layer — Offer Manager
Manages proactive media offers: create, present, accept, reject, expire.
Decoupled from playback — caller (MediaIntelligence) drives execution.
"""

from __future__ import annotations

import json
import re
import time
import uuid
from dataclasses import dataclass, field
from enum import Enum
from typing import Any, Dict, List, Optional

from mini_kio.media.media_intelligence_models import (
    EntityType, MediaProvider, ResolvedEntity
)
from mini_kio.memory.memory_store import MemoryStore


# ─────────────────────────── enums ───────────────────────────

class OfferStatus(str, Enum):
    PENDING   = "pending"
    ACCEPTED  = "accepted"
    REJECTED  = "rejected"
    EXPIRED   = "expired"
    PLAYED    = "played"


class OfferTrigger(str, Enum):
    TRAILER_RELEASED    = "trailer_released"
    HIGHLIGHTS_AVAILABLE = "highlights_available"
    NEW_SONG            = "new_song"
    NEW_ALBUM           = "new_album"
    INTERVIEW_AVAILABLE = "interview_available"
    LIVESTREAM_LIVE     = "livestream_live"
    MATCH_STARTED       = "match_started"
    SCORE_UPDATE        = "score_update"
    ARTIST_NEWS         = "artist_news"
    TRENDING_NOW        = "trending_now"
    USER_QUERY          = "user_query"       # user asked, system found
    CONTINUATION        = "continuation"     # after a track ends


# ─────────────────────────── dataclasses ───────────────────────────

@dataclass
class MediaOffer:
    offer_id: str = field(default_factory=lambda: str(uuid.uuid4())[:8])
    trigger: OfferTrigger = OfferTrigger.USER_QUERY
    entity: Optional[ResolvedEntity] = None
    title: str = ""                                # display title for offer
    description: str = ""                          # context shown to user
    candidates: List[ResolvedEntity] = field(default_factory=list)  # multi-result offers
    status: OfferStatus = OfferStatus.PENDING
    created_at: float = field(default_factory=time.time)
    ttl_seconds: float = 300.0                     # 5 min default
    accepted_at: Optional[float] = None
    rejected_at: Optional[float] = None
    accepted_index: Optional[int] = None           # which candidate was chosen
    source_query: str = ""
    confidence: float = 1.0

    def is_expired(self) -> bool:
        return time.time() > self.created_at + self.ttl_seconds

    def age_seconds(self) -> float:
        return time.time() - self.created_at

    def to_dict(self) -> Dict:
        d = {
            "offer_id": self.offer_id,
            "trigger": self.trigger.value,
            "entity": self.entity.to_dict() if self.entity else None,
            "title": self.title,
            "description": self.description,
            "candidates": [c.to_dict() for c in self.candidates],
            "status": self.status.value,
            "created_at": self.created_at,
            "ttl_seconds": self.ttl_seconds,
            "accepted_at": self.accepted_at,
            "rejected_at": self.rejected_at,
            "accepted_index": self.accepted_index,
            "source_query": self.source_query,
            "confidence": self.confidence,
        }
        return d

    @classmethod
    def from_dict(cls, d: Dict) -> "MediaOffer":
        entity = ResolvedEntity.from_dict(d["entity"]) if d.get("entity") else None
        candidates = [ResolvedEntity.from_dict(c) for c in d.get("candidates", [])]
        return cls(
            offer_id=d["offer_id"],
            trigger=OfferTrigger(d["trigger"]),
            entity=entity,
            title=d["title"],
            description=d["description"],
            candidates=candidates,
            status=OfferStatus(d["status"]),
            created_at=d["created_at"],
            ttl_seconds=d["ttl_seconds"],
            accepted_at=d["accepted_at"],
            rejected_at=d["rejected_at"],
            accepted_index=d["accepted_index"],
            source_query=d["source_query"],
            confidence=d["confidence"],
        )

    def to_display(self) -> str:
        """Human-readable offer text."""
        if self.candidates:
            lines = [self.description or self.title, ""]
            for i, c in enumerate(self.candidates[:5], 1):
                lines.append(f"  {i}. {c.name}")
            lines.append("")
            lines.append("Would you like me to play one?")
            return "\n".join(lines)
        entity_name = self.entity.name if self.entity else "?"
        return f"{self.description}\n\nWould you like me to play it?"


# ─────────────────────────── manager ───────────────────────────

class MediaOfferManager:
    """
    Manages the lifecycle of proactive media offers.

    Usage:
        mgr = MediaOfferManager(memory)

        # Create offer
        offer = mgr.create_offer(trigger, entity, description)

        # Present to user (returns display string)
        text = offer.to_display()

        # User says "yes" → accept
        result = mgr.accept_active_offer()
        if result:
            entity = result.entity or result.candidates[0]
            # → hand to MediaManager.play(entity)

        # User says "no" → reject
        mgr.reject_active_offer()
    """

    # Affirmative / negative patterns
    _AFFIRMATIVES = {"yes", "yeah", "yep", "sure", "ok", "okay", "play it", "play",
                     "go ahead", "yup", "absolutely", "do it", "of course", "why not"}
    _NEGATIVES    = {"no", "nope", "nah", "skip", "not now", "don't", "never mind",
                     "pass", "no thanks", "forget it", "cancel"}

    def __init__(self, memory_store: MemoryStore):
        self._memory_store = memory_store
        self._offers: Dict[str, MediaOffer] = {}
        self._active: Optional[str] = None    # current pending offer id

    # ── create ────────────────────────────────────────────────

    def create_offer(
        self,
        trigger: OfferTrigger,
        entity: Optional[ResolvedEntity] = None,
        description: str = "",
        candidates: Optional[List[ResolvedEntity]] = None,
        ttl_seconds: float = 300.0,
        confidence: float = 1.0,
        source_query: str = "",
    ) -> MediaOffer:
        offer = MediaOffer(
            trigger=trigger,
            entity=entity,
            description=description,
            candidates=candidates or [],
            ttl_seconds=ttl_seconds,
            confidence=confidence,
            source_query=source_query,
            title=entity.name if entity else (
                candidates[0].name if candidates else ""
            ),
        )
        self._offers[offer.offer_id] = offer
        self._active = offer.offer_id
        # Persist to memory
        self._memory_store.set_fact(f"offer:{offer.offer_id}", json.dumps(offer.to_dict()))
        self._memory_store.set_fact("active_offer_id", offer.offer_id) # Store active offer ID
        return offer

    def create_single_offer(
        self,
        entity: ResolvedEntity,
        trigger: OfferTrigger,
        description: str,
        ttl: float = 300.0,
    ) -> MediaOffer:
        return self.create_offer(
            trigger=trigger,
            entity=entity,
            description=description,
            ttl_seconds=ttl,
        )

    def create_multi_offer(
        self,
        candidates: List[ResolvedEntity],
        trigger: OfferTrigger,
        description: str,
        ttl: float = 300.0,
    ) -> MediaOffer:
        return self.create_offer(
            trigger=trigger,
            candidates=candidates,
            description=description,
            ttl_seconds=ttl,
        )

    # ── accept / reject ───────────────────────────────────────

    def accept_active_offer(self, candidate_index: int = 0) -> Optional[MediaOffer]:
        """
        Accept the current pending offer.
        Returns the offer with .entity or .candidates[candidate_index] to play.
        """
        offer = self._get_active_offer()
        if not offer:
            return None
        offer.status       = OfferStatus.ACCEPTED
        offer.accepted_at  = time.time()
        offer.accepted_index = candidate_index
        self._memory_store.set_fact(f"offer:{offer.offer_id}", json.dumps(offer.to_dict()))
        self._memory_store.set_fact("active_offer_id", "")
        self._active = None
        return offer

    def reject_active_offer(self) -> Optional[MediaOffer]:
        offer = self._get_active_offer()
        if not offer:
            return None
        offer.status      = OfferStatus.REJECTED
        offer.rejected_at = time.time()
        self._memory_store.set_fact(f"offer:{offer.offer_id}", json.dumps(offer.to_dict()))
        self._memory_store.set_fact("active_offer_id", "")
        self._active = None
        return offer

    def parse_response(self, utterance: str) -> Optional[bool]:
        """
        Parse a user utterance as offer response.
        Returns True = accept, False = reject, None = not a response.
        """
        text = utterance.strip().lower()
        # Check ordinal ("play the second one" → index 1)
        import re
        ordinal_map = {"first": 0, "1": 0, "second": 1, "2": 1,
                       "third": 2, "3": 2, "fourth": 3, "4": 3, "fifth": 4, "5": 4}
        for word, idx in ordinal_map.items():
            if re.search(rf"\b{word}\b", text):
                offer = self._get_active_offer()
                if offer and offer.candidates:
                    self.accept_active_offer(candidate_index=idx)
                    return True

        if any(a in text for a in self._AFFIRMATIVES):
            self.accept_active_offer()
            return True
        if any(n in text for n in self._NEGATIVES):
            self.reject_active_offer()
            return False
        return None

    # ── query ─────────────────────────────────────────────────

    def get_active_offer(self) -> Optional[MediaOffer]:
        return self._get_active_offer()

    def has_pending_offer(self) -> bool:
        return self._get_active_offer() is not None

    def get_accepted_entity(self, offer: MediaOffer) -> Optional[ResolvedEntity]:
        """Get the entity to play from an accepted offer."""
        if offer.status != OfferStatus.ACCEPTED:
            return None
        idx = offer.accepted_index or 0
        if offer.candidates and idx < len(offer.candidates):
            return offer.candidates[idx]
        return offer.entity

    # ── cleanup ───────────────────────────────────────────────

    def expire_stale(self) -> int:
        expired = 0
        for offer_id, offer in list(self._offers.items()):
            if offer.status == OfferStatus.PENDING and offer.is_expired():
                offer.status = OfferStatus.EXPIRED
                self._memory_store.set_fact(f"offer:{offer.offer_id}", json.dumps(offer.to_dict()))
                expired += 1
                if self._active == offer_id:
                    self._active = None
                    self._memory_store.set_fact("active_offer_id", "")
        return expired

    def clear_all(self) -> None:
        for offer_id in list(self._offers.keys()):
            self._memory_store.set_fact(f"offer:{offer_id}", "")
        self._memory_store.set_fact("active_offer_id", "")
        self._offers.clear()
        self._active = None

    # ── internal ──────────────────────────────────────────────

    def _get_active_offer(self) -> Optional[MediaOffer]:
        active_offer_id = self._memory_store.get_fact("active_offer_id")
        if not active_offer_id:
            return None

        offer_str = self._memory_store.get_fact(f"offer:{active_offer_id}")
        if not offer_str:
            self._memory_store.set_fact("active_offer_id", "") # Clear stale active ID
            return None

        try:
            offer_dict = json.loads(offer_str)
            offer = MediaOffer.from_dict(offer_dict)
        except (json.JSONDecodeError, KeyError):
            self._memory_store.set_fact("active_offer_id", "") # Clear corrupted offer
            return None

        if offer.is_expired():
            offer.status = OfferStatus.EXPIRED
            self._memory_store.set_fact(f"offer:{offer.offer_id}", json.dumps(offer.to_dict())) # Update status
            self._memory_store.set_fact("active_offer_id", "") # Clear expired active ID
            return None
        
        # Cache internally for quicker access within a turn
        self._offers[offer.offer_id] = offer
        self._active = offer.offer_id
        return offer

    # ── factory helpers ───────────────────────────────────────

    @staticmethod
    def build_trailer_offer(
        title: str,
        entity: ResolvedEntity,
        mgr: "MediaOfferManager",
        description: str = "",
    ) -> MediaOffer:
        desc = description or f"{title} trailer released today."
        return mgr.create_single_offer(
            entity=entity,
            trigger=OfferTrigger.TRAILER_RELEASED,
            description=desc,
        )

    @staticmethod
    def build_highlights_offer(
        player_name: str,
        entity: ResolvedEntity,
        mgr: "MediaOfferManager",
    ) -> MediaOffer:
        return mgr.create_single_offer(
            entity=entity,
            trigger=OfferTrigger.HIGHLIGHTS_AVAILABLE,
            description=f"{player_name} match highlights available.",
        )


# ─────────────────────────── tests ───────────────────────────

import unittest

class TestMediaOfferManager(unittest.TestCase):

    def setUp(self):
        # Create a mock MemoryStore for testing
        class MockMemoryStore:
            def __init__(self):
                self._facts = {}
            def set_fact(self, key, value):
                self._facts[key] = value
            def get_fact(self, key):
                return self._facts.get(key)
            def get_all_facts(self): # Added to satisfy some potential future needs, not strictly for this current test
                return self._facts

        self.mock_memory_store = MockMemoryStore()
        self.mgr = MediaOfferManager(self.mock_memory_store)

    def _make_entity(self, name="Spider-Man Trailer", etype=EntityType.MOVIE):
        return ResolvedEntity(name=name, entity_type=etype,
                              provider=MediaProvider.YOUTUBE,
                              url="https://youtube.com/watch?v=abc")

    def test_create_offer(self):
        e = self._make_entity()
        offer = self.mgr.create_single_offer(e, OfferTrigger.TRAILER_RELEASED,
                                             "Spider-Man trailer dropped today.")
        self.assertEqual(offer.status, OfferStatus.PENDING)
        self.assertTrue(self.mgr.has_pending_offer())

    def test_accept_offer(self):
        e = self._make_entity()
        self.mgr.create_single_offer(e, OfferTrigger.TRAILER_RELEASED, "test")
        accepted = self.mgr.accept_active_offer()
        self.assertEqual(accepted.status, OfferStatus.ACCEPTED)
        self.assertFalse(self.mgr.has_pending_offer())

    def test_reject_offer(self):
        e = self._make_entity()
        self.mgr.create_single_offer(e, OfferTrigger.TRAILER_RELEASED, "test")
        rejected = self.mgr.reject_active_offer()
        self.assertEqual(rejected.status, OfferStatus.REJECTED)
        self.assertFalse(self.mgr.has_pending_offer())

    def test_parse_yes(self):
        e = self._make_entity()
        self.mgr.create_single_offer(e, OfferTrigger.TRAILER_RELEASED, "test")
        result = self.mgr.parse_response("yes")
        self.assertTrue(result)

    def test_parse_no(self):
        e = self._make_entity()
        self.mgr.create_single_offer(e, OfferTrigger.TRAILER_RELEASED, "test")
        result = self.mgr.parse_response("no")
        self.assertFalse(result)

    def test_parse_none_on_irrelevant(self):
        e = self._make_entity()
        self.mgr.create_single_offer(e, OfferTrigger.TRAILER_RELEASED, "test")
        result = self.mgr.parse_response("what time is it")
        self.assertIsNone(result)

    def test_parse_yep(self):
        e = self._make_entity()
        self.mgr.create_single_offer(e, OfferTrigger.TRAILER_RELEASED, "test")
        self.assertTrue(self.mgr.parse_response("yep sure"))

    def test_multi_offer(self):
        candidates = [
            self._make_entity("Fantastic Four Trailer"),
            self._make_entity("Ironheart Teaser"),
            self._make_entity("Thunderbolts Clip"),
        ]
        offer = self.mgr.create_multi_offer(candidates, OfferTrigger.TRAILER_RELEASED,
                                            "Found new Marvel content:")
        display = offer.to_display()
        self.assertIn("Fantastic Four", display)
        self.assertIn("Ironheart", display)

    def test_multi_offer_accept_second(self):
        candidates = [
            self._make_entity("A"),
            self._make_entity("B"),
        ]
        self.mgr.create_multi_offer(candidates, OfferTrigger.TRAILER_RELEASED, "Found:")
        self.mgr.parse_response("play the second one")
        # active offer should be gone
        self.assertFalse(self.mgr.has_pending_offer())

    def test_get_accepted_entity_single(self):
        e = self._make_entity("Spider-Man")
        self.mgr.create_single_offer(e, OfferTrigger.TRAILER_RELEASED, "test")
        offer = self.mgr.accept_active_offer()
        entity = self.mgr.get_accepted_entity(offer)
        self.assertEqual(entity.name, "Spider-Man")

    def test_get_accepted_entity_multi(self):
        candidates = [self._make_entity("A"), self._make_entity("B")]
        self.mgr.create_multi_offer(candidates, OfferTrigger.TRAILER_RELEASED, "Found:")
        offer = self.mgr.accept_active_offer(candidate_index=1)
        entity = self.mgr.get_accepted_entity(offer)
        self.assertEqual(entity.name, "B")

    def test_expire_stale(self):
        e = self._make_entity()
        offer = self.mgr.create_single_offer(e, OfferTrigger.TRAILER_RELEASED, "test", ttl=-1)
        expired = self.mgr.expire_stale()
        self.assertEqual(expired, 1)
        self.assertEqual(offer.status, OfferStatus.EXPIRED)

    def test_no_active_offer_returns_none(self):
        self.assertIsNone(self.mgr.accept_active_offer())
        self.assertIsNone(self.mgr.reject_active_offer())

    def test_display_single_offer(self):
        e = self._make_entity()
        offer = self.mgr.create_single_offer(e, OfferTrigger.TRAILER_RELEASED,
                                             "Spider-Man Brand New Day trailer released today.")
        display = offer.to_display()
        self.assertIn("Would you like me to play it?", display)

    def test_trailer_factory(self):
        e = self._make_entity()
        offer = MediaOfferManager.build_trailer_offer("Spider-Man", e, self.mgr)
        self.assertEqual(offer.trigger, OfferTrigger.TRAILER_RELEASED)
        self.assertIn("Spider-Man", offer.description)

    def test_highlights_factory(self):
        e = self._make_entity("Messi Highlights", EntityType.SPORTS_PLAYER)
        offer = MediaOfferManager.build_highlights_offer("Messi", e, self.mgr)
        self.assertEqual(offer.trigger, OfferTrigger.HIGHLIGHTS_AVAILABLE)

    def test_clear_all(self):
        e = self._make_entity()
        self.mgr.create_single_offer(e, OfferTrigger.TRAILER_RELEASED, "test")
        self.mgr.clear_all()
        self.assertFalse(self.mgr.has_pending_offer())


if __name__ == "__main__":
    unittest.main()
