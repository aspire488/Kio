# NEXT INTEGRATION PLAN — KIO FINAL

**Date:** 2026-09-04
**Status:** PLANNING ONLY — see §14. No integration code was written for this plan.
**Baseline:** `f46e21c` (restored 2026-09-04). Integration experiment preserved at `KIO-21AAD60-MCP-HANDOFF-BACKUP`.

---

## 1. Stable baseline

| Item | Value |
|---|---|
| Selected commit | `f46e21c` "chore: consolidate full KIO system restoration" |
| Branch | `kio-restoration-safety-20260823` (moved to `f46e21c` 2026-09-04) |
| Why selected | Direct evidence of intent: dedicated tags `KIO-F46E21C-SAFE` + branch `KIO-F46E21C-BACKUP`; commit consolidates the full restoration ("186+ relevant tests passing, 4 pre-existing failures unchanged"); the only child commit (`21aad60`) is the single-commit MCP integration handoff that repointed `launch_bot.py` at `KIO-Integration-Lab\kio` and defaulted optional MCP infrastructure ON. |
| Ancestry with `21aad60` | `f46e21c` is the **direct parent** of `21aad60` (`git merge-base --is-ancestor f46e21c 21aad60` ⇒ true). `21aad60` adds only the integration layer (7,652 insertions / 33 files). |
| Working tree | Only the known pre-existing `opencode.json` modification (dev-tooling executor MCP entry; contains a live Bearer token — never committed, preserved byte-for-byte). |
| Telegram | Completed restoration validation; subsystem untouched by this plan. |

## 2. Current KIO integration inventory (post-restore, evidence-verified)

| Surface | LOC (py) | State at `f46e21c` |
|---|---|---|
| `mini_kio/` (whole system) | ~99,536 | Canonical runtime/pipeline/media/memory/LLM. Core owned by KIO. |
| `adapters/` (external adapters: scrapling, openwork, agent_reach, shepherd, agency_swarm) | 873 | Dormant scaffolding. Only scrapling is reachable — 3 lazy call sites in `browser/facade.py`. Nothing else imports `adapters.*`. |
| `mini_kio/core/mcp/` (MCP client, registry, provider, in-process server defs: docker/fs/git/github/postgres/redis/sqlite/terminal) | 1,677 | Dormant generic mechanism. No server configs, no active connections. |
| `mini_kio/runtime/mcp_runtime/` (runtime, server, transport, executor, health, registry) | 1,331 | Dormant generic mechanism; imported by `capability_registry`, `execution_boundary`, `operational_health`, `runtime`, memory self-model. |
| `mini_kio/core/credential_vault.py` | 877 | Auth/credential boundary infrastructure. |
| `mini_kio/core/providers/` (browser, desktop, filesystem, system, terminal, workflow) | 484 | KIO's NATIVE capability providers — not external glue. |
| `mini_kio/knowledge/` (duckduckgo, exa, jina_reader, tavily, wikipedia + retrieval router) | — | Native web search/research capability. |
| LLM gateway / provider registry | — | Core; not counted as integration glue. |
| Untracked top-level shells (`mcp/`, `providers/`, `execution/`, `kio/`, `tools/`, `aura/`…) | 0 files | Empty leftover dirs; harmless, ignored/untracked. |

**Conclusion:** the baseline is internally self-contained. No external service is wired into the runtime pipeline as a required capability, and the `docs/external_dependency_authority_register.md` rows claiming "Wrapper — Active" (CUA, Scrapling, MarkItDown) are not backed by runtime wiring — a lesson-driven correction applied here.

## 3. MCP lessons

See `reports/MCP_INTEGRATION_LESSONS.md` (full evidence). Headline lessons driving this plan:

1. Lifecycle (not protocol) is where integrations fail: reconnect storms, event-loop ownership, duplicate connects, stale callbacks, orphaned children.
2. Optional integrations must stay optional and default-OFF; nothing external is a startup dependency.
3. External dispatch must not be woven into the canonical pipeline core.
4. Tool discovery is lazy and deterministic; never enumerate hundreds of tools; guard conversational false-positives.
5. Credentials live only in `.env`/OS stores; never in tracked or working-tree config; formatters redact by construction.
6. Real-runtime validation outranks test count; validation is a ladder, not a gate.
7. LOC accounting must include all touched non-test files under one fixed definition.
8. Integrations land in small revertible slices — never a single squashed handoff.
9. FINAL stays self-contained; no Lab pointers/copies; the authority register must reflect wired reality.
10. KIO never kills processes it did not spawn.

## 4. Mandatory integration contract (one standard, all future integrations)

```
DISCOVER → ADAPTER → CAPABILITY REGISTRATION → AVAILABILITY/LIFECYCLE
         → AUTH/CREDENTIAL BOUNDARY → EXECUTION → VERIFICATION
         → RESULT NORMALIZATION → KIO RESPONSE
```

- **States (per integration):** `UNAVAILABLE`, `CONNECTING`, `READY`, `DEGRADED`, `FAILED`. Startup succeeds in every state; only core failure blocks startup.
- **Discovery rule:** capability summary → likely capability → discover the relevant external tool(s) → execute → verify → normalize. Search/discovery is a capability, NOT the universal fallback. LLM is NOT the universal fallback. Deterministic routing remains preferred once intent is resolved.
- **Security contract (documented before code):** credential source, storage boundary, injection mechanism, scope, revocation behavior, failure behavior, user-confirmation requirements, sensitive-result handling, audit requirements.
- **Adapter contract:** `__adapter_id__`, `__version__`, `CAPABILITIES`, `class Adapter` with lazy imports and `health()` (existing spec: `docs/specifications/ADAPTER_REGISTRY.md`). External SDKs are never imported by `mini_kio/core` directly.
- **Result normalization:** reuse the rules codified in the experiment's formatter (human text, no raw JSON, no IDs/etags/secrets, empty ≠ error, malformed ≠ crash) — patterns only, ported under the baseline's own conventions.
- **Audit/trace:** capability invocation is logged with integration id + state; failures classify as A–G (code/config/dependency/credential/network/provider/unrelated) and never crash the runtime.

## 5. Candidate ranking

Classification key: A=use directly, B=wrap with adapter, C=selectively copy a tiny static artifact, D=reference only, E=reject. All candidates below are re-derived from code/register evidence; earlier Lab-era evaluations were used only where the register corroborates.

### TIER 1 — integrate next

#### T1-a: MarkItDown (document → Markdown) — classification **B (wrap)**

| Attribute | Assessment |
|---|---|
| Capability gained | Convert docx/xlsx/pptx/pdf/html into clean Markdown for KIO ingestion/knowledge. |
| Why KIO needs it | KIO natively generates OOXML artifacts and handles media; it has no local document→text reader. Lets KIO read back its own artifacts and user documents for memory/context. |
| Overlap with existing KIO | None (generation exists; ingestion of office docs does not). Complementary to `knowledge/` search providers. |
| Integration boundary | `adapters/markitdown/` (lazy import of `markitdown` lib) → `ExecutionProvider` wrapper → provider_registry. |
| Dependency footprint | 1 pip library (pure Python, ~173k-star, permissive). No servers, no containers. |
| Runtime requirements | None (in-process, local). |
| Credential requirements | None. |
| Lifecycle complexity | Very low (stateless conversion). |
| Security risk | Low — file content stays local; only risk is untrusted-document parsing (sandbox note). |
| Est. KIO glue LOC | 250–350 non-test (adapter + provider + registration). |
| Validation method | Ladder: import → lifecycle → invoke on a KIO-generated docx/xlsx/pptx → real runtime smoke → failure path (corrupt file) → disable test. |
| Rollback method | Delete the two module files + registration line; registry default OFF. |
| Recommendation | **Integrate next (Phase B).** Highest new-capability-to-risk ratio. |

#### T1-b: Scrapling (structured web extraction) — classification **B (wrap, reuse existing)**

| Attribute | Assessment |
|---|---|
| Capability gained | First-class structured extraction of a specified URL (already proven usable from `browser/facade.py`). |
| Why KIO needs it | Complements native search providers (ddg/exa/jina/tavily/wikipedia) with page-level extraction for research briefs (`mini_kio/research/briefs.py`). |
| Overlap with existing KIO | Low — search ≠ single-page structured extraction. |
| Integration boundary | Wire the EXISTING `adapters/scrapling/` adapter (15 files, 170 LOC) into the provider contract; no new external code. |
| Dependency footprint | Library already present/used by browser facade. |
| Runtime requirements | None beyond the library. |
| Credential requirements | None. |
| Lifecycle complexity | Low (stateless). |
| Security risk | Low; SSRF care: only user-specified URLs. |
| Est. KIO glue LOC | 150–250 (provider wrapper + registration + capability route). |
| Validation method | Ladder incl. real extraction of a live URL; failure path (unreachable host). |
| Rollback method | Unregister provider; delete wrapper file. |
| Recommendation | **Integrate next (Phase C)** — also de-orphans the dormant `adapters/` scaffolding. |

### TIER 2 — integrate later (each requires a founder decision before any code)

| Candidate | Capability | Why later / condition | Est. glue | Key risk |
|---|---|---|---|---|
| Executor/OpenAPI gateway (Gmail/Calendar/Drive…) — re-derived under contract | Read Google services via NL | The `21aad60` implementation is REJECTED as-is (hard startup dep, daemon kills, token plumbing). Only revisit after a Tier-1 integration proves the contract + auth boundary; must be optional, default OFF, no process killing, OAuth via `.env`. | 400–600 | Auth boundary, remote server, scope |
| Browser-use autonomous browsing (classification B) | LLM-driven multi-step web tasks | Overlaps existing deterministic browser/CDP stack; heavy dep; needs founder decision that autonomous browsing is wanted. | 300–450 | Overlap, LLM cost, runaway actions |
| OpenHands (classification B) | Autonomous coding agent | Duplicates KIO's own execution/model layer and operator authority model; heavyweight SDK + sandbox. Strong case to stay reference. | 300–450 | Duplication, authority conflict |

### TIER 3 — reference / pattern only

| Candidate | Why reference only |
|---|---|
| CUA (VM computer use) | Requires Docker/QEMU/cloud VM infra for capability that overlaps native desktop/app operators. Register claims "Active" — contradicted by wiring evidence. Pattern source only. |
| Pipecat (voice pipeline) | Real-time voice needs transports/audio infra; no voice channel exists in KIO today. Pattern source for future voice phase. |
| Open-LLM-VTuber / avatar | Far-future surface; pattern only. |
| Crawl4AI | Heavy crawling service; existing search + extraction cover current needs. |
| Shepherd (distributed scheduling) | Centralized runtime is an ARCHITECTURE_LOCK rule; distributed scheduling contradicts it today. |
| Agent-Reach, Agentic-Inbox, LibreChat, OpenWork | No current channel need; OpenWork scaffolding already staged in `adapters/` — revisit only with a concrete workflow use. |

### REJECTED

| Candidate | Reason |
|---|---|
| Docker MCP Gateway (315+ servers) | Heavyweight Docker infra; tool flood (violates discovery rule); was `optional: false`. Reject unless explicit founder decision. |
| Graphiti + Neo4j | Second memory system (living model + semantic graph already exist); heavyweight DB server; credential plumbing. Reject. |
| Agency-Swarm / multi-agent orchestration | `docs/FORBIDDEN_PATTERNS.md` bans multi-agent coordination. Reject. |
| OpenCode MCP stack (filesystem/git/memory/context7/playwright + executor) | Development tooling only (strategy §17; `KIO_MCP_SETUP.md`). Never a KIO runtime capability. |
| Any external repo cloned/copied into FINAL | External-repository rule (§10): A–E classification with written reason; KIO retains architectural ownership. |

## 6. Architecture boundaries

- **KIO owns:** `mini_kio/` (runtime, pipeline, operators, memory, LLM gateway, provider contract, registries), the `adapters/` directory contents under the Adapter contract, capability naming, result normalization.
- **External owns:** external libraries/SDKs/repos and their own servers/runtimes.
- **The seam:** `adapters/*/` (external-facing, may import external SDKs lazily) ↔ `mini_kio/core/providers/*_provider.py` (KIO-facing, implement `ExecutionProvider` from `provider_contract`) ↔ `mini_kio/core/provider_registry.py`. Nothing below the seam knows the external world.
- **No new managers:** reuse the existing AdapterRegistry spec, `provider_registry.py`, `credential_vault.py`. Do not add another registry/manager layer.
- **Core is inviolate:** no edits to pipeline `classify/resolve/exec/compose` hot path; external dispatch hangs off the pre-existing neutral `IntentType.MCP` handling leaf (present at `f46e21c`), defined precisely in Phase A.
- **Optionality:** every integration defaults OFF (`MCP_RUNTIME_ENABLED` stays `false`; per-integration enable flags explicit).
- **Self-containment:** no Lab path references, no copied external trees, no process-kill of non-KIO processes, no `asyncio.run` misuse.

## 7. Dependency graph

```
                      ┌──────────────────────────────┐
                      │  KIO response pipeline       │  (unchanged core)
                      └──────────────┬───────────────┘
                                     │ normalized result
                      ┌──────────────▼───────────────┐
                      │  Deterministic routing leaf  │  ← external dispatch point
                      │  (IntentType / capability)   │     (defined Phase A)
                      └──────────────┬───────────────┘
                                     │
                      ┌──────────────▼───────────────┐
                      │  provider_registry           │  (KIO-owned)
                      └──────────────┬───────────────┘
                                     │ ExecutionProvider impl
                      ┌──────────────▼───────────────┐
                      │  providers/<name>_provider   │  (thin, KIO-facing)
                      └──────────────┬───────────────┘
                                     │ Adapter contract
                      ┌──────────────▼───────────────┐
                      │  adapters/<name>/            │  (lazy external SDK imports)
                      └──────────────┬───────────────┘
                                     │
              ┌──────────────────────┼──────────────────────┐
              ▼                      ▼                      ▼
   external SDK (lib)      external service (HTTP/MCP)   credentials via
   (local, no server)      (only if auth boundary OK)    credential_vault/.env
```

Direction of dependency: always inward toward `mini_kio` core. `adapters/` never imports `mini_kio` internals beyond the Adapter contract types. No upper layer imports external SDKs directly.

## 8. LOC budget (recalculated — the reported 2,380/2,500 is not reproducible)

- **Reported figure:** "external integration glue 2,380/2,500, 120 remaining."
- **Why not reproducible:** reconstructing from `f46e21c..21aad60`, the near-final count of the four new adapters (751) + four providers (640) + `mcp_tool_mapping` (684) + `mcp_result_formatter` (476) ≈ **2,551**, close to 2,500 — but that subset excluded the invasive wiring: `mcp_runtime` hardening (+664), pipeline rework (+617), runtime deferred-connect + executor-daemon logic (+117), config/launcher/capability/kio_bot edits (~80). Total non-test footprint of the handoff: **3,923 LOC** (+3,729 test). The headline accounting understated the real cost by ~55%.
- **Fixed definition (going forward):** external-integration glue = every non-test line added/changed whose purpose is connecting an external repo/service/SDK, including lifecycle wiring, config, registration, and launcher edits — excluding generic dormant mechanism reused as-is and excluding tests.
- **Current baseline active glue:** 0 LOC of *new* active external glue (the `21aad60` layer was removed in restoration; dormant mechanism — `adapters/` 873, `core/mcp` 1,677, `mcp_runtime` 1,331, vault 877 — is pre-existing, mostly unwired, and is reused, not added).
- **Ceiling:** 2,500 LOC of external-integration glue; never exceeded without an explicit founder/architecture decision. Preference: stay well under.
- **Estimated next-phase cost:** Phase A ~150–250 (mostly tests) · Phase B (MarkItDown) ~250–350 · Phase C (Scrapling) ~150–250.
- **Projected total after Phases A–C:** ≤ ~1,000 non-test glue LOC (**~40% of ceiling**), leaving ≥ 1,500 headroom for a later founder-approved integration.

## 9. Implementation phases (plan only — see §14)

### PHASE A — Integration foundation hardening (slice A1..A3)
- **Exact repo:** FINAL only.
- **Exact KIO files expected to change:** `mini_kio/core/provider_registry.py` (adopt `adapters/` loading per ADAPTER_REGISTRY spec), `adapters/__init__.py`/`adapters/registry.py` wiring (make existing registry consumable by runtime), `mini_kio/core/config.py` (explicit per-integration enable flags; confirm `MCP_RUNTIME_ENABLED` default OFF), a small lifecycle-state helper module (states + bounded-retry constants, no new manager), tests.
- **Expected LOC:** 150–250 non-test (+150–250 test).
- **Dependencies:** none new.
- **Runtime requirements:** none.
- **Credentials:** none.
- **Tests:** registry adoption, optionality defaults, state transitions, disable paths.
- **Real-runtime validation:** boot KIO via production entrypoint; verify startup identical to baseline; Telegram single message still answered.
- **Rollback:** revert slice commits individually.
- **Hard-stop:** any change to pipeline `classify/resolve/exec/compose`; any default-ON flag; any new manager/registry → STOP and re-plan.

### PHASE B — Highest-value low-risk integration: MarkItDown
- **Exact repo:** FINAL only. External: `microsoft/markitdown` pip package (use, not copy).
- **Exact KIO files expected to change:** `adapters/markitdown/adapter.py` (+`__init__.py`/provider.yaml), `mini_kio/core/providers/markitdown_provider.py`, capability registration + routing leaf wiring, `requirements.txt`, tests.
- **Expected LOC:** 250–350 non-test (+250–350 test).
- **Dependencies:** `markitdown` (single pip).
- **Runtime requirements:** none.
- **Credentials:** none.
- **Tests:** import/structural, lifecycle, conversion of docx/xlsx/pptx generated by KIO itself, corrupt-input failure path, disable test.
- **Real-runtime validation:** KIO real-runtime smoke — ask KIO to summarize a generated artifact through the normal pipeline; Telegram regression (1 message).
- **Rollback:** unregister provider + remove files; flag OFF.
- **Hard-stop:** if conversion quality on KIO's own artifact formats is unacceptable, or LOC overrun > 150 over estimate → STOP, reassess.

### PHASE C — Second integration: Scrapling (reuse existing adapter)
- **Exact repo:** FINAL only. External: existing `adapters/scrapling/` code (already present) + library.
- **Exact KIO files expected to change:** `mini_kio/core/providers/scrapling_provider.py`, registration/routing leaf, research-briefs call site in `mini_kio/research/briefs.py`, tests. `adapters/scrapling/` only if a gap is proven.
- **Expected LOC:** 150–250 non-test (+150–250 test).
- **Dependencies:** none new (already present).
- **Runtime requirements:** none.
- **Credentials:** none.
- **Tests:** ladder incl. real live-URL extraction; unreachable-host failure path; disable path.
- **Real-runtime validation:** real extraction through normal pipeline; Telegram regression (1 message).
- **Rollback:** unregister + remove wrapper.
- **Hard-stop:** SSRF/untrusted-URL concern unresolved → STOP.

### PHASE D — Workflow/automation integration — ONLY if justified
- Candidate: deterministic calendar/tasks-style operator ONLY if a concrete workflow need is stated by the founder. Default: skip. If run: same contract, small slices, ≤ 300 LOC, optional default OFF.

### PHASE E — Advanced agents / browser / voice / desktop — ONLY where justified
- Candidates: browser-use, OpenHands, CUA, Pipecat (re-evaluated under contract). Each requires: founder decision, lifecycle + runtime analysis per candidate row in §5, auth-boundary proof from an earlier phase, real-runtime validation, and its own hard-stop conditions. **Explicitly NOT scheduled.**

## 10. Validation gates

Per slice: (G1) import/structural test · (G2) lifecycle test incl. all states · (G3) capability invocation · (G4) real runtime smoke via production entrypoint · (G5) real E2E where creds/env permit · (G6) failure-path validation · (G7) disable/unavailable validation. Plus: pinned deterministic suite run BEFORE and AFTER each slice on the SAME baseline with counts reported (lesson §9), and Telegram regression (one normal message) after every slice. "Installed" ≠ "integrated"; "connected" ≠ "working"; "unit tests pass" ≠ "production path works."

## 11. Security gates

- Credential review: no secret in code, tracked config, working tree, fixtures, or logs (search the diff for token shapes).
- `.env` remains the only credential source; `credential_vault.py` boundary respected.
- No process kill of non-KIO processes; no reading external state files.
- No new startup dependencies; optionality flags default OFF.
- Result normalizers redact raw payloads/IDs/etags by construction.
- Untrusted-input handling (documents, URLs) reviewed per integration.
- Diff checked against `docs/FORBIDDEN_PATTERNS.md` before merge.

## 12. Rollback strategy

- Every phase ships as small revertible slices; each slice is independently revertible via `git revert` (no squashed handoffs).
- Per-integration disable flag = runtime rollback without code change.
- Removal rollback = delete adapter + provider modules and unregister (documented per candidate in §5).
- Full-system rollback = branch reset to `f46e21c` (proven 2026-09-04; `KIO-F46E21C-SAFE` tag + backup branch retained). `21aad60` remains recoverable at `KIO-21AAD60-MCP-HANDOFF-BACKUP`.

## 13. Hard-stop conditions

STOP instead of coding if: stable baseline cannot be determined · restoration would destroy user work · current architecture contradicts project authority documents (`ARCHITECTURE_LOCK`, `FORBIDDEN_PATTERNS`) · integration duplicates existing KIO infrastructure · dependency/resource cost is unjustified · licensing is unacceptable · authentication boundary is unclear · verification cannot be performed · integration would exceed the LOC ceiling · integration requires copying an external framework wholesale · optional integration would become a mandatory startup dependency. Also: any proposed edit to the pipeline core, any new manager/registry, any default-ON flag, or any requirement to install Docker/QEMU/Neo4j-class infrastructure for a Tier-1/2 candidate → STOP for founder decision.

## 14. Explicit "DO NOT IMPLEMENT YET" statement

**DO NOT IMPLEMENT THE INTEGRATIONS DESCRIBED IN THIS PLAN.** This document is the planning gate only. The repository is restored to the stable baseline (`f46e21c`) with the integration experiment preserved for study (`KIO-21AAD60-MCP-HANDOFF-BACKUP`). No Phase A–E code exists or may be written until a separate implementation prompt explicitly approves a phase and its first slice.

**This task ends when:** STABLE BASELINE RESTORED + MCP LESSONS EXTRACTED + NEXT INTEGRATION PLAN WRITTEN + NO NEW INTEGRATION CODE IMPLEMENTED.
