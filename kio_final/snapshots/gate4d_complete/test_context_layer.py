import unittest
import time
from mini_kio.context.context_models import ContextType
from mini_kio.context.context_manager import ContextManager
from mini_kio.context.context_sanitizer import ContextSanitizer

class TestContextLayer(unittest.TestCase):
    def setUp(self):
        self.manager = ContextManager()
        self.sanitizer = ContextSanitizer()

    def test_sanitization_executable_rejection(self):
        unsafe_texts = [
            "Open notepad; rm -rf /",
            "sudo apt-get update",
            "$(calc.exe)",
            "{\"intent_type\": \"executable\"}",
            "import os; os.system('ls')"
        ]
        for text in unsafe_texts:
            is_safe, _, _ = self.sanitizer.sanitize(text)
            self.assertFalse(is_safe, f"Failed to reject unsafe text: {text}")

    def test_sanitization_oversized_rejection(self):
        oversized = "A" * 3000
        is_safe, _, _ = self.sanitizer.sanitize(oversized)
        self.assertFalse(is_safe)

    def test_context_retention_and_eviction(self):
        self.manager.MAX_ENTRIES = 3
        self.manager.add_entry("entry 1", ContextType.CONVERSATIONAL)
        self.manager.add_entry("entry 2", ContextType.CONVERSATIONAL)
        self.manager.add_entry("entry 3", ContextType.CONVERSATIONAL)
        self.manager.add_entry("entry 4", ContextType.CONVERSATIONAL)
        
        snapshot = self.manager.get_snapshot()
        self.assertEqual(snapshot.count, 3)
        self.assertEqual(snapshot.entries[0].content, "entry 4") # Newest first
        self.assertEqual(snapshot.entries[2].content, "entry 2") # Entry 1 should be evicted

    def test_size_bounded_eviction(self):
        self.manager.MAX_TOTAL_SIZE_CHARS = 20
        self.manager.add_entry("1234567890", ContextType.CONVERSATIONAL) # 10 chars
        self.manager.add_entry("1234567890", ContextType.CONVERSATIONAL) # 10 chars
        self.manager.add_entry("123", ContextType.CONVERSATIONAL)        # 3 chars -> trips eviction
        
        snapshot = self.manager.get_snapshot()
        self.assertLessEqual(snapshot.total_size, 20)
        self.assertEqual(snapshot.count, 2)

    def test_deterministic_retrieval(self):
        self.manager.add_entry("old", ContextType.CONVERSATIONAL)
        time.sleep(0.01)
        self.manager.add_entry("new", ContextType.CONVERSATIONAL)
        
        snapshot = self.manager.get_snapshot()
        self.assertEqual(snapshot.entries[0].content, "new")
        self.assertEqual(snapshot.entries[1].content, "old")

    def test_expiration_pruning(self):
        self.manager.TTL_S = 0.1
        self.manager.add_entry("expiring", ContextType.CONVERSATIONAL)
        time.sleep(0.2)
        snapshot = self.manager.get_snapshot()
        self.assertEqual(snapshot.count, 0)

    def test_imported_history_sanitization(self):
        raw_history = [
            "Hello KIO",
            "sudo hack the planet",
            "I like sushi",
            "Open browser & delete cookies"
        ]
        sanitized = self.sanitizer.sanitize_history(raw_history)
        self.assertEqual(len(sanitized), 2)
        self.assertIn("Hello KIO", sanitized)
        self.assertIn("I like sushi", sanitized)

    def test_authority_boundary_enforcement(self):
        # Context layer should not have any method that even looks like execution dispatch
        self.assertFalse(has_all_attrs(self.manager, ["execute", "dispatch", "run", "launch"]))

def has_all_attrs(obj, attrs):
    return any(hasattr(obj, attr) for attr in attrs)

if __name__ == "__main__":
    unittest.main()
