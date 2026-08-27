"""
test_companion_intelligence.py — Behavioral tests for the Companion Intelligence Layer.

These tests verify that KIO can:
1. Accumulate understanding from interactions
2. Distinguish facts from observations from inferences
3. Handle contradictions
4. Evolve beliefs through reinforcement
5. Project a coherent model for LLM reasoning
6. Track self-model (failures, learnings)
7. Handle temporal questions
8. Answer novel situations from the model
"""

import os
import unittest

os.environ["KIO_TEST_MODE"] = "1"

from mini_kio.companion.model import (
    CompanionModel, Belief, EpistemicLevel, TemporalScope,
    BeliefCategory, BeliefStatus,
)
from mini_kio.companion.observations import extract_observations
from mini_kio.companion.consolidation import consolidate, consolidate_exchange
from mini_kio.companion.projection import project_model, _find_situation_relevant


class TestBeliefStructure(unittest.TestCase):
    """Test that beliefs have proper structure and epistemic levels."""

    def test_belief_creation(self):
        b = Belief(
            subject="preference",
            proposition="Joel prefers concise answers",
            category=BeliefCategory.PREFERENCE,
            epistemic_level=EpistemicLevel.OBSERVATION,
            confidence=0.7,
        )
        self.assertEqual(b.epistemic_level, EpistemicLevel.OBSERVATION)
        self.assertEqual(b.confidence, 0.7)
        self.assertEqual(b.status, BeliefStatus.ACTIVE)
        self.assertTrue(b.is_current)

    def test_belief_epistemic_levels(self):
        for level in EpistemicLevel:
            b = Belief(epistemic_level=level.value)
            self.assertEqual(b.epistemic_level, level.value)

    def test_belief_reinforcement(self):
        b = Belief(confidence=0.5)
        b.reinforce(0.1)
        self.assertAlmostEqual(b.confidence, 0.6, places=1)
        b.reinforce(0.5)
        self.assertAlmostEqual(b.confidence, 1.0, places=1)

    def test_belief_weakening(self):
        b = Belief(confidence=0.8)
        b.weaken(0.3)
        self.assertAlmostEqual(b.confidence, 0.5, places=1)

    def test_belief_supersession(self):
        old = Belief(id="old1", status=BeliefStatus.ACTIVE)
        old.supersede("new1")
        self.assertEqual(old.status, BeliefStatus.SUPERSEDED)
        self.assertEqual(old.superseded_by, "new1")
        self.assertEqual(old.temporal_scope, TemporalScope.HISTORICAL)

    def test_belief_serialization(self):
        b = Belief(
            subject="test",
            proposition="test proposition",
            category=BeliefCategory.TRAIT,
            epistemic_level=EpistemicLevel.FACT,
            confidence=0.9,
        )
        d = b.to_dict()
        b2 = Belief.from_dict(d)
        self.assertEqual(b2.subject, "test")
        self.assertEqual(b2.epistemic_level, EpistemicLevel.FACT)
        self.assertAlmostEqual(b2.confidence, 0.9, places=1)


class TestCompanionModel(unittest.TestCase):
    """Test model operations."""

    def test_model_creation(self):
        m = CompanionModel(session_id="test")
        self.assertEqual(len(m.beliefs), 0)
        self.assertEqual(m.active_beliefs(), [])

    def test_add_and_query_beliefs(self):
        m = CompanionModel(session_id="test")
        b1 = Belief(category="preference", proposition="likes concise", confidence=0.8)
        b2 = Belief(category="goal", proposition="building KIO", confidence=0.9)
        m.add_belief(b1)
        m.add_belief(b2)
        self.assertEqual(len(m.active_beliefs()), 2)
        self.assertEqual(len(m.active_beliefs(category="preference")), 1)

    def test_find_similar(self):
        m = CompanionModel(session_id="test")
        m.add_belief(Belief(proposition="Joel prefers concise answers when debugging"))
        found = m.find_similar("Joel prefers short responses during debugging")
        self.assertIsNotNone(found)

    def test_supersede_belief(self):
        m = CompanionModel(session_id="test")
        old = Belief(id="old1", proposition="prefers Vue")
        m.add_belief(old)
        new = Belief(proposition="prefers React")
        m.replace_belief("old1", new)
        self.assertEqual(old.status, BeliefStatus.SUPERSEDED)
        self.assertIn(old.id, [b.supersedes for b in m.active_beliefs() if b.supersedes])

    def test_stats(self):
        m = CompanionModel(session_id="test")
        m.add_belief(Belief(epistemic_level="fact", confidence=0.9))
        m.add_belief(Belief(epistemic_level="observation", confidence=0.7))
        stats = m.stats()
        self.assertEqual(stats["active_beliefs"], 2)
        self.assertIn("fact", stats["by_epistemic"])


class TestObservationExtraction(unittest.TestCase):
    """Test that observations are extracted from interactions."""

    def test_correction_extraction(self):
        obs = extract_observations("No, wrong, that's not what I meant", "Sorry, let me fix that.")
        self.assertTrue(any(o.category == "self_failure" for o in obs))

    def test_approval_extraction(self):
        obs = extract_observations("Nice, that works perfectly", "Great!")
        self.assertTrue(any(o.source == "approval" for o in obs))

    def test_preference_extraction(self):
        obs = extract_observations("I prefer concise answers", "")
        self.assertTrue(any(o.category == "preference" for o in obs))

    def test_frustration_extraction(self):
        obs = extract_observations("This is broken and doesn't work, ugh", "")
        self.assertTrue(any(o.category == "emotional" for o in obs))

    def test_goal_extraction(self):
        obs = extract_observations("I want to build a mobile app", "")
        self.assertTrue(any(o.category == "goal" for o in obs))

    def test_brevity_observation(self):
        # Behavioral observations (message length) are intentionally not extracted
        # as standalone observations to prevent noise beliefs. Only meaningful
        # signals (corrections, preferences, goals) generate observations.
        # This test verifies that short messages don't create noise observations.
        obs = extract_observations("ok", "Sure.")
        behavioral = [o for o in obs if o.source == "behavioral"]
        self.assertEqual(len(behavioral), 0, "Short messages should not create behavioral noise observations")


class TestConsolidation(unittest.TestCase):
    """Test the consolidation engine."""

    def test_reinforcement(self):
        m = CompanionModel(session_id="test")
        for _ in range(3):
            m = consolidate_exchange(m, "I prefer concise answers", "", "test")
        beliefs = m.active_beliefs()
        self.assertTrue(len(beliefs) >= 1)
        # Confidence should increase with reinforcement
        self.assertGreater(beliefs[0].confidence, 0.5)

    def test_contradiction_creates_new_belief(self):
        m = CompanionModel(session_id="test")
        m = consolidate_exchange(m, "I prefer concise answers", "", "test")
        initial_count = len(m.active_beliefs())
        m = consolidate_exchange(m, "I prefer detailed explanations", "", "test")
        # Should have more beliefs after contradiction
        self.assertGreater(len(m.active_beliefs()), initial_count)

    def test_correction_updates_self_model(self):
        m = CompanionModel(session_id="test")
        m = consolidate_exchange(m, "Stop giving me essays, just give me the commands", "", "test")
        self_beliefs = [b for b in m.active_beliefs() if b.category.startswith("self_")]
        self.assertTrue(len(self_beliefs) > 0)

    def test_multiple_observations_build_pattern(self):
        m = CompanionModel(session_id="test")
        for _ in range(5):
            m = consolidate_exchange(m, "Can you just give me the code, not explanations?", "", "test")
        # Should have self-learning belief about communication preference
        self_beliefs = [b for b in m.active_beliefs() 
                       if b.category in ("self_learning", "communication")]
        self.assertTrue(len(self_beliefs) > 0)


class TestProjection(unittest.TestCase):
    """Test model projection for LLM consumption."""

    def test_empty_model_projection(self):
        m = CompanionModel(session_id="test")
        proj = project_model(m)
        self.assertEqual(proj, "")

    def test_projection_epistemic_markers(self):
        m = CompanionModel(session_id="test")
        m.add_belief(Belief(
            epistemic_level="fact",
            proposition="Joel is an engineering student",
            confidence=1.0,
        ))
        m.add_belief(Belief(
            epistemic_level="observation",
            proposition="Joel prefers concise answers",
            confidence=0.8,
        ))
        proj = project_model(m)
        self.assertIn("[fact]", proj)
        self.assertIn("[observation]", proj)

    def test_projection_confidence_values(self):
        m = CompanionModel(session_id="test")
        m.add_belief(Belief(proposition="test", confidence=0.75))
        proj = project_model(m)
        self.assertIn("0.75", proj)

    def test_projection_contradictions(self):
        m = CompanionModel(session_id="test")
        b1 = Belief(id="b1", proposition="prefers concise", category="preference")
        b2 = Belief(id="b2", proposition="prefers detailed", category="preference")
        b1.contradictory_observations = ["b2"]
        b2.contradictory_observations = ["b1"]
        m.add_belief(b1)
        m.add_belief(b2)
        proj = project_model(m)
        self.assertIn("CONTRADICTIONS", proj)


class TestTemporalModel(unittest.TestCase):
    """Test temporal reasoning."""

    def test_historical_beliefs(self):
        m = CompanionModel(session_id="test")
        old = Belief(id="old1", proposition="used to prefer Vue", temporal_scope="historical")
        old.status = BeliefStatus.SUPERSEDED
        new = Belief(id="new1", proposition="now prefers React", temporal_scope="evolving")
        m.add_belief(old)
        m.add_belief(new)
        historical = m.historical_beliefs()
        self.assertEqual(len(historical), 1)
        self.assertIn("Vue", historical[0].proposition)


class TestSelfModel(unittest.TestCase):
    """Test KIO's self-model."""

    def test_failure_recorded(self):
        m = CompanionModel(session_id="test")
        m = consolidate_exchange(m, "That URL you gave me was fabricated!", "", "test")
        self_failures = [b for b in m.active_beliefs() if b.category == "self_failure"]
        self.assertTrue(len(self_failures) > 0)

    def test_learning_recorded(self):
        m = CompanionModel(session_id="test")
        m = consolidate_exchange(m, "Stop fabricating URLs", "", "test")
        self_learnings = [b for b in m.active_beliefs() if b.category == "self_learning"]
        self.assertTrue(len(self_learnings) > 0)


class TestNovelSituation(unittest.TestCase):
    """Test that the model can support novel situation reasoning."""

    def test_situation_relevant_beliefs(self):
        m = CompanionModel(session_id="test")
        m.add_belief(Belief(category="preference", proposition="Joel prefers concise implementation"))
        m.add_belief(Belief(category="strength", proposition="Joel is good at rapid prototyping"))
        m.add_belief(Belief(category="weakness", proposition="Joel sometimes skips testing"))
        
        # Query with actual word overlap should find matching beliefs
        relevant = _find_situation_relevant(m, "I prefer concise implementation for this project")
        self.assertTrue(len(relevant) > 0)
        
        # Query with intent boost for project/goal should find project beliefs
        m2 = CompanionModel(session_id="test2")
        m2.add_belief(Belief(category="goal", proposition="Joel wants to build a mobile app"))
        relevant2 = _find_situation_relevant(m2, "thinking about building a mobile app")
        self.assertTrue(len(relevant2) > 0)

    def test_multi_dimensional_projection(self):
        m = CompanionModel(session_id="test")
        m.add_belief(Belief(
            category="trait", epistemic_level="fact",
            proposition="Joel is an engineering student", confidence=1.0))
        m.add_belief(Belief(
            category="preference", epistemic_level="observation",
            proposition="Joel prefers concise implementation", confidence=0.8))
        m.add_belief(Belief(
            category="self_failure", epistemic_level="observation",
            proposition="KIO has over-engineered solutions before", confidence=0.7))
        
        proj = project_model(m, "how should I approach this architecture?")
        self.assertIn("engineering student", proj)
        self.assertIn("concise implementation", proj)
        self.assertIn("over-engineered", proj)


if __name__ == "__main__":
    unittest.main()
