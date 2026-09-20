# KIO Phase 4 — AI_REASONING Live Runtime Acceptance Audit

**Date:** 2026-09-15  
**Auditor:** opencode (automated)  
**Scope:** Full-path live runtime acceptance of `ai_reasoning` provider  
**Decision:** **C — REQUIRES_REPAIR** (1 critical defect, 2 medium defects)

---

## 1. Executive Summary

The `ai_reasoning` adapter was wired in Step 7 and makes real LLM calls through the full provider chain. **However, the adapter has a concrete correctness defect: the system prompt does not specify which output fields each action must return.** Live testing confirmed the LLM returns valid JSON, but the field names don't match what downstream YAML steps expect. This means all 47 `ai_reasoning` actions across 46 templates would produce `None` for their declared output fields when executed through the full automation path.

**Bottom line:** The adapter calls real LLMs and returns `success: true`, but downstream steps would silently receive `None` values because the LLM's JSON keys don't match the YAML output contracts.

---

## 2. Provider Configuration (VERIFIED)

| Provider | Enabled | Model | Priority |
|----------|---------|-------|----------|
| Gemini | YES | gemini-2.5-flash | 0 (primary) |
| Groq | YES | openai/gpt-oss-120b | 1 |
| HuggingFace | YES | Qwen/Qwen3-32B | 2 |
| OpenRouter | YES | deepseek/deepseek-chat-v3-0324:free | 3 |
| Together AI | YES | (configured) | 4 |
| Cerebras | YES | gpt-oss-120b | 5 |
| SambaNova | YES | Llama-2-7b-chat-hf | 6 |
| Fireworks | YES | llama-v2-7b | 7 |
| Ollama | YES (local) | qwen3:8b | 8 |

**Primary cognition provider:** Gemini (gemini-2.5-flash)  
**Failover chain:** Gemini → Groq → HF → OpenRouter → Together → Cerebras → SambaNova → Fireworks → Ollama  
**Provider chain timeout:** 10s total, 5s per provider  
**Credentials present:** YES (all API keys loaded from .env)

---

## 3. Execution Path Verification

### Path: YAML → StepRunner → execute_capability → ai_reasoning adapter → ask_llm_sync → ask_llm → LLMGateway → Provider → Response

```
[VERIFIED] YAML template parsed correctly
[VERIFIED] StepRunner._ACTION_MAP maps all 52 actions to "execute_capability"
[VERIFIED] _call_boundary builds target: "ai_reasoning::action::{json_inputs}"
[VERIFIED] execute_capability() parses target into app_name="ai_reasoning", cap=action, args=json
[VERIFIED] ai_reasoning branch in execute_capability() constructs prompt from inputs
[VERIFIED] ask_llm_sync() called with task tier, system_prompt, timeout=20, max_tokens=1024
[VERIFIED] ask_llm() routes through LLMGateway with task-tier provider preference
[VERIFIED] LLMGateway tries providers in priority order with 5s/provider timeout
[VERIFIED] Response parsed: JSON extracted, markdown fences stripped
[VERIFIED] Non-JSON fallback: wrapped as {"text": "<raw>"}
[VERIFIED] _normalize_public_result() wraps final result
```

---

## 4. Live Test Results

### Test 1: `classify` action (reasoning tier)
- **Input:** `{"item": "My laptop battery dies at 40 percent", "categories": ["technical_support", "billing", "general_inquiry"]}`
- **LLM response:** `{"KIO": "technical_support"}`
- **Expected outputs:** `[category, confidence]`
- **Result:** `success: true` but `category` and `confidence` would be `None`
- **DEFECT:** LLM returned `"KIO"` key instead of `"category"`, no `confidence` field
- **Elapsed:** 9,444ms (Gemini timeout → Groq failover)

### Test 2: `summarize` action (summarize tier)
- **Input:** Quarterly report text
- **LLM response:** Detailed structured JSON with `period`, `revenue_change`, etc.
- **Expected outputs:** `[summary, action_items]`
- **Result:** `success: true` but `summary` and `action_items` would be `None`
- **DEFECT:** LLM returned domain-specific structure, not the declared output fields
- **Elapsed:** 2,622ms

### Test 3: `triage_ticket` action (reasoning tier)
- **Input:** Support ticket with subject and body
- **LLM response:** `{"category": "Authentication", "priority": "High", "urgency": "Urgent"}`
- **Expected outputs:** `[topic, urgency, sentiment, suggested_reply]`
- **Result:** `success: true` but `topic`, `sentiment`, `suggested_reply` would be `None`
- **DEFECT:** LLM returned `category` instead of `topic`, missing `sentiment` and `suggested_reply`
- **Elapsed:** 6,816ms

---

## 5. JSON Contract Audit

### 5.1 Downstream Output Expectations (47 actions across 46 templates)

Every `ai_reasoning` step declares specific output fields that downstream steps consume via `{{ steps.X.field }}` references:

| Action | Template | Declared Outputs | Live Test Match? |
|--------|----------|-----------------|------------------|
| classify | classify_and_route | category, confidence | NO — LLM returns "KIO" key |
| classify | email_label_ai | label, confidence | UNTESTED |
| classify_actionable | email_to_task | is_actionable, task_title, due, priority | UNTESTED |
| classify_issue | github_issue_triage | type, labels, priority, missing_info | UNTESTED |
| classify_response | form_intake | tag | UNTESTED |
| summarize | transcribe_summarize | summary, action_items | NO — LLM returns different structure |
| summarize | document_summarize | summary, key_points, action_items | UNTESTED |
| triage_ticket | support_ticket_triage | topic, urgency, sentiment, suggested_reply | NO — missing 3 of 4 fields |
| chat | chat_assistant | reply | UNTESTED |
| detect_pii | csv_pii_scrub | spans, columns_affected | UNTESTED |
| verify_no_pii | csv_pii_scrub | verified, residual | UNTESTED |
| ... (36 more actions) | ... | ... | UNTESTED |

### 5.2 Root Cause

The adapter's system prompt is:
```
"You are an AI reasoning engine. Analyze the input and return
a JSON object with the requested fields. Return ONLY valid JSON,
no markdown fences, no explanation."
```

**This prompt does not tell the LLM WHICH fields to return.** The LLM invents its own field names based on the input content, which almost never match the YAML-declared output fields.

### 5.3 What Would Happen in Production

1. YAML template parsed → step declares `outputs: [category, confidence]`
2. StepRunner calls `execute_capability("ai_reasoning::classify::{...}")`
3. Adapter calls LLM → gets `{"KIO": "technical_support"}`
4. Adapter returns `{"success": true, "message": "...", "KIO": "technical_support"}`
5. `_extract_outputs()` looks for `category` and `confidence` in result → **both are None**
6. Downstream step receives `category=None, confidence=None` → **silent failure**

---

## 6. Task-Tier Routing Analysis

The adapter classifies actions into three tiers that select preferred LLM provider:

| Tier | Actions (adapter) | YAML Actions | Provider Preference |
|------|-------------------|--------------|---------------------|
| reasoning | 11 actions (classify, detect_pii, etc.) | 3 used in YAML | Gemini |
| summarize | 5 actions (summarize, summarize_*) | 5 used in YAML | Groq |
| analysis | default for everything else | 39 actions | Gemini |

**Issue:** 39 of 47 YAML actions fall into the default "analysis" tier. This is functionally correct (all route to Gemini), but the tier classification is inaccurate — actions like `compose_brief`, `draft_reply`, `research` are not "analysis" tasks.

**Impact:** LOW — provider selection still works, just suboptimal for some actions.

---

## 7. Failure / Fallback Behavior

| Scenario | Behavior | Verified? |
|----------|----------|-----------|
| LLM returns None | Returns `success: false, message: "LLM returned no content"` | YES (mock test) |
| LLM returns non-JSON | Wraps as `{"text": "<raw>"}`, `success: true` | YES (mock test + live) |
| LLM returns markdown-fenced JSON | Strips fences, parses JSON | YES (mock test) |
| Invalid inputs JSON | Returns `success: false, message: "Invalid inputs JSON"` | YES (mock test) |
| Unknown action | Returns `success: false, message: "Unknown action: ..."` | YES (mock test) |
| Provider timeout | Gateway tries next provider in chain | YES (live: Gemini→Groq) |
| All providers exhausted | Returns None → adapter returns "LLM returned no content" | NOT TESTED (all providers enabled) |
| Gemini deprecation warning | Logged but does not affect functionality | YES (observed in live test) |

---

## 8. Security Audit

| Check | Status | Details |
|-------|--------|---------|
| API keys in output | PASS | No API keys leaked in any test output |
| Shell execution | N/A | ai_reasoning uses LLM calls, not shell |
| SecurityBridge active | PASS | Verified in execution_boundary.py |
| CredentialBridge active | PASS | Verified in execution_boundary.py |
| Input validation | PASS | JSON parse errors handled gracefully |
| Output sanitization | PASS | No execution claims or authority hallucinations in output |
| LLM output sanitization | PASS | `_sanitize_llm_output()` strips execution claims and authority hallucinations |
| Markdown fence stripping | PASS | Handles ```json...``` wrappers correctly |
| Provider secrets in logs | PASS | API keys never logged (checked config.py, llm_router.py) |

---

## 9. Resource Audit

| Metric | Value | Threshold | Status |
|--------|-------|-----------|--------|
| classify latency | 9,444ms | 20,000ms (adapter timeout) | PASS |
| summarize latency | 2,622ms | 20,000ms | PASS |
| triage_ticket latency | 6,816ms | 20,000ms | PASS |
| Provider chain budget | 10s total, 5s/provider | — | Within bounds |
| Max tokens per call | 1,024 | 4,096 (gateway cap) | PASS |
| Memory overhead | Negligible (HTTP calls only) | 650MB total | PASS |

---

## 10. Test Suite Status

| Test File | Result | Notes |
|-----------|--------|-------|
| test_ai_reasoning_routing.py | **19/19 PASS** | All adapter wiring tests pass |
| test_p1_contract_fix.py | 6/6 PASS | P1 contract still valid |
| test_workflow_routing.py | 24/24 PASS | Workflow handler unchanged |
| test_terminal_routing.py | 25/31 (6 pre-existing) | No regression |

---

## 11. Template Reconciliation (63 templates)

| Capability | Templates | Steps | Actions | Status |
|------------|-----------|-------|---------|--------|
| ai_reasoning | 46 | 58 | 47 unique | **DEFECT — output contract broken** |
| terminal | 1 | 1 | 1 | FULL (Step 1) |
| workflow | 1 | 7 | 7 | FULL (Step 2) |
| browser | 1 | 2 | 2 | DEFERRED |
| knowledge | 1 | 1 | 1 | DEFERRED |
| memory | 1 | 1 | 1 | DEFERRED |
| communication | 1 | 1 | 1 | DEFERRED |
| github | 1 | 1 | 1 | DEFERRED |
| media | 1 | 1 | 1 | DEFERRED |
| calendar | 1 | 1 | 1 | DEFERRED |
| artifact | 1 | 2 | 2 | FULL (Step 5: append_xlsx_row) |

**Post-Step-7 baseline:** FULL 31, PARTIAL 32, BLOCKED 0  
**Post-Step-8 correction:** 31 FULL templates that use `ai_reasoning` steps have broken output contracts → **effective PARTIAL count increases by up to 31** (templates where ai_reasoning is the ONLY step that provides outputs to downstream consumers).

---

## 12. Concrete Defects Found

### DEFECT-1: System Prompt Missing Output Field Specifications (CRITICAL)

**Location:** `mini_kio/core/app_operator.py:3585-3589`  
**Impact:** ALL 47 ai_reasoning actions return wrong JSON structure → downstream steps get None  
**Root cause:** Generic system prompt doesn't specify which fields each action must return  
**Evidence:** Live tests show LLM returns invented field names ("KIO", "period", "category" instead of "topic")  
**Fix:** Add action-specific field specifications to system prompt (lookup table mapping action → required output fields)  
**Effort:** ~30 lines (dict + prompt interpolation)  
**Priority:** P0 — blocks all ai_reasoning automation templates

### DEFECT-2: Task-Tier Classification Mismatch (MEDIUM)

**Location:** `mini_kio/core/app_operator.py:3571-3582`  
**Impact:** 39 of 47 actions classified as "analysis" instead of their natural tier  
**Root cause:** `_reasoning_actions` and `_summarize_actions` sets don't cover all YAML actions  
**Evidence:** Audit script shows 39 actions in default tier  
**Fix:** Expand classification sets or use action-name prefix matching  
**Effort:** ~15 lines  
**Priority:** P1 — suboptimal provider selection, not correctness

### DEFECT-3: Gemini Provider Timeout on First Call (LOW)

**Location:** Provider chain in llm_gateway.py  
**Impact:** First Gemini call timed out, fell back to Groq (added ~7s latency)  
**Root cause:** Gemini API response time exceeded 5s provider budget  
**Evidence:** "Gateway: 'gemini' timeout" in live test stderr  
**Fix:** Increase GEMINI_TIMEOUT_S or investigate Gemini API latency  
**Effort:** Config change  
**Priority:** P2 — failover works, just slower

---

## 13. What Step 7 Actually Delivered vs What Was Claimed

Step 7 claimed:
> "Post-Step-7 baseline: FULL 31, PARTIAL 32, BLOCKED 0"

**Reality:** The 31 "FULL" templates that use `ai_reasoning` steps are only FULL at the **code wiring** level (action → execute_capability → LLM call). At the **output contract** level (LLM returns fields matching YAML declarations), they are effectively **PARTIAL** because the adapter doesn't instruct the LLM which fields to return.

The Step 7 test suite (`test_ai_reasoning_routing.py`) tests adapter wiring with mocks — it verifies the code path works but does NOT verify the LLM returns the correct field structure. This is a test coverage gap, not a Step 7 bug per se.

---

## 14. Decision

### **C — REQUIRES_REPAIR**

**Rationale:**
- 1 critical defect (DEFECT-1) causes ALL 47 ai_reasoning actions to return wrong output structure
- Live testing confirms the defect is real, not theoretical
- The fix is well-scoped (~30 lines in app_operator.py)
- Without the fix, no ai_reasoning automation template can complete its downstream steps

**What must be repaired before acceptance:**
1. Add action-specific output field specifications to the adapter's system prompt
2. Optionally: expand task-tier classification (DEFECT-2)

**What is already accepted:**
- Adapter wiring (code path from YAML → LLM → response)
- Provider chain failover
- Security controls
- Error handling
- JSON parsing with markdown fence stripping

---

## 15. Recommended Next Step

**Step 9: Fix DEFECT-1 (output field specifications)** — Add a lookup table mapping each of the 47 actions to its required output fields, and append this to the system prompt so the LLM knows exactly which JSON keys to return.

Estimated effort: 30 minutes. This is a single-file change in `app_operator.py`.
