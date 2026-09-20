# KIO Phase 4 — Terminal Residual-Action Reconciliation

## Executive Summary

The 14 "terminal-dependent" templates use **15 distinct terminal actions**. Only **1 action** (`run_command`) is genuinely terminal-owned. **12 actions** have existing implementations in `artifact_operator.py` or `document_operator.py` but are misclassified as terminal. **2 actions** have no implementation anywhere.

**Verdict:** The terminal problem is a **classification problem**, not an implementation problem. The YAML templates point to the wrong capability. The actual implementations already exist in the correct modules — they just need the templates to call the right capability name.

---

## 1. Re-Enumeration: 14 Templates, 15 Terminal Actions

| # | Template | Terminal Steps | Actions Used |
|---|----------|---------------|--------------|
| 1 | `artifacts/data_to_xlsx` | render, recalc, verify | run_command ×3 |
| 2 | `artifacts/meeting_to_report` | render_docx, verify | render_docx, verify_docx |
| 3 | `artifacts/multiformat_report` | render_docx, render_pdf, render_pptx, verify | render_docx, render_pdf_from_html, render_pptx, verify_bundle |
| 4 | `artifacts/research_to_docx` | render, verify | render_docx, verify_docx |
| 5 | `artifacts/research_to_pdf` | render, verify | render_pdf_from_html, verify_pdf |
| 6 | `artifacts/research_to_pptx` | render, verify | render_pptx, verify_pptx |
| 7 | `development/issue_to_implementation` | implement | delegate_to_agent |
| 8 | `development/repo_health_report` | render, verify | render_docx, verify_docx |
| 9 | `development/scaffold_project` | scaffold, git_init, open | scaffold, git_init, open_vscode |
| 10 | `files/duplicate_detector` | report | render_markdown |
| 11 | `files/invoice_extract_to_sheet` | append, verify | append_xlsx_row, run_command |
| 12 | `productivity/weekly_review` | render | render_docx |
| 13 | `research/competitor_monitor` | report | render_docx |
| 14 | `research/web_scrape_to_report` | render, verify | render_docx, verify_docx |

**Total terminal-tagged steps:** 34
**Distinct terminal actions:** 15

---

## 2. Action Ownership Trace

For each action, traced to the actual KIO implementation:

### TERMINAL_OWNED (1 action)

| Action | Provider | Function | Location | Status |
|--------|----------|----------|----------|--------|
| `run_command` | TerminalProvider | `execute("run_command", cmd)` | `terminal_provider.py:57` | ✅ WORKING |

### ARTIFACT_OWNED (9 actions — misclassified as terminal)

| Action | Actual Function | Location | Notes |
|--------|----------------|----------|-------|
| `render_docx` | `artifact_operator.build_docx()` | `artifact_operator.py:1713` | Rich docx via python-docx, stdlib fallback |
| `verify_docx` | `document_operator.verify_docx()` | `document_operator.py:252` | ZIP integrity + word count |
| `render_pdf_from_html` | `artifact_operator._docx_to_pdf()` | `artifact_operator.py:1437` | Word COM export, bounded timeout |
| `verify_pdf` | `artifact_operator.verify_pdf()` | `artifact_operator.py:1410` | PDF header + page count check |
| `render_pptx` | `artifact_operator.build_pptx()` | `artifact_operator.py:1379` | Rich pptx via python-pptx, stdlib fallback |
| `verify_pptx` | `artifact_operator.verify_pptx()` | `artifact_operator.py:1383` | ZIP integrity + slide count |
| `scaffold` | `artifact_operator.create_code_project()` | `artifact_operator.py:1734` | Full project skeleton with LanguageSpec |
| `open_vscode` | `artifact_operator.open_in_editor()` | `artifact_operator.py:1956` | VS Code detection + launch |
| `render_markdown` | `filesystem` (no dedicated function) | — | Could be `run_command("echo ... > file.md")` or a new artifact action |

### DOCUMENT_OWNED (1 action — misclassified as terminal)

| Action | Actual Function | Location | Notes |
|--------|----------------|----------|-------|
| `verify_docx` | `document_operator.verify_docx()` | `document_operator.py:252` | Also imported in `artifact_operator.py:54` |

### MISSING (3 actions — no implementation anywhere)

| Action | Intended Purpose | Notes |
|--------|-----------------|-------|
| `verify_bundle` | Verify all formats in multiformat report | No function exists. Would compose verify_docx + verify_pdf + verify_pptx |
| `delegate_to_agent` | Run coding agent in sandbox | No function exists. Would invoke aider/openhands/claude_code subprocess |
| `append_xlsx_row` | Append row to Excel workbook | No function exists. Could use openpyxl (already installed) |

### SEMANTICALLY_MISCLASSIFIED (1 action)

| Action | Actual Ownership | Notes |
|--------|-----------------|-------|
| `render_markdown` | FILESYSTEM_OWNED | File writing, not terminal. Could be `filesystem::write_file` |

---

## 3. Routing Chain Trace

For `terminal::render_docx`, the full execution path:

```
StepRunner._run_step("terminal", "render_docx")
  → _ACTION_MAP[("terminal", "render_docx")] = "execute_capability"    [step_runner.py:287]
  → _call_boundary("execute_capability", ...)                          [step_runner.py:327]
    → builds target: "terminal::render_docx::{...}"                    [step_runner.py:399]
    → execute_action("execute_capability", "terminal::render_docx::...") [execution_boundary.py:929]
      → _load_handler("execute_capability") → app_operator.execute_capability [app_operator.py:3178]
        → APP_CAPABILITIES["terminal"] = ["run_command", "clipboard_copy", "clipboard_paste"] [line 3175]
        → "render_docx" NOT in list
        → BUT: terminal handler at line 3476 catches app_name == "terminal"
        → TerminalProvider.execute("render_docx", args)
        → Returns: {"success": False, "message": "TerminalProvider: unknown action render_docx"}
```

**Result:** `terminal::render_docx` reaches TerminalProvider but fails with "unknown action" because TerminalProvider only implements run_command/clipboard_copy/clipboard_paste.

---

## 4. Template-Level Truth (Post-Reconciliation)

| # | Template | Current State | Root Cause | Fix Type |
|---|----------|--------------|------------|----------|
| 1 | `data_to_xlsx` | 3 terminal steps all use `run_command` | **Genuinely terminal-owned** | ✅ Already correct |
| 2 | `meeting_to_report` | render_docx, verify_docx | Misclassified as terminal | Fix YAML capability |
| 3 | `multiformat_report` | 4 terminal steps | Misclassified + 1 missing | Fix YAML + implement verify_bundle |
| 4 | `research_to_docx` | render_docx, verify_docx | Misclassified as terminal | Fix YAML capability |
| 5 | `research_to_pdf` | render_pdf_from_html, verify_pdf | Misclassified as terminal | Fix YAML capability |
| 6 | `research_to_pptx` | render_pptx, verify_pptx | Misclassified as terminal | Fix YAML capability |
| 7 | `issue_to_implementation` | delegate_to_agent | Misclassified + missing impl | Fix YAML + implement delegate_to_agent |
| 8 | `repo_health_report` | render_docx, verify_docx | Misclassified as terminal | Fix YAML capability |
| 9 | `scaffold_project` | scaffold, git_init, open_vscode | Misclassified as terminal | Fix YAML capability |
| 10 | `duplicate_detector` | render_markdown | Misclassified as terminal | Fix YAML capability |
| 11 | `invoice_extract_to_sheet` | append_xlsx_row, run_command | run_command OK, append misclassified + missing | Fix YAML + implement append_xlsx_row |
| 12 | `weekly_review` | render_docx | Misclassified as terminal | Fix YAML capability |
| 13 | `competitor_monitor` | render_docx | Misclassified as terminal | Fix YAML capability |
| 14 | `web_scrape_to_report` | render_docx, verify_docx | Misclassified as terminal | Fix YAML capability |

### Classification Summary

| Category | Count | Action |
|----------|-------|--------|
| ✅ Already correct | 1 template (3 steps) | data_to_xlsx uses run_command |
| 🔧 YAML misclassification | 10 templates (25 steps) | Change `terminal` → `artifact`/`document`/`filesystem` in YAML |
| 🆕 Missing implementation | 3 templates (4 steps) | verify_bundle, delegate_to_agent, append_xlsx_row |
| 🔧 YAML + missing impl | 1 template (1 step) | render_markdown → filesystem::write_file |

---

## 5. Terminal Implementation Decision

### Decision: **D — ROUTING ONLY (no new terminal code)**

**Rationale:**

1. **Terminal is a subprocess gate, not a document factory.** TerminalProvider's job is `run_command` (subprocess execution) and clipboard operations. It should not grow into `render_docx`, `verify_pptx`, or `scaffold` — those are domain-specific artifact operations with their own rich implementations.

2. **The implementations already exist.** `artifact_operator.py` (2254 LOC) and `document_operator.py` (362 LOC) have production-quality implementations for every misclassified action. No new code is needed for 12 of 15 actions.

3. **The YAML templates are wrong.** The fix is to change the `capability` field in the YAML templates from `terminal` to the correct capability (`artifact`, `document`, `filesystem`). This is a YAML-only change for most templates.

4. **The execution pipeline is already wired.** `step_runner.py` already has `("artifact", "generate_docx"): "execute_capability"` etc. in `_ACTION_MAP`. The problem is that the YAML templates bypass this by using `terminal` instead.

### What Terminal Does NOT Need

| Do NOT add to TerminalProvider | Why |
|-------------------------------|-----|
| render_docx | `artifact_operator.build_docx()` already exists |
| verify_docx | `document_operator.verify_docx()` already exists |
| render_pdf_from_html | `artifact_operator._docx_to_pdf()` already exists |
| verify_pdf | `artifact_operator.verify_pdf()` already exists |
| render_pptx | `artifact_operator.build_pptx()` already exists |
| verify_pptx | `artifact_operator.verify_pptx()` already exists |
| scaffold | `artifact_operator.create_code_project()` already exists |
| open_vscode | `artifact_operator.open_in_editor()` already exists |

### What DOES Need Implementation (3 actions)

| Action | Owner | Effort | Notes |
|--------|-------|--------|-------|
| `verify_bundle` | artifact_operator | ~20 LOC | Compose verify_docx + verify_pdf + verify_pptx |
| `delegate_to_agent` | NEW provider or terminal extension | ~80-150 LOC | Subprocess wrapper for aider/openhands/claude_code |
| `append_xlsx_row` | artifact_operator or filesystem | ~25 LOC | openpyxl already installed |

### What the YAML Fix Looks Like

For `research_to_docx.yaml`:
```yaml
# BEFORE (broken):
  - id: render
    capability: terminal
    action: render_docx

# AFTER (correct):
  - id: render
    capability: artifact
    action: generate_docx
```

For `scaffold_project.yaml`:
```yaml
# BEFORE (broken):
  - id: scaffold
    capability: terminal
    action: scaffold

# AFTER (correct):
  - id: scaffold
    capability: artifact
    action: create_code_project
```

---

## 6. Summary

| Metric | Value |
|--------|-------|
| Templates audited | 14 |
| Terminal actions enumerated | 15 |
| Genuinely terminal-owned | 1 (run_command) |
| Misclassified as terminal | 12 |
| Missing implementation | 3 |
| New terminal code needed | **0 LOC** |
| YAML templates to fix | 11 of 14 |
| New functions to write | 3 (verify_bundle, delegate_to_agent, append_xlsx_row) |

**The terminal problem is a YAML classification problem, not an implementation gap.**
