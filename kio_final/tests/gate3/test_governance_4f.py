import unittest
from mini_kio.core.command_router import handle_command
from mini_kio.core.app_operator import launch_app, close_app, _RESTRICTED_CANONICAL_TARGETS
from mini_kio.core.execution_boundary import execute_action


class TestRestrictedTargetBlocking(unittest.TestCase):
    """Gate 4F — Restricted target .exe suffix normalization.

    All blocked tests return BEFORE execution (restricted check gates the path).
    No live apps are launched during these tests.
    """

    RESTRICTED_NAMES = {"explorer", "cmd", "powershell", "terminal", "taskmgr", "regedit", "services"}
    SAFE_NAMES = {"chrome", "notepad", "calculator", "spotify", "telegram"}

    def _assert_blocked(self, result: dict):
        self.assertFalse(result.get("success", True))
        self.assertTrue(
            result.get("blocked", False)
            or "restricted" in result.get("failure_class", "").lower()
            or "forbidden" in result.get("message", "").lower()
        )

    # ── Static normalization verification (no execution) ───────────

    def test_restricted_set_contains_explorer(self):
        self.assertIn("explorer", _RESTRICTED_CANONICAL_TARGETS)

    def test_restricted_set_contains_cmd(self):
        self.assertIn("cmd", _RESTRICTED_CANONICAL_TARGETS)

    def test_restricted_set_contains_powershell(self):
        self.assertIn("powershell", _RESTRICTED_CANONICAL_TARGETS)

    def test_restricted_set_contains_terminal(self):
        self.assertIn("terminal", _RESTRICTED_CANONICAL_TARGETS)

    def test_restricted_set_contains_taskmgr(self):
        self.assertIn("taskmgr", _RESTRICTED_CANONICAL_TARGETS)

    def test_restricted_set_contains_regedit(self):
        self.assertIn("regedit", _RESTRICTED_CANONICAL_TARGETS)

    def test_restricted_set_contains_services(self):
        self.assertIn("services", _RESTRICTED_CANONICAL_TARGETS)

    def test_restricted_set_does_not_contain_chrome(self):
        self.assertNotIn("chrome", _RESTRICTED_CANONICAL_TARGETS)

    def test_restricted_set_does_not_contain_notepad(self):
        self.assertNotIn("notepad", _RESTRICTED_CANONICAL_TARGETS)

    # ── Normalization correctness (string ops only, no execution) ──

    def test_normalize_strips_exe(self):
        for name in self.RESTRICTED_NAMES:
            with self.subTest(name=name):
                with_exe = f"{name}.exe"
                norm = with_exe[:-4] if with_exe.endswith(".exe") else with_exe
                self.assertEqual(norm, name)

    def test_normalize_preserves_safe_names(self):
        for name in self.SAFE_NAMES:
            with self.subTest(name=name):
                norm = name[:-4] if name.endswith(".exe") else name
                self.assertEqual(norm, name)

    def test_normalize_case_insensitive(self):
        for name in self.RESTRICTED_NAMES:
            with self.subTest(name=name):
                upper = f"{name.upper()}.EXE"
                norm = upper.lower()
                if norm.endswith(".exe"):
                    norm = norm[:-4]
                self.assertEqual(norm, name)

    def test_all_restricted_variants_map_to_base(self):
        variants = ["explorer", "explorer.exe", "EXPLORER.EXE", "Explorer.exe", "  explorer.exe  "]
        for v in variants:
            with self.subTest(variant=v):
                norm = v.strip().lower()
                if norm.endswith(".exe"):
                    norm = norm[:-4]
                self.assertIn(norm, self.RESTRICTED_NAMES)

    def test_safe_variants_not_in_restricted(self):
        variants = ["chrome", "CHROME", "notepad", "NOTEPAD.EXE"]
        for v in variants:
            with self.subTest(variant=v):
                norm = v.strip().lower()
                if norm.endswith(".exe"):
                    norm = norm[:-4]
                self.assertNotIn(norm, self.RESTRICTED_NAMES)

    # ── handle_command blocked tests (no execution — gate returns before dispatch) ──

    def test_open_explorer_exe_blocked(self):
        result = handle_command("open explorer.exe")
        self._assert_blocked(result)

    def test_open_explorer_blocked(self):
        result = handle_command("open explorer")
        self._assert_blocked(result)

    def test_open_cmd_exe_blocked(self):
        result = handle_command("open cmd.exe")
        self._assert_blocked(result)

    def test_open_powershell_exe_blocked(self):
        result = handle_command("open powershell.exe")
        self._assert_blocked(result)

    def test_open_regedit_blocked(self):
        result = handle_command("open regedit")
        self._assert_blocked(result)

    def test_open_taskmgr_blocked(self):
        result = handle_command("open taskmgr")
        self._assert_blocked(result)

    def test_open_terminal_blocked(self):
        result = handle_command("open terminal")
        self._assert_blocked(result)

    def test_open_services_blocked(self):
        result = handle_command("open services")
        self._assert_blocked(result)

    # ── case + whitespace normalization (handle_command) ────────────

    def test_open_explorer_exe_uppercase_blocked(self):
        result = handle_command("open EXPLORER.EXE")
        self._assert_blocked(result)

    def test_open_explorer_exe_mixed_case_blocked(self):
        result = handle_command("open Explorer.exe")
        self._assert_blocked(result)

    def test_open_explorer_exe_whitespace_blocked(self):
        result = handle_command("open  explorer.exe")
        self._assert_blocked(result)

    # ── launch_app blocked tests (no execution — restricted gate returns before dispatch) ──

    def test_launch_explorer_exe_blocked(self):
        result = launch_app("explorer.exe")
        self._assert_blocked(result)

    def test_launch_explorer_blocked(self):
        result = launch_app("explorer")
        self._assert_blocked(result)

    def test_launch_cmd_exe_blocked(self):
        result = launch_app("cmd.exe")
        self._assert_blocked(result)

    def test_launch_powershell_exe_blocked(self):
        result = launch_app("powershell.exe")
        self._assert_blocked(result)

    # ── close_app blocked tests (no execution) ──────────────────────

    def test_close_explorer_exe_blocked(self):
        result = close_app("explorer.exe")
        self._assert_blocked(result)

    def test_close_explorer_blocked(self):
        result = close_app("explorer")
        self._assert_blocked(result)

    def test_close_cmd_exe_blocked(self):
        result = close_app("cmd.exe")
        self._assert_blocked(result)

    # ── execute_action boundary veto (no execution — restricted gate returns before handler dispatch) ──

    def test_execute_open_explorer_exe_blocked(self):
        result = execute_action("open_app", "explorer.exe")
        self._assert_blocked(result)

    def test_execute_open_explorer_blocked(self):
        result = execute_action("open_app", "explorer")
        self._assert_blocked(result)

    def test_execute_close_explorer_exe_blocked(self):
        result = execute_action("close_app", "explorer.exe")
        self._assert_blocked(result)

    def test_execute_close_explorer_blocked(self):
        result = execute_action("close_app", "explorer")
        self._assert_blocked(result)

    def test_execute_open_cmd_exe_blocked(self):
        result = execute_action("open_app", "cmd.exe")
        self._assert_blocked(result)

    # ── all restricted targets blocked via launch_app ───────────────

    def test_all_restricted_targets_blocked(self):
        for target in _RESTRICTED_CANONICAL_TARGETS:
            with self.subTest(target=target):
                result = launch_app(target)
                self._assert_blocked(result)
                result = launch_app(f"{target}.exe")
                self._assert_blocked(result)

    # ── deterministic ──────────────────────────────────────────────

    def test_deterministic_same_result(self):
        r1 = handle_command("open explorer.exe")
        r2 = handle_command("open explorer.exe")
        self.assertEqual(r1.get("success"), r2.get("success"))
        self.assertEqual(r1.get("blocked"), r2.get("blocked"))

    # ── no execution attribute leakage ─────────────────────────────

    def test_no_execution_attributes(self):
        for func, name in [
            (handle_command, "handle_command"),
            (launch_app, "launch_app"),
            (close_app, "close_app"),
            (execute_action, "execute_action"),
        ]:
            for attr in ["execute", "dispatch", "run", "launch", "route"]:
                self.assertFalse(hasattr(func, attr), f"{name} has {attr}")


if __name__ == "__main__":
    unittest.main()
