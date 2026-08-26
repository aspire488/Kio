from __future__ import annotations

import functools
import logging
import re
import threading
import time
from typing import Optional

from mini_kio.core import config
from mini_kio.media.media_state import MediaState, MediaType, PlayerType
from mini_kio.media.media_session import (
    MediaResult, MediaSession, MediaCandidate, user_facing_media_label,
)
from mini_kio.media.media_context import MediaContext
from mini_kio.media.media_registry import MediaRegistry
from mini_kio.media.media_discovery import MediaDiscovery
from mini_kio.media.media_recommender import MediaRecommender
from mini_kio.media.media_intelligence_models import MediaArtifactType
from mini_kio.memory.memory_store import MemoryStore
from mini_kio.media.intelligence.media_opportunity_engine import MediaOpportunityEngine
from mini_kio.media.intelligence.media_offer_manager import MediaOfferManager
from mini_kio.media.providers.youtube_provider import YouTubeProvider
from mini_kio.media.providers.browser_provider import BrowserProvider
from mini_kio.media.providers.local_media_provider import LocalMediaProvider
from mini_kio.core.media_contract import score_content_intent, CONTENT_TYPE_PRIORITY as _CONTRACT_PRIORITY

logger = logging.getLogger(__name__)

_FUZZY_MAP: dict[str, str] = {
    "pasue": "pause",
    "resme": "resume",
    "unmut": "unmute",
    "colume": "volume",
    "volme": "volume",
    "seak": "seek",
    "foward": "forward",
    "backword": "backward",
    "unmute": "unmute",
    "volum": "volume",
}

_ARTIFACT_TYPOS: dict[str, str] = {
    "hihlighs": "highlights", "higlights": "highlights", "hightlights": "highlights", "highlites": "highlights",
    "trailor": "trailer", "tralier": "trailer",
    "game play": "gameplay", "gamepla": "gameplay",
}

# Artifact keywords that can be stripped from play queries to find the base entity name.
# When a user says "play interstellar trailer", the entity is "Interstellar" not the video title.
_ARTIFACT_KEYWORDS = [
    "trailer", "teaser", "highlights", "highlight", "gameplay",
    "music video", "official trailer", "official music video",
    "audiobook", "book review", "book summary", "author interview",
    "interview", "review", "recap", "blooper", "bloopers",
    "behind the scenes", "behind-the-scenes", "live performance",
    "acoustic", "acoustic version", "lyrics video", "lyrics",
    "official video", "best scenes", "best moments",
    "ending explained", "clip", "clips", "analysis",
    "match analysis", "concert", "live", "reading",
    "adaptation trailer", "episode", "season",
]

# ── inlined from media_followup_engine.py (Phase 3A merge) ─────────────

_TRANSPORT_PATTERNS: dict[re.Pattern, str] = {
    re.compile(r"\b(pause|hold on|wait|stop music for now)\b", re.I): "pause",
    re.compile(r"\b(resume|continue|unpause|play again|keep going|carry on|keep playing|resume it|continue playing)\b", re.I): "resume",
    re.compile(r"\b(stop (music|playing|the (?:music|song|video|audio|stream))|turn off (?:the )?(?:music|audio|video|stream))\b", re.I): "stop",
    re.compile(r"\b(next|next song|skip|skip this|next track)\b", re.I): "next",
    re.compile(r"\b(previous|prev|back|go back|last song)\b", re.I): "previous",
    re.compile(r"\b(shuffle|shuffle mode|random)\b", re.I): "shuffle",
    re.compile(r"\b(repeat|loop|repeat this|loop this)\b", re.I): "repeat",
    re.compile(r"\b(mute|silence|quiet)\b", re.I): "mute",
    re.compile(r"\b(unmute|restore sound)\b", re.I): "unmute",
}

_VOLUME_UP = re.compile(r"\b(louder|volume up|turn (it |the volume )?up|increase volume)\b", re.I)
_VOLUME_DOWN = re.compile(r"\b(quieter|softer|volume down|turn (it |the volume )?down|lower (the )?volume)\b", re.I)
_VOLUME_SET = re.compile(r"\b(\d+)\s*%?\s*(volume|vol)?\b", re.I)

def _parse_volume_delta(utterance: str) -> Optional[int]:
    text = utterance.lower()
    if _VOLUME_UP.search(text):
        return 10
    if _VOLUME_DOWN.search(text):
        return -10
    m = _VOLUME_SET.search(text)
    if m:
        return int(m.group(1))
    return None


_UI_NOISE_WORDS: set[str] = {
    "close", "sign in", "subscribe", "continue reading", "read more",
    "advertisement", "ads", "login", "menu", "ad", "sponsored",
}

_CONTENT_TYPE_PRIORITY: dict[str, list[str]] = {
    mt.value: providers for mt, providers in _CONTRACT_PRIORITY.items()
}

_SEEK_PATTERNS = [
    # Minute-based (high priority)
    (r"(?:jump|go)\s+ahead\s+(\d+)\s*min(?:ute)?s?", lambda m: int(m.group(1)) * 60),
    (r"(?:jump|go)\s+back\s+(\d+)\s*min(?:ute)?s?", lambda m: int(m.group(1)) * -60),
    (r"(?:seek|skip|go|move)\s+(?:forward|ahead)\s+(\d+)\s*min(?:ute)?s?", lambda m: int(m.group(1)) * 60),
    (r"(?:seek|skip|go|move)\s+(?:back|backward|rewind)\s+(\d+)\s*min(?:ute)?s?", lambda m: int(m.group(1)) * -60),
    # "seek forward by X seconds" — with "by" keyword
    (r"(?:seek|skip|go|move)\s+(?:forward|ahead)\s+by\s+(\d+)\s*(?:second|sec|s)?", 1),
    (r"(?:seek|skip|go|move)\s+(?:back|backward|rewind)\s+by\s+(\d+)\s*(?:second|sec|s)?", -1),
    (r"(?:forward|ahead)\s+by\s+(\d+)\s*(?:second|sec|s)?", 1),
    (r"(?:back|backward|rewind)\s+by\s+(\d+)\s*(?:second|sec|s)?", -1),
    (r"rewind\s+(\d+)\s*(?:second|sec|s)?", -1),
    # "skip ahead X seconds" / "seek forward X seconds"
    (r"(?:seek|skip|go|move)\s+(?:forward|ahead)\s+(\d+)\s*(?:second|sec|s)?", 1),
    (r"(?:seek|skip|go|move)\s+(?:back|backward|rewind)\s+(\d+)\s*(?:second|sec|s)?", -1),
    (r"(?:forward|ahead)\s+(\d+)\s*(?:second|sec|s)?", 1),
    (r"(?:back|backward|rewind)\s+(\d+)\s*(?:second|sec|s)?", -1),
    (r"(?:skip)\s+ahead\s+(\d+)\s*(?:second|sec|s)?", 1),
    (r"^skip\s+(\d+)\s*(?:second|sec|s)?", 1),
    (r"^(?:seek|skip)\s+(\d+)\s*(?:second|sec|s)?", 1),
]


_MEDIA_TOPIC_KEYWORDS: dict[str, str] = {
    "SPORTS": "fifa world cup football soccer basketball baseball nfl nba uefa formula 1 ipl premier league la liga bundesliga serie a champions league euro cup copa america f1 standings table fixtures results",
    "MOVIES": "movie film cinema marvel dc disney pixar star wars entertainment studio",
    "TV": "tv television show series episode season netflix hbo prime video apple tv streaming",
    "MUSIC": "music song album artist singer band track the weeknd",
    "GAMING": "game gaming videogame esports console pc playstation xbox rockstar gta",
    "TECH": "tech technology gadget software hardware ai",
}

_SPORTS_ENTITIES: dict[str, list[str]] = {
    "fifa_world_cup": ["fifa world cup", "world cup", "worldcup"],
    "fifa": ["fifa"],
    "uefa": ["uefa", "champions league", "europa league", "uefaa"],
    "premier_league": ["premier league", "premier leage", "epl"],
    "la_liga": ["la liga", "laliga"],
    "bundesliga": ["bundesliga"],
    "serie_a": ["serie a", "seriea"],
    "formula_1": ["formula 1", "f1", "formula one"],
    "nba": ["nba", "basketball"],
    "nfl": ["nfl", "american football"],
    "ipl": ["ipl", "indian premier league"],
    "euro_cup": ["euro cup", "eurocopa", "european cup"],
    "copa_america": ["copa america", "copa américa"],
    "germany": ["germany"],
    "curacao": ["curacao"],
    "brazil": ["brazil"],
    "argentina": ["argentina"],
    "france": ["france", "french team"],
    "spain": ["spain", "spanish team"],
    "england": ["england", "english team"],
    "portugal": ["portugal"],
    "netherlands": ["netherlands", "holland"],
}

_MOVIES_ENTITIES: dict[str, list[str]] = {
    "marvel": ["marvel", "mcu", "marvel cinematic universe"],
    "spider_man": ["spider-man", "spiderman"],
    "dc": ["dc", "dc comics", "dc extended universe", "dc universe"],
    "disney": ["disney"],
    "pixar": ["pixar"],
    "star_wars": ["star wars"],
}

_TV_ENTITIES: dict[str, list[str]] = {
    "netflix": ["netflix"],
    "hbo": ["hbo", "max"],
    "prime_video": ["prime video", "amazon prime"],
    "apple_tv": ["apple tv", "apple tv+"],
}

_MUSIC_ENTITIES: dict[str, list[str]] = {
    "the_weeknd": ["the weeknd", "abel tesfaye"],
}

_GAMING_ENTITIES: dict[str, list[str]] = {
    "gta_6": ["gta 6", "grand theft auto 6"],
    "playstation": ["playstation", "ps5", "ps4"],
    "xbox": ["xbox"],
    "rockstar": ["rockstar", "rockstar games"],
}

# Example events (will need dynamic extraction for real use cases)
_SPORTS_EVENTS: dict[str, list[str]] = {
    "germany_vs_curacao": ["germany vs curacao", "germany curacao match", "germany curacao game"],
    "brazil_vs_argentina": ["brazil vs argentina", "brazil argentina match", "brazil argentina game"],
    "france_vs_spain": ["france vs spain", "france spain match", "france spain game"],
}


def _detect_sports_mode(query: str) -> str:
    try:
        from mini_kio.media.intelligence.sports_intelligence import detect_sports_mode as _new_detect
        mode = _new_detect(query)
        return mode.value
    except Exception:
        pass
    return _detect_sports_mode_old(query)


def _event_record_to_legacy_dict(record) -> dict:
    score = f"{record.score_a}-{record.score_b}" if (record.score_a is not None and record.score_b is not None) else ""
    return {
        "entity_a": record.entity_a,
        "entity_b": record.entity_b,
        "score": score,
        "event_type": record.event_type,
        "canonical_name": f"{record.entity_a} vs {record.entity_b}",
        "status": record.status.value.upper(),
        "raw_text": record.raw_text,
    }


def _detect_sports_mode_old(query: str) -> str:
    ql = query.lower()
    if any(kw in ql for kw in ("standings", "standings", "table", "group table", "group standings", "points table", "group ", "groups")):
        if "highlight" not in ql:
            return "STANDINGS"
    if any(kw in ql for kw in ("fixtures", "fixture", "upcoming", "next match", "schedule", "next matches")):
        return "FIXTURES"
    if any(kw in ql for kw in ("results", "result", "scores", "score", "who won", "matches")):
        if "highlight" not in ql and "fixture" not in ql:
            return "RESULTS"
    if any(kw in ql for kw in ("highlights", "highlight", "best moments")):
        return "HIGHLIGHTS"
    return "GENERAL"


def _detect_media_topic(query: str) -> Optional[str]:
    ql = query.lower()
    scores: dict[str, int] = {}
    for topic, keywords in _MEDIA_TOPIC_KEYWORDS.items():
        score = sum(1 for kw in keywords.split() if kw in ql)
        if score > 0:
            scores[topic] = score
    if not scores:
        return None
    return max(scores, key=scores.get)


def _detect_media_type(query: str) -> str:
    """Score content-type intent using the media contract's weighted scorer.

    Returns a string media type for backward compatibility with providers
    and _CONTENT_TYPE_PRIORITY lookups.
    """
    intent = score_content_intent(query)
    return intent.media_type.value


def _parse_seek(text: str) -> Optional[int]:
    tl = text.lower().strip()
    for pattern, direction in _SEEK_PATTERNS:
        m = re.search(pattern, tl)
        if m:
            if callable(direction):
                try:
                    return direction(m)
                except Exception:
                    continue
            try:
                amount = int(m.group(1))
            except (ValueError, IndexError):
                continue
            if direction == -1:
                return -amount
            return amount
    return None


def _correct_fuzzy(text: str) -> str:
    words = text.lower().split()
    corrected = []
    for w in words:
        corrected.append(_FUZZY_MAP.get(w, w))
    result = " ".join(corrected)
    if result != text.lower():
        logger.info("[MM] fuzzy correction: '%s' -> '%s'", text, result)
    return result


# BUG 1 (Telegram concurrency): PTB now processes updates concurrently
# (concurrent_updates(4)), so a "hi" is answered while a slow media op runs.
# Media operations themselves MUST still be serialized: the YouTube provider
# holds a single _session/_tab_id and the registry/context are shared, so two
# concurrent media commands would corrupt each other's state. Non-media
# messages (greetings, chat) never touch MediaManager and stay fully
# concurrent. An RLock is used because media methods re-enter each other
# (process_followup -> play, seek_forward -> seek).
_MEDIA_OP_LOCK = threading.RLock()
_MEDIA_SINGLETON_LOCK = threading.Lock()


def _serialize_media_op(method):
    """Serialize a media mutation across Telegram's concurrent update threads."""
    @functools.wraps(method)
    def wrapper(self, *args, **kwargs):
        with _MEDIA_OP_LOCK:
            return method(self, *args, **kwargs)
    return wrapper


class MediaManager:
    _instance: Optional[MediaManager] = None

    def __init__(self):
        self._registry = MediaRegistry()
        self._context = MediaContext()
        self._discovery = MediaDiscovery()
        self._recommender = MediaRecommender()
        self._memory_store = MemoryStore(session_id="media_intelligence")
        self._offer_manager = MediaOfferManager(self._memory_store)
        self._opportunity_engine = MediaOpportunityEngine(self._context)
        self._last_execution_timestamp = 0.0
        self._last_execution_query = ""
        self._providers: dict[str, type] = {}
        self._provider_instances: dict[str, object] = {}
        self._init_providers()

        # Phase C4: MediaIntelligenceAdapter (unification)
        self._intelligence_adapter: Optional[object] = None
        try:
            from mini_kio.media.intelligence.integration_adapter import MediaIntelligenceAdapter
            from mini_kio.intelligence.retrieval_router import RetrievalRouter, RetrievalResult
            
            router = RetrievalRouter()
            
            def _adapter_retrieval(q: str, topic: Optional[str] = None, mode: str = "") -> Optional[RetrievalResult]:
                # Map string topic to RetrievalTopic if needed, or just pass hint
                res = router.retrieve(q)
                if res:
                    logger.info("[RETRIEVAL_ROUTER] source=%s query=%s", res.source, q)
                    return res
                logger.info("[RETRIEVAL_ROUTER] no_results query=%s", q)
                return None

            def _adapter_evidence(q: str, topic: Optional[str] = None, max_results: int = 4) -> list:
                # Multi-source evidence collection for currentness/verification:
                # returns ALL healthy provider results (with dates when exposed)
                # so the evidence layer ranks by freshness and reconciles
                # contradictions instead of trusting the first provider hit.
                try:
                    return router.retrieve_evidence(q, topic_hint=None, max_results=max_results)
                except Exception:
                    return []

            self._intelligence_adapter = MediaIntelligenceAdapter(
                retrieval_fn=_adapter_retrieval,
                play_fn=lambda q: self.play(q),
                pending_action_fn=lambda q: {"action": "search", "subject": self._context.entity} if self._context.pending_action == "play_media" and self._context.entity else None,
                retrieve_evidence_fn=_adapter_evidence,
            )

            # Wire LLM summarization (optional — falls back to deterministic if unavailable)
            try:
                from mini_kio.core.llm_router import ask_llm
                import asyncio
                def _llm_summarize(prompt: str) -> Optional[str]:
                    try:
                        loop = asyncio.new_event_loop()
                        asyncio.set_event_loop(loop)
                        try:
                            # Bounded but generous enough to complete a 2-4
                            # sentence answer; the composer rejects truncated
                            # output and falls back to deterministic extract.
                            return loop.run_until_complete(ask_llm(prompt, timeout=20.0, max_tokens=450))
                        finally:
                            loop.close()
                            asyncio.set_event_loop(None)
                    except Exception:
                        return None
                self._intelligence_adapter.set_llm_fn(_llm_summarize)

                # Verification synthesis is a heavier task: multi-claim evidence
                # plus a conversational register contract. The generic 15s/300
                # token budget caused timeouts that fell back to a raw source
                # dump. Give it a dedicated, longer budget.
                def _llm_verify(prompt: str) -> Optional[str]:
                    try:
                        loop = asyncio.new_event_loop()
                        asyncio.set_event_loop(loop)
                        try:
                            return loop.run_until_complete(ask_llm(prompt, timeout=30.0, max_tokens=600))
                        finally:
                            loop.close()
                            asyncio.set_event_loop(None)
                    except Exception:
                        return None
                self._intelligence_adapter.set_verify_llm_fn(_llm_verify)
                logger.info("[MM_INTELLIGENCE_ADAPTER] LLM summarization wired")
            except Exception:
                logger.info("[MM_INTELLIGENCE_ADAPTER] LLM summarization unavailable (deterministic fallback active)")
            logger.info("[MM_INTELLIGENCE_ADAPTER] MediaIntelligenceAdapter initialized")
        except Exception as exc:
            logger.warning("[MM_INTELLIGENCE_ADAPTER] Failed to initialize: %s", exc)

        # Legacy ArtifactMemory (for backward compatibility if needed)
        self._artifact_memory: Optional[object] = None
        if self._intelligence_adapter:
            # We assume it has artifact_memory property as per previous read
            self._artifact_memory = self._intelligence_adapter.artifact_memory
        else:
            try:
                from mini_kio.media.intelligence.artifact_memory import ArtifactMemory
                self._artifact_memory = ArtifactMemory()
            except Exception:
                pass

        # DiscoveryEngine: unified discovery pipeline
        self._discovery_engine: Optional[object] = None
        try:
            from mini_kio.media.intelligence.discovery_engine import DiscoveryEngine
            from mini_kio.media.intelligence.media_entity_memory import MediaEntityMemory
            from mini_kio.media.intelligence.media_preference_model import MediaPreferenceModel

            _mem = None
            if self._intelligence_adapter and hasattr(self._intelligence_adapter, '_mem'):
                _mem = self._intelligence_adapter._mem
            else:
                _mem = MediaEntityMemory()

            _prefs = MediaPreferenceModel(_mem)
            self._discovery_engine = DiscoveryEngine(_mem, _prefs, self._context)
            logger.info("[MM_DISCOVERY] DiscoveryEngine initialized")
        except Exception as exc:
            logger.warning("[MM_DISCOVERY] Failed to initialize DiscoveryEngine: %s", exc)

    # Active provider registry: ONLY YouTube-family + browser fallback.
    # Spotify is DISABLED — must never participate in provider selection.
    _ACTIVE_PROVIDERS = frozenset({"youtube", "browser", "local"})

    # Media operation serialization lock: Play/Next/Previous are LONG-RUNNING
    # operations that navigate and verify playback. Commands arriving during an
    # active transition ("Play X" + "Stop" arriving quickly) must be serialized
    # so the state machine completes before the next command acts on the result.
    _media_op_lock = threading.Lock()

    def _init_providers(self):
        self._providers = {
            "youtube": YouTubeProvider,
            # "spotify": DISABLED — not in active provider set
            "browser": BrowserProvider,
            "local": LocalMediaProvider,
        }

    def _get_provider(self, name: str):
        if name not in self._provider_instances:
            cls = self._providers.get(name)
            if cls:
                self._provider_instances[name] = cls()
        result = self._provider_instances.get(name)
        logger.info("[MM_TRACE] get_provider name=%s found=%s provider=%s", name, result is not None, type(result).__name__ if result else None)
        return result

    def _get_connector(self):
        from mini_kio.core.command_router import _get_connector
        return _get_connector()

    @classmethod
    def get_instance(cls) -> MediaManager:
        # Guarded lazy singleton: with concurrent Telegram updates two threads
        # could both see _instance is None and build different instances,
        # splitting session/provider state between them.
        if cls._instance is None:
            with _MEDIA_SINGLETON_LOCK:
                if cls._instance is None:
                    cls._instance = MediaManager()
        return cls._instance

    @classmethod
    def reset_instance(cls):
        with _MEDIA_SINGLETON_LOCK:
            cls._instance = None

    def _select_provider(self, query: str = "", platform: str = "", media_type: str = "") -> Optional[str]:
        if platform:
            # Guard: platform must be an active provider
            if platform not in self._ACTIVE_PROVIDERS:
                logger.warning("[MM_PROVIDER_GUARD] platform=%s not in active set, ignoring", platform)
                platform = ""
            else:
                return platform

        active = self._registry.get_active_by_player()
        if active:
            pname = active[0]
            if pname in self._ACTIVE_PROVIDERS:
                return pname

        if not media_type:
            media_type = _detect_media_type(query)

        priority = _CONTENT_TYPE_PRIORITY.get(media_type, ["youtube"])
        # Filter to active providers only
        priority = [p for p in priority if p in self._ACTIVE_PROVIDERS]
        for pname in priority:
            prov = self._get_provider(pname)
            if prov and hasattr(prov, "check_active"):
                session = prov.check_active()
                if session:
                    return pname
        return priority[0] if priority else "youtube"

    @staticmethod
    def _extract_entity_name(query: str) -> str:
        """Strip artifact keywords from a play query to get the base entity name.

        'interstellar trailer' -> 'interstellar'
        'believer music video' -> 'believer'
        'harry potter audiobook' -> 'harry potter'
        """
        q = query.strip()
        if not q:
            return ""
        q_lower = q.lower()
        for kw in sorted(_ARTIFACT_KEYWORDS, key=len, reverse=True):
            kw_lower = kw.lower()
            if q_lower.endswith(" " + kw_lower):
                q = q[:-(len(kw) + 1)].strip()
                q_lower = q.lower()
            elif q_lower.startswith(kw_lower + " "):
                q = q[(len(kw) + 1):].strip()
                q_lower = q.lower()
        return q

    def _register_session(self, provider_name: str, result: MediaResult):
        if result.success and result.session:
            self._registry.set(provider_name, result.session)
            # Learn from playback: record this as a positive preference signal
            self._learn_from_playback(result.session, provider_name)
            # Record in DiscoveryEngine for diversity tracking
            if self._discovery_engine:
                try:
                    from mini_kio.media.intelligence.discovery_engine import DiscoveryCandidate
                    _disc_cand = DiscoveryCandidate(
                        title=result.session.title or result.session.query or "",
                        channel=result.session.artist or "",
                        url=result.session.url or "",
                    )
                    self._discovery_engine.record_playback(_disc_cand)
                except Exception:
                    pass
            candidate = MediaCandidate(
                title=result.session.query or result.session.title,
                url=result.session.url,
                provider=provider_name,
                media_type=result.session.media_type,
                confidence=1.0,
                artist=result.session.artist,
                duration_s=result.session.duration_s,
            )
            self._context.set_current(candidate)
            self._context.last_query = result.session.query
            # Track current media ID for rejection handling
            self._context.current_media_id = (
                result.session.url or result.session.title or ""
            )
            # Update rejection context with the original query for next rejection.
            # MUST update every time (not just on first play) so "nah" after
            # "Play Weeknd" uses the Weeknd query, not a stale earlier query.
            self._context.current_rejection_query = result.session.query or ""
            
            # Skip entity registration for generic/thematic play queries
            # (e.g. "play a song from that movie", "play something from Vaazha II")
            # which should NOT overwrite the knowledge entity (Vaazha II) with
            # the individual played track title.
            _skip_entity_reg = False
            if self._context.last_query:
                _lq = self._context.last_query.lower()
                _generic_play = ("a song", "something", "a track", "a video",
                                 "that movie", "that show", "that film",
                                 "from that", "something from", "a song from")
                if any(p in _lq for p in _generic_play):
                    _skip_entity_reg = True
                    logger.info("[SKIP_ENTITY_REG] generic play query=%s — preserving existing entity", _lq)

            # Automatically register entity in memory (Part A)
            # RC6: the write boundary must refuse garbage — the session itself
            # is registered above (so controls still work), but nothing is
            # persisted to entity/artifact memory when the query/URL fails the
            # sanity checks (scraped page text, markdown dumps, huge URLs).
            _sane_reg = (
                self._is_sane_media_query(result.session.query or "")
                and self._is_sane_media_url(result.session.url or "")
            )
            if result.session.state == MediaState.PLAYING and self._intelligence_adapter and not _skip_entity_reg and _sane_reg:
                try:
                    from mini_kio.media.intelligence.media_entity_memory import ResolvedEntity, EntityType, MediaProvider, HistoricalMediaSession
                    from mini_kio.media.media_state import MediaType
                    import time
                    
                    m_map = {MediaType.MUSIC: EntityType.SONG, MediaType.VIDEO: EntityType.YOUTUBER, 
                             MediaType.TRAILER: EntityType.MOVIE, MediaType.TUTORIAL: EntityType.YOUTUBER}
                    etype = m_map.get(result.session.media_type, EntityType.SONG)
                    
                    p_map = {"youtube": MediaProvider.YOUTUBE, "browser": MediaProvider.BROWSER}
                    prov = p_map.get(provider_name, MediaProvider.UNKNOWN)
                    
                    # Extract base entity from query (strip artifact keywords).
                    # This prevents "Interstellar - Official Trailer (2024)" from
                    # overwriting the conceptual entity "Interstellar" in memory.
                    _entity_name = self._extract_entity_name(result.session.query or "")
                    entity = ResolvedEntity(
                        name=_entity_name or result.session.title or "",
                        entity_type=etype,
                        provider=prov,
                        url=result.session.url,
                        metadata={
                            "artist": result.session.artist, 
                            "query": result.session.query,
                            "topic": self._context.topic,
                            "media_type": str(result.session.media_type),
                            "platform": provider_name
                        }
                    )
                    
                    # Store in history (which also sets last_entity)
                    hist_session = HistoricalMediaSession(
                        session_id=str(int(time.time())),
                        entity=entity,
                        started_at=time.time()
                    )
                    self._intelligence_adapter._mem.push_session(hist_session)
                    
                    logger.info("[MEDIA_ENTITY_REGISTER] entity=%s type=%s success=True", entity.name, etype.value)
                    
                    # Also update ContextStore (Part D)
                    self._intelligence_adapter.context.set_subject(entity.name)
                    
                    # Automatically register artifact in memory (Part C)
                    if self._artifact_memory:
                        from mini_kio.media.intelligence.media_intelligence_models import ArtifactRecord, ArtifactType, TopicType
                        a_map = {MediaType.TRAILER: ArtifactType.TRAILER, MediaType.TUTORIAL: ArtifactType.TEASER,
                                 MediaType.VIDEO: ArtifactType.HIGHLIGHTS} # Fallback
                        
                        # Use title/query to refine artifact type
                        atype = a_map.get(result.session.media_type, ArtifactType.HIGHLIGHTS)
                        q_lower = (result.session.query or "").lower()
                        if "highlight" in q_lower: atype = ArtifactType.HIGHLIGHTS
                        elif "trailer" in q_lower: atype = ArtifactType.TRAILER
                        elif "gameplay" in q_lower: atype = ArtifactType.GAMEPLAY
                        elif "music video" in q_lower: atype = ArtifactType.MUSIC_VIDEO
                        
                        # Update entity metadata with detected artifact type
                        entity.metadata["artifact_type"] = atype.value
                        
                        art_record = ArtifactRecord(
                            artifact_type=atype,
                            topic=self._topic_str_to_enum(self._context.topic) or TopicType.UNKNOWN,
                            subject=entity.name,
                            url=result.session.url,
                            source="media_manager_auto"
                        )
                        # MediaIntelligenceAdapter already has artifact_memory property
                        self._intelligence_adapter.artifact_memory.store_artifact(art_record)
                        logger.info("[ARTIFACT_REGISTERED] type=%s subject=%s", atype.value, entity.name)

                except Exception as exc:
                    logger.warning("[MEDIA_ENTITY_REGISTER_FAILED] %s", exc)

    # Internal tags that must never reach users
    _INTERNAL_TAG_RE = re.compile(r"\s*\[[A-Z_]+\]\s*$")

    def _learn_from_playback(self, session: 'MediaSession', provider_name: str) -> None:
        """Record playback as a positive preference signal.

        Called after every successful play. Feeds the preference model
        so future discovery queries reflect what the user actually plays.
        """
        try:
            from mini_kio.media.intelligence.media_entity_memory import (
                MediaEntityMemory, ResolvedEntity, EntityType, MediaProvider,
                HistoricalMediaSession,
            )
            from mini_kio.media.intelligence.media_preference_model import MediaPreferenceModel
            from mini_kio.media.media_state import MediaType as _MT

            # Get or create the entity memory used by the intelligence adapter
            _mem = None
            if self._intelligence_adapter and hasattr(self._intelligence_adapter, '_mem'):
                _mem = self._intelligence_adapter._mem
            else:
                return  # no memory available, skip learning

            # Map provider name to MediaProvider enum
            _prov_map = {"youtube": MediaProvider.YOUTUBE, "browser": MediaProvider.BROWSER}
            prov = _prov_map.get(provider_name, MediaProvider.UNKNOWN)

            # Map media type
            _mt_map = {_MT.MUSIC: EntityType.SONG, _MT.VIDEO: EntityType.YOUTUBER,
                       _MT.TRAILER: EntityType.MOVIE, _MT.MUSIC_VIDEO: EntityType.SONG}
            etype = _mt_map.get(session.media_type, EntityType.SONG)

            # Build entity from session
            entity = ResolvedEntity(
                name=session.title or session.query or "",
                entity_type=etype,
                provider=prov,
                url=session.url,
                metadata={
                    "artist": session.artist or "",
                    "channel": session.artist or "",  # YouTube channel
                    "query": session.query or "",
                },
            )

            # Record as a historical session
            hist = HistoricalMediaSession(
                session_id=str(int(time.time())),
                entity=entity,
                started_at=time.time(),
            )
            _mem.push_session(hist)

            # Update preference model
            if not hasattr(self, '_pref_model'):
                self._pref_model = MediaPreferenceModel(_mem)
            self._pref_model.ingest_session(hist)

            logger.info("[LEARN] recorded playback: entity=%s type=%s provider=%s",
                        entity.name, etype.value, provider_name)
        except Exception as exc:
            logger.debug("[LEARN] failed to record playback: %s", exc)

    def _to_dict(self, result: MediaResult) -> dict:
        # A truthful failure may carry only `error` (no message). Surface it as
        # the user-facing message so the reply is the natural failure text, not
        # the generic "Command failed." fallback.
        _message = self._sanitize_media_message(result)
        d = {"success": result.success, "message": _message, "player": result.player}
        if result.error:
            d["error"] = result.error
        if result.session:
            d["session"] = result.session.to_dict()
        return d

    def _sanitize_media_message(self, result: MediaResult) -> str:
        """Strip internal tags and convert raw dicts to user-friendly text."""
        msg = result.message or result.error or ""
        if isinstance(msg, dict):
            return "Done." if result.success else (result.error or "Operation failed.")
        return self._INTERNAL_TAG_RE.sub("", str(msg)) or ("Done." if result.success else "Operation failed.")

    def _analyze_query_for_intelligence(self, query: str) -> None:
        ql = query.lower()
        self._context.topic = None
        self._context.entity = None
        self._context.event = None
        self._context.match_status = None
        self._context.source_provider = None
        self._context.source_confidence = 0.0
        self._context.source_event_type = None
        self._context.last_media_type = None
        self._context.last_completed_match = None
        self._context.media_candidate = None
        self._context.sports_mode = ""

        # Determine overall media topic
        detected_topic = _detect_media_topic(query)
        if detected_topic:
            self._context.topic = detected_topic
            self._context.last_media_type = detected_topic.lower() 

        # Extract entity and event based on topic
        if self._context.topic == "SPORTS":
            self._context.sports_mode = _detect_sports_mode(query)
            logger.info("[SPORTS_INTELLIGENCE_MODE] mode=%s query=%s", self._context.sports_mode, query)

            # Detect entities
            for entity_key, patterns in _SPORTS_ENTITIES.items():
                for pattern in patterns:
                    if pattern in ql:
                        self._context.entity = entity_key
                        break
                if self._context.entity:
                    break

            # Detect events
            for event_key, patterns in _SPORTS_EVENTS.items():
                for pattern in patterns:
                    if pattern in ql:
                        self._context.event = event_key
                        break
                if self._context.event:
                    break

            # Rule 2: Extract last_completed_match
            # Simple heuristic: Use the first sentence if it looks like a score/result
            # and doesn't contain "upcoming" or "tomorrow"
            if self._context.media_candidate: # Assuming summary is stored here temporarily
                summary = self._context.media_candidate
                sentences = re.split(r'(?<=[.!?])\s+', summary)
                if sentences:
                    candidate = sentences[0]
                    avoid_words = ["upcoming", "tomorrow", "next", "later"]
                    if not any(w in candidate.lower() for w in avoid_words):
                        if any(c.isdigit() for c in candidate) or "beat" in candidate.lower() or "win" in candidate.lower():
                            self._context.last_completed_match = candidate
                            logger.info("[MM_INTELLIGENCE] Detected last_completed_match: %s", self._context.last_completed_match)

        elif self._context.topic in ("MOVIES", "TV", "MUSIC", "GAMING"):
            _entity_key = f"_{self._context.topic}_ENTITIES"
            _entity_dict = globals().get(_entity_key, {})
            for entity_key, patterns in _entity_dict.items():
                for pattern in patterns:
                    if pattern in ql:
                        self._context.entity = entity_key
                        break
                if self._context.entity:
                    break

            if self._context.media_candidate:
                 logger.info("[MM_INTELLIGENCE] Detected media_candidate: %s", self._context.media_candidate)

        # Fallback for media_type if not set by topic
        if not self._context.last_media_type:
            self._context.last_media_type = _detect_media_type(query)

        logger.info(
            "[MM_INTELLIGENCE] Query Analysis: topic=%s, entity=%s, event=%s, media_type=%s",
            self._context.topic,
            self._context.entity,
            self._context.event,
            self._context.last_media_type,
        )

    # ── Public API ────────────────────────────────────────────────────

    def _playing(self, result: MediaResult) -> bool:
        """True if the provider result actually established playback."""
        return bool(
            result.success
            and result.session
            and result.session.state == MediaState.PLAYING
        )

    @staticmethod
    def _is_sane_media_query(q: str) -> bool:
        """A resolved play query must look like a search target, never scraped
        page text: no URL scheme, no markdown-link syntax, bounded length."""
        if not q:
            return False
        if len(q) > 150:
            return False
        if q.startswith(("http://", "https://", "www.")):
            return False
        if "http" in q.lower() or "](" in q or ")" in q:
            return False
        return bool(re.search(r"[a-z0-9]{2,}", q, re.IGNORECASE))

    @staticmethod
    def _is_sane_media_url(url: str) -> bool:
        """RC6: a stored media URL must be a real YouTube URL — never scraped
        page text, markdown-link dumps, or whitespace-laden navigation garbage.
        The write boundary refuses such values so garbage is never persisted as
        the canonical media reference."""
        u = (url or "").strip()
        if not u or len(u) > 400:
            return False
        if not u.startswith(("https://www.youtube.com/", "https://youtu.be/",
                             "https://music.youtube.com/")):
            return False
        if any(ch in u for ch in (" ", "\n", "\t")) or ")[" in u or "](" in u:
            return False
        return True

    @_serialize_media_op
    def play(self, query: str = "", platform: str = "") -> dict:
        logger.info("[MM] action=play query=%s platform=%s", query, platform)
        logger.info("[MM_TRACE] enter query=%s platform=%s", query, platform)

        ql = query.lower().strip()
        _is_rejection = False  # Flag: set True when user rejects current media

        # ── Step -3: Rejection / Next Candidate Handling ──
        # Context-aware rejection: when media is active, short negative/
        # continuation phrases are interpreted as media rejections — no giant
        # regex needed. The active session IS the context.
        _is_rejection_candidate = False
        if self._context.last_query or self._context.current_media_id:
            # Short negative/continuation signals — interpreted as rejection
            # BECAUSE there is an active media session (context provides meaning)
            _NEGATIVE_SIGNALS = {
                "nah", "nope", "no", "nahh", "nahhh", "naw", "naww",
                "nah bro", "no bro", "nah man", "no man",
            }
            _CHANGE_SIGNALS = {
                "not this", "not this one", "not feeling this", "not it",
                "this ain't it", "this isn't it", "this sucks", "this is bad",
                "skip", "skip this", "skip it", "skip that",
                "next", "next one", "another", "another one", "another please",
                "something different", "something better", "play something else",
                "play something different", "try another", "try something else",
                "try something different", "give me another", "give me something else",
                "change it", "switch it",
                "not what i meant", "not what we meant",
                "that's not what i meant", "thats not what i meant",
            }
            if ql in _NEGATIVE_SIGNALS or ql in _CHANGE_SIGNALS:
                _is_rejection_candidate = True
            # Also match compound patterns: "nah, next" / "nah, another"
            elif ql.startswith("nah") and any(w in ql for w in ("next", "another", "try")):
                _is_rejection_candidate = True
            elif ql.startswith("no") and any(w in ql for w in ("next", "another", "try")):
                _is_rejection_candidate = True
            # Catch-all: short negative that doesn't look like a new play request
            elif len(ql.split()) <= 3 and any(ql.startswith(n) for n in ("nah", "no", "not ")) and "play" not in ql:
                _is_rejection_candidate = True

        if _is_rejection_candidate:
            # Track rejection in both legacy context and discovery engine
            if self._context.current_media_id:
                self._context.rejected_media_ids.append(self._context.current_media_id)

            # Record rejection in preference model (negative learning)
            if self._discovery_engine and self._context.last_selected_candidate:
                try:
                    from mini_kio.media.media_intelligence_models import ResolvedEntity, EntityType, MediaProvider
                    _rej_entity = ResolvedEntity(
                        name=self._context.last_selected_candidate.title or "",
                        entity_type=EntityType.SONG,
                        provider=MediaProvider.YOUTUBE,
                        metadata={
                            "channel": self._context.last_selected_candidate.artist or "",
                            "artist": self._context.last_selected_candidate.artist or "",
                        },
                    )
                    # Escalating rejection penalty: more rejections = stronger penalty
                    _rej_strength = min(0.5, 0.2 + 0.1 * self._context.discovery_rejection_count)
                    self._discovery_engine._prefs.record_rejection(_rej_entity, strength=_rej_strength)
                    logger.info("[REJECT_LEARN] recorded rejection strength=%.2f count=%d",
                                _rej_strength, self._context.discovery_rejection_count)
                except Exception as exc:
                    logger.debug("[REJECT_LEARN] failed: %s", exc)

            # Use DiscoveryEngine to build re-discovery query
            if self._discovery_engine and self._context.discovery_active:
                try:
                    result = self._discovery_engine.handle_rejection()
                    if result.query_used:
                        query = result.query_used
                        ql = query.lower().strip()
                        _is_rejection = True
                        logger.info("[MM_REJECTION] discovery_engine query=%s intent=%s",
                                    query, result.intent.semantic_intent if result.intent else "")
                    else:
                        # Fallback to original query
                        original_query = self._context.current_rejection_query or self._context.last_query
                        if original_query:
                            query = original_query
                            ql = query.lower().strip()
                            _is_rejection = True
                        else:
                            return {"success": True, "message": "What would you like to play?"}
                except Exception as exc:
                    logger.warning("[MM_REJECTION] discovery_engine failed: %s", exc)
                    original_query = self._context.current_rejection_query or self._context.last_query
                    if original_query:
                        query = original_query
                        ql = query.lower().strip()
                        _is_rejection = True
                    else:
                        return {"success": True, "message": "What would you like to play?"}
            else:
                # No discovery engine — use legacy rejection handling
                original_query = self._context.current_rejection_query or self._context.last_query
                original_mood = self._context.current_rejection_mood or self._context.get_mood() or ""
                original_activity = self._context.current_rejection_activity or self._context.get_activity() or ""
                if original_query:
                    logger.info("[MM_REJECTION] legacy rejecting current=%s query=%s rejected_ids=%s",
                                self._context.current_media_id, original_query, self._context.rejected_media_ids)
                    self._context.current_rejection_query = original_query
                    self._context.current_rejection_mood = original_mood
                    self._context.current_rejection_activity = original_activity
                    query = original_query
                    ql = query.lower().strip()
                    _is_rejection = True
                else:
                    return {"success": True, "message": "What would you like to play?"}

        # R5: ordinal selection of a pending offer ("play the second one" → index 1).
        # The offer engine's parse_response already maps ordinals; only route here
        # when an offer is actually pending, otherwise fall through to normal play.
        _ORDINAL_RE = re.compile(r"\b(?:first|second|third|fourth|fifth|[1-5])\b")
        if ql and _ORDINAL_RE.search(ql) and self._offer_manager.has_pending_offer():
            parsed = self._offer_manager.parse_response(ql)
            if parsed is True:
                return self.accept_intelligence_offer()

        # ── Step -2.5: Pronoun resolution — "it" / "that" / "this" → last entity name ──
        _PRONOUNS = frozenset(("it", "that", "this", "them", "those"))
        _pronoun_resolved = False
        if ql in _PRONOUNS:
            last_e = None
            if self._intelligence_adapter:
                try:
                    last_e = self._intelligence_adapter._mem.get_last_entity()
                except Exception:
                    pass
            if last_e and last_e.name:
                logger.info("[PRONOUN_RESOLVE] original=%s resolved=%s", query, last_e.name)
                query = last_e.name
                ql = query.lower().strip()
                _pronoun_resolved = True
            else:
                # R-EFG: fall back to the session's last successful play so
                # "play it" resolves through the same continuity state G4 uses.
                try:
                    from mini_kio.core.runtime import get_last_successful_interaction
                    last_play = get_last_successful_interaction(action_type="play", must_have_target=True)
                    if last_play and str(last_play.get("target", "")).strip():
                        query = str(last_play["target"])
                        ql = query.lower().strip()
                        _pronoun_resolved = True
                        logger.info("[PRONOUN_RESOLVE_RUNTIME] original=%s resolved=%s", query, ql)
                except Exception:
                    pass
            # Truthfulness: an unresolved pronoun must NEVER be played as the
            # literal word ("Play it" -> YouTube search for "it"). That both
            # misleads the user and registers a garbage entity that poisons
            # later pronoun resolutions. Say there is nothing to play instead.
            if not _pronoun_resolved:
                logger.info("[PRONOUN_RESOLVE] unresolved=%r — nothing to resolve to", ql)
                return {"success": True, "message": "I don't have a previous media to play — tell me what you'd like."}

        # ── Step -2: Bare artifact resolution — prepend last entity name ──
        _bare_artifact_patterns = {
            "trailer", "the trailer", "trailers", "the trailers",
            "teaser", "the teaser", "teasers",
            "highlight", "highlights", "the highlights",
            "gameplay", "the gameplay",
            "interview", "interviews", "the interview",
            "music video", "the music video",
            "recap", "the recap",
            "clip", "clips", "the clips",
            "blooper", "bloopers", "the bloopers",
            "behind the scenes", "behind-the-scenes",
            "best scenes", "best moments",
            "ending explained",
            "analysis", "match analysis",
            "live performance", "concert",
            "acoustic", "acoustic version",
            "lyrics video", "lyrics",
            "official video", "official music video",
        }
        if ql in _bare_artifact_patterns:
            try:
                if self._intelligence_adapter:
                    last_e = self._intelligence_adapter._mem.get_last_entity()
                    if last_e and last_e.name:
                        enriched = f"{last_e.name} {query}"
                        logger.info("[BARE_ARTIFACT_RESOLVE] original=%s enriched=%s entity=%s", query, enriched, last_e.name)
                        query = enriched
                        ql = query.lower().strip()
            except Exception:
                pass

        # R-EFG: bare "again" → replay last successful media via the session
        # continuity state (same source as G4); otherwise a truthful no-op
        # instead of searching the word "again".
        if ql == "again":
            try:
                from mini_kio.core.runtime import get_last_successful_interaction
                last = get_last_successful_interaction(action_type="play", must_have_target=True)
            except Exception:
                last = None
            if last and str(last.get("target", "")).strip():
                query = str(last["target"])
                ql = query.lower().strip()
                logger.info("[MM_AGAIN] replaying last successful media: %s", query)
            else:
                logger.info("[MM_AGAIN] no previous media to replay")
                return {"success": True, "message": "Nothing to replay — no previous media."}

        # ── Step -1: Intelligence / Continuity / Recommendation Resolution ──
        # The intelligence adapter can resolve contextual references ("that one",
        # "something from that movie") and provide continuity. It should NOT
        # override an explicit query ("play Interstellar") but SHOULD help
        # with ambiguous/contextual queries.
        _skip_intel = False
        # Skip for explicit named queries (user said a specific title/entity)
        if query and len(query.split()) >= 2 and not any(p in ql for p in (
            "give me", "find me", "show me", "put on", "play something",
            "play anything", "play random", "entertain", "surprise",
        )):
            # Has enough words to be a specific request — skip intel override
            _skip_intel = True
        # Skip for explicitly enriched artifact queries
        if not _skip_intel:
            _skip_intel = any(p in ql for p in (" audiobook", " interview", " behind the scenes", " behind-the-scenes"))
        # Skip intelligence for discovery queries — they use their own strategy
        if not _skip_intel:
            _discovery_bare = frozenset({
                "something random", "something", "anything", "surprise me",
                "surprise", "whatever", "entertain me", "play something",
                "put something on", "find something", "give me something",
                "show me something",
            })
            if ql in _discovery_bare or ql.startswith(("play something ", "play anything ", "play random ", "put on something ")):
                _skip_intel = True
        if not _skip_intel:
            try:
                _saved_subject = self._intelligence_adapter.context.recent_subject()
                _saved_art_len = len(self._intelligence_adapter._art._store)
                _saved_topic = self._intelligence_adapter.context.recent_topic()
            except Exception:
                _saved_subject = _saved_art_len = _saved_topic = None
            try:
                res = self._intelligence_adapter.handle(query, execute=False)
                if res.source in ("continuity", "recommendation", "followup", "artifact", "acceptance") and res.subject:
                    _resolved = str(res.subject)
                    if self._is_sane_media_query(_resolved):
                        logger.info("[MEDIA_INTELLIGENCE_RESOLVE] source=%s original=%s resolved=%s",
                                    res.source, ql, _resolved)
                        query = _resolved
                        ql = query.lower().strip()
                    else:
                        logger.warning("[MM_QUERY_GUARD] rejected resolution source=%s resolved=%r keeping=%r",
                                       res.source, _resolved[:80], query)
                elif _saved_subject is not None and self._intelligence_adapter:
                    # Result not applied — roll back side effects
                    self._intelligence_adapter.context.set_subject(_saved_subject, _saved_topic or None)
                    if _saved_art_len is not None:
                        del self._intelligence_adapter._art._store[_saved_art_len:]
            except Exception as exc:
                logging.getLogger(__name__).warning("[MEDIA_INTELLIGENCE_FAILED] %s", exc)

        # Rule: Duplicate Media Execution — guard vars set AFTER confirmed PLAYING below
        now = time.time()
        if ql == self._last_execution_query and (now - self._last_execution_timestamp) < 2.0:
            logger.info("[MEDIA_DUPLICATE_GUARD] Skipping duplicate execution for '%s'", ql)
            return {"success": True, "message": f"Media already playing: {query} [MEDIA_DUPLICATE_GUARD]"}

        # Rule: Play Next Video Routing
        if ql in ("next video", "play next video", "skip"):
            logger.info("[MM_ROUTING] Routing '%s' directly to next_track", ql)
            return self.next_track()
        if ql in ("previous video", "play previous video"):
            logger.info("[MM_ROUTING] Routing '%s' directly to previous_track", ql)
            return self.previous_track()

        # ── Guard: bare discovery phrases must never reach YouTube literally ──
        # Searching "play something" on YouTube finds a video literally called
        # "Play Something" — that's not personalization. Strip these phrases
        # and route through intelligent discovery instead.
        _BARE_DISCOVERY_PHRASES = {
            "play something", "play anything", "play random",
            "put something on", "put on something", "put on some music",
            "give me something", "give me something good",
            "give me something to watch", "give me something to listen to",
            "find something", "find me something", "find me something good",
            "show me something", "show me something good",
            "entertain me", "amuse me",
            "what should i watch", "what should i listen to",
            "what's good", "whats good",
            "recommend something", "suggest something",
            "something random", "something", "anything", "anything random",
            "surprise me", "surprise", "whatever",
            "i'm bored", "im bored", "i am bored", "bored",
        }
        if ql in _BARE_DISCOVERY_PHRASES:
            # Try intelligence adapter for personalized discovery
            if self._intelligence_adapter:
                try:
                    rec_result = self._intelligence_adapter._handle_recommendation(ql)
                    if rec_result and hasattr(rec_result, 'subject') and rec_result.subject:
                        _resolved = str(rec_result.subject)
                        if self._is_sane_media_query(_resolved) and _resolved.lower() != ql:
                            query = _resolved
                            ql = query.lower().strip()
                            logger.info("[DISCOVERY_INTEL] bare '%s' resolved to '%s'", ql, query)
                except Exception:
                    pass
            # If still a bare discovery phrase, ask user what they want
            if ql in _BARE_DISCOVERY_PHRASES:
                logger.info("[DISCOVERY_BARE] no resolution for '%s' — asking user", ql)
                return {"success": True, "message": "What would you like to play?"}

        # ── Step 0: Resume active ──────────────────────────────
        if not query and not platform:
            active = self._registry.get_active()
            if active:
                prov = self._registry.get_player_for_session(active)
                if prov:
                    p = self._get_provider(prov)
                    if p:
                        result = p.resume()
                        self._register_session(prov, result)
                        logger.info("[MM_TRACE] resuming active session result=%s", result)
                        return self._to_dict(result)
            logger.info("[MM_TRACE] no query/platform and no active session — gate3")
            return {"success": True, "message": "What would you like to play?"}

        # ── Step 1: Media type detection ───────────────────────
        mt = _detect_media_type(query)
        logger.info("[MEDIA_INTENT] query=%s content_type=%s platform=%s", query, mt, platform or "default")

        # ── Step 2: Platform-specific path ─────────────────────
        if platform:
            logger.info("[MM_TRACE] platform_path platform=%s", platform)
            prov = self._get_provider(platform)
            if not prov:
                logger.info("[MM_TRACE] platform_path provider_not_found")
                return {"success": False, "message": f"No provider available: {platform}"}
            try:
                logger.info("[MM_TRACE] invoking provider.play() platform=%s", platform)
                _rej_kw = {"rejected_ids": self._context.rejected_media_ids} if _is_rejection and self._context.rejected_media_ids else {}
                result = prov.play(query, media_type=mt, platform=platform, **_rej_kw)
                logger.info("[MM_TRACE] provider returned success=%s state=%s", result.success, result.session.state if result.session else "no_session")
                if self._playing(result):
                    self._last_execution_query = ql
                    self._last_execution_timestamp = now
                    logger.info("[MM_TRACE] registering PLAYING session")
                    self._register_session(platform, result)
                elif result.success and result.session:
                    logger.info("[MM_TRACE] registering non-PLAYING session (state=%s)", result.session.state.value)
                    self._register_session(platform, result)
                logger.info("[MM_TRACE] returning platform_result")
                return self._to_dict(result)
            except Exception as exc:
                logger.info("[MM_TRACE] platform_path exception: %s", exc)
                return {"success": False, "message": f"Playback on {platform} failed: {exc}"}

        # ── Step 3: Automatic selection — priority chain ───────
        priority = _CONTENT_TYPE_PRIORITY.get(mt, ["youtube"])
        # Filter to active providers only
        priority = [p for p in priority if p in self._ACTIVE_PROVIDERS]
        logger.info("[PROVIDER_SELECTION] content_type=%s provider_chain=%s", mt, priority)
        last_result = None
        last_provider = ""

        def _result_score(r: MediaResult) -> int:
            if not r or not r.success:
                return -1
            if r.session and r.session.state == MediaState.PLAYING:
                return 2
            if r.session and r.session.state in (MediaState.READY, MediaState.PAUSED):
                return 1
            return 0

        for provider_name in priority:
            logger.info("[MM_TRACE] attempting provider=%s", provider_name)
            prov = self._get_provider(provider_name)
            if not prov:
                logger.info("[MM_TRACE] provider_obj=None skipping name=%s", provider_name)
                continue
            logger.info("[MM_TRACE] provider_obj=%s", type(prov).__name__)
            try:
                logger.info("[MM_TRACE] invoking provider.play()")
                _rej_kw2 = {"rejected_ids": self._context.rejected_media_ids} if _is_rejection and self._context.rejected_media_ids else {}
                result = prov.play(query, media_type=mt, **_rej_kw2)
                logger.info("[MM_TRACE] provider returned=%s success=%s state=%s", type(result).__name__, result.success, result.session.state if result and result.session else "no_session")
                if self._playing(result):
                    self._last_execution_query = ql
                    self._last_execution_timestamp = now
                    logger.info("[MM_TRACE] PLAYING result — registering and returning")
                    self._register_session(provider_name, result)
                    return self._to_dict(result)
                if _result_score(result) > _result_score(last_result):
                    logger.info("[MM_TRACE] saving as best result (score=%d)", _result_score(result))
                    last_result = result
                    last_provider = provider_name
                # Media contract: a provider that ALREADY resolved the exact
                # media (exact video id / tab) must not have its failure
                # masked by falling back to another provider (e.g. a generic
                # browser search page). Stop the chain and report truthfully.
                if getattr(result, "no_fallback", False) and not self._playing(result):
                    logger.info("[MM_TRACE] provider resolved exact media — stopping fallback chain")
                    break
            except Exception as exc:
                logger.warning("[MM] %s.play failed: %s", provider_name, exc)
                continue

        if last_result:
            logger.info("[MM_TRACE] returning best_result provider=%s", last_provider)
            self._register_session(last_provider, last_result)
            return self._to_dict(last_result)

        logger.info("[MM_TRACE] returning gate3 — no provider succeeded")
        query_clean = query.rstrip(".!?;:,") if query else ""
        if query_clean:
            _prov = self._get_provider("youtube")
            if _prov:
                try:
                    _mt = _detect_media_type(query)
                    _rej_kw3 = {"rejected_ids": self._context.rejected_media_ids} if _is_rejection and self._context.rejected_media_ids else {}
                    _result = _prov.play(query, media_type=_mt, platform="youtube", **_rej_kw3)
                    # Surface any truthful provider outcome with a session —
                    # incl. the no-connector fallback that opened the actual
                    # video in the default browser (state=IDLE, can't verify).
                    if _result and _result.success and _result.session:
                        self._register_session("youtube", _result)
                        return self._to_dict(_result)
                except Exception:
                    pass
            # Media contract: never echo an internal URL back at the user.
            # A user-supplied URL is parsed as input; the response uses a
            # natural label instead.
            _label = user_facing_media_label(query_clean) or "the requested media"
            return {"success": False, "message": f"I found {_label}, but playback could not be verified."}
        return {"success": False, "message": "Nothing to play."}

    def now_playing(self) -> dict:
        """Capability C: report the CURRENT media entity truthfully.

        Reads the live media registry (not a cached claim) and answers with the
        actual session label + state. Never invents a "playing" state.
        """
        logger.info("[MM] action=now_playing")
        active = self._registry.get_active_by_player()
        if not active:
            return {"success": False, "message": "Nothing is playing right now."}
        _pname, session = active
        # Use actual title + artist/channel, not the search query
        _title = session.title or ""
        _artist = session.artist or ""
        # Clean title: strip " - YouTube" suffix
        import re as _re
        _clean_title = _re.sub(r"\s*[-|]\s*YouTube\s*$", "", _title).strip() if _title else ""
        if _clean_title:
            display = f"{_clean_title} by {_artist}" if _artist else _clean_title
        elif session.query:
            from mini_kio.media.media_session import user_facing_media_label
            display = user_facing_media_label(session.query) or session.query
        else:
            display = session.domain_hint or "media"
        state = session.state.value
        if state == MediaState.PLAYING.value:
            return {"success": True, "message": f"Playing {display}."}
        if state == MediaState.PAUSED.value:
            return {"success": True, "message": f"Paused on {display}."}
        return {"success": True, "message": f"Loaded {display} (ready to play)."}

    # BUG 2: pause/resume user-facing replies are clean, but the full state
    # object (session) and verification remain internally intact. A failed
    # operation is never converted into "Paused." / "Resumed.".
    @_serialize_media_op
    def pause(self, domain_hint: str = "") -> dict:
        logger.info("[MEDIA_INTENT] action=pause")
        active = self._registry.get_active_by_player()
        if active:
            pname, session = active
            logger.info("[PLAYER_STATE_BEFORE] player=%s state=%s", pname, session.state.value)
            prov = self._get_provider(pname)
            if prov:
                result = prov.pause()
                if result.success:
                    state = MediaState.PAUSED
                    if result.session:
                        state = result.session.state
                    self._registry.update_state(pname, state)
                    logger.info("[PLAYER_STATE_AFTER] action=pause state=%s verified=%s", state.value, state == MediaState.PAUSED)
                    self._log_media_state("pause")
                    d = self._to_dict(result)
                    d["message"] = "Paused."
                    return d
                return {"success": False, "message": result.error or "Pause failed."}

        prov = self._get_provider("browser")
        if prov:
            result = prov.pause()
            if result.success:
                self._register_session("browser", result)
                self._log_media_state("pause")
                d = self._to_dict(result)
                d["message"] = "Paused."
                return d
            return {"success": False, "message": result.error or "Pause failed."}

        return {"success": False, "message": "No media to pause."}

    @_serialize_media_op
    def resume(self, domain_hint: str = "") -> dict:
        logger.info("[MEDIA_INTENT] action=resume")
        active = self._registry.get_active_by_player()
        if active:
            pname, session = active
            logger.info("[PLAYER_STATE_BEFORE] player=%s state=%s", pname, session.state.value)
            prov = self._get_provider(pname)
            if prov:
                result = prov.resume()
                if result.success:
                    state = MediaState.PLAYING
                    if result.session:
                        state = result.session.state
                    self._registry.update_state(pname, state)
                    logger.info("[PLAYER_STATE_AFTER] action=resume state=%s verified=%s", state.value, state == MediaState.PLAYING)
                    self._log_media_state("resume")
                    d = self._to_dict(result)
                    d["message"] = "Resumed."
                    return d
                return {"success": False, "message": result.error or "Resume failed."}

        prov = self._get_provider("browser")
        if prov:
            result = prov.resume()
            if result.success:
                self._register_session("browser", result)
                self._log_media_state("resume")
                d = self._to_dict(result)
                d["message"] = "Resumed."
                return d
            return {"success": False, "message": result.error or "Resume failed."}

        return {"success": False, "message": "No media to resume."}

    @_serialize_media_op
    def stop(self, domain_hint: str = "") -> dict:
        logger.info("[MEDIA_INTENT] action=stop")
        active = self._registry.get_active_by_player()
        if active:
            pname, session = active
            logger.info("[PLAYER_STATE_BEFORE] player=%s state=%s", pname, session.state.value)
            prov = self._get_provider(pname)
            if prov:
                result = prov.stop()
                if result.success:
                    state = MediaState.STOPPED
                    if result.session:
                        state = result.session.state
                    self._registry.update_state(pname, state)
                    logger.info("[PLAYER_STATE_AFTER] action=stop state=%s verified=%s", state.value, state == MediaState.STOPPED)
                    self._log_media_state("stop")
                    d = self._to_dict(result)
                    d["message"] = "Stopped."
                    return d
                return {"success": False, "message": result.error or "Stop failed."}
        return {"success": False, "message": "No media to stop."}

    @_serialize_media_op
    def next_track(self) -> dict:
        logger.info("[MEDIA_INTENT] action=next")
        active = self._registry.get_active_by_player()
        if active:
            pname, session_before = active
            logger.info("[PROVIDER_SELECTION] player=%s media_id_before=%s",
                        pname, (session_before.url or session_before.title or "")[:80])
            prov = self._get_provider(pname)
            if prov:
                result = prov.next_track()
                if result.success:
                    # Ensure playback actually resumes after navigation.
                    # The provider verified URL change; now verify play state.
                    if result.session and result.session.state != MediaState.PLAYING:
                        try:
                            prov.resume()
                        except Exception:
                            pass
                    media_after = (result.session.url or result.session.title or "") if result.session else ""
                    logger.info("[MEDIA_STATE] action=next media_id_after=%s player_state=%s",
                                media_after[:80], result.session.state.value if result.session else "unknown")
                    self._log_media_state("next")
                    d = self._to_dict(result)
                    d["message"] = "Next track."
                    return d
                return {"success": False, "message": result.error or "Couldn't switch to next track."}
        return {"success": False, "message": "No active media session for next track."}

    @_serialize_media_op
    def previous_track(self) -> dict:
        logger.info("[MEDIA_INTENT] action=previous")
        active = self._registry.get_active_by_player()
        if active:
            pname, session_before = active
            logger.info("[PROVIDER_SELECTION] player=%s media_id_before=%s",
                        pname, (session_before.url or session_before.title or "")[:80])
            prov = self._get_provider(pname)
            if prov:
                result = prov.previous_track()
                if result.success:
                    # Ensure playback actually resumes after navigation.
                    if result.session and result.session.state != MediaState.PLAYING:
                        try:
                            prov.resume()
                        except Exception:
                            pass
                    media_after = (result.session.url or result.session.title or "") if result.session else ""
                    logger.info("[MEDIA_STATE] action=previous media_id_after=%s player_state=%s",
                                media_after[:80], result.session.state.value if result.session else "unknown")
                    self._log_media_state("previous")
                    d = self._to_dict(result)
                    d["message"] = "Previous track."
                    return d
                return {"success": False, "message": result.error or "Couldn't switch to previous track."}
        return {"success": False, "message": "No active media session for previous track."}

    # BUG 3: mute/unmute route through the ACTIVE provider (which owns the
    # extension `mute`/`unmute` scripts) and the state is verified — the
    # reply is only sent when the player actually reports muted/unmuted.
    @_serialize_media_op
    def mute(self, domain_hint: str = "") -> dict:
        logger.info("[MM] action=mute")
        active = self._registry.get_active_by_player()
        if active:
            pname, _ = active
            prov = self._get_provider(pname)
            if prov and hasattr(prov, "mute"):
                result = prov.mute()
                if result.success:
                    if result.session and result.session.muted is True:
                        self._log_media_state("mute")
                        return {"success": True, "message": "Muted."}
                    return {"success": False, "message": "Mute not verified on the player."}
                return {"success": False, "message": result.error or "Mute failed."}

        prov = self._get_provider("browser")
        if prov and hasattr(prov, "mute"):
            result = prov.mute()
            if result.success:
                self._log_media_state("mute")
                return {"success": True, "message": "Muted."}
            return {"success": False, "message": result.error or "Mute failed."}
        return {"success": False, "message": "No media to mute."}

    @_serialize_media_op
    def unmute(self, domain_hint: str = "") -> dict:
        logger.info("[MM] action=unmute")
        active = self._registry.get_active_by_player()
        if active:
            pname, _ = active
            prov = self._get_provider(pname)
            if prov and hasattr(prov, "unmute"):
                result = prov.unmute()
                if result.success:
                    if result.session and result.session.muted is False:
                        self._log_media_state("unmute")
                        return {"success": True, "message": "Unmuted."}
                    return {"success": False, "message": "Unmute not verified on the player."}
                return {"success": False, "message": result.error or "Unmute failed."}

        prov = self._get_provider("browser")
        if prov and hasattr(prov, "unmute"):
            result = prov.unmute()
            if result.success:
                self._log_media_state("unmute")
                return {"success": True, "message": "Unmuted."}
            return {"success": False, "message": result.error or "Unmute failed."}
        return {"success": False, "message": "No media to unmute."}

    @_serialize_media_op
    def volume_up(self, domain_hint: str = "") -> dict:
        logger.info("[MM] action=volume_up")
        prov = self._get_provider("browser")
        if prov:
            result = prov.volume(direction="up")
            if result.success:
                self._log_media_state("volume_up")
                return self._to_dict(result)
        return {"success": True, "message": "No media to adjust."}

    @_serialize_media_op
    def volume_down(self, domain_hint: str = "") -> dict:
        logger.info("[MM] action=volume_down")
        prov = self._get_provider("browser")
        if prov:
            result = prov.volume(direction="down")
            if result.success:
                self._log_media_state("volume_down")
                return self._to_dict(result)
        return {"success": True, "message": "No media to adjust."}

    @_serialize_media_op
    def set_volume(self, level: int) -> dict:
        logger.info("[MM] action=set_volume level=%d", level)
        # Convert 0-100 to 0.0-1.0
        float_level = max(0.0, min(1.0, level / 100.0))
        
        active = self._registry.get_active_by_player()
        if active:
            pname, _ = active
            prov = self._get_provider(pname)
            if prov:
                result = prov.volume(level=float_level)
                if result.success:
                    self._log_media_state(f"set_volume_{level}")
                    return self._to_dict(result)

        prov = self._get_provider("browser")
        if prov:
            result = prov.volume(level=float_level)
            if result.success:
                self._log_media_state(f"set_volume_{level}")
                return self._to_dict(result)
        return {"success": True, "message": "No media to adjust."}

    @_serialize_media_op
    def seek(self, seconds: int) -> dict:
        logger.info("[MM] action=seek seconds=%d", seconds)
        self._log_media_state("before_seek")
        active = self._registry.get_active_by_player()
        if active:
            pname, _ = active
            prov = self._get_provider(pname)
            if prov:
                result = prov.seek(seconds)
                if result.success:
                    self._log_media_state("seek")
                    return self._to_dict(result)
                return {"success": True, "message": "Seek not supported for this player."}
        return {"success": True, "message": "No active media to seek."}

    @_serialize_media_op
    def seek_forward(self, domain_hint: str = "", seconds: int = 10) -> dict:
        return self.seek(seconds)

    @_serialize_media_op
    def seek_backward(self, domain_hint: str = "", seconds: int = 10) -> dict:
        return self.seek(-seconds)

    @_serialize_media_op
    def search(self, query: str, platform: str = "") -> dict:
        if platform:
            prov = self._get_provider(platform)
            if prov:
                result = prov.search(query)
                self._register_search_candidate(platform, query, result)
                return self._to_dict(result)
        return {"success": False, "message": "No provider for search."}

    def _register_search_candidate(self, provider_name: str, query: str, result) -> None:
        """Register a successful search's best candidate so follow-up
        references ('play it', 'play again') resolve to it (E/F/G support).

        The search page stays open in the controlled connector world; the
        candidate becomes the current media context and the remembered entity.
        """
        if not (result and getattr(result, "success", False)):
            return
        try:
            candidates = list(getattr(result, "candidates", None) or [])
            if not candidates:
                return
            cand = candidates[0]
            # RC6: refuse to persist garbage candidates (scraped page text or
            # markdown-link dumps) as the canonical search reference.
            if not (self._is_sane_media_query(cand.title or query)
                    and self._is_sane_media_url(cand.url or "")):
                logger.warning("[MM_SEARCH_REGISTER] skipping garbage candidate title=%r url=%r",
                               (cand.title or "")[:60], (cand.url or "")[:80])
                return
            self._context.set_current(cand)
            self._context.last_query = query
            if self._intelligence_adapter is None:
                return
            from mini_kio.media.intelligence.media_entity_memory import (
                ResolvedEntity, EntityType, MediaProvider, HistoricalMediaSession,
            )
            import time as _t
            m_map = {
                MediaType.MUSIC: EntityType.SONG,
                MediaType.VIDEO: EntityType.YOUTUBER,
                MediaType.TRAILER: EntityType.MOVIE,
                MediaType.TUTORIAL: EntityType.YOUTUBER,
            }
            etype = m_map.get(cand.media_type, EntityType.SONG)
            p_map = {
                "youtube": MediaProvider.YOUTUBE,
                "browser": MediaProvider.BROWSER,
            }
            entity = ResolvedEntity(
                name=cand.title or query,
                entity_type=etype,
                provider=p_map.get(provider_name, MediaProvider.UNKNOWN),
                url=cand.url,
                metadata={"query": query, "platform": provider_name},
            )
            self._intelligence_adapter._mem.push_session(HistoricalMediaSession(
                session_id=str(int(_t.time())), entity=entity, started_at=_t.time(),
            ))
            self._intelligence_adapter.context.set_subject(entity.name)
            logger.info("[MM_SEARCH_REGISTER] candidate=%s entity=%s", cand.title, entity.name)
        except Exception as exc:
            logger.warning("[MM_SEARCH_REGISTER] failed: %s", exc)

    def resolve_query(self, text: str) -> Optional[str]:
        return self._context.resolve_reference(text)

    def _detect_transport(self, text: str) -> Optional[dict]:
        text_stripped = text.strip()
        # Standalone "stop" (short message) is a media command.
        # Longer messages containing "stop" as a word are NOT media commands.
        is_short = len(text_stripped) < 20
        is_standalone_stop = is_short and text_stripped.lower() in ("stop", "stop.", "stop!", "stop it", "stop that")

        for pattern, command in _TRANSPORT_PATTERNS.items():
            if pattern.search(text):
                dispatch = {
                    "pause": self.pause, "resume": self.resume,
                    "stop": self.stop, "next": self.next_track,
                    "previous": self.previous_track,
                    "mute": self.mute, "unmute": self.unmute,
                    "shuffle": lambda: {"success": True, "message": "shuffle."},
                    "repeat": lambda: {"success": True, "message": "repeat."},
                }
                fn = dispatch.get(command)
                if fn:
                    return fn()
                return {"success": True, "message": f"{command}."}
        # Standalone short "stop" without media context words
        if is_standalone_stop:
            return self.stop()
        return None

    def _detect_volume(self, text: str) -> Optional[dict]:
        delta = _parse_volume_delta(text)
        if delta is None:
            return None
        if delta > 0:
            return self.volume_up()
        if delta < 0:
            return self.volume_down()
        return {"success": True, "message": "Volume adjusted."}

    def _log_media_state(self, action: str):
        active = self._registry.get_active()
        if active:
            if isinstance(active, tuple):
                _, s = active
            else:
                s = active
            logger.info("[MEDIA_STATE] action=%s state=%s volume=%s position_s=%s duration_s=%s",
                        action, s.state.value if s.state else "none", s.volume,
                        s.position_s, s.duration_s)

    def get_context(self) -> MediaContext:
        return self._context

    def get_registry(self) -> MediaRegistry:
        return self._registry

    def get_discovery(self) -> MediaDiscovery:
        return self._discovery

    def get_recommender(self) -> MediaRecommender:
        return self._recommender

    def process_nl_seek(self, text: str) -> Optional[dict]:
        seconds = _parse_seek(text)
        if seconds is not None:
            return self.seek(seconds)
        return None

    @_serialize_media_op
    def process_followup(self, text: str) -> Optional[dict]:
        from mini_kio.media.intelligence.artifact_memory import parse_artifact_type
        tl = text.lower().strip()
        # Normalize artifact typos
        for typo, correct in _ARTIFACT_TYPOS.items():
            if typo in tl:
                tl = tl.replace(typo, correct)
                logger.info("[QUERY_NORMALIZED] typo=%s -> %s", typo, correct)

        # Priority 1: Event reference resolution (exploit context before search)
        if self._context.recent_events:
            event_ref_patterns = ["what happened", "tell me about", "tell me more",
                                  "who scored", "how did", "the first", "the second",
                                  "the third", "that match", "that game", "what happened there"]
            if any(p in tl for p in event_ref_patterns):
                ev = self._resolve_event_reference(tl)
                if ev:
                    logger.info("[MEDIA_CONTEXT_RESOLVE] resolved event reference: canonical=%s status=%s",
                                ev["canonical_name"], ev["status"])
                    if ev["status"] == "COMPLETED":
                        narrative = self._build_sports_narrative([ev], [])
                        msg_lines = [narrative] if narrative else [ev["canonical_name"]]
                    elif ev["status"] == "UPCOMING":
                        msg_lines = [ev["canonical_name"], "", "Match hasn't started yet."]
                    else:
                        msg_lines = [ev["canonical_name"], "", "Match is live."]
                    if ev["status"] != "UPCOMING":
                        msg_lines.append("")
                        msg_lines.append(self._build_offer_line())
                    return {"success": True, "message": "\n".join(msg_lines)}
                # No event match — fall through to search

        # Priority 2: Artifact-specific triggers (resolve pending context without needing "play/show" prefix)
        _artifact_triggers = ("trailer", "highlights", "gameplay", "music video",
                              "trailer pls", "highlights pls", "gameplay pls",
                              "clips", "clip", "interview", "behind the scenes",
                              "behind-the-scenes", "bts", "audiobook", "live performance")
        if any(t in tl for t in _artifact_triggers):
            # Only use pending context when the artifact type matches what user is asking for
            if self._context.pending_action == "play_media" and self._context.pending_media_query:
                _matched_type = self._context.artifact_type or ""
                _query_type = parse_artifact_type(tl)
                if _query_type and _matched_type and _query_type.value == _matched_type:
                    logger.info("[MEDIA_CONTEXT_RESOLVE] artifact=%s query=%s trigger=%s",
                                self._context.artifact_type, self._context.pending_media_query, tl)
                    q = self._context.pending_media_query
                    self._register_current_artifact()
                    result = self.play(q)
                    if result.get("success") and not self._is_platform_choice(result):
                        self._context.pending_action = ""
                        self._context.pending_media_query = ""
                    else:
                        logger.info("[MEDIA_CONTEXT_RESOLVE] play deferred — pending context preserved")
                    return result
                # Artifact type mismatch — clear stale pending context
                self._context.pending_action = ""
                self._context.pending_media_query = ""
                self._context.artifact_type = ""
            # No matching pending artifact — try artifact memory
            artifact_result = self._resolve_via_artifact_memory(tl)
            if artifact_result:
                self._register_current_artifact()
                return artifact_result

        # Priority 3: Pending media context from info query
        if tl in ("yes", "yeah", "sure", "ok", "okay", "play it", "play that",
                  "show it", "watch it", "do it", "go ahead", "show me"):
            if self._context.pending_action == "play_media" and self._context.pending_media_query:
                logger.info("[MEDIA_CONTEXT_RESOLVE] resolving pending action=%s query=%s",
                            self._context.pending_action, self._context.pending_media_query)
                q = self._context.pending_media_query
                self._context.pending_action = ""
                self._context.pending_media_query = ""
                self._register_current_artifact()
                return self.play(q)
            if self._context.media_candidate:
                logger.info("[MM_INTELLIGENCE] Resolving affirmative to media_candidate: %s", self._context.media_candidate)
                return self.play(self._context.media_candidate)
            # Sports "play it" with event context
            if self._context.recent_events and self._context.topic == "SPORTS":
                for ev in self._context.recent_events:
                    if ev["status"] == "COMPLETED":
                        q = self._build_artifact_query("", "highlights", ev)
                        logger.info("[EVENT_MEDIA_RESOLVE] event=%s artifact=%s query=%s",
                                    ev.get("canonical_name", ""), "highlights", q)
                        return self.play(q)
            # No pending or event — try artifact memory
            artifact_result = self._resolve_via_artifact_memory(tl)
            if artifact_result:
                return artifact_result

        # Priority 4: Generic artifact request resolved from event context
        if self._context.recent_events and self._context.topic == "SPORTS":
            artifact = None
            if "highlight" in tl:
                artifact = "highlights"
            elif "trailer" in tl:
                artifact = "trailer"
            elif "gameplay" in tl:
                artifact = "gameplay"
            elif "music video" in tl:
                artifact = "music video"
            if artifact:
                ev = self._resolve_event_reference(tl)
                if not ev:
                    for e in self._context.recent_events:
                        if e["status"] == "COMPLETED":
                            ev = e
                            break
                if ev:
                    q = self._build_artifact_query(ev.get("entity_a", ""), artifact, ev)
                    logger.info("[EVENT_MEDIA_RESOLVE] event=%s artifact=%s query=%s",
                                ev.get("canonical_name", ""), artifact, q)
                    return self.play(q)

        # Priority 5: Artifact memory resolution (before fresh retrieval)
        artifact_result = self._resolve_via_artifact_memory(tl)
        if artifact_result:
            return artifact_result

        # Priority 6: Artifact-specific play commands
        if any(p in tl for p in ("play highlight", "show highlight", "watch highlight")):
            if self._context.pending_media_query and "highlight" in self._context.pending_media_query.lower():
                q = self._context.pending_media_query
                self._context.pending_media_query = ""
                return self.play(q)
            if self._context.last_completed_match:
                return self.play(f"{self._context.last_completed_match} highlights")
            if self._context.entity and self._context.topic == "SPORTS":
                return self.play(f"{self._context.entity.replace('_', ' ')} highlights")
            # Use the first completed event if available
            for ev in self._context.recent_events:
                if ev["status"] == "COMPLETED":
                    return self.play(f"{ev['canonical_name']} highlights")

        if any(p in tl for p in ("play trailer", "show trailer", "watch trailer")):
            if self._context.pending_media_query:
                q = self._context.pending_media_query
                self._context.pending_media_query = ""
                return self.play(q)
            if self._context.media_candidate and "trailer" in self._context.media_candidate.lower():
                return self.play(self._context.media_candidate)
            if self._context.entity and self._context.topic in ("MOVIES", "TV"):
                return self.play(f"{self._context.entity.replace('_', ' ')} official trailer")

        if any(p in tl for p in ("interview", "show interview", "watch interview")):
            logger.info("[FOLLOWUP_ARTIFACT] matched=interview tl=%s entity=%s", tl, self._context.entity)
            if self._context.entity:
                entity = self._context.entity.replace('_', ' ')
                return self.play(f"{entity} interview", platform="youtube")
            if self._context.pending_media_query:
                q = self._context.pending_media_query
                self._context.pending_media_query = ""
                return self.play(q)

        if any(p in tl for p in ("behind the scenes", "behind-the-scenes", "show behind", "bts")):
            logger.info("[FOLLOWUP_ARTIFACT] matched=behind_the_scenes tl=%s entity=%s", tl, self._context.entity)
            if self._context.entity:
                entity = self._context.entity.replace('_', ' ')
                return self.play(f"{entity} behind the scenes", platform="youtube")
            if self._context.pending_media_query:
                q = self._context.pending_media_query
                self._context.pending_media_query = ""
                return self.play(q)

        if any(p in tl for p in ("audiobook", "audio book", "open audiobook")):
            logger.info("[FOLLOWUP_ARTIFACT] matched=audiobook tl=%s entity=%s", tl, self._context.entity)
            if self._context.entity:
                entity = self._context.entity.replace('_', ' ')
                return self.play(f"{entity} audiobook", platform="youtube")
            if self._context.pending_media_query:
                q = self._context.pending_media_query
                self._context.pending_media_query = ""
                return self.play(q)

        if any(p in tl for p in ("live performance", "live concert", "show live")):
            logger.info("[FOLLOWUP_ARTIFACT] matched=live_performance tl=%s entity=%s", tl, self._context.entity)
            if self._context.entity:
                entity = self._context.entity.replace('_', ' ')
                return self.play(f"{entity} live performance", platform="youtube")

        # Priority 6: Standings / fixtures / team updates
        if self._context.topic == "SPORTS" and self._context.recent_events:
            if tl in ("standings", "show standings", "table"):
                return {"success": True, "message": "Standings data needs a fresh search. Querying now...",
                        "_needs_search": True, "_search_query": f"{self._context.last_query} standings"}
            if tl in ("fixtures", "show fixtures", "schedule"):
                return {"success": True, "message": "Fetching fixtures..."}
            # Team-specific update: "scotland updates", "brazil updates"
            for ev in self._context.recent_events:
                for entity in (ev["entity_a"].lower(), ev["entity_b"].lower()):
                    if f"{entity} update" in tl or entity in tl:
                        return {"success": True, "message": f"Fetching latest on {entity.title()}...",
                                "_needs_search": True, "_search_query": f"{entity} football"}

        # Priority 7: Intelligence adapter contextual resolution
        if self._intelligence_adapter:
            try:
                last_subject = self._intelligence_adapter.get_last_subject()
                if last_subject and not any(kw in tl for kw in ("play ", "watch ")):
                    _intel_res = self._intelligence_adapter.handle_contextual_query(tl)
                    if _intel_res and _intel_res.response_text:
                        logger.info("[MM_INTELLIGENCE] contextual query resolved subject=%s source=%s",
                                    last_subject, _intel_res.source)
                        return {"success": True, "message": _intel_res.response_text}
            except Exception:
                logger.warning("[MM_INTELLIGENCE] contextual query failed", exc_info=True)

        # ── inlined transport / volume / offer detection ─────────────────
        transport = self._detect_transport(text)
        if transport:
            return transport
        volume = self._detect_volume(text)
        if volume:
            return volume
        if self._offer_manager.has_pending_offer():
            result = self._offer_manager.parse_response(text)
            if result is True:
                return self.accept_intelligence_offer()
            if result is False:
                return {"success": True, "message": "Offer skipped."}
        return None

    def process_opportunity(self, query: str) -> Optional[dict]:
        opp = self._opportunity_engine.detect(query)
        if not opp:
            return None
        return {
            "entity_name": opp.entity_name,
            "opportunity_type": opp.opportunity_type.value,
            "search_query": opp.search_query,
            "display_question": opp.to_display_question(),
        }

    def _artifact_for_topic(self) -> str:
        t = self._context.topic
        if t == "SPORTS":
            status = self._context.match_status
            if status == "UPCOMING":
                return MediaArtifactType.NEWS_SUMMARY.value
            if status == "LIVE":
                return MediaArtifactType.LIVE_COVERAGE.value
            return MediaArtifactType.HIGHLIGHTS.value
        if t in ("MOVIES", "TV"):
            return MediaArtifactType.TRAILER.value
        if t == "MUSIC":
            return MediaArtifactType.MUSIC_VIDEO.value
        if t == "GAMING":
            return MediaArtifactType.GAMEPLAY.value
        if t == "TECH":
            return MediaArtifactType.HANDS_ON.value
        if t == "BOOKS":
            return MediaArtifactType.AUDIOBOOK.value
        return MediaArtifactType.HIGHLIGHTS.value

    def _emoji_for_topic(self) -> str:
        try:
            from mini_kio.media.intelligence.media_response_formatter import _TOPIC_EMOJI
            from mini_kio.media.intelligence.media_intelligence_models import TopicType
            tm = {"SPORTS": TopicType.SPORTS, "MOVIES": TopicType.MOVIES,
                  "TV": TopicType.MOVIES, "MUSIC": TopicType.MUSIC,
                  "GAMING": TopicType.GAMING, "TECH": TopicType.TECH}
            tt = tm.get(self._context.topic)
            if tt:
                return _TOPIC_EMOJI.get(tt, "\U0001f4f0")
        except Exception:
            pass
        return self._emoji_for_topic_old()

    def _emoji_for_topic_old(self) -> str:
        t = self._context.topic
        if t == "SPORTS":
            return "\u26bd"
        if t in ("MOVIES", "TV"):
            return "\U0001f3ac"
        if t == "MUSIC":
            return "\U0001f3b5"
        if t == "GAMING":
            return "\U0001f3ae"
        if t == "TECH":
            return "\U0001f4bb"
        return "\U0001f4f0"

    def _entity_display(self) -> str:
        e = self._context.entity
        if e:
            return e.replace("_", " ").title()
        return ""

    def _build_media_query(self) -> str:
        e = self._context.entity
        topic = self._context.topic
        display = self._entity_display()
        if topic == "SPORTS":
            status = self._context.match_status
            if status == "UPCOMING":
                return ""
            event = self._context.event
            if event:
                return f"{event.replace('_', ' ').title()} highlights"
            if display:
                return f"{display} highlights"
            return f"{self._context.last_query} highlights"
        if topic in ("MOVIES", "TV"):
            if display:
                return f"{display} official trailer"
            return f"{self._context.last_query} official trailer"
        if topic == "MUSIC":
            if display:
                return f"{display} music video"
            return f"{self._context.last_query} music video"
        if topic == "GAMING":
            if display:
                return f"{display} gameplay"
            return f"{self._context.last_query} gameplay"
        if topic == "TECH":
            if display:
                return f"{display} hands-on"
            return f"{self._context.last_query} hands-on"
        return f"{self._context.last_query}"

    def _build_artifact_query(self, entity: str, artifact_type: str, event: Optional[dict] = None) -> str:
        if event:
            canon = event.get("canonical_name", "") or f"{event.get('entity_a', '')} vs {event.get('entity_b', '')}"
            if canon:
                return f"{canon} {artifact_type}"
        if entity:
            e = entity.replace("_", " ")
            if artifact_type == "trailer":
                return f"{e} official trailer"
            return f"{e} {artifact_type}"
        return ""

    def _store_pending_context(self, media_query: str, action: str, artifact_type: str):
        if not media_query or not action:
            logger.info("[MEDIA_CONTEXT_SKIP_EMPTY] query=%r action=%r artifact=%s", media_query, action, artifact_type)
            self._context.pending_media_query = ""
            self._context.pending_action = ""
            self._context.artifact_type = ""
            self._context.current_topic = ""
            return
        self._context.pending_media_query = media_query
        self._context.pending_action = action
        self._context.artifact_type = artifact_type
        self._context.current_topic = media_query
        logger.info("[MEDIA_CONTEXT_STORE] query=%s action=%s artifact=%s", media_query, action, artifact_type)
        if artifact_type and media_query and action:
            self._register_current_artifact()

    def _extract_sports_events(self, raw_text: str) -> list[dict]:
        try:
            from mini_kio.media.intelligence.sports_event_extractor import extract_events as _new_extract
            from mini_kio.media.intelligence.media_intelligence_models import EventRecord
            records = _new_extract(raw_text)
            if records:
                result = [_event_record_to_legacy_dict(r) for r in records]
                if result:
                    return result
        except Exception:
            pass
        return self._extract_sports_events_old(raw_text)

    def _extract_sports_events_old(self, raw_text: str) -> list[dict]:
        events = []
        tl = raw_text.lower()

        # Completed matches with scores: "Brazil 1-1 Morocco"
        score_pattern = re.compile(r'([A-Za-z]\S*(?:\s+[A-Za-z]\S*)?)\s+(\d+[–\-]\d+)\s+([A-Za-z]\S*(?:\s+[A-Za-z]\S*)?)')
        for m in score_pattern.finditer(raw_text):
            a = m.group(1).strip().title()
            b = m.group(3).strip().title()
            score = m.group(2)
            canonical = f"{a} vs {b}"
            events.append({
                "entity_a": a, "entity_b": b, "score": score,
                "event_type": "match", "canonical_name": canonical,
                "status": "COMPLETED", "raw_text": m.group(0).strip(),
            })

        # "X beat Y", "X defeated Y", "X won against Y"
        result_pattern = re.compile(r'([A-Za-z]\S*(?:\s+[A-Za-z]\S*)?)\s+(beat|defeated|won against|drew with|drawn with)\s+([A-Za-z]\S*(?:\s+[A-Za-z]\S*)?)', re.IGNORECASE)
        for m in result_pattern.finditer(raw_text):
            a = m.group(1).strip().title()
            b = m.group(3).strip().title()
            canonical = f"{a} vs {b}"
            if not any(e["canonical_name"] == canonical and e["event_type"] == "match" for e in events):
                events.append({
                    "entity_a": a, "entity_b": b, "score": "",
                    "event_type": "match", "canonical_name": canonical,
                    "status": "COMPLETED", "raw_text": m.group(0).strip(),
                })

        # Upcoming fixtures: "X vs Y"
        upcoming_idx = raw_text.lower().find("coming up")
        if upcoming_idx >= 0:
            after = raw_text[upcoming_idx + 9:]
        elif "upcoming" in tl:
            after = raw_text
        else:
            after = ""

        if after:
            fixture_pattern = re.compile(r'([A-Za-z]\S*(?:\s+[A-Za-z]\S*)?)\s+(?:vs\.?|v|V)\s+([A-Za-z]\S*(?:\s+[A-Za-z]\S*)?)')
            for m in fixture_pattern.finditer(after):
                a = m.group(1).strip().title()
                b = m.group(2).strip().title()
                canonical = f"{a} vs {b}"
                if not any(e["canonical_name"] == canonical for e in events):
                    events.append({
                        "entity_a": a, "entity_b": b, "score": "",
                        "event_type": "match", "canonical_name": canonical,
                        "status": "UPCOMING", "raw_text": m.group(0).strip(),
                    })

        # Mark events as LIVE if match_status says LIVE
        if self._context.match_status == "LIVE" and events:
            for e in events:
                if e["status"] != "COMPLETED":
                    e["status"] = "LIVE"

        return events

    def _extract_standings(self, raw_text: str) -> list[dict]:
        teams = []
        # Pattern: "1. Mexico 3 1 0 0 3" or "Mexico 3 1 0 0 3" (pos, team, pts, w, d, l, gd)
        lines = raw_text.split("\n")
        for line in lines:
            stripped = line.strip()
            if not stripped:
                continue
            # Skip header lines
            if any(h in stripped.lower() for h in ("team", "pld", "mp", "pts", "gp",
                                                     "w", "d", "l", "gd", "gf", "ga",
                                                     "position", "pos", "#", "club", "nation")):
                continue
            # Try numbered standings: "1. Mexico 3 1 0 0 +3" or "1. Mexico 3pts"
            m = re.match(r'^\d+[\.\)]?\s+([A-Za-z][A-Za-z\s]+?)\s+(\d+)\s+(\d+)\s+(\d+)\s+(\d+)\s+([+-]?\d+)', stripped)
            if m:
                name = m.group(1).strip()
                pts = int(m.group(2))
                w = int(m.group(3))
                d = int(m.group(4))
                l = int(m.group(5))
                gd = m.group(6)
                teams.append({"name": name, "points": pts, "wins": w, "draws": d, "losses": l, "gd": gd})
                continue
            # Try unnumbered: "Mexico 3 1 0 0 +3"
            m = re.match(r'^([A-Za-z][A-Za-z\s]+?)\s+(\d+)\s+(\d+)\s+(\d+)\s+(\d+)\s+([+-]?\d+)', stripped)
            if m:
                name = m.group(1).strip()
                pts = int(m.group(2))
                w = int(m.group(3))
                d = int(m.group(4))
                l = int(m.group(5))
                gd = m.group(6)
                teams.append({"name": name, "points": pts, "wins": w, "draws": d, "losses": l, "gd": gd})
                continue
            # Minimal: "Mexico 3 pts" or "Mexico — 3"
            m = re.match(r'^([A-Za-z][A-Za-z\s]+?)\s+[–\-—]\s*(\d+)', stripped)
            if m:
                name = m.group(1).strip()
                pts = int(m.group(2))
                teams.append({"name": name, "points": pts})
            elif re.match(r'^[A-Za-z]', stripped):
                m2 = re.match(r'^([A-Za-z][A-Za-z\s]+?)\s+(\d+)\s', stripped)
                if m2:
                    name = m2.group(1).strip()
                    pts = int(m2.group(2))
                    teams.append({"name": name, "points": pts})
        return teams[:8]  # Max top 8

    def _resolve_event_reference(self, text: str) -> Optional[dict]:
        tl = text.lower().strip()
        events = self._context.recent_events
        if not events:
            return None

        # Ordinal: "the first match", "the second match"
        ordinal_map = {"first": 0, "second": 1, "third": 2, "fourth": 3, "fifth": 4}
        for word, idx in ordinal_map.items():
            if word in tl and idx < len(events):
                return events[idx]

        # Team name lookup
        for e in events:
            a_lower = e["entity_a"].lower()
            b_lower = e["entity_b"].lower()
            if a_lower in tl or b_lower in tl:
                return e
            if e["canonical_name"].lower() in tl:
                return e

        # "that match", "that game", "the match"
        if any(p in tl for p in ["that match", "that game", "the match", "there"]):
            return events[0]

        return None

    def _is_media_eligible(self) -> bool:
        eligible_topics = {"MOVIES", "TV", "MUSIC", "GAMING", "TECH"}
        return self._context.topic in eligible_topics

    def _topic_str_to_enum(self, topic: Optional[str]):
        if not topic:
            return None
        try:
            from mini_kio.media.intelligence.media_intelligence_models import TopicType
            m = {"SPORTS": TopicType.SPORTS, "MOVIES": TopicType.MOVIES,
                 "TV": TopicType.TV, "GAMING": TopicType.GAMING,
                 "MUSIC": TopicType.MUSIC, "TECH": TopicType.TECH,
                 "NEWS": TopicType.NEWS, "BOOKS": TopicType.BOOKS}
            return m.get(topic)
        except Exception:
            return None

    def _register_current_artifact(self) -> None:
        if self._artifact_memory is None:
            return
        try:
            from mini_kio.media.intelligence.media_intelligence_models import ArtifactRecord, ArtifactType, TopicType
            at_str = self._context.artifact_type or self._context.source_event_type or ""
            if not at_str:
                return
            at_map = {"trailer": ArtifactType.TRAILER, "teaser": ArtifactType.TEASER,
                      "reveal trailer": ArtifactType.TRAILER, "gameplay": ArtifactType.GAMEPLAY,
                      "highlights": ArtifactType.HIGHLIGHTS, "music video": ArtifactType.MUSIC_VIDEO,
                      "music_video": ArtifactType.MUSIC_VIDEO, "hands-on": ArtifactType.TRAILER,
                      "live coverage": ArtifactType.HIGHLIGHTS,
                      "audiobook": ArtifactType.AUDIOBOOK, "book review": ArtifactType.BOOK_REVIEW,
                      "book summary": ArtifactType.BOOK_SUMMARY,
                      "adaptation trailer": ArtifactType.ADAPTATION_TRAILER,
                      "author interview": ArtifactType.AUTHOR_INTERVIEW, "reading": ArtifactType.READING}
            artifact_type = None
            for k, v in at_map.items():
                if at_str == k or at_str == v.value:
                    artifact_type = v
                    break
            if artifact_type is None:
                try:
                    artifact_type = ArtifactType(at_str)
                except (ValueError, TypeError):
                    return
            topic_type = self._topic_str_to_enum(self._context.topic)
            if topic_type is None:
                return
            subject = self._context.entity or self._context.last_query or ""
            if not subject:
                return
            record = ArtifactRecord(artifact_type=artifact_type, topic=topic_type, subject=subject, source="media_manager")
            self._artifact_memory.store_artifact(record)
            logger.info("[ARTIFACT_MEMORY_REGISTER] type=%s subject=%s topic=%s", artifact_type.value, subject, topic_type.value)
        except Exception:
            pass

    def _resolve_via_artifact_memory(self, query: str):
        if self._artifact_memory is None:
            return None
        try:
            from mini_kio.media.intelligence.artifact_memory import parse_artifact_type, default_artifact_for_topic
            from mini_kio.media.intelligence.media_intelligence_models import ArtifactType
            q = query.lower().strip()
            artifact_type = parse_artifact_type(q)
            if artifact_type is None:
                topic_type = self._topic_str_to_enum(self._context.topic)
                if topic_type and ("play it" in q or "show it" in q or q in ("play", "show")):
                    artifact_type = default_artifact_for_topic(topic_type)
            if artifact_type is None:
                return None
            subject = self._context.entity or self._context.last_query or ""
            topic_type = self._topic_str_to_enum(self._context.topic)
            record = self._artifact_memory.resolve_artifact(artifact_type, subject=subject, topic=topic_type)
            if record and record.url:
                # Skip Wikipedia/URL-based artifacts — search YouTube instead
                if "wikipedia" in record.url.lower() or "wiki" in record.url.lower():
                    logger.info("[ARTIFACT_MEMORY_SKIP] wikipedia url for %s, searching youtube for '%s %s'",
                                artifact_type.value, subject, artifact_type.value)
                    return self.play(f"{subject} {artifact_type.value}", platform="youtube")
                logger.info("[ARTIFACT_MEMORY_HIT] type=%s subject=%s url=%s", artifact_type.value, record.subject, record.url)
                return self.play(record.url)
        except Exception:
            pass
        return None

    def _build_sports_narrative(self, completed: list[dict], upcoming: list[dict]) -> str:
        try:
            narrative = self._build_sports_narrative_raw(completed, upcoming)
            if not narrative:
                return ""
            return f"Here's the latest: {narrative}"
        except Exception:
            pass
        return self._build_sports_narrative_old(completed, upcoming)

    def _build_sports_narrative_raw(self, completed: list[dict], upcoming: list[dict]) -> str:
        parts = []
        for c in completed:
            a = c["entity_a"]
            b = c["entity_b"]
            score = c.get("score", "")
            if score:
                clean = score.replace("\u2013", "-").replace("\u2014", "-")
                try:
                    a_goals, b_goals = int(clean.split("-")[0]), int(clean.split("-")[1])
                except (ValueError, IndexError):
                    a_goals = b_goals = 0
                if a_goals == b_goals:
                    parts.append(f"{a} drew {b} {score}")
                elif abs(a_goals - b_goals) == 1:
                    if a_goals > b_goals:
                        parts.append(f"{a} edged {b} {score}")
                    else:
                        parts.append(f"{b} edged {a} {score}")
                else:
                    if a_goals > b_goals:
                        parts.append(f"{a} beat {b} {score}")
                    else:
                        parts.append(f"{b} beat {a} {score}")
            else:
                parts.append(f"{a} vs {b}")
        narrative = " while ".join(parts)
        if upcoming:
            fixture_list = ", ".join(u["canonical_name"] for u in upcoming)
            narrative += f"\n\nNext up: {fixture_list}"
        return narrative

    def _build_sports_narrative_old(self, completed: list[dict], upcoming: list[dict]) -> str:
        return self._build_sports_narrative_raw(completed, upcoming)

    def _pick_best_sentence(self, raw_text: str, topic: Optional[str], entity: Optional[str]) -> str:
        try:
            from mini_kio.media.intelligence.media_intelligence_models import TopicType
            topic_map = {"MOVIES": TopicType.MOVIES, "TV": TopicType.TV,
                         "GAMING": TopicType.GAMING, "SPORTS": TopicType.SPORTS,
                         "MUSIC": TopicType.MUSIC, "TECH": TopicType.TECH,
                         "NEWS": TopicType.NEWS}
            tt = topic_map.get(topic, TopicType.UNKNOWN)
            subject = entity or self._context.last_query or ""
            best = self._pick_best_sentence_old(raw_text, topic, entity)
            if best:
                return f"Here's what I found about {subject}: {best}"
            return best
        except Exception:
            pass
        return self._pick_best_sentence_old(raw_text, topic, entity)

    def _pick_best_sentence_old(self, raw_text: str, topic: Optional[str], entity: Optional[str]) -> str:
        text = self._clean_headline(raw_text)
        sentences = re.split(r'(?<=[.!?])\s+', text)
        entity_lower = entity.lower() if entity else ""
        topic_keywords = {
            "MOVIES": ["announce", "confirm", "reveal", "trailer", "release",
                       "tease", "crossover", "sequel", "project", "film", "movie", "studio"],
            "TV": ["announce", "confirm", "reveal", "trailer", "release",
                   "tease", "season", "episode", "series", "show", "network", "streaming"],
            "GAMING": ["announce", "reveal", "release", "update", "development",
                       "gameplay", "trailer", "content", "patch"],
            "MUSIC": ["album", "single", "release", "tour", "song", "performance",
                      "collaboration", "debut", "new music", "concert"],
            "TECH": ["launch", "announce", "release", "feature", "update",
                     "new device", "software", "hardware", "upgrade"],
        }
        keywords = topic_keywords.get(topic, [])
        best, best_score = "", -1
        for s in sentences:
            sl = s.lower()
            score = 0
            if entity_lower and entity_lower in sl:
                score += 3
            score += sum(2 for kw in keywords if kw in sl)
            if any(w in sl for w in ["according to", "as of", "sources say", "sources indicate", "sources tell"]):
                score -= 5
            if len(s) > 20 and len(s) < 250 and score > best_score:
                best_score = score
                best = s.strip()
        return best

    def _is_platform_choice(self, result: dict) -> bool:
        msg = (result.get("message") or "").lower()
        return "youtube" in msg or "what would you like" in msg

    def _build_offer_line(self) -> str:
        try:
            from mini_kio.media.intelligence.media_response_formatter import _FOLLOWUP_OPTIONS
            from mini_kio.media.intelligence.media_intelligence_models import TopicType
            topic_map = {"SPORTS": TopicType.SPORTS, "MOVIES": TopicType.MOVIES,
                         "TV": TopicType.TV, "GAMING": TopicType.GAMING,
                         "MUSIC": TopicType.MUSIC, "TECH": TopicType.TECH,
                         "NEWS": TopicType.NEWS}
            tt = topic_map.get(self._context.topic)
            if tt and tt in _FOLLOWUP_OPTIONS:
                options = _FOLLOWUP_OPTIONS[tt][:4]
                return f"I can show " + ", ".join(options) + "."
        except Exception:
            pass
        return self._build_offer_line_old()

    def _build_offer_line_old(self) -> str:
        t = self._context.topic
        artifact = self._context.source_event_type
        if t == "SPORTS":
            completed = [e for e in self._context.recent_events if e["status"] == "COMPLETED"]
            options = ["highlights", "standings", "fixtures"]
            if completed:
                for c in completed[:2]:
                    options.append(f"{c['entity_a']} updates")
            return f"I can show " + ", ".join(options[:4]) + "."
        if t in ("MOVIES", "TV"):
            return f"I can show the {artifact}, reveal footage, or related updates."
        if t == "GAMING":
            return f"I can show {artifact} footage or breakdowns."
        if t == "MUSIC":
            return f"I can show the {artifact} or latest releases."
        if t == "TECH":
            return f"I can show hands-on demos or related coverage."
        return ""

    def _clean_headline(self, text: str) -> str:
        text = re.sub(r'^As of\s+[^,]+,\s*', '', text, flags=re.IGNORECASE)
        text = re.sub(r'^According to\s+[^,]+,\s*', '', text, flags=re.IGNORECASE)
        text = re.sub(r'^In\s+(an?\s+)?(interview|report|statement|article|announcement)\s+[^,]+,\s*', '', text, flags=re.IGNORECASE)
        text = re.sub(r'^[^A-Za-z]*', '', text).strip()
        text = re.sub(r'\s+https?://\S+', '', text)
        # Filter UI noise lines
        lines = text.split("\n")
        cleaned = []
        removed = 0
        for line in lines:
            stripped = line.strip()
            if stripped and stripped.lower() not in _UI_NOISE_WORDS:
                cleaned.append(stripped)
            else:
                removed += 1
        if removed:
            logger.info("[CLEANER_REMOVED_UI] count=%d", removed)
        text = " ".join(cleaned)
        text = text.strip().rstrip(".,;:")
        return text

    def _detect_match_status(self, raw_text: str) -> str:
        tl = raw_text.lower()
        future_indicators = ["tomorrow", "next week", "upcoming", "scheduled", "will play",
                             "will face", "kicks off", "set to", "due to", "fixture",
                             "coming up"]
        live_indicators = ["live", "currently", "now", "ongoing", "in progress", "underway",
                           "half-time", "halftime", "second half", "first half"]
        past_indicators = ["beat", "won", "lost", "defeated", "final score", "ended",
                           "finished", "result", "win over", "victory", "defeat"]
        score_pattern = re.compile(r'\d+[–\-]\d+')
        has_scores = bool(score_pattern.search(tl))
        if any(w in tl for w in future_indicators):
            return "UPCOMING"
        if any(w in tl for w in live_indicators):
            return "LIVE"
        if any(w in tl for w in past_indicators) or has_scores:
            return "COMPLETED"
        return "UNKNOWN"

    def _extract_updates(self, raw_text: str, max_lines: int = 2) -> list[str]:
        sentences = re.split(r'(?<=[.!?])\s+', raw_text.strip())
        updates = []
        for s in sentences:
            cleaned = self._clean_headline(s)
            if cleaned and len(cleaned) > 15 and len(cleaned) < 300:
                updates.append(cleaned)
                if len(updates) >= max_lines:
                    break
        return updates

    @_serialize_media_op
    def process_information_query(self, query: str, session_id: str = "") -> dict:
        self._analyze_query_for_intelligence(query)

        topic_query = query.strip()
        if not topic_query:
            return {"success": True, "message": "I don't have information on that."}

        self._context.last_query = topic_query
        
        # Phase C4: Delegate to Intelligence Adapter (session-scoped so the
        # verification claim store stays isolated per conversation)
        if self._intelligence_adapter:
            try:
                result = self._intelligence_adapter.handle(topic_query, session_id=session_id)
                
                # Sync context
                self._context.topic = result.topic.name if hasattr(result.topic, "name") else str(result.topic)
                self._context.entity = result.subject
                
                if result.events:
                    for ev in result.events:
                        # Convert EventRecord to legacy dict for MediaContext
                        legacy_ev = _event_record_to_legacy_dict(ev)
                        self._context.store_event(legacy_ev)
                    
                    # Fix for .status.name access (if it's an Enum)
                    def get_status_str(e):
                        if hasattr(e.status, "name"): return e.status.name
                        return str(e.status).upper()

                    first_completed = next((e for e in result.events if get_status_str(e) == "COMPLETED"), None)
                    if first_completed:
                        self._context.last_completed_match = first_completed.display()
                        logger.info("[MM_INTELLIGENCE] Stored last_completed_match from adapter events: %s", self._context.last_completed_match)

                # Determine pending action
                pending_action = ""
                pending_media_query = ""
                artifact_type = ""
                
                if result.topic in ("SPORTS", "MOVIES", "TV", "MUSIC", "GAMING", "TECH") and result.subject:
                    # Legacy logic for pending action
                    artifact_type = self._artifact_for_topic()
                    pending_media_query = self._build_media_query()
                    if pending_media_query:
                        pending_action = "play_media"
                
                self._store_pending_context(pending_media_query, pending_action, artifact_type)
                
                logger.info("[MEDIA_SUBJECT_UPDATE] subject=%s", result.subject)
                logger.info("[MEDIA_ENTITY_UPDATE] topic=%s source=%s", result.topic, result.source)

                return {
                    "success": True,
                    "message": result.response_text,
                    "subject": result.subject,
                    "topic": str(result.topic),
                    "entity": result.subject,
                    "_pending_action": pending_action,
                    "_pending_media_query": pending_media_query,
                    "_source_provider": result.source,
                    "_source_confidence": result.confidence,
                }
            except Exception as exc:
                logger.warning("[MM_INTELLIGENCE_ADAPTER_ERROR] %s", exc)
                # Fall through to legacy if adapter fails

        # ── Legacy Implementation (Fallback) ───────────────────────────
        self._context.match_status = "UNKNOWN"

        raw_text = ""
        provider_name = None
        try:
            from mini_kio.knowledge.retrieval_router import KnowledgeRouter
            router = KnowledgeRouter()
            res_legacy, provider_name = router.route_for_topic(topic_query, self._context.topic, self._context.sports_mode)
            if res_legacy and not res_legacy.is_empty():
                raw_text = "\n".join(s.content[:500] for s in res_legacy.sources if s.content)
        except Exception:
            res_legacy = None
            provider_name = None
            raw_text = ""

    def has_intelligence_offer(self) -> bool:
        return self._offer_manager.has_pending_offer()

    def get_intelligence_offer_display(self) -> Optional[str]:
        offer = self._offer_manager.get_active_offer()
        return offer.to_display() if offer else None

    @_serialize_media_op
    def accept_intelligence_offer(self) -> Optional[dict]:
        offer = self._offer_manager.accept_active_offer()
        if not offer:
            offer = self._offer_manager.get_last_accepted_offer()
        if not offer:
            return None
        entity = self._offer_manager.get_accepted_entity(offer)
        if not entity:
            return None
        provider_hint = entity.provider.value if entity.provider.value != "unknown" else ""
        return self.play(entity.name, platform=provider_hint)

    def correct_fuzzy(self, text: str) -> str:
        return _correct_fuzzy(text)

    def is_fuzzy_match(self, text: str) -> bool:
        tl = text.lower().strip()
        return tl in _FUZZY_MAP or any(
            w in _FUZZY_MAP for w in tl.split()
        )

    def offer_media(self, topic: str) -> Optional[dict]:
        opportunity = self._discovery.detect_opportunity(topic)
        if opportunity:
            self._discovery.set_last_offer(opportunity)
            self._context.current_topic = topic
            self._context.last_query = topic
            return opportunity
        return None

    def get_last_offer(self) -> Optional[dict]:
        return self._discovery.get_last_offer()

    @_serialize_media_op
    def accept_offer(self, query: str = "") -> Optional[dict]:
        offer = self._discovery.get_last_offer()
        if not offer:
            return None
        topic = query or offer.get("topic", "")
        if not topic:
            self._discovery.clear_last_offer()
            return None
        mt = offer.get("media_type", "video")
        provider_name = self._select_provider(topic, media_type=mt)
        prov = self._get_provider(provider_name)
        if not prov:
            self._discovery.clear_last_offer()
            return None
        try:
            search_result = prov.search(topic)
            if search_result.success and search_result.candidates:
                best = search_result.candidates[0]
                result = prov.play(best.title)
                self._register_session(provider_name, result)
                self._discovery.clear_last_offer()
                return self._to_dict(result)
            result = prov.play(topic)
            self._register_session(provider_name, result)
            self._discovery.clear_last_offer()
            return self._to_dict(result)
        except Exception as exc:
            logger.warning("[MM] accept_offer failed: %s", exc)
            self._discovery.clear_last_offer()
            return None

    def get_status(self) -> dict:
        active = self._registry.get_active()
        if active:
            return {"success": True, "message": active.to_dict()}
        return {"success": True, "message": "No active media session."}
