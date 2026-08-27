# KIO Capability-Delta — Final Report

**Batch:** Release Watcher, Research Thread, Project Summary, Media Truthfulness/Probe Repair
**Status:** Implemented, real-runtime-validated, 17 focused tests + 409 regression tests green.
**Date:** 2026-08-16

---

## 1. Capability Baseline (before this batch)

KIO already had deterministic owners for: math (`utilities.py` calculator AST), live FX/commodities (Frankfurter), package lookup (PyPI RSS), feed/`what's new` (atom parsing), weather (Open-Meteo), OpenAlex papers, deterministic project-summary-free GitHub access, local file ops, media playback via the Browser Connector (Chrome extension, `MediaManager`), arithmetic word forms, and a 59-test focused suite covering prior batches.

## 2. Gaps Identified

1. **No proactive capability.** KIO answered when prompted; it could not watch a source and push a change out-of-band.
2. **No persistent research thread.** Each question was independent; no brief could be saved, recalled, or continued with "new since last time."
3. **No project summary.** No way to get GitHub repo meta + releases + open issues, or PyPI metadata, deterministically.
4. **Media retrieval probe was dead code.** `RetrievalRouter._try_media_providers` called `yt.play(...)` on a stub contract and could never succeed.
5. **Media play lied when the connector was absent.** The no-connector fallback opened a YouTube *search page* and claimed `Playing X.` (MediaState.PLAYING) — a fabricated success.
6. **Collision risk:** the word "watch" (release-watching vs. media offer-acceptance "watch it").

## 3. High-Value Gaps Selected

Proactivity (watcher), research continuity (thread), developer-oriented project intelligence (summary), and media truthfulness (stop the lie / fix the probe). These span distinct domains: monitoring, research, developer tooling, media — exactly the "several distinct domains" acceptance bar.

## 4. Integrations Investigated / Rejected

- **Browser Connector (existing):** reused as the single verified-playback channel; the honest fallback only fires when connector support is disabled. Not replaced.
- **YouTube Data API:** rejected — requires an API key; the HTML-scrape videoId resolution is keyless.
- **New web-search SDKs:** rejected — research reuses the existing `RetrievalRouter` (Exa/Tavily/OpenAlex/DDGS) rather than adding a dependency.
- **GitHub API:** used keyless (60 req/hr); no token added.
- **`mcp-server-fetch`:** previously found unusable (ecosystem drift); not needed for this batch.

## 5. Actual New Capabilities (deterministic, no LLM)

1. **Release watcher** — `watch owner/repo` / `watch pkg` registers a target; a background poller (`POLL_INTERVAL_S = 60`) checks the feed; a *newer* release than at-add time is pushed to Telegram `sendMessage` out-of-band.
2. **Watch management** — `stop watching X` / `unwatch X` / `what am I watching`.
3. **Research thread** — `research <topic>` persists a brief (top sources, deduped by URL); `research brief on <topic>` recalls it; `continue research on <topic>` re-gathers and reports only *new* sources; `what did I research` lists topics.
4. **Project summary** — `summarize the project owner/repo` → GitHub description, language, stars, latest releases, top open issues (PRs excluded); bare name → PyPI metadata.
5. **Media probe repair** — `_try_media_providers` now uses the real `search()` contract (`MediaResult.success/.candidates`, `top.title/url`).
6. **Honest no-connector playback** — opens the *actual* resolved video (`_resolve_search_to_watch_url` → real `watch?v=...`), reports `Opened X in your browser. I can't verify playback without the browser extension.`, state = truthful `IDLE`, never a fake `PLAYING`.

## 6. New User Workflows

- `watch psf/requests for new releases` → confirm → poller notifies on new release (Telegram, no prompt).
- `research the papers of yann lecun 2026` → brief saved → later `research brief on ...` → `continue research on ...`.
- `summarize the project psf/requests` (GitHub) / `summarize the project requests` (PyPI).
- `play the live soundtrack trailer` with no connector → real video opened + honest caveat.

## 7. Before / After per Workflow

| Workflow | Before | After |
|---|---|---|
| "watch X for new releases" | nothing (no such owner) | registered target + out-of-band push on change |
| "research <topic>" | one-shot answer, forgotten | persisted brief, recallable & continuable ("no new sources" diff) |
| "summarize the project owner/repo" | nothing | GitHub meta + releases + open issues |
| media probe in retrieval | dead code, never a candidate | real search candidates, graceful None |
| "play X" without connector | opened a *search page*, claimed `Playing X.` | opened the *actual video*, honestly says playback unverified |

## 8. Capability Composition

- Watcher + Research + Project reuse `utilities._http_get_bytes/_parse_feed_items/_feed_url_for_target` (single feed seam → the "what's new" answer and the watcher can never disagree about a target's feed).
- Research reuses `RetrievalRouter.retrieve_evidence` (existing multi-provider intelligence) — no new search stack.
- Delivery reuses the one real outbound channel: Telegram Bot API.
- Media fallback reuses `browser_operator.open_url` (connector → BrowserRuntime → default browser priority).

## 9. Actions KIO Can Now Execute

Add/remove/list watches; poll a live feed on a timer; push a Telegram message; persist and recall research briefs; diff briefs against a new gather; fetch and summarize GitHub repos and PyPI packages; resolve a YouTube query to a real video ID; open it; report media state truthfully.

## 10. Proactive Improvements

`_start_watch_poller` daemon thread in `run_runtime` (only when `TELEGRAM_TOKEN` set); failed ticks logged+skipped (a watcher tolerates a skipped tick); baseline-at-add means existing releases never spam; only real change notifies.

## 11. Research Improvements

`research_answer` + `_compose_findings` (deterministic composer, URL-dedup, per-source provenance labels) + `_render_brief` + persistence keyed by `session_id + topic_key` + continue-diff. Proven live across Exa + Tavily + OpenAlex in a single brief.

## 12. Media Improvements

- `_try_media_providers` (retrieval_router.py:437) fixed to the real contract.
- `youtube_provider`: `_browser_fallback` extracted; both `conn is None` and `conn not connected (+ disabled)` route to it; configured-but-unavailable connector stays an honest error.
- `media_manager` gate3 now surfaces any truthful provider outcome with a session (incl. the IDLE fallback), consistent with the platform path.

## 13. Communication Improvements

Truthful delivery across the board: no fabricated `Playing X.`, no `I couldn't find` when the real cause is "GitHub unreachable/rate-limited" (distinguished), Telegram push confirmed via `"ok":true`.

## 14. Developer Improvements

`summarize the project owner/repo` gives description, language, stars, latest releases, and PR-excluded open issues — keyless.

## 15. Multimodal Improvements

None added this batch (unchanged scope; not a gap for these workflows).

## 16. OpenCode-MCP Improvements

None added this batch.

## 17. KIO-Runtime Improvements

`run_runtime` starts the watch poller thread; `_exec_utility` passes the routing `decision` (session/channel/user_id) through to `utility_answer` so delivery knows the chat; `runtime_watch_poller_start` trace emitted.

## 18. Real Runtime Validation

`tests/validate_new_capabilities.py` drives KIO's single routing authority `Pipeline.run(text, session_id, channel, user_id)` against live network + real DB (Telegram-like session `tg_777`, browser opens intercepted):

- `summarize the project psf/requests` → real GitHub meta (54,244 stars), releases v2.34.2/v2.34.1, 3 open issues.
- `summarize the project requests` → PyPI, 2.34.2.
- `watch psf/requests for new releases` → registered; `what am I watching` → listed; `poll_watches()` → `{checked: 1, notified: 0}` (baseline, correct no-spam); `stop watching` → removed.
- `watch requests` (bare, PyPI) → registered/listed/stopped live.
- `research the papers of yann lecun 2026` → live 3-source brief (Exa + Tavily + OpenAlex); brief recall; continue → "No new sources"; `what did I research` → topic listed.
- `play the live soundtrack trailer` (connector disabled) → resolved real `https://www.youtube.com/watch?v=BRyMlVQkqUk`, opened, honest unverified-playback message.

## 19. Real Workflows Completed

All six validation workflows above completed end-to-end through `Pipeline.run` with live data.

## 20. Failures Discovered During Validation

1. **Media fallback unreachable:** `conn is None` branch still returned `"Browser Connector not available"` — the honest fallback only covered `conn not connected`. (My earlier edit missed the `conn is None` branch.)
2. **MediaManager gate3 swallowed the honest fallback:** it required `state == PLAYING` before returning a result, discarding the truthful IDLE fallback into `"I couldn't start X."`
3. **`"watch it"` / `"watch this"` / `"watch that"` hijacked** by the watcher owner — broke media offer-acceptance (regression in `gate5/test_behavioral_compatibility` + `test_regression_efg_routing`).
4. **GitHub error conflation:** 404 and rate-limit/unreachable both said `"I couldn't find the GitHub project ..."`.
5. **Bad validation repo:** `openai/openai` does not exist (404 is *correct* behavior — not a bug; switched to `psf/requests`).

## 21. Systemic Fixes

- Extracted `_browser_fallback(query)`; both no-connector branches route through it; configured-but-unavailable stays an honest error (RC preserved).
- gate3 accepts any truthful provider result carrying a session (consistent with the existing platform path at media_manager.py:947).
- `_WATCH_STOP` extended with pronouns/modals (`it/this/that/them/those/they/now/again/later/here/there`) so watch routing never steals media offer-acceptance.
- GitHub 404 vs unreachable now distinguished by error `status`.

## 22. Focused Tests

`tests/test_new_capability_deltas.py` — 17 tests, all passing (~0.6s):
- watch: routing (incl. the new "watch it" guards), add-baseline, remove, list, poll notify-on-change, no-spam baseline, no-token push.
- research: route, persist/recall/continue-diff, topic list.
- project: GitHub (with issues PR-filter), PyPI, missing-repo.
- media: probe new contract, probe graceful None, honest fallback (no connector → real video, IDLE, caveat), configured-connector-missing honest error.

Plus 409 regression tests across the touched seams (media recovery, truthfulness, EFG routing, live FX/package/feed, gate5 compatibility, r11 search, connector reconnect, context quality, desktop state, continuity resolver) — all green. One pre-existing failure is unrelated and reproduced on the clean baseline: `test_fix_v3_conversations.py::test_media_knowledge_router_anime` (live Jikan/MyAnimeList API).

## 23. Remaining Gaps

- Verified playback still requires the Browser Connector extension (fundamental — KIO cannot verify playback without it; the fallback is honest, not verified).
- Telegram push is one-way; delivery reliability is best-effort (ponytail: no backoff — add when delivery reliability matters).
- GitHub unauthenticated rate limit (60 req/hr) bounds project summaries.
- Watch poll cadence is fixed at 60s (ponytail: per-watch intervals when throughput matters).
- `duckduckgo_search` package emits a rename warning (`ddgs`) — pre-existing, harmless.

## 24. Exact Files Changed (this batch)

| File | Change |
|---|---|
| `mini_kio/backend/models.py` | + `WatchModel`, `BriefModel` (watches, briefs tables) |
| `mini_kio/backend/repositories/watch_repository.py` | NEW — add/deactivate/list/active/update_last_seen |
| `mini_kio/backend/repositories/brief_repository.py` | NEW — upsert/get/list_topics |
| `mini_kio/monitoring/watches.py` | NEW — watch owner: send_telegram_message, watch_answer, poll_watches, POLL_INTERVAL_S=60, `_WATCH_STOP` pronoun guards |
| `mini_kio/research/briefs.py` | NEW — research owner: research_answer, compose/render/persist/continue |
| `mini_kio/core/utilities.py` | + `_extract_project_target`, `looks_like_project_summary`, `project_answer`; `_feed_url_for_target` refactor; `utility_answer(action, query, ctx, decision)` extended; GitHub 404-vs-unreachable |
| `mini_kio/core/pipeline/__init__.py` | + project/watch/research hooks in `_detect_utility`; `_exec_utility` passes `decision` |
| `mini_kio/core/runtime.py` | + `_start_watch_poller` (daemon, token-gated) in `run_runtime` |
| `mini_kio/intelligence/retrieval_router.py` | `_try_media_providers` fixed to real `search()` contract |
| `mini_kio/media/providers/youtube_provider.py` | + `_browser_fallback`, `_resolve_search_to_watch_url`; `play()` rewired (conn-None + disabled paths); honest IDLE + caveat |
| `mini_kio/media/media_manager.py` | gate3 surfaces truthful non-PLAYING outcomes |
| `tests/test_new_capability_deltas.py` | 17 focused tests |
| `tests/validate_new_capabilities.py` | NEW — live runtime validation driver |

## 25. Git Status

Working tree on `main` contains this batch plus prior uncommitted batches (this repo keeps deliverables uncommitted until review). New batch files are untracked; edited batch files show as modified. GitNexus MCP tools were not available in this session, so `impact`/`detect_changes` were not run; equivalent impact analysis was done by tracing each edited seam and running the 409-test regression set across the touched modules.

## 26. What KIO Can Now Actually Do

- **Watch a project's releases and get pushed a Telegram message when a new one drops — with zero prompting.** Register, list, stop; baseline-at-add so it never spams; background poller.
- **Run a real research thread:** gather a multi-source brief, save it per-chat, recall it, and continue it to see *only what's new since last time*.
- **Summarize any GitHub project** (description, language, stars, latest releases, open issues) or **any PyPI package**, keyless, deterministic.
- **Play media honestly:** with the connector it plays for real; without it, it opens the *actual video* and says plainly it can't verify playback — it never again claims to be playing something it isn't.