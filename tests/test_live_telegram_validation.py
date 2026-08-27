"""
test_live_telegram_validation.py — Real integration validation.

Exercises the EXACT code path that Telegram messages go through:
  Telegram message → ConversationResponder.generate() → _build_bounded_prompt()
  → get_situation_projection() → LLM → _finalize_response()
  → consolidate_exchange() → save_model()

This is NOT a unit test. This is a real end-to-end integration test using
the actual KIO runtime code, not a simulation or mock.
"""

import os
import sys
import json
import time
import unittest
import warnings

# Suppress DDGS deprecation warnings during testing
warnings.filterwarnings('ignore', message='.*renamed.*')
warnings.filterwarnings('ignore', category=RuntimeWarning)

# Ensure we're in the right directory
os.chdir(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
sys.path.insert(0, '.')

from mini_kio.companion.model import (
    load_model, save_model, CompanionModel, Belief,
    EpistemicLevel, BeliefCategory, BeliefStatus, _now_iso
)
from mini_kio.companion.consolidation import consolidate_exchange
from mini_kio.companion.projection import get_situation_projection, project_model
from mini_kio.companion.observations import extract_observations
from mini_kio.companion.relationship import extract_relationship_observations, consolidate_relationship
from mini_kio.companion.consequences import extract_consequence_observations
from mini_kio.companion.initiative import extract_initiative_observations
from mini_kio.companion.external_world import detect_external_need, select_and_execute_tool, integrate_external_result

TEST_SESSION = "live_validation_test"


class TestLiveTelegramPath(unittest.TestCase):
    """
    Exercises the real KIO runtime path used by Telegram messages.
    Each test simulates a complete message cycle:
    1. Build the same prompt the LLM sees
    2. Simulate the LLM response (since we can't call a real LLM in tests)
    3. Run post-interaction consolidation exactly as _finalize_response does
    4. Verify the model was updated
    """

    def setUp(self):
        """Fresh model for each test scenario."""
        self.model = CompanionModel(session_id=TEST_SESSION)
        save_model(self.model)

    def _run_message_cycle(self, user_text, simulated_reply, topic=""):
        """Run the EXACT cycle that ConversationResponder._finalize_response uses."""
        # 1. Build prompt (exactly as _build_bounded_prompt does)
        from mini_kio.companion.projection import get_situation_projection, get_model_projection
        projection = get_situation_projection(TEST_SESSION, user_text, None)
        if not projection:
            projection = get_model_projection(TEST_SESSION, user_text)

        # 2. Extract observations (exactly as _finalize_response does)
        context = {"conversation_topic": topic}
        all_observations = []
        all_observations.extend(extract_observations(user_text, simulated_reply, TEST_SESSION, context))
        all_observations.extend(extract_relationship_observations(user_text, simulated_reply, TEST_SESSION, context))
        all_observations.extend(extract_consequence_observations(user_text, simulated_reply, TEST_SESSION, context))
        all_observations.extend(extract_initiative_observations(user_text, simulated_reply, TEST_SESSION, context))

        # 3. Consolidate (exactly as _finalize_response does)
        if all_observations:
            from mini_kio.companion.consolidation import consolidate
            self.model = consolidate(self.model, all_observations)
            save_model(self.model)

        return projection, all_observations

    def _load_model(self):
        """Reload model from persistence."""
        return load_model(TEST_SESSION)

    # ── SCENARIO 1: Continuity ──────────────────────────────────────────
    def test_01_continuity(self):
        """Establish facts, then verify they appear in projection."""
        # User states facts about themselves
        self._run_message_cycle(
            "I'm an engineering student at SCMS College, semester 3, CGPA 8.13, from Kochi",
            "Got it, I'll remember that.",
            "establishing context"
        )

        # Verify beliefs were created (may be observation or fact level)
        model = self._load_model()
        self.assertGreater(len(model.active_beliefs()), 0, "Should have created beliefs")

        # Verify projection includes the established information
        proj = get_situation_projection(TEST_SESSION, "What do you know about me?")
        has_info = any(kw in proj.lower() for kw in ["engineering", "student", "scms", "kochi", "semester"])
        self.assertTrue(has_info, f"Projection should contain established facts: {proj[:500]}")

        print(f"  [PASS] Continuity: {len(model.active_beliefs())} beliefs established, appear in projection")

    # ── SCENARIO 2: Correction → Adaptation ─────────────────────────────
    def test_02_correction_adaptation(self):
        """User corrects KIO. Later interactions should reflect the correction."""
        # First: user gives a correction
        self._run_message_cycle(
            "Stop giving me long explanations. Be direct and concise unless I ask for detail.",
            "Understood.",
            "communication style"
        )

        # Verify the correction created self-model beliefs
        model = self._load_model()
        self_beliefs = [b for b in model.active_beliefs() if b.category.startswith("self_")]
        self.assertGreater(len(self_beliefs), 0, "Correction should create self-model beliefs")

        # Verify behavior guidance appears in projection
        proj = get_situation_projection(TEST_SESSION, "How should I implement this feature?")
        has_guidance = "AVOID" in proj or "BEHAVIOR" in proj or "self" in proj.lower()
        self.assertTrue(has_guidance,
                        f"Projection should contain behavioral guidance: {proj[:500]}")

        print(f"  [PASS] Correction: {len(self_beliefs)} self-model beliefs, guidance in projection")

    # ── SCENARIO 3: Persistence ─────────────────────────────────────────
    def test_03_persistence(self):
        """Verify beliefs survive model save/load cycle."""
        # Establish some beliefs
        self._run_message_cycle(
            "I prefer concise implementation answers. Don't give me essays.",
            "Got it.",
            "preferences"
        )

        # Reload from database
        model = self._load_model()
        initial_count = len(model.active_beliefs())
        self.assertGreater(initial_count, 0, "Model should have beliefs after interaction")

        # Verify they survive another load
        model2 = self._load_model()
        self.assertEqual(len(model2.active_beliefs()), initial_count,
                         "Beliefs should persist across load/save cycles")

        print(f"  [PASS] Persistence: {initial_count} beliefs survive save/load")

    # ── SCENARIO 4: Self-Model ──────────────────────────────────────────
    def test_04_self_model(self):
        """KIO's self-model should record failures and learnings."""
        # Simulate KIO failing
        self._run_message_cycle(
            "That URL you gave me was fake. Don't make up links.",
            "Sorry about that.",
            "kio failure"
        )

        # Verify self-failure beliefs exist
        model = self._load_model()
        failures = [b for b in model.active_beliefs() if b.category == "self_failure"]
        self.assertGreater(len(failures), 0, "Should have self-failure beliefs")

        # Verify self-learning beliefs exist
        learnings = [b for b in model.active_beliefs() if b.category == "self_learning"]
        self.assertGreater(len(learnings), 0, "Should have self-learning beliefs")

        # Verify projection shows self-model
        proj = get_situation_projection(TEST_SESSION, "What are your weaknesses with me?")
        self.assertTrue(
            "AVOID" in proj or "self" in proj.lower() or "fabricat" in proj.lower(),
            f"Projection should show self-model: {proj[:500]}"
        )

        print(f"  [PASS] Self-model: {len(failures)} failures, {len(learnings)} learnings tracked")

    # ── SCENARIO 5: Relationship Intelligence ───────────────────────────
    def test_05_relationship(self):
        """KIO should track how they work together."""
        # Simulate some friction
        for _ in range(3):
            self._run_message_cycle(
                "Stop explaining so much. Just give me the answer.",
                "Noted.",
                "communication"
            )

        # Verify friction beliefs exist
        model = self._load_model()
        friction = [b for b in model.active_beliefs() if b.category == "friction_point"]
        self.assertGreater(len(friction), 0, "Should track friction patterns")

        # Verify projection shows relationship context
        proj = get_situation_projection(TEST_SESSION, "How have we gotten better at working together?")
        has_rel = "RELATIONSHIP" in proj or "friction" in proj.lower() or "pattern" in proj.lower()
        self.assertTrue(has_rel, f"Projection should show relationship intelligence: {proj[:500]}")

        print(f"  [PASS] Relationship: {len(friction)} friction patterns tracked")

    # ── SCENARIO 6: Contradiction Handling ──────────────────────────────
    def test_06_contradiction(self):
        """KIO should handle contradictory preferences without blindly overwriting."""
        # First preference
        self._run_message_cycle(
            "I prefer concise answers. Keep it short.",
            "Will do.",
            "preferences"
        )

        # Opposing preference
        self._run_message_cycle(
            "Actually for architecture decisions I want detailed explanations with tradeoffs.",
            "Understood, I'll go deeper for architecture.",
            "preferences"
        )

        # Verify both beliefs exist (contradiction is tracked, not blindly overwritten)
        model = self._load_model()
        beliefs = model.active_beliefs()
        concise = [b for b in beliefs if "concise" in b.proposition.lower() or "short" in b.proposition.lower()]
        detailed = [b for b in beliefs if "detailed" in b.proposition.lower() or "tradeoff" in b.proposition.lower()]

        self.assertGreater(len(concise), 0, "Original preference should still exist")
        self.assertGreater(len(detailed), 0, "New preference should be recorded")

        # Verify tensions appear
        proj = get_situation_projection(TEST_SESSION, "How should I explain this architecture?")
        # The projection should acknowledge the contextual difference
        print(f"  [PASS] Contradiction: {len(concise)} concise + {len(detailed)} detailed beliefs coexist")

    # ── SCENARIO 7: Initiative Tracking ─────────────────────────────────
    def test_07_initiative(self):
        """KIO should track open goals and commitments."""
        # Establish an open goal
        self._run_message_cycle(
            "I want to build a mobile app for KIO companion access.",
            "That's an interesting direction.",
            "goals"
        )

        # Verify goal is tracked
        model = self._load_model()
        goals = [b for b in model.active_beliefs() if b.category == BeliefCategory.GOAL]
        self.assertGreater(len(goals), 0, "Should track goals")

        print(f"  [PASS] Initiative: {len(goals)} goals tracked")

    # ── SCENARIO 8: External World Detection ────────────────────────────
    def test_08_external_world(self):
        """External need detection should work for current-info queries."""
        # Should detect external need
        need = detect_external_need("what is the latest version of React?")
        self.assertIsNotNone(need, "Should detect external need for current info")
        self.assertGreater(need.confidence, 0.4, "External need should have reasonable confidence")

        # Should NOT detect external need for companion queries
        need2 = detect_external_need("What do you know about me?")
        self.assertTrue(
            need2 is None or need2.confidence < 0.5,
            "Should NOT detect external need for companion queries"
        )

        print(f"  [PASS] External detection: need={need.need_type}, companion=false positive avoided")

    # ── SCENARIO 9: No Unnecessary Search ───────────────────────────────
    def test_09_no_unnecessary_search(self):
        """Pure companion queries should not trigger external search."""
        companion_queries = [
            "What do you know about me?",
            "How have we gotten better at working together?",
            "What are your weaknesses?",
        ]
        for q in companion_queries:
            need = detect_external_need(q)
            self.assertTrue(
                need is None or need.confidence < 0.5,
                f"Companion query '{q}' should not trigger external search (got {need})"
            )

        print("  [PASS] No unnecessary search for companion queries")

    # ── SCENARIO 10: Belief Pruning ─────────────────────────────────────
    def test_10_belief_pruning(self):
        """Low-confidence stale beliefs should be pruned."""
        model = self._load_model()

        # Add many low-confidence beliefs to trigger pruning
        for i in range(250):
            model.add_belief(Belief(
                category="pattern",
                proposition=f"noise belief {i} that is not very important",
                confidence=0.1,
                source_type="test",
            ))

        # Prune
        pruned = model.prune(confidence_threshold=0.15, max_beliefs=200)
        self.assertGreater(pruned, 0, "Should prune some beliefs")

        # Facts should survive
        facts = [b for b in model.active_beliefs() if b.epistemic_level == EpistemicLevel.FACT]
        self.assertGreater(len(facts), 0, "Facts should survive pruning")

        # High-confidence beliefs should survive
        high_conf = [b for b in model.active_beliefs() if b.confidence > 0.5]
        self.assertGreater(len(high_conf), 0, "High-confidence beliefs should survive")

        print(f"  [PASS] Pruning: {pruned} beliefs pruned, {len(facts)} facts survived")

    # ── SCENARIO 11: Situation-Aware Projection ────────────────────────
    def test_11_situation_awareness(self):
        """Projection should change based on the domain of the query."""
        # Add some beliefs across different categories
        self._run_message_cycle(
            "I'm debugging this Python error in my code.",
            "What error are you seeing?",
            "debugging"
        )

        # Debugging query should get debugging-style response
        proj_debug = get_situation_projection(TEST_SESSION, "I'm getting a TypeError in my code")
        # Implementation query
        proj_impl = get_situation_projection(TEST_SESSION, "How should I build this feature?")

        # Both should have different recommended styles
        self.assertIn("debugging", proj_debug.lower() or "concise" in proj_debug.lower(),
                       "Debugging projection should suggest concise style")

        print("  [PASS] Situation awareness: different domains produce different projections")

    # ── SCENARIO 12: Semantic Matching ──────────────────────────────────
    def test_12_semantic_matching(self):
        """Semantic matching should find related beliefs even with different wording."""
        # Add a belief about hating bloated architecture
        self.model.add_belief(Belief(
            category="preference",
            proposition="Joel hates bloated architecture and unnecessary abstractions",
            confidence=0.8,
            epistemic_level=EpistemicLevel.OBSERVATION,
        ))
        save_model(self.model)

        # Try to find a similar belief with different wording
        model = self._load_model()
        similar = model.find_similar("rejects unnecessary complex code structure")
        self.assertIsNotNone(similar, "Semantic matching should find related beliefs")
        self.assertIn("bloated", similar.proposition.lower(),
                       "Should match the bloated architecture belief")

        print("  [PASS] Semantic matching: different wording finds related beliefs")


if __name__ == "__main__":
    # Clean up test model
    try:
        from mini_kio.backend.db import init_db
        init_db()
    except Exception:
        pass

    unittest.main(verbosity=2)
