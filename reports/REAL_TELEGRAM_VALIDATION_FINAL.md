# REAL TELEGRAM VALIDATION — FINAL (2026-08-12)

REAL RUNTIME VALIDATION > PYTEST VOLUME.

Baseline commit: `1934c87`. Final commit: see git log after this cycle.

## Runtime under test

| Item | Value |
|---|---|
| Bot PID | 10996 (venv shim) + 29984 (base interpreter worker) |
| Launcher | Normal `kio_bot.py` path via `.venv` (same as `launch_kio.vbs`) |
| Startup → Telegram ready | ~3 s (preflight DNS → getMe → deleteWebhook → Application started) |
| Browser connector | Chrome extension WS connected (`ws_server=True`, auth SUCCESS, port 9877) |
| Runtime state | `running`, safety_state `NORMAL`, health 80, MCP ready |
| Telegram transport | Real getUpdates polling, real sendMessage (HTTP 200 observed) |

## Validation types

- **REAL TELEGRAM** — message sent through the live bot; reply captured via Telethon (`live_msg.py`), latency end-to-end.
- **REAL OS** — Windows state observed after the action (`tasklist`, `EnumWindows`, `WM_GETTEXT`, `GetForegroundWindow`).
- **SIMULATION** — isolated in-process runtime with synthetic state; never live.
- **TARGETED TEST** — pytest on the changed surface.

---

## System / routing (REAL TELEGRAM)

| # | Input | Reply (abbrev.) | Latency | Result |
|---|-------|------------------|---------|--------|
| 1 | KIO status | "KIO is working. Uptime: under a minute" | 1.7 s | PASS |
| 2 | KIO health | "KIO's healthy and running normally." | 3.2 s | PASS |
| 3 | battery status | "Battery is at 60% and the system is running on battery." | 3.5 s | PASS |
| 4 | system status | CPU 23% / RAM 63% / C: 84% / battery 60% | 3.3 s | PASS |
| 5 | kio uptime | "KIO has been running for 1 minute." | 1.8 s | PASS |
| 6 | how long has the computer been running | "4 days, 17 h 57 m, started Aug 07 5:17 PM … Fast Startup … can't confirm physical shutdown" | 3.3 s | PASS (authoritative + honest caveat) |

## Inventory / LLM-bypass (REAL TELEGRAM)

| # | Input | Reply (abbrev.) | Latency | Result |
|---|-------|------------------|---------|--------|
| 7 | which programs are installed | 46+ real Windows app names | 1.7 s | PASS (real OS inventory) |
| 8 | what apps are open | Chrome tabs + Terminal + Explorer + Settings | 1.8 s | PASS (real desktop state) |
| 9 | what's running on my computer | **was a 9.9 s "WhatsRunning" Android-app hallucination** → after fix: real desktop state | 1.9 s | **FIXED** (was LLM bypass) |

## Native application lifecycle (REAL TELEGRAM + REAL OS)

| # | Input | Reply | OS observed | Result |
|---|-------|-------|-------------|--------|
| 10 | open notepad | "Opened notepad" | Notepad.exe running | PASS |
| 11 | open calculator | "Opened calculator" | CalculatorApp.exe running | PASS |
| 12 | close notepad | "Closed notepad." | Notepad.exe gone | PASS |
| 13 | close calculator | "Closed calculator." | CalculatorApp.exe gone | PASS |

## Browser / instance semantics (REAL TELEGRAM + REAL OS)

| # | Input | Reply | Observed browser state | Latency | Result |
|---|-------|-------|------------------------|---------|--------|
| 14 | open chatgpt | "Opened ChatGPT in Chrome." | ChatGPT tab present | — | PASS |
| 15 | open a new chatgpt tab | "Opened ChatGPT in Chrome." | tab list: `ChatGPT (2 tabs)` — NEW tab created | 19.2 s | PASS (instance=NEW_TAB) |
| 16 | open github in a new window | before fix: "Opened Github: in a new Chrome window." (colon artifact) → after fix: "Opened GitHub in a new Chrome window." | separate GitHub window (EnumWindows count 1→2) | 3.2 s | **FIXED** (window-verified) |
| 17 | open google in edge | "Opened Google in Edge." | Edge binary launched | 17.6 s | PASS (explicit browser) |
| 18 | open youtube in comet | before fix: no reply 60 s + Chrome-tab side effect → after fix: "Opened YouTube in Comet." | comet.exe running; no Chrome tab | 1.9 s | **FIXED** (modality gate) |

## CUA / desktop actions (REAL TELEGRAM + REAL OS)

| # | Input | Reply | OS observed | Latency | Result |
|---|-------|-------|-------------|---------|--------|
| 19 | open notepad | "Opened notepad" | running | 3.3 s | PASS |
| 20 | type kio live typing test 2026 into notepad | "Typed it into a new Notepad." | WM_GETTEXT read: `kio live typing test 2026` | 5.0 s | PASS (text verified) |
| 21 | press enter | "Pressed ENTER." | text now `kio live typing test 2026\r\n` | 1.7 s | PASS (key verified) |
| 22 | focus notepad | "Focused Notepad." | GetForegroundWindow = Notepad | 1.7 s | PASS (focus verified) |
| 23 | close it | "Closed notepad." | Notepad.exe gone | 3.3 s | PASS (contextual referent) |

## Media (REAL TELEGRAM)

| # | Input | Reply | Latency | Result |
|---|-------|-------|---------|--------|
| 24 | pause | "Paused." | 4.9 s | PASS (ack; no playable media to observe — provider-limited) |
| 25 | next | "Next track not supported for browser media" | 1.7 s | PASS (truthful provider limitation) |

## Companion intelligence (REAL TELEGRAM)

| # | Input | Reply (abbrev.) | Latency | Result |
|---|-------|------------------|---------|--------|
| 26 | what are you curious about | routed to conversation (curiosity family) | 3.7 s | PASS (routing) |
| 27 | do you like jazz music | reasoned opinion (persona deflection softened) | 5.5 s | PASS (routing + prompt fix) |
| 28 | what is your take on remote work | balanced reasoned judgment | 3.3 s | PASS (independent judgment) |
| 29 | recommend a good movie for tonight | "…try *Arrival*…" | 3.3 s | PASS (recommendation) |

## Knowledge (REAL TELEGRAM)

| # | Input | Reply | Latency | Result |
|---|-------|-------|---------|--------|
| 30 | what is photosynthesis | fact-grounded natural explanation | 4.8 s | PASS |
| 31 | tell me more | continued photosynthesis (C₄/CAM…) | 1.9 s | PASS (contextual follow-up) |

## Simulations (isolated — never live)

| Simulation | Result |
|---|---|
| DEGRADED scoping: 3× browser_goto failures → DEGRADED, degraded_groups=[browser] | browser_goto + chrome tab open BLOCKED with truthful message; native open/close/folder/lock/media ALLOWED |
| Close-all target selection (synthetic desktop) | Explorer / Windows Terminal / SecurityHealthService excluded; user apps selected; KIO pid-family excluded |

## Targeted tests (pytest)

`tests/test_gap_closure_v3.py` **80 passed** (running-state family, knowledge-shape preservation, system-healthy wording, new-window strip+verification, modality gating, converse-prompt rules). Connector/governance/fix-batch suites: 72 passed, 35 subtests, 1 pre-existing failure (`test_unknown_command_returns_error`, verified failing at clean HEAD).

## Fixes made this cycle (canonical owners)

1. `mini_kio/core/pipeline/__init__.py` — running-state family (`what's running on my computer/this pc/your system`, `what/which processes are running`, `is the system healthy`) routes to deterministic desktop-state/system owners. Knowledge shapes preserved.
2. `mini_kio/core/app_operator.py` — `::newwindow` marker strip `[:-10]`→`[:-11]` (colon artifact); new-window claims require observed window-handle-count increase (`window_identity` vs truthful `window_unverified`).
3. `mini_kio/core/app_operator.py` — browser-modality gate: connector serves ONLY the default browser; explicit edge/comet/firefox/brave go to their own binary (no Chrome side effect).
4. `mini_kio/llm/llm_constants.py` — converse prompt permits reasoned preferences/curiosity as KIO, forbids "I'm an AI" deflection.

## Latency summary (real Telegram, end-to-end)

| Class | Typical | Worst |
|---|---|---|
| Deterministic local queries | 1.7–3.5 s | 5.0 s |
| Native open/close (verified) | 1.8–5.0 s | 5.0 s |
| CUA type/key | 1.7–5.0 s | 5.0 s |
| Browser new-tab (connector + verify) | 19.2 s | 19.2 s |
| Browser binary launch (Edge) | 17.6 s | 17.6 s |
| New-window (launch + verify poll) | 3.2 s | 3.2 s |
| Companion / knowledge (LLM) | 3.3–5.5 s | 5.5 s |

Startup → deterministic action usable: **~3 s** (no 1-minute startup problem observed this cycle).

## Browser connector state

Connected throughout; extension registered at startup; heartbeat OK; stale-handle fast-fail present. New-tab latency (19.2 s) is tab-create + bounded tab-identity verification.

## Remaining genuine limitations

- New-window / binary-browser launches rely on the browser honoring the launch (`window_unverified` path exists for honesty).
- Media: no playable target on the machine — PAUSE acked, NEXT truthfully unsupported for browser media.
- Companion persona tone: the LLM can still hedge; prompt steers toward reasoned choices but model behavior is stochastic.
- `test_unknown_command_returns_error` (gate3) is a pre-existing failure at clean HEAD, unrelated to this cycle.
