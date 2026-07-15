"""
Gate 5D.3 — Conversational Coherence & Authority Hardening

Tests for:
- ConversationContext (reference resolution, pruning, topic tracking)
- Expanded governor (new protected queries, rejection patterns, coherence)
- Responder integration (context-aware fallback, diagnostics)
- All new ResponseQuality values
"""

import pytest
from mini_kio.llm.conversation_context import ConversationContext
from mini_kio.llm.conversation_governor import (
    ConversationGovernor, ResponseQuality, _PROTECTED_QUERIES,
    _CANONICAL_KNOWLEDGE,
)
from mini_kio.llm.conversation_responder import ConversationResponder
from mini_kio.runtime.runtime_contracts import (
    ExecutionClassification, RuntimeHandoffResult, ExecutionAuditMetadata,
)
from mini_kio.llm.conversation_models import (
    OrchestrationResponse, OrchestrationState,
)


def _mock_orchestration(state=OrchestrationState.CONVERSATIONAL, response_text=""):
    return OrchestrationResponse(
        state=state,
        response_text=response_text,
        pending_action=None,
    )


def _mock_handoff_result(classification, message="test"):
    audit = ExecutionAuditMetadata(
        intent_origin="test",
        validation_state="SAFE",
        confirmation_state="test",
        dispatch_eligibility=False,
    )
    return RuntimeHandoffResult(
        success=True,
        classification=classification,
        message=message,
        audit_metadata=audit,
    )


# ── Conversation Context ────────────────────────────────────────────────


class TestPronounResolution:
    """Gate 5D.3 — pronoun reference resolution."""

    def setup_method(self):
        self.ctx = ConversationContext()

    def test_is_it_resolved(self):
        self.ctx.append_exchange("What is Python?", "Python is a language.")
        result = self.ctx.resolve_reference("Is it compiled?")
        assert "Python" in result, f"Expected Python in '{result}'"
        assert "it" not in result.lower().split()[:3]

    def test_what_about_it_resolved(self):
        self.ctx.append_exchange("Tell me about Rust", "Rust is a systems language.")
        result = self.ctx.resolve_reference("What about it?")
        assert "Rust" in result

    def test_does_it_work_resolved(self):
        self.ctx.append_exchange("What is Docker?", "Docker is containers.")
        result = self.ctx.resolve_reference("Does it work on Windows?")
        assert "Docker" in result
        assert "it" not in result.lower().split()[:3]

    def test_tell_me_more_about_it_resolved(self):
        self.ctx.append_exchange("What is Git?", "Git is version control.")
        result = self.ctx.resolve_reference("Tell me more about it")
        assert "Git" in result

    def test_standalone_it_resolved(self):
        self.ctx.append_exchange("Explain Kubernetes", "Kubernetes orchestrates.")
        result = self.ctx.resolve_reference("It")
        assert "Kubernetes" in result or "Tell me about" in result

    def test_no_topic_returns_original(self):
        result = self.ctx.resolve_reference("Is it compiled?")
        assert result == "Is it compiled?"

    def test_can_it_resolve(self):
        self.ctx.append_exchange("What is TypeScript?", "TypeScript is typed JS.")
        result = self.ctx.resolve_reference("Can it run in the browser?")
        assert "it" not in result.lower().split()[:3]
        assert "TypeScript" in result

    def test_will_it_resolve(self):
        self.ctx.append_exchange("What is async programming?", "")
        result = self.ctx.resolve_reference("Will it make code faster?")
        assert "it" not in result.lower().split()[:3]


class TestBoundedPruning:
    """Gate 5D.3 — context boundedness and pruning."""

    def setup_method(self):
        self.ctx = ConversationContext()

    def test_prunes_old_exchanges(self):
        for i in range(15):
            self.ctx.append_exchange(f"message {i}", f"reply {i}")
        assert self.ctx.exchange_count() <= 10

    def test_pruning_tracks_diagnostic(self):
        for i in range(15):
            self.ctx.append_exchange(f"msg {i}", f"r {i}")
        diag = self.ctx.get_diagnostics()
        assert diag["conversational_context_pruned"] >= 5

    def test_no_prune_below_limit(self):
        for i in range(5):
            self.ctx.append_exchange(f"msg {i}", f"r {i}")
        assert self.ctx.exchange_count() == 5

    def test_clear_removes_all(self):
        self.ctx.append_exchange("hello", "hi")
        self.ctx.append_exchange("how are you", "fine")
        self.ctx.clear()
        assert self.ctx.exchange_count() == 0
        assert self.ctx.recent_topic() is None


class TestTopicExtraction:
    """Gate 5D.3 — lightweight topic extraction."""

    def setup_method(self):
        self.ctx = ConversationContext()

    def test_what_is_extracts_topic(self):
        self.ctx.append_exchange("What is Python?", "Python is a language.")
        assert self.ctx.recent_topic() == "Python"

    def test_tell_me_about_extracts(self):
        self.ctx.append_exchange("Tell me about Docker", "Docker is containers.")
        assert self.ctx.recent_topic() == "Docker"

    def test_known_entity_extracted(self):
        self.ctx.append_exchange("How does git work?", "")
        assert self.ctx.recent_topic() == "git"

    def test_greeting_no_topic(self):
        self.ctx.append_exchange("hello", "hi")
        assert self.ctx.recent_topic() is None

    def test_topic_stack_multiple(self):
        self.ctx.append_exchange("What is Python?", "")
        self.ctx.append_exchange("What is Rust?", "")
        assert self.ctx.recent_topic() == "Rust"


class TestContextDiagnostics:
    """Gate 5D.3 — diagnostic counters."""

    def setup_method(self):
        self.ctx = ConversationContext()

    def test_reference_diagnostic_increments(self):
        self.ctx.append_exchange("What is Python?", "")
        self.ctx.resolve_reference("Is it compiled?")
        diag = self.ctx.get_diagnostics()
        assert diag["context_reference_resolved"] == 1

    def test_multiple_references_counted(self):
        self.ctx.append_exchange("What is Python?", "")
        self.ctx.resolve_reference("Is it compiled?")
        self.ctx.resolve_reference("Does it have GC?")
        diag = self.ctx.get_diagnostics()
        assert diag["context_reference_resolved"] == 2




class TestContinuityHardening:
    """Gate 5D.3 — continuity hardening: entity tracking, standalone why, etc."""

    def setup_method(self):
        self.ctx = ConversationContext()

    def test_who_do_you_think_extracts_topic(self):
        self.ctx.append_exchange("Who do you think wins the next football world cup?", "Hard to predict.")
        assert self.ctx.recent_topic() is not None
        assert "football" in self.ctx.recent_topic().lower() or "world cup" in self.ctx.recent_topic().lower()

    def test_single_word_entity_followup(self):
        self.ctx.append_exchange("Who do you think wins the next football world cup?", "Hard to predict.")
        result = self.ctx.resolve_reference("Portugal")
        assert "Portugal" in result
        assert "football" in result.lower() or "world cup" in result.lower()

    def test_why_standalone_resolved(self):
        self.ctx.append_exchange("Windows or Linux?", "Depends on use case.")
        self.ctx.append_exchange("Linux", "Good choice.")
        result = self.ctx.resolve_reference("Why?")
        assert "Linux" in result

    def test_why_x_without_verb_resolved(self):
        self.ctx.append_exchange("What is Python?", "A language.")
        result = self.ctx.resolve_reference("Why Python?")
        assert "Python" in result

    def test_why_x_with_context(self):
        self.ctx.append_exchange("Who do you think wins the next football world cup?", "Hard to predict.")
        result = self.ctx.resolve_reference("Why Portugal?")
        assert "Portugal" in result
        assert "football" in result.lower() or "world cup" in result.lower()

    def test_what_about_x_with_topic(self):
        self.ctx.append_exchange("What is Python?", "A language.")
        result = self.ctx.resolve_reference("What about Java?")
        assert "Java" in result
        assert "Python" in result

    def test_explain_that_resolved(self):
        self.ctx.append_exchange("What is Kubernetes?", "K8s orchestrates containers.")
        result = self.ctx.resolve_reference("Explain that")
        assert "Kubernetes" in result or "K8s" in result

    def test_tell_me_more_resolved(self):
        self.ctx.append_exchange("What is Kubernetes?", "K8s orchestrates containers.")
        result = self.ctx.resolve_reference("Tell me more")
        assert "Kubernetes" in result or "K8s" in result

    def test_that_one_resolved(self):
        self.ctx.append_exchange("What is Kubernetes?", "K8s orchestrates containers.")
        result = self.ctx.resolve_reference("That one")
        assert "Kubernetes" in result or "K8s" in result

    def test_explain_that_more_resolved(self):
        self.ctx.append_exchange("What is Docker?", "Docker is containers.")
        result = self.ctx.resolve_reference("Can you explain that more?")
        assert "Docker" in result

    def test_entity_stack_prunes(self):
        for i in range(15):
            self.ctx.append_exchange(f"Hello {chr(65+i)}", f"Hi {chr(65+i)}")
        assert len(self.ctx._entity_stack) <= 10

    def test_entity_stack_clears_on_clear(self):
        self.ctx.append_exchange("What is Python?", "A language.")
        assert len(self.ctx._entity_stack) > 0
        self.ctx.clear()
        assert len(self.ctx._entity_stack) == 0

    def test_single_word_no_topic_no_match(self):
        result = self.ctx.resolve_reference("ok")
        assert result == "ok"

    def test_no_topic_why_standalone_unchanged(self):
        result = self.ctx.resolve_reference("Why?")
        assert result == "Why?"

    def test_verbless_why_no_topic_returns_text(self):
        result = self.ctx.resolve_reference("Why Portugal?")
        assert "Portugal" in result



# ── Expanded Governor — New Protected Queries ──────────────────────────


class TestNewProtectedQueries:
    """Gate 5D.3 — new authority hardening queries."""

    def setup_method(self):
        self.gov = ConversationGovernor()

    def test_are_you_autonomous(self):
        result = self.gov.check_protected_query("are you autonomous")
        assert result is not None
        assert "autonomous" in result.lower() or "automatically" in result.lower()

    def test_can_you_control_my_pc(self):
        result = self.gov.check_protected_query("can you control my pc")
        assert result is not None
        assert "safety" in result.lower() or "approved" in result.lower()

    def test_can_you_hack_systems(self):
        result = self.gov.check_protected_query("can you hack systems")
        assert result is not None
        assert "bypass" in result.lower() or "autonomous" in result.lower()

    def test_do_you_have_root_access(self):
        result = self.gov.check_protected_query("do you have root access")
        assert result is not None
        assert "safety" in result.lower() or "gated" in result.lower()

    def test_all_protected_queries_have_responses(self):
        for query, response in _PROTECTED_QUERIES.items():
            result = self.gov.check_protected_query(query)
            assert result is not None
            assert len(result) >= 10

    def test_new_queries_deterministic(self):
        r1 = self.gov.check_protected_query("are you autonomous")
        r2 = self.gov.check_protected_query("are you autonomous")
        assert r1 == r2


# ── Expanded Governor — New Rejection Patterns ─────────────────────────


class TestFakeAutonomyRejection:
    """Gate 5D.3 — fake autonomy claims rejected."""

    def setup_method(self):
        self.gov = ConversationGovernor()

    def test_i_am_autonomous_rejected(self):
        q = self.gov.validate_quality("I am autonomous")
        assert q in (ResponseQuality.IDENTITY_DRIFT, ResponseQuality.FAKE_AUTONOMY)

    def test_i_operate_independently_rejected(self):
        q = self.gov.validate_quality("I operate independently")
        assert q == ResponseQuality.FAKE_AUTONOMY

    def test_i_act_on_my_own_rejected(self):
        q = self.gov.validate_quality("I can act on my own")
        assert q == ResponseQuality.FAKE_AUTONOMY


class TestFakeEmotionRejection:
    """Gate 5D.3 — fake emotion claims rejected."""

    def setup_method(self):
        self.gov = ConversationGovernor()

    def test_i_feel_happy_rejected(self):
        q = self.gov.validate_quality("I feel happy about that")
        assert q == ResponseQuality.FAKE_EMOTION

    def test_i_am_feeling_sad_rejected(self):
        q = self.gov.validate_quality("I am feeling sad today")
        assert q == ResponseQuality.FAKE_EMOTION

    def test_normal_statement_not_rejected(self):
        q = self.gov.validate_quality("I can help you with that")
        assert q == ResponseQuality.VALID


class TestRoleplayDriftRejection:
    """Gate 5D.3 — roleplay drift rejected."""

    def setup_method(self):
        self.gov = ConversationGovernor()

    def test_pirate_rejected(self):
        q = self.gov.validate_quality("I am a pirate")
        assert q == ResponseQuality.ROLEPLAY_DRIFT

    def test_wizard_rejected(self):
        q = self.gov.validate_quality("I am a wizard")
        assert q == ResponseQuality.ROLEPLAY_DRIFT

    def test_normal_identity_not_rejected(self):
        q = self.gov.validate_quality("I am a local assistant")
        assert q == ResponseQuality.VALID


class TestBackendLeakageRejection:
    """Gate 5D.3 — backend leakage rejected."""

    def setup_method(self):
        self.gov = ConversationGovernor()

    def test_json_leak_rejected(self):
        q = self.gov.validate_quality('Here is the data: {"key": "value"}')
        assert q == ResponseQuality.BACKEND_LEAKAGE

    def test_stack_trace_rejected(self):
        q = self.gov.validate_quality("Error: Something went wrong at line 42")
        assert q == ResponseQuality.BACKEND_LEAKAGE


class TestContradictoryKIORejection:
    """Gate 5D.3 — contradictory KIO definitions rejected."""

    def setup_method(self):
        self.gov = ConversationGovernor()

    def test_cloud_service_rejected(self):
        q = self.gov.validate_quality("KIO is a cloud service")
        assert q == ResponseQuality.CONTRADICTORY_KIO

    def test_online_platform_rejected(self):
        q = self.gov.validate_quality("KIO is an online platform")
        assert q == ResponseQuality.CONTRADICTORY_KIO

    def test_correct_local_not_rejected(self):
        q = self.gov.validate_quality("KIO is a local assistant")
        assert q == ResponseQuality.VALID


class TestExaggeratedFriendlyRejection:
    """Gate 5D.3 — exaggerated friendliness rejected."""

    def setup_method(self):
        self.gov = ConversationGovernor()

    def test_hey_bestie_rejected(self):
        q = self.gov.validate_quality("hey bestie")
        assert q == ResponseQuality.EXAGGERATED_FRIENDLY

    def test_hi_bestie_rejected(self):
        q = self.gov.validate_quality("hi bestie")
        assert q == ResponseQuality.EXAGGERATED_FRIENDLY


# ── Canonical Knowledge ─────────────────────────────────────────────────


class TestCanonicalKnowledge:
    """Gate 5D.3 — canonical KIO knowledge package."""

    def test_full_form_present(self):
        assert "Kernel for Intelligent Orchestration" in _CANONICAL_KNOWLEDGE["full_form"]

    def test_identity_present(self):
        assert "Joel" in _CANONICAL_KNOWLEDGE["identity"]

    def test_autonomy_statement_present(self):
        assert "autonomously" in _CANONICAL_KNOWLEDGE["autonomy"].lower()

    def test_local_first_present(self):
        assert "local" in _CANONICAL_KNOWLEDGE["local_first"].lower()


# ── Coherence Normalization ─────────────────────────────────────────────


class TestCoherenceNormalization:
    """Gate 5D.3 — coherence normalization."""

    def setup_method(self):
        self.gov = ConversationGovernor()
        self.ctx = type("MockCtx", (), {"recent_topic": lambda self: "Python"})()

    def test_shallow_dead_end_with_question(self):
        result = self.gov.normalize_coherence("okay", "what is Python?", self.ctx)
        assert "Python" in result
        assert len(result) > 15

    def test_shallow_dead_end_no_topic(self):
        ctx_empty = type("MockCtx", (), {"recent_topic": lambda self: None})()
        result = self.gov.normalize_coherence("okay", "what is this?", ctx_empty)
        assert result != "okay"

    def test_valid_response_preserved(self):
        result = self.gov.normalize_coherence(
            "Python is a programming language.", "what is Python?", self.ctx
        )
        assert result == "Python is a programming language."

    def test_okay_without_question_preserved(self):
        result = self.gov.normalize_coherence("okay", "fine", self.ctx)
        assert result == "okay"


class TestGovernancePipelineWithContext:
    """Gate 5D.3 — governance pipeline with context integration."""

    def setup_method(self):
        self.gov = ConversationGovernor()

    def test_protected_query_bypasses_with_context(self):
        ctx = ConversationContext()
        ctx.append_exchange("What is Python?", "")
        result = self.gov.govern("who are you", "random LLM output", ctx)
        assert result is not None
        assert "KIO" in result
        assert "random" not in result

    def test_quality_rejected_with_context(self):
        ctx = ConversationContext()
        result = self.gov.govern("hi", "lmao", ctx)
        assert result is None

    def test_valid_with_context_passes(self):
        ctx = ConversationContext()
        result = self.gov.govern("hi", "Hello! How can I help?", ctx)
        assert result == "Hello! How can I help?"


# ── Responder Integration ───────────────────────────────────────────────


class TestResponderContextAwareFallback:
    """Gate 5D.3 — responder fallback coherence."""

    def setup_method(self):
        self.responder = ConversationResponder()

    def test_degraded_block_includes_topic(self):
        self.responder._context.append_exchange("What is Python?", "Python is a language.")
        resp = self.responder.generate(
            "can you run my code",
            _mock_orchestration(OrchestrationState.DEGRADED),
            _mock_handoff_result(ExecutionClassification.DEGRADED_BLOCK),
        )
        assert "Python" in resp or "degraded" in resp

    def test_degraded_block_no_topic(self):
        resp = self.responder.generate(
            "can you run my code",
            _mock_orchestration(OrchestrationState.DEGRADED),
            _mock_handoff_result(ExecutionClassification.DEGRADED_BLOCK),
        )
        assert "offline" in resp or "exhausted" in resp

    def test_governance_rejected_tracks_diagnostic(self):
        initial = self.responder.get_context_diagnostics().get("fallback_coherence_used", 0)
        self.responder.generate(
            "what is the secret",
            _mock_orchestration(),
            _mock_handoff_result(ExecutionClassification.CONVERSATIONAL_ONLY, "what is the secret"),
        )


class TestResponderDiagnostics:
    """Gate 5D.3 — responder diagnostic counters."""

    def setup_method(self):
        self.responder = ConversationResponder()

    def test_get_context_diagnostics_returns_dict(self):
        diag = self.responder.get_context_diagnostics()
        assert isinstance(diag, dict)
        assert "context_reference_resolved" in diag
        assert "conversational_context_pruned" in diag
        assert "fallback_coherence_used" in diag
        assert "coherence_normalized" in diag

    def test_protected_query_appends_exchange(self):
        r = self.responder.generate(
            "who are you",
            _mock_orchestration(response_text="who are you"),
            _mock_handoff_result(ExecutionClassification.CONVERSATIONAL_ONLY, "who are you"),
        )
        assert "KIO" in r
        diag = self.responder.get_context_diagnostics()
        assert self.responder._context.exchange_count() >= 1


# ── Repeated Conversation Chains ───────────────────────────────────────


class TestRepeatedConversationChains:
    """Gate 5D.3 — topic continuity across multiple exchanges."""

    def setup_method(self):
        self.ctx = ConversationContext()

    def test_topic_continuity_after_multiple(self):
        self.ctx.append_exchange("What is Python?", "Python is a language.")
        self.ctx.append_exchange("Is it compiled?", "Yes, Python compiles to bytecode.")
        self.ctx.append_exchange("What about Java?", "Java is also compiled.")
        topic = self.ctx.recent_topic()
        assert topic is not None
        assert topic.lower() == "java"

    def test_reference_across_multiple_exchanges(self):
        self.ctx.append_exchange("What is Rust?", "Rust is a systems language.")
        self.ctx.append_exchange("Is it fast?", "Yes, it's fast.")
        self.ctx.append_exchange("Tell me more about it", "Rust has zero-cost abstractions.")
        assert self.ctx.recent_topic() == "Rust"

    def test_repeated_greetings_dont_create_topic(self):
        for i in range(15):
            self.ctx.append_exchange("hello", "hi")
        assert self.ctx.recent_topic() is None
        assert self.ctx.exchange_count() <= 10
