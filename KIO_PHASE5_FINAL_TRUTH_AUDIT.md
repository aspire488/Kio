# KIO Phase 5 Final Truth Audit

**Date:** 2026-09-16
**Auditor:** Independent verification agent
**Scope:** All Phase 5 claims — template classification, handler implementation, resource controls, security boundaries
**Method:** Source-code inspection, runtime import verification, template-by-template capability audit, regression testing

---

## 1. EXECUTIVE SUMMARY

**Closure Recommendation: REQUIRES REPAIR**

Phase 5 implemented real handlers for 6 capability classes (artifact, github, media, communication, memory, mcp_tool) and added a resource admission gate. The handlers themselves are correctly wired and functionally sound for the actions they register. However, the **template classification claim is fundamentally wrong**: the implementation doc asserts FULL=53, PARTIAL=10, BLOCKED=0, but independent audit shows **FULL=13, PARTIAL=0, BLOCKED=50**. 50 of 63 templates (79%) reference capabilities or actions that have no handler in `APP_CAPABILITIES` and will fail at runtime.

The gap is caused by templates using `filesystem` (24 actions), `knowledge` (10 actions), `calendar` (4 actions), and numerous unregistered actions within `github`, `communication`, `memory`, `media`, and `terminal` — none of which have handlers in `execute_capability`.

---

## 2. WHAT PHASE 5 CLAIMED vs WHAT IS TRUE

| Claim (from KIO_PHASE5_HEAVY_RESOURCE_IMPLEMENTATION.md) | Actual Truth | Evidence |
|---|---|---|
| FULL=53, PARTIAL=10, BLOCKED=0 | FULL=13, PARTIAL=0, BLOCKED=50 | Per-template audit below |
| Artifact handlers: "all 5 wired" | TRUE | `build_docx`, `build_pptx`, `verify_docx`, `verify_pptx`, `verify_pdf` all exist and are importable |
| GitHub handler: "8 actions routed" | TRUE for 8 actions, but 11 additional github actions in templates are unregistered | `_ACTION_MAP` maps 11 more github actions to execute_capability, but execute_capability doesn't handle them |
| Media handler: "publish/verify_posts with honest refusal" | PARTIALLY TRUE — refusal works, but provider.publish() will crash | YouTubeProvider and SpotifyProvider have no `publish` method |
| Communication: "4 actions via message_answer" | TRUE for 4, but 11 additional communication actions in templates are unregistered | `_ACTION_MAP` maps 11 more communication actions, but execute_capability doesn't handle them |
| Memory: "5 actions via JSON store" | TRUE for 5, but 9 additional memory actions in templates are unregistered | `_ACTION_MAP` maps 9 more memory actions, but execute_capability doesn't handle them |
| MCP tool: "11 actions routed" | TRUE | `execute_mcp_tool` exists and is importable |
| Resource gate at 580MB | TRUE | Code at app_operator.py:3231-3248 |

---

## 3. PER-TEMPLATE INDEPENDENT CLASSIFICATION

### 3.1 Summary

| Classification | Count | Percentage |
|---|---|---|
| FULL | 13 | 20.6% |
| PARTIAL | 0 | 0.0% |
| BLOCKED | 50 | 79.4% |
| **Total** | **63** | **100%** |

### 3.2 FULL Templates (13) — All steps use registered capabilities

| File | Steps | Capabilities Used |
|---|---|---|
| `ai/classify_and_route.yaml` | 2 | ai_reasoning::classify, workflow::route |
| `ai/extract_to_structured.yaml` | 2 | ai_reasoning::extract_structured, workflow::verify_shape |
| `artifacts/data_to_xlsx.yaml` | 4 | ai_reasoning::design_spreadsheet, artifact::generate_docx, artifact::generate_pptx, artifact::verify_xlsx |
| `artifacts/meeting_to_report.yaml` | 3 | ai_reasoning::extract_meeting_structure, ai_reasoning::summarize, artifact::generate_docx |
| `artifacts/research_to_docx.yaml` | 6 | ai_reasoning::research, ai_reasoning::extract_structured, ai_reasoning::compose_html, artifact::generate_docx, artifact::verify_docx, workflow::verify_shape |
| `artifacts/research_to_pptx.yaml` | 4 | ai_reasoning::research, ai_reasoning::plan_slides, artifact::generate_pptx, artifact::verify_pptx |
| `business/email_autoresponder_approval.yaml` | 3 | ai_reasoning::classify_response, communication::draft_message, workflow::request_approval |
| `business/support_ticket_triage.yaml` | 3 | ai_reasoning::triage_ticket, workflow::route, communication::send_message |
| `data/json_transform.yaml` | 2 | ai_reasoning::extract_structured, workflow::transform_records |
| `data/knowledge_base_sync.yaml` | 3 | ai_reasoning::extract_structured, workflow::transform_records, mcp_tool::upsert |
| `files/invoice_extract_to_sheet.yaml` | 4 | ai_reasoning::extract_structured, ai_reasoning::detect_pii, artifact::generate_docx, artifact::append_xlsx_row |
| `media/content_repurpose.yaml` | 4 | ai_reasoning::adapt_per_platform, ai_reasoning::summarize, ai_reasoning::write_content, ai_reasoning::classify |
| `productivity/email_to_task.yaml` | 2 | ai_reasoning::classify_actionable, workflow::route |

### 3.3 BLOCKED Templates (50) — Reference unregistered capabilities or actions

Each blocked template has at least one step using a capability or action not in `APP_CAPABILITIES`. Full list with blocking原因:

| File | Blocked Steps | Reason |
|---|---|---|
| `ai/enrich_records.yaml` | 2 | `knowledge::batch_lookup`, `filesystem::write` |
| `ai/image_generate.yaml` | 2 | `media::generate_image`, `filesystem::verify_image` |
| `ai/rag_answer.yaml` | 1 | `knowledge::vector_search` |
| `ai/transcribe_summarize.yaml` | 1 | `filesystem::store_transcript` |
| `artifacts/multiformat_report.yaml` | 2 | `terminal::render_pdf_from_html`, `terminal::verify_bundle` |
| `artifacts/research_to_pdf.yaml` | 1 | `terminal::render_pdf_from_html` |
| `browser/page_change_monitor.yaml` | 1 | `browser::fetch_region` |
| `browser/price_monitor.yaml` | 1 | `browser::extract_price` |
| `browser/structured_extract.yaml` | 3 | `browser::extract_records`, `filesystem::write_csv`, `filesystem::verify_csv` |
| `business/crm_followup.yaml` | 2 | `memory::exclude_recently_contacted`, `communication::send_batch` |
| `business/lead_intake_crm.yaml` | 1 | `knowledge::validate_lead` |
| `communication/chat_assistant.yaml` | 3 | `communication::debounce_messages`, `memory::load_conversation`, `memory::save_turn` |
| `communication/escalation_alert.yaml` | 1 | `communication::send_with_ack` |
| `communication/notify.yaml` | 1 | `communication::format_for_channel` |
| `communication/voice_assistant.yaml` | 1 | `media::text_to_speech` |
| `communication/workflow_failure_alert.yaml` | 1 | `communication::format_failure` |
| `data/api_poll_to_store.yaml` | 3 | `knowledge::paginated_get`, `memory::filter_new`, `filesystem::append_records` |
| `data/csv_pii_scrub.yaml` | 1 | `filesystem::redact_csv` |
| `data/file_extract_to_csv.yaml` | 2 | `filesystem::append_csv`, `filesystem::verify_csv` |
| `data/form_intake.yaml` | 2 | `filesystem::append_sheet_row`, `filesystem::verify_sheet_row` |
| `data/record_sync.yaml` | 1 | `memory::apply_field_map` |
| `data/webhook_to_store.yaml` | 3 | `knowledge::verify_hmac`, `filesystem::store_record`, `filesystem::verify_record` |
| `development/ci_failure_alert.yaml` | 1 | `github::get_run_logs` |
| `development/dependency_monitor.yaml` | 1 | `github::dependency_scan` |
| `development/github_issue_triage.yaml` | 2 | `github::get_issue`, `github::apply_labels` |
| `development/issue_to_implementation.yaml` | 3 | `github::gather_issue_context`, `terminal::delegate_to_agent`, `github::create_draft_pr` |
| `development/pr_review_prep.yaml` | 1 | `github::get_pr_diff` |
| `development/release_changelog.yaml` | 2 | `github::prs_since_last_tag`, `github::create_release` |
| `development/repo_backup.yaml` | 4 | `github::export_archive`, `filesystem::upload_backup`, `filesystem::verify_upload`, `filesystem::prune_old_backups` |
| `development/repo_health_report.yaml` | 2 | `github::repo_metrics`, `communication::send_file` |
| `development/scaffold_project.yaml` | 4 | `terminal::scaffold`, `terminal::git_init`, `terminal::open_vscode`, `filesystem::verify_project` |
| `files/document_summarize.yaml` | 1 | `filesystem::extract_text` |
| `files/download_folder_organizer.yaml` | 3 | `filesystem::classify_file`, `filesystem::move_file`, `filesystem::verify_path` |
| `files/drive_to_social.yaml` | 4 | `filesystem::get_new_asset`, `media::transcode_variants`, `filesystem::write_derivatives`, `filesystem::verify_paths` |
| `files/duplicate_detector.yaml` | 3 | `filesystem::hash_tree`, `filesystem::group_duplicates`, `terminal::render_markdown` |
| `monitoring/inbox_monitor.yaml` | 1 | `communication::get_updates` |
| `monitoring/rss_news_monitor.yaml` | 2 | `knowledge::read_feeds`, `memory::filter_new` |
| `monitoring/security_scan_alert.yaml` | 1 | `knowledge::multi_scan` |
| `monitoring/website_uptime.yaml` | 2 | `knowledge::healthcheck`, `memory::state_transition` |
| `productivity/calendar_to_status.yaml` | 2 | `communication::set_status`, `communication::clear_status` |
| `productivity/ecosystem_briefing.yaml` | 3 | `calendar::today_events`, `communication::priority_unread`, `filesystem::recent_drive_changes` |
| `productivity/email_label_ai.yaml` | 1 | `communication::apply_label` |
| `productivity/email_to_calendar.yaml` | 2 | `calendar::run_command`, `calendar::get_event` |
| `productivity/meeting_prep.yaml` | 2 | `calendar::upcoming_within`, `memory::gather_context` |
| `productivity/morning_briefing.yaml` | 2 | `calendar::today_events`, `knowledge::get_weather` |
| `productivity/weekly_review.yaml` | 2 | `memory::week_activity`, `communication::send_file` |
| `research/competitor_monitor.yaml` | 3 | `browser::snapshot_sources`, `memory::diff_snapshots`, `communication::send_file` |
| `research/daily_brief.yaml` | 1 | `memory::filter_new` |
| `research/web_scrape_to_report.yaml` | 1 | `browser::crawl_extract` |
| `research/youtube_summary.yaml` | 2 | `knowledge::list_new_videos`, `memory::filter_new` |

---

## 4. CAPABILITY-BY-CAPABILITY TRUTH

### 4.1 Artifact (FULL)

**Registered actions:** `generate_docx`, `generate_pptx`, `verify_docx`, `verify_pptx`, `verify_pdf`, `append_xlsx_row`

| Handler | Function | Import Path | Verified |
|---|---|---|---|
| `generate_docx` | `build_docx()` | `mini_kio.core.artifact_operator` | Yes — live round-trip passed (36KB docx) |
| `generate_pptx` | `build_pptx()` | `mini_kio.core.artifact_operator` | Yes — importable |
| `verify_docx` | `verify_docx()` | `mini_kio.core.document_operator` | Yes — live round-trip passed |
| `verify_pptx` | `verify_pptx()` | `mini_kio.core.artifact_operator` | Yes — importable |
| `verify_pdf` | `verify_pdf()` | `mini_kio.core.artifact_operator` | Yes — importable |
| `append_xlsx_row` | `append_xlsx_row()` | `mini_kio.core.artifact_operator` | Yes — tested |

**Dependencies:** python-docx, openpyxl, python-pptx — all installed.

**Verdict: GENUINELY FULL**

### 4.2 GitHub (PARTIAL — 8 of 19 registered)

**Registered actions:** `search_repositories`, `get_repository`, `list_issues`, `create_issue`, `list_prs`, `get_contents`, `list_branches`, `list_commits`

| Handler | Function | Verified |
|---|---|---|
| `search_repositories` | `github_search_repos()` | Yes — importable |
| `get_repository` | `github_get_repo()` | Yes — importable |
| `list_issues` | `github_list_issues()` | Yes — importable |
| `create_issue` | `github_create_issue()` | Yes — importable |
| `list_prs` | `github_list_prs()` | Yes — importable |
| `get_contents` | `github_get_contents()` | Yes — importable |
| `list_branches` | `github_list_branches()` | Yes — importable |
| `list_commits` | `github_list_commits()` | Yes — importable |

**Unregistered actions used by templates:** `get_run_logs`, `dependency_scan`, `apply_labels`, `get_issue`, `gather_issue_context`, `create_draft_pr`, `get_pr_diff`, `prs_since_last_tag`, `create_release`, `export_archive`, `repo_metrics` (11 actions)

**Dependencies:** PyGithub installed. **GITHUB_TOKEN NOT SET** — all 8 registered actions will return auth errors without it.

**Verdict: PARTIAL** — 8/19 actions work (with GITHUB_TOKEN); 11/19 actions have no handler

### 4.3 Media (BROKEN)

**Registered actions:** `publish`, `verify_posts`

**CRITICAL BUG:** The handler at app_operator.py:3739 calls `provider.publish(inputs)` and at line 3761 calls `provider.verify_posts(inputs)`. However:
- `YouTubeProvider` has methods: `play`, `search`, `pause`, `next_track`, `previous_track`, `recommend`, `resume`, `seek`, `stop`, `volume` — **no `publish` method**
- `SpotifyProvider` has methods: `play`, `search`, `pause`, `next_track`, `previous_track`, `recommend`, `resume`, `seek`, `stop`, `volume` — **no `publish` method**

Without configured adapters, the handler returns honest refusal (correct). With configured adapters, it will crash with `AttributeError: 'YouTubeProvider' object has no attribute 'publish'`.

**Unregistered actions used by templates:** `generate_image`, `text_to_speech`, `transcode_variants` (3 actions)

**Verdict: PARTIAL for refusal path, BROKEN for real publish** — The providers are media-control (play/pause/search), not content publishers

### 4.4 Communication (PARTIAL — 4 of 15 registered)

**Registered actions:** `send_message`, `send_notification`, `send_update`, `draft_message`

| Handler | Verified |
|---|---|
| `send_message` | Yes — routes through `message_answer` from `mini_kio.communication.messages` |
| `send_notification` | Yes — same routing |
| `send_update` | Yes — same routing |
| `draft_message` | Yes — returns draft without side effects |

**Unregistered actions used by templates:** `send_batch`, `send_with_ack`, `send_file`, `format_for_channel`, `format_failure`, `apply_label`, `clear_status`, `set_status`, `debounce_messages`, `get_updates`, `priority_unread` (11 actions)

**Verdict: PARTIAL** — 4/15 actions work; 11/15 actions have no handler

### 4.5 Memory (PARTIAL — 5 of 14 registered)

**Registered actions:** `store`, `retrieve`, `snapshot`, `diff_against_last`, `record_and_compare`

All implemented as inline JSON-file store at `~/.kio/memory/`. Verified working.

**Unregistered actions used by templates:** `filter_new`, `log_event`, `apply_field_map`, `diff_snapshots`, `exclude_recently_contacted`, `gather_context`, `load_conversation`, `save_turn`, `state_transition`, `week_activity` (9 actions, noting some overlap with registered)

Actually corrected: `filter_new`, `log_event`, `apply_field_map`, `diff_snapshots`, `exclude_recently_contacted`, `gather_context`, `load_conversation`, `save_turn`, `state_transition`, `week_activity` — 10 unregistered actions.

Wait, the registered ones are `store`, `retrieve`, `snapshot`, `diff_against_last`, `record_and_compare`. The unregistered ones from templates are: `apply_field_map`, `diff_snapshots`, `exclude_recently_contacted`, `filter_new`, `gather_context`, `load_conversation`, `save_turn`, `state_transition`, `week_activity`. That's 9 unregistered.

**Verdict: PARTIAL** — 5/14 actions work; 9/14 actions have no handler

### 4.6 MCP Tool (FULL)

**Registered actions:** 11 actions routed to `execute_mcp_tool`

Handler at app_operator.py:4025-4050 routes to `mini_kio.core.execution_boundary.execute_mcp_tool`. The function exists and has correct signature.

**Verdict: FULL** — all 11 registered actions route correctly. Downstream server availability depends on configuration.

### 4.7 Browser (NOT IN APP_CAPABILITIES)

**CRITICAL FINDING:** `browser` is NOT in `APP_CAPABILITIES`. Browser actions route through `_ACTION_MAP` directly to browser functions (goto, click, etc.) in `step_runner.py`, bypassing `execute_capability` entirely for registered actions.

However, templates reference 5 browser actions (`crawl_extract`, `extract_price`, `extract_records`, `fetch_region`, `snapshot_sources`) that are NOT in the direct browser function mapping. These route to `execute_capability` which has no browser handler — returning "Capability browser not implemented."

**Verdict: PARTIAL for direct browser actions (bypass execute_capability), BLOCKED for extract/crawl actions**

### 4.8 Filesystem (NOT IN APP_CAPABILITIES)

**NOT registered.** 24 actions used by templates. No handler exists. All filesystem templates are BLOCKED.

Templates use: `write`, `write_csv`, `append_csv`, `append_records`, `append_sheet_row`, `classify_file`, `extract_text`, `get_new_asset`, `group_duplicates`, `hash_tree`, `move_file`, `prune_old_backups`, `recent_drive_changes`, `redact_csv`, `store_record`, `store_transcript`, `upload_backup`, `verify_csv`, `verify_image`, `verify_path`, `verify_paths`, `verify_project`, `verify_record`, `verify_sheet_row`, `verify_upload`, `write_derivatives`

**Verdict: BLOCKED** — no capability registered, no handler exists

### 4.9 Knowledge (NOT IN APP_CAPABILITIES)

**NOT registered.** 10 actions used by templates. No handler exists.

Templates use: `batch_lookup`, `get_weather`, `healthcheck`, `list_new_videos`, `multi_scan`, `paginated_get`, `read_feeds`, `validate_lead`, `vector_search`, `verify_hmac`

**Verdict: BLOCKED** — no capability registered, no handler exists

### 4.10 Calendar (NOT IN APP_CAPABILITIES)

**NOT registered.** 4 actions used by templates. No handler exists.

Templates use: `get_event`, `run_command`, `today_events`, `upcoming_within`

**Verdict: BLOCKED** — no capability registered, no handler exists

### 4.11 Terminal (PARTIAL — 3 of 10 registered)

**Registered actions:** `run_command`, `clipboard_copy`, `clipboard_paste`

Routed through `TerminalProvider.execute()`.

**Unregistered actions used by templates:** `render_pdf_from_html`, `verify_bundle`, `delegate_to_agent`, `git_init`, `open_vscode`, `scaffold`, `render_markdown` (7 actions)

**Verdict: PARTIAL** — 3/10 actions work; 7/10 actions have no handler

---

## 5. RESOURCE ADMISSION CONTROLS

### 5.1 Implementation

**Location:** `app_operator.py:3231-3248`

```python
_HEAVY_APPS = frozenset({"github", "media", "mcp_tool"})
_BROWSER_ACTIONS = frozenset({"goto", "click", "hover", "scroll", "drag", "select",
                               "fill", "type", "keypress", "evaluate", "screenshot", "pdf"})
if app_name in _HEAVY_APPS or (app_name in ("browser",) and cap in _BROWSER_ACTIONS):
    _ram_mb = psutil.Process(os.getpid()).memory_info().rss / 1024 / 1024
    if _ram_mb > 580:
        return {"success": False, "message": f"Resource limit reached ({_ram_mb:.0f}MB used)..."}
```

### 5.2 Findings

| Aspect | Claim | Truth |
|---|---|---|
| Threshold | 580MB | Correct — code uses 580 |
| Heavy apps | github, media, mcp_tool | Correct |
| Browser actions | goto, click, etc. | Correct |
| Measurement | Per-process RSS | Correct — uses `psutil.Process(os.getpid()).memory_info().rss` |
| Recovery | "Retry after freeing memory" | Correct — returns error with retry suggestion |
| ResourceGuard | Not mentioned | Exists separately at runtime.py:131 (SOFT=350MB, HARD=400MB) |

**Discrepancy:** ResourceGuard uses 350/400MB thresholds. The new admission gate uses 580MB. These are independent checks — ResourceGuard may block before the admission gate triggers.

**Verdict: FUNCTIONALLY CORRECT** but threshold inconsistency with ResourceGuard should be documented.

---

## 6. SECURITY BOUNDARY AUDIT

### 6.1 Core Brain / ExecutionBoundary

**Finding:** All new handlers are routed through `execute_capability` which is called by `step_runner.py`. The `execute_capability` function checks `APP_CAPABILITIES` before dispatching. Unregistered capabilities return "not implemented" — **no bypass possible**.

### 6.2 Path Traversal

**Verified in:**
- `artifact_operator.py:703-705` — blocks path traversal in xlsx operations
- `file_operator.py:218-225` — blocks path traversal in file operations

New handlers (memory store, GitHub, media) do not introduce new path traversal surfaces — memory uses fixed `~/.kio/memory/` directory, GitHub uses API calls, media routes to providers.

### 6.3 Credential Handling

**GitHub:** Uses `PyGithub` with `GITHUB_TOKEN` env var. Token not set in audit environment — all GitHub API calls will fail with auth errors. No credentials logged or exposed.

**Media:** Provider adapters configured externally. No credentials in code.

**MCP Tool:** Routes through `execute_mcp_tool` which delegates to `MCPRuntime`. No new credential surfaces.

### 6.4 Terminal Safety

Terminal handler routes through `TerminalProvider` which has whitelist/blocklist safety checks. No `shell=True` usage.

### 6.5 Verdict: NO SECURITY REGRESSIONS

The new handlers do not bypass existing security boundaries. All routing goes through established gates.

---

## 7. REGRESSION TEST RESULTS

```
105 passed, 2 warnings in 27.32s
```

- `test_automation_engine.py` — all pass
- `test_automation_integration.py` — all pass
- `test_append_xlsx_row.py` — all pass
- `test_ai_reasoning_routing.py` — all pass

**No regressions detected.**

---

## 8. DISCREPANCY ANALYSIS

### 8.1 Root Cause of Template Classification Error

The Phase 5 implementation doc classified templates based on **what capabilities the YAML references** vs **what the step_runner _ACTION_MAP routes to execute_capability**. This created a false impression because:

1. `_ACTION_MAP` maps many capability/action pairs to `execute_capability`
2. But `execute_capability` only handles capabilities registered in `APP_CAPABILITIES`
3. Unregistered capabilities (filesystem, knowledge, calendar) and unregistered actions within registered capabilities all return "not implemented"

The classification should have been based on **what execute_capability actually handles**, not what _ACTION_MAP routes to it.

### 8.2 Scope of the Gap

- **5 unregistered capabilities:** filesystem (24 actions), knowledge (10 actions), calendar (4 actions), browser (5 extract/crawl actions), plus unregistered actions in 5 registered capabilities
- **79% of templates (50/63)** are BLOCKED
- **Only 13 templates (21%)** are genuinely FULL

---

## 9. WHAT WORKS vs WHAT DOESN'T

### 9.1 Genuinely Working (13 templates)

Templates using only: `ai_reasoning` (all actions), `workflow` (all actions), `artifact` (all 6 actions), `communication` (4 registered actions), `memory` (5 registered actions), `mcp_tool` (all 11 actions), `terminal` (3 registered actions), `github` (8 registered actions with GITHUB_TOKEN)

### 9.2 Broken by Missing Capabilities

| Missing Capability | Actions | Templates Affected |
|---|---|---|
| filesystem | 24 | 17 templates |
| knowledge | 10 | 9 templates |
| calendar | 4 | 4 templates |
| browser (extract/crawl) | 5 | 5 templates |
| github (unregistered actions) | 11 | 7 templates |
| communication (unregistered actions) | 11 | 8 templates |
| memory (unregistered actions) | 9 | 8 templates |
| media (unregistered actions) | 3 | 3 templates |
| terminal (unregistered actions) | 7 | 4 templates |

### 9.3 Broken by Missing Dependencies

| Dependency | Impact |
|---|---|
| GITHUB_TOKEN not set | All 8 registered GitHub actions fail with auth errors |
| YouTubeProvider.publish() doesn't exist | Media publish will crash if provider is configured |
| SpotifyProvider.publish() doesn't exist | Media publish will crash if provider is configured |

---

## 10. CLOSURE RECOMMENDATION

### REQUIRES REPAIR

**Rationale:** The Phase 5 implementation added real, working handlers for 6 capability classes. The handlers themselves are correctly implemented and do not regress existing functionality (105 tests pass). However:

1. **Template classification is wrong** — 79% of templates are BLOCKED, not 0% as claimed
2. **Media publish is broken** — providers don't have `publish` method
3. **GitHub requires GITHUB_TOKEN** — not set in environment
4. **3 entire capability classes are missing** — filesystem, knowledge, calendar (38 actions total)
5. **50+ actions within registered capabilities are missing** — github (11), communication (11), memory (9), terminal (7), media (3)

**What would make this PASS:**
- Fix media provider publish methods OR change classification to BLOCKED
- Register filesystem, knowledge, calendar capabilities OR remove template references
- Register missing actions within github, communication, memory, terminal OR remove template references
- Set GITHUB_TOKEN OR document as prerequisite
- Correct the template classification numbers

---

## 11. PHASE 6 ENTRY GATE ASSESSMENT

| Gate Criterion | Status |
|---|---|
| All heavy capability classes routed | PARTIAL — media broken, filesystem/knowledge/calendar missing |
| Resource controls enforced | YES — 580MB gate functional |
| Template classification correct | NO — off by 37 templates |
| No security regressions | YES |
| No test regressions | YES — 105/105 pass |

**Phase 6 CANNOT begin until template classification is corrected and missing capabilities are addressed.**

---

*End of Phase 5 Final Truth Audit*
