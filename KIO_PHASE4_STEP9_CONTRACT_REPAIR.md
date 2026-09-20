# KIO Phase 4 — Step 9: AI_REASONING Output-Field Contract Repair

**Date:** 2026-09-15  
**Status:** COMPLETE  
**Decision:** C — REQUIRES_REPAIR → REPAIRED  
**LOC:** ~64 (dict: 49 lines, prompt template: ~15 lines)  
**Tests:** 23/23 pass, 72/72 regression pass (including Steps 1-7)

---

## 1. Defect Summary

| # | Severity | Description |
|---|----------|-------------|
| 1 | **CRITICAL** | System prompt told LLM "return JSON" but didn't specify which fields → downstream `_extract_outputs()` received None for every required field |
| 2 | MEDIUM | 6 actions had conflicting output-field contracts across templates (superset approach adopted) |

**Root cause:** The adapter system prompt at line ~3636 was generic. It parsed `inputs` but never told the LLM which JSON fields to return.

**Evidence:** Live test (Step 8) showed `classify` returning `{"KIO": "technical_support"}` instead of `{"category": "technical_support", "confidence": 0.88}`.

---

## 2. What Changed

### `mini_kio/core/app_operator.py` (1 file, ~64 LOC)

**A. `_ACTION_OUTPUT_FIELDS` dict (~49 lines)**

Maps all 47 YAML-defined ai_reasoning actions to their required output-field names:

```python
_ACTION_OUTPUT_FIELDS = {
    "classify": ["category", "confidence"],
    "classify_actionable": ["actionable", "confidence"],
    "classify_issue": ["category", "severity"],
    "classify_response": ["classification", "confidence"],
    "triage_ticket": ["topic", "urgency", "sentiment", "suggested_reply"],
    "summarize": ["summary", "action_items", "key_points"],
    # ... 41 more actions ...
    "write_content": ["content", "metadata"],
}
```

For 6 conflicting actions (classify, extract_structured, research, summarize, transcribe, write_content), the **superset** of all fields from all conflicting templates was used.

**B. System prompt modification (~15 lines)**

Before:
```python
system_prompt = f"You are an AI reasoning assistant. Analyze the following and return a JSON response.\n\nInputs: {json.dumps(inputs, indent=2)}"
```

After:
```python
_action_fields = _ACTION_OUTPUT_FIELDS.get(cap)
if _action_fields:
    system_prompt = (
        f"You are an AI reasoning assistant. Analyze the following and return a JSON response.\n\n"
        f"IMPORTANT: Return a JSON object with EXACTLY these fields: {', '.join(_action_fields)}\n"
        f"No markdown fences, no explanation — just a JSON object with those fields.\n\n"
        f"Inputs: {json.dumps(inputs, indent=2)}"
    )
else:
    system_prompt = (
        f"You are an AI reasoning assistant. Analyze the following and return a JSON response.\n\n"
        f"Return a JSON object with fields appropriate for the action '{cap}'.\n"
        f"No markdown fences, no explanation.\n\n"
        f"Inputs: {json.dumps(inputs, indent=2)}"
    )
```

---

## 3. Test Coverage

| Test class | Tests | Purpose |
|------------|-------|---------|
| TestA_ActionOutputFieldsMapping | 5 | Dict exists, 47 entries, key actions have correct fields |
| TestB_SystemPromptConstruction | 2 | Prompt template references the dict, fallback exists |
| TestC_ExtractOutputsSimulation | 4 | Field extraction logic works with correct/incorrect keys |
| TestD_MockAdapterPath | 9 | Full adapter with mocked LLM: classify, summarize, triage, markdown-fence, malformed JSON, empty response, unknown action, invalid inputs, no secrets |
| TestE_ProviderRouting | 3 | Task-tier routing: classify→reasoning, summarize→summarize, research→analysis |

**Total: 23 tests, all pass**

---

## 4. Regression

| Suite | Before | After |
|-------|--------|-------|
| test_p1_contract_fix | 6/6 | 6/6 |
| test_ai_reasoning_routing | 19/19 | 19/19 |
| test_workflow_routing | 24/24 | 24/24 |
| test_ai_reasoning_contract | (new) | 23/23 |
| **Total** | **49/49** | **72/72** |

---

## 5. Baseline

| Metric | Value |
|--------|-------|
| Total YAML templates | 63 (confirmed) |
| Unique ai_reasoning actions | 47 |
| Conflicting output contracts | 6 (resolved via superset) |
| Step 9 LOC | ~64 (target: 30-80) |
| Step 9 tests | 23 |
| Regression | 0 breakage |

---

## 6. What Was NOT Changed

- No new providers added
- No new frameworks added
- No task-tier classification changes (explicitly deferred per Step 9 constraints)
- No changes to `_extract_outputs()` (downstream logic unchanged)
- No changes to YAML templates
- No Step 10 audit created

---

## 7. Step 9 Completion Checklist

- [x] Defect identified and reproduced (Step 8 live evidence)
- [x] Fix implemented (~64 LOC)
- [x] All 47 actions mapped to required output fields
- [x] System prompt includes action-specific field names
- [x] Fallback prompt for unknown actions
- [x] 23 focused tests written and passing
- [x] 72/72 regression suite passes
- [x] 63-template baseline confirmed
- [x] No scope expansion beyond contract repair
- [x] No new providers/frameworks

---

## 8. Next Action

**PHASE 4 FINAL ACCEPTANCE** — Validate the complete Phase 4 implementation (Steps 1-9) for project completion.
