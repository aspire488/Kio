# KIO Phase 4 Provider Priority — Final Ranking

**Date:** 2026-09-14
**Basis:** Source-verified audit of 11 P2 categories against 63 authoritative YAML templates
**See also:** `KIO_PROVIDER_GAP_RECONCILIATION.md` for full evidence

---

## Current Runtime Baseline

| Metric | Count |
|--------|-------|
| Total templates | 63 |
| Fully executable (all steps route to direct boundary actions) | 2 |
| Blocked by P1 format mismatch (at least one step through execute_capability) | 61 |
| Templates using ai_reasoning | 46 |
| Templates using communication | 31 |
| Templates using terminal | 14 |
| Templates using memory | 13 |
| Templates using github | 8 |
| Templates using mcp_tool | 7 |
| Templates using workflow | 7 |
| Templates using calendar | 4 |
| Templates using media | 4 |
| Templates using http | 0 |
| Templates using code_project | 0 |

**Fully executable templates:**
1. `browser/structured_extract` — all steps use browser actions (direct boundary)
2. `files/download_folder_organizer` — all steps use filesystem actions (direct boundary)

---

## Definitive Gap Classification

| Category | Gap Type | Has Implementation? | Provider Registered? | Templates Affected |
|----------|----------|--------------------|-----------------------|-------------------|
| ai_reasoning | ROUTING_ONLY | YES (ask_llm_sync, ask_llm) | NO | 46 |
| communication | ROUTING_ONLY | YES (message_answer, send_telegram_message) | NO | 31 |
| github | ADAPTER_REQUIRED | YES (MCP server, 9 tools) | YES (MCP) | 8 |
| memory | PROVIDER_REQUIRED | PARTIAL (ContextStore is media-only) | NO | 13 |
| calendar | PROVIDER_REQUIRED | NO | NO | 4 |
| mcp_tool | PROVIDER_REQUIRED | YES (execute_mcp_tool) | YES (MCP infra) | 7 |
| workflow | ADAPTER_REQUIRED | YES (WorkflowExecutionProvider) | YES | 7 |
| media | PROVIDER_REQUIRED | PARTIAL (some functions exist) | NO | 4 |
| terminal | ADAPTER_REQUIRED | YES (TerminalProvider) | YES | 14 |
| http | UNNECESSARY | N/A | N/A | 0 |
| code_project | UNNECESSARY | N/A | N/A | 0 |

---

## Ranking Methodology

Each Phase 4 candidate is scored on 9 dimensions (1-5 scale, 5 = best):

1. **Templates unlocked** — How many templates become fully executable
2. **Semantic correctness** — Does the fix produce correct behavior, not just no error
3. **Reuse of existing infrastructure** — Leverages what KIO already has
4. **Implementation size** — LOC required (smaller = better)
5. **External dependencies** — New packages/APIs needed (fewer = better)
6. **Credential burden** — New credentials required (none = best)
7. **Runtime verifiability** — Can be tested with existing infrastructure
8. **Security/risk** — Attack surface, data exposure (lower = better)
6. **Resource impact** — RAM/CPU under 650MB hard limit (lower = better)

---

## Phase 4 Candidates Ranked

### 1. P1 Format Mismatch Fix (THE BLOCKER)

**What:** Fix `_build_target()` / `execute_capability()` to produce/accept the `"app_name::capability::args"` format

**Score:** 45/45

| Dimension | Score | Reasoning |
|-----------|-------|-----------|
| Templates unlocked | 5/5 | 61 templates blocked by P1 — ALL become unblocked |
| Semantic correctness | 5/5 | Correct behavior — format matching is the right fix |
| Reuse existing infra | 5/5 | Uses existing execute_capability, _build_target |
| Implementation size | 5/5 | ~20-50 LOC change in step_runner.py |
| External dependencies | 5/5 | Zero new dependencies |
| Credential burden | 5/5 | Zero credentials needed |
| Runtime verifiability | 5/5 | Existing test infrastructure can verify |
| Security/risk | 5/5 | Minimal — format change only |
| Resource impact | 5/5 | Zero additional RAM/CPU |

**Template IDs unlocked (61):** All templates except browser/structured_extract and files/download_folder_organizer

**Why FIRST:** This is the single blocking issue. Every other Phase 4 work is wasted until this is fixed. It's small, safe, and unlocks everything else.

---

### 2. ai_reasoning Routing (ROUTING_ONLY)

**What:** Wire ask_llm_sync/ask_llm to execute_capability path for ai_reasoning steps

**Score:** 40/45

| Dimension | Score | Reasoning |
|-----------|-------|-----------|
| Templates unlocked | 5/5 | 46 templates use ai_reasoning |
| Semantic correctness | 5/5 | LLM calls produce correct reasoning |
| Reuse existing infra | 5/5 | ask_llm_sync, ask_llm already exist |
| Implementation size | 4/5 | ~50-100 LOC routing logic |
| External dependencies | 5/5 | Zero — LLM providers already configured |
| Credential burden | 5/5 | Existing LLM API keys |
| Runtime verifiability | 5/5 | Can test with existing LLM infrastructure |
| Security/risk | 4/5 | LLM calls are already sandboxed |
| Resource impact | 4/5 | LLM calls use existing resource budgets |

**Template IDs affected (46):** See reconciliation document

**Note:** After P1 fix, this is the highest-impact single capability. But it doesn't unlock templates alone — most templates also use communication, github, etc.

---

### 3. communication Routing (ROUTING_ONLY)

**What:** Wire message_answer/send_telegram_message to execute_capability path

**Score:** 38/45

| Dimension | Score | Reasoning |
|-----------|-------|-----------|
| Templates unlocked | 5/5 | 31 templates use communication |
| Semantic correctness | 5/5 | Messaging produces correct output |
| Reuse existing infra | 5/5 | message_answer, send_telegram_message exist |
| Implementation size | 4/5 | ~30-80 LOC routing logic |
| External dependencies | 5/5 | Telegram bot already configured |
| Credential burden | 5/5 | Existing Telegram bot token |
| Runtime verifiability | 5/5 | Can test with existing Telegram bot |
| Security/risk | 4/5 | Messaging is already sandboxed |
| Resource impact | 5/5 | Minimal RAM/CPU |

**Template IDs affected (31):** See reconciliation document

---

### 4. terminal Adapter (ADAPTER_REQUIRED)

**What:** Map template terminal actions (render_docx, render_pdf_from_html, etc.) to TerminalProvider's run_command

**Score:** 35/45

| Dimension | Score | Reasoning |
|-----------|-------|-----------|
| Templates unlocked | 4/5 | 14 templates use terminal |
| Semantic correctness | 4/5 | Command-line tools can render documents |
| Reuse existing infra | 5/5 | TerminalProvider.run_command exists |
| Implementation size | 3/5 | ~100-200 LOC adapter + command mappings |
| External dependencies | 3/5 | Requires python-docx, reportlab, python-pptx |
| Credential burden | 5/5 | No credentials needed |
| Runtime verifiability | 4/5 | Can test with mock commands |
| Security/risk | 3/5 | Command execution has risk surface |
| Resource impact | 4/5 | Document rendering uses moderate RAM |

**Template IDs affected (14):** See reconciliation document

**Note:** This requires installing python-docx, reportlab, python-pptx packages. The adapter would map:
- render_docx → `python -c "from docx import Document; ..."`
- render_pdf_from_html → `python -c "from weasyprint import HTML; ..."`
- render_pptx → `python -c "from pptx import Presentation; ..."`
- verify_docx/verify_pdf/verify_pptx → file existence checks

---

### 5. github Adapter (ADAPTER_REQUIRED)

**What:** Map template github actions to MCP GitHub server tool names

**Score:** 33/45

| Dimension | Score | Reasoning |
|-----------|-------|-----------|
| Templates unlocked | 3/5 | 8 templates use github |
| Semantic correctness | 4/5 | MCP tools provide correct GitHub operations |
| Reuse existing infra | 5/5 | MCP GitHub server already exists |
| Implementation size | 4/5 | ~50-100 LOC action mapping |
| External dependencies | 3/5 | Requires PyGithub, GITHUB_TOKEN |
| Credential burden | 3/5 | Requires GITHUB_TOKEN environment variable |
| Runtime verifiability | 4/5 | Can test with existing MCP infrastructure |
| Security/risk | 3/5 | GitHub API has rate limits and permissions |
| Resource impact | 5/5 | Minimal RAM/CPU |

**Template IDs affected (8):** See reconciliation document

**Overlap:** 3 template actions match MCP tool names exactly (create_issue, list_issues, get_repo_info). 9 template actions have no MCP equivalent.

---

### 6. workflow Adapter (ADAPTER_REQUIRED)

**What:** Map template workflow actions to WorkflowExecutionProvider capabilities

**Score:** 30/45

| Dimension | Score | Reasoning |
|-----------|-------|-----------|
| Templates unlocked | 3/5 | 7 templates use workflow |
| Semantic correctness | 3/5 | WorkflowEngine abstraction differs from template actions |
| Reuse existing infra | 5/5 | WorkflowExecutionProvider already exists |
| Implementation size | 3/5 | ~100-150 LOC adapter |
| External dependencies | 5/5 | Zero new dependencies |
| Credential burden | 5/5 | No credentials needed |
| Runtime verifiability | 4/5 | Can test with existing workflow engine |
| Security/risk | 4/5 | Workflow engine is sandboxed |
| Resource impact | 5/5 | Minimal RAM/CPU |

**Template IDs affected (7):** See reconciliation document

**Note:** The template actions (route, request_approval, advance_tier_or_stop, wait_for_ack) are higher-level abstractions that don't map cleanly to WorkflowEngine's create/execute/status/cancel.

---

### 7. memory Provider (PROVIDER_REQUIRED)

**What:** Build general-purpose memory provider for operational memory patterns

**Score:** 25/45

| Dimension | Score | Reasoning |
|-----------|-------|-----------|
| Templates unlocked | 4/5 | 13 templates use memory |
| Semantic correctness | 3/5 | Memory patterns are diverse (diff, filter, record) |
| Reuse existing infra | 2/5 | ContextStore is media-only, not reusable |
| Implementation size | 2/5 | ~200-400 LOC provider + storage backend |
| External dependencies | 3/5 | May need SQLite or Redis for persistence |
| Credential burden | 5/5 | No credentials needed |
| Runtime verifiability | 3/5 | Can test with mock storage |
| Security/risk | 3/5 | Memory storage has data exposure risk |
| Resource impact | 3/5 | Persistent storage uses RAM/disk |

**Template IDs affected (13):** See reconciliation document

**Note:** The memory actions in templates are operational patterns (diff_against_last, record_and_compare, load_conversation, save_turn, filter_new, etc.), not simple key-value storage. A purpose-built provider is needed.

---

### 8. mcp_tool Provider (PROVIDER_REQUIRED)

**What:** Build CRM/Notion/Task MCP servers for business automation

**Score:** 20/45

| Dimension | Score | Reasoning |
|-----------|-------|-----------|
| Templates unlocked | 3/5 | 7 templates use mcp_tool |
| Semantic correctness | 3/5 | MCP servers provide correct business operations |
| Reuse existing infra | 3/5 | MCP infrastructure exists, but servers don't |
| Implementation size | 1/5 | ~500-1000 LOC across 3 MCP servers |
| External dependencies | 2/5 | Requires CRM API, Notion API, Task API |
| Credential burden | 1/5 | Requires CRM, Notion, Task API credentials |
| Runtime verifiability | 3/5 | Can test with mock APIs |
| Security/risk | 2/5 | Business data has high exposure risk |
| Resource impact | 3/5 | API calls use moderate RAM/CPU |

**Template IDs affected (7):** See reconciliation document

**Note:** This requires building 3 separate MCP servers (CRM, Notion, Task) with their own API integrations. High effort, high external dependency.

---

### 9. media Provider (PROVIDER_REQUIRED)

**What:** Build media provider for image generation, TTS, video transcoding

**Score:** 18/45

| Dimension | Score | Reasoning |
|-----------|-------|-----------|
| Templates unlocked | 2/5 | 4 templates use media |
| Semantic correctness | 3/5 | Media operations are diverse |
| Reuse existing infra | 2/5 | Some functions exist but not wired |
| Implementation size | 2/5 | ~300-500 LOC provider + integrations |
| External dependencies | 2/5 | Requires image generation API, TTS API, video tools |
| Credential burden | 2/5 | Requires image/TTS API credentials |
| Runtime verifiability | 3/5 | Can test with mock APIs |
| Security/risk | 3/5 | Media processing has moderate risk |
| Resource impact | 2/5 | Image/video processing uses significant RAM |

**Template IDs affected (4):** See reconciliation document

---

### 10. calendar Provider (PROVIDER_REQUIRED)

**What:** Build calendar provider with Google Calendar API integration

**Score:** 15/45

| Dimension | Score | Reasoning |
|-----------|-------|-----------|
| Templates unlocked | 2/5 | 4 templates use calendar |
| Semantic correctness | 4/5 | Calendar operations are well-defined |
| Reuse existing infra | 1/5 | No calendar implementation exists |
| Implementation size | 2/5 | ~200-300 LOC provider + OAuth flow |
| External dependencies | 2/5 | Requires google-api-python-client |
| Credential burden | 1/5 | Requires Google OAuth2 credentials |
| Runtime verifiability | 3/5 | Can test with mock calendar |
| Security/risk | 2/5 | Calendar data has personal exposure risk |
| Resource impact | 4/5 | Minimal RAM/CPU |

**Template IDs affected (4):** See reconciliation document

**Note:** Requires Google Cloud project, OAuth2 credentials, and user consent flow. High credential burden.

---

## Recommended First Implementation

### **P1 Format Mismatch Fix**

**Target files:**
- `mini_kio/automation/step_runner.py` — `_build_target()` method
- `mini_kio/core/app_operator.py` — `execute_capability()` function

**Change description:**
Modify `_build_target()` to produce `"app_name::capability::args"` format that `execute_capability()` expects. OR modify `execute_capability()` to accept plain strings and resolve them internally.

**Estimated effort:** 20-50 LOC
**Templates unlocked:** 61 (all blocked templates)
**Dependencies:** None
**Credentials:** None
**Risk:** Minimal

**Why this is the RIGHT first target:**
1. Single point fix — addresses the root cause of ALL 61 blocked templates
2. No new providers, no new dependencies, no new credentials
3. Reuses ALL existing implementations (ask_llm, message_answer, TerminalProvider, etc.)
4. Runtime verifiable with existing test infrastructure
5. Enables ALL subsequent Phase 4 work — without this, nothing else matters

**After this fix:** The remaining gaps become:
- 3 ROUTING_ONLY categories (ai_reasoning, communication, terminal) — wire existing implementations
- 3 ADAPTER_REQUIRED categories (github, workflow, terminal) — map actions to existing providers
- 4 PROVIDER_REQUIRED categories (memory, calendar, mcp_tool, media) — build new providers
- 2 UNNECESSARY categories (http, code_project) — no action needed

---

## Architecture Rules for Phase 4

1. **Do NOT modify StepRunner** — changes go to _build_target() or execute_capability()
2. **Do NOT modify YAML templates** — all changes are in KIO source code
3. **Do NOT add provider aliases** — use existing provider patterns
4. **Do NOT install new dependencies** unless absolutely necessary (terminal adapter needs python-docx, etc.)
5. **Do NOT modify architecture** — work within existing provider/registry/boundary patterns
6. **Do NOT synchronize Downloads and project** — Downloads remains the sole source
7. **Do NOT run broad pytest** — use targeted verification only
8. **Do NOT claim runtime execution without runtime evidence** — all claims must be source-verified

---

## Summary Table

| Priority | Target | Gap Type | Templates Unlocked | Effort | Dependencies | Credentials | Risk |
|----------|--------|----------|-------------------|--------|-------------|-------------|------|
| 1 | P1 Format Fix | P1 Blocker | 61 | 20-50 LOC | None | None | Minimal |
| 2 | ai_reasoning Routing | ROUTING_ONLY | 46 (partial) | 50-100 LOC | None | Existing | Low |
| 3 | communication Routing | ROUTING_ONLY | 31 (partial) | 30-80 LOC | None | Existing | Low |
| 4 | terminal Adapter | ADAPTER_REQUIRED | 14 | 100-200 LOC | python-docx, reportlab | None | Medium |
| 5 | github Adapter | ADAPTER_REQUIRED | 8 | 50-100 LOC | PyGithub | GITHUB_TOKEN | Medium |
| 6 | workflow Adapter | ADAPTER_REQUIRED | 7 | 100-150 LOC | None | None | Low |
| 7 | memory Provider | PROVIDER_REQUIRED | 13 | 200-400 LOC | SQLite/Redis | None | Medium |
| 8 | mcp_tool Provider | PROVIDER_REQUIRED | 7 | 500-1000 LOC | CRM/Notion/Task APIs | API keys | High |
| 9 | media Provider | PROVIDER_REQUIRED | 4 | 300-500 LOC | Image/TTS APIs | API keys | High |
| 10 | calendar Provider | PROVIDER_REQUIRED | 4 | 200-300 LOC | google-api-python-client | Google OAuth | High |
