"""
Focused tests for the capability-provider batch + generalized watch.

Covered owners:
  - mini_kio/core/utilities.py: air_quality / holiday / earthquake / book
    providers (routing hooks + answer contracts, honest failure)
  - mini_kio/core/pipeline/__init__.py: _detect_utility wiring for the four
    new providers
  - mini_kio/monitoring/watches.py: generalized watch (feed + page probes,
    one poll/diff/notify mechanism)
  - mini_kio/intelligence/retrieval_router.py: arXiv probe in the evidence
    chain

Tests are contract/regression tests — they never depend on live network.
"""

import unittest
from unittest import mock

from mini_kio.core import utilities
from mini_kio.core.pipeline import Pipeline
from mini_kio.monitoring import watches


def _classify(text):
    pipe = Pipeline()
    return pipe._classifier.classify(text, text)


class AirQualityProviderTest(unittest.TestCase):
    def test_hook_fires_with_location(self):
        self.assertTrue(utilities.looks_like_air_quality("what is the air quality in Delhi"))
        self.assertTrue(utilities.looks_like_air_quality("air quality in Beijing"))

    def test_hook_ignores_general_mention(self):
        self.assertFalse(utilities.looks_like_air_quality("what is air quality"))
        self.assertFalse(utilities.looks_like_air_quality("air quality index meaning"))

    def test_answer_honest_offline(self):
        with mock.patch.object(utilities, "_openmeteo_geocode", return_value=None):
            r = utilities.air_quality_answer("air quality in Nowhereville")
        self.assertFalse(r.get("success"))
        self.assertIn("air quality", r.get("message", ""))

    def test_answer_contract(self):
        with mock.patch.object(utilities, "_openmeteo_geocode", return_value=(10.0, 10.0, "Testville")), \
             mock.patch("mini_kio.core.utilities._http_get_json", return_value=None):
            # network fail -> honest message
            r = utilities.air_quality_answer("air quality in Testville")
        self.assertEqual(r.get("type"), "air_quality")
        self.assertFalse(r.get("success"))
        with mock.patch.object(utilities, "_openmeteo_geocode", return_value=(10.0, 10.0, "Testville")), \
             mock.patch("mini_kio.core.utilities._http_get_json",
                        return_value={"current": {"us_aqi": 42, "pm2_5": 12.0, "pm10": 30.0}}):
            r = utilities.air_quality_answer("air quality in Testville")
        self.assertTrue(r.get("success"))
        self.assertEqual(r.get("aqi"), 42)
        self.assertIn("Good", r.get("message", ""))

    def test_routes_to_utility(self):
        d = _classify("what is the air quality in Delhi")
        self.assertEqual(str(d.intent_type.value), "utility")
        self.assertEqual(d.action, "air_quality")


class HolidayProviderTest(unittest.TestCase):
    def test_hook_requires_holiday_word(self):
        self.assertTrue(utilities.looks_like_holiday("is today a holiday in India"))
        self.assertFalse(utilities.looks_like_holiday("happy holidays"))

    def test_article_tolerated(self):
        self.assertTrue(utilities.looks_like_holiday("is today a holiday in the US"))

    def test_next_holiday_answer(self):
        with mock.patch("mini_kio.core.utilities._http_get_json",
                        return_value=[{"date": "2026-12-25", "localName": "Christmas", "name": "Christmas"}]):
            r = utilities.holiday_answer("when is the next holiday in the US")
        self.assertTrue(r.get("success"))
        self.assertIn("Christmas", r.get("message", ""))

    def test_routes_to_utility(self):
        d = _classify("is today a holiday in India")
        self.assertEqual(str(d.intent_type.value), "utility")
        self.assertEqual(d.action, "holiday")


class EarthquakeProviderTest(unittest.TestCase):
    def test_hook(self):
        self.assertTrue(utilities.looks_like_earthquake("any earthquakes near Tokyo"))
        self.assertFalse(utilities.looks_like_earthquake("earthquake insurance"))
        self.assertFalse(utilities.looks_like_earthquake("did you feel that earthquake"))

    def test_answer_contract(self):
        with mock.patch("mini_kio.core.utilities._http_get_json",
                        return_value={"features": [{"properties": {"mag": 5.2, "place": "Test Region", "time": 1700000000000}}]}):
            r = utilities.earthquake_answer("earthquakes near Tokyo")
        self.assertTrue(r.get("success"))
        self.assertEqual(r.get("magnitude"), 5.2)

    def test_routes_to_utility(self):
        d = _classify("any earthquakes near Tokyo")
        self.assertEqual(d.action, "earthquake")


class BookProviderTest(unittest.TestCase):
    def test_hook_explicit_only(self):
        self.assertTrue(utilities.looks_like_book("find the book Dune"))
        self.assertTrue(utilities.looks_like_book("books by Frank Herbert"))
        # 'who wrote X' is a general knowledge question, never hijacked
        self.assertFalse(utilities.looks_like_book("who wrote Dune"))
        self.assertFalse(utilities.looks_like_book("who wrote the declaration of independence"))

    def test_general_who_wrote_not_hijacked(self):
        d = _classify("who wrote the declaration of independence")
        self.assertNotEqual(d.action, "book")

    def test_answer_contract(self):
        with mock.patch("mini_kio.core.utilities._http_get_json",
                        return_value={"docs": [{"title": "Dune", "author_name": ["Frank Herbert"], "first_publish_year": 1965}]}):
            r = utilities.book_answer("find the book Dune")
        self.assertTrue(r.get("success"))
        self.assertIn("Dune", r.get("message", ""))

    def test_routes_to_utility(self):
        d = _classify("find the book Dune")
        self.assertEqual(d.action, "book")


class WatchGeneralizationTest(unittest.TestCase):
    def test_kind_classification(self):
        self.assertEqual(watches._watch_kind("openai/openai")[0], "github")
        self.assertEqual(watches._watch_kind("requests")[0], "pypi")
        self.assertEqual(watches._watch_kind("https://example.com/")[0], watches._KIND_PAGE)
        self.assertEqual(watches._watch_kind("example.com")[0], watches._KIND_PAGE)

    _PAGE_A = (b"<html><head><script>var x=1;</script></head><body><h1>Title</h1>"
               b"<p>This is a long enough content paragraph to clear the fingerprint "
               b"length guard with room to spare.</p></body></html>")
    _PAGE_B = (b"<html><head><script>var x=1;</script></head><body><h1>Title</h1>"
               b"<p>This is a long enough content paragraph that CHANGED the page "
               b"significantly with room to spare.</p></body></html>")

    def test_page_fingerprint_stable(self):
        with mock.patch.object(watches.utilities, "_http_get_bytes", return_value=self._PAGE_A):
            k1, items = watches._page_fingerprint("https://example.com/")
            k2, _ = watches._page_fingerprint("https://example.com/")
        self.assertEqual(k1, k2)
        self.assertEqual(items[0][0], "https://example.com/")  # no <title> -> url used

    def test_page_fingerprint_sensitive_to_content(self):
        with mock.patch.object(watches.utilities, "_http_get_bytes", return_value=self._PAGE_A):
            k1, _ = watches._page_fingerprint("https://example.com/")
        with mock.patch.object(watches.utilities, "_http_get_bytes", return_value=self._PAGE_B):
            k2, _ = watches._page_fingerprint("https://example.com/")
        self.assertNotEqual(k1, k2)

    def test_page_probe_requires_content(self):
        with mock.patch.object(watches.utilities, "_http_get_bytes", return_value=b""):
            k, items = watches._page_fingerprint("https://example.com/")
        self.assertIsNone(k)
        self.assertEqual(items, [])

    def test_fetch_latest_dispatch(self):
        with mock.patch.object(watches, "_page_fingerprint", return_value=("abc", [("T", "u", "")])) as pf, \
             mock.patch.object(watches.utilities, "_feed_url_for_target", return_value=("https://x", "pypi")):
            k, _ = watches._fetch_latest("https://example.com/", watches._KIND_PAGE)
            pf.assert_called_once()
            self.assertEqual(k, "abc")

    def test_poll_uses_fingerprint_diff(self):
        rows = [
            mock.Mock(id=1, target="example.com", kind=watches._KIND_PAGE,
                      chat_id="1", last_seen_key="old-key"),
        ]
        with mock.patch.object(watches._repo, "all_active", return_value=rows), \
             mock.patch.object(watches, "_fetch_latest", return_value=("new-key", [("T", "https://example.com", "")])), \
             mock.patch.object(watches, "send_telegram_message", return_value=True) as send, \
             mock.patch.object(watches._repo, "update_last_seen") as upd:
            res = watches.poll_watches()
        self.assertEqual(res["notified"], 1)
        send.assert_called_once()
        upd.assert_called_once()

    def test_poll_silent_on_no_change(self):
        rows = [
            mock.Mock(id=1, target="example.com", kind=watches._KIND_PAGE,
                      chat_id="1", last_seen_key="same-key"),
        ]
        with mock.patch.object(watches._repo, "all_active", return_value=rows), \
             mock.patch.object(watches, "_fetch_latest", return_value=("same-key", [("T", "u", "")])), \
             mock.patch.object(watches, "send_telegram_message") as send:
            res = watches.poll_watches()
        self.assertEqual(res["notified"], 0)
        send.assert_not_called()

    def test_legacy_kind_normalized(self):
        rows = [
            mock.Mock(id=2, target="requests", kind="pypi",
                      chat_id="1", last_seen_key="old"),
        ]
        with mock.patch.object(watches._repo, "all_active", return_value=rows), \
             mock.patch.object(watches, "_fetch_latest", return_value=("new", [("T", "u", "")])), \
             mock.patch.object(watches, "send_telegram_message", return_value=True), \
             mock.patch.object(watches._repo, "update_last_seen"):
            res = watches.poll_watches()
        self.assertEqual(res["checked"], 1)
        self.assertEqual(res["notified"], 1)

    def test_watch_routes_utility(self):
        d = _classify("watch example.com")
        self.assertEqual(d.action, "watch")
        d2 = _classify("watch openai/openai for new releases")
        self.assertEqual(d2.action, "watch")

    def test_watch_question_never_registers(self):
        # Recommendation/preference questions with the word "watch" are
        # conversational — never watch registrations.
        for q in ("should i watch dune", "would you watch that",
                  "what should we watch tonight", "recommend something to watch"):
            action, target = watches._extract_watch_command(q)
            self.assertIsNone(action, f"{q!r} must not be a watch command")
        d = _classify("should i watch dune")
        self.assertNotEqual(d.action, "watch")


class UrlConversationGroundingTest(unittest.TestCase):
    """General web-document extraction primitive: a URL in a conversational
    message must inject the REAL page text into the LLM context (never a
    fabricated summary), while action URLs keep their own executors."""

    def test_url_message_routes_conversation(self):
        d = _classify("summarize https://en.wikipedia.org/wiki/Grace_Hopper")
        self.assertEqual(str(d.intent_type.value), "conversation")
        d2 = _classify("https://example.com/article")
        self.assertEqual(str(d2.intent_type.value), "conversation")

    def test_action_urls_never_hijacked(self):
        d = _classify("open https://en.wikipedia.org/wiki/Grace_Hopper")
        self.assertEqual(str(d.intent_type.value), "browser_navigate")
        d2 = _classify("play https://www.youtube.com/watch?v=dQw4w9WgXcQ")
        self.assertEqual(str(d2.intent_type.value), "media_play")

    def test_injects_page_content_into_context(self):
        from mini_kio.core.pipeline import _ExecutionCoordinator
        captured = {}

        def fake_read(url):
            captured["url"] = url
            return ("Title: Grace Hopper\n\nGrace Hopper was a pioneering computer "
                    "scientist. She invented the first compiler and championed COBOL.")

        def fake_ask(_msg, system_prompt=None, timeout=25.0, max_tokens=300, task="conversation"):
            captured["prompt"] = system_prompt or ""
            return "She invented the first compiler."

        pipe = Pipeline()
        decision = pipe._classifier.classify(
            "summarize https://en.wikipedia.org/wiki/Grace_Hopper",
            "summarize https://en.wikipedia.org/wiki/Grace_Hopper",
        )
        with mock.patch("mini_kio.knowledge.jina_reader_provider.read_url", side_effect=fake_read), \
             mock.patch("mini_kio.llm.llm_ops.ask_llm_sync", side_effect=fake_ask):
            reply = _ExecutionCoordinator()._chat_converse(decision)
        self.assertIn("Grace_Hopper", captured["url"])
        self.assertIn("WEB PAGE CONTENT", captured["prompt"])
        self.assertIn("invented the first compiler", captured["prompt"])
        self.assertEqual(reply, "She invented the first compiler.")

    def test_no_injection_without_url(self):
        from mini_kio.core.pipeline import _ExecutionCoordinator
        captured = {}

        def fake_ask(_msg, system_prompt=None, timeout=25.0, max_tokens=300, task="conversation"):
            captured["prompt"] = system_prompt or ""
            return "hello"

        pipe = Pipeline()
        decision = pipe._classifier.classify("what is your favorite movie", "what is your favorite movie")
        with mock.patch("mini_kio.llm.llm_ops.ask_llm_sync", side_effect=fake_ask):
            reply = _ExecutionCoordinator()._chat_converse(decision)
        self.assertNotIn("WEB PAGE CONTENT", captured["prompt"])
        self.assertEqual(reply, "hello")

    def test_reader_failure_is_silent(self):
        # Reader unavailable -> no fabricated content, no crash, honest path.
        from mini_kio.core.pipeline import _ExecutionCoordinator
        captured = {}

        def fake_ask(_msg, system_prompt=None, timeout=25.0, max_tokens=300, task="conversation"):
            captured["prompt"] = system_prompt or ""
            return "I can't read that page right now."

        pipe = Pipeline()
        decision = pipe._classifier.classify(
            "summarize https://example.com/blocked",
            "summarize https://example.com/blocked",
        )
        with mock.patch("mini_kio.knowledge.jina_reader_provider.read_url", return_value=None), \
             mock.patch("mini_kio.llm.llm_ops.ask_llm_sync", side_effect=fake_ask):
            reply = _ExecutionCoordinator()._chat_converse(decision)
        self.assertNotIn("WEB PAGE CONTENT", captured["prompt"])
        self.assertEqual(reply, "I can't read that page right now.")


class ReminderPrimitiveTest(unittest.TestCase):
    """Time-scheduled notification primitive — the TIME-trigger companion of
    the CHANGE-trigger watch primitive. Same delivery path, same poller."""

    def test_route_family(self):
        from mini_kio.monitoring import reminders
        self.assertTrue(reminders.looks_like_reminder("remind me in 2 hours to call Sarah"))
        self.assertTrue(reminders.looks_like_reminder("remind me at 5pm to check the weather"))
        self.assertTrue(reminders.looks_like_reminder("remind me tomorrow at 9 to review the draft"))
        self.assertTrue(reminders.looks_like_reminder("cancel my reminders"))
        self.assertTrue(reminders.looks_like_reminder("what reminders do I have"))

    def test_incomplete_and_casual_never_route(self):
        from mini_kio.monitoring import reminders
        # No trigger time -> incomplete conversational request
        self.assertFalse(reminders.looks_like_reminder("remind me to call Sarah"))
        # Casual topic-switch phrase
        self.assertFalse(reminders.looks_like_reminder("that reminds me of a good movie"))
        self.assertFalse(reminders.looks_like_reminder("this movie reminds me of Dune"))

    def test_time_parsing(self):
        from mini_kio.monitoring import reminders
        from datetime import datetime, timedelta, timezone
        now = datetime(2026, 8, 16, 10, 0, tzinfo=timezone.utc)
        d = reminders._parse_due("remind me in 45 minutes to X", now=now)
        self.assertEqual(int((d - now).total_seconds()), 2700)
        d = reminders._parse_due("remind me in 2 hours to X", now=now)
        self.assertEqual(int((d - now).total_seconds()), 7200)
        d = reminders._parse_due("remind me at 5pm to X", now=now)
        self.assertEqual(d.hour, 17)
        d = reminders._parse_due("remind me tomorrow at 9 to X", now=now)
        self.assertEqual(d.day, 17)
        self.assertEqual(d.hour, 9)
        self.assertIsNone(reminders._parse_due("remind me to call Sarah", now=now))

    def test_poll_delivers_due_and_marks_delivered(self):
        from mini_kio.monitoring import reminders
        from mini_kio.backend.repositories.reminder_repository import ReminderRepository
        from datetime import datetime, timedelta, timezone
        repo = ReminderRepository()
        due = datetime.now(timezone.utc) + timedelta(seconds=5)
        repo.add("test payload", due, "term1", channel="terminal", user_id="")
        with mock.patch.object(reminders, "send_telegram_message", return_value=True) as send:
            res = reminders.poll_reminders()
        self.assertEqual(res["delivered"], 0)  # not due yet
        send.assert_not_called()
        # force due
        from mini_kio.backend.models import ReminderModel
        from mini_kio.backend.db import db_session
        with db_session() as s:
            for row in s.query(ReminderModel).all():
                row.due_at = datetime.now(timezone.utc) - timedelta(seconds=1)
        with mock.patch.object(reminders, "send_telegram_message", return_value=True) as send:
            res = reminders.poll_reminders()
        self.assertEqual(res["checked"], 1)
        self.assertEqual(res["delivered"], 1)
        self.assertIn("test payload", send.call_args[0][1])
        # marked delivered -> no double delivery
        with mock.patch.object(reminders, "send_telegram_message", return_value=True) as send2:
            res2 = reminders.poll_reminders()
        self.assertEqual(res2["delivered"], 0)
        send2.assert_not_called()

    def test_answer_contract_and_cancel(self):
        from mini_kio.monitoring import reminders
        r = reminders.reminder_answer("remind me in 2 hours to review the draft")
        self.assertTrue(r.get("success"))
        self.assertEqual(r.get("type"), "reminder")
        self.assertEqual(r.get("action"), "add")
        n = reminders._repo.deactivate_by_text("review", "terminal")
        self.assertGreaterEqual(n, 1)


class WorkflowCapabilityTest(unittest.TestCase):
    """General workflow/automation primitive — the dormant WorkflowEngine
    made user-reachable: natural multi-step command -> engine execution with
    approval gates on consequential actions."""

    def test_routing_family(self):
        from mini_kio.execution import workflows
        for q in ("create a workflow to open chrome and search for python",
                  "run the workflow", "workflow status", "cancel the workflow",
                  "pause the workflow", "resume the workflow"):
            self.assertTrue(workflows.looks_like_workflow(q), q)
        self.assertFalse(workflows.looks_like_workflow("open chrome"))
        self.assertFalse(workflows.looks_like_workflow("how does a workflow work"))

    def test_step_parsing(self):
        from mini_kio.execution import workflows
        steps = workflows._parse_steps("open chrome and search for python")
        self.assertEqual(len(steps), 2)
        self.assertEqual(steps[0]["action"], "open")
        self.assertFalse(steps[0]["approval_required"])

    def test_consequential_actions_need_approval(self):
        from mini_kio.execution import workflows
        steps = workflows._parse_steps("close notepad and open chrome")
        self.assertTrue(steps[0]["approval_required"])
        self.assertFalse(steps[1]["approval_required"])

    def test_create_blocks_run_on_approval(self):
        from mini_kio.execution import workflows
        with mock.patch.object(workflows, "_get_engine") as eng:
            eng.return_value.list_workflows.return_value = []
            r = workflows.workflow_answer("create a workflow to close notepad and open chrome")
        self.assertTrue(r.get("success"))
        self.assertTrue(r.get("approval_required"))

    def test_routes_to_utility(self):
        d = _classify("create a workflow to open chrome and search for python")
        self.assertEqual(d.action, "workflow")
        d2 = _classify("workflow status")
        self.assertEqual(d2.action, "workflow")


class MessageCapabilityTest(unittest.TestCase):
    """General outbound-communication seam: draft/send/cancel/list with a
    provider-neutral lifecycle. Drafting needs no authorization; sending
    requires a resolved authorized sink and is persisted + verified."""

    def test_routing_family(self):
        from mini_kio.communication import messages
        self.assertTrue(messages.looks_like_message("draft a message to Sarah: running 10 min late"))
        self.assertTrue(messages.looks_like_message("send the draft"))
        self.assertTrue(messages.looks_like_message("cancel the draft"))
        self.assertTrue(messages.looks_like_message("what messages are pending"))
        # casual / incomplete forms never fire
        self.assertFalse(messages.looks_like_message("text me back"))
        self.assertFalse(messages.looks_like_message("send it to them"))

    def test_draft_persists_without_authorization(self):
        from mini_kio.communication import messages
        r = messages.message_answer("draft a message to Sarah: running 10 min late")
        self.assertTrue(r.get("success"))
        self.assertEqual(r.get("action"), "add_draft")
        self.assertEqual(r.get("type"), "message")

    def test_send_unresolved_recipient_refused(self):
        from mini_kio.communication import messages
        r = messages.message_answer("send a message to Sarah: running 10 min late")
        self.assertFalse(r.get("success"))
        self.assertTrue(r.get("refused"))

    def test_send_self_persists_and_verifies(self):
        from mini_kio.communication import messages
        from mini_kio.backend.repositories.outbound_message_repository import OutboundMessageRepository
        class _D:
            channel = "telegram"
            user_id = 424242
        decision = _D()
        with mock.patch.object(messages, "send_telegram_message", return_value=True) as send:
            r = messages.message_answer("send a message to me: test ping", decision=decision)
        self.assertTrue(r.get("success"))
        self.assertTrue(r.get("verified"))
        send.assert_called_once_with("424242", "test ping")
        rows = OutboundMessageRepository().list_active("424242")
        self.assertTrue(any(row["status"] == "sent" for row in rows))

    def test_send_failure_honest(self):
        from mini_kio.communication import messages
        class _D:
            channel = "telegram"
            user_id = 424243
        decision = _D()
        with mock.patch.object(messages, "send_telegram_message", return_value=False):
            r = messages.message_answer("send a message to me: test ping", decision=decision)
        self.assertFalse(r.get("success"))
        self.assertEqual(r.get("action"), "failed")
        self.assertFalse(r.get("verified"))

    def test_routes_to_utility(self):
        d = _classify("draft a message to Sarah: running 10 min late")
        self.assertEqual(d.action, "message")
        d2 = _classify("cancel the draft")
        self.assertEqual(d2.action, "message")


class ArxivProbeTest(unittest.TestCase):
    def test_arxiv_probe_parses_entry(self):
        from mini_kio.intelligence import retrieval_router as rr
        xml = b"""<?xml version="1.0"?>
<feed xmlns="http://www.w3.org/2005/Atom">
  <entry>
    <id>http://arxiv.org/abs/2301.00001v1</id>
    <title>  A Test Paper on Learning  </title>
    <published>2023-01-01T00:00:00Z</published>
    <summary>  This is the abstract text of the paper.  </summary>
  </entry>
</feed>"""
        r = rr.RetrievalRouter()
        with mock.patch.object(rr.requests, "get") as mget:
            mresp = mock.Mock(status_code=200, content=xml)
            mget.return_value = mresp
            res = r._try_arxiv("test learning", None)
        self.assertIsNotNone(res)
        self.assertEqual(res.source, "arXiv")
        self.assertIn("Test Paper", res.title)
        self.assertEqual(res.published_date, "2023-01-01")

    def test_arxiv_probe_in_evidence_chain(self):
        from mini_kio.intelligence import retrieval_router as rr
        probes = []
        r = rr.RetrievalRouter()
        for name in dir(r):
            if name.startswith("_try_"):
                probes.append(name)
        self.assertIn("_try_arxiv", probes)


if __name__ == "__main__":
    unittest.main()
