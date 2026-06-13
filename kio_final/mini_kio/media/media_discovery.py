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
    "what's new", "what is", "tell me about", "explain", "how to",
    "latest", "new", "upcoming", "trailer", "review", "unveiled",
    "announced", "released", "keynote", "presentation", "demo",
]

_MEDIA_OFFER_TEMPLATES: dict[str, str] = {
    MediaType.MOVIE_TRAILER: "I found the official trailer. Would you like me to play it?",
    MediaType.TV_TRAILER: "I found the trailer. Want me to play it?",
    MediaType.TUTORIAL: "I found a visual tutorial that explains this well. Want to watch it?",
    MediaType.EDUCATIONAL: "I found educational content about this topic. Want me to play it?",
    MediaType.MUSIC: "I found music related to this. Want me to play it?",
    MediaType.PODCAST: "I found a podcast discussing this. Want to listen?",
    MediaType.LIVESTREAM: "There's a live stream about this. Want to watch?",
    MediaType.SPORTS: "I found highlights. Want to watch?",
    MediaType.NEWS: "I found a news segment about this. Want me to play it?",
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
