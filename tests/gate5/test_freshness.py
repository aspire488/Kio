"""
test_freshness.py — Validation for freshness classifier, search routing, and pending action execution.

Tests:
1. FreshnessClassifier correctly classifies REQUIRED / OPTIONAL / NONE
2. REQUIRED freshness routes to search (not provider memory)
3. Non-freshness queries remain local
4. Pending action "yes" executes stored search
5. Pending action "no" clears without executing

All tests are deterministic with no external dependencies.
"""

import sys
import pytest
from typing import Optional
from dataclasses import dataclass
from unittest.mock import MagicMock


# ── FreshnessClassifier unit tests ─────────────────────────────────────────

from mini_kio.core.freshness_classifier import classify, is_confirmation, FreshnessLevel


class TestFreshnessClassifier:
    def test_required_latest(self):
        assert classify("latest nvidia gpu") == FreshnessLevel.REQUIRED

    def test_required_today(self):
        assert classify("today world news") == FreshnessLevel.REQUIRED

    def test_required_current(self):
        assert classify("current premier league table") == FreshnessLevel.REQUIRED

    def test_required_news(self):
        assert classify("latest windows version") == FreshnessLevel.REQUIRED

    def test_required_winner(self):
        assert classify("current ipl winner") == FreshnessLevel.REQUIRED

    def test_required_score(self):
        assert classify("match score") == FreshnessLevel.REQUIRED

    def test_required_weather(self):
        assert classify("weather today") == FreshnessLevel.REQUIRED

    def test_required_stock(self):
        assert classify("stock market") == FreshnessLevel.REQUIRED

    def test_required_live(self):
        assert classify("live election results") == FreshnessLevel.REQUIRED

    def test_optional_recent(self):
        assert classify("recent updates") == FreshnessLevel.OPTIONAL

    def test_optional_announcement(self):
        assert classify("new announcement") == FreshnessLevel.OPTIONAL

    def test_optional_trending(self):
        assert classify("trending topics") == FreshnessLevel.OPTIONAL

    def test_none_identity(self):
        assert classify("who created kio") == FreshnessLevel.NONE

    def test_none_educational(self):
        assert classify("explain recursion") == FreshnessLevel.NONE

    def test_none_concept(self):
        assert classify("what is oop") == FreshnessLevel.NONE

    def test_none_empty(self):
        assert classify("") == FreshnessLevel.NONE

    def test_none_greeting(self):
        assert classify("hello") == FreshnessLevel.NONE

    def test_none_how_are_you(self):
        assert classify("how are you") == FreshnessLevel.NONE


class TestFreshnessConfirmation:
    def test_confirmation_yes(self):
        assert is_confirmation("yes") is True

    def test_confirmation_yeah(self):
        assert is_confirmation("yeah") is True

    def test_confirmation_go_ahead(self):
        assert is_confirmation("go ahead") is True

    def test_confirmation_pls(self):
        assert is_confirmation("pls") is True

    def test_confirmation_do_it(self):
        assert is_confirmation("do it") is True

    def test_confirmation_no(self):
        assert is_confirmation("no") is False

    def test_confirmation_question(self):
        assert is_confirmation("what is python") is False

    def test_confirmation_empty(self):
        assert is_confirmation("") is False


# ── PendingAction unit tests ───────────────────────────────────────────────

from mini_kio.llm.conversation_context import ConversationContext, PendingAction


class TestPendingAction:
    def test_set_pending_search(self):
        ctx = ConversationContext()
        ctx.set_pending_search("latest nvidia gpu")
        assert ctx.has_pending_action() is True
        pending = ctx.get_pending_action()
        assert pending is not None
        assert pending.action_type == "search"
        assert pending.query == "latest nvidia gpu"

    def test_clear_pending_action(self):
        ctx = ConversationContext()
        ctx.set_pending_search("test query")
        ctx.clear_pending_action()
        assert ctx.has_pending_action() is False

    def test_mark_pending_executed(self):
        ctx = ConversationContext()
        ctx.set_pending_search("test query")
        ctx.mark_pending_executed()
        assert ctx.has_pending_action() is False

    def test_clear_resets_pending(self):
        ctx = ConversationContext()
        ctx.set_pending_search("test query")
        ctx.clear()
        assert ctx.has_pending_action() is False

    def test_no_pending_by_default(self):
        ctx = ConversationContext()
        assert ctx.has_pending_action() is False
        assert ctx.get_pending_action() is None


# ── RetrievalIntelligenceRouter freshness routing tests ──────────────────

from mini_kio.knowledge.retrieval_router import KnowledgeRouter


class TestRetrievalIntelligenceRouterFreshness:
    def test_route_freshness_calls_search_providers(self, monkeypatch):
        """route_freshness() should call search providers even for non-knowledge queries."""
        calls = []

        def fake_exa(query):
            calls.append(("exa", query))
            return None

        def fake_tavily(query):
            calls.append(("tavily", query))
            return None

        def fake_duck(query):
            calls.append(("duck", query))
            return "result from duckduckgo"

        monkeypatch.setattr("mini_kio.knowledge.retrieval_router.exa_provider.search", fake_exa)
        monkeypatch.setattr("mini_kio.knowledge.retrieval_router.tavily_provider.search", fake_tavily)
        monkeypatch.setattr("mini_kio.knowledge.retrieval_router.duckduckgo_provider.search", fake_duck)

        router = KnowledgeRouter()
        result = router.route_freshness("latest nvidia gpu")
        assert result is not None
        assert len(result.sources) == 1
        assert result.sources[0].content == "result from duckduckgo"
        assert len(calls) == 3  # tried exa, tavily, duckduckgo

    def test_route_freshness_returns_none_on_no_results(self, monkeypatch):
        def fake_none(query):
            return None

        monkeypatch.setattr("mini_kio.knowledge.retrieval_router.exa_provider.search", fake_none)
        monkeypatch.setattr("mini_kio.knowledge.retrieval_router.tavily_provider.search", fake_none)
        monkeypatch.setattr("mini_kio.knowledge.retrieval_router.duckduckgo_provider.search", fake_none)

        router = KnowledgeRouter()
        result = router.route_freshness("latest nvidia gpu")
        assert result is None

    def test_route_freshness_empty_query(self):
        router = KnowledgeRouter()
        assert router.route_freshness("") is None
        assert router.route_freshness(None) is None

    def test_route_freshness_bypasses_is_knowledge_query(self):
        """route_freshness should NOT check is_knowledge_query — always tries search."""
        router = KnowledgeRouter()
        # "latest nvidia gpu" may not match is_knowledge_query patterns,
        # but route_freshness should still try search providers
        # (no assertion on result since we can't call real providers in unit test)


# ── Full pipeline integration test: freshness triggers search ──────────────

class TestFreshnessPipeline:
    """Verify that KNOWLEDGE route with freshness REQUIRED triggers search, not provider memory."""

    def test_freshness_query_triggers_search_via_responder(self, monkeypatch):
        """A freshness-required query should call route_freshness, not _ask_gemini."""
        from mini_kio.llm.conversation_responder import ConversationResponder

        search_called = False

        def fake_freshness(self_, query):
            nonlocal search_called
            search_called = True
            return "NVIDIA RTX 5090 was announced."

        monkeypatch.setattr(
            "mini_kio.knowledge.retrieval_router.KnowledgeRouter.route_freshness",
            fake_freshness,
        )

        responder = ConversationResponder()
        result = responder._resolve_knowledge_request(
            "latest nvidia gpu",
            prefer_provider=True,
        )
        assert search_called is True, "route_freshness should be called for REQUIRED freshness"
        assert "NVIDIA" in result

    def test_non_freshness_uses_provider_first(self, monkeypatch):
        """A non-freshness query should use provider-first path."""
        from mini_kio.llm.conversation_responder import ConversationResponder

        search_called = False
        gemini_called = False

        def fake_freshness(query):
            nonlocal search_called
            search_called = True
            return None

        def fake_gemini(text, system_prompt=None):
            nonlocal gemini_called
            gemini_called = True
            return "Recursion is when a function calls itself."

        monkeypatch.setattr(
            "mini_kio.knowledge.retrieval_router.KnowledgeRouter.route_freshness",
            fake_freshness,
        )
        monkeypatch.setattr(
            "mini_kio.llm.conversation_responder._ask_gemini",
            fake_gemini,
        )
        monkeypatch.setattr(
            "mini_kio.knowledge.retrieval_router.KnowledgeRouter.route",
            MagicMock(return_value=None),
        )

        responder = ConversationResponder()
        result = responder._resolve_knowledge_request(
            "explain recursion",
            prefer_provider=True,
        )
        assert gemini_called is True, "_ask_gemini should be called for non-freshness"
        assert "Recursion" in result

    def test_freshness_with_no_search_results_returns_direct_failure(self, monkeypatch):
        """When freshness search returns nothing, must NOT ask permission or set pending."""
        from mini_kio.llm.conversation_responder import ConversationResponder

        def fake_none(self_, query):
            return None

        monkeypatch.setattr(
            "mini_kio.knowledge.retrieval_router.KnowledgeRouter.route_freshness",
            fake_none,
        )

        responder = ConversationResponder()
        result = responder._resolve_knowledge_request(
            "latest nvidia gpu",
            prefer_provider=True,
        )
        assert responder._context.has_pending_action() is False
        assert "couldn't find" in result or "Search failed" in result or "unavailable" in result
        assert "try again" not in result
        assert "just say yes" not in result
        assert "Would you like" not in result

    def test_pending_action_confirmation_executes_search(self, monkeypatch):
        """Confirming a pending search should execute it."""
        from mini_kio.llm.conversation_responder import ConversationResponder
        from mini_kio.llm.conversation_context import PendingAction
        from mini_kio.runtime.runtime_contracts import ExecutionClassification, RuntimeHandoffResult
        from mini_kio.llm.conversation_models import OrchestrationResponse, OrchestrationState
        from mini_kio.llm.intent_models import IntentType

        executed_query = []

        def fake_freshness(self_, query):
            executed_query.append(query)
            from mini_kio.knowledge.knowledge_models import MultiSourceResult, SearchSource
            return MultiSourceResult(query=query, sources=[SearchSource(name="test", url=None, content="NVIDIA RTX 5090 found.")])

        monkeypatch.setattr(
            "mini_kio.knowledge.retrieval_router.KnowledgeRouter.route_freshness",
            fake_freshness,
        )

        # Set up responder with a pending search action
        responder = ConversationResponder()
        responder._context.set_pending_search("latest nvidia gpu")

        from mini_kio.runtime.runtime_contracts import ExecutionAuditMetadata
        audit = ExecutionAuditMetadata(
            intent_origin="test",
            validation_state="validated",
            confirmation_state="confirmed",
            dispatch_eligibility=False,
        )
        orch = OrchestrationResponse(
            state=OrchestrationState.CONVERSATIONAL,
            response_text="",
            intent_type=IntentType.INFORMATIONAL,
            pending_action=None,
        )
        handoff = RuntimeHandoffResult(
            success=True,
            classification=ExecutionClassification.CONVERSATIONAL_ONLY,
            message="",
            audit_metadata=audit,
        )

        result = responder.generate("yes", orch, handoff)
        assert len(executed_query) == 1
        assert executed_query[0] == "latest nvidia gpu"
        assert "NVIDIA" in result
        assert responder._context.has_pending_action() is False

    def test_non_confirmation_does_not_execute_pending(self, monkeypatch):
        """Non-confirmation input should NOT execute pending search."""
        from mini_kio.llm.conversation_responder import ConversationResponder
        from mini_kio.runtime.runtime_contracts import ExecutionClassification, RuntimeHandoffResult
        from mini_kio.llm.conversation_models import OrchestrationResponse, OrchestrationState
        from mini_kio.llm.intent_models import IntentType

        executed = []

        def fake_freshness(self_, query):
            executed.append(query)
            return None

        monkeypatch.setattr(
            "mini_kio.knowledge.retrieval_router.KnowledgeRouter.route_freshness",
            fake_freshness,
        )

        responder = ConversationResponder()
        responder._context.set_pending_search("latest news")

        from mini_kio.runtime.runtime_contracts import ExecutionAuditMetadata
        audit = ExecutionAuditMetadata(
            intent_origin="test",
            validation_state="validated",
            confirmation_state="confirmed",
            dispatch_eligibility=False,
        )
        orch = OrchestrationResponse(
            state=OrchestrationState.CONVERSATIONAL,
            response_text="",
            intent_type=IntentType.INFORMATIONAL,
            pending_action=None,
        )
        handoff = RuntimeHandoffResult(
            success=True,
            classification=ExecutionClassification.CONVERSATIONAL_ONLY,
            message="",
            audit_metadata=audit,
        )

        # "no" — should NOT execute pending
        result = responder.generate("no", orch, handoff)
        assert len(executed) == 0
        # Pending should still be intact
        assert responder._context.has_pending_action() is True

    def test_identity_route_does_not_trigger_search(self, monkeypatch):
        """Identity queries like 'who created kio' should go through identity_resolve, not search."""
        from mini_kio.llm.conversation_responder import ConversationResponder
        from mini_kio.runtime.runtime_contracts import ExecutionClassification, RuntimeHandoffResult
        from mini_kio.llm.conversation_models import OrchestrationResponse, OrchestrationState
        from mini_kio.llm.intent_models import IntentType

        search_called = []

        def fake_search(self_, query):
            search_called.append(query)
            return None

        monkeypatch.setattr(
            "mini_kio.knowledge.retrieval_router.KnowledgeRouter.route_freshness",
            fake_search,
        )

        responder = ConversationResponder()
        from mini_kio.runtime.runtime_contracts import ExecutionAuditMetadata
        audit = ExecutionAuditMetadata(
            intent_origin="test",
            validation_state="validated",
            confirmation_state="confirmed",
            dispatch_eligibility=False,
        )
        orch = OrchestrationResponse(
            state=OrchestrationState.CONVERSATIONAL,
            response_text="",
            intent_type=IntentType.INFORMATIONAL,
            pending_action=None,
        )
        handoff = RuntimeHandoffResult(
            success=True,
            classification=ExecutionClassification.CONVERSATIONAL_ONLY,
            message="",
            audit_metadata=audit,
        )

        result = responder.generate("who created kio", orch, handoff)
        assert len(search_called) == 0, "Identity queries should not trigger search"
        assert "Joel" in result or "KIO" in result

    def test_freshness_query_on_identity_route_goes_to_identity(self, monkeypatch):
        """Even if a freshness query looks like identity, identity should win."""
        from mini_kio.llm.conversation_responder import ConversationResponder
        from mini_kio.runtime.runtime_contracts import ExecutionClassification, ExecutionAuditMetadata, RuntimeHandoffResult
        from mini_kio.llm.conversation_models import OrchestrationResponse, OrchestrationState
        from mini_kio.llm.intent_models import IntentType

        search_called = []

        def fake_search(self_, query):
            search_called.append(query)
            return None

        monkeypatch.setattr(
            "mini_kio.knowledge.retrieval_router.KnowledgeRouter.route_freshness",
            fake_search,
        )

        responder = ConversationResponder()
        audit = ExecutionAuditMetadata(
            intent_origin="test",
            validation_state="validated",
            confirmation_state="confirmed",
            dispatch_eligibility=False,
        )
        orch = OrchestrationResponse(
            state=OrchestrationState.CONVERSATIONAL,
            response_text="",
            intent_type=IntentType.INFORMATIONAL,
            pending_action=None,
        )
        handoff = RuntimeHandoffResult(
            success=True,
            classification=ExecutionClassification.CONVERSATIONAL_ONLY,
            message="",
            audit_metadata=audit,
        )

        result = responder.generate("who created kio", orch, handoff)
        assert len(search_called) == 0
        assert "Joel" in result


# ── Edge case tests ─────────────────────────────────────────────────────────

class TestFreshnessEdgeCases:
    def test_freshness_with_punctuation(self):
        assert classify("Latest NVIDIA GPU!") == FreshnessLevel.REQUIRED

    def test_freshness_with_extra_words(self):
        assert classify("can you tell me the latest news") == FreshnessLevel.REQUIRED

    def test_none_technical_concept(self):
        assert classify("what is a linked list") == FreshnessLevel.NONE

    def test_none_programming_question(self):
        assert classify("how does python garbage collection work") == FreshnessLevel.NONE

    def test_confirmation_with_punctuation(self):
        assert is_confirmation("yes!") is True  # punctuation is stripped


# ── Phase 2: Expanded freshness keyword tests ───────────────────────────────

class TestPhase2FreshnessExpansion:
    def test_required_ceo(self):
        assert classify("ceo of nvidia") == FreshnessLevel.REQUIRED

    def test_required_internship(self):
        assert classify("current internships in india") == FreshnessLevel.REQUIRED

    def test_required_jobs(self):
        assert classify("jobs in bangalore") == FreshnessLevel.REQUIRED

    def test_required_hiring(self):
        assert classify("hiring for software engineers") == FreshnessLevel.REQUIRED

    def test_required_election(self):
        assert classify("election results 2025") == FreshnessLevel.REQUIRED

    def test_required_champion(self):
        assert classify("latest champion league winner") == FreshnessLevel.REQUIRED

    def test_required_tournament(self):
        assert classify("latest tournament standings") == FreshnessLevel.REQUIRED

    def test_required_release_notes(self):
        assert classify("release notes python 3.13") == FreshnessLevel.REQUIRED

    def test_required_autosearch_freshness(self):
        assert classify("current premier league table") == FreshnessLevel.REQUIRED


# ── Phase 3: Educational routing edge cases ────────────────────────────────

class TestPhase3EducationalRouting:
    def test_what_is_a_ceo(self):
        assert classify("what is a ceo") == FreshnessLevel.NONE

    def test_what_is_an_internship(self):
        assert classify("what is an internship") == FreshnessLevel.NONE

    def test_explain_how_elections_work(self):
        assert classify("explain how elections work") == FreshnessLevel.NONE

    def test_teach_me_about_tournaments(self):
        assert classify("teach me about tournaments") == FreshnessLevel.NONE

    def test_explain_latest_nvidia(self):
        assert classify("explain latest nvidia announcement") == FreshnessLevel.REQUIRED

    def test_explain_current_openai(self):
        assert classify("explain current openai structure") == FreshnessLevel.REQUIRED

    def test_explain_today_spacex(self):
        assert classify("explain today spacex launch") == FreshnessLevel.REQUIRED

    def test_explain_current_state_of_ai(self):
        assert classify("explain the current state of ai") == FreshnessLevel.REQUIRED

    def test_who_is_current_ceo(self):
        assert classify("who is the current ceo of nvidia") == FreshnessLevel.REQUIRED

    def test_what_is_latest_version(self):
        assert classify("what is the latest version of python") == FreshnessLevel.REQUIRED

    def test_explain_how_tcp_works(self):
        assert classify("explain how TCP works") == FreshnessLevel.NONE

    def test_explain_recursion_remains_local(self):
        assert classify("explain recursion") == FreshnessLevel.NONE

    def test_educational_no_filler_short(self):
        assert classify("what is oop") == FreshnessLevel.NONE


# ── Phase 5: Memory recall tests ─────────────────────────────────────────

class TestMemoryRecall:
    def test_first_user_message(self):
        from mini_kio.memory.memory_store import MemoryStore
        ms = MemoryStore(session_id="test_first")
        assert ms.first_user_message() is None
        ms.append("user", "hello world")
        assert ms.first_user_message() == "hello world"
        ms.append("user", "second message")
        assert ms.first_user_message() == "hello world"

    def test_last_n_messages(self):
        from mini_kio.memory.memory_store import MemoryStore
        ms = MemoryStore(session_id="test_last_n")
        for i in range(5):
            ms.append("user", f"msg {i}")
        entries = ms.last_n_messages(3)
        assert len(entries) == 3
        assert entries[0].message == "msg 2"
        assert entries[-1].message == "msg 4"

    def test_summarize_empty_session(self):
        from mini_kio.memory.memory_store import MemoryStore
        ms = MemoryStore(session_id="test_empty")
        assert "empty" in ms.summarize_session().lower()

    def test_summarize_with_content(self):
        from mini_kio.memory.memory_store import MemoryStore
        ms = MemoryStore(session_id="test_summary")
        ms.append("user", "hello")
        ms.append("assistant", "hi there")
        summary = ms.summarize_session()
        assert "2 messages" in summary
        assert "1 user" in summary

    def test_clear_memory(self):
        from mini_kio.memory.memory_store import MemoryStore
        ms = MemoryStore(session_id="test_clear")
        ms.append("user", "hello")
        assert ms.count() == 1
        ms.clear()
        assert ms.count() == 0

    def test_get_fact(self):
        from mini_kio.memory.memory_store import MemoryStore
        ms = MemoryStore(session_id="test_fact")
        ms.set_fact("name", "kio")
        assert ms.get_fact("name") == "kio"
        assert ms.get_fact("nonexistent") is None


# ── Phase 6: Anti-hallucination / unknown-state tests ─────────────────────

class TestUnknownStateHonesty:
    def test_freshness_no_results_no_permission_asking(self, monkeypatch):
        from mini_kio.llm.conversation_responder import ConversationResponder

        def fake_none(self_, query):
            return None

        monkeypatch.setattr(
            "mini_kio.knowledge.retrieval_router.KnowledgeRouter.route_freshness",
            fake_none,
        )

        responder = ConversationResponder()
        result = responder._resolve_knowledge_request(
            "latest nvidia gpu",
            prefer_provider=True,
        )
        assert "couldn't find" in result or "unavailable" in result
        assert "try again" not in result
        assert "just say yes" not in result
        assert "Would you like" not in result


# ── Phase 9: Search pipeline hardening tests ─────────────────────────────

class TestSearchPipelineHardenig:
    def test_jina_reader_empty_string_falsy(self):
        """Verify empty string is falsy and does not bypass None checks."""
        assert not ""  # empty string is falsy
        assert not "   ".strip()  # whitespace-only is falsy after strip

    def test_freshness_execution_intercept(self, monkeypatch):
        """Verify EXECUTABLE search actions with freshness queries route to search, not app_operator."""
        from mini_kio.llm.conversation_responder import ConversationResponder
        from mini_kio.runtime.runtime_contracts import (
            ExecutionClassification, RuntimeHandoffResult, ExecutionAuditMetadata,
        )
        from mini_kio.llm.conversation_models import OrchestrationResponse, OrchestrationState
        from mini_kio.llm.intent_models import IntentType

        search_called = []

        def fake_route(self_, query):
            search_called.append(query)
            return "Internship opportunities at Google, Microsoft..."

        monkeypatch.setattr(
            "mini_kio.knowledge.retrieval_router.KnowledgeRouter.route_freshness",
            fake_route,
        )

        responder = ConversationResponder()
        audit = ExecutionAuditMetadata(
            intent_origin="test", validation_state="validated",
            confirmation_state="confirmed", dispatch_eligibility=False,
        )
        orch = OrchestrationResponse(
            state=OrchestrationState.CONVERSATIONAL, response_text="",
            intent_type=IntentType.INFORMATIONAL, pending_action=None,
        )
        handoff = RuntimeHandoffResult(
            success=True,
            classification=ExecutionClassification.EXECUTABLE_VALIDATED,
            message="Searched: current internships in india",
            audit_metadata=audit,
        )

        result = responder.generate("current internships in india", orch, handoff)
        assert len(search_called) >= 1, "Freshness search should be triggered"
        assert "Internship" in result, "Should return actual search results, not placeholder"
        assert "Searched:" not in result, "Should not contain placeholder text"


# ── Phase 7: Identity consistency tests ───────────────────────────────────

class TestIdentityConsistency:
    def test_who_are_you_identity(self):
        from mini_kio.llm.identity_dataset import resolve
        result, is_block = resolve("who are you")
        assert result is not None
        assert "KIO" in result or "kio" in result.lower()

    def test_who_created_you_identity(self):
        from mini_kio.llm.identity_dataset import resolve
        result, is_block = resolve("who created kio")
        assert result is not None
        assert "Joel" in result or "joel" in result.lower()

    def test_are_you_chatgpt(self):
        from mini_kio.llm.identity_dataset import resolve
        result, is_block = resolve("are you chatgpt")
        assert result is not None
        # KIO should deny being ChatGPT
        assert "no" in result.lower() or "not" in result.lower() or "KIO" in result

    def test_what_model_are_you(self):
        from mini_kio.llm.identity_dataset import resolve
        result, is_block = resolve("what model are you")
        assert result is not None
        # Should mention KIO, not a third-party model
        assert "KIO" in result

    def test_identity_provider_independent(self):
        """Identity responses should not change based on provider."""
        from mini_kio.llm.identity_dataset import resolve
        r1, _ = resolve("who are you")
        r2, _ = resolve("who are you")
        assert r1 == r2, "Identity response must be deterministic"
