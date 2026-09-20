# KIO Credential Requirements

**Date:** 2026-09-20
**Branch:** `kio-restoration-safety-20260823`
**Scope:** Credential / configuration / dependency identification for the 63 recovered workflows.
**Supersedes:** the credential findings in `KIO_PROVIDER_BLOCKER_CLOSURE_REPORT.md` §5 item 10/11 (see §10 correction).
**Status:** Phase 7 NOT started. No workflow YAML modified. No secret is recorded in this document.

---

## 0. Headline

**Google OAuth reauthorization is NOT required.** The existing credential was intact; only its read
path was broken. It is repaired and **live-verified** (Gmail: 15 labels; Calendar: 6 calendars
read through the real API). No new Google project, client, or credential was created.

Of the 29 credential names declared across the 63 workflows:

| Verdict | Count | Meaning |
|---|---:|---|
| Satisfied by an existing KIO-owned subsystem | 20 | nothing for you to provide |
| Stale / optional declaration (no credential needed) | 3 | should be pruned, not supplied |
| Conditional on a workflow `config` choice you make | 4 | resolvable to an existing credential if you pick the supported option |
| Genuinely requires a new external service or credential | 2 (`platform_creds`, `scanner_creds`) + `image_provider` | blocked by a missing **provider implementation**, not just a key |

Separately: **1 dependency missing** (`PyGithub`), **1 configuration flag** (`MCP_RUNTIME_ENABLED`),
**1 infrastructure item** (browser backend), and **several provider implementations missing**
(social publishing, image generation, Slack/Teams presence, external CRM/tracker MCP servers).

### Preflight effect of the repair

| Metric | Before repair | After repair |
|---|---:|---:|
| Missing capabilities — `email` | 9 | **0** |
| Missing capabilities — `calendar` | 6 | **0** |
| BLOCKED_MISSING_CAPABILITY | 33 | **26** |
| BLOCKED_MISSING_CREDENTIAL | 14 | 21* |

\* Not a regression: workflows that previously short-circuited on a missing capability now reach the
credential stage, where their declared credential names become visible. Resolving those names
(§2) is what turns them green.

Remaining missing capabilities: `mcp_tool 8 · github 8 · browser 5 · media 4 · http 2`.

---

## 1. Complete Credential Inventory

Every credential name declared in `credentials_required` across the 63 workflows. Classification:
**A** real external credential · **B** existing KIO-owned subsystem/configuration ·
**C** alias that should resolve to an existing credential · **D** stale/unused declaration ·
**E** ambiguous / needs architectural clarification.

| Credential | Type | WFs | Declared by (examples) | Class | What it actually is | Needs you? |
|---|---|---:|---|---|---|---|
| `llm_provider` | llm | 41 | most AI workflows | B | The env-configured LLM chain (9 providers live) | **No** — already wired |
| `none` | none | 5 | scaffold_project and others | B | Explicit "no credential" | No |
| `notify_cred` | bot_token | 9 | monitoring.*, development.ci_failure_alert | C | Telegram bot token (only integrated channel) | No |
| `channel_cred` | bot_token | 8 | communication.*, productivity.* | C | Telegram bot token | No |
| `github_token` | api_key | 7 | development.* | B | `GITHUB_TOKEN` in `.env` (present) | No (dependency gap instead, §6) |
| `mail_cred` | oauth2 | 5 | monitoring.inbox_monitor, productivity.email_* | C | The Google OAuth credential (gmail.modify) | No |
| `google_oauth` | oauth2 | 5 | productivity.email_to_task, data.form_intake | B | The Google OAuth credential (declared per-workflow scopes; see §2 for the `tasks`/`spreadsheets` gaps) | No |
| `store_cred` | oauth2 | 3 | ai.enrich_records, data.webhook_to_store, data.api_poll_to_store | **D** (2) / C (1) | Local filesystem store (`store_record`/`append_records`); only `api_poll_to_store` can mean Google Sheets (exists) | **No** |
| `calendar_cred` | oauth2 | 3 | productivity.calendar_to_status, morning_briefing, weekly_review | C | Google OAuth credential (calendar scope present) | No |
| `crm_cred` | api_key | 2 | business.crm_followup, business.lead_intake_crm | E | Config-driven: `crm_followup` allows hubspot/salesforce/airtable (none in vault); `lead_intake_crm` also allows **notion** (exists) | **Conditional** |
| `channel_credential` | bot_token | 2 | communication.notify, workflow_failure_alert | C | Telegram bot token | No |
| `image_provider` | api_key | 1 | ai.image_generate | A | An image-generation model key — but `media.generate_image` is **not implemented** | **Conditional** |
| `vectorstore_cred` | api_key | 1 | ai.rag_answer | **D** | `knowledge.vector_search` embeds locally (sentence-transformers) over caller-supplied documents; no external vector DB is used | **No** |
| `approval_cred` | bot_token | 1 | business.email_autoresponder_approval | C | Telegram bot token | No |
| `owner_cred` | bot_token | 1 | business.lead_intake_crm | C | Notification channel token; config default is `slack`, `telegram` is also allowed | **Conditional** |
| `tracker_cred` | api_key | 1 | business.support_ticket_triage | E | Config `tracker`: linear/jira/notion/airtable (default **linear**, not integrated); **notion** exists | **Conditional** |
| `tier_credentials` | bot_token | 1 | communication.escalation_alert | C | Per-escalation-tier notification tokens — same Telegram channel, tiered | No (single channel today) |
| `api_cred` | api_key | 1 | data.api_poll_to_store | A | Auth for the REST endpoint *you* configure (`config.endpoint`, required) | **Yes, when configured** |
| `kb_cred` | api_key | 1 | data.knowledge_base_sync | C | Notion API key — **present in vault**; config default `notion` | No |
| `system_a_cred` | api_key | 1 | data.record_sync | C | Dynamic: `config.system_a` names the system (e.g. `notion`) → existing vault credential | No |
| `system_b_cred` | api_key | 1 | data.record_sync | C | Dynamic: `config.system_b` (e.g. `todoist`) → existing vault credential | No |
| `webhook_secret` | api_key | 1 | data.webhook_to_store | B | HMAC shared secret between you and your webhook source (KIO-side config) | **Yes, when configured** |
| `source_cred` | api_key | 1 | development.repo_backup | C | Source repo access → GitHub token (present) | No |
| `dest_cred` | oauth2 | 1 | development.repo_backup | C | Destination: google_drive (default) / s3 / local — Google credential exists | No |
| `notify_channel_cred` | bot_token | 1 | files.document_summarize | C | Telegram bot token | No |
| `drive_cred` | oauth2 | 1 | files.drive_to_social | C | Google OAuth credential (drive scope present) | No |
| `platform_creds` | oauth2 | 1 | media.content_repurpose | A | Social publishing auth — **no adapter and no target platform exist** | **Yes, after a decision** |
| `scanner_creds` | api_key | 1 | monitoring.security_scan_alert | A | Reputation/scan service keys (URLScan/VirusTotal-class) — **not integrated** | **Yes, after a decision** |
| `status_cred` | oauth2 | 1 | productivity.calendar_to_status | E | Slack/Teams presence write — **neither is integrated**, and `set_status`/`clear_status` are stubs (§9) | **Yes, after a decision** |

---

## 2. Existing Credential Status (what is actually in the vault)

`CredentialVault` (metadata in SQLite, secrets in the Windows keyring). Contents right now:

| Provider | Type | State | Secret readable? | Serves |
|---|---|---|---|---|
| `google` | `oauth2` | **refreshable** | **Yes** (after repair) | Gmail, Calendar, Drive, YouTube |
| `notion` | `api_key` | valid | Yes | `kb_cred`, `system_a/b_cred`, `crm_cred` (if notion) |
| `todoist` | `api_key` | valid | Yes | `system_b_cred`, `task_store=todoist` |

Stored Google scopes (verified from the credential payload — no secret material shown):

```
calendar · drive · gmail.modify · youtube
```

Those four cover exactly what the 63 workflows require (Gmail API + YouTube Data API were the audit's
findings; Calendar and Drive are used by productivity/files workflows).

**Notably absent from the stored grant:** `tasks`, `contacts`, `photos`, `spreadsheets`, `documents`,
`meet`, `chat` are requested in `ACTIVE_SCOPES` but were never granted. Of the two workflows that
declare such scopes:

- `productivity.email_to_task` declares `tasks` and defaults to `task_store: google_tasks` — the
  current grant cannot serve that. **Todoist is already in the vault**, so `task_store: todoist`
  needs no new credential and no re-consent.
- `data.form_intake` declares `spreadsheets`, but its steps are `filesystem.append_sheet_row` /
  `verify_sheet_row`, which are **local openpyxl `.xlsx` writes** — not the Google Sheets API. The
  scope is not needed; the declaration is stale (see §1, §9).

---

## 3. Runtime Readability Status — the Google issue, resolved

### What was wrong

`CredentialVault.retrieve()` is **fail-closed by design and by test**
(`test_slice9_credential_lifecycle.py`: "Fail closed: retrieve() returns None for expired"). It
returns `None` for any credential past its `expires_at`.

For Google, the stored `expires_at` is the **short-lived access-token expiry** (~1 hour), while the
durable material is the `refresh_token`. So roughly an hour after every authorization:

- `retrieve()` refused to hand over a perfectly good credential,
- `google_oauth._get_credentials()` returned `None`,
- the automation preflight reported `email` and `calendar` as blocked.

This was already recorded in `KIO_PROVIDER_REVERIFICATION_REPORT.md:31` ("tokens expired after
approximately 10.8 hours… `retrieve()` correctly returns None") and treated as correct behaviour.

### Differential diagnosis (per the task's A–G list)

| Hypothesis | Verdict | Evidence |
|---|---|---|
| A. wrong provider name | No | `provider='google'`, `type='oauth2'` matched the row |
| B. wrong credential ID | No | the listed `credential_id` is the one `_get_credentials()` reads |
| C. vault initialization issue | No | metadata read fine; `list()` returned all 3 rows |
| D. keyring access issue | **No** | `notion` and `todoist` secrets read successfully in the same process |
| E. process/user-context issue | No | same user, same process as the successful non-Google reads |
| F. expired/revoked credential | **Partially — the access token only** | `expires_at = 2026-09-20 10:38`, checked at `12:16`; `revoked=False`; payload contained `access_token`, **`refresh_token`**, `scopes`, `token_uri` |
| G. genuinely missing | **No** | the secret was present and complete |

### The repair (read path, not credentials)

1. `CredentialVault.validate()` — an expired credential that still carries refresh material now
   reports the already-defined-but-unused `STATE_REFRESHABLE` instead of `expired`.
2. `CredentialVault.retrieve_for_refresh()` — a narrowly-scoped accessor that returns the payload
   for a token-refresh flow even when the access token has lapsed. `retrieve()` keeps its
   fail-closed contract for execution gating, and a credential with **no** refresh material still
   returns `None` (nothing is resurrected).
3. `google_oauth._get_credentials()` — falls back to `retrieve_for_refresh()`; google-auth then
   refreshes lazily on the first request.

### Live verification (real API calls, read-only)

```
validate('google','oauth2') -> refreshable      (was: expired)
needs_attention()           -> []               (was: [google oauth2 expired])
Gmail   labels().list()     -> OK, 15 labels
Calendar calendarList()     -> OK, 6 calendars
```

---

## 4. Ambiguous Credential Analysis

Each of the names flagged for clarification, resolved against the workflows, engine, resolver,
providers, vault, and runtime configuration.

### 4.1 `status_cred` — productivity.calendar_to_status
- **Declared as:** `oauth2`, scopes `['status.write']`, description "Status write".
- **What the workflow does:** `communication.set_status` / `clear_status`; `config.status_target`
  enum is `['slack','teams']`, default `slack`.
- **Finding:** neither Slack nor Teams exists anywhere in KIO — no token in `config.py`, no channel
  in the communication branch, no `SLACK_*` anywhere in the repo. `set_status`/`clear_status` are
  also **stubs that return `success: True` without calling any API** (§9).
- **Classification: E + missing provider implementation.**
- **Outcome:** cannot be satisfied by any existing credential. Requires a decision: implement a
  Slack or Teams presence adapter (new external credential + scopes), or remove this workflow's
  status path. Not a "give me a token" item yet.

### 4.2 `system_a_cred` / `system_b_cred` — data.record_sync
- **Declared as:** `api_key`, "System A auth" / "System B auth".
- **Finding:** `config.system_a` / `config.system_b` are *strings naming the systems*
  ("Source system id (e.g. notion)", "Target system id (e.g. todoist)"). The credential is therefore
  not a fixed service — it is whatever the two configured systems need. **Notion and Todoist
  credentials already exist in the vault.**
- **Classification: C (alias, config-resolved to existing credentials).**
- **Outcome:** resolvable by wiring the vault lookup to `config.system_a/system_b`. Note the steps
  are `mcp_tool list_changed` / `upsert`, whose MCP servers do not exist (§5) — the credential is
  not the blocker here.

### 4.3 `tier_credentials` — communication.escalation_alert
- **Declared as:** `bot_token`, "Tokens for each tier target".
- **Finding:** the escalation tiers are notification targets; the workflow's steps are
  `communication.send_with_ack` → `workflow.wait_for_ack` → `workflow.advance_tier_or_stop`.
  KIO's only integrated outbound channel is Telegram.
- **Classification: C.** All tiers resolve to the existing Telegram bot token (the workflow's
  per-tier distinction is channel/recipient, not a different credential).
- **Outcome:** resolvable by wiring; no new credential.

### 4.4 `owner_cred` — business.lead_intake_crm
- **Declared as:** `bot_token`, "Notify token".
- **Finding:** `config.owner_channel` enum `['telegram','slack','email']`, **default `slack`**.
  `telegram` is integrated; `slack` and `email` are not (email is Gmail-adjacent via the Google
  credential, but the notification path uses `communication.send_message`).
- **Classification: C if `owner_channel=telegram`; otherwise requires a new integration.**
- **Outcome:** resolvable by configuration (set `owner_channel: telegram`) — your call.

### 4.5 Additional names resolved during this pass (formerly ambiguous)

| Name | Resolution | Class |
|---|---|---|
| `kb_cred` | Notion API key — present; config default `notion` | C |
| `crm_cred` | Config-driven; `lead_intake_crm` allows `notion` (present); `crm_followup` allows only hubspot/salesforce/airtable | E (conditional) |
| `tracker_cred` | Config default `linear` (not integrated); `notion` is allowed and present | E (conditional) |
| `store_cred` | Local filesystem store; only `api_poll_to_store` can mean Google Sheets (present) | D (2 of 3) |
| `vectorstore_cred` | Local sentence-transformers embedding — no external store | **D** |
| `source_cred` / `dest_cred` | GitHub token (present) / Google Drive (present) | C |
| `drive_cred` / `mail_cred` / `calendar_cred` / `google_oauth` | The one Google credential | C/B |

---

## 5. Configuration Requirements (not credentials)

| Item | Current | What it affects | Note |
|---|---|---|---|
| `MCP_RUNTIME_ENABLED` | `false` | all 8 `mcp_tool` workflows (`crm_get`, `upsert`, `create_page`, `get_page`, `create_task`, `list_changed`, `upsert_ticket`, `find_stale_leads`) | Deliberately OFF by design (`reports/MCP_INTEGRATION_LESSONS.md`: optional integrations must not become startup dependencies). Enabling it is a **startup-dependency decision**, not a credential. |
| `KIO_MCP_SERVERS` | one server (`executor`) | as above | Even enabled, `register_all_mcp_servers()` ships filesystem/git/terminal/sqlite/docker/github/postgres/redis — **no Notion/Todoist/CRM/tracker servers exist** (§7). |
| Browser backend | not connected | 5 browser workflows | Infrastructure, not a credential. |
| `config.owner_channel` | `slack` | `lead_intake_crm` | Set to `telegram` to use the existing channel. |
| `config.tracker` | `linear` | `support_ticket_triage` | Set to `notion` to use the existing credential. |
| `config.task_store` | `google_tasks` | `email_to_task` | Set to `todoist` to use the existing credential (the stored Google grant lacks the `tasks` scope). |
| `config.dest` | `google_drive` | `repo_backup` | Already resolvable (Google credential present). |
| `config.store` | `google_sheets` | `api_poll_to_store` | Resolvable via Google; local DB also supported. |
| Stale capability declarations | 20 across 18 workflows | preflight | e.g. `http` ×2, `email` ×6 — prune (no credential implication). |

---

## 6. Dependency Requirements (not a credential)

**`PyGithub` is genuinely required** by the existing GitHub implementation — there is no
PyGithub-free path:

- `mini_kio/core/mcp/servers/mcp_github_server.py:5` — "Requires: pip install PyGithub"
- `_get_github()` does `from github import Github`; without it every call returns
  `"GitHub API not available (install PyGithub and set GITHUB_TOKEN)"`.
- Even the REST-based Dependabot path imports `GithubException` from PyGithub (line 187).

Effect: 8 workflows blocked (`development.ci_failure_alert`, `dependency_monitor`,
`github_issue_triage`, `issue_to_implementation`, `pr_review_prep`, `release_changelog`,
`repo_backup`, `repo_health_report`). The token itself is fine — `GITHUB_TOKEN` is present in `.env`.

**No GitHub credential is needed from you.**

---

## 7. Provider-Implementation Requirements (neither credential nor config)

| Capability | Blocked WFs | What is missing | Credential implication |
|---|---:|---|---|
| `media.publish` / `verify_posts` | 4 (`media.content_repurpose`, `files.drive_to_social`, `ai.image_generate`, `communication.voice_assistant`) | No social-publishing adapter; no target platform specified anywhere in the workflow or config. The code says so explicitly: "publish and verify_posts require external platform adapters (API keys)". | `platform_creds` only becomes meaningful after a platform decision |
| `media.generate_image` | 1 (`ai.image_generate`) | Not implemented in the media branch (only `publish`, `verify_posts`, `text_to_speech`, `transcode_variants` exist) | `image_provider` only meaningful afterwards |
| `mcp_tool` servers | 8 | No Notion/Todoist/CRM/tracker MCP servers exist. Vault credentials exist for Notion + Todoist, so a local adapter or server could use them. | credentials exist; implementation missing |
| `communication.set_status` / `clear_status` | 1 (`calendar_to_status`) | Stubs returning fake success (§9); no Slack/Teams adapter | `status_cred` meaningless until then |
| `knowledge.multi_scan` | 1 (`security_scan_alert`) | `multi_scan` maps to `web_search`; no scan-service integration | `scanner_creds` meaningless until then |
| `ai_reasoning.transcribe` | 2 (`ai.transcribe_summarize`, `communication.voice_assistant`) | Routed to the text LLM, not a speech-to-text engine (`providers_required: whisper` is unmet) | no credential named for it |

---

## 8. Genuine Missing Credentials (only what cannot be reached any other way)

These are the **only** credential-class gaps that cannot be closed by wiring an existing subsystem:

1. **`api_cred`** — auth for the REST endpoint configured in `data.api_poll_to_store`. Unknown by
   nature until you choose the endpoint; supply it when configuring the workflow.
2. **`webhook_secret`** — the HMAC secret shared with your webhook source. KIO-side configuration
   value; you generate/choose it when wiring the source.
3. **`crm_cred`** — only if you keep a CRM other than Notion (hubspot/salesforce/airtable).
4. **`tracker_cred`** — only if you keep a tracker other than Notion (linear/jira/airtable).
5. **`owner_cred`** — only if you notify via Slack instead of Telegram.
6. **`status_cred`** — only if a Slack/Teams presence adapter is built.
7. **`platform_creds`** — only if a specific social platform is chosen and implemented.
8. **`scanner_creds`** — only if a reputation/scan service is integrated.
9. **`image_provider`** — only if image generation is implemented.

Items 3–9 are **contingent on decisions or implementations that do not exist yet**, not on missing
credentials today.

---

## 9. Truthfulness & Contract Defects (flagged, not fixed)

These surfaced while resolving credentials and are recorded because they affect whether a credential
can mean anything. None were modified in this pass (no workflow semantics were to be changed).

1. **`communication.set_status` / `clear_status` are fake-success stubs.** They return
   `{"success": True, "message": "Status <action> completed."}` **without calling any API**, and
   `debounce_messages` returns `{"success": True, "debounced": True}` unconditionally. The
   `calendar_to_status` verification block asks for observable evidence ("presence actually set"),
   which these cannot provide. This is why `status_cred` is unresolvable.
2. **`data.form_intake` input-name mismatch.** The step passes `sheet_id` and `response`, but the
   `filesystem.append_sheet_row` handler reads `path` / `sheet_name` / `row_values`. The step
   therefore resolves empty arguments and fails with `"File not found: "`. Its declared
   `google_oauth`/`spreadsheets` credential is irrelevant — the target is a local `.xlsx` file.
3. **20 stale capability declarations** across 18 workflows (e.g. `http` ×2, `email` ×6), left over
   from the `http.* → knowledge.*` action correction. These over-block preflight.

---

## 10. Correction to the Previous Report

`KIO_PROVIDER_BLOCKER_CLOSURE_REPORT.md` §5 items 10–11 stated that the Google credential's secret
was "not readable from this process (keyring locked/unavailable)" and that reauthorization might be
required. **That was wrong.** The keyring was readable (proven by Notion/Todoist reads in the same
process); `retrieve()` was refusing the credential because its *access token* had expired while the
*refresh_token* remained valid. The report is superseded on this point by §3 above.

---

## 11. Credentials That Must NOT Be Recreated

| Must not be recreated | Because |
|---|---|
| Google OAuth client / Google Cloud project | Existing client config + credential work and are live-verified. Creating another would duplicate the identity. |
| Google OAuth credential in the vault | Present, refreshable, verified. Repair was in the read path only. |
| `GITHUB_TOKEN` | Present in `.env` and previously live-verified. The gap is `PyGithub`. |
| Notion API key | Present in the vault. |
| Todoist API key | Present in the vault. |
| Telegram bot token (`TELEGRAM_TOKEN`) | Present and used by the communication branch. |
| Discord bot token | Present (`DISCORD_BOT_TOKEN`). |
| LLM provider keys (Gemini, Groq, OpenRouter, Together, Cerebras, SambaNova, Fireworks, HF, Ollama) | All present; the chain reports 9 providers. |

---

## 12. USER ACTION CHECKLIST

Answering "NO" means KIO needs nothing from you for that item.

| # | Item | Needed? | Why / what exactly |
|---|---|---|---|
| 1 | **Google OAuth reauthorization** | **NO** | Credential intact; read path repaired; Gmail + Calendar live-verified. (Optional-only: if you ever want Google **Tasks**, a re-consent adding the `tasks` scope would be required — but Todoist is already available and is the better path.) |
| 2 | **GitHub token** | **NO** | `GITHUB_TOKEN` present. → instead approve installing **PyGithub** (§6), a dependency, not a credential. |
| 3 | **Notion token** | **NO** | Present in the vault. |
| 4 | **Todoist token** | **NO** | Present in the vault. |
| 5 | **MCP configuration** | **DECISION** | Turn `MCP_RUNTIME_ENABLED` on, and decide whether Notion/Todoist/CRM/tracker servers should be built. No credential. Affects 8 workflows. |
| 6 | **Browser backend** | **DECISION** | Connect the Browser Connector/BrowserRuntime (no credential). Affects 5 workflows. |
| 7 | **Social media credentials** | **DECISION FIRST** | No platform is specified and no publishing adapter exists. Tell me the platform + what "verified post" means, or leave `media` (4 workflows) formally blocked. |
| 8 | **Slack or Teams credentials** | **DECISION FIRST** | Only needed if you want Slack/Teams presence (1 workflow, currently a stub) or Slack notifications instead of Telegram. |
| 9 | **Scan-service keys** (URLScan/VirusTotal-class) | **DECISION FIRST** | Only if you want `security_scan_alert` to use a real reputation service. |
| 10 | **External CRM key** (HubSpot/Salesforce/Airtable) | **CONDITIONAL** | Only if you reject the Notion-backed option for `lead_intake_crm`. |
| 11 | **External tracker key** (Linear/Jira/Airtable) | **CONDITIONAL** | Only if you reject `tracker: notion` for `support_ticket_triage`. |
| 12 | **REST API key for `api_poll_to_store`** | **WHEN CONFIGURING** | You choose the endpoint; the key follows from that choice. Stored in CredentialVault, never in YAML. |
| 13 | **`webhook_secret` for `webhook_to_store`** | **WHEN CONFIGURING** | The HMAC secret shared with your webhook source. Stored in CredentialVault. |
| 14 | **Image-generation model key** | **CONDITIONAL** | Only after `media.generate_image` is implemented. |

**Recommended minimal path (no new secrets at all):**

1. Approve the credential-name → subsystem mapping so `mail_cred`, `calendar_cred`, `drive_cred`,
   `google_oauth`, `notify_cred`, `channel_cred`, `channel_credential`, `notify_channel_cred`,
   `approval_cred`, `tier_credentials`, `github_token`, `kb_cred`, `source_cred`, `dest_cred`,
   `system_a_cred`, `system_b_cred`, `store_cred`, `vectorstore_cred` all resolve through existing
   subsystems (this is wiring, not secrets).
2. Approve installing `PyGithub` (closes 8 GitHub workflows).
3. Choose the config values in §5 (`owner_channel`, `tracker`, `task_store`, `crm`, `store`, `dest`)
   where an external service would otherwise be needed.
4. Decide on the four provider-implementation gaps in §7 before any related credential is requested.

---

## 13. Security

No API key, access token, refresh token, password, or secret value appears in this document or in
any report produced during this work. Diagnostics printed only booleans, states, timestamps, key
names, and counts. All secret material remains in `CredentialVault` (keyring + metadata).
