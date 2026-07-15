"""
test_adapter_intelligence_integration.py
Regression tests for MediaIntelligenceAdapter integration:
- Memory-first resolution order
- Continuation query detection (including sports terms)
- Entity overwrite protection (last entity wins)
- Recommendation memory-first check
- Source tracing markers
"""
import pytest
from mini_kio.media.intelligence.media_intelligence_models import TopicType, IntelligenceResult
from mini_kio.intelligence.retrieval_router import RetrievalResult
from mini_kio.media.intelligence.integration_adapter import MediaIntelligenceAdapter
from mini_kio.media.media_intelligence_models import EntityType, ResolvedEntity


class TestContinuationQueryDetection:

    @pytest.fixture
    def adapter(self):
        return MediaIntelligenceAdapter(retrieval_fn=lambda q, t=None, m="": None)

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


class TestEntityOverwriteProtection:

    @pytest.fixture
    def adapter(self):
        def _retrieve(q, t=None, m=""):
            if "interstellar" in q.lower() and "direct" in q.lower():
                content = "Christopher Nolan directed Interstellar, a 2014 sci-fi film."
                return RetrievalResult(title="Interstellar", summary=content, source="mock", confidence=1.0, entity="Interstellar", topic=TopicType.MOVIES, raw_content=content)
            if "interstellar" in q.lower():
                content = "Interstellar is a 2014 film directed by Christopher Nolan."
                return RetrievalResult(title="Interstellar", summary=content, source="mock", confidence=1.0, entity="Interstellar", topic=TopicType.MOVIES, raw_content=content)
            return None
        a = MediaIntelligenceAdapter(retrieval_fn=_retrieve)
        # Register Believer first
        a._register_entity("Believer", TopicType.MUSIC, 
                           result=RetrievalResult(title="Believer", summary="Believer by Imagine Dragons", source="mock", confidence=1.0, entity="Believer", topic=TopicType.MUSIC), 
                           confidence=1.0)
        # Register Interstellar second (overwrites)
        a._register_entity("Interstellar", TopicType.MOVIES, 
                           result=RetrievalResult(title="Interstellar", summary="Interstellar is a 2014 film directed by Christopher Nolan", source="mock", confidence=1.0, entity="Interstellar", topic=TopicType.MOVIES), 
                           confidence=1.0)
        return a

    def test_last_entity_wins(self, adapter):
        last = adapter._mem.get_last_entity()
        assert last is not None
        assert last.name == "Interstellar"

    def test_context_last_subject_is_interstellar(self, adapter):
        assert adapter._ctx.get_value("last_subject") == "Interstellar"

    def test_context_last_raw_mentions_nolan(self, adapter):
        raw = adapter._ctx.get_value("last_raw", "")
        assert "Christopher Nolan" in raw

    def test_memory_resolve_who_directed_it(self, adapter):
        res = adapter._try_memory_resolve("who directed it", TopicType.MOVIES)
        assert res is not None
        assert res.subject == "Interstellar"
        assert "Christopher Nolan" in res.response_text

    def test_media_context_last_resolved_entity_is_interstellar(self, adapter):
        assert adapter._media_context.last_resolved_entity is not None
        assert adapter._media_context.last_resolved_entity.name == "Interstellar"


class TestCrossDomainEntityChain:

    @pytest.fixture
    def adapter(self):
        def _retrieve(q, t=None, m=""):
            if "young" in q.lower() and "sheldon" in q.lower():
                content = "Young Sheldon stars Iain Armitage. It is a prequel to The Big Bang Theory."
                return RetrievalResult(title="Young Sheldon", summary=content, source="mock", confidence=1.0, entity="Young Sheldon", topic=TopicType.TV, raw_content=content)
            return RetrievalResult(title="mock", summary="mocked response", source="mock", confidence=1.0, entity="mock", topic=TopicType.UNKNOWN)
        a = MediaIntelligenceAdapter(retrieval_fn=_retrieve)
        a._register_entity("Believer", TopicType.MUSIC, 
                           result=RetrievalResult(title="Believer", summary="Believer by Imagine Dragons", source="mock", confidence=1.0, entity="Believer", topic=TopicType.MUSIC), 
                           confidence=1.0)
        a._register_entity("Interstellar", TopicType.MOVIES, 
                           result=RetrievalResult(title="Interstellar", summary="Interstellar 2014 Christopher Nolan", source="mock", confidence=1.0, entity="Interstellar", topic=TopicType.MOVIES), 
                           confidence=1.0)
        a._register_entity("Young Sheldon", TopicType.TV, 
                           result=RetrievalResult(title="Young Sheldon", summary="Young Sheldon stars Iain Armitage", source="mock", confidence=1.0, entity="Young Sheldon", topic=TopicType.TV), 
                           confidence=1.0)
        return a

    def test_last_entity_is_young_sheldon(self, adapter):
        assert adapter._mem.get_last_entity().name == "Young Sheldon"

    def test_interstellar_query_does_not_resolve_to_believer(self, adapter):
        res = adapter._try_memory_resolve("interstellar", TopicType.MOVIES)
        assert res is None or res.subject != "Believer"


class TestSportsContinuationChain:

    @pytest.fixture
    def adapter(self):
        def _retrieve(q, t=None, m=""):
            if "brazil" in q.lower() or "argentina" in q.lower():
                return "Brazil beat Argentina 2-1 in a thrilling match. Neymar scored in the 57th minute."
            return "mocked sports response"
        a = MediaIntelligenceAdapter(retrieval_fn=_retrieve)
        a._register_entity("Brazil vs Argentina", TopicType.SPORTS,
                           raw_response="Brazil beat Argentina 2-1. Neymar scored in the 57th minute. Messi assisted.",
                           confidence=1.0)
        return a

    def test_who_scored_resolves_from_sports_memory(self, adapter):
        res = adapter._try_memory_resolve("who scored", TopicType.SPORTS)
        assert res is not None
        assert res.subject == "Brazil vs Argentina"

    def test_what_was_the_score_resolves(self, adapter):
        res = adapter._try_memory_resolve("what was the score", TopicType.SPORTS)
        assert res is not None

    def test_who_scored_the_goal_resolves(self, adapter):
        res = adapter._try_memory_resolve("who scored the goal", TopicType.SPORTS)
        assert res is not None


class TestMemoryFirstResolution:

    @pytest.fixture
    def adapter(self):
        a = MediaIntelligenceAdapter(retrieval_fn=lambda q, t=None, m="": "fresh retrieval result")
        a._register_entity("Interstellar", TopicType.MOVIES,
                           raw_response="Interstellar is a 2014 film directed by Christopher Nolan",
                           confidence=1.0)
        return a

    def test_continuation_returns_memory_not_retrieval(self, adapter):
        res = adapter._handle_music("who directed it", 0.8)
        assert res is not None
        assert "memory:Interstellar" in res.source or "memory" in res.source or "Christopher Nolan" in res.response_text

    def test_fresh_query_passes_through_to_retrieval(self, adapter):
        res = adapter._handle_music("believer", 0.8)
        assert res is not None
        assert res.source == "retrieval"

    def test_topic_passed_to_retrieve(self, adapter):
        retrieved_topics = []

        def tracking_retrieve(q, t=None, m=""):
            retrieved_topics.append(t)
            return "tracked"

        a = MediaIntelligenceAdapter(retrieval_fn=tracking_retrieve)
        a._safe_retrieve("believer", topic="MUSIC")
        assert "MUSIC" in retrieved_topics

    def test_sports_mode_passed_to_retrieve(self, adapter):
        retrieved_modes = []

        def tracking_retrieve(q, t=None, m=""):
            retrieved_modes.append(m)
            return "tracked"

        a = MediaIntelligenceAdapter(retrieval_fn=tracking_retrieve)
        a._safe_retrieve("standings", topic="SPORTS", mode="STANDINGS")
        assert "STANDINGS" in retrieved_modes
