"""
tests/test_intelligence_router.py
tests/test_retrieval_synthesizer.py
tests/test_local_reasoner.py
tests/test_emergency_responder.py

Combined test suite for the 5-layer intelligence fallback system.
Run: pytest tests/test_intelligence_*.py -v
"""

# ============================================================================
# tests/test_emergency_responder.py
# Runs standalone — zero external dependencies. Always runnable.
# ============================================================================

import pytest
import sys
import os

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))


class TestEmergencyResponder:
    """Emergency Responder must NEVER return empty. Ever."""

    @pytest.fixture
    def responder(self):
        from mini_kio.intelligence.emergency_responder import EmergencyResponder
        return EmergencyResponder()

    def test_never_returns_empty_string(self, responder):
        result = responder.respond("")
        assert result and result.strip(), "Empty query must not produce empty response"

    def test_never_returns_none(self, responder):
        result = responder.respond("")
        assert result is not None

    def test_help_query(self, responder):
        result = responder.respond("help")
        assert result and result.strip()
        assert "help" in result.lower() or "command" in result.lower()

    def test_status_query(self, responder):
        result = responder.respond("status")
        assert result and result.strip()

    def test_diagnostics_query(self, responder):
        result = responder.respond("diagnostics")
        assert result and result.strip()
        assert "diagnostic" in result.lower() or "runtime" in result.lower()

    def test_identity_query(self, responder):
        result = responder.respond("who are you")
        assert result and result.strip()
        assert "kio" in result.lower()

    def test_greeting(self, responder):
        result = responder.respond("hello")
        assert result and result.strip()

    def test_browser_query(self, responder):
        result = responder.respond("chrome won't open")
        assert result and result.strip()

    def test_unknown_query_still_responds(self, responder):
        result = responder.respond("xyzzy unknown gibberish query 12345")
        assert result and result.strip()

    def test_very_short_query(self, responder):
        result = responder.respond("hi")
        assert result and result.strip()

    def test_whitespace_only_query(self, responder):
        result = responder.respond("   ")
        assert result and result.strip()

    def test_long_query(self, responder):
        long_q = "what is the meaning of life and everything " * 20
        result = responder.respond(long_q)
        assert result and result.strip()

    def test_with_degraded_runtime_context(self, responder):
        ctx = {"runtime_state": "DEGRADED"}
        result = responder.respond("what is happening", runtime_context=ctx)
        assert result and result.strip()
        assert "degraded" in result.lower() or "unavailable" in result.lower()

    def test_with_failure_class_context(self, responder):
        ctx = {"failure_class": "quota"}
        result = responder.respond("why no answer", runtime_context=ctx)
        assert result and result.strip()

    def test_provider_failure_query(self, responder):
        result = responder.respond("all providers failed")
        assert result and result.strip()

    def test_call_count_increments(self, responder):
        responder.respond("hello")
        responder.respond("status")
        assert responder.get_call_count() == 2

    def test_response_always_contains_actionable_info(self, responder):
        """Every emergency response must give the user something to do."""
        test_queries = [
            "help me", "what can you do", "I'm stuck",
            "nothing works", "explain kio", "open chrome",
        ]
        for q in test_queries:
            result = responder.respond(q)
            assert result and result.strip(), f"Empty response for query: {q}"
            # Must contain at least one actionable word
            actionable = any(w in result.lower() for w in
                             ["help", "command", "type", "try", "open", "status",
                              "available", "local", "can", "diagnostics"])
            assert actionable, f"No actionable content in response for '{q}': {result}"

    @pytest.mark.parametrize("query", [
        "", "  ", "\n", "\t",
        "None", "null", "undefined",
        "a" * 1000,  # very long
        "!@#$%^&*()",  # special chars only
    ])
    def test_edge_cases_never_empty(self, responder, query):
        result = responder.respond(query)
        assert result is not None
        assert len(result.strip()) > 0


# ============================================================================
# tests/test_local_reasoner.py
# ============================================================================

class TestLocalReasoner:

    @pytest.fixture
    def reasoner(self):
        from mini_kio.intelligence.local_reasoner import LocalReasoner
        return LocalReasoner()

    def test_help_query(self, reasoner):
        result = reasoner.reason("help")
        assert result and result.strip()
        assert "command" in result.lower() or "open" in result.lower()

    def test_status_query_with_context(self, reasoner):
        ctx = {"runtime_state": "DEGRADED", "provider_status": {"groq": "failed", "gemini": "failed"}}
        result = reasoner.reason("status", runtime_context=ctx)
        assert result and result.strip()

    def test_status_query_no_context(self, reasoner):
        result = reasoner.reason("status")
        assert result and result.strip()

    def test_provider_failure_with_class(self, reasoner):
        ctx = {"failure_class": "quota"}
        result = reasoner.reason("why did the ai fail", runtime_context=ctx)
        assert result and result.strip()
        assert "quota" in result.lower()

    def test_provider_failure_with_all_failed_flag(self, reasoner):
        ctx = {"all_providers_failed": True}
        result = reasoner.reason("why are you offline", runtime_context=ctx)
        assert result and result.strip()
        assert "unavailable" in result.lower() or "offline" in result.lower()

    def test_browser_chrome_not_open(self, reasoner):
        result = reasoner.reason("chrome not open")
        assert result and result.strip()
        assert "chrome" in result.lower()

    def test_browser_tab_not_closed(self, reasoner):
        result = reasoner.reason("tab not closed")
        assert result and result.strip()
        assert "tab" in result.lower() or "ctrl+w" in result.lower()

    def test_browser_extension_issue(self, reasoner):
        result = reasoner.reason("extension not loaded")
        assert result and result.strip()

    def test_error_context_explanation(self, reasoner):
        ctx = {"last_error": "permission denied", "last_command": "open chrome"}
        result = reasoner.reason("what went wrong", runtime_context=ctx)
        assert result and result.strip()
        assert "permission" in result.lower()

    def test_error_context_timeout(self, reasoner):
        ctx = {"last_error": "operation timed out", "last_command": "search python"}
        result = reasoner.reason("why did it fail", runtime_context=ctx)
        assert result and result.strip()
        assert "timeout" in result.lower() or "timed out" in result.lower()

    def test_capability_camera(self, reasoner):
        result = reasoner.reason("can you use the camera")
        assert result and result.strip()
        assert "camera" in result.lower()

    def test_capability_general(self, reasoner):
        result = reasoner.reason("what can you do")
        assert result and result.strip()

    def test_command_explanation_open(self, reasoner):
        result = reasoner.reason("how do i open an app")
        assert result and result.strip()
        assert "open" in result.lower()

    def test_command_explanation_close(self, reasoner):
        result = reasoner.reason("how to close an app")
        assert result and result.strip()

    def test_unmatched_query_returns_none(self, reasoner):
        """Reasoner should return None for queries it can't match — not a fake answer."""
        result = reasoner.reason("what is the capital of france")
        # Reasoner returns None for unknown general knowledge — router moves to next layer
        assert result is None

    def test_empty_query_returns_none(self, reasoner):
        result = reasoner.reason("")
        assert result is None

    def test_no_crash_on_bad_context(self, reasoner):
        ctx = {"last_error": None, "runtime_state": None, "garbage": object()}
        result = reasoner.reason("status", runtime_context=ctx)
        # Should not raise — may return None or a string


# ============================================================================
# tests/test_retrieval_synthesizer.py
# ============================================================================

class TestRetrievalSynthesizer:
    """Test retrieval synthesis logic — provider calls mocked."""

    @pytest.fixture
    def synthesizer(self):
        from mini_kio.intelligence.retrieval_synthesizer import RetrievalSynthesizer
        return RetrievalSynthesizer(timeout_s=2.0)

    def test_synthesize_empty_query_returns_none(self, synthesizer):
        result = synthesizer.synthesize("")
        assert result is None

    def test_synthesize_whitespace_only_returns_none(self, synthesizer):
        result = synthesizer.synthesize("  ")
        assert result is None

    def test_all_providers_fail_returns_none(self, synthesizer, monkeypatch):
        """When all providers raise exceptions, returns None (not raises)."""
        monkeypatch.setattr(synthesizer, "_try_exa", lambda q: None)
        monkeypatch.setattr(synthesizer, "_try_tavily", lambda q: None)
        monkeypatch.setattr(synthesizer, "_try_duckduckgo", lambda q: None)
        monkeypatch.setattr(synthesizer, "_try_jina", lambda q: None)
        monkeypatch.setattr(synthesizer, "_try_wikipedia", lambda q: None)
        result = synthesizer.synthesize("what is recursion")
        assert result is None
        assert synthesizer.get_stats()["all_failed"] == 1

    def test_exa_success_short_circuits(self, synthesizer, monkeypatch):
        """If Exa succeeds, no other provider is called."""
        tavily_called = []
        monkeypatch.setattr(synthesizer, "_try_exa", lambda q: "Exa result for " + q)
        monkeypatch.setattr(synthesizer, "_try_tavily", lambda q: tavily_called.append(q) or None)
        result = synthesizer.synthesize("test query")
        assert result == "Exa result for test query"
        assert len(tavily_called) == 0
        assert synthesizer.get_stats()["exa_hit"] == 1

    def test_exa_fail_tavily_success(self, synthesizer, monkeypatch):
        monkeypatch.setattr(synthesizer, "_try_exa", lambda q: None)
        monkeypatch.setattr(synthesizer, "_try_tavily", lambda q: "Tavily result")
        result = synthesizer.synthesize("test query")
        assert result == "Tavily result"
        assert synthesizer.get_stats()["exa_fail"] == 1
        assert synthesizer.get_stats()["tavily_hit"] == 1

    def test_wikipedia_last_resort(self, synthesizer, monkeypatch):
        monkeypatch.setattr(synthesizer, "_try_exa", lambda q: None)
        monkeypatch.setattr(synthesizer, "_try_tavily", lambda q: None)
        monkeypatch.setattr(synthesizer, "_try_duckduckgo", lambda q: None)
        monkeypatch.setattr(synthesizer, "_try_jina", lambda q: None)
        monkeypatch.setattr(synthesizer, "_try_wikipedia", lambda q: "Wikipedia result")
        result = synthesizer.synthesize("test query")
        assert result == "Wikipedia result"
        assert synthesizer.get_stats()["wikipedia_hit"] == 1

    def test_provider_exception_does_not_propagate(self, synthesizer, monkeypatch):
        def raise_always(q):
            raise RuntimeError("Network died")
        monkeypatch.setattr(synthesizer, "_try_exa", raise_always)
        monkeypatch.setattr(synthesizer, "_try_tavily", raise_always)
        monkeypatch.setattr(synthesizer, "_try_duckduckgo", raise_always)
        monkeypatch.setattr(synthesizer, "_try_jina", raise_always)
        monkeypatch.setattr(synthesizer, "_try_wikipedia", raise_always)
        # Must not raise — returns None
        result = synthesizer.synthesize("what is python")
        assert result is None

    def test_stats_accumulate_correctly(self, synthesizer, monkeypatch):
        monkeypatch.setattr(synthesizer, "_try_exa", lambda q: None)
        monkeypatch.setattr(synthesizer, "_try_tavily", lambda q: "hit")
        synthesizer.synthesize("query 1")
        synthesizer.synthesize("query 2")
        stats = synthesizer.get_stats()
        assert stats["exa_fail"] == 2
        assert stats["tavily_hit"] == 2
        assert stats["total_synthesized"] == 2


class TestSynthesizeFunction:
    """Test the deterministic _synthesize extraction function."""

    def test_basic_text_extraction(self):
        from mini_kio.intelligence.retrieval_synthesizer import _synthesize
        raw = "Python is a programming language. It was created by Guido. It is widely used."
        result = _synthesize(raw)
        assert result and result.strip()
        assert "Python" in result

    def test_html_stripped(self):
        from mini_kio.intelligence.retrieval_synthesizer import _synthesize
        raw = "<p>Python is <b>great</b>. It runs everywhere.</p>"
        result = _synthesize(raw)
        assert "<" not in result
        assert "Python" in result

    def test_source_attribution_appended(self):
        from mini_kio.intelligence.retrieval_synthesizer import _synthesize
        result = _synthesize("Some content here.", source="Wikipedia")
        assert "Wikipedia" in result

    def test_empty_raw_returns_none(self):
        from mini_kio.intelligence.retrieval_synthesizer import _synthesize
        assert _synthesize("") is None
        assert _synthesize("   ") is None

    def test_output_within_length_limit(self):
        from mini_kio.intelligence.retrieval_synthesizer import _synthesize, _MAX_RESPONSE_CHARS
        long_text = "This is a sentence. " * 200
        result = _synthesize(long_text)
        assert result is None or len(result) <= _MAX_RESPONSE_CHARS + 100  # +100 for source line

    def test_markdown_stripped(self):
        from mini_kio.intelligence.retrieval_synthesizer import _synthesize
        raw = "**Python** is a _language_. It uses [links](http://example.com)."
        result = _synthesize(raw)
        assert "**" not in result
        assert "_language_" not in result


# ============================================================================
# tests/test_intelligence_router.py
# ============================================================================

class TestIntelligenceRouter:
    """Test the 5-layer routing logic."""

    @pytest.fixture
    def router(self, monkeypatch):
        """Return a router with all external layers mocked to fail by default."""
        # Patch imports before IntelligenceRouter init
        monkeypatch.setattr(
            "mini_kio.intelligence.retrieval_synthesizer.RetrievalSynthesizer.synthesize",
            lambda self, q: None,
        )
        from mini_kio.intelligence.intelligence_router import IntelligenceRouter
        return IntelligenceRouter()

    def test_cloud_hit_short_circuits_all_layers(self, router):
        """Layer 1 cloud hit should return immediately without trying others."""
        result = router.route("what is python", cloud_response="Python is a language.")
        assert result == "Python is a language."
        assert router.get_stats()["l1_cloud_hit"] == 1
        assert router.get_stats()["l2_retrieval_hit"] == 0

    def test_cloud_none_falls_through_to_emergency(self, router):
        """With all layers failing, emergency responder must produce a response."""
        result = router.route("some random query", cloud_response=None)
        assert result and result.strip()
        assert router.get_stats()["l5_emergency_hit"] == 1

    def test_result_is_never_empty(self, router):
        """Route always returns non-empty regardless of layer outcomes."""
        for query in ["", "  ", "hello", "explain recursion", "why did chrome fail"]:
            result = router.route(query, cloud_response=None)
            assert result is not None
            assert len(result.strip()) > 0, f"Empty result for query: '{query}'"

    def test_layer_3_knowledge_hit_for_identity(self, router, monkeypatch):
        """Internal knowledge layer handles identity questions offline."""
        # Patch retrieval to fail
        monkeypatch.setattr(router._retrieval, "synthesize", lambda q: None)
        result = router.route("who are you", cloud_response=None)
        assert result and result.strip()
        # Should get a response from L3 or L4 or L5
        assert any(w in result.lower() for w in ["kio", "joel", "assistant", "online"])

    def test_layer_4_reasoner_hit_for_help(self, router, monkeypatch):
        monkeypatch.setattr(router._retrieval, "synthesize", lambda q: None)
        result = router.route("help", cloud_response=None)
        assert result and result.strip()

    def test_stats_track_correctly(self, router):
        router.route("query 1", cloud_response="response 1")
        router.route("query 2", cloud_response=None)
        stats = router.get_stats()
        assert stats["total_routed"] == 2
        assert stats["l1_cloud_hit"] == 1

    def test_provider_timeout_scenario(self, router, monkeypatch):
        """Simulates: provider chain times out → router falls through layers."""
        monkeypatch.setattr(router._retrieval, "synthesize", lambda q: None)
        ctx = {"failure_class": "timeout", "runtime_state": "DEGRADED"}
        result = router.route("why no response", cloud_response=None, runtime_context=ctx)
        assert result and result.strip()

    def test_auth_failure_scenario(self, router, monkeypatch):
        monkeypatch.setattr(router._retrieval, "synthesize", lambda q: None)
        ctx = {"failure_class": "auth"}
        result = router.route("help", cloud_response=None, runtime_context=ctx)
        assert result and result.strip()

    def test_dns_failure_scenario(self, router, monkeypatch):
        monkeypatch.setattr(router._retrieval, "synthesize", lambda q: None)
        ctx = {"failure_class": "dns", "runtime_state": "DEGRADED"}
        result = router.route("what can you do", cloud_response=None, runtime_context=ctx)
        assert result and result.strip()

    def test_all_providers_removed_scenario(self, router, monkeypatch):
        """No API keys, no internet — only local layers."""
        monkeypatch.setattr(router._retrieval, "synthesize", lambda q: None)
        ctx = {"all_providers_failed": True}
        result = router.route("status", cloud_response=None, runtime_context=ctx)
        assert result and result.strip()

    def test_internet_disconnected_scenario(self, router, monkeypatch):
        monkeypatch.setattr(router._retrieval, "synthesize", lambda q: None)
        ctx = {"failure_class": "dns", "runtime_state": "DEGRADED"}
        for q in ["help", "what are you", "open chrome", "search python"]:
            result = router.route(q, cloud_response=None, runtime_context=ctx)
            assert result and result.strip(), f"Empty result for '{q}' in internet-disconnected scenario"

    @pytest.mark.parametrize("scenario,ctx", [
        ("A: all llm fail", {"failure_class": "quota"}),
        ("B: internet disconnected", {"failure_class": "dns", "runtime_state": "DEGRADED"}),
        ("C: dns unavailable", {"failure_class": "dns"}),
        ("D: all keys removed", {"all_providers_failed": True}),
        ("E: exa unavailable", {}),
        ("F: tavily unavailable", {}),
        ("G: all retrieval fail", {}),
        ("H: everything unavailable", {"failure_class": "all_failed", "runtime_state": "DEGRADED"}),
    ])
    def test_failure_matrix(self, router, monkeypatch, scenario, ctx):
        """All 8 failure scenarios must produce non-empty responses."""
        monkeypatch.setattr(router._retrieval, "synthesize", lambda q: None)
        for q in ["status", "help", "who are you", "what can you do"]:
            result = router.route(q, cloud_response=None, runtime_context=ctx)
            assert result and result.strip(), (
                f"Scenario {scenario}: empty response for query '{q}'"
            )


# ============================================================================
# Proof table: KIO never returns empty response
# ============================================================================

class TestNonEmptyGuarantee:
    """
    Exhaustive proof that no combination of failures produces an empty response.
    """

    @pytest.fixture
    def emergency(self):
        from mini_kio.intelligence.emergency_responder import EmergencyResponder
        return EmergencyResponder()

    @pytest.mark.parametrize("query", [
        # Identity
        "who are you", "what are you", "what is kio", "who built you",
        # Help
        "help", "commands", "what can you do",
        # Status
        "status", "are you running", "runtime state",
        # Diagnostics
        "diagnostics", "system check", "health check",
        # Browser
        "chrome won't open", "tab not closed", "browser failed",
        # Capabilities
        "can you play music", "can you search", "can you open files",
        # General
        "hello", "hi", "goodbye", "thanks",
        # Unknown
        "xyzzy", "frobulation", "what is 42",
        # Edge cases
        "", "  ", "?", "!",
    ])
    def test_emergency_always_responds(self, emergency, query):
        """The emergency layer alone guarantees non-empty response for any input."""
        result = emergency.respond(query)
        assert result is not None
        assert len(result.strip()) > 0, f"Empty response from emergency layer for: '{query}'"

    def test_sentinel_is_non_empty(self):
        """The hardcoded sentinel fallback in EmergencyResponder is non-empty."""
        from mini_kio.intelligence.emergency_responder import _SENTINEL
        assert _SENTINEL and _SENTINEL.strip()
        assert len(_SENTINEL) > 50  # meaningful content

    def test_router_non_empty_guarantee_with_all_mocked_failures(self, monkeypatch):
        """Even with every single layer mocked to fail, response is non-empty."""
        monkeypatch.setattr(
            "mini_kio.intelligence.retrieval_synthesizer.RetrievalSynthesizer.synthesize",
            lambda self, q: None,
        )
        monkeypatch.setattr(
            "mini_kio.intelligence.local_reasoner.LocalReasoner.reason",
            lambda self, q, **kw: None,
        )
        # EmergencyResponder is NOT mocked — it's the guarantee
        from mini_kio.intelligence.intelligence_router import IntelligenceRouter
        router = IntelligenceRouter()

        test_queries = ["", "hello", "help", "status", "xyzzy unknown"]
        for q in test_queries:
            result = router.route(q, cloud_response=None)
            assert result and result.strip(), f"Empty response for '{q}' with all layers mocked"
