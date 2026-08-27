# KIO Telegram Live Validation Protocol

## Purpose

How to perform repeatable live Telegram validation without entering restart loops.

---

## Runtime State

There are only four runtime states.

- STATE_STOPPED
- STATE_STARTING
- STATE_READY
- STATE_VALIDATING

Transitions must be explicit. Never restart from VALIDATING. Never restart twice.

---

## Golden Rule

Exactly ONE runtime may exist. Never create a second runtime. Never poll for startup repeatedly. Never issue another Start-Process while one runtime already exists.

---

## Startup Procedure

If runtime is stopped:

1. Start exactly once.
2. Wait until Telegram reports `Application started`.
3. Then wait until first successful `getUpdates` or first received Telegram message.
4. When READY is reached, write `runtime_ready.flag` (or equivalent runtime marker).
5. Validation begins. Never launch again.

---

## During Validation

Once READY, do NOT use `Start-Process`, `Stop-Process`, `taskkill`, `Get-CimInstance`, `tasklist`, `Get-NetTCPConnection`, port inspection, PID inspection, or startup log inspection, unless runtime actually crashes.

Conversation testing must NEVER restart the runtime.

---

## Code Changes

Small code changes: use in-process probes whenever possible (unit harness, integration harness, `handle_command()`, router probes, memory probes, response probes).

Only restart when code absolutely requires a fresh process. Batch multiple edits together. Never restart after every fix.

---

## Restart Policy

Restart ONLY when:

- Python module changed that cannot reload, OR
- runtime crashed, OR
- configuration changed

Otherwise continue using existing runtime.

Maximum: ONE restart per validation slice.

---

## Live Validation

Conversation, Knowledge, Memory, Browser, Media, Personality, Regression must all happen WITHOUT restarting.

---

## Failure Handling

If one test fails: Fix, retest ONLY that feature, continue. Do not restart entire validation.

---

## Completion

When all tests pass, write `validation_complete.md` with:

- files changed
- live transcript
- remaining issues
- restart count
- restart reason(s)
