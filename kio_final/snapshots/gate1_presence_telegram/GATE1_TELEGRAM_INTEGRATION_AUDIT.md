# Gate 1 — Telegram Integration Audit

## Scope
First Gate 1 objective: attach Telegram as the first real runtime interaction surface.

References:
- KIO Architecture v1.1
- `GATE0_ENGINEERING_AUDIT.md`
- `GATE1_EXECUTION_PLAN.md`
- `RUNTIME_ARCHITECTURE_SNAPSHOT.md`

This phase is **not** feature expansion. It establishes a runtime-owned communication bridge only.

---

## 1. Telegram Integration Audit (Current State)

| Area | Before Gate 1 | Gap | Gate 1 Target |
|------|----------------|-----|---------------|
| Process boot | `runtime.run_runtime()` owns bootstrap | None | Preserved |
| Channel attach | `start_runtime_channel(runtime, "telegram", run_bot)` | None | Preserved |
| Message routing | Telegram called `command_router.route()` directly | Bypassed runtime ownership plane | `dispatch_channel_input()` |
| Execution | `handle_command()` → `execute_action()` | Already correct | Preserved |
| Auth | `ALLOWED_USER_IDS` in adapter | Correct (channel concern) | Preserved in adapter |
| Failure isolation | Handler try/except; PTB error handler | No runtime trace on input | Trace + integrity on dispatch only |
| Shutdown | `start_runtime_channel` finally → `mark_stopped` | No explicit `request_shutdown` on PTB stop | Request shutdown before stop |

**Verdict:** Runtime nucleus and execution boundary were Gate-0-ready. The missing piece was a **runtime-owned channel input handoff** between the Telegram adapter and `command_router`.

---

## 2. Runtime / Channel Ownership Review

```
┌─────────────────────────────────────────────────────────────┐
│  RUNTIME (owner)                                            │
│  bootstrap · lifecycle · context · integrity · trace        │
│  dispatch_channel_input()  ← NEW Gate 1 entry               │
└───────────────────────────┬─────────────────────────────────┘
                            │ attaches after READY
┌───────────────────────────▼─────────────────────────────────┐
│  TELEGRAM ADAPTER (kio_bot.py)                              │
│  PTB polling · auth · typing · reply formatting · errors    │
│  MUST NOT: boot process · call operators · bypass router    │
└───────────────────────────┬─────────────────────────────────┘
                            │ thread handoff (async → sync)
┌───────────────────────────▼─────────────────────────────────┐
│  COMMAND ROUTER → EXECUTION BOUNDARY → OPERATORS            │
└─────────────────────────────────────────────────────────────┘
```

| Responsibility | Owner |
|----------------|-------|
| Lifecycle (`init`→`ready`→`running`→`stopped`) | `runtime.py` |
| Channel attach/detach semantics | `runtime.py` |
| Channel input trace + context | `runtime.py` |
| User authorization | Telegram adapter |
| Transport (polling, handlers) | Telegram adapter |
| Intent routing | `command_router.py` |
| Side effects | `execution_boundary.py` → operators |

Telegram **must not** own bootstrap, lifecycle, or operator invocation.

---

## 3. Proposed Lightweight Telegram Adapter Structure

Keep a single adapter module (no framework). No new `channels/` package yet — avoids import churn.

```
kio_final/
  kio_bot.py                    # Telegram adapter (transport only)
  mini_kio/core/
    runtime.py                  # dispatch_channel_input, format_channel_reply
    command_router.py           # handle_command (unchanged routing)
    execution_boundary.py       # execute_action (unchanged)
    config.py                   # TELEGRAM_TOKEN, ALLOWED_USER_IDS
```

Future Gate 1 channels can mirror the same pattern: adapter → `dispatch_channel_input(channel=...)`.

---

## 4. Runtime / Channel Attachment Flow

```text
process start
  → bootstrap_runtime()           # state: init → ready
  → TELEGRAM_TOKEN present?
       yes → start_runtime_channel("telegram", run_bot)
               → mark_running("telegram")
               → build_application()
               → app.run_polling()  [blocks]
               → request_shutdown() on exit
               → mark_stopped()
       no  → host_runtime()         # idle host, no channel
```

Per-message flow:

```text
Telegram Update (text)
  → adapter: auth check
  → asyncio.to_thread(dispatch_channel_input, ...)
  → runtime trace: runtime_channel_input
  → command_router.handle_command
  → execution_boundary.execute_action (when applicable)
  → normalized dict result
  → format_channel_reply
  → adapter: reply_text (truncate 4000)
```

---

## 5. Graceful Startup / Shutdown

**Startup**
1. `setup_startup_logging()`
2. `bootstrap_runtime()` → `ready`
3. Lazy-import Telegram libs only when channel starts
4. `mark_running("telegram")` before polling

**Shutdown**
1. Ctrl+C / polling end → `KeyboardInterrupt` or normal return
2. `runtime.request_shutdown()` in `run_bot` finally
3. `start_runtime_channel` finally → `mark_stopped()`
4. Trace: `runtime_channel_stop`

Runtime host without Telegram: `host_runtime()` idle loop until interrupt.

---

## 6. Failure-Isolation Strategy

| Failure | Behavior | Runtime impact |
|---------|----------|----------------|
| Single message handler exception | Log + user-safe reply | None (no lifecycle change) |
| PTB library error | `handle_error` logs only | None |
| `dispatch_channel_input` exception | Normalized error dict + integrity warning | Trace only; no `mark_degraded` |
| Polling crash / attach exception | `mark_degraded("channel_failure")` + re-raise | Degraded then stopped in finally |
| Missing token | Skip channel; `host_runtime` | Stays `idle` |

Principle: **message-level failures are isolated**; **channel-level failures** may mark degraded but must not corrupt execution boundary state.

---

## 7. Exact Files Requiring Edits

| File | Change |
|------|--------|
| `mini_kio/core/runtime.py` | Add `dispatch_channel_input`, `format_channel_reply` |
| `kio_final/kio_bot.py` | Call runtime dispatch; shutdown hook; store runtime in bot_data |
| `mini_kio/core/command_router.py` | `route()` delegates to runtime dispatch (selftest compat) |

No changes to: `execution_boundary.py`, operators, `task_engine.py`, LLM, voice, camera, UI.

---

## 8. Implementation Diff Plan

1. **runtime.py** — `dispatch_channel_input(text, *, channel, user_id)` with trace, context, guarded dispatch to `handle_command`; `format_channel_reply(result)` for channel text.
2. **command_router.py** — `route()` calls runtime dispatch (bootstrap selftest must call `bootstrap_runtime()` first or route still works via dispatch nil-runtime guard).
3. **kio_bot.py** — Replace `route()` with `dispatch_channel_input` + `format_channel_reply`; `run_bot` finally requests shutdown; pass runtime via `bot_data`.

---

## 9. Expected Runtime Behavior After Integration

1. `python -m mini_kio.core.runtime` or `python kio_bot.py` boots runtime first.
2. With valid `TELEGRAM_BOT_TOKEN`, Telegram attaches; state `running`.
3. Text message → runtime trace `runtime_channel_input` → router → boundary → reply.
4. `/start`, `/help` remain adapter-handled (transport UX); free-text uses runtime dispatch.
5. Handler errors return safe message; runtime keeps polling.
6. Ctrl+C stops polling, requests shutdown, transitions to `stopped`.
7. Without token, runtime idles with no Telegram import.

---

## Gate 1 Success Check (This Objective)

- [x] Runtime boots cleanly
- [x] Telegram attaches after bootstrap
- [x] Text routes through runtime-owned dispatch
- [x] Execution still flows through existing boundary
- [x] Message failures do not collapse runtime
- [x] Shutdown remains graceful
