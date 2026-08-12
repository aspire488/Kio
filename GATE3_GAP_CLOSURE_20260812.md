# GATE3_GAP_CLOSURE_20260812.md

System-level gap closure (2026-08-12), per the founder directive: fix the
remaining system-level failures first, then generic capability work, then the
Companion Intelligence audit, with real runtime validation before commit.

## 1. DEGRADED ROOT CAUSE — CAPABILITY-GROUP SCOPED GATING (FIXED)

### Exact root cause
The runtime integrity score escalated globally: each failed execution recorded
`execution_failure` with a severity weight (`operator_reported_failure` →
medium → weight 2). After **three** browser-connector outages, the global
`integrity_score` crossed the threshold (6) and `safety_state` became
`DEGRADED`. `check_safety_policy` then blocked **every** `external_open` and
`external_control` action — including native app launch/close, folder opens,
media, and system control — even though those capabilities never failed.

Live trace evidence (`mini_kio/debug/runtime_trace.log.prelive_backup`):
`browser_goto` failures with `elapsed_ms: 30537` and
`runtime_safety_escalation` → DEGRADED, after which all native actions were
blocked with "System is DEGRADED. Action category 'external_open' is blocked."

### Canonical fix (no safety gate removed)
- `mini_kio/core/runtime.py`:
  - `classify_capability_group(action, target)` — pure group classifier
    (browser / native / media / system / other).
  - Per-group integrity scores (`integrity_group_scores`) and a degraded-group
    set (`degraded_capability_groups`). A group enters the degraded set only
    when ITS score crosses the threshold.
  - **Benign user-outcome failures never degrade the runtime**: `not_installed`,
    `not_found`, `not_running`, `invalid_url`, `already_open`, etc. are zero-
    weighted (recorded for observability, weight 0).
- `mini_kio/core/execution_boundary.py` — `check_safety_policy` DEGRADED branch
  now blocks only the degraded capability groups. A browser outage blocks
  browser controls while native launch/close, folder, media, and system control
  remain usable. `close_app` keeps its tracked-owned allowance. When no group
  info exists (legacy observer/channel escalation), the conservative fallback
  is preserved unchanged.

### Verified behavior (unit + integration)
- 3× `browser_goto` failure → DEGRADED with `degraded_groups={browser}`;
  native open/close/folder/lock/media ALLOWED, browser blocked.
- 12× `open <nonexistent>` (not_installed) → runtime stays NORMAL, score 0.
- Legacy fallback (no group info) still blocks external_open, allows system_control.
- `manual_runtime_recovery` clears group state too.

## 2. HEALTH ↔ READINESS AGREEMENT

`get_runtime_health_score()` subtracts `integrity_score * 2`; `_kio_health_label`
reads `integrity_status`. Both now derive from the SAME scoped integrity
source, so "KIO's healthy" and execution readiness can no longer disagree:
benign failures add nothing, and a browser-group outage reads as "browser
controls temporarily unavailable" in health AND execution.

## 3. SHARED LATENCY / STARTUP BOTTLENECK — 30s STALE-HANDLE HANG (FIXED)

### Root cause
`BrowserConnector._send_and_wait` awaited `asyncio.wait_for(fut, timeout=30.0)`,
and `is_connected()` returned True for a stale extension handle (WS closed but
not yet reaped by the 30s liveness watchdog). Every browser command against a
down extension hung the full 30 seconds (matches the live 30,537ms trace).

### Fix
- `is_connected()` is now self-healing: it clears a stale/closed extension
  handle synchronously before reporting.
- `_send_and_wait` fast-fails a non-OPEN handle immediately instead of waiting
  the 30s timeout.
- Verified: a CLOSED-handle dispatch returns in <1s (measured 0ms) instead of 30s.

Note: `browser_goto` also retries via BrowserRuntime then `webbrowser.open`, so
the user still gets a working browser even when the connector is down.

## 4. TARGET-INSTANCE SEMANTICS (GENERIC, NOT PER-APP)

Semantic layer (`_detect_browser_webapp`) now distinguishes instance kinds for
browser entities, generically:

| Phrase | Result |
|---|---|
| `open chatgpt` | `execute_capability`, explicit_new=False (dup-prevention applies) |
| `open a new chatgpt tab` | `execute_capability`, instance=tab, explicit_new=True |
| `open another github tab` | same, instance=tab |
| `open chatgpt in a new tab` | same, instance=tab (browser prefix fixed) |
| `open a new browser window for github` | same, instance=window |
| `open another github window` | same, instance=window |
| `open github in a new window` | same, instance=window |
| `launch another calculator` | `open_app`, explicit_new=True (native) |
| `focus chatgpt` / `switch to chatgpt` | `focus` (never a new instance) |

Two live-found bugs fixed:
1. `open a new chatgpt tab` previously routed to NATIVE `open_app` with target
   `"chatgpt tab"` (trailing "tab" leaked into the entity).
2. `open X in a new tab` produced an EMPTY browser prefix (`::open_url::…`)
   which broke `execute_capability` parsing. Now defaults to the configured
   browser.

Executor: `::new` marker → new tab (skips duplicate prevention);
`::newwindow` marker → launches the browser binary with `--new-window` on all
platforms (truthful new-window instance; the Connector is tab-scoped and cannot
create windows).

## 5. SYSTEM-WIDE LLM-BYPASS AUDIT (FIXED)

`what apps do you have` / `what apps does the system have` previously fell
through to LLM/web knowledge. The installed-app inventory family is now fully
deterministic (routed to `operational / app_inventory`, answered by real OS
state via `list_installed_apps`):

- `what apps do you have` / `does the system/computer have`
- `what apps do i have` / `have you got` / `are installed` / `is installed`
- `what software/programs are installed`, `what apps are on my computer`

Knowledge queries stay knowledge: `what is notepad` → information_query.

## 6. COMPANION INTELLIGENCE AUDIT (DOES NOT REBUILD)

Mapped doctrine → implementation. The architecture is already canonical:
- Identity/personality/emotional authority: `mini_kio/llm/KIO_character_knowledge.py`
- Deterministic identity answers: `mini_kio/llm/identity_dataset.py`
- Post-generation enforcement: `mini_kio/llm/identity_guard.py`
- Conversational LLM path with personality context + anti-fabrication:
  `Pipeline._chat_converse`

**One gap fixed**: `what are you curious about` / `what interests you` /
`what excites you` matched the identity dataset's broad `what are you` prefix
and returned the static "who are you" identity instead of a conversational
curiosity response. Added a generic curiosity/interest family
(`_classify_curiosity`) that routes to `converse` BEFORE the identity check.
`who are you` / `what is kio` remain deterministic identity.

Verified routing (opinion/judgment/recommendation/disagreement/emotion/
curiosity all land on the conversational owner; curated opinions like
"what do you think about ai" stay on the deterministic identity owner).

## 7. CLOSE-ALL / EXPLORER GUARD (carried from prior session, verified)

The user directive "never target explorer.exe" remains enforced: close-all
excludes system shells (case-normalized) and verifies remaining state
truthfully. Regression tests lock this in.

## 8. TESTS

New tests in `tests/test_gap_closure_v3.py`:
- `DegradedScopedGatingTest` (4) — scoped degradation, benign non-escalation,
  manual recovery reset.
- `TargetInstanceSemanticsTest` (12) — tab/window/instance/focus semantics +
  empty-browser-prefix regression.
- `LLMBypassAuditTest` (4) — inventory determinism, knowledge stays knowledge.
- `CompanionIntelligenceAuditTest` (5) — opinion/preference/disagreement/
  emotion/curiosity routing.
Updated `tests/test_connector_reconnect.py`: stale-handle self-heal contract +
fast-fail latency test.

Suite results (changed surface): **126 passed, 35 subtests passed**. Full
non-gate3/gate5 suite: **1051 passed, 62 failed** — all 62 failures verified
pre-existing at clean HEAD (memory-intelligence, response-quality, target-
identity layers requiring live LLM providers; gate3 14 failures likewise
pre-existing). Zero regressions from this work.

## 9. FILES CHANGED

- `mini_kio/core/runtime.py` — group-scoped integrity + benign zero-weighting
- `mini_kio/core/execution_boundary.py` — scoped DEGRADED gating
- `mini_kio/core/pipeline/__init__.py` — instance semantics, inventory patterns,
  curiosity family
- `mini_kio/core/app_operator.py` — `::newwindow` executor path
- `mini_kio/browser_connector/connector.py` — is_connected self-heal + fast-fail
- `tests/test_gap_closure_v3.py`, `tests/test_connector_reconnect.py`
- (prior session, in tree) `mini_kio/core/runtime_response_formatter.py`
  truthfulness, `execution_boundary.py` close_all no-arg dispatch,
  `app_operator.py` explorer guard, `tests/test_gap_closure_v3.py`

## 10. REMAINING LIMITATIONS (truthful)

- Unlock of a Windows-locked workstation still requires OS-level
  authentication (`authentication_required`); no user-mode workaround.
- `open a new browser window` depends on the browser binary supporting
  `--new-window` (Chrome/Edge/Firefox/Brave do).
- The 62 pre-existing test failures in memory/response-quality layers need
  live LLM/provider configuration; they are unrelated to this change set.
