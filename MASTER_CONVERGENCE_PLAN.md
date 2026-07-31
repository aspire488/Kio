# MASTER CONVERGENCE PLAN

**Version:** 1.0
**Status:** For Approval
**Governing Document:** `KIO_CONSTITUTION.md` (ratified)
**Executed By:** `KIO_ENGINEERING_OS.md`
**Position in the chain:** Constitution defines the destination → this document defines the path → the Engineering OS is the loop that walks it.

This document consolidates the full repository audit, contradiction analysis, convergence decisions, gate planning, and open questions already produced for KIO. It does not redo the audit and does not invent new Gates — it is the canonical, single-source-of-truth form of that analysis, structured so the Engineering Operating System can execute against it without needing another planning document.

---

## Executive Summary

KIO has real engineering substance and a clear constitutional vision. Between the vision and the codebase lie specific, measurable gaps. This plan identifies each gap, names the contradiction or missing piece, and defines a dependency-ordered sequence to close them.

**What this plan does not do:** propose rewrites, add features, or redesign architecture. Every recommendation maximizes reuse of existing code.

**Core finding:** the system works (97.8% test pass rate, ~45 MB idle RAM, production Telegram channel). The gap is not stability — it is coherence. AURA is named in the Constitution but not present in the repository. Six state systems compete for context authority. Two architecture generations coexist. The routing layer cannot discover capabilities dynamically. The planning layer exists but is disconnected from routing.

---

## Current Repository State

**Audit scope:** 7 phases, covering ~36 directories, ~185+ Python files, 20 key architecture/doctrine documents, 11 external repositories, and 16 historical snapshot archives (~1.3 GB).

**What's working:**
- 97.8% test pass rate across the existing suite
- ~45 MB idle RAM — well inside the `HARD_LIMIT_MB = 190` constant
- Production Telegram channel, actively serving conversations
- Safety gateway (`execution_boundary.py`) and `ARCHITECTURE_LOCK.md` Rules 1–11 hold up under audit
- Browser (`browser_runtime/`) and MCP (`mcp_runtime/`) runtimes are both production-grade, not stubs

**What's fragmented:**
- Two runtime generations coexist: `mini_kio/core/runtime.py` (the actual dispatch authority) and a separately built top-level `runtime/` (well-designed, but not authoritative)
- Six state systems independently track session/context: `SessionState`, `ConversationContext`, `ContinuityState`, `MediaEntityMemory`, `ArtifactMemory`, `MediaContext`
- Command routing is a 422-line hardcoded if/elif chain (`command_router.py`) with no dynamic capability discovery
- The planning layer (`executive.py`, `task_engine.py`, `agent_manager.py`, `orchestrator.py`) is fully built and **never called** by the actual routing path
- Two LLM provider routing chains diverge (`backup_llm/` vs. `mini_kio/llm/llm_gateway.py`), with different provider lists
- Two `provider_base` interfaces exist for the word "provider" — one ABC-based (LLM-focused), one Protocol-based (generic capability execution)
- **AURA, as described in the Constitution (17 subsystems, 11 pending agents, Layer 0–9 hierarchy, ~40-chapter canonical document), does not exist.** The `aura/` directory is a 35-line stub README. `aura_integration.py` is a real, well-designed 200-line integration API — but it emits observations to a receiver that isn't there yet.

This is the starting point every Gate below is measured against.

---

## Current-State Map

Full subsystem inventory: current implementation, Constitution target, gap, and recommendation for every module audited.

### Core Runtime — `mini_kio/core/`

| Module | Current Implementation | Constitution Target | Gap | Recommendation |
|---|---|---|---|---|
| `runtime.py` | LOCKED (Gate 3), 1643 lines. Dispatch pipeline, state machine, safety states. Both `dispatch_channel_input()` (primary) and `_route_via_orchestration()` (Gate 3) exist; some routes bypass orchestration. | Single dispatch authority (Constitution §6, "capability-based over implementation-specific") | Bypass routes exist | **Keep** |
| `command_router.py` | LOCKED, ~1280 lines. 422-line hardcoded `_dispatch_command()` if/elif chain, 20+ branches. | Discoverable capability routing (Constitution §6, "observable and explainable by default") | No dynamic capability discovery; new capabilities require editing this file | **Replace** — capability registry |
| `execution_boundary.py` | LOCKED, ~620 lines. Safety gateway. | Safety-by-default (Constitution §6) | None found | **Keep** |
| `config.py` | LOCKED, ~200 lines. Multiple env sources. | Configuration correctness | None found | **Keep** |
| `executive.py` | Built, 37 lines. Clean orchestrator wrapper. | Persistent planning (Constitution §15) | Never called by routing path | **Integrate** |
| `task_engine.py` | Built, ~150 lines. Multi-step execution. | Multi-step goal decomposition (Constitution §15) | Never called by routing path | **Integrate** |
| `agent_manager.py` | Built, ~80 lines. Agent lifecycle. | Future agent orchestration | Never called by routing path | **Keep** (future) |
| `orchestrator.py` | Built, ~120 lines. Plan-from-prompt pipeline. | Goal-to-plan pipeline (Constitution §15) | Never called by routing path | **Integrate** |
| `command_parser.py` | Stable, ~100 lines. | — | None found | **Keep** |
| Operators (app, browser, file, system) | LOCKED. Stable, correctly designed. | Execution layer | None found | **Keep** |
| `activation.py` / `camera_runtime.py` | Built, ~200 lines. Wake-word, camera. | Multi-modal input (future) | Not triggered in Telegram mode | **Keep** |
| `desktop_intelligence.py` | Built, ~400 lines. Desktop NL routes. | Desktop capability | None found | **Keep** |
| `directorates.py` | Built, ~60 lines. Capability directorates, used by `executive.py`. | Capability organization | None found | **Keep** |
| `providers.py` / `provider_registry.py` | Built, ~200 lines. Execution provider registry. | Capability-based routing (Constitution §6) | Bypassed by `_dispatch_command()` | **Integrate** |

### LLM Layer — `mini_kio/llm/`

| Module | Current Implementation | Constitution Target | Gap | Recommendation |
|---|---|---|---|---|
| `llm_gateway.py` | Stable, 157 lines. Multi-provider failover, 45s chain timeout, response validation. | Reliability over novelty (Constitution §6) | None found | **Keep** |
| `provider_manager.py` | Gate 4A active, 125 lines. Circuit breakers, health tracking. | Observable and explainable by default | None found | **Keep** |
| `provider_base.py` | Stable, 31 lines. ABC for LLM providers. | Capability-based routing | Duplicate interface philosophy with `providers/provider_base.py` | **Keep**, disambiguate (see D-08) |
| `providers/` (gemini, ollama, huggingface, freellm, mock) | Varies. Gemini and mock are production; others partial. | Local-first where practical | Partial provider coverage | **Keep, consolidate** |
| `intent_classifier.py` | Stable, 219 lines. Heuristic + JSON pattern matching. | Fast-path routing | No LLM-based classification | **Keep** as fast-path |
| `intent_validator.py` | Stable, ~150 lines. Safety validation. | Security by default | None found | **Keep** |
| `conversation_orchestrator.py` | Stable, 247 lines. 4-state machine (CONVERSATIONAL, AWAITING_CONFIRMATION, EXECUTABLE_READY, REFUSED). | Persistent planning (Constitution §15) | No PLANNING/EXECUTING/VERIFYING states | **Extend** |
| `conversation_responder.py` | Stable, ~500 lines. Monolithic LLM prompt — intent, memory, formatting, character all in one. | Composition over duplication (Constitution §6) | Concerns not separated | **Refactor** |
| `fallback_manager.py` | Stable, 120 lines. Repetition suppression, diversified fallback pool. | Reliability | None found | **Keep** |
| `input_normalizer.py` | Stable, ~200 lines. Sanitization, typo normalization, authority overrides. | Security by default | None found | **Keep** |
| `session_state.py` | Stable, ~300 lines. Per-session state. | Single context authority (Constitution §6) | One of 6 overlapping state systems | **Merge** into unified context |
| `conversation_context.py` | Stable, ~200 lines. Bounded exchange history. | Single context authority | Overlaps with SessionState | **Merge** into unified context |
| `KIO_character_knowledge.py` | Stable, ~300 lines. Character Bible v2. | Stable behavioral identity (Constitution §15) | None found | **Keep** |
| `backup_llm/` (standalone) | Archive, ~435 lines. Secondary LLM routing, different provider config. | Single provider chain | Duplicates `mini_kio/llm/` | **Retire** |

### AURA Continuity Layer

| Module | Current Implementation | Constitution Target | Gap | Recommendation |
|---|---|---|---|---|
| `aura/README.md` | Stub, 35 lines. Template placeholder. | 17 subsystems, ~40-chapter canonical doc (Constitution §1) | Everything | **Build** |
| `mini_kio/execution/aura_integration.py` | Built, 200 lines. Integration API — observe, request_*, report_*. Graceful degradation throughout. Correct design. | Continuity layer entry point (Constitution §7) | Emits to a receiver that doesn't exist yet | **Keep and extend** |
| AURA canonical architecture document | **Missing.** Referenced in Constitution §2. | 40-chapter document | Does not exist in the filesystem | **Founder decision required** (Q-01) |
| AURA Layer 0–9 hierarchy | **Not implemented.** | Full cognitive-loop hierarchy | No code or architecture doc | **Build** (Gate C-7) |
| AURA agents (17 subsystems, 11 pending) | **Not implemented.** | 17 implemented, 11 pending activation | No code exists | **Build** (Gate C-7) |

### Adapter Framework — `adapters/`

| Module | Current Implementation | Constitution Target | Gap | Recommendation |
|---|---|---|---|---|
| `registry.py` | Complete, ~150 lines. Singleton, discover, load, lifecycle. Stdlib only. | Capability discovery (Constitution §6) | None found | **Keep** |
| `discovery.py` | Complete, ~80 lines. Scans `adapters/` for metadata. | Discoverable capabilities | None found | **Keep** |
| `loader.py` | Complete, ~50 lines. Dynamic import via importlib. | Modular by design | None found | **Keep** |
| `types.py` | Complete, ~60 lines. AdapterInfo, AdapterState, AdapterHealth. | Observable and explainable | None found | **Keep** |
| Agency Swarm adapter | Stub, 31 lines. `health()` returns True. | Multi-agent coordination (future) | No real integration | **Keep as stub** |
| Agent Reach adapter | Partial stub, 74 lines. `read_url()`, `search()`. Lazy import. | Web reading/search capability | Not wired to a proven gap | **Keep as stub** |
| OpenWork adapter | Stub, 20 lines + 10 sub-modules (runtime, workspace, session, mcp, etc.). Interface defined, not wired. | Workspace/session management | Not wired | **Keep as stub** |
| Scrapling adapter | Partial stub, 93 lines. Extraction methods, lazy imports, 12 sub-modules. | Structured web extraction | Not wired | **Keep as stub** |
| Shepherd adapter | Stub, 31 lines. `health()` returns True. | — | No real integration | **Keep as stub** |
| LibreChat, Agentic Inbox, Avatar, Voice | Empty directories, no code. | Future multi-modal/multi-channel | Placeholders only | **Keep as placeholders** |

### Top-Level V2 Architecture (coexisting with `mini_kio/`)

| Module | Current Implementation | Constitution Target | Gap | Recommendation |
|---|---|---|---|---|
| `runtime/` (ObservationBus, events, subscribers) | Built, ~200 lines. Well-designed, matches spec. | Single event authority | Coexists with `mini_kio/core/runtime.py` — a different runtime system | **Keep as utility** — not dispatch authority |
| `execution/` (Dispatcher, Engine, Executor, Planner, Scheduler) | Stub ABCs, ~100 lines. Not wired to anything. | Composition over duplication | Unused abstraction layer | **Retire** or merge into `mini_kio` |
| `communication/` (EventBus, Message, PubSub protocols) | Built, ~140 lines. Protocol definitions. | Shared contracts | Not actively used — `mini_kio` runtime has its own event system | **Keep** as shared protocols |
| `browser/` (facade, automation, tabs) | Built, ~12 files. | Single browser authority | Coexists with `mini_kio/core/browser_operator.py` and `browser_runtime/` | **Merge** into `browser_runtime` |
| `workspace/` (workspace, session, registry, artifacts) | Built, ~6 files. | Persistent workspace management | Not wired to `mini_kio` runtime | **Integrate** |
| `providers/provider_base.py` (Protocol-based) | Built, 63 lines. Second provider interface — different from `mini_kio/llm/provider_base.py`. | Capability-based routing | Two provider philosophies sharing one name | **Reconcile** (D-08) |
| `governance/`, `voice/`, `avatar/`, `distributed/` | Stub READMEs only, 35 lines each. | Future subsystems | Policy/voice/avatar/distributed not implemented | **Keep placeholder** |

### Standalone Runtimes — `mini_kio/runtime/`

| Module | Current Implementation | Constitution Target | Gap | Recommendation |
|---|---|---|---|---|
| `browser_runtime/` | Production, ~32 files. Playwright-based, clean lifecycle, crash recovery, health monitoring, 13 browser commands. | Local-first browser automation | None found | **Keep** — active browser engine |
| `mcp_runtime/` | Production, ~12 files. JSON-RPC 2.0 over stdio, server connection, tool registry, executor, health monitor. | MCP integration (Constitution §2) | None found | **Keep** — active MCP engine |

### External Repositories (see full Convergence detail below)

| Repository | Path | Current State | Recommendation |
|---|---|---|---|
| agency-swarm | `external/agency-swarm/` | Cloned, unused | Do not integrate |
| agent-reach | `external/agent-reach/` | Cloned, unused | Do not integrate |
| agentic-inbox | `external/agentic-inbox/` | Cloned, unused | Do not integrate |
| cua | `external/cua/` | Cloned, partially wired via CUA provider | **Keep** — already routes through the capability system |
| LibreChat | `external/LibreChat/` | Cloned, unused | Do not integrate until needed |
| Open-LLM-VTuber | `external/Open-LLM-VTuber/` | Cloned, unused | Do not integrate |
| openwork | `external/openwork/` | Cloned, unused | Do not integrate until needed |
| Scrapling | `external/Scrapling/` | Cloned, unused | Do not integrate until needed |
| shepherd | `external/shepherd/` | Cloned, unused | Do not integrate until needed |
| kio_test_server | `external/kio_test_server/` | Active (MCP test server) | **Keep** |

### Snapshot Archives

16 snapshot directories (Gate 0 through Gate 4E), ~1.3 GB. Historical states — not active code. Archive to cold storage (Q-05, D-14).

---

## Unified Target Architecture

Not a redesign — the destination already implied by the Constitution, made concrete.

```
User Input (Telegram / local / Discord / future channel)
  │
  ▼
┌────────────────────────────────────────────┐
│  Layer 1: Input Processing                 │  mini_kio/llm/input_normalizer.py
│  - Sanitization, typo/emoji normalization  │  (Keep — works)
│  - Authority override detection             │
└────────────────────┬───────────────────────┘
                     │ Normalized text
                     ▼
┌────────────────────────────────────────────┐
│  Layer 2: Routing / Goal Parsing           │  Replace command_router.py if/elif
│  - Fast path: direct command match         │  Preserve: intent_classifier.py
│  - Goal parser (structured Goal object)    │  NEW: Goal dataclass
│  - Capability registry query               │  NEW: CapabilityRegistry.find()
└────────────────────┬───────────────────────┘
                     │ Goal {domain, action, target, constraints}
                     ▼
┌────────────────────────────────────────────┐
│  Layer 3: Central Context Manager          │  NEW: unified module
│  - Active domain / entity (single source)  │  Replaces: SessionState, ContinuityState,
│  - Continuation detection (one system)     │    ConversationContext, MediaEntityMemory,
│  - History, memory integration             │    IntegrationAdapter continuity logic
└────────────────────┬───────────────────────┘
                     │ Goal + Context
                     ▼
┌────────────────────────────────────────────┐
│  Layer 4: Planning / Execution             │  INTEGRATE: executive.py, task_engine.py,
│  - Goal → plan decomposition               │    orchestrator.py (reuse, not rewrite)
│  - Multi-step dependency resolution        │
│  - Execution via execution_boundary.py     │
└────────────────────┬───────────────────────┘
                     │ Execution plan / result
                     ▼
┌────────────────────────────────────────────┐
│  Layer 5: Response Generation              │  REFACTOR conversation_responder.py
│  - Template-based formatting               │  Separate: what to say vs how
│  - Self-verification gate                  │  NEW: verify(goal, response)
└────────────────────┬───────────────────────┘
                     │ Verified response
                     ▼
┌────────────────────────────────────────────┐
│  Layer 6: AURA Continuity Layer            │  BUILD on aura_integration.py
│  - Observation ingestion, learning         │  (integration API exists;
│  - Long-term memory consolidation          │   cognitive layer does not)
│  - Initiative engine (within safety bounds)│  Requires Q-02 resolution first
└────────────────────────────────────────────┘
```

**Layer boundary rules:**

1. Lower layers never import higher layers.
2. Layer 2 (routing) is the only entry point for channel input.
3. Layer 3 (context) is the sole source of truth for session state.
4. Layer 4 (planning) is the only path to multi-step execution.
5. Layer 5 (response) is the only path to channel output formatting.
6. Layer 6 (AURA) receives observations but never blocks execution.

**What does NOT change:** `execution_boundary.py`, `llm_gateway.py` + provider chain, `browser_runtime/`, `mcp_runtime/`, all operators, `FactRepository`/`MemoryRepository`, `MathResolver`/`IdentityResolver`/`KnowledgeResolver`, Telegram integration, `ARCHITECTURE_LOCK.md` Rules 1–11, and every existing passing test.

---

## Convergence Principles

The permanent architectural rules this plan is built against. These are the practical application of Constitution §6 to the convergence work specifically — not a restatement of the Constitution, but how its principles resolve concretely for this codebase:

- **One authority per responsibility.** Context has one manager (Layer 3), routing has one registry (Layer 2), each "provider" concept has one interface. Where two currently exist for the same responsibility, the plan's default is to merge, not to pick a favorite and orphan the other silently.
- **Discoverability over hardcoding.** Every convergence decision that touches routing moves toward the capability being registered and found, not matched by an if/elif branch.
- **No new capability without a mapped seam.** New work integrates through `adapters/`, `CapabilityProvider`, or the Capability Registry — never as a bespoke one-off wired directly into the runtime.
- **Safety doctrine is untouched by default.** `execution_boundary.py` and `ARCHITECTURE_LOCK.md` Rules 1–11 are preserved as-is. Rule 12 is the sole exception under active dispute (C-07 / Q-02), and it requires a Founder decision, not an engineering judgment call.
- **Reuse before build.** Every Gate below prioritizes wiring existing, already-implemented code (`executive.py`, `task_engine.py`, `orchestrator.py`, `providers.py`) over writing new implementations.
- **Consolidate before extend.** State, routing, and provider consolidation (Gates C-1, C-2, C-5) happen before new capability is layered on top (Gate C-3 onward) — building on six competing state systems would only deepen the fragmentation.

---

## Contradiction Log

| ID | Problem | Impact | Resolution | Status |
|---|---|---|---|---|
| C-01 | AURA described in Constitution §1, 2, 7 as having 17 implemented subsystems, 11 pending agents, and a ~40-chapter canonical document. Reality: 35-line stub README, an integration API that emits to nowhere, no cognitive-loop code, no canonical document. | The Constitution's foundational claim about AURA's existence level is incorrect as a description of current state. | Treat Constitution's AURA description as the *target*, not current state (per Engineering OS's incremental-build rule). Build via Gate C-7. | **Open** — Q-01 |
| C-02 | Two runtime architectures coexist. `STRUCTURE_V2.md` describes a layered architecture; `ARCHITECTURE_LOCK.md` declares `runtime.py` the single dispatch source of truth. In practice, `mini_kio/core/runtime.py` (1643 lines, active) and `runtime/observation_bus.py` + `runtime/events.py` (well-designed, not authoritative) both exist. | New contributors — human or agent — will be confused about which runtime is authoritative; documentation describes a system that doesn't match the codebase. | `mini_kio/core/runtime.py` is confirmed as the dispatch authority (D-02). Top-level `runtime/` is kept as an event utility only (D-03). | **Resolved** — pending doc reconciliation (Gate C-6) |
| C-02a | Two `provider_base` interfaces: `mini_kio/llm/provider_base.py` (ABC — `generate()`, `health_check()`) vs. `providers/provider_base.py` (Protocol — `initialize()`, `shutdown()`, `health()`, `capabilities()`, `metadata()`, `execute()`). | Two different interface philosophies share the name "provider," serving genuinely different purposes (LLM text generation vs. generic capability execution). | Keep both, but rename the Protocol-based one to `CapabilityProvider` to disambiguate (D-08). | **Resolved** — Gate C-5 |
| C-03 | Planning layer (`executive.py`, `task_engine.py`, `agent_manager.py`, `orchestrator.py`) is fully implemented but never called by `_dispatch_command()` or `dispatch_channel_input()`. | Years of planning-layer engineering sit unused; the system cannot decompose multi-step goals. | Wire into the routing path (Gate C-3, D-16). | **Resolved** — pending Gate C-3 execution |
| C-04 | Three independent continuity systems (ContinuityResolver, IntegrationAdapter._is_continuation_query, runtime pre-route) each decide, with different rules, whether input is a continuation. | Context bleed is the most common documented failure pattern — 7 of 19 documented failure scenarios. | Merge into one Central Context Manager (Gate C-1, D-13). | **Resolved** — pending Gate C-1 execution |
| C-05 | Adapter framework (registry, discovery, loading, health aggregation, lifecycle) is fully implemented; all 6 concrete adapters are stubs returning `{"status": True}`. | 11 external repositories cloned, 6 adapter interfaces defined, zero live integrations — the framework works but delivers no proven value yet. | Keep the framework; keep adapters as stubs until a currently-open gap genuinely maps to one (D-15). | **Resolved** — no action required unless a gap is proven |
| C-06 | Two LLM provider chains diverge: `backup_llm/llm_router.py` (Gemini → Groq → …) vs. `mini_kio/llm/llm_gateway.py` (active gateway, different provider list). | Configuration drift — unclear which provider chain is canonical. | Consolidate into `mini_kio/llm/`; retire `backup_llm/` (D-10). | **Resolved** — Gate C-5 |
| C-07 | `ARCHITECTURE_LOCK.md` Rule 12: "No uncontrolled autonomy — all actions require explicit user request or deterministic trigger. No autonomous initiative." Constitution §15: "Initiative and curiosity within safe boundaries — the ability to explore and propose, bounded by the user's authority, preferences, permissions, and safety constraints." | Direct contradiction between safety doctrine and the companion vision's autonomy. | **Requires Founder decision** before any initiative-taking behavior is implemented. | **Open** — Q-02, blocks initiative-specific work within Gate C-7 only (per Engineering OS §12 scoped-escalation rule) |
| C-08 | `docs/CURRENT_TASK.md` references `mini_kio/context/context_manager.py`; the actual file is at `mini_kio/core/context_manager.py`. | Minor — stale path reference from a prior reorganization. | Correct the path reference. | **Resolved** — trivial fix, any Gate touching this file corrects it in passing |
| C-09 | Three distinct capability‑discovery systems (`CommandRegistry` from Gate C‑2, `ProviderRegistry` + `STATIC_ACTION_TABLE` used by the planner, and `CapabilityRegistry` for browser sessions) are independent and never consult each other. | Planner validation passes actions that lack a live browser session, causing degraded behavior. Fragmentation defeats the Convergence Plan's "single authority per responsibility" principle. | Resolved by `KIO_Implementation_Plan.md` Slice 6: added `resolve_capability(action)` to `routing_utils.py` — unified query across STATIC_ACTION_TABLE + ProviderRegistry. CapabilityRegistry excluded (tracks runtime sessions, not static capabilities — session validation belongs in Slice 7's execution gate protocol). CommandRegistry excluded (dispatch mechanism for command_router, not capability registry). Triple pronoun-resolution excluded (three domains: general context, media context, memory — different backing stores, no confirmed divergence bug). | **Resolved** — Slice 6


---

## Architectural Decisions

| ID | Capability | Decision | Justification |
|---|---|---|---|
| D-01 | AURA implementation | **Build** (not skip) | Constitutional requirement (C-01). Must start from the accurate current-state (stub), not the assumed-existing 40-chapter description. |
| D-02 | `mini_kio/core/runtime.py` | **Keep** as runtime authority | It IS the dispatch source of truth; `ARCHITECTURE_LOCK.md` Rule 1 confirmed. |
| D-03 | `runtime/` (top-level ObservationBus) | **Keep** as event utility | Well-designed eventing infrastructure; not the dispatch authority. |
| D-04 | `execution/` top-level ABCs | **Retire** | Abstract base classes with no implementations wired; actual execution fabric lives in `mini_kio/core/` and `mini_kio/execution/`. |
| D-05 | `communication/` protocols | **Keep** as shared contracts | Well-defined EventBus, Message, PubSub protocols; can be referenced by future adapters. |
| D-06 | `browser/` V2 module | **Merge** into `browser_runtime` | Consolidate domain aliases, tab tracking, and routing into a single source of truth. |
| D-07 | `workspace/` V2 module | **Merge** into `mini_kio` | Wire workspace management into `KioRuntime` for persistence. |
| D-08 | `providers/provider_base.py` (Protocol) | **Keep** separate, rename `CapabilityProvider` | Serves a genuinely different purpose (generic capability execution) from the LLM provider ABC; renaming disambiguates without merging incompatible concerns. |
| D-09 | `governance/`, `voice/`, `avatar/`, `distributed/` | **Keep** as placeholders | Remove README stubs; leave directories empty for future implementation. |
| D-10 | `backup_llm/` | **Retire** | Consolidate provider configuration into `mini_kio/llm/`; remove duplicate routing code. |
| D-11 | Command routing (`_dispatch_command()`) | **Replace** | 422-line if/elif chain becomes a dynamic capability registry; preserve all existing routes exactly. |
| D-12 | Continuity systems (3 → 1) | **Merge** | Replace 3 independent continuity systems with one Central Context Manager. |
| D-13 | State objects (6 → 2) | **Merge** | Merge SessionState, ConversationContext, ContinuityState, MediaEntityMemory, ArtifactMemory, and MediaContext into one ContextManager per session. |
| D-14 | Snapshot directories | **Archive** | Move 16 snapshot directories (~1.3 GB) to cold storage; historical references, not active code. |
| D-15 | External repositories | **Keep cloned, no integration** | Adapter stubs are sufficient until an integration need is proven against a currently-open gap. |
| D-16 | `executive.py`, `task_engine.py`, `orchestrator.py` | **Integrate** | Wire the existing planning layer into the routing path — reuse, not rewrite. |

---

## Risks

| ID | Risk | Likelihood | Impact | Mitigation | Owner | Exit Criteria |
|---|---|---|---|---|---|---|
| R-01 | AURA no-rewrite doctrine (Constitution §1) collides with a needed KIO interface change | Medium | High — could block Gate C-7 | Identify exact interface changes needed during Gate C-1 refactoring; propose minimal surface changes, not rewrites | Architect | Accepted interface-change proposals reviewed for minimality |
| R-02 | Capability registry refactoring breaks existing routes | Medium | High — silent misrouting | All 20+ existing routes preserved exactly; parallel run (old + new routing, compare outputs) before removing old code | Architect | All Gate 3 tests pass; no regression in the 19 documented failure scenarios |
| R-03 | Context manager merge introduces new continuity bugs | Medium | Medium — context bleed | Conservative migration: one state object at a time, each validated against the 7 documented context-bleed failures | Architect | All 7 context-bleed scenarios pass correctly |
| R-04 | Founder decision on C-07/Q-02 (autonomy vs. safety) not forthcoming | Low | High — blocks initiative-specific work in Gate C-7 | Per Engineering OS §12, this blocks only autonomous-initiative behavior specifically; Gates C-1 through C-6 (~6–8 weeks) proceed regardless | Founder | Decision documented in a Constitution amendment or decision log |
| R-05 | AURA canonical document (~40 chapters) never existed | High | Medium — Gate C-7 must define AURA architecture from scratch | Gate C-7 includes architecture definition as its first step; the Constitution's outline (Layer 0–9, cognitive loop) provides the shape, the detail must be built | Architect | AURA architecture document written and approved before implementation begins |
| R-06 | External repo integration becomes urgent before adapters are ready | Low | Low — adapters are stubs | Adapter framework is complete and functional; when integration need arises, only the specific adapter needs implementation | N/A | When first adapter is wired, all existing stubs still work |
| R-07 | Gates C-1 through C-6 produce 6+ weeks of change with no user-visible improvement | Medium | Medium — stakeholder fatigue | Each Gate has concrete exit criteria and testable improvements; Gate C-1 alone fixes 7 of 19 documented failures — this IS user-visible | Architect | Each Gate's exit criteria verified and communicated |

---

## Founder Questions

Only genuine unresolved Founder-level decisions — engineering decisions already resolved (see Architectural Decisions above) are excluded.

**Q-01 — AURA: what is the real state?**
The Constitution describes AURA as having 17 implemented subsystems, 11 pending agents, and a ~40-chapter canonical document. The audit found a stub README, an integration API emitting to nowhere, and no cognitive-loop code. Is AURA aspirational (the Constitution describes a target, not current state), or was a prior version lost or moved? If aspirational, Gate C-7 builds it from scratch with accurate expectations — this is the plan's working assumption pending Founder confirmation.

**Q-02 — ARCHITECTURE_LOCK Rule 12 vs. Constitution §15.**
Rule 12 prohibits autonomous initiative outright. Constitution §15 calls for "initiative and curiosity within safe boundaries." These are directly contradictory. Which takes precedence? If the Constitution wins, `ARCHITECTURE_LOCK.md` needs an amendment. If the lock wins, the companion vision's initiative is not achievable under current rules. Resolution is required before initiative-taking behavior is implemented in Gate C-7 — it does not block the rest of the plan.

**Q-03 — Is the full companion vision in scope for this convergence?**
Constitution §15 describes persistent reasoning, continuous reflection, evolving identity, goal prioritization, confidence estimation, initiative, and self-evaluation. The current system is a command-processing assistant with LLM integration. Are Gates C-1 through C-7 the right sequence toward that vision, or is there additional guidance needed on what "companion" means in practice for the near term?

**Q-04 — What is the target deployment model?**
KIO currently runs as a Telegram bot on a desktop machine. The Constitution states "local-first where practical." Should convergence prioritize the current single-machine desktop model, or prepare for a server-based/always-on deployment? This affects default assumptions about resource budgets, network availability, and persistence — a decision with real switching cost, not a preference.

**Q-05 — Snapshot archive disposition.**
16 snapshot directories (~1.3 GB) preserve historical states across Gates 0–4E. Can these be archived to cold storage and removed from the working tree, or do they serve an active reference purpose?

---

## Gate Roadmap

The canonical implementation sequence. Gates are as already established — none invented here.

### Gate C-1 — Central Context Manager

- **Purpose:** Replace six competing state systems with one context authority.
- **Scope:** `SessionState`, `ConversationContext`, `ContinuityState`, `MediaEntityMemory`, `ArtifactMemory`, `MediaContext`, and `IntegrationAdapter`'s continuity logic.
- **Subsystems touched:** `mini_kio/llm/session_state.py`, `mini_kio/llm/conversation_context.py`, `IntegrationAdapter`, runtime pre-route logic.
- **Dependencies:** None.
- **Entry criteria:** None — first Gate.
- **Exit criteria:** Single `ContextManager` replaces all six state sources. All continuity/cross-domain tests pass.
- **Validation:** Engineering OS §5 (runtime), §8 (regression — all 7 context-bleed scenarios specifically).
- **Definition of Done:** Engineering OS §11, applied to the Context Manager: zero orphaned duplicate state implementations remain.
- **Expected constitutional improvement:** Directly resolves C-04; is the load-bearing prerequisite for Constitution §15's "contextual understanding."
- **Duration estimate:** 1 week. **Risk:** Low.

### Gate C-2 — Capability Registry (Routing Decoupling)

- **Purpose:** Replace hardcoded routing with discoverable capability registration.
- **Scope:** `_dispatch_command()`'s 422-line if/elif chain.
- **Subsystems touched:** `command_router.py`, `desktop_intelligence.py` routes, MCP tool routes.
- **Dependencies:** Gate C-1 (unified context for capability state).
- **Entry criteria:** Gate C-1 exit criteria met.
- **Exit criteria:** `_dispatch_command()` no longer exists as an if/elif chain; all existing commands route identically through `CapabilityRegistry.find()`.
- **Validation:** Engineering OS §5, §8 — parallel-run comparison of old vs. new routing outputs (Risk R-02's mitigation).
- **Definition of Done:** Engineering OS §11; capability-based routing satisfies Constitution §6 principle 6 directly.
- **Expected constitutional improvement:** Resolves the "observable and explainable" gap in routing; unblocks Gate C-3.
- **Duration estimate:** 1–2 weeks. **Risk:** Medium.

### Gate C-3 — Planning Layer Wiring

- **Purpose:** Connect the already-built planning layer to the routing path.
- **Scope:** `executive.py`, `task_engine.py`, `orchestrator.py`.
- **Subsystems touched:** `dispatch_channel_input()`, the Goal dataclass from Gate C-2.
- **Dependencies:** Gate C-2 (capability registry enables planning-aware routing).
- **Entry criteria:** Gate C-2 exit criteria met.
- **Exit criteria:** Multi-step commands ("open notepad and type hello") decompose and execute correctly through the planning layer.
- **Validation:** Engineering OS §5, §6 (real Telegram multi-step goal validation).
- **Definition of Done:** Engineering OS §11; resolves C-03.
- **Expected constitutional improvement:** Direct progress on Constitution §15's "persistent planning" and "Goal Prioritization Model."
- **Duration estimate:** 1 week. **Risk:** Medium.

### Gate C-4 — LLM Response Separation

- **Purpose:** Replace the monolithic response prompt with a deterministic, verifiable pipeline.
- **Scope:** `conversation_responder.py`.
- **Subsystems touched:** Memory retrieval, response formatting, self-verification.
- **Dependencies:** Gate C-1 (clean context for memory retrieval), Gate C-3 (clean planning for execution reporting).
- **Entry criteria:** Gates C-1 and C-3 exit criteria met.
- **Exit criteria:** Memory facts injected deterministically; response format is template-based with LLM used only for content generation; self-verification gate in place.
- **Validation:** Engineering OS §5, §6, §8.
- **Definition of Done:** Engineering OS §11; resolves the composition-over-duplication gap in this module.
- **Expected constitutional improvement:** Directly supports Constitution §15's "self-evaluation" via the new `verify(goal, response)` gate.
- **Duration estimate:** 1 week. **Risk:** Medium.

### Gate C-5 — Provider Consolidation & Adapter Cleanup

- **Purpose:** Eliminate duplicate provider infrastructure.
- **Scope:** `backup_llm/`, the two `provider_base` interfaces, adapter stub cleanup.
- **Subsystems touched:** `mini_kio/core/config.py`, `mini_kio/llm/provider_base.py`, `providers/provider_base.py`, `adapters/`, `governance/`/`voice/`/`avatar/`/`distributed/` READMEs.
- **Dependencies:** None — can run in parallel with C-1 through C-4.
- **Entry criteria:** None.
- **Exit criteria:** One LLM provider chain; one disambiguated `CapabilityProvider` interface; `backup_llm/` removed.
- **Validation:** Engineering OS §5, §8 (all existing tests pass unchanged).
- **Definition of Done:** Engineering OS §11; resolves C-02a and C-06.
- **Expected constitutional improvement:** Resolves duplication flagged by Constitution §6 principle 5.
- **Duration estimate:** 3–4 days. **Risk:** Low.

### Gate C-6 — Architecture Documentation Reconciliation

- **Purpose:** Make architecture documentation match the converged reality.
- **Scope:** `STRUCTURE_V2.md`, `MODULE_OWNERSHIP.md`, `OWNERSHIP_MATRIX.md`, `ARCHITECTURE_LOCK.md` (if C-07/Q-02 resolution changes Rule 12), snapshot archival.
- **Subsystems touched:** Documentation only — no runtime code.
- **Dependencies:** Gates C-1 through C-5 (architecture must match reality before it's documented).
- **Entry criteria:** Gates C-1–C-5 exit criteria met.
- **Exit criteria:** Documentation audit finds no contradictions with the codebase; 16 snapshot directories archived to cold storage.
- **Validation:** Documentation cross-check against the Contradiction Log — every entry above should be marked resolved or explicitly still open.
- **Definition of Done:** Engineering OS §11.
- **Expected constitutional improvement:** Resolves C-02 fully; closes the "observable and explainable" gap at the documentation layer, not just the code layer.
- **Duration estimate:** 2–3 days. **Risk:** Low.

### Gate C-7 — AURA Foundation

- **Purpose:** Build AURA's actual cognitive loop, starting from its real current state (a stub).
- **Scope:** AURA Layers 0–6 (Observation, Knowledge, Belief, Reasoning, Planning, Action, Reflection); Layers 7–9 (Identity, Meta-cognition, Growth) deferred to architecture-only.
- **Subsystems touched:** `aura/`, `aura_integration.py`, `observation_bus.py`, `FactRepository`.
- **Dependencies:** Founder decision on Q-02 (blocks only the Action/initiative layer specifically, per Engineering OS §12); Gate C-1 (context input to AURA); Gate C-4 (clean response pipeline for observations).
- **Entry criteria:** Gates C-1 and C-4 exit criteria met. Founder decision on Q-02 required before Layer 5 (Action) specifically.
- **Exit criteria:** A working cognitive loop (Observe → Know → Believe → Reason → Plan → Act → Reflect) for at least one domain, demonstrably improving KIO's behavior over repeated interactions.
- **Validation:** Engineering OS §6 (10+ real Telegram interactions in one test domain, measuring behavioral improvement).
- **Definition of Done:** Engineering OS §11; resolves C-01 by replacing the aspirational description with an actual, if initially narrow, implementation.
- **Expected constitutional improvement:** The single largest step toward Constitution §15 — this Gate is where KIO stops being a command processor and starts being the continuity layer the Constitution describes.
- **Duration estimate:** 2–3 weeks post-Founder decision. **Risk:** High.

---

## Gate Dependencies

```
C-1 (Context Manager)
  │
  ▼
C-2 (Capability Registry) ──┐
  │                          │
  ▼                          │
C-3 (Planning Wiring)        │
  │                          │
  ▼                          │
C-4 (Response Separation)    │
  │                          │
  └──────────┬───────────────┘
             ▼
   C-6 (Doc Reconciliation)
             ▲
             │
   C-5 (Provider Consolidation) ── runs independently, parallel to C-1–C-4

   C-7 (AURA Foundation) ── depends on C-1 + C-4, gated additionally
                             on the Q-02 Founder decision for its
                             Action/initiative layer specifically
```

C-5 is the only Gate with no upstream dependency — it can start immediately, in parallel with C-1. C-6 is the only Gate that depends on everything else being substantially done, since its job is to describe the converged state accurately. C-7 is the only Gate blocked, even partially, on a Founder decision — and per the Engineering OS's scoped-escalation rule, only its Action/initiative layer is blocked, not the whole Gate.

---

## Capability Convergence Roadmap

How each cross-cutting capability moves from its current fragmented state to one coherent implementation:

- **Context:** Six systems (`SessionState`, `ConversationContext`, `ContinuityState`, `MediaEntityMemory`, `ArtifactMemory`, `MediaContext`) → one `ContextManager` (Gate C-1, D-13). This is the foundational convergence — nearly everything else depends on it having happened first.
- **Routing:** One 422-line if/elif chain → a discoverable `CapabilityRegistry` (Gate C-2, D-11). Existing routes preserved exactly; new capabilities register instead of requiring a code edit to a central file.
- **Planning:** Fully built but disconnected (`executive.py`, `task_engine.py`, `orchestrator.py`) → wired into the routing path as Layer 4 (Gate C-3, D-16). No new planning code — this is pure integration.
- **Response generation:** One monolithic LLM prompt → separated "what to say" (deterministic, memory-driven) from "how to say it" (LLM-generated), with a self-verification gate (Gate C-4).
- **Providers:** Two LLM chains + two `provider_base` interfaces → one LLM chain (D-10), one renamed `CapabilityProvider` protocol disambiguated from the LLM ABC (D-08) (Gate C-5).
- **Memory:** `FactRepository`/`MemoryRepository` already work and are unchanged by this plan — they become the deterministic source Gate C-4's response pipeline reads from, and the eventual substrate AURA's Knowledge layer (Gate C-7) builds on.
- **Browser:** Two implementations (`mini_kio/core/browser_operator.py` + top-level `browser/`) converge into the already-production `browser_runtime/` (D-06). `browser_runtime/` itself does not change — it's the target, not a participant in the merge.
- **MCP:** Already a single, production-grade implementation (`mcp_runtime/`) — no convergence action needed; it's a stable target other Gates route through, not a subject of consolidation.
- **Tool execution:** Consolidates through the same `CapabilityRegistry` as routing (Gate C-2) — tool execution is a category of capability, not a separate system, once the registry exists.
- **Safety:** `execution_boundary.py` and `ARCHITECTURE_LOCK.md` Rules 1–11 are the one subsystem explicitly excluded from convergence work — they're already coherent and are preserved as-is throughout every Gate. Rule 12 alone is under active dispute (C-07/Q-02) and is handled separately, as a Founder decision, not an engineering convergence.
- **AURA:** Stub → real cognitive loop (Gate C-7), built on the context (C-1), planning (C-3), and response (C-4) convergences that precede it. AURA is the capstone convergence — it's what the rest of the roadmap is a prerequisite for, not a parallel track.

---

## External Repository Convergence

For every cloned repository under `external/`. Per Constitution §6 ("capability-based over implementation-specific") and D-15, the default is **no integration** until a currently-open gap genuinely maps to one.

| Repository | Purpose | Capabilities Worth Extracting | Capabilities to Ignore | Integration Approach | Why Architecture Should NOT Be Copied |
|---|---|---|---|---|---|
| **agency-swarm** | Multi-agent orchestration framework | Agent coordination patterns, if/when Gate C-7's AURA agents need multi-agent structure | Its own runtime, event system, and provider abstractions — KIO already has these | Adapter stub only (already exists); extract a coordination *pattern* into AURA's agent layer if C-7 proves the need | KIO already has a runtime, routing, and provider layer; importing agency-swarm's would recreate the exact fragmentation this plan exists to remove |
| **agent-reach** | Web reading and search | `read_url()` and `search()` patterns — genuinely useful, low-risk primitives | Its own session/state management | Wire the two functions through `CapabilityProvider` only if a Gate needs live web-reading (none currently do) | The functions are useful; the surrounding framework is not needed for two primitives |
| **agentic-inbox** | Not yet evaluated against an open gap | None identified | Entire repository, for now | Do not integrate | No currently-open gap maps to this repository |
| **cua** | Computer-use provider | Already partially wired — the CUA provider exists and routes through the capability system today | N/A — already integrated at the appropriate scope | Already correctly integrated; no further action needed | N/A — this is the model for how integration should look elsewhere |
| **LibreChat** | Chat UI/backend framework | Possibly UI patterns for a future non-Telegram channel | Its entire backend architecture — KIO's runtime is authoritative | Adapter is currently empty; do not build until a second channel is actually prioritized (relates to Q-04) | LibreChat is a complete chat application; KIO needs a channel adapter, not a second application |
| **Open-LLM-VTuber** | Voice/avatar-driven interaction | Possibly relevant to the empty `voice/`/`avatar/` placeholders, far in the future | Its full runtime and rendering pipeline | Not evaluated until `voice/`/`avatar/` leave placeholder status | Same fragmentation risk as LibreChat — extract the technique, not the application shell |
| **openwork** | Workspace/session/runtime patterns | The runtime/workspace/session/mcp submodule split may inform how KIO's own `workspace/` (D-07) gets wired in Gate-adjacent work | Its own MCP implementation — KIO's `mcp_runtime/` is already production-grade and authoritative | Adapter stub exists (interface defined, not wired); revisit if Gate C-6 documentation work surfaces a genuine workspace-integration gap | KIO's `workspace/` V2 module and `mcp_runtime/` already exist; adopting openwork's versions would reintroduce exactly the duplication D-07 is meant to resolve |
| **Scrapling** | Structured web extraction | Extraction method patterns (12 sub-modules define the interface) — worth mining if a Gate needs robust scraping beyond `agent-reach`'s simple `search()`/`read_url()` | Its own request/session layer | Keep as partial stub; extract specific extraction techniques only if a proven gap emerges | The extraction *technique* is valuable; the surrounding scraping framework duplicates capability KIO's browser layer already covers |
| **shepherd** | Not yet evaluated against an open gap | None identified | Entire repository, for now | Do not integrate | No currently-open gap maps to this repository |
| **kio_test_server** | MCP test server | Already active — used for MCP runtime testing | N/A | Keep as-is; this is test infrastructure, not a capability-convergence candidate | N/A — already correctly scoped |

**General rule across all rows:** extract the pattern, never the folder. A repository "worth integrating" contributes a technique to an existing KIO seam (`adapters/`, `CapabilityProvider`, `CapabilityRegistry`) — it never becomes a second parallel implementation of something KIO already has authoritatively (routing, context, providers, browser, MCP).

---

## Current Technical Debt

Prioritized register, consolidated from the Current-State Map's Tech Debt notes and the Contradiction Log above.

### Critical
- **AURA absence** (C-01) — the Constitution's central continuity-layer claim doesn't match the repository. Blocks the companion vision most directly.
- **Hardcoded routing** (`_dispatch_command()`, 422 lines, 20+ branches) — every new capability currently requires editing this file; no discoverability.

### High
- **Two runtime generations coexisting** (C-02) — `mini_kio/core/runtime.py` vs. top-level `runtime/`. Resolved by decision (D-02/D-03), pending documentation reconciliation (Gate C-6).
- **Six competing state/continuity systems** (C-04) — the direct cause of 7 of 19 documented failure scenarios (context bleed).
- **Disconnected planning layer** (C-03) — fully-built code (`executive.py`, `task_engine.py`, `orchestrator.py`) sitting unused.

### Medium
- **Two `provider_base` interfaces sharing a name** (C-02a) — resolved by decision (D-08), pending Gate C-5 execution.
- **Two diverging LLM provider chains** (C-06) — resolved by decision (D-10), pending Gate C-5 execution.
- **Monolithic response prompt** (`conversation_responder.py`) — intent, memory, formatting, and character all mixed into one LLM call, resolved by plan (Gate C-4).
- **Adapter framework with zero live integrations** (C-05) — not urgent; framework works, no proven gap requires activation yet.

### Low
- **Stale path reference** (`docs/CURRENT_TASK.md`, C-08) — trivial, one-line fix.
- **Snapshot archive bloat** (~1.3 GB, 16 directories) — a storage/hygiene issue, not a correctness issue; blocked only on Q-05.

---

## Final Target State

When Gates C-1 through C-7 close, the repository looks like this:

- **One context authority** (Layer 3's `ContextManager`) — no competing state systems, no context bleed from the 7 documented scenarios.
- **One discoverable capability registry** (Layer 2) — new capabilities register instead of requiring an edit to a central dispatch file.
- **The planning layer is live** — multi-step goals decompose and execute through `executive.py`/`task_engine.py`/`orchestrator.py`, not just LLM fallback.
- **One provider chain, one disambiguated capability-provider interface** — no configuration drift between `backup_llm/` and `mini_kio/llm/`, no naming collision between the two `provider_base`s.
- **Documentation matches reality** — `STRUCTURE_V2.md`, `MODULE_OWNERSHIP.md`, and the Contradiction Log accurately describe the converged codebase, not an aspirational or historical one.
- **AURA has a real, working cognitive loop** for at least one domain, built from its actual starting point rather than an assumed 40-chapter document, with the Action/initiative layer resolved one way or the other per the Q-02 Founder decision.
- **Browser and MCP remain exactly as they are today** — both were already production-grade at the start of this plan and needed no convergence work themselves; they're targets other layers route through, not subjects of it.
- **Every existing test still passes, at or above the 97.8% baseline**, and the 19 documented failure scenarios are a permanent, passing regression suite.

At that point, per `KIO_ENGINEERING_OS.md`'s Project End State, engineering shifts from convergence mode to maintenance mode. This document and the Engineering OS both become historical records of how KIO got there — not active operating instructions for what comes after.

---

## Estimated Timeline

C-1 through C-6 (architecture convergence): 6–8 weeks. C-7 (AURA foundation): 2–3 weeks post-Founder decision on Q-02. **Total: 8–11 weeks**, contingent on Founder responses to Q-01 through Q-05 arriving without extended delay — none of which, per the Engineering OS's scoped-escalation rule, block more than their directly-affected slice of work.

---

## Deliverables Checklist

- [x] Repository audit consolidated (no re-audit performed)
- [x] Current-State Map consolidated, with Current Implementation / Constitution Target / Gap / Recommendation for every subsystem
- [x] Unified Target Architecture consolidated
- [x] Convergence Principles stated
- [x] Contradiction Log consolidated (8 items, C-01–C-08)
- [x] Architectural Decisions consolidated (16 items, D-01–D-16)
- [x] Risks consolidated (7 items, R-01–R-07)
- [x] Founder Questions consolidated (5 items, Q-01–Q-05, no resolved-engineering-decisions included)
- [x] Gate Roadmap consolidated (7 Gates, C-1–C-7, no new Gates invented)
- [x] Gate Dependencies mapped
- [x] Capability Convergence Roadmap written
- [x] External Repository Convergence detailed, per repository
- [x] Current Technical Debt prioritized (Critical/High/Medium/Low)
- [x] Final Target State described
- [ ] Ready for implementation approval ← **YOU ARE HERE**
