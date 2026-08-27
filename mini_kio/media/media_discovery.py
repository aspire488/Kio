from __future__ import annotations

import logging
import time
from typing import Optional

from mini_kio.media.media_session import MediaCandidate
from mini_kio.media.media_state import MediaType

logger = logging.getLogger(__name__)

_TOPIC_PATTERNS = {
    MediaType.MOVIE_TRAILER: ["trailer", "movie", "film", "cinema", "new movie"],
    MediaType.TV_TRAILER: ["series", "show", "tv", "episode", "season"],
    MediaType.TUTORIAL: ["tutorial", "how to", "guide", "walkthrough", "learn"],
    MediaType.EDUCATIONAL: ["explain", "what is", "how does", "why is", "science", "history"],
    MediaType.MUSIC: ["song", "music", "album", "artist", "singer", "band"],
    MediaType.PODCAST: ["podcast", "episode", "talk show"],
    MediaType.LIVESTREAM: ["live", "stream", "gameplay", "playing"],
    MediaType.SPORTS: ["highlights", "match", "game", "sports", "nfl", "nba", "soccer"],
    MediaType.NEWS: ["news", "update", "announcement", "launch", "release", "keynote"],
}

_OPPORTUNITY_KEYWORDS = [
    # Media-SEEKING intent only. Bare "what is"/"explain" are general
    # knowledge questions — offering a video after every one would make KIO
    # a search bot (live over-eagerness: "what is the capital of France"
    # triggered an educational-video offer). The opportunity model must
    # fire only when the user is actually LOOKING for media/current
    # material, not after every topic answer.
    "what's new", "how to", "tutorial", "documentary", "watch", "listen",
    "latest", "new", "upcoming", "trailer", "review", "unveiled",
    "announced", "released", "keynote", "presentation", "demo", "clip",
    "clips", "highlights", "trailers", "teaser", "teasers",
]

_MEDIA_OFFER_TEMPLATES: dict[str, str] = {
    # Natural KIO-voiced, restrained offers — an OPTION the user can take,
    # never an automatic dump. Wording mirrors how KIO speaks in
    # conversation ("if you want"/"want me to"), not a search-engine prompt.
    MediaType.MOVIE_TRAILER: "There's an official trailer if you want to see what it actually looks like — want me to pull it up?",
    MediaType.TV_TRAILER: "There's a trailer for it if you'd like a look — want me to play it?",
    MediaType.TUTORIAL: "There's a visual walkthrough that explains this well, if you'd rather watch than read.",
    MediaType.EDUCATIONAL: "There's a solid video explainer on this if you'd like me to play it.",
    MediaType.MUSIC: "There's music along these lines if you want to hear something fitting.",
    MediaType.PODCAST: "There's a podcast that digs into this, if you'd rather listen.",
    MediaType.LIVESTREAM: "There's a live stream covering this right now, if you want to check it out.",
    MediaType.SPORTS: "There are highlights of it if you want to see the actual moment.",
    MediaType.NEWS: "There's a news segment about this if you'd like the fuller picture.",
}


class MediaDiscovery:
    def __init__(self):
        self._candidates: dict[str, list[MediaCandidate]] = {}
        self._last_offer: Optional[dict] = None
        self._last_offer_time: float = 0.0
        self._offer_ttl_s: int = 300

    def detect_opportunity(self, query: str) -> Optional[dict]:
        ql = query.lower()
        matched_types: list[MediaType] = []

        for mt, keywords in _TOPIC_PATTERNS.items():
            if any(kw in ql for kw in keywords):
                matched_types.append(mt)

        is_opportunity = any(kw in ql for kw in _OPPORTUNITY_KEYWORDS)

        if not is_opportunity and not matched_types:
            return None

        if matched_types and is_opportunity:
            primary = matched_types[0]
            template = _MEDIA_OFFER_TEMPLATES.get(primary, "I found related content. Want me to play it?")
            return {"media_type": primary.value, "offer": template, "topic": query}

        return None

    def store_candidates(self, key: str, candidates: list[MediaCandidate]):
        self._candidates[key] = candidates

    def get_candidates(self, key: str) -> list[MediaCandidate]:
        return self._candidates.get(key, [])

    def set_last_offer(self, offer: dict):
        self._last_offer = offer
        self._last_offer_time = time.time()

    def get_last_offer(self) -> Optional[dict]:
        if self._last_offer is None:
            return None
        if time.time() - self._last_offer_time > self._offer_ttl_s:
            self._last_offer = None
            return None
        return self._last_offer

    def clear_last_offer(self):
        self._last_offer = None
