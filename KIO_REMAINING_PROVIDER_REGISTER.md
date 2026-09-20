# KIO Remaining Provider Register

**Date:** 2026-09-18 (reconciled 2026-09-20)
**Purpose:** Deduplicated provider list with integration details

---

## Provider Categories

- **A. REQUIRED TO CLOSE CURRENT 63 WORKFLOWS** — must be integrated
- **B. REQUIRED BUT ALREADY AVAILABLE LOCALLY** — no new provider needed
- **C. REQUIRED EXTERNAL PROVIDERS** — need credential/config
- **D. OPTIONAL / FUTURE** — do NOT configure now
- **E. NOT ACTUALLY REQUIRED** — YAML references concept, not real call

---

## A. REQUIRED TO CLOSE CURRENT 63 WORKFLOWS

### 1. Gmail (email)

- **Workflows using it:**
  - productivity.email_to_task (classify actionable email)
  - productivity.email_label_ai (apply labels)
  - productivity.email_to_calendar (detect event from email)
  - business.email_autoresponder_approval (draft reply)
- **Required actions:** read_inbox, send_email, apply_label
- **Required API/scopes:** Gmail API (gmail.modify scope)
- **Authentication method:** OAuth2
- **Credential type:** google_oauth (existing client) + gmail.modify scope
- **Existing KIO capability:** `get_gmail_service()` in google_oauth.py — LIVE_VERIFIED
- **Existing MCP server:** None for email
- **Status:** LIVE_VERIFIED (read inbox, send, labels all verified 2026-09-20)
- **Exact blocker (inbox_monitor only):** The `monitoring.inbox_monitor.yaml` template uses wrong capability (communication/get_updates = Telegram, not email). The `email` capability (read_inbox, watch_inbox) is registered in step_runner but has NO handler in app_operator. Template needs refactoring to use Gmail API.
- **Note:** The 4 email-related templates above work through `ai_reasoning` + `communication` (Telegram delivery), NOT through an `email` capability. The `email` capability exists only in step_runner registration, not in app_operator execution.

### 2. Vector Store (for RAG)

- **Workflows using it:**
  - ai.rag_answer (vector_search)
- **Required actions:** vector_search, embed, store_vectors
- **Required API/scopes:** Vector DB API or local store
- **Authentication method:** API key or local
- **Credential type:** vectorstore_cred
- **Existing KIO capability:** None
- **Existing MCP server:** None
- **Status:** STILL_BLOCKED — no vector DB installed, KnowledgeProvider has no vector_search handler
- **Verification operation:** store embedding, query, retrieve
- **Free/local option:** Yes — ChromaDB (local, pip install chromadb)
- **Paid account required:** No (local option available)
- **Exact blocker:** No vector store configured, no vector_search handler in KnowledgeProvider

---

## B. REQUIRED BUT ALREADY AVAILABLE LOCALLY

These capabilities are fully satisfied by KIO's existing infrastructure. No new provider needed.

### 3. LLM Provider (ai_reasoning)

- **Workflows using it:** 48 of 63 templates
- **Required actions:** classify, summarize, extract, chat, compose, etc.
- **Existing KIO capability:** Gemini, Groq, OpenRouter, Together, Cerebras, Ollama
- **Status:** ALREADY_LIVE_VERIFIED
- **Next action:** None — already working

### 4. Telegram Bot (communication)

- **Workflows using it:** 25+ templates
- **Required actions:** send_message, send_alert, send_batch
- **Existing KIO capability:** @KIO_Runtime_bot
- **Status:** ALREADY_LIVE_VERIFIED
- **Next action:** None — already working

### 5. Google Calendar

- **Workflows using it:** 5 templates (ecosystem_briefing, email_to_calendar, meeting_prep, morning_briefing, calendar_to_status)
- **Required actions:** today_events, create_event, get_event
- **Existing KIO capability:** Google Calendar API (6 calendars)
- **Status:** ALREADY_LIVE_VERIFIED
- **Next action:** None — already working

### 6. Google Drive

- **Workflows using it:** 3 templates (repo_backup, drive_to_social, ecosystem_briefing)
- **Required actions:** upload_backup, verify_upload, recent_drive_changes
- **Existing KIO capability:** Google Drive API (100 files accessible)
- **Status:** ALREADY_LIVE_VERIFIED
- **Next action:** None — already working

### 7. GitHub API

- **Workflows using it:** 9 templates (all development/*)
- **Required actions:** list_issues, create_issue, get_pr_diff, scan_dependencies, etc.
- **Existing KIO capability:** GitHub MCP server + GITHUB_TOKEN
- **Status:** ALREADY_LIVE_VERIFIED
- **Next action:** None — already working

### 8. Notion

- **Workflows using it:** 1 template (knowledge_base_sync)
- **Required actions:** create_page, get_page
- **Existing KIO capability:** Bot KIO (3 pages, 24 blocks)
- **Status:** ALREADY_LIVE_VERIFIED
- **Next action:** None — already working

### 9. Todoist

- **Workflows using it:** 1 template (email_to_task via mcp_tool create_task)
- **Required actions:** create_task, due_tasks
- **Existing KIO capability:** Todoist API v1 (task CRUD verified)
- **Status:** ALREADY_LIVE_VERIFIED
- **Next action:** None — already working

### 10. Browser Runtime

- **Workflows using it:** 3 templates (browser/*)
- **Required actions:** monitor_page, extract_price, extract_records
- **Existing KIO capability:** BrowserRuntime/BrowserConnector
- **Status:** ALREADY_LIVE_VERIFIED
- **Next action:** None — already working

### 11. Knowledge Providers (Web Search)

- **Workflows using it:** 10+ templates
- **Required actions:** web_search, fetch_url, batch_lookup
- **Existing KIO capability:** Tavily, Exa, DuckDuckGo, Wikipedia, Jina Reader
- **Status:** ALREADY_LIVE_VERIFIED
- **Next action:** None — already working

### 12. FFmpeg

- **Workflows using it:** Media templates
- **Required actions:** transcode_variants
- **Existing KIO capability:** v8.1.2 verified
- **Status:** ALREADY_LIVE_VERIFIED
- **Next action:** None — already working

### 13. edge-tts

- **Workflows using it:** Communication/voice templates
- **Required actions:** text_to_speech
- **Existing KIO capability:** v7.2.8 verified
- **Status:** ALREADY_LIVE_VERIFIED
- **Next action:** None — already working

### 14. Local Store (CRM/Tasks/Tickets)

- **Workflows using it:** 4 templates (business/*)
- **Required actions:** crm_upsert, crm_get, find_stale_leads, upsert_ticket
- **Existing KIO capability:** local_store.py (task/CRM/ticket CRUD)
- **Status:** LOCAL_CAPABILITY
- **Next action:** None — already working

### 15. File Operator

- **Workflows using it:** 20+ templates
- **Required actions:** write_csv, read_file, move_file, hash_tree, etc.
- **Existing KIO capability:** file_operator.py
- **Status:** LOCAL_CAPABILITY
- **Next action:** None — already working

### 16. Terminal Provider

- **Workflows using it:** 8 templates
- **Required actions:** run_command, scaffold, git_init, render_*
- **Existing KIO capability:** terminal_provider.py
- **Status:** LOCAL_CAPABILITY
- **Next action:** None — already working

### 17. Memory Ops

- **Workflows using it:** 12 templates
- **Required actions:** store, retrieve, diff_snapshots, exclude_recently_contacted
- **Existing KIO capability:** memory_ops.py
- **Status:** LOCAL_CAPABILITY
- **Next action:** None — already working

### 18. Artifact Operator

- **Workflows using it:** 8 templates
- **Required actions:** generate_pdf, generate_docx, generate_pptx, generate_xlsx
- **Existing KIO capability:** artifact_operator.py (openpyxl, python-docx, python-pptx, weasyprint)
- **Status:** LOCAL_CAPABILITY
- **Next action:** None — already working

### 19. Execution Engine

- **Workflows using it:** 10+ templates
- **Required actions:** route, request_approval, conditional_branch
- **Existing KIO capability:** execution engine
- **Status:** LOCAL_CAPABILITY
- **Next action:** None — already working

---

## C. REQUIRED EXTERNAL PROVIDERS

After re-audit (2026-09-20), the actual remaining blockers are:

| # | Provider | Workflows | Free? | Status |
|---|----------|-----------|-------|--------|
| 1 | Gmail API | 4 templates (email_to_task, email_label_ai, email_to_calendar, email_autoresponder) | Yes | **LIVE_VERIFIED** — scope gmail.modify authorized. inbox_monitor needs YAML refactor (uses Telegram instead of Gmail). |
| 2 | Vector Store | 1 template (ai.rag_answer) | Yes (local) | **STILL_BLOCKED** — no vector DB installed, no vector_search handler |
| 3 | Social Media Publisher | 1 template (media.content_repurpose) | Depends on platform | **STILL_BLOCKED** — no Twitter/LinkedIn/Instagram adapter exists |

---

## D. OPTIONAL / FUTURE

Do NOT configure these now:

| Provider | Workflows | Reason |
|----------|-----------|--------|
| Slack/Discord/WhatsApp | 0 templates | NOT referenced by any YAML template |
| Dropbox/OneDrive | 0 templates | NOT referenced by any YAML template |
| CRM (Salesforce/HubSpot) | 0 templates | local_store handles CRM; no external CRM referenced |
| Ticketing (Jira/Linear) | 0 templates | local_store handles tickets; no external ticketing referenced |

---

## E. NOT ACTUALLY REQUIRED

These credential names appear in YAML but are satisfied by existing providers:

| Credential Name | Actually Maps To | Satisfied By |
|----------------|------------------|--------------|
| llm_provider | LLM API key | Gemini/Groq/OpenRouter (already live) |
| channel_cred | Telegram bot token | @KIO_Runtime_bot (already live) |
| github_token | GitHub PAT | GITHUB_TOKEN in .env (already live) |
| google_oauth | Google OAuth token | Existing CredentialVault (already live) |
| drive_cred | Google Drive access | Same Google OAuth (already live) |
| calendar_cred | Google Calendar access | Same Google OAuth (already live) |
| crm_cred | Local CRM store | local_store.py (built-in) |
| tracker_cred | Local ticket store | local_store.py (built-in) |
| mail_cred | Email send capability | Gmail API (already live) — but inbox_monitor YAML still references IMAP |
| kb_cred | Notion access | Notion bot KIO (already live) |
| notify_cred | Notification channel | Telegram bot (already live) |
| approval_cred | Approval workflow | Execution engine (built-in) |
| webhook_secret | HMAC verification | Execution engine (built-in) |
| api_cred | HTTP client | urllib (built-in) |
| image_provider | Image generation | KIO Media generate_image (already live) |
| vectorstore_cred | Vector DB | NOT YET SATISFIED — see category C |
| platform_creds | Social media publish/verify | NOT YET SATISFIED — no social media adapters exist |
