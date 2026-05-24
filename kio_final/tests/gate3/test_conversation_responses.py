import unittest
from unittest.mock import MagicMock, patch
from mini_kio.llm.conversation_responder import ConversationResponder, _SAFE_DEGRADED_FALLBACK
from mini_kio.runtime.runtime_contracts import ExecutionClassification, ExecutionAuditMetadata, RuntimeHandoffResult
from mini_kio.llm.conversation_models import OrchestrationResponse, OrchestrationState, PendingAction
from mini_kio.llm.intent_models import IntentType, ExtractedIntent, IntentClassification


def _mock_orchestration(
    state: OrchestrationState,
    intent_type: IntentType = IntentType.CONVERSATIONAL,
    action: str = "open",
    target: str = "notepad",
    response_text: str = "",
):
    primary = ExtractedIntent(
        raw_text=response_text,
        normalized_text=response_text.lower(),
        confidence=1.0,
        intent_type=intent_type,
        proposed_action=action,
        proposed_target=target,
    )
    classification = IntentClassification(primary_intent=primary, is_safe=True)
    pending = None
    if intent_type == IntentType.EXECUTABLE:
        pending = PendingAction(
            action=action, target=target, classification=classification,
            requires_confirmation=(state == OrchestrationState.AWAITING_CONFIRMATION),
            reason="Low intent confidence" if state == OrchestrationState.AWAITING_CONFIRMATION else None,
        )
    return OrchestrationResponse(
        state=state,
        response_text=response_text,
        intent_type=intent_type,
        pending_action=pending,
    )


def _mock_handoff_result(
    classification: ExecutionClassification,
    message: str = "",
    success: bool = True,
):
    audit = ExecutionAuditMetadata(
        intent_origin="test",
        validation_state="SAFE",
        confirmation_state="test",
        dispatch_eligibility=False,
    )
    return RuntimeHandoffResult(
        success=success,
        classification=classification,
        message=message,
        audit_metadata=audit,
    )


class TestConversationResponder(unittest.TestCase):
    def setUp(self):
        self.responder = ConversationResponder()

    # ── Informational prompts ──────────────────────────────────────────

    def test_informational_what_is_kio(self):
        """'what is kio' returns meaningful answer, not echo."""
        orch = _mock_orchestration(OrchestrationState.CONVERSATIONAL, response_text="what is kio")
        result = _mock_handoff_result(ExecutionClassification.CONVERSATIONAL_ONLY, "what is kio")
        response = self.responder.generate("what is kio", orch, result)
        self.assertNotEqual(response, "what is kio")
        self.assertIn("KIO", response)
        self.assertIn("assistant", response.lower())

    def test_informational_runtime_authority(self):
        """'how does runtime authority work' returns meaningful explanation."""
        text = "how does runtime authority work"
        orch = _mock_orchestration(OrchestrationState.CONVERSATIONAL, response_text=text)
        result = _mock_handoff_result(ExecutionClassification.CONVERSATIONAL_ONLY, text)
        response = self.responder.generate(text, orch, result)
        self.assertNotEqual(response, text)
        self.assertIn("runtime", response.lower())
        self.assertIn("veto", response.lower())

    def test_informational_safety_features(self):
        """'what are your safety features' returns safety explanation."""
        text = "what are your safety features"
        orch = _mock_orchestration(OrchestrationState.CONVERSATIONAL, response_text=text)
        result = _mock_handoff_result(ExecutionClassification.CONVERSATIONAL_ONLY, text)
        response = self.responder.generate(text, orch, result)
        self.assertIn("safety", response.lower())
        self.assertIn("runtime veto", response.lower())

    def test_informational_confirmation_explanation(self):
        """'how does confirmation work' returns confirmation explanation."""
        text = "how does confirmation work"
        orch = _mock_orchestration(OrchestrationState.CONVERSATIONAL, response_text=text)
        result = _mock_handoff_result(ExecutionClassification.CONVERSATIONAL_ONLY, text)
        response = self.responder.generate(text, orch, result)
        self.assertIn("confirmation", response.lower())

    def test_informational_who_created_you(self):
        """'who created you' returns creator answer."""
        text = "who created you"
        orch = _mock_orchestration(OrchestrationState.CONVERSATIONAL, response_text=text)
        result = _mock_handoff_result(ExecutionClassification.CONVERSATIONAL_ONLY, text)
        response = self.responder.generate(text, orch, result)
        self.assertIn("Joel", response)

    # ── Greeting prompts ───────────────────────────────────────────────

    def test_greeting_hello(self):
        """'hello' returns greeting, not echo."""
        orch = _mock_orchestration(OrchestrationState.CONVERSATIONAL, response_text="hello")
        result = _mock_handoff_result(ExecutionClassification.CONVERSATIONAL_ONLY, "hello")
        response = self.responder.generate("hello", orch, result)
        self.assertNotEqual(response, "hello")
        self.assertIn("Hello", response)

    def test_greeting_how_are_you(self):
        """'how are you' returns status response."""
        orch = _mock_orchestration(OrchestrationState.CONVERSATIONAL, response_text="how are you")
        result = _mock_handoff_result(ExecutionClassification.CONVERSATIONAL_ONLY, "how are you")
        response = self.responder.generate("how are you", orch, result)
        self.assertNotEqual(response, "how are you")
        self.assertIn("functioning", response.lower())

    def test_greeting_thanks(self):
        """'thanks' returns acknowledgment."""
        orch = _mock_orchestration(OrchestrationState.CONVERSATIONAL, response_text="thanks")
        result = _mock_handoff_result(ExecutionClassification.CONVERSATIONAL_ONLY, "thanks")
        response = self.responder.generate("thanks", orch, result)
        self.assertIn("welcome", response.lower())

    # ── Confirmation prompts ───────────────────────────────────────────

    def test_confirmation_prompt_includes_action(self):
        """Confirmation prompt must include action and target."""
        orch = _mock_orchestration(
            OrchestrationState.AWAITING_CONFIRMATION, IntentType.EXECUTABLE,
            action="open", target="chrome",
        )
        result = _mock_handoff_result(ExecutionClassification.EXECUTABLE_REQUIRES_CONFIRMATION,
                                      "Action requires user confirmation")
        response = self.responder.generate("open chrome", orch, result)
        self.assertIn("open", response.lower())
        self.assertIn("chrome", response.lower())
        self.assertIn("proceed", response.lower())

    def test_confirmation_prompt_with_reason(self):
        """Confirmation prompt must include reason when available."""
        orch = _mock_orchestration(
            OrchestrationState.AWAITING_CONFIRMATION, IntentType.EXECUTABLE,
            action="close", target="notepad",
        )
        result = _mock_handoff_result(ExecutionClassification.EXECUTABLE_REQUIRES_CONFIRMATION)
        response = self.responder.generate("close notepad", orch, result)
        self.assertIn("proceed", response.lower())

    # ── Refusal prompts ────────────────────────────────────────────────

    def test_refusal_unsafe_action(self):
        """Refusal for unsafe action returns clear message."""
        orch = _mock_orchestration(OrchestrationState.REFUSED, response_text="I cannot perform that action for safety reasons.")
        result = _mock_handoff_result(ExecutionClassification.EXECUTABLE_BLOCKED, orch.response_text, success=False)
        response = self.responder.generate("delete system32", orch, result)
        self.assertIn("safety", response.lower())

    def test_refusal_runtime_veto_sanitized(self):
        """Runtime Veto message must not leak runtime internals."""
        orch = _mock_orchestration(OrchestrationState.EXECUTABLE_READY, IntentType.EXECUTABLE)
        result = _mock_handoff_result(ExecutionClassification.EXECUTABLE_BLOCKED,
                                      "Runtime Veto: System in EMERGENCY mode", success=False)
        response = self.responder.generate("open notepad", orch, result)
        self.assertNotIn("EMERGENCY", response)
        self.assertIn("blocked", response.lower())

    # ── Degraded fallback ──────────────────────────────────────────────

    def test_degraded_fallback(self):
        """Degraded state must return safe fallback message."""
        orch = _mock_orchestration(OrchestrationState.DEGRADED)
        result = _mock_handoff_result(ExecutionClassification.DEGRADED_BLOCK,
                                      "Provider in degraded state", success=False)
        response = self.responder.generate("open notepad", orch, result)
        self.assertEqual(response, _SAFE_DEGRADED_FALLBACK)

    # ── Orchestration summaries ────────────────────────────────────────

    def test_execution_summary_preserved(self):
        """Execution result message from handoff must be preserved."""
        orch = _mock_orchestration(OrchestrationState.EXECUTABLE_READY, IntentType.EXECUTABLE)
        result = _mock_handoff_result(ExecutionClassification.EXECUTABLE_VALIDATED,
                                      "Opened notepad", success=True)
        response = self.responder.generate("open notepad", orch, result)
        self.assertEqual(response, "Opened notepad")

    def test_execution_summary_truncated(self):
        """Execution summary must be bounded."""
        long_msg = "x" * 2000
        orch = _mock_orchestration(OrchestrationState.EXECUTABLE_READY, IntentType.EXECUTABLE)
        result = _mock_handoff_result(ExecutionClassification.EXECUTABLE_VALIDATED,
                                      long_msg, success=True)
        response = self.responder.generate("open notepad", orch, result)
        self.assertLessEqual(len(response), 600)

    # ── Restricted-topic handling ──────────────────────────────────────

    def test_unknown_topic_generic_response(self):
        """Unknown conversational prompts get generic response, not error."""
        orch = _mock_orchestration(OrchestrationState.CONVERSATIONAL, response_text="tell me about quantum physics")
        result = _mock_handoff_result(ExecutionClassification.CONVERSATIONAL_ONLY, "tell me about quantum physics")
        response = self.responder.generate("tell me about quantum physics", orch, result)
        self.assertNotIn("I don't understand", response)

    # ── Clarification prompts ──────────────────────────────────────────

    def test_malformed_payload_clarification(self):
        """Malformed payload must return clarification prompt."""
        orch = _mock_orchestration(OrchestrationState.CONVERSATIONAL)
        result = _mock_handoff_result(ExecutionClassification.MALFORMED_PAYLOAD, "Missing pending action", success=False)
        response = self.responder.generate("???", orch, result)
        self.assertIn("rephrase", response.lower())

    # ── No execution leakage ───────────────────────────────────────────

    def test_no_execution_leakage_in_conversational(self):
        """Conversational responses must never contain action/target leakage."""
        orch = _mock_orchestration(OrchestrationState.CONVERSATIONAL, response_text="hello")
        result = _mock_handoff_result(ExecutionClassification.CONVERSATIONAL_ONLY, "hello")
        response = self.responder.generate("hello", orch, result)
        # Should not contain raw orchestration metadata
        self.assertNotIn("pending_action", response)
        self.assertNotIn("raw_text", response)

    def test_response_length_bounded(self):
        """All responses must be under max length."""
        orch = _mock_orchestration(OrchestrationState.CONVERSATIONAL,
                                   response_text="hello " * 500)
        result = _mock_handoff_result(ExecutionClassification.CONVERSATIONAL_ONLY,
                                      "hello " * 500)
        response = self.responder.generate("hello", orch, result)
        self.assertLessEqual(len(response), 600)


class TestResponderIntegration(unittest.TestCase):
    """Integration test — responder used inside _route_via_orchestration."""

    @patch('mini_kio.core.runtime._CURRENT_RUNTIME')
    @patch('mini_kio.core.runtime.emit_runtime_trace')
    def test_responder_called_in_orchestration_flow(self, mock_trace, mock_runtime):
        """_route_via_orchestration must call the responder."""
        from mini_kio.core.runtime import _route_via_orchestration

        mock_runtime.state = "running"
        mock_runtime.shutdown_requested = False
        mock_runtime.prune_tracked_processes = MagicMock()
        mock_runtime._gate3_pipeline = None
        if hasattr(mock_runtime, '_gate3_pipeline'):
            del mock_runtime._gate3_pipeline

        result = _route_via_orchestration("hello")

        self.assertIn("_orchestrated", result)
        self.assertIn("message", result)
        # Should NOT be echoing the input text
        self.assertNotEqual(result.get("message"), "hello")


if __name__ == "__main__":
    unittest.main()
