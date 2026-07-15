import logging
from typing import Optional, Tuple
from mini_kio.knowledge.knowledge_models import MultiSourceResult

logger = logging.getLogger(__name__)

from mini_kio.knowledge.media_providers import (
    fetch_movie_metadata, fetch_tv_metadata, fetch_anime_metadata, 
    fetch_music_metadata, fetch_sports_metadata
)

class MediaKnowledgeRouter:
    """Unified routing layer for all media-related queries."""

    def is_media_query(self, query: str) -> bool:
        """Temporarily disabled (GA Recovery Pass). Media metadata providers
        (OMDb, TVMaze, Jikan, MusicBrainz, SportsDB) were contaminating retrieval
        quality. Re-enable by restoring the keyword-based heuristic body."""
        return False

    def route(self, query: str) -> Tuple[Optional[dict], str]:
        """Routes media queries to appropriate providers based on content type."""
        # Determine domain
        query_lower = query.lower()
        domain = "GENERAL"
        metadata = {}

        # Priority mapping for specific known entities or keywords
        if any(kw in query_lower for kw in ["movie", "film", "interstellar", "oppenheimer", "whiplash", "the batman", "gladiator", "spider-man", "prestige", "arrival", "blade runner", "dune", "mission impossible", "avatar", "mad max", "john wick", "martian", "ford v ferrari", "top gun"]):
            domain = "MOVIE"
            metadata = fetch_movie_metadata(query)
        elif any(kw in query_lower for kw in ["tv", "series", "episode", "the bear", "young sheldon", "arcane", "succession", "the last of us", "severance", "andor", "house of the dragon", "wednesday", "peacemaker", "invincible", "reacher", "silo"]):
            domain = "TV"
            metadata = fetch_tv_metadata(query)
        elif any(kw in query_lower for kw in ["anime", "frieren", "blue lock", "one piece", "naruto", "solo leveling", "attack on titan", "jujutsu kaisen", "chainsaw man", "kaiju", "dandadan", "vinland saga", "spy x family"]):
            domain = "ANIME"
            metadata = fetch_anime_metadata(query)
        elif any(kw in query_lower for kw in ["music", "song", "album", "artist", "believer", "coldplay", "the weeknd", "starboy", "blinding lights", "imagine dragons", "linkin park", "taylor swift", "billie eilish", "kendrick lamar"]):
            domain = "MUSIC"
            metadata = fetch_music_metadata(query)
        elif any(kw in query_lower for kw in ["sport", "football", "soccer", "nba", "f1", "fifa", "oscar piastri", "lamine yamal", "lewis hamilton", "max verstappen", "jude bellingham", "real madrid", "barcelona", "manchester city", "champions league", "formula 1"]):
            domain = "SPORTS"
            metadata = fetch_sports_metadata(query)
        elif any(kw in query_lower for kw in ["mrbeast", "pewdiepie", "mark rober", "youtuber", "creator", "mkbhd", "veritasium", "kurzgesagt", "linus tech tips", "ali abdaal"]):
            domain = "CREATOR"
            metadata = {} # Handled via YouTube directly
        elif any(kw in query_lower for kw in ["cyberpunk", "gta 6", "witcher 4", "elden ring", "black myth", "ghost of yotei", "death stranding", "hades"]):
            domain = "GAMING"
            metadata = {}
        elif any(kw in query_lower for kw in ["book", "novel", "author", "harry potter", "dune", "atomic habits", "hunger games", "twilight", "percy jackson", "song of ice and fire", "lord of the rings", "the hobbit", "think and grow rich", "deep work", "the alchemist", "sapiens"]):
            domain = "BOOKS"
            metadata = {}  # Books handled via web search (DuckDuckGo/Wikipedia)
        
        logger.info("[MEDIA_ROUTING] query=%s domain=%s provider=%s", 
                    query, domain, "OMDb" if domain == "MOVIE" else "TVMaze" if domain == "TV" else "Jikan" if domain == "ANIME" else "MusicBrainz" if domain == "MUSIC" else "SportsDB" if domain == "SPORTS" else "DuckDuckGo" if domain == "BOOKS" else "None")
        
        return metadata, domain

    def get_artifact_offers(self, entity_type: str, state: str) -> list[str]:
        """Returns artifact offers based on entity type and state."""
        
        _OFFER_TEMPLATES = {
            "MOVIE": {
                "RELEASED": ["Best Scenes", "Behind The Scenes", "Cast Interviews", "Ending Explained", "Bloopers", "Documentary"],
                "UPCOMING": ["Trailer", "Teaser", "Production Update", "Cast Interview"],
                "DEFAULT": ["Trailer", "Cast Interview", "Production Update"]
            },
            "TV": {
                "ONGOING": ["Best Moments", "Cast Interview", "Recap", "Season Breakdown"],
                "ENDED": ["Best Moments", "Cast Interview", "Full Series Breakdown", "Bloopers"],
                "DEFAULT": ["Best Moments", "Cast Interview", "Recap"]
            },
            "SPORTS": {
                "LIVE": ["Live Updates", "Press Conference", "Tactical Analysis"],
                "COMPLETED": ["Highlights", "Goal Compilation", "Press Conference", "Tactical Analysis"],
                "DEFAULT": ["Highlights", "Press Conference", "Analysis"]
            },
            "MUSIC": {
                "DEFAULT": ["Official Video", "Live Performance", "Acoustic Version", "Lyrics Video"]
            },
            "CREATOR": {
                "DEFAULT": ["Latest Upload", "Most Viewed Video", "Recent Interview", "Documentary"]
            },
            "ANIME": {
                "DEFAULT": ["Opening Theme", "Ending Theme", "Trailer", "Best Moments", "Review"]
            },
            "BOOKS": {
                "DEFAULT": ["Audiobook", "Author Interview", "Book Review", "Adaptation Trailer", "Reading", "Summary"]
            }
        }

        domain_templates = _OFFER_TEMPLATES.get(entity_type, {})
        offers = domain_templates.get(state, domain_templates.get("DEFAULT", []))
            
        return offers
