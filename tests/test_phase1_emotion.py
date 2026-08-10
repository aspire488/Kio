"""Phase 1: Emotion routing — regression + new behavior tests."""
import unittest
from mini_kio.core.pipeline import _IntentClassifier
from mini_kio.core.pipeline.types import IntentType


class TestEmotionRouting(unittest.TestCase):
    def setUp(self):
        self.clf = _IntentClassifier()

    def _classify(self, text):
        return self.clf.classify(text, text)

    # --- Must route to CONVERSATION (empathy) ---
    def test_im_sad(self):
        d = self._classify("I'm sad")
        self.assertEqual(d.intent_type, IntentType.CONVERSATION)
        self.assertEqual(d.action, "empathy")

    def test_im_angry(self):
        d = self._classify("I'm angry about something")
        self.assertEqual(d.intent_type, IntentType.CONVERSATION)
        self.assertEqual(d.action, "empathy")

    def test_im_stressed(self):
        d = self._classify("I'm stressed")
        self.assertEqual(d.intent_type, IntentType.CONVERSATION)

    def test_im_exhausted(self):
        d = self._classify("I'm exhausted")
        self.assertEqual(d.intent_type, IntentType.CONVERSATION)

    def test_im_happy(self):
        d = self._classify("I'm so happy right now")
        self.assertEqual(d.intent_type, IntentType.CONVERSATION)

    def test_im_excited(self):
        d = self._classify("I'm excited about the trip")
        self.assertEqual(d.intent_type, IntentType.CONVERSATION)

    def test_i_feel_sad(self):
        d = self._classify("I feel sad today")
        self.assertEqual(d.intent_type, IntentType.CONVERSATION)

    def test_i_am_angry(self):
        d = self._classify("I am angry")
        self.assertEqual(d.intent_type, IntentType.CONVERSATION)

    def test_sad_right_now(self):
        d = self._classify("sad right now")
        self.assertEqual(d.intent_type, IntentType.CONVERSATION)

    def test_angry_today(self):
        d = self._classify("angry today")
        self.assertEqual(d.intent_type, IntentType.CONVERSATION)

    def test_im_very_frustrated(self):
        d = self._classify("I'm very frustrated")
        self.assertEqual(d.intent_type, IntentType.CONVERSATION)

    def test_im_really_nervous(self):
        d = self._classify("I'm really nervous")
        self.assertEqual(d.intent_type, IntentType.CONVERSATION)

    # --- Must NOT be caught (media, commands, etc.) ---
    def test_play_music_still_works(self):
        d = self._classify("play some jazz music")
        self.assertNotEqual(d.intent_type, IntentType.CONVERSATION)

    def test_play_interstellar_trailer(self):
        d = self._classify("play interstellar trailer")
        self.assertNotEqual(d.intent_type, IntentType.CONVERSATION)

    def test_open_youtube(self):
        d = self._classify("open youtube")
        self.assertNotEqual(d.intent_type, IntentType.CONVERSATION)

    def test_search_python(self):
        d = self._classify("search python tutorial")
        self.assertNotEqual(d.intent_type, IntentType.CONVERSATION)

    def test_close_tab(self):
        d = self._classify("close tab")
        self.assertNotEqual(d.intent_type, IntentType.CONVERSATION)

    def test_play_something_similar(self):
        d = self._classify("play something similar")
        self.assertNotEqual(d.intent_type, IntentType.CONVERSATION)

    def test_what_is_python(self):
        d = self._classify("what is python")
        self.assertNotEqual(d.action, "empathy")

    def test_hello(self):
        d = self._classify("hello")
        self.assertNotEqual(d.action, "empathy")

    def test_tell_me_a_joke(self):
        d = self._classify("tell me a joke")
        self.assertNotEqual(d.action, "empathy")

    # --- False positives: must NOT trigger emotion ---
    def test_angry_birds(self):
        d = self._classify("Angry Birds")
        self.assertNotEqual(d.action, "empathy")

    def test_happy_feet(self):
        d = self._classify("Happy Feet")
        self.assertNotEqual(d.action, "empathy")

    def test_angry_playlist(self):
        d = self._classify("Angry playlist")
        self.assertNotEqual(d.action, "empathy")

    def test_angry_music(self):
        d = self._classify("Angry music")
        self.assertNotEqual(d.action, "empathy")

    def test_stress_testing(self):
        d = self._classify("Stress testing")
        self.assertNotEqual(d.action, "empathy")

    def test_frustrated_interview(self):
        d = self._classify("Frustrated Lewis Hamilton interview")
        self.assertNotEqual(d.action, "empathy")

    def test_play_happy_song(self):
        d = self._classify("Play Happy by Pharrell")
        self.assertNotEqual(d.action, "empathy")


if __name__ == "__main__":
    unittest.main()
