import logging
import requests
from mini_kio.core import config

logger = logging.getLogger(__name__)

def fetch_movie_metadata(title: str) -> dict:
    """Fetch movie/TV show metadata from OMDb."""
    api_key = getattr(config, "OMDB_API_KEY", "4771560")
    url = f"http://www.omdbapi.com/?t={title}&apikey={api_key}"
    
    try:
        logger.info("[MEDIA_PROVIDER] provider=OMDb query='%s'", title)
        resp = requests.get(url, timeout=5)
        data = resp.json()
        if data.get("Response") == "True":
            return data
    except Exception as e:
        logger.error("[MEDIA_PROVIDER_ERROR] provider=OMDb error=%s", e)
    return {}

def fetch_tv_metadata(title: str) -> dict:
    """Fetch TV show metadata from TVMaze."""
    url = f"https://api.tvmaze.com/singlesearch/shows?q={title}"
    
    try:
        logger.info("[MEDIA_PROVIDER] provider=TVMaze query='%s'", title)
        resp = requests.get(url, timeout=5)
        if resp.status_code == 200:
            return resp.json()
    except Exception as e:
        logger.error("[MEDIA_PROVIDER_ERROR] provider=TVMaze error=%s", e)
    return {}

def fetch_anime_metadata(title: str) -> dict:
    """Fetch anime metadata from Jikan (MyAnimeList)."""
    url = f"https://api.jikan.moe/v4/anime?q={title}&limit=1"
    
    try:
        logger.info("[MEDIA_PROVIDER] provider=Jikan query='%s'", title)
        resp = requests.get(url, timeout=5)
        if resp.status_code == 200:
            data = resp.json()
            if data.get("data"):
                return data["data"][0]
    except Exception as e:
        logger.error("[MEDIA_PROVIDER_ERROR] provider=Jikan error=%s", e)
    return {}

def fetch_music_metadata(query: str) -> dict:
    """Fetch music metadata from MusicBrainz."""
    # Simplified MusicBrainz search
    url = f"https://musicbrainz.org/ws/2/recording/?query={query}&fmt=json"
    headers = {"User-Agent": "KIO/1.0 ( joelj@example.com )"}
    
    try:
        logger.info("[MEDIA_PROVIDER] provider=MusicBrainz query='%s'", query)
        resp = requests.get(url, headers=headers, timeout=5)
        if resp.status_code == 200:
            data = resp.json()
            if data.get("recordings"):
                return data["recordings"][0]
    except Exception as e:
        logger.error("[MEDIA_PROVIDER_ERROR] provider=MusicBrainz error=%s", e)
    return {}

def fetch_sports_metadata(query: str) -> dict:
    """Fetch sports metadata from SportsDB."""
    api_key = getattr(config, "SPORTSDB_API_KEY", "3")
    url = f"https://www.thesportsdb.com/api/v1/json/{api_key}/searchteams.php?t={query}"
    
    try:
        logger.info("[MEDIA_PROVIDER] provider=SportsDB query='%s'", query)
        resp = requests.get(url, timeout=5)
        if resp.status_code == 200:
            return resp.json()
    except Exception as e:
        logger.error("[MEDIA_PROVIDER_ERROR] provider=SportsDB error=%s", e)
    return {}
