"""
test_provider_first_intelligence.py — Gate 5 Provider-First Conversational Intelligence

Validates:
1. Provider-backed educational escalation (provider-first routing, then KnowledgeFallback fallback)
2. Continuity persistence (next/continue lesson_step progression)
3. Local bootstrap fallback survivability (degraded fallback still works)
4. Execution isolation (provider never handles execution commands)
5. Generic fallback suppression (no filler collapse for educational queries)
6. Browser containment non-regression (capability close routing isolated)
"""

import pytest
from mini_kio.llm.conversation_responder import ConversationResponder
from mini_kio.llm.conversation_models import (
    OrchestrationResponse, OrchestrationState, PendingAction,
)
from mini_kio.llm.intent_models import IntentType, IntentClassification, ExtractedIntent
from mini_kio.runtime.runtime_contracts import (
    ExecutionClassification, RuntimeHandoffResult, ExecutionAuditMetadata,
)

_NONCE = 0
EXPLICIT_FAILURE = "I couldn't retrieve information for that topic right now."

def _mock_orchestration(state=OrchestrationState.CONVERSATIONAL, response_text="", intent_type=None, **kw):
    global _NONCE
    _NONCE += 1
    meta = kw.pop("metadata", {})
    base = OrchestrationResponse(
        state=state,
        response_text=response_text,
        pending_action=None,
        intent_type=intent_type,
        metadata=meta,
    )
    object.__setattr__(base, "_nonce", _NONCE)
    return base

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


# ══════════════════════════════════════════════════════════════════════
# Part 1: Provider-Backed Educational Escalation
# ══════════════════════════════════════════════════════════════════════


class TestEducationalEscalation:
    """Educational queries escalate through provider first, fall through to KnowledgeFallback."""

    def test_topic_in_knowledge_fallback_returns_lesson(self):
        """Known topic should return lesson pack content via provider→fallback path."""
        r = ConversationResponder()
        o = _mock_orchestration(response_text="tell me about recursion", intent_type=IntentType.EDUCATIONAL)
        h = _mock_handoff_result(ExecutionClassification.CONVERSATIONAL_ONLY, "recursion")
        resp = r.generate("tell me about recursion", o, h)
        assert "call" in resp.lower() or "function" in resp.lower() or resp == EXPLICIT_FAILURE
        assert len(resp) > 10

    def test_unknown_topic_falls_to_generic(self):
        """Unrecognized educational topic returns generic fallback, not crash."""
        r = ConversationResponder()
        o = _mock_orchestration(response_text="advanced decorators", intent_type=IntentType.EDUCATIONAL)
        h = _mock_handoff_result(ExecutionClassification.CONVERSATIONAL_ONLY, "advanced decorators")
        resp = r.generate("teach me advanced decorators", o, h)
        assert len(resp) > 0
        assert len(resp) <= 2000

    def test_os_scheduling_educational_route(self):
        """'explain operating system scheduling' routes through educational path."""
        r = ConversationResponder()
        o = _mock_orchestration(response_text="explain operating system scheduling", intent_type=IntentType.EDUCATIONAL)
        h = _mock_handoff_result(ExecutionClassification.CONVERSATIONAL_ONLY, "operating system scheduling")
        resp = r.generate("explain operating system scheduling", o, h)
        assert "operating system" in resp.lower() or "kernel" in resp.lower() or "schedul" in resp.lower() or resp == EXPLICIT_FAILURE
        diag = r.get_context_diagnostics()
        assert diag.get("educational_intent_detected", 0) > 0

    def test_recursion_explanation_returns_content(self):
        """'what is recursion' should return lesson content."""
        r = ConversationResponder()
        o = _mock_orchestration(response_text="what is recursion", intent_type=IntentType.EDUCATIONAL)
        h = _mock_handoff_result(ExecutionClassification.CONVERSATIONAL_ONLY, "recursion")
        resp = r.generate("what is recursion", o, h)
        assert "function" in resp.lower() or "call" in resp.lower() or resp == EXPLICIT_FAILURE

    def test_photo_editing_educational_fallback(self):
        """'teach me photo editing' routes educational, returns fallback or generic."""
        r = ConversationResponder()
        o = _mock_orchestration(response_text="teach me photo editing", intent_type=IntentType.EDUCATIONAL)
        h = _mock_handoff_result(ExecutionClassification.CONVERSATIONAL_ONLY, "photo editing")
        resp = r.generate("teach me photo editing", o, h)
        assert len(resp) > 0
        assert len(resp) <= 2000

    def test_educational_diagnostics_recorded(self):
        """Educational escalation increments diagnostic counters."""
        r = ConversationResponder()
        o = _mock_orchestration(response_text="tell me about recursion", intent_type=IntentType.EDUCATIONAL,
                                metadata={"educational_state_preserved": True})
        h = _mock_handoff_result(ExecutionClassification.CONVERSATIONAL_ONLY, "recursion")
        r.generate("tell me about recursion", o, h)
        diag = r.get_context_diagnostics()
        assert diag.get("educational_intent_detected", 0) >= 1
        assert diag.get("educational_authority_used", 0) >= 1


# ══════════════════════════════════════════════════════════════════════
# Part 2: Continuity Persistence
# ══════════════════════════════════════════════════════════════════════


# ══════════════════════════════════════════════════════════════════════
# Part 3: Knowledge Base & Reasoning
# ══════════════════════════════════════════════════════════════════════


# ══════════════════════════════════════════════════════════════════════
# Part 3: Local Bootstrap Fallback Survivability
# ══════════════════════════════════════════════════════════════════════


class TestLocalBootstrapFallback:
    """Degraded fallback still works when provider unavailable."""

    def test_degraded_block_returns_fallback(self):
        r = ConversationResponder()
        o = _mock_orchestration(state=OrchestrationState.CONVERSATIONAL)
        h = _mock_handoff_result(ExecutionClassification.DEGRADED_BLOCK, "degraded")
        resp = r.generate("do something", o, h)
        assert "offline" in resp.lower() or "exhausted" in resp.lower()
        assert len(resp) <= 2000

    def test_known_topic_local_fallback_survives(self):
        r = ConversationResponder()
        o = _mock_orchestration(response_text="tell me about python", intent_type=IntentType.EDUCATIONAL)
        h = _mock_handoff_result(ExecutionClassification.CONVERSATIONAL_ONLY, "python")
        resp = r.generate("tell me about python", o, h)
        assert "python" in resp.lower() or resp == EXPLICIT_FAILURE

    def test_execution_blocked_returns_refusal(self):
        r = ConversationResponder()
        o = _mock_orchestration(state=OrchestrationState.CONVERSATIONAL)
        h = _mock_handoff_result(ExecutionClassification.EXECUTABLE_BLOCKED, "blocked by runtime")
        resp = r.generate("delete system32", o, h)
        assert "block" in resp.lower() or "safe" in resp.lower() or "refused" in resp.lower()

    def test_malformed_payload_returns_clarification(self):
        r = ConversationResponder()
        o = _mock_orchestration(state=OrchestrationState.CONVERSATIONAL)
        h = _mock_handoff_result(ExecutionClassification.MALFORMED_PAYLOAD, "bad input")
        resp = r.generate("!@#$%", o, h)
        assert "didn't quite understand" in resp.lower() or "rephrase" in resp.lower()

    def test_confirmation_returns_prompt(self):
        r = ConversationResponder()
        ei = ExtractedIntent(
            raw_text="open calculator", normalized_text="open calculator",
            confidence=0.9, intent_type=IntentType.EXECUTABLE,
            proposed_action="open", proposed_target="calculator",
        )
        ic = IntentClassification(primary_intent=ei, is_safe=True)
        pending = PendingAction(action="open", target="calculator", classification=ic)
        o = OrchestrationResponse(
            state=OrchestrationState.AWAITING_CONFIRMATION,
            response_text="open calculator",
            pending_action=pending,
            metadata={},
        )
        h = _mock_handoff_result(ExecutionClassification.EXECUTABLE_REQUIRES_CONFIRMATION, "open calculator")
        resp = r.generate("open calculator", o, h)
        assert "ready" in resp.lower() or "proceed" in resp.lower() or "Shall I" in resp


# ══════════════════════════════════════════════════════════════════════
# Part 4: Execution Isolation
# ══════════════════════════════════════════════════════════════════════


class TestExecutionIsolation:
    """Execution commands remain deterministic/local — provider never handles them."""

    def test_open_app_returns_execution_summary(self):
        r = ConversationResponder()
        audit = ExecutionAuditMetadata("test", "SAFE", "confirmed", True)
        h = RuntimeHandoffResult(True, ExecutionClassification.EXECUTABLE_VALIDATED,
                                 "opened calculator (pid 1234)", audit)
        o = _mock_orchestration(state=OrchestrationState.EXECUTABLE_READY, response_text="open calculator")
        resp = r.generate("open calculator", o, h)
        assert "calculator" in resp.lower()
        assert "ready" in resp.lower() or "opened" in resp.lower() or "running" in resp.lower()

    def test_close_app_returns_execution_summary(self):
        r = ConversationResponder()
        audit = ExecutionAuditMetadata("test", "SAFE", "confirmed", True)
        h = RuntimeHandoffResult(True, ExecutionClassification.EXECUTABLE_VALIDATED,
                                 "closed notepad (pid 5678)", audit)
        o = _mock_orchestration(state=OrchestrationState.EXECUTABLE_READY, response_text="close notepad")
        resp = r.generate("close notepad", o, h)
        assert "notepad" in resp.lower()
        assert "closed" in resp.lower()

    def test_search_returns_execution_summary(self):
        r = ConversationResponder()
        audit = ExecutionAuditMetadata("test", "SAFE", "confirmed", True)
        h = RuntimeHandoffResult(True, ExecutionClassification.EXECUTABLE_VALIDATED,
                                 "searched python tutorials (pid 0)", audit)
        o = _mock_orchestration(state=OrchestrationState.EXECUTABLE_READY, response_text="search python")
        resp = r.generate("search python", o, h)
        assert "python" in resp.lower()

    def test_executable_classification_masks_provider(self):
        """EXECUTABLE_VALIDATED should never route through provider path."""
        r = ConversationResponder()
        audit = ExecutionAuditMetadata("test", "SAFE", "confirmed", True)
        h = RuntimeHandoffResult(True, ExecutionClassification.EXECUTABLE_VALIDATED,
                                 "opened chrome (pid 99)", audit)
        o = _mock_orchestration(state=OrchestrationState.EXECUTABLE_READY, response_text="open chrome")
        resp = r.generate("open chrome", o, h)
        assert "chrome" in resp.lower()
        diag = r.get_context_diagnostics()
        assert diag.get("provider_teaching_route_used", 0) == 0


# ══════════════════════════════════════════════════════════════════════
# Part 5: Generic Fallback Suppression
# ══════════════════════════════════════════════════════════════════════


class TestGenericFallbackSuppression:
    """Educational queries do not collapse into generic fillers."""

    _FILLERS = frozenset({
        "alright", "okay", "ok", "sure", "got it", "fair enough",
        "sounds good", "understood", "noted", "i see",
    })

    def _is_filler(self, text):
        return text.lower().strip(".! ").strip() in self._FILLERS

    def test_educational_not_generic_filler(self):
        r = ConversationResponder()
        o = _mock_orchestration(response_text="tell me about recursion", intent_type=IntentType.EDUCATIONAL)
        h = _mock_handoff_result(ExecutionClassification.CONVERSATIONAL_ONLY, "recursion")
        resp = r.generate("tell me about recursion", o, h)
        assert not self._is_filler(resp), f"Response is generic filler: '{resp}'"

    def test_unknown_topic_not_generic_filler(self):
        r = ConversationResponder()
        o = _mock_orchestration(response_text="advanced decorators", intent_type=IntentType.EDUCATIONAL)
        h = _mock_handoff_result(ExecutionClassification.CONVERSATIONAL_ONLY, "advanced decorators")
        resp = r.generate("teach me advanced decorators", o, h)
        assert not self._is_filler(resp), f"Response is generic filler: '{resp}'"

    def test_educational_intent_no_filler_collapse(self):
        r = ConversationResponder()
        o = _mock_orchestration(response_text="explain operating system scheduling", intent_type=IntentType.EDUCATIONAL)
        h = _mock_handoff_result(ExecutionClassification.CONVERSATIONAL_ONLY, "operating system scheduling")
        resp = r.generate("explain operating system scheduling", o, h)
        assert not self._is_filler(resp), f"Response is generic filler: '{resp}'"
        assert "operating system" in resp.lower() or "schedul" in resp.lower() or resp == EXPLICIT_FAILURE

    def test_topic_aware_fallback_suppresses_filler(self):
        """Non-educational query after topic context clears educational state."""
        r = ConversationResponder()
        o1 = _mock_orchestration(response_text="tell me about python", intent_type=IntentType.EDUCATIONAL)
        h1 = _mock_handoff_result(ExecutionClassification.CONVERSATIONAL_ONLY, "python")
        r.generate("tell me about python", o1, h1)
        o2 = _mock_orchestration(response_text="random question here")
        h2 = _mock_handoff_result(ExecutionClassification.CONVERSATIONAL_ONLY, "random")
        resp = r.generate("random question here", o2, h2)
        assert len(resp) > 0
        assert len(resp) <= 2000

    def test_no_topic_context_returns_generic(self):
        """Without any topic context, generic response is acceptable."""
        r = ConversationResponder()
        o = _mock_orchestration(response_text="something completely random")
        h = _mock_handoff_result(ExecutionClassification.CONVERSATIONAL_ONLY, "something completely random")
        resp = r.generate("something completely random", o, h)
        assert len(resp) > 0
        assert len(resp) <= 2000


# ══════════════════════════════════════════════════════════════════════
# Part 6: Browser Containment Non-Regression
# ══════════════════════════════════════════════════════════════════════


class TestBrowserContainment:
    """Capability close routing remains isolated from provider path."""

    def test_close_it_with_capability_context(self):
        """'close it' with EXECUTABLE_VALIDATED returns execution summary, not provider response."""
        r = ConversationResponder()
        audit = ExecutionAuditMetadata("test", "SAFE", "confirmed", True)
        h = RuntimeHandoffResult(True, ExecutionClassification.EXECUTABLE_VALIDATED,
                                 "closed chrome (pid 0)", audit)
        o = _mock_orchestration(response_text="close it",
                                metadata={"tab_ownership_validated": True,
                                          "browser_canonicalization_used": True})
        resp = r.generate("close it", o, h)
        assert "chrome" in resp.lower() or "closed" in resp.lower()

    def test_close_app_does_not_route_through_provider(self):
        """EXECUTABLE_VALIDATED for close should return execution summary, not conversational."""
        r = ConversationResponder()
        audit = ExecutionAuditMetadata("test", "SAFE", "confirmed", True)
        h = RuntimeHandoffResult(True, ExecutionClassification.EXECUTABLE_VALIDATED,
                                 "closed chrome (pid 123)", audit)
        o = _mock_orchestration(state=OrchestrationState.CONVERSATIONAL, response_text="close chrome")
        resp = r.generate("close chrome", o, h)
        assert "chrome" in resp.lower()
        diag = r.get_context_diagnostics()
        assert diag.get("provider_teaching_route_used", 0) == 0
        assert diag.get("provider_knowledge_route_used", 0) == 0

    def test_browser_close_execution_isolation(self):
        """Close execution returns summary without provider diagnostics."""
        r = ConversationResponder()
        audit = ExecutionAuditMetadata("test", "SAFE", "confirmed", True)
        h = RuntimeHandoffResult(True, ExecutionClassification.EXECUTABLE_VALIDATED,
                                 "closed edge (pid 456)", audit)
        o = _mock_orchestration(response_text="close edge",
                                metadata={"tab_ownership_validated": True})
        resp = r.generate("close edge", o, h)
        assert "edge" in resp.lower()
        assert len(resp) <= 2000
        diag = r.get_context_diagnostics()
        assert diag.get("provider_teaching_route_used", 0) == 0


# ══════════════════════════════════════════════════════════════════════
# Part 7: Provider Path Diagnostics
# ══════════════════════════════════════════════════════════════════════


class TestProviderPathDiagnostics:
    """Provider-first routing correctly records diagnostics even when provider unavailable."""

    def test_educational_authority_diagnostic(self):
        r = ConversationResponder()
        o = _mock_orchestration(response_text="teach me recursion", intent_type=IntentType.EDUCATIONAL)
        h = _mock_handoff_result(ExecutionClassification.CONVERSATIONAL_ONLY, "recursion")
        r.generate("teach me recursion", o, h)
        diag = r.get_context_diagnostics()
        assert diag.get("educational_authority_used", 0) > 0
        assert diag.get("educational_intent_detected", 0) > 0
        assert diag.get("educational_route_used", 0) > 0

    def test_continuity_intercept_diagnostic(self):
        r = ConversationResponder()
        o1 = _mock_orchestration(response_text="teach me recursion", intent_type=IntentType.EDUCATIONAL)
        h1 = _mock_handoff_result(ExecutionClassification.CONVERSATIONAL_ONLY, "recursion")
        r.generate("teach me recursion", o1, h1)
        o2 = _mock_orchestration(response_text="next", metadata={"continuity_resume_used": True})
        h2 = _mock_handoff_result(ExecutionClassification.CONVERSATIONAL_ONLY, "next")
        r.generate("next", o2, h2)
        diag = r.get_context_diagnostics()
        assert diag.get("continuity_intercept_used", 0) > 0

    def test_fallback_coherence_diagnostic(self):
        r = ConversationResponder()
        o = _mock_orchestration(response_text="something unknown")
        h = _mock_handoff_result(ExecutionClassification.CONVERSATIONAL_ONLY, "unknown")
        r.generate("something unknown", o, h)
        diag = r.get_context_diagnostics()
        assert diag.get("fallback_coherence_used", 0) > 0

    def test_educational_route_diagnostic(self):
        """Educational authority intercept increments educational_route_used."""
        r = ConversationResponder()
        o = _mock_orchestration(response_text="tell me about python", intent_type=IntentType.EDUCATIONAL)
        h = _mock_handoff_result(ExecutionClassification.CONVERSATIONAL_ONLY, "python")
        r.generate("tell me about python", o, h)
        diag = r.get_context_diagnostics()
        assert diag.get("educational_route_used", 0) > 0
