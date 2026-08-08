# KNOWN_ISSUES.md

## Pre-existing (present at baseline, NOT introduced by this slice)
- `tests/test_media_intelligence_stabilization.py` — 3 failures: `NameError: name 'logger' is
  not defined` in the acceptance path at `mini_kio/media/intelligence/integration_adapter.py:668`
  (`_handle_acceptance` → `[ARTIFACT_RESOLVE]` log). Fix: add `logger = logging.getLogger(__name__)`
  at module top of integration_adapter.py (import `logging` already present).
- `tests/test_regression_pending_action.py` — collection ImportError: imports
  `_is_standalone_entity_query` from `mini_kio.core.command_router`, which no longer exists
  (renamed/removed). Fix: update the test to the current symbol or delete the stale test.
- ~100 suite failures: DuckDuckGo 403, missing optional packages (`curl_cffi` etc.), LLM provider
  count assertions, network-dependent RAG tests. Unrelated to production paths fixed here.

## Deferred (documented, not required for this slice)
- **Expand-on-demand loop:** after "Want more detail?", a follow-up "yes" re-enters the normal
  classifier. A dedicated expand path (re-ask LLM without the short-first cap) would complete the
  short-first contract.
- **Schema orientation:** `preference_{subject} → like` is inverted (subject in key, sentiment in
  value). Recall logic depends on it; migration touches `memory_store.py`, `fact_repository.py`,
  and all recall branches.
- **Dead `mini_kio/llm/providers/` v2 package:** zero callers (provider_metadata.py, etc.).
  Delete or wire it.
- **NVIDIA providers** (Maverick/GPT-OSS/Vision/Fallback) from the task brief not wired. Add as
  `DirectHTTPProvider` registrations + `_TASK_PROVIDER_PREFERENCE` entries when keys exist.
- **Duplicate artifact vocabulary:** artifact/followup word lists live in two places
  (continuity_engine `_artifact_kws`, integration_adapter `ref_words`). Shared module = upgrade path.
- **Browser close fallback:** closing a browser KIO didn't launch is still refused (strict
  ownership). Optional `taskkill` fallback noted in audits, not implemented.
- **LLM package deprecation warning:** `google.generativeai` is deprecated in favor of
  `google.genai` (warning shown at import). Migration is cosmetic until the deprecated package is
  actually removed upstream.

## Live-Environment Validation Pending
- Real LLM provider responses (Gemini/Groq/Cerebras…) — requires live keys in `.env`.
- Live Telegram round-trip via `kio_bot.py` (transcript validation per task brief).
- Live Playwright browser tab ops (headful Chrome + `BROWSER_RUNTIME_*` env).
- Task-tier routing under real multi-provider load.

## Media Playback & Selection — Status 2026-08-08

**RESOLVED** (committed `b5db667` `fix(media): stabilize YouTube playback and control`):
normal YouTube playback, playback state verification (incl. currentTime), pause/resume on
normal YouTube videos, "play it", "play again", "play next video", controlled YouTube search,
search again, mute, unmute, extension build compatibility, and the connector/media playback path.
Proven root cause fixed: injected player scripts were serialized independently by
`chrome.scripting.executeScript({func: ...})` and referenced `background.js` outer-scope helpers
that did not exist in the page execution context, producing non-state payloads
(`script 'play' returned non-state payload` / `Couldn't play X on YouTube`); the injected
functions are now self-contained. Playback correctness is substantially restored — NOT 100% media
correctness.

- **MEDIA-SELECTION: OPEN.** KIO can select a lexically related but semantically incorrect
  YouTube result for ambiguous/short media queries. Examples: `Play brand new day`,
  `Play lm game trailer`. Likely ownership: media entity resolution / query understanding /
  candidate retrieval — NOT basic playback transport. Do not treat as fixed.
- **SHORTS-CONTROL: OPEN / INVESTIGATION PENDING.** Pause/resume behavior for YouTube Shorts
  is not yet confirmed reliable, despite normal YouTube video control working. No root cause
  asserted for Shorts.
