"""Tests for Atomic Habits retrieval fix (topic-aware role rewriting, BOOKS topic routing).

Validates:
- _rewrite_retrieval produces topic-specific queries (BOOKS → author, not writer creator)
- BOOKS topics resolve through _try_memory_resolve correctly
- Classifier recognizes "wrote" as BOOKS keyword
- 6 regression scenarios from production validation
"""

import pytest
from mini_kio.media.intelligence.integration_adapter import MediaIntelligenceAdapter
from mini_kio.media.intelligence.media_intelligence_models import TopicType
from mini_kio.media.media_intelligence_models import EntityType, ResolvedEntity


@pytest.fixture
def fresh_adapter():
    a = MediaIntelligenceAdapter(retrieval_fn=lambda q, t=None, m="": "")
    yield a


@pytest.fixture
def adapter_with_atomic_habits():
    """Adapter with Atomic Habits in memory (BOOKS topic)."""
    def _retrieve(q, t=None, m=""):
        if "author" in q.lower() and "atomic" in q.lower():
            return "James Clear is the author of Atomic Habits. He writes about habit formation."
        return ""
    a = MediaIntelligenceAdapter(retrieval_fn=_retrieve)
    a._mem.set_last_entity(ResolvedEntity(name="Atomic Habits", entity_type=EntityType.BOOK, confidence=1.0))
    return a


@pytest.fixture
def adapter_with_the_bear():
    """Adapter with The Bear in memory (TV topic)."""
    def _retrieve(q, t=None, m=""):
        if "the bear" in q.lower():
            return "Christopher Storer created The Bear. The show premiered on Hulu."
        return ""
    a = MediaIntelligenceAdapter(retrieval_fn=_retrieve)
    a._mem.set_last_entity(ResolvedEntity(name="The Bear", entity_type=EntityType.TV_SHOW, confidence=1.0))
    return a


@pytest.fixture
def adapter_with_interstellar():
    """Adapter with Interstellar in memory (MOVIE topic)."""
    def _retrieve(q, t=None, m=""):
        ql = q.lower()
        if "interstellar" in ql and "director" in ql:
            return "Christopher Nolan directed Interstellar."
        if "interstellar" in ql and "composer" in ql:
            return "Hans Zimmer composed the score for Interstellar."
        return ""
    a = MediaIntelligenceAdapter(retrieval_fn=_retrieve)
    a._mem.set_last_entity(ResolvedEntity(name="Interstellar", entity_type=EntityType.MOVIE, confidence=1.0))
    return a


@pytest.fixture
def adapter_with_believer():
    """Adapter with Believer in memory (MUSIC topic)."""
    def _retrieve(q, t=None, m=""):
        ql = q.lower()
        if "believer" in ql and "imagine" in ql:
            return "Imagine Dragons wrote and performed Believer."
        return ""
    a = MediaIntelligenceAdapter(retrieval_fn=_retrieve)
    a._mem.set_last_entity(ResolvedEntity(name="Believer", entity_type=EntityType.SONG, confidence=1.0))
    return a


@pytest.fixture
def adapter_with_fifa():
    """Adapter with FIFA World Cup in memory (SPORTS topic)."""
    def _retrieve(q, t=None, m=""):
        return ""
    a = MediaIntelligenceAdapter(retrieval_fn=_retrieve)
    a._mem.set_last_entity(ResolvedEntity(name="FIFA World Cup 2026", entity_type=EntityType.SPORTS_TEAM, confidence=1.0))
    return a


# ═══════════════════════════════════════════════════════════════════
# Fix A: Topic-aware role rewriting in _rewrite_retrieval
# ═══════════════════════════════════════════════════════════════════

class TestQueryRewriteTopicAware:
    """_rewrite_retrieval must produce topic-specific queries for role questions."""

    def test_books_wrote_becomes_author(self, fresh_adapter):
        """'who wrote it' for BOOKS → 'subject author'."""
        result = fresh_adapter._rewrite_retrieval("Who wrote it?", TopicType.BOOKS, "Atomic Habits")
        assert "author" in result
        assert "writer creator" not in result

    def test_books_created_becomes_author(self, fresh_adapter):
        """'who created it' for BOOKS → 'subject author'."""
        result = fresh_adapter._rewrite_retrieval("Who created it?", TopicType.BOOKS, "Atomic Habits")
        assert "author" in result

    def test_movie_wrote_becomes_writer(self, fresh_adapter):
        """'who wrote it' for MOVIES → 'subject writer'."""
        result = fresh_adapter._rewrite_retrieval("Who wrote it?", TopicType.MOVIES, "Interstellar")
        assert "writer" in result
        assert "author" not in result

    def test_movie_created_becomes_creator(self, fresh_adapter):
        """'who created it' for MOVIES → 'subject creator'."""
        result = fresh_adapter._rewrite_retrieval("Who created it?", TopicType.MOVIES, "Interstellar")
        assert "creator" in result

    def test_tv_created_becomes_creator(self, fresh_adapter):
        """'who created it' for TV → 'subject creator'."""
        result = fresh_adapter._rewrite_retrieval("Who created it?", TopicType.TV, "The Bear")
        assert "creator" in result

    def test_music_wrote_becomes_songwriter(self, fresh_adapter):
        """'who wrote it' for MUSIC → 'subject songwriter' (non-disambiguated entity)."""
        result = fresh_adapter._rewrite_retrieval("Who wrote it?", TopicType.MUSIC, "Thriller")
        assert "songwriter" in result
        assert "writer creator" not in result

    def test_published_books_becomes_publisher(self, fresh_adapter):
        """'who published it' for BOOKS → 'subject publisher'."""
        result = fresh_adapter._rewrite_retrieval("Who published it?", TopicType.BOOKS, "Atomic Habits")
        assert "publisher" in result

    def test_when_released_books_becomes_publication_date(self, fresh_adapter):
        """'when was it released' for BOOKS → 'subject publication date'."""
        result = fresh_adapter._rewrite_retrieval("When was it released?", TopicType.BOOKS, "Atomic Habits")
        assert "publication date" in result

    def test_when_released_movie_becomes_release_date(self, fresh_adapter):
        """'when was it released' for MOVIES → 'subject release date'."""
        result = fresh_adapter._rewrite_retrieval("When was it released?", TopicType.MOVIES, "Interstellar")
        assert "release date" in result

    # ── existing behavior must NOT regress ──

    def test_sports_wrote_default(self, fresh_adapter):
        """'who wrote it' for SPORTS → default 'writer creator' (no sport-specific mapping)."""
        result = fresh_adapter._rewrite_retrieval("Who wrote it?", TopicType.SPORTS, "FIFA World Cup")
        assert "writer creator" in result

    def test_directed_preserved(self, fresh_adapter):
        """'who directed it' for MOVIES → 'subject director' (unchanged)."""
        result = fresh_adapter._rewrite_retrieval("Who directed it?", TopicType.MOVIES, "Interstellar")
        assert "director" in result

    def test_directed_preserved_books(self, fresh_adapter):
        """'who directed it' for BOOKS → 'subject director' (unchanged)."""
        result = fresh_adapter._rewrite_retrieval("Who directed it?", TopicType.BOOKS, "Atomic Habits")
        assert result == "Atomic Habits director"


# ═══════════════════════════════════════════════════════════════════
# Fix B: BOOKS in trusted topics for _try_memory_resolve
# ═══════════════════════════════════════════════════════════════════

class TestMemoryResolveBooksTopic:
    """_try_memory_resolve must use BOOKS topic for memory-resolved queries."""

    def test_who_wrote_it_resolves_from_books_memory(self, adapter_with_atomic_habits):
        """'who wrote it' after 'Atomic Habits' must resolve with BOOKS topic."""
        assert adapter_with_atomic_habits._is_continuation_query("who wrote it")
        res = adapter_with_atomic_habits._try_memory_resolve("who wrote it", TopicType.UNKNOWN)
        assert res is not None, "Must resolve from BOOKS memory"
        assert res.subject == "Atomic Habits"
        assert "James Clear" in (res.response_text or "")

    def test_continuation_query_detection(self, adapter_with_atomic_habits):
        """'who wrote it' must be detected as continuation (pronoun 'it')."""
        assert adapter_with_atomic_habits._is_continuation_query("who wrote it")

    def test_entity_preserved_in_response(self, adapter_with_atomic_habits):
        """Response subject must be 'Atomic Habits', not rewritten subject."""
        res = adapter_with_atomic_habits._try_memory_resolve("who wrote it", TopicType.UNKNOWN)
        assert res is not None
        assert res.subject == "Atomic Habits"


# ═══════════════════════════════════════════════════════════════════
# Fix C: "wrote" classified as BOOKS keyword
# ═══════════════════════════════════════════════════════════════════

class TestClassifierBooksWrote:
    """topic_classifier must recognize 'wrote' as BOOKS keyword."""

    def test_wrote_classified_as_books(self):
        """'wrote' alone should classify as BOOKS."""
        from mini_kio.media.intelligence.topic_classifier import classify_topic
        result = classify_topic("who wrote atomic habits")
        assert result.topic == TopicType.BOOKS, f"Expected BOOKS, got {result.topic}"

    def test_wrote_it_classified_as_books(self):
        """'who wrote it' should classify as BOOKS (has 'wrote')."""
        from mini_kio.media.intelligence.topic_classifier import classify_topic
        result = classify_topic("who wrote it")
        assert result.topic == TopicType.BOOKS, f"Expected BOOKS, got {result.topic}"


# ═══════════════════════════════════════════════════════════════════
# Regression: 6 required scenarios
# ═══════════════════════════════════════════════════════════════════

class TestRegressionScenarios:
    """6 production validation scenarios must all pass."""

    # SCENARIO 1: Atomic Habits → Who wrote it? → James Clear
    def test_atomic_habits_who_wrote_it(self, adapter_with_atomic_habits):
        res = adapter_with_atomic_habits._try_memory_resolve("who wrote it", TopicType.BOOKS)
        assert res is not None
        assert res.subject == "Atomic Habits"
        assert "James Clear" in (res.response_text or "")

    # SCENARIO 2: The Bear → Who created it? → Christopher Storer
    def test_the_bear_who_created_it(self, adapter_with_the_bear):
        res = adapter_with_the_bear._try_memory_resolve("who created it", TopicType.TV)
        assert res is not None
        assert res.subject == "The Bear"
        assert "Storer" in (res.response_text or "")

    # SCENARIO 3: Interstellar → Who directed it? → Christopher Nolan
    def test_interstellar_who_directed_it(self, adapter_with_interstellar):
        res = adapter_with_interstellar._try_memory_resolve("who directed it", TopicType.MOVIES)
        assert res is not None
        assert res.subject == "Interstellar"
        assert "Nolan" in (res.response_text or "")

    # SCENARIO 4: Interstellar → Who composed it? → Hans Zimmer
    def test_interstellar_who_composed_it(self, adapter_with_interstellar):
        res = adapter_with_interstellar._try_memory_resolve("who composed it", TopicType.MOVIES)
        assert res is not None
        assert res.subject == "Interstellar"
        assert "Zimmer" in (res.response_text or "")

    # SCENARIO 5: Believer → Who sings it? → Imagine Dragons
    def test_believer_who_sings_it(self, adapter_with_believer):
        res = adapter_with_believer._try_memory_resolve("who sings it", TopicType.MUSIC)
        assert res is not None
        assert res.subject == "Believer"
        assert "Imagine Dragons" in (res.response_text or "")

    # SCENARIO 6: FIFA World Cup 2026 → Latest standings → context retained
    def test_fifa_latest_standings_context(self, adapter_with_fifa):
        """'latest standings' after FIFA must resolve with FIFA context."""
        assert adapter_with_fifa._is_continuation_query("latest standings")
        res = adapter_with_fifa._try_memory_resolve("latest standings", TopicType.SPORTS)
        assert res is not None
        assert res.subject == "FIFA World Cup 2026"


# ═══════════════════════════════════════════════════════════════════
# Non-regression: existing behavior must still pass
# ═══════════════════════════════════════════════════════════════════

class TestNonRegression:
    """Existing working behavior must not break."""

    def test_interrogative_with_entity_is_fresh(self, fresh_adapter):
        """'who directed interstellar' must NOT be continuation (fresh query)."""
        fresh_adapter._mem.set_last_entity(ResolvedEntity(name="Believer", entity_type=EntityType.SONG, confidence=1.0))
        assert not fresh_adapter._is_continuation_query("who directed interstellar")

    def test_standalone_entity_not_continuation(self, fresh_adapter):
        """'Interstellar' after Believer must NOT be continuation."""
        fresh_adapter._mem.set_last_entity(ResolvedEntity(name="Believer", entity_type=EntityType.SONG, confidence=1.0))
        assert not fresh_adapter._is_continuation_query("Interstellar")

    def test_pronoun_continuation(self, fresh_adapter):
        """'it' must be continuation regardless of entity."""
        fresh_adapter._mem.set_last_entity(ResolvedEntity(name="The Bear", entity_type=EntityType.TV_SHOW, confidence=1.0))
        assert fresh_adapter._is_continuation_query("who directed it")

    def test_empty_retrieval_fallback_not_done(self, fresh_adapter):
        """Empty retrieval must return fallback message, not 'Done.'."""
        fresh_adapter._mem.set_last_entity(ResolvedEntity(name="Nonexistent", entity_type=EntityType.BOOK, confidence=1.0))
        res = fresh_adapter._try_memory_resolve("who wrote it", TopicType.BOOKS)
        assert res is not None
        assert res.response_text != ""
        assert "Done." not in (res.response_text or "")
        assert "information" in (res.response_text or "").lower()
