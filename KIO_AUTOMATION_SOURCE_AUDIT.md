# KIO Automation Source Audit — Phase 0

**Date**: 2026-09-13
**Status**: COMPLETE
**Purpose**: Map every integration surface between the 63 automation templates and the existing KIO codebase. Prerequisite for all implementation phases.

---

## 1. Automation Package Summary

| Property | Value |
|---|---|
| Library version | `1.0.0+612577cb612a74b7` |
| Canonical templates | 63 |
| Candidates | 10 (NEVER production-selectable) |
| Categories | 12 (artifacts, browser, business, communication, data, development, files, media, monitoring, productivity, research, ai) |
| Trigger types | natural_language, schedule, file_watch, event, poll, webhook, email_received, message_received, manual |
| Security classifications | read_only, low, consequential, destructive |
| Schema version | kio_template.schema.json (JSON Schema 2020-12) |

### Risk Distribution
- **read_only**: ~25 templates (CI alerts, monitors, health reports, research, structured extract, etc.)
- **low**: ~18 templates (artifacts, notify, calendar_to_status, etc.)
- **consequential**: ~20 templates (file moves, CRM, deploys, credential refresh, data transforms, etc.)
- **destructive**: 0 in canonical (candidates only)

---

## 2. KIO Architecture Summary (Existing)

### 2a. Pipeline Flow
```
Input → Normalize → Classify → Resolve → Execute → Compose → Output
```
- `Pipeline` class: `mini_kio/core/pipeline/__init__.py` (~9547 lines)
- Single routing authority; no competing routers
- `_StaleWorkTracker`: per-session superseded request abandonment

### 2b. Key Abstractions

| Abstraction | Location | Role |
|---|---|---|
| `Pipeline` | `mini_kio/core/pipeline/__init__.py:343` | Single routing authority |
| `_IntentClassifier` | pipeline/__init__.py:1853 | Classifies messages → `RoutingDecision` |
| `_CapabilityResolver` | pipeline/__init__.py:6001 | Maps `RoutingDecision` → (capability, params) |
| `_ExecutionCoordinator` | pipeline/__init__.py:6117 | Dispatches to handler by capability name |
| `CapabilityRegistry` | `mini_kio/core/capability_registry.py` | Dynamic capability discovery, MCP tool delegation |
| `ProviderRegistry` | `mini_kio/core/provider_registry.py` | Singleton: capability → `ExecutionProvider` |
| `ContextManager` | `mini_kio/core/context_manager.py` | Per-session state, continuation detection, referent resolution |
| `ExecutionBoundary` | `mini_kio/core/execution_boundary.py:761` | `execute_action()`: safety gate, RAM check, operator dispatch |
| `CredentialVault` | `mini_kio/core/credential_vault.py` | Keyring-backed secrets, SQLite metadata, Slice 8/9 lifecycle |
| `KioRuntime` | `mini_kio/core/runtime.py` | Singleton runtime, `SafetyState`, `ResourceGuard`, integrity tracking |
| `ObservationBus` | `runtime/observation_bus.py` | Async pub/sub for observations |
| `EventBus` | `communication/event_bus.py` | Protocol-only: `Event`, `Publisher`, `Subscriber` |
| `workflows.py` | `mini_kio/execution/workflows.py` | **DISABLED** — stub, returns "handled via n8n" |

### 2c. IntentType Enum (Pipeline Routing)
```python
class IntentType(enum.Enum):
    UNKNOWN, GREETING, SOCIAL, IDENTITY, DESKTOP_OPEN, DESKTOP_CLOSE,
    SEARCH, MEDIA_PLAY, MEDIA_TRANSPORT, BROWSER_FOCUS, BROWSER_TABS,
    BROWSER_NAVIGATE, SYSTEM, OPERATIONAL, CONVERSATION, KNOWLEDGE,
    MULTI_STEP, ENTITY_QUERY, INFORMATION, MEMORY, FILE, MCP,
    CREDENTIAL, DESKTOP_ACTION, UTILITY, SIMULATE
```

### 2d. Capability → Handler Dispatch Map
```python
# _ExecutionCoordinator._dispatch (pipeline/__init__.py:6136)
{
    "desktop": _exec_desktop,
    "media": _exec_media,
    "browser": _exec_browser,
    "conversation": _exec_conversation,
    "knowledge": _exec_knowledge,
    "system": _exec_system,
    "operational": _exec_operational,
    "file": _exec_desktop,           # ← shares desktop handler
    "coordinator": _exec_coordinator,
    "memory": _exec_memory,
    "desktop_action": _exec_desktop_action,
    "mcp": _exec_conversation,       # ← shares conversation handler
    "credential": _exec_credential,
    "utility": _exec_utility,
    "simulate": _exec_simulate,
}
```

### 2e. Execution Boundary Contract
- `execute_action(action, target)` is the **single runtime-owned handoff**
- LLM-derived intents are **untrusted** until validated
- Gate 2.5: Safety policy check, degraded throttling, RAM capacity check
- `_apply_verification()`: attaches `outcome_class`, `verification_status`, `failure_class`
- `_BLOCKED_ACTIONS`: destructive actions blocked during Gate 0
- `PrerequisiteGate`: Slice 7 prerequisite resolution (fail-closed)

### 2f. Credential Vault Invariants
- NEVER store secrets in SQLite (metadata only)
- NEVER log/print/return secret material
- NEVER fabricate a missing credential
- Storage requires EXPLICIT user consent (`consent=True`)
- Retrieval gated: only Execution Gate consumes secrets
- Lifecycle states: valid, missing, expired, revoked, unavailable, refreshable

### 2g. Disabled Systems
- `workflows.py`: **DISABLED** — "Workflows are handled via n8n integration — not available locally yet"
- Test file confirms: "Joel explicitly rejected n8n automation — wants code-first approach only"
- No scheduler, no cron runner, no file watcher, no event-driven trigger system exists in KIO today

---

## 3. A–AC Integration Surface Audit

### A. Intent Classification Gap
- **Template trigger types**: `natural_language`, `schedule`, `file_watch`, `event`, `poll`, `webhook`, `email_received`, `message_received`, `manual`
- **KIO IntentType**: Only `MULTI_STEP` and `CONVERSATION` could partially cover `natural_language` triggers
- **Gap**: No `AUTOMATION` or `WORKFLOW` intent type exists. No classification path for schedule/file_watch/event/webhook/poll triggers
- **Impact**: ~45 templates (non-natural_language triggers) have no KIO routing path today

### B. Execution Coordinator Gap
- **Template step capabilities**: `ai_reasoning`, `browser`, `filesystem`, `artifact`, `code_project`, `communication`, `workflow`, `monitoring`, `github`, `calendar`, `email`, `mcp_tool`, `media`, `memory`, `http`
- **KIO handler map**: `desktop`, `media`, `browser`, `conversation`, `knowledge`, `system`, `operational`, `file`, `coordinator`, `memory`, `desktop_action`, `mcp`, `credential`, `utility`, `simulate`
- **Overlap**: `browser`, `media`, `memory`, `mcp` (mcp_tool→mcp), `filesystem` (file→desktop)
- **Gap**: No handler for `artifact`, `code_project`, `workflow`, `monitoring`, `github`, `calendar`, `email`, `http`, `ai_reasoning`
- **Impact**: ~80% of template steps cannot dispatch through existing coordinator

### C. Multi-Step Execution Engine Gap
- **Template pattern**: Steps with `depends_on`, `when` gates, `on_error` retry/fallback, `goto` for repair loops
- **KIO multi-step**: `_classify_multi_step()` only detects "and" conjunctions → splits into independent commands. No DAG execution, no step chaining, no conditional gates, no retry/fallback
- **Impact**: Every template's step chain (avg 4-6 steps) would need a new executor

### D. Scheduler/Cron Gap
- **Templates using `schedule` trigger**: `development.dependency_monitor`, `development.repo_backup`, `development.repo_health_report`, `browser.page_change_monitor`, `browser.price_monitor`, `monitoring.rss_news_monitor`, `monitoring.website_uptime`, `research.competitor_monitor`, `research.daily_brief`, `research.youtube_summary`, `productivity.ecosystem_briefing`, `productivity.meeting_prep`, `productivity.morning_briefing`, `productivity.weekly_review`, `business.crm_followup`, `data.api_poll_to_store`, `data.record_sync` — **17 templates**
- **KIO scheduler**: None. No cron runner, no background task scheduler exists
- **Gap**: Entirely new subsystem needed

### E. File Watcher Gap
- **Templates using `file_watch` trigger**: `files.document_summarize`, `files.download_folder_organizer`, `files.drive_to_social`, `files.invoice_extract_to_sheet`, `ai.transcribe_summarize`, `data.file_extract_to_csv` — **6 templates**
- **KIO file watcher**: None
- **Gap**: Entirely new subsystem needed

### F. Event/Webhook/Email/Message Trigger Gap
- **Templates using `event` trigger**: `development.ci_failure_alert`, `development.github_issue_triage`, `development.issue_to_implementation`, `development.pr_review_prep`, `development.release_changelog`, `communication.escalation_alert`, `communication.notify`, `communication.workflow_failure_alert`, `data.form_intake`, `data.knowledge_base_sync`, `monitoring.security_scan_alert`, `ai.classify_and_route`, `ai.extract_to_structured` — **13 templates**
- **Templates using `webhook`**: `business.lead_intake_crm`, `data.webhook_to_store` — **2 templates**
- **Templates using `email_received`**: `productivity.email_label_ai`, `productivity.email_to_calendar`, `productivity.email_to_task`, `business.email_autoresponder_approval`, `business.support_ticket_triage` — **5 templates**
- **Templates using `message_received`**: `communication.chat_assistant`, `communication.voice_assistant` — **2 templates**
- **KIO trigger infrastructure**: None for event/webhook/email. `ObservationBus` exists but is internal pub/sub, not an inbound trigger system
- **Gap**: Inbound HTTP server for webhooks, IMAP/polling for email, GitHub webhook receiver

### G. Artifact Operator Gap
- **Templates using `artifact` capability**: `artifacts.data_to_xlsx`, `artifacts.meeting_to_report`, `artifacts.multiformat_report`, `artifacts.research_to_docx`, `artifacts.research_to_pdf`, `artifacts.research_to_pptx` — **6 templates**
- **KIO artifact operator**: None. No `python-docx`, `openpyxl`, `python-pptx`, `reportlab` integration
- **Gap**: New operator or MCP server for document generation

### H. GitHub Integration Gap
- **Templates using `github` capability**: `development.ci_failure_alert`, `development.github_issue_triage`, `development.issue_to_implementation`, `development.pr_review_prep`, `development.release_changelog`, `development.repo_backup`, `development.repo_health_report` — **7 templates**
- **KIO GitHub**: None. No `PyGithub`, no GitHub MCP server configured
- **Gap**: MCP server or operator for GitHub API

### I. Calendar Integration Gap
- **Templates using `calendar` capability**: `productivity.calendar_to_status`, `productivity.email_to_calendar`, `productivity.meeting_prep`, `productivity.morning_briefing` — **4 templates**
- **KIO calendar**: None
- **Gap**: Google Calendar MCP server or operator

### J. Email Integration Gap
- **Templates using `email` capability**: `productivity.email_label_ai`, `productivity.email_to_calendar`, `productivity.email_to_task`, `business.email_autoresponder_approval`, `business.support_ticket_triage` — **5 templates**
- **KIO email**: None
- **Gap**: IMAP/SMTP integration or MCP server

### K. HTTP Client Gap
- **Templates using `http` capability**: `data.api_poll_to_store`, `data.webhook_to_store`, `monitoring.website_uptime`, `research.web_scrape_to_report`, `browser.structured_extract` — **5 templates**
- **KIO HTTP**: `search_web` exists in browser_operator but is web search, not generic HTTP. `requests` available in stdlib
- **Gap**: Generic HTTP step executor (or reuse `requests` directly in step runner)

### L. Monitoring/Health Check Gap
- **Templates using `monitoring` capability**: `monitoring.inbox_monitor`, `monitoring.rss_news_monitor`, `monitoring.security_scan_alert`, `monitoring.website_uptime` — **4 templates**
- **KIO monitoring**: `operational_health.py` exists but is KIO-internal health, not external monitoring
- **Gap**: Generic poll/check pattern executor

### M. Code Project Operator Gap
- **Templates using `code_project` capability**: `development.scaffold_project`, `development.issue_to_implementation` — **2 templates**
- **KIO code project**: None
- **Gap**: Code scaffolding/implementation executor (or MCP tool delegation)

### N. Workflow Execution Engine Gap
- **Templates using `workflow` capability**: `communication.workflow_failure_alert` — **1 template** (but `workflow` is also listed in capabilities_required by several others)
- **KIO workflow**: **DISABLED** (`workflows.py` stub returns "handled via n8n")
- **Gap**: The entire template system IS the workflow engine. Need: step runner, dependency resolver, error handling, retry

### O. Credential Lifecycle Gap
- **Templates requiring credentials**: 55 of 63 templates declare `credentials_required`
- **Credential types in templates**: `llm`, `oauth2`, `api_key`, `bot_token`, `service_account`, `basic_auth`, `none`
- **KIO credential types**: `valid`, `missing`, `expired`, `revoked`, `unavailable`, `refreshable`
- **Overlap**: Good. KIO's `CredentialVault` lifecycle maps well to template needs
- **Gap**: Template `credentials_required` field needs resolution against vault at execution time. No "check all prerequisites before starting" pattern exists

### P. Security Classification Mapping
- **Template classifications**: `read_only`, `low`, `consequential`, `destructive`
- **KIO safety states**: `NORMAL`, `DEGRADED`, `EMERGENCY`, `LOCKDOWN`
- **KIO execution boundary**: `check_safety_policy()` exists, `_BLOCKED_ACTIONS` exists
- **Gap**: Template `security_classification` must map to KIO safety policy. `consequential`/`destructive` templates must require user confirmation via existing `check_safety_policy()`. This is a policy bridge, not a new system

### Q. User Confirmation Flow
- **Template field**: `user_confirmation_required: true` for consequential/destructive
- **KIO confirmation**: `check_safety_policy()` in execution_boundary.py gates destructive actions
- **Gap**: Template's boolean must feed into the safety policy gate. Natural fit — no new mechanism needed

### R. Verification System Gap
- **Template verification**: `verification[]` with `type`, `check`, `asserts[]`, `on_fail` (repair/notify/abort/flag)
- **KIO verification**: `_apply_verification()` classifies operator results (SUCCESS/FAILURE/BLOCKED/etc.) — different concern. `PrerequisiteGate` exists but is pre-execution
- **Gap**: Post-execution observable verification (file exists, API returned expected shape, artifact valid) is a new concept. KIO verifies execution outcome, not observable side effects

### S. Failure Recovery Gap
- **Template failure recovery**: `default_retry` (max, backoff), `on_failure` (notify_user/notify_admin/silent_log/abort/rollback), `idempotency_key`
- **KIO failure handling**: `_apply_verification()` classifies failures, `_BLOCKED_ACTIONS` prevents destructive retry. No retry loop, no backoff, no idempotency
- **Gap**: Retry with backoff, failure notification, rollback capability, idempotency keys

### T. Idempotency Gap
- **Template field**: `failure_recovery.idempotency_key` (expressions like `{{ inputs.topic }}-{{ today }}`)
- **KIO idempotency**: None. `_StaleWorkTracker` prevents duplicate concurrent requests but not duplicate side effects across restarts
- **Gap**: Idempotency key store (could be SQLite-backed like existing `FactRepository`)

### U. Template Config Surface Gap
- **Template `config[]`**: User-facing configuration with types (string, number, boolean, file_path, url, datetime, enum, secret_ref), defaults, descriptions
- **KIO config**: No user-facing configuration system for extensible behavior
- **Gap**: Config UI or CLI to let users set template parameters before activation

### V. Template Input Resolution Gap
- **Template `inputs[]`**: Typed input parameters with defaults and validation
- **KIO input**: Text input only via Telegram/Discord. No structured input forms
- **Gap**: For `natural_language` triggers: parameter extraction from utterance (LLM). For scheduled triggers: stored config values

### W. Step Variable Passing Gap
- **Template wiring**: `{{ steps.X.output }}`, `{{ inputs.Y }}`, `{{ config.Z }}`, `{{ trigger.W }}`
- **KIO variable passing**: None. Each handler receives `(params, decision)` and returns a flat dict
- **Gap**: Step runner must maintain a variable context that resolves `{{ }}` references between steps

### X. MCP Server Configuration Gap
- **Templates requiring MCP servers**: 12 templates declare `mcp_servers_required`
- **KIO MCP**: `mcp/configs/`, `mcp/servers/` directories exist. `CapabilityRegistry` delegates to MCP tools
- **Overlap**: Good. MCP tool delegation is the right pattern for many template capabilities
- **Gap**: Need to know which MCP servers are actually configured and healthy at execution time

### Y. Runtime Resource Expectations Gap
- **Template `resource_expectations`**: `est_runtime_seconds`, `est_peak_ram_mb`, `network`, `spawns_process`
- **KIO resource management**: `ResourceGuard` with `SOFT_LIMIT_MB=350`, `HARD_LIMIT_MB=400`. `check_capacity()` before lazy-load/execution
- **Overlap**: Good. Template RAM estimates can feed `ResourceGuard`
- **Gap**: Pre-execution budget check against `resource_expectations.est_peak_ram_mb` before starting a template run

### Z. Observation/Event Emission Gap
- **Template outputs**: Steps produce `outputs[]`, templates produce `outputs[]`
- **KIO observation**: `emit_runtime_trace()` for internal telemetry. `ObservationBus` for internal pub/sub
- **Gap**: Template execution progress/completion needs to be observable — could use existing `emit_runtime_trace()`

### AA. Provenance Tracking Gap
- **Template `provenance`**: `pattern_family`, `derived_from[]` (with source, url, license, reuse), `license`, `portability_notes`
- **KIO provenance**: None
- **Gap**: Optional — provenance is metadata for templates, not execution concern. Could be useful for audit trail

### AB. Context Manager Extension Gap
- **Template execution**: Needs session context for multi-step runs (variable state, progress, partial results)
- **KIO ContextManager**: `active_domain`, `active_entity`, `last_action`, `recent_targets`, exchange history. No "workflow execution context"
- **Gap**: Workflow run context (current step, variable store, progress) as a new context type or extension

### AC. Candidate Isolation Gap
- **10 candidates**: `candidate_01.yaml` through `candidate_10.yaml` — auto-converted from n8n, NOT production-ready
- **KIO isolation**: No mechanism to load/preview candidates without making them production-selectable
- **Gap**: Candidates directory must be loadable for review but NEVER routed to by `_CapabilityResolver`

---

## 4. Integration Pattern Decision

### What Already Exists (Reuse)
| KIO Abstraction | Template Need | Fit |
|---|---|---|
| `execute_action()` | Step execution | Partial — needs step wrapper |
| `CredentialVault` | Credential resolution | Good — lifecycle maps |
| `check_safety_policy()` | Security gating | Good — classification maps |
| `ResourceGuard` | RAM budget | Good — estimates feed in |
| `emit_runtime_trace()` | Progress telemetry | Good |
| `ContextManager` | Session state | Partial — needs workflow context |
| `_StaleWorkTracker` | Duplicate prevention | Partial — concurrent only |
| `CapabilityRegistry` | MCP delegation | Good |
| `EventBus` protocol | Internal events | Protocol only, needs implementation |

### What Must Be Built
| Component | Templates | Priority |
|---|---|---|
| Template engine (loader, validator, variable resolver) | All 63 | P0 |
| Step runner (DAG executor with depends_on/when/on_error) | All 63 | P0 |
| Scheduler (cron/schedule triggers) | 17 templates | P1 |
| File watcher (file_watch triggers) | 6 templates | P2 |
| Webhook receiver (HTTP inbound) | 2 templates | P2 |
| Email trigger (IMAP polling) | 5 templates | P2 |
| Artifact operator (DOCX/XLSX/PPTX/PDF generation) | 6 templates | P1 |
| GitHub MCP server integration | 7 templates | P1 |
| Retry/backoff engine | ~50 templates | P1 |
| Idempotency key store | ~20 templates | P2 |
| User confirmation flow bridge | ~20 consequential templates | P0 |

---

## 5. Risk Assessment

### Highest Risk
1. **Step runner (C)**: The core missing piece. Every template depends on it. Must not duplicate Pipeline's routing.
2. **Scheduler (D)**: 17 templates need cron-like scheduling. No KIO precedent.
3. **Execution boundary extension (B)**: 80% of template step capabilities have no KIO handler.

### Lowest Risk
1. **Credential mapping (O)**: Existing vault maps well
2. **Security classification (P)**: Safety policy bridge
3. **Resource expectations (Y)**: ResourceGuard exists
4. **MCP delegation (X)**: CapabilityRegistry already does this

### Architectural Invariants to Preserve
1. **No new runtimes**: Template engine must run INSIDE existing KIO process
2. **No new execution engines**: Step runner goes through `execute_action()` or equivalent boundary
3. **No duplicate security gates**: Template security classification feeds existing `check_safety_policy()`
4. **No parallel idempotency**: Single idempotency store shared with existing systems
5. **No template-specific executors**: Each step capability maps to an existing (or MCP) operator

---

## 6. Phase 0 Exit Criteria — MET

- [x] All 63 canonical templates cataloged with trigger types and capabilities
- [x] All 10 candidates cataloged (never production-selectable)
- [x] KIO Pipeline flow mapped end-to-end
- [x] Execution boundary contract documented
- [x] Credential vault lifecycle documented
- [x] Safety state machine documented
- [x] A–AC integration surfaces identified with gap analysis
- [x] Integration pattern decision: reuse vs. build
- [x] Risk assessment complete
- [x] Architectural invariants established

**Ready for Phase 1: Template Engine Design.**
