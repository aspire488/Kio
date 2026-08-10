"""
Pre-Slice-9 System Execution Corrections — targeted tests.

Covers (Part XII classes A-S):
  A. native application resolution        B. web target resolution
  C. ambiguous target resolution          D. installed vs unavailable app
  E. packaged/UWP application resolution  F. browser target preservation
  G. target-scope close                   H. contextual "it"
  I. lock state                           J. unlock/authentication-required
  K. KIO uptime                           L. system uptime
  M. boot/session timestamp               N. natural-language variants
  O. knowledge-vs-operational routing     P. no URL/ID/PID/internal leakage
  Q. no browser substitution              R. no false success
  S. no process-scope escalation
"""

import os
import sys
import unittest
from unittest import mock

sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..")))
os.environ.setdefault("KIO_TEST_MODE", "1")

from mini_kio.core.routing_utils import (
    get_browser_routing, probe_app_existence, probe_registered_app,
)
from mini_kio.core.app_operator import (
    _web_url_for_open, _find_installed_app, launch_app, close_app,
)
from mini_kio.core.pipeline import Pipeline
from mini_kio.core.pipeline.types import IntentType


def _decision(text: str):
    """Deterministic classifier decision (no LLM, no execution)."""
    from mini_kio.core.context_manager import get_session_context
    p = Pipeline()
    ctx = get_session_context("test_exec_corrections")
    normalized = p._normalizer.run(text.strip(), ctx)
    return p._classifier.classify(normalized, text)


# ---------------------------------------------------------------------------
# A. Native application resolution
# ---------------------------------------------------------------------------
class NativeResolutionTest(unittest.TestCase):
    def test_registered_native_app_routes_native(self):
        r = get_browser_routing("vscode")
        self.assertEqual(r["route_type"], "native")
        self.assertEqual(r["action"], "open_app")

    def test_generic_discovery_routes_native(self):
        with mock.patch("mini_kio.core.routing_utils._find_installed_app",
                        return_value={"kind": "exe", "target": "C:/x/Y.exe", "display": "y"}):
            r = get_browser_routing("some installed thing")
            self.assertEqual(r["route_type"], "native")

    def test_probe_registered_uri_app_is_installed(self):
        # Microsoft Store has a uri but no resolvable path — still installed.
        self.assertTrue(probe_registered_app("microsoft store"))

    def test_probe_false_for_unknown(self):
        with mock.patch("mini_kio.core.routing_utils._find_installed_app", return_value=None):
            self.assertFalse(probe_app_existence("definitely not an app 9876"))


# ---------------------------------------------------------------------------
# B. Web target resolution
# ---------------------------------------------------------------------------
class WebTargetResolutionTest(unittest.TestCase):
    def test_known_web_app_routes_browser(self):
        r = get_browser_routing("chatgpt")
        self.assertEqual(r["route_type"], "browser_fallback")
        self.assertIn("chat.openai.com", r["target"])

    def test_explicit_url_routes_browser(self):
        r = get_browser_routing("example.com")
        self.assertEqual(r["route_type"], "browser_fallback")

    def test_single_word_domain_synthesis(self):
        self.assertEqual(_web_url_for_open("github"), "https://github.com")

    def test_explicit_url_web_url_for_open(self):
        self.assertEqual(_web_url_for_open("chatgpt.com"), "https://chatgpt.com")


# ---------------------------------------------------------------------------
# C/D. Ambiguous + installed vs unavailable — no silent web substitution
# ---------------------------------------------------------------------------
class NoSilentWebSubstitutionTest(unittest.TestCase):
    def test_multisword_never_synthesized_as_domain(self):
        # This was THE bug: "da vinci resolve" -> davinciresolve.com
        self.assertIsNone(_web_url_for_open("da vinci resolve"))
        self.assertIsNone(_web_url_for_open("microsoft store"))

    def test_multisword_unknown_not_found_route(self):
        with mock.patch("mini_kio.core.routing_utils._find_installed_app", return_value=None):
            r = get_browser_routing("da vinci resolve")
            self.assertEqual(r["route_type"], "not_found")

    def test_launch_not_installed_truthful(self):
        with mock.patch("mini_kio.core.app_operator._find_installed_app", return_value=None):
            r = launch_app("nonexistent thing 1234")
            self.assertFalse(r["success"])
            self.assertIn("couldn't find", r["message"].lower())
            self.assertNotIn("http", r["message"].lower())

    def test_web_url_for_open_rejects_multisword_searchlike(self):
        self.assertIsNone(_web_url_for_open("best cheap laptops"))


# ---------------------------------------------------------------------------
# E. Packaged/UWP application resolution
# ---------------------------------------------------------------------------
class UWPResolutionTest(unittest.TestCase):
    def test_microsoft_store_native(self):
        r = get_browser_routing("microsoft store")
        self.assertEqual(r["route_type"], "native")

    def test_settings_native(self):
        self.assertTrue(probe_registered_app("settings"))


# ---------------------------------------------------------------------------
# F. Browser target preservation
# ---------------------------------------------------------------------------
class BrowserTargetPreservationTest(unittest.TestCase):
    def test_open_in_chrome_keeps_web(self):
        d = _decision("open chatgpt in chrome")
        self.assertEqual(d.intent_type, IntentType.BROWSER_NAVIGATE)


# ---------------------------------------------------------------------------
# G/H. Target-scope close + contextual "it"
# ---------------------------------------------------------------------------
class TargetScopeCloseTest(unittest.TestCase):
    def test_close_web_target_is_tab_scope_not_browser_process(self):
        # Web-scope close must go through the tab-scope path, never kill Chrome.
        with mock.patch("mini_kio.core.app_operator._close_web_target") as m:
            from mini_kio.core.app_operator import close_app
            m.return_value = {"success": True, "message": "Closed ChatGPT."}
            r = close_app("chatgpt")
            self.assertTrue(r["success"])
            m.assert_called_once()

    def test_close_unknown_never_kills_browser(self):
        with mock.patch("mini_kio.core.app_operator._find_installed_app", return_value=None):
            r = close_app("definitely not installed 777")
            self.assertFalse(r["success"])
            self.assertNotIn("chrome", r["message"].lower())


# ---------------------------------------------------------------------------
# I/J. Lock state + unlock (authentication-required, no bypass)
# ---------------------------------------------------------------------------
class LockUnlockTest(unittest.TestCase):
    def test_lock_routes_system(self):
        d = _decision("lock my pc")
        self.assertEqual(d.intent_type, IntentType.SYSTEM)
        self.assertEqual(d.action, "lock_system")

    def test_secure_my_computer_routes_lock(self):
        d = _decision("secure my computer")
        self.assertEqual(d.action, "lock_system")

    def test_unlock_routes_system(self):
        d = _decision("unlock")
        self.assertEqual(d.action, "unlock_system")

    def test_unlock_my_computer(self):
        d = _decision("unlock my computer")
        self.assertEqual(d.action, "unlock_system")

    def test_lock_state_query_routes_operational(self):
        d = _decision("is my computer locked")
        self.assertEqual(d.intent_type, IntentType.OPERATIONAL)
        self.assertEqual(d.action, "lock_state")

    def test_unlock_locked_reports_auth_required(self):
        from mini_kio.core import system_operator
        with mock.patch("mini_kio.core.system_operator.is_workstation_locked", return_value=True):
            r = system_operator.unlock_system()
            self.assertTrue(r["success"])
            self.assertNotIn("unlocked", r["message"].lower())
            self.assertIn("sign in", r["message"].lower())

    def test_unlock_unlocked_reports_truth(self):
        from mini_kio.core import system_operator
        with mock.patch("mini_kio.core.system_operator.is_workstation_locked", return_value=False):
            r = system_operator.unlock_system()
            self.assertIn("isn't locked", r["message"].lower())

    def test_unlock_unknown_is_honest(self):
        from mini_kio.core import system_operator
        with mock.patch("mini_kio.core.system_operator.is_workstation_locked", return_value=None):
            r = system_operator.unlock_system()
            self.assertIn("can't confirm", r["message"].lower())

    def test_lock_unconfirmed_reports_truthfully(self):
        """lock_system must NOT claim 'Locked' when OS state never confirms.

        Headless/RDP-disconnected sessions accept LockWorkStation but never
        show a secure desktop; claiming success there is a fabricated result.
        """
        from mini_kio.core import system_operator
        with mock.patch.object(
            system_operator, "is_workstation_locked", return_value=False
        ) as mock_locked, mock.patch.object(system_operator.subprocess, "run"):
            r = system_operator.lock_system()
            self.assertTrue(r["success"])
            self.assertNotIn("Locked", r["message"])
            self.assertIn("couldn't confirm", r["message"].lower())
            self.assertGreaterEqual(mock_locked.call_count, 1)

    def test_lock_confirmed_reports_locked(self):
        """When OS state confirms the lock, report 'Locked'."""
        from mini_kio.core import system_operator
        with mock.patch.object(
            system_operator, "is_workstation_locked", return_value=True
        ), mock.patch.object(system_operator.subprocess, "run"):
            r = system_operator.lock_system()
            self.assertTrue(r["success"])
            self.assertEqual(r["message"], "Locked")

    def test_execute_action_unlock_system_no_arg(self):
        """execute_action must invoke no-arg system handlers correctly.

        Regression: unlock_system/lock_state were added to the ACTION_REGISTRY
        without no-arg dispatch branches, so the generic handler(target) call
        raised "takes 0 positional arguments but 1 was given" and the live bot
        collapsed the failure to "Done.".
        """
        from mini_kio.core import execution_boundary as eb
        with mock.patch.object(eb, "_in_test_mode", return_value=False), mock.patch.object(
            eb, "get_runtime", return_value=None
        ):
            r = eb.execute_action("unlock_system")
            self.assertTrue(r.get("success"))
            self.assertIn("isn't locked", r["message"].lower())
            r2 = eb.execute_action("lock_state")
            self.assertIn("locked", r2["message"].lower())


# ---------------------------------------------------------------------------
# K/L/M. Uptime truth
# ---------------------------------------------------------------------------
class UptimeTruthTest(unittest.TestCase):
    def test_kio_uptime_routes(self):
        d = _decision("how long have you been running")
        self.assertEqual(d.action, "uptime")

    def test_system_uptime_routes(self):
        d = _decision("how long has my pc been on")
        self.assertEqual(d.action, "system_uptime")

    def test_system_uptime_has_boot_timestamp(self):
        from mini_kio.core import operational_health as ops
        with mock.patch.object(ops, "_system_metrics",
                               return_value={"system_uptime_s": 190000.0}):
            with mock.patch.object(ops, "_system_boot_ts", return_value=1760000000.0):
                with mock.patch.object(ops, "_fast_startup_enabled", return_value=False):
                    msg = ops.format_system_uptime()
                    self.assertIn("system session", msg)
                    self.assertIn("running for", msg)
                    self.assertIn("started on", msg)

    def test_system_uptime_fast_startup_caveat(self):
        from mini_kio.core import operational_health as ops
        with mock.patch.object(ops, "_system_metrics",
                               return_value={"system_uptime_s": 190000.0}):
            with mock.patch.object(ops, "_system_boot_ts", return_value=1760000000.0):
                with mock.patch.object(ops, "_fast_startup_enabled", return_value=True):
                    msg = ops.format_system_uptime()
                    self.assertIn("Fast Startup", msg)
                    self.assertIn("can't confirm from uptime alone", msg)


# ---------------------------------------------------------------------------
# N. Natural-language variants
# ---------------------------------------------------------------------------
class OpenVerbFamilyTest(unittest.TestCase):
    def test_open_launch_start_run_fireup(self):
        for q in ["open vscode", "launch vscode", "start vscode", "run vscode", "fire up vscode"]:
            with self.subTest(q=q):
                d = _decision(q)
                self.assertEqual(d.intent_type, IntentType.DESKTOP_OPEN, q)
                self.assertEqual(d.target, "vscode", q)

    def test_run_a_search_not_stolen(self):
        d = _decision("run a search for cats")
        self.assertNotEqual(d.intent_type, IntentType.DESKTOP_OPEN)

    def test_start_timer_not_stolen(self):
        d = _decision("start a timer")
        self.assertNotEqual(d.intent_type, IntentType.DESKTOP_OPEN)


# ---------------------------------------------------------------------------
# O. Knowledge-vs-operational routing (no theft)
# ---------------------------------------------------------------------------
class KnowledgeRoutingTest(unittest.TestCase):
    def test_what_is_uptime_is_knowledge(self):
        d = _decision("what is uptime")
        self.assertNotEqual(d.intent_type, IntentType.OPERATIONAL)

    def test_what_is_status_is_knowledge(self):
        d = _decision("what is status")
        self.assertNotEqual(d.intent_type, IntentType.OPERATIONAL)

    def test_what_is_microsoft_store_is_knowledge(self):
        d = _decision("what is microsoft store")
        self.assertNotEqual(d.intent_type, IntentType.DESKTOP_OPEN)
        self.assertNotEqual(d.intent_type, IntentType.BROWSER_NAVIGATE)

    def test_what_is_vscode_is_knowledge(self):
        d = _decision("what is vscode")
        self.assertNotEqual(d.intent_type, IntentType.DESKTOP_OPEN)

    def test_what_is_ram_is_knowledge(self):
        d = _decision("what is ram")
        self.assertNotEqual(d.intent_type, IntentType.OPERATIONAL)

    def test_what_is_running_time_is_knowledge(self):
        d = _decision("what is running time")
        self.assertNotEqual(d.intent_type, IntentType.BROWSER_TABS)

    def test_whats_open_source_is_knowledge(self):
        d = _decision("what's open source")
        self.assertNotEqual(d.intent_type, IntentType.BROWSER_TABS)

    def test_how_does_fast_startup_work_is_knowledge(self):
        d = _decision("how does fast startup work")
        self.assertNotEqual(d.intent_type, IntentType.OPERATIONAL)


# ---------------------------------------------------------------------------
# P/Q/R/S. Leakage, substitution, false success, scope escalation
# ---------------------------------------------------------------------------
class ResponseSafetyTest(unittest.TestCase):
    def test_no_pid_in_unlock_message(self):
        from mini_kio.core import system_operator
        with mock.patch("mini_kio.core.system_operator.is_workstation_locked", return_value=None):
            msg = system_operator.unlock_system()["message"]
            self.assertNotIn("pid", msg.lower())

    def test_launch_message_never_says_opened_for_unknown(self):
        with mock.patch("mini_kio.core.app_operator._find_installed_app", return_value=None):
            r = launch_app("ghost app 555")
            self.assertFalse(r["success"])

    def test_browser_routing_never_returns_execute_for_unknown_app(self):
        with mock.patch("mini_kio.core.routing_utils._find_installed_app", return_value=None):
            r = get_browser_routing("da vinci resolve")
            self.assertNotEqual(r["route_type"], "browser_fallback")


# ---------------------------------------------------------------------------
# T. FUNDAMENTAL INVARIANT — disclosed web fallback (never hide a modality
#    fallback; useful != misleading). Generic, not per-application.
# ---------------------------------------------------------------------------
class DisclosedWebFallbackTest(unittest.TestCase):
    def test_launch_single_word_missing_discloses_fallback(self):
        """B: app not installed + legitimate web version -> open web WITH disclosure."""
        with mock.patch("mini_kio.core.app_operator._find_installed_app", return_value=None):
            r = launch_app("winrar")
        self.assertTrue(r["success"])
        self.assertEqual(r.get("modality"), "web_fallback")
        self.assertIn("couldn't find", r["message"].lower())
        self.assertIn("web version", r["message"].lower())
        self.assertNotIn("opened winrar.", r["message"].lower())

    def test_launch_dual_modality_missing_discloses_fallback(self):
        """B: native identity registered (Telegram) but not installed -> disclosed web."""
        with mock.patch("mini_kio.core.app_operator._resolve_path", return_value=None), \
             mock.patch("mini_kio.core.app_operator._find_installed_app", return_value=None):
            r = launch_app("telegram")
        self.assertTrue(r["success"])
        self.assertEqual(r.get("modality"), "web_fallback")
        self.assertIn("couldn't find", r["message"].lower())
        self.assertIn("web version", r["message"].lower())

    def test_launch_multiword_missing_no_fabricated_fallback(self):
        """F: no native + no valid web target -> truthful failure (never fabricate)."""
        with mock.patch("mini_kio.core.app_operator._find_installed_app", return_value=None):
            r = launch_app("da vinci resolve")
        self.assertFalse(r["success"])
        self.assertIn("couldn't find", r["message"].lower())
        self.assertIn("web version", r["message"].lower())
        self.assertNotIn("http", r["message"].lower())

    def test_launch_unknown_no_web_version_failure(self):
        with mock.patch("mini_kio.core.app_operator._find_installed_app", return_value=None):
            r = launch_app("nonexistent thing 1234")
        self.assertFalse(r["success"])
        self.assertIn("couldn't find", r["message"].lower())
        self.assertIn("usable web version", r["message"].lower())
        self.assertNotIn("http", r["message"].lower())

    def test_native_launch_failure_discloses_fallback(self):
        """E: native installed but launch failed -> disclosed web fallback."""
        with mock.patch("mini_kio.core.app_operator._resolve_path",
                        return_value="C:/fake/Telegram.exe"), \
             mock.patch("mini_kio.core.app_operator._launch_from_info",
                        return_value={"success": False, "message": "boom"}), \
             mock.patch("mini_kio.core.app_operator._find_installed_app", return_value=None):
            r = launch_app("telegram")
        self.assertTrue(r["success"])
        self.assertEqual(r.get("modality"), "web_fallback")
        self.assertIn("couldn't launch", r["message"].lower())
        self.assertIn("web version", r["message"].lower())

    def test_close_after_web_fallback_resolves_web_target(self):
        """J: after a disclosed fallback, 'close it' resolves to the web target."""
        from mini_kio.core.app_operator import _close_web_target
        with mock.patch("mini_kio.core.app_operator._find_installed_app", return_value=None), \
             mock.patch("mini_kio.core.app_operator._close_web_target",
                        return_value={"success": True, "message": "Closed Winrar."}) as m:
            r = close_app("winrar")
        self.assertTrue(r["success"])
        m.assert_called_once()

    def test_close_dual_modality_web_fallback(self):
        """Registered native not running but web session may exist -> web scope."""
        from mini_kio.core.app_operator import _close_web_target
        with mock.patch("mini_kio.core.app_operator._find_matching_process_pid", return_value=None), \
             mock.patch("mini_kio.core.app_operator._find_installed_app", return_value=None), \
             mock.patch("mini_kio.core.app_operator._close_web_target",
                        return_value={"success": True, "message": "Closed Telegram."}) as m:
            r = close_app("telegram")
        self.assertTrue(r["success"])
        m.assert_called_once()

    def test_close_discovered_shortcut_app_never_web_scope(self):
        """Discovered shortcut-installed app (e.g. Cursor): close must stay at
        native scope. When the native process is running it closes natively;
        when it is not running it reports 'wasn't running' — it must NEVER fall
        through to a synthesized <name>.com web scope, because the native app
        IS installed (a disclosed web fallback only opens when native is
        absent)."""
        from mini_kio.core.app_operator import _close_web_target
        discovered = {"kind": "shortcut", "target": "C:/Users/x/Start Menu/Programs/Cursor.lnk"}
        with mock.patch("mini_kio.core.app_operator._find_installed_app",
                        return_value=discovered), \
             mock.patch("mini_kio.core.app_operator._find_matching_process_pid",
                        return_value=None), \
             mock.patch("mini_kio.core.app_operator._close_web_target") as m:
            r = close_app("cursor")
        self.assertFalse(r["success"])
        self.assertEqual(r.get("failure_class"), "not_running")
        self.assertIn("wasn't running", r["message"].lower())
        m.assert_not_called()

    def test_close_discovered_shortcut_app_running_closes_native(self):
        """Discovered shortcut-installed app with a running process: close
        resolves natively via the discovered process name (never web scope)."""
        with mock.patch("mini_kio.core.app_operator._find_installed_app",
                        return_value={"kind": "shortcut",
                                      "target": "C:/x/Start Menu/Programs/Cursor.lnk"}), \
             mock.patch("mini_kio.core.app_operator._find_matching_process_pid",
                        return_value=4242), \
             mock.patch("mini_kio.core.app_operator._terminate_with_verification",
                        return_value={"success": True, "message": "Closed Cursor.",
                                      "pid": 4242, "verified_terminated": True,
                                      "outcome_class": "SUCCESS",
                                      "verification_status": "passed"}), \
             mock.patch("mini_kio.core.app_operator._close_web_target") as m:
            r = close_app("cursor")
        self.assertTrue(r["success"])
        self.assertIn("closed cursor", r["message"].lower())
        m.assert_not_called()

    def test_routing_dual_modality_routes_through_executor(self):
        """Classifier consistency: dual-modality name missing -> executor path
        (disclosed fallback), never a silent browser_fallback."""
        with mock.patch("mini_kio.core.routing_utils._resolve_path", return_value=None), \
             mock.patch("mini_kio.core.routing_utils._find_installed_app", return_value=None):
            r = get_browser_routing("telegram")
        self.assertEqual(r["route_type"], "not_found")
        self.assertEqual(r["action"], "open_app")

    def test_routing_pure_web_app_stays_browser(self):
        """Pure web app (no native identity) stays browser_fallback — no disclosure needed."""
        r = get_browser_routing("chatgpt")
        self.assertEqual(r["route_type"], "browser_fallback")

    def test_formatter_preserves_fallback_disclosure(self):
        """H: formatter must never collapse a disclosed fallback into 'Opened X.'"""
        from mini_kio.core.runtime_response_formatter import format_result
        details = {
            "success": True,
            "modality": "web_fallback",
            "message": "I couldn't find winrar installed on your computer, so I opened its web version in your browser.",
        }
        out = format_result("open_app", "winrar", True, details)
        self.assertIn("couldn't find", out.lower())
        self.assertIn("web version", out.lower())
        self.assertNotEqual(out, "Opened Winrar.")

    def test_formatter_fallback_no_message_composes_disclosure(self):
        from mini_kio.core.runtime_response_formatter import format_result
        out = format_result("open_app", "winrar", True,
                            {"success": True, "modality": "web_fallback", "message": ""})
        self.assertIn("web version", out.lower())
        self.assertNotEqual(out, "Opened Winrar.")

    def test_web_fallback_url_blocks_internal_reserved(self):
        from mini_kio.core.app_operator import _web_fallback_url
        self.assertIsNone(_web_fallback_url("localhost"))
        self.assertIsNone(_web_fallback_url("explorer"))
        self.assertIsNone(_web_fallback_url("cmd"))
        self.assertIsNone(_web_fallback_url("best cheap laptops"))

    def test_native_launch_failure_no_web_truthful(self):
        """E: native installed, launch failed, and no web version -> truthful
        "found but couldn't launch", never a misleading "not installed"."""
        # A registered native app with NO web alias (no WEB_URLS entry, and
        # single-word synthesis is blocked for it) that fails to launch.
        with mock.patch("mini_kio.core.app_operator._resolve_path",
                        return_value="C:/fake/Code.exe"), \
             mock.patch("mini_kio.core.app_operator._launch_from_info",
                        return_value={"success": False, "message": "boom"}), \
             mock.patch("mini_kio.core.app_operator._find_installed_app", return_value=None):
            r = launch_app("vscode")
        self.assertFalse(r["success"])
        self.assertIn("couldn't launch", r["message"].lower())
        self.assertIn("found", r["message"].lower())
        self.assertNotIn("not installed", r["message"].lower())
        self.assertNotIn("http", r["message"].lower())

    def test_formatter_fallback_message_never_opened(self):
        from mini_kio.core.runtime_response_formatter import format_open_app
        out = format_open_app(
            "winrar", True,
            "I couldn't find winrar installed on your computer, so I opened its web version in your browser.",
            {"modality": "web_fallback"},
        )
        self.assertNotEqual(out, "Opened Winrar.")
        self.assertIn("web version", out.lower())

    def test_dual_modality_open_failure_never_claims_opened(self):
        """Step-2 false-success guard: when the web open FAILS for a dual-modality
        name, the result must keep the truthful failure message — never
        "so I opened its web version" attached to success=False."""
        with mock.patch("mini_kio.core.app_operator._resolve_path", return_value=None), \
             mock.patch("mini_kio.core.app_operator._find_installed_app", return_value=None), \
             mock.patch("mini_kio.core.app_operator._open_url",
                        return_value={"success": False, "message": "Failed to open telegram"}):
            r = launch_app("telegram")
        self.assertFalse(r["success"])
        self.assertIn("failed to open", r["message"].lower())
        self.assertNotIn("so i opened its web version", r["message"].lower())
        self.assertNotIn("so I opened its web version", r["message"])

    def test_web_fallback_survives_execution_boundary(self):
        """Boundary survival: a disclosed web-fallback launch result (no PID)
        must pass through execute_action with modality + disclosure intact.

        _open_url sets verification_mode="noop", so the boundary selects
        noop_probe instead of process_liveness_probe — a pid-less web open is
        never downgraded to a failure by the liveness check.
        """
        from mini_kio.core import execution_boundary as eb
        with mock.patch("mini_kio.core.app_operator._find_installed_app", return_value=None), \
             mock.patch.object(eb, "_in_test_mode", return_value=False), \
             mock.patch.object(eb, "get_runtime", return_value=None):
            r = eb.execute_action("open_app", "winrar")
        self.assertTrue(r["success"])
        self.assertEqual(r.get("modality"), "web_fallback")
        self.assertIn("couldn't find", r["message"].lower())
        self.assertIn("web version", r["message"].lower())
        self.assertEqual(r.get("verification_status"), "passed")
        self.assertEqual(r.get("outcome_class"), "SUCCESS")


if __name__ == "__main__":
    unittest.main()
