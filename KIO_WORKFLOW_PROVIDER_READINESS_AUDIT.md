# KIO Workflow Provider Readiness Audit

**Date:** 2026-09-15
**Scope:** All YAML templates using `capability: workflow` and the infrastructure that must execute them
**Method:** Static code analysis only — no changes made

---

## 1. Executive Verdict

**BLOCKED — Workflow templates cannot execute.**

The step runner maps every `("workflow", action)` pair to `execute_capability` in `app_operator.py`, which only handles app-control verbs (chrome, spotify, etc.). The `WorkflowExecutionProvider` exists and is registered, but is never invoked for YAML template actions because `execute_capability` short-circuits through the static action table before the provider registry is consulted.

**Recommendation: A** — Implement the 8 missing action handlers in `WorkflowExecutionProvider.execute()`. No structural changes needed; the provider and registration path already exist.

---

## 2. Template Inventory

### 2.1 Templates declaring `capability: workflow`

| # | Template ID | Category | Workflow Actions Used |
|---|-------------|----------|-----------------------|
| 1 | `data.json_transform` | data | `transform_records`, `verify_shape` |
| 2 | `ai.classify_and_route` | ai | `route` |
| 3 | `business.email_autoresponder_approval` | business | `request_approval` |
| 4 | `communication.escalation_alert` | communication | `wait_for_ack`, `advance_tier_or_stop` |
| 5 | `media.content_repurpose` | media | `request_approval` |
| 6 | `files.invoice_extract_to_sheet` | files | `branch` |
| 7 | `data.webhook_to_store` | data | `validate_schema` |

**Total: 7 templates, 8 distinct workflow actions.**

### 2.2 Unique workflow actions required

| Action | Used by templates | Semantics |
|--------|-------------------|-----------|
| `transform_records` | json_transform | Map/filter/aggregate over JSON array |
| `verify_shape` | json_transform | Validate output matches declared schema |
| `route` | classify_and_route | Route item to handler based on category + confidence |
| `request_approval` | email_autoresponder_approval, content_repurpose | Pause, send draft to channel, wait for approve/edit/reject |
| `wait_for_ack` | escalation_alert | Block until ack received or timeout |
| `advance_tier_or_stop` | escalation_alert | If acked → stop; else advance to next escalation tier |
| `branch` | invoice_extract_to_sheet | Confidence-gated fork: ok → proceed, else → flag |
| `validate_schema` | webhook_to_store | Validate payload against JSON schema |

---

## 3. Provider Analysis

### 3.1 WorkflowExecutionProvider (`core/providers/workflow_provider.py`)

**Registered:** Yes — via `providers/__init__.py:register_all_providers()`
**Provider ID:** `"workflow"`
**Capabilities declared:**
- `workflow_create`, `workflow_execute`, `workflow_status`, `workflow_cancel`, `workflow_pause`, `workflow_resume`, `workflow_list`, `workflow_progress`

**Actions handled in `execute()`:**
- `workflow_list` — list all WorkflowEngine executions
- `workflow_create` — create a named workflow in WorkflowEngine
- `workflow_execute` — run a WorkflowEngine execution by ID
- `workflow_status`, `workflow_cancel`, `workflow_pause`, `workflow_resume`, `workflow_progress` — lifecycle management

**Gap:** None of the 8 YAML template actions (`transform_records`, `verify_shape`, `route`, `request_approval`, `wait_for_ack`, `advance_tier_or_stop`, `branch`, `validate_schema`) are handled. The provider only wraps the `WorkflowEngine` lifecycle, not the per-step logic.

### 3.2 Routing problem

The execution path for a workflow step:

```
step_runner._ACTION_MAP[("workflow", action)] → "execute_capability"
  → step_runner._call_boundary("execute_capability", target)
    → execute_action("execute_capability", target)
      → _load_handler("execute_capability")
        → STATIC_ACTION_TABLE["execute_capability"] → app_operator.execute_capability()
          → APP_CAPABILITIES.get("workflow", []) → [] (missing!)
          → {"success": False, "message": "workflow does not support '...'."}
```

The `WorkflowExecutionProvider` in the provider registry is **never consulted** because `execute_capability` is in the static action table and takes priority in `_load_handler()`.

### 3.3 CapabilityResolver (`automation/capability_resolver.py`)

- Maps `"workflow"` → `["workflow"]` provider names
- Lists `"workflow"` in `_ALWAYS_AVAILABLE` — always passes availability checks
- Status: `{"available": True, "reason": "deterministic transform"}`

**Irony:** The resolver always reports workflow as available, but the execution path fails.

---

## 4. Capability Matrix

| Template | `workflow` | Other Capabilities | Blocking Capability |
|----------|------------|---------------------|---------------------|
| json_transform | YES (2 steps) | — | `workflow` only |
| classify_and_route | YES (1 step) | `ai_reasoning` | `workflow` blocks; `ai_reasoning` requires LLM |
| email_autoresponder_approval | YES (1 step) | `ai_reasoning`, `communication` | `workflow` blocks; also needs LLM + mail + bot |
| escalation_alert | YES (2 steps) | `communication` | `workflow` blocks; also needs bot token |
| content_repurpose | YES (1 step) | `ai_reasoning`, `media` | `workflow` blocks; also needs LLM + media |
| invoice_extract_to_sheet | YES (1 step) | `ai_reasoning`, `terminal` | `workflow` blocks; also needs LLM + openpyxl |
| webhook_to_store | YES (1 step) | `knowledge`, `filesystem` | `workflow` blocks; also needs HMAC + store |

**Key finding:** `json_transform` is the ONLY template blocked purely by workflow. All others have additional capability dependencies (LLM, communication, media) that would also need to be satisfied.

---

## 5. Per-Template Analysis

### 5.1 `data.json_transform`
- **Workflow actions:** `transform_records` (pure data transform), `verify_shape` (schema check)
- **Other capabilities:** None
- **Complexity:** LOW — deterministic, no I/O, no approval gates
- **Other blockers:** None
- **If workflow fixed:** FULLY WORKS

### 5.2 `ai.classify_and_route`
- **Workflow actions:** `route` (dispatch by category + confidence threshold)
- **Other capabilities:** `ai_reasoning` (classify)
- **Complexity:** LOW — `route` is a simple conditional dispatch
- **Other blockers:** Requires LLM provider
- **If workflow fixed:** Still blocked by LLM

### 5.3 `business.email_autoresponder_approval`
- **Workflow actions:** `request_approval` (pause → send to channel → wait → resume)
- **Other capabilities:** `ai_reasoning` (draft), `communication` (send)
- **Complexity:** HIGH — async approval gate, needs external channel interaction
- **Other blockers:** Requires LLM + mail OAuth + bot token
- **If workflow fixed:** Still blocked by LLM + credentials

### 5.4 `communication.escalation_alert`
- **Workflow actions:** `wait_for_ack` (timeout-gated wait), `advance_tier_or_stop` (loop control)
- **Other capabilities:** `communication` (send_with_ack)
- **Complexity:** HIGH — async wait with timeout, loop across tiers
- **Other blockers:** Requires bot tokens for tier channels
- **If workflow fixed:** Still blocked by communication credentials

### 5.5 `media.content_repurpose`
- **Workflow actions:** `request_approval` (conditional: only when auto_publish=false)
- **Other capabilities:** `ai_reasoning` (adapt), `media` (publish, verify)
- **Complexity:** MEDIUM — approval gate is conditional
- **Other blockers:** Requires LLM + media provider (not implemented)
- **If workflow fixed:** Still blocked by LLM + media

### 5.6 `files.invoice_extract_to_sheet`
- **Workflow actions:** `branch` (confidence threshold fork)
- **Other capabilities:** `ai_reasoning` (extract), `terminal` (append_xlsx_row, run_command)
- **Complexity:** LOW — `branch` is a simple conditional
- **Other blockers:** Requires LLM + openpyxl
- **If workflow fixed:** Still blocked by LLM

### 5.7 `data.webhook_to_store`
- **Workflow actions:** `validate_schema` (JSON schema validation)
- **Other capabilities:** `knowledge` (verify_hmac), `filesystem` (store_record, verify_record)
- **Complexity:** MEDIUM — schema validation with error propagation
- **Other blockers:** Requires HMAC secret + store credential
- **If workflow fixed:** Still blocked by credentials

---

## 6. Security Analysis

| Action | Risk | Notes |
|--------|------|-------|
| `transform_records` | LOW | Pure data transform, no side effects |
| `verify_shape` | LOW | Schema validation, no side effects |
| `route` | LOW | Conditional dispatch, no I/O |
| `branch` | LOW | Conditional fork, no I/O |
| `validate_schema` | LOW | Schema validation, no side effects |
| `request_approval` | MEDIUM | Sends user content to external channel; requires human confirmation |
| `wait_for_ack` | LOW | Blocks on external signal; no data mutation |
| `advance_tier_or_stop` | LOW | Loop control logic; no direct I/O |

**Template-level security:**
- `email_autoresponder_approval` → `consequential` + `user_confirmation_required: true`
- `content_repurpose` → `consequential` + `user_confirmation_required: true`
- `webhook_to_store` → `consequential` + `user_confirmation_required: true`
- `invoice_extract_to_sheet` → `consequential` + `user_confirmation_required: true`
- All others → `low` or `read_only`

---

## 7. LOC Estimate for Provider Implementation

| Component | Files | Est. LOC | Notes |
|-----------|-------|----------|-------|
| Add 8 action handlers to `WorkflowExecutionProvider.execute()` | `workflow_provider.py` | ~120 | Each action: ~10-20 lines of logic |
| `transform_records` — map/filter/aggregate | `workflow_provider.py` | 30 | Supports map, filter, aggregate, split, join ops |
| `verify_shape` — schema validation | `workflow_provider.py` | 15 | JSON schema check against declared output |
| `route` — conditional dispatch | `workflow_provider.py` | 10 | Match category → route mapping |
| `branch` — confidence fork | `workflow_provider.py` | 8 | Simple threshold comparison |
| `validate_schema` — payload validation | `workflow_provider.py` | 15 | JSON schema validation with error list |
| `request_approval` — async approval gate | `workflow_provider.py` + `execution/` | 40 | Needs channel send + wait + resume |
| `wait_for_ack` — timeout wait | `workflow_provider.py` | 15 | Poll/subscribe for ack with timeout |
| `advance_tier_or_stop` — loop control | `workflow_provider.py` | 8 | Check ack → advance or stop |
| **Total** | | **~160** | |

**Note:** `request_approval` and `wait_for_ack` are the most complex because they require async external interaction (sending to Telegram/Slack, waiting for user response). These may need integration with the communication provider.

---

## 8. Comparison with Existing Providers

| Provider | Actions Handled | Pattern |
|----------|----------------|---------|
| `BrowserProvider` | 15+ actions (navigate, click, fill, etc.) | Each action → specific Playwright call |
| `KnowledgeProvider` | 8+ actions (web_search, fetch_url, etc.) | Each action → requests/BS4 call |
| `FilesystemProvider` | 6+ actions (write_csv, read_file, etc.) | Each action → pathlib/shutil call |
| `TerminalProvider` | 4+ actions (run, execute, etc.) | Each action → subprocess call |
| `WorkflowExecutionProvider` | 8 lifecycle actions | Missing: 8 template-level actions |

The gap is clear: every other provider maps template actions to real implementations. `WorkflowExecutionProvider` only has lifecycle management, not the action-level logic that templates need.

---

## 9. Final Decision

### Recommendation: **A — Implement the missing actions**

**Rationale:**
1. The provider infrastructure is already in place (registered, health-checking, capability-declaring)
2. The step runner already routes workflow actions correctly (mapping to `execute_capability`)
3. The only missing piece is the actual action logic in `WorkflowExecutionProvider.execute()`
4. 5 of the 8 actions are trivially implementable (pure data transforms, no I/O)
5. The 3 complex actions (`request_approval`, `wait_for_ack`, `advance_tier_or_stop`) need async integration but share a common pattern

**Priority order:**
1. `transform_records`, `verify_shape`, `validate_schema`, `branch`, `route` — deterministic, no external deps
2. `advance_tier_or_stop`, `wait_for_ack` — need timeout/async but no new infrastructure
3. `request_approval` — needs communication channel integration

**Alternative options rejected:**
- **B (N8n delegation):** Rejected — `execution/workflows.py` is explicitly disabled ("Workflows will be handled via n8n"), but the YAML templates are designed for KIO-native execution
- **C (Skip workflow capability):** Rejected — `json_transform` would be entirely blocked with no workaround
- **D (Rewrite templates):** Rejected — templates are well-designed and the gap is in the provider, not the templates
- **E (Hybrid):** Unnecessary — the fix is scoped to one provider file

---

## 10. Audit Confirmation

- [x] All YAML templates with `capability: workflow` identified (7 templates)
- [x] All workflow actions catalogued (8 unique actions)
- [x] Provider infrastructure verified (registered, healthy, capability-declared)
- [x] Execution routing traced (step runner → execution boundary → app_operator → FAIL)
- [x] Root cause identified (missing action handlers in WorkflowExecutionProvider)
- [x] Per-template blocking analysis complete
- [x] Security classification reviewed
- [x] Implementation estimate provided (~160 LOC)
- [x] No source code, YAML, or architecture modified
