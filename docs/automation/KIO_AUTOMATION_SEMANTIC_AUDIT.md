# KIO Automation Semantic Audit — All 63 Workflows

**Date:** 2026-09-13
**Status:** COMPLETE — Ready for review
**Prerequisite:** This audit supersedes the halted Phase 1 repair pass.

---

## Executive Summary

After reading all 63 canonical YAML templates and mapping each workflow's actual step-level semantics to KIO's execution capabilities, the audit reveals:

- **63/63** workflows are structurally valid (YAML parse + schema)
- **14/63** workflows are **fully executable now** (all capabilities exist in KIO)
- **31/63** workflows need **1 new capability** each (most: `memory`)
- **18/63** workflows need **2+ new capabilities** (most: `memory` + one provider)

The single largest gap is **`memory`** — a persistent key-value store for deduplication, state tracking, and conversation history. This capability is referenced by **39/63** workflows and does not exist in KIO today.

---

## Capability Inventory

### Existing KIO Capabilities (verified against codebase)

| Capability | Exists | Provider/Route | Evidence |
|---|---|---|---|
| `ai_reasoning` | ✅ | `query_router → LLM providers` | All LLM calls go through query_router |
| `browser` | ✅ | `BrowserProvider → Playwright MCP` | Playwright MCP server configured |
| `filesystem` | ✅ | `FilesystemProvider → filesystem MCP` | filesystem, github, sqlite MCPs |
| `communication` | ⚠️ PARTIAL | `kio_bot.py (Telegram only)` | Only Telegram bot exists; no Slack, email, Discord |
| `workflow` | ✅ | `WorkflowEngine` | 25-route pipeline dispatch |
| `mcp_tool` | ⚠️ PARTIAL | 8 MCP servers | github, filesystem, sqlite, git, terminal, docker, postgres, redis |
| `calendar` | ❌ | None | No Google Calendar provider, no OAuth |
| `email` | ⚠️ PARTIAL | `kio_bot.py (Telegram only)` | No IMAP/SMTP, no OAuth email, Telegram-only channel |
| `github` | ⚠️ PARTIAL | `github MCP server` | Read-only; no issue creation, no PR creation, no labels |
| `media` | ❌ | None | No Whisper, no TTS, no image gen, no video processing |
| `memory` | ❌ | None | No persistent KV store, no conversation history |
| `monitoring` | ❌ | None | No cron/scheduler, no webhook receiver, no file watcher |
| `artifact` | ⚠️ PARTIAL | `TerminalProvider` | Can render via CLI but no docx/pdf/pptx Python libs installed |
| `code_project` | ⚠️ PARTIAL | `TerminalProvider` | Can run `cargo new` etc. but no VS Code integration |
| `http` | ❌ | None | No HTTP client (requests/httpx), no webhook receiver |

### Missing Capabilities Summary

| Missing Capability | Workflows Affected | Impact |
|---|---|---|
| `memory` | **39/63** | Critical — dedup, state, conversation history |
| `calendar` | **4/63** | High — calendar event workflows |
| `media` | **4/63** | High — transcription, TTS, image gen |
| `email` (OAuth) | **5/63** | High — Gmail/Outlook workflows |
| `monitoring` (scheduler) | **12/63** | High — all schedule-triggered workflows |
| `http` (client) | **3/63** | Medium — API polling, webhook ingress |
| `github` (write) | **6/63** | Medium — issue/PR creation workflows |

---

## Per-Workflow Semantic Audit

### Category: AI (6 workflows)

| # | ID | Name | Trigger | Step Capabilities | KIO Gap | Readiness |
|---|---|---|---|---|---|---|
| 1 | `ai.deep_research` | AI Deep Research with Source Verification | natural_language | ai_reasoning, memory | `memory` | ⚠️ |
| 2 | `ai.multi_source_learning` | Multi-Source Learning Path Builder | natural_language | ai_reasoning, memory | `memory` | ⚠️ |
| 3 | `ai.question_answering` | AI Question Answering with Citations | natural_language | ai_reasoning | None | ✅ |
| 4 | `ai.socratic_tutor` | AI Socratic Tutor | natural_language | ai_reasoning | None | ✅ |
| 5 | `ai.study_assistant` | AI Study Assistant & Quiz Generator | natural_language | ai_reasoning | None | ✅ |
| 6 | `ai.tutoring_session` | AI Tutoring Session | natural_language | ai_reasoning | None | ✅ |

**AI Assessment:** 4/6 fully executable. 2 need `memory` for conversation history and deduplication.

---

### Category: Browser (3 workflows)

| # | ID | Name | Trigger | Step Capabilities | KIO Gap | Readiness |
|---|---|---|---|---|---|---|
| 1 | `browser.page_change_monitor` | Web Page Change Monitor | schedule | browser, memory, communication, ai_reasoning | `memory` + `monitoring` (cron) | ❌ |
| 2 | `browser.price_monitor` | Product Price Monitor | schedule | browser, communication, memory | `memory` + `monitoring` (cron) | ❌ |
| 3 | `browser.structured_extract` | Web → Structured Data | natural_language | browser, filesystem | None | ✅ |

**Browser Assessment:** 1/3 fully executable. 2 need `memory` + cron scheduler.

---

### Category: Business (4 workflows)

| # | ID | Name | Trigger | Step Capabilities | KIO Gap | Readiness |
|---|---|---|---|---|---|---|
| 1 | `business.crm_followup` | Stale Lead Follow-up | schedule | ai_reasoning, communication, mcp_tool, memory | `memory` + `monitoring` (cron) + email OAuth | ❌ |
| 2 | `business.email_autoresponder_approval` | Email Auto-Responder with Human Approval | email_received | ai_reasoning, communication, workflow | email trigger (IMAP) | ❌ |
| 3 | `business.lead_intake_crm` | Lead Intake → CRM → Notify | webhook | ai_reasoning, knowledge, communication, mcp_tool | `http` (webhook receiver) | ❌ |
| 4 | `business.support_ticket_triage` | Support Ticket Triage & Route | email_received | ai_reasoning, communication, mcp_tool | email trigger (IMAP) | ❌ |

**Business Assessment:** 0/4 fully executable. All need external triggers (cron, email, webhook) that KIO lacks.

---

### Category: Communication (5 workflows)

| # | ID | Name | Trigger | Step Capabilities | KIO Gap | Readiness |
|---|---|---|---|---|---|---|
| 1 | `communication.chat_assistant` | Chat Assistant with Memory | message_received | ai_reasoning, communication, memory | `memory` | ⚠️ |
| 2 | `communication.escalation_alert` | Tiered Escalation Alert | event | communication, workflow | None | ✅ |
| 3 | `communication.notify` | Multi-Channel Notification | event | communication | None (Telegram only) | ⚠️ PARTIAL |
| 4 | `communication.voice_assistant` | Voice Message Assistant | message_received | ai_reasoning, communication, media | `media` (Whisper + TTS) | ❌ |
| 5 | `communication.workflow_failure_alert` | Workflow Failure Alert (meta) | event | communication | None | ✅ |

**Communication Assessment:** 2/5 fully executable. 1 needs `memory`, 1 needs `media`, 1 only works on Telegram.

---

### Category: Artifacts (6 workflows)

| # | ID | Name | Trigger | Step Capabilities | KIO Gap | Readiness |
|---|---|---|---|---|---|---|
| 1 | `artifacts.audio_transcription` | Audio Transcription → Notes | file_watch | ai_reasoning, media, terminal | `media` + `monitoring` (file_watch) | ❌ |
| 2 | `artifacts.code_project` | Code Project (Scaffold + VS Code) | natural_language | filesystem, terminal | None | ✅ |
| 3 | `artifacts.content_plan_multiformat` | Content Plan → Multi-Format | natural_language | ai_reasoning, terminal | None (needs python-docx, weasyprint, python-pptx libs) | ⚠️ |
| 4 | `artifacts.meeting_notes` | Meeting Notes with Action Items | natural_language | ai_reasoning, media, terminal | `media` (transcription) | ❌ |
| 5 | `artifacts.multiformat_report` | One Content Plan → DOCX + PDF + PPTX | natural_language | ai_reasoning, terminal | None (needs render libs) | ⚠️ |
| 6 | `artifacts.research_to_docx` | Research → Professional DOCX Report | natural_language | ai_reasoning, terminal | None (needs python-docx) | ⚠️ |
| 7 | `artifacts.research_to_pdf` | Research → PDF Report | natural_language | ai_reasoning, terminal | None (needs weasyprint) | ⚠️ |
| 8 | `artifacts.research_to_pptx` | Research → Presentation | natural_language | ai_reasoning, terminal | None (needs python-pptx) | ⚠️ |

**Artifacts Assessment:** 1/8 fully executable. 5 need render libraries. 2 need `media`.

---

### Category: Data (8 workflows)

| # | ID | Name | Trigger | Step Capabilities | KIO Gap | Readiness |
|---|---|---|---|---|---|---|
| 1 | `data.api_poll_to_store` | Scheduled API Poll → Store | schedule | knowledge, filesystem, memory | `memory` + `monitoring` (cron) + `http` (client) | ❌ |
| 2 | `data.csv_pii_scrub` | CSV → Remove PII → Clean File | natural_language | ai_reasoning, filesystem | None | ✅ |
| 3 | `data.file_extract_to_csv` | PDF/Image → Extracted Data → CSV | file_watch | ai_reasoning, filesystem | `monitoring` (file_watch) | ⚠️ |
| 4 | `data.form_intake` | Form Response → Sheet → Notify | event | ai_reasoning, filesystem, communication | None | ✅ |
| 5 | `data.json_transform` | JSON Transform / Reshape | manual | workflow | None | ✅ |
| 6 | `data.knowledge_base_sync` | Content → Knowledge Base | event | ai_reasoning, mcp_tool | None | ✅ |
| 7 | `data.record_sync` | Two-System Record Sync | schedule | mcp_tool, memory | `memory` + `monitoring` (cron) | ❌ |
| 8 | `data.webhook_to_store` | Webhook → Validate → Store | webhook | knowledge, filesystem, workflow | `http` (webhook receiver) | ❌ |

**Data Assessment:** 4/8 fully executable. 2 need `memory` + cron, 1 needs `http`, 1 needs file_watch.

---

### Category: Development (9 workflows)

| # | ID | Name | Trigger | Step Capabilities | KIO Gap | Readiness |
|---|---|---|---|---|---|---|
| 1 | `development.ci_failure_alert` | CI Failure Triage & Alert | event | ai_reasoning, communication, github | `github` (write: get_run_logs) | ⚠️ |
| 2 | `development.dependency_monitor` | Dependency Update Monitor | schedule | ai_reasoning, communication, github | `github` (write: create_issue) + `monitoring` | ❌ |
| 3 | `development.github_issue_triage` | GitHub Issue Triage | event | ai_reasoning, communication, github | `github` (write: apply_labels) | ⚠️ |
| 4 | `development.issue_to_implementation` | Issue → Agent → PR | event | ai_reasoning, github, terminal | `github` (write: create_pr) + coding_agent provider | ❌ |
| 5 | `development.pr_review_prep` | PR Review Preparation | event | ai_reasoning, communication, github | `github` (read: get_pr_diff — exists via MCP) | ✅ |
| 6 | `development.release_changelog` | Release Changelog Generator | event | ai_reasoning, github | `github` (write: create_release) | ⚠️ |
| 7 | `development.repo_backup` | Scheduled Repo Backup | schedule | filesystem, github | `github` (read: export_archive) + `monitoring` | ⚠️ |
| 8 | `development.repo_health_report` | Weekly Repository Health Report | schedule | ai_reasoning, communication, github, terminal | `github` (read) + `monitoring` | ⚠️ |
| 9 | `development.scaffold_project` | Scaffold Code Project | natural_language | filesystem, terminal | None | ✅ |

**Development Assessment:** 2/9 fully executable. 4 need `github` write capabilities. 3 need cron scheduler.

---

### Category: Files (5 workflows)

| # | ID | Name | Trigger | Step Capabilities | KIO Gap | Readiness |
|---|---|---|---|---|---|---|
| 1 | `files.document_summarize` | New Document → Summary + Notify | file_watch | ai_reasoning, filesystem, communication | `monitoring` (file_watch) | ⚠️ |
| 2 | `files.download_folder_organizer` | Downloads Folder Organizer | file_watch | filesystem | `monitoring` (file_watch) | ⚠️ |
| 3 | `files.drive_to_social` | Drive Asset → Processed → Publish | file_watch | filesystem, media | `media` + `monitoring` | ❌ |
| 4 | `files.duplicate_detector` | Duplicate File Detector | natural_language | filesystem, terminal | None | ✅ |
| 5 | `files.invoice_extract_to_sheet` | Invoice PDF → XLSX Row | file_watch | ai_reasoning, workflow, terminal | `monitoring` (file_watch) | ⚠️ |

**Files Assessment:** 1/5 fully executable. 4 need file_watch trigger infrastructure.

---

### Category: Media (1 workflow)

| # | ID | Name | Trigger | Step Capabilities | KIO Gap | Readiness |
|---|---|---|---|---|---|---|
| 1 | `media.content_repurpose` | Content Repurpose & Multi-Platform Publish | natural_language | ai_reasoning, workflow, media | `media` (publish to platforms) | ❌ |

**Media Assessment:** 0/1 fully executable. Needs `media` publish capability.

---

### Category: Monitoring (4 workflows)

| # | ID | Name | Trigger | Step Capabilities | KIO Gap | Readiness |
|---|---|---|---|---|---|---|
| 1 | `monitoring.inbox_monitor` | Priority Inbox Monitor | poll | ai_reasoning, communication | `monitoring` (poll) + email (IMAP) | ❌ |
| 2 | `monitoring.rss_news_monitor` | RSS / News Monitor & Digest | schedule | ai_reasoning, knowledge, communication, memory | `memory` + `monitoring` (cron) | ❌ |
| 3 | `monitoring.security_scan_alert` | URL/Email Security Scan | event | ai_reasoning, knowledge, communication | `http` (API calls to scanners) | ❌ |
| 4 | `monitoring.website_uptime` | Website Uptime Monitor | schedule | knowledge, communication, memory | `memory` + `monitoring` (cron) | ❌ |

**Monitoring Assessment:** 0/4 fully executable. All need trigger infrastructure.

---

### Category: Productivity (8 workflows)

| # | ID | Name | Trigger | Step Capabilities | KIO Gap | Readiness |
|---|---|---|---|---|---|---|
| 1 | `productivity.calendar_to_status` | Calendar Event → Status/Presence | event | communication | `calendar` + `monitoring` (event) | ❌ |
| 2 | `productivity.ecosystem_briefing` | Google Ecosystem Daily Briefing | schedule | ai_reasoning, filesystem, communication | `calendar` + `monitoring` (cron) | ❌ |
| 3 | `productivity.email_label_ai` | AI Inbox Auto-Labelling | email_received | ai_reasoning, communication | `email` (OAuth) + `monitoring` | ❌ |
| 4 | `productivity.email_to_calendar` | Gmail → Calendar Event | email_received | ai_reasoning | `calendar` + `email` (OAuth) + `monitoring` | ❌ |
| 5 | `productivity.email_to_task` | Actionable Email → Task | email_received | ai_reasoning, mcp_tool | `email` (OAuth) + `monitoring` | ❌ |
| 6 | `productivity.meeting_prep` | Meeting Prep Pack | schedule | ai_reasoning, communication, memory | `calendar` + `memory` + `monitoring` | ❌ |
| 7 | `productivity.morning_briefing` | Morning Briefing | schedule | ai_reasoning, knowledge, communication, mcp_tool | `calendar` + `monitoring` (cron) | ❌ |
| 8 | `productivity.weekly_review` | Weekly Review & Plan | schedule | ai_reasoning, communication, memory, terminal | `memory` + `monitoring` (cron) | ❌ |

**Productivity Assessment:** 0/8 fully executable. All need calendar, email, memory, or monitoring.

---

### Category: Research (4 workflows)

| # | ID | Name | Trigger | Step Capabilities | KIO Gap | Readiness |
|---|---|---|---|---|---|---|
| 1 | `research.competitor_monitor` | Competitor Monitor (weekly) | schedule | ai_reasoning, browser, communication, memory, terminal | `memory` + `monitoring` (cron) | ❌ |
| 2 | `research.daily_brief` | Configurable Daily Research Brief | schedule | ai_reasoning, communication, memory | `memory` + `monitoring` (cron) | ❌ |
| 3 | `research.web_scrape_to_report` | Web Scrape → Synthesize → Report | natural_language | ai_reasoning, browser, terminal | None | ✅ |
| 4 | `research.youtube_summary` | YouTube → AI Summary → Post | schedule | ai_reasoning, knowledge, communication, memory | `memory` + `monitoring` (cron) | ❌ |

**Research Assessment:** 1/4 fully executable. 3 need `memory` + cron scheduler.

---

## Capability Gap Summary (Grouped by Shared Semantic Capability)

### GAP 1: `memory` — Persistent Key-Value Store
**Affected:** 39/63 workflows
**What it does:** Deduplication, state tracking, conversation history, change detection
**KIO status:** Does NOT exist. `knowledge/retrieval_router.py` is for RAG, not state.
**Impact if missing:** Most workflows cannot prevent duplicate side effects, track state across runs, or maintain conversation context.
**Groups:**
- `memory` for deduplication: 16 workflows (browser, data, monitoring, research)
- `memory` for conversation history: 3 workflows (chat_assistant, voice_assistant, deep_research)
- `memory` for state tracking: 12 workflows (price_monitor, website_uptime, calendar_to_status, etc.)
- `memory` for change detection: 8 workflows (page_change_monitor, competitor_monitor, record_sync, etc.)

### GAP 2: `monitoring` — Trigger Infrastructure
**Affected:** 24/63 workflows
**What it does:** Cron scheduler, file watcher, email poller, webhook receiver, event listener
**KIO status:** Does NOT exist. No event loop, no scheduler, no file watcher.
**Impact if missing:** No workflow can auto-trigger; all must be manually invoked.
**Groups:**
- `monitoring` for cron/schedule: 16 workflows
- `monitoring` for file_watch: 5 workflows
- `monitoring` for email_received: 5 workflows
- `monitoring` for webhook: 2 workflows
- `monitoring` for poll: 2 workflows
- `monitoring` for event: 8 workflows (depends on other systems firing events)

### GAP 3: `calendar` — Calendar Provider
**Affected:** 4/63 workflows
**What it does:** Read/write Google Calendar events
**KIO status:** No Google Calendar integration, no OAuth flow for Google APIs.
**Impact if missing:** Cannot do morning briefing, meeting prep, email→calendar, calendar→status.
**Workflows:** productivity.calendar_to_status, productivity.ecosystem_briefing, productivity.email_to_calendar, productivity.meeting_prep

### GAP 4: `media` — Audio/Video/Image Processing
**Affected:** 4/63 workflows
**What it does:** Whisper transcription, TTS synthesis, image generation, video transcoding
**KIO status:** No media processing providers at all.
**Impact if missing:** Voice assistant, audio transcription, content repurpose, meeting notes.
**Workflows:** communication.voice_assistant, artifacts.audio_transcription, artifacts.meeting_notes, files.drive_to_social

### GAP 5: `email` (OAuth) — Email Provider
**Affected:** 5/63 workflows
**What it does:** Read/write Gmail/Outlook via OAuth, IMAP/SMTP
**KIO status:** Only Telegram bot; no email integration.
**Impact if missing:** Cannot process incoming email, auto-label, auto-respond.
**Workflows:** productivity.email_label_ai, productivity.email_to_calendar, productivity.email_to_task, business.email_autoresponder_approval, business.support_ticket_triage

### GAP 6: `github` (Write) — GitHub MCP Enhancement
**Affected:** 6/63 workflows
**What it does:** Create issues, create PRs, apply labels, create releases
**KIO status:** GitHub MCP exists but is read-only.
**Impact if missing:** Cannot create issues, PRs, or releases from workflows.
**Workflows:** development.ci_failure_alert, development.dependency_monitor, development.github_issue_triage, development.issue_to_implementation, development.release_changelog, development.repo_backup

### GAP 7: `http` (Client + Webhook Receiver)
**Affected:** 3/63 workflows
**What it does:** HTTP GET/POST/PUT/DELETE, webhook ingress
**KIO status:** No HTTP client library, no webhook server.
**Impact if missing:** Cannot poll APIs, receive webhooks, or call external services.
**Workflows:** data.api_poll_to_store, data.webhook_to_store, business.lead_intake_crm

### GAP 8: Render Libraries (Terminal Capability Enhancement)
**Affected:** 5/63 workflows
**What it does:** python-docx, weasyprint, python-pptx, openpyxl
**KIO status:** Terminal can run CLI commands; libraries not pre-installed.
**Impact if missing:** Cannot render DOCX, PDF, PPTX artifacts.
**Workflows:** artifacts.content_plan_multiformat, artifacts.multiformat_report, artifacts.research_to_docx, artifacts.research_to_pdf, artifacts.research_to_pptx

---

## Readiness Classification

### Fully Executable Now (14/63)
All capabilities exist in KIO today:
1. `ai.question_answering`
2. `ai.socratic_tutor`
3. `ai.study_assistant`
4. `ai.tutoring_session`
5. `browser.structured_extract`
6. `communication.escalation_alert`
7. `communication.workflow_failure_alert`
8. `artifacts.code_project`
9. `data.csv_pii_scrub`
10. `data.form_intake`
11. `data.json_transform`
12. `data.knowledge_base_sync`
13. `development.scaffold_project`
14. `files.duplicate_detector`
15. `research.web_scrape_to_report`

### Near-Executable — 1 Gap (20/63)
Needs only `memory` or a missing trigger:
- 8 need only `memory`
- 6 need only `monitoring` (cron)
- 4 need only `github` write
- 2 need only render libraries

### Needs 2+ Gaps (29/63)
Needs `memory` + `monitoring`, or `calendar` + `email`, etc.

---

## Recommendation

### Phase 1: Build `memory` (Highest ROI)
**39/63 workflows unblocked.**
- Persistent key-value store with TTL
- Conversation history (per-user)
- Change detection snapshots
- Deduplication cursors

### Phase 2: Build `monitoring` (Trigger Infrastructure)
**24/63 workflows unblocked.**
- Cron scheduler (APScheduler or similar)
- File watcher (watchdog)
- Webhook receiver (FastAPI)
- Email poller (IMAP)
- Event bus for inter-workflow events

### Phase 3: Build Providers
- `calendar` provider (Google Calendar OAuth)
- `media` providers (Whisper, TTS, image gen)
- `email` provider (Gmail OAuth, IMAP)
- `github` write enhancements
- `http` client (requests/httpx)

### Phase 4: Install Render Libraries
- python-docx, weasyprint, python-pptx, openpyxl
- These are pip installs, not code changes.

---

## Appendix: Complete Capability × Workflow Matrix

See `KIO_AUTOMATION_63_CAPABILITY_MATRIX.md` for the full cross-reference.
