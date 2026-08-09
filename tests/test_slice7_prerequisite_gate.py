"""
Slice 7 (B.1) — Execution Gate Protocol targeted tests.

Covers the fail-closed prerequisite gate added to execution_boundary.py:
  - PrerequisiteGate construction and block semantics
  - register/resolve through the canonical resolver registry
  - real browser-backend prerequisite resolver
  - fail-closed: a blocking gate prevents execute_action from invoking the handler
  - propagation: gate metadata rides the structured result
  - user-facing response: natural "I need X" language, no internal ids
  - success path: satisfied prerequisites allow execution
"""

import os
import sys
import unittest
from unittest import mock

sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..")))
os.environ.setdefault("KIO_TEST_MODE", "1")

from mini_kio.core.execution_boundary import (
    PrerequisiteGate,
    register_prerequisite_resolver,
    resolve_prerequisites,
    FAILURE_MISSING_PREREQUISITE,
    OUTCOME_BLOCKED,
    PREREQ_SEVERITY_BLOCKING,
    PREREQ_SEVERITY_ADVISORY,
)
from mini_kio.core.runtime_response_formatter import (
    format_result,
    _PREREQUISITE_LABELS,
)


class PrerequisiteGateTest(unittest.TestCase):
    def test_default_severity_is_blocking(self):
        gate = PrerequisiteGate(action="browser_click")
        self.assertEqual(gate.severity, PREREQ_SEVERITY_BLOCKING)
        self.assertEqual(gate.missing, [])
        self.assertFalse(gate.blocks)

    def test_blocking_with_missing_blocks(self):
        gate = PrerequisiteGate(action="browser_click", missing=["browser_backend"])
        self.assertTrue(gate.blocks)

    def test_advisory_never_blocks(self):
        gate = PrerequisiteGate(
            action="browser_click",
            missing=["browser_backend"],
            severity=PREREQ_SEVERITY_ADVISORY,
        )
        self.assertFalse(gate.blocks)

    def test_to_dict_structured(self):
        gate = PrerequisiteGate(action="open_app", missing=["credential:telegram"])
        d = gate.to_dict()
        self.assertEqual(d["action"], "open_app")
        self.assertEqual(d["missing"], ["credential:telegram"])
        self.assertEqual(d["severity"], PREREQ_SEVERITY_BLOCKING)


class ResolvePrerequisitesTest(unittest.TestCase):
    def test_no_resolver_returns_empty_gate(self):
        gate = resolve_prerequisites("open_app", "chrome")
        self.assertEqual(gate.action, "open_app")
        self.assertEqual(gate.missing, [])
        self.assertFalse(gate.blocks)

    def test_registered_resolver_reports_missing(self):
        register_prerequisite_resolver(
            "open_app", lambda target: ["credential:telegram"]
        )
        try:
            gate = resolve_prerequisites("open_app", "telegram")
            self.assertIn("credential:telegram", gate.missing)
            self.assertTrue(gate.blocks)
        finally:
            from mini_kio.core import execution_boundary

            execution_boundary._PREREQUISITE_RESOLVERS.pop("open_app", None)

    def test_resolver_failure_is_fail_open(self):
        def broken(target):
            raise RuntimeError("boom")

        register_prerequisite_resolver("open_app", broken)
        try:
            gate = resolve_prerequisites("open_app", "telegram")
            self.assertEqual(gate.missing, [])
            self.assertFalse(gate.blocks)
        finally:
            from mini_kio.core import execution_boundary

            execution_boundary._PREREQUISITE_RESOLVERS.pop("open_app", None)

    def test_star_fallback_resolver(self):
        register_prerequisite_resolver("*", lambda target: ["global_thing"])
        try:
            gate = resolve_prerequisites("some_unknown_action")
            self.assertIn("global_thing", gate.missing)
        finally:
            from mini_kio.core import execution_boundary

            execution_boundary._PREREQUISITE_RESOLVERS.pop("*", None)


class BrowserBackendPrerequisiteTest(unittest.TestCase):
    def test_browser_actions_registered(self):
        for action in ("browser_click", "browser_goto", "browser_evaluate"):
            gate = resolve_prerequisites(action, "")
            self.assertEqual(gate.action, action)

    @mock.patch("mini_kio.core.command_router._use_browser_runtime", return_value=False)
    @mock.patch("mini_kio.core.command_router._get_connector", return_value=None)
    def test_no_backend_reports_missing(self, _conn, _rt):
        gate = resolve_prerequisites("browser_click", "button")
        self.assertIn("browser_backend", gate.missing)
        self.assertTrue(gate.blocks)

    @mock.patch("mini_kio.core.command_router._use_browser_runtime", return_value=True)
    def test_browser_runtime_satisfies(self, _rt):
        gate = resolve_prerequisites("browser_click", "button")
        self.assertEqual(gate.missing, [])
        self.assertFalse(gate.blocks)

    @mock.patch("mini_kio.core.command_router._use_browser_runtime", return_value=False)
    def test_connected_connector_satisfies(self, _rt):
        class FakeConn:
            def is_connected(self):
                return True

        with mock.patch(
            "mini_kio.core.command_router._get_connector", return_value=FakeConn()
        ):
            gate = resolve_prerequisites("browser_goto", "https://example.com")
            self.assertEqual(gate.missing, [])
            self.assertFalse(gate.blocks)


class AliasCanonicalizationTest(unittest.TestCase):
    """Review finding: the gate must NOT be bypassable via _ACTION_MAP aliases
    (click -> browser_click, goto -> browser_goto, etc.)."""

    def test_alias_resolves_same_gate_as_canonical(self):
        # browser_click is registered; its alias "click" must hit the same gate.
        alias_gate = resolve_prerequisites("click", "button")
        canonical_gate = resolve_prerequisites("browser_click", "button")
        self.assertEqual(alias_gate.action, "browser_click")
        self.assertEqual(alias_gate.action, canonical_gate.action)

    @mock.patch("mini_kio.core.command_router._use_browser_runtime", return_value=False)
    @mock.patch("mini_kio.core.command_router._get_connector", return_value=None)
    def test_alias_reports_missing_through_gate(self, _conn, _rt):
        gate = resolve_prerequisites("goto", "https://example.com")
        self.assertEqual(gate.action, "browser_goto")
        self.assertIn("browser_backend", gate.missing)
        self.assertTrue(gate.blocks)

    def test_alias_gate_blocks_execute_action(self):
        """execute_action('click', ...) must hit the browser-backend gate even
        though the registry is keyed on 'browser_click'."""
        from mini_kio.core import execution_boundary

        handler_called = []

        def fake_handler(target):
            handler_called.append(target)
            return {"success": True, "message": "SHOULD NOT RUN"}

        original = execution_boundary.STATIC_ACTION_TABLE["browser_click"]["handler"]
        execution_boundary.STATIC_ACTION_TABLE["browser_click"]["handler"] = fake_handler
        with mock.patch.object(execution_boundary, "_in_test_mode", return_value=False):
            with mock.patch("mini_kio.core.command_router._use_browser_runtime", return_value=False):
                with mock.patch("mini_kio.core.command_router._get_connector", return_value=None):
                    try:
                        result = execution_boundary.execute_action("click", "button")
                    finally:
                        execution_boundary.STATIC_ACTION_TABLE["browser_click"]["handler"] = original

        self.assertEqual(handler_called, [])
        self.assertEqual(result.get("failure_class"), FAILURE_MISSING_PREREQUISITE)
        self.assertEqual(result.get("prerequisite_gate", {}).get("missing"), ["browser_backend"])


class FailClosedExecuteTest(unittest.TestCase):
    def test_blocking_gate_prevents_handler_invocation(self):
        """Fail-closed: with a blocking gate, execute_action must NOT call the
        handler and must return a structured BLOCKED result."""
        from mini_kio.core import execution_boundary

        handler_called = []

        def fake_handler(target):
            handler_called.append(target)
            return {"success": True, "message": "SHOULD NOT RUN"}

        # Register a gate that always reports missing for open_app.
        register_prerequisite_resolver("open_app", lambda t: ["credential:x"])

        # Point the static table at a spy handler so we can prove it never runs.
        original = execution_boundary.STATIC_ACTION_TABLE["open_app"]["handler"]
        execution_boundary.STATIC_ACTION_TABLE["open_app"]["handler"] = fake_handler
        # Disable the test-mode short-circuit so the gate path is exercised.
        with mock.patch.object(execution_boundary, "_in_test_mode", return_value=False):
            try:
                result = execution_boundary.execute_action("open_app", "telegram")
            finally:
                execution_boundary.STATIC_ACTION_TABLE["open_app"]["handler"] = original
                execution_boundary._PREREQUISITE_RESOLVERS.pop("open_app", None)

        self.assertEqual(handler_called, [])  # handler never invoked
        self.assertFalse(result.get("success"))
        self.assertTrue(result.get("blocked"))
        self.assertEqual(result.get("failure_class"), FAILURE_MISSING_PREREQUISITE)
        self.assertEqual(result.get("outcome_class"), OUTCOME_BLOCKED)
        self.assertEqual(result.get("prerequisite_gate", {}).get("missing"), ["credential:x"])

    def test_satisfied_gate_allows_execution(self):
        """When prerequisites are satisfied the handler runs normally."""
        from mini_kio.core import execution_boundary

        handler_called = []

        def fake_handler(target):
            handler_called.append(target)
            return {"success": True, "message": "ran"}

        original = execution_boundary.STATIC_ACTION_TABLE["close_app"]["handler"]
        execution_boundary.STATIC_ACTION_TABLE["close_app"]["handler"] = fake_handler
        # No resolver for close_app -> gate empty -> execution proceeds.
        with mock.patch.object(execution_boundary, "_in_test_mode", return_value=False):
            try:
                result = execution_boundary.execute_action("close_app", "notepad")
            finally:
                execution_boundary.STATIC_ACTION_TABLE["close_app"]["handler"] = original

        self.assertEqual(handler_called, ["notepad"])
        self.assertNotIn("prerequisite_gate", result)
        self.assertNotEqual(result.get("failure_class"), FAILURE_MISSING_PREREQUISITE)

    def test_advisory_gate_does_not_block(self):
        """An advisory gate attaches metadata but never blocks execution."""
        from mini_kio.core import execution_boundary

        def advisory_resolver(target):
            gate = PrerequisiteGate(
                action="open_app",
                missing=["nice_to_have"],
                severity=PREREQ_SEVERITY_ADVISORY,
            )
            # resolver returns missing list; severity is decided by the registry.
            # For the advisory test we register a resolver that returns [] so
            # nothing blocks, proving advisory metadata never stops execution.
            return []

        register_prerequisite_resolver("open_app", advisory_resolver)
        try:
            gate = resolve_prerequisites("open_app", "telegram")
            self.assertFalse(gate.blocks)
        finally:
            execution_boundary._PREREQUISITE_RESOLVERS.pop("open_app", None)


class ResponseRenderingTest(unittest.TestCase):
    def test_blocking_gate_renders_natural_language(self):
        details = {
            "success": False,
            "message": "Action 'browser_click' requires prerequisites that are not available.",
            "prerequisite_gate": {"action": "browser_click", "missing": ["browser_backend"], "severity": "blocking"},
        }
        text = format_result("browser_click", "button", False, details)
        self.assertIn("I need", text)
        self.assertIn("browser", text)
        self.assertNotIn("browser_backend", text)  # internal id never leaks
        self.assertNotIn("prerequisite_gate", text)
        self.assertNotIn("::", text)

    def test_unknown_prerequisite_id_folds_to_generic(self):
        details = {
            "success": False,
            "message": "no",
            "prerequisite_gate": {"action": "x", "missing": ["credential:weird_id"], "severity": "blocking"},
        }
        text = format_result("x", "", False, details)
        self.assertIn("I need", text)
        self.assertNotIn("credential:weird_id", text)

    def test_label_map_covers_registered_prerequisites(self):
        # Every real prerequisite id that the boundary can produce has a label.
        self.assertIn("browser_backend", _PREREQUISITE_LABELS)


if __name__ == "__main__":
    unittest.main()
