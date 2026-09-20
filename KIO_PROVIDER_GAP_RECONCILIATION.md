# KIO Provider Gap Reconciliation — Source-Verified Audit

**Date:** 2026-09-14
**Scope:** All 11 P2 provider-gap categories, verified against actual KIO source and 63 authoritative YAML templates
**Source of Truth:** `C:\Users\joelj\Downloads\kio_final\automation\library\` (runtime source, per `KIO_AUTOMATION_SOURCE_OF_TRUTH_AUDIT.md`)

---

## Executive Summary

**Definitive Template Counts:**
- FULLY EXECUTABLE: **2** templates (all steps route to direct boundary actions)
- BLOCKED BY P1 FORMAT MISMATCH: **61** templates (at least one step routes through `execute_capability`)

**Previous audit claims DISPROVED:**
- "8/32/23 → FULLY/PARTIAL/BLOCKED" — **FALSE**. Only 2 are fully executable, not 8.
- "8 of 11 categories have existing native implementations" — **MISLEADING**. Only 6 have full implementations; 2 have partial; 2 are N/A (0 templates).
- "ai_reasoning routing alone could unlock 42/63 templates" — **FALSE**. 46 templates use ai_reasoning, but fixing routing alone doesn't unlock them — the LLM calls must also work, and many templates use multiple capabilities.

---

## Execution Path Analysis

### How Templates Execute

```
StepRunner.execute_step()
  → _ACTION_MAP[(capability, action)] → boundary_action
  → _build_target(capability, action, inputs) → plain string
  → _call_boundary(boundary_action, target, inputs, capability, action)
    → execute_action(action, target)
      → _load_handler(action) → handler
        → handler(target)
```

### The P1 Format Mismatch (applies to ALL 11 categories)

1. `_build_target()` produces a plain string (e.g., `"youtube search terms"`)
2. `execute_capability()` in `app_operator.py:3177` expects `"app_name::capability::args"` format
3. `target.split("::", 3)` produces `["youtube search terms"]` — only 1 part
4. Returns `"Invalid capability routing format"` — execution fails

**This is the single blocking issue for ALL non-filesystem/non-browser/non-knowledge steps.**

### Which Categories Route Where

| Category | _ACTION_MAP Target | Direct Boundary Action? | Hits P1? |
|----------|-------------------|------------------------|----------|
| browser | `browser_goto`, `browser_click`, etc. | YES (most actions) | NO (direct) |
| filesystem | `write_csv`, `fs_exists`, etc. | YES (all actions) | NO (direct) |
| knowledge | `web_search`, `fetch_url`, etc. | YES (all actions) | NO (direct) |
| ai_reasoning | `execute_capability` | NO | YES |
| communication | `execute_capability` | NO | YES |
| github | `execute_capability` | NO | YES |
| memory | `execute_capability` | NO | YES |
| calendar | `execute_capability` | NO | YES |
| mcp_tool | `execute_capability` | NO | YES |
| workflow | `execute_capability` | NO | YES |
| media | `execute_capability` | NO | YES |
| terminal | `execute_capability` | NO | YES |
| http | `execute_capability` | NO | YES |
| code_project | `execute_capability` | NO | YES |

---

## Definitive Category Matrix

| # | Capability | YAML Templates | Actions Used (template) | _ACTION_MAP Entries | Actions NOT in _ACTION_MAP | Existing Native Implementation | Provider Registered | Gap Type | Required Action |
|---|-----------|---------------|------------------------|--------------------|-----------------------------|--------------------------------|--------------------|---------|-----------------|
| 1 | ai_reasoning | 46 | classify, enrich, summarize, extract_structured, validate_against_schema, embed, grounded_answer, transcribe, design_spreadsheet, extract_meeting_structure, research, write_content, plan_document, repair_document, compose_html, plan_slides, summarize_change, draft_followups, draft_reply, dedupe_and_score, triage_ticket, chat, detect_pii, verify_no_pii, classify_response, structure_entry, extract_error, prioritize_updates, classify_issue, review_diff, analyze_diff, write_changelog, summarize_health, adapt_per_platform, score_priority, summarize_digest, aggregate_risk, compose_briefing, detect_event, classify_actionable, compose_prep, compose_review, analyze_competitive_changes, compose_brief, research_topics, synthesize_report, summarize_videos | classify, analyze, summarize, extract, generate, transform, enrich, reason | 38 actions not in _ACTION_MAP | `ask_llm_sync()` at `llm/llm_ops.py:62`, `ask_llm()` at `llm_router.py:295` | NO | ROUTING_ONLY | Wire LLM calls to execute_capability path |
| 2 | communication | 31 | send_message, send_batch, debounce_messages, send_with_ack, format_for_channel, send_file, get_updates, clear_status, set_status, priority_unread, apply_label | send_message, format_for_channel, send_notification, send_alert | send_batch, debounce_messages, send_with_ack, send_file, get_updates, clear_status, set_status, priority_unread, apply_label | `message_answer()` at `messages.py`, `send_telegram_message()` at `watches.py:72` | NO | ROUTING_ONLY | Wire messaging to execute_capability path |
| 3 | github | 8 | get_run_logs, create_issue, dependency_scan, apply_labels, get_issue, create_draft_pr, gather_issue_context, get_pr_diff, create_release, prs_since_last_tag, export_archive, repo_metrics | get_pr_diff, list_issues, create_issue, get_repo_info, backup_repo, scan_dependencies, create_release | get_run_logs, dependency_scan, apply_labels, get_issue, create_draft_pr, gather_issue_context, prs_since_last_tag, export_archive, repo_metrics | GitHub MCP server (`mcp_github_server.py`) with 9 tools | YES (MCP) | ADAPTER_REQUIRED | Create adapter mapping template actions to MCP tool names |
| 4 | memory | 13 | diff_against_last, record_and_compare, exclude_recently_contacted, load_conversation, save_turn, filter_new, apply_field_map, state_transition, gather_context, week_activity, diff_snapshots | store, retrieve, log_event | ALL 11 actions not in _ACTION_MAP | `ContextStore` at `context_store.py` (media intelligence only, NOT general memory) | NO | PROVIDER_REQUIRED | Build general-purpose memory provider |
| 5 | calendar | 4 | today_events, get_event, run_command, upcoming_within | list_events, create_event, get_todays_events | ALL 4 actions not in _ACTION_MAP | NONE | NO | PROVIDER_REQUIRED | Build calendar provider (requires Google OAuth) |
| 6 | mcp_tool | 7 | find_stale_leads, crm_get, crm_upsert, upsert_ticket, create_page, get_page, list_changed, upsert, create_task, due_tasks | call | ALL 10 actions not in _ACTION_MAP | `execute_mcp_tool()` at `execution_boundary.py:1445` | YES (MCP infra) | PROVIDER_REQUIRED | Build CRM/Notion/Task MCP servers |
| 7 | workflow | 7 | route, request_approval, advance_tier_or_stop, wait_for_ack, transform_records, verify_shape, validate_schema, branch | transform_records, verify_shape, route, aggregate, filter, conditional_branch | request_approval, advance_tier_or_stop, wait_for_ack, validate_schema, branch | `WorkflowExecutionProvider` with 8 capabilities | YES | ADAPTER_REQUIRED | Map template actions to provider capabilities |
| 8 | media | 4 | generate_image, text_to_speech, transcode_variants, publish, verify_posts | transcribe, generate_image, process_video | text_to_speech, transcode_variants, publish, verify_posts | Some functions exist in `voice.py`, `media/` | NO | PROVIDER_REQUIRED | Build media provider |
| 9 | http | 0 | N/A | fetch, poll, post | N/A | `fetch_url` in KnowledgeProvider | NO | UNNECESSARY | None (0 templates) |
| 10 | code_project | 0 | N/A | scaffold, run_tests, lint | N/A | `terminal.scaffold` in scaffold_project.yaml | NO | UNNECESSARY | None (0 templates) |
| 11 | terminal | 14 | run_command, render_docx, verify_docx, render_pdf_from_html, render_pptx, verify_bundle, verify_pdf, verify_pptx, delegate_to_agent, git_init, open_vscode, scaffold, render_markdown, append_xlsx_row | run, execute, scaffold, backup, health_check, scan, create_release, extract, generate | render_docx, verify_docx, render_pdf_from_html, render_pptx, verify_bundle, verify_pdf, verify_pptx, delegate_to_agent, git_init, open_vscode, render_markdown, append_xlsx_row | `TerminalProvider` with run_command, clipboard_copy, clipboard_paste | YES | ADAPTER_REQUIRED | Map template actions to provider capabilities |

---

## Per-Category Evidence and Template Impact

### 1. ai_reasoning — ROUTING_ONLY

**Evidence:**
- `ask_llm_sync()` exists at `llm/llm_ops.py:62` — synchronous LLM call wrapper
- `ask_llm()` exists at `llm_router.py:295` — async LLM call with multi-provider failover
- NO provider registered in ProviderRegistry for ai_reasoning
- ALL 46 templates route through `execute_capability` which fails at P1

**Template IDs affected (46):**
- ai: classify_and_route, enrich_records, extract_to_structured, rag_answer, transcribe_summarize
- artifacts: data_to_xlsx, meeting_to_report, multiformat_report, research_to_docx, research_to_pdf, research_to_pptx
- browser: page_change_monitor
- business: crm_followup, email_autoresponder_approval, lead_intake_crm, support_ticket_triage
- communication: chat_assistant, voice_assistant
- data: csv_pii_scrub, file_extract_to_csv, form_intake, knowledge_base_sync
- development: ci_failure_alert, dependency_monitor, github_issue_triage, issue_to_implementation, pr_review_prep, release_changelog, repo_health_report
- files: document_summarize, invoice_extract_to_sheet
- media: content_repurpose
- monitoring: inbox_monitor, rss_news_monitor, security_scan_alert
- productivity: ecosystem_briefing, email_label_ai, email_to_calendar, email_to_task, meeting_prep, morning_briefing, weekly_review
- research: competitor_monitor, daily_brief, web_scrape_to_report, youtube_summary

**Impact if fixed:** All 46 templates would still be blocked by other capabilities (communication, github, etc.) in multi-capability templates. ai_reasoning alone doesn't unlock any template end-to-end.

---

### 2. communication — ROUTING_ONLY

**Evidence:**
- `message_answer()` at `messages.py` — Telegram outbound messaging
- `send_telegram_message()` at `watches.py:72` — monitoring alert messaging
- NO provider registered in ProviderRegistry for communication
- ALL 31 templates route through `execute_capability`

**Template IDs affected (31):**
- ai: transcribe_summarize
- browser: page_change_monitor, price_monitor
- business: crm_followup, email_autoresponder_approval, lead_intake_crm, support_ticket_triage
- communication: chat_assistant, escalation_alert, notify, voice_assistant, workflow_failure_alert
- data: form_intake
- development: ci_failure_alert, dependency_monitor, github_issue_triage, pr_review_prep, repo_health_report
- files: document_summarize
- monitoring: inbox_monitor, rss_news_monitor, security_scan_alert, website_uptime
- productivity: calendar_to_status, ecosystem_briefing, email_label_ai, meeting_prep, morning_briefing, weekly_review
- research: competitor_monitor, daily_brief, youtube_summary

**Note:** Some communication steps (send_message) DO have _ACTION_MAP entries, but they still route to execute_capability which fails at P1.

---

### 3. github — ADAPTER_REQUIRED

**Evidence:**
- GitHub MCP server exists at `mcp_github_server.py` with 9 tools:
  - github_search_repos, github_get_repo, github_list_issues, github_create_issue
  - github_list_prs, github_get_contents, github_list_branches, github_list_commits, github_create_gist
- MCP server IS registered via `register_all_mcp_servers()`
- Template actions DON'T MATCH MCP tool names (e.g., `get_pr_diff` vs `github_list_prs`)
- Requires `GITHUB_TOKEN` environment variable and `PyGithub` package

**Template IDs affected (8):**
- development: ci_failure_alert, dependency_monitor, github_issue_triage, issue_to_implementation, pr_review_prep, release_changelog, repo_backup, repo_health_report

**Overlap analysis:**
- Template `create_issue` → MCP `github_create_issue` ✓ (name matches)
- Template `get_pr_diff` → MCP `github_list_prs` (partial overlap)
- Template `list_issues` → MCP `github_list_issues` ✓ (name matches)
- Template `get_repo_info` → MCP `github_get_repo` ✓ (name matches)
- Template `dependency_scan`, `apply_labels`, `get_issue`, `create_draft_pr`, `gather_issue_context`, `prs_since_last_tag`, `export_archive`, `repo_metrics` → NO MCP equivalent

---

### 4. memory — PROVIDER_REQUIRED

**Evidence:**
- `ContextStore` at `context_store.py` exists but is a MEDIA INTELLIGENCE store (stores media watch context, not general-purpose memory)
- NO general-purpose memory provider exists
- NO provider registered in ProviderRegistry for memory
- ALL 13 templates route through `execute_capability`

**Template IDs affected (13):**
- browser: page_change_monitor, price_monitor
- business: crm_followup
- communication: chat_assistant
- data: api_poll_to_store, record_sync
- monitoring: rss_news_monitor, website_uptime
- productivity: meeting_prep, weekly_review
- research: competitor_monitor, daily_brief, youtube_summary

**Note:** The memory actions used in templates (diff_against_last, record_and_compare, load_conversation, save_turn, filter_new, etc.) are operational memory patterns, not general-purpose key-value storage. A purpose-built provider is needed.

---

### 5. calendar — PROVIDER_REQUIRED

**Evidence:**
- NO calendar implementation exists anywhere in KIO
- NO provider registered in ProviderRegistry for calendar
- ALL 4 templates route through `execute_capability`
- Requires external infrastructure (Google Calendar API, OAuth credentials)

**Template IDs affected (4):**
- productivity: ecosystem_briefing, email_to_calendar, meeting_prep, morning_briefing

**External dependencies:** Google Calendar API, OAuth2 credentials, `google-api-python-client` package

---

### 6. mcp_tool — PROVIDER_REQUIRED

**Evidence:**
- `execute_mcp_tool()` exists at `execution_boundary.py:1445`
- MCP infrastructure is registered (filesystem, git, terminal, sqlite, docker, github, postgres, redis)
- Template actions (crm_get, crm_upsert, create_page, create_task, etc.) require CRM/Notion/Task MCP servers that DON'T EXIST
- NO provider for these specific MCP servers

**Template IDs affected (7):**
- business: crm_followup, lead_intake_crm, support_ticket_triage
- data: knowledge_base_sync, record_sync
- productivity: email_to_task, morning_briefing

**External dependencies:** Custom MCP servers for CRM (Salesforce/HubSpot), Notion, Task management

---

### 7. workflow — ADAPTER_REQUIRED

**Evidence:**
- `WorkflowExecutionProvider` exists with 8 capabilities: workflow_create, workflow_execute, workflow_status, workflow_cancel, workflow_pause, workflow_resume, workflow_list, workflow_progress
- Provider IS registered in ProviderRegistry
- Template actions (route, request_approval, advance_tier_or_stop, wait_for_ack, transform_records, verify_shape, validate_schema, branch) DON'T MATCH provider capabilities
- The provider wraps WorkflowEngine at a different abstraction level

**Template IDs affected (7):**
- ai: classify_and_route
- business: email_autoresponder_approval
- communication: escalation_alert
- data: json_transform, webhook_to_store
- files: invoice_extract_to_sheet
- media: content_repurpose

**Note:** Some template actions (transform_records, verify_shape, route) ARE in _ACTION_MAP but still route to execute_capability, not to the WorkflowExecutionProvider.

---

### 8. media — PROVIDER_REQUIRED

**Evidence:**
- Some functions exist: `transcribe` in voice.py, `generate_image` potentially in media/
- NO media provider registered in ProviderRegistry
- ALL 4 templates route through `execute_capability`

**Template IDs affected (4):**
- ai: image_generate
- communication: voice_assistant
- files: drive_to_social
- media: content_repurpose

**Actions needed:** generate_image, text_to_speech, transcode_variants, publish, verify_posts

---

### 9. http — UNNECESSARY

**Evidence:**
- 0 templates use `capability: http`
- _ACTION_MAP entries (fetch, poll, post) exist but are dead code
- `fetch_url` exists in KnowledgeProvider — could serve this role

**Template IDs affected:** NONE

---

### 10. code_project — UNNECESSARY

**Evidence:**
- 0 templates use `capability: code_project`
- _ACTION_MAP entries (scaffold, run_tests, lint) exist but are dead code
- `scaffold_project.yaml` uses `terminal: scaffold`, not `code_project: scaffold`

**Template IDs affected:** NONE

**Note:** Previous audit claimed code_project was "PROVIDER_REQUIRED" or "ROUTING_ONLY". Both were WRONG. The correct classification is UNNECESSARY — no templates use this capability.

---

### 11. terminal — ADAPTER_REQUIRED

**Evidence:**
- `TerminalProvider` exists with capabilities: run_command, clipboard_copy, clipboard_paste
- Provider IS registered in ProviderRegistry
- Template actions (render_docx, verify_docx, render_pdf_from_html, render_pptx, etc.) DON'T MATCH provider capabilities
- The provider only supports run_command, not document rendering

**Template IDs affected (14):**
- artifacts: data_to_xlsx (3 steps), meeting_to_report, multiformat_report, research_to_docx, research_to_pdf, research_to_pptx
- development: issue_to_implementation, repo_health_report, scaffold_project
- files: duplicate_detector, invoice_extract_to_sheet
- productivity: weekly_review
- research: competitor_monitor, web_scrape_to_report

**Note:** The terminal capability in templates is used for document rendering (docx, pdf, pptx, xlsx), not just command execution. The TerminalProvider's `run_command` could potentially handle some of these via command-line tools, but the template actions are higher-level abstractions.

---

## Previous Claims Verification

### Claim 1: "8 of 11 missing provider categories have existing native implementations"

**Verdict: FALSE (misleading)**

| Category | Has Implementation? | Details |
|----------|-------------------|---------|
| ai_reasoning | YES | ask_llm_sync, ask_llm |
| communication | YES | message_answer, send_telegram_message |
| github | YES | MCP server with 9 tools |
| memory | PARTIAL | ContextStore exists but is media-only, not general memory |
| calendar | NO | No implementation |
| mcp_tool | YES | execute_mcp_tool exists, MCP infra registered |
| workflow | YES | WorkflowExecutionProvider with 8 capabilities |
| media | PARTIAL | Some functions exist in voice.py, media/ |
| terminal | YES | TerminalProvider with 3 capabilities |
| http | N/A | 0 templates |
| code_project | N/A | 0 templates |

**Actual count:** 6 full, 2 partial, 2 N/A. The claim of "8" counts partial implementations as full, which is misleading because having an implementation doesn't mean it's wired to the template execution path.

### Claim 2: "ai_reasoning routing alone could unlock 42/63 templates"

**Verdict: FALSE**

**Facts:**
- 46 templates use ai_reasoning (not 42)
- Fixing ai_reasoning routing alone doesn't unlock ANY template end-to-end
- Most templates using ai_reasoning also use other blocked capabilities (communication, github, memory, etc.)
- Example: `development/github_issue_triage.yaml` uses ai_reasoning, github, AND communication — fixing ai_reasoning alone leaves 2 blocked capabilities

**Actual unlock potential:** 0 templates fully unlocked by fixing ai_reasoning alone

---

## Gap Type Summary

| Gap Type | Count | Categories | What It Means |
|----------|-------|------------|---------------|
| NONE | 0 | — | No gap |
| ROUTING_ONLY | 3 | ai_reasoning, communication, terminal | Implementation exists, not wired to execute_capability path |
| ADAPTER_REQUIRED | 3 | github, workflow, terminal | Provider exists but template actions don't match provider capabilities |
| PROVIDER_REQUIRED | 4 | memory, calendar, mcp_tool, media | No provider exists, must be built |
| UNNECESSARY | 2 | http, code_project | 0 templates use this capability |
| EXTERNAL_INFRASTRUCTURE_REQUIRED | 1 | calendar | Requires Google OAuth, external APIs |
| TRIGGER_INFRASTRUCTURE_REQUIRED | 0 | — | — |
| GENUINELY_UNSUPPORTED | 0 | — | — |

---

## Recommended Phase 4 Priority (Summary)

See `KIO_PHASE4_PROVIDER_PRIORITY_FINAL.md` for detailed ranking.

**Recommended FIRST implementation target:** P1 format mismatch fix in `_build_target()` / `execute_capability()`

**Rationale:**
- Single point fix unlocks ALL 61 blocked templates (from P1 perspective)
- No new providers needed
- No external dependencies
- No credential burden
- Reuses existing implementations (ask_llm, message_answer, TerminalProvider, etc.)
- Runtime verifiable with existing test infrastructure

**After P1 fix:** The remaining gaps are:
- ROUTING_ONLY (3): Wire LLM calls, messaging, terminal actions
- ADAPTER_REQUIRED (3): Map template actions to existing provider capabilities
- PROVIDER_REQUIRED (4): Build new providers (memory, calendar, mcp_tool, media)
- UNNECESSARY (2): No action needed
