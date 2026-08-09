"""
System-level target-identity regression tests (2026-08-09 audit fixes).

Covers the bug class behind "Open ChatGPT -> Close it killed all of Chrome":
  BC-1  target collapse (capability string -> browser process)
  BC-2  tab -> app scope escalation
  BC-3  raw serialized targets stored as conversational referents
  BC-4  unverified open
  BC-5  response leakage of internal serialization
  BC-6  multi-action false-success summary
plus the new capabilities (context-aware desktop state, state-aware media).
"""

import os
import sys
import unittest
from unittest import mock

sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..")))
os.environ.setdefault("KIO_TEST_MODE", "1")

from mini_kio.core.target_ref import parse_target, safe_target_name, parse_capability_string


class TargetRefTest(unittest.TestCase):
    """BC-1/BC-3/BC-5: canonical target identity."""

    def test_capability_string_parses_to_webapp(self):
        ref = parse_target("chrome::open_url::https://chat.openai.com::chatgpt")
        self.assertEqual(ref.kind, "webapp")
        self.assertEqual(ref.name, "chatgpt")
        self.assertEqual(ref.browser, "chrome")
        self.assertEqual(ref.url, "https://chat.openai.com")
        self.assertEqual(ref.capability, "open_url")

    def test_safe_name_never_leaks_capability_chain(self):
        name = safe_target_name("chrome::open_url::https://chat.openai.com::chatgpt")
        self.assertEqual(name, "chatgpt")
        self.assertNotIn("::", name)
        self.assertNotIn("http", name)

    def test_safe_name_never_leaks_url(self):
        name = safe_target_name("https://chat.openai.com")
        self.assertNotIn("http", name)

    def test_safe_name_preserves_media_query_case(self):
        name = safe_target_name("never gonna give you up")
        self.assertEqual(name, "never gonna give you up")

    def test_browser_name_is_browser_kind(self):
        self.assertEqual(parse_target("chrome").kind, "browser")
        self.assertEqual(parse_target("edge").kind, "browser")

    def test_webapp_hint_kind(self):
        self.assertEqual(parse_target("chatgpt").kind, "webapp")
        self.assertEqual(parse_target("telegram").kind, "webapp")

    def test_parse_capability_string_helper(self):
        parts = parse_capability_string("chrome::open_url::https://chat.openai.com::chatgpt")
        self.assertIsNotNone(parts)
        self.assertEqual(parts["name"], "chatgpt")
        self.assertEqual(parts["browser"], "chrome")


class CloseAppNoEscalationTest(unittest.TestCase):
    """BC-1/BC-2: close_app must NEVER collapse a web-app target into the
    host browser process."""

    @mock.patch("mini_kio.core.app_operator._find_matching_process_pid")
    def test_close_capability_target_does_not_kill_browser(self, mock_pid):
        from mini_kio.core.app_operator import close_app

        mock_pid.return_value = 12345
        result = close_app("chrome::open_url::https://chat.openai.com::chatgpt")
        # No capability session + no connector in test env -> truthful failure,
        # and crucially the process-discovery kill path is NEVER reached.
        mock_pid.assert_not_called()
        self.assertFalse(result.get("success"))
        self.assertIn("Couldn't find", result.get("message", ""))

    @mock.patch("mini_kio.core.app_operator._find_matching_process_pid")
    def test_close_webapp_name_does_not_kill_browser(self, mock_pid):
        from mini_kio.core.app_operator import close_app

        mock_pid.return_value = 12345
        result = close_app("chatgpt")
        mock_pid.assert_not_called()
        self.assertFalse(result.get("success"))
        self.assertIn("Couldn't find", result.get("message", ""))

    def test_close_browser_name_still_native_path(self):
        # Explicit "close chrome" is a browser-scope request: it must still
        # resolve through the native registry path (not the web-target path).
        from mini_kio.core.app_operator import _find_in_registry

        self.assertTrue(_find_in_registry("chrome") is not None)


class ContextReferentSanitizationTest(unittest.TestCase):
    """BC-3: stored conversational referents must be user-safe names."""

    def test_raw_capability_target_not_stored_as_referent(self):
        from mini_kio.core.context_manager import get_session_context

        ctx = get_session_context("test_ref_sanitize")
        ctx.update(
            {
                "success": True,
                "target": "chrome::open_url::https://chat.openai.com::chatgpt",
                "action": "execute_capability",
            },
            "open chatgpt",
        )
        self.assertEqual(ctx.last_target, "chatgpt")
        self.assertEqual(ctx.active_entity, "chatgpt")

    def test_pronoun_resolution_uses_safe_referent(self):
        from mini_kio.core.context_manager import get_session_context

        ctx = get_session_context("test_ref_pronoun")
        ctx.update(
            {
                "success": True,
                "target": "chrome::open_url::https://chat.openai.com::chatgpt",
                "action": "execute_capability",
            },
            "open chatgpt",
        )
        resolved = ctx.resolved_text("close it")
        self.assertEqual(resolved, "close chatgpt")


class ResponseFormatterSafeNameTest(unittest.TestCase):
    """BC-5: responses never leak internal serialization."""

    def test_close_format_sanitizes_capability_target(self):
        from mini_kio.core.runtime_response_formatter import format_close_app

        msg = format_close_app(
            "chrome::open_url::https://chat.openai.com::chatgpt",
            True,
            {"outcome_class": "SUCCESS", "verification_status": "passed"},
        )
        self.assertIn("ChatGPT", msg)
        self.assertNotIn("::", msg)
        self.assertNotIn("http", msg)

    def test_open_format_sanitizes_capability_target(self):
        from mini_kio.core.runtime_response_formatter import format_open_app

        msg = format_open_app("chrome::open_url::https://chat.openai.com::chatgpt", True, "ok")
        self.assertIn("ChatGPT", msg)
        self.assertNotIn("::", msg)


class MultiStepTruthfulnessTest(unittest.TestCase):
    """BC-6: multi-action aggregation must be truthful."""

    def test_summary_partial_success(self):
        from mini_kio.core.command_router import _summarize_steps

        steps = [
            {"action": "open", "target": "chatgpt"},
            {"action": "open", "target": "telegram"},
        ]
        results = [
            {"success": True, "blocked": False},
            {"success": False, "blocked": False},
        ]
        summary = _summarize_steps(steps, results)
        self.assertIn("Opened", summary)
        self.assertIn("couldn't", summary)
        self.assertIn("Telegram", summary)
        self.assertNotIn("done -", summary)

    def test_summary_all_success(self):
        from mini_kio.core.command_router import _summarize_steps

        steps = [
            {"action": "open", "target": "chatgpt"},
            {"action": "open", "target": "telegram"},
        ]
        results = [
            {"success": True, "blocked": False},
            {"success": True, "blocked": False},
        ]
        summary = _summarize_steps(steps, results)
        self.assertIn("ChatGPT", summary)
        self.assertIn("Telegram", summary)
        self.assertNotIn("couldn't", summary)

    def test_summary_all_failed(self):
        from mini_kio.core.command_router import _summarize_steps

        steps = [{"action": "open", "target": "chatgpt"}]
        results = [{"success": False, "blocked": False}]
        summary = _summarize_steps(steps, results)
        self.assertIn("couldn't", summary)

    def test_execute_multi_step_does_not_abort_on_first_failure(self):
        # A failing first step must not prevent the second step from executing.
        from mini_kio.core.command_router import _execute_multi_step

        steps = [
            {"action": "open", "target": "chatgpt"},
            {"action": "open", "target": "telegram"},
        ]
        with mock.patch(
            "mini_kio.core.command_router._run_single_step",
            side_effect=[
                {"success": False, "blocked": False, "message": "no"},
                {"success": True, "blocked": False, "message": "ok"},
            ],
        ):
            result = _execute_multi_step(steps)
        self.assertEqual(len(result["results"]), 2)
        self.assertFalse(result["success"])  # not all succeeded
        self.assertIn("couldn't", result["message"])


class CapabilityClassifierTest(unittest.TestCase):
    """Capability A/C: intent classification for the new capabilities."""

    def _classify(self, text):
        from mini_kio.core.pipeline import _IntentClassifier

        return _IntentClassifier().classify(text, text)

    def test_whats_open_is_desktop_state(self):
        from mini_kio.core.pipeline.types import IntentType

        d = self._classify("what's open")
        self.assertEqual(d.intent_type, IntentType.BROWSER_TABS)

    def test_what_am_i_using(self):
        from mini_kio.core.pipeline.types import IntentType

        d = self._classify("what am i using")
        self.assertEqual(d.intent_type, IntentType.BROWSER_TABS)

    def test_whats_playing_is_media_transport(self):
        from mini_kio.core.pipeline.types import IntentType

        d = self._classify("what's playing")
        self.assertEqual(d.intent_type, IntentType.MEDIA_TRANSPORT)
        self.assertEqual(d.action, "now_playing")

    def test_focus_routes_to_browser_focus(self):
        from mini_kio.core.pipeline.types import IntentType

        d = self._classify("switch to telegram")
        self.assertEqual(d.intent_type, IntentType.BROWSER_FOCUS)

    def test_close_tab_phrasing(self):
        d = self._classify("close the chatgpt tab")
        self.assertEqual(d.action, "close_tab")
        self.assertEqual(d.target, "chatgpt")

    def test_close_browser_name(self):
        d = self._classify("close chrome")
        self.assertEqual(d.action, "close_app")
        self.assertEqual(d.target, "chrome")


class MediaNowPlayingTest(unittest.TestCase):
    """Capability C: state-aware media queries."""

    def test_now_playing_nothing(self):
        from mini_kio.media.media_manager import MediaManager

        mm = MediaManager.get_instance()
        mm._registry.clear()
        result = mm.now_playing()
        self.assertIn("Nothing is playing", result.get("message", ""))

    def test_now_playing_reports_session(self):
        from mini_kio.media.media_manager import MediaManager
        from mini_kio.media.media_session import MediaSession
        from mini_kio.media.media_state import MediaState, PlayerType

        mm = MediaManager.get_instance()
        mm._registry.clear()
        session = MediaSession(
            player=PlayerType.BROWSER,
            title="Never Gonna Give You Up",
            state=MediaState.PLAYING,
        )
        mm._registry.set("browser", session)
        result = mm.now_playing()
        self.assertTrue(result.get("success"))
        self.assertIn("Never Gonna Give You Up", result.get("message", ""))


if __name__ == "__main__":
    unittest.main()
