from __future__ import annotations

import time
from dataclasses import dataclass, field
from typing import Optional

from mini_kio.media.media_session import MediaCandidate


@dataclass
class MediaContext:
    current_song: str = ""
    current_artist: str = ""
    current_album: str = ""
    current_video: str = ""
    current_trailer: str = ""
    current_tutorial: str = ""
    current_topic: str = ""
    current_playlist: str = ""
    current_podcast: str = ""
    current_audiobook: str = ""
    last_query: str = ""
    last_provider: str = ""
    last_media_type: str = ""
    last_candidates: list[MediaCandidate] = field(default_factory=list)
    last_selected_candidate: Optional[MediaCandidate] = None

    def set_current(self, candidate: MediaCandidate):
        self.last_selected_candidate = candidate
        mt = candidate.media_type
        if mt in ("music", "music_video"):
            self.current_song = candidate.title
            if candidate.artist:
                self.current_artist = candidate.artist
        elif mt in ("movie_trailer", "tv_trailer"):
            self.current_trailer = candidate.title
        elif mt == "tutorial":
            self.current_tutorial = candidate.title
        elif mt == "educational":
            self.current_tutorial = candidate.title
            self.current_topic = candidate.title
        elif mt == "podcast":
            self.current_podcast = candidate.title
        elif mt == "audiobook":
            self.current_audiobook = candidate.title
        else:
            self.current_video = candidate.title
        self.last_provider = candidate.provider
        self.last_media_type = mt

    def resolve_reference(self, text: str) -> Optional[str]:
        tl = text.lower().strip()
        if tl in ("it", "this", "that"):
            if self.last_selected_candidate:
                return self.last_selected_candidate.title
            if self.current_song:
                return self.current_song
            if self.current_video:
                return self.current_video
            if self.current_trailer:
                return self.current_trailer
            if self.current_tutorial:
                return self.current_tutorial
            return None

        if tl in ("another one", "another song", "play another"):
            if self.current_song:
                return f"more like {self.current_song}"
            if self.current_artist:
                return f"more by {self.current_artist}"
            return None

        if tl in ("more like this", "similar", "similar music"):
            if self.current_song:
                return f"similar to {self.current_song}"
            if self.current_artist:
                return f"similar to {self.current_artist}"
            return None

        if tl.startswith("another song by ") or tl.startswith("another by "):
            artist = tl.replace("another song by ", "").replace("another by ", "").strip()
            if artist:
                if artist in ("him", "her", "them", "it", "that guy", "that girl", "that band"):
                    if self.current_artist:
                        return f"{self.current_artist} songs"
                    return None
                return f"{artist} songs"
            if self.current_artist:
                return f"{self.current_artist} songs"
            return None

        for prefix in ("play ", "watch ", "show "):
            if tl.startswith(prefix):
                rest = tl[len(prefix):].strip()
                resolved = self.resolve_reference(rest)
                if resolved != rest:
                    return resolved

        return text

    def get_provider_for_reference(self) -> str:
        return self.last_provider

    def get_media_type_for_reference(self) -> str:
        return self.last_media_type

    def get_topic(self) -> str:
        if self.current_topic:
            return self.current_topic
        if self.current_song:
            return self.current_song
        if self.current_video:
            return self.current_video
        if self.current_trailer:
            return self.current_trailer
        return ""

    def to_dict(self) -> dict:
        return {
            "current_song": self.current_song,
            "current_artist": self.current_artist,
            "current_album": self.current_album,
            "current_video": self.current_video,
            "current_trailer": self.current_trailer,
            "current_tutorial": self.current_tutorial,
            "current_topic": self.current_topic,
            "current_playlist": self.current_playlist,
            "last_query": self.last_query,
            "last_provider": self.last_provider,
            "last_media_type": self.last_media_type,
        }
