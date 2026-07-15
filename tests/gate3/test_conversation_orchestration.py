import unittest
from mini_kio.llm.intent_models import IntentType, ExtractedIntent, IntentClassification
from mini_kio.llm.conversation_models import OrchestrationState
from mini_kio.llm.conversation_orchestrator import ConversationOrchestrator


class TestConversationOrchestration(unittest.TestCase):
    def setUp(self):
        self.orchestrator = ConversationOrchestrator()

    def _mock_classification(self, intent_type: IntentType, action=None, target=None, safe=True, confidence=1.0, text=""):
        primary = ExtractedIntent(
            raw_text=text,
            normalized_text=text.lower(),
            confidence=confidence,
            intent_type=intent_type,
            proposed_action=action,
            proposed_target=target,
            validation_errors=[] if safe else ["Unsafe"]
        )
        return IntentClassification(primary_intent=primary, is_safe=safe)

    def test_conversational_routing(self):
        c = self._mock_classification(IntentType.CONVERSATIONAL, text="Hello")
        response = self.orchestrator.orchestrate(c)
        self.assertEqual(response.state, OrchestrationState.CONVERSATIONAL)
        self.assertEqual(response.response_text, "Hello")

    def test_executable_routing_immediate(self):
        c = self._mock_classification(IntentType.EXECUTABLE, action="open", target="notepad", confidence=0.9)
        response = self.orchestrator.orchestrate(c)
        self.assertEqual(response.state, OrchestrationState.EXECUTABLE_READY)
        self.assertIn("Executing open notepad", response.response_text)

    def test_confirmation_gating_low_confidence(self):
        c = self._mock_classification(IntentType.EXECUTABLE, action="open", target="notepad", confidence=0.5)
        response = self.orchestrator.orchestrate(c)
        self.assertEqual(response.state, OrchestrationState.AWAITING_CONFIRMATION)
        self.assertIn("Shall I proceed", response.response_text)
        self.assertEqual(response.metadata["confirmation_reason"], "Low intent confidence")

    def test_confirmation_gating_destructive(self):
        c = self._mock_classification(IntentType.EXECUTABLE, action="close", target="notepad")
        response = self.orchestrator.orchestrate(c)
        self.assertEqual(response.state, OrchestrationState.AWAITING_CONFIRMATION)
        self.assertEqual(response.metadata["confirmation_reason"], "Potentially destructive action")

    def test_confirmation_success(self):
        # 1. Trigger confirmation state
        c1 = self._mock_classification(IntentType.EXECUTABLE, action="close", target="notepad")
        self.orchestrator.orchestrate(c1)
        
        # 2. Provide confirmation
        c2 = self._mock_classification(IntentType.CONVERSATIONAL, text="yes")
        response = self.orchestrator.orchestrate(c2)
        
        self.assertEqual(response.state, OrchestrationState.EXECUTABLE_READY)
        self.assertIn("Confirmed", response.response_text)

    def test_confirmation_rejection(self):
        # 1. Trigger confirmation state
        c1 = self._mock_classification(IntentType.EXECUTABLE, action="close", target="notepad")
        self.orchestrator.orchestrate(c1)
        
        # 2. Provide rejection
        c2 = self._mock_classification(IntentType.CONVERSATIONAL, text="no")
        response = self.orchestrator.orchestrate(c2)
        
        self.assertEqual(response.state, OrchestrationState.REFUSED)
        self.assertIn("cancelled", response.response_text)

    def test_refusal_handling_unsafe(self):
        c = self._mock_classification(IntentType.EXECUTABLE, action="delete", target="system32", safe=False)
        response = self.orchestrator.orchestrate(c)
        self.assertEqual(response.state, OrchestrationState.REFUSED)
        self.assertIn("safety reasons", response.response_text)

    def test_invalid_confirmation_rejection(self):
        # Implicit confirmation without state should be treated as conversational
        c = self._mock_classification(IntentType.CONVERSATIONAL, text="do it")
        response = self.orchestrator.orchestrate(c)
        self.assertEqual(response.state, OrchestrationState.CONVERSATIONAL)
        self.assertEqual(response.response_text, "do it")


if __name__ == "__main__":
    unittest.main()
