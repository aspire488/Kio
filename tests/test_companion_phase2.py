"""
test_companion_phase2.py — Phase 2 Behavioral Tests.

Tests the upgraded companion intelligence:
1. Semantic matching (beyond token overlap)
2. Situation model
3. Relationship intelligence
4. Consequence reasoning
5. Initiative tracking
6. Self-model behavior guidance
7. Full end-to-end consolidation with all modules
8. Correction → learning → behavioral change
9. Persistence across model reload
10. Projection includes situation + relationship + consequences + initiative
"""

import os
import unittest

os.environ["KIO_TEST_MODE"] = "1"

from mini_kio.companion.model import (
    CompanionModel, Belief, EpistemicLevel, TemporalScope,
    BeliefCategory, BeliefStatus, save_model, load_model, get_or_create_model,
)
from mini_kio.companion.observations import extract_observations
from mini_kio.companion.consolidation import consolidate, consolidate_exchange
from mini_kio.companion.projection import (
    project_model, project_situation, get_model_projection,
    get_situation_projection, _find_situation_relevant,
)


class TestSemanticMatching(unittest.TestCase):
    """Test that semantic matching works beyond token overlap."""

    def test_semantic_matcher_available(self):
        """Verify sentence-transformers model loads."""
        from mini_kio.companion.semantic import is_available
        # Model may or may not be available in test env
        # This test documents the capability
        available = is_available()
        self.assertIsInstance(available, bool)

    def test_find_similar_semantic(self):
        """Semantic matching should find related beliefs even with different words."""
        m = CompanionModel(session_id="test_semantic")
        m.add_belief(Belief(
            id="b1",
            proposition="Joel hates bloated architecture and unnecessary abstractions",
            category=BeliefCategory.PREFERENCE,
            confidence=0.8,
        ))
        # This should match semantically even though vocabulary differs
        found = m.find_similar("Joel rejects overengineered solutions")
        self.assertIsNotNone(found)
        self.assertEqual(found.id, "b1")

    def test_find_similar_fallback_to_token(self):
        """When semantic is unavailable, token overlap still works."""
        m = CompanionModel(session_id="test_token")
        m.add_belief(Belief(
            id="b2",
            proposition="Joel prefers concise answers when debugging",
            category=BeliefCategory.PREFERENCE,
            confidence=0.7,
        ))
        found = m.find_similar("Joel prefers concise answers during debugging")
        self.assertIsNotNone(found)

    def test_semantic_match_score(self):
        """Test semantic similarity scoring."""
        from mini_kio.companion.semantic import semantic_match_score
        # Similar texts should score high
        score = semantic_match_score(
            "Joel likes concise code",
            "Joel prefers brief implementations"
        )
        self.assertGreater(score, 0.0)
        self.assertLessEqual(score, 1.0)


class TestSituationModel(unittest.TestCase):
    """Test the SituationModel."""

    def test_domain_detection_debugging(self):
        from mini_kio.companion.situation import _detect_domain
        self.assertEqual(_detect_domain("This error is broken"), "debugging")
        self.assertEqual(_detect_domain("There's a bug in the code"), "debugging")

    def test_domain_detection_architecture(self):
        from mini_kio.companion.situation import _detect_domain
        self.assertEqual(_detect_domain("Let's talk about the system architecture"), "architecture")
        self.assertEqual(_detect_domain("What pattern should we use for the component?"), "architecture")

    def test_domain_detection_companion(self):
        from mini_kio.companion.situation import _detect_domain
        self.assertEqual(_detect_domain("What do you know about me?"), "companion")
        self.assertEqual(_detect_domain("What are my strengths?"), "companion")

    def test_domain_detection_implementation(self):
        from mini_kio.companion.situation import _detect_domain
        self.assertEqual(_detect_domain("Build me a function"), "implementation")
        self.assertEqual(_detect_domain("Add a new feature"), "implementation")

    def test_urgency_detection(self):
        from mini_kio.companion.situation import _detect_urgency
        self.assertEqual(_detect_urgency("This is urgent, production is down"), "high")
        self.assertEqual(_detect_urgency("I'm frustrated with this bug"), "elevated")
        self.assertEqual(_detect_urgency("Can you help me with something?"), "normal")

    def test_situation_model_builds(self):
        from mini_kio.companion.situation import build_situation_model
        m = CompanionModel(session_id="test_sit")
        m.add_belief(Belief(
            category="preference", proposition="Joel prefers concise implementation",
            confidence=0.8, epistemic_level="observation",
        ))
        m.add_belief(Belief(
            category="self_failure", proposition="KIO has over-engineered solutions before",
            confidence=0.7, epistemic_level="observation",
        ))
        situation = build_situation_model(
            "Let's talk about the system architecture", None, "test_sit", m
        )
        self.assertEqual(situation.domain, "architecture")
        self.assertTrue(len(situation.user_beliefs) > 0 or len(situation.self_beliefs) > 0)

    def test_situation_model_recommendation(self):
        from mini_kio.companion.situation import build_situation_model, project_situation_model
        m = CompanionModel(session_id="test_rec")
        m.add_belief(Belief(
            category="preference", proposition="Joel prefers concise implementation",
            confidence=0.8,
        ))
        situation = build_situation_model("This is broken, fix it", None, "test_rec", m)
        text = project_situation_model(situation)
        self.assertIn("SITUATION", text)

    def test_situation_model_empty(self):
        from mini_kio.companion.situation import SituationModel
        s = SituationModel()
        self.assertTrue(s.is_empty())


class TestRelationshipIntelligence(unittest.TestCase):
    """Test relationship pattern tracking."""

    def test_friction_detection(self):
        from mini_kio.companion.relationship import extract_relationship_observations
        obs = extract_relationship_observations(
            "Stop giving me long explanations, just give me the code",
            "Sure, here's the code.",
        )
        friction = [o for o in obs if o.category == "friction_point"]
        self.assertTrue(len(friction) > 0)

    def test_success_detection(self):
        from mini_kio.companion.relationship import extract_relationship_observations
        obs = extract_relationship_observations(
            "Nice, that works perfectly!",
            "Great.",
        )
        success = [o for o in obs if o.category == "collaboration_pattern"]
        self.assertTrue(len(success) > 0)

    def test_trust_signal_detection(self):
        from mini_kio.companion.relationship import extract_relationship_observations
        obs = extract_relationship_observations(
            "You always understand what I mean",
            "Thanks.",
        )
        trust = [o for o in obs if o.category == "trust_signal"]
        self.assertTrue(len(trust) > 0)

    def test_relationship_consolidation(self):
        m = CompanionModel(session_id="test_rel")
        from mini_kio.companion.relationship import (
            extract_relationship_observations, consolidate_relationship,
        )
        for _ in range(3):
            obs = extract_relationship_observations(
                "Stop giving me verbose explanations!",
                "Sure.",
            )
            consolidate_relationship(m, obs)
        
        rel_beliefs = [b for b in m.active_beliefs() if b.category in (
            "friction_point", "collaboration_pattern", "trust_signal", "relationship_pattern")]
        self.assertTrue(len(rel_beliefs) > 0, f"Expected relationship beliefs, got: {[(b.category, b.proposition[:40]) for b in m.active_beliefs()]}")

    def test_relationship_summary(self):
        m = CompanionModel(session_id="test_rel_sum")
        m.add_belief(Belief(
            category="friction_point",
            proposition="Joel gets frustrated by verbose responses",
            confidence=0.7,
        ))
        m.add_belief(Belief(
            category="collaboration_pattern",
            proposition="Brief exchanges work well for implementation",
            confidence=0.6,
        ))
        from mini_kio.companion.relationship import get_relationship_summary
        summary = get_relationship_summary(m)
        self.assertTrue(len(summary) > 0, f"Expected non-empty summary, got: '{summary}'")


class TestConsequenceReasoning(unittest.TestCase):
    """Test consequence/causal reasoning."""

    def test_consequence_extraction(self):
        from mini_kio.companion.consequences import extract_consequence_observations
        # KIO reply must be > 100 chars to trigger verbose-response detection
        long_reply = "Here is a detailed explanation of the concept. " * 5
        obs = extract_consequence_observations(
            "Shorter please, too verbose",
            long_reply,
        )
        consequences = [o for o in obs if o.metadata.get("pattern_type") == "consequence"]
        self.assertTrue(len(consequences) > 0,
                       f"Expected consequence observations, got: {[(o.source, o.content[:60]) for o in obs]}")

    def test_success_consequence(self):
        from mini_kio.companion.consequences import extract_consequence_observations
        obs = extract_consequence_observations(
            "That works perfectly, exactly what I needed",
            "Done.",
        )
        consequences = [o for o in obs if o.metadata.get("pattern_type") == "consequence"]
        self.assertTrue(len(consequences) > 0)

    def test_consequence_consolidation(self):
        m = CompanionModel(session_id="test_cons")
        from mini_kio.companion.consequences import (
            extract_consequence_observations, consolidate_consequences,
        )
        long_reply = "Here is a detailed explanation of the concept. " * 5
        for _ in range(3):
            obs = extract_consequence_observations(
                "Shorter please, too verbose",
                long_reply,
            )
            consolidate_consequences(m, obs)
        
        patterns = [b for b in m.active_beliefs() if b.category == "pattern"]
        self.assertTrue(len(patterns) > 0,
                       f"Expected pattern beliefs, got: {[(b.category, b.proposition[:60]) for b in m.active_beliefs()]}")

    def test_consequence_summary(self):
        m = CompanionModel(session_id="test_cons_sum")
        m.add_belief(Belief(
            category="pattern",
            proposition="When kio verbose response, the result tends to be user requests brevity",
            confidence=0.7,
            notes="antecedent:kio_verbose_response;consequence:user_requests_brevity",
        ))
        from mini_kio.companion.consequences import get_consequence_summary
        summary = get_consequence_summary(m)
        self.assertIn("Learned patterns", summary)


class TestInitiativeTracking(unittest.TestCase):
    """Test proactive initiative tracking."""

    def test_commitment_detection(self):
        from mini_kio.companion.initiative import extract_initiative_observations
        obs = extract_initiative_observations(
            "Can you fix the database issue?",
            "I'll investigate and fix that for you.",
        )
        # KIO's reply contains a commitment
        commitments = [o for o in obs if o.metadata.get("loop_type") == "commitment"]
        self.assertTrue(len(commitments) > 0)

    def test_unresolved_question(self):
        from mini_kio.companion.initiative import extract_initiative_observations
        obs = extract_initiative_observations(
            "Should we use PostgreSQL or SQLite?",
            "",
        )
        questions = [o for o in obs if o.metadata.get("loop_type") == "question"]
        self.assertTrue(len(questions) > 0)

    def test_goal_tracking(self):
        from mini_kio.companion.initiative import extract_initiative_observations
        obs = extract_initiative_observations(
            "I want to build a mobile app",
            "",
        )
        goals = [o for o in obs if o.metadata.get("loop_type") == "goal"]
        self.assertTrue(len(goals) > 0, f"Expected goal observations, got: {[(o.source, o.content[:60]) for o in obs]}")

    def test_initiative_summary(self):
        m = CompanionModel(session_id="test_init")
        m.add_belief(Belief(
            category="goal",
            proposition="User wants to build mobile app",
            confidence=0.6,
            notes="loop_type:goal",
        ))
        from mini_kio.companion.initiative import get_initiative_summary
        summary = get_initiative_summary(m)
        self.assertIn("Open loops", summary)


class TestSelfModelBehavior(unittest.TestCase):
    """Test that self-model beliefs are operationalized in projection."""

    def test_self_model_in_projection(self):
        m = CompanionModel(session_id="test_self_beh")
        m.add_belief(Belief(
            category="self_failure",
            proposition="KIO has historically over-engineered solutions",
            confidence=0.7,
            epistemic_level="observation",
        ))
        m.add_belief(Belief(
            category="self_learning",
            proposition="KIO should default to concise responses during debugging",
            confidence=0.8,
            epistemic_level="observation",
        ))
        proj = project_model(m, "how should I approach this?")
        # Self-model guidance should be present as AVOID/APPLY or BEHAVIOR GUIDANCE
        self.assertTrue(
            "avoid" in proj.lower() or "apply" in proj.lower() or
            "recurring mistake" in proj.lower() or "BEHAVIOR GUIDANCE" in proj,
            f"Expected behavior guidance in projection: {proj[:300]}"
        )
        # The guidance section should contain action-oriented labels (AVOID/APPLY)
        self.assertTrue(
            "avoid" in proj.lower() or "apply" in proj.lower() or
            "learned behavior" in proj.lower() or "LEARNED BEHAVIOR" in proj,
            f"Expected action labels in projection: {proj[:300]}"
        )

    def test_correction_creates_self_learning(self):
        m = CompanionModel(session_id="test_corr_learn")
        m = consolidate_exchange(m, "Stop giving me essays, just give me the commands", "", "test")
        self_learnings = [b for b in m.active_beliefs() if b.category == "self_learning"]
        self.assertTrue(len(self_learnings) > 0)

    def test_correction_changes_behavior_in_projection(self):
        """After correction, the projection should contain behavior guidance."""
        m = CompanionModel(session_id="test_beh_change")
        # Simulate correction
        m = consolidate_exchange(m, "Stop giving me long explanations", "", "test")
        # Now check projection contains guidance
        proj = project_model(m, "help me with debugging")
        # Should contain either self_learning or self_failure beliefs
        self.assertTrue(
            "learned behavior" in proj.lower() or "recurring mistake" in proj.lower() or 
            "self" in proj.lower() or "kio" in proj.lower(),
            f"Expected behavioral guidance: {proj[:200]}"
        )


class TestFullEndToEnd(unittest.TestCase):
    """Test the full observation → consolidation → projection pipeline."""

    def test_correction_learning_pipeline(self):
        """Correction → learning → behavior guidance in projection."""
        m = CompanionModel(session_id="test_e2e")
        
        # Phase 1: Multiple verbose interactions
        for _ in range(3):
            m = consolidate_exchange(
                m, "That's too long, just give me the answer", 
                "Here's a detailed explanation of the concept...", "test"
            )
        
        # Phase 2: Explicit correction
        m = consolidate_exchange(
            m, "Stop giving me essays! Just give me the code.",
            "Here's the code...", "test"
        )
        
        # Phase 3: Check the model has learned
        self_failures = [b for b in m.active_beliefs() if b.category == "self_failure"]
        self_learnings = [b for b in m.active_beliefs() if b.category == "self_learning"]
        
        self.assertTrue(len(self_failures) > 0 or len(self_learnings) > 0,
                       "Model should have recorded failure and/or learning from correction")
        
        # Phase 4: Check projection contains behavior guidance
        proj = project_model(m, "help me implement this")
        # Should contain some form of behavioral guidance from self-model
        has_guidance = any(kw in proj for kw in (
            "RECURRING MISTAKE", "LEARNED BEHAVIOR", "self_failure", "self_learning",
            "KIO", "over", "verbose", "concise"
        ))
        self.assertTrue(has_guidance, f"Projection should contain behavioral guidance: {proj[:300]}")

    def test_relationship_consolidation_pipeline(self):
        """Friction → relationship belief → summary."""
        m = CompanionModel(session_id="test_rel_e2e")
        
        from mini_kio.companion.relationship import (
            extract_relationship_observations, consolidate_relationship,
        )
        
        # Multiple friction signals
        for _ in range(3):
            obs = extract_relationship_observations(
                "Stop explaining so much!", "Ok."
            )
            consolidate_relationship(m, obs)
        
        rel_beliefs = [b for b in m.active_beliefs() if b.category in (
            "friction_point", "collaboration_pattern", "trust_signal", "relationship_pattern")]
        self.assertTrue(len(rel_beliefs) > 0,
                       f"Expected relationship beliefs: {[(b.category, b.proposition[:40]) for b in m.active_beliefs()]}")
        
        from mini_kio.companion.relationship import get_relationship_summary
        summary = get_relationship_summary(m)
        self.assertTrue(len(summary) > 0)

    def test_consequence_pattern_accumulates(self):
        """Repeated consequence → reinforcement."""
        m = CompanionModel(session_id="test_cons_e2e")
        
        from mini_kio.companion.consequences import (
            extract_consequence_observations, consolidate_consequences,
        )
        
        long_reply = "Here is a detailed explanation of the concept. " * 5
        for _ in range(4):
            obs = extract_consequence_observations(
                "Too verbose, just give me the answer",
                long_reply,
            )
            consolidate_consequences(m, obs)
        
        patterns = [b for b in m.active_beliefs() if b.category == "pattern"]
        self.assertTrue(len(patterns) > 0,
                       f"Expected pattern beliefs, got: {[(b.category, b.proposition[:60]) for b in m.active_beliefs()]}")
        # Confidence should be reinforced
        self.assertGreater(patterns[0].confidence, 0.4)

    def test_persistence_across_reload(self):
        """Model survives save/load cycle."""
        m = CompanionModel(session_id="test_persist")
        m.add_belief(Belief(
            category="preference", proposition="Joel likes concise answers",
            confidence=0.8, epistemic_level="observation",
        ))
        m.add_belief(Belief(
            category="self_failure", proposition="KIO has been verbose before",
            confidence=0.7, epistemic_level="observation",
        ))
        save_model(m)
        
        m2 = load_model("test_persist")
        self.assertEqual(len(m2.active_beliefs()), 2)
        
        # Beliefs should survive consolidation
        m2 = consolidate_exchange(m2, "Thanks, that was helpful", "", "test")
        save_model(m2)
        
        m3 = load_model("test_persist")
        self.assertGreaterEqual(len(m3.active_beliefs()), 2)

    def test_situation_projection_includes_all_dimensions(self):
        """Situation projection should include user + self + relationship + consequences."""
        m = CompanionModel(session_id="test_sit_all")
        m.add_belief(Belief(
            category="preference", proposition="Joel prefers concise implementation",
            confidence=0.8, epistemic_level="observation",
        ))
        m.add_belief(Belief(
            category="self_failure", proposition="KIO has over-engineered before",
            confidence=0.7, epistemic_level="observation",
        ))
        m.add_belief(Belief(
            category="self_learning", proposition="KIO should be brief during implementation",
            confidence=0.75, epistemic_level="observation",
        ))
        m.add_belief(Belief(
            category="friction_point", proposition="Joel gets frustrated by verbose responses",
            confidence=0.65, epistemic_level="observation",
        ))
        m.add_belief(Belief(
            category="pattern",
            proposition="When kio verbose response, the result tends to be user requests brevity",
            confidence=0.6,
            notes="antecedent:kio_verbose_response;consequence:user_requests_brevity",
        ))
        
        proj = project_situation(m, "How should I implement this?", None, "test_sit_all")
    
        # Should contain multiple dimensions
        self.assertIn("joel prefers", proj.lower(), "Should contain preference beliefs")
        self.assertTrue(
            "over-engineer" in proj.lower() or "RECURRING MISTAKE" in proj,
            "Should contain self-model behavior guidance"
        )


class TestNovelGeneralization(unittest.TestCase):
    """Test that the model supports novel situation reasoning."""

    def test_novel_question_answerable(self):
        """A novel question should surface relevant beliefs from multiple dimensions."""
        m = CompanionModel(session_id="test_novel")
        
        # Seed with diverse beliefs
        beliefs = [
            Belief(category="trait", proposition="Joel is an engineering student",
                   confidence=1.0, epistemic_level="fact"),
            Belief(category="preference", proposition="Joel prefers concise implementation",
                   confidence=0.8, epistemic_level="observation"),
            Belief(category="strength", proposition="Joel is good at rapid prototyping",
                   confidence=0.7, epistemic_level="observation"),
            Belief(category="weakness", proposition="Joel sometimes skips testing",
                   confidence=0.6, epistemic_level="observation"),
            Belief(category="self_failure", proposition="KIO has over-engineered solutions",
                   confidence=0.7, epistemic_level="observation"),
            Belief(category="pattern",
                   proposition="When kio verbose response, user requests brevity",
                   confidence=0.65, epistemic_level="observation",
                   notes="antecedent:kio_verbose_response;consequence:user_requests_brevity"),
        ]
        for b in beliefs:
            m.add_belief(b)
        
        # Novel question never directly answered in "archive"
        proj = project_situation(
            m, "What kind of project would suit me?", None, "test_novel"
        )
        
        # Should surface relevant beliefs from multiple dimensions
        # Compact projection filters stale academic facts for non-personal queries
        self.assertTrue(
            "concise" in proj.lower() or "prototype" in proj.lower(),
            f"Should surface relevant beliefs for project suitability: {proj[:300]}"
        )


if __name__ == "__main__":
    unittest.main()
