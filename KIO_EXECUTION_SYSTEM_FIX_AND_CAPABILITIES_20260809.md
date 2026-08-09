# KIO Execution-System Fix + Capabilities Report — 2026-08-09

## 1. Root causes identified (system level)

The live failure `Open ChatGPT` → `Close it` → **whole Chrome session killed** was the
symptom of a systemic defect, fully proven from code:

| # | Root cause | Evidence |
|---|-----------|----------|
| BC-1 | **Target collapse**: `close_app` did `key.split("::")[0]` on capability-serialized targets, turning `chrome::open_url::https://chat.openai.com::chatgpt` into `chrome` and then killing the browser | `app_operator.py` (removed) |
| BC-2 | **Scope escalation**: `_exec_browser.close_tab` fell through to `execute_action("close_app", ...)` when the tab wasn't found, escalating tab-scope → process-scope | `pipeline/__init__.py` (fixed) |
| BC-3 | **Raw serialized targets stored as referents**: `context_manager.update` and `remember_runtime_context` stored `result["target"]` verbatim — the `::`-chain became the conversational referent, so `Close it` spliced the internal serialization into the command | `context_manager.py`, `pipeline/__init__.py`, `execution_boundary.py` (fixed) |
| BC-4 | **Unverified open**: web opens returned `verification_mode: "noop"`; success was asserted, not verified against tab identity | `app_operator.py` (fixed: tab-identity probe) |
| BC-5 | **Response leakage**: `format_close_app`/`format_open_app` capitalized the raw target → "Closed chrome::open_url::https://...::chatgpt, but some background processes..." | `runtime_response_formatter.py` (fixed: safe display names) |
| BC-6 | **Multi-action false success**: `_summarize_steps` emitted "done - opened A and B" from unverified ACKs; `_execute_multi_step` aborted remaining steps on first failure | `command_router.py` (rewritten) |

Full forensic trace: `KIO_TARGET_IDENTITY_FORENSIC_AUDIT_20260809.md`.

## 2. System-level fixes

### New: `mini_kio/core/target_ref.py` — canonical target identity
- `parse_target()`: parses capability strings, URLs, browser names, web-app hints into
  structured refs `{kind, name, browser, url, capability}` (app/browser/tab/webapp/media).
- `safe_target_name()`: user-safe referent (never URL / `::` chain, preserves case for
  media queries).
- `display_target_name()`: brand-cased display name (chatgpt → ChatGPT, youtube → YouTube).

### `app_operator.py` — close can never kill the host browser
- Removed `key.split("::")[0]` collapse.
- Capability-serialized / web-app targets route to `_close_web_target()`: capability-registry
  session close → connector tab close → truthful "Couldn't find X open in the browser."
  Never a browser-process kill.
- `execute_capability` connector open now verifies tab identity (`_verify_web_tab_opened`).

### `pipeline/__init__.py` — no scope escalation; capability routing
- `close_tab` never escalates to `close_app` except through the web-aware close path.
- `focus`/`switch` gains native-app window focus fallback.
- `list_tabs` ("What's open?") now includes KIO-tracked running apps.
- Classifier: `what's open` / `what am i using` → desktop state; `what's playing` → media.
- Composer stores safe referents in the runtime context buffer.

### `command_router.py` — truthful multi-action aggregation
- `_run_single_step()`: every step routed through the same verified path as single commands
  (browser-vs-app close decision, native focus fallback, capability open routing).
- `_execute_multi_step()`: no early abort; all steps run; result = honest aggregate.
- `_summarize_steps()`: verb-grouped, partial-aware ("Opened ChatGPT, but I couldn't open
  Telegram."), never a blanket "done -".

### `context_manager.py` / `execution_boundary.py` / `runtime_response_formatter.py`
- Referents and runtime buffer store `safe_target_name()` — never raw serialization.
- Formatters render brand-cased display names; raw URLs/`::` chains cannot leak.
- `noop_probe` now preserves an honest operator-provided `verification_status` (unverified
  stays unverified; an ACK is no longer silently upgraded to "verified").

## 3. New capabilities (enabled by the fixes)

### Capability A — Context-aware computer control
- **"What's open?" / "What am I using?"** → lists browser tabs **and** KIO-tracked running
  apps (live-tested: "Open right now: 1. ChatGPT ... Apps: Chrome").
- **"Switch to X" / "Focus X"** → browser tab focus first, native-app window focus fallback.

### Capability B — Composed multi-action tasks
- "Open ChatGPT and Telegram" decomposes into independently resolved+verified steps with a
  truthful aggregate (live-tested: "Opened ChatGPT and Telegram.").
- No early abort; partial success is reported honestly.

### Capability C — State-aware media / contextual media control
- **"What's playing?" / "What's on?"** → `MediaManager.now_playing()` reads the live media
  registry (live-tested: "Paused on Never Gonna Give You Up.").
- "Pause it" / "Resume it" resolve the same media entity and report verified state
  (live-tested: Paused. → What's playing? → Resumed., with position advancing).

## 4. Files changed

| File | Change |
|------|--------|
| `mini_kio/core/target_ref.py` | **NEW** — canonical target identity + safe/display names |
| `mini_kio/core/app_operator.py` | close_app no-collapse + `_close_web_target` + `_verify_web_tab_opened`; brand-cased messages |
| `mini_kio/core/command_router.py` | `_run_single_step`, truthful `_summarize_steps`, no-abort `_execute_multi_step` |
| `mini_kio/core/pipeline/__init__.py` | close_tab no-escalation, focus native fallback, list_tabs + apps, what's-open/now-playing classifier, safe referents |
| `mini_kio/core/context_manager.py` | referent sanitization via `safe_target_name` |
| `mini_kio/core/execution_boundary.py` | safe referents; `noop_probe` preserves honest verification status |
| `mini_kio/core/runtime_response_formatter.py` | `display_target_name` for open/close |
| `mini_kio/media/media_manager.py` | `now_playing()` capability |

## 5. Tests

- **New**: `tests/test_target_identity_fixes.py` — 26 tests covering target parsing, close
  no-escalation (never calls `_find_matching_process_pid` for web targets), referent
  sanitization, formatter sanitization, multi-step truthfulness, capability classification,
  media now-playing.
- **Targeted regression**: 200 passed (state verification, connector reconnect, pause/resume,
  EFG routing, R11 search, pending action, history pollution, media recovery, truthfulness,
  fix-batch, target-identity, gate5 registry/repairs).
- **Pre-existing failures unchanged**: gate5 `test_browser_fallback_stable`,
  `test_emoji_sanitization`, `test_consciousness_denial`, `test_consciousness_alive`,
  `test_freshness` — verified identical on the stashed baseline (test defects mocking
  `command_router.execute_action`, which never existed at module level).

## 6. Live Telegram verification (real bot, one message at a time)

| Test | Message | Reply | Actual state | Latency | Result |
|------|---------|-------|--------------|---------|--------|
| T1 | Open ChatGPT | Opened ChatGPT in Chrome. | Tab opened | 19.4s | ✅ |
| T2 | Close it | Closed ChatGPT tab. | **Chrome alive (24→26 procs)** — only the tab closed | 1.7s | ✅ |
| T3 | What is open? | Open right now: 1. ... ChatGPT ... Apps: Chrome | Tabs + apps listed | 1.7s | ✅ |
| T4a | Play Never Gonna Give You Up | Playing Never Gonna Give You Up. | `PLAY_VERIFY_FINAL paused=False` | 22.4s | ✅ |
| T4b | Pause it | Paused. | `state=paused position_s=11.77` | 3.3s | ✅ |
| T4c | What is playing? | Paused on Never Gonna Give You Up. | Live registry read | 1.7s | ✅ |
| T4d | Resume it | Resumed. | `state=playing position_s=11.83` | 1.7s | ✅ |
| T5 | Open ChatGPT and Telegram | Opened ChatGPT and Telegram. | Both tabs verified | 21.0s | ✅ |
| T6 | Hi during media | Hey! What's on your mind? | 1.67s while media still running; media → "Playing Dangal Trailer." | 1.7s | ✅ |
| T7 | Close the ChatGPT tab | Closed ChatGPT tab. | Tab-scope close | 3.2s | ✅ |
| T8 | Close Telegram | Closed Telegram tab. | Tab closed, Chrome alive | 1.8s | ✅ |
| T9 | Hi | Hey there. What's up? | Bot alive after all | 1.7s | ✅ |

**Acceptance criteria met:**
- ✅ ChatGPT tab never escalates to Chrome process (the core bug).
- ✅ No raw URLs / `::` chains / internal IDs in any response.
- ✅ No "Error:" or "done -" style leaks.
- ✅ Normal chat responsive during long actions (1.7s while media ran).
- ✅ Media selection + verified playback + truthful pause/resume preserved.
- ✅ App/close verification (calculator/notepad/chrome from prior session) untouched.
- ✅ 3 new capabilities work through the normal execution pipeline.

## 7. Remaining known issues (unchanged, out of scope)
- gate5 test defects listed above are pre-existing (mock the wrong module path).
- `test_response_quality.py` needs a live LLM API (pre-existing).
- Multi-step tasks run sequentially on the dispatcher thread — acceptable; noted for future
  background-task work.

## 8. Git status
Nothing committed (per instruction). New files: `mini_kio/core/target_ref.py`,
`tests/test_target_identity_fixes.py`, `KIO_TARGET_IDENTITY_FORENSIC_AUDIT_20260809.md`,
this report. Modified: the 8 source files listed in §4.

## 9. Next logical milestone
Move multi-step execution to a background task with progress feedback (builds on the
already-proven Telegram concurrency), then extend `SEARCH → ENTITY → ACTION` chaining
("find X and open it") using the same verified capability path.
