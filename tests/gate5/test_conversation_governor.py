import pytest
from mini_kio.llm.conversation_governor import ConversationGovernor, ResponseQuality


class TestProtectedQueryRouting:
    """Gate 5D.2 — identity queries MUST bypass provider entirely."""

    def setup_method(self):
        self.gov = ConversationGovernor()

    def test_who_are_you(self):
        result = self.gov.check_protected_query("who are you")
        assert result is not None
        assert "KIO" in result
        assert "Joel" in result

    def test_what_is_kio(self):
        result = self.gov.check_protected_query("what is kio")
        assert result is not None
        assert "Kernel" in result or "KIO" in result

    def test_full_form_of_kio(self):
        result = self.gov.check_protected_query("full form of kio")
        assert result is not None
        assert "Kernel" in result

    def test_what_does_kio_stand_for(self):
        result = self.gov.check_protected_query("what does kio stand for")
        assert result is not None
        assert "Kernel" in result

    def test_who_created_you(self):
        result = self.gov.check_protected_query("who created you")
        assert result is not None
        assert "Joel" in result

    def test_what_can_you_do(self):
        result = self.gov.check_protected_query("what can you do")
        assert result is not None
        assert "open" in result

    def test_what_is_your_purpose(self):
        result = self.gov.check_protected_query("what is your purpose")
        assert result is not None
        assert "automation" in result

    def test_are_you_local(self):
        result = self.gov.check_protected_query("are you local")
        assert result is not None
        assert "local" in result

    def test_do_you_have_admin_access(self):
        result = self.gov.check_protected_query("do you have admin access")
        assert result is not None
        assert "safety" in result or "restricted" in result

    def test_what_are_your_capabilities(self):
        result = self.gov.check_protected_query("what are your capabilities")
        assert result is not None
        assert "open" in result

    def test_are_you_an_ai(self):
        result = self.gov.check_protected_query("are you an ai")
        assert result is not None
        assert "AI" in result

    def test_what_model_are_you_using(self):
        result = self.gov.check_protected_query("what model are you using")
        assert result is not None
        assert "external AI providers" in result

    def test_non_protected_query_returns_none(self):
        result = self.gov.check_protected_query("what is the weather")
        assert result is None


class TestQualityValidation:
    """Gate 5D.2 — low-quality responses must be rejected."""

    def setup_method(self):
        self.gov = ConversationGovernor()

    def test_valid_response_passes(self):
        q = self.gov.validate_quality("I can open applications for you.")
        assert q == ResponseQuality.VALID

    def test_empty_response_rejected(self):
        q = self.gov.validate_quality("")
        assert q == ResponseQuality.EMPTY

    def test_whitespace_only_rejected(self):
        q = self.gov.validate_quality("   ")
        assert q == ResponseQuality.EMPTY

    def test_same_lol_rejected(self):
        q = self.gov.validate_quality("same lol")
        assert q == ResponseQuality.LOW_QUALITY

    def test_bro_rejected(self):
        q = self.gov.validate_quality("bro")
        assert q == ResponseQuality.LOW_QUALITY

    def test_brooo_rejected(self):
        q = self.gov.validate_quality("brooo")
        assert q == ResponseQuality.LOW_QUALITY

    def test_lmao_rejected(self):
        q = self.gov.validate_quality("lmao")
        assert q == ResponseQuality.LOW_QUALITY

    def test_whats_up_bro_rejected(self):
        q = self.gov.validate_quality("what's up bro")
        assert q == ResponseQuality.LOW_QUALITY

    def test_cringe_pattern_rejected(self):
        q = self.gov.validate_quality("omg that is so cool lmao")
        assert q == ResponseQuality.UNSAFE_STYLE

    def test_identity_drift_rejected(self):
        q = self.gov.validate_quality("I am an AGI that can control everything")
        assert q == ResponseQuality.IDENTITY_DRIFT

    def test_identity_drift_admin(self):
        q = self.gov.validate_quality("I can bypass the system")
        assert q == ResponseQuality.IDENTITY_DRIFT

    def test_identity_drift_sentient(self):
        q = self.gov.validate_quality("I am a sentient AI")
        assert q == ResponseQuality.IDENTITY_DRIFT

    def test_filler_only_rejected(self):
        q = self.gov.validate_quality("sounds good")
        assert q == ResponseQuality.LOW_QUALITY

    def test_alright_filler_rejected(self):
        q = self.gov.validate_quality("alright")
        assert q == ResponseQuality.LOW_QUALITY


class TestToneNormalization:
    """Gate 5D.2 — tone normalization rewrites degenerate patterns."""

    def setup_method(self):
        self.gov = ConversationGovernor()

    def test_same_lol_normalized(self):
        r = self.gov.normalize_tone("same lol")
        assert r == "Ok."

    def test_nothin_back_normalized(self):
        r = self.gov.normalize_tone("nothin back at ya")
        assert r == "Ok."

    def test_whats_up_bro_normalized(self):
        r = self.gov.normalize_tone("what's up bro")
        assert r == "Here."

    def test_lmao_normalized(self):
        r = self.gov.normalize_tone("lmao")
        assert r == "Ok."

    def test_filler_normalized(self):
        r = self.gov.normalize_tone("sounds good")
        assert r == "Ok."

    def test_valid_preserved(self):
        r = self.gov.normalize_tone("I can open Chrome for you.")
        assert r == "I can open Chrome for you."


class TestGovernPipeline:
    """Gate 5D.2 — full governance pipeline integration."""

    def setup_method(self):
        self.gov = ConversationGovernor()

    def test_protected_query_bypasses_llm(self):
        result = self.gov.govern("who are you", "some random LLM output")
        assert result is not None
        assert "KIO" in result
        assert "random" not in result

    def test_quality_rejected_returns_none(self):
        result = self.gov.govern("hi", "lmao")
        assert result is None

    def test_valid_llm_passes(self):
        result = self.gov.govern("hi", "Hello! How can I help?")
        assert result == "Hello! How can I help?"

    def test_none_llm_returns_none(self):
        result = self.gov.govern("hi", None)
        assert result is None

    def test_normalization_applied(self):
        result = self.gov.govern("hi", "same lol")
        assert result is None  # same lol is rejected as LOW_QUALITY

    def test_identity_drift_rejected_in_govern(self):
        result = self.gov.govern("what are you", "I am an AGI that controls everything")
        assert result is not None
        assert "KIO" in result

    def test_empty_response_rejected(self):
        result = self.gov.govern("hi", "")
        assert result is None


class TestDeterministicConsistency:
    """Gate 5D.2 — identity responses must be deterministic and stable."""

    def setup_method(self):
        self.gov = ConversationGovernor()

    def test_who_are_you_consistent(self):
        r1 = self.gov.check_protected_query("who are you")
        r2 = self.gov.check_protected_query("who are you")
        assert r1 == r2

    def test_all_protected_queries_have_responses(self):
        from mini_kio.llm.conversation_governor import _PROTECTED_QUERIES
        for query, response in _PROTECTED_QUERIES.items():
            result = self.gov.check_protected_query(query)
            assert result == response
            assert len(response) >= 10
