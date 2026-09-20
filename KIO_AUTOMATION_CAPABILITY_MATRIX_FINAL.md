# KIO Automation — Definitive Capability Matrix (63 Templates)

> **Source of truth:** Every claim grounded in actual source code reading and package probing.
> **Date:** 2026-09-13
> **Author:** Automated audit

---

## Infrastructure Summary

### Registered KIO Providers (7)
| Provider | ID | Actions | Status |
|----------|----|---------|--------|
| BrowserProvider | `browser` | `play_youtube`, `search_youtube` | ✅ YouTube only |
| FilesystemProvider | `filesystem` | `open_folder` | ✅ Single action |
| TerminalProvider | `terminal` | Safe command whitelist (git, dir, tree, etc.) | ✅ Generic |
| WorkflowProvider | `workflow` | Delegates to WorkflowEngine | ✅ Generic |
| SystemProvider | `system` | `lock_system`, `shutdown_system`, `restart_system`, `recovery_runtime` | ✅ System control |
| DesktopProvider | `desktop` | `open_app`, `close_app`, `search_web`, `execute_capability` + 16 rich actions (mouse/keyboard/clipboard/screen/window) | ✅ Desktop automation |
| MCPProvider | `mcp_tool` | Delegates to MCP server registry | ✅ Via MCP servers |

### MCP Servers (8 types, 4 local + 4 external)
| Server | Type | Status |
|--------|------|--------|
| filesystem | Local | ✅ Auto-registered |
| git | Local | ✅ Auto-registered |
| terminal | Local | ✅ Auto-registered |
| sqlite | Local | ✅ Auto-registered |
| docker | External | ⚠️ If Docker installed |
| github | External | ⚠️ If GitHub MCP configured |
| postgres | External | ⚠️ If Postgres MCP configured |
| redis | External | ⚠️ If Redis MCP configured |

### LLM Providers (6, chain-based failover)
| Provider | Priority | Status |
|----------|----------|--------|
| Gemini | 0 | ✅ Primary |
| Groq | 1 | ✅ Fast inference |
| HuggingFace | 2 | ✅ Free tier |
| OpenRouter | 3 | ✅ Multi-model |
| Together AI | 4 | ✅ Fallback |
| Cerebras | 5 | ✅ Fallback |

### Installed Packages (verified by probe)
| Package | Version | Status |
|---------|---------|--------|
| httpx | 0.28.1 | ✅ |
| playwright | 1.61.0 | ✅ (sync + async) |
| python-docx | installed | ✅ |
| openpyxl | 3.1.5 | ✅ |
| python-pptx | installed | ✅ |
| lxml | 6.1.1 | ✅ |
| pandas | 2.5.1 | ✅ |
| numpy | 2.5.1 | ✅ |
| jinja2 | 3.1.6 | ✅ |
| keyring | 25.7.0 | ✅ |
| psutil | 7.2.2 | ✅ |
| pyyaml | installed | ✅ |
| pillow | installed | ✅ |
| aiohttp | 3.14.3 | ✅ |
| faster_whisper | 1.2.1 | ✅ |
| torch | 2.13.0 | ✅ |
| sentence_transformers | 6.0.0 | ✅ |
| requests | 2.33.0 | ✅ |
| scikit-learn | installed | ✅ |
| pydantic | 2.13.5 | ✅ |
| fastapi | 0.138.2 | ✅ |
| uvicorn | 0.49.0 | ✅ |
| pyotp | 2.9.0 | ✅ |
| cryptography | 49.0.0 | ✅ |
| discord.py | installed | ✅ |
| google-api-python-client | installed | ✅ |
| boto3 | 1.43.88 | ✅ |
| **beautifulsoup4** | — | ❌ NOT INSTALLED |
| **gitpython** | — | ❌ NOT INSTALLED |
| **feedparser** | — | ❌ NOT INSTALLED |
| **chromadb** | — | ❌ NOT INSTALLED |
| **qdrant-client** | — | ❌ NOT INSTALLED |
| **slack_sdk** | — | ❌ NOT INSTALLED |
| **msal** | — | ❌ NOT INSTALLED |
| **selenium** | — | ❌ NOT INSTALLED |
| **yfinance** | — | ❌ NOT INSTALLED |
| **sendgrid** | — | ❌ NOT INSTALLED |
| **twilio** | — | ❌ NOT INSTALLED |
| **stripe** | — | ❌ NOT INSTALLED |

---

## Capability → KIO Implementation Mapping

| Capability | KIO Implementation | Action Coverage | Truth |
|------------|-------------------|-----------------|-------|
| `workflow` | WorkflowProvider → WorkflowEngine | `transform_records`, `verify_shape`, `validate_schema`, `branch`, `route`, `request_approval`, `wait_for_ack`, `advance_tier_or_stop` | ✅ IMPLEMENTED |
| `ai_reasoning` | LLM Gateway (Gemini/Groq/etc.) | `research`, `plan_document`, `write_content`, `classify`, `summarize`, `transcribe`, `extract_structured`, `detect_pii`, `draft_reply`, `compose_*`, `analyze_*`, `prioritize_*`, `aggregate_risk`, `score_priority`, `triage_ticket`, `enrich`, `validate_against_schema`, `embed`, `grounded_answer` | ✅ IMPLEMENTED (via LLM) |
| `terminal` | TerminalProvider → subprocess (safe whitelist) | `render_docx`, `render_pptx`, `render_pdf_from_html`, `verify_docx`, `verify_pptx`, `verify_pdf`, `git_init`, `open_vscode`, `scaffold`, `append_xlsx_row`, `render_markdown`, `run_command`, `delegate_to_agent` | ⚠️ PARTIAL — safe-command whitelist may block some actions |
| `filesystem` | FilesystemProvider → file_operator | `open_folder` | ❌ SINGLE ACTION — missing: `write_csv`, `verify_csv`, `move_file`, `hash_tree`, `classify_file`, `extract_text`, `append_csv`, `store_record`, `write`, `verify_path`, `verify_project`, `verify_image`, `verify_paths`, `write_derivatives`, `upload_backup`, `verify_upload`, `prune_old_backups`, `append_sheet_row`, `verify_sheet_row`, `recent_drive_changes`, `get_new_asset` |
| `browser` | BrowserProvider → browser_operator | `play_youtube`, `search_youtube` | ❌ YOUTUBE ONLY — missing: `extract_records`, `extract_price`, `fetch_region`, `crawl_extract`, `snapshot_sources`, `browser_goto`, `browser_click`, `browser_hover`, `browser_scroll`, `browser_drag`, `browser_select`, `browser_fill`, `browser_type`, `browser_keypress`, `browser_evaluate`, `browser_extract_text`, `browser_extract_html`, `browser_screenshot`, `browser_pdf`, `search_web` (Google) |
| `communication` | Telegram bot (kio_bot.py) | `send_message` (Telegram only) | ⚠️ TELEGRAM ONLY — missing: `send_file`, `send_batch`, `send_with_ack`, `apply_label`, `get_updates`, `set_status`, `clear_status`, `priority_unread`, `format_for_channel`, `format_failure`, `debounce_messages` |
| `memory` | state_verification.py + trace_logger | `record_and_compare`, `diff_against_last`, `filter_new` (partial) | ⚠️ PARTIAL — has state tracking but not a full KV store with `diff_snapshots`, `week_activity`, `load_conversation`, `save_turn`, `gather_context`, `apply_field_map`, `exclude_recently_contacted` |
| `knowledge` | — | None | ❌ NOT IMPLEMENTED — missing: `vector_search`, `verify_hmac`, `paginated_get`, `healthcheck`, `multi_scan`, `read_feeds`, `batch_lookup`, `list_new_videos`, `validate_lead`, `get_weather` |
| `mcp_tool` | MCP servers (filesystem, git, terminal, sqlite, docker, github, postgres, redis) | File/git/terminal/sqlite operations | ⚠️ PARTIAL — missing: `notion`, `airtable`, `linear`, `google_tasks`, `todoist` MCP servers |
| `media` | media_contract.py (type definitions only) | None | ❌ CONTRACTS ONLY — missing: `publish`, `verify_posts`, `transcode_variants`, `generate_image`, `text_to_speech` |
| `calendar` | — | None | ❌ NOT IMPLEMENTED — missing: `today_events`, `upcoming_within`, `get_event`, `run_command` (create event) |
| `github` | MCP github server | `get_issue`, `get_pr_diff`, `create_draft_pr`, `apply_labels`, `create_issue`, `create_release`, `dependency_scan`, `export_archive`, `repo_metrics`, `get_run_logs`, `gather_issue_context`, `prs_since_last_tag` | ⚠️ PARTIAL — depends on MCP github server being configured |
| `system` | SystemProvider | `lock_system`, `shutdown_system`, `restart_system`, `recovery_runtime` | ✅ IMPLEMENTED |
| `desktop` | DesktopProvider | `open_app`, `close_app`, `search_web`, `execute_capability` + 16 rich actions | ✅ IMPLEMENTED |
| `code_project` | — | None | ❌ NOT IMPLEMENTED |

---

## 63-Template Capability Matrix

### Legend
- ✅ = Capability fully implemented in KIO
- ⚠️ = Partial implementation (some actions missing)
- ❌ = Not implemented / provider missing
- **TRUTH** = Can this template actually execute in current KIO?

---

### AI Category (6 templates)

| # | Template ID | Name | Capabilities Required | Providers Required | Package Deps | TRUTH |
|---|-------------|------|----------------------|-------------------|--------------|-------|
| 1 | `ai.classify_and_route` | Classify → Route | ai_reasoning, workflow | llm | — | ✅ EXECUTABLE |
| 2 | `ai.enrich_records` | Enrich Records with AI + Web | ai_reasoning, knowledge, filesystem | llm | — | ❌ BLOCKED: knowledge missing |
| 3 | `ai.extract_to_structured` | Unstructured → Structured Fields | ai_reasoning | llm | — | ✅ EXECUTABLE |
| 4 | `ai.image_generate` | Prompt → Generated Image → Deliver | filesystem, media | image_model | — | ❌ BLOCKED: media missing |
| 5 | `ai.rag_answer` | RAG Answer over Knowledge Base | ai_reasoning, knowledge | llm, vectorstore | — | ❌ BLOCKED: knowledge/vectorstore missing |
| 6 | `ai.transcribe_summarize` | Audio/Video → Transcript → Summary | ai_reasoning, filesystem, communication | llm, whisper | faster_whisper, torch | ⚠️ PARTIAL: transcription works, communication limited to Telegram |

### Artifacts Category (6 templates)

| # | Template ID | Name | Capabilities Required | Providers Required | Package Deps | TRUTH |
|---|-------------|------|----------------------|-------------------|--------------|-------|
| 7 | `artifacts.data_to_xlsx` | Spec → Calculating Spreadsheet | ai_reasoning, terminal | llm, terminal | openpyxl | ⚠️ PARTIAL: openpyxl present, LibreOffice needed for recalc |
| 8 | `artifacts.meeting_to_report` | Meeting Transcript → Polished Report | ai_reasoning, terminal | llm, python_docx | python-docx | ⚠️ PARTIAL: LLM writes, python-docx renders |
| 9 | `artifacts.multiformat_report` | One Content Plan → DOCX + PDF + PPTX | ai_reasoning, terminal | llm, python_docx, weasyprint, python_pptx, libreoffice | python-docx, python-pptx | ⚠️ PARTIAL: DOCX+PPTX possible, PDF needs WeasyPrint |
| 10 | `artifacts.research_to_docx` | Research → Professional DOCX Report | ai_reasoning, terminal | llm, python_docx, libreoffice | python-docx | ⚠️ PARTIAL: LLM research + python-docx render |
| 11 | `artifacts.research_to_pdf` | Research → PDF Report (HTML/CSS engine) | ai_reasoning, terminal | llm, weasyprint, pypdf | — | ❌ BLOCKED: weasyprint not installed |
| 12 | `artifacts.research_to_pptx` | Research → Presentation | ai_reasoning, terminal | llm, python_pptx, libreoffice | python-pptx | ⚠️ PARTIAL: python-pptx present, LibreOffice for rasterize |

### Browser Category (3 templates)

| # | Template ID | Name | Capabilities Required | Providers Required | Package Deps | TRUTH |
|---|-------------|------|----------------------|-------------------|--------------|-------|
| 13 | `browser.page_change_monitor` | Web Page Change Monitor | ai_reasoning, browser, communication, memory | playwright, llm | playwright | ❌ BLOCKED: browser only has YouTube actions |
| 14 | `browser.price_monitor` | Product Price Monitor | browser, communication, memory | playwright | playwright | ❌ BLOCKED: browser only has YouTube actions |
| 15 | `browser.structured_extract` | Web → Structured Data (CSV/Sheet) | browser, filesystem | playwright, llm | playwright | ❌ BLOCKED: browser only has YouTube actions |

### Business Category (4 templates)

| # | Template ID | Name | Capabilities Required | Providers Required | Package Deps | TRUTH |
|---|-------------|------|----------------------|-------------------|--------------|-------|
| 16 | `business.crm_followup` | Stale Lead Follow-up | ai_reasoning, communication, mcp_tool, memory | llm | — | ❌ BLOCKED: mcp_tool needs airtable, communication limited |
| 17 | `business.email_autoresponder_approval` | Email Auto-Responder with Approval | ai_reasoning, communication, workflow | llm | — | ⚠️ PARTIAL: LLM drafts, workflow approval, but no email send |
| 18 | `business.lead_intake_crm` | Lead Intake → CRM → Notify | ai_reasoning, knowledge, communication, mcp_tool | llm | — | ❌ BLOCKED: mcp_tool needs airtable, knowledge missing |
| 19 | `business.support_ticket_triage` | Support Ticket Triage & Route | ai_reasoning, communication, mcp_tool | llm | — | ❌ BLOCKED: mcp_tool needs linear/notion |

### Communication Category (5 templates)

| # | Template ID | Name | Capabilities Required | Providers Required | Package Deps | TRUTH |
|---|-------------|------|----------------------|-------------------|--------------|-------|
| 20 | `communication.chat_assistant` | Chat Assistant with Memory | ai_reasoning, communication, memory | llm | — | ⚠️ PARTIAL: LLM + Telegram send work, memory limited |
| 21 | `communication.escalation_alert` | Tiered Escalation Alert | communication, workflow | — | — | ⚠️ PARTIAL: Telegram send works, multi-channel limited |
| 22 | `communication.notify` | Multi-Channel Notification | communication | — | — | ⚠️ TELEGRAM ONLY: no Slack/Discord/email |
| 23 | `communication.voice_assistant` | Voice Message Assistant | ai_reasoning, communication, media | llm, whisper | faster_whisper | ⚠️ PARTIAL: transcription works, TTS missing |
| 24 | `communication.workflow_failure_alert` | Workflow Failure Alert (meta) | communication | — | — | ⚠️ TELEGRAM ONLY |

### Data Category (8 templates)

| # | Template ID | Name | Capabilities Required | Providers Required | Package Deps | TRUTH |
|---|-------------|------|----------------------|-------------------|--------------|-------|
| 25 | `data.api_poll_to_store` | Scheduled API Poll → Store | knowledge, filesystem, memory | — | httpx | ❌ BLOCKED: knowledge missing |
| 26 | `data.csv_pii_scrub` | CSV → Remove PII → Clean File | ai_reasoning, filesystem | llm | — | ⚠️ PARTIAL: LLM detects PII, filesystem write limited |
| 27 | `data.file_extract_to_csv` | PDF/Image → Extracted Data → CSV | ai_reasoning, filesystem | llm, pdf_reader | — | ⚠️ PARTIAL: LLM extraction works, filesystem write limited |
| 28 | `data.form_intake` | Form Response → Sheet → Notify | ai_reasoning, filesystem, communication | google_sheets, llm | — | ❌ BLOCKED: google_sheets provider missing |
| 29 | `data.json_transform` | JSON Transform / Reshape | workflow | — | — | ✅ EXECUTABLE |
| 30 | `data.knowledge_base_sync` | Content → Knowledge Base | ai_reasoning, mcp_tool | llm | — | ❌ BLOCKED: mcp_tool needs notion/airtable |
| 31 | `data.record_sync` | Two-System Record Sync | mcp_tool, memory | — | — | ❌ BLOCKED: mcp_tool needs notion/airtable |
| 32 | `data.webhook_to_store` | Webhook → Validate → Store | knowledge, filesystem, workflow | — | — | ❌ BLOCKED: knowledge missing, webhook trigger not implemented |

### Development Category (8 templates)

| # | Template ID | Name | Capabilities Required | Providers Required | Package Deps | TRUTH |
|---|-------------|------|----------------------|-------------------|--------------|-------|
| 33 | `development.ci_failure_alert` | CI Failure Triage & Alert | ai_reasoning, communication, github | llm | — | ⚠️ PARTIAL: needs MCP github server, LLM works |
| 34 | `development.dependency_monitor` | Dependency Update Monitor | ai_reasoning, communication, github | llm | — | ⚠️ PARTIAL: needs MCP github server |
| 35 | `development.github_issue_triage` | GitHub Issue Triage | ai_reasoning, communication, github | llm | — | ⚠️ PARTIAL: needs MCP github server |
| 36 | `development.issue_to_implementation` | Issue → Implementation → PR | ai_reasoning, github, terminal | coding_agent | — | ❌ BLOCKED: coding_agent provider missing |
| 37 | `development.pr_review_prep` | PR Review Preparation | ai_reasoning, communication, github | llm | — | ⚠️ PARTIAL: needs MCP github server |
| 38 | `development.release_changelog` | Release Changelog Generator | ai_reasoning, github | llm | — | ⚠️ PARTIAL: needs MCP github server |
| 39 | `development.repo_backup` | Scheduled Repo Backup to Drive | filesystem, github | — | — | ⚠️ PARTIAL: needs MCP github + cloud storage |
| 40 | `development.repo_health_report` | Weekly Repository Health Report | ai_reasoning, communication, github, terminal | llm, python_docx | python-docx | ⚠️ PARTIAL: needs MCP github server |
| 41 | `development.scaffold_project` | Scaffold Code Project → VS Code | filesystem, terminal | vscode_cli | — | ⚠️ PARTIAL: terminal scaffold possible, vscode_cli missing |

### Files Category (5 templates)

| # | Template ID | Name | Capabilities Required | Providers Required | Package Deps | TRUTH |
|---|-------------|------|----------------------|-------------------|--------------|-------|
| 42 | `files.document_summarize` | New Document → Summary + Notify | ai_reasoning, filesystem, communication | llm, pdf_reader | — | ⚠️ PARTIAL: LLM summarize works, filesystem limited |
| 43 | `files.download_folder_organizer` | Downloads Folder Organizer | filesystem | — | — | ❌ BLOCKED: filesystem only has open_folder |
| 44 | `files.drive_to_social` | Drive Asset → Processed → Publish Queue | filesystem, media | google_drive | — | ❌ BLOCKED: google_drive + media missing |
| 45 | `files.duplicate_detector` | Duplicate File Detector | filesystem, terminal | — | — | ⚠️ PARTIAL: terminal can hash, filesystem verify limited |
| 46 | `files.invoice_extract_to_sheet` | Invoice PDF → Structured Row in XLSX | ai_reasoning, workflow, terminal | llm, pdf_reader, openpyxl | openpyxl | ⚠️ PARTIAL: LLM extraction + openpyxl append possible |

### Media Category (1 template)

| # | Template ID | Name | Capabilities Required | Providers Required | Package Deps | TRUTH |
|---|-------------|------|----------------------|-------------------|--------------|-------|
| 47 | `media.content_repurpose` | Content Repurpose & Multi-Platform Publish | ai_reasoning, workflow, media | llm | — | ❌ BLOCKED: media provider missing (publish/transcode) |

### Monitoring Category (4 templates)

| # | Template ID | Name | Capabilities Required | Providers Required | Package Deps | TRUTH |
|---|-------------|------|----------------------|-------------------|--------------|-------|
| 48 | `monitoring.inbox_monitor` | Priority Inbox Monitor | ai_reasoning, communication | imap, llm | — | ❌ BLOCKED: imap provider missing |
| 49 | `monitoring.rss_news_monitor` | RSS / News Monitor & Digest | ai_reasoning, knowledge, communication, memory | llm | feedparser ❌ | ❌ BLOCKED: knowledge + feedparser missing |
| 50 | `monitoring.security_scan_alert` | URL/Email Security Scan & Alert | ai_reasoning, knowledge, communication | llm | — | ❌ BLOCKED: knowledge missing |
| 51 | `monitoring.website_uptime` | Website Uptime Monitor | knowledge, communication, memory | — | httpx | ❌ BLOCKED: knowledge missing |

### Productivity Category (7 templates)

| # | Template ID | Name | Capabilities Required | Providers Required | Package Deps | TRUTH |
|---|-------------|------|----------------------|-------------------|--------------|-------|
| 52 | `productivity.calendar_to_status` | Calendar Event → Status / Presence | communication | google_calendar | — | ❌ BLOCKED: google_calendar + Slack status missing |
| 53 | `productivity.ecosystem_briefing` | Google Ecosystem Daily Briefing | ai_reasoning, filesystem, communication | google_calendar, gmail, google_drive, llm | — | ❌ BLOCKED: google_* providers missing |
| 54 | `productivity.email_label_ai` | AI Inbox Auto-Labelling | ai_reasoning, communication | llm | — | ⚠️ PARTIAL: LLM classifies, but no email label API |
| 55 | `productivity.email_to_calendar` | Gmail → Calendar Event | ai_reasoning | gmail, google_calendar, llm | — | ❌ BLOCKED: gmail + google_calendar missing |
| 56 | `productivity.email_to_task` | Actionable Email → Task | ai_reasoning, mcp_tool | gmail, llm | — | ❌ BLOCKED: gmail + mcp_tool task store missing |
| 57 | `productivity.meeting_prep` | Meeting Prep Pack | ai_reasoning, communication, memory | google_calendar, gmail, llm | — | ❌ BLOCKED: google_calendar + gmail missing |
| 58 | `productivity.morning_briefing` | Morning Briefing | ai_reasoning, knowledge, communication, mcp_tool | llm | — | ❌ BLOCKED: knowledge + mcp_tool (tasks) missing |
| 59 | `productivity.weekly_review` | Weekly Review & Plan | ai_reasoning, communication, memory, terminal | llm, python_docx | python-docx | ⚠️ PARTIAL: LLM + python-docx possible, memory limited |

### Research Category (4 templates)

| # | Template ID | Name | Capabilities Required | Providers Required | Package Deps | TRUTH |
|---|-------------|------|----------------------|-------------------|--------------|-------|
| 60 | `research.competitor_monitor` | Competitor Monitor (weekly) | ai_reasoning, browser, communication, memory, terminal | playwright, llm, python_docx | playwright, python-docx | ❌ BLOCKED: browser only YouTube |
| 61 | `research.daily_brief` | Configurable Daily Research Brief | ai_reasoning, communication, memory | llm | — | ⚠️ PARTIAL: LLM research works, memory limited |
| 62 | `research.web_scrape_to_report` | Web Scrape → Synthesize → Report | ai_reasoning, browser, terminal | playwright, llm, python_docx | playwright, python-docx | ❌ BLOCKED: browser only YouTube |
| 63 | `research.youtube_summary` | YouTube/Video → AI Summary → Post | ai_reasoning, knowledge, communication, memory | llm | — | ⚠️ PARTIAL: LLM summarize possible, YouTube fetch limited |

---

## Summary by Status

### ✅ FULLY EXECUTABLE (2/63)
1. `data.json_transform` — Pure workflow, no external deps
2. `ai.classify_and_route` — LLM + workflow, both implemented
3. `ai.extract_to_structured` — Pure LLM, implemented

### ⚠️ PARTIALLY EXECUTABLE (22/63)
Templates where core LLM/reasoning works but some actions are limited:
- `ai.transcribe_summarize` — transcription works, communication limited
- `artifacts.data_to_xlsx` — openpyxl works, LibreOffice needed
- `artifacts.meeting_to_report` — python-docx works
- `artifacts.multiformat_report` — DOCX+PPTX work, PDF needs WeasyPrint
- `artifacts.research_to_docx` — python-docx works
- `artifacts.research_to_pptx` — python-pptx works
- `business.email_autoresponder_approval` — LLM drafts work, no email send
- `communication.chat_assistant` — LLM + Telegram work, memory limited
- `communication.escalation_alert` — Telegram works, multi-channel limited
- `communication.notify` — Telegram works
- `communication.voice_assistant` — transcription works, TTS missing
- `communication.workflow_failure_alert` — Telegram works
- `data.csv_pii_scrub` — LLM detection works, filesystem limited
- `data.file_extract_to_csv` — LLM extraction works
- `development.ci_failure_alert` — needs MCP github
- `development.dependency_monitor` — needs MCP github
- `development.github_issue_triage` — needs MCP github
- `development.pr_review_prep` — needs MCP github
- `development.release_changelog` — needs MCP github
- `development.repo_backup` — needs MCP github + cloud
- `development.repo_health_report` — needs MCP github
- `development.scaffold_project` — terminal works, vscode missing
- `files.document_summarize` — LLM works, filesystem limited
- `files.duplicate_detector` — terminal hash works
- `files.invoice_extract_to_sheet` — LLM + openpyxl work
- `productivity.email_label_ai` — LLM classifies, no email API
- `productivity.weekly_review` — LLM + python-docx work
- `research.daily_brief` — LLM works, memory limited
- `research.youtube_summary` — LLM works, YouTube fetch limited

### ❌ BLOCKED (39/63)
Templates where at least one critical capability has NO implementation:

**Blocked by `knowledge` capability (no vector store, no web fetch, no RSS):**
- `ai.enrich_records`
- `ai.rag_answer`
- `data.api_poll_to_store`
- `data.webhook_to_store`
- `monitoring.rss_news_monitor`
- `monitoring.security_scan_alert`
- `monitoring.website_uptime`
- `productivity.morning_briefing`
- `business.lead_intake_crm`

**Blocked by `browser` capability (only YouTube):**
- `browser.page_change_monitor`
- `browser.price_monitor`
- `browser.structured_extract`
- `research.competitor_monitor`
- `research.web_scrape_to_report`

**Blocked by `media` capability (contracts only):**
- `ai.image_generate`
- `files.drive_to_social`
- `media.content_repurpose`
- `communication.voice_assistant` (TTS part)

**Blocked by `calendar` capability (no Google Calendar):**
- `productivity.calendar_to_status`
- `productivity.ecosystem_briefing`
- `productivity.email_to_calendar`
- `productivity.meeting_prep`

**Blocked by `email` capability (no Gmail/IMAP):**
- `monitoring.inbox_monitor`
- `productivity.email_to_task`
- `productivity.email_to_calendar`

**Blocked by `mcp_tool` needing external servers (notion/airtable/linear):**
- `data.knowledge_base_sync`
- `data.record_sync`
- `data.form_intake`
- `business.crm_followup`
- `business.lead_intake_crm`
- `business.support_ticket_triage`
- `productivity.email_to_task`
- `productivity.morning_briefing`

**Blocked by missing providers:**
- `development.issue_to_implementation` — coding_agent provider
- `files.download_folder_organizer` — filesystem write actions
- `data.form_intake` — google_sheets provider

---

## Aggregated Capability Demand

| Capability | Templates Using It | Can KIO Satisfy? |
|------------|-------------------|------------------|
| `ai_reasoning` | 47/63 | ✅ YES (LLM Gateway) |
| `communication` | 35/63 | ⚠️ TELEGRAM ONLY |
| `filesystem` | 25/63 | ❌ 1 ACTION ONLY |
| `terminal` | 18/63 | ⚠️ SAFE-CMD WHITELIST |
| `memory` | 16/63 | ⚠️ PARTIAL |
| `workflow` | 10/63 | ✅ YES (WorkflowEngine) |
| `knowledge` | 12/63 | ❌ NOT IMPLEMENTED |
| `mcp_tool` | 10/63 | ⚠️ LOCAL SERVERS ONLY |
| `github` | 9/63 | ⚠️ NEEDS MCP GITHUB |
| `browser` | 8/63 | ❌ YOUTUBE ONLY |
| `media` | 5/63 | ❌ CONTRACTS ONLY |
| `calendar` | 4/63 | ❌ NOT IMPLEMENTED |
| `system` | 0/63 | ✅ YES (not used by templates) |
| `desktop` | 0/63 | ✅ YES (not used by templates) |

---

## Provider Gap Analysis

### Critical Missing Providers (block most templates)
1. **`knowledge`** — 12 templates blocked. Needs: web fetch (httpx), RSS (feedparser), vector search (chromadb or qdrant), HMAC verification
2. **`calendar`** — 4 templates blocked. Needs: Google Calendar API integration
3. **`email`** — 3 templates blocked. Needs: Gmail API or IMAP client
4. **`media`** — 5 templates blocked. Needs: image generation API, TTS, social media publishing
5. **`browser` (generic)** — 5 templates blocked. Needs: generic web scraping actions (not just YouTube)

### Partially Implemented (need more actions)
6. **`filesystem`** — 25 templates use it, only 1 action implemented. Needs: write, read, move, hash, verify, CSV operations
7. **`communication`** — 35 templates use it, Telegram only. Needs: Slack, Discord, email send
8. **`memory`** — 16 templates use it, partial. Needs: full KV store with diff, conversation history
9. **`mcp_tool`** — 10 templates use it, local servers only. Needs: notion, airtable, linear MCP servers

### External Service Dependencies (not providers, but needed)
10. **Google APIs** — Calendar, Gmail, Drive, Sheets (5+ templates)
11. **CRM APIs** — HubSpot, Salesforce, Airtable (3+ templates)
12. **Ticket APIs** — Linear, Jira, Notion (2+ templates)
13. **Social APIs** — LinkedIn, X, Instagram (1 template)
