# BROWSER_COMMAND_FIX_REPORT.md

## Symptom
`list tabs` / `focus tab` / `close tab` always returned "Browser not available" even when
Playwright-backed `BrowserRuntime` was configured. "Open Chrome" worked (subprocess), but tab
management was dead.

## Root Cause
- `bootstrap_runtime` (`runtime.py:1208-1242`) constructs `BrowserRuntime` but **never calls
  `start()`** — it relies on lazy start.
- `browser_operator.py` has a correct lazy-start helper `_get_browser_runtime()` that calls
  `br.start()` once under a lock.
- But `command_router._use_browser_runtime()` only checked the `_started` flag directly and never
  triggered the start. So every tab command fell through to the connector fallback → "Browser not
  available".

## Fix
`command_router._use_browser_runtime()` now delegates to `browser_operator._get_browser_runtime()`
instead of peeking at `_started`. First tab command lazily boots Playwright; subsequent calls
reuse the running instance. Failure is handled (returns None → existing connector/error paths).

## Verification
- `_use_browser_runtime` now returns True iff the runtime actually started (or started just-in-time).
- Full suite: no regression (identical failure set).
- Live browser launch requires Playwright + configured `BROWSER_RUNTIME_*` env vars; not exercised
  headlessly here.

## ponytail: noted
Eager `br.start()` at boot was considered and rejected — lazy start is smaller and avoids an
unused Chrome window at login. If cold-start latency on first tab command becomes a problem,
eager-start at `bootstrap_runtime` is the upgrade path.
