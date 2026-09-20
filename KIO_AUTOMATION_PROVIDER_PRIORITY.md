# KIO Automation — Provider Priority (Implementation Roadmap)

> **Date:** 2026-09-13
> **Principle:** Priority ordered by templates unlocked, then by implementation effort.
> **No large implementations** — each provider is minimal, reuses existing infrastructure.

---

## Priority Summary

| Priority | Provider | Effort | Templates Unlocked | Cumulative |
|----------|----------|--------|-------------------|------------|
| P0 | Filesystem (expand) | LOW | +15 | 18/63 (29%) |
| P1 | Communication (expand) | LOW | +10 | 28/63 (44%) |
| P2 | Knowledge (new) | MEDIUM | +12 | 40/63 (63%) |
| P3 | Browser (expand) | LOW | +5 | 45/63 (71%) |
| P4 | Memory (expand) | LOW | +6 | 51/63 (81%) |
| P5 | Calendar (new) | MEDIUM | +4 | 55/63 (87%) |
| P6 | Email (new) | MEDIUM | +3 | 58/63 (92%) |
| P7 | Media (new) | HIGH | +5 | 63/63 (100%) |

---

## P0: Filesystem (expand)

**Current state:** 1 action (`open_folder`)
**Target state:** ~15 actions covering read/write/move/hash/verify
**Effort:** LOW — thin wrappers around stdlib (pathlib, shutil, hashlib)
**Templates unlocked:** 15 directly, cascading benefit to 25

### Actions to Implement
| Action | Implementation | Lines |
|--------|---------------|-------|
| `write_file` | `pathlib.Path.write_text()` | ~5 |
| `read_file` | `pathlib.Path.read_text()` | ~5 |
| `write_csv` | `csv.writer` | ~15 |
| `read_csv` | `csv.reader` | ~10 |
| `move_file` | `shutil.move()` | ~5 |
| `copy_file` | `shutil.copy2()` | ~5 |
| `hash_file` | `hashlib.sha256` | ~10 |
| `hash_tree` | `os.walk` + hash_file | ~20 |
| `list_dir` | `pathlib.Path.iterdir()` | ~10 |
| `verify_path` | `pathlib.Path.exists()` | ~5 |
| `classify_file` | Extension mapping | ~15 |
| `extract_text` | Read + decode | ~10 |
| `append_csv` | `csv.writer` append mode | ~10 |
| `store_record` | JSON append | ~15 |
| `delete_file` | `pathlib.Path.unlink()` | ~5 |

**Registration:** Add to existing FilesystemProvider in `mini_kio/core/providers/filesystem_provider.py`
**Total new code:** ~150 lines

### Templates Unblocked
1. `files.download_folder_organizer` — classify_file + move_file
2. `files.document_summarize` — extract_text
3. `files.duplicate_detector` — hash_tree
4. `files.invoice_extract_to_sheet` — write_csv + append_csv
5. `data.csv_pii_scrub` — write_csv
6. `data.file_extract_to_csv` — write_csv
7. `development.repo_backup` — hash_file + write_file
8. `development.scaffold_project` — write_file + list_dir
9. `artifacts.data_to_xlsx` — write_file
10. `artifacts.meeting_to_report` — write_file
11. `artifacts.research_to_docx` — write_file
12. `artifacts.research_to_pptx` — write_file
13. `artifacts.multiformat_report` — write_file
14. `productivity.weekly_review` — write_file
15. `research.daily_brief` — write_file

---

## P1: Communication (expand)

**Current state:** Telegram send only
**Target state:** Multi-channel (Telegram, Slack, Discord, email send)
**Effort:** LOW — discord.py installed, slack_sdk needs install
**Templates unlocked:** 10 directly

### Actions to Implement
| Action | Implementation | Lines |
|--------|---------------|-------|
| `send_file` | Telegram + Slack + Discord file send | ~30 |
| `send_batch` | Loop over send_message | ~15 |
| `send_with_ack` | send + wait for reaction | ~20 |
| `set_status` | Platform-specific status update | ~15 |
| `apply_label` | Telegram folder / Slack channel | ~15 |
| `debounce_messages` | Time-based dedup | ~20 |

### Platform Integrations
| Platform | Package | Status | Effort |
|----------|---------|--------|--------|
| Telegram | python-telegram-bot | ✅ Working | Existing |
| Slack | slack_sdk | ❌ Not installed | `pip install slack_sdk` + ~50 lines |
| Discord | discord.py | ✅ Installed | ~50 lines |
| Email | smtplib (stdlib) | ✅ Available | ~30 lines |

**Registration:** Expand existing CommunicationProvider (or create new one)
**Total new code:** ~200 lines + slack_sdk install

### Templates Unblocked
1. `communication.notify` — multi-channel send
2. `communication.escalation_alert` — send_with_ack
3. `communication.workflow_failure_alert` — send_file (error details)
4. `communication.chat_assistant` — send_file (images, files)
5. `communication.voice_assistant` — send_file (audio)
6. `productivity.email_label_ai` — apply_label
7. `productivity.calendar_to_status` — set_status
8. `business.email_autoresponder_approval` — send_file (draft)
9. `files.drive_to_social` — send_file (assets)
10. `media.content_repurpose` — send_file (processed content)

---

## P2: Knowledge (new)

**Current state:** Not implemented
**Target state:** Web fetch + RSS + HMAC verification
**Effort:** MEDIUM — new provider, but httpx available
**Templates unlocked:** 12

### Actions to Implement
| Action | Implementation | Lines |
|--------|---------------|-------|
| `web_fetch` | httpx.get() + timeout | ~20 |
| `web_fetch_html` | httpx + html parsing | ~25 |
| `rss_read` | feedparser.parse() | ~20 |
| `hmac_verify` | hmac.compare_digest | ~15 |
| `url_check` | HEAD request + status | ~15 |
| `search_web` | httpx + search API | ~30 |
| `get_weather` | httpx + weather API | ~20 |

### Package Dependencies
| Package | Status | Install |
|---------|--------|---------|
| httpx | ✅ Installed | — |
| feedparser | ❌ Not installed | `pip install feedparser` |
| beautifulsoup4 | ❌ Not installed | `pip install beautifulsoup4` |
| lxml | ✅ Installed | — (alternative parser) |

**Registration:** New provider `KnowledgeProvider` in `mini_kio/core/providers/knowledge_provider.py`
**Total new code:** ~150 lines + 2 package installs

### Templates Unblocked
1. `ai.enrich_records` — web_fetch
2. `data.api_poll_to_store` — web_fetch + hmac_verify
3. `data.webhook_to_store` — hmac_verify
4. `monitoring.rss_news_monitor` — rss_read
5. `monitoring.security_scan_alert` — url_check
6. `monitoring.website_uptime` — web_fetch
7. `productivity.morning_briefing` — rss_read + web_fetch
8. `business.lead_intake_crm` — web_fetch
9. `business.crm_followup` — web_fetch
10. `business.support_ticket_triage` — web_fetch
11. `research.daily_brief` (partially) — web_fetch
12. `research.youtube_summary` (partially) — web_fetch

---

## P3: Browser (expand)

**Current state:** YouTube + DOM interaction only
**Target state:** Generic web scraping (extract, screenshot, PDF)
**Effort:** LOW — Playwright installed, browser_operator has DOM primitives
**Templates unlocked:** 5

### Actions to Implement
| Action | Implementation | Lines |
|--------|---------------|-------|
| `extract_text` | page.inner_text() | ~10 |
| `extract_html` | page.content() | ~10 |
| `extract_records` | page.query_selector_all + parse | ~30 |
| `extract_price` | page.text_content + regex | ~20 |
| `screenshot` | page.screenshot() | ~10 |
| `pdf` | page.pdf() | ~10 |
| `wait_for_selector` | page.wait_for_selector() | ~10 |
| `goto` | page.goto() | ~5 |

**Registration:** Expand existing BrowserProvider
**Total new code:** ~100 lines

### Templates Unblocked
1. `browser.structured_extract` — extract_records
2. `browser.price_monitor` — extract_price
3. `browser.page_change_monitor` — extract_html + wait_for_selector
4. `research.competitor_monitor` — extract_text + screenshot
5. `research.web_scrape_to_report` — extract_text + goto

---

## P4: Memory (expand)

**Current state:** State tracking (record_and_compare, diff_against_last)
**Target state:** Full KV store with conversation history
**Effort:** LOW — extend state_verification.py
**Templates unlocked:** 6

### Actions to Implement
| Action | Implementation | Lines |
|--------|---------------|-------|
| `get` | Dict lookup | ~5 |
| `set` | Dict store + persist | ~10 |
| `diff` | Compare two snapshots | ~15 |
| `load_conversation` | Read JSON history | ~10 |
| `save_turn` | Append to JSON history | ~10 |
| `gather_context` | Load + filter + format | ~15 |
| `week_activity` | Filter by timestamp | ~10 |
| `exclude_recently_contacted` | Filter by last contact | ~10 |

**Registration:** Expand existing state_verification or create MemoryProvider
**Total new code:** ~80 lines

### Templates Unblocked
1. `communication.chat_assistant` — load_conversation + save_turn
2. `browser.price_monitor` — diff + set
3. `browser.page_change_monitor` — diff + set
4. `productivity.weekly_review` — week_activity
5. `research.competitor_monitor` — gather_context
6. `business.crm_followup` — exclude_recently_contacted

---

## P5: Calendar (new)

**Current state:** Not implemented
**Target state:** Google Calendar API wrapper
**Effort:** MEDIUM — google-api-python-client installed, needs OAuth2
**Templates unlocked:** 4

### Actions to Implement
| Action | Implementation | Lines |
|--------|---------------|-------|
| `today_events` | Calendar API events.list | ~25 |
| `upcoming_within` | events.list with timeMax | ~20 |
| `get_event` | events.get | ~15 |
| `create_event` | events.insert | ~25 |
| `update_event` | events.update | ~20 |
| `delete_event` | events.delete | ~15 |

### Dependencies
| Package | Status | Install |
|---------|--------|---------|
| google-api-python-client | ✅ Installed | — |
| google-auth-oauthlib | ❌ Not installed | `pip install google-auth-oauthlib` |
| google-auth-httplib2 | ❌ Not installed | `pip install google-auth-httplib2` |

**Registration:** New provider `CalendarProvider` in `mini_kio/core/providers/calendar_provider.py`
**Total new code:** ~120 lines + 2 package installs + OAuth2 credentials

### Templates Unblocked
1. `productivity.calendar_to_status` — today_events
2. `productivity.ecosystem_briefing` — today_events
3. `productivity.email_to_calendar` — create_event
4. `productivity.meeting_prep` — upcoming_within

---

## P6: Email (new)

**Current state:** Not implemented
**Target state:** Gmail API or IMAP client
**Effort:** MEDIUM — imaplib available, Gmail API possible
**Templates unlocked:** 3

### Actions to Implement
| Action | Implementation | Lines |
|--------|---------------|-------|
| `inbox_scan` | IMAP search + fetch | ~30 |
| `send_email` | smtplib (stdlib) | ~25 |
| `read_email` | IMAP fetch | ~20 |
| `label_email` | IMAP store | ~15 |
| `search_email` | IMAP search | ~15 |

### Dependencies
| Package | Status | Install |
|---------|--------|---------|
| imaplib | ✅ Stdlib | — |
| smtplib | ✅ Stdlib | — |
| email | ✅ Stdlib | — |
| google-api-python-client | ✅ Installed | — (for Gmail API) |

**Registration:** New provider `EmailProvider` in `mini_kio/core/providers/email_provider.py`
**Total new code:** ~100 lines + OAuth2 credentials (for Gmail API)

### Templates Unblocked
1. `monitoring.inbox_monitor` — inbox_scan
2. `productivity.email_to_task` — inbox_scan
3. `productivity.email_to_calendar` — inbox_scan (also needs calendar)

---

## P7: Media (new)

**Current state:** Type definitions only (media_contract.py)
**Target state:** Image gen, TTS, publishing, transcoding
**Effort:** HIGH — multiple APIs, complex integration
**Templates unlocked:** 5

### Actions to Implement
| Action | Implementation | Lines |
|--------|---------------|-------|
| `generate_image` | API client (DALL-E/Stable Diffusion) | ~40 |
| `text_to_speech` | pyttsx3 or API | ~30 |
| `transcribe` | faster_whisper (already installed) | ~20 |
| `publish_social` | Platform APIs | ~50 |
| `transcode_video` | ffmpeg subprocess | ~30 |

### Dependencies
| Package | Status | Install |
|---------|--------|---------|
| faster_whisper | ✅ Installed | — |
| pyttsx3 | ❌ Not installed | `pip install pyttsx3` |
| ffmpeg | ⚠️ Check | System install |

**Registration:** New provider `MediaProvider` in `mini_kio/core/providers/media_provider.py`
**Total new code:** ~170 lines + package installs + API keys

### Templates Unblocked
1. `ai.image_generate` — generate_image
2. `communication.voice_assistant` — text_to_speech
3. `media.content_repurpose` — publish_social + transcode
4. `files.drive_to_social` — publish_social
5. `research.competitor_monitor` — screenshot (also needs browser)

---

## Implementation Order (Recommended)

### Phase 1: Quick Wins (P0 + P1) — 1-2 days
1. Expand FilesystemProvider with 15 actions (~150 lines)
2. Expand CommunicationProvider with send_file + multi-channel (~200 lines)
3. Install slack_sdk
4. **Result:** 28/63 executable (44%)

### Phase 2: Core Infrastructure (P2 + P3) — 2-3 days
5. Create KnowledgeProvider (~150 lines)
6. Install feedparser + beautifulsoup4
7. Expand BrowserProvider with scraping (~100 lines)
8. **Result:** 45/63 executable (71%)

### Phase 3: Integration (P4 + P5 + P6) — 2-3 days
9. Expand Memory (~80 lines)
10. Create CalendarProvider (~120 lines)
11. Create EmailProvider (~100 lines)
12. Install google-auth-oauthlib + google-auth-httplib2
13. **Result:** 58/63 executable (92%)

### Phase 4: Media (P7) — 3-5 days
14. Create MediaProvider (~170 lines)
15. Install pyttsx3, configure ffmpeg
16. **Result:** 63/63 executable (100%)

---

## Total Effort Estimate

| Phase | Lines of Code | Packages | Time |
|-------|--------------|----------|------|
| P0 + P1 | ~350 | slack_sdk | 1-2 days |
| P2 + P3 | ~250 | feedparser, beautifulsoup4 | 2-3 days |
| P4 + P5 + P6 | ~300 | google-auth-oauthlib, google-auth-httplib2 | 2-3 days |
| P7 | ~170 | pyttsx3 | 3-5 days |
| **Total** | **~1,070** | **5 packages** | **8-13 days** |

---

## Non-Provider Blockers (also need resolution)

| Blocker | Affects | Resolution |
|---------|---------|------------|
| OAuth2 credentials | Calendar, Email, Gmail | User must provide Google Cloud credentials |
| API keys | Image generation, social publishing | User must provide API keys |
| MCP server configs | notion, airtable, linear | User must configure MCP servers |
| ffmpeg | Media transcoding | System install |
| LibreOffice | PDF/docx rendering | System install |
