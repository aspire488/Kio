# KIO — Pre-Phase-7 Decision Gate

**Scope:** resolve user decisions, dependencies and non-credential blockers only.
**Not in scope / not done:** no credential requested or created, no workflow YAML modified, no Phase 7 start, no new provider or MCP gateway, no duplicate Google/GitHub credential.

**Method:** every claim below was checked against the running system. Capability and credential checks were run *after* `bootstrap_runtime()` + `register_all_providers()` — i.e. the same bootstrap the real runtime performs (`mini_kio/core/runtime.py:1417`, `mini_kio/core/providers/__init__.py`). Anything verified live is marked **[live]**.

---

## 1. Corrected matrix (post-PyGithub, post-bootstrap)

```
TOTAL=63  PREFLIGHT_PASS=49  BLOCKED=14
  mcp_tool  8 workflows
  media     4 workflows
  http      2 workflows
```

Three of those 14 are **oracle noise, not real blockers** (see §6), and one *real* blocker
(`productivity/calendar_to_status.yaml`) is **not** flagged at all because a stub reports success (see §7).
Truthful position: **9 genuinely blocked, 5 falsely blocked, 1 falsely passing.**

---

## 2. Decision table

| Item | Affects workflows | Current state | User decision required | Exact decision |
|---|---:|---|---|---|
| **1. PyGithub** | 8 (github capability) | **RESOLVED.** `PyGithub==2.10.0` installed and verified **[live]** | No | none — informational only |
| **2. MCP runtime** | 8 declare `mcp_tool`; **7 actually execute** mcp_tool steps | `MCP_RUNTIME_ENABLED=false`; only configured server is third-party `executor`; **no server exposes the 10 required tools** | **YES — approval before changing config** | (a) approve flipping `MCP_RUNTIME_ENABLED`; (b) decide how the 10 tools get provided |
| **3. Browser backend** | 5 | Playwright + Chromium installed; BrowserRuntime verified working **[live]**; not a missing backend — a code path defect blocks the fallback | **YES — approve a ~3-line fix** | Approve making `_browser_goto_and_extract` fall through to the Playwright path instead of returning early |
| **4. Social publishing** | 1 (`media/content_repurpose.yaml`) | No publishing adapter for any platform; YAML default targets are `linkedin, x, instagram` | **YES — platform choice** | Which platform(s) to implement as the first real adapter (or declare the workflow out of scope) |
| **5. Scanner** | 1 (`monitoring/security_scan_alert.yaml`) | No scan-service client exists; the action is silently aliased to a web search | **YES — service choice** | Which scan service to implement (YAML default suggests urlscan.io + VirusTotal) or declare out of scope |
| **6. Slack/Teams status** | 1 (`productivity/calendar_to_status.yaml`) | `set_status`/`clear_status` are fake-success stubs; no Slack/Teams client exists | **YES — implement or exclude** | Implement a real presence adapter (needs a NEW external Slack/Teams credential) **or** exclude the workflow |
| **7. Oracle precision** | 5 (2 media false, 3 stale-declaration) | `media` is blocked wholesale; stale capability declarations block 3 workflows | **YES — approve small fix** | Approve narrowing the `media` rule and honouring stale declarations, so the matrix stops lying in both directions |

---

## 3. Item 1 — PyGithub (RESOLVED, no action)

**Class: DEPENDENCY (not a credential).**

- Requirement was real: `mcp_github_server.py` imports `from github import Github` and `GithubException`.
- Environment: **Python 3.14.5**. Installed **`PyGithub==2.10.0`** (latest; resolves on 3.14).
- Pulled in only `PyJWT 2.14.0` + `PyNaCl 1.6.2`. All other deps already satisfied:
  `requests 2.34.2`, `urllib3 2.7.0`, `cryptography 49.0.0`, `typing-extensions 4.16.0`.
- Ramp; `sentence-transformers 5.6.0`, `playwright 1.61.0` unchanged.

**[live] verification — no mock, no new token:**

```
client_constructed: True
authenticated_as: aspire488          <- real authenticated identity read
github_repo_metrics("octocat/Hello-World") success: True  | stars: 3823 | default_branch: master
github_list_issues("octocat/Hello-World")  success: True  | count: 2
```

Capability check now reports `github available=True / "GitHub token and client available"`.
No GitHub token was requested, read out, printed, or replaced.

**Pending housekeeping (needs a go-ahead):** `requirements.txt` has 111 pins and does **not**
contain PyGithub. The file is **UTF-16LE with BOM**, `==`-pinned and alphabetised; the available
file-editing tools write UTF-8, so appending the pin risks corrupting the manifest. The exact line
to add is `PyGithub==2.10.0`. Say the word and I will append it in the file's existing encoding
rather than converting the file.

---

## 4. Item 2 — `MCP_RUNTIME_ENABLED` (approval required)

**Class: CONFIGURATION + missing PROVIDER IMPLEMENTATION/CONTRACT. Not a credential.**

**Workflows affected — 8 declare `mcp_tool`, but only 7 have mcp_tool steps:**

| Workflow | MCP steps | Tools required |
|---|---:|---|
| `business/crm_followup.yaml` | 1 | `find_stale_leads` |
| `business/lead_intake_crm.yaml` | 2 | `crm_upsert`, `crm_get` |
| `business/support_ticket_triage.yaml` | 1 | `upsert_ticket` |
| `data/knowledge_base_sync.yaml` | 2 | `create_page`, `get_page` |
| `data/record_sync.yaml` | 2 | `list_changed`, `upsert` |
| `productivity/email_to_task.yaml` | 1 | `create_task` |
| `productivity/morning_briefing.yaml` | 1 | `due_tasks` |
| `productivity/weekly_review.yaml` | **0** | — (stale declaration, see §6) |

**Target systems named by each workflow's own config defaults:**

- CRM (`crm`, default `airtable`; options hubspot/salesforce/airtable, +notion in lead_intake)
- Tracker (`tracker`, default `linear`; options linear/jira/notion/airtable)
- Knowledge base (`kb`, default `notion`; options notion/airtable)
- Record sync (`system_a` default hinted `notion`, `system_b` default hinted `todoist`)
- Task store (`task_store`, default `google_tasks`; options google_tasks/todoist/notion/memory)

**Current state — three separate facts:**

1. `MCP_RUNTIME_ENABLED=false` (`mini_kio/core/config.py:181`).
2. Only one server is configured: `KIO_MCP_SERVERS = [{"server_id":"executor","command":".../npm/executor.cmd","args":["mcp"]}]`.
   `executor` is a third-party npm tool-catalog aggregator (`executor@1.6.7`,
   github.com/UsefulSoftwareCo/executor) — not a CRM/Notion/Linear/Todoist integration.
3. **No MCP server in the repository exposes any of the 10 required tools.** Registered tools across
   all bundled KIO servers (`mini_kio/core/mcp/servers/*.py`) are only `github_*`, `docker_*`, `pg_*`,
   `redis_*`, plus filesystem/git/sqlite/terminal. Nothing in KIO maps `crm_upsert`-style action names
   to a server/tool — `execute_mcp_tool` (`execution_boundary.py:1446`) calls a tool named *literally*
   after the action (`app_operator.py:5055` → `tool_name = inputs.pop("tool_name", cap)`).

**Conclusion:** enabling MCP is **necessary but not sufficient**. Flipping the flag alone would move
these 7 workflows from a preflight block to an execution failure ("tool not found"). **Enabling MCP
does not, by itself, unblock any workflow.**

**Not asked for here:** no credentials are being requested for any target system. The gap is an
MCP integration contract, and it should be resolved as a contract decision first.

**Separate observation (not a 63-workflow blocker):** the bundled in-process MCP servers are
registered into `MCPServerRegistry`, but `execute_mcp_tool` goes through `MCPRuntime`, which only
loads servers from `KIO_MCP_SERVERS`. So KIO's own bundled MCP servers are currently unreachable
from the `mcp_tool` capability. Flagging it; not fixing it under this gate.

---

## 5. Item 3 — Browser backend (no new dependency; one approval)

**Class: INFRASTRUCTURE (already present) + CODE DEFECT. Not a credential.**

**Workflows affected — 5, and every one explicitly declares its provider as Playwright:**

| Workflow | Step |
|---|---|
| `browser/page_change_monitor.yaml` | `browser.fetch_region` |
| `browser/price_monitor.yaml` | `browser.extract_price` |
| `browser/structured_extract.yaml` | `browser.extract_records` |
| `research/competitor_monitor.yaml` | `browser.snapshot_sources` |
| `research/web_scrape_to_report.yaml` | `browser.crawl_extract` |

All five declare `providers_required: [playwright, …]`. **The intended backend is Playwright.**

**Existing infrastructure is complete — nothing to install:**

- `playwright 1.61.0` (Python) installed; Chromium binaries present in `AppData/Local/ms-playwright`
  (`chromium-1234`, `chromium_headless_shell-1234`, …).
- `BrowserRuntime` (Playwright) + the Chrome-extension Browser Connector both exist; the capability
  layer already accepts either (`execution_boundary.py:174` `_browser_backend_missing`).
- **No Browser Use / Selenium / any other browser-agent framework was installed, and none is needed.**

**[live] proof the backend works** (real Chromium, real navigation, real extraction):

```
browser runtime started: True | start_error: None
workspace exists: True
new_tab: True tab_1_...
EXTRACTED: Example Domain  This domain is for use in documentation examples without
           needing permission. Avoid use in operations.  Learn more
```

**Correction to my previous report:** browser was *not* blocked. `_browser_backend_missing("")`
returns `[]` → readiness is `browser backend connected`. My earlier "browser (5) blocked" line was a
**harness false negative** (that preflight ran without `bootstrap_runtime()`, so `get_runtime()`
returned `None`). With the real bootstrap these 5 workflows pass preflight.

**The actual defect (needs your approval to fix):** `mini_kio/core/browser_operator.py:519-556`.
`_browser_goto_and_extract` tries the extension connector first. When the connector reports
connected but the *separate* JS-bridge extension is not, it **returns the failure at line 551**
instead of falling through to the BrowserRuntime/Playwright fallback that sits immediately after.

**[live] repro:**
```
browser_fetch_region("https://example.com")  ->  success: False
                                                 "Extraction failed: not connected"
(same page, BrowserRuntime path)             ->  success: True, real page text
```

Smallest existing-compatible backend = **the Playwright runtime you already have.** The fix is to let
the connector branch fall through to the fallback instead of returning early; it affects
`fetch_region`, `extract_records`, `crawl_extract`, `snapshot_sources`, `extract_price`.
**Approve and I will apply it** (no installs, no YAML changes, no config change).

---

## 6. Item 4 — Social publishing (platform decision required)

**Class: PROVIDER IMPLEMENTATION REQUIRED. Not a credential decision yet.**

- **Exactly one workflow** requires `publish` / `verify_posts`: **`media/content_repurpose.yaml`**
  (steps: `ai_reasoning.adapt_per_platform` → `workflow.request_approval` → `media.publish` → `media.verify_posts`).
- **Intended platform, as far as the contract states it:** config
  `platforms: {type: array, default: [linkedin, x, instagram], required: true}`. So the YAML's *default*
  names LinkedIn, X and Instagram — but the type is a free-form array, so this is a default, not a
  binding single target.
- **No adapter exists for any of them.** The media router (`app_operator.py:3792-3837`) accepts
  `publish`/`verify_posts` only for YouTube/Spotify providers, and both are media-*control* only
  (play/pause/search) and are explicitly rejected for publishing. Repo-wide there is **no** LinkedIn /
  X / Instagram publishing code — only URL and display-name mapping tables
  (`browser_session_registry.py`, `target_ref.py`, `runtime_response_formatter.py`).
- Credential named by the workflow: `platform_creds` (oauth2, scope `publish`). **Not requested.**

**Missing contract:** one social-publishing adapter + which platform it targets. Decision needed
before any credential is requested.

---

## 7. Item 5 — Scanner (service decision required)

**Class: PROVIDER IMPLEMENTATION REQUIRED. Not a credential decision yet.**

- `scanner_creds` is declared by **exactly one** workflow: **`monitoring/security_scan_alert.yaml`**
  (config `scanners: {type: array, default: [urlscan, virustotal]}`).
- **Concrete service names do appear** — in that YAML's own default and provenance line
  ("Phishing analysis URLScan.io and Virustotal"). But **nothing implements them**: no URLScan or
  VirusTotal client, key handling, or integration exists anywhere in the repository.
- `knowledge.multi_scan` is **not implemented** by `KnowledgeProvider` (its handler map has no
  `multi_scan`; unknown actions return `"unknown action"`), and `step_runner.py:304` aliases
  `("knowledge","multi_scan") → "web_search"`. As written, a scan step would resolve to a *web search*,
  not scan verdicts — a semantic mismatch, not a credential gap. This workflow is **not** currently
  flagged as blocked, which is itself misleading.
- The other monitor, `development/dependency_monitor.yaml`, does **not** use `scanner_creds` — it uses
  `github.dependency_scan`, which now works with the installed PyGithub. Its only remaining preflight
  block is a stale `http` declaration (§8).

**Missing contract:** which scan service to implement. No credentials requested.

---

## 8. Item 6 — Slack / Teams status (implement-or-exclude decision)

**Class: PROVIDER IMPLEMENTATION REQUIRED (+ a NEW external credential *if* you choose to implement).**

- `status_cred` is declared by **exactly one** workflow: **`productivity/calendar_to_status.yaml`**
  (config `status_target: {enum: [slack, teams], default: slack}`, `dnd`, `busy_text`).
  So Slack **is** specified — as the default status target — with Teams as the alternative.
- **Nothing implements either.** No Slack or Teams API client exists; the only occurrences are
  desktop application-name and display-name mapping tables (`operational_health.py`, `credential_vault.py`,
  `desktop_state.py`).
- **`communication.set_status` / `clear_status` are fake-success stubs**
  (`app_operator.py:3943-3947`: they return `success: True` with a message and perform no side effect).
  Confirmed by reading the branch. **They are not counted as FULL, and I have not turned them into FULL.**

**Related but different:** **28** workflows offer `slack` as a channel option and **9 default to it**
(incl. `lead_intake_crm`, `support_ticket_triage`, `security_scan_alert`, `dependency_monitor`,
`data/form_intake`, `research/competitor_monitor`, `development/pr_review_prep`, …). For those,
`communication` is a genuinely available capability (channels configured: **telegram, discord**) and
Slack is a runtime *config choice* — not a preflight blocker and not a credential requirement unless
you actually want Slack delivery.

**Decision:** implement a real presence adapter (would require a **new** Slack or Teams credential —
not requested yet) **or** declare `calendar_to_status.yaml` out of the 63-workflow FULL scope so the
stub stops being mistaken for a pass.

---

## 9. Oracle precision — false blocks and a false pass (approval required)

**Class: harness/availability-oracle defects, not credentials.**

**a) `media` is blocked wholesale (4 workflows) — 2 of those are false.**
`_UNIMPLEMENTED_CAPABILITIES["media"]` rejects the whole capability because of the publishing gap.
Per-action truth:

| Workflow | media action | Reality |
|---|---|---|
| `media/content_repurpose.yaml` | `publish`, `verify_posts` | **genuinely missing** (no adapter) |
| `ai/image_generate.yaml` | `generate_image` | **genuinely missing** — router returns `"Media: unknown action generate_image"`; needs an image-model provider |
| `communication/voice_assistant.yaml` | `text_to_speech` | **implemented** (`media_ops.text_to_speech`) — false block |
| `files/drive_to_social.yaml` | `transcode_variants` | **implemented** (`media_ops.transcode_variants`) — false block |

**b) Stale capability declarations (3 false blocks).** 26 declared-but-unused capability entries exist
across 25 workflows. Three of them currently cause preflight failures for workflows that have no such
step:
`productivity/weekly_review.yaml` (`mcp_tool`), `development/dependency_monitor.yaml` (`http`),
`research/daily_brief.yaml` (`http`).
I have **not** pruned them, because editing the recovered library's manifest is a contract change and
your instruction is to leave the YAMLs alone — the correct fix is in the resolver's declaration
handling, not the YAML.

**c) One false pass.** `productivity/calendar_to_status.yaml` passes preflight today and would report
FULL while doing nothing, because of the §8 stub.

Fixing (a) + (b) makes the matrix both narrower and larger, honestly: **9 genuinely blocked**, not 14.

---

## 10. Credential / configuration / dependency / implementation split

| Item | CREDENTIAL | CONFIGURATION | DEPENDENCY | IMPLEMENTATION |
|---|---|---|---|---|
| PyGithub | no | no | **yes — resolved** | n/a |
| MCP runtime | no (yet) | **yes** (`MCP_RUNTIME_ENABLED`, integrations) | no | **yes** — 10 MCP tools unprovided |
| Browser | no | no | **no — already installed** | code path fix only |
| Social publish | later (`platform_creds`) | no | no | **yes** — publishing adapter |
| Scanner | later (`scanner_creds`) | no | no | **yes** — scan client + `multi_scan` |
| Slack/Teams status | later (new) | no | no | **yes** — presence adapter |

No credential problem is being presented as a configuration problem, or vice versa.

---

## 11. Not recreated / not touched

- **No** new GitHub token, Google OAuth client, Google project, or Google credential.
- **No** duplicate provider, LLM framework, MCP gateway, vector store, or memory system.
- **No** workflow YAML modified; the recovered library and commit `c6c6748` corrections are intact.
- **No** fake provider, no mocked external call, no bypass of `ExecutionBoundary`/`CredentialVault`.
- **No** secret printed anywhere in this document or in the session output.
- 650 MB stack limit respected: nothing heavy was added; PyGithub/PyJWT/PyNaCl are small and the
  existing lazy provider behaviour is unchanged.

---

# USER ACTIONS REQUIRED

Everything below is a decision or an approval. **No credentials are being requested yet.**

| # | Action | Why | Applies to | Reuse existing? |
|---|---|---|---|---|
| 1 | **Approve the browser fallback fix** | Without it the 5 browser workflows fail even though the Playwright backend works | 5 browser workflows | Yes — existing Playwright |
| 2 | **Approve the oracle-precision fix** (§9) | Stops the matrix showing 5 false blocks and 1 false pass | 6 workflows | n/a |
| 3 | **Decide MCP** (§4): enable `MCP_RUNTIME_ENABLED` **and** how the 10 tools are provided | Enabling alone unblocks nothing | 7 workflows | No MCP integration exists |
| 4 | **Decide the publishing platform** (§6) | One adapter is the smallest real fix | `media/content_repurpose.yaml` | No adapter exists |
| 5 | **Decide the scan service** (§5/§7) | `multi_scan` is currently aliased to a web search | `monitoring/security_scan_alert.yaml` | No client exists |
| 6 | **Decide Slack/Teams status** (§8): implement, or exclude the workflow | Stub currently reports fake success | `productivity/calendar_to_status.yaml` | No client exists |
| 7 | **Approve appending `PyGithub==2.10.0` to `requirements.txt`** | Manifest already installed but unrecorded; file is UTF-16LE so it needs an encoding-preserving write | — | n/a |

**Explicitly NOT required:** Google OAuth reauthorization · a new GitHub token · Notion token ·
Todoist token · LLM keys · Telegram config · any new browser framework.

**Not yet requested, and deliberately deferred until the decisions above:** `platform_creds`
(social publishing), `scanner_creds` (scan service), `image_provider` (image generation),
a Slack/Teams credential (presence).

Stop point: this gate is unresolved until items 1–7 are answered. Phase 7 has not been started.
