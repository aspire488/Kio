from __future__ import annotations

import logging
import random
from typing import Optional

from mini_kio.media.media_session import MediaCandidate
from mini_kio.media.media_context import MediaContext
from mini_kio.media.media_state import MediaType

logger = logging.getLogger(__name__)

_ARTIST_SONGS: dict[str, list[str]] = {}

_TOPIC_RELATIONS: dict[str, list[str]] = {}


class MediaRecommender:
    def __init__(self):
        self._artist_cache: dict[str, list[str]] = {}
        self._similar_cache: dict[str, list[str]] = {}

    def recommend_another(self, context: MediaContext) -> Optional[dict]:
        if context.current_artist:
            return {
                "query": f"{context.current_artist} songs",
                "reason": f"Another song by {context.current_artist}",
                "artist": context.current_artist,
            }
        if context.current_song:
            return {
                "query": f"music similar to {context.current_song}",
                "reason": "Similar music",
                "artist": "",
            }
        return None

    def recommend_more_like_this(self, context: MediaContext) -> Optional[dict]:
        if context.current_song:
            return {
                "query": f"songs like {context.current_song}",
                "reason": "More like this",
                "artist": "",
            }
        if context.current_artist:
            return {
                "query": f"{context.current_artist} similar artists",
                "reason": f"Similar to {context.current_artist}",
                "artist": "",
            }
        if context.current_trailer:
            return {
                "query": f"{context.current_trailer} related videos",
                "reason": "Related content",
                "artist": "",
            }
        return None

    def recommend_by_artist(self, artist: str) -> dict:
        return {
            "query": f"{artist} songs",
            "reason": f"More by {artist}",
            "artist": artist,
        }

    def recommend_trailer(self, topic: str) -> dict:
        return {
            "query": f"{topic} trailer",
            "reason": f"Trailer for {topic}",
            "artist": "",
        }

    def recommend_tutorial(self, topic: str) -> dict:
        return {
            "query": f"{topic} tutorial",
            "reason": f"Tutorial about {topic}",
            "artist": "",
        }
