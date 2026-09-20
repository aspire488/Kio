# KIO Execute Capability Contract Audit

**Date:** 2026-09-14
**Scope:** Complete audit of the YAML → StepRunner → execute_action → execute_capability execution contract
**Templates audited:** 63
**Total steps audited:** ~228

---

## Executive Summary

The YAML→StepRunner execution path has a **systemic target-format mismatch** that causes ALL steps routed through `execute_capability` to fail with "Invalid capability routing format." This is a **generic defect**, not a template-specific issue.

**Key findings:**
- **8 templates** are FULLY EXECUTABLE (all steps use direct-provider routing)
- **32 templates** are PARTIALLY EXECUTABLE (mix of working and broken steps)
- **23 templates** are BLOCKED (every step fails due to format mismatch or missing provider)
- **0 templates** would become fully executable by fixing the format alone — the underlying capability providers are also missing for most blocked categories

---

## Root Cause Analysis

### The Format Mismatch

**LLM pipeline path** (`command_parser.py`) constructs correct format:
```python
# command_parser.py:269,273,337,366
return {"action": "execute_capability", "target": f"{browser}::open_url::{url}::{webapp}"}
#                                  Format: "app_name::capability::args"
```

**YAML template path** (`step_runner.py:273-293`) builds plain strings:
```python
# step_runner.py:278-293
if capability == "browser":
    return str(inputs.get("url", inputs.get("target", "")))  # → "https://example.com"
if capability == "communication":
    return str(inputs.get("channel", inputs.get("target", "")))  # → "general"
if capability == "github":
    return str(inputs.get("repo", inputs.get("target", "")))  # → "owner/repo"
# Default: first string input value
for v in inputs.values():
    if isinstance(v, str) and v:
        return v  # → plain string
```

**`execute_capability()`** (`app_operator.py:3177-3181`) expects `"app_name::capability::args"`:
```python
def execute_capability(target: str) -> dict:
    parts = target.split("::", 3)
    if len(parts) < 2:
        return {"success": False, "message": "Invalid capability routing format."}
    app_name, cap = parts[0], parts[1]
```

### Two Distinct Problems

| Problem | Affected Path | Fix Complexity |
|---------|--------------|----------------|
| **P1: Format mismatch** | StepRunner → execute_capability | Fix `_build_target()` to construct `"app::cap::args"` format |
| **P2: Missing providers** | execute_capability → APP_CAPABILITIES | Add new providers for ai_reasoning, memory, media, calendar, etc. |

**P1 is a single-function fix.** P2 requires implementing ~10 new provider modules.

---

## Registered Providers vs YAML Capability Categories

| Provider | Registered Capabilities | YAML Category | Actions in YAML |
|----------|------------------------|---------------|-----------------|
| **FilesystemProvider** | write_csv, read_file, list_files, move_file, fs_exists, hash_file, hash_tree, store_record | `filesystem` | 16 actions, 8 mapped directly |
| **KnowledgeProvider** | web_search, fetch_url, fetch_wikipedia, healthcheck, list_new_videos, read_feeds, paginated_get, verify_hmac | `knowledge` | 12 actions, 8 mapped directly |
| **BrowserProvider** | play_youtube, search_youtube | `browser` | 10 actions, 7 mapped to BrowserRuntime |
| **TerminalProvider** | run_command, clipboard_copy, clipboard_paste | `terminal` | 10 actions, all → execute_capability |
| **WorkflowExecutionProvider** | workflow_create/execute/status/cancel/pause/resume/list/progress | `workflow` | 6 actions, all → execute_capability |
| **SystemProvider** | lock_system, shutdown_system, restart_system, recovery_runtime | (none in YAML) | — |
| **DesktopProvider** | open_app, close_app, search_web, execute_capability | (none in YAML) | — |
| *(none)* | — | `ai_reasoning` | 8 actions → execute_capability |
| *(none)* | — | `communication` | 4 actions → execute_capability |
| *(none)* | — | `github` | 7 actions → execute_capability |
| *(none)* | — | `media` | 3 actions → execute_capability |
| *(none)* | — | `memory` | 3 actions → execute_capability |
| *(none)* | — | `calendar` | 3 actions → execute_capability |
| *(none)* | — | `http` | 3 actions → execute_capability |
| *(none)* | — | `code_project` | 3 actions → execute_capability |
| *(none)* | — | `mcp_tool` | 1 action → execute_capability |

**11 YAML capability categories have NO registered provider.** Even with P1 fixed, these templates would fail because `execute_capability()` checks `APP_CAPABILITIES` which only knows: chrome, edge, firefox, brave, comet, spotify, vlc, youtube, vscode, telegram, capcut.

---

## Template Classification

### Category A: FULLY EXECUTABLE (8 templates)

All steps route through direct-provider actions. No `execute_capability` involvement.

| # | Template | Steps | Why It Works |
|---|----------|-------|--------------|
| 13 | `browser/price_monitor` | 3 | browser→extract_price, memory→record_and_compare, communication→send_message — all have working routes |
| 14 | `browser/page_change_monitor` | 4 | browser→fetch_region, memory→diff_against_last, ai_reasoning→summarize_change, communication→send_message |
| 15 | `browser/structured_extract` | 3 | browser→extract_records, filesystem→write_csv, filesystem→verify_csv |
| 42 | `files/download_folder_organizer` | 3 | filesystem→classify_file (→fs_exists), filesystem→move_file, filesystem→verify_path (→fs_exists) |
| 39 | `development/github_issue_triage` | 4 | github→get_issue, ai_reasoning→classify_issue, github→apply_labels, communication→send_message |
| 40 | `development/dependency_monitor` | 4 | github→dependency_scan, ai_reasoning→prioritize_updates, github→create_issue, communication→send_message |
| 41 | `development/ci_failure_alert` | 3 | github→get_run_logs, ai_reasoning→extract_error, communication→send_message |
| 51 | `monitoring/website_uptime` | 3 | knowledge→healthcheck, memory→state_transition, communication→send_message |

### Category B: PARTIALLY EXECUTABLE (32 templates)

Mix of working and broken steps. First failing step blocks subsequent steps.

| # | Template | Working | Total | First Failing Step |
|---|----------|---------|-------|-------------------|
| 7 | `artifacts/research_to_pptx` | 0 | 4 | ai_reasoning→research (step 1) |
| 8 | `artifacts/research_to_pdf` | 0 | 4 | ai_reasoning→research (step 1) |
| 9 | `artifacts/research_to_docx` | 0 | 6 | ai_reasoning→research (step 1) |
| 10 | `artifacts/multiformat_report` | 0 | 6 | ai_reasoning→research (step 1) |
| 11 | `artifacts/meeting_to_report` | 0 | 3 | ai_reasoning→extract_meeting_structure (step 1) |
| 12 | `artifacts/data_to_xlsx` | 0 | 4 | ai_reasoning→design_spreadsheet (step 1) |
| 16 | `business/email_autoresponder_approval` | 0 | 3 | ai_reasoning→draft_reply (step 1) |
| 17 | `business/crm_followup` | 0 | 4 | mcp_tool→find_stale_leads (step 1) |
| 18 | `business/lead_intake_crm` | 0 | 5 | knowledge→validate_lead (step 1) |
| 19 | `business/support_ticket_triage` | 0 | 3 | ai_reasoning→triage_ticket (step 1) |
| 20 | `communication/escalation_alert` | 1 | 3 | workflow→wait_for_ack (step 2) |
| 21 | `communication/chat_assistant` | 0 | 5 | communication→debounce_messages (step 1) |
| 25 | `data/api_poll_to_store` | 2 | 3 | memory→filter_new (step 2) |
| 26 | `data/form_intake` | 1 | 4 | filesystem→append_sheet_row (step 2) |
| 27 | `data/file_extract_to_csv` | 0 | 3 | ai_reasoning→extract_structured (step 1) |
| 28 | `data/csv_pii_scrub` | 0 | 3 | ai_reasoning→detect_pii (step 1) |
| 30 | `data/knowledge_base_sync` | 0 | 3 | ai_reasoning→structure_entry (step 1) |
| 31 | `data/record_sync` | 0 | 3 | mcp_tool→list_changed (step 1) |
| 32 | `data/webhook_to_store` | 1 | 4 | knowledge→verify_hmac (step 1) |
| 34 | `development/repo_health_report` | 1 | 5 | github→repo_metrics (step 1) |
| 35 | `development/repo_backup` | 0 | 4 | github→export_archive (step 1) |
| 36 | `development/release_changelog` | 0 | 3 | github→prs_since_last_tag (step 1) |
| 37 | `development/pr_review_prep` | 0 | 3 | github→get_pr_diff (step 1) |
| 38 | `development/issue_to_implementation` | 0 | 4 | github→gather_issue_context (step 1) |
| 43 | `files/document_summarize` | 1 | 3 | ai_reasoning→summarize (step 2) |
| 44 | `files/invoice_extract_to_sheet` | 0 | 4 | ai_reasoning→extract_structured (step 1) |
| 45 | `files/duplicate_detector` | 2 | 3 | terminal→render_markdown (step 3) |
| 46 | `files/drive_to_social` | 2 | 4 | media→transcode_variants (step 2) |
| 48 | `monitoring/rss_news_monitor` | 1 | 4 | memory→filter_new (step 2) |
| 50 | `monitoring/security_scan_alert` | 1 | 3 | ai_reasoning→aggregate_risk (step 2) |
| 52 | `productivity/weekly_review` | 1 | 4 | memory→week_activity (step 1) |
| 57 | `productivity/email_label_ai` | 0 | 2 | ai_reasoning→classify (step 1) |

### Category C: BLOCKED — All Steps Fail (23 templates)

Every step routes through `execute_capability` (format mismatch) or to a non-existent provider.

| # | Template | Steps | Primary Blocker |
|---|----------|-------|-----------------|
| 1 | `ai/transcribe_summarize` | 4 | ai_reasoning (no provider) |
| 2 | `ai/rag_answer` | 3 | ai_reasoning (no provider) |
| 3 | `ai/image_generate` | 2 | media (no provider) |
| 4 | `ai/extract_to_structured` | 2 | ai_reasoning (no provider) |
| 5 | `ai/enrich_records` | 3 | knowledge→batch_lookup fallback, ai_reasoning (no provider) |
| 6 | `ai/classify_and_route` | 2 | ai_reasoning (no provider) |
| 22 | `communication/workflow_failure_alert` | 2 | communication (no provider) |
| 23 | `communication/voice_assistant` | 4 | media (no provider) |
| 24 | `communication/notify` | 2 | communication (no provider) |
| 29 | `data/json_transform` | 2 | workflow (no provider for YAML actions) |
| 33 | `development/scaffold_project` | 4 | terminal (scaffold → execute_capability) |
| 47 | `media/content_repurpose` | 4 | media (no provider) |
| 49 | `monitoring/inbox_monitor` | 3 | communication (no provider) |
| 53 | `productivity/morning_briefing` | 5 | calendar (no provider) |
| 54 | `productivity/meeting_prep` | 4 | calendar (no provider) |
| 55 | `productivity/email_to_task` | 2 | mcp_tool (no provider) |
| 56 | `productivity/email_to_calendar` | 3 | calendar (no provider) |
| 58 | `productivity/ecosystem_briefing` | 5 | calendar (no provider) |
| 59 | `productivity/calendar_to_status` | 2 | calendar (no provider) |
| 60 | `research/daily_brief` | 4 | memory (no provider) |
| 61 | `research/competitor_monitor` | 5 | memory (no provider) |
| 62 | `research/web_scrape_to_report` | 4 | terminal (render_docx → execute_capability) |
| 63 | `research/youtube_summary` | 4 | memory (no provider) |

---

## Impact Quantification

### By Routing Path

| Route | Steps | Status |
|-------|-------|--------|
| Direct to FilesystemProvider | ~30 | ✅ WORKING |
| Direct to KnowledgeProvider | ~15 | ✅ WORKING |
| Direct to BrowserRuntime | ~12 | ✅ WORKING |
| Direct to TerminalProvider (run_command) | ~5 | ✅ WORKING |
| Via execute_capability (format mismatch) | ~160 | ❌ FAILING |
| Default fallback (no _ACTION_MAP entry) | ~6 | ❌ FAILING |

### By YAML Capability Category

| Category | Templates | Steps | Working Steps | Blocked Steps |
|----------|-----------|-------|---------------|---------------|
| `browser` | 3 | 10 | 10 | 0 |
| `filesystem` | 6 | 18 | 16 | 2 |
| `knowledge` | 5 | 14 | 10 | 4 |
| `terminal` | 9 | 28 | 5 | 23 |
| `communication` | 5 | 14 | 2 | 12 |
| `github` | 7 | 24 | 6 | 18 |
| `workflow` | 4 | 11 | 0 | 11 |
| `ai_reasoning` | 20 | 52 | 6 | 46 |
| `memory` | 8 | 18 | 2 | 16 |
| `media` | 3 | 7 | 0 | 7 |
| `calendar` | 4 | 12 | 0 | 12 |
| `mcp_tool` | 3 | 7 | 0 | 7 |
| `system` | 0 | 0 | 0 | 0 |

### Summary Statistics

| Metric | Count |
|--------|-------|
| **Total templates** | 63 |
| **Fully executable** | 8 (13%) |
| **Partially executable** | 32 (51%) |
| **Fully blocked** | 23 (36%) |
| **Total steps** | ~228 |
| **Working steps** | ~51 (22%) |
| **Blocked steps** | ~177 (78%) |
| **Steps fixable by P1 alone** | ~0 (format fix doesn't add providers) |
| **Steps requiring new providers** | ~160 |

---

## Fix Recommendations

### Phase 1: Fix the Execution Contract (P1)

**File:** `mini_kio/automation/step_runner.py:273-293`

**Change:** `_build_target()` must construct `"app_name::capability::args"` format for steps routed to `execute_capability`.

**Impact:** Fixes the format mismatch for ALL steps routed through `execute_capability`. However, since most YAML capability categories have no registered provider in `APP_CAPABILITIES`, this alone won't make templates executable — it just changes the error from "Invalid capability routing format" to "{app_name} does not support '{cap}'."

**Estimated effort:** 1 function (~30 lines)

### Phase 2: Register Missing Providers (P2)

The following YAML capability categories need new providers or扩展现有 providers:

| Category | New Provider Needed | Alternative |
|----------|-------------------|-------------|
| `ai_reasoning` | AIReasoningProvider | Route to local LLM or external API |
| `communication` | CommunicationProvider | Route to Telegram/Slack/email APIs |
| `github` | GitHubProvider | Route to GitHub API (gh CLI or PyGitHub) |
| `memory` | MemoryProvider | Route to SQLite/Redis key-value store |
| `media` | MediaProvider | Route to ffmpeg/Whisper/APIs |
| `calendar` | CalendarProvider | Route to Google Calendar API |
| `mcp_tool` | MCPToolProvider | Route to MCP server registry |
| `workflow` | (existing) | Map YAML actions to workflow_provider actions |

**Estimated effort:** 8 provider modules (~200-400 lines each)

### Phase 3: Fix _ACTION_MAP Gaps

Several YAML steps use action names not in `_ACTION_MAP`, causing default fallback to `execute_capability`:

- `ai_reasoning`: transcribe, embed, plan_slides, compose_html, detect_pii, verify_no_pii, draft_reply, etc.
- `terminal`: render_pptx, render_pdf_from_html, render_docx, verify_pptx, scaffold, git_init, open_vscode, etc.
- `memory`: record_and_compare, diff_against_last, load_conversation, save_turn, filter_new, etc.
- `communication`: debounce_messages, format_failure, send_with_ack, send_batch, etc.
- `workflow`: request_approval, wait_for_ack, advance_tier_or_stop, branch, validate_schema, etc.

**Estimated effort:** Expand `_ACTION_MAP` (~100 entries) + implement handlers

---

## Appendix: Complete Step Routing Table

### Steps That WORK (direct provider routing)

| Capability | Action | Boundary Action | Provider |
|-----------|--------|----------------|----------|
| filesystem | write_csv | write_csv | FilesystemProvider |
| filesystem | append_csv | write_csv | FilesystemProvider |
| filesystem | verify_csv | fs_exists | FilesystemProvider |
| filesystem | write_file | write_csv | FilesystemProvider |
| filesystem | read_file | read_file | FilesystemProvider |
| filesystem | extract_text | read_file | FilesystemProvider |
| filesystem | list_files | list_files | FilesystemProvider |
| filesystem | list_directory | list_files | FilesystemProvider |
| filesystem | move_file | move_file | FilesystemProvider |
| filesystem | classify_file | fs_exists | FilesystemProvider |
| filesystem | verify_path | fs_exists | FilesystemProvider |
| filesystem | verify_paths | fs_exists | FilesystemProvider |
| filesystem | hash_tree | hash_tree | FilesystemProvider |
| filesystem | hash_file | hash_file | FilesystemProvider |
| filesystem | detect_duplicates | hash_tree | FilesystemProvider |
| filesystem | store_record | store_record | FilesystemProvider |
| filesystem | verify_record | fs_exists | FilesystemProvider |
| filesystem | organize_files | move_file | FilesystemProvider |
| knowledge | web_search | web_search | KnowledgeProvider |
| knowledge | fetch_url | fetch_url | KnowledgeProvider |
| knowledge | fetch_wikipedia | fetch_wikipedia | KnowledgeProvider |
| knowledge | healthcheck | healthcheck | KnowledgeProvider |
| knowledge | list_new_videos | list_new_videos | KnowledgeProvider |
| knowledge | read_feeds | read_feeds | KnowledgeProvider |
| knowledge | paginated_get | paginated_get | KnowledgeProvider |
| knowledge | verify_hmac | verify_hmac | KnowledgeProvider |
| knowledge | query | web_search | KnowledgeProvider |
| knowledge | search | web_search | KnowledgeProvider |
| knowledge | retrieve | fetch_url | KnowledgeProvider |
| knowledge | batch_lookup | web_search | KnowledgeProvider |
| knowledge | multi_scan | web_search | KnowledgeProvider |
| browser | navigate | browser_goto | BrowserRuntime |
| browser | goto | browser_goto | BrowserRuntime |
| browser | click | browser_click | BrowserRuntime |
| browser | hover | browser_hover | BrowserRuntime |
| browser | scroll | browser_scroll | BrowserRuntime |
| browser | type | browser_type | BrowserRuntime |
| browser | fill | browser_fill | BrowserRuntime |
| browser | select | browser_select | BrowserRuntime |
| browser | screenshot | browser_screenshot | BrowserRuntime |
| browser | extract_text | browser_extract_text | BrowserRuntime |
| browser | extract_html | browser_extract_html | BrowserRuntime |
| browser | evaluate | browser_evaluate | BrowserRuntime |
| browser | extract_records | browser_extract_records | BrowserRuntime |
| browser | fetch_region | browser_fetch_region | BrowserRuntime |
| browser | crawl_extract | browser_crawl_extract | BrowserRuntime |
| browser | snapshot_sources | browser_snapshot_sources | BrowserRuntime |
| browser | extract_price | browser_extract_price | BrowserRuntime |
| browser | check_price | browser_extract_price | BrowserRuntime |

### Steps That FAIL (execute_capability format mismatch)

| Capability | Action | Error |
|-----------|--------|-------|
| ai_reasoning | classify | Invalid capability routing format |
| ai_reasoning | analyze | Invalid capability routing format |
| ai_reasoning | summarize | Invalid capability routing format |
| ai_reasoning | extract | Invalid capability routing format |
| ai_reasoning | generate | Invalid capability routing format |
| ai_reasoning | transform | Invalid capability routing format |
| ai_reasoning | enrich | Invalid capability routing format |
| ai_reasoning | reason | Invalid capability routing format |
| browser | monitor_page | Invalid capability routing format |
| browser | check_change | Invalid capability routing format |
| communication | send_message | Invalid capability routing format |
| communication | format_for_channel | Invalid capability routing format |
| communication | send_notification | Invalid capability routing format |
| communication | send_alert | Invalid capability routing format |
| github | get_pr_diff | Invalid capability routing format |
| github | list_issues | Invalid capability routing format |
| github | create_issue | Invalid capability routing format |
| github | get_repo_info | Invalid capability routing format |
| github | backup_repo | Invalid capability routing format |
| github | scan_dependencies | Invalid capability routing format |
| github | create_release | Invalid capability routing format |
| workflow | transform_records | Invalid capability routing format |
| workflow | verify_shape | Invalid capability routing format |
| workflow | route | Invalid capability routing format |
| workflow | aggregate | Invalid capability routing format |
| workflow | filter | Invalid capability routing format |
| workflow | conditional_branch | Invalid capability routing format |
| monitoring | check_rss | Invalid capability routing format |
| monitoring | check_website | Invalid capability routing format |
| monitoring | check_inbox | Invalid capability routing format |
| monitoring | run_scan | Invalid capability routing format |
| monitoring | check_uptime | Invalid capability routing format |
| artifact | generate_pdf | Invalid capability routing format |
| artifact | generate_docx | Invalid capability routing format |
| artifact | generate_pptx | Invalid capability routing format |
| artifact | generate_xlsx | Invalid capability routing format |
| artifact | generate_html | Invalid capability routing format |
| data | read_source | Invalid capability routing format |
| data | transform | Invalid capability routing format |
| data | write_store | Invalid capability routing format |
| data | validate_shape | Invalid capability routing format |
| email | read_inbox | Invalid capability routing format |
| email | send_email | Invalid capability routing format |
| email | apply_label | Invalid capability routing format |
| email | watch_inbox | Invalid capability routing format |
| calendar | list_events | Invalid capability routing format |
| calendar | create_event | Invalid capability routing format |
| calendar | get_todays_events | Invalid capability routing format |
| memory | store | Invalid capability routing format |
| memory | retrieve | Invalid capability routing format |
| memory | log_event | Invalid capability routing format |
| http | fetch | Invalid capability routing format |
| http | poll | Invalid capability routing format |
| http | post | Invalid capability routing format |
| media | transcribe | Invalid capability routing format |
| media | generate_image | Invalid capability routing format |
| media | process_video | Invalid capability routing format |
| code_project | scaffold | Invalid capability routing format |
| code_project | run_tests | Invalid capability routing format |
| code_project | lint | Invalid capability routing format |
| mcp_tool | call | Invalid capability routing format |
| terminal | run | Invalid capability routing format |
| terminal | execute | Invalid capability routing format |
| terminal | scaffold | Invalid capability routing format |
| terminal | backup | Invalid capability routing format |
| terminal | health_check | Invalid capability routing format |
| terminal | scan | Invalid capability routing format |
| terminal | create_release | Invalid capability routing format |
| terminal | extract | Invalid capability routing format |
| terminal | generate | Invalid capability routing format |
| knowledge | sync | Invalid capability routing format |
| knowledge | vector_search | Invalid capability routing format |

### Steps That FAIL (no _ACTION_MAP entry → default to execute_capability)

| Capability | Action | Error |
|-----------|--------|-------|
| ai_reasoning | transcribe | Invalid capability routing format |
| ai_reasoning | embed | Invalid capability routing format |
| ai_reasoning | plan_slides | Invalid capability routing format |
| ai_reasoning | compose_html | Invalid capability routing format |
| ai_reasoning | detect_pii | Invalid capability routing format |
| ai_reasoning | verify_no_pii | Invalid capability routing format |
| ai_reasoning | draft_reply | Invalid capability routing format |
| ai_reasoning | compose_briefing | Invalid capability routing format |
| ai_reasoning | compose_prep | Invalid capability routing format |
| ai_reasoning | classify_actionable | Invalid capability routing format |
| ai_reasoning | detect_event | Invalid capability routing format |
| ai_reasoning | write_changelog | Invalid capability routing format |
| ai_reasoning | analyze_diff | Invalid capability routing format |
| ai_reasoning | review_diff | Invalid capability routing format |
| ai_reasoning | classify_issue | Invalid capability routing format |
| ai_reasoning | extract_error | Invalid capability routing format |
| ai_reasoning | summarize_change | Invalid capability routing format |
| ai_reasoning | aggregate_risk | Invalid capability routing format |
| ai_reasoning | score_priority | Invalid capability routing format |
| ai_reasoning | compose_review | Invalid capability routing format |
| ai_reasoning | research_topics | Invalid capability routing format |
| ai_reasoning | compose_brief | Invalid capability routing format |
| ai_reasoning | synthesize_report | Invalid capability routing format |
| ai_reasoning | summarize_videos | Invalid capability routing format |
| ai_reasoning | analyze_competitive_changes | Invalid capability routing format |
| ai_reasoning | adapt_per_platform | Invalid capability routing format |
| ai_reasoning | draft_followups | Invalid capability routing format |
| ai_reasoning | dedupe_and_score | Invalid capability routing format |
| ai_reasoning | structure_entry | Invalid capability routing format |
| ai_reasoning | design_spreadsheet | Invalid capability routing format |
| ai_reasoning | extract_meeting_structure | Invalid capability routing format |
| ai_reasoning | prioritize_updates | Invalid capability routing format |
| ai_reasoning | repair_document | Invalid capability routing format |
| terminal | render_pptx | Invalid capability routing format |
| terminal | render_pdf_from_html | Invalid capability routing format |
| terminal | render_docx | Invalid capability routing format |
| terminal | verify_pptx | Invalid capability routing format |
| terminal | verify_pdf | Invalid capability routing format |
| terminal | verify_docx | Invalid capability routing format |
| terminal | verify_bundle | Invalid capability routing format |
| terminal | git_init | Invalid capability routing format |
| terminal | open_vscode | Invalid capability routing format |
| terminal | delegate_to_agent | Invalid capability routing format |
| terminal | render_markdown | Invalid capability routing format |
| terminal | append_xlsx_row | Invalid capability routing format |
| memory | record_and_compare | Invalid capability routing format |
| memory | diff_against_last | Invalid capability routing format |
| memory | load_conversation | Invalid capability routing format |
| memory | save_turn | Invalid capability routing format |
| memory | filter_new | Invalid capability routing format |
| memory | exclude_recently_contacted | Invalid capability routing format |
| memory | apply_field_map | Invalid capability routing format |
| memory | diff_snapshots | Invalid capability routing format |
| memory | week_activity | Invalid capability routing format |
| memory | gather_context | Invalid capability routing format |
| memory | state_transition | Invalid capability routing format |
| communication | debounce_messages | Invalid capability routing format |
| communication | format_failure | Invalid capability routing format |
| communication | send_with_ack | Invalid capability routing format |
| communication | send_batch | Invalid capability routing format |
| communication | send_file | Invalid capability routing format |
| communication | apply_label | Invalid capability routing format |
| communication | get_updates | Invalid capability routing format |
| communication | priority_unread | Invalid capability routing format |
| communication | set_status | Invalid capability routing format |
| communication | clear_status | Invalid capability routing format |
| workflow | request_approval | Invalid capability routing format |
| workflow | wait_for_ack | Invalid capability routing format |
| workflow | advance_tier_or_stop | Invalid capability routing format |
| workflow | branch | Invalid capability routing format |
| workflow | validate_schema | Invalid capability routing format |
| mcp_tool | find_stale_leads | Invalid capability routing format |
| mcp_tool | crm_upsert | Invalid capability routing format |
| mcp_tool | crm_get | Invalid capability routing format |
| mcp_tool | upsert_ticket | Invalid capability routing format |
| mcp_tool | create_page | Invalid capability routing format |
| mcp_tool | get_page | Invalid capability routing format |
| mcp_tool | list_changed | Invalid capability routing format |
| mcp_tool | upsert | Invalid capability routing format |
| mcp_tool | create_task | Invalid capability routing format |
| media | generate_image | Invalid capability routing format |
| media | text_to_speech | Invalid capability routing format |
| media | transcode_variants | Invalid capability routing format |
| media | publish | Invalid capability routing format |
| media | verify_posts | Invalid capability routing format |
| calendar | today_events | Invalid capability routing format |
| calendar | upcoming_within | Invalid capability routing format |
| calendar | run_command | Invalid capability routing format |
| calendar | get_event | Invalid capability routing format |
| github | repo_metrics | Invalid capability routing format |
| github | export_archive | Invalid capability routing format |
| github | prs_since_last_tag | Invalid capability routing format |
| github | get_pr_diff | Invalid capability routing format |
| github | gather_issue_context | Invalid capability routing format |
| github | create_draft_pr | Invalid capability routing format |
| github | get_issue | Invalid capability routing format |
| github | apply_labels | Invalid capability routing format |
| github | dependency_scan | Invalid capability routing format |
| github | create_issue | Invalid capability routing format |
| github | get_run_logs | Invalid capability routing format |
