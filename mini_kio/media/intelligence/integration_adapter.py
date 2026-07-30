from __future__ import annotations
import re
from typing import Optional, Callable, Any
from mini_kio.media.intelligence.media_intelligence_models import TopicType, ArtifactType, EventRecord, ArtifactRecord, IntelligenceResult
from mini_kio.intelligence.retrieval_router import RetrievalResult
from mini_kio.media.intelligence.topic_classifier import classify_topic
from mini_kio.media.intelligence.artifact_memory import ArtifactMemory, parse_artifact_type, default_artifact_for_topic
from mini_kio.media.intelligence.context_store import ContextStore
from mini_kio.media.intelligence.continuity_engine import ContinuityEngine, ResolutionResult
from mini_kio.media.intelligence.sports_intelligence import build_sports_response, detect_sports_mode, detect_competition, extract_events
from mini_kio.media.intelligence.answer_composer import _is_current_info_query
from mini_kio.media.intelligence.media_entity_memory import MediaEntityMemory
from mini_kio.media.intelligence.media_preference_model import MediaPreferenceModel
from mini_kio.media.intelligence.media_recommendation_engine import MediaRecommendationEngine
from mini_kio.media.intelligence.media_reference_resolver import MediaReferenceResolver, ReferenceResolution, ReferenceType
from mini_kio.media.intelligence.media_response_formatter import (
    format_media_response, format_artifact_response,
    format_sports_response, format_fallback,
)
from mini_kio.media.intelligence.answer_composer import AnswerComposer
from mini_kio.media.media_intelligence_models import EntityType, ResolvedEntity, MediaProvider


class MediaIntelligenceAdapter:
    """
    Drop-in adapter connecting the new intelligence layer to KIO's existing
    KnowledgeRouter / RetrievalRouter / MediaManager / CommandRouter.

    Usage:
        adapter = MediaIntelligenceAdapter(
            retrieval_fn=knowledge_router.retrieve,
            play_fn=media_manager.play_url,
            pending_action_fn=command_router.get_pending,
        )
        result = adapter.handle(query)
    """

    def __init__(
        self,
        retrieval_fn: Callable[[str, Optional[str], str], Optional[RetrievalResult]],
        play_fn: Optional[Callable[[str], None]] = None,
        pending_action_fn: Optional[Callable[[str], Optional[dict]]] = None,
        max_context_entries: int = 50,
        session_state: Optional["SessionState"] = None,
    ) -> None:
        self.retrieve = retrieval_fn
        self.play = play_fn
        self._ctx = ContextStore(max_context_entries)
        self._art = ArtifactMemory()
        self._mem = MediaEntityMemory()
        self._prefs = MediaPreferenceModel(self._mem)
        
        # Gate 5: unified session state — all subsystems read/write this
        self._session_state = session_state
        
        # Forward session_state to ContinuityResolver so it has authoritative entity/domain
        if session_state:
            from mini_kio.core.continuity_resolver import ContinuityResolver
            ContinuityResolver.set_session_state(session_state)
            # Bootstrap MediaEntityMemory from SessionState
            if session_state.active_entity:
                from mini_kio.media.media_intelligence_models import ResolvedEntity
                from mini_kio.media.intelligence.media_intelligence_models import TopicType
                _DOMAIN_TO_TOPIC = {
                    "media": TopicType.MOVIES,
                    "research": TopicType.TECH,
                    "conversation": TopicType.UNKNOWN,
                    "unknown": TopicType.UNKNOWN,
                }
                dom = TopicType.UNKNOWN
                if session_state.active_domain:
                    dom = _DOMAIN_TO_TOPIC.get(session_state.active_domain, TopicType.UNKNOWN)
                et = self._topic_to_entity_type(dom)
                self._mem.set_last_entity(ResolvedEntity(
                    name=session_state.active_entity,
                    entity_type=et,
                    metadata={"topic": dom.value},
                ))
        
        # We need a MediaContext wrapper for ReferenceResolver as it expects it
        from mini_kio.media.media_context import MediaContext
        self._media_context = MediaContext() 
        self._resolver = MediaReferenceResolver(self._media_context)
        
        self._recommender = MediaRecommendationEngine(self._mem, self._resolver, self._prefs)
        
        self._continuity = ContinuityEngine(
            context=self._ctx,
            artifact_memory=self._art,
            pending_action_resolver=pending_action_fn,
        )

        self._llm_fn: Optional[Callable[[str], Optional[str]]] = None
        self._composer = AnswerComposer(llm_fn=None)

        # Track last answer-person for pronoun resolution (who-directed questions)
        self._answer_person: str = ""

    def set_session_state(self, state: "SessionState") -> None:
        """Wire (or re-wire) unified SessionState after construction.
        
        Called from runtime once the SessionState (owned by ConversationResponder)
        is available.  Bootstraps entity memory, wires ContinuityResolver, and
        enables all SessionState writes from _register_entity, _handle_acceptance, etc.
        """
        self._session_state = state
        from mini_kio.core.continuity_resolver import ContinuityResolver
        ContinuityResolver.set_session_state(state)
        # Bootstrap entity memory from persisted state ONLY if empty
        if state.active_entity and not self._mem.get_last_entity():
            from mini_kio.media.media_intelligence_models import ResolvedEntity
            from mini_kio.media.intelligence.media_intelligence_models import TopicType
            # Map stored DomainContinuationType-compatible value back to TopicType
            _DOMAIN_TO_TOPIC = {
                "media": TopicType.MOVIES,
                "research": TopicType.TECH,
                "conversation": TopicType.UNKNOWN,
                "unknown": TopicType.UNKNOWN,
            }
            dom = TopicType.UNKNOWN
            if state.active_domain:
                dom = _DOMAIN_TO_TOPIC.get(state.active_domain, TopicType.UNKNOWN)
            et = self._topic_to_entity_type(dom)
            self._mem.set_last_entity(ResolvedEntity(
                name=state.active_entity,
                entity_type=et,
                metadata={"topic": dom.value},
            ))

    # ── memory helpers ──────────────────────────────────────────────────────────

    _PRONOUN_QUERIES = {
        "it", "that", "this", "they", "them", "him", "he", "she",
        "the song", "the movie", "the show", "the artist",
        "the album", "the video", "the trailer", "the game",
        "the team", "the match", "the player", "that one",
    }

    _INFO_PATTERNS = (
        "who", "what", "when", "where", "why", "how",
        "tell me about", "tell us about",
    )

    _ENTITY_TO_TOPIC: dict[EntityType, TopicType] = {
        EntityType.MOVIE: TopicType.MOVIES,
        EntityType.TV_SHOW: TopicType.TV,
        EntityType.ACTOR: TopicType.MOVIES,
        EntityType.MUSIC_ARTIST: TopicType.MUSIC,
        EntityType.SONG: TopicType.MUSIC,
        EntityType.ALBUM: TopicType.MUSIC,
        EntityType.SPORTS_PLAYER: TopicType.SPORTS,
        EntityType.SPORTS_TEAM: TopicType.SPORTS,
        EntityType.GAME: TopicType.GAMING,
        EntityType.YOUTUBER: TopicType.MOVIES,
        EntityType.STREAMER: TopicType.MOVIES,
        EntityType.COMPANY: TopicType.TECH,
        EntityType.BOOK: TopicType.BOOKS,
        EntityType.AUTHOR: TopicType.BOOKS,
    }

    @staticmethod
    def _topic_to_entity_type(topic: TopicType) -> EntityType:
        mapping = {
            TopicType.MOVIES: EntityType.MOVIE,
            TopicType.TV: EntityType.TV_SHOW,
            TopicType.MUSIC: EntityType.SONG,
            TopicType.SPORTS: EntityType.SPORTS_TEAM,
            TopicType.GAMING: EntityType.GAME,
            TopicType.PEOPLE: EntityType.ACTOR,
            TopicType.TECH: EntityType.COMPANY,
            TopicType.NEWS: EntityType.UNKNOWN,
            TopicType.BOOKS: EntityType.BOOK,
        }
        return mapping.get(topic, EntityType.UNKNOWN)

    def _entity_type_to_topic(self, et: EntityType) -> TopicType:
        return self._ENTITY_TO_TOPIC.get(et, TopicType.UNKNOWN)

    @staticmethod
    def _topic_to_continuity_domain(topic: TopicType) -> str:
        """Map TopicType to DomainContinuationType-compatible value.
        
        Media/entertainment domains → "media", tech/news → "research",
        people → "media", others → "conversation" or "unknown".
        """
        _MAP = {
            TopicType.MOVIES: "media",
            TopicType.TV: "media",
            TopicType.MUSIC: "media",
            TopicType.SPORTS: "media",
            TopicType.GAMING: "media",
            TopicType.BOOKS: "media",
            TopicType.PEOPLE: "media",
            TopicType.TECH: "research",
            TopicType.NEWS: "research",
        }
        return _MAP.get(topic, "unknown")

    def _is_continuation_query(self, ql: str) -> bool:
        if ql in self._PRONOUN_QUERIES:
            return True
        words = ql.split()
        if len(words) > 6:
            _fillers_early = {"the", "a", "an", "is", "are", "was", "were", "be", "been",
                              "do", "does", "did", "has", "have", "had", "in", "on", "at",
                              "for", "to", "of", "with", "by", "from", "about", "and", "or",
                              "but", "no", "not", "up", "down", "out", "off", "over",
                              "will", "would", "can", "could", "should", "may", "might",
                              "get", "got", "go", "went", "come", "came", "make", "made"}
            _cont_noise = {"explain", "without", "you", "spoilers", "ending",
                           "tell", "me", "describe", "summarize", "overview",
                           "recap", "synopsis", "plot", "story", "please",
                           "major", "minor", "big", "little", "main", "key",
                           "any", "brief", "quick", "simple", "basic",
                           "summary", "ideas", "concept", "concepts", "theme"}
            remaining = {w.strip("?.!") for w in words
                         if w.strip("?.!") not in _fillers_early
                         and w.strip("?.!") not in _cont_noise}
            if not remaining:
                return True
            return False
        # Bare freshness followups (≤3 words, all freshness words)
        if len(words) <= 3:
            _fresh = {"latest", "updates", "news", "recent", "current", "today", "any",
                      "standings", "results", "highlights", "fixtures", "scores",
                      "group", "table", "leader", "leading", "qualified", "eliminated"}
            if all(w.strip("?.!") in _fresh for w in words):
                return True
        # Do NOT include artifact/content words (updates, news, trailer, etc.)
        # — those belong in ContinuityEngine's followup detection.
        ref_words = {"it", "that", "this", "they", "them", "he", "she", "him", "his", "her", "their",
                     "scored", "score", "goal", "goals", "scoring", "scorer",
                     "who", "what", "where", "when", "why", "how",
                      "show", "play", "any", "there", "more",
                     "filming", "complete", "production", "release", "cast",
                     "episode", "season", "director", "producer", "writer",
                     "canceled", "cancelled", "renewed", "announced", "confirmed",
                     "singer", "song", "band", "artist", "album",
                     "standings", "results", "highlights", "fixtures", "scores",
                     "group", "table", "leader", "leading", "qualified", "eliminated",
                     "composer", "composed", "composition", "soundtrack",
                     "trailer", "gameplay", "clips", "ending",
                     "review", "rating", "ratings", "chapter"}
        query_words = {w.strip("?.!") for w in words}

        # Pronouns always trigger continuation — they need entity resolution from memory
        pronouns = {"it", "this", "they", "them", "he", "she", "him", "his", "her", "their"}
        if query_words & pronouns:
            return True
        # "that" as pronoun: exclude conjunction usage ("remember that I...")
        if "that" in query_words:
            import re
            if not re.search(r"\bthat\b\s+(?:i|you|he|she|it|we|they|my|your|his|her|its|our|their)\b", ql, re.I):
                return True

        # Interrogatives (who/what/where/when/why/how) — only continuation if query
        # lacks explicit entity content (e.g. "who directed interstellar" is FRESH,
        # not a continuation of the previous entity).
        interrogatives = {"who", "what", "where", "when", "why", "how"}
        if interrogatives & query_words:
            last_e = self._mem.get_last_entity()
            if last_e and last_e.name and last_e.name.lower() in ql:
                return True
            # Non-entity filler/structure words — subtracting these prevents false
            # "fresh query" detection for queries like "what was the score".
            _fillers = {"the", "a", "an", "is", "are", "was", "were", "be", "been",
                        "do", "does", "did", "has", "have", "had", "in", "on", "at",
                        "for", "to", "of", "with", "by", "from", "about", "and", "or",
                        "but", "not", "no", "up", "down", "out", "off", "over",
                        "will", "would", "can", "could", "should", "may", "might",
                        "get", "got", "go", "went", "come", "came", "make", "made"}
            non_ref = query_words - interrogatives - ref_words - pronouns - _fillers
            if non_ref and len(words) > 2:
                return False

        # Content-word guard: if query has explicit entity words (not ref/filler/noise),
        # treat as fresh query, not continuation. Prevents "the song Believer by Imagine
        # Dragons" from inheriting a stale entity (e.g. "Can You Give Me The Current Top
        # Scorers As Well?") just because "song" is a ref_word.
        _fillers = {"the", "a", "an", "is", "are", "was", "were", "be", "been",
                    "do", "does", "did", "has", "have", "had", "in", "on", "at",
                    "for", "to", "of", "with", "by", "from", "about", "and", "or",
                    "but", "not", "no", "up", "down", "out", "off", "over",
                    "will", "would", "can", "could", "should", "may", "might",
                    "get", "got", "go", "went", "come", "came", "make", "made"}
        content_words = query_words - ref_words - pronouns - _fillers
        if content_words and len(words) > 2:
            return False
        return bool(ref_words & query_words)

    def _resolve_memory_topic(self, target_topic: TopicType) -> TopicType:
        """Use memory's original topic when the target topic is a poor match."""
        last_e = self._mem.get_last_entity()
        if not last_e:
            return target_topic
        mem_topic = self._entity_type_to_topic(last_e.entity_type)
        # If classifier picked a generic topic (UNKNOWN/TECH/NEWS/GAMING) but memory has a specific one, trust memory
        generic = {TopicType.UNKNOWN, TopicType.TECH, TopicType.NEWS, TopicType.GAMING}
        specific = {TopicType.SPORTS, TopicType.MOVIES, TopicType.TV, TopicType.MUSIC, TopicType.BOOKS}
        if target_topic in generic and mem_topic in specific:
            return mem_topic
        return target_topic

    def _is_url_like(self, text: str) -> bool:
        """Detect if a string looks like a URL or Wikipedia revision URL."""
        lower = text.lower()
        return lower.startswith(("http://", "https://", "www.", "en.wikipedia.org",
                                 "//en.wikipedia.org"))

    def _register_entity(
        self, subject: str, topic: TopicType, result: Optional[RetrievalResult] = None,
        confidence: float = 1.0, raw_response: Optional[str] = None,
    ) -> None:
        import logging
        logger = logging.getLogger(__name__)
        if not subject:
            return
        
        # Reject URL-like entity names — they corrupt memory state
        if self._is_url_like(subject):
            logger.warning("[ENTITY_URL_REJECT] refusing to register URL-as-entity: %s", subject[:80])
            return
        
        if raw_response is None:
            if result:
                raw_response = result.raw_content or result.summary
            else:
                raw_response = ""

        entity = ResolvedEntity(
            name=subject,
            entity_type=self._topic_to_entity_type(topic),
            metadata={"topic": topic.value if hasattr(topic, "value") else str(topic), "confidence": str(confidence)},
            confidence=confidence,
        )
        self._mem.set_last_entity(entity)
        self._media_context.set_last_entity(entity)
        self._ctx.put("last_subject", subject, topic=topic, confidence=confidence, source="handler")
        # Track the entity topic for offer resolution
        self._ctx.put("last_entity_topic", topic.value if hasattr(topic, "value") else str(topic), topic=topic, confidence=confidence, source="handler")
        
        if raw_response:
            # Store in context store for reference
            self._ctx.put("last_raw_response", raw_response, topic=topic)
        if raw_response:
            self._ctx.put("last_raw", raw_response, topic=topic, confidence=confidence, source="retrieval")
            logger.info("[ENTITY_REGISTER] subject=%s topic=%s response_len=%d", subject, topic.value, len(raw_response))
        else:
            logger.info("[ENTITY_REGISTER] subject=%s topic=%s", subject, topic.value)
        # Sync to unified SessionState using DomainContinuationType-compatible value
        if self._session_state:
            _dom_val = self._topic_to_continuity_domain(topic)
            self._session_state.set_entity_and_domain(subject, _dom_val)

    def _try_memory_resolve(self, query: str, topic: TopicType) -> Optional[IntelligenceResult]:
        import logging
        logger = logging.getLogger(__name__)
        ql = query.lower().strip()
        last_e = self._mem.get_last_entity()
        if not last_e:
            logger.info("[MEMORY_MISS] no last entity for query=%s topic=%s", query, topic)
            return None
        if not self._is_continuation_query(ql):
            logger.info("[MEMORY_MISS] query=%s not a continuation of last=%s", query, last_e.name)
            return None

        entity_name = last_e.name
        # Personal pronouns ("him", "he", "she") should resolve to the last
        # answer-person (e.g. "Christopher Nolan" from "Who directed X?"),
        # not the query subject entity (e.g. "Interstellar").
        _personal_pronouns = {"him", "he", "she"}
        q_words = set(ql.split())
        used_answer_person = _personal_pronouns & q_words and bool(self._answer_person)
        resolve_name = self._answer_person if used_answer_person else entity_name
        # Use entity's native topic when classifier picks a generic/wrong one
        mem_topic = self._entity_type_to_topic(last_e.entity_type)
        use_topic = mem_topic if mem_topic in {TopicType.SPORTS, TopicType.MOVIES, TopicType.TV, TopicType.MUSIC, TopicType.BOOKS} else topic
        logger.info("[MEMORY_HIT] last=%s query=%s topic=%s mem_topic=%s", entity_name, query, topic, use_topic)

        # Build targeted retrieval query from entity context + user query intent
        noise = {"it", "that", "this", "they", "them", "he", "she", "him", "his", "her", "their"}
        meaningful = [w for w in ql.split() if w not in noise]
        new_query = f"{resolve_name} {' '.join(meaningful)}" if meaningful else resolve_name
        # Apply retrieval rewriting to optimize the query
        rewritten = self._rewrite_retrieval(query, use_topic, resolve_name)
        if rewritten != query:
            new_query = rewritten
        logger.info("[MEMORY_RESOLVE] entity=%s original=%s new_query=%s", resolve_name, query, new_query)

        # NEW retrieval — memory provides context, retrieval provides facts
        res = self._safe_retrieve(new_query, topic=use_topic.value)
        if not res:
            res = self._safe_retrieve(resolve_name, topic=use_topic.value)

        # Discover artifacts from the retrieved content so that followup artifact
        # queries (e.g. "show trailer", "play highlights") can resolve from memory.
        if res:
            self._discover_artifacts(res, use_topic, entity_name)

        text = self._compose_answer(res, query) if res else ""
        # Always register original entity (not answer_person) to maintain subject continuity
        self._register_entity(entity_name, topic, result=res, confidence=0.85)
        # Sync continuity context with memory entity — keeps the "subject" key
        # in lockstep so _handle_acceptance continuity fallback resolves correctly.
        self._continuity.update_context(query, use_topic, entity_name, confidence=0.85)

        return IntelligenceResult(
            topic=self._entity_type_to_topic(last_e.entity_type),
            response_text=text,
            subject=entity_name,
            confidence=0.85,
            source=f"memory:{entity_name}",
        )

    # ── main entry point ───────────────────────────────────────────────────────

    # ── acceptance handler ──────────────────────────────────────────────────

    # Number-to-offer mapping
    _NUMBER_WORDS = {
        "1": 0, "2": 1, "3": 2, "4": 3, "5": 4, "6": 5,
        "first": 0, "first one": 0, "the first one": 0,
        "second": 1, "second one": 1, "the second one": 1,
        "third": 2, "third one": 2, "the third one": 2,
    }
    _ACCEPT_WORDS = frozenset({"yes", "yeah", "sure", "ok", "okay", "yep", "do it", "show it", "play it", "go ahead", "show them", "pls", "please"})

    _ACCEPT_FOUND_MSG = {
        "trailer": "Got it. Opening the {} trailer.",
        "teaser": "Got it. Opening the {} teaser.",
        "gameplay": "Got it. Opening gameplay footage for {}.",
        "music_video": "Got it. Playing the music video for {}.",
        "audiobook": "Got it. Opening the audiobook for {}.",
        "soundtrack": "Got it. Opening the soundtrack for {}.",
        "interview": "Got it. Opening the interview for {}.",
        "behind_the_scenes": "Got it. Opening behind-the-scenes footage for {}.",
        "highlights": "Got it. Opening highlights for {}.",
        "clips": "Got it. Opening clips from {}.",
        "best_scenes": "Got it. Opening best scenes from {}.",
        "live_performance": "Got it. Playing the live performance for {}.",
        "concert": "Got it. Playing the concert for {}.",
        "lyrics": "Got it. Showing lyrics for {}.",
        "book_review": "Got it. Opening the book review for {}.",
        "book_summary": "Got it. Opening the book summary for {}.",
        "author_interview": "Got it. Opening the author interview for {}.",
        "reading": "Got it. Opening the reading for {}.",
    }
    _ACCEPT_SEARCH_MSG = {
        "trailer": "Finding the {} trailer.",
        "teaser": "Finding the {} teaser.",
        "gameplay": "Searching for {} gameplay footage.",
        "music_video": "Looking up the music video for {}.",
        "audiobook": "Finding the audiobook for {}.",
        "soundtrack": "Looking for the soundtrack of {}.",
        "interview": "Searching for an interview with {}.",
        "behind_the_scenes": "Looking for behind-the-scenes of {}.",
        "highlights": "Finding highlights for {}.",
        "clips": "Looking for clips from {}.",
        "best_scenes": "Finding best scenes from {}.",
        "live_performance": "Looking for a live performance of {}.",
        "concert": "Searching for a {} concert.",
        "lyrics": "Finding lyrics for {}.",
        "book_review": "Looking for reviews of {}.",
        "book_summary": "Finding a summary of {}.",
        "author_interview": "Looking for an interview with {}.",
        "reading": "Finding a reading of {}.",
    }

    def _acceptance_msg(self, entity: str, artifact: ArtifactType, found: bool) -> str:
        key = artifact.value
        if found:
            template = self._ACCEPT_FOUND_MSG.get(key)
            if template:
                return template.format(entity)
            return f"Got it. Opening {entity}."
        template = self._ACCEPT_SEARCH_MSG.get(key)
        if template:
            return template.format(entity)
        return f"Searching for {entity}."

    def _handle_acceptance(self, query: str) -> Optional[IntelligenceResult]:
        """Handle acceptance responses that resolve to a previously-offered artifact.
        
        Only triggers for PURE acceptance phrases:
        - Bare digits: "1", "2", "3" → select offer by number
        - Ordinals: "first one", "the second one" → select offer by index
        - Acceptance: "yes", "yeah", "sure", "ok" → top-ranked offer
        - Action: "show it", "play it", "do it" → default artifact for entity
        
        Does NOT intercept information queries like "Show standings" or "Any teaser available?"
        — those flow through to continuity engine and normal routing.
        """
        q = query.lower().strip()

        # Check for number or ordinal
        for word, index in self._NUMBER_WORDS.items():
            if q == word:
                logger.info("[ARTIFACT_RESOLVE] selection=%s index=%d", word, index)
                return self._resolve_offer_index(index)

        # Handle "play the first one", "show the first one", "play first one" etc.
        # Strip leading action verb + optional article, then re-check ordinals
        ordinal_match = re.match(r"(?:play|show|watch)\s+(?:the\s+)?(.+)", q)
        if ordinal_match:
            stripped = ordinal_match.group(1).strip()
            for word, index in self._NUMBER_WORDS.items():
                if stripped == word:
                    logger.info("[ARTIFACT_RESOLVE] ordinal_stripped=%s selection=%s index=%s", q, word, index)
                    return self._resolve_offer_index(index)

        # F3: Action shortcut keywords — short artifact/resolution tokens
        # e.g. "trailer", "cast", "gameplay", "highlights"
        _SHORTCUT_KEYWORDS = frozenset({
            "trailer", "teaser", "cast", "soundtrack", "gameplay", "highlights",
            "clips", "interview", "behind the scenes", "standings", "fixtures",
            "results", "summary", "author", "lyrics", "similar", "reviews",
            "episodes", "walkthrough", "show", "show me",
        })
        q_normalized = q.rstrip(".,!?;:").strip()
        q_words = q_normalized.split()
        # Only treat as shortcut if query is short (1-3 words) and not a multi-word entity query
        if len(q_words) <= 2:
            q_short = q_normalized
            # Strip leading "show"/"play"/"watch" for matching
            for prefix in ("play ", "show ", "watch ", "open "):
                if q_short.startswith(prefix):
                    q_short = q_short[len(prefix):].strip()
            if q_short in _SHORTCUT_KEYWORDS:
                result = self._resolve_offer_by_name(q_short)
                if result:
                    return result
                # Fallback: treat "trailer" → search for subject trailer
                if q_short != "similar":
                    return self._resolve_artifact_shortcut(q_short)

        # Only match acceptance words as STANDALONE WORDS, not substrings
        # e.g. "ok" should not match inside "book" — use word boundaries
        def _has_acceptance_word(text: str) -> bool:
            for aw in self._ACCEPT_WORDS:
                if " " in aw:
                    parts = [re.escape(w) for w in aw.split()]
                    pattern = r"\b" + r"\s+".join(parts) + r"\b"
                else:
                    pattern = r"\b" + re.escape(aw) + r"\b"
                if re.search(pattern, text):
                    return True
            return False
        if not _has_acceptance_word(q):
            return None

        # "yes/yeah/sure/ok" → resolve to highest-ranked offer (index 0)
        # Normalize trailing punctuation so "Yes." matches "yes"
        q_stripped = q.rstrip(".,!?;:")
        if q_stripped in ("yes", "yeah", "sure", "ok", "okay", "yep"):
            q = q_stripped
        if q in ("yes", "yeah", "sure", "ok", "okay", "yep"):
            result = self._resolve_offer_index(0)
            if result:
                return result
            # No stored offers — fall through to default artifact for entity topic
            # (e.g. "yes" after "play believer" → play music video for believer)

        # "show them" resolution
        if q == "show them":
            was = self._ctx.get("last_offers")
            if was and was.value:
                subject = was.value.get("subject", "")
                logger.info("[ARTIFACT_RESOLVE] entity=%s artifact=multiple selection=all", subject)
                return IntelligenceResult(
                    topic=TopicType(was.value.get("topic", "unknown")),
                    response_text=f"Available for {subject}: " + ", ".join(was.value.get("offers", [])),
                    subject=subject,
                    source="acceptance",
                    confidence=0.9
                )

         # "show it" / "play it" / "do it" → default artifact for entity topic
        last_e = self._mem.get_last_entity()
        # Try entity memory first, then continuity context
        if last_e:
            topic = self._entity_type_to_topic(last_e.entity_type)
            target_artifact = default_artifact_for_topic(topic) if topic else None
        else:
            target_artifact = None
        if not target_artifact:
            # Guard: reject stale continuity context if entity memory has a
            # different topic (cross-group contamination defense).
            last_topic_entry = self._ctx.get("last_entity_topic")
            if last_topic_entry and last_topic_entry.value:
                try:
                    mem_topic = TopicType(last_topic_entry.value)
                    ctx_topic = self._ctx.recent_topic()
                    if ctx_topic and mem_topic != ctx_topic and mem_topic != TopicType.UNKNOWN and ctx_topic != TopicType.UNKNOWN:
                        return None
                except (ValueError, TypeError):
                    pass
            ctx_subject = self._ctx.recent_subject()
            ctx_topic = self._ctx.recent_topic()
            if ctx_subject and ctx_topic:
                target_artifact = default_artifact_for_topic(ctx_topic)
                if target_artifact:
                    logger.info("[ARTIFACT_RESOLVE] entity=%s artifact=%s selection=default(continuity)", ctx_subject, target_artifact.value)
                    record = self._art.resolve_artifact(target_artifact, subject=ctx_subject, topic=ctx_topic)
                    if record:
                        return IntelligenceResult(
                            topic=ctx_topic,
                            response_text=self._acceptance_msg(ctx_subject, target_artifact, True),
                            subject=ctx_subject,
                            source="acceptance",
                            confidence=0.85,
                        )
                    return IntelligenceResult(
                        topic=ctx_topic,
                        response_text=self._acceptance_msg(ctx_subject, target_artifact, False),
                        subject=ctx_subject,
                        source="acceptance",
                        confidence=0.7,
                        followup_options=[f"play {ctx_subject} {target_artifact.value}"],
                    )
            return None
        
        if target_artifact:
            logger.info("[ARTIFACT_RESOLVE] entity=%s artifact=%s selection=default", last_e.name, target_artifact.value)
            record = self._art.resolve_artifact(target_artifact, subject=last_e.name, topic=topic)
            if record:
                return IntelligenceResult(
                    topic=topic,
                    response_text=self._acceptance_msg(last_e.name, target_artifact, True),
                    subject=last_e.name,
                    source="acceptance",
                    confidence=0.85,
                )
            return IntelligenceResult(
                topic=topic,
                response_text=self._acceptance_msg(last_e.name, target_artifact, False),
                subject=last_e.name,
                source="acceptance",
                confidence=0.7,
                followup_options=[f"play {last_e.name} {target_artifact.value}"],
            )
        return None

    def _resolve_offer_index(self, index: int) -> Optional[IntelligenceResult]:
        """Resolve acceptance to the offer at the given index."""
        was = self._ctx.get("last_offers")
        if not was or not was.value or not isinstance(was.value, dict):
            return None
        offers = was.value.get("offers", [])
        if index >= len(offers):
            return None
        subject = was.value.get("subject", "")
        topic_val = was.value.get("topic", "")
        topic = TopicType(topic_val) if topic_val else TopicType.UNKNOWN
        offer_name = offers[index]
        
        # Store for artifact resolution
        artifact_key = self._offer_name_to_key(offer_name)
        self._ctx.put("last_offered", {
            "subject": subject, "artifact_type": artifact_key,
            "offer_name": offer_name,
        }, topic=topic, confidence=1.0, source="acceptance")
        
        # Sync action to unified SessionState
        if self._session_state:
            self._session_state.last_action = artifact_key
            self._session_state.last_action_target = subject
        
        logger.info("[ARTIFACT_RESOLVE] entity=%s artifact=%s selection=%d", subject, offer_name, index + 1)
        
        # Determine if it's an info request or a play request
        play_keywords = {"play", "trailer", "video", "performance", "highlights", "audiobook"}
        is_play = any(k in offer_name.lower() for k in play_keywords)
        
        if is_play and self.play:
            # Check if we already have a URL in artifact memory
            atype = parse_artifact_type(offer_name.lower())
            if atype:
                record = self._art.resolve_artifact(atype, subject=subject, topic=topic)
                if record and record.url:
                    side_effect = self.play(record.url)
                    return IntelligenceResult(
                        topic=topic,
                        response_text=f"Launching {offer_name} for {subject}...",
                        subject=subject,
                        source="acceptance",
                        confidence=1.0,
                        side_effect_result=side_effect
                    )
            
            # If no URL, resolve to a play command that MediaManager will catch
            return IntelligenceResult(
                topic=topic,
                response_text=f"Searching for {subject} {offer_name}...",
                subject=subject,
                source="acceptance",
                confidence=0.9,
                side_effect_result={"action": "play", "query": f"{subject} {offer_name}"}
            )
        
        # Info request — execute retrieval
        res = self._safe_retrieve(f"{subject} {offer_name}", topic=topic.value)
        if not res:
            res = self._safe_retrieve(subject, topic=topic.value)
        
        text = self._compose_answer(res, f"{subject} {offer_name}") if res else f"I couldn't find more details on {offer_name}."
        self._register_entity(subject, topic, result=res)
        
        return IntelligenceResult(
            topic=topic,
            response_text=text,
            subject=subject,
            source="acceptance",
            confidence=0.95
        )


    def _resolve_offer_by_name(self, name: str) -> Optional[IntelligenceResult]:
        """Resolve a shortcut keyword to an offer by name."""
        was = self._ctx.get("last_offers")
        if not was or not was.value or not isinstance(was.value, dict):
            return None
        offers = was.value.get("offers", [])
        subject = was.value.get("subject", "")
        topic_val = was.value.get("topic", "")
        if not offers or not subject:
            return None
        topic = TopicType(topic_val) if topic_val else TopicType.UNKNOWN
        name_lower = name.lower().strip()
        for i, offer in enumerate(offers):
            if name_lower in offer.lower():
                return self._resolve_offer_index(i)
        return None

    def _resolve_artifact_shortcut(self, keyword: str) -> Optional[IntelligenceResult]:
        """Resolve a standalone artifact keyword to a search/trailer action."""
        last_e = self._mem.get_last_entity()
        if not last_e:
            return None
        topic = self._entity_type_to_topic(last_e.entity_type) or TopicType.UNKNOWN
        artifact_types = {
            "trailer": "trailer", "teaser": "teaser", "gameplay": "gameplay",
            "highlights": "highlights", "standings": "standings", "fixtures": "fixtures",
            "cast": "cast", "soundtrack": "soundtrack", "lyrics": "lyrics",
            "walkthrough": "gameplay", "summary": "book_summary",
        }
        # Sync action to unified SessionState
        if self._session_state:
            self._session_state.last_action = keyword.lower()
            self._session_state.last_action_target = last_e.name
        
        art = artifact_types.get(keyword.lower())
        if art:
            atype = parse_artifact_type(art)
            if atype:
                record = self._art.resolve_artifact(atype, subject=last_e.name, topic=topic)
                if record and record.url:
                    return IntelligenceResult(
                        topic=topic, response_text=self._acceptance_msg(last_e.name, atype, True),
                        subject=last_e.name, source="acceptance", confidence=0.85,
                    )
                return IntelligenceResult(
                    topic=topic, response_text=self._acceptance_msg(last_e.name, atype, False),
                    subject=last_e.name, source="acceptance", confidence=0.7,
                    side_effect_result={"action": "play", "query": f"{last_e.name} {art}"},
                )
        # Generic search fallback
        res = self._safe_retrieve(f"{last_e.name} {keyword}", topic=topic.value)
        text = self._compose_answer(res, f"{last_e.name} {keyword}") if res else f"Searching for {keyword}..."
        return IntelligenceResult(
            topic=topic, response_text=text, subject=last_e.name,
            source="acceptance", confidence=0.7,
        )

    @staticmethod
    def _offer_name_to_key(name: str) -> str:
        """Convert display offer name to artifact key."""
        mapping = {
            "Best scenes": "best_scenes", "Trailer": "trailer", "Teaser": "teaser",
            "Behind-the-scenes": "behind_the_scenes", "Behind the scenes": "behind_the_scenes",
            "Cast interviews": "interview", "Director interview": "interview",
            "Ending explained": "ending_explained", "Bloopers": "bloopers",
            "Highlights": "highlights", "Match analysis": "match_analysis",
            "Standings": "standings", "Results": "results", "Fixtures": "fixtures",
            "Press conferences": "press_conference",
            "Goal compilations": "goal_compilation", "Tactical breakdowns": "tactical_breakdown",
            "Official video": "music_video", "Live performance": "live_performance",
            "Acoustic version": "acoustic_version", "Lyrics video": "lyrics_video",
            "Music video": "music_video", "Lyrics": "lyrics_video", "Interviews": "interview",
            "Music videos": "music_video", "Live performances": "live_performance",
            "Concert footage": "concert_footage", "Band interview": "interview",
            "Gameplay": "gameplay", "Developer updates": "developer_update",
            "Reviews": "book_review", "Walkthrough": "gameplay", "Walkthroughs": "gameplay",
            "Clips": "clips", "Recaps": "recap",
            "Production updates": "production_update", "Set footage": "set_footage",
            "News coverage": "results", "Latest videos": "latest_video",
            "Project breakdowns": "project_breakdown",
            "Soundtrack": "soundtrack", "Audiobook": "audiobook",
            "Author interview": "author_interview", "Summary": "book_summary",
            "Adaptation trailer": "adaptation_trailer",
        }
        return mapping.get(name, name.lower().replace(" ", "_"))

    def handle(self, query: str, execute: bool = True) -> IntelligenceResult:
        import logging
        logger = logging.getLogger(__name__)

        # Sync media context with last entity from memory
        last_e = self._mem.get_last_entity()
        if last_e:
            self._media_context.set_last_entity(last_e)

        # 0a. Acceptance handler for yes/ok/sure/show it
        accept_res = self._handle_acceptance(query)
        if accept_res:
            logger.info("[ACCEPTANCE_RESOLVED] query=%s source=%s", query, accept_res.source)
            return accept_res

        # 1. recommendation check
        rec_triggers = ("recommend", "suggest", "similar", "something like", "another one",
                        "watch next", "listen next", "next to watch", "next to listen",
                        "what should i watch", "what should i listen", "what to watch", "what to listen",
                        "similar tracks", "similar songs", "more like this")
        if any(w in query.lower() for w in rec_triggers):
            return self._handle_recommendation(query)

        # 2. check continuity first
        if self._continuity.is_followup(query):
            logger.info("[FOLLOWUP_DETECTED] query=%s", query)
            followup_res = self._handle_followup(query, execute=execute)
            if followup_res.source != "none" and followup_res.confidence > 0:
                logger.info("[QUERY_RESOLVE] original=%s resolved=%s", query, followup_res.subject)
                logger.info("[FOLLOWUP_RESOLVED] source=%s subject=%s", followup_res.source, followup_res.subject)
                return followup_res
            logger.info("[FOLLOWUP_FALLTHROUGH] query=%s", query)

        # 2.5 Bare freshness followup (e.g. "Latest updates" after MrBeast)
        # If query is all freshness words with no entity of its own, force continuation
        _freshness_words = frozenset({"latest", "updates", "news", "recent", "current", "today", "any",
                                     "standings", "results", "highlights", "fixtures", "scores",
                                     "group", "table", "leader", "leading", "qualified", "eliminated"})
        ql = query.lower().strip()
        q_words = ql.split()
        if last_e and len(q_words) <= 3 and all(w.strip("?.!") in _freshness_words for w in q_words):
            topic = classify_topic(query).topic
            logger.info("[BARE_FRESHNESS] query=%s forcing continuation of last=%s topic=%s", query, last_e.name, topic)
            memory_res = self._try_memory_resolve(query, topic)
            if memory_res:
                return memory_res

        # 3. classify
        classification = classify_topic(query)
        topic = classification.topic

        # 3.5 Reference Resolution (as a fallback before generic handling)
        # Handle pronouns, mood, activity, etc. ONLY if not an information query
        if not _is_current_info_query(query) and not ql.startswith(("who", "what", "where", "when", "why", "how")):
            ref_res = self._resolver.resolve(query)
            if ref_res.success:
                logger.info("[REPLAY_RESOLVED] original=%s resolved=%s source=resolver", 
                            query, ref_res.query_override or (ref_res.resolved_entity.name if ref_res.resolved_entity else ""))
                return self._handle_reference_resolution(ref_res, query, execute=execute)

        # 4. route by topic
        if topic == TopicType.SPORTS:
            return self._handle_sports(query, classification.confidence)
        if topic in (TopicType.MOVIES, TopicType.TV):
            return self._handle_media(query, topic, classification.confidence)
        if topic == TopicType.GAMING:
            return self._handle_gaming(query, classification.confidence)
        if topic == TopicType.MUSIC:
            return self._handle_music(query, classification.confidence)
        if topic == TopicType.BOOKS:
            return self._handle_books(query, classification.confidence)
        if topic == TopicType.PEOPLE:
            return self._handle_people(query, classification.confidence)
        # TECH / NEWS / UNKNOWN
        return self._handle_generic(query, topic, classification.confidence)

    # ── reference resolution ───────────────────────────────────────────────────

    def _handle_reference_resolution(self, ref: ReferenceResolution, original_query: str, execute: bool = True) -> IntelligenceResult:
        side_effect_res = None
        from mini_kio.media.media_intelligence_models import EntityType
        
        if ref.resolved_entity:
            entity = ref.resolved_entity
            topic = self._entity_type_to_topic(entity.entity_type)
            # Fall back to topic classifier if resolver couldn't determine entity type
            if topic == TopicType.UNKNOWN and entity.name:
                topic = classify_topic(entity.name).topic
            if self.play and execute:
                play_target = entity.url or entity.name
                if entity.url and not entity.url.startswith(("http://", "https://")):
                    play_target = entity.name
                side_effect_res = self.play(play_target)
                # playback — return resolve confirmation
                self._register_entity(entity.name, topic, confidence=ref.confidence)
                return IntelligenceResult(
                    topic=topic,
                    response_text=f"Resolved: {entity.name}",
                    subject=entity.name,
                    confidence=ref.confidence,
                    source="resolver",
                    side_effect_result=side_effect_res,
                )
                # no playback — retrieve and compose an answer for the resolved entity
            res = self._safe_retrieve(f"{entity.name} {original_query}", topic=topic.value)
            if not res:
                res = self._safe_retrieve(entity.name, topic=topic.value)
            text = self._compose_answer(res, original_query) if res else f"I couldn't find info on {entity.name}."
            self._register_entity(entity.name, topic, result=res, confidence=ref.confidence)
            return IntelligenceResult(
                topic=topic,
                response_text=text,
                subject=entity.name,
                confidence=ref.confidence,
                source=f"resolver:{entity.name}",
                side_effect_result=side_effect_res,
            )
        
        if ref.query_override:
            res = self._safe_retrieve(ref.query_override, topic=TopicType.UNKNOWN.value)
            text = self._compose_answer(res, ref.query_override) if res else ""
            self._register_entity(ref.query_override, TopicType.UNKNOWN, result=res, confidence=ref.confidence)
            return IntelligenceResult(
                topic=TopicType.UNKNOWN,
                response_text=text,
                subject=ref.query_override,
                confidence=ref.confidence,
                source="resolver",
            )
        
        return self._handle_generic(original_query, TopicType.UNKNOWN, 0.0)

    # ── recommendation ─────────────────────────────────────────────────────────

    def _handle_recommendation(self, query: str) -> IntelligenceResult:
        import logging
        logger = logging.getLogger(__name__)

        # Skip memory resolve for recommendations — the recommendation engine already
        # uses the last entity for context. Memory resolve would just append entity name
        # to the query, producing stale entity-focused results instead of fresh recommendations.
        rec_result = self._recommender.recommend(query)
        eff_query = rec_result.request.effective_query()
        
        if eff_query:
            # Clean leading/trailing whitespace from query
            eff_query_clean = eff_query.strip()
            logger.info("[RECOMMENDATION_RESOLVED] query=%s strategy=%s", eff_query_clean, rec_result.strategy_used)
            last_e = self._mem.get_last_entity()
            if last_e and last_e.entity_type in (EntityType.MOVIE, EntityType.TV_SHOW):
                topic = TopicType.MOVIES
            elif last_e and last_e.entity_type in (EntityType.SONG, EntityType.MUSIC_ARTIST):
                topic = TopicType.MUSIC
            elif last_e and last_e.entity_type in (EntityType.BOOK, EntityType.AUTHOR):
                topic = TopicType.BOOKS
            elif last_e and last_e.entity_type in (EntityType.GAME,):
                topic = TopicType.GAMING
            elif last_e and last_e.entity_type in (EntityType.SPORTS_PLAYER, EntityType.SPORTS_TEAM):
                topic = TopicType.SPORTS
            else:
                ql = eff_query_clean.lower()
                if "music" in ql or "song" in ql or "artist" in ql or "album" in ql:
                    topic = TopicType.MUSIC
                elif "book" in ql or "novel" in ql or "author" in ql:
                    topic = TopicType.BOOKS
                elif "game" in ql or "gaming" in ql:
                    topic = TopicType.GAMING
                elif "sport" in ql or "team" in ql or "player" in ql:
                    topic = TopicType.SPORTS
                elif "movie" in ql or "film" in ql or "tv" in ql or "show" in ql:
                    topic = TopicType.MOVIES
                else:
                    topic = TopicType.UNKNOWN
            res = self._safe_retrieve(eff_query_clean, topic=topic.value)
            if not res and last_e:
                res = self._safe_retrieve(last_e.name, topic=topic.value)
            subject_for_answer = eff_query_clean or (last_e.name if last_e else query)
            text = self._compose_answer(res, query) if res else ""
            self._register_entity(subject_for_answer, topic, result=res, confidence=rec_result.confidence)
            self._continuity.update_context(query, topic, subject_for_answer, rec_result.confidence)
            # Store recommendations in unified SessionState
            if self._session_state:
                rec_entry = {
                    "query": query,
                    "effective_query": eff_query_clean,
                    "subject": subject_for_answer,
                    "topic": topic.value,
                    "strategy": str(rec_result.strategy_used) if rec_result.strategy_used else "unknown",
                }
                existing = list(self._session_state.last_recommendations)
                existing.append(rec_entry)
                self._session_state.last_recommendations = existing
            return IntelligenceResult(
                topic=topic,
                response_text=text,
                subject=subject_for_answer,
                confidence=rec_result.confidence,
                source="recommendation",
            )
        
        return self._handle_generic(query, TopicType.UNKNOWN, 0.3)

    # ── followup ───────────────────────────────────────────────────────────────

    def _handle_followup(self, query: str, execute: bool = True) -> IntelligenceResult:
        result = self._continuity.resolve_followup(query)
        side_effect_res = None

        if result.action == "play" and result.artifact_record and self.play:
            topic = result.topic or TopicType.UNKNOWN
            # If artifact has no URL, fall through to search instead of playing nothing
            if result.artifact_record.url:
                if execute:
                    _url = result.artifact_record.url
                    if _url.startswith(("http://", "https://", "www.")):
                        side_effect_res = self.play(_url)
                self._register_entity(result.subject or "", topic, confidence=result.confidence)
                return IntelligenceResult(
                    topic=topic,
                    response_text=format_artifact_response(
                        result.subject or "",
                        result.artifact_type or ArtifactType.TRAILER,
                        result.artifact_record.url,
                        topic,
                    ),
                    subject=result.artifact_record.url or result.subject or "",
                    confidence=result.confidence,
                    source=result.source,
                    side_effect_result=side_effect_res,
                )
            # No URL in artifact — fall through to search path below
            logger.info("[ARTIFACT_NO_URL] type=%s subject=%s falling back to search", 
                        result.artifact_type.value if result.artifact_type else "?", result.subject)

        if result.action == "search" and result.subject:
            topic = result.topic or TopicType.UNKNOWN
            # Apply entity-aware query rewriting so followups use the entity name + intent
            rewritten = self._rewrite_retrieval(query, topic, result.subject)
            # If not explicitly rewritten, prepend subject for context
            if rewritten == query:
                rewritten = f"{result.subject} {query}"
            res = self._safe_retrieve(rewritten, topic=topic.value)
            if not res:
                res = self._safe_retrieve(result.subject, topic=topic.value)
            text = self._compose_answer(res, query) if res else ""
            # Always register entity from followup subject to maintain continuity
            if result.subject and result.confidence > 0.3:
                self._register_entity(result.subject, topic, result=res, confidence=result.confidence)
            return IntelligenceResult(
                topic=topic,
                response_text=text,
                subject=result.subject,
                confidence=result.confidence,
                source=result.source,
            )

        if result.action == "show" and result.event_record:
            e = result.event_record
            subject = e.display()
            artifact_val = result.artifact_type.value if result.artifact_type else "highlights"
            search_q = f"{subject} {artifact_val}"
            res = self._safe_retrieve(search_q, topic=TopicType.SPORTS.value)
            text = self._compose_answer(res, search_q) if res else ""
            self._register_entity(subject, TopicType.SPORTS, result=res, confidence=result.confidence)
            self._ctx.put("last_subject", subject, topic=TopicType.SPORTS, confidence=result.confidence, source="followup")
            return IntelligenceResult(
                topic=TopicType.SPORTS,
                events=[e],
                response_text=text,
                subject=subject,
                confidence=result.confidence,
                source=result.source,
            )

        return IntelligenceResult(
            topic=TopicType.UNKNOWN,
            response_text=format_fallback(query, None),
            confidence=0.0,
            source="none",
        )

    # ── sports ─────────────────────────────────────────────────────────────────

    def _handle_sports(self, query: str, confidence: float) -> IntelligenceResult:
        memory_res = self._try_memory_resolve(query, TopicType.SPORTS)
        if memory_res:
            return memory_res

        competition = detect_competition(query)
        sports_mode = detect_sports_mode(query)
        mode_val = sports_mode.value if sports_mode else ""
        last_e = self._mem.get_last_entity()
        subject = competition or (last_e.name if last_e else None) or query

        # Retrieve fresh data with query rewriting
        rewritten = self._rewrite_retrieval(query, TopicType.SPORTS, subject)
        res = self._safe_retrieve(rewritten, topic=TopicType.SPORTS.value, mode=mode_val)
        if not res:
            res = self._safe_retrieve(query, topic=TopicType.SPORTS.value, mode=mode_val)
        if res:
            self._discover_artifacts(res, TopicType.SPORTS, subject)

        # Extract events for continuity context
        events = extract_events(res.raw_content or res.summary, competition) if res else []
        for event in events:
            self._ctx.add_event(event)

        # store competition and mode context
        if competition:
            self._ctx.put("competition", competition, topic=TopicType.SPORTS)
        if sports_mode:
            self._ctx.put("sports_mode", sports_mode.value, topic=TopicType.SPORTS)

        # Compose structured answer via AnswerComposer
        text = self._compose_answer(res, query) if res else f"I couldn't find sports info on {subject}."

        # Build followup options
        followup_options = ["show standings", "show fixtures", "show analysis"]
        if events:
            top_event = events[0]
            followup_options = [
                f"show {top_event.entity_a} highlights" if top_event.entity_a else "show highlights",
                "show standings", "show fixtures", "show results", "show analysis",
            ]
        # Merge with dynamic artifact-based options
        dynamic = self._build_dynamic_followup(TopicType.SPORTS, subject, followup_options)
        followup_options = dynamic[:6]

        self._register_entity(subject, TopicType.SPORTS, result=res, confidence=confidence)
        self._continuity.update_context(query, TopicType.SPORTS, subject, confidence)

        return IntelligenceResult(
            topic=TopicType.SPORTS,
            sports_mode=sports_mode,
            events=events,
            response_text=text,
            subject=subject,
            confidence=confidence,
            source="retrieval",
            followup_options=followup_options[:4],
        )

    def _extract_answer_person(self, query: str, res: Any) -> str:
        ql = query.lower().strip()
        if not ql.startswith("who "):
            return ""
        _role_verbs = {"directed", "created", "wrote", "composed", "produced",
                       "developed", "designed", "voiced", "played", "plays",
                       "starred", "stars", "sang", "sings", "narrated",
                       "hosted", "hosts", "founded", "invented", "made"}
        if not any(w in ql for w in _role_verbs):
            return ""
        if not res:
            return ""
        raw_text = ""
        if isinstance(res, str):
            raw_text = res
        elif hasattr(res, "raw_content") and res.raw_content:
            raw_text = res.raw_content
        elif hasattr(res, "summary") and res.summary:
            raw_text = res.summary
        elif hasattr(res, "raw_text") and res.raw_text:
            raw_text = res.raw_text
        if not raw_text:
            return ""
        _role_markers = {"directed by", "created by", "written by", "composed by",
                         "produced by", "developed by", "performed by", "starring",
                         "featuring", "played by", "voiced by", "narrated by",
                         "hosted by", "founded by", "invented by", "made by"}
        raw_lower = raw_text.lower()
        for marker in _role_markers:
            idx = raw_lower.find(marker)
            if idx >= 0:
                after = raw_text[idx + len(marker):].strip().strip(".,!?;:")
                name = after.split(",")[0].split("(")[0].split(" (")[0].strip().rstrip(".")
                if name and len(name) > 3 and not any(c in name for c in "0123456789"):
                    return name
        _skip = {"the", "a", "an", "and", "or", "in", "on", "at", "to", "for",
                 "of", "with", "by", "from", "is", "was", "are", "were", "has",
                 "have", "had", "been", "being", "will", "would", "could",
                 "should", "may", "might", "shall", "can", "do", "does", "did",
                 "this", "that", "these", "those", "it", "its", "he", "she",
                 "him", "her", "they", "them", "their", "his", "who", "what",
                 "when", "where", "why", "how", "the", "of"}
        first_150 = raw_text[:200]
        for w in first_150.split():
            wc = w.strip(".,!?;:()'\"")
            if wc and wc[0].isupper() and wc.lower() not in _skip and len(wc) > 3:
                return wc
        return ""

    # ── movies / tv ────────────────────────────────────────────────────────────

    def _handle_media(self, query: str, topic: TopicType, confidence: float) -> IntelligenceResult:
        memory_res = self._try_memory_resolve(query, topic)
        if memory_res:
            return memory_res

        subject = self._extract_subject(query, topic)
        text, res = self._retrieve_and_summarize(query, topic, subject)
        self._register_entity(subject, topic, result=res, confidence=confidence)
        self._continuity.update_context(query, topic, subject, confidence)

        # Track answer person for "who [role] X?" questions so personal pronouns
        # ("him", "he", "she") resolve to the answer person, not the query subject.
        ql = query.lower().strip()
        words = ql.split()
        if words and words[0] == "who":
            _role_verbs = {"directed", "created", "wrote", "composed", "produced",
                           "developed", "designed", "voiced", "played", "plays",
                           "starred", "stars", "sang", "sings", "narrated",
                           "hosted", "hosts", "founded", "invented", "made"}
            if any(w in ql for w in _role_verbs):
                self._answer_person = self._extract_answer_person(query, res)

        return IntelligenceResult(
            topic=topic,
            response_text=text,
            subject=subject,
            confidence=confidence,
            source="retrieval",
            followup_options=self._build_dynamic_followup(topic, subject, ["show trailer", "show teaser", "show interviews"]),
        )

    # ── gaming ─────────────────────────────────────────────────────────────────

    def _handle_gaming(self, query: str, confidence: float) -> IntelligenceResult:
        memory_res = self._try_memory_resolve(query, TopicType.GAMING)
        if memory_res:
            return memory_res

        subject = self._extract_subject(query, TopicType.GAMING)
        text, res = self._retrieve_and_summarize(query, TopicType.GAMING, subject)
        self._register_entity(subject, TopicType.GAMING, result=res, confidence=confidence)
        self._continuity.update_context(query, TopicType.GAMING, subject, confidence)
        return IntelligenceResult(
            topic=TopicType.GAMING,
            response_text=text,
            subject=subject,
            confidence=confidence,
            source="retrieval",
            followup_options=self._build_dynamic_followup(TopicType.GAMING, subject, ["show gameplay", "show the trailer", "show developer update"]),
        )

    # ── music ──────────────────────────────────────────────────────────────────

    def _handle_music(self, query: str, confidence: float) -> IntelligenceResult:
        memory_res = self._try_memory_resolve(query, TopicType.MUSIC)
        if memory_res:
            return memory_res

        subject = self._extract_subject(query, TopicType.MUSIC)
        text, res = self._retrieve_and_summarize(query, TopicType.MUSIC, subject)
        self._register_entity(subject, TopicType.MUSIC, result=res, confidence=confidence)
        self._continuity.update_context(query, TopicType.MUSIC, subject, confidence)
        return IntelligenceResult(
            topic=TopicType.MUSIC,
            response_text=text,
            subject=subject,
            confidence=confidence,
            source="retrieval",
            followup_options=self._build_dynamic_followup(TopicType.MUSIC, subject, ["play music video", "show live performance"]),
        )

    # ── books ──────────────────────────────────────────────────────────────────

    def _handle_books(self, query: str, confidence: float) -> IntelligenceResult:
        memory_res = self._try_memory_resolve(query, TopicType.BOOKS)
        if memory_res:
            return memory_res

        subject = self._extract_subject(query, TopicType.BOOKS)
        if not subject:
            last_e = self._mem.get_last_entity()
            if last_e:
                subject = last_e.name
        text, res = self._retrieve_and_summarize(query, TopicType.BOOKS, subject)
        self._register_entity(subject, TopicType.BOOKS, result=res, confidence=confidence)
        self._continuity.update_context(query, TopicType.BOOKS, subject, confidence)
        return IntelligenceResult(
            topic=TopicType.BOOKS,
            response_text=text,
            subject=subject,
            confidence=confidence,
            source="retrieval",
            followup_options=self._build_dynamic_followup(TopicType.BOOKS, subject, ["show audiobook", "show author interview", "show adaptation trailer", "show book review"]),
        )

    # ── people ─────────────────────────────────────────────────────────────────

    def _handle_people(self, query: str, confidence: float) -> IntelligenceResult:
        memory_res = self._try_memory_resolve(query, TopicType.PEOPLE)
        if memory_res:
            return memory_res
        subject = self._extract_subject(query, TopicType.PEOPLE)
        if not subject:
            last_e = self._mem.get_last_entity()
            if last_e:
                subject = last_e.name
        text, res = self._retrieve_and_summarize(query, TopicType.PEOPLE, subject)
        self._register_entity(subject, TopicType.PEOPLE, result=res, confidence=confidence)
        self._continuity.update_context(query, TopicType.PEOPLE, subject, confidence)
        return IntelligenceResult(
            topic=TopicType.PEOPLE,
            response_text=text,
            subject=subject,
            confidence=confidence,
            source="retrieval",
            followup_options=self._build_dynamic_followup(TopicType.PEOPLE, subject, ["show interview", "show biography", "show related people"]),
        )

    # ── generic ────────────────────────────────────────────────────────────────

    def _handle_generic(self, query: str, topic: TopicType, confidence: float) -> IntelligenceResult:
        memory_res = self._try_memory_resolve(query, topic)
        if memory_res:
            return memory_res

        subject = self._extract_subject(query, topic)
        text, res = self._retrieve_and_summarize(query, topic, subject)
        self._register_entity(subject, topic, result=res, confidence=confidence)
        self._continuity.update_context(query, topic, subject, confidence)
        return IntelligenceResult(
            topic=topic,
            response_text=text,
            subject=subject,
            confidence=confidence,
            source="retrieval",
        )

    # ── artifact discovery ─────────────────────────────────────────────────────

    def _discover_artifacts(self, result: RetrievalResult, topic: TopicType, subject: str) -> None:
        """Scan retrieval result for known artifact mentions and register them."""
        import logging
        import re
        logger = logging.getLogger(__name__)
        if not result or not subject:
            return

        raw = result if isinstance(result, str) else (result.raw_content or result.summary)
        if not raw:
            return
        
        # Topic-specific artifact keyword patterns
        patterns: dict[ArtifactType, list[str]] = {
            ArtifactType.TRAILER: ["trailer", "official trailer", "first look"],
            ArtifactType.TEASER: ["teaser", "teaser trailer", "sneak peek", "teaser trailer"],
            ArtifactType.INTERVIEW: ["interview", "press conference", "qa", "red carpet", "cast interview"],
            ArtifactType.HIGHLIGHTS: ["highlight", "best moments", "top plays", "recap"],
            ArtifactType.STANDINGS: ["standing", "table", "rankings", "points"],
            ArtifactType.FIXTURES: ["fixture", "schedule", "upcoming match", "upcoming game"],
            ArtifactType.RESULTS: ["result", "score", "final score"],
            ArtifactType.MUSIC_VIDEO: ["music video", "official video", "lyric video"],
            ArtifactType.LIVE_PERFORMANCE: ["live performance", "concert", "live session", "live show"],
            ArtifactType.GAMEPLAY: ["gameplay", "walkthrough", "playthrough"],
            ArtifactType.DEVELOPER_UPDATE: ["developer update", "dev diary", "patch notes"],
            ArtifactType.BEST_SCENES: ["best scene", "iconic scene", "epic scene", "fan favorite scene"],
            ArtifactType.BEHIND_THE_SCENES: ["behind the scenes", "behind-the-scenes", "bts", "making of"],
            ArtifactType.ENDING_EXPLAINED: ["ending explained", "ending breakdown", "explained ending"],
            ArtifactType.DOCUMENTARY: ["documentary", "doc", "the story of", "making of documentary"],
            ArtifactType.RECAP: ["recap", "previous episode", "season recap", "story so far"],
            ArtifactType.CLIPS: ["clip", "scene", "exclusive clip"],
            ArtifactType.BLOOPERS: ["blooper", "bloopers", "outtakes", "gag reel"],
            ArtifactType.ANALYSIS: ["analysis", "analyst", "breakdown", "deep dive"],
            ArtifactType.TACTICAL_BREAKDOWN: ["tactical", "formation", "strategy", "tactics"],
            ArtifactType.PRESS_CONFERENCE: ["press conference", "media briefing", "post-match interview"],
            ArtifactType.MATCH_ANALYSIS: ["match analysis", "game analysis", "post-match analysis"],
            ArtifactType.ONBOARD_FOOTAGE: ["onboard", "on-board", "helmet cam", "driver cam"],
            ArtifactType.TEAM_RADIO: ["team radio", "radio message", "pit radio"],
            ArtifactType.ACOUSTIC_VERSION: ["acoustic", "acoustic version", "unplugged", "stripped"],
            ArtifactType.LYRICS_VIDEO: ["lyric video", "lyrics video", "official lyric"],
            ArtifactType.CONCERT_FOOTAGE: ["concert", "live concert", "tour", "live at"],
            ArtifactType.PRODUCTION_UPDATE: ["production update", "production progress", "filming update", "in production"],
            ArtifactType.SET_FOOTAGE: ["set footage", "on set", "behind the camera", "filming set"],
            ArtifactType.EPISODE_PREVIEW: ["episode preview", "next episode", "episode guide", "upcoming episode"],
            ArtifactType.VOICE_ACTOR_INTERVIEW: ["voice actor", "voice cast", "voice over", "voice interview"],
            ArtifactType.LATEST_VIDEO: ["latest video", "new video", "recent video"],
            ArtifactType.PROJECT_BREAKDOWN: ["project breakdown", "cost breakdown", "how it was made"],
            ArtifactType.GOAL_COMPILATION: ["goal", "goals", "goal compilation", "goal highlights"],
            ArtifactType.BEST_MOMENTS: ["best moments", "top moments", "greatest moments", "fan favorite"],
            ArtifactType.AUDIOBOOK: ["audiobook", "audio book", "audio edition", "narrated by"],
            ArtifactType.BOOK_REVIEW: ["review", "rating", "critic review", "reader review", "book review"],
            ArtifactType.BOOK_SUMMARY: ["summary", "overview", "synopsis", "about the book", "blurb"],
            ArtifactType.ADAPTATION_TRAILER: ["adaptation", "film adaptation", "tv adaptation", "movie adaptation", "screen adaptation"],
            ArtifactType.AUTHOR_INTERVIEW: ["author interview", "interview with the author", "qa with", "writer interview"],
            ArtifactType.READING: ["reading", "read by", "excerpt", "sample", "first chapter"],
            ArtifactType.SOUNDTRACK: ["soundtrack", "original score", "background score", "music by", "ost", "composed by"],
            ArtifactType.COMPOSER_INTERVIEW: ["composer interview", "music interview", "interview with the composer"],
        }

        topic_artifacts = {
            TopicType.MOVIES: [ArtifactType.TRAILER, ArtifactType.TEASER, ArtifactType.INTERVIEW,
                               ArtifactType.BEST_SCENES, ArtifactType.BEHIND_THE_SCENES,
                               ArtifactType.ENDING_EXPLAINED, ArtifactType.DOCUMENTARY,
                               ArtifactType.CLIPS, ArtifactType.BLOOPERS,
                               ArtifactType.SOUNDTRACK, ArtifactType.COMPOSER_INTERVIEW],
            TopicType.TV: [ArtifactType.TRAILER, ArtifactType.TEASER, ArtifactType.INTERVIEW,
                           ArtifactType.CLIPS, ArtifactType.RECAP, ArtifactType.BEHIND_THE_SCENES,
                           ArtifactType.BLOOPERS, ArtifactType.EPISODE_PREVIEW,
                           ArtifactType.VOICE_ACTOR_INTERVIEW,
                           ArtifactType.SOUNDTRACK, ArtifactType.COMPOSER_INTERVIEW],
            TopicType.GAMING: [ArtifactType.GAMEPLAY, ArtifactType.TRAILER, ArtifactType.DEVELOPER_UPDATE,
                               ArtifactType.INTERVIEW, ArtifactType.DOCUMENTARY],
            TopicType.SPORTS: [ArtifactType.HIGHLIGHTS, ArtifactType.STANDINGS, ArtifactType.FIXTURES,
                               ArtifactType.RESULTS, ArtifactType.ANALYSIS, ArtifactType.TACTICAL_BREAKDOWN,
                               ArtifactType.PRESS_CONFERENCE, ArtifactType.MATCH_ANALYSIS,
                               ArtifactType.GOAL_COMPILATION, ArtifactType.BEST_MOMENTS],
            TopicType.MUSIC: [ArtifactType.MUSIC_VIDEO, ArtifactType.LIVE_PERFORMANCE, ArtifactType.INTERVIEW,
                              ArtifactType.ACOUSTIC_VERSION, ArtifactType.LYRICS_VIDEO,
                              ArtifactType.CONCERT_FOOTAGE, ArtifactType.DOCUMENTARY],
            TopicType.BOOKS: [ArtifactType.AUDIOBOOK, ArtifactType.BOOK_REVIEW, ArtifactType.BOOK_SUMMARY,
                              ArtifactType.ADAPTATION_TRAILER, ArtifactType.AUTHOR_INTERVIEW,
                              ArtifactType.READING, ArtifactType.INTERVIEW, ArtifactType.DOCUMENTARY],
        }

        relevant = topic_artifacts.get(topic, [])
        raw_lower = raw.lower()

        for atype in relevant:
            keywords = patterns.get(atype, [])
            for kw in keywords:
                if kw in raw_lower:
                    # Extract URL from raw text if available (look for first http/https URL)
                    url = ""
                    url_match = re.search(r'https?://[^\s"\'<>]+', raw)
                    if url_match:
                        url = url_match.group(0)
                    record = ArtifactRecord(
                        artifact_type=atype,
                        topic=topic,
                        subject=subject,
                        url=url,
                        confidence=0.6,
                    )
                    self._art.store_artifact(record)
                    logger.info("[ARTIFACT_REGISTER] type=%s subject=%s topic=%s keyword=%s url=%s",
                                atype.value, subject, topic.value, kw, url or "none")
                    break  # one registration per artifact type per scan

    # ── LLM summarization ──────────────────────────────────────────────────────

    def set_llm_fn(self, fn: Callable[[str], Optional[str]]) -> None:
        self._llm_fn = fn
        self._composer._llm_fn = fn

    def _compose_answer(self, result: RetrievalResult, query: str) -> str:
        """Use AnswerComposer to build a structured, topic-appropriate answer."""
        import logging
        logger = logging.getLogger(__name__)
        
        formatted = self._composer.compose(result, query)
        
        # Store offers for acceptance resolution
        offers_info = self._composer.get_last_offers()
        subject = result.entity or result.title
        topic = result.topic
        
        if offers_info.get("offers"):
            self._ctx.put("last_offers", {
                "subject": subject,
                "topic": topic.value if hasattr(topic, "value") else str(topic),
                "offers": offers_info["offers"],
            }, topic=topic, confidence=1.0, source="answer_composer")
        
        logger.info("[ANSWER_COMPOSED] subject=%s topic=%s source=%s", subject, topic, result.source)
        return formatted

    # ── helpers ────────────────────────────────────────────────────────────────

    def _build_dynamic_followup(self, topic: TopicType, subject: str, static: list[str]) -> list[str]:
        """Build followup options from actual artifact memory, falling back to static suggestions.

        Checks ArtifactMemory for any artifacts registered for this subject+topic
        and prepends matching options to the static list, so the user sees offers
        based on what was actually discovered rather than always seeing the defaults.
        """
        if not subject:
            return static
        dynamic = []
        artifact_order = [
            ("trailer", "show trailer"), ("teaser", "show teaser"),
            ("gameplay", "show gameplay"), ("highlights", "show highlights"),
            ("standings", "show standings"), ("fixtures", "show fixtures"),
            ("results", "show results"), ("music_video", "play music video"),
            ("live_performance", "show live performance"),
            ("interview", "show interview"), ("best_scenes", "show best scenes"),
            ("behind_the_scenes", "show behind the scenes"),
            ("ending_explained", "show ending explained"),
            ("recap", "show recap"), ("clips", "show clips"),
            ("audiobook", "show audiobook"),
            ("book_review", "show book review"),
            ("book_summary", "show book summary"),
            ("adaptation_trailer", "show adaptation trailer"),
            ("author_interview", "show author interview"),
            ("reading", "show reading"),
        ]
        from mini_kio.media.intelligence.media_intelligence_models import ArtifactType
        for art_type_str, display_text in artifact_order:
            try:
                atype = ArtifactType(art_type_str)
            except ValueError:
                continue
            found = self._art.resolve_artifact(atype, subject=subject, topic=topic)
            if found:
                dynamic.append(display_text)
        # De-duplicate while preserving order
        seen = set()
        result = []
        for item in dynamic + static:
            if item not in seen:
                seen.add(item)
                result.append(item)
        return result[:6]  # cap at 6 offers

    # ── contextual info query (called from MediaManager for non-play queries) ──

    def handle_contextual_query(self, query: str) -> Optional[IntelligenceResult]:
        import logging
        logger = logging.getLogger(__name__)
        ql = query.lower().strip()
        last_e = self._mem.get_last_entity()
        if not last_e:
            logger.info("[MEMORY_MISS] handle_contextual_query: no last entity for query=%s", query)
            return None
        if not self._is_continuation_query(ql):
            logger.info("[MEMORY_MISS] handle_contextual_query: not continuation last=%s query=%s", last_e.name, query)
            return None

        entity_name = last_e.name
        topic = self._entity_type_to_topic(last_e.entity_type)
        logger.info("[MEMORY_HIT] handle_contextual_query last=%s query=%s topic=%s", entity_name, query, topic)

        # Build targeted query from entity context + user intent
        noise = {"it", "that", "this", "they", "them", "he", "she", "him", "his", "her", "their"}
        meaningful = [w for w in ql.split() if w not in noise]
        new_query = f"{entity_name} {' '.join(meaningful)}" if meaningful else entity_name
        rewritten = self._rewrite_retrieval(query, topic, entity_name)
        if rewritten != query:
            new_query = rewritten
        logger.info("[MEMORY_RESOLVE] entity=%s original=%s new_query=%s", entity_name, query, new_query)

        # NEW retrieval — never return stale stored text
        res = self._safe_retrieve(new_query, topic=topic.value)
        if not res:
            res = self._safe_retrieve(entity_name, topic=topic.value)

        if res:
            self._discover_artifacts(res, topic, entity_name)

        text = self._compose_answer(res, query) if res else ""
        self._register_entity(entity_name, topic, result=res, confidence=0.85)
        return IntelligenceResult(
            topic=topic,
            response_text=text,
            subject=entity_name,
            confidence=0.85,
            source=f"memory:{entity_name}",
        )

    def get_last_subject(self) -> str:
        last_e = self._mem.get_last_entity()
        return last_e.name if last_e else ""

    # ── helpers ────────────────────────────────────────────────────────────────

    def _safe_retrieve(self, query: str, topic: Optional[str] = None, mode: str = "") -> Optional[RetrievalResult]:
        import logging
        logger = logging.getLogger(__name__)
        logger.info("[RETRIEVAL_PROVIDER] topic=%s query=%s mode=%s", topic or "none", query, mode or "none")
        try:
            res = self.retrieve(query, topic, mode)
            if res:
                raw = res.raw_content or res.summary
                # Quality filter: reject empty/too-short results
                if len(raw) < 50:
                    logger.info("[RETRIEVAL_RESULT] source=%s query=%s len=%d — TOO SHORT, ignoring", res.source, query, len(raw))
                    res = None
                else:
                    logger.info("[RETRIEVAL_RESULT] source=%s query=%s len=%d", res.source, query, len(raw))
            else:
                logger.info("[RETRIEVAL_RESULT] topic=%s query=%s empty", topic or "none", query)
            return res
        except Exception:
            logger.info("[RETRIEVAL_RESULT] exception query=%s", query, exc_info=True)
            return None

    def _rewrite_retrieval(self, query: str, topic: TopicType, subject: str) -> str:
        """Rewrite user query into a retrieval-optimized query."""
        import logging
        logger = logging.getLogger(__name__)
        ql = query.lower().strip()
        original = query
        rewritten = None
        is_current = _is_current_info_query(query)

        # ── Explicit disambiguation for known ambiguous entities ──────────────
        _DISAMBIGUATION = {
            "believer": "Believer Imagine Dragons song",
        }
        if subject and subject.lower() in _DISAMBIGUATION:
            disambiguated = _DISAMBIGUATION[subject.lower()]
            rewritten = disambiguated

        # ── Freshness queries ────────────────────────────────────────────────
        if not rewritten and is_current:
            if topic == TopicType.SPORTS:
                rewritten = f"{subject} latest results standings fixtures scores news 2026"
            elif topic in (TopicType.MOVIES, TopicType.TV):
                rewritten = f"{subject} latest update news 2026"
            elif topic == TopicType.MUSIC:
                rewritten = f"{subject} latest release tour news 2026"
            elif topic == TopicType.GAMING:
                rewritten = f"{subject} latest update patch news 2026"
            elif topic == TopicType.BOOKS:
                rewritten = f"{subject} latest release news 2026"
            else:
                rewritten = f"{subject} latest update news 2026"

        # ── "who" questions ──────────────────────────────────────────────────
        if not rewritten:
            who_m = re.match(r"who\s+(played|plays|directed|directs|sang|sings|composed|composes|scored|scores|wrote|writes|created|creates|voiced|voices|made|produced|published|developed|designed|edited|screenplayed)\s+(.+)$", ql)
            if who_m:
                role = who_m.group(1)
                who_obj = re.sub(r"[?.!]+$", "", who_m.group(2)).strip()
                if role in ("directed", "directs"):
                    rewritten = f"{subject} director"
                elif role in ("played", "plays"):
                    rewritten = f"{subject} cast {who_obj} actor"
                elif role in ("sang", "sings"):
                    rewritten = f"{subject} singer artist"
                elif role in ("composed", "composes", "scored", "scores"):
                    rewritten = f"{subject} composer music"
                elif role in ("made", "produced"):
                    rewritten = f"{subject} producer"
                elif role in ("developed", "designed"):
                    rewritten = f"{subject} developer studio"
                elif role in ("wrote", "writes", "created", "creates", "screenplayed"):
                    if topic == TopicType.BOOKS:
                        rewritten = f"{subject} author"
                    elif topic == TopicType.MUSIC:
                        rewritten = f"{subject} songwriter"
                    elif topic in (TopicType.MOVIES, TopicType.TV):
                        rewritten = f"{subject} creator" if role in ("created", "creates") else f"{subject} writer"
                    else:
                        rewritten = f"{subject} writer creator"
                elif role == "published":
                    rewritten = f"{subject} publisher"
                elif role in ("voiced", "voices"):
                    rewritten = f"{subject} voice actor"
                elif role in ("edited",):
                    rewritten = f"{subject} editor"
                else:
                    rewritten = f"{subject} {role}"
            elif ql.startswith("who "):
                rest = ql[4:].strip()
                if rest:
                    rewritten = f"{subject} {rest}"

        # ── "who is the author/writer/director" pattern ──────────────────────
        if not rewritten:
            who_is_m = re.match(r"who\s+is\s+(the\s+)?(author|writer|creator|director|composer|producer|singer|publisher)\s*(of\s+.+)?$", ql)
            if who_is_m:
                role = who_is_m.group(2)
                if role == "author" or (role in ("writer", "creator") and topic == TopicType.BOOKS):
                    rewritten = f"{subject} author"
                elif role == "publisher":
                    rewritten = f"{subject} publisher"
                elif role == "director":
                    rewritten = f"{subject} director"
                elif role == "composer":
                    rewritten = f"{subject} composer"
                elif role == "producer":
                    rewritten = f"{subject} producer"
                elif role == "singer":
                    rewritten = f"{subject} singer"
                else:
                    rewritten = f"{subject} {role}"

        # ── Role keywords (standalone) ───────────────────────────────────────
        if not rewritten:
            role_keywords = {
                "composer": "composer", "scored": "composer", "music by": "composer",
                "writer": "writer", "written by": "writer", "screenplay": "writer",
                "creator": "creator", "created by": "creator",
                "producer": "producer", "produced by": "producer",
                "director": "director", "directed by": "director",
                "cinematography": "cinematographer", "edited by": "editor",
            }
            for kw, target in role_keywords.items():
                if kw in ql:
                    rewritten = f"{subject} {target}"
                    break

        # ── "how is it performing" / performance questions ───────────────────
        if not rewritten:
            perf_m = re.match(r"how\s+(is|was|are|does)\s+(it|this|the)\s+(performing|doing|playing)", ql)
            if perf_m:
                if topic in (TopicType.MOVIES, TopicType.TV):
                    rewritten = f"{subject} box office ratings reviews performance"
                elif topic == TopicType.SPORTS:
                    rewritten = f"{subject} latest results form performance"
                elif topic == TopicType.MUSIC:
                    rewritten = f"{subject} chart performance streams"
                elif topic == TopicType.GAMING:
                    rewritten = f"{subject} player count reviews performance"

        # ── "when was it released / published" ──────────────────────────────
        if not rewritten:
            when_m = re.search(r"when\s+(was|did|is)\s+(it|this|that|the)\s+(released|published|come\s*out|came\s*out)", ql)
            if when_m:
                if topic == TopicType.BOOKS:
                    rewritten = f"{subject} publication date"
                elif topic in (TopicType.MOVIES, TopicType.TV):
                    rewritten = f"{subject} release date"
                elif topic == TopicType.MUSIC:
                    rewritten = f"{subject} release date"
                elif topic == TopicType.GAMING:
                    rewritten = f"{subject} release date"
                else:
                    rewritten = f"{subject} release date"

        # ── "tell me about" / "tell me more about" ───────────────────────────
        if not rewritten:
            about_m = re.search(r"tell\s+me\s+(more\s+)?about", ql)
            if about_m and subject:
                if topic == TopicType.MUSIC:
                    rewritten = f"{subject} Imagine Dragons song"
                elif topic == TopicType.SPORTS:
                    rewritten = f"{subject} biography career stats news"
                elif topic == TopicType.BOOKS:
                    rewritten = f"{subject} book summary author details"
                else:
                    rewritten = f"{subject} biography history"

        # ── "what happened in X match" (SPORTS-only) ──────────────────────
        if not rewritten and topic == TopicType.SPORTS:
            match_m = re.match(r"what happened\s+(in|at|during)\s+(the\s+)?(.+?)(match|game|race)?$", ql)
            if match_m:
                match_entity = match_m.group(3).strip()
                if match_entity:
                    rewritten = f"{match_entity} latest match goals scorers key events"

        # ── "what happened last X" (SPORTS-only) ───────────────────────────
        if not rewritten and topic == TopicType.SPORTS:
            last_m = re.match(r"what happened\s+(last|this|yesterday('s)?)\s+(.+)", ql)
            if last_m:
                time_ref = last_m.group(1)
                event_context = last_m.group(3).strip()
                rewritten = f"{subject} latest {event_context} results news 2026"

        # ── "show standings/fixtures/highlights/results/analysis" ───────────
        if not rewritten:
            show_m = re.match(r"(?:show|get|find)\s+(standings|fixtures|highlights|results|scores|schedule|table|analysis|recap|clips|bloopers|tactical|best.scenes|behind.the.scenes|ending.explained|goal.compilation)", ql)
            if show_m:
                action = show_m.group(1)
                rewritten = f"{subject} {action}"

        # ── "any X available/updates/news" ──────────────────────────────────
        if not rewritten:
            any_m = re.match(r"any\s+(.+?)\s*(updates?|news|available|released|out yet)?$", ql)
            if any_m:
                request = any_m.group(1).strip()
                if request:
                    rewritten = f"{subject} {request}"

        # ── Single-word entity disambiguation ───────────────────────────────
        if not rewritten and subject and " " not in subject and ql.strip() == subject.lower():
            if topic == TopicType.MUSIC:
                rewritten = f"{subject} song"
            elif topic == TopicType.MOVIES:
                rewritten = f"{subject} movie"
            elif topic == TopicType.TV:
                rewritten = f"{subject} TV show"
            elif topic == TopicType.GAMING:
                rewritten = f"{subject} video game"
            elif topic == TopicType.SPORTS:
                rewritten = f"{subject} sports"
            elif topic == TopicType.BOOKS:
                rewritten = f"{subject} book"

        result = rewritten or query
        if result != query:
            logger.info("[QUERY_REWRITE] original=%s entity=%s rewritten=%s topic=%s", original, subject, result, topic.value)
        return result

    def _retrieve_and_summarize(self, query: str, topic: TopicType, subject: str, mode: str = "") -> tuple[str, Optional[RetrievalResult]]:
        """Retrieve fresh data and compose a structured, topic-appropriate answer."""
        import logging
        logger = logging.getLogger(__name__)
        rewritten = self._rewrite_retrieval(query, topic, subject)
        
        # If rewritten doesn't include the subject, prepend it
        if subject and subject.lower() not in rewritten.lower():
            rewritten = f"{subject} {rewritten}"
        
        res = self._safe_retrieve(rewritten, topic=topic.value, mode=mode)
        
        # Fallback: if first result has empty/insufficient content, retry with original query
        if res:
            raw = res.raw_content or res.summary
            if not raw or len(raw) < 100:
                logger.info("[RETRIEVAL_FALLBACK] rewritten result too short (%d bytes), retrying with original query", len(raw or ""))
                res = self._safe_retrieve(query, topic=topic.value, mode=mode)
        if not res:
            res = self._safe_retrieve(query, topic=topic.value, mode=mode)
        
        if res:
            raw = res.raw_content or res.summary
            if not self._is_relevant(raw, query, subject):
                logger.info("[RELEVANCE_REJECT] query=%s subject=%s len=%d", query, subject, len(raw))
                res = None  # reject irrelevant content
        
        if res:
            self._discover_artifacts(res, topic, subject)
            return self._compose_answer(res, query), res
        
        return f"I don't have information on {subject} yet.", None

    def _is_relevant(self, text: str, query: str, subject: str) -> bool:
        if len(text) < 50:
            return False
        text_lower = text.lower()
        q_words = {w for w in query.lower().split() if len(w) > 2}
        s_words = {w for w in subject.lower().split() if len(w) > 2}
        key_terms = q_words | s_words
        if not key_terms:
            return True
        match_count = sum(1 for t in key_terms if t in text_lower)
        ratio = match_count / len(key_terms)
        return ratio >= 0.3

    def _extract_subject(self, query: str, topic: TopicType) -> str:
        """Best-effort subject extraction from query. Word-boundary-aware.

        For role-based queries (who composed/directed/wrote/created etc.),
        preserves the last entity from memory instead of extracting a garbage
        subject like "Who Composed Soundtrack" from "who composed the soundtrack".
        """
        ql = query.lower().strip()
        # Role queries about the current entity — preserve memory entity name
        _role_words = {"composed", "composer", "soundtrack", "score", "scored",
                       "directed", "director", "wrote", "writer", "created",
                       "creator", "produced", "producer", "developed", "developer",
                       "designed", "designer", "voiced", "voice", "voices",
                       "sang", "sings", "sing",
                       "cast", "actor", "actress", "starred", "stars",
                       "features", "featuring"}
        _first_w = ql.split()[0] if ql.split() else ""
        _interrogatives = {"who", "what", "which"}
        if _first_w in _interrogatives:
            has_role = any(w in ql for w in _role_words)
            if has_role:
                last_e = self._mem.get_last_entity()
                # Prefer explicit entity mentioned in query over stale memory entity.
                # E.g. "Who created The Bear?" should extract "The Bear",
                # not a stale memory entity like "Atomic Habits".
                _query_words = [w.strip(".,!?;:") for w in ql.split()[1:]]
                _has_own_entity = any(w not in _role_words for w in _query_words)
                if _has_own_entity:
                    # Reconstruct entity from original query preserving case.
                    # Filter out role words AND filler words so "Who composed the
                    # soundtrack for Interstellar?" returns "Interstellar", not
                    # "the for Interstellar".
                    _fillers = {"the", "a", "an", "is", "are", "was", "were", "in",
                                "on", "at", "for", "to", "of", "with", "by", "from",
                                "about", "and", "or", "this", "that", "these", "those",
                                "it", "its", "like", "watch", "show", "give", "tell",
                                "i", "me", "my", "we", "you", "your", "he", "she",
                                "they", "them", "their", "can", "could", "would",
                                "will", "shall", "do", "did", "does", "has", "have",
                                "had", "been", "being", "get", "got", "some", "any",
                                "very", "just", "also", "now", "please", "into",
                                "biggest", "compared", "new", "best", "big", "latest"}
                    reconstructed = []
                    for w in query.split()[1:]:
                        w_clean = w.strip(".,!?;:")
                        wl = w_clean.lower()
                        if wl not in _role_words and wl not in _fillers:
                            reconstructed.append(w_clean)
                    if reconstructed:
                        # Check if any reconstructed word was capitalized in the original query
                        # (indicating it IS a proper noun / entity name, not a generic word).
                        orig_words_after_first = query.split()[1:]
                        orig_caps = {w.strip(".,!?;:\"'").lower() 
                                     for w in orig_words_after_first 
                                     if w.strip(".,!?;:\"'") and w.strip(".,!?;:\"'")[0].isupper()}
                        has_proper = any(w.lower() in orig_caps for w in reconstructed)
                        if has_proper:
                            # Casting/character queries about the current memory entity
                            # should preserve the series entity (e.g. "Solo Leveling"),
                            # not register the character name ("Sung Jinwoo").
                            _cast_roles = {"voiced", "voice", "voices", "cast", "actor",
                                           "actress", "starred", "stars", "played", "plays"}
                            if last_e and last_e.name and any(r in ql for r in _cast_roles):
                                return last_e.name
                            # Comparison queries ("compared to GTA V", "vs old version") 
                            # extract the comparison target, not the subject entity.
                            # Prefer memory entity in this case.
                            if last_e and last_e.name and ("compared" in ql or " versus " in ql or " vs " in ql):
                                return last_e.name
                            return " ".join(reconstructed)
                        # All generic words (e.g. "main members") — prefer memory entity
                        if last_e and last_e.name:
                            return last_e.name
                        return query.strip().title()
                    # All words filtered out — use memory entity
                    if last_e and last_e.name:
                        return last_e.name
                # No entity in query — use memory
                if last_e and last_e.name:
                    return last_e.name

        strip_words = [
            "latest", "update", "updates", "news", "about", "on",
            "tell me", "show me", "what about", "any",
            "explain", "story", "plot", "summary", "synopsis",
            "describe", "overview", "recap", "audiobook", "spoilers",
            "currently", "leading",
            "biggest", "new", "compared",
            "first", "second", "third", "one", "two", "three",
        ]
        q = query.lower()
        for w in strip_words:
            if " " in w:
                q = q.replace(w, "")
            else:
                q = re.sub(rf"\b{re.escape(w)}\b", "", q)
        q = re.sub(r"\s+", " ", q).strip()
        if not q:
            last_e = self._mem.get_last_entity()
            if last_e and last_e.name:
                return last_e.name
            return query.strip().title()
        # Garbage detection: if extracted subject looks like a full sentence
        # (question/command structure, or >5 words), fall back to memory entity.
        q_words = q.split()
        garbage_indicators = {"who", "what", "when", "where", "why", "how", "can",
                              "would", "could", "should", "will", "shall", "do",
                              "does", "did", "is", "are", "was", "were", "has",
                              "have", "had", "get", "got", "make", "made", "want",
                              "like", "need", "let", "please", "give", "show",
                              "tell", "watch", "play", "open", "find", "search",
                              "i", "you", "he", "she", "we", "they", "me", "my",
                              "your", "his", "her", "its", "our", "their", "that",
                              "this", "these", "those", "some", "any", "there",
                              "then", "than", "very", "just", "also", "now", "here",
                              "without", "with", "about", "after", "before", "while",
                              "first", "then", "next", "last", "between", "through",
                              "during", "because", "although", "however", "therefore"}
        is_garbage = (
            len(q_words) > 5
            or any(w in garbage_indicators for w in q_words)
            or (len(q_words) == 1 and len(q_words[0]) <= 3)
            # Single short generic word ("the", "one", "a", "an") is never a valid subject
        )
        if is_garbage:
            # Try to extract proper nouns from the original query before falling
            # back to stale memory.  Look for words that are capitalized in the
            # original query and are not generic action/filler words.
            orig_words = query.split()
            _skip = {"play", "show", "watch", "the", "a", "an", "i", "me", "my",
                     "we", "you", "he", "she", "it", "they", "them", "this",
                     "that", "these", "those", "who", "what", "where", "when",
                     "why", "how", "can", "will", "would", "could", "should",
                     "do", "does", "did", "has", "have", "had", "is", "are",
                     "was", "were", "be", "been", "get", "got", "go", "went",
                     "come", "came", "make", "made", "want", "like", "need",
                     "let", "please", "give", "tell", "open", "find", "search",
                     "about", "with", "without", "for", "to", "of", "in", "on",
                     "at", "by", "from", "into", "through", "during", "before",
                     "after", "while", "then", "than", "very", "just", "also",
                     "now", "here", "there", "some", "any", "all", "both",
                     "each", "every", "first", "last", "next", "more", "much",
                     "many", "too", "again", "once", "never", "always",
                     "ending", "explain", "spoilers", "major", "currently"}
            proper = []
            for w in orig_words:
                wc = w.strip(".,!?;:'\"")
                if wc and wc[0].isupper() and wc.lower() not in _skip:
                    proper.append(wc)
            if proper:
                return " ".join(proper)
            # No proper nouns found (query may be lowercased by caller).
            # Filter out stop/artifact words to extract meaningful entity words.
            _artifact_content = {"song", "trailer", "teaser", "gameplay", "highlights",
                                 "interview", "movie", "film", "show", "series", "book",
                                 "novel", "audiobook", "soundtrack", "lyrics", "music",
                                 "video", "live", "performance", "concert", "official",
                                 "latest", "update", "updates", "news", "current",
                                 "recent", "standings", "results", "fixtures", "scores",
                                 "table", "group", "leader", "schedule", "analysis",
                                 "recap", "clips", "blooper", "behind", "scenes",
                                 "ending", "explained", "cast", "episode", "season",
                                 "director", "producer", "writer", "composer",
                                 "footage", "version", "scene", "scenes", "moments",
                                 "match", "game", "race", "event", "status",
                                 "spoilers", "spoiler", "major", "main", "ideas",
                                 "summary", "overview", "synopsis", "recap",
                                 "leading", "biggest", "compared", "features"}
            meaningful = [w.strip(".,!?;:'\"") for w in q_words
                          if w.strip(".,!?;:'\"") not in _skip
                          and w.strip(".,!?;:'\"") not in _artifact_content
                          and len(w.strip(".,!?;:'\"")) > 2]
            if meaningful:
                return " ".join(meaningful).title()
            last_e = self._mem.get_last_entity()
            if last_e and last_e.name:
                return last_e.name
            return q.title()
        return q.title()

    # ── store artifact manually (call from MediaManager callbacks) ────────────

    def register_artifact(self, record: ArtifactRecord) -> None:
        self._art.store_artifact(record)
        self._ctx.add_artifact(record)

    # ── expose context for testing ────────────────────────────────────────────

    @property
    def context(self) -> ContextStore:
        return self._ctx

    @property
    def artifact_memory(self) -> ArtifactMemory:
        return self._art
