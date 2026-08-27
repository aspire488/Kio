"""Focused tests for the FINAL semantic substrate (Node/Link graph +
computed activation + general reference resolver + Planner + invariants).

Covered owners:
  - mini_kio/semantic/graph.py         canonical Node/Link store + universal
                                       metadata (supersede/contradict/forget,
                                       symmetric attribution)
  - mini_kio/semantic/activation.py    computed activation (no topic pointer)
  - mini_kio/semantic/reference.py     one general reference resolver
  - mini_kio/semantic/decomposer.py    utterance -> graph ops
  - mini_kio/semantic/planner.py       Planner over decomposed ops
  - mini_kio/semantic/invariants.py    13 graph invariants
  - mini_kio/core/pipeline/__init__.py _chat_converse wiring (additive,
                                       defensive)

These are contract/regression tests; they never depend on live network.
"""

import unittest
from unittest import mock

from mini_kio.semantic.graph import KIO_KEY, USER_KEY, SemanticGraph
from mini_kio.semantic.intelligence import (
    ingest_turn, planner_decision, record_kio_reply, resolve_references,
    semantic_state_block,
)
from mini_kio.semantic.invariants import check_all, all_pass
from mini_kio.semantic.planner import decide


def _g(session_id="t_sem_graph"):
    return SemanticGraph(session_id)


class GraphStoreTest(unittest.TestCase):
    def test_node_kinds_are_data_not_routers(self):
        g = _g("kinds")
        g.ensure_node("participant", "Alex")
        g.ensure_node("topic", "ukulele")
        g.ensure_node("resource", "interstellar 2014")
        g.ensure_node("concept", "glorp")
        kinds = {n.kind for n in g.all_active_nodes()}
        self.assertTrue({"participant", "topic", "resource", "concept"} <= kinds)
        # one storage type covers everything: only node/claim kinds exist
        self.assertEqual(len({n.kind for n in g.all_active_nodes()}), 4)

    def test_attribution_symmetric(self):
        g = _g("sym")
        g.ensure_participant("user")
        g.ensure_participant("kio")
        g.record_statement(USER_KEY, "I prefer dark mode", stance="assertion")
        g.record_statement(KIO_KEY, "I think this project is interesting", stance="assertion")
        g.ensure_participant("alex")
        g.record_statement("participant:alex", "the launch is delayed", stance="assertion")
        for who in (USER_KEY, KIO_KEY, "participant:alex"):
            self.assertTrue(g.attributed_statements(who, active_only=True),
                            f"attributed statements missing for {who}")

    def test_supersession_preserves_history(self):
        g = _g("super")
        first = g.record_statement("participant:alex", "the launch is Friday")
        g.record_statement("participant:alex", "the launch is Thursday",
                           supersede_prior=True)
        active = g.attributed_statements("participant:alex", active_only=True)
        self.assertEqual(len(active), 1)
        self.assertEqual(active[0].target_name, "the launch is Thursday")
        all_rows = g.attributed_statements("participant:alex", active_only=False)
        self.assertEqual(len(all_rows), 2, "supersession must preserve history")

    def test_contradiction_keeps_both(self):
        g = _g("contr")
        a = g.record_statement("participant:alex", "price will rise")
        b = g.record_statement("participant:sarah", "price will fall")
        g.contradict(a.id, b.id)
        links = g.recent_links(active_only=True)
        self.assertTrue(any(l.relation == "contradicts" for l in links),
                        "contradiction must be represented as a link")

    def test_forget_excludes_from_recall_keeps_history(self):
        g = _g("forget")
        g.ensure_participant("alex")
        g.record_statement("participant:alex", "secret plan")
        g.forget("participant:alex")
        self.assertEqual(g.get_node_by_key("participant:alex").status, "forgotten")
        self.assertEqual(g.attributed_statements("participant:alex", active_only=True), [])
        self.assertEqual(len(g.attributed_statements("participant:alex", active_only=False)), 1)

    def test_universal_metadata_present(self):
        g = _g("meta")
        g.ensure_participant("alex")
        l = g.record_statement("participant:alex", "claim x", stance="desire",
                               confidence=0.8, event_time="yesterday")
        self.assertEqual(l.stance, "desire")
        self.assertEqual(l.attributed_to, "participant:alex")
        self.assertAlmostEqual(l.confidence, 0.8)
        self.assertEqual(l.event_time, "yesterday")
        self.assertTrue(l.created_at is not None)


class DecomposerTest(unittest.TestCase):
    def test_friend_name_merges_into_one_participant(self):
        g = _g("merge")
        d = ingest_turn("merge", "My friend Alex said the launch is delayed")["decomposition"]
        self.assertEqual(d.participants, ["Alex"], "role must merge into the named participant")
        self.assertIn("inform", d.intents)

    def test_third_party_statement_attributed_correctly(self):
        g = _g("attr")
        ingest_turn("attr", "My colleague Sarah believes the refactor is risky")
        stmts = g.attributed_statements("participant:sarah", active_only=True)
        self.assertEqual(len(stmts), 1)
        self.assertIn("risky", stmts[0].target_name)

    def test_correction_supersedes_most_recent(self):
        g = _g("corr")
        ingest_turn("corr", "My friend Alex said the launch is delayed until Friday")
        ingest_turn("corr", "Actually it is on Thursday now")
        active_alex = g.attributed_statements("participant:alex", active_only=True)
        self.assertEqual(len(active_alex), 0, "corrected claim must be superseded")
        all_alex = g.attributed_statements("participant:alex", active_only=False)
        self.assertEqual(len(all_alex), 1, "history preserved")
        user_stmts = g.attributed_statements(USER_KEY, active_only=True)
        self.assertTrue(user_stmts, "user's corrected claim recorded")

    def test_invented_entity_is_ordinary_participant(self):
        g = _g("inv")
        d = ingest_turn("inv", "The quibble-bot said the glorp is mibbling")["decomposition"]
        self.assertEqual(d.participants, ["quibble-bot"])
        self.assertTrue(g.attributed_statements("participant:quibblebot", active_only=True))


class ReferenceResolutionTest(unittest.TestCase):
    def _seed(self, sid):
        ingest_turn(sid, "My friend Alex said the launch is delayed until Friday")

    def test_he_resolves_and_retrieves(self):
        self._seed("ref_he")
        res = ingest_turn("ref_he", "What did he say?")["resolution"]
        self.assertEqual(res.referents.get("he").name, "Alex")
        self.assertEqual([s.target_name for s in res.statements],
                         ["the launch is delayed until Friday"])

    def test_they_ambiguous_with_multiple_parties(self):
        ingest_turn("ref_they", "My friend Alex said the launch is delayed")
        ingest_turn("ref_they", "My colleague Sarah recommended the orange framework")
        res = ingest_turn("ref_they", "What did they say?")["resolution"]
        self.assertIn("they", res.unresolved)

    def test_description_attribution(self):
        ingest_turn("ref_desc", "The quibble-bot said the glorp is mibbling")
        res = ingest_turn("ref_desc", "What did the quibble-bot say?")["resolution"]
        self.assertEqual([s.target_name for s in res.statements],
                         ["the glorp is mibbling"])

    def test_you_said_retrieves_kio_statement(self):
        ingest_turn("ref_kio", "What do you think about the launch?")
        record_kio_reply("ref_kio", "I think the delay is plausible given the backlog.")
        res = ingest_turn("ref_kio", "What did you say?")["resolution"]
        self.assertTrue(any(s.attributed_to == KIO_KEY for s in res.statements))

    def test_i_decided_retrieves_user_decision(self):
        ingest_turn("ref_user", "I decided to learn the ukulele")
        res = ingest_turn("ref_user", "What did I decide?")["resolution"]
        self.assertTrue(any("ukulele" in s.target_name for s in res.statements))

    def test_unresolved_never_fabricates(self):
        res = resolve_references("ref_empty", "Send it to him")
        self.assertTrue(res.unresolved)


class PlannerTest(unittest.TestCase):
    def test_unresolved_consequential_action_asks(self):
        g = _g("pl_ask")
        g.ensure_participant("user")
        g.ensure_participant("kio")
        res = resolve_references("pl_ask", "Send it to him")
        dec = decide(g, "Send it to him", None, res)
        self.assertEqual(dec.mode, "ask")
        self.assertIn("Ask", dec.block)

    def test_currentness_routes_to_research(self):
        g = _g("pl_cur")
        g.ensure_participant("user")
        g.ensure_participant("kio")
        from mini_kio.semantic.decomposer import decompose
        d = decompose(g, "what is the latest on the neutrino detector")
        dec = decide(g, "what is the latest on the neutrino detector", d, None)
        self.assertEqual(dec.mode, "research")


class ActivationTest(unittest.TestCase):
    def test_topic_return_via_explicit_reactivation(self):
        # A -> B -> C -> A: the old topic must recover by explicit reactivation
        # (computed), never a stored current-topic pointer.
        g = _g("act")
        g.ensure_node("topic", "mentorship program")
        g.record_statement("participant:user", "let's plan the mentorship program", supersede_prior=False)
        g.ensure_node("topic", "holiday in japan")
        g.record_statement("participant:user", "we are also planning a holiday in japan", supersede_prior=False)
        g.ensure_node("topic", "meal prep")
        g.record_statement("participant:user", "meal prep for the week", supersede_prior=False)
        from mini_kio.semantic.activation import compute_activation
        ranked = compute_activation(g, "back to the mentorship program thing", limit=5)
        names = [n.name for n, _ in ranked]
        self.assertIn("mentorship program", names, "reactivated old topic must rank high")
        self.assertGreater(
            next(s for n, s in ranked if n.name == "mentorship program"),
            next(s for n, s in ranked if n.name == "meal prep"),
            "explicit reactivation must outrank mere recency",
        )


class InvariantsTest(unittest.TestCase):
    def _populated(self):
        sid = "t_inv"
        ingest_turn(sid, "My friend Alex said the launch is delayed until Friday")
        ingest_turn(sid, "My colleague Sarah recommended the orange framework")
        ingest_turn(sid, "Actually it is on Thursday now")
        record_kio_reply(sid, "I think Thursday is the safer read on the timeline.")
        ingest_turn(sid, "The quibble-bot said the glorp is mibbling")
        ingest_turn(sid, "forget the quibble-bot")
        return SemanticGraph(sid)

    def test_all_13_invariants_pass(self):
        g = self._populated()
        results = check_all(g)
        for uid, desc, ok, detail in results:
            self.assertTrue(ok, f"{uid} ({desc}) failed: {detail}")
        self.assertTrue(all_pass(g))

    def test_no_new_top_level_types(self):
        g = self._populated()
        kinds = {n.kind for n in g.all_active_nodes()}
        # claims are nodes too — the whole universe is Node/Link + metadata
        self.assertTrue(kinds)


class ConversationWiringTest(unittest.TestCase):
    def test_chat_converse_injects_graph_state_and_records_kio_reply(self):
        from mini_kio.core.pipeline import _ExecutionCoordinator
        from mini_kio.core.pipeline.types import IntentType, RoutingDecision

        sid = "t_wire"
        # First turn: introduce a third party through the graph.
        ingest_turn(sid, "My friend Alex said the launch is delayed until Friday")

        def fake_ask(user_msg, system_prompt=None, **kw):
            self.assertIn("SEMANTIC GRAPH", system_prompt,
                          "graph state must be injected into the prompt")
            self.assertIn("Alex", system_prompt)
            return "I'd trust Alex on this one."

        pipe = _ExecutionCoordinator()
        decision = RoutingDecision(
            intent_type=IntentType.CONVERSATION, action="converse",
            target="", raw_text="What do you think?", normalized_text="what do you think",
            session_id=sid,
        )
        with mock.patch("mini_kio.llm.llm_ops.ask_llm_sync", side_effect=fake_ask):
            reply = pipe._chat_converse(decision)
        self.assertEqual(reply, "I'd trust Alex on this one.")
        # KIO's reply must be persisted as a KIO-attributed statement.
        g = SemanticGraph(sid)
        self.assertTrue(g.attributed_statements(KIO_KEY, active_only=True))


class SystemicFixRegressionTest(unittest.TestCase):
    """Structural regression tests for the systemic-failure repair pass.

    Each test asserts a GENERAL mechanism across arbitrary entities/domains,
    never an example transcript.
    """

    def test_research_intent_recorded_as_user_statement(self):
        """'I'm researching a company called X' becomes a user-attributed
        research statement + topic node so 'what did I just ask about?'
        resolves from the graph."""
        from mini_kio.semantic import intelligence as sem
        from mini_kio.semantic.graph import USER_KEY
        sid = "t_research_intent"
        sem.ingest_turn(sid, "Anyway, I'm researching a company called Zorbion Dynamics")
        g = sem.get_graph(sid)
        research = [s.target_name for s in g.attributed_statements(USER_KEY, active_only=True, limit=10)
                    if str(getattr(s, "target_name", "") or "").startswith("researching:")]
        self.assertTrue(any("Zorbion" in r for r in research),
                        f"research intent not recorded: {research}")
        topics = [n.name for n in g.all_active_nodes() if n.kind == "topic"]
        self.assertTrue(any("Zorbion" in t for t in topics), f"topic not created: {topics}")

    def test_named_attribution_retrieves_graph_statement(self):
        """'What did Dana say?' retrieves Dana's ACTUAL attributed statement;
        an unseen name stays unresolved (never fabricated)."""
        from mini_kio.semantic import intelligence as sem
        sid = "t_named_attr"
        g = sem.get_graph(sid)
        g.ensure_participant("dana", aliases=["dana"])
        g.record_statement("participant:dana", "the vorbel protocol is the future of data sync",
                           supersede_prior=False, provenance="decomposer")
        res = sem.resolve_references(sid, "What did Dana say?")
        self.assertTrue(any("vorbel" in (s.target_name or "") for s in res.statements))
        res2 = sem.resolve_references(sid, "What did Priya say?")
        self.assertFalse(res2.statements)
        self.assertTrue(any("Priya" in str(u) for u in res2.unresolved))

    def test_draft_does_not_require_recipient(self):
        """Draft/content-creation requests are answered WITHOUT resolving the
        recipient; delivery (send it to X) is a separate consequential step."""
        from mini_kio.semantic import intelligence as sem
        sid = "t_draft_vs_send"
        pd = sem.planner_decision(sid, "Give me something I can send him",
                                  None, None)
        self.assertEqual(pd.mode, "answer")
        # Content creation proceeds WITHOUT resolving the recipient.
        self.assertIn("recipient", pd.block.lower())
        self.assertIn("do not ask who the recipient is", pd.block.lower())

    def test_social_situation_routes_to_conversation(self):
        """'Someone said something wrong about you, give them a reply' is a
        social situation about conversation participants — never an
        ENTITY_QUERY web lookup."""
        from mini_kio.core.pipeline import Pipeline
        p = Pipeline()
        d = p._classifier.classify(
            "someone said something wrong about you, give them a reply",
            "Someone said something wrong about you, give them a reply",
        )
        self.assertEqual(d.intent_type.name, "CONVERSATION")

    def test_identity_with_audience_routes_to_conversation(self):
        """'introduce yourself to my friend' names an audience — the identity
        executor delegates to the conversational generator instead of the
        canned dataset answer."""
        from mini_kio.core.pipeline import _ExecutionCoordinator
        from mini_kio.core.pipeline.types import IntentType, RoutingDecision
        from unittest import mock
        sid = "t_identity_audience"
        pipe = _ExecutionCoordinator()
        decision = RoutingDecision(
            intent_type=IntentType.IDENTITY, action="", target="",
            raw_text="Hey KIO, introduce yourself to my friend",
            normalized_text="hey kio, introduce yourself to my friend",
            session_id=sid,
        )
        with mock.patch("mini_kio.core.pipeline._ExecutionCoordinator._chat_converse",
                        return_value="Hey bro — I'm KIO, Joel's personal AI companion.") as m:
            result = pipe._exec_conversation({"template": "identity"}, decision)
            m.assert_called_once()
            self.assertEqual(result["message"], "Hey bro — I'm KIO, Joel's personal AI companion.")

    def test_forget_resolves_graph_target_not_legacy_last_fact(self):
        """'forget that whole X thing' marks the graph node forgotten and
        confirms what was forgotten; unrelated nodes stay active."""
        from mini_kio.semantic.graph import USER_KEY, SemanticGraph
        sid = "t_forget_graph"
        g = SemanticGraph(sid)
        g.ensure_participant("zorbion", aliases=["zorbion"])
        g.record_statement("participant:zorbion", "a fictional company",
                           supersede_prior=False, provenance="decomposer")
        g.ensure_participant("dana", aliases=["dana"])
        g.record_statement("participant:dana", "the vorbel protocol is the future",
                           supersede_prior=False, provenance="decomposer")
        from mini_kio.core.pipeline import _ExecutionCoordinator
        from mini_kio.core.pipeline.types import IntentType, RoutingDecision
        pipe = _ExecutionCoordinator()
        decision = RoutingDecision(
            intent_type=IntentType.MEMORY, action="forget", target="",
            raw_text="forget that whole Zorbion thing",
            normalized_text="forget that whole zorbion thing",
            session_id=sid,
        )
        result = pipe._semantic_forget(sid, "that whole Zorbion thing")
        self.assertTrue(result.get("success"))
        self.assertIn("zorbion", result["message"].lower())
        g2 = SemanticGraph(sid)
        self.assertEqual(g2.get_node_by_key("participant:zorbion").status, "forgotten")
        self.assertEqual(g2.get_node_by_key("participant:dana").status, "active")

    def test_research_subject_guard_blocks_fabrication(self):
        """A research intent creates a topic node but NO proposition — the
        state block must inject the RESEARCH SUBJECT GUARD on the intent turn
        AND on later 'what about X' turns, so the LLM never describes an
        unresearched entity (live: fabricated 'Zorbion Dynamics is a private
        aerospace company')."""
        from mini_kio.semantic import intelligence as sem
        sid = "t_research_guard"
        sem.ingest_turn(sid, "Anyway, I'm researching a company called Zorbion Dynamics")
        self.assertIn("RESEARCH SUBJECT GUARD",
                      sem.semantic_state_block(sid, "I'm researching a company called Zorbion Dynamics", None))
        self.assertIn("RESEARCH SUBJECT GUARD",
                      sem.semantic_state_block(sid, "What about Zorbion?", None))

    def test_forget_reactivation_and_idempotency(self):
        """'forget X' resolves the most specific graph object; re-mentioning X
        reactivates it; re-forgetting is idempotent (never the legacy store).
        (live failure: re-forgetting Zorbion fell through to 'I don't have
        anything saved about you yet' because forgotten nodes were not
        scanned and re-mentions did not reactivate.)"""
        from mini_kio.core.pipeline import _ExecutionCoordinator
        from mini_kio.semantic.graph import USER_KEY, SemanticGraph
        sid = "t_forget_cycle"
        g = SemanticGraph(sid)
        g.ensure_node("topic", "Zorbion Dynamics")
        g.record_statement(USER_KEY, "researching zorbion dynamics",
                           supersede_prior=False, provenance="decomposer")
        pipe = _ExecutionCoordinator()
        r1 = pipe._semantic_forget(sid, "that whole Zorbion thing")
        self.assertTrue(r1.get("success"))
        self.assertIn("zorbion", r1["message"].lower())
        g2 = SemanticGraph(sid)
        self.assertEqual(g2.get_node_by_key("topic:zorbiondynamics").status, "forgotten")
        # Re-mention reactivates (explicit re-reference re-addresses the entity)
        SemanticGraph(sid).ensure_node("topic", "Zorbion Dynamics")
        self.assertEqual(SemanticGraph(sid).get_node_by_key("topic:zorbiondynamics").status, "active")
        # Re-forget resolves again (idempotent, still a real object)
        r2 = pipe._semantic_forget(sid, "forget Zorbion again")
        self.assertTrue(r2.get("success"))
        self.assertNotIn("anything saved", r2["message"].lower())
        self.assertEqual(SemanticGraph(sid).get_node_by_key("topic:zorbiondynamics").status, "forgotten")

    def test_holdout_name_adverb_attribution(self):
        """F1 (holdout): 'My supervisor Raj ALSO believes X' — an adverb
        between the name and the reporting verb must not drop the
        participant. Reproduced across geology/cooking/agriculture; the
        fix is a general adverb slot in the name-attribution pattern, never
        a phrase list."""
        from mini_kio.semantic import intelligence as sem
        sid = "t_holdout_adv"
        sem.ingest_turn(sid, "My supervisor Raj also believes the fossils are old.",
                        "My supervisor Raj also believes the fossils are old.")
        g = sem.get_graph(sid)
        node = g.get_node_by_key("participant:raj")
        self.assertIsNotNone(node)
        stmts = [s.target_name for s in g.attributed_statements(node.key, active_only=True, limit=4)]
        self.assertTrue(any("fossils are old" in s for s in stmts))
        # The user does NOT own Raj's claim (no contamination).
        user_stmts = [s.target_name for s in g.attributed_statements(USER_KEY, active_only=True, limit=4)]
        self.assertFalse(any("fossils" in s for s in user_stmts))

    def test_holdout_user_factual_assertion_ingested(self):
        """F2 (holdout): 'The Zephyr-7 draws 42 amps' is a USER-attributed
        observation (user state = graph query). Reproduced across aviation/
        cooking; 'what did I say about X' must resolve from the graph."""
        from mini_kio.semantic import intelligence as sem
        sid = "t_holdout_fact"
        sem.ingest_turn(sid, "The Zephyr-7 autopilot draws 42 amps under load.",
                        "The Zephyr-7 autopilot draws 42 amps under load.")
        g = sem.get_graph(sid)
        user_stmts = [s.target_name for s in g.attributed_statements(USER_KEY, active_only=True, limit=6)]
        self.assertTrue(any("zephyr-7" in s.lower() and "42" in s for s in user_stmts))
        topics = [n.name for n in g.all_active_nodes() if n.kind == "topic"]
        self.assertTrue(any("zephyr-7" in t.lower() for t in topics))

    def test_holdout_contraction_intention(self):
        """F3 (holdout): 'I'm planning to X' / 'I'll just do X' / 'I'm going
        to X' must all be recorded as user intentions (contractions are the
        same grammar as 'I want'). Reproduced across music/cooking."""
        from mini_kio.semantic import intelligence as sem
        sid = "t_holdout_intent"
        for text in (
            "I'm planning to open a small bakery next spring.",
            "I'll just do a single.",
            "I'm going to learn the theremin this year.",
        ):
            sem.ingest_turn(sid, text, text)
        g = sem.get_graph(sid)
        user_stmts = [s.target_name for s in g.attributed_statements(USER_KEY, active_only=True, limit=10)]
        self.assertTrue(any("bakery" in s for s in user_stmts))
        self.assertTrue(any("single" in s for s in user_stmts))
        self.assertTrue(any("theremin" in s for s in user_stmts))

    def test_holdout_correction_reattributes_third_party(self):
        """Correction reporting a THIRD-PARTY self-correction ("she
        corrected herself — she now thinks X") re-attributes to the third
        party, not the user. Reproduced in geology + linguistics."""
        from mini_kio.semantic import intelligence as sem
        sid = "t_holdout_corr"
        sem.ingest_turn(sid, "My colleague Imani thinks the fossils are from the Permian.",
                        "My colleague Imani thinks the fossils are from the Permian.")
        sem.ingest_turn(sid, "Actually she corrected herself — she now thinks they're Triassic.",
                        "Actually she corrected herself — she now thinks they're Triassic.")
        g = sem.get_graph(sid)
        node = g.get_node_by_key("participant:imani")
        self.assertIsNotNone(node)
        stmts = [s.target_name for s in g.attributed_statements(node.key, active_only=True, limit=4)]
        self.assertTrue(any("triassic" in s.lower() for s in stmts))
        user_stmts = [s.target_name for s in g.attributed_statements(USER_KEY, active_only=True, limit=4)]
        self.assertFalse(any("triassic" in s.lower() for s in user_stmts))

    def test_holdout_goal_forget(self):
        """'forget the EP' when the EP is a user GOAL claim (not a topic
        node) expires the goal — never 'I don't have anything saved'.
        Reproduced in music (EP/single change of mind)."""
        from mini_kio.semantic import intelligence as sem
        from mini_kio.core.pipeline import _ExecutionCoordinator
        sid = "t_holdout_goal_forget"
        sem.ingest_turn(sid, "I'm planning to record an EP called Static Bloom.",
                        "I'm planning to record an EP called Static Bloom.")
        pipe = _ExecutionCoordinator()
        r = pipe._semantic_forget_goal(sid, "the EP")
        self.assertTrue(r and r.get("success"))
        g = sem.get_graph(sid)
        remaining = [s.target_name for s in g.attributed_statements(USER_KEY, active_only=True, limit=6)]
        self.assertFalse(any("static bloom" in s.lower() for s in remaining))

    def test_holdout_called_open_class(self):
        """'an excavation site called the Maluti Basin dig' — the noun before
        'called' is an open class; a closed list missed 'site' and kept the
        whole phrase as research subject. Reproduced in geology."""
        from mini_kio.semantic import intelligence as sem
        sid = "t_holdout_called"
        sem.ingest_turn(sid, "I'm researching an excavation site called the Maluti Basin dig.",
                        "I'm researching an excavation site called the Maluti Basin dig.")
        g = sem.get_graph(sid)
        user_stmts = [s.target_name for s in g.attributed_statements(USER_KEY, active_only=True, limit=6)]
        self.assertTrue(any("maluti basin dig" in s.lower() for s in user_stmts))
        topics = [n.name for n in g.all_active_nodes() if n.kind == "topic"]
        self.assertTrue(any("maluti" in t.lower() for t in topics))

    def test_topic_extraction_rejects_function_words(self):
        """'about you' / 'about it' must never create degenerate topic nodes
        (live: topic:you polluted activation)."""
        from mini_kio.semantic import intelligence as sem
        sid = "t_topic_stop"
        sem.ingest_turn(sid, "What did they say about you?")
        g = sem.get_graph(sid)
        topics = [n.name for n in g.all_active_nodes() if n.kind == "topic"]
        self.assertFalse(any(t.strip().lower() in ("you", "it", "that", "this", "them") for t in topics),
                         f"degenerate topic created: {topics}")


if __name__ == "__main__":
    unittest.main()


class HistoricalImportProfileTest(unittest.TestCase):
    """Personalization phase: canonical history import + profile projection +
    proactive decision logic. All general — no user-specific rules."""

    def test_import_writes_provenance_and_temporal(self):
        import tempfile, os, json
        from mini_kio.memory.historical_import import _claim_for_v2
        # extraction families are general
        self.assertEqual(_claim_for_v2("i plan to push kio to github", "user")[1], "plans to: push kio to github")
        self.assertEqual(_claim_for_v2("i decided to switch to fedora", "user")[1], "decided: to switch to fedora")
        self.assertIsNone(_claim_for_v2("i want to ask you something", "user"))
        self.assertIsNone(_claim_for_v2("what if i try x?", "user"))
        self.assertIsNone(_claim_for_v2("she left, she said dont wait", "user"))
        self.assertIsNone(_claim_for_v2("i like tried creating before 18", "user"))
        # junk claims never surface
        self.assertIsNone(_claim_for_v2("i'll do it later", "user"))

    def test_profile_projection_and_forget(self):
        from mini_kio.semantic.graph import SemanticGraph, USER_KEY
        from mini_kio.memory.profile import profile_block, recall_about_user
        sid = "t_profile_phase"
        g = SemanticGraph(sid)
        g.record_statement(USER_KEY, "wants: build a terrarium", relation="wants",
                           event_time="2026-06-01T00:00:00+00:00", supersede_prior=False)
        g.record_statement(USER_KEY, "prefers: dark mode", relation="prefers",
                           event_time="2026-06-02T00:00:00+00:00", supersede_prior=False)
        block = profile_block(sid)
        self.assertIn("build a terrarium", block)
        self.assertIn("2026-06", block)
        # forgetting drops it from projection but keeps history
        node = None
        for s in g.attributed_statements(USER_KEY, active_only=True, limit=10):
            if "terrarium" in s.target_name:
                node = g.get_node(s.target_id)
        self.assertIsNotNone(node)
        g.forget(node.key)
        self.assertNotIn("terrarium", profile_block(sid))
        self.assertNotIn("terrarium", recall_about_user(sid))

    def test_proactive_silence_for_imported_history(self):
        from mini_kio.monitoring.proactive import evaluate
        from mini_kio.semantic.graph import SemanticGraph, USER_KEY
        sid = "t_proactive_hist"
        g = SemanticGraph(sid)
        g.record_statement(USER_KEY, "wants: old imported goal", relation="wants",
                           event_time="2026-06-01T00:00:00+00:00",
                           provenance="chatgpt_export:conv1", supersede_prior=False)
        decs = evaluate(sid)
        self.assertTrue(all(d["decision"] == "silence" for d in decs),
                        f"imported history must not notify: {decs}")

    def test_proactive_notify_for_live_stale_goal(self):
        from mini_kio.monitoring.proactive import evaluate
        from mini_kio.semantic.graph import SemanticGraph, USER_KEY
        import datetime
        sid = "t_proactive_live"
        g = SemanticGraph(sid)
        old = (datetime.datetime.now(datetime.timezone.utc)
               - datetime.timedelta(hours=48)).isoformat(timespec="seconds")
        g.record_statement(USER_KEY, "wants: finish the side project", relation="wants",
                           event_time=old, supersede_prior=False)
        decs = evaluate(sid)
        self.assertTrue(any(d["decision"] == "notify" for d in decs), decs)
        # and the goal label is stripped of scaffolding
        d = [x for x in decs if x["decision"] == "notify"][0]
        self.assertEqual(d["goal"], "finish the side project")

    def test_profile_recall_answer(self):
        from mini_kio.core.pipeline import Pipeline
        from mini_kio.semantic.graph import SemanticGraph, USER_KEY
        sid = "t_recall_phase"
        g = SemanticGraph(sid)
        g.record_statement(USER_KEY, "wants: a proper LOGO for KIO", relation="wants",
                           event_time="2026-06-10T00:00:00+00:00", supersede_prior=False)
        pipe = Pipeline()
        # deterministic recall runs before any LLM
        r = pipe._apply_profile_recall_answer(
            type("D", (), {"session_id": sid, "normalized_text": "", "raw_text": ""}),
            "when did I tell you about the KIO logo?")
        self.assertIsNotNone(r)
        self.assertIn("2026-06", r["message"])
        r2 = pipe._apply_profile_recall_answer(
            type("D", (), {"session_id": sid, "normalized_text": "", "raw_text": ""}),
            "what do you remember about me?")
        self.assertIsNotNone(r2)
        msg = (r2["message"] or "").lower()
        # the user's actual goal (KIO logo) is recalled...
        self.assertTrue("logo" in msg, msg)
        # ...and it is NEVER misattributed to KIO itself
        self.assertNotIn("creating a proper logo for myself", msg)
        self.assertNotIn("my own development", msg)


if __name__ == "__main__":
    unittest.main()


class ProactiveCapabilityAwareTest(unittest.TestCase):
    """Capability-aware proactivity: workflow-engine state becomes notify /
    silence decisions through the SAME evaluator gates (re-engagement,
    cooldown, value). Tests real engine state; never sends messages."""

    def setUp(self):
        # the workflow engine is a process-global singleton; reset it so
        # workflows from one test never leak into another
        from mini_kio.execution.workflows import _get_engine
        _get_engine()._executions.clear()

    def _wf(self, eng, name, status, created_h, completed_h=None, approval=None):
        from mini_kio.execution.engine import WorkflowStatus, StepStatus
        from datetime import datetime, timedelta, timezone
        steps = []
        if approval:
            steps.append({"name": approval, "action": "close_app", "target": "x",
                          "approval_required": True})
        steps.append({"name": "go", "action": "research", "target": "y"})
        wf = eng.create_workflow(name=name, steps=steps)
        wf.created_at = (datetime.now(timezone.utc) - timedelta(hours=created_h)).timestamp()
        wf.status = status
        if completed_h is not None:
            wf.completed_at = (datetime.now(timezone.utc) - timedelta(hours=completed_h)).timestamp()
        if approval:
            for stp in wf.steps:
                if getattr(stp, "approval_required", False):
                    stp.status = StepStatus.PENDING
        return wf

    def test_failed_workflow_notifies(self):
        from mini_kio.execution.workflows import _get_engine
        from mini_kio.execution.engine import WorkflowStatus
        from mini_kio.monitoring import proactive
        from datetime import datetime, timezone
        eng = _get_engine()
        self._wf(eng, "cap-failed-wf", WorkflowStatus.FAILED, created_h=30)
        d = proactive.evaluate("t_cap_failed", now=datetime.now(timezone.utc))
        wf = [x for x in d if x.get("kind") == "workflow"]
        self.assertTrue(wf, d)
        self.assertEqual(wf[0]["subkind"], "failed")
        self.assertEqual(wf[0]["goal"], "cap-failed-wf")

    def test_approval_pending_notifies_with_steps(self):
        from mini_kio.execution.workflows import _get_engine
        from mini_kio.execution.engine import WorkflowStatus
        from mini_kio.monitoring import proactive
        from datetime import datetime, timezone
        eng = _get_engine()
        self._wf(eng, "cap-approval-wf", WorkflowStatus.PAUSED, created_h=30,
                 approval="close old session")
        d = proactive.evaluate("t_cap_approval", now=datetime.now(timezone.utc))
        wf = [x for x in d if x.get("kind") == "workflow"]
        self.assertTrue(wf, d)
        self.assertEqual(wf[0]["subkind"], "approval")
        self.assertIn("close old session", wf[0].get("workflow_steps", []))

    def test_completed_while_away_notifies_but_not_with_recent_engagement(self):
        from mini_kio.execution.workflows import _get_engine
        from mini_kio.execution.engine import WorkflowStatus
        from mini_kio.monitoring import proactive
        from datetime import datetime, timedelta, timezone
        eng = _get_engine()
        # completed 2h ago, no user engagement after -> notify
        self._wf(eng, "cap-done-away", WorkflowStatus.COMPLETED, created_h=30, completed_h=2)
        d1 = proactive.evaluate("t_cap_done1", now=datetime.now(timezone.utc))
        self.assertTrue([x for x in d1 if x.get("kind") == "workflow" and x.get("subkind") == "completed"], d1)
        # completed 2h ago, user engaged after -> silence
        sid = "t_cap_done2"
        g = SemanticGraph(sid)
        g.record_statement(USER_KEY, "wants: check the render", relation="wants",
                           confidence=0.9, supersede_prior=False)
        self._wf(eng, "cap-done-engaged", WorkflowStatus.COMPLETED, created_h=30, completed_h=5)
        d2 = proactive.evaluate(sid, now=datetime.now(timezone.utc))
        engaged = [x for x in d2 if x.get("goal") == "cap-done-engaged"]
        self.assertFalse(engaged, d2)

    def test_marker_after_delivery_silences(self):
        from mini_kio.execution.workflows import _get_engine
        from mini_kio.execution.engine import WorkflowStatus
        from mini_kio.monitoring import proactive
        from datetime import datetime, timezone
        eng = _get_engine()
        wf = self._wf(eng, "cap-marked", WorkflowStatus.FAILED, created_h=40)
        wf.context["proactive_notified"] = datetime.now(timezone.utc).isoformat()
        d = proactive.evaluate("t_cap_marked", now=datetime.now(timezone.utc))
        self.assertFalse([x for x in d if x.get("kind") == "workflow"], d)

    def test_wait_state_defers_not_notifies(self):
        from mini_kio.monitoring import proactive
        from datetime import datetime, timezone
        sid = "t_cap_wait"
        g = SemanticGraph(sid)
        g.record_statement(USER_KEY, "waiting for the lab results", relation="said",
                           confidence=0.9, supersede_prior=False)
        d = proactive.evaluate(sid, now=datetime.now(timezone.utc))
        waits = [x for x in d if x.get("kind") == "wait"]
        self.assertTrue(waits, d)
        self.assertEqual(waits[0]["decision"], "defer")


class CompanionWaitAndDeclTest(unittest.TestCase):
    """General fixes for realistic companion failures:
    F-R1 wait-state recall answers from the graph (never fabricated); F-R2
    proper-named third-person status declarations CREATE projects."""

    def test_wait_state_recall_answers_from_graph(self):
        from mini_kio.core.pipeline import Pipeline
        sid = "t_wait_recall"
        g = SemanticGraph(sid)
        g.record_statement(USER_KEY, "waiting for the render queue to clear",
                           relation="said", confidence=0.9, supersede_prior=False)
        pipe = Pipeline()
        r = pipe._apply_profile_recall_answer(
            type("D", (), {"session_id": sid, "normalized_text": "", "raw_text": ""}),
            "what am I waiting for right now?")
        self.assertIsNotNone(r)
        self.assertIn("render queue", r["message"])

    def test_wait_state_recall_honest_when_empty(self):
        from mini_kio.core.pipeline import Pipeline
        pipe = Pipeline()
        r = pipe._apply_profile_recall_answer(
            type("D", (), {"session_id": "t_no_wait", "normalized_text": "", "raw_text": ""}),
            "what am I waiting for?")
        self.assertIsNotNone(r)
        self.assertIn("Nothing", r["message"])

    def test_proper_named_declaration_creates_project(self):
        from mini_kio.semantic.decomposer import decompose
        g = SemanticGraph("t_proper_decl")
        d = decompose(g, "MediMind is on hold for now", "MediMind is on hold for now")
        self.assertTrue(d.project_ops, d.project_ops)
        self.assertEqual(d.project_ops[0]["status"], "paused")
        self.assertIn("medimind", d.project_ops[0]["name"].lower())

    def test_generic_named_declaration_does_not_create(self):
        from mini_kio.semantic.decomposer import decompose
        g = SemanticGraph("t_generic_decl")
        d = decompose(g, "the build is on hold", "the build is on hold")
        # generic single-word lowercase head never creates a project
        self.assertFalse([p for p in d.project_ops if "build" in p["name"].lower()], d.project_ops)

    def test_proper_decl_creates_and_abandons(self):
        from mini_kio.semantic.decomposer import decompose
        g = SemanticGraph("t_proper_decl2")
        d = decompose(g, "CoFlow is dead", "CoFlow is dead")
        self.assertTrue(d.project_ops, d.project_ops)
        self.assertEqual(d.project_ops[0]["status"], "abandoned")
