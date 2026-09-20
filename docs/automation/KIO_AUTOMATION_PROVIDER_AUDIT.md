# KIO Automation — Provider Audit

> **Date:** 2026-09-13
> **Scope:** Every provider, capability, and package dependency audited against actual source code.

---

## Audit Methodology

For each provider/capability:
1. **Source evidence** — file path and line where implementation exists
2. **Registration evidence** — how it's registered in ProviderRegistry
3. **Capability probe** — what actions it actually supports
4. **Truth verdict** — IMPLEMENTED / PARTIAL / MISSING

---

## 1. BrowserProvider

**File:** `mini_kio/core/providers/browser_provider.py`
**Registration:** `ProviderRegistry.register(browser, BrowserProvider)`

### Implemented Actions
| Action | Method | Evidence |
|--------|--------|----------|
| `play_youtube` | `_play_youtube()` | Line ~100 — uses browser_operator.open_website + open_specific_website |
| `search_youtube` | `_search_youtube()` | Line ~130 — types query into YouTube search |
| `browser_click` | `_browser_click()` | Line ~160 — delegates to browser_operator.click |
| `browser_hover` | `_browser_hover()` | Line ~170 |
| `browser_scroll` | `_browser_scroll()` | Line ~180 |
| `browser_drag` | `_browser_drag()` | Line ~190 |
| `browser_select` | `_browser_select()` | Line ~200 |
| `browser_fill` | `_browser_fill()` | Line ~210 |
| `browser_type` | `_browser_type()` | Line ~220 |
| `browser_keypress` | `_browser_keypress()` | Line ~230 |
| `browser_evaluate` | `_browser_evaluate()` | Line ~240 |

### Missing Actions (needed by templates)
| Action | Needed By | Status |
|--------|-----------|--------|
| `extract_records` | browser.structured_extract | ❌ MISSING |
| `extract_price` | browser.price_monitor | ❌ MISSING |
| `crawl_extract` | browser.page_change_monitor | ❌ MISSING |
| `snapshot_sources` | browser.page_change_monitor | ❌ MISSING |
| `browser_screenshot` | Multiple templates | ❌ MISSING |
| `browser_pdf` | Multiple templates | ❌ MISSING |

### Verdict: ⚠️ PARTIAL
YouTube + DOM interaction exists. Generic web scraping (extract, screenshot, PDF) does NOT exist.

---

## 2. FilesystemProvider

**File:** `mini_kio/core/providers/filesystem_provider.py`
**Registration:** `ProviderRegistry.register(filesystem, FilesystemProvider)`

### Implemented Actions
| Action | Method | Evidence |
|--------|--------|----------|
| `open_folder` | `_open_folder()` | Line ~50 — delegates to file_operator |

### Missing Actions (needed by 25 templates)
| Action | Needed By | Status |
|--------|-----------|--------|
| `write` | Multiple | ❌ MISSING |
| `read` | Multiple | ❌ MISSING |
| `write_csv` | data.csv_pii_scrub | ❌ MISSING |
| `verify_csv` | data.csv_pii_scrub | ❌ MISSING |
| `move_file` | files.download_folder_organizer | ❌ MISSING |
| `hash_tree` | files.duplicate_detector | ❌ MISSING |
| `classify_file` | files.download_folder_organizer | ❌ MISSING |
| `extract_text` | files.document_summarize | ❌ MISSING |
| `store_record` | data.record_sync | ❌ MISSING |
| `verify_path` | Multiple | ❌ MISSING |
| `verify_project` | development.scaffold_project | ❌ MISSING |
| `verify_image` | ai.image_generate | ❌ MISSING |
| `verify_paths` | Multiple | ❌ MISSING |
| `write_derivatives` | media.content_repurpose | ❌ MISSING |
| `upload_backup` | development.repo_backup | ❌ MISSING |
| `verify_upload` | development.repo_backup | ❌ MISSING |
| `prune_old_backups` | development.repo_backup | ❌ MISSING |
| `append_sheet_row` | data.form_intake | ❌ MISSING |
| `verify_sheet_row` | data.form_intake | ❌ MISSING |
| `recent_drive_changes` | files.drive_to_social | ❌ MISSING |
| `get_new_asset` | files.drive_to_social | ❌ MISSING |

### Verdict: ❌ CRITICALLY INCOMPLETE
Single action. 25 templates depend on this. Needs 10+ actions minimum.

---

## 3. TerminalProvider

**File:** `mini_kio/core/providers/terminal_provider.py`
**Registration:** `ProviderRegistry.register(terminal, TerminalProvider)`

### Implemented Actions
| Action | Method | Evidence |
|--------|--------|----------|
| `run_command` | `_run_command()` | Line ~50 — safe_command_whitelist check, then subprocess.run |

### Safe Command Whitelist (from source)
`git`, `dir`, `tree`, `echo`, `type`, `where`, `python`, `pip`, `node`, `npm`, `code`, `explorer`, `start`

### Actions Needed by Templates
| Action | Needed By | Can Terminal Do It? |
|--------|-----------|-------------------|
| `render_docx` | artifacts.* | ⚠️ NEEDS: `python -c "from docx import Document; ..."` — long command, may exceed safe-cmd |
| `render_pptx` | artifacts.research_to_pptx | ⚠️ Same issue |
| `render_pdf_from_html` | artifacts.research_to_pdf | ⚠️ Needs WeasyPrint (not installed) |
| `verify_docx` | artifacts.meeting_to_report | ⚠️ Same issue |
| `verify_pptx` | artifacts.research_to_pptx | ⚠️ Same issue |
| `verify_pdf` | artifacts.research_to_pdf | ⚠️ Same issue |
| `git_init` | development.scaffold_project | ✅ git in whitelist |
| `open_vscode` | development.scaffold_project | ⚠️ code in whitelist |
| `scaffold` | development.scaffold_project | ⚠️ mkdir/file creation |
| `append_xlsx_row` | data.form_intake | ⚠️ Needs openpyxl command |
| `render_markdown` | research.daily_brief | ⚠️ Needs pandoc or custom |
| `delegate_to_agent` | Multiple | ❌ MISSING |

### Verdict: ⚠️ PARTIAL
Safe whitelist covers basic CLI. Python one-liners for docx/pptx may be too long for safe-cmd. Needs `delegate_to_agent` for multi-step.

---

## 4. WorkflowProvider

**File:** `mini_kio/core/providers/workflow_provider.py`
**Registration:** `ProviderRegistry.register(workflow, WorkflowProvider)`

### Implemented Actions
All WorkflowEngine actions delegated:
- `transform_records`, `verify_shape`, `validate_schema`
- `branch`, `route`
- `request_approval`, `wait_for_ack`, `advance_tier_or_stop`

### Verdict: ✅ IMPLEMENTED
Fully delegates to WorkflowEngine. All workflow actions available.

---

## 5. SystemProvider

**File:** `mini_kio/core/providers/system_provider.py`
**Registration:** `ProviderRegistry.register(system, SystemProvider)`

### Implemented Actions
- `lock_system`, `shutdown_system`, `restart_system`, `recovery_runtime`

### Verdict: ✅ IMPLEMENTED
No templates currently use system actions. Available for future use.

---

## 6. DesktopProvider

**File:** `mini_kio/core/providers/desktop_provider.py`
**Registration:** `ProviderRegistry.register(desktop, DesktopProvider)`

### Implemented Actions
Basic: `open_app`, `close_app`, `search_web`, `execute_capability`
Rich (16): mouse move/click/scroll, keyboard type/key, clipboard get/set, screenshot, window focus/resize, notification, volume, brightness

### Verdict: ✅ IMPLEMENTED
No templates currently use desktop actions. Available for future use.

---

## 7. MCPProvider

**File:** `mini_kio/core/mcp/provider.py`
**Registration:** `ProviderRegistry.register(mcp_tool, MCPProvider)`

### Implemented Actions
Delegates to MCP server registry. Each MCP server provides its own actions.

### MCP Server Coverage
| Server | Available Actions | Templates Needing |
|--------|------------------|-------------------|
| filesystem | file read/write/list | 10+ |
| git | repo operations | 9+ |
| terminal | command execution | 18+ |
| sqlite | database queries | 2+ |
| docker | container management | 0 |
| github | issues/PRs/releases | 9 |
| postgres | database queries | 0 |
| redis | cache operations | 0 |

### Missing MCP Servers (needed by templates)
| Server | Needed By | Status |
|--------|-----------|--------|
| notion | data.knowledge_base_sync, business.* | ❌ NOT CONFIGURED |
| airtable | data.record_sync, business.* | ❌ NOT CONFIGURED |
| linear | business.support_ticket_triage | ❌ NOT CONFIGURED |
| google_tasks | productivity.email_to_task | ❌ NOT CONFIGURED |
| todoist | productivity.email_to_task | ❌ NOT CONFIGURED |

### Verdict: ⚠️ PARTIAL
Local servers work. External servers (notion, airtable, linear) not configured.

---

## 8. LLM Gateway (ai_reasoning capability)

**File:** `mini_kio/core/llm_router.py`
**Providers:** Gemini, Groq, HuggingFace, OpenRouter, Together, Cerebras

### Capabilities
- Text generation (all templates)
- Research, planning, writing, classification
- Structured extraction
- PII detection
- Draft replies
- Embeddings (via sentence_transformers local)

### Verdict: ✅ IMPLEMENTED
6 provider failover chain. 47 templates depend on this. Works.

---

## 9. Communication (Telegram)

**File:** `mini_kio/bot/kio_bot.py` + `kio_runner.py`
**Platform:** Telegram Bot API only

### Implemented Actions
- `send_message` (Telegram)

### Missing Actions
| Action | Needed By | Status |
|--------|-----------|--------|
| `send_file` | communication.* | ❌ MISSING |
| `send_batch` | communication.* | ❌ MISSING |
| `send_with_ack` | communication.escalation_alert | ❌ MISSING |
| `apply_label` | productivity.email_label_ai | ❌ MISSING |
| `set_status` | productivity.calendar_to_status | ❌ MISSING |
| `debounce_messages` | communication.notify | ❌ MISSING |

### Verdict: ⚠️ TELEGRAM ONLY
35 templates depend on communication. Only Telegram send works.

---

## 10. Memory (KV Store)

**File:** `mini_kio/core/state_verification.py` + trace_logger
**Capabilities:** State tracking, diff comparison, conversation history

### Implemented
- `record_and_compare` — state snapshots
- `diff_against_last` — change detection
- `filter_new` — new record detection

### Missing
| Action | Needed By | Status |
|--------|-----------|--------|
| `diff_snapshots` | browser.price_monitor | ❌ MISSING |
| `week_activity` | productivity.weekly_review | ❌ MISSING |
| `load_conversation` | communication.chat_assistant | ❌ MISSING |
| `save_turn` | communication.chat_assistant | ❌ MISSING |
| `gather_context` | research.* | ❌ MISSING |
| `apply_field_map` | data.record_sync | ❌ MISSING |
| `exclude_recently_contacted` | business.crm_followup | ❌ MISSING |

### Verdict: ⚠️ PARTIAL
State tracking exists. Full KV store with conversation history does NOT exist.

---

## 11. Knowledge (Web Fetch + RSS + Vector Store)

**File:** NONE — not implemented

### Needed By (12 templates)
- `ai.enrich_records` — web fetch for enrichment
- `ai.rag_answer` — vector search
- `data.api_poll_to_store` — HTTP polling
- `data.webhook_to_store` — webhook validation
- `monitoring.rss_news_monitor` — RSS parsing
- `monitoring.security_scan_alert` — URL scanning
- `monitoring.website_uptime` — HTTP health checks
- `productivity.morning_briefing` — news aggregation
- `business.lead_intake_crm` — lead validation
- `business.crm_followup` — CRM data fetch

### Required Components
| Component | Package | Status |
|-----------|---------|--------|
| Web fetch | httpx | ✅ INSTALLED |
| RSS parsing | feedparser | ❌ NOT INSTALLED |
| HMAC verification | hashlib | ✅ STDLIB |
| Vector search | chromadb OR qdrant-client | ❌ NOT INSTALLED |
| HTML parsing | beautifulsoup4 | ❌ NOT INSTALLED (lxml YES) |

### Verdict: ❌ NOT IMPLEMENTED
12 templates blocked. httpx available but no framework.

---

## 12. Calendar (Google Calendar)

**File:** NONE — not implemented

### Needed By (4 templates)
- `productivity.calendar_to_status`
- `productivity.ecosystem_briefing`
- `productivity.email_to_calendar`
- `productivity.meeting_prep`

### Required Components
| Component | Package | Status |
|-----------|---------|--------|
| Google Calendar API | google-api-python-client | ✅ INSTALLED |
| OAuth2 credentials | google_auth_oauthlib | ❌ NOT INSTALLED |
| Calendar operations | — | ❌ NOT IMPLEMENTED |

### Verdict: ❌ NOT IMPLEMENTED
Package available but no OAuth2 flow or calendar operations.

---

## 13. Email (Gmail/IMAP)

**File:** NONE — not implemented

### Needed By (3 templates)
- `monitoring.inbox_monitor`
- `productivity.email_to_task`
- `productivity.email_to_calendar`

### Required Components
| Component | Package | Status |
|-----------|---------|--------|
| Gmail API | google-api-python-client | ✅ INSTALLED |
| OAuth2 credentials | google_auth_oauthlib | ❌ NOT INSTALLED |
| IMAP client | imaplib (stdlib) | ✅ STDLIB |
| Email operations | — | ❌ NOT IMPLEMENTED |

### Verdict: ❌ NOT IMPLEMENTED
Package available but no email operations.

---

## 14. Media (Publishing + TTS + Image Gen)

**File:** `mini_kio/core/media_contract.py` (type definitions only)

### Needed By (5 templates)
- `ai.image_generate` — image generation
- `files.drive_to_social` — asset publishing
- `media.content_repurpose` — multi-platform publish
- `communication.voice_assistant` — TTS output
- `research.competitor_monitor` — screenshot capture

### Required Components
| Component | Package | Status |
|-----------|---------|--------|
| Image generation | API client | ❌ NOT IMPLEMENTED |
| TTS | pyttsx3 OR API | ❌ NOT INSTALLED |
| Social publishing | Platform APIs | ❌ NOT IMPLEMENTED |
| Transcoding | ffmpeg | ⚠️ May be installed |

### Verdict: ❌ CONTRACTS ONLY
Type definitions exist. Zero implementation.

---

## 15. Code Project (Development Environment)

**File:** NONE — not implemented

### Needed By (1 template)
- `development.issue_to_implementation`

### Required Components
| Component | Package | Status |
|-----------|---------|--------|
| Coding agent | Custom | ❌ NOT IMPLEMENTED |
| Git operations | gitpython | ❌ NOT INSTALLED |
| VS Code CLI | vscode_cli | ❌ NOT INSTALLED |

### Verdict: ❌ NOT IMPLEMENTED

---

## Package Dependency Summary

### Installed (can use)
httpx, playwright, python-docx, openpyxl, python-pptx, lxml, pandas, numpy, jinja2, keyring, psutil, pyyaml, pillow, aiohttp, faster_whisper, torch, sentence_transformers, requests, scikit-learn, pydantic, fastapi, uvicorn, pyotp, cryptography, discord.py, google-api-python-client, boto3

### Missing (blocks specific templates)
| Package | Blocks | Install Effort |
|---------|--------|---------------|
| beautifulsoup4 | 5+ templates (HTML parsing) | `pip install beautifulsoup4` |
| feedparser | 1 template (RSS) | `pip install feedparser` |
| gitpython | 1 template (repo operations) | `pip install gitpython` |
| chromadb OR qdrant-client | 1 template (RAG) | `pip install chromadb` |
| slack_sdk | 3+ templates (Slack) | `pip install slack_sdk` |
| msal | 2+ templates (Microsoft) | `pip install msal` |
| selenium | 0 (playwright替代) | NOT NEEDED |
| yfinance | 0 | NOT NEEDED |
| sendgrid | 1 template (email) | `pip install sendgrid` |
| twilio | 1 template (SMS) | `pip install twilio` |
| stripe | 0 | NOT NEEDED |
| docker | 0 | NOT NEEDED |
| paramiko | 0 | NOT NEEDED |
| azure-identity | 1 template (Azure) | `pip install azure-identity` |
| google-cloud-storage | 1 template (GCS) | `pip install google-cloud-storage` |
