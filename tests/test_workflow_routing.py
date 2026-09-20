"""Focused tests for Workflow provider domain action routing (Phase 4 Step 2)."""

import json
import os
import sys
import unittest

os.environ.setdefault("KIO_TEST_MODE", "1")

from mini_kio.core.providers.workflow_provider import WorkflowExecutionProvider


class TestWorkflowProviderRegistration(unittest.TestCase):
    """Verify provider is registered and exposes correct capabilities."""

    def test_provider_id(self):
        wp = WorkflowExecutionProvider()
        self.assertEqual(wp.id(), "workflow")

    def test_capabilities_include_domain_actions(self):
        wp = WorkflowExecutionProvider()
        caps = [c.name for c in wp.capabilities()]
        self.assertIn("workflow_create", caps)
        self.assertIn("workflow_execute", caps)

    def test_health(self):
        from mini_kio.core.provider_contract import ProviderHealth
        wp = WorkflowExecutionProvider()
        self.assertEqual(wp.health(), ProviderHealth.HEALTHY)


class TestRouteAction(unittest.TestCase):
    """Test workflow::route handler."""

    def test_route_above_threshold(self):
        wp = WorkflowExecutionProvider()
        result = wp.execute("route", "", category="bug", confidence=0.9,
                            routes={"bug": "jira", "feature": " Linear"},
                            min_confidence=0.5)
        self.assertTrue(result["success"])
        self.assertEqual(result["routed_to"], "jira")
        self.assertFalse(result["needs_review"])

    def test_route_below_threshold(self):
        wp = WorkflowExecutionProvider()
        result = wp.execute("route", "", category="bug", confidence=0.3,
                            routes={"bug": "jira"},
                            min_confidence=0.5)
        self.assertTrue(result["success"])
        self.assertIsNone(result["routed_to"])
        self.assertTrue(result["needs_review"])

    def test_route_unknown_category_uses_default(self):
        wp = WorkflowExecutionProvider()
        result = wp.execute("route", "", category="unknown", confidence=0.9,
                            routes={"bug": "jira", "default": "triage"},
                            min_confidence=0.5)
        self.assertTrue(result["success"])
        self.assertEqual(result["routed_to"], "triage")


class TestBranchAction(unittest.TestCase):
    """Test workflow::branch handler."""

    def test_branch_above_threshold(self):
        wp = WorkflowExecutionProvider()
        result = wp.execute("branch", "", value=0.9, threshold=0.8)
        self.assertTrue(result["success"])
        self.assertTrue(result["ok"])

    def test_branch_below_threshold(self):
        wp = WorkflowExecutionProvider()
        result = wp.execute("branch", "", value=0.5, threshold=0.8)
        self.assertTrue(result["success"])
        self.assertFalse(result["ok"])

    def test_branch_uses_confidence_alias(self):
        wp = WorkflowExecutionProvider()
        result = wp.execute("branch", "", confidence=0.9, threshold=0.8)
        self.assertTrue(result["success"])
        self.assertTrue(result["ok"])


class TestRequestApprovalAction(unittest.TestCase):
    """Test workflow::request_approval handler."""

    def test_approval_returns_approved(self):
        wp = WorkflowExecutionProvider()
        result = wp.execute("request_approval", "", channel="slack",
                            draft="Dear team, ...")
        self.assertTrue(result["success"])
        self.assertEqual(result["decision"], "approved")
        self.assertEqual(result["edited_draft"], "Dear team, ...")


class TestWaitForAckAction(unittest.TestCase):
    """Test workflow::wait_for_ack handler."""

    def test_wait_returns_acknowledged(self):
        wp = WorkflowExecutionProvider()
        result = wp.execute("wait_for_ack", "", handle="inc_123", timeout=10)
        self.assertTrue(result["success"])
        self.assertTrue(result["acknowledged"])


class TestAdvanceTierAction(unittest.TestCase):
    """Test workflow::advance_tier_or_stop handler."""

    def test_advance_when_not_acknowledged(self):
        wp = WorkflowExecutionProvider()
        result = wp.execute("advance_tier_or_stop", "", acknowledged=False,
                            tiers=["tier1", "tier2", "tier3"])
        self.assertTrue(result["success"])
        self.assertFalse(result["done"])
        self.assertEqual(result["next_tier"], "tier1")

    def test_stop_when_acknowledged(self):
        wp = WorkflowExecutionProvider()
        result = wp.execute("advance_tier_or_stop", "", acknowledged=True,
                            tiers=["tier1", "tier2"])
        self.assertTrue(result["success"])
        self.assertTrue(result["done"])
        self.assertIsNone(result["next_tier"])

    def test_stop_when_no_tiers(self):
        wp = WorkflowExecutionProvider()
        result = wp.execute("advance_tier_or_stop", "", acknowledged=False,
                            tiers=[])
        self.assertTrue(result["success"])
        self.assertTrue(result["done"])


class TestTransformRecordsAction(unittest.TestCase):
    """Test workflow::transform_records handler."""

    def test_transform_upper(self):
        wp = WorkflowExecutionProvider()
        data = [{"name": "hello world"}]
        transform = {"name": {"type": "upper"}}
        result = wp.execute("transform_records", "", data=data, transform=transform)
        self.assertTrue(result["success"])
        self.assertEqual(result["result"][0]["name"], "HELLO WORLD")
        self.assertEqual(result["row_count"], 1)

    def test_transform_number(self):
        wp = WorkflowExecutionProvider()
        data = [{"total": "42.5"}]
        transform = {"total": {"type": "number"}}
        result = wp.execute("transform_records", "", data=data, transform=transform)
        self.assertTrue(result["success"])
        self.assertEqual(result["result"][0]["total"], 42.5)

    def test_transform_passthrough(self):
        wp = WorkflowExecutionProvider()
        data = [{"x": 1}]
        result = wp.execute("transform_records", "", data=data, transform={})
        self.assertTrue(result["success"])
        self.assertEqual(result["result"][0]["x"], 1)


class TestVerifyShapeAction(unittest.TestCase):
    """Test workflow::verify_shape handler."""

    def test_valid_shape(self):
        wp = WorkflowExecutionProvider()
        data = [{"name": "test", "total": 42}]
        transform = {"name": {}, "total": {}}
        result = wp.execute("verify_shape", "", result=data, transform=transform)
        self.assertTrue(result["success"])
        self.assertTrue(result["verified"])

    def test_missing_field(self):
        wp = WorkflowExecutionProvider()
        data = [{"name": "test"}]
        transform = {"name": {}, "total": {}}
        result = wp.execute("verify_shape", "", result=data, transform=transform)
        self.assertTrue(result["success"])
        self.assertFalse(result["verified"])
        self.assertTrue(len(result["errors"]) > 0)


class TestValidateSchemaAction(unittest.TestCase):
    """Test workflow::validate_schema handler."""

    def test_valid_schema(self):
        wp = WorkflowExecutionProvider()
        payload = {"name": "test", "amount": 100}
        schema = {
            "name": {"type": "string", "required": True},
            "amount": {"type": "number", "required": True},
        }
        result = wp.execute("validate_schema", "", payload=payload, schema=schema)
        self.assertTrue(result["success"])
        self.assertTrue(result["ok"])
        self.assertEqual(result["record"]["amount"], 100.0)

    def test_missing_required_field(self):
        wp = WorkflowExecutionProvider()
        payload = {"name": "test"}
        schema = {
            "name": {"type": "string", "required": True},
            "amount": {"type": "number", "required": True},
        }
        result = wp.execute("validate_schema", "", payload=payload, schema=schema)
        self.assertTrue(result["success"])
        self.assertFalse(result["ok"])
        self.assertTrue(len(result["errors"]) > 0)

    def test_wrong_type(self):
        wp = WorkflowExecutionProvider()
        payload = {"amount": "not_a_number"}
        schema = {"amount": {"type": "number"}}
        result = wp.execute("validate_schema", "", payload=payload, schema=schema)
        self.assertTrue(result["success"])
        self.assertFalse(result["ok"])


class TestUnknownActionRejection(unittest.TestCase):
    """Verify unknown actions are rejected."""

    def test_unknown_action(self):
        wp = WorkflowExecutionProvider()
        result = wp.execute("nonexistent_action", "")
        self.assertFalse(result["success"])
        self.assertIn("unknown action", result["message"].lower())


class TestRoutingFromAppOperator(unittest.TestCase):
    """Test that workflow actions route through execute_capability."""

    def test_app_capabilities_has_workflow(self):
        from mini_kio.core.app_operator import APP_CAPABILITIES
        self.assertIn("workflow", APP_CAPABILITIES)
        expected = {"route", "branch", "request_approval", "wait_for_ack",
                    "advance_tier_or_stop", "transform_records", "verify_shape",
                    "validate_schema"}
        self.assertTrue(expected.issubset(set(APP_CAPABILITIES["workflow"])))


if __name__ == "__main__":
    unittest.main()
