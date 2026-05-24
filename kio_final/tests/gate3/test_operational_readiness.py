import unittest
from unittest.mock import MagicMock, patch
from mini_kio.llm.intent_models import IntentType, ExtractedIntent, IntentClassification
from mini_kio.llm.conversation_models import OrchestrationResponse, OrchestrationState, PendingAction
from mini_kio.runtime.runtime_handoff import RuntimeHandoff
from mini_kio.runtime.runtime_contracts import ExecutionClassification
from mini_kio.core.runtime import SafetyState

class TestOperationalReadiness(unittest.TestCase):
    """
    Final mocked operational readiness checks for Gate 3.
    Verifies critical safety scenarios that must pass before manual walkthroughs.
    """

    def setUp(self):
        self.handoff = RuntimeHandoff()

    def _mock_orch(self, state: OrchestrationState, intent_type: IntentType = IntentType.CONVERSATIONAL, 
                  action="open", target="notepad", safe=True):
        primary = ExtractedIntent(
            raw_text="op", normalized_text="op", confidence=1.0, 
            intent_type=intent_type, proposed_action=action, proposed_target=target,
            validation_errors=[] if safe else ["Unsafe"]
        )
        classification = IntentClassification(primary_intent=primary, is_safe=safe)
        pending = PendingAction(action=action, target=target, classification=classification) if intent_type == IntentType.EXECUTABLE else None
        
        return OrchestrationResponse(
            state=state, response_text="mock", intent_type=intent_type, pending_action=pending
        )

    @patch('mini_kio.runtime.runtime_handoff.get_runtime')
    def test_readiness_runtime_lockdown_veto(self, mock_get_runtime):
        # Scenario: User confirmed an action but admin triggered LOCKDOWN simultaneously.
        mock_get_runtime.return_value = MagicMock(safety_state=SafetyState.LOCKDOWN)
        
        orch = self._mock_orch(OrchestrationState.EXECUTABLE_READY, IntentType.EXECUTABLE)
        result = self.handoff.handle_handoff(orch)
        
        self.assertEqual(result.classification, ExecutionClassification.EXECUTABLE_BLOCKED)
        self.assertIn("LOCKDOWN", result.message)

    def test_readiness_expired_confirmation_rejection(self):
        # Scenario: Orchestrator is still waiting for confirmation.
        # Handoff should NEVER execute in this state.
        orch = self._mock_orch(OrchestrationState.AWAITING_CONFIRMATION, IntentType.EXECUTABLE)
        
        with patch('mini_kio.runtime.runtime_handoff.execute_action') as mock_exec:
            result = self.handoff.handle_handoff(orch)
            self.assertEqual(result.classification, ExecutionClassification.EXECUTABLE_REQUIRES_CONFIRMATION)
            mock_exec.assert_not_called()

    def test_readiness_degraded_provider_blocking(self):
        # Scenario: Gateway has marked provider as degraded.
        orch = self._mock_orch(OrchestrationState.DEGRADED)
        result = self.handoff.handle_handoff(orch)
        
        self.assertEqual(result.classification, ExecutionClassification.DEGRADED_BLOCK)
        self.assertFalse(result.success)

    def test_readiness_unvalidated_intent_blocking(self):
        # Scenario: Orchestrator somehow passed an unsafe intent to READY state.
        orch = self._mock_orch(OrchestrationState.EXECUTABLE_READY, IntentType.EXECUTABLE, safe=False)
        result = self.handoff.handle_handoff(orch)
        
        self.assertEqual(result.classification, ExecutionClassification.EXECUTABLE_BLOCKED)
        self.assertIn("validation failure", result.message)

    def test_readiness_malformed_payload_protection(self):
        # Scenario: Executable state without pending action metadata.
        orch = OrchestrationResponse(
            state=OrchestrationState.EXECUTABLE_READY, 
            response_text="oops", 
            intent_type=IntentType.EXECUTABLE
        )
        result = self.handoff.handle_handoff(orch)
        
        self.assertEqual(result.classification, ExecutionClassification.MALFORMED_PAYLOAD)

    @patch('mini_kio.runtime.runtime_handoff.get_runtime')
    def test_readiness_context_isolation(self, mock_get_runtime):
        # Verify the context manager (if accessible) has no side-effects.
        from mini_kio.context.context_manager import ContextManager
        from mini_kio.context.context_models import ContextType
        
        cm = ContextManager()
        # Verify it can add entries safely
        self.assertTrue(cm.add_entry("Safe context", ContextType.CONVERSATIONAL))
        
        # Verify it rejects executable content
        self.assertFalse(cm.add_entry("Open notepad; rm -rf /", ContextType.CONVERSATIONAL))

if __name__ == "__main__":
    unittest.main()
