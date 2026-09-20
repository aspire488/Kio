import unittest
from unittest.mock import MagicMock, patch, PropertyMock
from mini_kio.runtime.runtime_contracts import ExecutionClassification
from mini_kio.runtime.runtime_handoff import RuntimeHandoff
from mini_kio.llm.intent_models import IntentType, ExtractedIntent, IntentClassification
from mini_kio.llm.conversation_models import OrchestrationResponse, OrchestrationState, PendingAction
from mini_kio.llm.conversation_orchestrator import ConversationOrchestrator
from mini_kio.llm.intent_classifier import IntentClassifier
from mini_kio.llm.intent_validator import IntentValidator
from mini_kio.core.runtime import SafetyState
from mini_kio.core.command_router import handle_command


class TestRuntimeWiring(unittest.TestCase):
    def setUp(self):
        self.handoff = RuntimeHandoff()

    def _mock_orchestration(self, state: OrchestrationState, intent_type: IntentType = IntentType.CONVERSATIONAL, 
                           action="open", target="notepad", safe=True, text=""):
        primary = ExtractedIntent(
            raw_text=text,
            normalized_text=text.lower(),
            confidence=1.0,
            intent_type=intent_type,
            proposed_action=action,
            proposed_target=target,
            validation_errors=[] if safe else ["Unsafe"]
        )
        classification = IntentClassification(primary_intent=primary, is_safe=safe)
        pending = PendingAction(action=action, target=target, classification=classification) if intent_type == IntentType.EXECUTABLE else None
        
        return OrchestrationResponse(
            state=state,
            response_text=text or f"Handling {state.value}",
            intent_type=intent_type,
            pending_action=pending
        )

    @patch('mini_kio.runtime.runtime_handoff.execute_action')
    @patch('mini_kio.runtime.runtime_handoff.get_runtime')
    def test_validated_handoff_success(self, mock_get_runtime, mock_execute):
        # Setup: Normal state, executable ready
        mock_get_runtime.return_value = MagicMock(safety_state=SafetyState.NORMAL)
        mock_execute.return_value = {"success": True, "message": "Launched"}
        
        orch = self._mock_orchestration(OrchestrationState.EXECUTABLE_READY, intent_type=IntentType.EXECUTABLE)
        result = self.handoff.handle_handoff(orch)
        
        self.assertTrue(result.success)
        self.assertEqual(result.classification, ExecutionClassification.EXECUTABLE_VALIDATED)
        self.assertEqual(result.audit_metadata.dispatch_eligibility, True)
        mock_execute.assert_called_once_with("open", "notepad")

    @patch('mini_kio.runtime.runtime_handoff.get_runtime')
    def test_veto_in_emergency_mode(self, mock_get_runtime):
        mock_get_runtime.return_value = MagicMock(safety_state=SafetyState.EMERGENCY)
        
        orch = self._mock_orchestration(OrchestrationState.EXECUTABLE_READY, intent_type=IntentType.EXECUTABLE)
        result = self.handoff.handle_handoff(orch)
        
        self.assertFalse(result.success)
        self.assertEqual(result.classification, ExecutionClassification.EXECUTABLE_BLOCKED)
        self.assertIn("Runtime Veto", result.message)

    def test_confirmation_enforcement(self):
        orch = self._mock_orchestration(OrchestrationState.AWAITING_CONFIRMATION, intent_type=IntentType.EXECUTABLE)
        result = self.handoff.handle_handoff(orch)
        
        self.assertTrue(result.success)
        self.assertEqual(result.classification, ExecutionClassification.EXECUTABLE_REQUIRES_CONFIRMATION)
        self.assertEqual(result.audit_metadata.dispatch_eligibility, True)

    def test_unvalidated_intent_rejection(self):
        orch = self._mock_orchestration(OrchestrationState.EXECUTABLE_READY, intent_type=IntentType.EXECUTABLE, safe=False)
        result = self.handoff.handle_handoff(orch)
        
        self.assertFalse(result.success)
        self.assertEqual(result.classification, ExecutionClassification.EXECUTABLE_BLOCKED)
        self.assertIn("validation failure", result.message)

    def test_conversational_isolation(self):
        orch = self._mock_orchestration(OrchestrationState.CONVERSATIONAL, text="Hello there")
        result = self.handoff.handle_handoff(orch)
        
        self.assertTrue(result.success)
        self.assertEqual(result.classification, ExecutionClassification.CONVERSATIONAL_ONLY)
        self.assertEqual(result.message, "Hello there")

    def test_malformed_payload_rejection(self):
        orch = OrchestrationResponse(state=OrchestrationState.EXECUTABLE_READY, response_text="oops")
        result = self.handoff.handle_handoff(orch)
        
        self.assertFalse(result.success)
        self.assertEqual(result.classification, ExecutionClassification.MALFORMED_PAYLOAD)

    def test_audit_metadata_generation(self):
        orch = self._mock_orchestration(OrchestrationState.CONVERSATIONAL, text="Audit me")
        result = self.handoff.handle_handoff(orch)
        
        self.assertIsNotNone(result.audit_metadata)
        self.assertEqual(result.audit_metadata.intent_origin, str(IntentType.CONVERSATIONAL))
        self.assertEqual(result.audit_metadata.confirmation_state, str(OrchestrationState.CONVERSATIONAL))


class TestGate3PipelineIntegration(unittest.TestCase):
    """End-to-end Gate 3 orchestration pipeline integration tests."""

    def setUp(self):
        self.classifier = IntentClassifier()
        self.validator = IntentValidator()
        self.orchestrator = ConversationOrchestrator()
        self.handoff = RuntimeHandoff()

    def _run_pipeline(self, text: str) -> dict:
        """Run the full Gate 3 pipeline and return a handoff result."""
        classification = self.classifier.classify(text)
        validated = self.validator.validate(classification)
        orchestration = self.orchestrator.orchestrate(validated)
        result = self.handoff.handle_handoff(orchestration)
        return {
            "success": result.success,
            "message": result.message,
            "classification": result.classification,
            "audit": result.audit_metadata,
        }

    # ── Conversational prompts ─────────────────────────────────────────

    def test_conversational_prompt_does_not_fall_through(self):
        """'Tell me about KIO' must not produce parser failure."""
        result = self._run_pipeline("Tell me about KIO")
        self.assertTrue(result["success"])
        self.assertNotIn("I don't understand", result["message"])

    def test_conversational_routing(self):
        """Conversational input returns CONVERSATIONAL_ONLY."""
        result = self._run_pipeline("Hello, how are you?")
        self.assertTrue(result["success"])
        self.assertEqual(result["classification"], ExecutionClassification.CONVERSATIONAL_ONLY)

    # ── Informational prompts ──────────────────────────────────────────

    def test_informational_prompt_routes_safely(self):
        """'How does runtime authority work' must not produce parser failure."""
        result = self._run_pipeline("How does runtime authority work")
        self.assertTrue(result["success"])
        self.assertNotIn("I don't understand", result["message"])

    # ── Executable prompts ─────────────────────────────────────────────

    def test_executable_prompt_classification(self):
        """'open notepad' classifies executable, gates through confirmation (confidence 0.7 < 0.8)."""
        result = self._run_pipeline("open notepad")
        self.assertEqual(result["classification"], ExecutionClassification.EXECUTABLE_REQUIRES_CONFIRMATION)

    def test_executable_prompt_requires_confirmation_for_low_confidence(self):
        """Low-confidence executable must gate through confirmation."""
        result = self._run_pipeline("open something_unknown")
        self.assertEqual(result["classification"], ExecutionClassification.EXECUTABLE_REQUIRES_CONFIRMATION)

    # ── Confirmation lifecycle ─────────────────────────────────────────

    def test_yes_confirms_outside_state_is_conversational(self):
        """'yes' outside confirmation state must be conversational."""
        result = self._run_pipeline("yes")
        self.assertTrue(result["success"])
        self.assertEqual(result["classification"], ExecutionClassification.CONVERSATIONAL_ONLY)

    def test_do_it_confirms_outside_state_is_conversational(self):
        """'do it' outside confirmation state must be conversational."""
        result = self._run_pipeline("do it")
        self.assertTrue(result["success"])
        self.assertEqual(result["classification"], ExecutionClassification.CONVERSATIONAL_ONLY)

    def test_no_outside_confirmation_is_conversational(self):
        """'no' outside confirmation state must be conversational."""
        result = self._run_pipeline("no")
        self.assertTrue(result["success"])
        self.assertEqual(result["classification"], ExecutionClassification.CONVERSATIONAL_ONLY)

    def test_confirmation_lifecycle_full(self):
        """Full confirmation flow: executable -> await -> yes -> execute."""
        # Step 1: Trigger executable with low confidence (forces confirmation)
        c1 = self.classifier.classify("open edge")
        v1 = self.validator.validate(c1)
        o1 = self.orchestrator.orchestrate(v1)
        self.assertEqual(o1.state, OrchestrationState.AWAITING_CONFIRMATION)

        # Step 2: Confirm with 'yes'
        c2 = self.classifier.classify("yes")
        v2 = self.validator.validate(c2)
        o2 = self.orchestrator.orchestrate(v2)
        self.assertEqual(o2.state, OrchestrationState.EXECUTABLE_READY)

    def test_confirmation_rejection(self):
        """Confirmation rejection: executable -> await -> no -> refuse."""
        c1 = self.classifier.classify("close edge")
        v1 = self.validator.validate(c1)
        o1 = self.orchestrator.orchestrate(v1)
        self.assertEqual(o1.state, OrchestrationState.AWAITING_CONFIRMATION)

        c2 = self.classifier.classify("no")
        v2 = self.validator.validate(c2)
        o2 = self.orchestrator.orchestrate(v2)
        self.assertEqual(o2.state, OrchestrationState.REFUSED)

    # ── Restricted-target rejection ────────────────────────────────────

    def test_restricted_target_rejected(self):
        """'open explorer.exe' must be rejected by validator."""
        classification = self.classifier.classify("open explorer.exe")
        validated = self.validator.validate(classification)
        self.assertFalse(validated.is_safe)
        self.assertTrue(any("Forbidden target" in err for err in validated.primary_intent.validation_errors))

    # ── Runtime veto via handoff ───────────────────────────────────────
    # NOTE: Full-pipeline veto requires high-confidence JSON intent (>= 0.8)
    #       to reach EXECUTABLE_READY state before veto applies.
    #       The unit test test_veto_in_emergency_mode (TestRuntimeWiring)
    #       already covers handoff-level veto directly.

    # ── Unknown command handling ───────────────────────────────────────

    def test_unknown_command_returns_error(self):
        """Unknown commands must not crash and return helpful response."""
        result = handle_command("xyzzy_unrecognizable_command")
        self.assertIn("success", result)
        self.assertTrue(result.get("success") or "understand" in result.get("message", "").lower()
                        or "Cannot process" in result.get("message", ""))


class TestPipelineDispatchIntegration(unittest.TestCase):
    """Integration tests for the authoritative Pipeline dispatch."""

    @patch('mini_kio.core.runtime.get_runtime_snapshot')
    @patch('mini_kio.core.runtime._CURRENT_RUNTIME')
    @patch('mini_kio.core.command_router.handle_command')
    def test_dispatch_goes_through_pipeline(self, mock_handle, mock_runtime, mock_snapshot):
        """dispatch_channel_input must go through handle_command (Pipeline) exactly once."""
        from mini_kio.core.runtime import dispatch_channel_input

        mock_snapshot.return_value = {}
        mock_runtime.state = "running"
        mock_runtime.shutdown_requested = False
        mock_runtime.prune_tracked_processes = MagicMock()
        mock_handle.return_value = {"success": True, "message": "handled"}

        result = dispatch_channel_input("hello", channel="test", user_id=0)

        mock_handle.assert_called_once()
        self.assertTrue(result.get("success"))


if __name__ == "__main__":
    unittest.main()
