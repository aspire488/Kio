import unittest
from unittest.mock import patch, MagicMock
import os
import sys

# Ensure mini_kio is in path
sys.path.append(os.path.abspath(os.path.join(os.path.dirname(__file__), '..')))

from mini_kio.core.app_operator import _normalize_web_target_to_url, launch_app, close_app, _RESTRICTED_CANONICAL_TARGETS
from mini_kio.core.execution_boundary import classify_action
from mini_kio.core.command_router import handle_command

class Gate2RegressionTests(unittest.TestCase):

    # ── A. BROWSER NORMALIZATION ───────────────────────────────────────────
    
    def test_browser_normalization_valid(self):
        """Verify valid synthetic and explicit domains."""
        self.assertEqual(_normalize_web_target_to_url("google"), "https://google.com")
        self.assertEqual(_normalize_web_target_to_url("github.com"), "https://github.com")
        self.assertEqual(_normalize_web_target_to_url("claude.ai"), "https://claude.ai")
        self.assertEqual(_normalize_web_target_to_url("google.com/search"), "https://google.com/search")

    def test_browser_normalization_malformed(self):
        """Verify malformed inputs are rejected."""
        self.assertIsNone(_normalize_web_target_to_url("google..com"))
        # Contract update (pre-slice execution corrections): explicit scheme
        # URLs are now accepted — the mandate requires "Open https://..." ->
        # website. Scheme passthrough is intentional; the safety contract that
        # matters is that malformed/internal/command-injected targets below
        # remain rejected.
        self.assertEqual(_normalize_web_target_to_url("http://google.com"), "http://google.com")
        self.assertIsNone(_normalize_web_target_to_url("google.com/"))
        self.assertIsNone(_normalize_web_target_to_url("google/path/extra"))

    def test_browser_normalization_restricted_hosts(self):
        """Verify localhost and internal hosts are blocked."""
        self.assertIsNone(_normalize_web_target_to_url("localhost"))
        self.assertIsNone(_normalize_web_target_to_url("127.0.0.1"))
        self.assertIsNone(_normalize_web_target_to_url("192.168.1.1"))
        self.assertIsNone(_normalize_web_target_to_url("appdata")) # Reserved synthetic label

    def test_browser_normalization_homoglyphs_and_chars(self):
        """Verify forbidden characters and potential homoglyphs."""
        self.assertIsNone(_normalize_web_target_to_url("google.com;rm -rf"))
        self.assertIsNone(_normalize_web_target_to_url("google.com&ls"))
        # Unicode homoglyphs (e.g., 'а' Cyrillic) - _SAFE_EXPLICIT_DOMAIN_RE is [a-z0-9]
        self.assertIsNone(_normalize_web_target_to_url("gооgle.com")) 

    # ── B. RESTRICTED TARGETS ──────────────────────────────────────────────

    def test_restricted_targets_launch(self):
        """Verify restricted targets reject in launch_app before execution."""
        for target in _RESTRICTED_CANONICAL_TARGETS:
            result = launch_app(target)
            self.assertFalse(result["success"])
            self.assertEqual(result["failure_class"], "restricted_target")

    def test_restricted_targets_close(self):
        """Verify restricted targets reject in close_app before execution."""
        # Special case: explorer has a unique message
        result = close_app("explorer")
        self.assertFalse(result["success"])
        self.assertEqual(result["failure_class"], "restricted_shell_control")
        
        for target in ["cmd", "powershell", "taskmgr", "regedit"]:
            result = close_app(target)
            self.assertFalse(result["success"])
            self.assertEqual(result["failure_class"], "restricted_target")

    # ── D. EXECUTION CLASSIFICATION ───────────────────────────────────────

    def test_execution_classification(self):
        """Verify actions map to correct categories."""
        self.assertEqual(classify_action("open"), "external_open")
        self.assertEqual(classify_action("close"), "external_control")
        self.assertEqual(classify_action("search"), "external_open")
        self.assertEqual(classify_action("folder"), "external_open")
        self.assertEqual(classify_action("shutdown"), "destructive_system")
        self.assertEqual(classify_action("restart"), "destructive_system")
        self.assertEqual(classify_action("lock"), "system_control")
        self.assertEqual(classify_action("execute_capability"), "external_control")

    def test_browser_routing_safety(self):
        """Verify browser routes never fall through to native execution."""
        # Test "open invalid in chrome"
        result = handle_command("open 127.0.0.1 in chrome")
        self.assertFalse(result["success"])
        self.assertEqual(result["message"], "Invalid browser web target.")

if __name__ == '__main__':
    unittest.main()
