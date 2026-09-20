# KIO Phase 4 — Workflow Provider Implementation

## Audit Verification

Previous audit claimed 7 templates, ~160 LOC. Verified against source:

- **7 templates confirmed** — exact count matches audit
- **9 workflow steps** across 7 templates — confirmed
- **8 distinct workflow actions** required — confirmed
- **LOC: ~138** (121 in workflow_provider.py + 17 in app_operator.py) — within estimate

---

## Existing Workflow Infrastructure

| Component | Status | Location |
|-----------|--------|----------|
| WorkflowExecutionProvider | ✅ Exists | `workflow_provider.py:29` (122 lines) |
| WorkflowEngine | ✅ Exists | `execution/engine.py` (468 lines) |
| Provider registration | ✅ Registered | `providers/__init__.py:17` |
| CapabilityResolver | ✅ Knows workflow | `capability_resolver.py:21` |
| StepRunner _ACTION_MAP | ✅ 11 workflow entries | `step_runner.py:170-180` |
| `_ALWAYS_AVAILABLE` | ✅ workflow included | `capability_resolver.py:35` |

### What Already Existed

The WorkflowExecutionProvider handled lifecycle actions:
- `workflow_create`, `workflow_execute`, `workflow_status`
- `workflow_cancel`, `workflow_pause`, `workflow_resume`
- `workflow_list`, `workflow_progress`

### What Was Missing

The 8 domain actions required by templates were NOT in:
- `APP_CAPABILITIES` (no "workflow" entry)
- `execute_capability()` (no workflow handler)
- `WorkflowExecutionProvider.execute()` (no domain action handlers)

---

## Workflow Action Gap

| Action | Template | Existing Implementation | Route | Status |
|--------|----------|----------------------|-------|--------|
| `route` | classify_and_route | None | StepRunner→execute_capability→workflow_provider | **IMPLEMENTED** |
| `request_approval` | email_autoresponder_approval, content_repurpose | None | StepRunner→execute_capability→workflow_provider | **IMPLEMENTED** |
| `wait_for_ack` | escalation_alert | None | StepRunner→execute_capability→workflow_provider | **IMPLEMENTED** |
| `advance_tier_or_stop` | escalation_alert | None | StepRunner→execute_capability→workflow_provider | **IMPLEMENTED** |
| `transform_records` | json_transform | None | StepRunner→execute_capability→workflow_provider | **IMPLEMENTED** |
| `verify_shape` | json_transform | None | StepRunner→execute_capability→workflow_provider | **IMPLEMENTED** |
| `validate_schema` | webhook_to_store | None | StepRunner→execute_capability→workflow_provider | **IMPLEMENTED** |
| `branch` | invoice_extract_to_sheet | None | StepRunner→execute_capability→workflow_provider | **IMPLEMENTED** |

---

## Implementation

### Changes Made

**1. `mini_kio/core/app_operator.py` (+17 LOC)**

- Added `"workflow"` to `APP_CAPABILITIES` with all 8 action names
- Added `_parse_workflow_kwargs()` helper to parse JSON args
- Added workflow handler in `execute_capability()` (before terminal handler)

Routing chain:
```
StepRunner._run_step("workflow", "branch")
  → _ACTION_MAP[("workflow", "branch")] = "execute_capability"
  → _call_boundary builds target: "workflow::branch::{json}"
  → execute_action → execute_capability
  → APP_CAPABILITIES["workflow"] includes "branch" ✓
  → workflow handler → WorkflowExecutionProvider.execute("branch", ...)
  → _handle_branch(kwargs)
```

**2. `mini_kio/core/providers/workflow_provider.py` (+121 LOC)**

Added 8 domain action handlers as private methods:
- `_handle_route()` — category/confidence routing with default fallback
- `_handle_branch()` — threshold comparison (value >= threshold)
- `_handle_request_approval()` — approval via observation stream
- `_handle_wait_for_ack()` — acknowledgment with timeout
- `_handle_advance_tier()` — escalation tier progression
- `_handle_transform_records()` — deterministic field transforms (upper/lower/strip/number)
- `_handle_verify_shape()` — schema shape validation
- `_handle_validate_schema()` — payload schema validation with type checking

### Architecture Preserved

- All actions route through: Template → StepRunner → ExecutionBoundary → execute_capability → WorkflowExecutionProvider
- No parallel execution path created
- No new engine, planner, or executor introduced
- Security gates untouched
- Idempotency untouched
- Verification untouched
- Observation stream used for approval tracking

---

## Tests

**24 new tests** in `tests/test_workflow_routing.py`:

| Test Class | Tests | Status |
|------------|-------|--------|
| TestWorkflowProviderRegistration | 3 | ✅ PASS |
| TestRouteAction | 3 | ✅ PASS |
| TestBranchAction | 3 | ✅ PASS |
| TestRequestApprovalAction | 1 | ✅ PASS |
| TestWaitForAckAction | 1 | ✅ PASS |
| TestAdvanceTierAction | 3 | ✅ PASS |
| TestTransformRecordsAction | 3 | ✅ PASS |
| TestVerifyShapeAction | 2 | ✅ PASS |
| TestValidateSchemaAction | 3 | ✅ PASS |
| TestUnknownActionRejection | 1 | ✅ PASS |
| TestRoutingFromAppOperator | 1 | ✅ PASS |
| **Total** | **24** | **24/24 PASS** |

**Regression tests:**
- `test_p1_contract_fix.py`: 6/6 PASS
- Pre-existing terminal test failures: unchanged (6 failures are pre-existing, not caused by this step)

---

## 7-Template Evaluation

| # | Template | Workflow Status | Other Blockers | Final Status |
|---|----------|----------------|----------------|--------------|
| 1 | ai.classify_and_route | ✅ route supported | None | **FULLY_EXECUTABLE** |
| 2 | business.email_autoresponder_approval | ✅ request_approval supported | None | **FULLY_EXECUTABLE** |
| 3 | communication.escalation_alert | ✅ wait_for_ack + advance_tier supported | None | **FULLY_EXECUTABLE** |
| 4 | data.json_transform | ✅ transform_records + verify_shape supported | None | **FULLY_EXECUTABLE** |
| 5 | data.webhook_to_store | ✅ validate_schema supported | None | **FULLY_EXECUTABLE** |
| 6 | files.invoice_extract_to_sheet | ✅ branch supported | terminal::append_xlsx_row MISSING | **BLOCKED** |
| 7 | media.content_repurpose | ✅ request_approval supported | None | **FULLY_EXECUTABLE** |

**Results:** 6 FULLY_EXECUTABLE, 0 PARTIALLY_EXECUTABLE, 1 BLOCKED

---

## Security / Idempotency

| Check | Result |
|-------|--------|
| No new heavyweight dependency | ✅ Zero new imports |
| No security bypass | ✅ All actions are deterministic data transforms |
| No alternate executor | ✅ Routes through existing WorkflowExecutionProvider |
| No uncontrolled process spawning | ✅ No subprocess calls in domain handlers |
| Resource guard active | ✅ No RAM/CPU impact (pure Python logic) |
| KIO under 650 MB | ✅ No new memory allocation |
| Idempotency preserved | ✅ Deterministic inputs → deterministic outputs |
| Verification preserved | ✅ Provider.verify() still called |
| Observation stream used | ✅ Approval tracking via obs.workflow() |

---

## Resource Validation

| Metric | Value |
|--------|-------|
| LOC changed | ~138 (121 workflow_provider + 17 app_operator) |
| New dependencies | 0 |
| Files modified | 2 |
| Tests added | 24 |
| Tests passed | 24/24 |
| RAM impact | ~0 MB (pure logic, no caching) |
| Security gates | Untouched |

---

## Remaining Blockers

| Blocker | Templates Affected | Resolution |
|---------|-------------------|------------|
| `terminal::append_xlsx_row` not implemented | files.invoice_extract_to_sheet | Requires openpyxl wrapper (~25 LOC) — separate step |
| 11 terminal YAML misclassifications | 10 templates | YAML-only changes — separate step |

---

## Next Phase 4 Recommendation

**Recommended target: YAML classification corrections**

The 11 terminal YAML misclassifications affect 10 templates. These are YAML-only changes (no code) that reclassify `terminal::render_docx` → `artifact::generate_docx` etc. This would unlock 10 additional templates.

After that, the 3 missing terminal actions (verify_bundle, append_xlsx_row, delegate_to_agent) would unlock the final blocked templates.

**Workflow is now COMPLETE.** All 8 domain actions are implemented and tested. 6 of 7 workflow templates are FULLY_EXECUTABLE. The 1 blocked template is blocked by a terminal action, not a workflow action.
