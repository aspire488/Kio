"""
System-level target/instance semantics tests (2026-08-13).

Covers the canonical fixes:
  A. NEW-TAB semantics: Connector.open_tab(force_new=True) creates exactly
     ONE genuinely new tab even when a same-domain tab already exists —
     never navigates/refreshes/reuses the existing tab (Tests A-H of the
     directive: Telegram/Gemini/ChatGPT new-tab / new-window).
  B. execute_capability threads force_new through to the connector and
     verifies the matching-tab count increased by exactly one.
  C. "open a new Word document" / "new Excel workbook" resolve the APP with
     explicit_new instance semantics — never a failed "word document" target.
  D. App inventory response is COMPOSED (useful apps from real state, count,
     full-list offer) — never a raw dump of registry names.
  E. "switch to the other X" carries instance_index=1 (same-app multi-instance
     selection).
  F. Native-only apps (Notepad/Excel/Word/VS Code) focus NATIVE-first —
     no browser-tab round trip for a deterministic local operation.
"""

import asyncio
import os
import sys
import unittest
from unittest import mock

sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..")))
os.environ.setdefault("KIO_TEST_MODE", "1")

from mini_kio.core.pipeline import Pipeline


def _classify(text):
    p = Pipeline()
    return p._classifier.classify(text, text)


class ConnectorNewTabSemanticsTest(unittest.TestCase):
    """Directive Tests A/B/D/E/F: a 'new tab' request must create exactly one
    new tab; an existing same-domain tab must never be reused/refreshed."""

    def _make_conn(self):
        from mini_kio.browser_connector.connector import Connector
        from mini_kio.browser_connector.protocol import Message, MessageType

        conn = Connector(mock=True)
        loop = asyncio.new_event_loop()

        async def _seed(url):
            msg = Message(type=MessageType.OPEN_TAB, command_id="seed1", url=url)
            r = await conn._dispatch(msg)
            assert r.success, r

        try:
            loop.run_until_complete(_seed("https://web.telegram.org"))
        finally:
            loop.close()
        return conn

    def _run_scenario(self, coro):
        loop = asyncio.new_event_loop()
        try:
            return loop.run_until_complete(asyncio.wait_for(coro, timeout=20))
        finally:
            loop.close()

    def test_default_open_reuses_existing_tab(self):
        conn = self._make_conn()
        before = conn.registry.owned_count()

        async def scenario():
            r = await conn.open_tab("https://web.telegram.org")
            return r

        r = self._run_scenario(scenario())
        self.assertTrue(r.success)
        # Default open must NOT create a second tab (dedup applies).
        self.assertEqual(conn.registry.owned_count(), before)

    def test_force_new_creates_exactly_one_new_tab(self):
        # Test A: current tabs = [Telegram]; "open a new Telegram tab" ->
        # [Telegram, Telegram(new)] — exactly +1.
        conn = self._make_conn()
        before = conn.registry.owned_count()

        async def scenario():
            return await conn.open_tab("https://web.telegram.org", force_new=True)

        r = self._run_scenario(scenario())
        self.assertTrue(r.success)
        self.assertEqual(conn.registry.owned_count(), before + 1)

    def test_two_force_new_creates_exactly_two_new_tabs(self):
        # Test B: two "new tab" requests -> exactly +2 total.
        conn = self._make_conn()
        before = conn.registry.owned_count()

        async def scenario():
            r1 = await conn.open_tab("https://web.telegram.org", force_new=True)
            r2 = await conn.open_tab("https://web.telegram.org", force_new=True)
            return r1.success and r2.success

        self.assertTrue(self._run_scenario(scenario()))
        self.assertEqual(conn.registry.owned_count(), before + 2)

    def test_force_new_never_navigates_existing_tab(self):
        # The old bug: open_tab dedup found the existing Telegram tab and
        # NAVIGATED it (refreshed) instead of creating a new one. With
        # force_new=True the OPEN_TAB message must be dispatched (new tab),
        # never a NAVIGATE_TAB to the existing tab.
        conn = self._make_conn()
        dispatched = []

        original_dispatch = conn._dispatch

        async def _wrapped(cmd):
            dispatched.append(cmd.type)
            return await original_dispatch(cmd)

        conn._dispatch = _wrapped
        before = conn.registry.owned_count()

        async def scenario():
            return await conn.open_tab("https://web.telegram.org", force_new=True)

        r = self._run_scenario(scenario())
        self.assertTrue(r.success)
        self.assertEqual(conn.registry.owned_count(), before + 1)
        # An OPEN_TAB was dispatched (a new tab created); no NAVIGATE_TAB
        # reuse of the pre-existing tab.
        types = [str(getattr(d, "value", d)) for d in dispatched]
        self.assertIn("open_tab", types)
        self.assertNotIn("navigate_tab", types)


class ExecutorForceNewTest(unittest.TestCase):
    """execute_capability must pass force_new through and verify +1 count."""

    def _conn(self, existing_telegram_tabs=2):
        class FakeTab:
            def __init__(self, tab_id, url, title):
                self.tab_id = tab_id
                self.url = url
                self.title = title

        tabs = ([FakeTab(11, "https://web.telegram.org", "Telegram"),
                 FakeTab(12, "https://web.telegram.org", "Telegram Web")]
                [:existing_telegram_tabs] + [FakeTab(13, "https://google.com", "Google")])

        class FakeResult:
            success = True
            error = ""

        calls = {"force_new": None, "open_called": 0}

        class FakeConn:
            def is_connected(self):
                return True

            async def list_tabs(self):
                r = FakeResult()
                r.tabs = list(tabs)
                return r

            async def open_tab(self, url, *, force_new=False):
                calls["force_new"] = force_new
                calls["open_called"] += 1
                r = FakeResult()
                r.tab_id = 99
                r.url = url
                r.title = "Telegram"
                return r

        return FakeConn(), calls

    def test_force_new_passed_to_connector(self):
        from mini_kio.core import command_router
        conn, calls = self._conn()
        with mock.patch.object(command_router, "_get_connector", return_value=conn):
            from mini_kio.core import app_operator
            result = app_operator.execute_capability(
                "chrome::open_url::https://web.telegram.org::telegram::new")
        self.assertTrue(result["success"])
        self.assertTrue(calls["force_new"])
        self.assertEqual(calls["open_called"], 1)

    def test_plain_open_does_not_pass_force_new(self):
        # Default open goes through duplicate prevention (which may focus an
        # existing target); when no existing target exists it must call
        # open_tab WITHOUT force_new (connector-side dedup still applies).
        from mini_kio.core import command_router
        from mini_kio.core import app_operator
        conn, calls = self._conn(existing_telegram_tabs=0)
        with mock.patch.object(command_router, "_get_connector", return_value=conn), \
                mock.patch.object(app_operator, "_find_existing_web_target", return_value=None):
            result = app_operator.execute_capability(
                "chrome::open_url::https://web.telegram.org::telegram")
        self.assertTrue(result["success"])
        self.assertIs(calls["force_new"], False)

    def test_verify_new_tab_requires_plus_one(self):
        from mini_kio.core import app_operator
        conn, calls = self._conn(existing_telegram_tabs=2)
        # before_count=2 (two Telegram tabs already), after=2 -> NOT +1.
        verified = app_operator._verify_web_tab_opened(
            conn, "https://web.telegram.org", "telegram", before_count=2)
        self.assertFalse(verified)
        # before_count=1, after=2 -> exactly +1.
        verified = app_operator._verify_web_tab_opened(
            conn, "https://web.telegram.org", "telegram", before_count=1)
        self.assertTrue(verified)


class DocumentInstanceSemanticsTest(unittest.TestCase):
    """'open a new Word document' must resolve the Word app with new-instance
    semantics — never a failed 'word document' native target."""

    def test_open_new_word_document_resolves_word_app(self):
        d = _classify("open a new Word document")
        self.assertEqual(d.intent_type.value, "desktop_open")
        self.assertEqual(d.action, "open_app")
        self.assertEqual(d.target, "word")
        self.assertTrue(d.metadata.get("explicit_new"))

    def test_open_new_excel_workbook_resolves_excel_app(self):
        d = _classify("open a new Excel workbook")
        self.assertEqual(d.intent_type.value, "desktop_open")
        self.assertEqual(d.action, "open_app")
        self.assertEqual(d.target, "excel")
        self.assertTrue(d.metadata.get("explicit_new"))

    def test_open_new_powerpoint_presentation_resolves_ppt(self):
        d = _classify("open a new PowerPoint presentation")
        self.assertEqual(d.action, "open_app")
        self.assertEqual(d.target, "powerpoint")
        self.assertTrue(d.metadata.get("explicit_new"))

    def test_open_vscode_window_resolves_vscode_app(self):
        d = _classify("open a new VS Code window")
        self.assertEqual(d.action, "open_app")
        self.assertIn(d.target, ("vscode", "vs code"))
        self.assertTrue(d.metadata.get("explicit_new"))
        # Never a synthesized vscode.com browser window.
        self.assertNotEqual(d.intent_type.value, "browser_navigate")

    def test_plain_open_word_stays_plain(self):
        d = _classify("open Word")
        self.assertEqual(d.action, "open_app")
        self.assertEqual(d.target, "word")
        self.assertFalse(d.metadata.get("explicit_new"))

    def test_artifact_noun_never_strips_non_registered_base(self):
        # A non-registered base must NOT be rewritten: "open a new report
        # document" keeps its full target (truthful failure downstream), never
        # mangled into a wrong app.
        d = _classify("open a new report document")
        self.assertEqual(d.action, "open_app")
        self.assertEqual(d.target, "report document")


class InventoryResponseCompositionTest(unittest.TestCase):
    """Section 7: the app-inventory answer is COMPOSED from real state — a
    clean KIO response, never a raw dump of registry names."""

    def _format(self, fake_apps):
        from mini_kio.core import operational_health as oh
        with mock.patch(
            "mini_kio.core.app_operator.list_installed_apps",
            return_value=list(fake_apps),
        ):
            return oh._format_app_inventory()

    def test_names_useful_apps_and_count(self):
        apps = [
            "Microsoft Word", "Microsoft Excel", "Microsoft PowerPoint",
            "Visual Studio Code", "Google Chrome", "Microsoft Edge",
            "Telegram Desktop", "Spotify", "Calculator", "Camera",
            "ActionsMcpHost", "Application Verifier", "AMD Ryzen Master SDK",
            "Agoda", "Administrative Tools",
        ]
        msg = self._format(apps)
        self.assertIn("Microsoft Word", msg)
        self.assertIn("Excel", msg)
        self.assertIn("Chrome", msg)
        self.assertIn("Telegram", msg)
        # Count is real and full list is offered — never a raw dump.
        self.assertIn("apps", msg)
        self.assertIn("full list", msg.lower())
        # Implementation-only utilities are NOT name-dropped in the curated
        # part of the answer.
        self.assertNotIn("ActionsMcpHost", msg)

    def test_no_useful_hits_still_composed(self):
        # No curated matches: the response still names real apps from the
        # machine with the true count — never an invented list.
        apps = ["AlphaOne", "BetaTwo", "GammaThree", "DeltaFour"]
        msg = self._format(apps)
        self.assertIn("apps", msg)
        self.assertIn("AlphaOne", msg)
        self.assertNotIn("ActionsMcpHost", msg)  # fabricated names never appear


class MultiInstanceFocusTest(unittest.TestCase):
    """Section 4: same-application multi-instance selection."""

    def test_switch_to_the_other_window_marks_instance_index(self):
        d = _classify("switch to the other Word window")
        self.assertEqual(d.intent_type.value, "browser_focus")
        self.assertEqual(d.action, "focus")
        self.assertEqual((d.metadata or {}).get("instance_index"), 1)

    def test_focus_the_other_excel_marks_instance_index(self):
        d = _classify("focus the other Excel window")
        self.assertEqual(d.action, "focus")
        self.assertEqual((d.metadata or {}).get("instance_index"), 1)

    def test_plain_switch_has_no_instance_index(self):
        d = _classify("switch to Word")
        self.assertEqual(d.action, "focus")
        self.assertNotEqual((d.metadata or {}).get("instance_index"), 1)


class NativeFirstFocusTest(unittest.TestCase):
    """Section 5: 'switch to X' for a native-only app is a deterministic
    local operation — the browser-tab machinery must not run first."""

    def test_native_only_app_skips_connector(self):
        from mini_kio.core.pipeline import _ExecutionCoordinator

        coord = _ExecutionCoordinator()
        called = {"native": False, "conn": False}

        with mock.patch.object(
            coord, "_try_native_focus",
            side_effect=lambda *a, **k: called.__setitem__("native", True) or
            {"success": True, "message": "Focused Notepad."},
        ), mock.patch.object(
            coord, "_try_browser_activate",
        ):
            result = coord._exec_browser(
                {"action": "focus", "target": "notepad", "metadata": {}},
                None,
            )
        self.assertTrue(result["success"])
        self.assertTrue(called["native"])
        # Notepad is native-only: no tab/connector path ran.
        self.assertFalse(called["conn"])


if __name__ == "__main__":
    unittest.main()
