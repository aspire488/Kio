"""Phase 4B: P1 contract fix regression tests.

Validates that _call_boundary() formats the target string correctly
for execute_capability, matching the "app::cap::args" contract that
execute_capability() in app_operator.py expects.
"""

from __future__ import annotations

import json
import sys
from pathlib import Path
from unittest.mock import patch, MagicMock

# Add the project root to path
_project_root = Path(__file__).resolve().parent.parent
if str(_project_root) not in sys.path:
    sys.path.insert(0, str(_project_root))


def test_call_boundary_formats_execute_capability_target():
    """When boundary_action is execute_capability, target must be 'cap::action::json(inputs)'."""
    from mini_kio.automation.step_runner import StepRunner

    runner = StepRunner()

    # Mock execute_action to capture what gets called (patched at source, not local import)
    with patch("mini_kio.core.execution_boundary.execute_action") as mock_exec:
        mock_exec.return_value = {"success": True, "data": {}}

        # Test: ai_reasoning + classify
        runner._call_boundary(
            action="execute_capability",
            target="wrong_format_string",
            inputs={"query": "hello", "context": "test"},
            capability="ai_reasoning",
            step_action="classify",
        )

        # Verify execute_action was called with the correct formatted target
        mock_exec.assert_called_once()
        call_args = mock_exec.call_args
        called_action = call_args[0][0]
        called_target = call_args[0][1]

        assert called_action == "execute_capability", f"Wrong action: {called_action}"
        assert called_target.startswith("ai_reasoning::classify::"), f"Wrong target format: {called_target}"

        # Verify the args portion is valid JSON
        args_part = called_target.split("::", 2)[2]
        parsed_args = json.loads(args_part)
        assert parsed_args == {"query": "hello", "context": "test"}, f"Wrong args: {parsed_args}"

    print("PASS: test_call_boundary_formats_execute_capability_target")


def test_call_boundary_multiple_capabilities():
    """Verify correct formatting for all capability categories that route to execute_capability."""
    from mini_kio.automation.step_runner import StepRunner

    runner = StepRunner()

    test_cases = [
        ("ai_reasoning", "classify", {"query": "test"}),
        ("communication", "send_message", {"channel": "telegram", "text": "hi"}),
        ("github", "get_pr_diff", {"repo": "owner/repo"}),
        ("memory", "store", {"key": "foo", "value": "bar"}),
        ("calendar", "create_event", {"title": "Meeting"}),
        ("mcp_tool", "call", {"server": "github", "tool": "list_repos"}),
        ("workflow", "transform_records", {"records": [1, 2, 3]}),
        ("media", "transcribe", {"file": "audio.wav"}),
        ("terminal", "run", {"command": "ls -la"}),
        ("monitoring", "check_rss", {"url": "https://example.com/feed"}),
        ("artifact", "generate_pdf", {"template": "report.html"}),
        ("data", "read_source", {"source": "database"}),
        ("email", "send_email", {"to": "user@test.com"}),
        ("http", "fetch", {"url": "https://api.example.com"}),
        ("code_project", "scaffold", {"name": "myapp"}),
    ]

    for capability, action, inputs in test_cases:
        with patch("mini_kio.core.execution_boundary.execute_action") as mock_exec:
            mock_exec.return_value = {"success": True, "data": {}}

            runner._call_boundary(
                action="execute_capability",
                target="should_be_overwritten",
                inputs=inputs,
                capability=capability,
                step_action=action,
            )

            called_target = mock_exec.call_args[0][1]
            expected_prefix = f"{capability}::{action}::"
            assert called_target.startswith(expected_prefix), \
                f"Failed for ({capability}, {action}): got {called_target}"

            # Verify JSON args are parseable
            args_part = called_target.split("::", 2)[2]
            parsed = json.loads(args_part)
            assert isinstance(parsed, dict), f"Args not a dict: {parsed}"

    print("PASS: test_call_boundary_multiple_capabilities")


def test_call_boundary_non_execute_capability_unaffected():
    """Non-execute_capability actions must NOT be reformatted."""
    from mini_kio.automation.step_runner import StepRunner

    runner = StepRunner()

    with patch("mini_kio.core.execution_boundary.execute_action") as mock_exec:
        mock_exec.return_value = {"success": True, "data": {}}

        # Test: browser_goto should NOT be reformatted
        runner._call_boundary(
            action="browser_goto",
            target="https://example.com",
            inputs={"url": "https://example.com"},
            capability="browser",
            step_action="navigate",
        )

        mock_exec.assert_called_once()
        called_target = mock_exec.call_args[0][1]
        assert called_target == "https://example.com", \
            f"browser_goto target was incorrectly reformatted: {called_target}"

    print("PASS: test_call_boundary_non_execute_capability_unaffected")


def test_call_boundary_filesystem_passthrough():
    """Filesystem actions must pass inputs as kwargs, not reformat."""
    from mini_kio.automation.step_runner import StepRunner

    runner = StepRunner()

    with patch("mini_kio.core.execution_boundary.execute_action") as mock_exec:
        mock_exec.return_value = {"success": True, "data": {}}

        runner._call_boundary(
            action="read_file",
            target="/tmp/test.txt",
            inputs={"path": "/tmp/test.txt", "encoding": "utf-8"},
            capability="filesystem",
            step_action="read_file",
        )

        mock_exec.assert_called_once()
        call_args = mock_exec.call_args
        # Filesystem should pass inputs as kwargs
        assert call_args[1].get("path") == "/tmp/test.txt" or \
               (len(call_args[0]) >= 3 and call_args[0][2] == "/tmp/test.txt"), \
            f"Filesystem kwargs not passed correctly: {call_args}"

    print("PASS: test_call_boundary_filesystem_passthrough")


def test_execute_capability_splits_correctly():
    """The formatted target must survive execute_capability's split('::', 3)."""
    # Simulate what execute_capability does
    test_cases = [
        ("ai_reasoning", "classify", {"query": "hello"}),
        ("communication", "send_message", {"channel": "telegram"}),
        ("github", "get_pr_diff", {"repo": "owner/repo", "pr": 42}),
    ]

    for capability, action, inputs in test_cases:
        formatted = f"{capability}::{action}::{json.dumps(inputs)}"
        parts = formatted.split("::", 3)

        assert len(parts) >= 3, f"Split produced {len(parts)} parts: {parts}"
        assert parts[0] == capability, f"Wrong app_name: {parts[0]}"
        assert parts[1] == action, f"Wrong cap: {parts[1]}"
        parsed = json.loads(parts[2])
        assert isinstance(parsed, dict), f"Args not a dict: {parsed}"

    print("PASS: test_execute_capability_splits_correctly")


def test_empty_inputs_produce_valid_json():
    """Empty inputs dict must produce valid JSON in the formatted target."""
    from mini_kio.automation.step_runner import StepRunner

    runner = StepRunner()

    with patch("mini_kio.core.execution_boundary.execute_action") as mock_exec:
        mock_exec.return_value = {"success": True, "data": {}}

        runner._call_boundary(
            action="execute_capability",
            target="old_format",
            inputs={},
            capability="ai_reasoning",
            step_action="classify",
        )

        called_target = mock_exec.call_args[0][1]
        args_part = called_target.split("::", 2)[2]
        parsed = json.loads(args_part)
        assert parsed == {}, f"Empty inputs not preserved: {parsed}"

    print("PASS: test_empty_inputs_produce_valid_json")


if __name__ == "__main__":
    test_call_boundary_formats_execute_capability_target()
    test_call_boundary_multiple_capabilities()
    test_call_boundary_non_execute_capability_unaffected()
    test_call_boundary_filesystem_passthrough()
    test_execute_capability_splits_correctly()
    test_empty_inputs_produce_valid_json()
    print("\n=== ALL P1 CONTRACT FIX TESTS PASSED ===")
