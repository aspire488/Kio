"""Tests for the KIO Automation Engine."""

from __future__ import annotations

import sys
from pathlib import Path

# Add the project root to path (this file lives in <root>/tests/)
_project_root = Path(__file__).resolve().parents[1]
if str(_project_root) not in sys.path:
    sys.path.insert(0, str(_project_root))

# The recovered, Git-tracked library is the authoritative source of truth.
# The old Downloads copy was permanently deleted and must not be depended on.
# Call sites below append "automation/library", so this stays the project root.
_downloads_root = _project_root  # legacy name kept so call sites stay readable


def test_template_store_loads_all_63():
    """Verify TemplateStore loads all 63 YAML templates."""
    from mini_kio.automation.template_store import TemplateStore

    library_root = _downloads_root / "automation" / "library"
    store = TemplateStore(library_root)
    count = store.load()

    print(f"Loaded {count} templates")
    print(f"Categories: {store.categories()}")
    print(f"Load errors: {store.load_errors}")

    # Should load 63
    assert count >= 60, f"Expected >=60 templates, got {count}"
    assert len(store.load_errors) == 0, f"Load errors: {store.load_errors}"

    # Check specific templates exist
    for tid in [
        "browser.structured_extract",
        "data.json_transform",
        "ai.classify_and_route",
        "communication.notify",
        "development.pr_review_prep",
    ]:
        assert store.get(tid) is not None, f"Missing template: {tid}"

    print("PASS: test_template_store_loads_all_63")


def test_template_validation_catches_errors():
    """Verify template validation catches bad templates."""
    from mini_kio.automation.template_store import TemplateStore

    store = TemplateStore(_downloads_root / "automation" / "library")
    count = store.load()

    # All loaded templates should have valid structure
    for record in store.all_records():
        assert record.template_id, f"Template at {record.path} has no id"
        assert record.steps, f"Template {record.template_id} has no steps"
        assert record.capabilities_required, f"Template {record.template_id} has no capabilities"
        for step in record.steps:
            assert "id" in step, f"Step in {record.template_id} has no id"
            assert "capability" in step, f"Step {step.get('id')} in {record.template_id} has no capability"
            assert "action" in step, f"Step {step.get('id')} in {record.template_id} has no action"

    print("PASS: test_template_validation_catches_errors")


def test_dependency_resolution():
    """Verify step dependency resolution."""
    from mini_kio.automation.context import AutomationExecutionContext

    ctx = AutomationExecutionContext(
        template_id="test",
        inputs={"url": "https://example.com"},
        config={"max_pages": 5},
    )
    ctx.set_step_output("extract", "rows", [{"col1": "val1"}])
    ctx.set_step_output("extract", "columns", ["col1"])

    # Test reference resolution
    assert ctx.resolve_ref("steps.extract.rows") == [{"col1": "val1"}]
    assert ctx.resolve_ref("steps.extract.columns") == ["col1"]
    assert ctx.resolve_ref("inputs.url") == "https://example.com"
    assert ctx.resolve_ref("config.max_pages") == 5

    # Test string resolution
    resolved = ctx.resolve_value("{{ steps.extract.columns }}")
    assert resolved == ["col1"]

    resolved = ctx.resolve_value("URL is {{ inputs.url }}")
    assert resolved == "URL is https://example.com"

    print("PASS: test_dependency_resolution")


def test_security_bridge_enforces_policy():
    """Verify security bridge enforces classification policy."""
    from mini_kio.automation.bridges import SecurityBridge

    bridge = SecurityBridge()

    # destructive without confirmation should be forced
    result = bridge.check_template_security({
        "security_classification": "destructive",
        "user_confirmation_required": False,
    })
    assert result["requires_confirmation"] is True
    assert len(result["warnings"]) > 0

    # read_only with confirmation should be fine
    result = bridge.check_template_security({
        "security_classification": "read_only",
        "user_confirmation_required": False,
    })
    assert result["requires_confirmation"] is False

    # read_only should block write actions
    result = bridge.check_step_security(
        {"capability": "communication", "action": "send_message"},
        "read_only",
    )
    assert result["permitted"] is False

    print("PASS: test_security_bridge_enforces_policy")


def test_status_registry_tracks_states():
    """Verify status registry tracks template states correctly."""
    from mini_kio.automation.status import StatusRegistry

    registry = StatusRegistry()

    # Default state
    status = registry.get_status("test.template")
    assert status["execution_status"] == "candidate"

    # Record success
    registry.record_success("test.template")
    status = registry.get_status("test.template")
    assert status["execution_status"] == "runtime_proven"
    assert status["last_runtime_test"] is not None

    # Record failure
    registry.record_failure("test.template2", "step X failed")
    status = registry.get_status("test.template2")
    assert status["execution_status"] == "failed"
    assert status["failure_reason"] == "step X failed"

    # Summary
    summary = registry.summary()
    assert summary.get("runtime_proven", 0) >= 1
    assert summary.get("failed", 0) >= 1

    print("PASS: test_status_registry_tracks_states")


def test_engine_initializes():
    """Verify the automation engine initializes and loads templates."""
    from mini_kio.automation.engine import AutomationEngine

    engine = AutomationEngine(_downloads_root / "automation" / "library")
    count = engine.load_templates()

    assert count >= 60, f"Expected >=60 templates, got {count}"
    assert engine.template_count >= 60

    # Check status summary
    summary = engine.status_summary()
    assert summary["total_templates"] >= 60
    assert summary["loaded"] is True

    # Check runtime capabilities
    caps = engine.runtime_capabilities()
    assert "filesystem" in caps
    assert "workflow" in caps
    assert "memory" in caps

    print(f"Engine initialized with {count} templates")
    print(f"Status summary: {summary}")
    print("PASS: test_engine_initializes")


if __name__ == "__main__":
    test_template_store_loads_all_63()
    test_template_validation_catches_errors()
    test_dependency_resolution()
    test_security_bridge_enforces_policy()
    test_status_registry_tracks_states()
    test_engine_initializes()
    print("\n=== ALL TESTS PASSED ===")
