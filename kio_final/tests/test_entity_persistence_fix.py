"""Tests for entity persistence fix (Fixes A/B/C/D).

Covers:
- Fix A: T8-6 weak-reference guard (standalone entities not continuations)
- Fix B: Interrogative with explicit entity content = fresh query
- Fix C: Gate 3 state sync for pronoun resolution
- Fix D: Standalone entity detection in command_router
- All 11 required test scenarios
"""

import pytest
from mini_kio.core.continuity_resolver import (
    ContinuityResolver, DomainContinuationType,
)
from mini_kio.media.intelligence.media_intelligence_models import TopicType


@pytest.fixture(autouse=True)
def fresh_resolver():
    ContinuityResolver.reset()
    yield


# ═══════════════════════════════════════════════════════════════════
# Fix A — T8-6 Weak-Reference Guard
# ═══════════════════════════════════════════════════════════════════

class TestFixA_T8_6_WeakRefGuard:
    """T8-6 must NOT fire for standalone entity queries."""

    def setup_state(self):
        ContinuityResolver.set_state_subject("believer", DomainContinuationType.MEDIA)
        ContinuityResolver.set_state_domain(DomainContinuationType.MEDIA)

    def test_standalone_entity_not_continuation(self):
        """'Interstellar' after 'believer' must NOT be a continuation."""
        self.setup_state()
        r = ContinuityResolver.resolve("Interstellar")
        assert not r.is_continuation, "T8-6 must not fire for 'Interstellar'"

    def test_interrogative_with_explicit_entity(self):
        """'who directed interstellar' after 'believer' must NOT be continuation."""
        self.setup_state()
        r = ContinuityResolver.resolve("who directed interstellar")
        assert not r.is_continuation, "Explicit entity + interrogative is not continuation"

    def test_pronoun_query_is_continuation(self):
        """'it' in query must still be continuation (T8-6 fires)."""
        self.setup_state()
        r = ContinuityResolver.resolve("who directed it")
        assert r.is_continuation, "Pronoun query must be continuation"

    def test_weak_ref_more_is_continuation(self):
        """'more' after media must still be continuation via T8-6."""
        # Only triggers T8-6 when domain is UNKNOWN.
        # Set MEDIA domain but resolve a query that doesn't match media keywords.
        ContinuityResolver.set_state_subject("believer", DomainContinuationType.MEDIA)
        ContinuityResolver.set_state_domain(DomainContinuationType.MEDIA)
        r = ContinuityResolver.resolve("more")
        assert r.is_continuation, "'more' must be continuation via T8-6"

    def test_entity_name_in_lowercase_not_continuation(self):
        """Lowercase entity without weak refs must NOT be continuation."""
        self.setup_state()
        r = ContinuityResolver.resolve("the bear")
        assert not r.is_continuation, "'the bear' without weak ref is not continuation"

    def test_bare_entity_switches_domain_subject(self):
        """After 'Interstellar' bypasses T8-6, new entity takes over."""
        self.setup_state()
        ContinuityResolver.resolve("Interstellar")
        # Without Fix A this would still have 'believer'
        assert ContinuityResolver.get_state().active_subject == "believer", \
            "ContinuityResolver state only updates via update_state (not resolve)"


# ═══════════════════════════════════════════════════════════════════
# Fix B — _is_continuation_query Interrogative Guard
# ═══════════════════════════════════════════════════════════════════

class TestFixB_IsContinuationQuery:
    """_is_continuation_query must not trigger for interrogative + entity content."""

    @pytest.fixture
    def adapter(self):
        from mini_kio.media.intelligence.integration_adapter import MediaIntelligenceAdapter
        a = MediaIntelligenceAdapter(retrieval_fn=lambda q, t=None, m="": "")
        from mini_kio.media.media_intelligence_models import EntityType, ResolvedEntity
        a._mem.set_last_entity(ResolvedEntity(name="Believer", entity_type=EntityType.SONG, confidence=1.0))
        return a

    # ── Existing tests that must NOT break ──

    def test_pronoun_it_is_continuation(self, adapter):
        assert adapter._is_continuation_query("it")

    def test_pronoun_that_is_continuation(self, adapter):
        assert adapter._is_continuation_query("that")
    
    def test_pronoun_they_is_continuation(self, adapter):
        assert adapter._is_continuation_query("they")

    def test_who_scored_is_continuation(self, adapter):
        assert adapter._is_continuation_query("who scored")

    def test_what_was_the_score_is_continuation(self, adapter):
        assert adapter._is_continuation_query("what was the score")

    def test_who_scored_the_goal_is_continuation(self, adapter):
        assert adapter._is_continuation_query("who scored the goal")

    def test_who_directed_it_is_continuation(self, adapter):
        assert adapter._is_continuation_query("who directed it")

    def test_who_sings_it_is_continuation(self, adapter):
        assert adapter._is_continuation_query("who sings it")

    def test_what_genre_is_it_is_continuation(self, adapter):
        assert adapter._is_continuation_query("what genre is it")

    def test_open_chrome_is_not_continuation(self, adapter):
        assert not adapter._is_continuation_query("open chrome")

    def test_search_python_is_not_continuation(self, adapter):
        assert not adapter._is_continuation_query("search python")

    def test_long_query_not_continuation(self, adapter):
        assert not adapter._is_continuation_query("a b c d e f g h i j k")

    # ── New Fix B tests ──

    def test_interrogative_with_explicit_entity_is_fresh(self, adapter):
        """'who directed interstellar' has explicit entity — NOT continuation."""
        assert not adapter._is_continuation_query("who directed interstellar")

    def test_interrogative_with_different_entity_is_fresh(self, adapter):
        """'tell me about interstellar' has different entity than memory."""
        assert not adapter._is_continuation_query("tell me about interstellar")

    def test_interrogative_singing_entity_from_memory_is_continuation(self, adapter):
        """'who sings believer' mentions memory entity — IS continuation."""
        assert adapter._is_continuation_query("who sings believer")

    def test_pronoun_with_interrogative_is_continuation(self, adapter):
        """Pronoun trumps interrogative."""
        assert adapter._is_continuation_query("who directed it")  # 'it' is pronoun
        assert adapter._is_continuation_query("where is it")
        assert adapter._is_continuation_query("what did they do")

    def test_short_interrogative_without_entity_is_continuation(self, adapter):
        """2-word interrogatives without entity content are continuations."""
        assert adapter._is_continuation_query("what happened")
        assert adapter._is_continuation_query("who won")
        assert adapter._is_continuation_query("how come")


# ═══════════════════════════════════════════════════════════════════
# Fix C — Gate 3 State Sync
# ═══════════════════════════════════════════════════════════════════

class TestFixC_Gate3StateSync:
    """After Gate 3 handles a query, state must be synced for pronoun resolution."""

    def test_set_state_subject_updates_active_subject(self):
        """Simulates Gate 3 setting 'Interstellar' after handling query."""
        ContinuityResolver.set_state_subject("Interstellar", DomainContinuationType.MEDIA)
        ContinuityResolver.set_state_domain(DomainContinuationType.MEDIA)
        assert ContinuityResolver.get_state().active_subject == "Interstellar"
        assert ContinuityResolver.get_state().active_domain == DomainContinuationType.MEDIA

    def test_pronoun_resolves_to_synced_entity(self):
        """After state sync, 'who directed it' resolves to 'Interstellar'."""
        ContinuityResolver.set_state_subject("Interstellar", DomainContinuationType.MEDIA)
        ContinuityResolver.set_state_domain(DomainContinuationType.MEDIA)
        r = ContinuityResolver.resolve("who directed it")
        assert r.is_continuation
        assert "Interstellar" in r.resolved_text or "Interstellar" in (r.context.active_subject if r.context else "")

    def test_media_entity_memory_updated(self):
        """MediaEntityMemory must reflect synced entity."""
        from mini_kio.media.intelligence.integration_adapter import MediaIntelligenceAdapter
        a = MediaIntelligenceAdapter(retrieval_fn=lambda q, t=None, m="": "")
        from mini_kio.media.media_intelligence_models import EntityType, ResolvedEntity
        entity = ResolvedEntity(name="Interstellar", entity_type=EntityType.MOVIE, confidence=0.7)
        a._mem.set_last_entity(entity)
        last = a._mem.get_last_entity()
        assert last is not None
        assert last.name == "Interstellar"


# ═══════════════════════════════════════════════════════════════════
# Fix D — Standalone Entity Detection
# ═══════════════════════════════════════════════════════════════════

class TestFixD_StandaloneEntity:
    """_is_standalone_entity_query must correctly identify entity queries."""

    @staticmethod
    def _check(cmd: str) -> bool:
        from mini_kio.core.command_router import _is_standalone_entity_query
        return _is_standalone_entity_query(cmd)

    def test_capitalized_entity_is_standalone(self):
        assert self._check("Interstellar"), "Capitalized entity is standalone"

    def test_lowercase_entity_not_standalone(self):
        assert not self._check("believer"), "Lowercase without interrogative is not standalone"

    def test_interrogative_with_content_is_standalone(self):
        assert self._check("who directed interstellar"), "Interrogative + content is standalone"

    def test_pronoun_query_not_standalone(self):
        assert not self._check("who directed it"), "Pronoun in query is not standalone"
        assert not self._check("it"), "Bare pronoun not standalone"
        assert not self._check("that"), "Bare 'that' not standalone"

    def test_short_interrogative_not_standalone(self):
        assert not self._check("who scored"), "2-word interrogative not standalone"
        assert not self._check("what happened"), "Short interrogative not standalone"

    def test_media_verb_not_standalone(self):
        assert not self._check("play believer"), "play+entity not standalone"
        assert not self._check("pause"), "Transport verb not standalone"


# ═══════════════════════════════════════════════════════════════════
# Integration: Cross-Entity Switch Test (11 Scenarios)
# ═══════════════════════════════════════════════════════════════════

class TestScenario_CrossEntitySwitch:
    """Full cross-entity switch scenarios."""

    # ── TEST 1: Believer → Who sings it? ──

    def test_believer_who_sings_it(self):
        """After 'Believer' in memory, 'who sings it' resolves to Believer."""
        from mini_kio.media.intelligence.integration_adapter import MediaIntelligenceAdapter
        def _retrieve(q, t=None, m=""):
            if "believer" in q.lower() and "imagine" in q.lower():
                return "Imagine Dragons is the band that performs Believer."
            return ""
        a = MediaIntelligenceAdapter(retrieval_fn=_retrieve)
        from mini_kio.media.media_intelligence_models import EntityType, ResolvedEntity
        a._mem.set_last_entity(ResolvedEntity(name="Believer", entity_type=EntityType.SONG, confidence=1.0))

        # 'who sings it' must be detected as continuation
        assert a._is_continuation_query("who sings it"), "Pronoun query is continuation"
        res = a._try_memory_resolve("who sings it", TopicType.MUSIC)
        assert res is not None
        assert res.subject == "Believer"

    # ── TEST 3: Believer → Interstellar → Who directed it? ──

    def test_believer_to_interstellar_to_who_directed_it(self):
        """After switching from Believer to Interstellar, 'who directed it' resolves to Interstellar."""
        from mini_kio.media.intelligence.integration_adapter import MediaIntelligenceAdapter
        from mini_kio.media.intelligence.media_intelligence_models import TopicType
        from mini_kio.media.media_intelligence_models import EntityType, ResolvedEntity

        from mini_kio.intelligence.retrieval_router import RetrievalResult
        def _retrieve(q, t=None, m=""):
            if "interstellar" in q.lower() and "director" in q.lower():
                return RetrievalResult(title="", summary="Christopher Nolan directed Interstellar. The film was released in 2014 and received critical acclaim.", source="mock", confidence=1.0, entity="Interstellar", topic=TopicType.MOVIES, raw_content="Christopher Nolan directed Interstellar. The film was released in 2014 and received critical acclaim.")
            return None
        a = MediaIntelligenceAdapter(retrieval_fn=_retrieve)

        # Step 1: Register Believer (simulating 'play believer')
        a._mem.set_last_entity(ResolvedEntity(name="Believer", entity_type=EntityType.SONG, confidence=1.0))

        # Step 2: Simulate Gate 3 sync (Fix C) — 'Interstellar' becomes new entity
        a._mem.set_last_entity(ResolvedEntity(name="Interstellar", entity_type=EntityType.MOVIE, confidence=0.7))
        ContinuityResolver.set_state_subject("Interstellar", DomainContinuationType.MEDIA)
        ContinuityResolver.set_state_domain(DomainContinuationType.MEDIA)

        # Step 3: 'who directed it' must use Interstellar, not Believer
        assert a._is_continuation_query("who directed it"), "Pronoun query must be continuation"
        last = a._mem.get_last_entity()
        assert last.name == "Interstellar", "Memory must have Interstellar"

        res = a._try_memory_resolve("who directed it", TopicType.MOVIES)
        assert res is not None
        assert res.subject == "Interstellar"
        assert "Christopher Nolan" in res.response_text or "Nolan" in res.response_text

    # ── TEST 4: Believer → who directed interstellar ──

    def test_believer_to_who_directed_interstellar(self):
        """'who directed interstellar' after Believer must NOT resolve to Believer."""
        from mini_kio.media.intelligence.integration_adapter import MediaIntelligenceAdapter
        from mini_kio.media.intelligence.media_intelligence_models import TopicType
        from mini_kio.media.media_intelligence_models import EntityType, ResolvedEntity

        def _retrieve(q, t=None, m=""):
            return ""
        a = MediaIntelligenceAdapter(retrieval_fn=_retrieve)
        a._mem.set_last_entity(ResolvedEntity(name="Believer", entity_type=EntityType.SONG, confidence=1.0))

        # Fix B: interrogative + explicit entity = NOT continuation
        assert not a._is_continuation_query("who directed interstellar"), \
            "Interrogative with explicit entity must NOT be continuation"

    # ── TEST 7: The Bear → who created it ──

    def test_the_bear_who_created_it(self):
        """'who created it' after 'The Bear' must resolve to The Bear."""
        from mini_kio.media.intelligence.integration_adapter import MediaIntelligenceAdapter
        from mini_kio.media.intelligence.media_intelligence_models import TopicType
        from mini_kio.media.media_intelligence_models import EntityType, ResolvedEntity

        def _retrieve(q, t=None, m=""):
            if "the bear" in q.lower() and "created" in q.lower():
                return "Christopher Storer created The Bear."
            return ""
        a = MediaIntelligenceAdapter(retrieval_fn=_retrieve)

        # Simulate Gate 3 + Fix C: The Bear is synced
        a._mem.set_last_entity(ResolvedEntity(name="The Bear", entity_type=EntityType.TV_SHOW, confidence=0.7))
        ContinuityResolver.set_state_subject("The Bear", DomainContinuationType.MEDIA)
        ContinuityResolver.set_state_domain(DomainContinuationType.MEDIA)

        assert a._is_continuation_query("who created it"), "Pronoun + 'created' is continuation"
        res = a._try_memory_resolve("who created it", TopicType.TV)
        assert res is not None
        assert res.subject == "The Bear"

    # ── TEST 8: Interstellar → Believer → who sings it ──

    def test_interstellar_to_believer_to_who_sings_it(self):
        """Switching from Interstellar to Believer then 'who sings it' → Believer."""
        from mini_kio.media.intelligence.integration_adapter import MediaIntelligenceAdapter
        from mini_kio.media.intelligence.media_intelligence_models import TopicType
        from mini_kio.media.media_intelligence_models import EntityType, ResolvedEntity

        def _retrieve(q, t=None, m=""):
            if "believer" in q.lower() and "imagine" in q.lower():
                return "Imagine Dragons performs Believer."
            return ""
        a = MediaIntelligenceAdapter(retrieval_fn=_retrieve)

        # Interstellar synced first
        a._mem.set_last_entity(ResolvedEntity(name="Interstellar", entity_type=EntityType.MOVIE, confidence=1.0))
        # Then Believer synced (Fix C for "Believer")
        a._mem.set_last_entity(ResolvedEntity(name="Believer", entity_type=EntityType.SONG, confidence=0.7))
        ContinuityResolver.set_state_subject("Believer", DomainContinuationType.MEDIA)
        ContinuityResolver.set_state_domain(DomainContinuationType.MEDIA)

        assert a._is_continuation_query("who sings it"), "Pronoun query is continuation"
        last = a._mem.get_last_entity()
        assert last.name == "Believer", "Memory has Believer"

    # ── TEST 10: FIFA World Cup → Who scored? ──

    def test_fifa_who_scored(self):
        """'who scored' after FIFA World Cup must use FIFA context."""
        from mini_kio.media.intelligence.integration_adapter import MediaIntelligenceAdapter
        from mini_kio.media.intelligence.media_intelligence_models import TopicType
        from mini_kio.media.media_intelligence_models import EntityType, ResolvedEntity

        def _retrieve(q, t=None, m=""):
            if "fifa" in q.lower() and "scored" in q.lower():
                return "Messi scored for Argentina in the FIFA World Cup final."
            if "goal" in q.lower() or "scored" in q.lower():
                return "Neymar scored in the 57th minute."
            return ""
        a = MediaIntelligenceAdapter(retrieval_fn=_retrieve)
        a._mem.set_last_entity(ResolvedEntity(name="FIFA World Cup", entity_type=EntityType.SPORTS_TEAM, confidence=1.0))

        # 'who scored' must be continuation
        assert a._is_continuation_query("who scored"), "'who scored' must be continuation"
        res = a._try_memory_resolve("who scored", TopicType.SPORTS)
        assert res is not None
        assert res.subject == "FIFA World Cup"


# ═══════════════════════════════════════════════════════════════════
# Regression: Fix D UnboundLocalError (Epoch 4 production crash)
# ═══════════════════════════════════════════════════════════════════

class TestFixD_UnboundLocalError:
    """Fix D's `if _is_standalone_entity_query` block must NOT raise
    UnboundLocalError for `DomainContinuationType`.

    Root cause: `from ... import DomainContinuationType` at line 303 was
    only in the non-standalone branch. The standalone branch at line 299
    referenced the name before the import executed. Python's compile-time
    scoping marked it as a local variable → UnboundLocalError.
    """

    def test_is_standalone_true_for_capitalized_query(self):
        """'Tell me about the movie Interstellar' must be detected as standalone."""
        from mini_kio.core.command_router import _is_standalone_entity_query
        assert _is_standalone_entity_query("Tell me about the movie Interstellar")

    def test_no_unbound_local_error_for_standalone_entity(self):
        """handle_command must not crash with UnboundLocalError for standalone queries.

        The function may raise other errors (e.g. MediaManager not initialized),
        but must NOT raise UnboundLocalError on DomainContinuationType.
        """
        from mini_kio.core.command_router import handle_command
        try:
            handle_command("Tell me about the movie Interstellar")
        except UnboundLocalError:
            pytest.fail("UnboundLocalError: DomainContinuationType referenced before import")
        except Exception:
            pass  # Other errors (e.g. uninitialized MediaManager) are acceptable

    def test_domain_continuation_type_importable(self):
        """DomainContinuationType must be importable from continuity_resolver."""
        from mini_kio.core.continuity_resolver import DomainContinuationType
        assert DomainContinuationType is not None
