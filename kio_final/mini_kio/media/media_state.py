from __future__ import annotations

from enum import Enum
from typing import Optional


class MediaState(str, Enum):
    IDLE = "idle"
    PLAYING = "playing"
    PAUSED = "paused"
    STOPPED = "stopped"
    LOADING = "loading"
    ERROR = "error"

    def can_transition_to(self, target: MediaState) -> bool:
        transitions = {
            MediaState.IDLE: {MediaState.LOADING, MediaState.PLAYING, MediaState.ERROR},
            MediaState.LOADING: {MediaState.PLAYING, MediaState.PAUSED, MediaState.STOPPED, MediaState.ERROR},
            MediaState.PLAYING: {MediaState.PAUSED, MediaState.STOPPED, MediaState.IDLE, MediaState.ERROR},
            MediaState.PAUSED: {MediaState.PLAYING, MediaState.STOPPED, MediaState.IDLE, MediaState.ERROR},
            MediaState.STOPPED: {MediaState.PLAYING, MediaState.LOADING, MediaState.IDLE},
            MediaState.ERROR: {MediaState.IDLE, MediaState.LOADING},
        }
        return target in transitions.get(self, set())


class MediaType(str, Enum):
    MUSIC = "music"
    MUSIC_VIDEO = "music_video"
    MOVIE_TRAILER = "movie_trailer"
    TV_TRAILER = "tv_trailer"
    PODCAST = "podcast"
    AUDIOBOOK = "audiobook"
    INTERVIEW = "interview"
    EDUCATIONAL = "educational"
    TUTORIAL = "tutorial"
    LIVESTREAM = "livestream"
    SPORTS = "sports"
    NEWS = "news"
    BROWSER_MEDIA = "browser_media"
    LOCAL_MEDIA = "local_media"
    UNKNOWN = "unknown"


class PlayerType(str, Enum):
    YOUTUBE = "youtube"
    YOUTUBE_MUSIC = "youtube_music"
    SPOTIFY = "spotify"
    SPOTIFY_WEB = "spotify_web"
    BROWSER = "browser"
    VLC = "vlc"
    LOCAL = "local"
    NETFLIX = "netflix"
    PRIME_VIDEO = "prime_video"
    DISNEY = "disney"
    JELLYFIN = "jellyfin"
    PLEX = "plex"
    APPLE_MUSIC = "apple_music"
    UNKNOWN = "unknown"
