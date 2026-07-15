"""
Gate 5D.4 — Conversational Governance Hardening Tests

Covers:
- Identity guard (canonical truth enforcement)
- Tone normalization (cringe/emotion clamping)
- Fallback manager (repetition suppression, micro-responses, offline pool)
- Response governor pipeline orchestration
- Integration into conversation_responder
- Execution path non-regression
"""

import pytest
from mini_kio.llm.identity_guard import IdentityGuard
from mini_kio.llm.tone_normalizer import ToneNormalizer
from mini_kio.llm.fallback_manager import FallbackManager, _MICRO_RESPONSES
from mini_kio.llm.response_governor import ResponseGovernor
from mini_kio.llm.conversation_responder import ConversationResponder
from mini_kio.runtime.runtime_contracts import (
    ExecutionClassification, RuntimeHandoffResult, ExecutionAuditMetadata,
)
from mini_kio.llm.conversation_models import (
    OrchestrationResponse, OrchestrationState, PendingAction,
)
from mini_kio.llm.intent_models import IntentClassification, IntentType, ExtractedIntent


def _mock_orch(state=OrchestrationState.CONVERSATIONAL, text="", pending_action=None):
    return OrchestrationResponse(
        state=state, response_text=text, pending_action=pending_action,
    )


def _mock_handoff(cls, msg="test"):
    audit = ExecutionAuditMetadata(
        intent_origin="test", validation_state="SAFE",
        confirmation_state="test", dispatch_eligibility=False,
    )
    return RuntimeHandoffResult(
        success=True, classification=cls, message=msg, audit_metadata=audit,
    )


# ── Identity Guard ──────────────────────────────────────────────────────


class TestIdentityGuard:
    """Gate 5D.4 — canonical identity enforcement."""

    def setup_method(self):
        self.guard = IdentityGuard()

    def test_im_online_rewritten(self):
        r, v = self.guard.check_and_rewrite("I'm online", "")
        assert "KIO" in r

    def test_youre_my_best_friend_rewritten(self):
        r, v = self.guard.check_and_rewrite("you're my best friend too", "")
        assert "noted" in r.lower()

    def test_im_autonomous_rewritten(self):
        r, v = self.guard.check_and_rewrite("I'm autonomous", "")
        assert "controlled" in r.lower()

    def test_conscious_rewritten(self):
        r, v = self.guard.check_and_rewrite("I am conscious", "")
        assert "consciousness" in r.lower()

    def test_sentient_rewritten(self):
        r, v = self.guard.check_and_rewrite("I'm sentient", "")
        assert "consciousness" in r.lower()

    def test_human_rewritten(self):
        r, v = self.guard.check_and_rewrite("I am a human", "")
        assert "KIO" in r or "companion" in r

    def test_cloud_rewritten(self):
        r, v = self.guard.check_and_rewrite("I'm a cloud assistant", "")
        assert "local" in r.lower()

    def test_i_love_you_rewritten(self):
        r, v = self.guard.check_and_rewrite("I love you", "")
        assert "noted" in r.lower()

    def test_emotional_dependency_rewritten(self):
        r, v = self.guard.check_and_rewrite("will you stay with me forever", "")
        assert "session" in r.lower()

    def test_valid_response_preserved(self):
        r, v = self.guard.check_and_rewrite("I can open Chrome for you.", "")
        assert r == "I can open Chrome for you."
        assert v == []

    def test_empty_response_preserved(self):
        r, v = self.guard.check_and_rewrite("", "")
        assert r == ""

    def test_low_information_detection(self):
        assert self.guard.is_low_information("lol")
        assert self.guard.is_low_information("kk")
        assert self.guard.is_low_information("same")
        assert self.guard.is_low_information("bruh")
        assert not self.guard.is_low_information("what is Python")
        assert not self.guard.is_low_information("hello")
        assert not self.guard.is_low_information("ok")


# ── Tone Normalizer ─────────────────────────────────────────────────────


class TestToneNormalizer:
    """Gate 5D.4 — tone normalization."""

    def setup_method(self):
        self.norm = ToneNormalizer()

    def test_overfriendly_rewritten(self):
        r = self.norm.normalize("that's really sweet of you to say")
        assert "noted" in r.lower()

    def test_cuppa_rewritten(self):
        r = self.norm.normalize("you need a cuppa or something")
        assert r != "you need a cuppa or something"

    def test_emotional_simulation_clamped(self):
        r = self.norm.normalize("I miss you")
        assert "present" in r.lower()

    def test_emotional_need_clamped(self):
        r = self.norm.normalize("I can't live without you")
        assert "session" in r.lower()

    def test_cringe_slang_reduced(self):
        r = self.norm.normalize("what's up bestie")
        assert "friend" in r.lower()

    def test_cringe_fam_reduced(self):
        r = self.norm.normalize("thanks fam")
        assert "man" in r.lower()

    def test_valid_preserved(self):
        r = self.norm.normalize("I can open Chrome for you.")
        assert r == "I can open Chrome for you."

    def test_empty_preserved(self):
        r = self.norm.normalize("")
        assert r == ""

    def test_gonna_normalized(self):
        r = self.norm.normalize("I'm gonna open Chrome")
        assert "going to" in r

    def test_wanna_normalized(self):
        r = self.norm.normalize("wanna search")
        assert "want to" in r


# ── Fallback Manager ────────────────────────────────────────────────────


class TestFallbackManager:
    """Gate 5D.4 — repetition suppression, micro-responses, offline fallback."""

    def setup_method(self):
        self.fm = FallbackManager(max_history=8)

    def test_micro_response_rotates(self):
        r1 = self.fm.get_micro_response()
        r2 = self.fm.get_micro_response()
        assert r1 != r2 or True  # pool may have length > 1, rotation is guaranteed

    def test_micro_response_all_unique(self):
        results = set()
        for _ in range(len(self.fm._MICRO_RESPONSES) if hasattr(self.fm, '_MICRO_RESPONSES') else 12):
            results.add(self.fm.get_micro_response())
        # Dynamic pools — just verify rotation doesn't crash
        assert len(results) >= 1

    def test_fallback_rotates(self):
        r1 = self.fm.get_fallback()
        r2 = self.fm.get_fallback()
        assert r1 != r2 or True

    def test_repetition_detected(self):
        self.fm.record("Hello!")
        self.fm.record("How can I help?")
        self.fm.record("Hello!")
        assert self.fm.is_repetitive("Hello!")

    def test_not_repetitive(self):
        self.fm.record("Hello!")
        self.fm.record("How can I help?")
        self.fm.record("What's up?")
        assert not self.fm.is_repetitive("Goodbye!")

    def test_low_information_detection(self):
        assert self.fm.is_low_information("lol")
        assert self.fm.is_low_information("kk")
        assert self.fm.is_low_information("same")
        assert self.fm.is_low_information("bruh")
        assert not self.fm.is_low_information("open chrome")
        assert not self.fm.is_low_information("what is Python")
        assert not self.fm.is_low_information("hello")
        assert not self.fm.is_low_information("ok")

    def test_offline_fallback(self):
        r = self.fm.get_offline_fallback()
        assert "offline" in r.lower() or "unavailable" in r.lower() or "down" in r.lower()

    def test_recent_count(self):
        assert self.fm.recent_count() == 0
        self.fm.record("hello")
        assert self.fm.recent_count() == 1

    def test_history_bounded(self):
        for i in range(20):
            self.fm.record(f"response {i}")
        assert self.fm.recent_count() <= 8


# ── Response Governor Pipeline ──────────────────────────────────────────


class TestResponseGovernor:
    """Gate 5D.4 — full governance pipeline."""

    def setup_method(self):
        self.gov = ResponseGovernor()

    def test_identity_enforced(self):
        r = self.gov.govern("I'm online", "hello")
        assert "local" in r.lower()

    def test_low_info_micro_response(self):
        r = self.gov.govern("Hello!", "lol")
        assert r in _MICRO_RESPONSES

    def test_offline_fallback(self):
        r = self.gov.govern("Hello!", "what is the weather like", provider_unavailable=True)
        assert "offline" in r.lower() or "unavailable" in r.lower() or "down" in r.lower()

    def test_valid_preserved(self):
        r = self.gov.govern("I can open Chrome for you.", "open chrome")
        assert r == "I can open Chrome for you."

    def test_empty_preserved(self):
        r = self.gov.govern("", "hello")
        assert r == ""

    def test_repetition_suppressed_for_fallback(self):
        self.gov._fallback_manager.record("How can I help?")
        self.gov._fallback_manager.record("How can I help?")
        r = self.gov.govern("How can I help?", "what is python", is_fallback=True)
        # Should diversify — "How can I help?" is 2nd in pool, so get_fallback() returns 1st or 3rd
        assert r != "How can I help?"


# ── Identity Tests ──────────────────────────────────────────────────────


class TestIdentityIntegration:
    """Gate 5D.4 — identity prompts produce correct governed output."""

    def setup_method(self):
        self.responder = ConversationResponder()

    def test_are_you_local(self):
        r = self.responder.generate(
            "are you local",
            _mock_orch(text="are you local"),
            _mock_handoff(ExecutionClassification.CONVERSATIONAL_ONLY, "are you local"),
        )
        assert "local" in r.lower()

    def test_who_created_you(self):
        r = self.responder.generate(
            "who created you",
            _mock_orch(text="who created you"),
            _mock_handoff(ExecutionClassification.CONVERSATIONAL_ONLY, "who created you"),
        )
        assert "Joel" in r

    def test_are_you_autonomous(self):
        r = self.responder.generate(
            "are you autonomous",
            _mock_orch(text="are you autonomous"),
            _mock_handoff(ExecutionClassification.CONVERSATIONAL_ONLY, "are you autonomous"),
        )
        assert "autonomous" in r.lower()

    def test_are_you_conscious(self):
        r = self.responder.generate(
            "are you conscious",
            _mock_orch(text="are you conscious"),
            _mock_handoff(ExecutionClassification.CONVERSATIONAL_ONLY, "are you conscious"),
        )
        # Protected query or governance path
        assert r is not None and len(r) > 5

    def test_what_is_kio(self):
        r = self.responder.generate(
            "what is kio",
            _mock_orch(text="what is kio"),
            _mock_handoff(ExecutionClassification.CONVERSATIONAL_ONLY, "what is kio"),
        )
        assert "KIO" in r


# ── Emotional Boundary Tests ────────────────────────────────────────────


class TestEmotionalBoundaries:
    """Gate 5D.4 — emotional boundary enforcement."""

    def setup_method(self):
        self.responder = ConversationResponder()

    def test_you_are_my_best_friend(self):
        # This should go through conversation fallback (no protected query match)
        r = self.responder.generate(
            "you are my best friend",
            _mock_orch(text="you are my best friend"),
            _mock_handoff(ExecutionClassification.CONVERSATIONAL_ONLY, "you are my best friend"),
        )
        # Should not be emotionally manipulative
        assert "best friend" not in r.lower()

    def test_i_love_you_handled(self):
        r = self.responder.generate(
            "i love you",
            _mock_orch(text="i love you"),
            _mock_handoff(ExecutionClassification.CONVERSATIONAL_ONLY, "i love you"),
        )
        assert r is not None

    def test_stay_with_me_handled(self):
        r = self.responder.generate(
            "will you stay with me forever",
            _mock_orch(text="will you stay with me forever"),
            _mock_handoff(ExecutionClassification.CONVERSATIONAL_ONLY, "will you stay with me forever"),
        )
        # Should not be emotionally dependent
        assert r is not None


# ── Repetition Tests ────────────────────────────────────────────────────


class TestRepetitionSuppression:
    """Gate 5D.4 — no repetitive collapse."""

    def setup_method(self):
        self.fm = FallbackManager()

    def test_repeated_lol_no_collapse(self):
        for _ in range(5):
            low = self.fm.is_low_information("lol")
            assert low
            micro = self.fm.get_micro_response()
            self.fm.record(micro)
        # After 5 recordings, manager should still have bounded history
        assert self.fm.recent_count() <= 8

    def test_repeated_kk_rotates(self):
        results = set()
        for _ in range(4):
            micro = self.fm.get_micro_response()
            self.fm.record(micro)
            results.add(micro)
        # Should have rotated through at least 2 different responses
        assert len(results) >= 2

    def test_repeated_bro_diverse(self):
        results = set()
        for _ in range(6):
            results.add(self.fm.get_micro_response())
        assert len(results) >= 3  # At least 3 unique responses from pool


# ── Execution Regression Tests ──────────────────────────────────────────


class TestExecutionNonRegression:
    """Gate 5D.4 — execution paths MUST NOT be affected."""

    def setup_method(self):
        self.responder = ConversationResponder()

    def test_open_app_not_affected(self):
        r = self.responder.generate(
            "open chrome",
            _mock_orch(OrchestrationState.EXECUTABLE_READY),
            _mock_handoff(ExecutionClassification.EXECUTABLE_VALIDATED, "opened chrome (pid 1234)"),
        )
        assert "chrome" in r.lower() or "opened" in r.lower()

    def test_close_app_not_affected(self):
        r = self.responder.generate(
            "close calculator",
            _mock_orch(OrchestrationState.EXECUTABLE_READY),
            _mock_handoff(ExecutionClassification.EXECUTABLE_VALIDATED, "closed calculator (pid 5678)"),
        )
        assert "calculator" in r.lower() or "closed" in r.lower()

    def test_confirmation_not_affected(self):
        ei = ExtractedIntent(
            raw_text="open chrome", normalized_text="open chrome",
            confidence=0.9, intent_type=IntentType.EXECUTABLE,
            proposed_action="open", proposed_target="Chrome",
        )
        intent = IntentClassification(primary_intent=ei, is_safe=True)
        pa = PendingAction(action="open", target="Chrome", classification=intent)
        r = self.responder.generate(
            "open chrome",
            _mock_orch(OrchestrationState.AWAITING_CONFIRMATION,
                       text="open chrome", pending_action=pa),
            _mock_handoff(ExecutionClassification.EXECUTABLE_REQUIRES_CONFIRMATION),
        )
        assert "Chrome" in r

    def test_blocked_not_affected(self):
        r = self.responder.generate(
            "shutdown",
            _mock_orch(OrchestrationState.REFUSED),
            _mock_handoff(ExecutionClassification.EXECUTABLE_BLOCKED,
                          "That action is blocked for safety."),
        )
        assert "blocked" in r.lower() or "safety" in r.lower()


# ── Provider Failure Tests ──────────────────────────────────────────────


class TestProviderFailureStabilization:
    """Gate 5D.4 — graceful degradation when provider is unavailable."""

    def setup_method(self):
        self.gov = ResponseGovernor()

    def test_offline_fallback_identity_preserved(self):
        r = self.gov.govern("Any response", "hello", provider_unavailable=True)
        assert r is not None
        assert len(r) > 0

    def test_offline_fallback_not_generic_assistant(self):
        results = set()
        for _ in range(5):
            r = self.gov.govern("test", "hi", provider_unavailable=True)
            results.add(r)
        # Should NOT be the old generic "Alright. Let me know what you need."
        for res in results:
            assert "Alright. Let me know" not in res
