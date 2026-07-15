
import unittest
import sys
from typing import Any, Optional, Callable
from mini_kio.media.intelligence.integration_adapter import MediaIntelligenceAdapter
from mini_kio.media.intelligence.media_intelligence_models import TopicType, ArtifactType

class MockMediaSystem:
    def __init__(self):
        self.last_played = None
    
    def retrieve(self, query: str, topic: Any = None, mode: Any = None) -> str:
        q = query.lower()
        if "interstellar" in q:
            if "composer" in q or "music" in q:
                return "Hans Zimmer composed the soundtrack for Interstellar. It is one of the most iconic scores."
            if "soundtrack" in q:
                return "The Interstellar soundtrack is available. Composed by Hans Zimmer."
            return "Interstellar is a 2014 epic science fiction film directed by Christopher Nolan. It stars Matthew McConaughey."
        if "fifa world cup" in q:
            if "standings" in q or "leading" in q or "table" in q:
                return "In Group A of the FIFA World Cup 2026, Canada is leading the group with 6 points."
            if "results" in q:
                return "Recent results for FIFA World Cup 2026: USA 2-1 Mexico."
            if "highlights" in q:
                return "Latest highlights from FIFA World Cup 2026 show great goals."
            return "The 2026 FIFA World Cup will be hosted by Canada, Mexico, and the United States."
        if "atomic habits" in q:
            if "audiobook" in q:
                return "Atomic Habits audiobook is narrated by James Clear."
            if "author" in q or "interview" in q:
                return "Show author interview with James Clear about Atomic Habits. He discusses habit loops."
            return "Atomic Habits by James Clear is a guide to building good habits."
        if "gta vi" in q:
            if "gameplay" in q:
                return "GTA VI gameplay reveals the return to Vice City with stunning visuals."
            return "GTA VI is the upcoming game from Rockstar Games. Set in Vice City."
        if "believer" in q:
            return "Believer by Imagine Dragons is a hit song from their album Evolve."
        return f"Information about {query}"
    
    def play(self, url: str) -> None:
        self.last_played = url

class TestFinalMediaGA(unittest.TestCase):
    def setUp(self):
        self.system = MockMediaSystem()
        self.adapter = MediaIntelligenceAdapter(
            retrieval_fn=self.system.retrieve,
            play_fn=self.system.play,
            pending_action_fn=lambda q: None
        )

    def test_fifa_continuity(self):
        # 1. FIFA -> latest standings
        res1 = self.adapter.handle("FIFA World Cup 2026 latest updates")
        self.assertEqual(res1.subject, "FIFA World Cup")
        
        res2 = self.adapter.handle("Latest standings")
        self.assertEqual(res2.subject, "FIFA World Cup")
        self.assertIn("Canada", res2.response_text)
        
        # 2. FIFA -> latest results
        res3 = self.adapter.handle("Latest results")
        self.assertEqual(res3.subject, "FIFA World Cup")
        
        # 3. FIFA -> latest highlights
        res4 = self.adapter.handle("Latest highlights")
        self.assertEqual(res4.subject, "FIFA World Cup")
        
        # 4. FIFA -> who is leading the group
        res5 = self.adapter.handle("Who is leading the group?")
        self.assertEqual(res5.subject, "FIFA World Cup")
        self.assertIn("Canada", res5.response_text)

    def test_interstellar_queries(self):
        # 5. Interstellar -> show soundtrack
        self.adapter.handle("Interstellar")
        res1 = self.adapter.handle("Show soundtrack")
        self.assertEqual(res1.subject, "Interstellar")
        
        # 6. Interstellar -> who composed it?
        res2 = self.adapter.handle("Who composed it?")
        self.assertEqual(res2.subject, "Interstellar")
        self.assertIn("Hans Zimmer", res2.response_text)
        
        # 7. Interstellar -> show composer interview
        res3 = self.adapter.handle("Show composer interview")
        self.assertEqual(res3.subject, "Interstellar")

    def test_atomic_habits(self):
        # 8. Atomic Habits -> audiobook -> author interview
        self.adapter.handle("Atomic Habits")
        res1 = self.adapter.handle("Play audiobook")
        self.assertEqual(res1.subject, "Atomic Habits")
        
        res2 = self.adapter.handle("Show author interview")
        self.assertEqual(res2.subject, "Atomic Habits")
        self.assertIn("James Clear", res2.response_text)

    def test_gta_vi_gameplay(self):
        # 9. GTA VI -> gameplay
        self.adapter.handle("GTA VI")
        res1 = self.adapter.handle("Show gameplay")
        self.assertEqual(res1.subject, "Gta Vi")
        self.assertIn("Vice City", res1.response_text)

    def test_cross_domain_switch(self):
        # 10. Believer -> Interstellar -> Who directed it?
        self.adapter.handle("Believer")
        self.adapter.handle("Interstellar")
        res = self.adapter.handle("Who directed it?")
        self.assertEqual(res.subject, "Interstellar")
        self.assertIn("Nolan", res.response_text)
        
        # 11. Interstellar -> FIFA -> Latest standings
        self.adapter.handle("FIFA World Cup 2026")
        res2 = self.adapter.handle("Latest standings")
        self.assertEqual(res2.subject, "FIFA World Cup")

    def test_entity_preservation_after_artifact(self):
        # 12. Entity preservation after artifact execution
        self.adapter.handle("Interstellar")
        self.adapter.handle("Show trailer")
        res = self.adapter.handle("Who directed it?")
        self.assertEqual(res.subject, "Interstellar")

if __name__ == "__main__":
    unittest.main()
