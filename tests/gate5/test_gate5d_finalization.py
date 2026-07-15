"""
Gate 5D Finalization — Response Authority Unification + Conversational Reliability Hardening

Tests:
- identity consistency (who're u → canonical)
- educational continuity (Malayalam teaching + "more")
- semantic normalization (what's python → knowledge)
- anti-generic filtering (reject "Alright. Let me know what you need.")
- repeated-response blocking
- Malayalam teaching continuity
- fallback educational responses
- conversational coherence validation
- provider failure stabilization
- no execution regression
"""

import pytest
from mini_kio.llm.semantic_quality import SemanticQualityScorer, ResponseSemanticQuality
from mini_kio.llm.knowledge_fallback import KnowledgeFallback
from mini_kio.llm.fallback_manager import _MICRO_RESPONSES
from mini_kio.llm.response_governor import ResponseGovernor
from mini_kio.llm.conversation_responder import ConversationResponder
from mini_kio.runtime.runtime_contracts import (
    ExecutionClassification, RuntimeHandoffResult, ExecutionAuditMetadata,
)
from mini_kio.llm.conversation_models import (
    OrchestrationResponse, OrchestrationState,
)

EXPLICIT_FAILURE = "I couldn't retrieve information for that topic right now."


def _mock_orch(state=OrchestrationState.CONVERSATIONAL, text=""):
    return OrchestrationResponse(state=state, response_text=text, pending_action=None)


def _mock_handoff(cls, message="test"):
    audit = ExecutionAuditMetadata(
        intent_origin="test", validation_state="SAFE",
        confirmation_state="test", dispatch_eligibility=False,
    )
    return RuntimeHandoffResult(
        success=True, classification=cls, message=message, audit_metadata=audit,
    )


# ── Semantic Quality Scoring ────────────────────────────────────────────


class TestSemanticQualityScoring:
    """Gate 5D Finalization — semantic quality scoring."""

    def setup_method(self):
        self.scorer = SemanticQualityScorer()

    def test_strong_response(self):
        q = self.scorer.score("Python is a programming language.", "what is python")
        assert q == ResponseSemanticQuality.STRONG

    def test_generic_rejected(self):
        q = self.scorer.score("Alright. Let me know what you need.", "what is python")
        assert q == ResponseSemanticQuality.GENERIC

    def test_empty_rejected(self):
        q = self.scorer.score("", "hello")
        assert q == ResponseSemanticQuality.EMPTY

    def test_filler_rejected(self):
        q = self.scorer.score("lol", "hello")
        assert q == ResponseSemanticQuality.GENERIC

    def test_weak_short_rejected(self):
        q = self.scorer.score("okay", "what is python")
        assert q == ResponseSemanticQuality.GENERIC

    def test_educational_filler_rejected(self):
        q = self.scorer.score("cool", "teach me python")
        assert q == ResponseSemanticQuality.GENERIC

    def test_question_filler_rejected(self):
        q = self.scorer.score("lol", "what's the weather?")
        assert q == ResponseSemanticQuality.GENERIC

    def test_is_generic_detection(self):
        assert self.scorer.is_generic("Alright. Let me know what you need.")
        assert self.scorer.is_generic("what's up")
        assert self.scorer.is_generic("Got it.")
        assert not self.scorer.is_generic("Python is a language.")

    def test_is_filler_detection(self):
        assert self.scorer.is_filler("lol")
        assert self.scorer.is_filler("😂")
        assert self.scorer.is_filler("kk")
        assert not self.scorer.is_filler("Python is great.")


# ── Knowledge Fallback ──────────────────────────────────────────────────


class TestKnowledgeFallback:
    """Gate 5D Finalization — deterministic educational fallback."""

    def setup_method(self):
        self.kf = KnowledgeFallback()

    def test_removed_general_topics_have_no_local_fallback(self):
        # Topics not in _MORE_TOPICS or _OFFLINE_KNOWLEDGE should return None
        for prompt in (
            "what is java",
            "explain recursion",
            "what is an operating system",
            "what is machine learning",
            "what is ai",
            "what is quantum physics",
        ):
            assert self.kf.get_fallback(prompt) is None

    def test_kio_fallback(self):
        r = self.kf.get_fallback("tell me about kio")
        assert r is not None
        assert "KIO" in r

    def test_unknown_topic(self):
        r = self.kf.get_fallback("what is quantum physics")
        assert r is None

    def test_detect_topic_kio(self):
        t = self.kf.detect_topic("what is kio")
        assert t == "kio"

    def test_detect_topic_missing(self):
        t = self.kf.detect_topic("hello world")
        assert t is None

    def test_is_educational_request(self):
        assert self.kf.is_educational_request("teach me python")
        assert self.kf.is_educational_request("what is recursion")
        assert self.kf.is_educational_request("explain AI")
        assert not self.kf.is_educational_request("hello")

    def test_is_continuation_request(self):
        assert self.kf.is_continuation_request("more")
        assert self.kf.is_continuation_request("continue")
        assert self.kf.is_continuation_request("tell me more")
        assert not self.kf.is_continuation_request("hello")

    def test_removed_aliases_no_longer_detected(self):
        assert self.kf.detect_topic("py") is None


class TestMalayalamTeaching:
    """Gate 5D Finalization — Malayalam educational continuity."""

    def setup_method(self):
        self.kf = KnowledgeFallback()

    def test_malayalam_pack_removed(self):
        r = self.kf.get_fallback("teach me malayalam")
        assert r is None

    def test_non_continuation_ignored(self):
        self.kf.get_fallback("teach me malayalam")
        r = self.kf.get_continuation("hello")
        assert r is None


# ── Response Governor Pipeline ──────────────────────────────────────────


class TestResponseGovernorFinalization:
    """Gate 5D Finalization — unified response governance pipeline."""

    def setup_method(self):
        self.gov = ResponseGovernor()

    def test_generic_replaced_with_diversified(self):
        r = self.gov.govern("Alright. Let me know what you need.", "what is python")
        assert r != "Alright. Let me know what you need."

    def test_generic_educational_replaced_with_knowledge(self):
        r = self.gov.govern("Alright. Let me know what you need.", "teach me python")
        assert r == EXPLICIT_FAILURE

    def test_identity_still_enforced(self):
        r = self.gov.govern("I'm online", "hello")
        assert "KIO" in r

    def test_tone_still_normalized(self):
        r = self.gov.govern("that's really sweet of you to say", "what is python")
        assert r != "that's really sweet of you to say"
        assert len(r) > 10

    def test_low_info_micro_response(self):
        r = self.gov.govern("Hello!", "lol")
        assert r in _MICRO_RESPONSES

    def test_offline_fallback(self):
        r = self.gov.govern("Hello!", "what is the weather like", provider_unavailable=True)
        assert "offline" in r.lower() or "unavailable" in r.lower()

    def test_valid_preserved(self):
        r = self.gov.govern("Python is a programming language.", "what is python")
        assert r == "Python is a programming language."

    def test_empty_preserved(self):
        r = self.gov.govern("", "hello")
        assert r == ""

    def test_diagnostics_exist(self):
        d = self.gov.get_diagnostics()
        assert "semantic_quality_rejected" in d
        assert "low_information_blocked" in d
        assert "educational_fallback_used" in d
        assert "repeated_response_blocked" in d
        assert "semantic_normalization_applied" in d


# ── Identity Consistency ───────────────────────────────────────────────


class TestIdentityConsistencyFinalization:
    """Gate 5D Finalization — identity consistency across variants."""

    def setup_method(self):
        self.responder = ConversationResponder()

    def test_who_re_u_normalized_to_identity(self):
        r = self.responder.generate(
            "who're u",
            _mock_orch(text="who're u"),
            _mock_handoff(ExecutionClassification.CONVERSATIONAL_ONLY, "who're u"),
        )
        assert "KIO" in r or "Joel" in r

    def test_whos_kio_normalized_to_identity(self):
        r = self.responder.generate(
            "whos kio",
            _mock_orch(text="whos kio"),
            _mock_handoff(ExecutionClassification.CONVERSATIONAL_ONLY, "whos kio"),
        )
        assert "KIO" in r

    def test_whats_kio_normalized(self):
        r = self.responder.generate(
            "whats kio",
            _mock_orch(text="whats kio"),
            _mock_handoff(ExecutionClassification.CONVERSATIONAL_ONLY, "whats kio"),
        )
        assert "Kernel" in r or "KIO" in r

    def test_identity_all_variants_canonical(self):
        for q in ("who are you", "who're u", "whos kio", "what is kio", "whats kio"):
            r = self.responder.generate(
                q,
                _mock_orch(text=q),
                _mock_handoff(ExecutionClassification.CONVERSATIONAL_ONLY, q),
            )
            assert r is not None and len(r) > 5


# ── Anti-Generic Response Filtering ────────────────────────────────────


class TestAntiGenericFiltering:
    """Gate 5D Finalization — generic responses are blocked."""

    def test_all_generics_detected(self):
        scorer = SemanticQualityScorer()
        generics = [
            "Alright. Let me know what you need.",
            "what's up",
            "whats up",
            "Got it.",
            "Same lol",
            "okay",
            "cool",
            "nice",
            "fair",
            "Sounds good.",
        ]
        for g in generics:
            q = scorer.score(g, "what is python")
            assert q in (ResponseSemanticQuality.GENERIC, ResponseSemanticQuality.WEAK), f"'{g}' not rejected"

    def test_generic_educational_routes_to_knowledge(self):
        self.gov = ResponseGovernor()
        r = self.gov.govern("Alright. Let me know what you need.", "teach me python")
        assert r == EXPLICIT_FAILURE
        assert "Alright" not in r


# ── Educational Continuity ──────────────────────────────────────────────


class TestEducationalContinuity:
    """Gate 5D Finalization — educational continuity via responder."""

    def setup_method(self):
        self.gov = ResponseGovernor()

    def test_get_continuation_is_always_none(self):
        # Lesson mode removed, so get_continuation should always be None
        self.gov.govern("cool", "teach me malayalam")
        r = self.gov.get_continuation("more")
        assert r is None

    def test_get_continuation_non_edu(self):
        self.gov.govern("Python is a programming language.", "what is python")
        r = self.gov.get_continuation("more")
        assert r is None  # No active lesson

    def test_is_continuation_detection(self):
        assert self.gov.is_continuation_request("more")
        assert self.gov.is_continuation_request("continue")
        assert not self.gov.is_continuation_request("hello")


# ── Coherence Validation ────────────────────────────────────────────────


class TestCoherenceValidation:
    """Gate 5D Finalization — conversational coherence validation."""

    def setup_method(self):
        self.scorer = SemanticQualityScorer()

    def test_question_filler_detected(self):
        q = self.scorer.score("lol", "what is python?")
        assert q == ResponseSemanticQuality.GENERIC

    def test_educational_filler_detected(self):
        q = self.scorer.score("cool", "teach me malayalam")
        assert q == ResponseSemanticQuality.GENERIC

    def test_valid_answer_passes(self):
        q = self.scorer.score("Python is a programming language.", "what is python?")
        assert q == ResponseSemanticQuality.STRONG


# ── Execution Non-Regression ────────────────────────────────────────────


class TestExecutionNonRegressionFinalization:
    """Gate 5D Finalization — execution paths MUST NOT be affected."""

    def setup_method(self):
        self.responder = ConversationResponder()

    def test_open_app(self):
        r = self.responder.generate(
            "open chrome",
            _mock_orch(OrchestrationState.EXECUTABLE_READY),
            _mock_handoff(ExecutionClassification.EXECUTABLE_VALIDATED, "opened chrome (pid 1234)"),
        )
        assert "chrome" in r.lower() or "opened" in r.lower()

    def test_close_app(self):
        r = self.responder.generate(
            "close calculator",
            _mock_orch(OrchestrationState.EXECUTABLE_READY),
            _mock_handoff(ExecutionClassification.EXECUTABLE_VALIDATED, "closed calculator (pid 5678)"),
        )
        assert "calculator" in r.lower() or "closed" in r.lower()

    def test_confirmation(self):
        r = self.responder.generate(
            "open chrome",
            _mock_orch(OrchestrationState.AWAITING_CONFIRMATION, text="open chrome"),
            _mock_handoff(ExecutionClassification.EXECUTABLE_REQUIRES_CONFIRMATION),
        )
        assert "confirm" in r.lower() or "continue" in r.lower()
        assert len(r) > 5

    def test_blocked(self):
        r = self.responder.generate(
            "shutdown",
            _mock_orch(OrchestrationState.REFUSED),
            _mock_handoff(ExecutionClassification.EXECUTABLE_BLOCKED, "blocked for safety."),
        )
        assert "blocked" in r.lower() or "safety" in r.lower()


# ── Fallback Educational Response ───────────────────────────────────────


class TestFallbackEducationalResponses:
    """Gate 5D Finalization — educational fallback when provider unavailable."""

    def setup_method(self):
        self.gov = ResponseGovernor()

    def test_python_educational_fallback(self):
        r = self.gov.govern("Alright. Let me know what you need.", "teach me python")
        assert r == EXPLICIT_FAILURE

    def test_javascript_educational_fallback(self):
        r = self.gov.govern("Got it.", "what is javascript", is_fallback=True)
        assert r == EXPLICIT_FAILURE

    def test_malayalam_fallback(self):
        r = self.gov.govern("cool", "teach me malayalam")
        assert r == EXPLICIT_FAILURE

    def test_unknown_topic_generic(self):
        r = self.gov.govern("Alright.", "what is quantum physics")
        assert r != "Alright."


# ── Repeated Response Blocking ─────────────────────────────────────────


class TestRepeatedResponseBlocking:
    """Gate 5D Finalization — repeated responses are diversified."""

    def setup_method(self):
        self.gov = ResponseGovernor()

    def test_repeated_generic_gets_diversified(self):
        self.gov._fallback_manager.record("How can I help?")
        self.gov._fallback_manager.record("How can I help?")
        r = self.gov.govern("How can I help?", "hi", is_fallback=True)
        assert r != "How can I help?"
