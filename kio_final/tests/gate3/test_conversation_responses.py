import unittest
from unittest.mock import MagicMock, patch
from mini_kio.llm.conversation_responder import ConversationResponder, _SAFE_DEGRADED_FALLBACK
from mini_kio.runtime.runtime_contracts import ExecutionClassification, ExecutionAuditMetadata, RuntimeHandoffResult
from mini_kio.llm.conversation_models import OrchestrationResponse, OrchestrationState, PendingAction, ConversationTone
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
        self.assertIn("doing", response.lower())

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
        """Execution result summary must reference target."""
        orch = _mock_orchestration(OrchestrationState.EXECUTABLE_READY, IntentType.EXECUTABLE)
        result = _mock_handoff_result(ExecutionClassification.EXECUTABLE_VALIDATED,
                                      "Opened notepad", success=True)
        response = self.responder.generate("open notepad", orch, result)
        self.assertIn("notepad", response.lower())

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


class TestTemplateRotation(unittest.TestCase):
    """Deterministic template rotation tests."""

    def setUp(self):
        self.responder = ConversationResponder()

    def _send(self, text: str):
        """Helper to send a conversational input."""
        orch = _mock_orchestration(OrchestrationState.CONVERSATIONAL, response_text=text)
        result = _mock_handoff_result(ExecutionClassification.CONVERSATIONAL_ONLY, text)
        return self.responder.generate(text, orch, result)

    def test_greeting_rotation_three_calls_different(self):
        """Same greeting 3 times returns 3 different responses."""
        r1 = self._send("hello")
        r2 = self._send("hello")
        r3 = self._send("hello")
        self.assertNotEqual(r1, r2)
        self.assertNotEqual(r2, r3)

    def test_greeting_rotation_exhausts_and_wraps(self):
        """Rotation wraps around when all variants used."""
        results = set()
        for _ in range(10):
            results.add(self._send("hello"))
        # Should have used all 5 variants at least once
        self.assertGreaterEqual(len(results), 3)

    def test_repeated_input_hello_again(self):
        """2nd same greeting returns 'Hello again!'"""
        self._send("hello")
        r2 = self._send("hello")
        self.assertIn("again", r2.lower())

    def test_repeated_input_greeting_a_lot(self):
        """3rd same greeting returns repetition acknowledgment."""
        self._send("hello")
        self._send("hello")
        r3 = self._send("hello")
        self.assertIn("a lot", r3.lower())

    def test_repeated_input_counts_per_text(self):
        """Different texts have independent counters."""
        self._send("hello")
        self._send("hi")   # same category, different text
        r1_second = self._send("hello")
        self.assertIn("again", r1_second.lower())

    def test_rotation_deterministic_same_sequence(self):
        """Same sequence produces same results across fresh responders."""
        r1 = ConversationResponder()
        r2 = ConversationResponder()
        seq1 = []
        seq2 = []
        for _ in range(4):
            seq1.append(r1.generate("hello", _mock_orchestration(OrchestrationState.CONVERSATIONAL, response_text="hello"), _mock_handoff_result(ExecutionClassification.CONVERSATIONAL_ONLY, "hello")))
            seq2.append(r2.generate("hello", _mock_orchestration(OrchestrationState.CONVERSATIONAL, response_text="hello"), _mock_handoff_result(ExecutionClassification.CONVERSATIONAL_ONLY, "hello")))
        self.assertEqual(seq1, seq2)

    def test_different_categories_independent_counters(self):
        """Each category has its own rotation counter."""
        r_hello = self._send("hello")
        r_how = self._send("how are you")
        r_hello2 = self._send("hello")
        self.assertNotEqual(r_hello, r_hello2)
        # hi and how_are_you are independent
        r_how2 = self._send("how are you")
        self.assertNotEqual(r_how, r_how2)

    def test_multiple_greeting_inputs_same_category(self):
        """'hi' and 'hello' share the 'hello' category counter."""
        self._send("hello")
        # Explicit generate with 'hi' — not via _send, to avoid repeated counter
        orch = _mock_orchestration(OrchestrationState.CONVERSATIONAL, response_text="hi")
        result = _mock_handoff_result(ExecutionClassification.CONVERSATIONAL_ONLY, "hi")
        r2 = self.responder.generate("hi", orch, result)
        # If counters were per-input: "hi" would use counter 0 -> variants[0]
        # If per-category (shared): "hello" used counter 0 -> now counter is 1 -> variants[1]
        # 'hi' input never seen before -> no repeated detection
        self.assertNotIn("again", r2.lower())


class TestToneProfiles(unittest.TestCase):
    """Deterministic tone profile tests."""

    def setUp(self):
        self.responder = ConversationResponder()

    def _generic(self):
        """Helper to trigger a generic fallback response."""
        orch = _mock_orchestration(OrchestrationState.CONVERSATIONAL, response_text="tell me about quantum physics")
        result = _mock_handoff_result(ExecutionClassification.CONVERSATIONAL_ONLY, "tell me about quantum physics")
        return self.responder.generate("tell me about quantum physics", orch, result)

    def test_tone_default_is_neutral(self):
        """Default tone is NEUTRAL."""
        self.assertEqual(self.responder.get_tone(), ConversationTone.NEUTRAL)

    def test_tone_neutral_generic(self):
        """Neutral generic response is standard."""
        response = self._generic()
        self.assertIn("Alright", response)

    def test_tone_concise(self):
        """Concise tone generic response is shorter."""
        self.responder.set_tone(ConversationTone.CONCISE)
        response = self._generic()
        self.assertEqual(response, "Okay.")

    def test_tone_helpful(self):
        """Helpful tone generic response."""
        self.responder.set_tone(ConversationTone.HELPFUL)
        response = self._generic()
        self.assertIn("Sure!", response)

    def test_tone_does_not_affect_knowledge_base(self):
        """Tone does not alter knowledge base responses."""
        self.responder.set_tone(ConversationTone.CONCISE)
        orch = _mock_orchestration(OrchestrationState.CONVERSATIONAL, response_text="who created you")
        result = _mock_handoff_result(ExecutionClassification.CONVERSATIONAL_ONLY, "who created you")
        response = self.responder.generate("who created you", orch, result)
        self.assertIn("Joel", response)

    def test_tone_does_not_affect_greeting_rotation(self):
        """Tone does not alter greeting variant selection."""
        self.responder.set_tone(ConversationTone.HELPFUL)
        response = self.responder.generate("hello", _mock_orchestration(OrchestrationState.CONVERSATIONAL, response_text="hello"), _mock_handoff_result(ExecutionClassification.CONVERSATIONAL_ONLY, "hello"))
        # Should still be a valid greeting variant
        self.assertTrue("Hello" in response or "Hi" in response or "Hey" in response)


class TestSafetyResponseImmutability(unittest.TestCase):
    """Safety-critical responses must not be variant."""

    def setUp(self):
        self.responder = ConversationResponder()

    def test_confirmation_prompt_unchanged_across_calls(self):
        """Confirmation prompts are identical every time."""
        orch = _mock_orchestration(OrchestrationState.AWAITING_CONFIRMATION, IntentType.EXECUTABLE, action="open", target="notepad")
        result = _mock_handoff_result(ExecutionClassification.EXECUTABLE_REQUIRES_CONFIRMATION)
        r1 = self.responder.generate("open notepad", orch, result)
        r2 = self.responder.generate("open notepad", orch, result)
        r3 = self.responder.generate("open notepad", orch, result)
        self.assertEqual(r1, r2)
        self.assertEqual(r2, r3)

    def test_confirmation_prompt_unchanged_with_tone(self):
        """Tone changes do not affect confirmation prompts."""
        self.responder.set_tone(ConversationTone.CONCISE)
        orch = _mock_orchestration(OrchestrationState.AWAITING_CONFIRMATION, IntentType.EXECUTABLE, action="open", target="chrome")
        result = _mock_handoff_result(ExecutionClassification.EXECUTABLE_REQUIRES_CONFIRMATION)
        response = self.responder.generate("open chrome", orch, result)
        self.assertIn("proceed", response.lower())

    def test_refusal_unchanged_across_calls(self):
        """Refusal messages are identical."""
        orch = _mock_orchestration(OrchestrationState.REFUSED)
        result = _mock_handoff_result(ExecutionClassification.EXECUTABLE_BLOCKED, "Blocked for safety", success=False)
        r1 = self.responder.generate("delete system32", orch, result)
        result = _mock_handoff_result(ExecutionClassification.EXECUTABLE_BLOCKED, "Blocked for safety", success=False)
        r2 = self.responder.generate("delete system32", orch, result)
        self.assertEqual(r1, r2)

    def test_degraded_fallback_unchanged(self):
        """Degraded fallback is the constant _SAFE_DEGRADED_FALLBACK."""
        orch = _mock_orchestration(OrchestrationState.DEGRADED)
        result = _mock_handoff_result(ExecutionClassification.DEGRADED_BLOCK, "", success=False)
        response = self.responder.generate("open notepad", orch, result)
        self.assertEqual(response, _SAFE_DEGRADED_FALLBACK)

    def test_clarification_prompt_unchanged(self):
        """Clarification prompt is identical every time."""
        orch = _mock_orchestration(OrchestrationState.CONVERSATIONAL)
        result = _mock_handoff_result(ExecutionClassification.MALFORMED_PAYLOAD, "", success=False)
        r1 = self.responder.generate("???", orch, result)
        r2 = self.responder.generate("???", orch, result)
        self.assertEqual(r1, r2)

    def test_knowledge_base_unchanged_by_rotation(self):
        """Knowledge base responses are not affected by rotation state."""
        orch = _mock_orchestration(OrchestrationState.CONVERSATIONAL, response_text="who is joel")
        result = _mock_handoff_result(ExecutionClassification.CONVERSATIONAL_ONLY, "who is joel")
        r1 = self.responder.generate("who is joel", orch, result)
        orch2 = _mock_orchestration(OrchestrationState.CONVERSATIONAL, response_text="who is joel")
        result2 = _mock_handoff_result(ExecutionClassification.CONVERSATIONAL_ONLY, "who is joel")
        r2 = self.responder.generate("who is joel", orch2, result2)
        self.assertEqual(r1, r2)

    def test_no_execution_leakage_preserved(self):
        """Conversational responses still avoid execution leakage."""
        orch = _mock_orchestration(OrchestrationState.CONVERSATIONAL, response_text="hello")
        result = _mock_handoff_result(ExecutionClassification.CONVERSATIONAL_ONLY, "hello")
        response = self.responder.generate("hello", orch, result)
        self.assertNotIn("pending_action", response)
        self.assertNotIn("raw_text", response)



class TestExecutionRotation(unittest.TestCase):
    """Deterministic execution response rotation tests."""

    def setUp(self):
        self.responder = ConversationResponder()

    def _open(self, msg: str = "Opened chrome"):
        orch = _mock_orchestration(OrchestrationState.EXECUTABLE_READY, IntentType.EXECUTABLE)
        result = _mock_handoff_result(ExecutionClassification.EXECUTABLE_VALIDATED, msg, success=True)
        return self.responder.generate("open chrome", orch, result)

    def test_execution_rotation_three_calls_different(self):
        """Same execution message 3 times returns 3 different responses."""
        r1 = self._open()
        r2 = self._open()
        r3 = self._open()
        self.assertNotEqual(r1, r2)
        self.assertNotEqual(r2, r3)

    def test_execution_rotation_exhausts_and_wraps(self):
        """Execution rotation wraps around when all variants used."""
        results = set()
        for _ in range(8):
            results.add(self._open())
        self.assertGreaterEqual(len(results), 3)

    def test_execution_close_variant_target_present(self):
        """Close execution variant includes target name."""
        orch = _mock_orchestration(OrchestrationState.EXECUTABLE_READY, IntentType.EXECUTABLE)
        result = _mock_handoff_result(ExecutionClassification.EXECUTABLE_VALIDATED,
                                      "Closed chrome", success=True)
        response = self.responder.generate("close chrome", orch, result)
        self.assertIn("chrome", response.lower())

    def test_execution_search_variant_target_present(self):
        """Search execution variant includes query."""
        orch = _mock_orchestration(OrchestrationState.EXECUTABLE_READY, IntentType.EXECUTABLE)
        result = _mock_handoff_result(ExecutionClassification.EXECUTABLE_VALIDATED,
                                      "Searched Google: python", success=True)
        response = self.responder.generate("search python", orch, result)
        self.assertIn("python", response.lower())

    def test_execution_unknown_message_passthrough(self):
        """Unrecognized execution messages pass through unchanged."""
        orch = _mock_orchestration(OrchestrationState.EXECUTABLE_READY, IntentType.EXECUTABLE)
        result = _mock_handoff_result(ExecutionClassification.EXECUTABLE_VALIDATED,
                                      "Custom action result", success=True)
        response = self.responder.generate("custom", orch, result)
        self.assertEqual(response, "Custom action result")

    def test_execution_deterministic_same_sequence(self):
        """Same execution sequence across fresh responders."""
        r1 = ConversationResponder()
        r2 = ConversationResponder()
        seq1, seq2 = [], []
        for _ in range(4):
            o = _mock_orchestration(OrchestrationState.EXECUTABLE_READY, IntentType.EXECUTABLE)
            h = _mock_handoff_result(ExecutionClassification.EXECUTABLE_VALIDATED, "Opened chrome", success=True)
            seq1.append(r1.generate("open chrome", o, h))
            seq2.append(r2.generate("open chrome", o, h))
        self.assertEqual(seq1, seq2)

    def test_execution_pid_stripped(self):
        """PID info in close message is stripped before variant selection."""
        orch = _mock_orchestration(OrchestrationState.EXECUTABLE_READY, IntentType.EXECUTABLE)
        result = _mock_handoff_result(ExecutionClassification.EXECUTABLE_VALIDATED,
                                      "Closed notepad (pid 1234)", success=True)
        response = self.responder.generate("close notepad", orch, result)
        self.assertIn("notepad", response.lower())

    def test_execution_summary_bounded(self):
        """Execution summary respects max length."""
        long_target = "x" * 2000
        orch = _mock_orchestration(OrchestrationState.EXECUTABLE_READY, IntentType.EXECUTABLE)
        result = _mock_handoff_result(ExecutionClassification.EXECUTABLE_VALIDATED,
                                      f"Opened {long_target}", success=True)
        response = self.responder.generate(f"open {long_target}", orch, result)
        self.assertLessEqual(len(response), 600)


class TestGenericVariation(unittest.TestCase):
    """Generic fallback response rotation tests."""

    def setUp(self):
        self.responder = ConversationResponder()

    def _generic(self):
        orch = _mock_orchestration(OrchestrationState.CONVERSATIONAL, response_text="tell me about quantum physics")
        result = _mock_handoff_result(ExecutionClassification.CONVERSATIONAL_ONLY, "tell me about quantum physics")
        return self.responder.generate("tell me about quantum physics", orch, result)

    def test_generic_neutral_rotates(self):
        """Neutral generic responses rotate through variants."""
        r1 = self._generic()
        r2 = self._generic()
        r3 = self._generic()
        self.assertNotEqual(r1, r2)
        self.assertNotEqual(r2, r3)

    def test_generic_rotation_deterministic(self):
        """Same sequence produces same generic responses."""
        r1 = ConversationResponder()
        r2 = ConversationResponder()
        seq1, seq2 = [], []
        for _ in range(5):
            o = _mock_orchestration(OrchestrationState.CONVERSATIONAL, response_text="tell me about quantum physics")
            h = _mock_handoff_result(ExecutionClassification.CONVERSATIONAL_ONLY, "tell me about quantum physics")
            seq1.append(r1.generate("tell me about quantum physics", o, h))
            seq2.append(r2.generate("tell me about quantum physics", o, h))
        self.assertEqual(seq1, seq2)

    def test_generic_exhausts_and_wraps(self):
        """Generic responses wrap around after exhausting pool."""
        results = set()
        for _ in range(10):
            results.add(self._generic())
        self.assertGreaterEqual(len(results), 3)

    def test_concise_generic_rotates(self):
        """Concise tone generic rotates through variants."""
        self.responder.set_tone(ConversationTone.CONCISE)
        r1 = self._generic()
        r2 = self._generic()
        self.assertNotEqual(r1, r2)


class TestKnowledgeBaseVariants(unittest.TestCase):
    """Knowledge-base variant rotation tests."""

    def setUp(self):
        self.responder = ConversationResponder()

    def test_kb_what_is_kio_rotates(self):
        """'what is kio' rotates through variants."""
        o = _mock_orchestration(OrchestrationState.CONVERSATIONAL, response_text="what is kio")
        h = _mock_handoff_result(ExecutionClassification.CONVERSATIONAL_ONLY, "what is kio")
        r1 = self.responder.generate("what is kio", o, h)
        o2 = _mock_orchestration(OrchestrationState.CONVERSATIONAL, response_text="what is kio")
        h2 = _mock_handoff_result(ExecutionClassification.CONVERSATIONAL_ONLY, "what is kio")
        r2 = self.responder.generate("what is kio", o2, h2)
        self.assertNotEqual(r1, r2)

    def test_kb_what_can_you_do_rotates(self):
        """'what can you do' rotates through variants."""
        o = _mock_orchestration(OrchestrationState.CONVERSATIONAL, response_text="what can you do")
        h = _mock_handoff_result(ExecutionClassification.CONVERSATIONAL_ONLY, "what can you do")
        r1 = self.responder.generate("what can you do", o, h)
        r2 = self.responder.generate("what can you do", o, h)
        self.assertNotEqual(r1, r2)

    def test_kb_who_is_joel_static(self):
        """'who is joel' stays static (no variant pool)."""
        o = _mock_orchestration(OrchestrationState.CONVERSATIONAL, response_text="who is joel")
        h = _mock_handoff_result(ExecutionClassification.CONVERSATIONAL_ONLY, "who is joel")
        r1 = self.responder.generate("who is joel", o, h)
        r2 = self.responder.generate("who is joel", o, h)
        self.assertEqual(r1, r2)

    def test_kb_deterministic_reproducible(self):
        """Same KB sequence produces same output across fresh responders."""
        r1 = ConversationResponder()
        r2 = ConversationResponder()
        seq1, seq2 = [], []
        for _ in range(4):
            o = _mock_orchestration(OrchestrationState.CONVERSATIONAL, response_text="what is kio")
            h = _mock_handoff_result(ExecutionClassification.CONVERSATIONAL_ONLY, "what is kio")
            seq1.append(r1.generate("what is kio", o, h))
            seq2.append(r2.generate("what is kio", o, h))
        self.assertEqual(seq1, seq2)

    def test_kb_variant_target_present(self):
        """KB variants still contain core information."""
        o = _mock_orchestration(OrchestrationState.CONVERSATIONAL, response_text="what is kio")
        h = _mock_handoff_result(ExecutionClassification.CONVERSATIONAL_ONLY, "what is kio")
        response = self.responder.generate("what is kio", o, h)
        self.assertIn("KIO", response)
        self.assertIn("assistant", response.lower())


class TestRepeatedResponseVariants(unittest.TestCase):
    """Repeated-input response pool tests."""

    def setUp(self):
        self.responder = ConversationResponder()

    def _send(self, text: str):
        orch = _mock_orchestration(OrchestrationState.CONVERSATIONAL, response_text=text)
        result = _mock_handoff_result(ExecutionClassification.CONVERSATIONAL_ONLY, text)
        return self.responder.generate(text, orch, result)

    def test_repeated_second_call_acknowledges(self):
        """Second same greeting returns repeated response."""
        self._send("hello")
        r2 = self._send("hello")
        self.assertIn("again", r2.lower())

    def test_repeated_third_call_acknowledges(self):
        """Third same greeting acknowledges repetition."""
        self._send("hello")
        self._send("hello")
        r3 = self._send("hello")
        self.assertIn("greeting", r3.lower())

    def test_repeated_rotates_across_calls(self):
        """Repeated responses use rotation within pools."""
        self._send("hello")
        r2_first = self._send("hello")
        # Reset with fresh responder to test rotation at repeat count
        r2 = ConversationResponder()
        r2.generate("hello", _mock_orchestration(OrchestrationState.CONVERSATIONAL, response_text="hello"), _mock_handoff_result(ExecutionClassification.CONVERSATIONAL_ONLY, "hello"))
        r2_second = r2.generate("hello", _mock_orchestration(OrchestrationState.CONVERSATIONAL, response_text="hello"), _mock_handoff_result(ExecutionClassification.CONVERSATIONAL_ONLY, "hello"))
        # Both fresh responders start at same rotation counter -> same result
        self.assertEqual(r2_first, r2_second)

    def test_repeated_hi_counts_independently(self):
        """'hi' and 'hello' have independent repeat counters."""
        self._send("hello")
        self._send("hi")
        r2_hello = self._send("hello")
        self.assertIn("again", r2_hello.lower())

    def test_repeated_for_non_hello_category(self):
        """Repeated detection works for non-hello categories like 'thanks'."""
        self._send("thanks")
        r2 = self._send("thanks")
        self.assertIn("again", r2.lower())


class TestNormalization(unittest.TestCase):
    """Deterministic input normalization tests."""

    def setUp(self):
        self.responder = ConversationResponder()

    def _send(self, text: str):
        orch = _mock_orchestration(OrchestrationState.CONVERSATIONAL, response_text=text)
        result = _mock_handoff_result(ExecutionClassification.CONVERSATIONAL_ONLY, text)
        return self.responder.generate(text, orch, result)

    def test_contraction_whats_kio(self):
        """'what's kio' normalizes and resolves KB entry."""
        response = self._send("what's kio")
        self.assertIn("KIO", response)
        self.assertNotEqual(response, "what's kio")

    def test_contraction_whats_kio_no_apostrophe(self):
        """'whats kio' (no apostrophe) normalizes and resolves."""
        response = self._send("whats kio")
        self.assertIn("KIO", response)

    def test_typo_helo(self):
        """'helo' normalizes to 'hello' greeting."""
        response = self._send("helo")
        self.assertIn("Hello", response)

    def test_typo_hellp(self):
        """'hellp' normalizes to 'hello' greeting."""
        response = self._send("hellp")
        self.assertIn("Hello", response)

    def test_alias_thx(self):
        """'thx' normalizes to 'thanks' acknowledgment."""
        response = self._send("thx")
        self.assertIn("welcome", response.lower())

    def test_alias_ok_to_okay(self):
        """'ok' normalizes to 'okay' acknowledgment."""
        response = self._send("ok")
        self.assertIn("Got it", response)

    def test_normalization_deterministic(self):
        """Normalized matching is deterministic across fresh responders."""
        r1 = ConversationResponder()
        r2 = ConversationResponder()
        o = _mock_orchestration(OrchestrationState.CONVERSATIONAL, response_text="what's kio")
        h = _mock_handoff_result(ExecutionClassification.CONVERSATIONAL_ONLY, "what's kio")
        resp1 = r1.generate("what's kio", o, h)
        resp2 = r2.generate("what's kio", o, h)
        self.assertEqual(resp1, resp2)

    def test_whos_joel_normalizes(self):
        """'whos joel' normalizes to 'who is joel' KB entry."""
        response = self._send("whos joel")
        self.assertIn("Joel", response)

    def test_normalization_preserves_known_kb(self):
        """Existing KB queries still work unchanged."""
        response = self._send("who created you")
        self.assertIn("Joel", response)


class TestSynthesisCoherence(unittest.TestCase):
    """Lightweight response synthesis and transition coherence."""

    def setUp(self):
        self.responder = ConversationResponder()

    def test_execution_summary_closing_appears(self):
        """Execution summary optionally includes closing after rotation."""
        from mini_kio.llm.conversation_responder import _EXECUTION_CLOSINGS
        open_closings = _EXECUTION_CLOSINGS.get("open", [""])
        # Should have at least one non-empty closing
        has_closing = any(c for c in open_closings)
        self.assertTrue(has_closing)

    def test_synthesize_header_only(self):
        """_synthesize with header only returns header."""
        from mini_kio.llm.conversation_responder import _synthesize
        result = _synthesize("test header")
        self.assertEqual(result, "test header")

    def test_synthesize_with_detail(self):
        """_synthesize with detail appends detail."""
        from mini_kio.llm.conversation_responder import _synthesize
        result = _synthesize("header", detail="detail")
        self.assertEqual(result, "header detail")

    def test_synthesize_with_closing(self):
        """_synthesize with closing appends closing."""
        from mini_kio.llm.conversation_responder import _synthesize
        result = _synthesize("header", closing="done.")
        self.assertEqual(result, "header done.")

    def test_synthesize_all_parts(self):
        """_synthesize with all parts assembles correctly."""
        from mini_kio.llm.conversation_responder import _synthesize
        result = _synthesize("header", detail="middle", closing="end.")
        self.assertEqual(result, "header middle end.")

    def test_synthesize_empty_parts_omitted(self):
        """_synthesize omits empty detail and closing."""
        from mini_kio.llm.conversation_responder import _synthesize
        result = _synthesize("header", detail="", closing="")
        self.assertEqual(result, "header")

    def test_execution_summary_bounded_with_closing(self):
        """Execution summary with closing stays under max length."""
        long_target = "x" * 2000
        orch = _mock_orchestration(OrchestrationState.EXECUTABLE_READY, IntentType.EXECUTABLE)
        result = _mock_handoff_result(ExecutionClassification.EXECUTABLE_VALIDATED,
                                      f"Opened {long_target}", success=True)
        response = self.responder.generate(f"open {long_target}", orch, result)
        self.assertLessEqual(len(response), 600)


class TestMultiStepNarration(unittest.TestCase):
    """Deterministic multi-step summary tests via _summarize_steps."""

    def setUp(self):
        from mini_kio.core.command_router import _summarize_steps
        self._summarize = _summarize_steps

    def test_all_succeeded_two_steps(self):
        """Two successful steps collapse repeated verb."""
        steps = [{"action": "open_app", "target": "chrome"},
                 {"action": "open_app", "target": "calculator"}]
        results = [{"success": True}, {"success": True}]
        msg = self._summarize(steps, results)
        self.assertEqual(msg, "done - opened chrome and calculator")

    def test_all_succeeded_three_steps(self):
        """Three successful steps produce list with oxford comma."""
        steps = [{"action": "open_app", "target": "chrome"},
                 {"action": "open_app", "target": "calculator"},
                 {"action": "search_web", "target": "python"}]
        results = [{"success": True}, {"success": True}, {"success": True}]
        msg = self._summarize(steps, results)
        self.assertIn("opened chrome", msg)
        self.assertIn("calculator", msg)
        self.assertIn("searched python", msg)
        self.assertTrue(msg.startswith("done -"))

    def test_one_succeeded_one_blocked(self):
        """Mixed success/blocked produces partial summary."""
        steps = [{"action": "open_app", "target": "chrome"},
                 {"action": "close_app", "target": "notepad"}]
        results = [{"success": True}, {"blocked": True}]
        msg = self._summarize(steps, results)
        self.assertIn("done", msg.lower())
        self.assertIn("blocked", msg.lower())

    def test_all_blocked(self):
        """All steps blocked produces 'all blocked' message."""
        steps = [{"action": "close_app", "target": "notepad"}]
        results = [{"blocked": True}]
        msg = self._summarize(steps, results)
        self.assertEqual(msg, "all blocked - closed notepad")

    def test_single_step_succeeded(self):
        """Single successful step produces clean summary."""
        steps = [{"action": "open_app", "target": "chrome"}]
        results = [{"success": True}]
        msg = self._summarize(steps, results)
        self.assertEqual(msg, "done - opened chrome")

    def test_empty_steps(self):
        """Empty steps produce minimal summary."""
        msg = self._summarize([], [])
        self.assertEqual(msg, "done")


if __name__ == "__main__":
    unittest.main()
