"""
System-level gap-closure tests (2026-08-12).

Covers:
  A. deterministic close semantics — APP vs WINDOW vs BROWSER vs TAB
  B. generic CLOSE / SCOPE=ALL_APPLICATIONS (classifier + executor)
  C. desktop-action capability classes (TYPE / KEY_PRESS / SCROLL / CLICK)
     with the bounded anti-leak guards
  D. lock/unlock single authoritative system-session model
  E. "shut down the computer" stays a SYSTEM action, never an app close
  F. MCP startup is non-blocking (optional provider must not block the
     deterministic local command path)
"""

import os
import sys
import time
import unittest
from unittest import mock

sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..")))
os.environ.setdefault("KIO_TEST_MODE", "1")

from mini_kio.core.pipeline import Pipeline
from mini_kio.core.command_parser import parse_command


def _classify(text):
    p = Pipeline()
    return p._classifier.classify(text, text)


class CloseSemanticsTest(unittest.TestCase):
    """Section 6: a request to close an APPLICATION must never silently
    become a browser-tab operation; a web app closes at TAB scope."""

    def test_close_registered_native_app_is_app_scope(self):
        d = _classify("close spotify")
        self.assertEqual(d.intent_type.value, "desktop_close")
        self.assertEqual(d.action, "close_app")
        self.assertEqual(d.target, "spotify")

    def test_close_generic_app_is_app_scope(self):
        d = _classify("close notepad")
        self.assertEqual(d.action, "close_app")
        self.assertEqual(d.target, "notepad")

    def test_close_browser_is_app_scope(self):
        d = _classify("close chrome")
        self.assertEqual(d.action, "close_app")
        self.assertEqual(d.target, "chrome")

    def test_close_webapp_without_native_is_tab_scope(self):
        # chatgpt has no registered native install -> tab scope, never the
        # host browser process, never a fake native close.
        d = _classify("close chatgpt")
        self.assertEqual(d.intent_type.value, "browser_focus")
        self.assertEqual(d.action, "close_tab")

    def test_close_tab_phrasing_stays_tab_scope(self):
        d = _classify("close the chatgpt tab")
        self.assertEqual(d.action, "close_tab")

    def test_registered_webapp_with_native_identity_is_app_scope(self):
        # telegram is a registered native app -> close at application scope
        # (close_app resolves native-vs-web truthfully).
        d = _classify("close telegram")
        self.assertEqual(d.action, "close_app")


class CloseAllTest(unittest.TestCase):
    """Section 7: generic CLOSE / SCOPE=ALL_APPLICATIONS — natural wording
    converges on one canonical representation."""

    def test_close_all_apps(self):
        d = _classify("close all apps")
        self.assertEqual(d.intent_type.value, "desktop_close")
        self.assertEqual(d.action, "close_all_apps")

    def test_close_everything(self):
        d = _classify("close everything")
        self.assertEqual(d.action, "close_all_apps")

    def test_quit_all_applications(self):
        d = _classify("quit all applications")
        self.assertEqual(d.action, "close_all_apps")

    def test_kill_all_programs(self):
        d = _classify("kill all programs")
        self.assertEqual(d.action, "close_all_apps")

    def test_close_all_open_windows(self):
        d = _classify("close all open windows")
        self.assertEqual(d.action, "close_all_apps")

    def test_close_all(self):
        d = _classify("close all")
        self.assertEqual(d.action, "close_all_apps")

    def test_close_all_tabs_is_not_app_scope(self):
        # tabs are browser scope — must never converge on ALL_APPLICATIONS.
        d = _classify("close all tabs")
        self.assertNotEqual(d.action, "close_all_apps")

    def test_executor_skips_system_shells_and_reports_remaining(self):
        from mini_kio.core import app_operator

        fake_windows = [
            {"app": "Notepad", "base": "notepad", "pid": 101, "title": "Untitled"},
            {"app": "Spotify", "base": "spotify", "pid": 202, "title": "Spotify"},
            {"app": "File Explorer", "base": "explorer", "pid": 303, "title": ""},
            {"app": "Calculator", "base": "calculator", "pid": 404, "title": "Calculator"},
        ]
        closed = []
        with mock.patch(
            "mini_kio.core.desktop_state.observe_native_windows",
            side_effect=[(list(fake_windows), True), (list(fake_windows), True)],
        ), mock.patch.object(
            app_operator, "close_app",
            side_effect=lambda name, pid=None: closed.append((name, pid)) or {"success": True, "message": f"Closed {name}."},
        ):
            result = app_operator.close_all_user_apps()
        self.assertTrue(result["success"])
        closed_names = {n for n, _ in closed}
        # explorer (system shell) must never be targeted; real user apps are.
        self.assertNotIn("File Explorer", closed_names)
        self.assertIn("Notepad", closed_names)
        self.assertIn("Spotify", closed_names)
        self.assertIn("Calculator", closed_names)

    def test_executor_reports_truthful_remaining(self):
        from mini_kio.core import app_operator

        before = [
            {"app": "Notepad", "base": "notepad", "pid": 101, "title": ""},
            {"app": "Spotify", "base": "spotify", "pid": 202, "title": ""},
        ]
        after = [  # Spotify refused to close -> remains open
            {"app": "Spotify", "base": "spotify", "pid": 202, "title": ""},
        ]
        def _close(name, pid=None):
            if name == "Spotify":
                return {"success": False, "message": "Couldn't close Spotify."}
            return {"success": True, "message": f"Closed {name}."}

        with mock.patch(
            "mini_kio.core.desktop_state.observe_native_windows",
            side_effect=[(list(before), True), (list(after), True)],
        ), mock.patch.object(app_operator, "close_app", side_effect=_close):
            result = app_operator.close_all_user_apps()
        self.assertIn("Still open", result["message"])
        self.assertIn("Notepad", result["closed"])
        self.assertTrue(any("Spotify" in r for r in result["remaining"]))
        self.assertIn("Spotify", result["failed"])
        # Never claim everything closed when something remains.
        self.assertNotIn("Spotify", result["closed"])


class DesktopActionClassificationTest(unittest.TestCase):
    """Section 11/12: generic capability classes with bounded anti-leak
    guards — knowledge phrases that merely share a verb stay on the
    knowledge path."""

    def test_type_into_target(self):
        d = _classify("type hello into notepad")
        self.assertEqual(d.intent_type.value, "desktop_action")
        self.assertEqual(d.action, "type")
        self.assertEqual(d.metadata.get("payload"), "hello")

    def test_bare_type_short_payload(self):
        d = _classify("type hello")
        self.assertEqual(d.action, "type")
        self.assertEqual(d.metadata.get("payload"), "hello")

    def test_bare_type_long_payload_is_typing_not_conversation(self):
        # Live-found regression: "type hello world this is a kio test" leaked
        # to the conversation path, where the LLM FABRICATED a success claim
        # ("I've typed ...") instead of executing. Long typing payloads must
        # route to the canonical TYPE executor, never to conversation.
        d = _classify("type hello world this is a kio test")
        self.assertEqual(d.intent_type.value, "desktop_action")
        self.assertEqual(d.action, "type")
        self.assertEqual(d.metadata.get("payload"), "hello world this is a kio test")

    def test_bare_type_multiline_payload_is_typing(self):
        d = _classify("type my name is joel and i live in kochi")
        self.assertEqual(d.intent_type.value, "desktop_action")
        self.assertEqual(d.action, "type")

    def test_type_2_diabetes_is_knowledge_not_typing(self):
        d = _classify("type 2 diabetes")
        self.assertNotEqual(d.intent_type.value, "desktop_action")

    def test_type_of_cancer_is_knowledge(self):
        d = _classify("type of cancer")
        self.assertNotEqual(d.intent_type.value, "desktop_action")

    def test_type_b_blood_is_knowledge(self):
        d = _classify("type b blood")
        self.assertNotEqual(d.intent_type.value, "desktop_action")

    def test_type_coercion_is_knowledge(self):
        d = _classify("type coercion")
        self.assertNotEqual(d.intent_type.value, "desktop_action")

    def test_write_a_poem_is_not_typing(self):
        d = _classify("write a poem")
        self.assertNotEqual(d.intent_type.value, "desktop_action")

    def test_type_into_running_app_opens_new_document_first(self):
        # Live-found regression: "type hello into notepad" with Notepad ALREADY
        # open on an existing file must create a NEW blank document (Ctrl+N)
        # before typing — typed text must never land in existing content.
        from mini_kio.core.pipeline import _ExecutionCoordinator

        events = []
        dp = mock.Mock()
        dp.execute.side_effect = lambda cap, target="": (
            events.append((cap, target)) or
            ({"success": True, "message": "ok"} if cap.startswith("keyboard_") else {"success": False, "message": "no"})
        )
        coord = _ExecutionCoordinator()
        with mock.patch(
            "mini_kio.desktop.DesktopProvider",
            return_value=dp,
        ), mock.patch.object(
            coord, "_try_native_focus",
            side_effect=[{"success": True, "message": "Focused Notepad."}, None],
        ):
            result = coord._exec_desktop_action(
                {"action": "type", "target": "notepad", "metadata": {"payload": "hello"}},
                None,
            )
        self.assertTrue(result["success"])
        # Ctrl+N must be sent BEFORE the payload is typed.
        hotkey_idx = [i for i, (c, _) in enumerate(events) if c == "keyboard_hotkey"]
        type_idx = [i for i, (c, _) in enumerate(events) if c == "keyboard_type"]
        self.assertTrue(hotkey_idx and type_idx, f"events={events}")
        self.assertLess(hotkey_idx[0], type_idx[0])
        self.assertEqual(events[type_idx[0]][1], "hello")
        self.assertIn("new", result["message"].lower())

    def test_type_into_freshly_opened_app_skips_ctrl_n(self):
        # If KIO itself just launched the app, it is already a blank document
        # — no extra Ctrl+N new-document shortcut is needed.
        from mini_kio.core.pipeline import _ExecutionCoordinator

        events = []
        dp = mock.Mock()
        dp.execute.side_effect = lambda cap, target="": (
            events.append((cap, target)) or
            ({"success": True, "message": "ok"} if cap.startswith("keyboard_") else {"success": False, "message": "no"})
        )
        coord = _ExecutionCoordinator()
        with mock.patch(
            "mini_kio.desktop.DesktopProvider",
            return_value=dp,
        ), mock.patch.object(
            coord, "_try_native_focus",
            side_effect=[None, {"success": True, "message": "Focused Notepad."}],
        ), mock.patch(
            "mini_kio.core.execution_boundary.execute_action",
            return_value={"success": True},
        ):
            result = coord._exec_desktop_action(
                {"action": "type", "target": "notepad", "metadata": {"payload": "hello"}},
                None,
            )
        self.assertTrue(result["success"])
        caps = [c for c, _ in events]
        # keyboard_type present; no ctrl+n hotkey issued for a fresh launch.
        self.assertIn("keyboard_type", caps)
        self.assertNotIn("keyboard_hotkey", caps)

    def test_press_enter(self):
        d = _classify("press enter")
        self.assertEqual(d.intent_type.value, "desktop_action")
        self.assertEqual(d.action, "key_press")
        self.assertEqual(d.target, "enter")

    def test_press_enter(self):
        d = _classify("press enter")
        self.assertEqual(d.intent_type.value, "desktop_action")
        self.assertEqual(d.action, "key_press")
        self.assertEqual(d.target, "enter")

    def test_press_ctrl_s(self):
        d = _classify("press ctrl+s")
        self.assertEqual(d.action, "key_press")
        self.assertEqual(d.target, "ctrl+s")

    def test_press_release_is_not_key_press(self):
        d = _classify("press release")
        self.assertNotEqual(d.intent_type.value, "desktop_action")

    def test_hit_me_with_your_best_shot_is_not_key_press(self):
        d = _classify("hit me with your best shot")
        self.assertNotEqual(d.intent_type.value, "desktop_action")

    def test_shortcut_family(self):
        self.assertEqual(_classify("save").target, "ctrl+s")
        self.assertEqual(_classify("copy that").target, "ctrl+c")
        self.assertEqual(_classify("paste it here").target, "ctrl+v")
        self.assertEqual(_classify("select all").target, "ctrl+a")
        self.assertEqual(_classify("undo").target, "ctrl+z")
        self.assertEqual(_classify("redo").target, "ctrl+y")

    def test_scroll_and_click(self):
        self.assertEqual(_classify("scroll down").action, "scroll")
        self.assertEqual(_classify("scroll to the bottom").target, "bottom")
        d = _classify("click here")
        self.assertEqual(d.action, "click")

    def test_click_named_element_is_not_faked(self):
        d = _classify("click the search box")
        self.assertNotEqual(d.intent_type.value, "desktop_action")

    def test_multi_step_desktop_actions_route_through_canonical_executor(self):
        from mini_kio.core.command_router import _run_desktop_action_step

        with mock.patch(
            "mini_kio.core.pipeline._ExecutionCoordinator._exec_desktop_action",
            return_value={"success": True, "message": "typed"},
        ) as exec_action:
            steps = parse_command("open notepad and type hello and save")
            actions = [s["action"] for s in steps]
            self.assertIn("type", actions)
            self.assertIn("save", actions)
            # type step -> canonical type with payload
            r = _run_desktop_action_step("type", "hello")
            self.assertTrue(r["success"])
            called = exec_action.call_args[0][0]
            self.assertEqual(called["action"], "type")
            self.assertEqual(called["metadata"]["payload"], "hello")
            # save step -> canonical key_press ctrl+s
            r2 = _run_desktop_action_step("save", "")
            self.assertTrue(r2["success"])
            called2 = exec_action.call_args[0][0]
            self.assertEqual(called2["action"], "key_press")
            self.assertEqual(called2["target"], "ctrl+s")


class LockUnlockTest(unittest.TestCase):
    """Section 8: lock/unlock is a single authoritative system-session model.
    All variants resolve to the same canonical owner; responses are truthful
    and carry the lock_state."""

    def test_unlock_variants_resolve_to_canonical_owner(self):
        for phrase in ("unlock", "unlock the system", "wake and unlock"):
            d = _classify(phrase)
            self.assertEqual(d.intent_type.value, "system", phrase)
            self.assertEqual(d.action, "unlock_system", phrase)

    def test_lock_variants_resolve_to_canonical_owner(self):
        for phrase in ("lock", "lock the computer", "secure my pc"):
            d = _classify(phrase)
            self.assertEqual(d.intent_type.value, "system", phrase)
            self.assertEqual(d.action, "lock_system", phrase)

    def test_lock_state_queries_route_operational(self):
        for phrase in ("is my computer locked", "what is the lock status",
                       "can i use the computer", "is the pc unlocked"):
            d = _classify(phrase)
            self.assertEqual(d.intent_type.value, "operational", phrase)
            self.assertEqual(d.action, "lock_state", phrase)

    def test_lock_state_returns_truthful_dict(self):
        from mini_kio.core.system_operator import lock_state
        result = lock_state()
        self.assertIn("lock_state", result)
        self.assertIn(result["lock_state"], ("locked", "unlocked", "unknown"))
        if result["lock_state"] == "locked":
            self.assertIn("locked", result["message"].lower())
        elif result["lock_state"] == "unlocked":
            self.assertIn("isn't locked", result["message"].lower())

    def test_unlock_never_claims_unlocked_without_state(self):
        # A LOCKED workstation must yield authentication_required, never a
        # fabricated UNLOCKED.
        from mini_kio.core import system_operator
        with mock.patch.object(system_operator, "is_workstation_locked", return_value=True):
            result = system_operator.unlock_system()
            self.assertEqual(result["lock_state"], "authentication_required")
            self.assertNotIn("isn't locked", result["message"].lower())
        with mock.patch.object(system_operator, "is_workstation_locked", return_value=False):
            result = system_operator.unlock_system()
            self.assertEqual(result["lock_state"], "unlocked")


class SystemNounBoundaryTest(unittest.TestCase):
    """System nouns stay OUT of the close-verb family."""

    def test_shut_down_the_computer_is_shutdown(self):
        d = _classify("shut down the computer")
        self.assertEqual(d.intent_type.value, "system")
        self.assertEqual(d.action, "shutdown_system")

    def test_shut_down_my_pc_is_shutdown(self):
        d = _classify("shut down my pc")
        self.assertEqual(d.action, "shutdown_system")


class MCPStartupNonBlockingTest(unittest.TestCase):
    """Section 9: optional MCP provider initialization must not block the
    deterministic local command path at startup."""

    def test_start_returns_immediately(self):
        from mini_kio.core.mcp.registry import MCPServerRegistry, MCPServerInfo
        from mini_kio.core.mcp.client import MCPClient

        registry = MCPServerRegistry()
        for stype in ("filesystem", "git", "terminal", "sqlite", "docker",
                      "github", "postgres", "redis"):
            registry.register_server(MCPServerInfo(server_type=stype, display_name=stype))

        blocked = mock.Mock(side_effect=lambda info: time.sleep(0.5))
        client = MCPClient(registry)
        with mock.patch.object(client, "_connect", blocked):
            start = time.monotonic()
            client.start()
            elapsed = time.monotonic() - start
        # start() must return without waiting for any server handshake.
        self.assertLess(elapsed, 0.3)
        self.assertEqual(blocked.call_count, 8)
        time.sleep(0.9)  # allow the daemon threads to finish


if __name__ == "__main__":
    unittest.main()
