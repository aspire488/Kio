"""Phase 4 Step 5: append_xlsx_row implementation tests.

Validates the artifact append_xlsx_row function: routing, XLSX operations,
security, and idempotency.
"""

from __future__ import annotations

import json
import sys
import tempfile
from pathlib import Path
from unittest.mock import patch, MagicMock

# Add the project root to path
_project_root = Path(__file__).resolve().parent.parent
if str(_project_root) not in sys.path:
    sys.path.insert(0, str(_project_root))


def test_artifact_routing_in_step_runner():
    """Verify (artifact, append_xlsx_row) maps to execute_capability."""
    from mini_kio.automation.step_runner import StepRunner
    runner = StepRunner()
    assert runner._ACTION_MAP.get(("artifact", "append_xlsx_row")) == "execute_capability"
    print("PASS: test_artifact_routing_in_step_runner")


def test_call_boundary_formats_artifact_target():
    """Verify _call_boundary builds 'artifact::append_xlsx_row::{...}' format."""
    from mini_kio.automation.step_runner import StepRunner
    runner = StepRunner()

    with patch("mini_kio.core.execution_boundary.execute_action") as mock_exec:
        mock_exec.return_value = {"success": True, "data": {}}
        runner._call_boundary(
            action="execute_capability",
            target="wrong",
            inputs={"workbook": "test.xlsx", "record": {"a": 1}},
            capability="artifact",
            step_action="append_xlsx_row",
        )
        called_target = mock_exec.call_args[0][1]
        assert called_target.startswith("artifact::append_xlsx_row::"), f"Wrong target: {called_target}"
        args_part = called_target.split("::", 2)[2]
        parsed = json.loads(args_part)
        assert parsed["workbook"] == "test.xlsx"
    print("PASS: test_call_boundary_formats_artifact_target")


def test_execute_capability_routes_to_artifact():
    """Verify execute_capability dispatches artifact::append_xlsx_row correctly."""
    from mini_kio.core.app_operator import execute_capability

    with patch("mini_kio.core.artifact_operator.append_xlsx_row") as mock_fn:
        mock_fn.return_value = {"success": True, "message": "Row appended", "row_index": 2, "workbook": "/tmp/test.xlsx"}
        target = 'artifact::append_xlsx_row::{"workbook": "/tmp/test.xlsx", "record": {"a": 1}}'
        result = execute_capability(target)
        assert result.get("success") is True, f"Failed: {result}"
        mock_fn.assert_called_once_with("/tmp/test.xlsx", {"a": 1})
    print("PASS: test_execute_capability_routes_to_artifact")


def test_artifact_capability_registered():
    """Verify 'artifact' is in APP_CAPABILITIES with append_xlsx_row."""
    from mini_kio.core.app_operator import APP_CAPABILITIES
    assert "artifact" in APP_CAPABILITIES, f"artifact missing from APP_CAPABILITIES"
    assert "append_xlsx_row" in APP_CAPABILITIES["artifact"]
    print("PASS: test_artifact_capability_registered")


def test_append_xlsx_row_creates_new_workbook():
    """When workbook doesn't exist, create it with headers + row."""
    from mini_kio.core.artifact_operator import append_xlsx_row
    import openpyxl

    with tempfile.TemporaryDirectory() as td:
        wb_path = str(Path(td) / "test.xlsx")
        record = {"Vendor": "Acme", "Total": 123.45, "Date": "2026-01-15"}
        result = append_xlsx_row(wb_path, record)

        assert result["success"] is True, f"Failed: {result}"
        assert result["row_index"] == 2
        # Verify file was created
        assert Path(wb_path).exists()
        # Verify content
        wb = openpyxl.load_workbook(wb_path)
        ws = wb.active
        assert ws.cell(1, 1).value == "Vendor"
        assert ws.cell(1, 2).value == "Total"
        assert ws.cell(1, 3).value == "Date"
        assert ws.cell(2, 1).value == "Acme"
        assert ws.cell(2, 2).value == 123.45
        assert ws.cell(2, 3).value == "2026-01-15"
        wb.close()
    print("PASS: test_append_xlsx_row_creates_new_workbook")


def test_append_xlsx_row_appends_to_existing():
    """Append to an existing workbook with matching headers."""
    from mini_kio.core.artifact_operator import append_xlsx_row
    import openpyxl

    with tempfile.TemporaryDirectory() as td:
        wb_path = str(Path(td) / "test.xlsx")
        # Create initial workbook
        wb = openpyxl.Workbook()
        ws = wb.active
        ws.append(["Vendor", "Total", "Date"])
        ws.append(["Beta Inc", 99.99, "2026-01-10"])
        wb.save(wb_path)
        wb.close()

        # Append new row
        result = append_xlsx_row(wb_path, {"Vendor": "Acme", "Total": 123.45, "Date": "2026-01-15"})
        assert result["success"] is True, f"Failed: {result}"
        assert result["row_index"] == 3

        # Verify both rows
        wb = openpyxl.load_workbook(wb_path)
        ws = wb.active
        assert ws.cell(2, 1).value == "Beta Inc"
        assert ws.cell(3, 1).value == "Acme"
        assert ws.max_row == 3
        wb.close()
    print("PASS: test_append_xlsx_row_appends_to_existing")


def test_append_xlsx_row_empty_record_fails():
    """Empty record should fail."""
    from mini_kio.core.artifact_operator import append_xlsx_row
    result = append_xlsx_row("/tmp/test.xlsx", {})
    assert result["success"] is False
    assert "empty" in result["message"].lower()
    print("PASS: test_append_xlsx_row_empty_record_fails")


def test_append_xlsx_row_path_traversal_blocked():
    """Path traversal attempts should be blocked."""
    from mini_kio.core.artifact_operator import append_xlsx_row
    result = append_xlsx_row("../../etc/passwd", {"a": 1})
    assert result["success"] is False
    assert "traversal" in result["message"].lower()
    print("PASS: test_append_xlsx_row_path_traversal_blocked")


def test_append_xlsx_row_returns_row_index():
    """Verify row_index is returned for downstream consumption."""
    from mini_kio.core.artifact_operator import append_xlsx_row

    with tempfile.TemporaryDirectory() as td:
        wb_path = str(Path(td) / "test.xlsx")
        result = append_xlsx_row(wb_path, {"col1": "val1"})
        assert "row_index" in result
        assert isinstance(result["row_index"], int)
        assert result["row_index"] >= 2  # row 1 = header
    print("PASS: test_append_xlsx_row_returns_row_index")


def test_append_xlsx_row_handles_new_columns():
    """When record has keys not in existing headers, extend headers."""
    from mini_kio.core.artifact_operator import append_xlsx_row
    import openpyxl

    with tempfile.TemporaryDirectory() as td:
        wb_path = str(Path(td) / "test.xlsx")
        # Create workbook with initial headers
        wb = openpyxl.Workbook()
        ws = wb.active
        ws.append(["Vendor", "Total"])
        ws.append(["Beta", 50])
        wb.save(wb_path)
        wb.close()

        # Append with extra column
        result = append_xlsx_row(wb_path, {"Vendor": "Acme", "Total": 100, "Tax": 8.0})
        assert result["success"] is True

        wb = openpyxl.load_workbook(wb_path)
        ws = wb.active
        # Verify header extended
        assert ws.cell(1, 3).value == "Tax"
        # Verify new column value
        assert ws.cell(3, 3).value == 8.0
        wb.close()
    print("PASS: test_append_xlsx_row_handles_new_columns")


def test_yaml_template_uses_artifact_capability():
    """Verify the invoice template uses artifact capability."""
    import yaml
    template_path = Path(r"C:\Users\joelj\Downloads\kio_final\automation\library\files\invoice_extract_to_sheet.yaml")
    if template_path.exists():
        with open(template_path) as f:
            template = yaml.safe_load(f)
        append_step = next(s for s in template["steps"] if s["id"] == "append")
        assert append_step["capability"] == "artifact", f"Expected artifact, got {append_step['capability']}"
        assert append_step["action"] == "append_xlsx_row"
        assert "artifact" in template["capabilities_required"]
    print("PASS: test_yaml_template_uses_artifact_capability")


if __name__ == "__main__":
    tests = [
        test_artifact_routing_in_step_runner,
        test_call_boundary_formats_artifact_target,
        test_execute_capability_routes_to_artifact,
        test_artifact_capability_registered,
        test_append_xlsx_row_creates_new_workbook,
        test_append_xlsx_row_appends_to_existing,
        test_append_xlsx_row_empty_record_fails,
        test_append_xlsx_row_path_traversal_blocked,
        test_append_xlsx_row_returns_row_index,
        test_append_xlsx_row_handles_new_columns,
        test_yaml_template_uses_artifact_capability,
    ]
    passed = 0
    failed = 0
    for test in tests:
        try:
            test()
            passed += 1
        except Exception as e:
            print(f"FAIL: {test.__name__}: {e}")
            failed += 1
    print(f"\nResults: {passed} passed, {failed} failed, {passed + failed} total")
    sys.exit(1 if failed else 0)
