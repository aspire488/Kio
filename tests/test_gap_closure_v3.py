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

    def test_executor_never_targets_explorer_shell(self):
        # User directive (2026-08-12): close-all must NEVER target explorer.exe
        # — File Explorer is the Windows desktop shell. Even when a File
        # Explorer window (with a real titled window, as in practice) is
        # observed, it must be excluded from the close pass AND from the
        # remaining report.
        from mini_kio.core import app_operator

        fake_windows = [
            {"app": "File Explorer", "base": "explorer", "pid": 303, "title": "Documents"},
            {"app": "Notepad", "base": "notepad", "pid": 101, "title": "Untitled"},
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
        closed_names = {n for n, _ in closed}
        self.assertNotIn("File Explorer", closed_names)
        self.assertNotIn("explorer", closed_names)
        self.assertNotIn("explorer.exe", closed_names)
        self.assertNotIn("File Explorer", result.get("closed", []))
        self.assertIn("Notepad", closed_names)

    def test_executor_skips_explorer_regardless_of_base_case(self):
        # Explorer protection must be case-proof: the observation layer
        # lowercases bases, but a defensive explicit guard should hold even
        # for a mixed-case "Explorer" base.
        from mini_kio.core import app_operator

        fake_windows = [
            {"app": "File Explorer", "base": "Explorer", "pid": 303, "title": "Downloads"},
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
        closed_names = {n for n, _ in closed}
        self.assertNotIn("File Explorer", closed_names)
        self.assertNotIn("explorer", closed_names)
        self.assertIn("Calculator", closed_names)
        self.assertTrue(result["success"])

    def test_close_all_forbidden_set_is_case_normalized(self):
        # Live-found: close-all closed the terminal because the forbidden set
        # held mixed-case "WindowsTerminal.exe" while window observation
        # lowercases to "windowsterminal.exe" — the case-sensitive lookup
        # missed. Every forbidden entry must be lowercase so the protection
        # is deterministic.
        from mini_kio.core import app_operator

        forbidden = app_operator._close_all_forbidden_exes()
        self.assertTrue(all(f == f.lower() for f in forbidden))
        self.assertIn("explorer.exe", forbidden)
        self.assertIn("windowsterminal.exe", forbidden)
        self.assertIn("cmd.exe", forbidden)
        self.assertIn("dwm.exe", forbidden)

    def test_execute_action_close_all_dispatch_without_target_arg(self):
        # Live-found regression: "close all apps" failed with
        # "close_all_user_apps() takes 0 positional arguments but 1 was given"
        # because the dispatch passed the positional target. The no-arg
        # handler must be invoked as handler(), and the boundary must surface
        # a truthful failure (never a success-shaped "Done.").
        #
        # NOTE: _load_handler() returns STATIC_ACTION_TABLE[...]["handler"],
        # which captured the ORIGINAL function at import time — patching the
        # module attribute (execution_boundary.close_all_user_apps) would be
        # ineffective and the REAL close-all would run. Patch the table entry
        # the dispatcher actually resolves.
        from mini_kio.core import execution_boundary

        entry = execution_boundary.STATIC_ACTION_TABLE["close_all_apps"]
        handler = mock.Mock(return_value={"success": True, "message": "Closed all apps."})
        # execute_action builds handler_name via handler.__module__/.__name__
        handler.__name__ = "close_all_user_apps"
        handler.__module__ = "mini_kio.core.app_operator"
        with mock.patch.dict(entry, {"handler": handler}), mock.patch.object(
            execution_boundary, "_in_test_mode", return_value=False,
        ):
            result = execution_boundary.execute_action("close_all_apps", "")
        self.assertTrue(result["success"])
        handler.assert_called_once_with()  # no positional target

    def test_generic_failure_never_formats_as_done(self):
        # Live-found regression: a failed generic action was rendered as
        # "Done." — an untruthful success claim. Failures must surface the
        # actual error text.
        from mini_kio.core import runtime_response_formatter as fmt
        rendered = fmt.format_result(
            "close_all_apps", "", False,
            {"message": "Execution failed: boom", "outcome_class": "failure"},
        )
        self.assertNotIn("Done", rendered)
        self.assertIn("boom", rendered.lower())


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


class DegradedScopedGatingTest(unittest.TestCase):
    """Live-found (2026-08-12): a browser connector outage escalated the
    WHOLE runtime to DEGRADED and blocked unrelated native app launch/close.
    Gate 2.5 refinement: integrity degrades per capability group, and the
    safety gate blocks only the degraded group's actions."""

    def test_browser_outage_degrades_browser_group_only(self):
        from mini_kio.core import runtime as rt
        from mini_kio.core.execution_boundary import check_safety_policy

        r = rt.KioRuntime()
        rt._CURRENT_RUNTIME = r
        # 3 browser_goto failures (operator_reported_failure -> medium, w=2)
        # cross the degraded threshold (6) for the browser group.
        for _ in range(3):
            rt.record_runtime_integrity_warning(
                "execution_failure",
                {"action": "browser_goto", "target": "https://x.com",
                 "failure_class": "operator_reported_failure"},
            )
        self.assertEqual(r.safety_state, "DEGRADED")
        self.assertEqual(r.degraded_capability_groups, {"browser"})

        # Browser-group actions are blocked...
        allowed, reason = check_safety_policy("browser_goto", "https://x.com", r)
        self.assertFalse(allowed)
        self.assertIn("browser", reason)
        allowed, _ = check_safety_policy(
            "execute_capability", "chrome::open_url::https://chatgpt.com::chatgpt", r)
        self.assertFalse(allowed)

        # ...but native launch/close, media, and system control stay available.
        allowed, _ = check_safety_policy("open_app", "notepad", r)
        self.assertTrue(allowed)
        allowed, _ = check_safety_policy("close_app", "notepad", r)
        self.assertTrue(allowed)
        allowed, _ = check_safety_policy("open_folder", "downloads", r)
        self.assertTrue(allowed)
        allowed, _ = check_safety_policy("lock_system", "", r)
        self.assertTrue(allowed)
        allowed, _ = check_safety_policy("media_play", "", r)
        self.assertTrue(allowed)

    def test_benign_failures_never_degrade_runtime(self):
        # "open <nonexistent>", "close <not running>", invalid URLs, etc.
        # are normal user-request outcomes, NOT runtime integrity problems.
        from mini_kio.core import runtime as rt

        r = rt.KioRuntime()
        rt._CURRENT_RUNTIME = r
        for _ in range(12):
            rt.record_runtime_integrity_warning(
                "execution_failure",
                {"action": "open_app", "target": "nonexistentapp",
                 "failure_class": "not_installed"},
            )
        self.assertEqual(r.safety_state, "NORMAL")
        self.assertEqual(r.integrity_score, 0)
        self.assertEqual(r.degraded_capability_groups, set())

    def test_group_scores_reset_on_manual_recovery(self):
        from mini_kio.core import runtime as rt

        r = rt.KioRuntime()
        rt._CURRENT_RUNTIME = r
        for _ in range(3):
            rt.record_runtime_integrity_warning(
                "execution_failure",
                {"action": "browser_goto", "target": "https://x.com",
                 "failure_class": "operator_reported_failure"},
            )
        self.assertEqual(r.safety_state, "DEGRADED")
        rt.manual_runtime_recovery()
        self.assertEqual(r.safety_state, "NORMAL")
        self.assertEqual(r.integrity_group_scores, {})
        self.assertEqual(r.degraded_capability_groups, set())


class TargetInstanceSemanticsTest(unittest.TestCase):
    """Section 2/3: the semantic layer must distinguish open / open another /
    new tab / new window / new instance / focus — generically, never per-app.
    Entity identity is preserved while INSTANCE changes."""

    def test_plain_open_is_existing_target(self):
        d = _classify("open chatgpt")
        self.assertFalse(d.metadata.get("explicit_new"))

    def test_open_another_tab_marks_explicit_new(self):
        d = _classify("open another tab of chatgpt")
        self.assertEqual(d.intent_type.value, "browser_navigate")
        self.assertEqual(d.action, "execute_capability")
        self.assertTrue(d.metadata.get("explicit_new"))
        self.assertEqual(d.metadata.get("instance"), "tab")
        self.assertIn("chatgpt", d.target)

    def test_open_a_new_entity_tab_trailing_form(self):
        # Live-found semantic gap (2026-08-12): "open a new chatgpt tab" was
        # routed to NATIVE open_app with target "chatgpt tab" (the trailing
        # "tab" leaked into the entity). It must be a NEW browser-tab
        # instance of the entity, never a native app named "chatgpt tab".
        d = _classify("open a new chatgpt tab")
        self.assertEqual(d.intent_type.value, "browser_navigate")
        self.assertEqual(d.action, "execute_capability")
        self.assertTrue(d.metadata.get("explicit_new"))
        self.assertEqual(d.metadata.get("instance"), "tab")
        self.assertIn("chatgpt", d.target)
        self.assertNotIn("tab", d.target.split("::")[-1])  # entity is chatgpt, not chatgpt tab

    def test_open_another_entity_tab_trailing_form(self):
        d = _classify("open another github tab")
        self.assertEqual(d.action, "execute_capability")
        self.assertTrue(d.metadata.get("explicit_new"))
        self.assertEqual(d.metadata.get("instance"), "tab")
        self.assertIn("github", d.target)

    def test_open_in_new_tab_has_browser_prefix(self):
        # Live-found latent bug: "open X in a new tab" produced an EMPTY
        # browser prefix ("::open_url::...") which broke execute_capability
        # parsing. The modal target must carry the resolved default browser.
        d = _classify("open chatgpt in a new tab")
        self.assertTrue(d.metadata.get("explicit_new"))
        prefix = d.target.split("::")[0]
        self.assertIn(prefix, ("chrome", "edge", "firefox", "brave", "comet"))

    def test_new_browser_window_is_window_instance(self):
        d = _classify("open a new browser window for github")
        self.assertEqual(d.intent_type.value, "browser_navigate")
        self.assertEqual(d.action, "execute_capability")
        self.assertTrue(d.metadata.get("explicit_new"))
        self.assertEqual(d.metadata.get("instance"), "window")
        self.assertIn("github", d.target)

    def test_another_entity_window_is_window_instance(self):
        d = _classify("open another github window")
        self.assertEqual(d.action, "execute_capability")
        self.assertTrue(d.metadata.get("explicit_new"))
        self.assertEqual(d.metadata.get("instance"), "window")

    def test_open_in_new_window_is_window_instance(self):
        d = _classify("open github in a new window")
        self.assertTrue(d.metadata.get("explicit_new"))
        self.assertEqual(d.metadata.get("instance"), "window")

    def test_open_in_new_tab_marks_explicit_new(self):
        d = _classify("open chatgpt in a new tab")
        self.assertTrue(d.metadata.get("explicit_new"))

    def test_open_another_instance_marks_explicit_new(self):
        d = _classify("open another calculator")
        self.assertEqual(d.intent_type.value, "desktop_open")
        self.assertEqual(d.action, "open_app")
        self.assertTrue(d.metadata.get("explicit_new"))
        self.assertEqual(d.target, "calculator")

    def test_open_a_new_instance_marks_explicit_new(self):
        d = _classify("open a new calculator")
        self.assertTrue(d.metadata.get("explicit_new"))
        self.assertEqual(d.target, "calculator")

    def test_focus_is_not_explicit_new(self):
        d = _classify("focus chatgpt")
        self.assertEqual(d.intent_type.value, "browser_focus")
        self.assertEqual(d.action, "focus")

    def test_switch_to_is_focus_not_new(self):
        d = _classify("switch to chatgpt")
        self.assertEqual(d.action, "focus")

    def test_plain_open_skips_force_new_dup_prevention(self):
        # The executor path: default open must go through duplicate
        # prevention; explicit-new opens must skip it (force_new).
        from mini_kio.core import app_operator
        from mini_kio.core import command_router

        with mock.patch.object(
            app_operator, "_find_existing_web_target", return_value=None
        ), mock.patch.object(
            command_router, "_get_connector", return_value=None
        ):
            # friendly_name with ::new marker -> force_new skips dedup
            result = app_operator.execute_capability(
                "chrome::open_url::https://chatgpt.com::chatgpt::new")
        self.assertIn("chatgpt", result.get("message", "").lower())


class LLMBypassAuditTest(unittest.TestCase):
    """Section 7 (2026-08-12 directive): deterministic local/system state
    queries must NEVER fall through to LLM/web knowledge. The app inventory
    is answered from actual Windows state, whatever the possession wording."""

    def test_what_apps_do_you_have_is_inventory(self):
        # Live-found: "what apps do you have" produced irrelevant external
        # web content. It is the SAME inventory as "what apps do I have".
        for phrase in (
            "what apps do you have",
            "what apps does the system have",
            "what apps does the computer have",
            "what apps do i have",
            "what apps are installed",
            "what apps have you got",
            "what software is installed",
            "what programs are installed",
            "what apps are on my computer",
        ):
            d = _classify(phrase)
            self.assertEqual(d.intent_type.value, "operational", phrase)
            self.assertEqual(d.action, "app_inventory", phrase)

    def test_installed_existence_query_is_os_probe(self):
        for phrase in ("is notepad installed", "is winrar installed"):
            d = _classify(phrase)
            self.assertEqual(d.intent_type.value, "operational", phrase)
            self.assertEqual(d.action, "app_installed", phrase)

    def test_running_state_query_is_os_probe(self):
        d = _classify("is spotify running")
        self.assertEqual(d.intent_type.value, "operational")
        self.assertEqual(d.action, "app_running")

    def test_whats_running_on_computer_is_desktop_state(self):
        # Live-found (2026-08-12 revalidation): "what's running on my
        # computer" fell through to web knowledge and described the Android
        # app "WhatsRunning". The whole running-state family must route to the
        # deterministic desktop-state owner (list_tabs), whatever the trailing
        # location or the noun (apps/processes).
        for phrase in (
            "what's running on my computer",
            "what's running on this pc",
            "what is running on your system",
            "what's running on the machine",
            "what processes are running",
            "which processes are running",
            "what's running right now",
            "what apps are running",
            "what's currently running",
        ):
            d = _classify(phrase)
            self.assertEqual(d.intent_type.value, "browser_tabs", phrase)
            self.assertEqual(d.action, "list_tabs", phrase)
        # Knowledge shapes that merely share a word must NOT be hijacked.
        for phrase in ("what is running time", "what's open source",
                       "how much does ram cost"):
            d = _classify(phrase)
            self.assertEqual(d.intent_type.value, "information", phrase)

    def test_system_healthy_wording_routes_system(self):
        # "is the system healthy" must agree with "is my computer okay":
        # deterministic system owner, never the conversation fallback.
        for phrase in ("is the system healthy", "is my computer okay",
                       "is the computer healthy"):
            d = _classify(phrase)
            self.assertEqual(d.intent_type.value, "operational", phrase)
            self.assertEqual(d.action, "system", phrase)


class NewWindowTruthfulnessTest(unittest.TestCase):
    """Live-found (2026-08-12 revalidation): "open github in a new window"
    replied "Opened Github: in a new Chrome window." — (1) the "::newwindow"
    marker strip used [:-10] on an 11-char marker, leaving a trailing colon in
    the friendly name, and (2) the new-window claim carried verification_mode
    "noop" (no evidence). The canonical owner must strip the full marker and
    only claim a separate window when one is actually observed."""

    def test_newwindow_strip_and_window_verification(self):
        from types import SimpleNamespace
        from mini_kio.core import app_operator as ao
        from mini_kio.core import routing_utils as ru
        with mock.patch.object(ao, "_find_in_registry",
                               return_value={"exe": "chrome.exe",
                                             "process": "chrome.exe"}), \
                mock.patch.object(ao, "_resolve_path",
                                  return_value=r"C:\nonexistent\chrome.exe"), \
                mock.patch.object(ao, "subprocess") as sp, \
                mock.patch.object(ao, "_visible_browser_window_count",
                                  side_effect=[0, 1]), \
                mock.patch.object(ru, "register_browser_capability"):
            sp.Popen.return_value = SimpleNamespace(pid=12345)
            result = ao.execute_capability(
                "chrome::open_url::https://github.com::github::newwindow"
            )
        # Full marker stripped: no "Github:" colon artifact, clean display.
        self.assertNotIn("Github:", result["message"])
        self.assertIn("GitHub", result["message"])
        # New window actually observed (window count 0 -> 1): verified claim.
        self.assertEqual(result.get("verification_mode"), "window_identity")

    def test_newwindow_unconfirmed_is_truthful(self):
        # If no extra window is observed, KIO must NOT claim a new window.
        from types import SimpleNamespace
        from mini_kio.core import app_operator as ao
        from mini_kio.core import routing_utils as ru
        with mock.patch.object(ao, "_find_in_registry",
                               return_value={"exe": "chrome.exe",
                                             "process": "chrome.exe"}), \
                mock.patch.object(ao, "_resolve_path",
                                  return_value=r"C:\nonexistent\chrome.exe"), \
                mock.patch.object(ao, "subprocess") as sp, \
                mock.patch.object(ao, "_visible_browser_window_count",
                                  side_effect=[1, 1, 1, 1, 1]), \
                mock.patch.object(ru, "register_browser_capability"):
            sp.Popen.return_value = SimpleNamespace(pid=12345)
            result = ao.execute_capability(
                "chrome::open_url::https://github.com::github::newwindow"
            )
        self.assertEqual(result.get("verification_mode"), "window_unverified")
        self.assertNotIn("new Chrome window", result["message"])
        self.assertIn("couldn't confirm", result["message"])

    def test_knowledge_queries_stay_knowledge(self):
        # "what is notepad" must stay a KNOWLEDGE query, never an OS action.
        d = _classify("what is notepad")
        self.assertEqual(d.intent_type.value, "information")


class CompanionIntelligenceAuditTest(unittest.TestCase):
    """Section 17 (2026-08-12 directive): Companion Intelligence — the
    doctrine's dimensions (independent judgment, preference, disagreement,
    recommendation, uncertainty, curiosity, emotional modelling, self-
    evaluation) must route to the conversational/identity owners, NEVER to
    web knowledge or the wrong canonical owner."""

    def test_opinion_judgment_routes_conversation(self):
        # Curated opinion topics ("ai", "technology") have deterministic
        # canonical answers; uncurated topics route to the conversational LLM.
        for phrase in (
            "what is your take on remote work",
            "in your opinion, is it worth it",
            "what do you think about urban farming",
        ):
            d = _classify(phrase)
            self.assertEqual(d.intent_type.value, "conversation", phrase)
            self.assertEqual(d.action, "converse", phrase)
        # Curated deterministic opinions stay on the identity owner.
        for phrase in ("what do you think about ai", "what are your opinions on technology"):
            d = _classify(phrase)
            self.assertEqual(d.intent_type.value, "identity", phrase)


    def test_preference_and_recommendation_route_conversation(self):
        for phrase in (
            "do you like jazz music",
            "what is your favorite color",
            "should i watch dune",
            "recommend a good movie for tonight",
            "would you recommend that book",
            "which is better, apple or android",
        ):
            d = _classify(phrase)
            self.assertEqual(d.intent_type.value, "conversation", phrase)
            self.assertEqual(d.action, "converse", phrase)

    def test_converse_prompt_allows_reasoned_preferences(self):
        # Live-found (2026-08-12): "do you like jazz music" deflected with
        # "As an AI, I don't have personal preferences" — doctrine's Section 5
        # forbids using "I'm an AI" as a substitute for truthful behavior. The
        # converse system prompt must permit reasoned preferences/curiosity
        # while still forbidding fabricated human experience.
        from mini_kio.llm.llm_constants import _ASYSTEM_PROMPT
        joined = _ASYSTEM_PROMPT.lower()
        self.assertIn("i'd choose", joined)
        self.assertIn("deflecting", joined)
        self.assertIn("never fabricate human memories", joined)
        self.assertIn("curiosity", joined)

    def test_disagreement_routes_conversation(self):
        d = _classify("i disagree with you")
        self.assertEqual(d.intent_type.value, "conversation")

    def test_emotional_expression_routes_empathy(self):
        for phrase in ("i feel really stressed today", "im so excited"):
            d = _classify(phrase)
            self.assertEqual(d.intent_type.value, "conversation", phrase)
            self.assertEqual(d.action, "empathy", phrase)

    def test_curiosity_is_conversation_not_static_identity(self):
        # Live-found: "what are you curious about" matched the identity
        # dataset's broad "what are you" prefix and returned the static
        # "who are you" identity. Curiosity is a conversational dimension
        # (doctrine Section 5) and must route to the LLM with personality
        # context, while "who are you" stays the deterministic identity.
        for phrase in (
            "what are you curious about",
            "what interests you",
            "what excites you",
            "what are you interested in",
        ):
            d = _classify(phrase)
            self.assertEqual(d.intent_type.value, "conversation", phrase)
            self.assertEqual(d.action, "converse", phrase)
        # Identity questions remain deterministic.
        for phrase in ("who are you", "what is kio", "what are you"):
            d = _classify(phrase)
            self.assertEqual(d.intent_type.value, "identity", phrase)


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


class BrowserModalityGatingTest(unittest.TestCase):
    """Live-found (2026-08-12 revalidation): "open youtube in comet" opened a
    Chrome tab AND launched Comet — the Chrome extension connector served an
    explicit non-default-browser request. The connector may only serve the
    DEFAULT browser; explicit edge/comet/firefox/brave requests must go
    straight to their own browser binary (never a silent Chrome substitution).
    """

    def _make_conn(self):
        from types import SimpleNamespace
        conn = mock.Mock()
        conn.is_connected.return_value = True
        conn.open_tab = mock.AsyncMock(return_value=SimpleNamespace(
            success=True, tab_id="t1", url="https://youtube.com",
            title="YouTube", window_id=1,
        ))
        return conn

    def _patch_env(self, default_browser):
        from mini_kio.core import app_operator as ao
        from mini_kio.core import routing_utils as ru
        from mini_kio.core import command_router as cr
        from mini_kio.core import config as cfg
        from unittest import mock
        return [
            mock.patch.object(ao, "_find_in_registry",
                              return_value={"exe": "comet.exe",
                                            "process": "comet.exe"}),
            mock.patch.object(ao, "_resolve_path",
                              return_value=r"C:\fake\comet.exe"),
            mock.patch.object(ao, "subprocess"),
            mock.patch.object(ao, "_refine_pid_windows", return_value=9876),
            mock.patch.object(ru, "register_browser_capability"),
            mock.patch.object(cr, "_get_connector"),
            mock.patch.object(cfg, "DEFAULT_BROWSER", default_browser),
        ]

    def test_nondefault_browser_skips_connector(self):
        # DEFAULT_BROWSER=chrome, request is comet: the Chrome connector must
        # NOT be used (no Chrome tab side effect); Comet binary is launched.
        from types import SimpleNamespace
        from mini_kio.core import app_operator as ao
        conn = self._make_conn()
        patches = self._patch_env("chrome")
        with patches[6], patches[5] as get_conn, patches[0], patches[1], \
                patches[2] as sp, patches[3], patches[4]:
            get_conn.return_value = conn
            sp.Popen.return_value = SimpleNamespace(pid=999)
            result = ao.execute_capability(
                "comet::open_url::https://youtube.com::youtube"
            )
        conn.open_tab.assert_not_called()
        self.assertIn("Comet", result["message"])
        self.assertTrue(result["success"])

    def test_default_browser_uses_connector(self):
        # DEFAULT_BROWSER=chrome, request is chrome: the connector path runs
        # (tab-level open with verification), no binary relaunch.
        from mini_kio.core import app_operator as ao
        conn = self._make_conn()
        patches = self._patch_env("chrome")
        with patches[6], patches[5] as get_conn, patches[0], patches[1], \
                patches[2] as sp, patches[3], patches[4]:
            get_conn.return_value = conn
            result = ao.execute_capability(
                "chrome::open_url::https://youtube.com::youtube"
            )
        conn.open_tab.assert_awaited_once()
        self.assertIn("YouTube", result["message"])



class InstanceMarkerReferentTest(unittest.TestCase):
    """Live-found (post-commit 84a95b0 smoke): after "open a new chatgpt tab"
    the context referent became 'new' (the ::new INSTANCE marker was captured
    as the entity by parse_target's lazy arg + trailing name group), so a later
    "close it" resolved to 'close new' -> truthful but useless failure.
    The entity (chatgpt) must stay the referent; the instance marker is a
    qualifier, never a name.
    """

    def test_newwindow_never_becomes_referent(self):
        from mini_kio.core.target_ref import parse_target, safe_target_name
        ref = parse_target("chrome::open_url::https://github.com::github::newwindow")
        self.assertEqual(ref.name, "github")
        self.assertEqual(ref.kind, "webapp")
        self.assertEqual(ref.url, "https://github.com")
        self.assertEqual(safe_target_name(
            "chrome::open_url::https://github.com::github::newwindow"), "github")

    def test_newtab_never_becomes_referent(self):
        from mini_kio.core.target_ref import parse_target, safe_target_name
        ref = parse_target("chrome::open_url::https://chat.openai.com::chatgpt::new")
        self.assertEqual(ref.name, "chatgpt")
        self.assertEqual(ref.url, "https://chat.openai.com")
        self.assertEqual(safe_target_name(
            "chrome::open_url::https://chat.openai.com::chatgpt::new"), "chatgpt")

    def test_plain_capability_name_unchanged(self):
        # No marker: name behavior is untouched.
        from mini_kio.core.target_ref import parse_target, safe_target_name
        ref = parse_target("chrome::open_url::https://chat.openai.com::chatgpt")
        self.assertEqual(ref.name, "chatgpt")
        self.assertEqual(safe_target_name(
            "chrome::open_url::https://chat.openai.com::chatgpt"), "chatgpt")

    def test_context_close_it_resolves_to_entity_not_marker(self):
        # End-to-end referent: after a NEW-TAB execute_capability the
        # context manager must remember 'chatgpt', so 'close it' becomes
        # 'close chatgpt' — never 'close new'.
        from mini_kio.core.context_manager import SessionContext
        from mini_kio.core.target_ref import safe_target_name
        cm = SessionContext(session_id="test-session")
        target = "chrome::open_url::https://chat.openai.com::chatgpt::new"
        result = {
            "success": True,
            "action": "execute_capability",
            "target": target,
        }
        cm.update(result, "open a new chatgpt tab")
        self.assertEqual(cm.active_entity, safe_target_name(target))
        self.assertEqual(cm.active_entity, "chatgpt")
        resolved = cm.resolved_text("close it")
        self.assertEqual(resolved, "close chatgpt")


if __name__ == "__main__":
    unittest.main()
