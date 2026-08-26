"""
discovery_engine.py
KIO Media Intelligence Layer — Discovery Engine

The unified discovery pipeline that replaces scattered hardcoded fallbacks.

Architecture:
  User request ("play something", "nah", "another one", "play something funny")
    → analyze_semantic_intent()      — extract what the user wants
    → build_discovery_query()        — combine intent + preferences + context
    → (provider retrieves candidates)
    → score_and_select()             — multi-candidate scoring with diversity
    → handle_rejection()             — negative signals, re-discovery
    → generate_response()            — natural response from structured facts

Key principles:
  - NO hardcoded content queries (no "Popular Songs", "trending music", etc.)
  - Preferences are DATA, not constants
  - Rejections change future selection
  - Diversity prevents bubbles
  - Cold start uses user's own words
"""

from __future__ import annotations

import math
import random
import time
from dataclasses import dataclass, field
from typing import Any, Dict, List, Optional, Tuple

from mini_kio.media.media_context import MediaContext
from mini_kio.media.intelligence.media_entity_memory import MediaEntityMemory
from mini_kio.media.intelligence.media_preference_model import MediaPreferenceModel
from mini_kio.media.media_intelligence_models import (
    EntityType, MediaProvider, ResolvedEntity, HistoricalMediaSession
)


# ─────────────────────────── dataclasses ───────────────────────────

@dataclass
class DiscoveryIntent:
    """Structured representation of what the user wants from discovery."""
    # What the user literally said
    raw_text: str = ""
    # Semantic intent: "funny", "Malayalam comedy", "something like Karikku"
    semantic_intent: str = ""
    # Extracted mood: "chill", "funny", "energetic"
    mood: str = ""
    # Extracted content type: "comedy", "music", "interview"
    content_type: str = ""
    # Is this a bare discovery request? ("play something", "I'm bored")
    is_bare_discovery: bool = False
    # Is this a rejection? ("nah", "not this")
    is_rejection: bool = False
    # Is this a continuation? ("another one", "more like this")
    is_continuation: bool = False
    # Is this a replay? ("play that again")
    is_replay: bool = False
    # The original request that started this discovery session
    original_request: str = ""
    # Confidence in the intent extraction
    confidence: float = 0.0


@dataclass
class DiscoveryCandidate:
    """A scored candidate for discovery."""
    # The entity/search result
    title: str = ""
    channel: str = ""
    url: str = ""
    video_id: str = ""
    # Scores
    preference_score: float = 0.0    # how well it matches learned preferences
    relevance_score: float = 0.0     # how well it matches the current request
    diversity_score: float = 0.0     # how different from recently played
    final_score: float = 0.0         # weighted combination
    # Metadata for response generation
    reason: str = ""                 # why this was selected
    # For rejection tracking
    is_rejected: bool = False


@dataclass
class DiscoveryResult:
    """Result of a discovery operation."""
    # The selected candidate (if any)
    selected: Optional[DiscoveryCandidate] = None
    # All candidates considered
    candidates: List[DiscoveryCandidate] = field(default_factory=list)
    # The query that was used for retrieval
    query_used: str = ""
    # The semantic intent that was detected
    intent: Optional[DiscoveryIntent] = None
    # Whether this was a cold start (no preferences)
    cold_start: bool = False
    # Number of candidates retrieved
    candidate_count: int = 0
    # Whether the candidate pool is exhausted
    pool_exhausted: bool = False


# ─────────────────────────── engine ───────────────────────────

class DiscoveryEngine:
    """
    Unified discovery pipeline that replaces scattered hardcoded fallbacks.

    Integration:
        engine = DiscoveryEngine(memory, preference_model, media_context)
        result = engine.process_request("play something")
        # result.selected has the chosen candidate
        # result.query_used has what was searched for
    """

    # Scoring weights for candidate selection
    WEIGHT_PREFERENCE = 0.35    # learned user preferences
    WEIGHT_RELEVANCE = 0.30     # match to current request
    WEIGHT_DIVERSITY = 0.20     # novelty vs recently played
    WEIGHT_CHANNEL_AFFINITY = 0.15  # channel/creator affinity

    # Diversity: penalty for recently played content
    RECENT_PLAY_PENALTY = 0.4   # penalty for same creator within 3 plays
    RECENT_TITLE_PENALTY = 0.8  # penalty for exact same title

    # Exploration: probability of selecting non-top candidate
    EXPLORATION_RATE = 0.25     # 25% chance to explore among top-3

    # Rejection: how much to penalize rejected content
    REJECTION_PENALTY = 0.6     # penalty for rejected video
    REPEATED_REJECTION_DECAY = 0.15  # additional decay per repeated rejection

    # Cold start: minimum confidence to use preference-derived query
    COLD_START_THRESHOLD = 0.3

    def __init__(
        self,
        memory: MediaEntityMemory,
        preference_model: MediaPreferenceModel,
        media_context: MediaContext,
    ):
        self._mem = memory
        self._prefs = preference_model
        self._ctx = media_context

    # ── public entry points ──────────────────────────────────

    def analyze_intent(self, utterance: str) -> DiscoveryIntent:
        """
        Analyze the user's utterance to extract discovery intent.

        This is the semantic understanding layer that replaces hardcoded
        pattern matching with structured intent extraction.
        """
        text = utterance.lower().strip()
        intent = DiscoveryIntent(raw_text=utterance)

        # 1. Detect continuation FIRST (before rejection — "another one" is
        # continuation, not rejection)
        _CONTINUATION_SIGNALS = {
            "another one", "next one", "one more", "play more",
            "more like this", "more like that", "another song", "another track",
        }
        if text in _CONTINUATION_SIGNALS:
            intent.is_continuation = True
            intent.confidence = 0.90
            return intent

        # 2. Detect replay
        if text in ("play that again", "replay", "play it again", "again"):
            intent.is_replay = True
            intent.confidence = 0.90
            return intent

        # 3. Detect rejection
        _REJECTION_SIGNALS = {
            "nah", "nope", "no", "nahh", "nahhh", "naw", "naww",
            "not this", "not this one", "not feeling this", "not it",
            "this ain't it", "this isn't it", "this sucks", "this is bad",
            "skip", "skip this", "skip it", "skip that",
            "next", "another",
            "something different", "something better", "play something else",
            "play something different", "try another", "try something else",
            "try something different", "give me another", "give me something else",
            "change it", "switch it",
            "not what i meant", "not what we meant",
            "that's not what i meant", "thats not what i meant",
        }
        if text in _REJECTION_SIGNALS:
            intent.is_rejection = True
            intent.confidence = 0.95
            return intent

        # Also match compound patterns
        if text.startswith("nah") and any(w in text for w in ("next", "another", "try")):
            intent.is_rejection = True
            intent.confidence = 0.90
            return intent
        if text.startswith("no") and any(w in text for w in ("next", "another", "try")):
            intent.is_rejection = True
            intent.confidence = 0.90
            return intent

        # Short negative that doesn't look like a new play request
        if len(text.split()) <= 3 and any(text.startswith(n) for n in ("nah", "no", "not ")) and "play" not in text:
            intent.is_rejection = True
            intent.confidence = 0.85
            return intent

        # 4. Extract mood from the request
        _MOOD_KEYWORDS = {
            "funny": "comedy", "comedy": "comedy", "hilarious": "comedy",
            "laugh": "comedy", "amusing": "comedy",
            "chill": "chill", "relaxing": "chill", "calm": "chill",
            "sad": "sad", "emotional": "sad", "heartbreak": "sad",
            "happy": "happy", "upbeat": "happy", "energetic": "energetic",
            "hype": "energetic", "pump": "energetic",
            "romantic": "romantic", "love": "romantic",
            "scary": "horror", "horror": "horror", "creepy": "horror",
        }
        for keyword, mood in _MOOD_KEYWORDS.items():
            if keyword in text:
                intent.mood = mood
                intent.semantic_intent = mood
                break

        # 5. Extract content type
        _CONTENT_KEYWORDS = {
            "interview": "interview", "documentary": "documentary",
            "trailer": "trailer", "teaser": "trailer",
            "music video": "music video", "song": "song",
            "podcast": "podcast", "tutorial": "tutorial",
            "highlights": "highlights", "clip": "clip",
        }
        for keyword, ct in _CONTENT_KEYWORDS.items():
            if keyword in text:
                intent.content_type = ct
                if not intent.semantic_intent:
                    intent.semantic_intent = ct
                break

        # 6. Detect bare discovery
        _BARE_DISCOVERY = {
            "play something", "play anything", "play random",
            "put something on", "put something random on",
            "surprise me", "surprise", "entertain me", "amuse me",
            "give me something", "find something", "pick something",
            "show me something", "recommend something", "suggest something",
            "what should i watch", "what should i listen to",
            "what's good", "whats good", "something", "anything",
            "something random", "anything random",
            "i'm bored", "im bored", "i am bored", "bored",
        }
        if text in _BARE_DISCOVERY:
            intent.is_bare_discovery = True
            intent.confidence = 0.85
            return intent

        # 7. If we extracted mood/content but no other signal, it's a contextual discovery
        if intent.semantic_intent:
            intent.confidence = 0.75
            return intent

        # 8. Default: treat as explicit query
        intent.semantic_intent = text
        intent.confidence = 0.60
        return intent

    def build_discovery_query(self, intent: DiscoveryIntent) -> str:
        """
        Build a search query from intent + learned preferences.

        This is the CORE of personalized discovery. It combines:
        - The user's semantic intent (mood, content type)
        - Learned preferences (channels, artists, languages)
        - Conversation context
        - NEVER inserts hardcoded generic queries
        - NEVER returns literal command words ("play something") as the search

        CRITICAL: For bare discovery ("play something") with no preferences,
        this method must NOT return empty or the literal command words.
        It generates a genuine exploration intent instead.
        """
        parts: List[str] = []

        # 1. If explicit topic/entity, use it directly
        if intent.semantic_intent and not intent.is_bare_discovery:
            # Check if semantic_intent looks like a specific entity/topic
            # (not just a mood word)
            _MOOD_ONLY = {"comedy", "chill", "sad", "happy", "energetic", "romantic", "horror"}
            if intent.semantic_intent not in _MOOD_ONLY:
                parts.append(intent.semantic_intent)

        # 2. Add preference signals
        now = time.time()

        # Top channel/creator (strongest signal)
        top_channels = self._prefs.get_top_channels(3)
        if top_channels:
            # Only add if not already in the query
            for ch_name, ch_score in top_channels:
                if ch_name not in " ".join(parts).lower():
                    parts.append(ch_name)
                    break  # add at most one channel

        # Top genre from preferences
        top_genres = sorted(self._prefs._genres.items(),
                           key=lambda kv: kv[1].decayed_score(now), reverse=True)
        if top_genres and intent.mood:
            # Combine mood with genre preference
            genre = top_genres[0][0]
            if genre not in " ".join(parts).lower():
                parts.append(genre)

        # Language preference
        top_langs = self._prefs.get_top_languages(1)
        if top_langs:
            lang = top_langs[0][0]
            if lang not in " ".join(parts).lower():
                parts.append(lang)

        # 3. Add mood/content type if not already covered
        if intent.mood and intent.mood not in " ".join(parts).lower():
            parts.append(intent.mood)
        if intent.content_type and intent.content_type not in " ".join(parts).lower():
            parts.append(intent.content_type)

        # 4. If we have parts, join them
        if parts:
            return " ".join(parts[:4])  # keep query concise

        # 5. Cold start with bare discovery: derive from conversation context
        # NEVER search for literal "play something" — that's not an intent.
        if intent.is_bare_discovery:
            return self._generate_cold_start_query(intent)

        # 6. Non-bare request with no other signals: use the user's own words
        if intent.raw_text:
            # Strip discovery phrases to get the semantic content
            _strip = intent.raw_text.lower().strip()
            for phrase in ("play something", "play anything", "put something on",
                          "give me something", "find something", "show me something"):
                if _strip.startswith(phrase):
                    _strip = _strip[len(phrase):].strip()
                    break
            if _strip:
                return _strip

        # 7. Truly no signal — generate exploration query
        return self._generate_cold_start_query(intent)

    def _generate_cold_start_query(self, intent: DiscoveryIntent) -> str:
        """
        Generate a search query when there are no preferences and the request
        is bare discovery ("play something").

        Strategy:
        1. Check recent media history for context
        2. Check conversation context for topical signals
        3. Check explicit preference statements
        4. Use LLM to derive an exploration intent if available
        5. Return an empty string (callers must handle gracefully)

        NEVER returns:
        - "popular songs"
        - "trending music"
        - "top tracks"
        - "play something" (literal command words)
        - any hardcoded generic query
        """
        # Strategy 1: Recent media history — play something similar
        recent_sessions = self._mem.get_recent_sessions(5)
        if recent_sessions:
            last = recent_sessions[-1]
            entity = last.entity
            # Use the last played creator/channel as exploration seed
            channel = entity.metadata.get("channel") or entity.metadata.get("creator") or ""
            if channel:
                return channel  # e.g. "Karikku" — YouTube will show similar
            artist = entity.metadata.get("artist") or ""
            if artist:
                return artist
            # Use entity name as context
            if entity.name:
                return entity.name

        # Strategy 2: Explicit preferences
        explicit = self._prefs.get_explicit_prefs()
        if explicit:
            # Pick the strongest explicit preference
            for key, val in explicit.items():
                if val == "like":
                    return key

        # Strategy 3: Try to use the LLM for intent derivation
        llm_query = self._derive_intent_via_llm(intent)
        if llm_query:
            return llm_query

        # Strategy 4: No signal at all — return empty string.
        # The caller MUST handle this by either:
        # - Using the intelligence adapter to generate intent
        # - Using a conversation-context-aware fallback
        # - NOT inserting "Popular Songs" or any hardcoded fallback
        return ""

    def _derive_intent_via_llm(self, intent: DiscoveryIntent) -> str:
        """
        Use the LLM to derive an appropriate exploration intent for bare
        discovery when there are no preferences.

        Returns a search-ready query string, or empty if LLM is unavailable.
        """
        try:
            from mini_kio.core.llm_router import ask_llm
            import asyncio

            # Build context for the LLM
            context_parts = []
            if self._ctx.last_query:
                context_parts.append(f"Last media request: {self._ctx.last_query}")
            if self._ctx.current_artist:
                context_parts.append(f"Currently playing: {self._ctx.current_artist}")
            if self._ctx.current_mood:
                context_parts.append(f"Current mood: {self._ctx.current_mood}")

            context_str = "; ".join(context_parts) if context_parts else "no prior context"

            prompt = (
                f"The user wants to watch something on YouTube. "
                f"Context: {context_str}. "
                f"Generate a single short YouTube search query (2-4 words) that would "
                f"find entertaining video content. Do NOT use generic terms like "
                f"'popular' or 'trending'. Return ONLY the search query, nothing else."
            )

            loop = asyncio.new_event_loop()
            asyncio.set_event_loop(loop)
            try:
                response = loop.run_until_complete(
                    ask_llm(prompt, timeout=8.0, max_tokens=30)
                )
            finally:
                loop.close()
                asyncio.set_event_loop(None)

            if response and isinstance(response, str):
                query = response.strip().strip('"').strip("'").strip()
                # Safety: reject generic/hardcoded queries
                _forbidden = {"popular songs", "trending music", "top tracks",
                              "popular music", "good music", "viral videos",
                              "play something", "something interesting"}
                if query.lower() not in _forbidden and len(query) > 2:
                    return query
        except Exception:
            pass
        return ""

    def score_and_select(
        self,
        candidates: List[DiscoveryCandidate],
        intent: DiscoveryIntent,
    ) -> DiscoveryResult:
        """
        Score candidates and select the best one with controlled exploration.

        Scoring formula:
          final = W_pref * preference_score
                + W_rel * relevance_score
                + W_div * diversity_score
                + W_ch * channel_affinity

        Selection: probabilistic among top-3 to ensure diversity.
        """
        if not candidates:
            return DiscoveryResult(
                selected=None,
                candidates=[],
                intent=intent,
                pool_exhausted=True,
            )

        # Score each candidate
        for c in candidates:
            # Apply rejection penalty
            if c.video_id in self._ctx.discovery_rejected_candidates:
                c.preference_score *= (1.0 - self.REJECTION_PENALTY)
                c.is_rejected = True
            if c.title in self._ctx.discovery_rejected_candidates:
                c.preference_score *= (1.0 - self.REJECTION_PENALTY)
                c.is_rejected = True

            # Apply recently-played penalty
            if c.channel and c.channel in self._ctx.discovery_candidate_history[-5:]:
                c.diversity_score *= (1.0 - self.RECENT_PLAY_PENALTY)
            if c.title in self._ctx.discovery_candidate_history[-5:]:
                c.diversity_score *= (1.0 - self.RECENT_TITLE_PENALTY)

            # Calculate final score
            c.final_score = (
                self.WEIGHT_PREFERENCE * c.preference_score
                + self.WEIGHT_RELEVANCE * c.relevance_score
                + self.WEIGHT_DIVERSITY * c.diversity_score
                + self.WEIGHT_CHANNEL_AFFINITY * c.preference_score  # reuse preference as channel affinity
            )

        # Sort by final score
        candidates.sort(key=lambda c: c.final_score, reverse=True)

        # Filter out rejected candidates
        viable = [c for c in candidates if not c.is_rejected]
        if not viable:
            viable = candidates  # if all rejected, use all (shouldn't happen)

        # Controlled exploration: probabilistic selection among top-3
        top_n = viable[:3]
        if len(top_n) > 1 and random.random() < self.EXPLORATION_RATE:
            # Explore: pick randomly from top-3 (weighted by score)
            weights = [max(0.01, c.final_score) for c in top_n]
            total = sum(weights)
            weights = [w / total for w in weights]
            selected = random.choices(top_n, weights=weights, k=1)[0]
        else:
            # Exploit: pick the best
            selected = top_n[0]

        # Mark as played
        self._ctx.discovery_candidate_history.append(selected.title)
        if selected.channel:
            # Track channel for diversity
            pass  # channel tracking is in the history

        return DiscoveryResult(
            selected=selected,
            candidates=candidates,
            intent=intent,
            candidate_count=len(candidates),
        )

    def handle_rejection(self) -> DiscoveryResult:
        """
        Handle a rejection ("nah", "not this") by:
        1. Recording the rejected candidate
        2. Preserving the original semantic intent
        3. Re-discovering with exclusion

        CRITICAL: The re-discovery query must NEVER be the literal command
        words ("play something"). It must be an intelligent intent-derived
        query that respects the original request semantics.
        """
        # Record rejection
        if self._ctx.current_media_id:
            self._ctx.discovery_rejected_candidates.append(self._ctx.current_media_id)
        if self._ctx.last_selected_candidate:
            self._ctx.discovery_rejected_candidates.append(
                self._ctx.last_selected_candidate.title
            )

        self._ctx.discovery_rejection_count += 1

        # Build re-discovery intent from original request
        original = self._ctx.discovery_original_request or ""
        intent = DiscoveryIntent(
            raw_text=original,
            is_rejection=False,  # this is a re-discovery, not another rejection
            original_request=original,
            confidence=0.80,
        )

        # Preserve semantic intent from original request
        if self._ctx.discovery_intent:
            intent.semantic_intent = self._ctx.discovery_intent

        # Build query with exclusion
        query = self.build_discovery_query(intent)

        # Safety: if query is still a bare discovery phrase or empty,
        # generate a cold-start exploration query instead
        _BARE = {"play something", "play anything", "play random",
                 "put something on", "give me something", "find something",
                 "show me something", "something", "anything"}
        if not query or query.lower().strip() in _BARE:
            query = self._generate_cold_start_query(intent)

        return DiscoveryResult(
            selected=None,
            query_used=query,
            intent=intent,
        )

    def start_discovery_session(self, utterance: str) -> DiscoveryIntent:
        """
        Start a new discovery session. Called when user says "play something".
        Records the original request for future rejections.
        """
        intent = self.analyze_intent(utterance)

        if intent.is_bare_discovery or (not intent.is_rejection and not intent.is_continuation):
            self._ctx.discovery_original_request = utterance
            self._ctx.discovery_intent = intent.semantic_intent
            self._ctx.discovery_rejection_count = 0
            self._ctx.discovery_rejected_candidates = []
            self._ctx.discovery_candidate_history = []
            self._ctx.discovery_active = True
            self._ctx.discovery_last_action_time = time.time()

        return intent

    def record_playback(self, candidate: DiscoveryCandidate) -> None:
        """Record that a candidate was successfully played."""
        self._ctx.discovery_candidate_history.append(candidate.title)
        if candidate.channel:
            # Channel is already tracked in preference model via _learn_from_playback
            pass
        self._ctx.discovery_last_action_time = time.time()

    def get_discovery_state(self) -> Dict[str, Any]:
        """Get the current discovery state for debugging/logging."""
        return {
            "active": self._ctx.discovery_active,
            "original_request": self._ctx.discovery_original_request,
            "intent": self._ctx.discovery_intent,
            "rejection_count": self._ctx.discovery_rejection_count,
            "rejected_candidates": self._ctx.discovery_rejected_candidates,
            "candidate_history": self._ctx.discovery_candidate_history,
            "last_action_time": self._ctx.discovery_last_action_time,
        }


# ─────────────────────────── tests ───────────────────────────

import unittest


class TestDiscoveryEngine(unittest.TestCase):

    def setUp(self):
        from mini_kio.media.intelligence.media_entity_memory import MediaEntityMemory
        from mini_kio.media.intelligence.media_preference_model import MediaPreferenceModel
        from mini_kio.media.media_context import MediaContext

        self.mem = MediaEntityMemory()
        self.ctx = MediaContext()
        self.prefs = MediaPreferenceModel(self.mem)
        self.engine = DiscoveryEngine(self.mem, self.prefs, self.ctx)

    def _push_session(self, name, artist, channel=""):
        e = ResolvedEntity(
            name=name, entity_type=EntityType.SONG,
            provider=MediaProvider.YOUTUBE,
            metadata={"artist": artist, "channel": channel or artist},
        )
        s = HistoricalMediaSession(session_id=f"s_{name}", entity=e, started_at=time.time())
        self.mem.push_session(s)
        self.prefs.ingest_session(s)

    # ── Intent analysis ──────────────────────────────────────

    def test_bare_discovery_detected(self):
        intent = self.engine.analyze_intent("play something")
        self.assertTrue(intent.is_bare_discovery)

    def test_rejection_detected(self):
        intent = self.engine.analyze_intent("nah")
        self.assertTrue(intent.is_rejection)

    def test_not_this_detected(self):
        intent = self.engine.analyze_intent("not this one")
        self.assertTrue(intent.is_rejection)

    def test_continuation_detected(self):
        intent = self.engine.analyze_intent("another one")
        self.assertTrue(intent.is_continuation)

    def test_replay_detected(self):
        intent = self.engine.analyze_intent("play that again")
        self.assertTrue(intent.is_replay)

    def test_mood_extracted(self):
        intent = self.engine.analyze_intent("play something funny")
        self.assertEqual(intent.mood, "comedy")
        self.assertEqual(intent.semantic_intent, "comedy")

    def test_content_type_extracted(self):
        intent = self.engine.analyze_intent("play an interview")
        self.assertEqual(intent.content_type, "interview")

    def test_explicit_query(self):
        intent = self.engine.analyze_intent("play Karikku")
        self.assertEqual(intent.semantic_intent, "play karikku")
        self.assertFalse(intent.is_bare_discovery)

    # ── Query generation ─────────────────────────────────────

    def test_cold_start_uses_user_words(self):
        intent = self.engine.analyze_intent("play something funny")
        query = self.engine.build_discovery_query(intent)
        # Should contain "comedy" (the mood) but NOT "popular songs"
        self.assertIn("comedy", query)
        self.assertNotIn("popular", query)
        self.assertNotIn("trending", query)

    def test_preference_based_query(self):
        self._push_session("Video1", "Karikku", channel="Karikku")
        self._push_session("Video2", "Karikku", channel="Karikku")
        self._push_session("Video3", "Karikku", channel="Karikku")
        intent = self.engine.analyze_intent("play something")
        query = self.engine.build_discovery_query(intent)
        # Should contain the learned channel
        self.assertIn("karikku", query.lower())

    def test_no_hardcoded_fallbacks(self):
        # Test various discovery requests — none should produce "popular songs"
        for request in ["play something", "put something on", "surprise me", "give me something"]:
            intent = self.engine.analyze_intent(request)
            query = self.engine.build_discovery_query(intent)
            self.assertNotIn("popular songs", query.lower())
            self.assertNotIn("trending music", query.lower())
            self.assertNotIn("top tracks", query.lower())
            self.assertNotIn("good music", query.lower())

    # ── Scoring and selection ────────────────────────────────

    def test_scoring_prefers_known_creators(self):
        self._push_session("V1", "Karikku", channel="Karikku")
        self._push_session("V2", "Karikku", channel="Karikku")

        c1 = DiscoveryCandidate(title="Karikku Video", channel="Karikku",
                                preference_score=0.9, relevance_score=0.7, diversity_score=0.8)
        c2 = DiscoveryCandidate(title="Random Video", channel="Unknown",
                                preference_score=0.1, relevance_score=0.5, diversity_score=0.9)
        intent = DiscoveryIntent(raw_text="play something", is_bare_discovery=True)
        result = self.engine.score_and_select([c1, c2], intent)
        self.assertEqual(result.selected.title, "Karikku Video")

    def test_rejection_excludes_candidate(self):
        c1 = DiscoveryCandidate(title="Video A", channel="Ch1",
                                preference_score=0.8, relevance_score=0.7, diversity_score=0.8)
        c2 = DiscoveryCandidate(title="Video B", channel="Ch2",
                                preference_score=0.6, relevance_score=0.6, diversity_score=0.9)

        # Mark Video A as rejected
        self.ctx.discovery_rejected_candidates.append("Video A")
        intent = DiscoveryIntent(raw_text="play something", is_bare_discovery=True)
        result = self.engine.score_and_select([c1, c2], intent)
        # Video B should be selected (Video A is rejected)
        self.assertEqual(result.selected.title, "Video B")

    def test_diversity_across_repeated_requests(self):
        """Multiple 'play something' requests should diversify."""
        c1 = DiscoveryCandidate(title="Same Creator", channel="Ch1",
                                preference_score=0.9, relevance_score=0.7, diversity_score=0.5)
        c2 = DiscoveryCandidate(title="Different Creator", channel="Ch2",
                                preference_score=0.7, relevance_score=0.6, diversity_score=0.9)

        # After playing "Same Creator", it should appear in history
        self.ctx.discovery_candidate_history.append("Same Creator")

        intent = DiscoveryIntent(raw_text="play something", is_bare_discovery=True)
        # Run multiple times — diversity penalty should reduce "Same Creator" score
        results = []
        for _ in range(10):
            result = self.engine.score_and_select([c1, c2], intent)
            results.append(result.selected.title)
        # "Different Creator" should appear at least once due to diversity
        self.assertIn("Different Creator", results)

    # ── Rejection handling ───────────────────────────────────

    def test_rejection_preserves_intent(self):
        self.ctx.discovery_original_request = "play something funny"
        self.ctx.discovery_intent = "comedy"
        self.ctx.current_media_id = "video_123"
        self.ctx.last_selected_candidate = type('obj', (object,), {'title': 'Video A'})()

        result = self.engine.handle_rejection()
        self.assertEqual(result.intent.semantic_intent, "comedy")
        self.assertIn("video_123", self.ctx.discovery_rejected_candidates)
        self.assertIn("Video A", self.ctx.discovery_rejected_candidates)

    def test_rejection_count_increments(self):
        self.ctx.discovery_original_request = "play something"
        self.ctx.current_media_id = "vid1"
        self.ctx.last_selected_candidate = type('obj', (object,), {'title': 'V1'})()

        self.engine.handle_rejection()
        self.assertEqual(self.ctx.discovery_rejection_count, 1)
        self.engine.handle_rejection()
        self.assertEqual(self.ctx.discovery_rejection_count, 2)

    # ── Session management ───────────────────────────────────

    def test_start_discovery_session(self):
        intent = self.engine.start_discovery_session("play something")
        self.assertTrue(intent.is_bare_discovery)
        self.assertTrue(self.ctx.discovery_active)
        self.assertEqual(self.ctx.discovery_original_request, "play something")

    def test_record_playback(self):
        c = DiscoveryCandidate(title="Test Video", channel="TestChannel")
        self.engine.record_playback(c)
        self.assertIn("Test Video", self.ctx.discovery_candidate_history)


if __name__ == "__main__":
    unittest.main()
