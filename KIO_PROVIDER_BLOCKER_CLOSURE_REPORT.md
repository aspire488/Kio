# KIO Provider Blocker Closure Report

**Date:** 2026-09-20
**Branch:** `kio-restoration-safety-20260823`
**Scope:** Pre-Phase-7 provider/capability/credential blocker closure (63 recovered workflows)
**Method:** real `AutomationEngine` preflight + real boundary execution. No mocks, no fakes, no simulated external calls.
**Baseline:** `KIO_63_WORKFLOW_RUNTIME_ACCEPTANCE.md` / `KIO_63_RUNTIME_ACCEPTANCE_RAW.json` (commit `656f090`)

---

## 1. Headline Result

| Metric | Baseline (`656f090`) | Now | Δ |
|---|---|---|---|
| Workflows loaded | 63/63 | 63/63 | — |
| Structurally valid | 63/63 | 63/63 | — |
| Steps registered in `_ACTION_MAP` | 221/221 | 221/221 | — |
| **PREFLIGHT_PASS** | **3/63** | **16/63** | **+13** |
| BLOCKED_MISSING_CAPABILITY | 54/63 | 33/63 | −21 |
| BLOCKED_MISSING_CREDENTIAL | 6/63 | 14/63 | +8 (reclassified, see §5) |
| **`ai_reasoning` blocked** | **48/63** | **0/63** | **−48** |
| **`llm_provider` credential failing** | **41/63** | **0/63** | **−41** |
| Real E2E executions verified | 1 | 2 | +1 |

The single dominant blocker (`ai_reasoning`, 48 workflows — 76% of the library) is closed and
live-verified through the real LLM chain.

> **Not claimed:** 63/63 FULL. 33 workflows still block at preflight on capability, and 14 on
> credential. See §5 for the exact remaining contract per workflow.

---

## 2. Root Cause of the Baseline

The baseline was **not** a missing-implementation problem. Two defects produced 54 of the 63
capability blocks:

1. **The availability oracle asked the wrong question.** `automation/capability_resolver.py`
   resolved every workflow capability through `ProviderRegistry.get_provider()` using
   **hardcoded names that do not exist in the registry**:
   - `ai_reasoning` → `["llm", "ai_reasoning"]` — neither was registered (implemented in KIO's
     own capability router, not as a provider).
   - `filesystem` → `["filesystem", "file_system"]` — the registry key is `read_file` /
     `write_csv`, not `filesystem`.
   - `terminal` → `["terminal", ...]` — the registry key is `run_command`.

   A capability whose implementation lives in the capability router (`APP_CAPABILITIES` +
   `execute_capability`) therefore reported **missing even though it worked**, so the engine
   blocked at preflight before ever reaching it.

2. **The capability router discarded provider payloads.** Three branches returned only
   `success`/`message`, dropping the values the step declared as outputs. `_normalize_result`
   additionally let boundary metadata (`category`, …) shadow a same-named payload key. Result:
   steps reported `success: true` with **null outputs**, so downstream `{{ steps.X.field }}`
   references silently resolved to `None`.

The baseline harness also never called `register_all_providers()` (the real runtime does, at
`runtime.py:1472`), so even local capabilities reported unregistered.

---

## 3. Unique Blocker Matrix — Classification and Disposition

Legend (per handoff): **A** implementation exists but unregistered · **B** wrong routing ·
**C** provider exists but not initialized · **D** credential exists but not wired ·
**E** credential genuinely missing · **F** provider genuinely missing ·
**G** external API config missing · **H** KIO capability genuinely missing ·
**I** other concrete runtime defect.

### Closed in this pass

| # | Blocker | Workflows | Class | Root cause (evidence) | Fix |
|---|---|---|---|---|---|
| 1 | `ai_reasoning` capability unresolvable | 48 | **A** | Implemented at `app_operator.py:4897` (`execute_capability` → `ask_llm_sync` → `ask_llm` → `LLMGateway`), but no provider registered under `ai_reasoning`/`llm`. Registry listing confirmed absence. | New `AIReasoningProvider` (thin, health-gated). `health()` is `HEALTHY` only when the real LLM chain has ≥1 provider, else `OFFLINE`. |
| 2 | `llm_provider` credential failing | 41 | **D** | YAML declares `{name: llm_provider, type: llm}`; `CredentialBridge` queried `CredentialVault`, but KIO keeps LLM keys in env-configured provider clients. | `llm_credential_status()` (one shared resolver, used by both credential paths) resolves `type: llm` against the live chain. Reports availability + provider count only — never a secret. |
| 3 | `filesystem` / `terminal` / `code_project` / `knowledge` / `workflow` unresolvable | 23 / 4 / 1 / 10 / 7 | **B** | Registered, but looked up under names the registry does not use. | Mappings corrected to registered capability names (`read_file`, `run_command`, `web_search`, `workflow_execute`). |
| 4 | `artifact` unresolvable | 12 | **B** | Implemented in the capability router; no provider. | Readiness probe: OOXML libraries present (`docx`, `pptx`, `openpyxl`). |
| 5 | `communication` unresolvable | 32 | **B** | Implemented in the router; channel tokens live in config. | Readiness probe: a channel token is configured (telegram/discord). |
| 6 | Monitoring / browser capability names | — | **B** | Same class. | Reuses the boundary's own browser-backend gate and the watch poller check. |
| 7 | Boundary telemetry swallowed capability payload keys | 3 declared outputs directly (`category` ×2, `result` ×1) | **I** | `_normalize_result` sets `category` to the *routing* category before copying payload keys; payload values with that name were dropped. Live proof: `classify` returned `label`+`confidence`, and `category` came back as `external_control`. | Payload additionally returned under `data` (the documented payload channel, already preferred by `_extract_outputs`) in the `ai_reasoning` and `filesystem` branches. |
| 8 | `workflow` capability dropped its entire payload | 7 | **I** | `workflow` branch returned only `success`/`message`, discarding `routed_to`, `result`, `verified`, `next_tier`, … | Payload propagated (flat + under `data`). |

### Remaining — each with a concrete disposition

| # | Blocker | Workflows | Class | Exact finding | Disposition |
|---|---|---|---|---|---|
| 9 | `github` capability | 8 | **G** | `GITHUB_TOKEN` **is** present in `.env`. `PyGithub` is **not installed** (`import github` → `ModuleNotFoundError`), and the existing `mcp_github_server.py` requires it. | Requires installing `PyGithub` (small; already the declared dependency of the existing server, used by no new architecture). **Needs your go-ahead to install.** |
| 10 | `email` capability | 9 | **D** | Vault **has** a `provider=google, type=oauth2` credential, but `google_oauth._get_credentials()` returns `None` here: the metadata row exists while `vault.retrieve()` returns `None` — the secret is not readable from this process (keyring locked/unavailable). Existing Gmail OAuth path is reused, not duplicated. | Must be verified **inside the real KIO session** (interactive keyring). Not claimed until then. |
| 11 | `calendar` capability | 6 | **D** | Same Google credential, same retrievability limit. | Same as #10. |
| 12 | `mcp_tool` capability | 8 | **C** | `MCP_RUNTIME_ENABLED=false` (config default is deliberately OFF; one server configured: `executor`). | Config decision, not a defect. Turning it on is a startup-dependency decision — **yours to make**. |
| 13 | `browser` capability | 5 | **C** | No browser backend connected (reuses the boundary's existing `browser_backend` prerequisite gate). | Runtime state. Connect the Browser Connector/BrowserRuntime and re-run. |
| 14 | `media` capability | 4 | **F** | `publish` / `verify_posts` have **no adapter at all**. No target platform is specified by the workflow/config. | Per handoff: do **not** invent LinkedIn/X/Instagram. **Missing contract to decide:** which platform(s), which credential, what "verified post" means (post id? URL?). |
| 15 | `http` capability | 2 | **I** | Neither workflow contains a single `http` step — the capability is left over in `capabilities_required` after the `http.* → knowledge.*` correction. `APP_CAPABILITIES` has no `http` key, so an http step could not run either. | Manifest defect — prune the stale declaration (see §6). |
| 16 | 28 nominal credential names | up to 14 | **D** | e.g. `notify_cred` (9), `channel_cred` (8), `github_token` (7), `mail_cred` (5), `google_oauth` (5), `store_cred`, `crm_cred`, `tracker_cred`, `kb_cred`, `calendar_cred`, `drive_cred`, `status_cred`, `tier_credentials`, `system_a_cred`, `system_b_cred`, `approval_cred`, `webhook_secret`, `api_cred`, `source_cred`, `dest_cred`, `scanner_creds`, `owner_cred`, `vectorstore_cred`, `image_provider`, `platform_creds`. | Most map to subsystems KIO already owns (Telegram token, GITHUB_TOKEN, Google OAuth, Notion/Todoist vault keys, `local_store`). `vectorstore_cred` and `platform_creds` are genuinely unsatisfied. | **Needs a decision:** a name→subsystem mapping table. Several names (`status_cred`, `system_a/b_cred`, `tier_credentials`, `owner_cred`) are ambiguous, and guessing a mapping would be fake wiring. See §7. |

---

## 4. Live Verification (real calls, no mocks)

### 4.1 `ai_reasoning.classify` through the execution boundary

```
execute_action("execute_capability", 'ai_reasoning::classify::{...}')
→ success: True · 10,073 ms · category="external_control"(telemetry) · confidence=0.95
```

Confirms the path reaches the real chain (chain has **9 providers configured**; Gemini timed out
and the request failed over).

### 4.2 `ai.classify_and_route` — full workflow, end to end

```
success: True · 13,345 ms
  step classify | success True | outputs {"category": "billing", "confidence": 0.95}
  step route    | success True | outputs {"routed_to": "email.send_email", "needs_review": false}
FINAL OUTPUTS: {"category": "billing", "routed_to": "email.send_email"}
```

Baseline status: `BLOCKED_MISSING_CAPABILITY`. The `category` value is the model's classification,
not boundary telemetry — this is the output-collision fix working.

### 4.3 `data.json_transform` — payload propagation

```
success: True
  apply  | outputs {"result": [{"name":"bob","email":"b@x.com"}], "row_count": 1}
  verify | outputs {"verified": true}
```

Baseline ran this workflow but produced **null** outputs for both steps.

---

## 5. Post-Closure Preflight Matrix (63 workflows)

Capability + credential resolution through the real `AutomationEngine` preflight. **No steps were
executed for this matrix** (no side effects on real accounts).

```
PREFLIGHT_PASS        16
BLOCKED_CAP           33
BLOCKED_CRED          14
```

Remaining missing capabilities by workflow count:
`email 9 · mcp_tool 8 · github 8 · calendar 6 · browser 5 · media 4 · http 2`

| Workflow | Block | Missing caps | Failing creds |
|---|---|---|---|
| ai.enrich_records | CRED | — | store_cred |
| ai.image_generate | CAP | media | image_provider |
| ai.rag_answer | CRED | — | vectorstore_cred |
| browser.page_change_monitor | CAP | browser | notify_cred |
| browser.price_monitor | CAP | browser | notify_cred |
| browser.structured_extract | CAP | browser | — |
| business.crm_followup | CAP | email, mcp_tool | crm_cred, mail_cred |
| business.email_autoresponder_approval | CAP | email | approval_cred, mail_cred |
| business.lead_intake_crm | CAP | mcp_tool | crm_cred, owner_cred |
| business.support_ticket_triage | CAP | email, mcp_tool | channel_cred, mail_cred, tracker_cred |
| communication.chat_assistant | CRED | — | channel_cred |
| communication.escalation_alert | CRED | — | tier_credentials |
| communication.notify | CRED | — | channel_credential |
| communication.voice_assistant | CAP | media | channel_cred |
| communication.workflow_failure_alert | CRED | — | channel_credential |
| data.api_poll_to_store | CRED | — | api_cred, store_cred |
| data.form_intake | CRED | — | channel_cred, google_oauth |
| data.knowledge_base_sync | CAP | mcp_tool | kb_cred |
| data.record_sync | CAP | mcp_tool | system_a_cred, system_b_cred |
| data.webhook_to_store | CRED | — | store_cred, webhook_secret |
| development.ci_failure_alert | CAP | github | github_token, notify_cred |
| development.dependency_monitor | CAP | github, http | github_token |
| development.github_issue_triage | CAP | github | github_token |
| development.issue_to_implementation | CAP | github | github_token |
| development.pr_review_prep | CAP | github | github_token |
| development.release_changelog | CAP | github | github_token |
| development.repo_backup | CAP | github | dest_cred, source_cred |
| development.repo_health_report | CAP | github | github_token |
| files.document_summarize | CRED | — | notify_channel_cred |
| files.drive_to_social | CAP | media | drive_cred |
| media.content_repurpose | CAP | media | platform_creds |
| monitoring.inbox_monitor | CAP | email | mail_cred, notify_cred |
| monitoring.rss_news_monitor | CRED | — | notify_cred |
| monitoring.security_scan_alert | CRED | — | notify_cred, scanner_creds |
| monitoring.website_uptime | CRED | — | notify_cred |
| productivity.calendar_to_status | CAP | calendar | calendar_cred, status_cred |
| productivity.ecosystem_briefing | CAP | calendar, email | channel_cred, google_oauth |
| productivity.email_label_ai | CAP | email | mail_cred |
| productivity.email_to_calendar | CAP | email, calendar | google_oauth |
| productivity.email_to_task | CAP | email, mcp_tool | google_oauth |
| productivity.meeting_prep | CAP | calendar, email | channel_cred, google_oauth |
| productivity.morning_briefing | CAP | calendar, mcp_tool | calendar_cred, channel_cred |
| productivity.weekly_review | CAP | calendar, mcp_tool | calendar_cred, channel_cred |
| research.competitor_monitor | CAP | browser | — |
| research.daily_brief | CAP | http | notify_cred |
| research.web_scrape_to_report | CAP | browser | — |
| research.youtube_summary | CRED | — | notify_cred |

Raw data: `.local/preflight_after_provider_closure.json`.
Note the rise in `BLOCKED_CRED`: workflows that previously short-circuited on a missing
capability now progress to the credential stage, so their credential requirements become visible.
That is a reclassification, not a regression.

---

## 6. Manifest Defects Found (no YAML edited)

20 capability declarations are **declared but used by no step** in 18 workflows — the
`http.* → knowledge.*` action correction (`c6c6748`) did not prune the matching capability list:

| Workflow | Stale declaration |
|---|---|
| business.crm_followup | email |
| business.email_autoresponder_approval | communication |
| business.support_ticket_triage | email |
| communication.escalation_alert, communication.voice_assistant | memory |
| development.dependency_monitor, research.daily_brief | http |
| files.download_folder_organizer | ai_reasoning |
| files.duplicate_detector | artifact |
| media.content_repurpose | communication |
| monitoring.inbox_monitor | memory |
| productivity.calendar_to_status, productivity.weekly_review | calendar |
| productivity.ecosystem_briefing | email |
| productivity.email_label_ai | memory |
| productivity.email_to_calendar, productivity.email_to_task, productivity.meeting_prep | email |
| productivity.weekly_review | mcp_tool |

Consequence: the preflight blocks workflows on capabilities they never use (`email` ×6,
`calendar` ×2, `mcp_tool` ×1, `http` ×2 of the 33 capability blocks are attributable to this).
Not fixed unilaterally — pruning changes the recovered library's declared contract.

### Additional defect observed (not fixed)

`ask_llm_sync` (`llm/llm_ops.py:98`) eagerly creates the `ask_llm` coroutine before
`asyncio.run()` raises `RuntimeError` in an async context, leaking an un-awaited coroutine and
emitting `RuntimeWarning: coroutine 'ask_llm' was never awaited` on every async caller. The
fallback path then succeeds, so it is cosmetic today but noisy and should take a coroutine
factory instead.

---

## 7. Decisions Needed Before Phase 7

1. **Credential-name mapping (biggest remaining item, up to 14 workflows).** Approve a
   `credential name → owning subsystem` table (Telegram token, GITHUB_TOKEN, Google OAuth,
   Notion, Todoist, `local_store`, …) so the credential bridge can resolve them truthfully. The
   ambiguous names (`status_cred`, `system_a_cred`, `system_b_cred`, `tier_credentials`,
   `owner_cred`, `scanner_creds`) need an explicit answer — I will not guess them.
2. **Install `PyGithub`** to close all 8 `github` workflows (token already present).
3. **Google secret retrievability** — confirm the keyring is readable in the real KIO session so
   `email` (9) and `calendar` (6) can be verified live; I will not claim Gmail/Calendar until a
   real call succeeds.
4. **`mcp_tool`** — enable `MCP_RUNTIME_ENABLED`, or accept these 8 workflows as blocked.
5. **Media publishing contract** — platform, credential, and verification semantics, or keep
   `media` (4 workflows) formally blocked.
6. **Prune the 20 stale capability declarations** (§6) — yes/no.
7. **Browser backend** — connect it; then the 5 browser workflows unblock (no code change).

---

## 8. Files Changed

| File | Change |
|---|---|
| `mini_kio/core/providers/ai_reasoning_provider.py` | **new** — health-gated provider exposing the existing LLM chain; `health()` derived from the real chain; execution delegated through the boundary (no bypass, no second LLM stack) |
| `mini_kio/core/providers/__init__.py` | registers `AIReasoningProvider` |
| `mini_kio/automation/capability_resolver.py` | registered-capability mappings corrected; per-capability readiness probes (artifact, google, github, communication, mcp, browser, monitoring); explicit unimplemented entries (`media`, `http`); accuracy fixes (env-load ordering; distinguishes "not authorized" from "secret unretrievable") |
| `mini_kio/automation/bridges.py` | shared `llm_credential_status()`; `CredentialBridge` resolves `type: llm` against the live chain |
| `mini_kio/core/app_operator.py` | `workflow`, `ai_reasoning`, `filesystem` branches propagate provider payloads (flat + under `data`); `workflow` no longer parses args twice |
| `tests/test_terminal_routing.py` | initializes the provider registry before asserting capability resolution (the assertion was previously unpassable — registry was empty) |

**Tests:** 152 passed (`test_ai_reasoning_contract`, `test_ai_reasoning_routing`,
`test_automation_integration`, `test_p1_contract_fix`, `test_workflow_routing`,
`test_append_xlsx_row`), `test_terminal_routing` 31/31. No full-suite run (per handoff testing rule).

**Resource limit:** unaffected. No model or heavy provider is loaded at rest; the new provider
declares a 20 MB budget and holds no state. The 650 MB ceiling is intact.

**Not done (deliberately):** no workflow YAML regenerated or modified; no fake/mock provider; no
second LLM framework, MCP gateway, or credential store; recovery work not redone.
