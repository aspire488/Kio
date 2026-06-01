from mini_kio.llm.knowledge_fallback import KnowledgeFallback


class TestKnowledgeFallbackAlignment:
    def setup_method(self):
        self.kb = KnowledgeFallback()

    def test_kio_identity_fallback(self):
        response = self.kb.get_fallback("what is kio")
        assert response is not None
        assert "KIO" in response

    def test_creator_fallback(self):
        response = self.kb.get_fallback("who is joel")
        assert response is not None
        assert "Joel" in response

    def test_general_topics_not_stored_locally(self):
        assert self.kb.get_fallback("what is python") is None
        assert self.kb.get_fallback("teach me kubernetes") is None

    def test_knowledge_failure_is_truthful(self):
        response = self.kb.get_knowledge_failure("what is branch prediction")
        assert "couldn't retrieve information" in response.lower()

    def test_continuation_is_none(self):
        response = self.kb.get_continuation("next")
        assert response is None
