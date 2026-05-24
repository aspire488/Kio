import unittest
from unittest.mock import MagicMock, patch
from mini_kio.llm.intent_models import IntentType, ExtractedIntent, IntentClassification
from mini_kio.llm.conversation_models import OrchestrationResponse, OrchestrationState, PendingAction
from mini_kio.runtime.runtime_handoff import RuntimeHandoff
from mini_kio.runtime.runtime_contracts import ExecutionClassification
from mini_kio.core.runtime import SafetyState

class TestIntegrationBoundaries(unittest.TestCase):
    def setUp(self):
        self.handoff = RuntimeHandoff()

    def _mock_orchestration(self, state: OrchestrationState, intent_type: IntentType = IntentType.CONVERSATIONAL, 
                           action="open", target="notepad", safe=True):
        primary = ExtractedIntent(
            raw_text="mock",
            normalized_text="mock",
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
            response_text="mock response",
            intent_type=intent_type,
            pending_action=pending
        )

    @patch('mini_kio.runtime.runtime_handoff.get_runtime')
    @patch('mini_kio.runtime.runtime_handoff.execute_action')
    def test_end_to_end_validated_handoff_path(self, mock_execute, mock_get_runtime):
        # NORMAL state, EXECUTABLE_READY, intent is SAFE
        mock_get_runtime.return_value = MagicMock(safety_state=SafetyState.NORMAL)
        mock_execute.return_value = {"success": True}
        
        orch = self._mock_orchestration(OrchestrationState.EXECUTABLE_READY, IntentType.EXECUTABLE, safe=True)
        result = self.handoff.handle_handoff(orch)
        
        self.assertEqual(result.classification, ExecutionClassification.EXECUTABLE_VALIDATED)
        self.assertTrue(result.success)
        mock_execute.assert_called_once()

    def test_provider_degradation_blocking(self):
        # Orchestration state is DEGRADED (gateway failure)
        orch = self._mock_orchestration(OrchestrationState.DEGRADED)
        result = self.handoff.handle_handoff(orch)
        
        self.assertEqual(result.classification, ExecutionClassification.DEGRADED_BLOCK)
        self.assertFalse(result.success)

    @patch('mini_kio.runtime.runtime_handoff.get_runtime')
    def test_runtime_veto_enforcement(self, mock_get_runtime):
        # System in LOCKDOWN, attempt executable handoff
        mock_get_runtime.return_value = MagicMock(safety_state=SafetyState.LOCKDOWN)
        
        orch = self._mock_orchestration(OrchestrationState.EXECUTABLE_READY, IntentType.EXECUTABLE)
        result = self.handoff.handle_handoff(orch)
        
        self.assertEqual(result.classification, ExecutionClassification.EXECUTABLE_BLOCKED)
        self.assertIn("LOCKDOWN", result.message)

    def test_malformed_orchestration_rejection(self):
        # EXECUTABLE_READY but missing pending_action metadata
        orch = OrchestrationResponse(
            state=OrchestrationState.EXECUTABLE_READY,
            response_text="oops",
            intent_type=IntentType.EXECUTABLE
        )
        result = self.handoff.handle_handoff(orch)
        
        self.assertEqual(result.classification, ExecutionClassification.MALFORMED_PAYLOAD)

    def test_conversational_isolation(self):
        # CONVERSATIONAL state should never trigger execution boundary
        orch = self._mock_orchestration(OrchestrationState.CONVERSATIONAL, IntentType.CONVERSATIONAL)
        
        with patch('mini_kio.runtime.runtime_handoff.execute_action') as mock_execute:
            result = self.handoff.handle_handoff(orch)
            self.assertEqual(result.classification, ExecutionClassification.CONVERSATIONAL_ONLY)
            mock_execute.assert_not_called()

    def test_expired_confirmation_rejection(self):
        # If state is AWAITING_CONFIRMATION, handoff should not execute
        orch = self._mock_orchestration(OrchestrationState.AWAITING_CONFIRMATION, IntentType.EXECUTABLE)
        
        with patch('mini_kio.runtime.runtime_handoff.execute_action') as mock_execute:
            result = self.handoff.handle_handoff(orch)
            self.assertEqual(result.classification, ExecutionClassification.EXECUTABLE_REQUIRES_CONFIRMATION)
            mock_execute.assert_not_called()

if __name__ == "__main__":
    unittest.main()
