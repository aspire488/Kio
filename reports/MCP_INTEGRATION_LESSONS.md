# MCP Integration Lessons — KIO FINAL

**Date:** 2026-09-04
**Baseline under analysis:** `21aad60` ("chore: finalize KIO integration handoff") — the MCP/external-integration experiment, preserved at `KIO-21AAD60-MCP-HANDOFF-BACKUP`.
**Stable baseline restored:** `f46e21c` ("chore: consolidate full KIO system restoration").
**Evidence sources:** the `f46e21c..21aad60` diff (7,652 insertions; 3,923 non-test / 3,729 test), code comments inside that diff, test-suite docstrings added at `21aad60`, commit messages, `docs/` authority documents, and live-runtime observations from the 2026-09-04 Telegram E2E session.

Every lesson below is written as **lesson → evidence → resulting rule → future implementation consequence**. Inferences are explicitly marked `[inference]`; nothing else is speculation.

---

## 1. What worked

| Lesson | Evidence | Resulting rule | Future consequence |
|---|---|---|---|
| **Adapter + provider layering is a sound shape.** New integrations were expressed as a thin `Adapter` (top-level `adapters/*_adapter.py`) plus an `ExecutionProvider` wrapper (`mini_kio/core/providers/*_provider.py`) under the existing `provider_contract`. Docstrings explicitly say the adapter "does NOT duplicate" the external library and "Does NOT replace the existing" native provider. | `adapters/browser_use_adapter.py`, `adapters/cua_adapter.py`, `adapters/openhands_adapter.py`, `adapters/pipecat_adapter.py`; `mini_kio/core/providers/*_provider.py` (all added at `21aad60`). | Future integrations must use the same two-layer shape: adapter (external-facing) + ExecutionProvider wrapper (KIO-facing), never direct runtime imports of external SDKs. | Any new integration reuses this proven skeleton instead of inventing a new manager. |
| **Availability detection + lazy import kept optional libraries from crashing KIO.** Every adapter probes `import` in `__init__`, records `_last_error`, sets `_available = False`, and lazy-imports heavy SDKs. | `try: import browser_use ... except ImportError as e: self._last_error = ...; logger.warning(...)` pattern in all four adapters at `21aad60`. | Import-time failure of an optional dependency must degrade to UNAVAILABLE, never raise into runtime startup. | This becomes the mandated UNAVAILABLE state path in the integration contract. |
| **The integration was test-heavy and its tests encode the real failure catalog.** 3,729 test LOC added (48% of the handoff). Test docstrings enumerate lifecycle, stabilization, false-positive guards, and no-secret rules. | `tests/test_mcp_lifecycle.py` (947 LOC), `test_mcp_stabilization.py` (652), `test_mcp_pipeline.py` (707) docstrings at `21aad60`. | Every failure class fixed in the MCP phase gets a permanent regression test. | The failure catalog below is directly reusable as a test checklist for future integrations. |
| **Conversational false-positive guards were recognized as essential.** Tests explicitly assert "Ordinary conversational Google questions do NOT become MCP calls." | `tests/test_mcp_pipeline.py` items 11–15 (docstring): unsupported capability, executor unavailable, auth failure, malformed args, conversational guard, "No secrets appear in logs/output." | NL→external-tool classification must prove it never fires on ordinary conversation. | Discovery-by-intent must sit behind deterministic routing, not replace it. |

## 2. What failed initially

| Lesson | Evidence | Resulting rule | Future consequence |
|---|---|---|---|
| **MCP subprocesses died shortly after connect and were misread as crashes, triggering reconnect storms.** `executor.cmd mcp` detects an already-running Executor daemon and exits ~0.7 s after MCP init. | Runtime code comment at `21aad60` in `mini_kio/core/runtime.py` (`_kill_executor_daemon`): "the Executor daemon ... exits within 0.7s after MCP initialization, crashing the KIO MCP runtime connection." | Never treat a child exiting for environmental reasons as a generic crash; distinguish clean exit, port conflict, and crash; no unbounded reconnect. | Lifecycle state machine must include terminal states (STOPPED/FAILED) plus bounded reconnect with backoff. |
| **Connecting MCP during bootstrap corrupted the event loop.** `safe_run_async(asyncio.run())` created a temporary loop; when it closed, the transport pump task was cancelled, falsely marking the server crashed. | Runtime code comment at `21aad60`: "Connecting during bootstrap via safe_run_async(asyncio.run()) creates a temporary event loop; when it closes the transport pump task is cancelled, which falsely marks the server as crashed." | MCP transport tasks must live on the long-lived main event loop (deferred connect from Telegram `post_init`), never on a per-call loop. | Startup wiring must be reviewed for `asyncio.run` misuse before any async subprocess integration. |
| **Concurrent connects and reconnects raced.** Multiple code paths could connect the same server or reconnect concurrently. | Fixes added at `21aad60` in `mini_kio/runtime/mcp_runtime/runtime.py`: `_reconnect_locks` (per-server `asyncio.Lock`), connect lock, `_MIN_RECONNECT_INTERVAL_S = 5.0`, `_last_reconnect` throttle. | All connect/reconnect paths must be serialized per server. | The lifecycle contract must name a single owner for each server connection. |
| **Process/scope leaked into killing user processes.** The fix force-killed Executor daemons (ports 4789/4788) via `taskkill` from inside KIO startup, reading a state file at `~/.executor/daemon-localhost-4789.json`. | `_kill_executor_daemon()` implementation at `21aad60` in `mini_kio/core/runtime.py`. | KIO runtime must never kill processes it did not spawn; daemon/port conflicts are configuration errors to report, not processes to terminate. | Process-kill logic is a hard review flag in every future integration diff. |
| **Integration process leaked: cleanup was incomplete.** In the 2026-09-04 live session, shutting down the bot left an orphaned `executor.exe` MCP child; it had to be killed manually. | Live observation (bot log + `tasklist` after SIGTERM), 2026-09-04 Telegram E2E session. | Child-process teardown must be proven (parent death → child death), not assumed. | Real-runtime shutdown validation is a mandatory gate for any subprocess-based integration. |

## 3. Why it failed

| Lesson | Evidence | Resulting rule | Future consequence |
|---|---|---|---|
| **The failure mode was lifecycle, not protocol.** JSON-RPC/MCP message handling was never the problem; process lifetime, event-loop ownership, reconnect policy, and teardown were. | The entire `21aad60` stabilization delta is lifecycle code: `mcp_runtime/runtime.py` (+241), `server.py` (+315), `transport.py` (+108) — reconnect bounds, locks, terminal states, stale-callback protection, duplicate-connection prevention. | Budget lifecycle work first: availability, connection ownership, reconnect policy, teardown. | Every integration plan must include a lifecycle design section before tool-mapping design. |
| **Integration was validated against mocks, not reality.** 372 targeted mock/unit tests passed at `21aad60` ("262 MCP + 99 integration + 11 infrastructure"), yet live runtime surfaced daemon orphaning and false crash detection. | Commit message `21aad60`; live-session observations. | "Unit tests pass" ≠ "production path works." Mock suites cannot validate process lifetime. | Real-runtime smoke on every lifecycle path is a non-negotiable gate (see validation philosophy). |

## 4. What architectural assumptions were wrong

| Lesson | Evidence | Resulting rule | Future consequence |
|---|---|---|---|
| **Assumption: optional integrations can default ON.** `MCP_RUNTIME_ENABLED` default was flipped `"false" → "true"` at `21aad60` (`mini_kio/core/config.py`), and `mcp_servers.json` marked `executor` and `docker-gateway` as `"optional": false` — making Docker and a remote executor REQUIRED startup dependencies. | `config.py` delta and `mcp_servers.json` at `21aad60`. | Optional integrations must never become startup dependencies; defaults stay OFF until a founder/architecture decision. | The contract's availability states (UNAVAILABLE/CONNECTING/READY/DEGRADED/FAILED) apply at startup, and startup must succeed in every state except total failure of core. |
| **Assumption: one squashed handoff commit is a safe way to land an integration stack.** The entire MCP layer (~3,923 non-test LOC across 33 files) landed as a single commit on top of the stable baseline, so regressions could not be bisected and the tree could only be "restored," not "reverted." | Reflog: `f46e21c → 21aad60` is a single commit; the restoration itself required a branch reset + backup ref. | Integration work lands in small, independently revertible slices. | Every phase below is sliced so each slice is revertible on its own. |
| **Assumption: external work belongs in a Lab repo that is then merged wholesale.** `21aad60` changed `launch_bot.py`'s `KIO_DIR` to `KIO-Integration-Lab\kio`, pointing the canonical launcher at the staging repo. | `launch_bot.py` delta at `21aad60`. | FINAL must remain self-contained; external repos are reference material only; nothing in FINAL may point at a staging repo. | Section 0 of the plan: "no Lab copy-in, no Lab pointer." |
| **Assumption: the baseline register described reality.** `docs/external_dependency_authority_register.md` lists CUA/Scrapling/MarkItDown as `Wrapper — Active`, but at `f46e21c` nothing in `mini_kio/` imports `adapters.*` except `browser/facade.py` (scrapling, 3 call sites). The register overstated integration status. | Register rows vs. `git grep` at `f46e21c`. | Status is defined by wired runtime behavior, not by a register row. | Candidate evaluation must be re-derived from code, not from earlier report claims. |

## 5. Lifecycle problems

| Lesson | Evidence | Resulting rule | Future consequence |
|---|---|---|---|
| Reconnect storms (unbounded) | `_MIN_RECONNECT_INTERVAL_S = 5.0`, `_last_reconnect` throttle, `max_restart_attempts == 3` default added at `21aad60`. | Bounded attempts + minimum interval between reconnects. | Lifecycle contract: bounded retry, terminal states, backoff. |
| Reconnect of a server already in a terminal state | "terminal state checks" listed in `21aad60` commit message; `tests/test_mcp_lifecycle.py` §5. | Never reconnect from STOPPED/FAILED without explicit re-init. | State machine per server: `stopped → starting → initializing → running → stopping → stopped`, plus `failed`. |
| Duplicate connections to the same server | "duplicate connection prevention" in `21aad60` commit message. | One live connection per server id, enforced by the owning lock. | Registry asserts uniqueness before connect. |
| Stale callbacks firing after reconnect | "stale callback protection" in `21aad60` commit message. | Callbacks carry connection generation; stale generations are dropped. | Execution responses are tagged with connection epoch. |
| Child-process cleanup on shutdown | Orphaned `executor.exe` after SIGTERM (live session, 2026-09-04). | Teardown must cancel pending reconnects and terminate children; verify with a real stop. | Shutdown validation gate for every subprocess integration. |

## 6. Authentication / credential problems

| Lesson | Evidence | Resulting rule | Future consequence |
|---|---|---|---|
| **Tokens appeared in dev config that sits in the repo.** The working-tree `opencode.json` delta (pre-existing, never committed) carried an `executor` remote MCP entry with a live `Authorization: Bearer …` token; a `config.py`-adjacent server config carried `NEO4J_PASSWORD`/`OPENAI_API_KEY` envs (empty in the committed file, but present as plumbing). | `opencode.json` working diff (2026-09-04); `mcp_servers.json` at `21aad60` (graphiti env block). | Credentials live only in `.env` (gitignored) or an OS secret store; never in tracked config, JSON, or code; never in the repo working tree. | Security contract: credential source / storage boundary / injection / scope / revocation / failure behavior documented per integration before code. |
| **Auth failure paths were an afterthought — then tested.** The pipeline tests list "Authentication failure handled cleanly" as a required behavior. | `tests/test_mcp_pipeline.py` docstring item 12. | Every integration must define its auth-failure response (user-facing message, no secret leak, retry policy). | Auth-failure behavior is a first-class acceptance criterion. |
| **No-secret rules were needed in formatting.** Formatter rules: "Never expose raw JSON… Never expose internal IDs, etags…", and tests assert no secrets in logs/output. | `mini_kio/core/mcp_result_formatter.py` module docstring at `21aad60`; `tests/test_mcp_pipeline.py` item 15. | Result normalization must redact tokens/IDs by construction. | Result-formatter templates are reviewed against the secret list before merge. |

## 7. Tool-discovery problems

| Lesson | Evidence | Resulting rule | Future consequence |
|---|---|---|---|
| **Discovery-by-flood is rejected.** The `docker-gateway` server advertised "315+ MCP servers (PRIMARY integration layer)"; exposing hundreds of tools to the model is unmanageable. | `mcp_servers.json` description at `21aad60`. | Lazy/on-demand discovery: capability summary → likely capability → discover relevant tool(s) → execute → verify → normalize. Search is a capability, not the universal fallback. | The plan's DISCOVER stage never enumerates a whole server's tool list into core context. |
| **NL→tool mapping needs tight patterns + conversational guard.** `mcp_tool_mapping.py` (684 LOC) matched intent regexes to tool names; pipeline added `_classify_mcp`; tests demanded ordinary chat never maps to tools. | `mcp_tool_mapping.py`; pipeline delta at `21aad60`; `tests/test_mcp_pipeline.py`. | Intent resolution stays deterministic; external-tool dispatch is a leaf of deterministic routing, not an LLM judgement call. | Deterministic routing remains preferred when intent is already resolved. |

## 8. Process / scope problems

| Lesson | Evidence | Resulting rule | Future consequence |
|---|---|---|---|
| Scope creep inside the codebase: the "integration" rewrote canonical routing. `mini_kio/core/pipeline/__init__.py` grew +617 LOC to host MCP classification inside the deterministic router — the highest-blast-radius file in KIO. | Pipeline delta at `21aad60`. | Integration changes to core dispatch are prohibited without explicit architecture review; external dispatch must hang off a stable extension point, not be woven into `classify/resolve/exec/compose`. | Phase A (foundation hardening) must define that extension point before any integration lands. |
| Cross-repo confusion (Lab pointer). | `launch_bot.py` delta. | One canonical repo; integration material stays in reference snapshots. | See §4 above. |
| Environment scope: repo-root clutter (log files, leftover dirs) accumulated; `.pytest-media-tmp` permission warnings surfaced repeatedly. | `ls` + git status during 2026-09-04 session. | Runtime writes go to designated runtime dirs; repo root stays clean. | Housekeeping rule for generated artifacts (flag files, logs) in every phase's exit criteria. |

## 9. Validation gaps discovered

| Lesson | Evidence | Resulting rule | Future consequence |
|---|---|---|---|
| Baseline-vs-integration regression comparison was never done on one suite. `f46e21c` claimed "186+ relevant tests, 4 pre-existing failures"; the `21aad60` era showed 14 failures across the gate3 batch (124 tests). The two numbers are not the same suite, so causation is unknown — but no head-to-head run was recorded at the handoff. | Commit messages; 2026-09-04 session test run. | Every integration slice must run the SAME deterministic suite before/after on the SAME baseline and report the delta. | Validation gates below require a pinned suite + before/after counts. |
| "Installed ≠ integrated," "connected ≠ working," "tool listed ≠ tool executable." | Register vs. `git grep`; mock tests passing while live daemon orphaning occurred. | Validation ladder is mandatory: import → lifecycle → capability invocation → real runtime smoke → real E2E (where creds/env permit) → failure path → disable/unavailable. | Each phase's exit criteria enumerate which ladder rungs were climbed. |
| Unrelated failures were documented but not attributed. Discord channel start failed on `No module named 'discord'` (non-fatal by design). | Live session log, 2026-09-04. | Out-of-scope failures get a written note with the classification used (pre-existing / non-blocking / blocker), not silent passing. | Report discipline carried into every phase. |

## 10. Patterns that become MANDATORY for future integrations

1. **Two-layer shape**: thin `Adapter` + `ExecutionProvider` wrapper under the existing `provider_contract`; lazy import; availability detection; graceful UNAVAILABLE.
2. **Explicit states** per integration: `UNAVAILABLE / CONNECTING / READY / DEGRADED / FAILED`, with startup succeeding in all non-core states.
3. **Bounded lifecycle**: single connection owner, per-server connect lock, bounded reconnect + backoff, terminal state checks, stale-callback protection, proven child teardown.
4. **Deterministic discovery**: capability summary first; NL→tool only via tight patterns with conversational false-positive guards; never dump full tool lists.
5. **Result normalization contract**: human-readable output, no raw JSON, no IDs/etags/secrets, empty ≠ error, malformed ≠ crash (rules already written in `mcp_result_formatter.py` — reuse them).
6. **Security contract**: credential source / storage boundary / injection / scope / revocation / failure behavior / user-confirmation / sensitive-result handling / audit, documented before code (Section 9 of the strategy brief).
7. **Real-runtime validation ladder** (Section 15 of the strategy brief) on every lifecycle path.
8. **LOC accounting with a fixed definition including ALL touched files** (wiring, config, lifecycle, tests excluded) — no narrow "glue-only" accounting.
9. **Small revertible slices**; never a single squashed integration commit.
10. **FINAL stays self-contained**; no Lab pointers, no repo copies; external repos are A–E classified (use/wrap/copy-tiny-artifact/reference/reject) with a written reason.

## 11. Patterns that must NOT be repeated

1. No `optional: false` external servers; no default-ON integration flags (`MCP_RUNTIME_ENABLED` default must stay off).
2. No `taskkill`/process-kill of processes KIO did not spawn; no daemon state-file surgery (`~/.executor/...`).
3. No `asyncio.run` per-call loops for long-lived transports.
4. No edits to the canonical pipeline `classify/resolve/exec/compose` to host external dispatch.
5. No bearer tokens or passwords in tracked/working-tree config (`opencode.json`, `mcp_servers.json` env blocks, fixtures).
6. No Docker/Neo4j/gateway-class infrastructure as an integration prerequisite without an explicit founder decision (executor + docker-gateway + graphiti config at `21aad60` is the anti-pattern).
7. No "315+ tools available" discovery model.
8. No register rows claiming Active without wired runtime behavior.
9. No single-commit integration handoffs (~3.9k non-test LOC).
10. No `launch_bot.py`-style repointing of the canonical launcher at a staging repo.

## 12. Reusable integration contract (exact)

```
STAGE 1  DISCOVER                 — capability summary; match intent deterministically;
                                    no full-tool enumeration, no LLM-as-fallback.
STAGE 2  ADAPTER                  — adapters/<name>/ under existing Adapter contract
                                    (__adapter_id__, __version__, CAPABILITIES, class Adapter,
                                    lazy import, health()); external SDK never imported by core.
STAGE 3  CAPABILITY REGISTRATION  — ExecutionProvider wrapper in mini_kio/core/providers/
                                    registered via provider_registry; capability name collision-checked.
STAGE 4  AVAILABILITY / LIFECYCLE — states UNAVAILABLE|CONNECTING|READY|DEGRADED|FAILED;
                                    one connection owner; bounded reconnect; terminal states;
                                    teardown proven. Startup unaffected by non-core state.
STAGE 5  AUTH / CREDENTIAL BOUNDARY — .env or OS store only; source, scope, revocation,
                                    failure behavior, user confirmation, audit documented.
STAGE 6  EXECUTION                — deterministic routing → adapter invocation; timeout-bound.
STAGE 7  VERIFICATION             — result validated against expected shape before release.
STAGE 8  RESULT NORMALIZATION     — formatter rules (human text, no raw JSON, no secrets/IDs,
                                    empty≠error, malformed≠crash) — reuse mcp_result_formatter patterns.
STAGE 9  KIO RESPONSE             — normalized result enters the normal response pipeline;
                                    no bypass of the standard response path.
```

Validation ladder (each integration, in order): 1 import/structural test → 2 lifecycle test → 3 capability invocation → 4 real runtime smoke → 5 real E2E where credentials/environment permit → 6 failure-path validation → 7 disable/unavailable validation. "Installed" ≠ "integrated"; "connected" ≠ "working"; "unit tests pass" ≠ "production path works".

---

*This report is derived solely from repository evidence and the documented 2026-09-04 live session. The `21aad60` experiment remains fully inspectable at `KIO-21AAD60-MCP-HANDOFF-BACKUP`; nothing here copies its code into the restored baseline.*
