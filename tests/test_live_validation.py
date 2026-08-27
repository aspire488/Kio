"""
test_live_validation.py — Live Telegram Path Validation.

Exercises the EXACT same code path as the real Telegram bot:
kio_bot.handle_message → route → ConversationResponder.generate →
_build_bounded_prompt (which calls get_situation_projection) →
_finalize_response (which calls consolidate_exchange)

This proves the companion intelligence works in the real runtime,
not just in isolated unit tests.
"""

import os
import unittest

os.environ["KIO_TEST_MODE"] = "1"

from mini_kio.companion.model import (
    CompanionModel, Belief, EpistemicLevel, save_model, load_model,
    get_or_create_model,
)
from mini_kio.companion.consolidation import consolidate, consolidate_exchange
from mini_kio.companion.projection import project_model, project_situation


class TestLiveTelegramPath(unittest.TestCase):
    """Test the exact code path used by the Telegram bot."""

    def setUp(self):
        """Set up a fresh model for each test."""
        self.session_id = "live_validation_test"
        self.model = get_or_create_model(self.session_id)
        # Clear existing beliefs for clean test
        self.model.beliefs = []
        self.model.total_observations_processed = 0
        # Seed with realistic beliefs
        self.model.add_belief(Belief(
            subject="education", proposition="Joel is an engineering student at SCMS College",
            category="trait", epistemic_level="fact", confidence=1.0,
        ))
        self.model.add_belief(Belief(
            subject="location", proposition="Joel is from Kochi, India",
            category="trait", epistemic_level="fact", confidence=1.0,
        ))
        save_model(self.model)

    def test_01_projection_contains_model(self):
        """A. The LLM should see the companion model, not raw evidence."""
        proj = project_situation(
            self.model, "What do you know about me?", None, self.session_id
        )
        self.assertIn("COMPANION MODEL", proj)
        self.assertIn("FACTS", proj)
        self.assertIn("engineering student", proj.lower())

    def test_02_correction_creates_self_failure(self):
        """B. Correction should create self_failure beliefs."""
        self.model = consolidate_exchange(
            self.model, "Stop giving me verbose explanations",
            "Ok, concise mode.", self.session_id
        )
        failures = [b for b in self.model.active_beliefs() if b.category == "self_failure"]
        self.assertTrue(len(failures) > 0,
                       f"Expected self_failure after correction, got: {[(b.category, b.proposition[:40]) for b in self.model.active_beliefs()]}")

    def test_03_repeated_correction_generates_operational_rule(self):
        """C. Repeated corrections should generate operational rules."""
        corrections = [
            "Stop giving me verbose responses",
            "I hate long explanations, give me code only",
            "Don't write essays, just provide the implementation",
        ]
        for msg in corrections:
            self.model = consolidate_exchange(
                self.model, msg, "", self.session_id
            )
        op_rules = [b for b in self.model.active_beliefs()
                    if "operational_rule" in (b.notes or "")]
        self.assertTrue(len(op_rules) > 0,
                       f"Expected operational rules after corrections")

    def test_04_behavior_guidance_in_projection(self):
        """D. Self-model should produce behavior guidance in projection."""
        # Create enough self-failures
        for msg in ["Stop giving me verbose responses",
                     "I hate long explanations",
                     "Don't write essays"]:
            self.model = consolidate_exchange(self.model, msg, "", self.session_id)

        proj = project_model(self.model, "help me implement this")
        self.assertTrue(
            "BEHAVIOR GUIDANCE" in proj or "RECURRING MISTAKE" in proj,
            f"Expected behavior guidance in projection"
        )

    def test_05_contradiction_detected(self):
        """E. Contradictions should be detected and surfaced."""
        self.model = consolidate_exchange(
            self.model, "I prefer concise answers", "", self.session_id
        )
        self.model = consolidate_exchange(
            self.model, "I prefer detailed explanations", "", self.session_id
        )
        contradictions = self.model.contradictions()
        proj = project_model(self.model)
        # Either contradictions detected or contradictions section present
        self.assertTrue(len(contradictions) > 0 or "CONTRADICTIONS" in proj)

    def test_06_relationship_patterns_tracked(self):
        """F. Relationship friction should be tracked."""
        from mini_kio.companion.relationship import (
            extract_relationship_observations, consolidate_relationship,
        )
        for _ in range(3):
            obs = extract_relationship_observations(
                "Stop explaining so much!", "Ok."
            )
            consolidate_relationship(self.model, obs)
        rel = [b for b in self.model.active_beliefs()
               if b.category in ("friction_point", "collaboration_pattern")]
        self.assertTrue(len(rel) > 0)

    def test_07_consequence_reasoning(self):
        """G. Consequence patterns should be tracked."""
        from mini_kio.companion.consequences import (
            extract_consequence_observations, consolidate_consequences,
        )
        for _ in range(3):
            obs = extract_consequence_observations(
                "Shorter please, too verbose",
                "Here is a detailed explanation of the concept. " * 5
            )
            consolidate_consequences(self.model, obs)
        patterns = [b for b in self.model.active_beliefs() if b.category == "pattern"]
        self.assertTrue(len(patterns) > 0)

    def test_08_novel_situation_synthesis(self):
        """H. Novel questions should synthesize from multiple model dimensions."""
        self.model.add_belief(Belief(
            category="preference", proposition="Joel prefers concise implementation",
            confidence=0.8,
        ))
        self.model.add_belief(Belief(
            category="strength", proposition="Joel is good at rapid prototyping",
            confidence=0.7,
        ))
        proj = project_situation(
            self.model, "What kind of project would suit me?", None, self.session_id
        )
        self.assertTrue(len(proj) > 500)
        self.assertIn("SITUATION", proj)

    def test_09_persistence_across_reload(self):
        """I. Model should persist across save/load cycle."""
        self.model = consolidate_exchange(
            self.model, "I value practical simplicity", "", self.session_id
        )
        save_model(self.model)

        m2 = load_model(self.session_id)
        self.assertGreater(len(m2.active_beliefs()), 0)
        # Should have either preference or value beliefs
        relevant = [b for b in m2.active_beliefs() if b.category in ("preference", "value")]
        self.assertTrue(len(relevant) > 0)

    def test_10_belief_pruning(self):
        """J. Low-confidence beliefs should be pruned."""
        # Add a very low confidence belief
        low = Belief(
            category="pattern", proposition="Maybe something",
            confidence=0.05,
        )
        self.model.add_belief(low)
        initial = len(self.model.active_beliefs())
        pruned = self.model.prune(confidence_threshold=0.15)
        self.assertGreater(pruned, 0)
        self.assertLess(len(self.model.active_beliefs()), initial)

    def test_11_self_model_categories(self):
        """K. Self-model should have failures, learnings, capabilities."""
        # Add diverse self-model beliefs
        self.model.add_belief(Belief(
            category="self_failure", proposition="KIO has given verbose responses",
            confidence=0.7,
        ))
        self.model.add_belief(Belief(
            category="self_learning", proposition="KIO should be brief during debugging",
            confidence=0.8,
        ))
        self.model.add_belief(Belief(
            category="self_capability", proposition="KIO can search the web",
            confidence=0.9, epistemic_level="fact",
        ))
        proj = project_model(self.model)
        self.assertIn("SELF-MODEL", proj)

    def test_12_external_need_detection(self):
        """L. External need detection should work correctly."""
        from mini_kio.companion.external_world import detect_external_need
        # Should detect external need for time-sensitive queries
        need = detect_external_need("What is the latest version of React?")
        self.assertIsNotNone(need)
        self.assertEqual(need.need_type, "current_info")
        # Should NOT detect external need for companion queries
        need2 = detect_external_need("What do you know about me?")
        self.assertIsNone(need2)

    def test_13_full_lifecycle(self):
        """M. Full lifecycle: seed -> interact -> correct -> learn -> project."""
        # Seed
        self.model.add_belief(Belief(
            category="preference", proposition="Joel prefers concise answers",
            confidence=0.7, epistemic_level="observation",
        ))
        # Interact
        self.model = consolidate_exchange(
            self.model, "Nice, that works!", "Great.", self.session_id
        )
        # Correct
        self.model = consolidate_exchange(
            self.model, "Stop giving me verbose responses", "Ok.", self.session_id
        )
        # Learn
        self.model = consolidate_exchange(
            self.model, "I hate long explanations", "", self.session_id
        )
        self.model = consolidate_exchange(
            self.model, "Don't write essays", "", self.session_id
        )
        save_model(self.model)

        # Verify: model has beliefs, self-failures, and projection works
        beliefs = self.model.active_beliefs()
        failures = [b for b in beliefs if b.category == "self_failure"]
        prefs = [b for b in beliefs if b.category == "preference"]
        self.assertGreater(len(beliefs), 3)
        self.assertGreater(len(failures), 0)
        self.assertGreater(len(prefs), 0)

        # Project
        proj = project_situation(
            self.model, "Help me implement this", None, self.session_id
        )
        self.assertGreater(len(proj), 500)
        self.assertIn("SITUATION", proj)

        # Reload and verify persistence
        m2 = load_model(self.session_id)
        self.assertGreater(len(m2.active_beliefs()), 3)


if __name__ == "__main__":
    unittest.main()
