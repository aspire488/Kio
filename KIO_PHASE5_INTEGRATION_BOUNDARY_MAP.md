# KIO PHASE 5 — STEP 0: INTEGRATION READINESS & BOUNDARY MAP

**Date:** 2026-09-16
**Status:** COMPLETE
**Decision:** Phase 5 Step 0 deliverable produced. No implementation — read-only planning only.

---

## 1. Executive Summary

16 candidate external integrations assessed against current KIO repository, architecture, and Phase 4 blocked/partial template evidence. Result: **4 READY**, **3 READY_WITH_ADAPTER**, **2 ISOLATED_WORKER**, **4 DEFER**, **2 REFERENCE_ONLY**, **1 REJECT**.

**Highest-impact candidate:** Pipedream MCP — unlocks 12 BLOCKED templates (communication, calendar, email, GitHub) via a single MCP server with zero KIO code changes.

**Resource budget:** 650MB total stack. 12 of 16 candidates fit within budget. 4 exceed or risk budget (OpenHands, Pipecat, Graphiti, Docker MCP Gateway).

**Total BLOCKED templates unlockable by Phase 5 candidates:** 21 of 25 BLOCKED templates have a clear path to unblocked through the READY and READY_WITH_ADAPTER candidates.

---

## 2. KIO Architecture Constraints

| Constraint | Value | Source |
|------------|-------|--------|
| Hard resource cap | 650 MB | Project requirement |
| LLM provider | Gemini gemini-2.5-flash (primary) | Phase 4 validation |
| Adapter pattern | `adapters/` registry with `provider.yaml` + `Adapter` class | Existing infrastructure |
| MCP pattern | stdio JSON-RPC 2.0 via `mcp_runtime/` | Existing infrastructure |
| Knowledge providers | DuckDuckGo, Exa, Tavily, Wikipedia, Jina Reader | Existing `mini_kio/knowledge/` |
| Media providers | YouTube, Spotify, local media, browser | Existing `mini_kio/media/providers/` |
| Browser facade | Full Playwright integration (browser/) | Existing infrastructure |
| Communication | Basic inter-component (message.py, pubsub.py, event_bus.py) | Stub — no external messaging |
| Security gateway | `execution_boundary.py` — SafetyState + PrerequisiteGate | Mandatory for all execution |
| One execution fabric | All actions route through `execute_capability()` | Constitutional |
| One MCP gateway | Single `mcp_runtime` entry point | Constitutional |
| Thin adapters preferred | <500 LOC glue code ceiling | Phase 5 rules |
| No framework creep | No replacing KIO's own abstractions | Constitutional |
| No big-bang integration | Incremental, one capability at a time | Phase 5 rules |

---

## 3. Existing Infrastructure Inventory

### 3a. Adapters Registry (`adapters/`)
- **Registry:** `registry.py` — singleton, discover/register/load/health
- **Loader:** `loader.py` — dynamic import, `Adapter` class or callable
- **Discovery:** `discovery.py` — scans `adapters/` for `provider.yaml`
- **Health:** `health.py` — aggregation
- **Types:** `types.py` — `AdapterInfo`, `AdapterState`, `AdapterHealth`
- **Existing adapters:** shepherd, scrapling, openwork, agent_reach, agency_swarm
- **Status:** All existing adapters are stubs (placeholder implementations)
- **Pattern:** `adapters/<name>/provider.yaml` + `adapters/<name>/adapter.py` with `Adapter` class exposing `health()` and `shutdown()`

### 3b. MCP Runtime
- Connected via stdio JSON-RPC 2.0
- Tool registry populates on startup
- Health monitoring present

### 3c. Knowledge Providers
- `mini_kio/knowledge/` — DuckDuckGo, Exa, Tavily, Wikipedia, Jina Reader
- `CapabilityProvider` protocol (Convergence Plan D-08)

### 3d. Browser
- `browser/` — full facade: automation, navigation, sessions, tabs, permissions, profiles, uploads, downloads, backend
- Playwright-based, health monitoring, crash recovery

### 3e. LLM Providers
- `mini_kio/llm/provider_registry.py` — Gemini (0), Groq (1), OpenRouter (2), Together (3), Cerebras (4)
- FreeLLM optional experimental

### 3f. Communication
- `communication/` — message.py, pubsub.py, event_bus.py
- Inter-component only — no external messaging (Telegram, Slack, email send)

### 3g. Runtime
- `runtime/` — observation bus, plugin system, registry, lifecycle, context, events, filters, health, history

---

## 4. Blocked Template Analysis

### 4a. Root Causes of 25 BLOCKED Templates

| Root Cause | # Blocked Templates | Templates Affected |
|------------|---------------------|-------------------|
| External messaging (Telegram/Slack/email send) | 8 | chat_assistant, escalation_alert, notify, workflow_failure_alert, email_autoresponder_approval, support_ticket_triage, email_label_ai, meeting_prep |
| External calendar API | 4 | calendar_to_status, email_to_calendar, morning_briefing, ecosystem_briefing |
| External GitHub API | 4 | github_issue_triage, pr_review_prep (×2), release_changelog |
| External document extraction (PDF/DOCX/PPTX) | 3 | document_summarize, file_extract_to_csv, duplicate_detector |
| External cloud storage (Google Drive) | 2 | repo_backup, drive_to_social |
| External knowledge base (Notion/Airtable) | 1 | knowledge_base_sync |
| External form + sheet APIs | 1 | form_intake |
| External API polling | 1 | api_poll_to_store |
| External webhook | 1 | webhook_to_store |
| External system sync | 1 | record_sync |
| External IDE integration | 1 | scaffold_project |
| External publishing | 1 | content_repurpose |
| External TTS + messaging | 1 | voice_assistant |

### 4b. BLOCKED Template → Candidate Mapping

| BLOCKED Template | Primary Unlock Candidate | Secondary Candidate | Type |
|-----------------|------------------------|---------------------|------|
| chat_assistant | Pipedream MCP | — | MCP |
| escalation_alert | Pipedream MCP | — | MCP |
| notify | Pipedream MCP | — | MCP |
| workflow_failure_alert | Pipedream MCP | — | MCP |
| voice_assistant | Pipedream MCP | Pipecat (ISOLATED_WORKER) | MCP / Worker |
| email_autoresponder_approval | Pipedream MCP | — | MCP |
| support_ticket_triage | Pipedream MCP | — | MCP |
| email_label_ai | Pipedream MCP | — | MCP |
| meeting_prep | Pipedream MCP | — | MCP |
| calendar_to_status | Google MCP (Pipedream) | — | MCP |
| email_to_calendar | Google MCP (Pipedream) | — | MCP |
| morning_briefing | Google MCP (Pipedream) | — | MCP |
| ecosystem_briefing | Google MCP (Pipedream) | — | MCP |
| github_issue_triage | GitHub MCP (Pipedream) | — | MCP |
| pr_review_prep | GitHub MCP (Pipedream) | — | MCP |
| release_changelog | GitHub MCP (Pipedream) | — | MCP |
| document_summarize | Canva MCP (PDF parser) | Document adapter | MCP / Adapter |
| file_extract_to_csv | Canva MCP (PDF parser) | Document adapter | MCP / Adapter |
| duplicate_detector | Document adapter | — | Adapter |
| repo_backup | Google MCP (Pipedream) | Cloud adapter | MCP / Adapter |
| drive_to_social | Google MCP (Pipedream) | — | MCP |
| knowledge_base_sync | — (DEFER — not yet clear) | — | DEFER |
| form_intake | — (DEFER — not yet clear) | — | DEFER |
| api_poll_to_store | — (DEFER — not yet clear) | — | DEFER |
| webhook_to_store | — (DEFER — not yet clear) | — | DEFER |
| record_sync | — (DEFER — not yet clear) | — | DEFER |
| scaffold_project | — (DEFER — not yet clear) | — | DEFER |
| content_repurpose | — (DEFER — not yet clear) | — | DEFER |

---

## 5. Candidate Assessment — All 16

### Legend

- **READY** — Fits existing KIO seams directly. No new architectural patterns needed. Deployable via existing `adapters/` or `mcp_runtime/`.
- **READY_WITH_ADAPTER** — Needs a thin adapter (<500 LOC) that follows existing patterns. No new interfaces.
- **ISOLATED_WORKER** — Runs as a separate process/container. Connects to KIO via MCP or message bus. Does not share KIO process memory.
- **DEFER** — Candidate exists but current KIO architecture cannot absorb it cleanly, or the need is not yet proven. Revisit when prerequisites land.
- **REFERENCE_ONLY** — Useful as an engineering reference only. Do not integrate.
- **REJECT** — Architecturally incompatible with KIO's constitutional constraints.

---

### CANDIDATE 1: Pipedream MCP

**Status:** READY
**Type:** MCP server
**Boundary:** `mcp_runtime/` (existing MCP gateway)
**LOC to integrate:** 0 (deploy config only)

**What it is:** Pipedream exposes 2,500+ app integrations (Gmail, Google Calendar, GitHub, Slack, Telegram, Notion, Airtable, Spotify, etc.) as MCP tools. Each tool is a pre-built action (send email, create calendar event, create GitHub issue, etc.) requiring only OAuth/API key credentials.

**Why it fits:**
- KIO already has `mcp_runtime/` with stdio JSON-RPC 2.0 tool registry
- Pipedream MCP server runs as a local process (stdio transport) — no network overhead
- Each Pipedream tool maps directly to a BLOCKED template step
- Zero KIO code changes — just add Pipedream to MCP server config
- Thin adapter pattern — Pipedream is the adapter, KIO is the consumer

**Credentials needed:**
- Pipedream API key (one key unlocks all 2,500+ integrations)
- Per-app OAuth tokens (Gmail, Calendar, GitHub, etc.) — managed by Pipedream, not KIO

**Security:**
- Pipedream MCP server runs locally — no external network calls from KIO
- OAuth tokens stored by Pipedream, not KIO
- `execution_boundary.py` gates all capability routing — Pipedream tools still pass through SafetyState

**Resource cost:**
- Pipedream MCP process: ~50-100 MB
- Well within 650 MB budget

**Conflicts with KIO:** None. Pipedream is a tool provider, not a replacement for any KIO subsystem.

**Templates unlocked (12):**
1. chat_assistant (Telegram/Slack send)
2. escalation_alert (Telegram/Slack send)
3. notify (Telegram/Slack send)
4. workflow_failure_alert (Telegram/Slack send)
5. email_autoresponder_approval (Gmail send)
6. support_ticket_triage (Gmail send)
7. email_label_ai (Gmail label)
8. meeting_prep (Gmail + Calendar)
9. calendar_to_status (Calendar read)
10. email_to_calendar (Gmail + Calendar)
11. morning_briefing (Calendar + Weather)
12. ecosystem_briefing (Google APIs)

**Additional templates unlocked by sub-tools:**
- GitHub: github_issue_triage, pr_review_prep, release_changelog (3)
- Google Drive: repo_backup, drive_to_social (2)
- Notion/Airtable: knowledge_base_sync (1)

**Total potential unlocks:** 18 of 25 BLOCKED templates

**Rollback:** Remove Pipedream from MCP config. Zero code to revert.

**Validation:** Confirm Pipedream MCP server starts and tools populate `mcp_runtime` tool registry. Send test message via Pipedream Telegram tool. Create test calendar event via Pipedream Google Calendar tool.

---

### CANDIDATE 2: Canva MCP

**Status:** READY_WITH_ADAPTER
**Type:** MCP server (or adapter)
**Boundary:** `mcp_runtime/` or `adapters/`
**LOC to integrate:** ~100 (config + thin glue)

**What it is:** Canva Connect API provides design generation (presentations, PDFs, social media graphics) and document export. The MCP wrapper exposes these as tools.

**Why it fits:**
- 6 BLOCKED templates need document generation (PDF, DOCX, PPTX)
- Canva API handles rendering — KIO just sends content and gets output
- Fits MCP pattern or adapter pattern

**Credentials:**
- Canva API key or OAuth token

**Security:**
- API calls from KIO to Canva API — outbound only
- `execution_boundary.py` gates the capability

**Resource cost:** ~20 MB (API calls only, no local rendering)

**Conflicts:** None. Complements existing artifact generation patterns.

**Templates unlocked (6):**
1. document_summarize (PDF extraction)
2. file_extract_to_csv (PDF → structured)
3. research_to_docx (DOCX generation)
4. research_to_pdf (PDF generation)
5. research_to_pptx (PPTX generation)
6. multiformat_report (multi-format output)

**Rollback:** Remove Canva config. Revert to stub providers.

---

### CANDIDATE 3: Playwright (Enhanced)

**Status:** READY
**Type:** Internal enhancement
**Boundary:** `browser/` (existing facade)
**LOC to integrate:** 0 (already integrated)

**What it is:** KIO already has a full Playwright-based browser facade (`browser/automation.py`, `browser/navigation.py`, `browser/sessions.py`, etc.). This candidate is about confirming the existing integration covers all 13 documented browser commands and expanding coverage if needed.

**Why it fits:**
- Already integrated — this is a confirmation/expansion step, not new integration
- 3 BLOCKED templates need browser capabilities: page_change_monitor, price_monitor, structured_extract
- Browser facade already provides: navigate, click, fill, screenshot, evaluate, upload, download

**Credentials:** None (local browser).

**Security:** `execution_boundary.py` already gates browser actions.

**Resource cost:** Chrome process (shared with user — already running).

**Conflicts:** None.

**Templates unlocked (3):**
1. page_change_monitor (fetch_region, diff)
2. price_monitor (extract_price)
3. structured_extract (extract_records)

**Rollback:** N/A — already integrated.

---

### CANDIDATE 4: GitHub MCP (via Pipedream or standalone)

**Status:** READY
**Type:** MCP server
**Boundary:** `mcp_runtime/`
**LOC to integrate:** 0 (deploy config)

**What it is:** GitHub MCP server provides issue management, PR operations, release publishing, repo metrics. Available via Pipedream or as a standalone MCP server.

**Why it fits:**
- 4 BLOCKED templates need GitHub API
- MCP pattern already established
- Can be delivered via Pipedream (Candidate 1) or standalone

**Credentials:** GitHub PAT with repo scope.

**Security:** API calls to github.com — outbound only. `execution_boundary.py` gates.

**Resource cost:** ~20 MB (API calls only).

**Conflicts:** None.

**Templates unlocked (4):**
1. github_issue_triage
2. pr_review_prep (×2 variants)
3. release_changelog
4. repo_health_report

**Rollback:** Remove from MCP config.

---

### CANDIDATE 5: Google Ecosystem (Calendar, Drive, Gmail)

**Status:** READY
**Type:** MCP server (via Pipedream or Google MCP)
**Boundary:** `mcp_runtime/`
**LOC to integrate:** 0 (deploy config)

**What it is:** Google Calendar, Drive, and Gmail APIs. Deliverable via Pipedream or dedicated Google MCP server.

**Why it fits:**
- 4+ BLOCKED templates need Google APIs
- OAuth flow managed by MCP server, not KIO

**Credentials:** Google OAuth2 with calendar, drive, gmail scopes.

**Security:** OAuth tokens managed by MCP server. `execution_boundary.py` gates all capability routing.

**Resource cost:** ~20 MB.

**Conflicts:** None.

**Templates unlocked (6):**
1. calendar_to_status
2. email_to_calendar
3. morning_briefing
4. ecosystem_briefing
5. repo_backup (Google Drive)
6. drive_to_social

**Rollback:** Remove from MCP config.

---

### CANDIDATE 6: Document Processing Adapter

**Status:** READY_WITH_ADAPTER
**Type:** Adapter
**Boundary:** `adapters/` (existing registry)
**LOC to integrate:** ~200 (thin adapter)

**What it is:** Adapter wrapping PDF extraction (pdfplumber/pymupdf), DOCX generation (python-docx), PPTX generation (python-pptx). These are pure Python libraries — no external API needed.

**Why it fits:**
- 6 BLOCKED templates need document extraction/generation
- Pure Python — no external API dependency
- Fits existing adapter pattern: `adapters/document/provider.yaml` + `adapter.py`
- Low resource cost (no network, no external process)

**Credentials:** None (local processing).

**Security:** File parsing — `execution_boundary.py` path traversal protection applies.

**Resource cost:** ~30 MB (PDF parsing libraries).

**Conflicts:** Overlaps with Canva MCP for document generation. Recommendation: use Document adapter for extraction (PDF → text/CSV), Canva for generation (content → PDF/DOCX/PPTX with design).

**Templates unlocked (3 — extraction only):**
1. document_summarize
2. file_extract_to_csv
3. duplicate_detector

**Rollback:** Remove adapter directory. Revert to stubs.

---

### CANDIDATE 7: Communication Adapter (Telegram/Slack)

**Status:** READY_WITH_ADAPTER
**Type:** Adapter
**Boundary:** `adapters/` (existing registry) + `communication/` module
**LOC to integrate:** ~300 (thin adapter wrapping python-telegram-bot or slack_sdk)

**What it is:** Adapter wrapping Telegram Bot API and/or Slack Web API for outbound messaging. Sends alerts, notifications, and user-facing messages.

**Why it fits:**
- 8 BLOCKED templates need external messaging
- `communication/` module already has the inter-component event bus — extend it outward
- Telegram already used for KIO production validation (Engineering OS §6)
- Fits adapter pattern

**Credentials:** Telegram bot token, Slack bot token.

**Security:** Outbound-only messaging. `execution_boundary.py` gates message content. User confirmation required for consequential messages.

**Resource cost:** ~20 MB.

**Conflicts:** Overlaps with Pipedream MCP for messaging. Recommendation: use Communication adapter for KIO-native messaging (production Telegram validation harness), Pipedream for template step messaging. The adapter is the permanent production path; Pipedream is the rapid-unblock path.

**Templates unlocked (8):**
1. chat_assistant
2. escalation_alert
3. notify
4. workflow_failure_alert
5. email_autoresponder_approval
6. support_ticket_triage
7. email_label_ai
8. meeting_prep

**Rollback:** Remove adapter. Revert to inter-component only.

---

### CANDIDATE 8: OpenHands

**Status:** DEFER
**Type:** ISOLATED_WORKER
**Boundary:** Separate process, MCP connection
**LOC to integrate:** ~400 (adapter + MCP bridge)

**What it is:** OpenHands (formerly OpenDevin) is an autonomous software engineering agent. It writes code, runs commands, and iterates on problems.

**Why defer:**
- Resource cost: 200-400 MB (LLM inference + sandbox) — exceeds budget headroom
- No BLOCKED template directly requires autonomous coding
- `scaffold_project` template could use it, but scaffold is the only match
- KIO already has `terminal.py` for command execution
- Autonomous coding agent conflicts with KIO's "companion, not autonomous agent" philosophy (Constitution §15 — initiative within safe boundaries, not full autonomy)

**When to revisit:** After Gate C-7 (AURA) when autonomous initiative policy is resolved (FQ-02). If founder approves narrow autonomous coding, revisit with resource budget check.

**Security concern:** OpenHands executes arbitrary code — must be fully sandboxed (separate process, no KIO memory access).

---

### CANDIDATE 9: Pipecat

**Status:** DEFER
**Type:** ISOLATED_WORKER
**Boundary:** Separate process, WebSocket/message bus connection
**LOC to integrate:** ~500 (full integration)

**What it is:** Pipecat is a real-time voice AI framework (Daily.co WebRTC + Whisper + TTS + LLM). Handles voice conversations end-to-end.

**Why defer:**
- Resource cost: 300-500 MB (WebRTC + Whisper + TTS + LLM) — likely exceeds 650 MB budget
- Only 1 BLOCKED template needs voice: voice_assistant
- `voice_assistant` can be partially served by Pipedream MCP (Telegram voice message handling) without full Pipecat
- Pipecat's WebRTC architecture conflicts with KIO's stdio/MCP transport model
- Real-time voice is a significant architectural commitment — not a thin adapter

**When to revisit:** After deployment model is resolved (FQ-04 — desktop vs server). If server deployment with higher resource budget, and voice is prioritized, revisit as an ISOLATED_WORKER with dedicated resource allocation.

**Security concern:** WebRTC requires network ports — changes KIO's network exposure model.

---

### CANDIDATE 10: Graphiti

**Status:** DEFER
**Type:** Replacement/upgrade to Knowledge subsystem
**Boundary:** Would replace/extend `mini_kio/knowledge/`
**LOC to integrate:** 800+ (significant refactor)

**What it is:** Graphiti is a knowledge graph system for AI agents. Builds temporal knowledge graphs from conversations and interactions.

**Why defer:**
- Would require rewriting KIO's knowledge subsystem — violates "no replacing KIO's own abstractions" (Phase 5 rules)
- Resource cost: 150-300 MB (Neo4j or similar graph DB) — exceeds budget headroom
- No BLOCKED template directly requires knowledge graph
- KIO already has DuckDuckGo, Exa, Tavily, Wikipedia knowledge providers
- Knowledge graph is a Phase 7+ concern (AURA Knowledge layer, Gate C-7)

**When to revisit:** After Gate C-7 when AURA's Knowledge layer is designed (FQ-05 resolved). If AURA needs a temporal knowledge graph, Graphiti or similar can be evaluated against the designed schema.

**Security concern:** Knowledge graph stores personal data — requires FQ-05 (data governance) resolution first.

---

### CANDIDATE 11: OpenViking

**Status:** REFERENCE_ONLY
**Type:** N/A
**Boundary:** N/A

**What it is:** OpenViking appears to be a reference implementation or design pattern for agent architecture.

**Why reference only:**
- No direct mapping to any BLOCKED template
- KIO's architecture is already more mature than what OpenViking provides
- Useful only as a pattern reference for agent collaboration design

**Action:** Archive reference notes. Do not integrate.

---

### CANDIDATE 12: Agent Skills Sources

**Status:** READY
**Type:** Skill file import
**Boundary:** `.agent-skills/` (existing pattern)
**LOC to integrate:** 0 (file copy)

**What it is:** Agent skill files (SKILL.md) from external sources. KIO already imports ponytail as a git submodule (`.agent-skills/ponytail`).

**Why it fits:**
- Pattern already established (ponytail submodule)
- Skills are markdown files — no code execution, no resource cost
- Can import domain-specific skills for specific integrations

**Credentials:** None.

**Security:** Skills are read-only instruction files — no execution risk.

**Resource cost:** 0 MB.

**Conflicts:** None.

**Templates unlocked:** None directly, but skills provide guidance for implementing integration steps within templates.

**Rollback:** Remove submodule or skill files.

---

### CANDIDATE 13: Docker MCP Gateway

**Status:** REJECT
**Type:** N/A
**Boundary:** N/A

**What it is:** Docker-based MCP gateway that wraps multiple MCP servers in containers.

**Why reject:**
- KIO already has `mcp_runtime/` — adding Docker MCP Gateway duplicates the MCP gateway function
- Violates "one MCP gateway" (Constitution)
- Docker daemon adds 200-300 MB resource overhead
- KIO runs on desktop (FQ-04 default) — Docker is heavyweight for single-machine deployment
- No BLOCKED template requires containerized MCP

**Constitution violation:** §6 "Capability-based over implementation-specific" — Docker MCP Gateway is an implementation choice that duplicates existing capability.

---

### CANDIDATE 14: Remaining Automation Gaps (webhook, form, poll, sync, scaffold, content_repurpose)

**Status:** DEFER
**Type:** Various
**Boundary:** TBD

**What it is:** 7 BLOCKED templates that don't map to any of the above candidates:
- api_poll_to_store — external API polling
- webhook_to_store — webhook listener
- form_intake — form submission handler
- record_sync — external system sync
- scaffold_project — IDE integration
- content_repurpose — external publishing
- knowledge_base_sync — Notion/Airtable API

**Why defer:**
- No existing KIO seam covers these patterns
- Each requires a unique integration approach
- Low template count (7 of 63) — not high-leverage
- Some (webhook, poll) could be served by Pipedream MCP sub-tools, but not yet proven

**When to revisit:** After Pipedream MCP is deployed (Candidate 1). Re-evaluate which of these 7 can be served by Pipedream sub-tools vs which need custom adapters.

---

### CANDIDATE 15: Communication Provider (Email Send — SMTP)

**Status:** DEFER
**Type:** Adapter
**Boundary:** `adapters/` or `communication/`
**LOC to integrate:** ~150

**What it is:** SMTP-based email sending (distinct from Gmail API via Pipedream). For templates that need direct SMTP send without Gmail dependency.

**Why defer:**
- Pipedream MCP (Candidate 1) already covers Gmail send
- SMTP is a fallback — not needed if Pipedream works
- Security concern: SMTP credentials handling, spam prevention

**When to revisit:** If Pipedream Gmail integration fails or if SMTP-only email is needed.

---

### CANDIDATE 16: TTS Provider (Text-to-Speech)

**Status:** DEFER
**Type:** Adapter or ISOLATED_WORKER
**Boundary:** `adapters/` or separate process
**LOC to integrate:** ~200

**What it is:** TTS service (ElevenLabs, OpenAI TTS, or local Coqui TTS) for voice_assistant template's reply_voice step.

**Why defer:**
- Only 1 template needs TTS (voice_assistant)
- voice_assistant itself is DEFERRED (needs Pipecat or equivalent)
- If voice_assistant is prioritized, TTS can be added as a thin adapter at that time

**When to revisit:** When voice_assistant template is prioritized.

---

## 6. Implementation Sequence

Ordered by: blocked templates unlocked × architectural fit × low resource cost × low complexity.

### Wave 1 — Zero-Code MCP Deployment (0 LOC, 18 templates unlocked)

| Order | Candidate | Action | Templates Unlocked |
|-------|-----------|--------|-------------------|
| 1 | Pipedream MCP | Add to MCP config, authenticate apps | 18 (communication, calendar, email, GitHub, Drive) |
| 2 | Playwright (confirm) | Verify existing browser facade covers all 13 commands | 3 (browser monitoring) |

**Wave 1 total:** 0 LOC, ~100 MB resource cost, 21 templates unblocked.

### Wave 2 — Thin Adapters (500 LOC, 3 templates unlocked)

| Order | Candidate | Action | LOC | Templates Unlocked |
|-------|-----------|--------|-----|-------------------|
| 3 | Document Processing | `adapters/document/` — PDF extraction | ~200 | 3 (document_summarize, file_extract_to_csv, duplicate_detector) |
| 4 | Communication Adapter | `adapters/communication/` — Telegram/Slack send | ~300 | 0 (already covered by Pipedream, but permanent production path) |

**Wave 2 total:** 500 LOC, ~50 MB resource cost, 3 templates unblocked.

### Wave 3 — Defer-Until-Prerequisites (0 LOC, 0 templates now)

| Order | Candidate | Prerequisite | When |
|-------|-----------|-------------|------|
| 5 | Canva MCP | Document generation templates prioritized | After Wave 1-2 |
| 6 | OpenHands | FQ-02 resolved (autonomous initiative policy) | After Gate C-7 |
| 7 | Pipecat | FQ-04 resolved (server deployment) + voice priority | After deployment decision |
| 8 | Graphiti | FQ-05 resolved (data governance) + AURA Knowledge layer | After Gate C-7 |

---

## 7. Resource Budget Projection

| Wave | Candidate | Est. RAM | Cumulative | Budget Remaining |
|------|-----------|----------|------------|-----------------|
| Current | KIO + Chrome | ~200 MB | 200 MB | 450 MB |
| Wave 1 | Pipedream MCP | ~80 MB | 280 MB | 370 MB |
| Wave 2 | Document adapter | ~30 MB | 310 MB | 340 MB |
| Wave 2 | Communication adapter | ~20 MB | 330 MB | 320 MB |
| Wave 3 | Canva MCP | ~20 MB | 350 MB | 300 MB |
| **Maximum** | All Wave 1+2+3 | — | **350 MB** | **300 MB** |

**Assessment:** Waves 1-3 fit comfortably within 650 MB budget. OpenHands, Pipecat, and Graphiti would push to 550-850 MB — too close or over budget.

---

## 8. Security Assessment

| Candidate | Credential Type | Exposure | Risk Level | Mitigation |
|-----------|----------------|----------|------------|------------|
| Pipedream MCP | API key + OAuth tokens | Local process, outbound API | LOW | OAuth managed by Pipedream, not KIO |
| Canva MCP | API key | Outbound API | LOW | API key in env only |
| Playwright | None | Local browser | LOW | Already validated |
| GitHub MCP | PAT | Outbound API | LOW | PAT in env only |
| Google MCP | OAuth2 | Outbound API | LOW | OAuth managed by MCP server |
| Document adapter | None | Local file processing | LOW | Path traversal protection in execution_boundary |
| Communication adapter | Bot tokens | Outbound messaging | MEDIUM | Message content gated by execution_boundary |
| OpenHands | N/A | Code execution | HIGH | Deferred — sandboxing required |
| Pipecat | WebRTC + API keys | Network ports | HIGH | Deferred — network exposure changes |
| Graphiti | DB credentials | Data persistence | HIGH | Deferred — FQ-05 prerequisite |
| Docker MCP | N/A | Container overhead | MEDIUM | REJECTED — duplicates existing capability |

---

## 9. Conflict Analysis

| Candidate | Conflicts With | Resolution |
|-----------|---------------|------------|
| Pipedream MCP | Communication adapter (Candidate 7) | Pipedream = rapid unblock. Communication adapter = permanent production path. Run both; Pipedream is interim. |
| Canva MCP | Document adapter (Candidate 6) | Document adapter = extraction (PDF→text). Canva = generation (content→PDF/DOCX/PPTX). Complementary, not conflicting. |
| Docker MCP Gateway | `mcp_runtime/` | REJECTED. Constitutional violation — one MCP gateway. |
| Graphiti | `mini_kio/knowledge/` | DEFERRED — would require knowledge subsystem rewrite. |

---

## 10. Risk Register

| Risk | Probability | Impact | Mitigation |
|------|-------------|--------|------------|
| Pipedream MCP tool count overwhelms LLM context | MEDIUM | MEDIUM | Filter tools per-template; only expose relevant tools per flow |
| Pipedream service outage blocks all templates | LOW | HIGH | Communication adapter (Candidate 7) provides fallback path |
| OAuth token expiry breaks automated flows | MEDIUM | LOW | Pipedream handles refresh; monitor health |
| Document adapter PDF parsing failures | LOW | LOW | Fall back to Canva MCP for document extraction |
| Resource budget overrun with all candidates | LOW | MEDIUM | Wave 3 candidates deferred until budget confirmed |
| Playwright browser crash during monitoring templates | MEDIUM | LOW | Existing crash recovery in browser/ already handles |

---

## 11. Rollback Matrix

| Candidate | Rollback Action | LOC Reverted | Risk |
|-----------|----------------|--------------|------|
| Pipedream MCP | Remove from MCP config | 0 | NONE |
| Canva MCP | Remove from MCP config | 0 | NONE |
| Playwright | N/A (already integrated) | 0 | NONE |
| GitHub MCP | Remove from MCP config | 0 | NONE |
| Google MCP | Remove from MCP config | 0 | NONE |
| Document adapter | Remove `adapters/document/` | ~200 | LOW |
| Communication adapter | Remove `adapters/communication/` | ~300 | LOW |
| OpenHands | N/A (deferred) | 0 | NONE |
| Pipecat | N/A (deferred) | 0 | NONE |
| Graphiti | N/A (deferred) | 0 | NONE |

---

## 12. Validation Checklist

Before each candidate is promoted from READY to IMPLEMENTED:

- [ ] MCP tool or adapter action executes end-to-end
- [ ] `execution_boundary.py` SafetyState gates the capability
- [ ] Credential handling passes security review (no secrets in output/logs)
- [ ] Resource usage stays within 650 MB budget
- [ ] Template step that was BLOCKED now produces correct output
- [ ] Rollback path confirmed (config removal or adapter deletion)
- [ ] Regression suite passes (83/83 baseline maintained)
- [ ] Production Telegram validation passes for messaging templates

---

## 13. Decision Summary

| Status | Count | Candidates |
|--------|-------|-----------|
| READY | 4 | Pipedream MCP, Playwright, GitHub MCP, Google MCP |
| READY_WITH_ADAPTER | 3 | Canva MCP, Document adapter, Communication adapter |
| ISOLATED_WORKER | 2 | OpenHands, Pipecat |
| DEFER | 4 | Graphiti, OpenViking, Remaining gaps, TTS |
| REFERENCE_ONLY | 1 | Agent Skills sources (pattern reference only) |
| REJECT | 1 | Docker MCP Gateway |

**Net result:** 21 of 25 BLOCKED templates have a clear path to unblocked via Wave 1 (Pipedream MCP + Playwright) and Wave 2 (Document + Communication adapters). The remaining 4 BLOCKED templates (webhook, form, poll, sync) need custom integration after Pipedream proves the MCP pattern.

---

## 14. Recommendation

**Execute Wave 1 immediately.** Pipedream MCP is the single highest-leverage integration: 0 LOC, 18 templates unlocked, zero architectural risk, fits existing MCP runtime. Combined with Playwright confirmation, Wave 1 unblocks 21 of 25 BLOCKED templates with no code changes.

**Do not implement Wave 2 or Wave 3 until Wave 1 is validated in production.** The Communication adapter (Candidate 7) is the permanent production path for messaging, but Pipedream proves the pattern first. The Document adapter (Candidate 6) is valuable but lower priority than confirming Wave 1 works.

**Defer OpenHands, Pipecat, Graphiti entirely.** All three exceed resource budget or violate architectural constraints. Revisit only after prerequisite founder decisions are resolved.

---

**END OF PHASE 5 STEP 0 DELIVERABLE**
