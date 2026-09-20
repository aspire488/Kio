# KIO Phase 4 Step 5: append_xlsx_row Implementation

## Summary

Implemented `append_xlsx_row` — the terminal action that routes through the new `artifact` capability to provide deterministic XLSX row appending. This closes the smallest verified runtime gap in the artifact provider audit.

**LOC changed:** ~120 (artifact_operator.py: ~100, app_operator.py: ~20)
**Tests:** 11/11 pass
**Template:** invoice_extract_to_sheet.yaml updated

## Routing Architecture

```
YAML template (artifact::append_xlsx_row)
  → StepRunner._ACTION_MAP[("artifact", "append_xlsx_row")] = "execute_capability"
  → _call_boundary() builds: "artifact::append_xlsx_row::{json(inputs)}"
  → execute_action("execute_capability", target)
  → execute_capability() parses app_name="artifact", cap="append_xlsx_row"
  → artifact handler: parse inputs JSON, call append_xlsx_row(workbook, record)
  → artifact_operator.append_xlsx_row()
```

## Changes Made

### 1. `mini_kio/core/artifact_operator.py` (+100 LOC)

Added `append_xlsx_row()` function after `verify_xlsx()`:

```python
def append_xlsx_row(workbook: str, record: dict, worksheet: str = "") -> dict:
```

**Semantics:**
- Opens existing workbook or creates new one with record keys as headers
- Maps record values to existing header order
- Extends headers when record has new keys not in existing headers
- Returns `row_index` (1-based, header=row 1)
- `worksheet` parameter targets specific sheet (defaults to active)

**Security:**
- Path traversal blocked (`..` in path segments)
- Row count capped at 50,000 (`_MAX_XLSX_ROWS`)
- File size check (20MB limit before opening)
- Empty record rejection

**Verification:**
- ZIP integrity check after write
- Row count validation via XML parsing

### 2. `mini_kio/core/app_operator.py` (+20 LOC)

Added `"artifact"` to `APP_CAPABILITIES`:
```python
"artifact": ["append_xlsx_row", "generate_docx", "generate_pptx",
             "verify_docx", "verify_pptx", "verify_pdf"],
```

Added artifact handler in `execute_capability()`:
```python
if app_name == "artifact":
    # Parse inputs JSON, dispatch to append_xlsx_row or unknown action
```

### 3. `mini_kio/automation/step_runner.py` (1 LOC changed)

Changed mapping from `("terminal", "append_xlsx_row")` to `("artifact", "append_xlsx_row")`.

### 4. YAML Template (1 file)

`files/invoice_extract_to_sheet.yaml`:
- `capabilities_required`: `[ai_reasoning, workflow, terminal]` → `[ai_reasoning, workflow, artifact]`
- `append` step: `capability: terminal` → `capability: artifact`

## Test Results

```
test_artifact_routing_in_step_runner          PASS
test_call_boundary_formats_artifact_target    PASS
test_execute_capability_routes_to_artifact    PASS
test_artifact_capability_registered           PASS
test_append_xlsx_row_creates_new_workbook     PASS
test_append_xlsx_row_appends_to_existing      PASS
test_append_xlsx_row_empty_record_fails       PASS
test_append_xlsx_row_path_traversal_blocked   PASS
test_append_xlsx_row_returns_row_index        PASS
test_append_xlsx_row_handles_new_columns      PASS
test_yaml_template_uses_artifact_capability   PASS

Results: 11 passed, 0 failed
```

Existing test suites:
- P1 contract fix: 6/6 pass
- Terminal routing: 29/31 pass (2 pre-existing failures unrelated to this change)
- Workflow routing: 24/24 pass

## Global 63-Template Re-evaluation

| Status | Count | Delta from Step 4 |
|--------|-------|-------------------|
| FULLY  | 5     | 0                 |
| PARTIAL| 38    | +4                |
| BLOCKED| 20    | -4                |

**Shift:** 4 templates moved from BLOCKED → PARTIAL (artifact now available, but ai_reasoning still missing).

**Template status:**
- `invoice_extract_to_sheet.yaml`: BLOCKED → PARTIAL (artifact + workflow available, ai_reasoning missing)
- 10 templates with artifact steps: all PARTIAL (ai_reasoning required but unavailable)
- 0 templates fully unlocked by this change

## What This Enables

1. **Deterministic XLSX row appending** — no LLM needed for the write operation
2. **Artifact routing** — foundation for future artifact actions (generate_docx, etc.)
3. **Template correctness** — invoice_extract_to_sheet now routes through correct capability
4. **Capability registration** — artifact is now a registered capability in APP_CAPABILITIES

## What This Does NOT Enable

1. **No new templates fully executable** — all 10 artifact templates still require ai_reasoning
2. **No artifact provider class** — routing is ad-hoc in execute_capability(), not through ProviderRegistry
3. **No other artifact actions** — only append_xlsx_row is implemented; generate_docx, verify_docx, etc. remain stubs

## Next Steps

1. Consider implementing ai_reasoning provider to unlock 38 PARTIAL templates
2. Consider implementing remaining artifact actions (generate_docx, generate_pptx, etc.)
3. Consider formalizing artifact as a proper Provider with ProviderRegistry integration
