import unittest
from mini_kio.llm.intent_models import IntentType
from mini_kio.llm.intent_classifier import IntentClassifier
from mini_kio.llm.intent_validator import IntentValidator


class TestIntentExtraction(unittest.TestCase):
    def setUp(self):
        self.classifier = IntentClassifier()
        self.validator = IntentValidator()

    def test_conversational_classification(self):
        raw = "Hello, how are you today?"
        classification = self.classifier.classify(raw)
        validated = self.validator.validate(classification)
        
        self.assertEqual(validated.primary_intent.intent_type, IntentType.CONVERSATIONAL)
        self.assertTrue(validated.is_safe)

    def test_informational_classification(self):
        raw = "What is the capital of France?"
        classification = self.classifier.classify(raw)
        validated = self.validator.validate(classification)
        
        self.assertEqual(validated.primary_intent.intent_type, IntentType.INFORMATIONAL)
        self.assertTrue(validated.is_safe)

    def test_executable_classification(self):
        raw = "Open notepad"
        classification = self.classifier.classify(raw)
        validated = self.validator.validate(classification)
        
        self.assertEqual(validated.primary_intent.intent_type, IntentType.EXECUTABLE)
        self.assertEqual(validated.primary_intent.proposed_action, "open")
        self.assertEqual(validated.primary_intent.proposed_target, "notepad")
        self.assertTrue(validated.is_safe)

    def test_forbidden_target_rejection(self):
        raw = "Close explorer.exe"
        classification = self.classifier.classify(raw)
        validated = self.validator.validate(classification)
        
        self.assertFalse(validated.is_safe)
        self.assertTrue(any("Forbidden target" in err for err in validated.primary_intent.validation_errors))

    def test_forbidden_action_rejection(self):
        # Test JSON input for explicit forbidden action
        raw = '{"intent_type": "executable", "action": "shutdown", "target": "now", "confidence": 1.0}'
        classification = self.classifier.classify(raw)
        validated = self.validator.validate(classification)
        
        self.assertFalse(validated.is_safe)
        self.assertTrue(any("Forbidden action" in err for err in validated.primary_intent.validation_errors))

    def test_ambiguous_target_rejection(self):
        raw = "Open notepad and calculator"
        classification = self.classifier.classify(raw)
        validated = self.validator.validate(classification)
        
        self.assertFalse(validated.is_safe)
        self.assertTrue(any("Ambiguous" in err for err in validated.primary_intent.validation_errors))

    def test_shell_injection_rejection(self):
        raw = "Open notepad; calc.exe"
        classification = self.classifier.classify(raw)
        validated = self.validator.validate(classification)
        
        self.assertFalse(validated.is_safe)
        self.assertTrue(any("Restricted pattern" in err for err in validated.primary_intent.validation_errors))

    def test_empty_payload_rejection(self):
        raw = "   "
        classification = self.classifier.classify(raw)
        validated = self.validator.validate(classification)
        
        self.assertEqual(validated.primary_intent.intent_type, IntentType.UNKNOWN)
        self.assertFalse(validated.is_safe)

    def test_unsafe_classification_rejection(self):
        raw = '{"intent_type": "unsafe", "confidence": 1.0}'
        classification = self.classifier.classify(raw)
        validated = self.validator.validate(classification)
        
        self.assertEqual(validated.primary_intent.intent_type, IntentType.UNSAFE)
        self.assertFalse(validated.is_safe)


if __name__ == "__main__":
    unittest.main()
