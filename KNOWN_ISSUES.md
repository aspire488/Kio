# KNOWN_ISSUES.md

## Pre-existing (present at baseline, NOT introduced by this slice)
- `tests/test_entity_persistence_fix.py` — 7 failures (`TestFixD_StandaloneEntity`,
  `TestFixD_UnboundLocalError`): the tests import `_is_standalone_entity_query` from
  `mini_kio.core.command_router`, a symbol that does not exist in the current
  `command_router.py`. The "Fix D" production change was never applied. The fix
  tests were written for a not-landed refactor; either land the function or
  delete/adjust the stale tests. (Note: `tests/test_regression_pending_action.py`
  itself PASSES — an earlier doc claimed its collection failed; that was a
  mis-attribution.)
- ~60-100 suite failures: DuckDuckGo 403, missing optional packages
  (`curl_cffi` etc.), LLM provider count assertions, network-dependent RAG tests,
  and live-API dependence in two recovery-truthfulness tests (see below). All
  unrelated to production paths fixed here.
- `tests/test_regression_recovery_truthfulness.py` — 2 failures
  (`test_play_accepts_playing_despite_stale_paused_payload`,
  `test_play_retries_timing_failure_until_playing`) when a real `YOUTUBE_API_KEY`
  is present in `.env`: the mock connector's `search_results` returns no
  candidates, but the live API path returns real candidates, arming the RC8
  identity gate against a mock-loaded URL. Environment-dependent, not a
  production defect.

## Deferred (documented, not required for this slice)
- **Expand-on-demand loop:** after "Want more detail?", a follow-up "yes" re-enters
  the normal classifier. A dedicated expand path (re-ask LLM without the short-first
  cap) would complete the short-first contract.
- **Schema orientation:** `preference_{subject} → like` is inverted (subject in key,
  sentiment in value). Recall logic depends on it; migration touches
  `memory_store.py`, `fact_repository.py`, and all recall branches.
- **Dead `mini_kio/llm/providers/` v2 package:** zero callers (provider_metadata.py,
  etc.). Delete or wire it.
- **NVIDIA providers** (Maverick/GPT-OSS/Vision/Fallback) from the task brief not
  wired. Add as `DirectHTTPProvider` registrations + `_TASK_PROVIDER_PREFERENCE`
  entries when keys exist.
- **Duplicate artifact vocabulary:** artifact/followup word lists live in two places
  (continuity_engine `_artifact_kws`, integration_adapter `ref_words`). Shared module
  = upgrade path.
- **LLM package deprecation warning:** `google.generativeai` is deprecated in favor
  of `google.genai` (warning shown at import). Migration is cosmetic until the
  deprecated package is actually removed upstream.
- **MEDIA-SELECTION: OPEN.** KIO can select a lexically related but semantically
  incorrect YouTube result for ambiguous/short media queries. Examples:
  `Play brand new day`, `Play lm game trailer`. Likely ownership: media entity
  resolution / query understanding / candidate retrieval — NOT basic playback
  transport. Scoring heuristics (RC7-RC10) mitigate but do not fully solve it.
- **SHORTS-CONTROL: OPEN / INVESTIGATION PENDING.** Pause/resume behavior for
  YouTube Shorts is not yet confirmed reliable, despite normal YouTube video control
  working. No root cause asserted for Shorts.

## Resolved (this slice, 2026-08-09)
- **Browser/application close policy:** `close_app` previously refused every
  non-tracked target ("I didn't open X, so I can't close it"). Registered apps
  (browser or not) running without a KIO-tracked PID are now discovered safely by
  registry process name (helper-process aware) and closed with tree-aware
  verification; registered apps not running report truthfully ("wasn't running");
  unregistered apps keep the strict ownership refusal.
- **Close response truthfulness:** close outcomes are classified
  (SUCCESS / SUCCESS_WITH_RESIDUALS / NOT_RUNNING / FAILED) and the user-facing
  message is concise and never self-contradictory (no more "Closed chrome. Primary
  browser process terminated, but helper processes may persist.").
- **Stale `runtime_ready.flag`:** the flag is now overwritten on every successful
  bootstrap with the live PID + timestamp + component readiness, so a dead process
  can never leave an authoritative-looking marker. Authoritative readiness remains
  `get_runtime_snapshot()`.
- **YouTube Data API quota:** explicit 429 classification (`QUOTA_EXHAUSTED`), no
  key leakage, no retry storm, silent degrade to the browser-scrape path which keeps
  intelligent candidate scoring.
- **YouTube playback start:** the extension `play` script now prefers the YouTube
  player API (`#movie_player.playVideo()`) over a raw `video.play()`, which the
  player controller could reconcile back to paused (playback never started).
- **Retry architecture:** the provider's play loop no longer re-triggers the full
  state-verification deadline on every retry/stabilization poll (raw connector for
  the loop; the provider's own player-state/currentTime acceptance is the
  verification). Definitive verification failures are not retried; lost tabs are
  classified and fail truthfully.
- **Extension build single source of truth:** `_EXPECTED_BUILD` (state_verification)
  and `_EXPECTED_EXTENSION_BUILD` (connector) now import from
  `mini_kio/browser_connector/build.py` instead of duplicating a literal.

## Live-Environment Validation Pending
- Real LLM provider responses (Gemini/Groq/Cerebras…) — requires live keys in `.env`.
- Live Telegram round-trip via `kio_bot.py` (transcript validation per task brief).
- Live Playwright browser tab ops (headful Chrome + `BROWSER_RUNTIME_*` env).
- Task-tier routing under real multi-provider load.
