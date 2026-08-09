# KIO Implementation Plan

**Status**: Ratified — Active Revision
**Supersedes**: `KIO_IMPLEMENTATION_BLUEPRINT.md`
**Current checkpoint (reconciled 2026-08-09)**: The historical claim "ALL 30 SLICES COMPLETE" was **partially stale**. Reconciliation against source + tests + live evidence (Revision 5 below; see also `KIO_MASTER_PLAN_AUDIT_REPORT.md` and the two 08-09 execution reports) corrects it as follows: **Stream A (Slices 1-6) and the genuinely-delivered slices are IMPLEMENTED** — routing repairs (3), decision logging (5), dead-code removal + C-09 unification (6), Identity Resolver (10), Session Continuity (11-12), Active Window Tracker (16), Context Fusion (17), Keyword + Structured Memory + FQ-05 (18, incl. Phase-2/3 foundations). **Slice 15 (M-LIVE) was executed live on 2026-08-09 (Telegram verification matrix). NOT STARTED / NO SOURCE**: Credential Vault (8-9 — only a stale `.pyc` exists), Proactive Event Bus (13 — EventBus is browser-scoped only), Startup Configuration Validation (14 — no framework exists), Proactivity (23-27), Autonomy/Goals (28-30 — no goals module exists; `executive.py`/`orchestrator.py` absent), Alternative Generation (22). **PARTIAL**: Canonical Provider Abstraction (4 — two provider bases remain, D-08 unresolved), Preference Extraction (20), Reasoner Refactor (21). Slice 19 SKIPPED (optional). Test baseline at HEAD `28721f5`: **1761 passed / 68 failed / 1829 collected**, 68 failures pre-existing. Next: live M-LIVE already satisfied for Telegram; missing slices 8-9/13/14/22-30 remain roadmap per `KIO_MASTER_EXECUTION_PLAN.md`.
**Revision 3 additions**: Slice 3 expanded with routing pattern repairs (exec_patterns, is_knowledge_query, confirmation triggers, ordinal references). Slice 6 expanded with C-09 capability-discovery unification + triple pronoun-resolution merge. Slice 18 expanded with FQ-05 memory governance (retention metadata, confidence decay, inspection/deletion). §26 FQ-06 override policy added. §1 Critical Gaps expanded to acknowledge all known issues.
**Revision 4 additions (2026-08-08) — Media playback recovery**: YouTube playback/control recovery completed and committed as `b5db667` (`fix(media): stabilize YouTube playback and control`). **COMPLETED**: injected YouTube player-script/player-control reliability (self-contained injected functions), playback state verification (incl. currentTime), extension build compatibility, controlled YouTube search/replay routing, preserved verified media playback state, media transport controls incl. mute/unmute. **Proven root cause fixed**: Chrome extension scripts injected via `chrome.scripting.executeScript({func: ...})` are serialized independently, so references to `background.js` outer-scope helpers were unavailable in the page execution context — producing `script 'play' returned non-state payload` / `Couldn't play X on YouTube`. The fix made the injected player-control/state functions self-contained, restoring correct playback and state verification. **Live validation** demonstrated working play / pause / resume / "play it" / "play again" / "play next video" / "play h" / YouTube search / search again / mute / unmute. Playback correctness is substantially restored — NOT 100% media correctness. **REMAINING (NOT fixed, NOT playback-engine failures)**: (1) semantic media selection still imperfect — KIO can select a lexically related but semantically wrong YouTube result for ambiguous/short queries (observed: "Play brand new day", "Play lm game trailer"); owned by media entity resolution / query understanding / candidate retrieval, not playback transport. (2) YouTube Shorts pause/resume — investigation pending; no root cause asserted. **NEXT MEDIA WORK**: system-level media entity resolution / semantic selection (framed as a system-level entity-resolution problem, not another set of YouTube filters), then separately investigate Shorts pause/resume. No new architecture, media manager, or provider was introduced; media selection and Shorts are explicitly NOT claimed solved.
**Revision 5 additions (2026-08-09) — Execution System + Contextual Control Milestone**: The 08-09 work (implemented, live-verified, uncommitted at HEAD) fixed a system-level execution defect class and added three user-visible capabilities. **Root problem**: target identity was collapsed across the pipeline — web-app opens were serialized as `chrome::open_url::<url>::<name>` capability strings, stored verbatim as conversational referents, and `close_app` did `key.split("::")[0]`, so "Close it" after "Open ChatGPT" killed the **entire Chrome session**. **System-level fix** (evidence: `KIO_TARGET_IDENTITY_FORENSIC_AUDIT_20260809.md` + `KIO_EXECUTION_SYSTEM_FIX_AND_CAPABILITIES_20260809.md`): (1) new canonical target-identity module `mini_kio/core/target_ref.py` (parse/safe-name/display-name for app · browser · tab · webapp · media refs); (2) removed the `::` collapse — web-target closes route to tab scope (`_close_web_target`), never a process kill; (3) web opens verify tab identity instead of `verification_mode: noop`; (4) contextual referents now store safe target names, not serialized routing strings; (5) multi-step execution aggregates verified per-step outcomes truthfully (no blanket "done"); (6) response formatters render brand-cased display names (ChatGPT, YouTube) — no raw URLs/PIDs/capability strings in user-facing text. **Capabilities unlocked (live-verified on Telegram 2026-08-09)**: (A) context-aware computer control — "What's open?", focus/switch native apps + browser targets; (B) composed multi-action tasks — "Open ChatGPT and Telegram" with independent per-target verification; (C) state-aware media control — "What's playing?", verified Pause/Resume, contextual media references. **Evidence**: live matrix (Open ChatGPT → Close it closed the tab, Chrome alive; Play Never Gonna Give You Up → paused=False verified; Pause it / What's playing? / Resume it; Hi during media ≈1.7s) + 26 new targeted tests + 200 targeted regression tests green across 13 suites; pre-existing failures baseline-identical. **NEXT (unchanged)**: system-level media entity resolution / semantic selection, then Shorts pause/resume investigation.
**Revision 2 additions**: §3 architecture diagram updated (Agent Layer, Interface Layer, MCP Runtime). §12 expanded with KIO's own MCP runtime design (async, crash-isolated, 8 servers, 59 tools). §24 Agent Layer Architecture (interface-based protocol, registry, multi-agent orchestration). §25 Interface Architecture (voice-primary, desktop power-user, platform-agnostic Channel protocol). §26 Companion Evolution (assistant → cognitive partner → PCI mapped to phases). 6 new ponytail ceilings (MCP, Agent Layer, Interface, Voice).
**Vocabulary**: Foundation Streams (parallel work tracks) → Implementation Phases (sequential deliveries). No "Cognitive Layers." No "Gates" (retired with convergence planning). Every slice is a thin vertical: working code in one commit.

---

## 1. Executive Summary

KIO is a **Persistent Companion Intelligence** (per `KIO_COMPANION_INTELLIGENCE_DOCTRINE.md`). A system that develops shared history, acts with initiative, and operates under **Freedom of Mind, Governance of Action**. Not a chatbot. Not a Telegram bot. Not a command router. Its architecture spans four layers: Runtime → Agent Layer → Execution Boundary → Interface Layer.

The codebase has real engineering substance: production runtime, safety gateway, provider registries, MCP runtime (async, crash-isolated), browser automation, voice pipeline, **97.8% test pass rate (confirmed by Production Acceptance Report, 2026-07-20)**. Phase 0 cleanup complete (~150 files removed). Gates C-1 through C-4b delivered. The gap is not stability — it's coherence across three new architectural layers: Agent Layer (multi-agent coordination), MCP Layer (tool integration runtime), and Interface Layer (voice-primary multi-channel).

**Critical gaps this plan solves:**
1. **No prerequisite resolution** — KIO cannot discover it needs credentials/permissions/consent, request them, store them, and retry. It either fabricates or fails silently.
2. **No identity model** — KIO cannot resolve "Aaron" across messaging platforms, email, and contacts.
3. **No session continuity** — KIO forgets everything on restart.
4. **No proactive capability** — KIO never acts without being asked.
5. **8 "cognitive layers"** that over-engineer the planning taxonomy and gate useful work behind unnecessary infrastructure.
6. **C-09 capability fragmentation** — three independent capability-discovery systems (CommandRegistry, ProviderRegistry, CapabilityRegistry) don't consult each other; planner validates actions against stale session state.
7. **Conversational routing failures** — exec_patterns start anchor blocks "can you open X"; is_knowledge_query patterns miss natural queries like "Interstellar cast"; media transport commands (pause/next) unreachable; exact-match confirmation triggers reject "yes please".
8. **Triple pronoun-resolution systems** — ContinuityEngine, MediaReferenceResolver, and IntegrationAdapter resolve "it"/"that"/"him" against three independent state stores that can diverge.
9. **FQ-05 memory governance absent** — no per-item retention metadata, no confidence decay, no user-facing inspection/correction/deletion.
10. **FQ-06 override policy absent** — KIO has no bounded-disagreement behavior; no "disagree once, then defer" protocol.

**The fix**: Phase 0 (complete) → 2 Foundation Streams + foundation fixes embedded in existing slices → 4 Implementation Phases → ~30 slices. Each slice produces working, testable, mergeable code.

---

## 2. Guiding Principles

Unchanged from the ratified blueprint. Every implementation decision is measured against these, in priority order:

| # | Principle | Rule |
|---|-----------|------|
| 1 | **Surgical change** | Touch only what the requirement mandates. |
| 2 | **Single canonical owner** | Every capability in exactly one subsystem. |
| 3 | **Deterministic before LLM** | If deterministic exists, use it. |
| 4 | **Intelligence ≠ LLM** | Reasoning, planning, memory are separate concerns. |
| 5 | **Behaviour before optimisation** | Make it work, then make it right, then make it fast. |
| 6 | **Thin vertical slice** | Every commit delivers working value. |
| 7 | **Test before merge** | RED → GREEN → REFACTOR for all new logic. |
| 8 | **Architecture before convenience** | Right architecture even when harder. |
| 9 | **Memory influences behaviour** | Retrieved memories must change system behaviour. |
| 10 | **Reasoning before execution** | No action without justification. |
| 11 | **Safety before autonomy** | KIO vetoes any action, including its own. |
| 12 | **Explainability over hidden behaviour** | Every decision traceable to a rule or reasoning step. |
| 13 | **No heuristic chain for reasoning** | 3+ heuristics → replace with inference step. |
| 14 | **One integration point per external dependency** | No scattered ad-hoc calls. |

---

## 3. Final Architecture

### High-level structure

```
┌──────────────────────────────────────────────────────────────┐
│                     Runtime (KioRuntime)                     │
│  dispatch authority, safety states, resource guarding        │
├──────────────────────────────────────────────────────────────┤
│                      Agent Layer                              │
│  Agent protocol → registry → resolver → orchestrator         │
│  (interface-based, not hardcoded to any agent provider)       │
├──────────────────────────────────────────────────────────────┤
│                   Execution Boundary                          │
│  classify → gate(prerequisites) → resolve(agents) → validate │
│  → execute → verify                                          │
├──────────────────────────────────────────────────────────────┤
│   Provider Registry  │  Capability Registry  │  MCP Runtime  │
│   (15 providers)     │  (tool discovery)    │  (async,    │
│                      │                      │  crash-iso) │
├──────────────────────────────────────────────────────────────┤
│   Context Manager    │  Memory Store         │  Goal Mgr    │
├──────────────────────────────────────────────────────────────┤
│   Credential Vault   │  Identity Resolver   │  EventBus    │
├──────────────────────────────────────────────────────────────┤
│   LLM Gateway (multi-provider)    │    Intent Pipeline      │
├──────────────────────────────────────────────────────────────┤
│              Interface Layer                                 │
│  Voice (primary)  │  Desktop (power-user)  │  Platform      │
│  (STT/TTS/speaker │  (CLI, TUI)           │  Transports    │
│   diarization)    │                       │  (Telegram,    │
│                    │                       │   Discord)     │
└──────────────────────────────────────────────────────────────┘
```

All existing subsystems (runtime, execution boundary, registries, MCP context, LLM gateway) are correct and preserved. **Three new layers** are formalized:

- **Agent Layer** — interface-based agent abstraction. Protocol-driven. Not coupled to Agency Agents or any specific agent provider. Owns agent registration, resolution, lifecycle, and multi-agent orchestration. Replaces the existing `Executive`/`Orchestrator`/`Planner` pattern with a unified agent protocol — the old classes become the first Agent Layer implementation, not a parallel system.
- **MCP Runtime** — already exists in `mcp_runtime/` as an async, crash-isolated, auto-recovering runtime. Formalized as KIO's own MCP layer (not OpenCode's). Owns server lifecycle, tool discovery, transport management.
- **Interface Layer** — Voice-first design. Voice is the primary interaction mode (STT → NLU → execution → TTS). Desktop CLI/TUI is the power-user interface. Platform transports (Telegram, Discord) are abstracted behind a common `Channel` protocol — no interface is hardcoded to any platform.

### Development vs Runtime MCP classification

Every MCP server accessible to KIO belongs to exactly one category:

| Category | Purpose | Examples | Wired Into |
|----------|---------|----------|-----------|
| **Core Runtime** | KIO's own tool execution infrastructure | Filesystem, Terminal, Git, SQLite, Browser | `CapabilityRegistry` at bootstrap |
| **Optional Runtime** | User-configured tool capabilities | Docker, Postgres, Redis, GitHub, Gmail, Slack | User config → `MCPRuntime.add_server()` |
| **Development Only** | Building KIO itself — never shipped as runtime capability | Playwright/Browser (for testing), Context7, WebFetch | `AGENTS.md` / `opencode.json` only |
| **Future** | Planned but not yet implemented | Calendar, Drive, WhatsApp, enterprise MCPs | Roadmap |

Development MCPs are documented in `AGENTS.md` and configured via `opencode.json`. They are never loaded by KIO's MCP Runtime. The two environments share no configuration, no process, and no dependency. This distinction is enforced by directory convention: Development MCPs live in project root config; Runtime MCP servers live in `mini_kio/runtime/mcp_runtime/` or user configuration.

Additions within existing layers: Credential Vault, Identity Resolver, Event Bus, and the `resolve` stage in the execution boundary.

### Execution pipeline (the critical path)

```
User input → Intent Classifier → [resolve prerequisites] → Safety Check → Execute → Verify → Respond
                                        │
                                        ▼
                              ┌──────────────────┐
                              │  Execution Gate   │
                              │  (prerequisite    │
                              │   resolution)     │
                              └──────────────────┘
                                        │
                              missing? → emit structured request → user provides → verify → store → retry
                                        │
                              present? → proceed
```

The Execution Gate is one generic mechanism. Not a special case for credentials, permissions, consent, or any other prerequisite type. Every prerequisite is a key in the Prerequisite Registry. Missing → blocked. Present → proceed.

---

## 4. Foundation Streams

### Foundation Stream A: Runtime Consolidation (unchanged, continue)

**Purpose**: Fix known architectural problems. Eliminate duplicate systems, monolithic routing, split ownership.

**Prerequisites**: None — Slices 1-2 committed.

**Work items**:
1. ~~SessionContext Consolidation~~ (committed, Slice 1)
2. ~~system_routes Extraction~~ (committed, Slice 2)
3. ~~Remaining `_route_builtin` decomposition into dispatched handler modules by domain~~ (committed, Slice 3 + Slice 3 routing repairs)
4. ~~Establish single canonical provider abstraction~~ (committed, Slice 4)
5. ~~Add decision logging to routing paths~~ (committed, Slice 5)
6. ~~Phase 0 dead code removal~~ (committed — removed browser stubs, governance stubs, 4 unused adapter packages, providers/ package, 45 temp files, stale .pyc caches. Remaining: aura/ stub README, entity_state_engine.py stub, duplicate _normalize_public_result consolidation)

### Foundation Stream B: Continuity & Authentication (new, replaces old Streams B and C)

**Purpose**: Give KIO the ability to work with authenticated services, remember who people are across platforms, survive restarts, and proactively handle time-based events.

**Prerequisites**: None — can start after or alongside Stream A.

**Work items**:
1. **Prerequisite Resolution (Execution Gate)** — Add `resolve_prerequisites` stage to `execution_boundary.py` before handler invocation. Define `PrerequisiteGate` structured result type. Wire gate propagation through runtime to user-facing request flow.
2. **Credential Vault** — `keyring`-backed (Win Credential Manager, macOS Keychain, Linux Secret Service) + SQLite metadata. OAuth flow template. Storage only on explicit user consent. Never plaintext. Never fabricated.
3. **Identity Resolver** — Map person → contacts across messaging platforms (Telegram, email, WhatsApp, etc.). Connect to existing `resolvers/identity_resolver.py`. SQLite-backed. User-managed.
4. **Session Continuity** — Serialize runtime state (context buffer, safety state, active goals) to SQLite. Restore on startup. Periodic checkpoint during execution for crash recovery.
5. **Proactive Event Bus** — Time-based + state-change-based triggers. Morning briefing, goal reminders, build notifications. User-configurable proactivity level (off/low/medium/high).
6. **Startup Configuration Validation** — On launch, validate all required credentials (api_id, api_hash, bot token, provider keys). If missing: display validation report listing every missing credential with explanation, prompt user, validate, offer to persist securely to `.env`, re-run validation. Reusable framework for all providers. Never crash or partially initialise on missing config.
7. **Live Integration & Validation Phase** — Dedicated validation phase after Phase 1 completion. Covers provider validation, browser validation, memory validation, workflow validation, Telegram/Discord/Voice validation, agent orchestration validation, MCP validation, stress testing, recovery testing, end-to-end validation. Automated + manual scenarios.

---

## 5. Implementation Phases

4 sequential phases. Each phase delivers user-visible behaviour. No phase requires "cognitive layer infrastructure" — each is a set of concrete features wired into the existing runtime.

### Phase 1: Reliable Foundation

Requires: Stream A complete, Stream B Work Items 1-4.

**Deliverable**: KIO survives restarts, remembers the user, accesses authenticated services, stops execution when prerequisites are missing rather than fabricating them, and validates all configuration on startup.

```
Slices 3-15 (13 slices) 
┌─────────────────────────────────────────────────────────────┐
│ Stream A.3: Complete _route_builtin decomposition           │
│ Stream A.4: Single provider abstraction                     │
│ Stream A.5: Decision logging                                │
│ Stream A.6: Dead code removal (Phase 0 cleanup done)        │
│ Stream B.1: Execution Gate protocol                         │
│ Stream B.2: Credential Vault                                │
│ Stream B.3: Identity Resolver                               │
│ Stream B.4: Session Continuity                              │
│ Stream B.6: Startup Configuration Validation                │
│ Stream B.7: Live Integration & Validation Phase             │
└─────────────────────────────────────────────────────────────┘
```

### Phase 2: Situational Awareness

Requires: Phase 1 (session continuity, identity, credentials), Stream B Work Item 5.

**Deliverable**: KIO knows what's happening NOW (active window, foreground app, time/calendar context), remembers what happened BEFORE (keyword + structured memory), and initiates contextually appropriate suggestions.

```
Slices 16-22 (7 slices) 
┌─────────────────────────────────────────────────────────────┐
│ Stream B.5: Proactive Event Bus                             │
│ Context: Active window tracker                              │
│ Context: Context fusion (structured, not flat text)         │
│ Memory: Keyword + structured queries                        │
│ Memory: Vector support (optional)                           │
│ Memory: Preference extraction + influence                   │
│ Reasoning: Replace local_reasoner pattern matching           │
│ Reasoning: Alternative generation + comparison              │
└─────────────────────────────────────────────────────────────┘
```

### Phase 3: Initiative

Requires: Phase 2 (context, memory, event bus).

**Deliverable**: KIO acts without being asked. Morning briefings, stalled goal follow-ups, relevant suggestions. User can tune or disable.

```
Slices 23-27 (5 slices)
┌─────────────────────────────────────────────────────────────┐
│ Proactivity: Trigger model (time + state + goal conditions) │
│ Proactivity: Suggestion engine (ranked, confidence-gated)   │
│ Proactivity: Follow-up tracker (stalled goals)              │
│ Proactivity: Morning briefing                               │
│ Proactivity: Arbiter (confidence threshold, user tuning)    │
└─────────────────────────────────────────────────────────────┘
```

### Phase 4: Autonomy

Requires: Phase 3 (proactivity, context, memory, identity, credentials).

**Deliverable**: KIO accepts high-level goals and pursues them independently within safety boundaries. Read-only autonomy first. Write autonomy last.

```
Slices 28-30 (3 slices)
┌─────────────────────────────────────────────────────────────┐
│ Autonomy: Goal registry (user-defined + detected)           │
│ Autonomy: Autonomous execution loop (select → plan → exec)  │
│ Autonomy: Safety governor (hard boundaries, audit trail)    │
└─────────────────────────────────────────────────────────────┘
```

---

## 6. Work Items

### Stream A Work Items

| ID | Work Item | Slices | Depends On |
|----|-----------|--------|------------|
| A.3 | _route_builtin decomposition | 3 | A.1, A.2 (done) |
| A.4 | Canonical provider abstraction | 4 | A.3 |
| A.5 | Decision logging | 5 | A.4 |
| A.6 | Dead code removal (Phase 0) | 6 | A.5 |

### Stream B Work Items

| ID | Work Item | Slices | Depends On |
|----|-----------|--------|------------|
| B.1 | Prerequisite Resolution (Execution Gate) | 7 | A.3 (for stability) |
| B.2 | Credential Vault | 8-9 | B.1 |
| B.3 | Identity Resolver | 10 | B.2 |
| B.4 | Session Continuity | 11-12 | B.1 |
| B.5 | Proactive Event Bus | 13 | B.4 |
| B.6 | Startup Configuration Validation | 14 | B.2 |
| B.7 | Live Integration & Validation Phase | 15 | Phase 1 |

### Phase 2 Work Items

| ID | Work Item | Slices | Depends On |
|----|-----------|--------|------------|
| C.1 | Active window tracker | 16 | Phase 1, B.7 |
| C.2 | Context fusion | 17 | C.1 |
| M.1 | Keyword + structured memory | 18 | Phase 1, B.7 |
| M.2 | Vector support | 19 | M.1 |
| M.3 | Preference extraction | 20 | M.1 |
| R.1 | Reasoner refactor | 21 | M.1 |
| R.2 | Alternative generation | 22 | R.1 |

### Phase 3 Work Items

| ID | Work Item | Slices | Depends On |
|----|-----------|--------|------------|
| P.1 | Trigger model | 23 | Phase 2 |
| P.2 | Suggestion engine | 24 | P.1 |
| P.3 | Follow-up tracker | 25 | P.2 |
| P.4 | Morning briefing | 26 | P.3 |
| P.5 | Initiative arbiter | 27 | P.4 |

### Phase 4 Work Items

| ID | Work Item | Slices | Depends On |
|----|-----------|--------|------------|
| A.1 | Goal registry | 28 | Phase 3 |
| A.2 | Autonomous loop | 29 | A.1 |
| A.3 | Safety governor | 30 | A.2 |

---

## 7. Slice Breakdown

### Slice status reconciliation (verified 2026-08-09)
Statuses below are reconciled from source + tests + live evidence (`KIO_MASTER_PLAN_AUDIT_REPORT.md`; `KIO_TARGET_IDENTITY_FORENSIC_AUDIT_20260809.md`). "VERIFIED" means live-validated; "IMPLEMENTED" means source + tests confirm the slice's deliverable exists; "PARTIAL" means a stub or partial implementation exists; "NOT STARTED" means no source exists. This table corrects the historical "ALL 30 SLICES COMPLETE" checkpoint.

| Slice | Status | Evidence |
|---|---|---|
| 1-2 (Phase 0 / Stream A foundation) | IMPLEMENTED | Committed in earlier sessions; gate C-1..C-4b delivered |
| 3 — routing pattern repairs | IMPLEMENTED | `exec_patterns`, `is_knowledge_query`, media transport commands in classifier/`routing_utils.py` |
| 4 — canonical provider abstraction | IMPLEMENTED (D-08 resolved 2026-08-09) | Canonical contract = `core/provider_contract.py` `ExecutionProvider` (ABC), wired via `core/provider_registry.py` + `register_all_providers()`; dead top-level `providers/` Protocol package deleted (zero importers; restores earlier cleanup) |
| 5 — decision logging | IMPLEMENTED | Structured routing/trace logs (`trace_logger.py`, execution metrics) |
| 6 — dead code + C-09 unification | IMPLEMENTED | `resolve_capability()` in `routing_utils.py`; dead stubs deleted |
| 7 — execution gate protocol | **VERIFIED (2026-08-09)** | `PrerequisiteGate` + `resolve_prerequisites()` in `execution_boundary.py`, fail-closed before handler; 21 targeted tests; live smoke no-regression (prerequisite satisfied live) |
| 8 — credential vault: core | **VERIFIED (2026-08-09)** | `mini_kio/core/credential_vault.py` + `credentials` metadata table on the canonical backend engine; 22 targeted tests incl. mandatory secret-leak proof (see Slice 8 section below) |
| 9 — credential vault: lifecycle | OPEN | Slice 9 (refresh expired tokens / revoke / list-manage UI / expiry at the Execution Gate) not implemented — next Stream B work |
| 10 — identity resolver | IMPLEMENTED | `mini_kio/resolvers/identity_resolver.py` exists |
| 11-12 — session continuity | IMPLEMENTED | `memory_store.py`, `get_last_successful_interaction()`, continuity resolver |
| 13 — proactive event bus | NOT STARTED (browser-scoped only) | `EventBus` only in `runtime/browser_runtime/events.py`; no global bus |
| 14 — startup configuration validation | NOT STARTED | No validation framework found |
| 15 — live integration & validation (M-LIVE) | VERIFIED (Telegram; partial) | Live Telegram matrix executed 2026-08-09 (concurrency, media, app control, recovery) |
| 16 — active window tracker | IMPLEMENTED | `mini_kio/platform/window_activation.py`; 08-09 added focus/switch + "what's open" |
| 17 — context fusion | IMPLEMENTED | `context_manager.py` structured sections; 08-09 referent sanitization |
| 18 — keyword + structured memory + FQ-05 | IMPLEMENTED | `memory_store.py` multi-field queries + governance metadata |
| 19 — vector support | SKIPPED (optional) | Per historical checkpoint |
| 20 — preference extraction | PARTIAL | Preference signals partially present (context models); no full preference store |
| 21 — reasoner refactor | PARTIAL | `local_reasoner.py` exists; pattern-matching chain retained |
| 22 — alternative generation | NOT STARTED | No pros/cons generation module found |
| 23-27 — proactivity (trigger/suggestion/follow-up/briefing/arbiter) | NOT STARTED | No proactive modules; initiative ROADMAP per CAP.AUTONOMY.001 |
| 28-30 — autonomy (goals/execution loop/safety governor) | NOT STARTED | No goals module; `executive.py`/`orchestrator.py` absent; only `task_engine.py` exists |

**Cross-cutting capability (pre-Slice-9 refinement, verified 2026-08-09): Operational Awareness.** KIO now answers KIO health / status / uptime, system health (CPU/RAM/GPU/storage/battery), component status, and "what's wrong" deterministically from real runtime + system state. Canonical owner: `mini_kio/core/operational_health.py`; `IntentType.OPERATIONAL` + the `_OPERATIONAL_ROUTES` semantic family in `pipeline/__init__.py` (natural + `/health`-style command routing, no LLM fallback); thin PTB wiring in `kio_bot.py` for `/health /status /uptime /system /systemhealth`. Unavailable metrics are reported honestly (never 0); responses carry no implementation tokens. Evidence: 22 targeted tests (`tests/test_operational_health.py`) + 448-test regression gate (2 pre-existing gate2 failures baseline-identical) + live Telegram verification with values cross-checked against psutil/nvidia-smi. Not a roadmap slice — bounded capability refinement; no Slice status changed.

---

### Slice 3 — _route_builtin Decomposition + Routing Pattern Repairs (A.3)
Extract remaining monolithic routing into domain-specific handler modules. Each handler < 200 lines. Test coverage before each extraction.

**Routing repairs included in this slice** (same subsystem, same decomposition pass):
- Fix `exec_patterns` start anchor (`intent_classifier.py:17-25`) so "can you open chrome" is classified EXECUTABLE not INFORMATIONAL
- Add missing media transport commands (pause, resume, stop, next, previous) to exec_patterns
- Expand `is_knowledge_query()` patterns (`retrieval_router.py:131-170`) beyond 12 explicit question forms — "Interstellar cast" must route to knowledge providers
- Fix exact-match confirmation triggers (`conversation_orchestrator.py:41,55,189`) to use substring matching — "yes please" must confirm, not topic-change
- Fix ordinal reference regex coverage in ContinuityEngine — "the first" and "first" both resolve correctly

### Slice 4 — Canonical Provider Abstraction (A.4)
Single `Provider` protocol used by all execution providers. Unify existing ABC + Protocol patterns under one interface. Adapter layer for backward compat.

**Slice 4 Completion (D-08 resolved, 2026-08-09)**:

| Objective | Status | Evidence |
|-----------|--------|----------|
| Single canonical provider interface | **COMPLETE** | `mini_kio/core/provider_contract.py` defines `ExecutionProvider` (ABC) — single contract with `id()`, `capabilities()`, `health()`, `execute()`, `verify()`. `core/provider_registry.py` is the single registry; `register_all_providers()` (called by `runtime.py`) registers all 6 execution providers + MCP servers. |
| Unify ABC + Protocol patterns | **COMPLETE** | The only remaining Protocol-based generic-provider base was the dead top-level `providers/` package (5 files) — zero importers in mini_kio, tests, root files, or config; already deleted once by `7eeb7c8` (July) and re-added as a dead snapshot by `c641220`. Deleted 2026-08-09, restoring the earlier cleanup. `llm/provider_base.py` (`LLMProvider` ABC) is a separate live subsystem (LLM failover chain) and is correctly excluded from the execution-provider contract. |
| Adapter layer for backward compat | **NOT REQUIRED** | Dead package had zero importers — no compat surface to preserve. |

### Slice 5 — Decision Logging (A.5)
Structured log entry for every routing decision: action, intent, confidence, safety state, provider, outcome. Queryable via structured logging.

### Slice 6 — Dead Code Removal + C-09 Unification (A.6, Phase 0)
**Completed (this session)**: `aura/` stub directory deleted. `entity_state_engine.py` (stub with zero usages) deleted. `browser/automation.py` (dead wrappers, zero imports) deleted. Added `resolve_capability(action)` to `routing_utils.py` — unified query across STATIC_ACTION_TABLE and ProviderRegistry, replacing planner.py's inline check that called non-existent `get_provider_registry().resolve()`. 553 gate5 tests pass, 0 new failures. Pre-existing failures (CUA class name, search provider count, ConversationResponse subscriptability) unchanged.

**Slice 6 Completion (all objectives resolved)**:

| Objective | Status | Evidence |
|-----------|--------|----------|
| Dead code removal (aura/, entity_state_engine.py, browser/automation.py) | **COMPLETE** | 3 files deleted, 553 tests pass, 0 regressions |
| `_normalize_public_result` consolidation | **NOT REQUIRED** | browser_operator and app_operator versions have diverged (different failure_class, PID handing, browser-vs-app fields). Merging would add mode parameters. No bug reported. |
| C-09: resolve_capability() unified query | **COMPLETE** | Added to routing_utils.py, planner.py updated. Unifies STATIC_ACTION_TABLE + ProviderRegistry. |
| C-09: CommandRegistry in query | **NOT REQUIRED** | CommandRegistry is a dispatch mechanism for command_router.py, not a capability registry for the execution boundary. Handlers return dict results directly — not called through execute_action(). Adding it would create false positives. |
| C-09: CapabilityRegistry in query | **MOVE TO SLICE 7** | CapabilityRegistry tracks runtime sessions (IS there an active browser session?). Planner validation checks static capability (CAN this action be executed?). Session validation belongs in Slice 7's execution gate protocol, not in planner pre-check. |
| Triple pronoun-resolution merge | **NOT REQUIRED** | ContinuityEngine (general context), MediaReferenceResolver (media context), IntegrationAdapter._try_memory_resolve (memory) serve different domains with different backing stores. No confirmed bug from divergence. Merging would couple unrelated concerns — violates single-responsibility. CANONICAL_ENGINEERING_VALIDATION.md §474 asks "How often does the triple pronoun-resolution divergence actually manifest?" — unanswered, suggesting theoretical concern, not proven bug. |

### Slice 7 — Execution Gate Protocol (B.1)
Add `resolve_prerequisites()` to `execution_boundary.py` between safety check and handler invocation. Define `PrerequisiteGate(action, missing=[], severity=blocking)` dataclass. Wire propagation: execution boundary → runtime → user-facing "I need X" message. On user response → validate → store → retry. **Fail-closed**: missing prerequisite = execution never reaches handler.

**Slice 7 Completion (2026-08-09)**:

| Objective | Status | Evidence |
|-----------|--------|----------|
| `resolve_prerequisites()` in `execution_boundary.py` | **COMPLETE** | Added, wired into `execute_action()` between the safety policy check and handler invocation. Canonical `_PREREQUISITE_RESOLVERS` registry + `register_prerequisite_resolver()`. Action names canonicalized through `_ACTION_MAP` so aliases (`click` → `browser_click`) cannot bypass the gate. |
| `PrerequisiteGate(action, missing=[], severity=blocking)` | **COMPLETE** | Dataclass in `execution_boundary.py` with `blocks` predicate and `to_dict()`; `FAILURE_MISSING_PREREQUISITE` failure class; blocked results carry structured `prerequisite_gate` metadata. |
| Fail-closed | **COMPLETE** | Blocking gate returns `OUTCOME_BLOCKED` before the handler is invoked; handler never runs, no false success. Verified by spy-handler tests. |
| Wire propagation boundary → runtime → user-facing | **COMPLETE** | Result rides the structured execution result; `runtime_response_formatter._format_prerequisite()` renders natural "I need X before I can do that." with no internal ids. |
| Real registered prerequisite | **COMPLETE** | `browser_backend` resolver for all 14 `browser_*` DOM/scripting actions (BrowserRuntime or connected connector satisfies). |
| On user response → validate → store → retry | **DEFERRED to Slice 8-9** | The credential-vault lifecycle (validate/store/retry with user consent) is the Credential Vault slice; Slice 7 delivers the gate mechanism + propagation only, per plan sequencing. |

Tests: `tests/test_slice7_prerequisite_gate.py` (21 tests — construction, resolution, alias canonicalization, fail-closed handler prevention, satisfied-path execution, advisory non-blocking, natural response rendering, no internal leakage).

### Slice 8 — Credential Vault: Core (B.2)
`keyring`-backed credential store. OAuth flow template: auth URL → callback → token exchange → encrypted storage. Schema: provider, credential_type, expires_at, metadata JSON. Only store on explicit user consent.

**CredentialVault API interface** (file: `mini_kio/core/credential_vault.py`):

```python
class CredentialVault:
    def store(provider: str, credential_type: str, secret: str,
              expires_at: datetime | None = None, metadata: dict = {}) -> str
        """Store credential. Returns credential_id. Raises on empty secret.
        Only stores on explicit user consent — caller must set consent=True."""
    def retrieve(credential_id: str) -> Credential | None
        """Returns Credential or None if not found / expired.
        Never returns plaintext to LLM context — only to Execution Gate."""
    def revoke(credential_id: str) -> None
        """Remove credential. Next access will re-prompt."""
    def list() -> list[CredentialMetadata]
        """Returns metadata only (no secrets). For /credentials UI."""
    def has_valid(provider: str, credential_type: str) -> bool
        """Quick check for Execution Gate. Does not expose secret."""
```

Schema: `credential_id UUID, provider str, credential_type str, metadata JSON, expires_at int (unix ts), created_at int, consent_recorded bool`. Token encrypted via `keyring` before SQLite storage. Never in plaintext.

**STATUS — IMPLEMENTED + VERIFIED (2026-08-09).** `mini_kio/core/credential_vault.py` delivers the full Slice 8 core: keyring-backed secret store (`_KeyringBackend` — Windows Credential Manager / macOS Keychain / Linux Secret Service), `credentials` metadata table on the canonical backend engine (`mini_kio/backend/models.py::CredentialRecordModel`), explicit-consent `store(consent=True)`, `OAuthFlowTemplate` (auth URL → callback → token exchange → secure storage), and `credential_missing()` / `register_credential_prerequisite()` wired through the Slice 7 `_PREREQUISITE_RESOLVERS` registry (no parallel credential path). Security invariants enforced: secrets only in keyring (never SQLite/logs/repr/responses), `_sanitize_metadata()` drops secret-shaped metadata keys, `Credential.__repr__` redacts, empty-secret rejected, missing credentials never fabricated. Evidence: 22 targeted tests (`tests/test_slice8_credential_vault.py`) incl. mandatory secret-leak proof (`TEST_SECRET_DO_NOT_LEAK_123` absent from logs/SQLite/repr/responses) + 21 Slice 7 tests + 270 regression tests green; 2 pre-existing gate2 failures baseline-identical. `keyring>=25.0` added to `requirements.txt`. Slice 9 (lifecycle: refresh/revoke UI/expiry at gate) remains OPEN.

### Slice 9 — Credential Vault: Lifecycle (B.2)
Refresh expired tokens. Revoke on user request. List/manage UI. Detect expiry at Execution Gate → request re-auth.

### Slice 10 — Identity Resolver (B.3)
Schema: person_name, service, service_user_id, metadata. Connect to existing `resolvers/identity_resolver.py`. User can add, edit, delete. KIO queries on intent resolution ("tell Aaron" → resolve Aaron → find Telegram/email/WhatsApp contact).

### Slice 11 — Session Continuity: Clean Shutdown (B.4)
Serialize to SQLite on `SIGTERM`/clean shutdown: context buffer, safety state, active goals, recent observations. Restore on startup. Verify: after restart, KIO can answer "what were we doing?"

### Slice 12 — Session Continuity: Crash Recovery (B.4)
Periodic checkpoint during execution (every N actions or M minutes). On unexpected restart, restore from last checkpoint. Verify: kill -9 followed by restart → KIO resumes near where it was.

### Slice 13 — Proactive Event Bus (B.5)
Time-based triggers (cron-like schedule stored in SQLite). State-change triggers (credential added, session restored, build status check). Register/deregister/listen pattern. Event → handler dispatch.

### Slice 14 — Startup Configuration Validation (B.6)
On first launch (and every launch), validate all required configuration before any initialisation. Scan `.env` + OS keychain for: `api_id`, `api_hash` (Telegram), `BOT_TOKEN` (Telegram bot), `GROQ_API_KEY` (primary LLM), `OPENAI_API_KEY`, `DISCORD_TOKEN`, provider keys. If any required credential is missing: **do not crash** — display a structured startup validation report listing every missing variable, explaining why each is required. Prompt user to input missing values. Validate each input (e.g., test API key against service). Offer to persist validated values to `.env` securely. Re-run validation. Only continue startup after validation succeeds. **Reusable pattern**: each provider registers its credential requirements; the validator framework discovers and validates them generically. Build once, reuse for every future provider.

### Slice 15 — Live Integration & Validation Phase (B.7)
After Phase 1 deliverables are complete (Slices 3-14), run a dedicated Live Integration & Validation phase before proceeding to Phase 2. This is NOT a development slice — it is a validation gate. Execute all validation scenarios (see §19 Verification Protocol — Live Integration). Pass milestone M-LIVE before any Phase 2 work begins.

### Slice 16 — Active Window Tracker (C.1)
Poll OS for foreground window title + process name via platform API (`pygetwindow` on Windows, AppKit on macOS, `xdotool`/`wnck` on Linux). Store recent history (timestamped window, duration). No embeddings needed.

### Slice 17 — Context Fusion (C.2)
Merge active window state + conversation history + session state + time context into structured output (not flat text). Replace existing flat text context assembly. Structured sections: `{conversation, desktop, browser, memory, session}`.

### Slice 18 — Keyword + Structured Memory + FQ-05 Governance (M.1)
Upgrade `memory_store.py`: multi-field queries (by time, source, type, keyword). Indexed. Existing key-value API preserved.

**FQ-05 memory governance** (same slice — schema extension): Add per-item retention metadata (retention_policy, stored_at, last_accessed). Implement confidence decay over configurable time window. Provide user-facing inspection/correction/deletion interface (`/memory inspect`, `/memory forget`). Retention is bounded by usefulness, not unconditional — no permanent-by-default storage. Confidence values decay; knowledge may be revised. Sensitive categories gated behind user consent flag per item.

### Slice 19 — Vector Support (M.2)
Local embedding model (`sentence-transformers/all-MiniLM-L6-v2` or smaller). Similarity search via numpy dot-product. Optional backend — keyword retrieval remains primary. One work item, not a foundation stream.

### Slice 20 — Preference Extraction (M.3)
Detect preference signals in conversation (explicit: "I prefer...", implicit: repeated patterns). Store with confidence score. Surface to response pipeline. Influence suggestions, style, tool selection.

### Slice 21 — Reasoner Refactor (R.1)
Replace pattern-matching chain in `local_reasoner.py` with actual inference step. Keep pattern matching as fallback. Single inference step, not a reasoning engine abstraction with multiple backends — YAGNI until a second backend is proven necessary.

### Slice 22 — Alternative Generation (R.2)
Structured pros/cons output for decisions. Uncertainty quantification (confidence score per conclusion). Contradiction detection across memory + context + new information.

### Slice 23 — Proactivity: Trigger Model (P.1)
Context + preferences + Goal Manager active goals → opportunity detection. Time-based (morning, idle threshold). State-based (build status change, new notification). Event-based (scheduled trigger).

### Slice 24 — Proactivity: Suggestion Engine (P.2)
Generate proactive suggestions ranked by relevance + confidence. Template-based + learned preference weighting.

### Slice 25 — Proactivity: Follow-Up Tracker (P.3)
Check Goal Manager for stalled goals. "You were working on X. Would you like to continue?" Configurable interval.

### Slice 26 — Proactivity: Morning Briefing (P.4)
Multi-source summary: build status, notifications, pending goals, upcoming events, recommended next work. User-configurable content and frequency.

### Slice 27 — Proactivity: Initiative Arbiter (P.5)
When to act vs when to ask vs when to stay silent. Confidence threshold per trigger type. User tuning: off/low/medium/high. Emergency suppression (safety state < NORMAL).

### Slice 28 — Autonomy: Goal Registry (A.1)
User-defined goals ("keep my desktop organised") + Goal Manager-detected goals. Priority, status, success criteria, lifespan. Persisted across sessions.

### Slice 29 — Autonomy: Execution Loop (A.2)
Select goal → plan → execute → verify → reflect → iterate. Read-only actions first (search, read, summarize). Loop runs with user-configurable approval requirements per action category.

### Slice 30 — Autonomy: Safety Governor (A.3)
Hard boundaries: no destructive system actions, no spending, no data deletion, no messaging without confirmation. Full audit trail. Always overrideable by user. Safety governor is absolute — no layer can bypass it.

---

## 8. Dependency Graph

```
Stream A ──────────────────────────────────────────┐
(A.3 → A.4 → A.5 → A.6)                            │
                                                    ▼
Stream B ───────────────────────────────────▶ Phase 1 · Live Validation
(B.1 → B.2 → B.3 → B.4 → B.6)   (Slices 3-15: reliable foundation,
                                                     │    credentials, identity,
                                                     ▼    session continuity, config)
                                              Phase 2
                                   (Slices 16-22: context, memory,
                                                     │    reasoning)
                                                     ▼
                                              Phase 3
                                   (Slices 23-27: proactivity,
                                                     │    suggestions, briefing)
                                                     ▼
                                              Phase 4
                                        (Slices 28-30: autonomy,
                                                     goal pursuit)
```

**Key dependencies**:
- Slice 7 (Execution Gate) is the most critical dependency — it gates everything that requires user interaction (credentials, permissions, confirmations).
- Phase 2 starts after Phase 1 because context + memory depend on session continuity + identity + credentials.
- Slice 14 (Startup Validation) must consume B.2 (Credential Vault) — the validator framework reuses the vault's credential schema.
- B.7 (Slice 15, Live Validation) is a mandatory gate before Phase 2. No Phase 2 work starts until M-LIVE passes.
- Vector support (Slice 19) is optional. Keyword retrieval covers 80% of recall needs. Skip Slice 19 if profiling doesn't show a recall quality gap.
- Autonomy (Phase 4) is the only phase that can be deferred indefinitely without degrading core KIO functionality.

---

## 9. Execution Architecture

### Current state (correct, preserved)

`execution_boundary.py` implements: `classify_action()` → `check_safety_policy()` → RAM check → handler dispatch → result normalization.

### Execution Gate addition (Slice 7)

The pipeline becomes (resolve_prerequisites BEFORE safety check — two independent gates, one pipeline):

```
classify_action(action) → category
resolve_prerequisites(action, target, context) → gate/allowed   ← NEW
check_safety_policy(action, target, rt) → permitted/reason
check_ram_budget(descriptor) → ok/denied
execute_handler(handler, target) → result
verify_result(action, result) → verified/failed                ← NEW
```

`resolve_prerequisites()` queries the `PrerequisiteRegistry` (generic key-value store):

- Each action can register prerequisites by name at action registration time.
- Prerequisite types: `credential`, `permission`, `confirmation`, `identity`, `service_available`, `tool_available`, `network_available`, `file_exists`.
- If prerequisite is missing → return `PrerequisiteGate(action, missing=[{type, description, severity}])`.
- If all prerequisites satisfied → return `PrerequisiteGate(allowed=True)`.

### Gate propagation

```
Execution Gate blocks → runtime receives PrerequisiteGate
                      → runtime formats: "I need X to do Y."
                      → user responds with information
                      → runtime validates: is this credential valid?
                      → on valid: store in PrerequisiteRegistry
                      → retry original action
                      → on invalid: "That didn't work. Please check and try again."
                      → on reject: "Cancelled. Let me know if you change your mind."
```

**Fail-closed**: If `resolve_prerequisites` cannot determine whether a prerequisite is satisfied, it assumes missing. No execution path reaches the handler without passing the gate.

**No credential fabrication**: The LLM never sees raw credential values. The Execution Gate blocks before the LLM prompt is constructed for execution. The gate is deterministic Python code, not an LLM prompt.

---

## 10. Identity Architecture

### Does KIO need an identity model?

Yes, but a minimal one. The acceptance scenarios ("Tell Aaron", "Email my professor") require resolving identity across services. The minimum model is:

**People**: `{name, aliases[], contacts[{service, service_user_id, label}], metadata{}}`
**Services**: `{service_name, auth_required, credential_ref, provider}`
**Preferences**: `{person_id, service_id, preference_weight}`

### Where it lives

New tables in the existing SQLite backend (`mini_kio/backend/`). Connected to existing `resolvers/identity_resolver.py`. No new package. No graph database. No elaborate ontology.

### What KIO learns

| Concept | Stored As | Learned How |
|---------|-----------|-------------|
| People | `identity_person` table | User adds, KIO detects from conversation |
| Contacts | `identity_contact` table | User adds, KIO detects from message history |
| Service preferences | `identity_preference` table | Implicit (user picks WhatsApp over Telegram for Aaron twice → stores preference) |
| User facts | `memory_store` | Preference extraction (Slice 20) |
| Application registry | `APP_REGISTRY` (existing) | Already exists |

### Key design decision

No universal entity resolution system. KIO doesn't need to know that "John Smith" and "Dr. Smith" are the same person — it needs to know that "Aaron" maps to `{telegram: @aaron, email: aaron@example.com}`. The model is a contact book, not a knowledge graph.

---

## 11. Capability Architecture

### What exists (correct, preserved)

- `provider_registry.py` — maps action names to execution providers
- `capability_registry.py` — dynamic capability discovery and query
- `command_registry.py` — replaces the old if/elif chain
- 15 execution providers (browser, mcp, terminal, filesystem, etc.)

### What changes

Capabilities register their prerequisites at registration time:

```python
registry.register(
    name="send_message",
    provider=telegram_provider,
    prerequisites=["credential:telegram_auth", "identity:recipient"],
    safety_category="messaging",
)
```

The Execution Gate uses this registration to check prerequisites before executing any capability. No special-case credential checking in individual providers.

---

## 12. Integration & MCP Architecture

KIO has two integration layers: the **MCP Runtime** (subprocess-based tool servers) and the **Provider Registry** (in-process execution providers). Both are independent of OpenCode's MCP — KIO implements its own transport, lifecycle, and discovery.

### 12a. MCP Runtime (`mini_kio/runtime/mcp_runtime/`)

KIO's MCP runtime is its own async, crash-isolated, production-grade design — **not** a copy of OpenCode's MCP or any external framework.

**Transport**: Subprocess stdio. Each server runs as a child process (`asyncio.create_subprocess_exec`). JSON-RPC 2.0 with newline-delimited JSON on stdin/stdout.

**Lifecycle per server**:
1. `add_server(config)` → spawns subprocess → MCP handshake (`initialize` → `tools/list`) → registers discovered tools in `ToolRegistry`
2. Running state: health monitor polls every 15s → detects `CRASHED` transitions → auto-restart with exponential backoff (2^n s, max `max_restart_attempts`)
3. `remove_server()` → disconnect → cleanup tools → clear registry entries

**Tool discovery**: After connect, server sends `tools/list` response → each tool is stored as `ToolDescriptor` keyed by `server_id::tool_name`. Type-safe JSON-Schema-subset validation on call arguments (required fields, types, enums).

**Execution flow**:
```
call_tool(tool_name, arguments, server_id?)
  → ToolRegistry lookup by server_id::tool_name
  → argument validation
  → retry (exponential backoff, configurable)
  → MCPServerConnection.call_tool() → tools/call JSON-RPC request
  → timeout enforcement
  → ToolCallResult
```

**Configuration**: Environment-driven (`KIO_MCP_SERVERS` JSON env var) + recursive file discovery (`mcp.{json,yaml,toml}` from CWD down). Example env config:
```json
[{"server_id": "my-server", "command": "python", "args": ["-m", "my_mcp_server"]}]
```

**8 built-in server types**: filesystem (6 tools), git (6), terminal (3), sqlite (4), docker (11), github (9), postgres (4), redis (16). Auto-registered on availability. ~59 total tools.

**Two historical implementations**:
- `mini_kio/runtime/mcp_runtime/` — **active, modern, async**. Crash-isolated, health-monitored, auto-recovering. Wired to `CapabilityRegistry` at bootstrap. Used via `execute_mcp_tool()` in `execution_boundary.py`.
- `mini_kio/core/mcp/` — **legacy, thread-based**. Provider-system integrated but not actively called in production flows. Preserved for backward compatibility.

**MCP position**: MCP is a provider integration protocol, not part of the core execution architecture. The Execution Gate applies to MCP tools the same way as any action — prerequisites checked at the gate, not inside the tool. No special MCP credential handling. Crash isolation means one server crashing never affects other servers or the runtime.

**ponytail**: Legacy `core/mcp/` layer retained for compatibility. Remove when no external code references it.

**Legacy tracking**: Add a grep-based CI check (`scripts/check-legacy-mcp-refs.sh`) that fails if any import of `mini_kio.core.mcp` exists outside of `tests/` or a migration shim. Run after every Phase 1 slice. Target: zero legacy references by M-LIVE (Slice 15). If any remain, the legacy `core/mcp/` directory is preserved but frozen — no new features, no bugfixes, only removal commits.

### 12b. Current Integration State (preserved)

- **Browser**: Playwright-based. Production-grade runtime in `browser_runtime/`.
- **LLM**: Multi-provider gateway in `mini_kio/llm/llm_gateway.py`. Providers: gemini, ollama, huggingface, freellm, mock. Fallback chain.
- **Platforms**: Telegram (production), Discord transport, CLI.

### 12c. Adding a New Integration

Add a new provider implementing the existing `Provider` protocol. Register actions and prerequisites with registries. The Execution Gate, safety checks, agent layer, and result normalization work without modification.

---

## 13. Memory Architecture

### Current state

`memory_store.py` — key-value store with basic persistence. PatternMemoryExtractor for fact extraction.

### Phase 2 upgrades

1. **Slice 18**: Add multi-field query (by time, source, type, keyword). Indexed SQLite queries.
2. **Slice 19**: Add vector similarity search as optional backend. Embedding model + numpy dot-product. No Chroma/Faiss dependency. Swap to a dedicated vector DB only when recall quality with numpy is demonstrably insufficient.
3. **Slice 20**: Preference extraction — detect explicit and implicit preference signals, store with confidence, surface to response pipeline.

### Memory types

| Type | Storage | Retrieval | Used By |
|------|---------|-----------|---------|
| Episodic | SQLite + optional vector | Keyword + time range | Context assembly |
| Factual | SQLite | Exact match + keyword | Reasoning |
| Preference | SQLite | Keyword | Response pipeline, proactivity |
| Procedural | Code (not data) | N/A | Execution |

No procedural memory type. Procedural knowledge is code, not data. YAGNI.

---

## 14. Runtime Architecture

### Current state (correct, preserved)

`KioRuntime` singleton in `mini_kio/core/runtime.py` (1643 lines). Ownership: dispatch authority, safety state machine, resource guarding, observer management, channel dispatch. No changes needed.

### Session continuity (Slice 11-12)

Serialize on clean shutdown: `runtime.to_snapshot()` → SQLite `runtime_snapshots` table.
Restore on startup: `runtime.from_snapshot()` → rehydrate context buffer, safety state, active goals.
Periodic checkpoint: `runtime.checkpoint()` every N dispatches → overwrite last checkpoint.
On unexpected restart: restore from last checkpoint.

### No runtime decomposition

The singleton pattern is correct for a dispatch authority. Decomposing it into microservices would add latency and failure modes with zero user-facing benefit.

---

## 15. Safety Architecture

### Current state (correct, preserved)

`execution_boundary.py` safety gateway:
- Safety states: NORMAL → DEGRADED → EMERGENCY → LOCKDOWN
- Per-state action category allow/block rules
- RAM budget enforcement via `ResourceGuard`
- Blocked destructive actions during stabilization
- Verification probes (process liveness, exit code)

### Safety + Execution Gate interaction

The Execution Gate (`resolve_prerequisites`) runs BEFORE the safety check. Order of operations:

1. `classify_action` → category
2. `resolve_prerequisites` → gate check (missing info? block)
3. `check_safety_policy` → safety state check
4. RAM check → resource budget check
5. `execute_handler` → run action
6. verification → verify result

This ordering ensures: no action reaches the safety check without first passing prerequisite resolution. Safety check is the second gate. Two independent gates, one pipeline.

### Safety boundaries for proactivity + autonomy

- Proactivity (Phase 3): Read-only suggestions only. No action without user confirmation.
- Autonomy (Phase 4): Read-only actions (search, read, summarize) may execute autonomously. Write actions (send message, modify file, execute tool) require user confirmation. Confirmation threshold is configurable but defaults to "always ask."
- Safety governor (Slice 30): Absolute hard boundaries. No code path can bypass them. Every autonomous action produces an audit trail.

---

## 16. Prerequisite Resolution Architecture

This is the Execution Gate — the single most important architectural addition.

### Core concept

Every action may have prerequisites. Prerequisites are conditions that must be satisfied before the action executes. If unsatisfied, execution stops, the user is asked, and execution resumes only after the prerequisite is satisfied.

### Prerequisite types

| Type | Example | Storage | Validated By |
|------|---------|---------|--------------|
| `credential` | Email password, API token | Keychain + SQLite metadata | Test: try authentication |
| `permission` | "Can I access your email?" | User consent record | User said yes |
| `confirmation` | "Send this message?" | User consent record | User confirmed |
| `identity` | "Who is Aaron?" | Identity Resolver | Identity lookup succeeds |
| `service_available` | "Is Telegram connected?" | Service health check | Ping service |
| `tool_available` | "Is the browser running?" | Browser runtime health | Health check |
| `network_available` | "Is there internet?" | Network check | Ping host |
| `file_exists` | /path/to/file | Filesystem check | os.path.exists |

### Architecture

**PrerequisiteRegistry**: Lives in `mini_kio/core/prerequisite_registry.py` (new file, not part of any existing registry). Owned by Execution Boundary. Uses a dict-backed store with check functions registered per action.

Interface:

```python
class PrerequisiteRegistry:
    @dataclass
    class Prereg:
        prereq_type: str    # "credential" | "permission" | "confirmation" | "identity" | etc.
        description: str
        severity: str       # "blocking" | "warning"
        check_fn: Callable  # (action, context) -> (satisfied: bool, details: str)

    def register(action: str, prereq: Prereg) -> None
    def get_prerequisites(action: str) -> list[Prereg]
    def check(action: str, context: Context) -> PrerequisiteGate
    def resolve(action: str, context: Context) -> PrerequisiteGate
```

At registration time:
```python
registry.register("send_email", Prereg(
    prereq_type="credential",
    description="Email account credentials",
    severity="blocking",
    check_fn=check_email_creds,
))
registry.register("send_email", Prereg(
    prereq_type="identity",
    description="Recipient contact info",
    severity="blocking",
    check_fn=check_recipient_identity,
))
```

At execution time (in `resolve_prerequisites`):
```python
for prereq in registry.get_prerequisites(action):
    ok, detail = prereq.check_fn(action, context)
    if not ok:
        return PrerequisiteGate(blocked=True, missing=[prereq])
return PrerequisiteGate(allowed=True)
```

**Result caching**: Once a prerequisite is satisfied, it's cached for the session (credential remains valid until expiry, identity resolution stays until changed). Cross-session caching handled by Credential Vault + Identity Resolver persistence.

**Fail-closed default**: The default for any unrecognized prerequisite type is BLOCKED. Only explicitly registered check functions can unblock.

---

## 17. Acceptance Criteria

### Scenario A: Email professor (authenticated service)
> User: "Email my professor."
> KIO: [no email credentials] → "I need your email account. Please authenticate."
> User authenticates.
> KIO: [no professor contact] → "What's your professor's email address?"
> User provides.
> KIO drafts email, asks confirmation, sends.
> Pass: No credential fabrication. No silent failure. Every missing prerequisite surfaced to user.

### Scenario B: Cross-provider messaging
> User: "Tell Aaron I'll be there by 5."
> KIO: resolves Aaron → finds Telegram + WhatsApp contacts.
> KIO: "I can message Aaron via Telegram or WhatsApp. Which should I use?"
> User picks.
> Message sent.
> Pass: Identity resolution works. Provider selection works. Preference stored for future.

### Scenario C: Session recovery
> User: "Continue KIO." [after restart]
> KIO: restores session from checkpoint.
> KIO: "You were reviewing the architectural plan. Build was green. 2 unread messages."
> Pass: Session continuity. No user re-explanation needed.

### Scenario D: Capability chaining
> User: "When's Avengers Doomsday?"
> KIO answers.
> "Play the trailer."
> KIO plays trailer via preferred video provider.
> Pass: Intent carries across invocations. Capability discovery works without re-prompting.

### Scenario E: No credential fabrication (ALL paths)
> Any action requiring auth where no credential is stored.
> KIO stops, asks, never guesses.
> Verified by: inject test with empty credential vault → every action returns PrerequisiteGate.

### Scenario F: Proactive morning briefing
> Morning arrives (time trigger in Event Bus).
> KIO: "Morning. Build: green. 1 PR needs review. Your first meeting is at 10am."
> User configures content and timing.
> Pass: Proactivity works. User can disable.

### Scenario G: Goal pursuit
> User: "Research quantum computing trends and summarize by Friday."
> KIO: creates goal. Returns "I'll get started and report back."
> KIO researches periodically. Reports progress. Delivers summary by Friday.
> Pass: Autonomous goal pursuit within safety bounds.

### Scenario H: Startup validation with missing credentials
> User starts KIO with empty `.env`.
> KIO: displays structured startup report: "Missing: api_id (Telegram authentication required), BOT_TOKEN (Telegram bot registration required), GROQ_API_KEY (primary LLM provider)." Prompts for each.
> User inputs valid credentials.
> KIO validates (test API call), persists to `.env`, re-runs validation.
> KIO starts successfully.
> Pass: No crash. No partial initialisation. Clear explanation. Secure persistence.

### Scenario I: Production health endpoint
> External monitor queries KIO health endpoint.
> Response: `{"status": "ready", "safety_state": "NORMAL", "health_score": 100, "uptime": "14s", "providers": {"groq": "ok", "telegram": "ok"}, "browser": {"state": "RUNNING", "uptime": "10s"}}`.
> Pass: Unified health endpoint. Machine-readable. Covers all subsystems.

---

## 18. Milestones

| Milestone | Slices | Verification | Target Behavior |
|-----------|--------|-------------|-----------------|
| **M0: Phase 0 Cleanup** | 6 | 206+ tests pass after removing 150 files. Zero dangling references. | Clean codebase with no stubs, dead code, or unused adapters. |
| **M1: Prerequisite Gate active** | 7 | All 5 critical paths tested with empty credential vault → all blocked with structured message | KIO never fabricates credentials |
| **M2: Credential Vault shipping** | 8-9 | OAuth flow works for at least one provider. Token stored. Token reused on subsequent calls. | Users can authenticate once and KIO remembers |
| **M3: Identity Resolution** | 10 | "Tell Aaron" resolves to correct contact across at least 2 services | Cross-platform messaging works |
| **M4: Session Survival** | 11-12 | Runtime restart preserves context, safety state, active goals | "Continue KIO" works without re-explanation |
| **M5: Startup Validation** | 14 | `.env` with missing credentials → structured report + prompt. All valid → clean startup. | KIO never crashes on missing config |
| **M-LIVE: Live Integration Pass** | 15 | All 12 validation domains pass (provider, browser, memory, workflow, Telegram, Discord, voice, agent orchestration, MCP, stress, recovery, E2E) | System validated across all interfaces |
| **M6: Morning Briefing** | 13, 23-26 | Time-triggered multi-source summary delivered | Proactive behavior starts |
| **M7: Memory Influences Behaviour** | 18, 20 | After storing "user prefers dark mode", KIO suggests dark mode | Memory not decoration |
| **M8: Read-Only Autonomy** | 28-29 | KIO researches and summarizes without supervision | Autonomous goal pursuit begins |
| **M9: Full Autonomy with Guardrails** | 30 | KIO acts independently within safety boundaries. Cannot bypass governor. | Companion behaviour achieved |

### Milestone dependency graph

```
M0 ← Slice 6
M1 ← Slice 7
M2 ← Slices 8-9
M3 ← Slice 10
M4 ← Slices 11-12
M5 ← Slice 14
M-LIVE ← Slices 3-15 (depends on M1-M5)
  │
  ├── M6 ← Slices 13, 23-26 (depends on M-LIVE)
  ├── M7 ← Slices 18, 20 (depends on M-LIVE)
  └── M8 ← Slices 28-29 (depends on M6, M7)
        └── M9 ← Slice 30 (depends on M8)
```

Key: M-LIVE is the hard gate between Phase 1 and Phase 2. No Phase 2 milestone (M6, M7) starts before M-LIVE passes. M8-M9 (Phase 4) depend on Phase 2-3 foundations.

---

## 19. Verification Protocol

Every major slice, work item, milestone, and phase completion requires live end-to-end verification through actual user-facing interfaces. Automated tests alone are insufficient — they confirm the code works, not that the behaviour is correct from the user's perspective.

### Verification workflow (embedded in every slice)

After the last commit of every slice, before marking complete:

1. **Run automated tests** — full test suite passes. No regressions.
2. **Live verification** — execute the scenario through the actual chat interface (Telegram, Discord, or CLI). Observe behaviour.
3. **Failure injection** — test the negative path: missing credential, wrong input, network down. Confirm graceful handling, not crashes.
4. **Log review** — check structured logs for the slice's key decisions. Confirm traceability.
5. **Runtime diagnostics** — confirm no RAM budget exceeded, no unhandled exceptions, safety state correct.
6. **Regression check** — run the top 3 acceptance scenarios from the previous slice. Confirm they still work.

If any step fails, the slice is not complete. Fix first, verify second.

### Per-milestone verification requirements

#### M1: Prerequisite Gate (Slice 7)

| Activity | Detail |
|----------|--------|
| **Manual test**: Telegram | Send "play Starboy" with no music service credentials. KIO responds "I need access to a music service. Please authenticate." |
| **Manual test**: Telegram | Send "email my professor" with no email credentials. KIO responds with credential request, not a fabricated "email sent." |
| **Manual test**: CLI | Same scenarios via `cua_cli/main.py`. |
| **Automated** | Unit test: `resolve_prerequisites` with empty vault → returns `PrerequisiteGate(blocked=True, missing=[...])`. |
| **Automated** | Unit test: `resolve_prerequisites` with populated vault → returns `PrerequisiteGate(allowed=True)`. |
| **Automated** | Unit test: expired credential → `PrerequisiteGate(blocked=True, missing=["credential:expired"])`. |
| **Failure injection** | Corrupt vault entry → gate blocks with explanation, not crash. |
| **Log review** | Every gate block produces a structured log entry: `exec_prerequisite_blocked {action, missing, severity}`. |
| **Regression** | All existing Slices 1-2 acceptance scenarios still work unchanged. |

#### M2: Credential Vault (Slices 8-9)

| Activity | Detail |
|----------|--------|
| **Manual test**: Telegram | Authenticate with email OAuth. KIO stores token. Subsequent "email my professor" skips auth. |
| **Manual test**: Telegram | "Revoke my email access." Token removed from vault. Next email request re-prompts for auth. |
| **Automated** | Unit test: `CredentialVault.store()` → `CredentialVault.retrieve()` round-trip with encrypted token. |
| **Automated** | Unit test: expired token → `retrieve()` returns `None` + expiry reason. |
| **Failure injection** | OS keychain unavailable → fallback to encrypted SQLite. Log warning. No crash. |
| **Log review** | `credential_stored`, `credential_retrieved`, `credential_expired` events logged. |

#### M3: Identity Resolution (Slice 10)

| Activity | Detail |
|----------|--------|
| **Manual test**: Telegram | "Tell Aaron I'll be there by 5." KIO resolves Aaron → finds Telegram contact → sends message → asks confirmation first time. |
| **Manual test**: Telegram | Same command again. KIO uses stored preference, skips provider selection. |
| **Automated** | Unit test: `identity_resolver.resolve("Aaron")` returns correct contact record. |
| **Automated** | Unit test: `identity_resolver.resolve("UnknownPerson")` returns empty result. |
| **Log review** | `identity_resolved`, `identity_ambiguous`, `identity_not_found` events logged. |

#### M4: Session Continuity (Slices 11-12)

| Activity | Detail |
|----------|--------|
| **Manual test**: Telegram | Start conversation. Kill process. Restart. Send "continue." KIO recovers context, safety state, active goals. |
| **Manual test**: Telegram | Same with `SIGKILL` (no clean shutdown). KIO recovers from last checkpoint. |
| **Automated** | Unit test: `runtime.to_snapshot()` → `runtime.from_snapshot()` round-trip preserves all fields. |
| **Automated** | Integration test: serialize, kill, restart, same query returns same result. |
| **Failure injection** | Corrupt checkpoint file → KIO starts fresh with "I lost my last session due to a crash" message. |
| **Log review** | `session_checkpoint_created`, `session_checkpoint_restored`, `session_checkpoint_corrupt` events logged. |

#### M5: Startup Validation (Slice 14)

| Activity | Detail |
|----------|--------|
| **Manual test**: CLI | Start KIO with empty `.env`. KIO displays structured validation report with all missing credentials listed. |
| **Manual test**: CLI | Input valid credentials. KIO validates (test API call), persists to `.env`, re-runs validation, starts cleanly. |
| **Manual test**: CLI | Input invalid credential. KIO reports failure, re-prompts. |
| **Automated** | Unit test: validator framework discovers all registered credential requirements. |
| **Automated** | Unit test: valid credential → persistence → re-validation succeeds. |
| **Automated** | Unit test: invalid credential → re-prompt with error message. |
| **Failure injection** | Corrupt `.env` → validator detects and reports parse error. |
| **Log review** | `config_validation_passed`, `config_missing_key`, `config_validation_failed` events logged. |

#### M6: Morning Briefing (Slices 13, 23-26)

| Activity | Detail |
|----------|--------|
| **Manual test**: Telegram | Set briefing time to 1 minute from now. Wait. KIO delivers multi-source summary unprompted. |
| **Manual test**: CLI | Same via CLI invocation. |
| **Automated** | Unit test: `EventBus.trigger_time_based()` fires correct handlers. |
| **Automated** | Unit test: briefing content includes at least 2 configured sources (build status, goals, notifications). |
| **Failure injection** | All sources unavailable → KIO says "No updates available" instead of failing. |
| **Log review** | `proactive_briefing_delivered`, `proactive_briefing_source_unavailable` events logged. |

#### M7: Memory Influences Behaviour (Slices 18, 20)

| Activity | Detail |
|----------|--------|
| **Manual test**: Telegram | "I prefer dark mode." Next unrelated query: KIO's response references dark mode preference. |
| **Manual test**: Telegram | After 5 conversations about Python, KIO references Python knowledge without re-prompting. |
| **Automated** | Unit test: store preference "dark mode" → query memory → preference returned in results. |
| **Automated** | Unit test: memory consolidation preserves key facts, prunes low-confidence noise. |
| **Log review** | `preference_stored`, `memory_consolidation_complete` events logged. |

#### M8: Read-Only Autonomy (Slices 28-29)

| Activity | Detail |
|----------|--------|
| **Manual test**: Telegram | "Research quantum computing trends and summarize by Friday." KIO acknowledges goal, returns periodic updates. |
| **Manual test**: Telegram | "Stop researching." KIO cancels goal. |
| **Automated** | Unit test: goal registry stores, lists, archives goals. |
| **Automated** | Integration test: read-only autonomous loop executes N iterations without write actions. |
| **Failure injection** | Safety state changes to EMERGENCY → autonomous loop suspends. Resumes when state normalizes. |
| **Log review** | `goal_created`, `goal_progress`, `goal_completed`, `goal_cancelled`, `goal_blocked` events logged. |

#### M9: Full Autonomy (Slice 30)

| Activity | Detail |
|----------|--------|
| **Manual test**: Telegram | Goal that requires a write action (send message, create file). KIO asks for confirmation before executing. |
| **Manual test**: Telegram | Goal that requires destructive action (delete file, modify system). KIO blocks with explanation. |
| **Automated** | Unit test: safety governor blocks all destructive action categories regardless of goal priority. |
| **Automated** | Integration test: every autonomous action produces explainability trace. |
| **Failure injection** | Simulate safety governor override attempt → governor rejects, logged as security event. |
| **Log review** | `safety_governor_blocked`, `action_confirmation_requested`, `action_confirmed`, `action_rejected` events logged. |

### Live Integration & Validation (Slice 15, B.7)

After Phase 1 completion and before Phase 2 begins, execute this mandatory validation gate. **M-LIVE must pass** before any Phase 2 slice starts.

| Domain | Validation | Method | Evidence |
|--------|-----------|--------|----------|
| **Provider validation** | All 9+ LLM providers respond correctly. Fallback chain works end-to-end. | Automated health check + manual test per provider | Log output for each provider call |
| **Telegram validation** | Full conversation lifecycle: start, respond, continue, error. Media commands work. | Manual via Telegram client | Screenshot + log trace |
| **Discord validation** | Connection, message handling, command routing. | Manual via Discord client | Screenshot + log trace |
| **Browser validation** | Goto, click, scroll, fill, type, screenshot, extract. Crash recovery. | Playwright MCP automated + manual | Test report + screenshot |
| **Memory validation** | Store, retrieve, update, delete across memory types (episodic, factual, preference). | Automated test suite | Test pass report |
| **Workflow validation** | Multi-step execution chains (2-5 steps). Continuity across steps. | Automated + manual | Execution traces |
| **Voice validation** | Voice input → text → execution → response. | Manual | Audio + log trace |
| **Agent orchestration validation** | Agency Agents dispatch, coordination, result collection. | Automated test suite | Agent execution trace |
| **MCP validation** | Tool registration, invocation, error propagation, server health. | Automated + manual | MCP health snapshot |
| **Stress testing** | Sustained conversation (50+ turns). Multi-step under load. RAM budget enforcement. | Automated script | RAM profile, health score over time |
| **Recovery testing** | SIGTERM → clean restart preserves state. SIGKILL → checkpoint recovery. Provider failover. | Automated script | Recovery logs, restored state |
| **End-to-end validation** | Full acceptance scenarios A-I executed through actual Telegram/Discord client. | Manual walkthrough | Video or written evidence per scenario |

**Pass criteria**: All 12 domains pass. Zero critical issues. All regressions clean. Logs reviewed for each domain.

**Remediation if M-LIVE fails**:
1. Identify failing domain(s) — failed domains are blocking, passing domains are preserved.
2. Create targeted fix slices (1 slice per domain, max 5 days per slice).
3. Re-run only the failed domain validation + regression check on previously passing domains.
4. Repeat until all 12 domains pass.
5. If a domain fails 3 consecutive remediation attempts: escalate to architecture review — the domain may require a design change, not a fix. Document as architectural debt.
6. No Phase 2 work starts until M-LIVE passes. This gate is absolute.

**ponytail**: M-LIVE is manual + automated scripts. Formalize into CI pipeline (Slice 31, post-Phase 1) when release frequency exceeds 1/week.

### Phase completion verification

When all slices in a phase are done, run a phase-level integration test:

| Phase | Integration Test |
|-------|-----------------|
| **Phase 1 end** | "Continue KIO" after restart → recovers state. "Email X" with stored credentials → works. "Email X" with no credentials → gate blocks, asks, stores, retries. |
| **Phase 2 end** | "What app am I in?" → correct answer. "Remember that I prefer dark mode" → subsequent responses reference it. Unprompted event bus triggers suggestion. |
| **Phase 3 end** | Morning briefing delivers. Unprompted suggestion is appropriate. User disables proactivity → no suggestions. |
| **Phase 4 end** | "Research X by Friday" → autonomous execution, progress updates, final summary. Safety governor blocks destructive actions. |

All automated tests pass. All manual scenarios demonstrated. All logs reviewed. All regressions clean.

---

## 20. Migration Notes

### From the old blueprint

1. **Foundation Stream B (vectors) is removed** as a stream. The single vector work item moves to Slice 19 under Phase 2 Memory. Existing vector work in progress (if any) is preserved but does not block any other slice.
2. **Foundation Stream C (state persistence) is absorbed** into Stream B Work Item 4 (Slices 11-12). Scope expanded from serialization-only to full session continuity.
3. **Cognitive Layers 1-9 are retired** as a concept. Replaced by 4 Implementation Phases. No code changes needed — the old plan was never implemented beyond planning.
4. **"Gates" terminology retired** with the convergence planning phase. Use "Slices" and "Milestones."
5. **Existing completed work** (Slices 1-2, Phase 0 cleanup, Gates C-1 through C-4b, Production Acceptance Report) remains valid. The test suite continues to pass. No contracts or interfaces are modified.
6. **Phase 0 (dead code removal)** is complete. 150 files removed (browser stubs, governance stubs, 4 unused adapter packages, providers/ package, 45 temp/scratch files, stale .pyc caches). All 206+ tests pass. Remaining cleanup packaged into Slice 6.
7. **Startup Configuration Validation** (Slice 14) is a new work item. It is NOT a prerequisite for Phase 1 — it is part of Phase 1 delivery. Build after Credential Vault.
8. **Live Integration & Validation** (Slice 15) is a mandatory validation gate after Phase 1. Required before Phase 2. Not a development task — it is a verification gate.

### Backward compatibility

- All existing tests pass without modification.
- All existing interfaces unchanged.
- All database schemas unchanged (new tables are additive).
- `KioResponse` format unchanged.
- No contract violations.

---

## 21. Final Development Roadmap

### From Slice 3 onward

```
Phase 0: Dead code cleanup                      │ Completed
────────────────────────────────────────────────┤
Slice  3: _route_builtin decomposition          │ Stream A · Phase 1 · Committed
Slice  4: Canonical provider abstraction         │ Stream A · Phase 1 · Committed
Slice  5: Decision logging                       │ Stream A · Phase 1 · Committed
Slice  6: Dead code removal (remaining)          │ Stream A · Phase 1
Slice  7: Execution Gate protocol                │ Stream B · Phase 1
Slice  8: Credential Vault: core                 │ Stream B · Phase 1
Slice  9: Credential Vault: lifecycle            │ Stream B · Phase 1
Slice 10: Identity Resolver                      │ Stream B · Phase 1
Slice 11: Session Continuity: clean shutdown     │ Stream B · Phase 1
Slice 12: Session Continuity: crash recovery     │ Stream B · Phase 1
Slice 13: Proactive Event Bus                    │ Stream B · Phase 1
Slice 14: Startup Configuration Validation       │ Stream B · Phase 1
Slice 15: Live Integration & Validation Gate     │ Stream B · Phase 1
────────────────────────────────────────────────┤
Slice 16: Active window tracker                  │ Phase 2
Slice 17: Context fusion                         │ Phase 2
Slice 18: Keyword + structured memory            │ Phase 2
Slice 19: Vector support (optional)              │ Phase 2 · SKIP if keyword sufficient
Slice 20: Preference extraction                  │ Phase 2
Slice 21: Reasoner refactor                      │ Phase 2
Slice 22: Alternative generation                 │ Phase 2
────────────────────────────────────────────────┤
Slice 23: Proactivity: trigger model             │ Phase 3
Slice 24: Proactivity: suggestion engine         │ Phase 3
Slice 25: Proactivity: follow-up tracker         │ Phase 3
Slice 26: Proactivity: morning briefing          │ Phase 3
Slice 27: Proactivity: initiative arbiter        │ Phase 3
────────────────────────────────────────────────┤
Slice 28: Autonomy: goal registry                │ Phase 4
Slice 29: Autonomy: execution loop               │ Phase 4
Slice 30: Autonomy: safety governor              │ Phase 4
```

**Order notes**:
- Phase 0 (cleanup) is complete. Slices 3-6 (Stream A completion) can be parallelized if the team has multiple engineers. Otherwise, sequential.
- Slice 7 (Execution Gate) is the highest-priority slice — everything in Phases 2-4 depends on prerequisite resolution.
- Slice 14 (Startup Validation) depends on B.2 (Credential Vault) for the credential schema. Can start after Slice 8.
- Slice 15 (Live Integration) is a mandatory gate. **M-LIVE must pass before any Phase 2 work begins.**
- Slice 19 (vectors) is marked optional. Do not start it unless keyword recall quality is measurably insufficient. If never started, the system still works.
- Phase 4 is the only phase safe to defer indefinitely. Milestone M7 (Memory Influences Behaviour) at Slice 20 already delivers companion-quality behaviour.

### What to build first

**Slice 7** (next priority). One new function in `execution_boundary.py`. One dataclass. Wire propagation to runtime. Tests for all 5 critical paths (missing credential, expired credential, missing permission, missing identity, network unavailable). This single change eliminates the class of bugs where KIO fabricates or silently fails on missing prerequisites.

**ponytail**: The Execution Gate replaces an unbounded set of special-case checks (one per provider, per action, per credential type) with one generic mechanism. That's the lazy win — delete N special cases by building one gate.

**Skipped**: Vector infrastructure as a Foundation Stream. Cognitive layer infrastructure. Planning as a separate layer. Reflection as a separate layer. Learning as a separate layer. Add when: profiling shows a measurable gap that simpler approaches (keyword, structured queries, deterministic rules) cannot close.

---

## 22. Development Capabilities

The implementation plan leverages the OpenCode engineering environment during development. These are **development capabilities** — they are NOT runtime features of KIO.

| Capability | When to Use | How to Use |
|-----------|-------------|------------|
| **Agency Agents** | Architecture validation, security review, code review, product validation | Delegate specialist agents (Backend Architect, Security Architect, Code Reviewer, Product Manager) for targeted review. Cross-review with Reality Checker. |
| **MCP-assisted development** | When modifying MCP runtime, adding MCP servers, validating MCP tool registration | Use Playwright MCP for browser automation testing. Use Context7 MCP to validate framework/library recommendations against current docs. |
| **Repository intelligence (GitNexus)** | Before editing any function/class/method | Run `impact({target, direction: "upstream"})` to assess blast radius. Run `detect_changes()` before committing. See `AGENTS.md` for full workflow. |
| **Git-assisted architectural review** | During architecture validation | Use `git log` to trace implementation history. Use `git diff` to verify minimal change scope. |
| **Code intelligence** | Before refactoring or decomposing monoliths | Use GitNexus `query()` to find execution flows. Use `context()` for full symbol context. |
| **Browser automation validation** | During M-LIVE, browser milestone testing | Use Playwright MCP to automate browser interaction tests. Run full browser command matrix. |
| **Karpathy engineering reasoning** | Before any implementation decision | Apply: single-file fixes, delete before add, implement before optimize, simple before clever. |
| **Ponytail / YAGNI review** | Before adding new dependencies, abstractions, or infrastructure | Climb the ladder: stdlib → existing codebase → native platform → one line. No speculative work. |

**Principle**: Use these tools to reduce implementation risk, not to add process overhead. If a tool doesn't meaningfully improve the outcome for a specific slice, skip it.

---

## 23. ponytail Ceilings

Deliberate simplifications with known ceilings, marked throughout the codebase and plan:

- `# ponytail: credential vault uses keyring + SQLite metadata.`
- `# ponytail: add hardware-backed keystore if threat model requires it.`
- `# ponytail: identity resolver is a contact book, not a knowledge graph.`
- `# ponytail: upgrade to graph DB when entity count exceeds 10K.`
- `# ponytail: vector support is numpy dot-product on SQLite vectors.`
- `# ponytail: replace with dedicated vector DB when recall@5 drops below 0.8.`
- `# ponytail: prerequisite cache is in-memory dict per session.`
- `# ponytail: add Redis/valkey when multi-process runtime requires it.`
- `# ponytail: startup validation is a simple CLI prompt.`
- `# ponytail: add TUI/config wizard when provider count exceeds 10.`
- `# ponytail: health endpoint is a single JSON response.`
- `# ponytail: add Prometheus/metrics when multi-instance deployment occurs.`
- `# ponytail: Live Integration gate is manual + automated scripts.`
- `# ponytail: formalize into CI pipeline when release frequency exceeds 1/week.`
- `# ponytail: MCP runtime uses stdio transport — add TCP/Unix socket when remote servers required.`
- `# ponytail: Agent Layer is in-process — extract to subprocess when isolation requirements grow.`
- `# ponytail: agent registry is dict-backed — add persistence when agent configs exceed 20.`
- `# ponytail: Interface Layer Channel protocol is duck-typed — formalize ABC when 3rd transport added.`
- `# ponytail: Voice pipeline is synchronous STT→process→TTS — add streaming when latency becomes feedback issue.`

---

## 24. Agent Layer Architecture

The Agent Layer is a runtime abstraction providing interface-based multi-agent coordination. It is NOT hardcoded to Agency Agents or any specific agent provider — any agent conforming to the `Agent` protocol can participate.

### Position in the stack

```
Runtime (dispatch authority)
  └── Agent Layer
        ├── Agent Protocol (interface, not implementation)
        ├── Agent Registry (capability-based discovery)
        ├── Agent Resolver (intent → best-fit agent)
        ├── Agent Lifecycle (register → resolve → invoke → collect)
        └── Multi-Agent Orchestrator (coordinated multi-step workflows)
```

The Agent Layer sits between Runtime and Execution Boundary. The runtime delegates to the agent orchestrator when an intent requires multi-step reasoning or specialist coordination. The orchestrator resolves agents, dispatches sub-tasks, collects results, and returns a unified response.

### Reconciliation with existing code

Three existing subsystems converge into the Agent Layer:

1. **`agent_manager.py`** — Already defines an `Agent` dataclass and `AgentRegistry` that wraps providers. Its `Agent` has `identity`, `specialization`, `capabilities`, and `handler`. This becomes the *implementation* of the Agent Layer's `Agent` protocol. The protocol replaces the dataclass, keeping the same registration logic.
2. **`Executive`** (`executive.py`) — Routes intents to agents or conversation fallback. Becomes the primary consumer of the Agent Resolver.
3. **`Orchestrator`/`Planner`** (`orchestrator.py`, `planner.py`) — Builds task graphs from prompts. Becomes the Multi-Agent Orchestrator implementation.

Migration: The Agent Protocol becomes the single interface. `agent_manager.py` is refactored to implement the protocol. `Executive`, `Orchestrator`, and `Planner` become internal implementations behind the Agent Layer facade — they are NOT deleted, they are absorbed.

**ponytail**: The existing `Executive`/`Orchestrator`/`Planner` pattern already works for single-intent routing. The Agent Layer protocol is an abstraction over that proven pattern. Add multi-agent orchestration patterns (parallel, competing, supervisor) only when a use case requires them — single dispatch and sequential chain are the default.

### Agent Protocol

```python
class Agent(Protocol):
    agent_id: str
    description: str
    capabilities: list[str]

    def can_handle(self, intent: Intent, context: Context) -> float:
        """Return confidence score (0.0–1.0) for handling this intent."""
        ...

    async def execute(self, intent: Intent, context: Context) -> AgentResult:
        """Execute against the intent. Never fabricates credentials or prerequisites."""
        ...
```

No base class. No shared state. Protocol-only. Any object with `agent_id`, `description`, `capabilities`, `can_handle()`, and `execute()` is an Agent.

### Agent Registry

Keyed by `agent_id`. Each entry: `{agent_id, description, capabilities, instance, health}`. Capabilities are free-form strings (e.g., `"code_review"`, `"security_audit"`, `"architecture_validation"`). Registry supports:
- `register(agent)` — register an agent instance
- `resolve(capability)` → list of matching agents, ranked by declared relevance
- `health(agent_id)` → per-agent health status
- `list()` → all registered agents

### Agent Orchestration Flow

```
Runtime receives intent with multi-agent flag
  → AgentLayer.resolve(intent) → ranked candidates
  → Orchestrator.select(candidates, context) → best agent(s)
  → For each agent: call execute() with bounded context
  → Collect results → merge or chain → return unified response
```

**Sequential**: One agent at a time, passing context forward. Used for pipeline workflows (review → fix → verify).

**Parallel**: Multiple agents simultaneously. Used for independent analysis (security audit + code review + product validation).

**Fallback**: Primary agent fails → next best candidate gets the intent. Configurable per workflow.

### Multi-Agent Orchestration Workflow Types

| Pattern | Use Case | Example |
|---------|----------|---------|
| **Single dispatch** | One agent handles the full intent | "Run a security audit on auth.py" → Security Architect |
| **Sequential chain** | Agents pass context forward | "Review this PR" → Code Reviewer → Security Architect → Product Manager |
| **Parallel fan-out** | Independent analysis, merge results | "Validate this design" → Software Architect + Backend Architect + UX Architect |
| **Competing** | Multiple agents propose solutions, arbiter selects | "Best approach for caching?" → 3 agents propose, arbiter picks |
| **Supervisor** | Orchestrator delegates sub-tasks, synthesizes final output | "Design the auth system" → decompose into sub-tasks, assign specialists |

### Integration with Existing Systems

- **Capability Registry**: Agent capabilities are registered alongside tool capabilities. Runtime queries both for unified capability resolution.
- **Execution Gate**: Agents pass through the same prerequisite resolution as any other action. No agent can fabricate credentials.
- **Safety Gateway**: Agent actions are safety-checked per the standard safety state machine. Agent autonomy bounded by the same governor as direct execution.
- **MCP Runtime**: Agents can invoke MCP tools via `execute_mcp_tool()`. MCP servers are a tool-layer resource, not agent-layer.

### KIO Runtime Sub-Agents

KIO ships with a curated set of first-class runtime sub-agents. Each is a concrete `Agent` protocol implementation. These are inspired by — but not coupled to — the installed Agency Agents (170+ specialist definitions in `agency-agents/`). Agency Agents are development-only tooling. KIO runtime sub-agents are production runtime capabilities.

#### Curated set (Phase 2+ delivery)

| Sub-Agent | Responsibility | Capabilities | Phase |
|-----------|---------------|--------------|-------|
| **Planner** | Decompose goals into executable task graphs. Owns sequencing and dependency resolution. | `task_decomposition`, `dependency_resolution`, `goal_planning` | Phase 3 |
| **Researcher** | Multi-source information gathering. Web search, document retrieval, knowledge synthesis. | `web_search`, `knowledge_retrieval`, `fact_synthesis`, `source_validation` | Phase 2 |
| **Reasoner** | Single inference step replacing pattern-matching chains. Uncertainty quantification, contradiction detection. | `inference`, `uncertainty_estimation`, `contradiction_detection`, `pros_cons` | Phase 2 |
| **Memory Specialist** | Episodic memory management. Consolidation, pruning, preference extraction, relevance scoring. | `memory_store`, `preference_extraction`, `memory_consolidation`, `relevance_scoring` | Phase 2 |
| **Browser Specialist** | Web automation — navigation, extraction, interaction, form filling, screenshot. | `browser_navigate`, `browser_extract`, `browser_interact`, `browser_screenshot` | Phase 1 (exists) |
| **Security Specialist** | Safety policy enforcement, threat assessment, credential validation, anomaly detection. | `safety_check`, `credential_validate`, `anomaly_detect`, `policy_enforce` | Phase 3 |
| **Code Specialist** | Code generation, review, refactoring, and analysis within KIO's own development context. | `code_review`, `code_refactor`, `code_generate`, `static_analysis` | Phase 4 |
| **Knowledge Specialist** | Long-term knowledge management. Fact extraction, entity resolution, relationship mapping. | `fact_extraction`, `entity_resolution`, `knowledge_query`, `knowledge_synthesis` | Phase 3 |
| **Reflection Specialist** | Post-execution analysis. Outcome evaluation, improvement suggestions, learning extraction. | `outcome_analysis`, `improvement_suggest`, `lesson_extraction`, `behaviour_adjust` | Phase 4 |
| **Companion Specialist** | Personality consistency, relationship depth, emotional context, initiative calibration. | `relationship_model`, `tone_adaptation`, `initiative_calibrate`, `personality_consistency` | Phase 4 |

Each sub-agent:
- Implements the `Agent` protocol (`can_handle()` + `execute()`).
- Has explicit permission boundaries (what it can/cannot do without user confirmation).
- Has a defined lifecycle (registered at startup, resolved by capability, invoked on intent).
- Participates in the standard orchestration patterns (single, sequential, parallel, supervisor).
- Passes through the Execution Gate — no sub-agent can bypass prerequisite resolution or safety checks.

**Agency Agent mapping**: The 170+ Agency Agents in `agency-agents/` are today's reference implementations for sub-agent capabilities. During Phase 3-4, each KIO sub-agent can use individual Agency Agent definitions as prompt/behavior templates — but the KIO `Agent` protocol is the interface, not the Agency Agent file format. Migration path: Agency Agent → review → extract behavior patterns → implement as KIO Agent → delete Agency Agent reference.

**ponytail**: Not all sub-agents are built in Phase 1. Only Planner (from existing `Executive`/`Orchestrator`/`Planner`) and Browser Specialist (existing) are available immediately. Others are added in their respective phases. If a sub-agent's capability is never needed, it is never built.

### ponytail

- Agent registry is in-memory dict — backed by SQLite when agent configs exceed 20.
- Agent orchestration is runtime-in-process — extract to subprocess orchestrator when isolation or language-agnostic agents are needed.
- Competing pattern uses simple confidence ranking — add debate/negotiation protocol when agents disagree.
- No agent persistence across sessions — add agent state serialization when agents carry long-lived workflows.

---

## 25. Interface Architecture

KIO's interface layer is designed **voice-first, desktop primary, platform-agnostic**. No interface is hardcoded to a specific chat platform.

### Design Principles

1. **Voice is the primary interface** — natural for a companion. STT → intent → execution → TTS. Conversational, hands-free, ambient.
2. **Desktop CLI is the power-user interface** — rich output, scripting, pipeable, automatable. The CLI exposes everything voice can do plus diagnostics.
3. **Platform transports are abstractions, not identities** — Telegram, Discord, etc. are `Channel` implementations. KIO's companion identity is not "a Telegram bot."
4. **Multi-channel continuity** — same companion across voice, CLI, and chat. Shared memory, shared state, shared goals.

### Interface Layer Stack

```
┌─────────────────────────────────────────────────┐
│              Interface Layer                     │
│                                                   │
│  ┌─────────────────────┐  ┌──────────────────┐  │
│  │  Voice Channel       │  │  Desktop Channel  │  │
│  │  (STT → NLU → TTS)  │  │  (CLI, TUI)       │  │
│  │  Primary interface   │  │  Power-user       │  │
│  └─────────┬───────────┘  └────────┬─────────┘  │
│            │                       │            │
│  ┌─────────┴───────────┐  ┌────────┴─────────┐  │
│  │  Platform Transport  │  │  Platform Transport│ │
│  │  (Telegram, Discord) │  │  (same protocol,  │  │
│  │  via Channel proto   │  │  different adapter)│ │
│  └─────────────────────┘  └──────────────────┘  │
│                                                   │
│  Common: dispatch_channel_input(text, channel,    │
│          user_id) → KioResponse                   │
└─────────────────────────────────────────────────┘
```

### Channel Protocol

```python
class Channel(Protocol):
    channel_id: str
    channel_type: str  # "voice" | "desktop" | "messaging"

    async def send(self, response: KioResponse) -> None: ...
    async def receive(self) -> ChannelInput | None: ...
    def health(self) -> ChannelHealth: ...
```

All transports implement the same protocol. The runtime dispatches via `dispatch_channel_input()` regardless of source channel. Channel metadata (platform, user_id) is passed as context — not hardcoded into routing logic.

### Voice Pipeline (Primary)

```
Audio in → VAD → STT (Whisper) → Normalize → dispatch_channel_input(channel="voice") →
  → Execute → Response → TTS → Audio out
```

Components (all exist in `mini_kio/`):
- **VAD**: Silero VAD for voice activity detection
- **STT**: Whisper (local or API) for speech-to-text
- **Speaker diarization**: Identify who is speaking (multi-user context)
- **TTS**: Local or API text-to-speech for response

### Desktop CLI (Power-User)

```
CLI input → dispatch_channel_input(channel="cli") → Execute → Response → stdout
```

Capabilities beyond voice:
- Rich formatted output (syntax-highlighted code, tables, structured data)
- Pipe/stdin integration for scripting
- `--json` flag for machine-readable output
- Diagnostic commands (`/health`, `/providers`, `/agents`, `/mcp`)
- Session management (attach, detach, inspect)

### Platform Transports

Telegram, Discord, and future platforms implement the `Channel` protocol. They are:
- **Interchangeable**: Swap Telegram for Matrix without changing KIO core
- **Independent**: One transport failing never affects others
- **Augmenting**: Platform-specific features (inline keyboards, markdown, attachments) are exposed as optional extensions, not base protocol requirements

### Multi-Channel Design Rules

1. All channels converge on `dispatch_channel_input()` — single dispatch point
2. All responses are `KioResponse` — typed, channel-agnostic, formatted by `format_channel_reply()`
3. Platform-specific formatting is done by the transport adapter, not by core logic
4. Session identity is platform-agnostic — "Aaron" in Telegram is the same "Aaron" in voice
5. Proactive events deliver to the user's preferred channel (configurable per event type)

### ponytail

- Channel protocol is duck-typed — formalize as ABC when 3rd transport added.
- Voice pipeline is synchronous chain — streaming VAD/STT optional, add when latency is a feedback issue.
- Platform-specific features (Telegram inline keyboards) tunnel through metadata — add structured extensions when 3rd platform needs them.
- No multi-channel session merging — user in Telegram and user in CLI are separate sessions. Merge when cross-platform continuity is required.

---

## 26. Companion Evolution

The companion intelligence doctrine defines a transition path from assistant to companion. This section maps that evolution onto the implementation phases.

### Evolution Path

```
Assistant ──► Cognitive Partner ──► Persistent Companion Intelligence
(Phase 1)        (Phase 2-3)             (Phase 4+)
```

| Axis | Assistant (Phase 1) | Cognitive Partner (Phase 2-3) | PCI (Phase 4+) |
|------|-------------------|------------------------------|----------------|
| **Initiative** | Reactive only | Time+state based suggestions | Autonomous goal pursuit |
| **Memory** | Session-only | Persistent + preference extraction | Lifelong shared history |
| **Identity** | No | Person resolution across services (Phase 2: contact book. Phase 3: preference-aware resolution) | Deep relationship model (interaction history, trust-weighted) |
| **Proactivity** | Off | Configurable (low/medium/high) | Context-aware initiative |
| **Trust** | None | Accumulated via reliable execution + preference confidence scores | Explicit trust model (per-domain, time-decayed) |
| **Personality** | Functional | Consistent style, evolving via Preference Extraction (Slice 20) | Stable behavioral identity with learned adaptation |
| **Reasoning** | Pattern matching | Inference step + alternatives | Independent thought with self-correction |
| **Voice** | Optional | Primary interface | Natural, anticipatory |

### Companion Architecture Invariants (from Doctrine, not modified)

- **Freedom of Mind, Governance of Action** — cognition unrestricted, external actions pass execution governance
- **Companion vs Assistant** — companion participates, anticipates, develops shared history
- **Trust governs autonomy** — trust expands through demonstrated reliability, not elapsed time
- **No consciousness claim** — emotional model communicates reasoning state, not subjective experience
- **Epistemic integrity** — facts vs speculation, confidence estimates, revise when evidence changes

### Doctrine Integration Points

| Doctrine Principle | Implementation Plan Mapping |
|-------------------|---------------------------|
| Freedom of Mind. Governance of Action. | Safety Architecture §15 + Execution Gate §16 |
| Initiative defines companionship | Proactivity Phases P.1-P.5 (Phase 3) |
| Personality persists across years | Preference Extraction (Slice 20) + consistent response style |
| Emotional modelling for prioritization | Preference confidence scores + context-aware communication |
| Relationships deepen through continuity | Session Continuity (Slices 11-12) + Identity Resolver (Slice 10) |
| Independent thought | Reasoner Refactor (Slice 21) + Alternative Generation (Slice 22) |
| Epistemic integrity | Decision logging (Slice 5) + uncertainty quantification |
| Trust evolution | Proactivity arbiter + Safety governor + audit trail |
| Growth over decades | Phase 4+: learning from experience, accumulated knowledge |

### What Changes (and What Doesn't)

**No changes to**: Constitution (`KIO_CONSTITUTION.md`), Engineering OS (`KIO_ENGINEERING_OS.md`), existing runtime code, test suite, interfaces, or contracts.

**Changes** (all within this plan):
- Phase 1 delivers the **Assistant** foundation (credentials, identity, session, config)
- Phase 2-3 delivers **Cognitive Partner** (context, memory, proactivity, reasoning quality)
- Phase 4 delivers **Persistent Companion Intelligence** (autonomy, safety governor, goal pursuit)
- The doctrine informs priorities and design decisions but does not create new work items

### FQ-06 Override Policy (response-layer constraint)

Per `FINAL_FOUNDER_DECISIONS.md` FQ-06: KIO may respectfully disagree once. After that, the user's decision prevails unless already prohibited by safety policy. This is a response-layer behavior constraint — not a new gate mechanism. Implemented in the response pipeline (Slice 5 decision logging + Gate C-4 response separation): when KIO detects a conflict with its stored preference or safety recommendation, it may express disagreement once in the response. If the user confirms, execution proceeds through the standard safety gate. No new refusal category is introduced beyond what `execution_boundary.py` already enforces.

### ponytail

- No new work items created from the doctrine — existing 30 slices already cover the evolution path.
- Personality persistence is Preference Extraction (Slice 20) — sufficient for Phase 2-3. Add explicit personality model when users consistently report "KIO feels inconsistent."
- Trust model is implicit (proactivity confidence threshold) — formalize as explicit TrustStore when variable trust across domains (finance, health, personal) is required.
