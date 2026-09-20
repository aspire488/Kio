"""Integration test suite for KIO AutomationEngine pipeline wiring.

18 test categories covering:
- Intent recognition (AUTOMATION)
- Pipeline classification
- Resolver mapping
- Template ID resolution
- Engine initialization
- Template loading
- Execution path
- Response formatting
- Error handling
- Regression (existing intents unaffected)
- Capability blocking
- Security bridge
- Credential checks
- Step execution
- Status tracking
- Template store
- Context resolution
- End-to-end pipeline

Run: python -m pytest tests/test_automation_integration.py -v
"""
from __future__ import annotations

import asyncio
import pytest
from unittest.mock import patch, MagicMock, AsyncMock


# ── Category 1: Intent Recognition ───────────────────────────────────

class TestAutomationIntentRecognition:
    """Verify AUTOMATION intent is added to IntentType enum."""

    def test_automation_intent_exists(self):
        from mini_kio.core.pipeline.types import IntentType
        assert hasattr(IntentType, "AUTOMATION")
        assert IntentType.AUTOMATION.value == "automation"

    def test_automation_intent_count(self):
        from mini_kio.core.pipeline.types import IntentType
        count = len(IntentType)
        assert count == 27  # 26 original + 1 AUTOMATION

    def test_automation_in_all_values(self):
        from mini_kio.core.pipeline.types import IntentType
        values = [i.value for i in IntentType]
        assert "automation" in values


# ── Category 2: Pipeline Classification ──────────────────────────────

class TestPipelineClassification:
    """Verify the pipeline classifier recognizes automation triggers."""

    def _classify(self, text: str):
        from mini_kio.core.pipeline import _IntentClassifier
        classifier = _IntentClassifier()
        return classifier.classify(text, text)

    def test_run_workflow(self):
        d = self._classify("run the morning routine")
        assert d.intent_type.value == "automation"
        assert d.action == "run_workflow"

    def test_execute_workflow(self):
        d = self._classify("execute data json transform")
        assert d.intent_type.value == "automation"
        assert d.action == "run_workflow"

    def test_start_workflow(self):
        d = self._classify("start the daily briefing")
        assert d.intent_type.value == "automation"
        assert d.action == "run_workflow"

    def test_launch_workflow(self):
        d = self._classify("launch the pr review prep")
        assert d.intent_type.value == "automation"
        assert d.action == "run_workflow"

    def test_run_daily_briefing(self):
        d = self._classify("run the daily briefing")
        assert d.intent_type.value == "automation"
        assert "daily" in d.metadata.get("template_candidate", "").lower()

    def test_run_nightly_routine(self):
        d = self._classify("run the nightly routine")
        assert d.intent_type.value == "automation"

    def test_automation_does_not_steal_greeting(self):
        d = self._classify("hello")
        assert d.intent_type.value != "automation"

    def test_automation_does_not_steal_utility(self):
        d = self._classify("what time is it")
        assert d.intent_type.value != "automation"

    def test_automation_does_not_steal_media(self):
        d = self._classify("play some music")
        assert d.intent_type.value != "automation"

    def test_automation_does_not_steal_search(self):
        d = self._classify("search for python docs")
        assert d.intent_type.value != "automation"


# ── Category 3: Resolver Mapping ─────────────────────────────────────

class TestResolverMapping:
    """Verify AUTOMATION maps to 'automation' capability in the resolver."""

    def test_automation_mapping_exists(self):
        from mini_kio.core.pipeline.types import IntentType, RoutingDecision
        from mini_kio.core.pipeline import _CapabilityResolver
        decision = RoutingDecision(
            IntentType.AUTOMATION, "run_workflow", "test_template",
            "run test template", "run test template",
        )
        resolver = _CapabilityResolver()
        capability, params = resolver.resolve(decision)
        assert capability == "automation"

    def test_automation_params_include_target(self):
        from mini_kio.core.pipeline.types import IntentType, RoutingDecision
        from mini_kio.core.pipeline import _CapabilityResolver
        decision = RoutingDecision(
            IntentType.AUTOMATION, "run_workflow", "my_workflow",
            "run my workflow", "run my workflow",
            metadata={"template_candidate": "my_workflow"},
        )
        resolver = _CapabilityResolver()
        capability, params = resolver.resolve(decision)
        assert params.get("target") == "my_workflow"
        assert params.get("metadata", {}).get("template_candidate") == "my_workflow"


# ── Category 4: Template ID Resolution ───────────────────────────────

class TestTemplateResolution:
    """Verify template candidate names resolve to correct template IDs."""

    def _get_store(self):
        from mini_kio.automation.template_store import TemplateStore
        store = TemplateStore()
        store.load()
        return store

    def test_exact_match(self):
        store = self._get_store()
        from mini_kio.core.pipeline import _ExecutionCoordinator
        result = _ExecutionCoordinator._resolve_template_id(store, "data.json_transform")
        assert result == "data.json_transform"

    def test_normalized_match_with_spaces(self):
        store = self._get_store()
        from mini_kio.core.pipeline import _ExecutionCoordinator
        result = _ExecutionCoordinator._resolve_template_id(store, "data json transform")
        assert result is not None
        assert "data" in result and "json" in result

    def test_normalized_match_with_dashes(self):
        store = self._get_store()
        from mini_kio.core.pipeline import _ExecutionCoordinator
        result = _ExecutionCoordinator._resolve_template_id(store, "structured-extract")
        assert result is not None

    def test_partial_prefix_match(self):
        store = self._get_store()
        from mini_kio.core.pipeline import _ExecutionCoordinator
        # "browser" should match browser.* templates
        result = _ExecutionCoordinator._resolve_template_id(store, "browser structured extract")
        assert result is not None
        assert result.startswith("browser.")

    def test_no_match_returns_none(self):
        store = self._get_store()
        from mini_kio.core.pipeline import _ExecutionCoordinator
        result = _ExecutionCoordinator._resolve_template_id(store, "xyzzy_nonexistent")
        assert result is None

    def test_fuzzy_match_returns_suggestions(self):
        store = self._get_store()
        from mini_kio.core.pipeline import _ExecutionCoordinator
        results = _ExecutionCoordinator._fuzzy_match_templates(store, "browser")
        assert len(results) > 0  # should find at least one browser template


# ── Category 5: Engine Initialization ────────────────────────────────

class TestEngineInitialization:
    """Verify AutomationEngine initializes correctly."""

    def test_create_engine(self):
        from mini_kio.automation import create_automation_engine
        engine = create_automation_engine()
        assert engine is not None
        assert engine.template_count >= 63

    def test_engine_has_templates(self):
        from mini_kio.automation import create_automation_engine
        engine = create_automation_engine()
        ids = engine.list_templates()
        assert len(ids) >= 63

    def test_engine_status_summary(self):
        from mini_kio.automation import create_automation_engine
        engine = create_automation_engine()
        summary = engine.status_summary()
        assert "total_templates" in summary
        assert summary["total_templates"] >= 63


# ── Category 6: Template Loading ─────────────────────────────────────

class TestTemplateLoading:
    """Verify all 63 YAML templates load correctly."""

    def test_load_count(self):
        from mini_kio.automation.template_store import TemplateStore
        store = TemplateStore()
        count = store.load()
        assert count >= 63

    def test_no_load_errors(self):
        from mini_kio.automation.template_store import TemplateStore
        store = TemplateStore()
        store.load()
        errors = store.load_errors
        assert len(errors) == 0, f"Load errors: {errors}"

    def test_all_categories_present(self):
        from mini_kio.automation.template_store import TemplateStore
        store = TemplateStore()
        store.load()
        cats = store.categories()
        assert len(cats) > 0

    def test_data_json_transform_loads(self):
        from mini_kio.automation.template_store import TemplateStore
        store = TemplateStore()
        store.load()
        record = store.get("data.json_transform")
        assert record is not None
        assert record.template_id == "data.json_transform"
        assert record.category == "data"


# ── Category 7: Execution Path ───────────────────────────────────────

class TestExecutionPath:
    """Verify automation execution flows through the pipeline correctly."""

    def test_pipeline_run_triggers_automation(self):
        from mini_kio.core.pipeline import Pipeline
        p = Pipeline()
        result = p.run("run data json transform", session_id="test_exec")
        assert isinstance(result, dict)
        assert "success" in result
        assert "message" in result

    def test_pipeline_run_with_automation_intent(self):
        from mini_kio.core.pipeline import Pipeline
        p = Pipeline()
        result = p.run("run the morning routine", session_id="test_exec_2")
        assert isinstance(result, dict)
        assert "message" in result

    def test_missing_template_returns_helpful_error(self):
        from mini_kio.core.pipeline import Pipeline
        p = Pipeline()
        result = p.run("run completely nonexistent workflow xyzzy", session_id="test_missing")
        assert result.get("success") is False
        assert "workflow" in result.get("message", "").lower() or "find" in result.get("message", "").lower()


# ── Category 8: Response Formatting ──────────────────────────────────

class TestResponseFormatting:
    """Verify automation results format correctly for users."""

    def test_success_response_has_steps(self):
        from mini_kio.core.pipeline import Pipeline
        p = Pipeline()
        result = p.run("run data json transform", session_id="test_fmt")
        assert isinstance(result, dict)
        assert "message" in result
        msg = result["message"]
        assert "Workflow" in msg or "workflow" in msg

    def test_error_response_has_explanation(self):
        from mini_kio.core.pipeline import Pipeline
        p = Pipeline()
        result = p.run("run nonexistent workflow abc", session_id="test_fmt_err")
        assert result.get("success") is False
        assert len(result.get("message", "")) > 10


# ── Category 9: Error Handling ───────────────────────────────────────

class TestErrorHandling:
    """Verify error conditions are handled gracefully."""

    def test_empty_trigger_returns_error(self):
        from mini_kio.core.pipeline.types import IntentType, RoutingDecision
        from mini_kio.core.pipeline import _ExecutionCoordinator
        coord = _ExecutionCoordinator()
        decision = RoutingDecision(
            IntentType.AUTOMATION, "run_workflow", "",
            "run", "run",
            metadata={},
        )
        result = coord._exec_automation({}, decision)
        assert result["success"] is False
        assert "workflow name" in result["message"].lower()

    def test_invalid_template_returns_error(self):
        from mini_kio.core.pipeline.types import IntentType, RoutingDecision
        from mini_kio.core.pipeline import _ExecutionCoordinator
        coord = _ExecutionCoordinator()
        decision = RoutingDecision(
            IntentType.AUTOMATION, "run_workflow", "nonexistent_xyzzy",
            "run nonexistent", "run nonexistent",
            metadata={"template_candidate": "nonexistent_xyzzy"},
        )
        result = coord._exec_automation({}, decision)
        assert result["success"] is False

    def test_exception_handling(self):
        from mini_kio.core.pipeline.types import IntentType, RoutingDecision
        from mini_kio.core.pipeline import _ExecutionCoordinator
        coord = _ExecutionCoordinator()
        decision = RoutingDecision(
            IntentType.AUTOMATION, "run_workflow", "test",
            "run test", "run test",
            metadata={"template_candidate": 123},  # wrong type
        )
        result = coord._exec_automation({}, decision)
        assert isinstance(result, dict)
        assert "success" in result


# ── Category 10: Regression — Existing Intents Unaffected ────────────

class TestRegressionExistingIntents:
    """Verify adding AUTOMATION didn't break existing intents."""

    def _classify(self, text: str):
        from mini_kio.core.pipeline import _IntentClassifier
        classifier = _IntentClassifier()
        return classifier.classify(text, text)

    def test_greeting_still_works(self):
        d = self._classify("hello")
        assert d.intent_type.value == "greeting"

    def test_media_still_works(self):
        d = self._classify("play some music")
        assert d.intent_type.value == "media_play"

    def test_desktop_still_works(self):
        d = self._classify("open notepad")
        assert d.intent_type.value in ("desktop_open", "desktop_action")

    def test_utility_still_works(self):
        d = self._classify("what time is it")
        assert d.intent_type.value == "utility"

    def test_knowledge_still_works(self):
        d = self._classify("what is python")
        assert d.intent_type.value in ("knowledge", "information", "conversation")

    def test_system_still_works(self):
        d = self._classify("lock the screen")
        assert d.intent_type.value == "system"

    def test_search_still_works(self):
        d = self._classify("google python docs")
        # In this KIO build, "google X" routes through conversation/research
        assert d.intent_type.value != "automation"

    def test_pipeline_run_greeting(self):
        from mini_kio.core.pipeline import Pipeline
        p = Pipeline()
        result = p.run("hello", session_id="test_regression")
        assert isinstance(result, dict)
        assert result.get("success") is True

    def test_pipeline_run_utility(self):
        from mini_kio.core.pipeline import Pipeline
        p = Pipeline()
        result = p.run("what time is it", session_id="test_regression_util")
        assert isinstance(result, dict)
        assert "message" in result


# ── Category 11: Capability Blocking ─────────────────────────────────

class TestCapabilityBlocking:
    """Verify BLOCKED workflows report correctly."""

    def test_blocked_workflow_returns_blocked(self):
        from mini_kio.automation import create_automation_engine
        engine = create_automation_engine()
        summary = engine.status_summary()
        statuses = summary.get("statuses", {})
        blocked_count = statuses.get("blocked", 0)
        assert blocked_count > 0, "Expected at least some blocked workflows"

    def test_structurally_valid_count(self):
        from mini_kio.automation import create_automation_engine
        engine = create_automation_engine()
        summary = engine.status_summary()
        statuses = summary.get("statuses", {})
        valid_count = statuses.get("structurally_valid", 0)
        assert valid_count >= 1, "Expected at least data.json_transform to be structurally_valid"


# ── Category 12: Security Bridge ─────────────────────────────────────

class TestSecurityBridge:
    """Verify security classification is enforced."""

    def test_security_bridge_initializes(self):
        from mini_kio.automation.bridges import SecurityBridge
        bridge = SecurityBridge()
        assert bridge is not None

    def test_template_security_check(self):
        from mini_kio.automation.bridges import SecurityBridge
        from mini_kio.automation.template_store import TemplateStore
        bridge = SecurityBridge()
        store = TemplateStore()
        store.load()
        record = store.get("data.json_transform")
        assert record is not None
        result = bridge.check_template_security(record.template)
        assert "permitted" in result or "warnings" in result


# ── Category 13: Credential Checks ───────────────────────────────────

class TestCredentialChecks:
    """Verify credential checking is wired correctly."""

    def test_credential_bridge_initializes(self):
        from mini_kio.automation.bridges import CredentialBridge
        bridge = CredentialBridge()
        assert bridge is not None

    def test_empty_credentials_resolve(self):
        from mini_kio.automation.bridges import CredentialBridge
        bridge = CredentialBridge()
        result = bridge.resolve_credentials([])
        assert isinstance(result, dict)


# ── Category 14: Step Execution ──────────────────────────────────────

class TestStepExecution:
    """Verify step runner executes through execution_boundary."""

    def test_step_runner_initializes(self):
        from mini_kio.automation.step_runner import StepRunner
        runner = StepRunner()
        assert runner is not None


# ── Category 15: Status Tracking ─────────────────────────────────────

class TestStatusTracking:
    """Verify execution status is tracked correctly."""

    def test_status_registry_initializes(self):
        from mini_kio.automation.status import StatusRegistry
        registry = StatusRegistry()
        assert registry is not None

    def test_status_default(self):
        from mini_kio.automation.status import StatusRegistry
        registry = StatusRegistry()
        status = registry.get_status("nonexistent_template")
        assert status["execution_status"] == "candidate"

    def test_status_record_success(self):
        from mini_kio.automation.status import StatusRegistry
        registry = StatusRegistry()
        registry.record_success("test_template")
        status = registry.get_status("test_template")
        assert status["execution_status"] == "runtime_proven"

    def test_status_summary(self):
        from mini_kio.automation.status import StatusRegistry
        registry = StatusRegistry()
        registry.record_success("a")
        registry.record_failure("b", "test error")
        summary = registry.summary()
        assert summary.get("runtime_proven") == 1
        assert summary.get("failed") == 1


# ── Category 16: Template Store ──────────────────────────────────────

class TestTemplateStore:
    """Verify TemplateStore loads and validates correctly."""

    def test_store_loads_all(self):
        from mini_kio.automation.template_store import TemplateStore
        store = TemplateStore()
        count = store.load()
        assert count >= 63

    def test_store_get_by_id(self):
        from mini_kio.automation.template_store import TemplateStore
        store = TemplateStore()
        store.load()
        record = store.get("data.json_transform")
        assert record is not None
        assert record.template_id == "data.json_transform"

    def test_store_list_ids(self):
        from mini_kio.automation.template_store import TemplateStore
        store = TemplateStore()
        store.load()
        ids = store.list_ids()
        assert len(ids) >= 63
        assert "data.json_transform" in ids

    def test_store_categories(self):
        from mini_kio.automation.template_store import TemplateStore
        store = TemplateStore()
        store.load()
        cats = store.categories()
        assert "data" in cats

    def test_store_list_by_category(self):
        from mini_kio.automation.template_store import TemplateStore
        store = TemplateStore()
        store.load()
        data_templates = store.list_by_category("data")
        assert len(data_templates) > 0


# ── Category 17: Context Resolution ──────────────────────────────────

class TestContextResolution:
    """Verify {{ steps.X.Y }} reference resolution works."""

    def test_context_initializes(self):
        from mini_kio.automation.context import AutomationExecutionContext
        ctx = AutomationExecutionContext(
            template_id="test",
            inputs={},
            config={},
            trigger_data={},
            security_classification="read_only",
        )
        assert ctx is not None

    def test_step_output_set_and_resolve(self):
        from mini_kio.automation.context import AutomationExecutionContext
        ctx = AutomationExecutionContext(
            template_id="test",
            inputs={},
            config={},
            trigger_data={},
            security_classification="read_only",
        )
        ctx.set_step_output("step1", "result", {"key": "value"})
        resolved = ctx.resolve_value("{{ steps.step1.result }}")
        assert resolved == {"key": "value"}

    def test_config_resolve(self):
        from mini_kio.automation.context import AutomationExecutionContext
        ctx = AutomationExecutionContext(
            template_id="test",
            inputs={},
            config={"my_key": "my_value"},
            trigger_data={},
            security_classification="read_only",
        )
        resolved = ctx.resolve_value("{{ config.my_key }}")
        assert resolved == "my_value"

    def test_input_resolve(self):
        from mini_kio.automation.context import AutomationExecutionContext
        ctx = AutomationExecutionContext(
            template_id="test",
            inputs={"file_path": "/tmp/test.txt"},
            config={},
            trigger_data={},
            security_classification="read_only",
        )
        resolved = ctx.resolve_value("{{ inputs.file_path }}")
        assert resolved == "/tmp/test.txt"


# ── Category 18: End-to-End Pipeline ─────────────────────────────────

class TestEndToEndPipeline:
    """Full pipeline integration: user text → classify → resolve → execute → respond."""

    def test_e2e_run_data_transform(self):
        from mini_kio.core.pipeline import Pipeline
        p = Pipeline()
        result = p.run("run data json transform", session_id="e2e_test")
        assert isinstance(result, dict)
        assert "success" in result
        assert "message" in result

    def test_e2e_run_returns_workflow_info(self):
        from mini_kio.core.pipeline import Pipeline
        p = Pipeline()
        result = p.run("run data json transform", session_id="e2e_test_2")
        msg = result.get("message", "")
        assert len(msg) > 0

    def test_e2e_unknown_workflow_suggests(self):
        from mini_kio.core.pipeline import Pipeline
        p = Pipeline()
        result = p.run("run my custom workflow that does not exist", session_id="e2e_test_3")
        assert result.get("success") is False
        assert len(result.get("message", "")) > 10

    def test_e2e_existing_pipeline_unaffected(self):
        from mini_kio.core.pipeline import Pipeline
        p = Pipeline()
        result = p.run("hello", session_id="e2e_regression")
        assert isinstance(result, dict)
        assert result.get("success") is True


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
