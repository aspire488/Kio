# KIO Capability-Space Expansion — 2026 Report

Date: 2026-08-16. Method: read canonical KIO docs first, mapped the real
implementation (utility seam, retrieval seam, MCP runtime), ran parallel
OpenCode research agents over the MCP ecosystem, free public-API landscape,
and free/local AI landscape, then re-verified live endpoints over HTTP.
Implemented only results that plug into existing seams, one owner per
capability, zero new keys. All capabilities validated by real invocation.

---

## 1. Capability families investigated

- Data / finance (FX rates, crypto, commodities)
- Developer ecosystem (package status, releases, changelogs, code search)
- Monitoring / proactivity (release feeds, news feeds, change detection, notifications)
- Research / data (open scholarly APIs, citation graphs)
- Communication / productivity (messaging, calendar, notes)
- Multimodal (local vision/ASR/TTS, document parsing)
- MCP server ecosystem (what servers exist that KIO's `MCPRuntime` could host)
- Local AI (Ollama models, HF pipelines, embedded models)

## 2. New capability classes added

Four new utility/retrieval classes, all keyless, all routed through existing seams:

1. **Live FX conversion** — `utilities.py: _live_fx_rates()` via Frankfurter
   (`https://api.frankfurter.app/latest?base=USD`), live branch inside the
   existing `convert_answer` currency path; static `_CURRENCY_RATES` table kept
   as honest fallback. Output labels distinguish "(live rate)" vs
   "about/approximate".
2. **Package status** — `utilities.py: package_answer` (PyPI JSON latest
   version + release date, `importlib.metadata` comparison for "is X outdated"),
   with `_extract_package_name` and the `looks_like_package` routing hook.
3. **Feed / release watch** — `utilities.py: feed_answer` (stdlib
   `xml.etree.ElementTree`, Atom + RSS 2.0), `_extract_feed_target`,
   `looks_like_feed` hook. Slash target → `github.com/<o>/<r>/releases.atom`;
   bare name → `pypi.org/rss/project/<pkg>/releases.xml`.
4. **OpenAlex research probe** — `retrieval_router.py: _try_openalex`
   (works API, `default.search` filter) + `_reconstruct_abstract` (inverted
   index → full abstract), wired into the `retrieve_evidence` probe chain after
   Wikipedia, before DuckDuckGo.

## 3. Ecosystems explored

- **MCP ecosystem** — catalogued viable servers (see `MCP_SERVER_ECOSYSTEM_2026.md`):
  filesystem, git, memory, time, sequential-thinking, context7, github (remote,
  GITHUB_PAT), chrome-devtools, playwright, firecrawl, dbhub, serena — all
  already configured in the OpenCode workspace.
- **Free API ecosystem** — Frankfurter (FX, keyless), PyPI JSON/RSS, GitHub
  releases.atom/commits.atom + api.github.com, hn.algolia.com/hnrss.org,
  OpenAlex, Wikipedia, Open-Meteo. All verified live HTTP 200.
- **Monitoring ecosystem** — feedparser 6.0.14 (pure Python, installs clean on
  3.14), ntfy.sh (curl POST, no account), Apprise (30+ services), Windows Task
  Scheduler / schtasks + toast notifications, stdlib polling loop vs APScheduler.
- **Local AI ecosystem** — Ollama + HF provider paths already in KIO's
  `provider_registry`; no new local models introduced this session.

## 4. APIs investigated and verified

| API | Endpoint | Key | Verified |
|---|---|---|---|
| Frankfurter | `api.frankfurter.app/latest?base=USD` | no | 200, EUR 0.86453 etc. |
| Frankfurter (dev host) | `api.frankfurter.dev` | no | 403 without UA, 200 with UA |
| PyPI JSON | `pypi.org/pypi/<pkg>/json` | no | 200 |
| PyPI RSS | `pypi.org/rss/project/<pkg>/releases.xml` | no | 200 (fastapi → 0.141.1) |
| GitHub releases.atom | `github.com/<o>/<r>/releases.atom` | no | 200 (kurtmckee/feedparser → v6.0.14) |
| GitHub API | `api.github.com/repos/<o>/<r>/releases/latest` | no | 200; ~60 req/hr anonymous cap |
| Hacker News | `hnrss.org` / `hn.algolia.com` | no | 200 |
| OpenAlex | `api.openalex.org/works` | no | 200 |
| exchangerate.host | — | yes | rejected (needs key) |

## 5. MCPs

- KIO's own `MCPRuntime` (stdio JSON-RPC client, health monitor, crash
  isolation) is built but **gated off** (`MCP_RUNTIME_ENABLED` absent from
  `.env`).
- `mcp-server-fetch` unusable due to ecosystem PyPI drift (`McpError` →
  `MCPError`) — not a KIO bug; documented as blocked.
- **GitNexus MCP now wired into OpenCode** — see §10.

## 6. Local implementations preferred

- Feed parsing: stdlib `xml.etree.ElementTree` — no feedparser dependency
  (skipped; add when Atom namespace handling or malformed-feed tolerance grows).
- HTTP: `urllib.request` (`_http_get_bytes` / `_http_get_json`) — no `requests`
  dependency in utilities.
- Dates: `email.utils.parsedate_to_datetime` — no `dateutil`.

## 7. Highest-value candidates selected

All keyless, all single-owner, all with a working seam:

1. Live FX rates (finance, immediate user value, clean fallback story).
2. Package status ("what's the latest X" / "is X outdated") — natural dev-ops
   queries that previously fell through to generic retrieval.
3. Feed/release watching ("latest releases of o/r", "what's new in X") — feeds
   the proactive/monitoring roadmap with zero infra.
4. OpenAlex scholarly probe — closes the research gap in the retrieval chain.

## 8. Rejected candidates and why

- **exchangerate.host / fixer.io / currencyapi / Twelve Data** — need API keys.
- **crypto (CoinGecko/CoinCap)** — nice, but a third data family adds routing
  surface for little marginal value; defer.
- **full feedparser dependency** — stdlib XML parser covers Atom+RSS we verified;
  add the lib when real-world feeds break the parser.
- **ntfy.sh/Apprise push notifications** — real user value, but delivery is a
  separate subsystem; the feed reader is the retrieval half, delivery deferred.
- **APScheduler** — stdlib polling loop suffices for watch-on-query; scheduler
  only if standing background jobs are requested.
- **mcp-server-fetch** — ecosystem-broken, not our bug.

## 9. Capabilities implemented (this session)

| Capability | File / owner | Live proof |
|---|---|---|
| Live FX conversion | `utilities.py` `_live_fx_rates` + `convert_answer` | 100 USD → €86.45; 50 EUR → ¥9196.33 |
| Package status | `utilities.py` `package_answer` | "latest requests" → 2.34.2 (2026-05-14); "is requests outdated" → current=true |
| Feed/release watch | `utilities.py` `feed_answer` | "what is new in fastapi" → 0.141.1; "latest releases of kurtmckee/feedparser" → v6.0.14 |
| OpenAlex probe | `retrieval_router.py` `_try_openalex` | abstract reconstruction + evidence entry + `openalex_hits` stats |

Routing: package/feed hooks added in `_detect_utility`
(`pipeline/__init__.py`, after weather, before convert). End-to-end routing
verified via `_IntentClassifier` — package/feed queries land on
`(utility, package)` / `(utility, feed)`; weather/convert/calculate/time intact.

## 10. OpenCode MCP changes

- **Added GitNexus MCP** to the project `opencode.json`:
  `node .gitnexus/run.cjs mcp` (stdio). This is the MCP backend for the
  AGENTS.md-mandated `impact` (pre-edit blast radius) and `detect_changes`
  (pre-commit scope check) workflows, which were previously only reachable by
  hand-tracing.
- **Validated**: spawned the server, completed the MCP `initialize` handshake,
  and `tools/list` returned 17 tools including `impact`, `detect_changes`,
  `context`, `trace`, `query`, `rename`, `explain`, `route_map`, `shape_check`.
  Tools become available to the agent on the next OpenCode session start.
- GitNexus index confirmed up-to-date (`status`: Indexed commit == current
  commit 23da4ba).

## 11. KIO MCP / provider changes

- None required. All new capabilities use in-process utility/retrieval owners;
  `MCPRuntime` remains gated off — hosting the new capabilities as MCP servers
  is a possible future shape, not a present requirement.

## 12. Credential configuration

- No new keys. `.env` untouched. All four capabilities run anonymous.
- Existing key names (for reference, never values): EXA_API_KEY, TAVILY_API_KEY,
  OMDB_API_KEY, SPORTSDB_API_KEY, SPOTIFY_*, TELEGRAM_*, YOUTUBE_API_KEY,
  HF_TOKEN, JINA_READER_ENABLED, OLLAMA_*.

## 13. Capability composition

- `convert_answer` → `_live_fx_rates()` → Frankfurter, falls back to static
  table; live branch labelled "(live rate)".
- `package_answer` → PyPI JSON + local `importlib.metadata`; composes into a
  single "latest / installed / outdated?" answer.
- `feed_answer` → `_parse_feed_items` → per-item (title, link, date, summary)
  → composed top-N "latest releases" answer.
- `retrieve_evidence` → ... → `_try_openalex` → `_reconstruct_abstract` →
  evidence dict → `retrieve` chain; result carries `openalex_hits` stat.

## 14. Proactive / monitoring

- Delivery half explored (ntfy.sh curl, Apprise, Windows Task Scheduler +
  schtasks/toast) but **not built** — deliberately deferred (see §8).
- Retrieval half is live: feed/release queries now resolve and compose real
  current data, so a scheduled watcher has a ready-made reader.
- Monitoring library findings: none of feedparser / apprise / apscheduler are
  installed; feedparser 6.0.14 installs clean on Python 3.14 when needed.

## 15. Multimodal

- Surveyed only this session. KIO already has a media intelligence layer
  (`media/intelligence/*`) and provider paths for local vision/ASR/TTS via
  Ollama/HF. No new multimodal capability added — the survey found no keyless
  gap that the existing providers don't already cover.

## 16. Research / data

- **OpenAlex probe implemented and validated** (works API, `default.search`,
  per-page=1, relevance sort). `_reconstruct_abstract` rebuilds abstracts from
  the inverted-index field, so results carry actual abstract text, not just
  metadata — directly comparable to the Wikipedia probe's output quality.

## 17. Communication / productivity

- Surveyed (messaging, notification rails). Telegram rails already exist in the
  repo (validated in earlier sessions per `reports/REAL_TELEGRAM_VALIDATION_FINAL.md`).
  No new communication capability needed this session; push notification of
  feed changes is the natural next step (§8, §14).

## 18. Developer ecosystem

- Package status + release feeds implemented (§9), covering the two highest
  recurring dev queries with one owner each.
- GitNexus MCP wired into OpenCode (§10), closing the AGENTS.md mandate gap.

## 19. Runtime validation

- Frankfurter / PyPI / GitHub / hnrss / OpenAlex endpoints all verified live
  over HTTP (200s) before implementation.
- Live invocation of all four capabilities with real network (see §9 values);
  an empty-releases edge case (`openai/openai` → 404, no releases) produced the
  honest fallback message as designed.
- Console mojibake for €/— is the Windows console codepage only; ASCII dump
  confirmed the payloads carry correct Unicode.

## 20. Test results

`pytest -q` on the four focused suites: **59 passed in 0.41s**.

- `tests/test_utilities_live_fx_package_feed.py` (16) — FX live/cross/fallback,
  package latest/outdated/unreachable/hooks, feed github/pypi/unreachable/
  bad-xml/hooks. Stub seam: `mini_kio.core.utilities._http_get_bytes`.
- `tests/test_retrieval_openalex.py` (4) — abstract reconstruction, result
  shape, evidence-chain integration, `openalex_hits` stat. Stub seam:
  `retrieval_router.requests.get`.
- `tests/test_utilities_live_weather.py` (prior) + `tests/test_deterministic_calculator.py`
  (regression) — unchanged, still green.

`conftest.py` sets `KIO_TEST_MODE=1` + operational monkeypatches only; tests
stub the HTTP seam directly, no network in tests.

## 21. Remaining gaps

- **Feed name ambiguity**: a bare feed name resolves to PyPI only; a bare
  GitHub repo can't be watched without a name→repo lookup. Marked with a
  `ponytail:` comment; upgrade path = GitHub repo-search name resolution.
- **Push notifications** for watched releases (ntfy/Apprise) — deferred.
- **Background scheduling** of watches (stdlib loop suffices for now) — deferred.
- **Crypto/commodities** data family — deferred.
- **GitNexus MCP tools** usable in-session only after OpenCode restart.
- `mcp-server-fetch` unusable (ecosystem drift) — blocked until upstream fixes.

## 22. Files changed (this session)

- `mini_kio/core/utilities.py` (untracked) — `_http_get_bytes`, `_http_get_json`,
  `_date_only`, `_live_fx_rates`, `_feed_rss_date`, `_parse_feed_items`,
  `_PACKAGE_STOP`, `_extract_package_name`, `looks_like_package`,
  `package_answer`, `_extract_feed_target`, `looks_like_feed`, `feed_answer`;
  modified `convert_answer` (live branch) + `utility_answer` (dispatch);
  docstring updated.
- `mini_kio/core/pipeline/__init__.py` — package/feed routing in `_detect_utility`.
- `mini_kio/intelligence/retrieval_router.py` — `_reconstruct_abstract`,
  `_try_openalex`, `openalex_hits`, probe tuple + `retrieve` chain.
- `opencode.json` — GitNexus MCP server entry.
- `tests/test_utilities_live_fx_package_feed.py`, `tests/test_retrieval_openalex.py`
  — new. (Plus earlier session files: `tests/test_utilities_live_weather.py`,
  `MCP_SERVER_ECOSYSTEM_2026.md`, this report.)
- This report replaces the prior 20-section draft.

## 23. Git status

Repo has extensive **pre-existing** drift (35+ modified files, dozens of
untracked `_probe*`/`_s*` scratch files and report `.md`s) that predates this
session and is untouched by it. Files this session changed are listed in §22.
No commits made (per standing instruction: commit only on explicit request).
`git status` at completion shows `mini_kio/core/utilities.py`,
`tests/test_utilities_live_fx_package_feed.py`, `tests/test_retrieval_openalex.py`,
`tests/test_utilities_live_weather.py`, `MCP_SERVER_ECOSYSTEM_2026.md`,
`CAPABILITY_EXPANSION_REPORT.md` untracked; `mini_kio/core/pipeline/__init__.py`,
`mini_kio/intelligence/retrieval_router.py`, `opencode.json` modified.