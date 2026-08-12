import logging
import re
from typing import Optional, List, Tuple
from mini_kio.knowledge.knowledge_models import SearchSource, MultiSourceResult

from mini_kio.knowledge.wikipedia_provider import fetch_summary
from mini_kio.knowledge import exa_provider
from mini_kio.knowledge import tavily_provider
from mini_kio.knowledge import duckduckgo_provider
from mini_kio.knowledge import jina_reader_provider

logger = logging.getLogger(__name__)

_TOPIC_PROVIDER_ORDER: dict[str, list[str]] = {
    "MOVIES": ["Wikipedia", "Exa", "Tavily", "DuckDuckGo"],
    "TV": ["Wikipedia", "Exa", "Tavily", "DuckDuckGo"],
    "SPORTS": ["Exa", "Tavily", "Wikipedia", "DuckDuckGo"],
    "GAMING": ["Wikipedia", "Exa", "Tavily", "DuckDuckGo"],
    "MUSIC": ["Wikipedia", "Exa", "Tavily", "DuckDuckGo"],
    "TECH": ["Wikipedia", "Exa", "Tavily", "DuckDuckGo"],
    "BOOKS": ["Wikipedia", "Exa", "Tavily", "DuckDuckGo"],
}

_PROVIDER_CONFIDENCE: dict[str, float] = {
    "Exa": 0.95,
    "Tavily": 0.90,
    "DuckDuckGo": 0.75,
    "Wikipedia": 0.85,
}

_PROVIDER_DISPATCH: dict[str, object] = {
    "Exa": exa_provider.search,
    "Tavily": tavily_provider.search,
    "DuckDuckGo": duckduckgo_provider.search,
    "Wikipedia": lambda q: fetch_summary(q),
    "Jina": lambda q: jina_reader_provider.read_url(q) if q.startswith(("http://", "https://")) else None,
}

_KNOWLEDGE_PATTERNS = [
    re.compile(r"^\s*what\s+is\s+.+", re.IGNORECASE),
    re.compile(r"^\s*what\s+are\s+.+", re.IGNORECASE),
    re.compile(r"^\s*what\s+do\s+.+", re.IGNORECASE),
    re.compile(r"^\s*what\s+does\s+.+", re.IGNORECASE),
    re.compile(r"^\s*who\s+is\s+.+", re.IGNORECASE),
    re.compile(r"^\s*who\s+created\s+.+", re.IGNORECASE),
    re.compile(r"^\s*who\s+wrote\s+.+", re.IGNORECASE),
    re.compile(r"^\s*who\s+made\s+.+", re.IGNORECASE),
    re.compile(r"^\s*explain\s+.+", re.IGNORECASE),
    re.compile(r"^\s*tell\s+me\s+about\s+.+", re.IGNORECASE),
    re.compile(r"^\s*define\s+.+", re.IGNORECASE),
    re.compile(r"^\s*how\s+does\s+.+\s+work\s*\??\s*$", re.IGNORECASE),
]

_NON_KNOWLEDGE_PATTERNS = [
    re.compile(r"^\s*what\s+is\s+the\s+weather\b", re.IGNORECASE),
    re.compile(r"^\s*what\s+is\s+the\s+temperature\b", re.IGNORECASE),
    re.compile(r"^\s*what\s+is\s+the\s+time\b", re.IGNORECASE),
    re.compile(r"^\s*what\s+is\s+the\s+date\b", re.IGNORECASE),
]


def _metadata_to_text(metadata: dict, domain: str) -> str:
    """Convert media metadata dict to formatted text for AnswerComposer."""
    parts = []
    if domain == "MOVIE":
        parts.append(f"Title: {metadata.get('Title', '')}")
        parts.append(f"Year: {metadata.get('Year', '')}")
        parts.append(f"Rated: {metadata.get('Rated', '')}")
        parts.append(f"Released: {metadata.get('Released', '')}")
        parts.append(f"Runtime: {metadata.get('Runtime', '')}")
        parts.append(f"Genre: {metadata.get('Genre', '')}")
        parts.append(f"Director: {metadata.get('Director', '')}")
        parts.append(f"Writers: {metadata.get('Writer', '')}")
        parts.append(f"Actors: {metadata.get('Actors', '')}")
        parts.append(f"Plot: {metadata.get('Plot', '')}")
        parts.append(f"Language: {metadata.get('Language', '')}")
        parts.append(f"Country: {metadata.get('Country', '')}")
        parts.append(f"Awards: {metadata.get('Awards', '')}")
        parts.append(f"IMDB Rating: {metadata.get('imdbRating', '')}")
        parts.append(f"IMDB Votes: {metadata.get('imdbVotes', '')}")
        parts.append(f"Metascore: {metadata.get('Metascore', '')}")
        parts.append(f"Box Office: {metadata.get('BoxOffice', '')}")
        parts.append(f"Production: {metadata.get('Production', '')}")
    elif domain == "TV":
        parts.append(f"Name: {metadata.get('name', '')}")
        parts.append(f"Type: {metadata.get('type', '')}")
        parts.append(f"Language: {metadata.get('language', '')}")
        parts.append(f"Status: {metadata.get('status', '')}")
        parts.append(f"Runtime: {metadata.get('runtime', '')} minutes")
        parts.append(f"Premiered: {metadata.get('premiered', '')}")
        if metadata.get('ended'):
            parts.append(f"Ended: {metadata.get('ended', '')}")
        parts.append(f"Genres: {', '.join(metadata.get('genres', []))}")
        parts.append(f"Network: {metadata.get('network', {}).get('name', '')}")
        parts.append(f"Summary: {metadata.get('summary', '').replace('<p>', '').replace('</p>', '')}")
        parts.append(f"Rating: {metadata.get('rating', {}).get('average', '')}")
        parts.append(f"Seasons: {metadata.get('season', '')}")
        parts.append(f"Episodes: {metadata.get('episodes', '')}")
    elif domain == "ANIME":
        data = metadata.get("data", metadata)
        parts.append(f"Title: {data.get('title', '')}")
        parts.append(f"Title (Japanese): {data.get('title_japanese', '')}")
        parts.append(f"Type: {data.get('type', '')}")
        parts.append(f"Episodes: {data.get('episodes', '')}")
        parts.append(f"Status: {data.get('status', '')}")
        parts.append(f"Aired: {data.get('aired', {}).get('string', '')}")
        parts.append(f"Genres: {', '.join(g.get('name', '') for g in data.get('genres', []))}")
        parts.append(f"Score: {data.get('score', '')}")
        parts.append(f"Synopsis: {data.get('synopsis', '')}")
        parts.append(f"Studio: {', '.join(s.get('name', '') for s in data.get('studios', []))}")
    elif domain == "MUSIC":
        parts.append(f"Title: {metadata.get('title', '')}")
        parts.append(f"Artist: {metadata.get('artist-credit', [{}])[0].get('artist', {}).get('name', '')}")
        parts.append(f"Length: {metadata.get('length', '')} ms")
        parts.append(f"Video: {metadata.get('video', '')}")
    elif domain == "SPORTS":
        if "teams" in metadata:
            teams = metadata.get("teams", [])
            if teams:
                team = teams[0]
                parts.append(f"Team: {team.get('strTeam', '')}")
                parts.append(f"League: {team.get('strLeague', '')}")
                parts.append(f"Country: {team.get('strCountry', '')}")
                parts.append(f"Stadium: {team.get('strStadium', '')}")
                parts.append(f"Description: {team.get('strDescriptionEN', '')}")
                parts.append(f"Badge: {team.get('strBadge', '')}")
    return "\n".join(parts)


class KnowledgeRouter:
    def is_knowledge_query(self, query: str) -> bool:
        text = (query or "").strip()
        if not text:
            return False
        if any(pattern.search(text) for pattern in _NON_KNOWLEDGE_PATTERNS):
            return False
        return any(pattern.search(text) for pattern in _KNOWLEDGE_PATTERNS)

    def _is_freshness_query(self, query: str) -> bool:
        """Determines if the query requires fresh information and should bypass memory."""
        freshness_keywords = [
            "latest", "recent", "today", "this week", "news", "update", "updates", 
            "what changed", "what happened", "any news", "any update",
            "developments", "current"
        ]
        text = (query or "").lower().strip()
        # Direct check or pattern match
        if any(keyword in text for keyword in freshness_keywords):
            return True
        # Check for specific news patterns (added update singular)
        if re.search(r"\b(news|update|updates|latest|recent)\b", text):
            return True
        return False

    def route(self, query: str) -> Optional[str]:
        # Freshness Check
        if self._is_freshness_query(query):
            logger.info("[FRESHNESS_BYPASS] query='%s'", query)
            logger.info("[MEMORY_SKIPPED] freshness required")
            # Force fresh retrieval
            multi_res = self.route_freshness(query)
            if multi_res and multi_res.sources:
                logger.info("[RETRIEVAL_RESULT] collected from %d sources", len(multi_res.sources))
                # Return the best content (concatenated or first)
                return "\n\n".join([s.content for s in multi_res.sources])

        # Tier 0: Media Intelligence Domain
        from mini_kio.knowledge.media_knowledge_router import MediaKnowledgeRouter
        media_router = MediaKnowledgeRouter()
        if media_router.is_media_query(query):
            metadata, domain = media_router.route(query)
            if metadata:
                from mini_kio.media.intelligence.answer_composer import AnswerComposer
                from mini_kio.media.intelligence.media_intelligence_models import TopicType
                
                # Convert domain string to TopicType
                domain_map = {
                    "MOVIE": TopicType.MOVIES,
                    "TV": TopicType.TV,
                    "ANIME": TopicType.MOVIES, # Anime often maps to Movies/TV in composer
                    "MUSIC": TopicType.MUSIC,
                    "SPORTS": TopicType.SPORTS,
                    "GAMING": TopicType.GAMING,
                }
                topic = domain_map.get(domain, TopicType.UNKNOWN)
                
                composer = AnswerComposer()
                # Use metadata as raw text for the composer if it's not already a string
                raw_metadata = str(metadata)
                subject = metadata.get("Title") or metadata.get("name") or metadata.get("strTeam") or query
                
                logger.info("[MEDIA_ROUTING] Domain match: %s", domain)
                composed_res = composer.compose(raw_metadata, query, topic, subject)
                
                # Sync offers with Media Intelligence context for follow-up resolution
                try:
                    from mini_kio.media.media_manager import MediaManager
                    mm = MediaManager.get_instance()
                    if mm._intelligence_adapter:
                        offers_data = composer.get_last_offers()
                        if offers_data and offers_data.get("offers"):
                            mm._intelligence_adapter.context.put("last_offers", offers_data, topic=topic, source="knowledge_router")
                            # Also register the subject as the last media entity for context isolation fix
                            from mini_kio.media.intelligence.media_entity_memory import ResolvedEntity, EntityType, MediaProvider
                            
                            # Map topic to EntityType
                            e_map = {
                                TopicType.MOVIES: EntityType.MOVIE,
                                TopicType.TV: EntityType.TV_SHOW,
                                TopicType.MUSIC: EntityType.SONG,
                                TopicType.SPORTS: EntityType.SPORTS_TEAM,
                                TopicType.GAMING: EntityType.GAME,
                            }
                            etype = e_map.get(topic, EntityType.UNKNOWN)
                            
                            entity = ResolvedEntity(
                                name=subject,
                                entity_type=etype,
                                provider=MediaProvider.UNKNOWN,
                                metadata={"domain": domain}
                            )
                            mm._intelligence_adapter._mem.set_last_entity(entity)
                            logger.info("[MEDIA_CONTEXT_SYNC] subject=%s topic=%s", subject, domain)
                except Exception as e:
                    logger.warning("[MEDIA_CONTEXT_SYNC_FAILED] %s", e)

                return composed_res

        if not self.is_knowledge_query(query):
            return None

        # Tier 1: External Search Providers
        # Try DuckDuckGo
        result = duckduckgo_provider.search(query)
        if result:
            logger.info("[RETRIEVAL_SOURCE] duckduckgo (query=%s)", query)
            return result

        # Tier 3: Wikipedia (Deterministic Topic extraction fallback)
        # We try Wikipedia on the full query first, then on extracted topic
        result = fetch_summary(query)
        if result:
            logger.info("[RETRIEVAL_SOURCE] wikipedia (query=%s)", query)
            return result
            
        from mini_kio.llm.conversation_context import ConversationContext
        effective_topic = ConversationContext._extract_topic(query)
        if effective_topic and effective_topic.lower() != query.lower():
            result = fetch_summary(effective_topic)
            if result:
                logger.info("[RETRIEVAL_SOURCE] wikipedia (extracted topic: %s)", effective_topic)
                return result

    def route_freshness(self, query: str) -> Optional[MultiSourceResult]:
        """Route a freshness-required query, bypassing is_knowledge_query().

        Attempts to collect results from all enabled search providers.
        Returns a MultiSourceResult for consensus analysis.
        """
        if not query or not query.strip():
            return None

        text = query.strip()
        sources: List[SearchSource] = []

        # Collect results from providers for consensus
        
        # DuckDuckGo
        res = duckduckgo_provider.search(text)
        if res:
            logger.debug("knowledge_router: collected from duckduckgo for '%s'", text)
            sources.append(SearchSource(name="DuckDuckGo", url=None, content=res))

        if not sources:
            logger.debug("knowledge_router: no freshness results for '%s'", query)
            return None

        return MultiSourceResult(query=query, sources=sources)

    def route_for_topic(self, query: str, topic: Optional[str] = None, mode: str = "") -> Tuple[Optional[MultiSourceResult], Optional[str]]:
        """Topic-aware retrieval using preferred provider ordering.

        Tries MediaKnowledgeRouter first for media entities (OMDb, TVMaze, Jikan, MusicBrainz, SportsDB),
        then web search providers in topic-specific priority order.
        Supports sports mode-based ordering (STANDINGS / FIXTURES / RESULTS / HIGHLIGHTS).
        Returns (MultiSourceResult, provider_name) from the first provider
        that returns data, or falls through to Wikipedia.
        """
        if not query or not query.strip():
            return None, None

        text = query.strip()

        # Tier 0: Media Intelligence Domain (OMDb, TVMaze, Jikan, MusicBrainz, SportsDB)
        try:
            from mini_kio.knowledge.media_knowledge_router import MediaKnowledgeRouter
            media_router = MediaKnowledgeRouter()
            if media_router.is_media_query(text):
                metadata, domain = media_router.route(text)
                if metadata:
                    provider_map = {
                        "MOVIE": "OMDb", "TV": "TVMaze", "ANIME": "Jikan",
                        "MUSIC": "MusicBrainz", "SPORTS": "SportsDB",
                    }
                    provider = provider_map.get(domain, domain)
                    logger.info("[MEDIA_ROUTING] domain=%s provider=%s query=%s", domain, provider, text)
                    logger.info("[MEDIA_PROVIDER] provider=%s query=%s", provider, text)
                    raw = _metadata_to_text(metadata, domain)
                    result = MultiSourceResult(
                        query=query,
                        sources=[SearchSource(name=provider, url=None, content=raw)],
                    )
                    return result, provider
        except Exception as e:
            logger.debug("[MEDIA_ROUTING_ERROR] %s", e)

        # Mode-aware provider ordering for sports
            _sports_mode_order: dict[str, list[str]] = {
                "STANDINGS": ["Exa", "Tavily", "Wikipedia", "DuckDuckGo"],
                "FIXTURES": ["Exa", "Tavily", "Wikipedia", "DuckDuckGo"],
                "RESULTS": ["Exa", "Tavily", "Wikipedia", "DuckDuckGo"],
                "HIGHLIGHTS": ["Exa", "Tavily", "Wikipedia", "DuckDuckGo"],
                "GENERAL": ["Exa", "Tavily", "Wikipedia", "DuckDuckGo"],
            }
            # Same fallback guarantee as the general path: Wikipedia is the
            # evergreen safety net when the configured web providers fail.
            order = _sports_mode_order.get(mode, ["DuckDuckGo", "Wikipedia"])
            logger.info("[SPORTS_SOURCE_USED] mode=%s provider_order=%s", mode, order)
        else:
            # General fallback: DuckDuckGo then Wikipedia, so a DDG failure
            # (e.g. provider/network issue) still yields grounded material
            # instead of returning nothing. Wikipedia is the evergreen source.
            order = _TOPIC_PROVIDER_ORDER.get(topic, ["DuckDuckGo", "Wikipedia"])

        for name in order:
            fn = _PROVIDER_DISPATCH.get(name)
            if not fn:
                continue
            try:
                logger.info("[RETRIEVAL_PROVIDER] trying=%s topic=%s query=%s", name, topic, text)
                # For SPORTS, use DuckDuckGo with timelimit="m" (past month)
                # to bias toward fresh results since Tavily/Exa may be
                # unavailable (no API keys configured).
                if name == "DuckDuckGo" and topic == "SPORTS":
                    res = duckduckgo_provider.search(text, timelimit="m")
                else:
                    res = fn(text)
                # Wikipedia often needs a distilled topic: the raw query may
                # be long/comparative ("KTU 2024 scheme vs KTU 2019 scheme")
                # and fail topic search. Retry with the extracted topic so
                # the evergreen fallback actually yields material.
                if not res and name == "Wikipedia":
                    try:
                        from mini_kio.llm.conversation_context import ConversationContext
                        topic_hint = ConversationContext._extract_topic(text)
                        if topic_hint and topic_hint.lower() != text.lower():
                            res = fetch_summary(topic_hint)
                    except Exception:
                        pass
                if res:
                    logger.info("[RETRIEVAL_SOURCE] provider=%s topic=%s query=%s",
                                name.lower(), topic, text)
                    result = MultiSourceResult(
                        query=query,
                        sources=[SearchSource(name=name, url=None, content=res)],
                    )
                    return result, name
            except Exception:
                logger.debug("[KNOWLEDGE_ROUTER] provider=%s failed for query=%s", name, text, exc_info=True)
                continue

        logger.debug("[KNOWLEDGE_ROUTER] all providers failed for query=%s topic=%s", query, topic)
        return None, None
