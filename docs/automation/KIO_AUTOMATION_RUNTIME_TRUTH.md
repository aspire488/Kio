# KIO Automation — Runtime Truth

> **Date:** 2026-09-13
> **Principle:** Every "available" claim needs source evidence, provider registration evidence, capability probe, or live execution. Every "unavailable" must have concrete reason.

---

## Executive Summary

| Metric | Count | Percentage |
|--------|-------|------------|
| Total templates | 63 | 100% |
| ✅ Fully executable | 3 | 5% |
| ⚠️ Partially executable | 22 | 35% |
| ❌ Blocked | 38 | 60% |

**The "48 executable / 0 blocked" claim is NOT authoritative.** The truthful count is 3 fully executable, 22 partially executable, 38 blocked.

---

## What Actually Works (3 templates)

### 1. `data.json_transform` — ✅ EXECUTABLE
- **Path:** Pure workflow actions (transform_records, verify_shape)
- **Provider:** WorkflowProvider → WorkflowEngine
- **Dependencies:** None external
- **Evidence:** Live test reached StepRunner and ExecutionBoundary (domain error on invalid input = expected)
- **Risk:** None — pure internal logic

### 2. `ai.classify_and_route` — ✅ EXECUTABLE
- **Path:** LLM classification → workflow routing
- **Provider:** LLM Gateway + WorkflowProvider
- **Dependencies:** LLM API key (Gemini/Groq/etc.)
- **Evidence:** LLM Gateway functional, WorkflowEngine functional
- **Risk:** LLM API availability

### 3. `ai.extract_to_structured` — ✅ EXECUTABLE
- **Path:** Pure LLM extraction
- **Provider:** LLM Gateway
- **Dependencies:** LLM API key
- **Evidence:** LLM Gateway functional
- **Risk:** LLM API availability

---

## What Partially Works (22 templates)

These templates have a working core but some actions are limited or missing.

### Tier 1: LLM + python-docx (artifacts, reports)
| Template | Working | Limited |
|----------|---------|---------|
| `artifacts.meeting_to_report` | LLM writes, python-docx renders | LibreOffice for PDF |
| `artifacts.research_to_docx` | LLM research + python-docx render | PDF export |
| `artifacts.research_to_pptx` | python-pptx present | LibreOffice for rasterize |
| `artifacts.data_to_xlsx` | openpyxl present | LibreOffice for recalc |
| `artifacts.multiformat_report` | DOCX + PPTX | PDF needs WeasyPrint |
| `development.repo_health_report` | LLM + python-docx | Needs MCP github |
| `productivity.weekly_review` | LLM + python-docx | Memory limited |

**Total: 7 templates** — core works, export formatting limited

### Tier 2: LLM + Telegram (communication)
| Template | Working | Limited |
|----------|---------|---------|
| `communication.notify` | Telegram send | No Slack/Discord/email |
| `communication.escalation_alert` | Telegram send | No multi-channel |
| `communication.workflow_failure_alert` | Telegram send | Telegram only |
| `communication.chat_assistant` | LLM + Telegram | Memory limited |
| `communication.voice_assistant` | Transcription works | TTS missing |

**Total: 5 templates** — Telegram works, multi-channel doesn't

### Tier 3: LLM + MCP GitHub (development)
| Template | Working | Limited |
|----------|---------|---------|
| `development.ci_failure_alert` | LLM triage | Needs MCP github |
| `development.dependency_monitor` | LLM analysis | Needs MCP github |
| `development.github_issue_triage` | LLM triage | Needs MCP github |
| `development.pr_review_prep` | LLM analysis | Needs MCP github |
| `development.release_changelog` | LLM generation | Needs MCP github |

**Total: 5 templates** — LLM works, GitHub integration needs MCP server

### Tier 4: LLM + filesystem (data, files)
| Template | Working | Limited |
|----------|---------|---------|
| `data.csv_pii_scrub` | LLM detects PII | Filesystem write limited |
| `data.file_extract_to_csv` | LLM extraction | Filesystem write limited |
| `files.document_summarize` | LLM summarize | Filesystem read limited |
| `files.invoice_extract_to_sheet` | LLM + openpyxl | Verify limited |

**Total: 4 templates** — LLM works, filesystem actions limited

### Tier 5: LLM only (research, productivity)
| Template | Working | Limited |
|----------|---------|---------|
| `research.daily_brief` | LLM research | Memory limited |
| `research.youtube_summary` | LLM summarize | YouTube fetch limited |
| `productivity.email_label_ai` | LLM classifies | No email API |
| `business.email_autoresponder_approval` | LLM drafts | No email send |
| `development.scaffold_project` | Terminal scaffold | VS Code missing |
| `files.duplicate_detector` | Terminal hash | Verify limited |

**Total: 6 templates** — LLM works, integration points limited

---

## What's Blocked (38 templates)

### Block Group 1: `knowledge` capability (12 templates)
**Root cause:** No web fetch framework, no RSS parser, no vector store, no HMAC verification
**Available:** httpx (installed), feedparser (NOT installed), chromadb (NOT installed), beautifulsoup4 (NOT installed)
**Required components:**
- Web fetch wrapper (httpx-based)
- RSS feed reader (feedparser)
- HMAC signature verification (stdlib hashlib)
- Vector search (chromadb or qdrant-client)
- HTML parsing (beautifulsoup4)

**Blocked templates:**
1. `ai.enrich_records` — needs web fetch for enrichment
2. `ai.rag_answer` — needs vector search
3. `data.api_poll_to_store` — needs HTTP polling
4. `data.webhook_to_store` — needs webhook validation
5. `monitoring.rss_news_monitor` — needs RSS parsing
6. `monitoring.security_scan_alert` — needs URL scanning
7. `monitoring.website_uptime` — needs HTTP health checks
8. `productivity.morning_briefing` — needs news aggregation
9. `business.lead_intake_crm` — needs lead validation
10. `business.crm_followup` — needs CRM data fetch
11. `business.support_ticket_triage` — needs ticket data fetch
12. `business.email_autoresponder_approval` (partially blocked)

### Block Group 2: `browser` generic scraping (5 templates)
**Root cause:** BrowserProvider only has YouTube + DOM interaction, no generic extract/screenshot/PDF
**Required:** Generic web scraping actions (extract_records, extract_price, crawl_extract, screenshot, PDF)
**Available:** Playwright (installed), browser_operator (partial)
**Blocked templates:**
1. `browser.page_change_monitor` — needs snapshot_sources + diff
2. `browser.price_monitor` — needs extract_price + diff
3. `browser.structured_extract` — needs extract_records
4. `research.competitor_monitor` — needs generic scraping
5. `research.web_scrape_to_report` — needs generic scraping

### Block Group 3: `calendar` capability (4 templates)
**Root cause:** No Google Calendar integration
**Available:** google-api-python-client (installed), no OAuth2 flow
**Required:** Google Calendar API wrapper + OAuth2 credentials
**Blocked templates:**
1. `productivity.calendar_to_status` — needs today_events
2. `productivity.ecosystem_briefing` — needs calendar + drive + gmail
3. `productivity.email_to_calendar` — needs gmail + calendar
4. `productivity.meeting_prep` — needs calendar + gmail

### Block Group 4: `email` capability (3 templates)
**Root cause:** No Gmail/IMAP integration
**Available:** google-api-python-client (installed), imaplib (stdlib), no OAuth2 flow
**Required:** Gmail API wrapper or IMAP client + credentials
**Blocked templates:**
1. `monitoring.inbox_monitor` — needs inbox scan
2. `productivity.email_to_task` — needs gmail + task API
3. `productivity.email_to_calendar` — (also in calendar group)

### Block Group 5: `media` capability (5 templates)
**Root cause:** media_contract.py is type definitions only, zero implementation
**Required:** Image generation API, TTS engine, social media publishing, transcoding
**Blocked templates:**
1. `ai.image_generate` — needs image generation API
2. `files.drive_to_social` — needs asset publishing
3. `media.content_repurpose` — needs multi-platform publish
4. `communication.voice_assistant` (TTS part) — needs TTS engine
5. `research.competitor_monitor` (screenshot part) — needs screenshot capture

### Block Group 6: `mcp_tool` external servers (8 templates)
**Root cause:** No notion/airtable/linear MCP servers configured
**Required:** External MCP server configurations
**Blocked templates:**
1. `data.knowledge_base_sync` — needs notion/airtable
2. `data.record_sync` — needs notion/airtable
3. `data.form_intake` — needs google_sheets
4. `business.crm_followup` — needs airtable
5. `business.lead_intake_crm` — needs airtable
6. `business.support_ticket_triage` — needs linear/notion
7. `productivity.email_to_task` — needs google_tasks
8. `productivity.morning_briefing` — needs task manager

### Block Group 7: Missing providers (3 templates)
**Root cause:** Provider not implemented
**Blocked templates:**
1. `development.issue_to_implementation` — needs coding_agent provider
2. `files.download_folder_organizer` — needs filesystem write actions
3. `data.form_intake` — needs google_sheets provider

---

## Dependency Chain Analysis

### What blocks the most templates?
| Capability | Templates Blocked | Cascade Effect |
|------------|------------------|----------------|
| `knowledge` | 12 | HIGH — blocks monitoring, business, data |
| `browser` (generic) | 5 | MEDIUM — blocks research, monitoring |
| `calendar` | 4 | MEDIUM — blocks productivity |
| `email` | 3 | LOW — blocks inbox monitoring |
| `media` | 5 | LOW — blocks content creation |
| `mcp_tool` (external) | 8 | HIGH — blocks business, data |
| `filesystem` (write) | 25 | CRITICAL — nearly everything |
| `communication` (multi) | 35 | CRITICAL — notification layer |

### Cascade Effect
```
knowledge provider
├── enables: monitoring.* (4 templates)
├── enables: business.* (4 templates)
├── enables: data.api_poll_to_store, data.webhook_to_store
├── enables: productivity.morning_briefing
└── enables: ai.enrich_records, ai.rag_answer

browser (generic scraping)
├── enables: browser.* (3 templates)
├── enables: research.* (2 templates)
└── enables: monitoring.security_scan_alert (URL scanning)

calendar provider
├── enables: productivity.calendar_to_status
├── enables: productivity.ecosystem_briefing
├── enables: productivity.email_to_calendar
└── enables: productivity.meeting_prep

filesystem (write actions)
├── enables: 25 templates that write files
└── enables: artifacts, files, development, data categories

communication (multi-channel)
├── enables: 35 templates that notify
└── enables: all escalation, alert, monitoring templates
```

---

## Truth Table: Provider × Capability × Templates

| Provider | Capability | Status | Templates Affected | Can Ship? |
|----------|-----------|--------|-------------------|-----------|
| LLM Gateway | ai_reasoning | ✅ | 47 | YES |
| WorkflowEngine | workflow | ✅ | 10 | YES |
| TerminalProvider | terminal | ⚠️ | 18 | PARTIAL |
| DesktopProvider | desktop | ✅ | 0 | YES (unused) |
| SystemProvider | system | ✅ | 0 | YES (unused) |
| BrowserProvider | browser | ❌ | 8 | NO (YouTube only) |
| FilesystemProvider | filesystem | ❌ | 25 | NO (1 action) |
| MCPProvider | mcp_tool | ⚠️ | 10 | PARTIAL (local only) |
| (none) | knowledge | ❌ | 12 | NO |
| (none) | calendar | ❌ | 4 | NO |
| (none) | email | ❌ | 3 | NO |
| (none) | media | ❌ | 5 | NO |
| (none) | code_project | ❌ | 1 | NO |

---

## Minimum Viable Provider Set (to unlock most templates)

To go from 3/63 → ~40/63 executable, build these providers in order:

1. **Filesystem (expand)** — add write/read/move/hash/verify actions → unlocks 25 templates
2. **Communication (expand)** — add Slack, Discord, email send → unlocks 35 templates (partial)
3. **Knowledge (new)** — web fetch + RSS + HMAC → unlocks 12 templates
4. **Browser (expand)** — add generic scraping → unlocks 5 templates
5. **Memory (expand)** — add conversation history + KV → unlocks 16 templates (partial)
6. **Calendar (new)** — Google Calendar API → unlocks 4 templates
7. **Email (new)** — Gmail API or IMAP → unlocks 3 templates

**Estimated total after these 7 providers:** ~45/63 executable (71%)
