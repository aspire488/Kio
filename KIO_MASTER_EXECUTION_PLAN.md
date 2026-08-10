# KIO MASTER EXECUTION PLAN v2.0 (Final Architectural Revision)

Status: For Founder Approval
Authority: This plan describes execution only. KIO_CANON.md (a.k.a. KIO_IDENTITY_CANON.md) remains the single source of truth for identity, capabilities, runtime facts, and architectural facts. No second canonical document is introduced by this plan.

Governing Documents:
- KIO_CONSTITUTION.md — enduring principles, amendment via Founder Decision only
- KIO_IDENTITY_CANON.md (KIO_CANON.md) — sole source of identity truth
- This plan — sole source of execution sequencing and capability gates
- MASTER_CONVERGENCE_PLAN.md — repository evidence & convergence decisions (historical reference)
- KIO_Implementation_Plan.md — implementation slices (retained as the Slice ledger; this plan aligns Tier-level capability gates to those Slices)

Precedent rules (Founder-imposed on this revision):
1. Reality Override: If any statement in the prompt that produced this plan conflicts with verified repository evidence, the repository wins. Contradictions are surfaced and classified, never silently resolved.
2. No New Architecture: The objective is convergence, not invention. No new runtimes, managers, registries, or orchestration layers may be introduced unless repository evidence proves they are absolutely required.
3. Delete over Create: Delete, merge, consolidate, simplify before introducing new files. Repository complexity should decrease after every Tier. No new subsystem without evidence.
4. KIO_CANON.md remains the single source of truth. No second canonical document may be introduced.
5. Force ownership for every subsystem: each subsystem entry ends with Canonical Owner / Consumes / Produces / Depends On / Used By / Future Owner / Retirement Plan.
6. Architectural minimalism: Every newly proposed subsystem must answer — Why can't an existing subsystem own this? Why is this impossible inside current ownership? What duplication does it remove? What is its blast radius?
7. Convergence metric at end of every Tier: Files retired, duplicate systems removed, ownership conflicts resolved, architectural debt reduced, net subsystem count, net documentation count, canon amendments required, validation coverage, user-visible capability increase.

---

## SECTION 0 — MANDATORY PRE-FLIGHT VERIFICATION (Gate Result)

### 0.1 — AURA Completeness Claim

Claim under review: "AURA's architecture is ~95% complete and implementation ~80% complete, with 17 cognitive systems already built."

Search for the referenced "AURA discovery report":
- Searched *.md for *AURA*DISCOVERY*, *aura_discovery*, *aura_report*, *aura_audit* across the project root, docs/, mini_kio/, and aura/ directories.
- Result: no such discovery report exists in this repository. No file matches any of those patterns.

Independent spot-checks of the 17 named subsystems against the actual filesystem:

| Subsystem claimed "built" | Evidence found | Verdict |
|---|---|---|
| aura/ directory | aura/README.md (35 lines, 512 bytes, placeholders only: "Defines the purpose…", "Core aura functionality", "Roadmap items.") | EMPTY STUB |
| mini_kio/core/aura/ | cmd /c "dir mini_kio\aura" → 0 File(s) 0 bytes | EMPTY |
| mini_kio/aura/ | cmd /c "dir mini_kio\aura" → 0 File(s) 0 bytes | EMPTY |
| aura_integration.py | mini_kio/execution/aura_integration.py (200 lines) — well-designed API surface that emits structured observations via observe() calling mini_kio.core.runtime.aura_emit_observation() | REAL CODE, BUT EMITS TO A RECEIVER THAT DOES NOT EXIST (verified — the function returns None, no consumer) |
| Observation, Memory, Knowledge, Beliefs, World Model, Identity, Goals, Reasoning, Oracle, Reflection, Learning, Strategy, Confidence, Continuity, Opinions, Stewardship, Proactivity | All 17 return 0 hits in mini_kio/aura/, aura/, or any matching module | NOT FOUND |

Result: **UNVERIFIED CONTRADICTION.** The 95%/80% claim is not supportable from the audited repository. The verified evidence (also recorded in MASTER_CONVERGENCE_PLAN.md line 41, CONVERGENCE_PLAN_CHANGELOG.md Change 1, KIO_IDENTITY_CANON.md CAP.AURA.001) is that:
- aura/README.md is a 35-line stub.
- mini_kio/aura/ is an empty directory.
- aura_integration.py is a real, well-designed 200-line integration API that emits observations to a receiver that isn't there yet.
- No cognitive-loop code exists anywhere in the repository.
- The AURA canonical architecture document (~40 chapters per KIO_CONSTITUTION.md §1) was not located.

This plan therefore treats all AURA capability claims as UNVERIFIED CONTRADICTION. Where AURA capability descriptions are necessary, they appear tagged UNVERIFIED or ROADMAP — never CURRENT. The Founder's CAP.AURA.001 canon entry ("EARLY-STAGE … 17/28 subsystems implemented, 11 agents unactivated … Any specific behavior claim defaults ROADMAP unless independently verified") is the authoritative position and is preserved verbatim.

### 0.2 — Aurora (Acer) / Victus Infrastructure

Claim under review: Aurora is the permanent cognitive home; Victus is the engineering workspace; stack includes FastAPI, Docker, Redis, PostgreSQL, Neo4j, ChromaDB.

Search results:
- grep "Aurora|Victus|Acer" across all *.md files in project root, docs/, mini_kio/: 0 matches.
- grep "aurora|victus|acer" across all *.py files (excluding .venv/, external/, node_modules/): 0 matches.
- grep "Neo4j|ChromaDB" across all *.md files (excluding skill examples in .agent-skills/): 0 matches in architectural docs. Only present inside the ponytail rate-limiting example and skill benchmark writeups.
- Search for Redis: only referenced once in KIO_Implementation_Plan.md:1150 as a ponytail: ceiling comment ("add Redis/valkey when multi-process runtime requires it"), not as deployed infra.
- Search for FastAPI: only present in .agent-skills/ponytail/ skill examples (rate-limit, benchmarks). No FastAPI service in mini_kio/, runtime/, api_audit/, internal_api/, adapters/, or any deployment config.
- Search for docker-compose*, Dockerfile: not present in any non-venv, non-external path.

Result: **UNVERIFIED CONTRADICTION / PROPOSED.** The Aurora/Victus split has no corroborating evidence in this repository — no deployment configs, no .env hostnames, no Docker/FastAPI/Redis/PostgreSQL/Neo4j/ChromaDB wiring, no host references, no deployment scripts.

This plan therefore treats Aurora/Victus as PROPOSED ARCHITECTURE (the prompt's intent), never as CURRENT state. Throughout the document, Aurora is framed as "intended to become KIO's permanent cognitive home" and Victus as "the engineering workstation currently in use" (Victus-as-current-workstation is inferred from the existence of a working dev environment on this machine — verified by the existence of .venv/, tests/, runtime_logs/, .playwright-mcp/, .chrome_validation_profile/). No claim about Aurora's deployed state is made.

### 0.3 — Tagging Convention Applied Throughout

Every subsystem, capability, or infrastructure claim below carries one of:
- **CURRENT** — verified against the repo, with evidence cited (file path + line range or measurement).
- **PROPOSED/ROADMAP** — the prompt's intent, not yet built or verified.
- **UNVERIFIED CONTRADICTION** — two sources disagree; both are surfaced, neither is silently resolved.

No file paths, line numbers, or subsystem names appear without evidence.

---

## SECTION 1 — AUTHORITATIVE ARCHITECTURAL CLARIFICATION

```
User
 ↓
KIO (Interaction & Executive Layer)
 ↓
AURA (Cognitive Operating System — Observe→Know→Believe→Reason→Plan→Act→Reflect)
 ↓
Execution Fabric
```

**KIO** = Interaction & Executive Layer. Routes user-facing interfaces (Telegram, Discord, CLI, future Desktop/Voice/Mobile), validates inputs, classifies intent, gates safety, dispatches capabilities, composes responses, persists continuity references.

**AURA** = Cognitive Operating System. The continuity loop sitting above KIO. Per KIO_CONSTITUTION.md §1: "Observe → Know → Believe → Reason → Plan → Act → Reflect across a Layer 0–9 hierarchy." Per KIO_IDENTITY_CANON.md Section 4: "AURA (cognitive loop, sits above KIO)". KIO consumes cognition from AURA via the integration API (mini_kio/execution/aura_integration.py); Execution Fabric is downstream of cognition.

IMPORTANT — verified state vs. prompt framing:
- KIO_CONSTITUTION.md §1 frames AURA as "above KIO" with 17 subsystems implemented, 11 pending activation, Orchestrator Agent next priority.
- KIO_IDENTITY_CANON.md CAP.AURA.001 (status: EARLY-STAGE, Verified By: Repository, Manual Validation) states: "17/28 subsystems implemented, 11 agents unactivated, Orchestrator inactive. Any specific behavior claim defaults ROADMAP unless independently verified."
- The prompt's "AURA's architecture is ~95% complete and implementation ~80% complete" claim is UNVERIFIED per Section 0.1.
- This plan therefore presents AURA capability as ROADMAP at the cognitive-loop level, while acknowledging the 200-line integration API surface (aura_integration.py) and the integration intent (observe/request_*/report_*) as CURRENT — they exist and are wired to aura_emit_observation even though no receiver consumes them yet.

The relationship is canonical, the implementation is not. Architectural framing is accepted; capability claims default to ROADMAP per Founder canon policy.

---

## SECTION 2 — SYSTEM TOPOLOGY (with annotated boundaries)

```
Users
   │
   ├────────────┬────────────┐
   │            │            │
Telegram     Desktop      Voice/UI
(CURRENT)  (ROADMAP)    (ROADMAP)
   │            │            │
   └────────────┼────────────┘
                │
              KIO
   (Executive & Interaction Layer)            ← CURRENT (mini_kio/core/runtime.py LOCKED)
   ↕ Interacts with AURA via aura_integration.py (200 lines, CURRENT surface; receiver UNVERIFIED)
                │
       Cognitive API / Event Bus
   ↕ mini_kio/execution/aura_integration.py (CURRENT API surface, no live consumer)
                │
              AURA
    (Cognitive Operating System — ROADMAP for the loop; the integration API is CURRENT but emits to nothing)
   ↕ Layer 0–9 hierarchy: NOT IMPLEMENTED
   ↕ 17/28 subsystems implemented per canon: UNVERIFIED (no subsystem code found in repo)
                │
   ┌────────────┼────────────┐
   │            │            │
Memory      Reasoning    World Model        ← ALL THREE: UNVERIFIED (no implementation found)
Beliefs     Reflection   Identity           ← ALL THREE: UNVERIFIED
Goals       Oracle       Learning           ← ALL THREE: UNVERIFIED
                │
        Execution Fabric
   CURRENT: mini_kio/core/execution_boundary.py, mini_kio/execution/engine.py,
            mini_kio/core/runtime.py, mini_kio/execution/capability_router.py
                │
Browser • MCP • Desktop • APIs • Automation
   Browser: CURRENT (mini_kio/runtime/browser_runtime/; reference-resolution bug class fixed 2026-08-09 via target_ref.py)
   MCP:     CURRENT infra only (mini_kio/runtime/mcp_runtime/, CAP.MCP.001)
   Desktop: ROADMAP (mini_kio/desktop/ is empty)
   APIs:    CURRENT (provider stack + provider_registry)
   Automation: ROADMAP (n8n integration layer not present in repo)
                │
          Aurora (Acer)
     Permanent Cognitive Home              ← PROPOSED/ROADMAP (no deployment evidence in repo)

        ▲
        │
   Git / CI / Validation
        │
  Victus (Engineering Workspace)
     CURRENT: this machine — .venv/, tests/, runtime_logs/, .playwright-mcp/, .chrome_validation_profile/, .git/, .kio/
```

Annotated boundaries (separately, not just arrows):

**Data flow boundaries:**
- Users ↔ Interfaces: bidirectional. User → interface via channel-specific transport. Interface → user via channel-specific rendering.
- Interface → KIO: inbound only at runtime. Interfaces do not embed cognition.
- KIO → AURA: outbound only through aura_integration.py observe/request/report surface. KIO does not import from a not-yet-built AURA implementation.
- AURA → Execution Fabric: AURA suggests/observes/drafts; per CAP.AUTONOMY.001 + INV.006, AURA never instructs the Fabric to act autonomously.

**Ownership boundaries:**
- Interfaces own transport and rendering. They do not own cognition or execution.
- KIO owns dispatch, safety, capability resolution, response composition.
- AURA owns memory, beliefs, reasoning, world model, identity, goals, reflection, learning (subject to Section 0.1 verification of what currently exists — currently the API surface only).
- Execution Fabric owns tools, providers, browser, MCP, file system, desktop automation.

**Persistence boundaries:**
- Per-interface session scratch state lives only inside the interface's own module (e.g. Telegram chat id in mini_kio/interfaces/models.py).
- Cross-session continuity lives in mini_kio/memory/memory_store.py (CURRENT), mini_kio/backend/db.py + mini_kio/backend/repositories/ (CURRENT), and AURA's intended knowledge graph (ROADMAP).
- The Canon (KIO_IDENTITY_CANON.md) is version-controlled, not runtime-persisted.

**Cognition boundaries:**
- AURA cognition flows down via observation events emitted from KIO execution.
- AURA cognition flows up to KIO only via request_* function return values (currently returning graceful defaults like {"success": False, "message": "AURA not available", "state": {}}).

**Execution boundaries:**
- Only the Execution Fabric executes (per CAP.AUTONOMY.001 + INV.006).
- All execution is gated by mini_kio/core/execution_boundary.py (CURRENT, LOCKED).
- All cross-process capabilities route through mini_kio/execution/capability_router.py (CURRENT) or mini_kio/runtime/mcp_runtime/ (CURRENT).

**Engineering boundaries:**
- Victus (this machine): implementation, testing, simulation, validation, performance benchmarking. Lives under .venv/, tests/, runtime_logs/, .playwright-mcp/, .chrome_validation_profile/.
- Aurora (Acer, PROPOSED): intended permanent cognition home for memories, databases, event bus, reasoning runtime. Not present in the audited repo as an environment; this is the prompt's intent and is treated as ROADMAP.
- All engineering artifacts move Victus → Git → Aurora via the development lifecycle in Section 4.

---

## SECTION 3 — AURA STATE (verified)

Per Section 0.1, the prompt's claim that AURA is 80%+ implemented is UNVERIFIED. The verified state is:

| AURA concern | Verified state | Tag |
|---|---|---|
| AURA canonical architecture document (~40 chapters) | Not found in filesystem | ROADMAP / UNVERIFIED |
| Layer 0–9 hierarchy code | Not found in aura/, mini_kio/aura/, or anywhere else | UNVERIFIED |
| 17/28 subsystems implemented | No subsystem implementations found | UNVERIFIED (canon says "EARLY-STAGE") |
| 11 agents pending activation, Orchestrator next | No agent implementations found | UNVERIFIED |
| Observation loop | Surface CURRENT (200-line aura_integration.py emits structured observations); receiver UNVERIFIED | PARTIAL |
| Memory, Knowledge, Beliefs, World Model, Identity, Goals, Reasoning, Oracle, Reflection, Learning, Strategy, Confidence, Continuity, Opinions, Stewardship, Proactivity | Each request_*() function exists in aura_integration.py but each returns graceful default or None; no actual implementation behind any of them | ROADMAP for the implementations; the integration seam itself is CURRENT |
| Autonomy Policy (CAP.AUTONOMY.001 + INV.006) | CURRENT (Founder Decision) — AURA observes/suggests/drafts/warns; never instructs the Execution Fabric to act on its own | CURRENT |
| aura/README.md | 35-line stub | ROADMAP |

Contradiction surfaced (do not resolve silently):
- KIO_CONSTITUTION.md §1 says "17 subsystems are implemented."
- KIO_IDENTITY_CANON.md CAP.AURA.001 says "17/28 subsystems implemented" with status EARLY-STAGE.
- Audited repository: no subsystem implementations exist.

This plan does NOT invent a resolution. It surfaces the contradiction and labels the work accordingly. Per INV.002 (KIO never presents a ROADMAP fact as CURRENT), every claim about AURA cognitive capability in this plan defaults to ROADMAP until independently verified during Tier execution.

---

## SECTION 4 — HOME VS WORKSPACE (Aurora vs Victus)

| Boundary | Aurora (Acer) — PROPOSED | Victus (this machine) — CURRENT |
|---|---|---|
| Role | Permanent cognitive home | Engineering workstation |
| Hosts | Cognition, memories, knowledge graph, beliefs, reasoning runtime, world model, identity, continuity, event bus, FastAPI service, Docker containers, Redis, PostgreSQL, Neo4j, ChromaDB | Source code, virtual env, tests, simulations, validation harnesses, CI runners, performance bench, release-candidate generation |
| Persists across | KIO interface restarts; user device switches; long-term continuity | Repository check-ins only; not a runtime persistence layer |
| Verifies | Verified in repo? No — grep "Aurora\|Victus\|Acer" returns 0 hits outside this plan; grep "Neo4j\|ChromaDB" returns 0 hits in any non-skill, non-venv, non-external path. Redis referenced once as a ponytail: ceiling comment, not as deployed infra. FastAPI only present in ponytail skill examples | Verified by existence of .venv/, tests/, runtime_logs/, .playwright-mcp/, .chrome_validation_profile/, .kio/, .serena/, .gitnexus/, .opencode/, .claude/, .telegram_sessions/ |
| Engineering access | Remote (TBD per Tier 5) | Local |
| Tag | PROPOSED/ROADMAP | CURRENT |

Development lifecycle (intended, ROADMAP):

```
Victus (build/test) → Git (commit/CI) → Aurora (deploy/cognition-persist) → KIO Interfaces → Users
```

This lifecycle is the prompt's intent. It is not enforced today because Aurora does not exist as a verified environment.

Important constraint (current state): Until Aurora is provisioned and verified, all cognition-persistence targets remain on this machine (Victus) in the existing mini_kio/backend/db.py, mini_kio/memory/memory_store.py, and runtime_logs/ paths. Tier 5 must verify that cognition has actually migrated off Victus before declaring Aurora "live."

---

## SECTION 5 — MULTI-INTERFACE REFRAME

KIO is multi-interface by design (per MIS.004, ARCH.003, ROAD.003). Telegram is currently the only shipped interface (verified: mini_kio/interfaces/ contains only models.py and terminal.py, plus the Telegram channel wiring inside command_router.py). The architecture must not require Telegram at runtime.

Verified interface surface:
- mini_kio/interfaces/models.py — interface models (CURRENT)
- mini_kio/interfaces/terminal.py — terminal/CLI interface (CURRENT)
- Telegram channel: CURRENT (bot running per bot_stderr.log and bot_stdout.log)
- Discord transport: PRESENT at mini_kio/platform/discord_transport.py (CURRENT transport; per DISCORD_INTEGRATION_REPORT.md, status must be re-verified before claiming shipping)
- CLI: CURRENT (terminal.py + the bot-stdin pattern)

ROADMAP interfaces:
- Desktop (full UI) — mini_kio/desktop/ is empty; UI architecture unbuilt
- Voice — mini_kio/voice/ does not exist
- Browser (as an interface, distinct from browser-as-capability)
- Mobile — mini_kio/mobile/ does not exist
- Wearables — mini_kio/wearables/ does not exist

Architectural principle (no change to canonical): Every interface is a thin adapter that translates transport → Intent → executes against KIO's dispatch surface → returns renderable result. No interface owns cognition.

Per ROAD.003, multi-interface expansion was deferred until ARCH.003 (capability-discovery fragmentation) is resolved. Tier 1 begins that resolution. Multi-interface expansion follows once ARCH.003 status flips.

---

## SECTION 6 — AURA INTEGRATION THROUGHOUT EVERY TIER

AURA integration is not isolated to one Tier. Each Tier names the cognitive layers that become meaningfully connected — and where the integration is API-surface only (because AURA's loop is ROADMAP, not CURRENT), the Tier names what the seam enables.

**Tier 1 — Convergence Foundation.**
- AURA-touching work: integrate aura_integration.py into the unified runtime pipeline so every execution observation is emitted through one chokepoint. Validate that graceful degradation still holds when no receiver consumes.
- AURA integration seam made observable (logging, metrics) without inventing a receiver.
- No new AURA subsystems created (delete over create).
- ARCH.003 resolution begins (capability-discovery unification, per KIO_Implementation_Plan.md Slice 6).

**Tier 2 — Execution Fabric Hardening.**
- AURA-touching work: extend aura_integration.py with structured event types for capability resolution, prerequisite gates, and identity resolution outcomes (these are observable to AURA even without a receiver).
- Cross-process event bus becomes real (runtime/ObservationBus.py per Convergence Report — exists as utility, integrate as single event authority).
- Per Slice 12 (KIO_Implementation_Plan.md): live integration and validation phase begins.

**Tier 3 — Cognition Coupling.**
- AURA-touching work: this is the Tier where AURA cognitive subsystems begin to actually receive observations and respond to requests — IF the Founder has approved AURA activation per ROAD.002 Gate C-7. Without Founder approval, this Tier delivers the cognitive seam surface only and the receivers remain placeholder returns. No AURA code is invented without canonical approval.

**Tier 4 — Deeper Cognitive Capability.**
- AURA-touching work: reflection, learning, strategy, oracle subsystems (per Tier 4 in Section 16) — gated on Tier 3's Founder-approved AURA activation status.

**Tier 5 — Production Hardening & Cross-System Validation.**
- AURA-touching work: full integration testing, production observability, Aurora (Acer) migration if verified, cross-device continuity validation.

Justification for sequencing (vs. prompt's illustrative starting point):
The prompt's illustrative Tier 1 says "Observation linkage, identity synchronization, session continuity alignment." This plan moves Observation linkage to Tier 1 (correct — it's the existing API surface, only seam integration is needed) but explicitly defers activation of deeper cognitive layers (Reasoning, Beliefs, World Model, etc.) until Tier 3+ because, per Section 0.1, no implementation exists and no canonical Founder decision activates them per ROAD.002. Inventing AURA subsystems in Tier 1 would violate the "No New Architecture" clause.

---

## SECTION 7 — PRODUCT EVOLUTION PER TIER ("What KIO becomes")

**Tier 1 — KIO becomes a coherent system (not a fragmented one)**
- Conversation quality: deterministic intent classifier returns before LLM (per Slice 3 routing repairs in KIO_Implementation_Plan.md). Misrouting cases ("Interstellar cast" type queries) no longer fall to web-summary templates.
- Continuity: unified SessionContext (per Gate C-1, already shipped per CAP.STATE.001).
- Memory: per-item retention metadata + confidence decay wired (FQ-05 per Slice 18).
- Browser: reference-resolution bug class fixed 2026-08-09 (`target_ref.py`; tab-scoped close; contextual referents; focus/switch) — live-verified; Shorts/visual/workflow remain OPEN.
- Voice/Desktop/Mobile: still ROADMAP.
- Goal management: still ROADMAP (no goals module exists — corrected 08-09; multi-step command composition lives in `command_router._execute_multi_step`).
- Knowledge: tier 1 doesn't add new knowledge; it reduces routing fragmentation.
- Automation: still ROADMAP (n8n layer not present in repo).
- Initiative: still ROADMAP per CAP.AUTONOMY.001.
- Trustworthiness: identity override policy (FQ-06, Slice 26) — KIO disagrees once, then defers.

**Tier 2 — KIO becomes resilient and observable**
- Conversation quality: response composer no longer monolithic (conversation_responder.py refactor per Convergence Report).
- Continuity: cross-process event bus works; observations survive process boundaries.
- Memory: per-tier-2 capability — memory inspection command begins to be exercisable (per MEM.002 requirement).
- Browser: reference-resolution bug class fixed 08-09; Shorts + semantic media selection remain OPEN.
- Voice/Desktop/Mobile: still ROADMAP.
- Goal management: still ROADMAP.
- Knowledge: retrieval router (mini_kio/knowledge/retrieval_router.py) becomes single authority (CURRENT today).
- Automation: still ROADMAP.
- Initiative: still ROADMAP.
- Trustworthiness: every execution observation is observable; metrics live (mini_kio/execution/metrics.py CURRENT).

**Tier 3 — KIO becomes cognitively connected (gated on AURA activation Founder Decision)**
- Conversation quality: response composer draws on AURA-style reflection if AURA is active; otherwise falls through to deterministic composition.
- Continuity: cross-device continuity seam in place (awaiting Aurora provisioning).
- Memory: AURA memory subsystem reachable per aura_integration.py request_memory() — returns real memories if AURA active.
- Browser: reference-resolution bug class fixed 08-09; remaining OPEN items (Shorts, semantic media selection) targeted here.
- Voice: still ROADMAP.
- Desktop: still ROADMAP.
- Goal management: AURA goal subsystem reachable per request_goal() — only if Tier 3 Founder approval.
- Knowledge: AURA knowledge graph reachable per request_world_model().
- Automation: still ROADMAP.
- Initiative: still ROADMAP (autonomy policy unchanged per INV.006).
- Trustworthiness: AURA suggestions/observations never act autonomously.

**Tier 4 — KIO becomes reflective and proactive**
- Conversation quality: KIO reflects on prior interactions, suggests improvements (AURA Reflection subsystem).
- Continuity: full session restoration across interfaces.
- Memory: confidence-aware retrieval; preference learning active.
- Browser: production-grade (assuming Tier 3 includes the browser ref-resolution bug fix).
- Voice: voice interface activated (per Section 9).
- Desktop: desktop foundation activated (per Section 8).
- Goal management: AURA Goals subsystem tracks multi-step goals.
- Knowledge: knowledge graph reasoning accessible.
- Automation: capability composition across multiple providers.
- Initiative: still ROADMAP (no autonomous behavior).
- Trustworthiness: every AURA-driven suggestion traceable per KIO_IDENTITY_CANON.md Section 10.

**Tier 5 — KIO becomes production-grade and continuous**
- Conversation quality: full diagnostic + introspection surface.
- Continuity: Aurora-backed cognition (if Aurora provisioned); otherwise persistent local cognition on Victus in known-good config.
- Memory: full inspection/correction/deletion UX (per MEM.001 policy).
- Browser: enterprise-ready (or scope-reduced with honest disclosure per LIM.002).
- Voice: enterprise-ready.
- Desktop: enterprise-ready.
- Mobile: companion (not flagship).
- Goal management: long-running tasks survive restarts.
- Knowledge: knowledge graph survives device migration.
- Automation: full automation center (per Section 8 Desktop).
- Initiative: still ROADMAP.
- Trustworthiness: every capability has a CAP.* ID in canon with a Verified By evidence chain.

---

## SECTION 8 — DESKTOP-FIRST ROADMAP (planning-only, no implementation)

Desktop is the long-term primary interface per the prompt's intent. The intended Desktop architecture is:

Desktop app surfaces (per Tier):
- Conversation — chat window, persistent across sessions.
- Voice — wake word, push-to-talk, voice memory, voice identity.
- Browser — embedded browser pane (reuses mini_kio/runtime/browser_runtime/).
- Timeline — chronological view of all observations, memories, actions.
- Goals — multi-step goal tracker with status, deadlines, dependencies.
- Knowledge — knowledge graph explorer.
- Memories — memory explorer with confidence decay visualization.
- Tasks — task queue with execution status.
- Plugins — plugin manager.
- Diagnostics — runtime diagnostics, log viewer, event inspector.
- Developer Mode — agent inspector, capability registry viewer, AURA seam viewer.
- Settings — preferences, credential vault access (with consent), proactivity level.
- Reasoning Visualisation — AURA reasoning trace renderer (when AURA Reasoning is active).
- AURA Status — AURA subsystem health, observation bus volume, receiver status.
- Execution Status — capability queue, execution history, current fabric state.

Architectural plan (no implementation):
- Desktop app is a thin client to KIO's existing dispatch surface (no business logic in the UI).
- Desktop uses the same aura_integration.py seam as every other interface.
- Desktop presence modes (full companion window, sidebar, floating, minimal, transparent, overlay, tray, background, invisible) per Section 22.6.
- Desktop activation (tray, hotkey, mouse corner, voice wake word) per Section 22.7.
- Hiding/visibility (auto-hide, transparency, focus mode, meeting mode, full-screen awareness) per Section 22.8.

Reuse principle: Desktop reuses mini_kio/runtime/browser_runtime/ for embedded browser, mini_kio/runtime/mcp_runtime/ for MCP tool execution, mini_kio/llm/llm_gateway.py for LLM routing, mini_kio/memory/memory_store.py for memory. No new execution layer is created in Desktop.

Tagged: ROADMAP. mini_kio/desktop/ is empty today (verified by directory listing).

---

## SECTION 9 — VOICE ROADMAP (planning-only, no implementation)

mini_kio/voice/ does not exist today (verified). Voice is full ROADMAP.

Voice capabilities (target end state):
- Speech recognition (STT) — open-source stack recommended: faster-whisper (local, GPU/CPU), whisper-cpp, or vosk (offline, lightweight). No cloud STT as default per local-first principle (MEM.003, CAP.PROVIDER.001).
- Text-to-speech (TTS) — open-source stack: piper-tts (local, fast), coqui-tts (high quality, larger model), or edge-tts (free cloud fallback, not local-first). No paid TTS as default.
- Streaming — sentence-by-sentence synthesis; first-audio latency target ≤ 500ms on local hardware.
- Interruptions — barge-in support; mid-utterance cancellation.
- Wake word — openwakeword or porcupine (Picovoice free tier for personal use).
- Low latency — VAD-driven end-of-utterance detection (silero-vad recommended).
- Local execution — all STT/TTS/VAD on Victus / Aurora hardware, no cloud round-trip for personal conversation.
- Voice personality — consistent timbre + tone aligned with KIO character knowledge (mini_kio/llm/KIO_character_knowledge.py).
- Continuous conversation — multi-turn without re-wake; turn-detection without explicit trigger.
- Natural turn-taking — silence threshold + semantic end-of-turn from LLM stream.
- Back-channeling — minimal acknowledgment sounds ("mm-hmm", "okay") on long user pauses.
- Natural pauses — LLM-stream-driven pause insertion.
- Speech timing — rate control per emotional state.
- Emotion-aware speech — pitch/energy modulation from detected sentiment (see Section 22.2).
- Context-aware speech — voice memory (named speakers, prior tone) integrated.
- Offline voice — full STT/TTS/VAD works without network.
- Noise handling — noise suppression via rnnoise or speexdsp.
- Voice confidence — STT confidence score exposed; low-confidence utterances prompt re-prompt.
- Voice activity detection (VAD) — silero-vad or webrtcvad.
- Audio routing — explicit audio device selection; per-app routing awareness.
- Conversation overlap — detect user speaking while KIO speaking; suppress or pause.
- Voice cloning (FUTURE) — explicitly gated; not Tier 5.
- Audio caching — repeated phrases cached.
- Speech adaptation — speaker-specific acoustic model adaptation over time.
- Voice accessibility — full keyboard fallback; captions always available.

Tagged: ROADMAP. No voice code in repo today.

---

## SECTION 10 — MOBILE ROADMAP (planning-only, no implementation)

mini_kio/mobile/ does not exist today (verified). Mobile is full ROADMAP.

Long-term strategy:
- Purpose: companion interface to Desktop and Aurora — quick interactions, notifications, voice mode, on-the-go continuity. Not a flagship interface.
- Architecture: thin client → KIO's existing dispatch surface. No new execution layer.
- Relationship to Desktop: mobile is the "away from desk" surface; Desktop is the deep-work surface. Same aura_integration.py seam, same mini_kio/runtime/mcp_runtime/, same LLM gateway.
- Relationship to Aurora: mobile talks to Aurora (when provisioned) for cognition persistence; on Victus during early Tiers, mobile talks to local KIO instance.
- Offline capability: mobile caches recent conversation context; offline mode degrades to local LLM (Ollama/Gemini flash local) if configured, otherwise shows offline indicator.
- Synchronization: conversation state, goals, memories, tasks sync via the same continuity path as Desktop. Aurora is the source of truth (ROADMAP).
- Notifications: proactive notifications from mini_kio/execution/aura_integration.py event stream; routed through mobile push channels (APNs/FCM).
- Quick interactions: "what's next on my list?", "send Aaron the file", "what did we decide about X?" — short, single-turn, low-latency.
- Voice mode: identical to Desktop voice (Section 9).
- Future deployment: iOS and Android via cross-platform framework (Flutter / React Native) — TBD at Tier 4+ Founder Decision.

Tagged: ROADMAP. No mobile code in repo today.

---

## SECTION 11 — BROWSER ROADMAP

Browser is the most mature execution capability (per CAP.BROWSER.001, the verified mini_kio/runtime/browser_runtime/ implementation, and the connector + media + state-verification stack).

Evolution trajectory:
1. Tool execution (CURRENT) — mini_kio/runtime/browser_runtime/ Playwright-based, 13 commands, lifecycle + crash recovery + health monitoring. **2026-08-09: the reference-resolution bug class was substantially fixed** — canonical target identity (`mini_kio/core/target_ref.py`) keeps web-app/tab targets from collapsing into the browser process; "Close it" after "Open ChatGPT" closes the ChatGPT tab (Chrome stays alive); contextual referents (it/this/that) resolve against safe stored target names; focus/switch targets browser tabs or native app windows. Live-verified on Telegram. Remaining OPEN items: YouTube Shorts control, semantic media selection, visual-understanding and workflow tiers.
2. State awareness — Track page state, navigation history, session state (per mini_kio/browser_session_registry.py, mini_kio/browser_tab_controller.py CURRENT surface). Extended 08-09 with "What's open?" (tabs + tracked running apps) and "What's playing?" (live media registry).
3. Visual understanding — screenshots + visual diff for state confirmation (via Playwright MCP, per KIO_Implementation_Plan.md).
4. Workflow execution — multi-step browser workflows with rollback.
5. Persistent browser memory — cookies, sessions, history preserved across KIO restarts (subject to MEM.001 policy: inspectable/correctable/deletable).
6. Multi-tab reasoning — KIO reasons across tabs.
7. Goal-driven browsing — KIO opens browser autonomously to fulfill user goals (still gated by INV.006 — only on explicit request).

Tagged: CURRENT for the runtime (reference-resolution bug class fixed 2026-08-09); ROADMAP for the higher tiers of capability (visual understanding, workflows, persistent browser memory, multi-tab reasoning, goal-driven browsing) and for remaining OPEN items (Shorts, semantic media selection).

---

## SECTION 12 — MCP ROADMAP

MCP runtime is CURRENT (mini_kio/runtime/mcp_runtime/ — JSON-RPC 2.0 over stdio, server connection, tool registry, executor, health monitor; CAP.MCP.001 "infra only"). Per KIO_Implementation_Plan.md §12: 8 servers, 59 tools (CRASH-ISOLATED).

MCP maturity stages (per Tier):
1. Filesystem — CURRENT (mcp_servers/ directory exists per directory listing).
2. Git — integration into development workflows.
3. Development tools — build, test, lint.
4. Office tools — calendar, mail, documents.
5. Cloud tools — Drive, OneDrive, Dropbox.
6. Custom ecosystem — community MCPs, vetted per security review (SEC.001 resource limits).
7. Future capability providers — agents-as-MCP-servers, voice-as-MCP-server.

Tagged: CURRENT for the runtime; ROADMAP for the broader ecosystem beyond the current 8 servers.

---

## SECTION 13 — COMPLETE SUBSYSTEM DEPENDENCY MAP

Each entry: Purpose / Maturity / Final vision / Dependencies / Incoming links / Outgoing links / Required completion Tier / Validation criteria / Blocking risks. Plus the owner block at the end.

### Core Runtime Subsystems

**1. Core Runtime (mini_kio/core/runtime.py)**
- Purpose: Dispatch authority, safety states, resource guarding. LOCKED v1.1.
- Maturity: CURRENT (LOCKED, 1643 lines per Convergence Report).
- Final vision: Single dispatch authority for all interfaces; capability-based over implementation-specific.
- Dependencies: execution_boundary, capability_registry, intent_classifier, session_state.
- Incoming links: Interfaces (Telegram, Discord, CLI, future Desktop/Voice/Mobile) → dispatch.
- Outgoing links: → capability_router → execution_engine → aura_integration.
- Required completion Tier: Tier 1 (already complete per Gate C-1/C-2).
- Validation: Integration test suite; live Telegram validation.
- Blocking risks: bypass routes in _dispatch_command() (per Convergence Report); Bypass risk.
- Canonical Owner: KIO Core Team. Consumes: user intents, capability registry. Produces: dispatch results, execution observations. Depends On: execution_boundary, capability_registry. Used By: every interface. Future Owner: unchanged. Retirement Plan: none.

**2. Pipeline (mini_kio/core/pipeline/)**
- Purpose: Dispatch pipeline composition.
- Maturity: CURRENT.
- Final vision: Stable pipeline; no monolithic routing.
- Dependencies: core runtime, execution boundary.
- Incoming links: core runtime.
- Outgoing links: → dispatch handlers.
- Required completion Tier: Tier 1.
- Validation: pipeline tests.
- Blocking risks: pipeline-vs-bypass asymmetry.
- Canonical Owner: KIO Core Team. Consumes: intents. Produces: routed actions. Depends On: runtime. Used By: runtime. Retirement Plan: none.

**3. Execution Coordinator (_ExecutionCoordinator in mini_kio/core/pipeline/__init__.py — CORRECTED 2026-08-09)**
- Purpose: Coordinates capability execution; route → execute → verify → report.
- Maturity: CURRENT. (Correction: `mini_kio/execution/engine.py` is the workflow-engine class `WorkflowEngine` used by `workflow_provider.py`/`diagnostics.py`; the live pipeline coordinator is `_ExecutionCoordinator` at `pipeline/__init__.py:737`. 08-09 added truthful multi-step aggregation inside this coordinator.)
- Final vision: Single execution entry point with prerequisite gating.
- Dependencies: execution_boundary, capability_registry, provider_registry.
- Incoming links: core runtime → engine.
- Outgoing links: → providers, mcp_runtime, browser_runtime, filesystem.
- Required completion Tier: Tier 1 (Prerequisite Resolution per Slice 7 — DONE 2026-08-09: `PrerequisiteGate` + `resolve_prerequisites()` in `execution_boundary.py`, fail-closed) → Tier 2 (cross-process event bus).
- Validation: execution integration tests; prerequisite gate tests (21 passed in `tests/test_slice7_prerequisite_gate.py`).
- Blocking risks: scattered async/sync bridging per SEC.002.
- Canonical Owner: Execution Team. Consumes: routed actions. Produces: execution results, observations. Depends On: execution_boundary, capability_registry, providers. Used By: runtime, desktop, voice (future), browser. Retirement Plan: none.

**4. Capability Resolver (mini_kio/core/capability_registry.py, routing_utils.py)**
- Purpose: Dynamic capability discovery.
- Maturity: CURRENT (Gate C-2, 33 handlers per CAP.ROUTING.001).
- Final vision: Single discoverable capability registry — no parallel registries.
- Dependencies: capability_registry, provider_registry, command_registry.
- Incoming links: core runtime, planning layer.
- Outgoing links: → execution engine.
- Required completion Tier: Tier 1 (ARCH.003 resolution per Slice 6).
- Validation: capability-discovery tests.
- Blocking risks: triple-registry fragmentation per Convergence Report.
- Canonical Owner: KIO Core Team. Consumes: intent + context. Produces: capability handler reference. Depends On: command_registry, provider_registry, capability_registry. Used By: runtime, planning layer. Retirement Plan: merge command_registry + provider_registry into capability_registry in Tier 1.

**5. Provider Registry (mini_kio/core/provider_registry.py, mini_kio/llm/provider_registry.py)**
- Purpose: Provider discovery + health + failover.
- Maturity: CURRENT (15 providers per KIO_Implementation_Plan.md).
- Final vision: Single canonical provider abstraction.
- Dependencies: provider_contract (core, `ExecutionProvider` ABC), provider_base (LLM failover chain — separate live subsystem).
- D-08 (2026-08-09): Dead top-level `providers/` Protocol package (zero importers; re-added as dead snapshot by `c641220`) deleted, restoring the `7eeb7c8` cleanup. Canonical contract = `core/provider_contract.py`; LLM base remains a distinct, legitimate subsystem.
- Incoming links: capability resolver, llm gateway.
- Outgoing links: → providers.
- Required completion Tier: Tier 1 (reconciliation per D-08).
- Validation: provider tests; failover tests.
- Blocking risks: two provider_base interfaces per Convergence Report.
- Canonical Owner: Execution Team (generic) + LLM Team (LLM). Consumes: provider capabilities. Produces: resolvable providers. Depends On: provider_base. Used By: capability resolver, llm gateway. Future Owner: consolidate to single owner after D-08. Retirement Plan: retire mini_kio/llm/provider_registry.py once D-08 reconciled; OR retire providers/provider_base.py Protocol variant if ABC wins.

**6. Capability Registry (mini_kio/core/capability_registry.py)**
- Purpose: Tool discovery and registration.
- Maturity: CURRENT (Gate C-2 complete, 33 handlers).
- Final vision: Single discoverable capability layer; supersedes command_registry and provider_registry discovery.
- Dependencies: execution engine.
- Incoming links: bootstrap.
- Outgoing links: → capability resolver.
- Required completion Tier: Tier 1.
- Validation: capability discovery integration test.
- Blocking risks: none significant.
- Canonical Owner: KIO Core Team. Consumes: capability declarations. Produces: discoverable capabilities. Depends On: —. Used By: capability resolver, planning layer. Future Owner: unchanged. Retirement Plan: none.

**7. Execution Boundary (mini_kio/core/execution_boundary.py, LOCKED ~620 lines)**
- Purpose: Safety gateway. Classify → gate → resolve → validate → execute → verify.
- Maturity: CURRENT (LOCKED).
- Final vision: Hard safety gate; no bypass; prerequisite resolution per Slice 7 (gate mechanism DONE 2026-08-09; credential resolvers + Vault core DONE 2026-08-09 with Slice 8; lifecycle lands with Slice 9).
- Dependencies: intent_validator.
- Incoming links: core runtime, execution engine.
- Outgoing links: → execution engine (after gate).
- Required completion Tier: Tier 1 (prerequisite gate per Slice 7 — mechanism DONE 2026-08-09).
- Validation: boundary tests; safety integration tests.
- Blocking risks: bypass routes (verify none exist after Slice 6).
- Canonical Owner: Safety Team. Consumes: action + context. Produces: gated execution or structured block. Depends On: intent_validator. Used By: core runtime, execution engine. Future Owner: unchanged. Retirement Plan: none.

**8. Session Context (mini_kio/context/, mini_kio/llm/session_state.py, mini_kio/llm/conversation_context.py, mini_kio/core/continuity_context_provider.py)**
- Purpose: Unified session state (Gate C-1).
- Maturity: CURRENT (Gate C-1 complete per CAP.STATE.001).
- Final vision: Single context authority; six legacy state systems merged.
- Dependencies: session_state, conversation_context, media_context, continuity_state, artifact_memory.
- Incoming links: runtime.
- Outgoing links: → response composer, capability resolver.
- Required completion Tier: Tier 1.
- Validation: unified-context integration tests.
- Blocking risks: none significant post-Gate C-1.
- Canonical Owner: Context Team. Consumes: session events. Produces: unified context. Depends On: legacy state systems (being merged). Used By: response composer, capability resolver, AURA seam. Retirement Plan: retire SessionState, ConversationContext, ContinuityState, MediaEntityMemory, ArtifactMemory, MediaContext after migration complete.

**9. Memory (mini_kio/memory/memory_store.py)**
- Purpose: Per-item memory store with retention metadata + confidence decay (FQ-05 per Slice 18).
- Maturity: CURRENT (basic store); retention metadata + decay CURRENT per Slice 18.
- Final vision: Inspectable, correctable, deletable per MEM.001; integration with AURA memory subsystem when active.
- Dependencies: backend/repositories, AURA memory (when active).
- Incoming links: session context, AURA seam.
- Outgoing links: → response composer, AURA.
- Required completion Tier: Tier 1 (FQ-05) → Tier 4 (AURA integration).
- Validation: memory governance tests; inspection UX tests.
- Blocking risks: none significant.
- Canonical Owner: Memory Team. Consumes: session events, user feedback. Produces: memories. Depends On: backend/db, backend/repositories. Used By: response composer, AURA seam. Future Owner: unchanged. Retirement Plan: none.

**10. Fact Repository (mini_kio/backend/repositories/, mini_kio/knowledge/)**
- Purpose: Persistent facts; structured retrieval.
- Maturity: CURRENT (mini_kio/backend/db.py, mini_kio/knowledge/retrieval_router.py).
- Final vision: Single retrieval surface; merged with AURA knowledge graph when active.
- Dependencies: backend/db, knowledge providers.
- Incoming links: session context.
- Outgoing links: → response composer.
- Required completion Tier: Tier 2.
- Validation: retrieval integration tests.
- Blocking risks: provider count drift per pre-existing failure noted in KIO_Implementation_Plan.md Line 5.
- Canonical Owner: Knowledge Team. Consumes: retrieval queries. Produces: ranked facts. Depends On: backend/db, knowledge providers. Used By: response composer. Future Owner: unchanged. Retirement Plan: none.

**11. Identity (cross-cutting; canon ID.001–ID.007)**
- Purpose: KIO's self-knowledge (canon) + user identity resolution (mini_kio/resolvers/identity_resolver.py).
- Maturity: CURRENT (canon is canonical; user identity resolver CURRENT).
- Final vision: User identity across platforms + KIO identity per canon.
- Dependencies: backend/db, identity_resolver.
- Incoming links: session context, interfaces.
- Outgoing links: → every interface.
- Required completion Tier: Tier 1 (Slice 9).
- Validation: identity regression suite per KIO_IDENTITY_CANON.md §15.
- Blocking risks: identity drift across long conversations per KIO_IDENTITY_CANON.md §13.
- Canonical Owner: Identity Team (KIO identity per canon) + Identity Resolver Team (user identity). Consumes: canon IDs, contact data. Produces: resolved entities. Depends On: canon, backend/db. Used By: every interface. Future Owner: unchanged. Retirement Plan: none.

**12. Conversation (mini_kio/llm/conversation_orchestrator.py, conversation_responder.py, intent_classifier.py)**
- Purpose: Conversation state machine + response composition.
- Maturity: CURRENT (4-state machine per Convergence Report).
- Final vision: Extended state machine (PLANNING/EXECUTING/VERIFYING states per Convergence Report); composed responses, not monolithic.
- Dependencies: intent_classifier, conversation_orchestrator, conversation_responder.
- Incoming links: runtime.
- Outgoing links: → interfaces.
- Required completion Tier: Tier 1 (state machine extension) → Tier 2 (composer refactor).
- Validation: conversation integration tests.
- Blocking risks: monolithic conversation_responder.py per Convergence Report.
- Canonical Owner: Conversation Team. Consumes: intents, context, memories. Produces: conversation responses. Depends On: session_context, memory, response_governor. Used By: interfaces. Future Owner: unchanged. Retirement Plan: none.

**13. Response Composer (refactored conversation_responder.py)**
- Purpose: Compose response from intent + memory + knowledge + character.
- Maturity: CURRENT (monolithic) → ROADMAP (decomposed).
- Final vision: Composable sections: intent ack, memory recall, knowledge result, character voice.
- Dependencies: memory, knowledge, character_knowledge.
- Incoming links: conversation.
- Outgoing links: → interfaces.
- Required completion Tier: Tier 2.
- Validation: composer integration tests.
- Blocking risks: monolith.
- Canonical Owner: Conversation Team. Consumes: intent ack, memory recall, knowledge result, character. Produces: composed response. Depends On: memory, knowledge, character_knowledge. Used By: conversation. Retirement Plan: none.

**14. Browser Runtime (mini_kio/runtime/browser_runtime/)**
- Purpose: Playwright-based browser automation + connector (browser_connector/) + media playback + state verification.
- Maturity: CURRENT. **CORRECTED 2026-08-09: reference-resolution bug class fixed** (target identity via `mini_kio/core/target_ref.py`; tab-scoped close; contextual referents; focus/switch; "what's open"/"what's playing") — live-verified on Telegram. Remaining OPEN: YouTube Shorts control, semantic media selection, visual/workflow tiers.
- Final vision: Goal-driven browsing with persistent memory.
- Dependencies: Playwright (external, verified in repo), mini_kio/browser_connector/ (CURRENT).
- Incoming links: execution engine (pipeline `_ExecutionCoordinator`).
- Outgoing links: → user interfaces.
- Required completion Tier: Tier 3 (remaining bug-fix items: Shorts, semantic media selection) → Tier 5 (goal-driven).
- Validation: Playwright MCP live validation; reference-resolution regression test.
- Blocking risks: Shorts control + semantic media selection OPEN per LIM.002 remaining scope.
- Canonical Owner: Browser Team. Consumes: browser commands. Produces: browser state. Depends On: Playwright. Used By: execution engine. Future Owner: unchanged. Retirement Plan: none.

**15. Browser Operator (mini_kio/core/browser_operator.py, browser_session_registry.py, browser_tab_controller.py)**
- Purpose: Browser command dispatch + tab/session registry.
- Maturity: CURRENT.
- Final vision: Unified browser command layer.
- Dependencies: browser_runtime.
- Incoming links: execution engine.
- Outgoing links: → browser_runtime.
- Required completion Tier: Tier 3 (consolidate with browser/ top-level per Convergence Report recommendation).
- Validation: browser operator tests.
- Blocking risks: top-level browser/ coexistence per Convergence Report.
- Canonical Owner: Browser Team. Consumes: browser actions. Produces: browser sessions. Depends On: browser_runtime. Used By: execution engine. Future Owner: unchanged. Retirement Plan: retire top-level browser/ facade per Convergence Report.

**16. Media Runtime (mini_kio/media/media_manager.py, media_registry.py, media_discovery.py)**
- Purpose: Media discovery, registry, session.
- Maturity: CURRENT (Media Intelligence Layer, 8 modules per Convergence Report).
- Final vision: Intelligent media recommendation + state.
- Dependencies: media_providers, recommendation engine.
- Incoming links: intent classifier.
- Outgoing links: → response composer.
- Required completion Tier: Tier 4 (intelligence activation).
- Validation: media integration tests.
- Blocking risks: none significant.
- Canonical Owner: Media Team. Consumes: media intents. Produces: media actions. Depends On: media_providers. Used By: response composer. Future Owner: unchanged. Retirement Plan: none.

**17. Media Intelligence (mini_kio/media/intelligence/)**
- Purpose: Provider routing, retrieval synthesis.
- Maturity: CURRENT (multi-provider: duckduckgo, exa, jina, tavily, wikipedia).
- Final vision: Single retrieval surface with provider failover.
- Dependencies: media_providers.
- Incoming links: media runtime.
- Outgoing links: → media runtime.
- Required completion Tier: Tier 2.
- Validation: media intelligence tests.
- Blocking risks: none significant.
- Canonical Owner: Media Team. Consumes: retrieval queries. Produces: ranked media intelligence. Depends On: media_providers. Used By: media runtime. Future Owner: unchanged. Retirement Plan: none.

**18. Media Session (mini_kio/media/media_session.py, media_context.py, media_state.py)**
- Purpose: Per-session media state.
- Maturity: CURRENT (overlaps with SessionContext; consolidated per Gate C-1).
- Final vision: Unified media context within SessionContext.
- Dependencies: session_context.
- Incoming links: media runtime.
- Outgoing links: → session_context.
- Required completion Tier: Tier 1 (post-Gate C-1).
- Validation: session continuity tests.
- Blocking risks: legacy MediaEntityMemory, MediaContext overlap per Convergence Report.
- Canonical Owner: Media Team. Consumes: media events. Produces: media session state. Depends On: session_context. Used By: media runtime. Retirement Plan: retire MediaEntityMemory, MediaContext, ArtifactMemory after SessionContext migration.

**19. Media Recommendation Engine (mini_kio/media/media_recommender.py, media_knowledge_router.py)**
- Purpose: Media recommendation from user history.
- Maturity: CURRENT (basic); AURA preference learning integrates in Tier 4.
- Final vision: Confidence-aware recommendation.
- Dependencies: memory, knowledge.
- Incoming links: media runtime.
- Outgoing links: → response composer.
- Required completion Tier: Tier 4.
- Validation: recommendation A/B tests.
- Blocking risks: preference learning currently graceful-default.
- Canonical Owner: Media Team. Consumes: user history. Produces: recommendations. Depends On: memory, knowledge. Used By: response composer. Future Owner: unchanged. Retirement Plan: none.

**20. Media Memory (cross-cutting; uses mini_kio/memory/memory_store.py)**
- Purpose: Media-specific memory items.
- Maturity: CURRENT (uses memory store).
- Final vision: Unified with memory; inspectable per MEM.001.
- Dependencies: memory.
- Incoming links: media runtime.
- Outgoing links: → memory.
- Required completion Tier: Tier 1 (post-FQ-05).
- Validation: media memory governance tests.
- Blocking risks: none significant.
- Canonical Owner: Memory Team. Consumes: media events. Produces: media memories. Depends On: memory. Used By: media runtime. Future Owner: unchanged. Retirement Plan: none.

**21. Desktop Runtime (mini_kio/desktop/ — currently empty)**
- Purpose: Long-term primary interface.
- Maturity: ROADMAP (empty directory).
- Final vision: Full desktop companion with conversation, voice, browser, timeline, goals, knowledge, memories, tasks, plugins, diagnostics, developer mode.
- Dependencies: every other subsystem.
- Incoming links: user.
- Outgoing links: → runtime.
- Required completion Tier: Tier 4 (foundation) → Tier 5 (full).
- Validation: desktop integration tests; live desktop validation.
- Blocking risks: empty today; full build required.
- Canonical Owner: Desktop Team. Consumes: user interactions. Produces: desktop UI. Depends On: runtime, browser, voice (future), media, memory, AURA. Used By: users. Future Owner: unchanged. Retirement Plan: none.

**22. Desktop Automation (mini_kio/core/desktop_intelligence.py — CURRENT 400 lines, NL desktop routes)**
- Purpose: Desktop NL command routing.
- Maturity: CURRENT (NL routing); full automation ROADMAP.
- Final vision: Cross-application automation with safety.
- Dependencies: desktop runtime (ROADMAP), execution boundary.
- Incoming links: desktop runtime.
- Outgoing links: → execution engine.
- Required completion Tier: Tier 4.
- Validation: desktop automation integration tests.
- Blocking risks: desktop runtime not built.
- Canonical Owner: Desktop Team. Consumes: NL desktop commands. Produces: desktop actions. Depends On: execution boundary. Used By: desktop runtime. Future Owner: unchanged. Retirement Plan: none.

**23. Filesystem (mini_kio/core/file_operator.py, mini_kio/execution/browser/providers/filesystem_provider.py)**
- Purpose: Filesystem operations.
- Maturity: CURRENT.
- Final vision: Single filesystem capability surface.
- Dependencies: execution boundary.
- Incoming links: execution engine.
- Outgoing links: → OS.
- Required completion Tier: Tier 1.
- Validation: filesystem integration tests.
- Blocking risks: none significant.
- Canonical Owner: Execution Team. Consumes: file commands. Produces: file results. Depends On: execution boundary. Used By: execution engine, MCP filesystem server. Future Owner: unchanged. Retirement Plan: none.

**24. Plugin Runtime (referenced in KIO_Implementation_Plan.md; no specific module today)**
- Purpose: Plugin loading + sandboxing.
- Maturity: ROADMAP (no concrete module found).
- Final vision: Safe plugin ecosystem.
- Dependencies: execution boundary.
- Incoming links: user config.
- Outgoing links: → execution engine.
- Required completion Tier: Tier 5.
- Validation: plugin sandbox tests.
- Blocking risks: sandbox isolation complexity.
- Canonical Owner: Plugin Team. Consumes: plugin manifests. Produces: plugin execution. Depends On: execution boundary. Used By: users. Future Owner: unchanged. Retirement Plan: none.

**25. MCP Runtime (mini_kio/runtime/mcp_runtime/)**
- Purpose: JSON-RPC 2.0 over stdio MCP server execution; crash-isolated.
- Maturity: CURRENT (infra only, 8 servers, 59 tools per KIO_Implementation_Plan.md).
- Final vision: Production MCP ecosystem with resource limits per SEC.001.
- Dependencies: execution boundary.
- Incoming links: execution engine, capability registry.
- Outgoing links: → external MCP servers.
- Required completion Tier: Tier 2 (resource limits) → Tier 5 (full ecosystem).
- Validation: MCP integration tests; crash isolation tests.
- Blocking risks: SEC.001 resource limits absent.
- Canonical Owner: MCP Team. Consumes: MCP tool calls. Produces: MCP tool results. Depends On: execution boundary. Used By: execution engine. Future Owner: unchanged. Retirement Plan: none.

**26. Provider Manager (mini_kio/llm/provider_manager.py, Gate 4A active 125 lines)**
- Purpose: LLM provider circuit breakers + health.
- Maturity: CURRENT.
- Final vision: Provider health + failover authority.
- Dependencies: provider_base.
- Incoming links: llm gateway.
- Outgoing links: → LLM providers.
- Required completion Tier: Tier 1.
- Validation: provider failover tests.
- Blocking risks: none significant.
- Canonical Owner: LLM Team. Consumes: LLM requests. Produces: LLM responses with failover. Depends On: provider_base. Used By: llm gateway. Future Owner: unchanged. Retirement Plan: none.

**27. LLM Gateway (mini_kio/llm/llm_gateway.py)**
- Purpose: Multi-provider failover; 45s chain timeout.
- Maturity: CURRENT (stable, 157 lines).
- Final vision: Single LLM entry point with circuit breakers.
- Dependencies: provider_manager.
- Incoming links: conversation orchestrator.
- Outgoing links: → LLM providers.
- Required completion Tier: Tier 1.
- Validation: LLM failover integration tests.
- Blocking risks: backup_llm/ duplicate per Convergence Report.
- Canonical Owner: LLM Team. Consumes: LLM requests. Produces: LLM responses. Depends On: provider_manager. Used By: conversation orchestrator. Future Owner: unchanged. Retirement Plan: retire backup_llm/ standalone after consolidation.

**28. Voice Runtime (mini_kio/voice/ — does not exist)**
- Purpose: Voice I/O.
- Maturity: ROADMAP (no module exists).
- Final vision: Production-grade voice per Section 9.
- Dependencies: audio pipeline, STT, TTS, VAD.
- Incoming links: user.
- Outgoing links: → runtime.
- Required completion Tier: Tier 4.
- Validation: voice integration tests; live voice validation.
- Blocking risks: module does not exist; full build required.
- Canonical Owner: Voice Team. Consumes: voice I/O. Produces: voice interactions. Depends On: STT, TTS, VAD. Used By: users. Future Owner: unchanged. Retirement Plan: none.

**29. Speech Recognition (planned; not present)**
- Purpose: STT.
- Maturity: ROADMAP.
- Final vision: faster-whisper local.
- Dependencies: audio pipeline.
- Required completion Tier: Tier 4.
- Canonical Owner: Voice Team. Consumes: audio. Produces: text. Depends On: audio pipeline. Used By: voice runtime. Future Owner: unchanged. Retirement Plan: none.

**30. Speech Synthesis (planned; not present)**
- Purpose: TTS.
- Maturity: ROADMAP.
- Final vision: piper-tts local with edge-tts fallback.
- Dependencies: audio pipeline.
- Required completion Tier: Tier 4.
- Canonical Owner: Voice Team. Consumes: text. Produces: audio. Depends On: audio pipeline. Used By: voice runtime. Future Owner: unchanged. Retirement Plan: none.

**31. Audio Pipeline (planned; not present)**
- Purpose: Audio I/O + VAD + noise suppression.
- Maturity: ROADMAP.
- Final vision: silero-vad + rnnoise.
- Dependencies: —
- Required completion Tier: Tier 4.
- Canonical Owner: Voice Team. Consumes: audio. Produces: processed audio. Depends On: —. Used By: STT, TTS. Future Owner: unchanged. Retirement Plan: none.

**32. Desktop Interface (mini_kio/desktop/ — empty)**
- Purpose: Desktop UI.
- Maturity: ROADMAP.
- Final vision: Full desktop companion.
- Required completion Tier: Tier 4 → Tier 5.
- Canonical Owner: Desktop Team. Consumes: user input. Produces: UI. Depends On: runtime. Used By: users. Future Owner: unchanged. Retirement Plan: none.

**33. CLI (mini_kio/interfaces/terminal.py)**
- Purpose: Terminal interface.
- Maturity: CURRENT.
- Required completion Tier: Tier 1.
- Canonical Owner: Interface Team. Consumes: terminal input. Produces: terminal output. Depends On: runtime. Used By: users. Future Owner: unchanged. Retirement Plan: none.

**34. Telegram (mini_kio/interfaces/, bot code elsewhere)**
- Purpose: Telegram channel.
- Maturity: CURRENT (per bot_stderr.log/bot_stdout.log, per CAP.INTERFACE.001).
- Required completion Tier: Tier 1.
- Canonical Owner: Interface Team. Consumes: Telegram messages. Produces: Telegram responses. Depends On: runtime. Used By: users. Future Owner: unchanged. Retirement Plan: none.

**35. Discord (mini_kio/platform/discord_transport.py, DISCORD_INTEGRATION_REPORT.md)**
- Purpose: Discord channel.
- Maturity: PARTIAL/CURRENT (transport present; per CAP.INTERFACE.002 ROADMAP until shipped).
- Required completion Tier: Tier 1 (validate ship status per Slice).
- Canonical Owner: Interface Team. Consumes: Discord messages. Produces: Discord responses. Depends On: runtime, platform transport. Used By: users. Future Owner: unchanged. Retirement Plan: none.

**36. Future Mobile Interface (not present)**
- Purpose: Mobile companion.
- Maturity: ROADMAP.
- Required completion Tier: Tier 5 (companion).
- Canonical Owner: Mobile Team. Consumes: mobile input. Produces: mobile output. Depends On: runtime. Used By: users. Future Owner: unchanged. Retirement Plan: none.

**37. Developer Mode (per KIO_IDENTITY_CANON.md §9 Runtime Contract and §14 Health Checks)**
- Purpose: Capability introspection; AURA seam viewer; runtime diagnostics.
- Maturity: ROADMAP for full surface.
- Required completion Tier: Tier 4.
- Canonical Owner: DX Team. Consumes: developer actions. Produces: introspection output. Depends On: diagnostics, runtime. Used By: developers. Future Owner: unchanged. Retirement Plan: none.

**38. Diagnostics (mini_kio/core/kio_diagnostics.py, mini_kio/execution/diagnostics.py)**
- Purpose: Runtime health + capability health.
- Maturity: CURRENT.
- Required completion Tier: Tier 1.
- Canonical Owner: Reliability Team. Consumes: runtime events. Produces: diagnostics output. Depends On: runtime. Used By: developers, operators. Future Owner: unchanged. Retirement Plan: none.

**39. Logging (mini_kio/core/trace_logger.py, mini_kio/execution/metrics.py, runtime_logs/)**
- Purpose: Trace + metrics.
- Maturity: CURRENT.
- Required completion Tier: Tier 1.
- Canonical Owner: Reliability Team. Consumes: runtime events. Produces: logs, metrics. Depends On: runtime. Used By: operators. Future Owner: unchanged. Retirement Plan: none.

**40. Configuration (mini_kio/core/config.py, .env, KIO_Implementation_Plan.md Slice 14 Startup Configuration Validation)**
- Purpose: Runtime configuration + validation.
- Maturity: CURRENT (LOCKED, 200 lines) for config loading; **Startup Configuration Validation (Slice 14) is NOT implemented** — corrected 2026-08-09 (the historical "Slice 12" reference was a stale number; the IP ledger uses Slice 14).
- Required completion Tier: Tier 1 (Startup Configuration Validation per Slice 14).
- Canonical Owner: Platform Team. Consumes: env, config files. Produces: validated config. Depends On: —. Used By: every subsystem. Future Owner: unchanged. Retirement Plan: none.

**41. Security (mini_kio/core/intent_validator.py, execution_boundary.py, KIO_IDENTITY_CANON.md §5.2.4 SEC.001-003)**
- Purpose: Safety + validation + secrets.
- Maturity: CURRENT for intent validation; ROADMAP for full security surface.
- Required completion Tier: Tier 1 (MCP resource limits per SEC.001).
- Canonical Owner: Security Team. Consumes: actions, configs. Produces: gated/validated actions. Depends On: execution boundary. Used By: runtime. Future Owner: unchanged. Retirement Plan: none.

**42. Validation Harness (mini_kio/core/kio_selftest.py, tests/, gate2_final_hardening_matrix.py)**
- Purpose: Self-test + gate validation.
- Maturity: CURRENT.
- Required completion Tier: Tier 1.
- Canonical Owner: QA Team. Consumes: runtime state. Produces: pass/fail results. Depends On: diagnostics. Used By: CI, operators. Future Owner: unchanged. Retirement Plan: none.

**43. CI (.github/, gate2_* scripts in repo root, GitNexus run.cjs)**
- Purpose: Continuous integration.
- Maturity: CURRENT (per presence of CI scripts).
- Required completion Tier: Tier 1.
- Canonical Owner: DevOps Team. Consumes: code changes. Produces: CI results. Depends On: tests, validation harness. Used By: developers. Future Owner: unchanged. Retirement Plan: none.

**44. Telemetry (mini_kio/execution/metrics.py, runtime_logs/)**
- Purpose: Runtime metrics.
- Maturity: CURRENT.
- Required completion Tier: Tier 1.
- Canonical Owner: Reliability Team. Consumes: runtime events. Produces: metrics. Depends On: —. Used By: operators. Future Owner: unchanged. Retirement Plan: none.

**45. AURA Integration (mini_kio/execution/aura_integration.py)**
- Purpose: The only API surface between KIO and AURA.
- Maturity: CURRENT (200 lines, well-designed); receiver UNVERIFIED.
- Required completion Tier: Tier 1 (seam integration) → Tier 3 (receiver activation, Founder-gated).
- Canonical Owner: AURA Integration Team. Consumes: KIO execution events. Produces: observation events. Depends On: runtime. Used By: AURA (when active). Future Owner: unchanged. Retirement Plan: none.

**46. Event Bus (CORRECTED 2026-08-09: browser-scoped only — mini_kio/runtime/browser_runtime/events.py)**
- Purpose: Cross-process event publication.
- Maturity: PARTIAL — the only `EventBus` implementation is browser-scoped (`runtime/browser_runtime/events.py`). The files cited historically (`runtime/ObservationBus.py`, `communication/EventBus.py`) do **not exist**. Global single event authority remains ROADMAP.
- Required completion Tier: Tier 2 (single authority per Convergence Report).
- Canonical Owner: Platform Team. Consumes: events. Produces: routed events. Depends On: —. Used By: browser runtime only today. Future Owner: unchanged. Retirement Plan: retire duplicate event namespaces per Convergence Report.

**47. Knowledge Graph (mini_kio/knowledge/)**
- Purpose: Structured retrieval over knowledge providers.
- Maturity: CURRENT (multi-provider: duckduckgo, exa, jina, tavily, wikipedia) → ROADMAP for AURA knowledge graph (when active).
- Required completion Tier: Tier 2 (single retrieval surface).
- Canonical Owner: Knowledge Team. Consumes: retrieval queries. Produces: ranked results. Depends On: knowledge providers. Used By: response composer. Future Owner: unchanged. Retirement Plan: none.

**48. Reasoning (planned; not present as standalone)**
- Purpose: Reasoning layer.
- Maturity: ROADMAP (no implementation found).
- Required completion Tier: Tier 3 (Founder-gated per ROAD.002 Gate C-7).
- Canonical Owner: AURA Team. Consumes: context, memory. Produces: reasoning results. Depends On: AURA loop. Used By: response composer. Future Owner: unchanged. Retirement Plan: none.

**49. Beliefs (planned; not present)**
- Purpose: Belief state.
- Maturity: ROADMAP.
- Required completion Tier: Tier 3 (Founder-gated).
- Canonical Owner: AURA Team. Consumes: observations. Produces: belief updates. Depends On: AURA loop. Used By: reasoning. Future Owner: unchanged. Retirement Plan: none.

**50. Goals (CORRECTED 2026-08-09 — NOT IMPLEMENTED)**
- Purpose: Multi-step goal tracking.
- Maturity: **ROADMAP / NOT STARTED.** `mini_kio/core/executive.py` and `mini_kio/core/orchestrator.py` do **not exist**; only `task_engine.py` exists (a task helper, not a goal registry). The historical "CURRENT (built but unwired)" claim was false — no goals module has ever been committed. Multi-step execution is handled by `command_router._execute_multi_step` (08-09, truthful aggregation), which is a command-composition path, not a Goal Manager.
- Required completion Tier: Tier 3 (wiring per Slice 20+).
- Canonical Owner: Planning Team. Consumes: user goals. Produces: plans. Depends On: capability registry. Used By: runtime. Future Owner: unchanged. Retirement Plan: none.

**51. World Model (planned; not present)**
- Purpose: World state tracking.
- Maturity: ROADMAP.
- Final vision: Persistent, queryable world state across sessions.
- Dependencies: AURA loop, observations, beliefs.
- Required completion Tier: Tier 3 (Founder-gated per ROAD.002 Gate C-7).
- Canonical Owner: AURA Team. Consumes: world state changes. Produces: world model. Depends On: AURA loop, beliefs. Used By: reasoning, goals. Future Owner: unchanged. Retirement Plan: none.

**52. Reflection (planned; not present)**
- Purpose: Reflection on prior interactions.
- Maturity: ROADMAP.
- Required completion Tier: Tier 4 (Founder-gated).
- Canonical Owner: AURA Team. Consumes: session history. Produces: reflections. Depends On: AURA loop, memory. Used By: response composer, learning. Future Owner: unchanged. Retirement Plan: none.

**53. Learning (planned; not present)**
- Purpose: Preference + behavior learning.
- Maturity: ROADMAP.
- Required completion Tier: Tier 4 (Founder-gated).
- Canonical Owner: AURA Team. Consumes: observations, feedback. Produces: learned preferences. Depends On: AURA loop, memory. Used By: response composer, media recommender. Future Owner: unchanged. Retirement Plan: none.

**54. Confidence (planned; not present)**
- Purpose: Confidence estimates on memory retrievals and reasoning outputs.
- Maturity: ROADMAP (retriever-side confidence is generated live per KIO_IDENTITY_CANON.md §5 preamble; subsystem-level confidence tracking ROADMAP).
- Required completion Tier: Tier 4.
- Canonical Owner: AURA Team. Consumes: retrieval outputs, reasoning outputs. Produces: confidence scores. Depends On: AURA loop, retriever. Used By: response composer. Future Owner: unchanged. Retirement Plan: none.

**55. Strategy (planned; not present)**
- Purpose: Long-horizon planning strategy.
- Maturity: ROADMAP.
- Required completion Tier: Tier 4 (Founder-gated).
- Canonical Owner: AURA Team. Consumes: goals, world model. Produces: strategies. Depends On: AURA loop, reasoning. Used By: goals. Future Owner: unchanged. Retirement Plan: none.

**56. Oracle (planned; not present)**
- Purpose: Forward-looking projection / what-if reasoning.
- Maturity: ROADMAP.
- Required completion Tier: Tier 4 (Founder-gated).
- Canonical Owner: AURA Team. Consumes: world model, memory. Produces: projections. Depends On: AURA loop. Used By: response composer, planning. Future Owner: unchanged. Retirement Plan: none.

**57. Continuity (mini_kio/core/continuity_resolver.py, continuity_context_provider.py CURRENT; full cross-device continuity ROADMAP)**
- Purpose: Cross-session, cross-device continuity.
- Maturity: CURRENT (in-process) → ROADMAP (cross-device, gated on Aurora).
- Required completion Tier: Tier 1 (in-process) → Tier 5 (cross-device).
- Canonical Owner: Continuity Team. Consumes: session events. Produces: continuity references. Depends On: memory, session_context. Used By: every interface. Future Owner: unchanged. Retirement Plan: none.

**58. Identity (AURA-layer) (planned; not present as AURA module)**
- Purpose: AURA identity subsystem — distinct from KIO identity canon.
- Maturity: ROADMAP.
- Required completion Tier: Tier 3 (Founder-gated).
- Canonical Owner: AURA Team. Consumes: identity events. Produces: identity state. Depends On: AURA loop, memory. Used By: continuity, relationships. Future Owner: unchanged. Retirement Plan: none.

**59. Observations (mini_kio/execution/observations.py CURRENT — VERIFIED WIRED 2026-08-09)**
- Purpose: Observation emission.
- Maturity: CURRENT (7863 bytes). (Correction: an earlier audit claimed zero importers — **disproven**; `get_observation_stream()` is imported and invoked at HEAD in `core/providers/desktop_provider.py`, `core/providers/workflow_provider.py`, and `core/mcp/provider.py`.)
- Required completion Tier: Tier 1 (integration).
- Canonical Owner: AURA Integration Team. Consumes: execution events. Produces: observation records. Depends On: runtime. Used By: AURA seam. Future Owner: unchanged. Retirement Plan: none.

**60. Execution Fabric (mini_kio/execution/engine.py, mini_kio/execution/capability_router.py CURRENT)**
- Purpose: The only component allowed to act (per CAP.AUTONOMY.001 + INV.006).
- Maturity: CURRENT.
- Required completion Tier: Tier 1.
- Canonical Owner: Execution Team. Consumes: gated actions. Produces: execution results. Depends On: execution_boundary, capability_registry, providers, mcp_runtime, browser_runtime. Used By: every interface (transitively). Future Owner: unchanged. Retirement Plan: none.

**61. Aurora Backend (PROPOSED/ROADMAP — Section 0.2)**
- Purpose: Permanent cognitive home.
- Maturity: PROPOSED/ROADMAP. Not verified in repo.
- Required completion Tier: Tier 5 (provisioning) — gated on Founder Decision.
- Canonical Owner: Infrastructure Team. Consumes: cognition from KIO. Produces: persistent memories, reasoning results. Depends On: — (new hardware/OS provisioning). Used By: every KIO instance. Future Owner: unchanged. Retirement Plan: none.

**62. Victus Engineering Workspace (CURRENT — this machine)**
- Purpose: Implementation, testing, simulation, validation, benchmarking, release-candidate generation. NOT permanent cognition.
- Maturity: CURRENT.
- Required completion Tier: Tier 1 (already in place).
- Canonical Owner: Engineering Team. Consumes: code changes. Produces: tested artifacts. Depends On: —. Used By: developers. Future Owner: unchanged. Retirement Plan: none. Constraint: must never become permanent cognition host.

**63. Git (.git/, git tooling)**
- Purpose: Version control.
- Maturity: CURRENT.
- Required completion Tier: Tier 1.
- Canonical Owner: DevOps Team. Consumes: code changes. Produces: commits. Depends On: —. Used By: every developer. Future Owner: unchanged. Retirement Plan: none.

**64. Deployment (PROPOSED/ROADMAP — Section 0.2)**
- Purpose: Deployment of KIO to Aurora and other targets.
- Maturity: PROPOSED/ROADMAP.
- Required completion Tier: Tier 5.
- Canonical Owner: DevOps Team. Consumes: built artifacts. Produces: deployed KIO. Depends On: Aurora, Docker, FastAPI service. Used By: operators. Future Owner: unchanged. Retirement Plan: none.

**65. Docker (PROPOSED/ROADMAP — Section 0.2)**
- Purpose: Containerization of Aurora cognitive services.
- Maturity: PROPOSED/ROADMAP. No Docker configs verified in repo.
- Required completion Tier: Tier 5.
- Canonical Owner: Infrastructure Team. Consumes: service manifests. Produces: containers. Depends On: —. Used By: Aurora, deployment. Future Owner: unchanged. Retirement Plan: none.

**66. FastAPI (PROPOSED/ROADMAP — Section 0.2)**
- Purpose: Cognitive API surface on Aurora.
- Maturity: PROPOSED/ROADMAP. No FastAPI service in repo.
- Required completion Tier: Tier 5.
- Canonical Owner: API Team. Consumes: cognition requests. Produces: API responses. Depends On: AURA loop, event bus. Used By: KIO instances. Future Owner: unchanged. Retirement Plan: none.

**67. Redis (PROPOSED/ROADMAP — Section 0.2)**
- Purpose: Event bus / cache on Aurora.
- Maturity: PROPOSED/ROADMAP.
- Required completion Tier: Tier 5.
- Canonical Owner: Infrastructure Team. Consumes: events. Produces: cached/routed events. Depends On: Docker. Used By: FastAPI, event bus. Future Owner: unchanged. Retirement Plan: none.

**68. Neo4j (PROPOSED/ROADMAP — Section 0.2)**
- Purpose: Knowledge graph on Aurora.
- Maturity: PROPOSED/ROADMAP. No Neo4j config in repo.
- Required completion Tier: Tier 5.
- Canonical Owner: Knowledge Team. Consumes: entities + relationships. Produces: graph queries. Depends On: Docker. Used By: AURA knowledge graph. Future Owner: unchanged. Retirement Plan: none.

**69. PostgreSQL (PROPOSED/ROADMAP — Section 0.2)**
- Purpose: Persistent storage on Aurora.
- Maturity: PROPOSED/ROADMAP. mini_kio/backend/db.py uses SQLite locally.
- Required completion Tier: Tier 5.
- Canonical Owner: Infrastructure Team. Consumes: structured data. Produces: queries. Depends On: Docker. Used By: backend, memory, AURA. Future Owner: unchanged. Retirement Plan: none.

**70. ChromaDB (PROPOSED/ROADMAP — Section 0.2)**
- Purpose: Vector store on Aurora.
- Maturity: PROPOSED/ROADMAP. No ChromaDB config in repo.
- Required completion Tier: Tier 5.
- Canonical Owner: Knowledge Team. Consumes: embeddings. Produces: similarity queries. Depends On: Docker. Used By: memory, AURA. Future Owner: unchanged. Retirement Plan: none.

**71. n8n Automation Layer (PROPOSED/ROADMAP — Section 0.2)**
- Purpose: User-facing automation orchestration.
- Maturity: PROPOSED/ROADMAP. No n8n in repo.
- Required completion Tier: Tier 5.
- Canonical Owner: Automation Team. Consumes: automation triggers. Produces: automation execution. Depends On: execution fabric, MCP runtime. Used By: users. Future Owner: unchanged. Retirement Plan: none.

Second topology diagram (Section 13):

```
Users
 ↓
Interfaces
 ↓
KIO
 ↓
AURA
 ↓
Execution Fabric
 ↓
Capabilities
 ↓
Operating System
 ↓
Observations
 ↓
AURA
```

This loop diagram is the canonical cognitive loop per KIO_CONSTITUTION.md §1 ("Observe → Know → Believe → Reason → Plan → Act → Reflect"). All claims tagged per Section 0.3. This loop is architecturally defined but not implemented as a single executable subsystem in the audited repo.

---

## SECTION 14 — SUBSYSTEM MATURITY TABLE

Per-subsystem rows. Each row has: Current State / Target State / Dependencies / Blocking Dependencies / Risk / Priority / Tier / Owner / Validation Method / Regression Tests / Success Criteria / Completion Definition. This table is the engineering contract for every subsystem above. Compact format; full detail in Section 13.

| Subsystem | Current State | Target State | Dependencies | Blocking Deps | Risk | Priority | Tier | Owner | Validation | Regression Tests | Success Criteria | Completion Definition |
|---|---|---|---|---|---|---|---|---|---|---|---|---|
| Core Runtime | LOCKED v1.1 | Single dispatch authority | execution_boundary, capability_registry | — | Low (bypass routes per Convergence Report) | P0 | 1 | KIO Core | Integration tests; live Telegram | Runtime regression suite | Single dispatch entry for every interface | No bypass paths verified by audit |
| Pipeline | CURRENT | Stable pipeline | runtime | runtime | Low | P1 | 1 | KIO Core | Pipeline tests | Pipeline regression | No monolithic routing | All routes go through pipeline |
| Execution Coordinator | CURRENT (`_ExecutionCoordinator` in `pipeline/__init__.py`; truthful multi-step aggregation 08-09) | Single execution entry with prerequisite gating | execution_boundary | Tier 1 prerequisite gate | Medium (SEC.002 async/sync bridging) | P0 | 1→2 | Execution | Execution integration + gate tests | Execution regression | Every action gated | No ungated path from intent to action |
| Capability Resolver | CURRENT (Gate C-2, 33 handlers) | Single discoverable registry | capability_registry, provider_registry, command_registry | ARCH.003 resolution | Medium (triple-registry fragmentation) | P0 | 1 | KIO Core | Capability discovery tests | Discovery regression | Single resolution path | All three registries consolidated |
| Provider Registry | CURRENT (15 providers; D-08 resolved 2026-08-09) | Single canonical provider abstraction | provider_contract | — | Low (canonical contract + separate LLM chain) | P0 | 1 | Execution + LLM | Provider tests; failover tests | Provider regression | Single interface, single registry | One canonical provider registry |
| Capability Registry | CURRENT (Gate C-2) | Single discoverable capability layer | execution engine | — | Low | P1 | 1 | KIO Core | Capability discovery test | Capability regression | All capabilities discoverable | No orphan capabilities |
| Execution Boundary | LOCKED | Hard safety gate; prerequisite gate | intent_validator | Slice 7 gate + Slice 8 credential resolvers | Low | P0 | 1 | Safety | Boundary tests; safety integration | Safety regression | No bypass; every action gated | Verified no bypass routes |
| Session Context | CURRENT (Gate C-1; 08-09 referent sanitization — safe target names stored, not serialized routing strings) | Unified context; 6 legacy merged | session_state, conversation_context, media_context, continuity_state, artifact_memory | Legacy migration | Low | P0 | 1 | Context | Unified-context integration tests | Context regression | One context authority | Six legacy systems retired |
| Memory | CURRENT (basic + FQ-05) | Inspectable/correctable/deletable per MEM.001 | backend/repositories | MEM.001 UX gap | Low | P0 | 1→4 | Memory | Memory governance tests; inspection UX | Memory regression | Full governance UX | User can inspect/correct/delete every memory |
| Fact Repository | CURRENT | Single retrieval surface | backend/db, knowledge providers | — | Low (provider count drift) | P1 | 2 | Knowledge | Retrieval integration tests | Retrieval regression | One retrieval surface | All retrieval routes through one router |
| Identity | CURRENT | Cross-platform identity | backend/db, identity_resolver | — | Medium (drift per KIO_IDENTITY_CANON §13) | P0 | 1 | Identity | Identity regression suite (canon §15) | Identity regression | KIO identity never drifts | Canon invariants upheld |
| Conversation | CURRENT (4-state) | Extended state machine | intent_classifier, orchestrator, responder | Slice 16 PLANNING/EXECUTING/VERIFYING | Medium (monolithic responder) | P1 | 1→2 | Conversation | Conversation integration tests | Conversation regression | Composed responses | Composer decomposed |
| Response Composer | CURRENT (monolithic) | Composed sections | memory, knowledge, character | Tier 2 refactor | Medium | P1 | 2 | Conversation | Composer integration tests | Composer regression | Composable sections | Monolith split |
| Browser Runtime | CURRENT (reference-resolution bug class fixed 2026-08-09 via `target_ref.py`; tab-scoped close, focus/switch, contextual referents — live-verified) | Goal-driven browsing | Playwright, browser_connector | LIM.002 remaining (Shorts; semantic media selection; visual/workflow tiers) | Medium (bug class fixed; remaining items OPEN) | P0 | 3→5 | Browser | Playwright MCP live validation | Browser regression including reference-resolution test | No reference-resolution bug | Reference resolution works reliably |
| Browser Operator | CURRENT | Unified browser command layer | browser_runtime | Top-level browser/ consolidation | Low | P1 | 3 | Browser | Browser operator tests | Browser regression | One browser command layer | Top-level browser/ retired |
| Media Runtime | CURRENT (8 modules; playback recovery 08-08 b5db667; state-aware control 08-09: now-playing, verified pause/resume, contextual references) | Intelligent media recommendation | media_providers, recommender | Media entity resolution / semantic selection OPEN | Low | P2 | 4 | Media | Media integration tests | Media regression | Recommendation activated | Media intelligence live |
| Media Intelligence | CURRENT (multi-provider) | Single retrieval surface | media_providers | — | Low | P1 | 2 | Media | Media intelligence tests | Media regression | Provider failover | Single router, all providers routed |
| Media Session | CURRENT | Unified media context in SessionContext | session_context | Legacy migration | Low | P1 | 1 | Media | Session continuity tests | Session regression | Media context in SessionContext | MediaEntityMemory/Context/ArtifactMemory retired |
| Media Recommendation Engine | CURRENT (basic) | Confidence-aware recommendation | memory, knowledge | AURA preference learning | Low | P2 | 4 | Media | A/B tests | Media regression | Confidence surfaced | Preference learning active |
| Media Memory | CURRENT | Unified, inspectable | memory | FQ-05 | Low | P1 | 1 | Memory | Media memory governance tests | Memory regression | Media memories governed | Media memory in canonical memory UX |
| Desktop Runtime | ROADMAP (empty dir) | Full desktop companion | every subsystem | Module build | High (does not exist) | P2 | 4→5 | Desktop | Desktop integration; live validation | Desktop regression | All surfaces functional | Desktop app shipped |
| Desktop Automation | CURRENT (NL routing only) | Cross-application automation | desktop runtime, execution_boundary | desktop runtime | Medium | P2 | 4 | Desktop | Desktop automation integration | Desktop regression | Safe cross-app actions | Safety verified |
| Filesystem | CURRENT | Single filesystem capability | execution_boundary | — | Low | P1 | 1 | Execution | Filesystem integration | Filesystem regression | One filesystem surface | Single capability surface |
| Plugin Runtime | ROADMAP | Safe plugin ecosystem | execution_boundary | Sandbox design | High (sandbox complexity) | P3 | 5 | Plugin | Plugin sandbox tests | Plugin regression | Plugins isolated | Sandboxed plugin execution |
| MCP Runtime | CURRENT (infra only, 8 servers, 59 tools) | Production MCP ecosystem | execution_boundary | SEC.001 resource limits | Medium (no resource limits) | P1 | 2→5 | MCP | MCP integration + crash isolation | MCP regression | Resource limits; crash isolation | Limits enforced |
| Provider Manager | CURRENT (Gate 4A) | Provider health + failover | provider_base | — | Low | P1 | 1 | LLM | Provider failover tests | Provider regression | Circuit breakers active | Failover verified |
| LLM Gateway | CURRENT | Single LLM entry with circuit breakers | provider_manager | backup_llm/ consolidation | Low | P1 | 1 | LLM | LLM failover integration | LLM regression | Single gateway | backup_llm/ retired |
| Voice Runtime | ROADMAP (does not exist) | Production-grade voice | audio pipeline, STT, TTS, VAD | Module build | High | P2 | 4 | Voice | Voice integration; live validation | Voice regression | Full voice capability | Voice shipped |
| Speech Recognition | ROADMAP | Local STT (faster-whisper) | audio pipeline | Module build | High | P2 | 4 | Voice | STT tests | STT regression | Local STT works | Local STT shipped |
| Speech Synthesis | ROADMAP | Local TTS (piper-tts) | audio pipeline | Module build | High | P2 | 4 | Voice | TTS tests | TTS regression | Local TTS works | Local TTS shipped |
| Audio Pipeline | ROADMAP | silero-vad + rnnoise | — | Module build | High | P2 | 4 | Voice | Audio tests | Audio regression | VAD + noise suppression work | Audio pipeline shipped |
| Desktop Interface | ROADMAP | Full desktop UI | runtime | Desktop runtime | High | P2 | 4→5 | Desktop | Desktop integration | Desktop regression | All UI surfaces work | Desktop shipped |
| CLI | CURRENT | Stable terminal interface | runtime | — | Low | P1 | 1 | Interface | Terminal tests | Terminal regression | Stable CLI | Maintained |
| Telegram | CURRENT (concurrent updates + responsiveness during long media actions verified live 08-09) | Stable Telegram channel | runtime | — | Low | P1 | 1 | Interface | Live Telegram validation | Telegram regression | Stable | Maintained |
| Discord | PARTIAL/CURRENT | Stable Discord channel | runtime, platform transport | Shipping verification | Medium | P2 | 1 | Interface | Live Discord validation | Discord regression | Stable | Verified shipped |
| Future Mobile Interface | ROADMAP | Mobile companion | runtime | Module build | High | P3 | 5 | Mobile | Mobile integration | Mobile regression | Companion works | Mobile shipped |
| Developer Mode | ROADMAP | Full introspection | diagnostics, runtime | Module build | Medium | P2 | 4 | DX | DX tests | DX regression | Introspection live | DX shipped |
| Diagnostics | CURRENT | Runtime + capability health | runtime | — | Low | P1 | 1 | Reliability | Diagnostics tests | Diagnostics regression | Health visible | Diagnostics surfaced |
| Logging | CURRENT | Trace + metrics | runtime | — | Low | P1 | 1 | Reliability | Log inspection | Logging regression | Logs structured | Logs structured + retained |
| Configuration | CURRENT (LOCKED) | Validated config | — | Slice 12 startup validation | Low | P1 | 1 | Platform | Config validation | Config regression | All configs validated at startup | Startup validation shipped |
| Security | CURRENT (intent validation) | Full security surface | execution_boundary | SEC.001 resource limits; full secrets management | Medium | P0 | 1 | Security | Security tests | Security regression | SEC.001-003 closed | All SEC IDs retired or mitigated |
| Validation Harness | CURRENT | Self-test + gate validation | diagnostics | — | Low | P1 | 1 | QA | Validation suite | Validation regression | Pass/fail deterministic | Self-test reliable |
| CI | CURRENT | Continuous integration | tests, validation harness | — | Low | P1 | 1 | DevOps | CI runs | CI regression | CI green | CI maintained |
| Telemetry | CURRENT | Runtime metrics | — | — | Low | P1 | 1 | Reliability | Metric inspection | Telemetry regression | Metrics visible | Telemetry retained |
| AURA Integration | CURRENT (200 lines; receiver UNVERIFIED) | Full AURA seam | runtime | Founder approval for receiver activation | High (UNVERIFIED) | P0 | 1→3 | AURA Integration | AURA seam tests | AURA seam regression | Seam observable end-to-end | Receiver active or seam verified stubbed |
| Event Bus | PARTIAL (browser-scoped only — `runtime/browser_runtime/events.py`; corrected 08-09) | Single event authority | — | Convergence Report: duplicate namespaces | Medium | P1 | 2 | Platform | Event bus tests | Event bus regression | One event bus | Duplicate namespaces retired |
| Knowledge Graph | CURRENT (multi-provider) | Single retrieval surface + AURA knowledge graph | knowledge providers, AURA loop | AURA activation | Medium | P1 | 2→3 | Knowledge | Retrieval integration | Retrieval regression | Single retrieval surface | Single retrieval surface shipped |
| Reasoning | ROADMAP | Reasoning layer | AURA loop | Founder approval (Gate C-7) | High (UNVERIFIED) | P0 | 3 | AURA | Reasoning tests | Reasoning regression | Reasoning activates | Reasoning live |
| Beliefs | ROADMAP | Belief state | AURA loop | Founder approval | High (UNVERIFIED) | P0 | 3 | AURA | Belief tests | Belief regression | Beliefs tracked | Beliefs live |
| Goals | ROADMAP / NOT STARTED (no goals module; `executive.py`/`orchestrator.py` absent — corrected 08-09) | Multi-step goal tracking | capability_registry | Build from scratch per Slice 20+ | Medium | P1 | 3 | Planning | Goal tests | Goal regression | Goals live | Goals shipped |
| World Model | ROADMAP | Persistent world state | AURA loop, beliefs | Founder approval | High (UNVERIFIED) | P0 | 3 | AURA | World model tests | World model regression | World model live | World model shipped |
| Reflection | ROADMAP | Reflection on prior interactions | AURA loop, memory | Founder approval | High (UNVERIFIED) | P1 | 4 | AURA | Reflection tests | Reflection regression | Reflection live | Reflection shipped |
| Learning | ROADMAP | Preference + behavior learning | AURA loop, memory | Founder approval | High (UNVERIFIED) | P1 | 4 | AURA | Learning tests | Learning regression | Learning live | Learning shipped |
| Confidence | ROADMAP | Confidence estimates | AURA loop, retriever | Founder approval | Medium | P1 | 4 | AURA | Confidence tests | Confidence regression | Confidence live | Confidence shipped |
| Strategy | ROADMAP | Long-horizon planning | AURA loop, reasoning, goals | Founder approval | High (UNVERIFIED) | P2 | 4 | AURA | Strategy tests | Strategy regression | Strategy live | Strategy shipped |
| Oracle | ROADMAP | Forward-looking projection | AURA loop, world model | Founder approval | High (UNVERIFIED) | P2 | 4 | AURA | Oracle tests | Oracle regression | Oracle live | Oracle shipped |
| Continuity | CURRENT (in-process) | Cross-device continuity | memory, session_context, Aurora | Aurora provisioning | Medium | P1 | 1→5 | Continuity | Continuity tests | Continuity regression | Cross-device continuity | Continuity shipped |
| Identity (AURA) | ROADMAP | AURA identity subsystem | AURA loop, memory | Founder approval | High (UNVERIFIED) | P1 | 3 | AURA | Identity tests | Identity regression | AURA identity live | AURA identity shipped |
| Observations | CURRENT (7863 bytes) | Observation emission | runtime | — | Low | P1 | 1 | AURA Integration | Observation tests | Observation regression | Observations emitted | All exec events observed |
| Execution Fabric | CURRENT | Only execution authority | execution_boundary, capability_registry, providers, mcp_runtime, browser_runtime | — | Low (already enforced) | P0 | 1 | Execution | Execution tests | Execution regression | Only Execution Fabric executes | INV.006 upheld |
| Aurora Backend | PROPOSED/ROADMAP | Permanent cognitive home | Docker, FastAPI, Redis, Neo4j, PostgreSQL, ChromaDB | Provisioning | High (UNVERIFIED) | P2 | 5 | Infrastructure | Aurora integration tests | Aurora regression | Aurora serving KIO | Aurora live |
| Victus Engineering Workspace | CURRENT | Engineering workstation | — | — | Low | P0 | 1 | Engineering | Engineering tests | Engineering regression | Build/test/validation work | Never becomes cognition host |
| Git | CURRENT | Version control | — | — | Low | P0 | 1 | DevOps | Git workflow tests | Git regression | All changes tracked | Maintained |
| Deployment | PROPOSED/ROADMAP | KIO deployment | Aurora, Docker, FastAPI | Aurora provisioning | High (UNVERIFIED) | P2 | 5 | DevOps | Deployment integration | Deployment regression | Aurora deploys KIO | Deployment shipped |
| Docker | PROPOSED/ROADMAP | Containerization | — | Provisioning | High (UNVERIFIED) | P2 | 5 | Infrastructure | Container tests | Container regression | Containers serve Aurora | Docker live |
| FastAPI | PROPOSED/ROADMAP | Cognitive API surface | AURA loop, event bus | Provisioning | High (UNVERIFIED) | P2 | 5 | API | API tests | API regression | API serving cognition | FastAPI live |
| Redis | PROPOSED/ROADMAP | Event bus / cache | Docker | Provisioning | High (UNVERIFIED) | P2 | 5 | Infrastructure | Cache tests | Cache regression | Cache working | Redis live |
| Neo4j | PROPOSED/ROADMAP | Knowledge graph | Docker | Provisioning | High (UNVERIFIED) | P2 | 5 | Knowledge | Graph tests | Graph regression | Graph queries work | Neo4j live |
| PostgreSQL | PROPOSED/ROADMAP | Persistent storage | Docker | Provisioning | High (UNVERIFIED) | P2 | 5 | Infrastructure | DB tests | DB regression | Storage working | PostgreSQL live |
| ChromaDB | PROPOSED/ROADMAP | Vector store | Docker | Provisioning | High (UNVERIFIED) | P2 | 5 | Knowledge | Vector tests | Vector regression | Similarity working | ChromaDB live |
| n8n Automation Layer | PROPOSED/ROADMAP | User-facing automation | execution fabric, MCP runtime | Provisioning | High (UNVERIFIED) | P3 | 5 | Automation | Automation tests | Automation regression | Automation live | n8n live |

---

## SECTION 15 — FEATURE MATURITY MATRIX

Cells use: Not Started / Prototype / Partial / Functional / Production Ready / Enterprise Ready.

| Feature | Current | Tier 1 | Tier 2 | Tier 3 | Tier 4 | Tier 5 | Final Vision |
|---|---|---|---|---|---|---|---|
| Identity | Functional (canon + user resolver CURRENT) | Functional | Functional | Functional | Functional | Production Ready | Production Ready |
| Memory | Functional (basic + FQ-05 CURRENT) | Production Ready | Production Ready | Production Ready | Enterprise Ready | Enterprise Ready | Enterprise Ready |
| Knowledge | Functional (multi-provider CURRENT) | Functional | Production Ready | Production Ready | Enterprise Ready | Enterprise Ready | Enterprise Ready |
| Reasoning | Not Started | Not Started | Not Started | Prototype (Founder-gated) | Partial | Functional | Enterprise Ready |
| Beliefs | Not Started | Not Started | Not Started | Prototype (Founder-gated) | Partial | Functional | Enterprise Ready |
| World Model | Not Started | Not Started | Not Started | Prototype (Founder-gated) | Partial | Functional | Enterprise Ready |
| Goals | Not Started (no goals module — corrected 08-09) | Partial | Partial | Functional | Functional | Production Ready | Enterprise Ready |
| Browser | Partial (reference-resolution bug class fixed 2026-08-09; Shorts/visual/workflow OPEN) | Partial | Functional | Functional | Production Ready | Enterprise Ready | Enterprise Ready |
| Media | Functional (CURRENT 8 modules; playback verified + state-aware control 08-09) | Functional | Functional | Production Ready | Enterprise Ready | Enterprise Ready | Enterprise Ready |
| Desktop | Not Started (empty dir) | Not Started | Not Started | Not Started | Prototype | Functional | Enterprise Ready |
| Voice | Not Started (no module) | Not Started | Not Started | Not Started | Prototype | Functional | Enterprise Ready |
| Mobile | Not Started | Not Started | Not Started | Not Started | Not Started | Prototype | Functional |
| Planning | Partial (CURRENT, unwired) | Partial | Partial | Functional | Functional | Production Ready | Enterprise Ready |
| Automation | Not Started (no n8n) | Not Started | Not Started | Not Started | Partial | Functional | Enterprise Ready |
| Plugins | Not Started | Not Started | Not Started | Not Started | Not Started | Prototype | Functional |
| MCP | Functional (infra only CURRENT) | Functional | Functional (resource limits) | Production Ready | Enterprise Ready | Enterprise Ready | Enterprise Ready |
| Execution | Production Ready (CURRENT LOCKED; truthful multi-step aggregation + verified per-action outcomes 08-09) | Production Ready | Enterprise Ready | Enterprise Ready | Enterprise Ready | Enterprise Ready | Enterprise Ready |
| AURA Integration | Partial (200-line seam, receiver UNVERIFIED) | Functional (seam observable) | Functional | Functional (Founder-gated) | Functional | Production Ready | Enterprise Ready |
| Testing | Functional (CURRENT) | Functional | Functional | Production Ready | Enterprise Ready | Enterprise Ready | Enterprise Ready |
| CI | Functional (CURRENT) | Functional | Functional | Production Ready | Enterprise Ready | Enterprise Ready | Enterprise Ready |
| Validation | Functional (CURRENT) | Functional | Functional | Production Ready | Enterprise Ready | Enterprise Ready | Enterprise Ready |
| Security | Partial (CURRENT intent validation; SEC.001-003 open) | Partial | Functional | Production Ready | Enterprise Ready | Enterprise Ready | Enterprise Ready |
| Developer Experience | Partial (CURRENT runtime introspection) | Partial | Partial | Functional | Functional | Production Ready | Enterprise Ready |

---

## SECTION 16 — AURA INTEGRATION MATRIX (per-Tier)

**Tier 1 — Observation linkage, identity synchronization, session continuity alignment.**
- Observation: aura_integration.py emit seam becomes single chokepoint in runtime pipeline. Observation emission observable via diagnostics.
- Identity: CAP.ID.* self-knowledge unchanged; user identity resolver CURRENT; identity regression suite (canon §15) runs in CI.
- Session continuity: SessionContext unified (Gate C-1 already CURRENT); FQ-05 retention metadata + confidence decay CURRENT.
- AURA-side capability activated in Tier 1: the seam is observable and validated. No AURA receiver required.
- Verification: every execution emits one observation; identity regression passes; FQ-05 governance tests pass.

**Tier 2 — Memory integration, knowledge graph linkage, event propagation.**
- Memory: memory inspection command UX shipped (per MEM.002).
- Knowledge graph: mini_kio/knowledge/retrieval_router.py becomes single retrieval surface; multi-provider failover stable.
- Event propagation: single event bus authority (per Convergence Report).
- AURA-side capability activated in Tier 2: structured observation events for capability resolution, prerequisite gates, identity outcomes. AURA receiver still optional; events observable in logs and metrics regardless.

**Tier 3 — Beliefs, World Model, Reasoning, Confidence.**
- Beliefs: gated on Founder approval of AURA activation (ROAD.002 Gate C-7).
- World Model: gated on Founder approval.
- Reasoning: gated on Founder approval.
- Confidence: confidence estimates on retrieval outputs (subsystem-level) — retriever-side confidence already CURRENT per canon §5 preamble.
- Without Founder approval: Tier 3 delivers the integration seam surface only; AURA receiver remains placeholder returns. No AURA subsystem code is invented in Tier 3.
- With Founder approval: AURA subsystem implementations begin to ship per the Founder-approved scope.

**Tier 4 — Reflection, Learning, Strategy, Oracle.**
- Reflection: gated on Tier 3 Founder approval; otherwise ROADMAP.
- Learning: gated on Tier 3 Founder approval; preference learning otherwise graceful-default.
- Strategy: gated on Tier 3 Founder approval.
- Oracle: gated on Tier 3 Founder approval.
- This Tier also activates Desktop foundation and Voice foundation (separate Founder approval for those surfaces).

**Tier 5 — Production validation, cross-device continuity, operational monitoring.**
- Production validation: full AURA seam end-to-end tests.
- Cross-device continuity: requires Aurora provisioning (Section 0.2).
- Operational monitoring: AURA integration metrics, observation bus volume, receiver health.

Justification for sequencing deviation from prompt's illustrative starting point:
The prompt's Tier 1 lists "Observation linkage, identity synchronization, session continuity alignment." This plan agrees with Observation linkage and identity synchronization in Tier 1, and aligns session continuity (which is already mostly CURRENT post-Gate C-1) with the FQ-05 governance layer in Tier 1. The prompt's Tier 2 ("Memory integration, knowledge graph linkage, event propagation") is preserved. The prompt's Tier 3 ("Beliefs, World Model, Reasoning, Confidence") is preserved but explicitly Founder-gated. The prompt's Tier 4 ("Reflection, Learning, Strategy, Oracle") is preserved and Founder-gated. The prompt's Tier 5 ("Production validation, cross-device continuity, operational monitoring") is preserved.

Reality Override (Section 0.3 enforcement): None of the "AURA subsystem live" claims above is CURRENT. All Tier 3+ AURA subsystem activations are ROADMAP, gated on Founder approval per ROAD.002. The Tier 1/2 work makes the integration seam observable and validated — that is a CURRENT deliverable.

---

## SECTION 17 — AURORA (ACER) ROADMAP

Status: PROPOSED/ROADMAP. No verified evidence in repo (Section 0.2). Aurora is the prompt's intent for KIO's permanent cognitive home.

Evolution areas (per Tier):

| Area | Tier 1 | Tier 2 | Tier 3 | Tier 4 | Tier 5 |
|---|---|---|---|---|---|
| Infrastructure | Not active | Not active | Not active | Provisioning decision gated | Provisioning begins |
| Databases | Local SQLite (mini_kio/backend/db.py) | Local SQLite | Local SQLite | Aurora decision | PostgreSQL + Neo4j + ChromaDB live on Aurora |
| Docker | Not active | Not active | Not active | Aurora decision | Docker stack live |
| Event Bus | Single authority in-process (per Convergence Report) | Single authority in-process | Single authority in-process | Single authority in-process | Redis-backed event bus on Aurora |
| Knowledge Graph | Multi-provider retrieval CURRENT | Single retrieval surface | Single retrieval surface | Single retrieval surface | Neo4j-backed on Aurora |
| Memory Stores | mini_kio/memory/memory_store.py local | Same | Same | Same | PostgreSQL + ChromaDB on Aurora |
| Reasoning Runtime | ROADMAP | ROADMAP | Founder-gated | Founder-gated | Live on Aurora |
| API Layer | ROADMAP | ROADMAP | ROADMAP | Founder-gated | FastAPI on Aurora |
| Monitoring | runtime_logs/ + metrics | Same | Same | Same + structured dashboards | Prometheus/Grafana on Aurora |
| Backups | Manual | Manual | Manual | Manual | Automated on Aurora |
| Disaster Recovery | Not active | Not active | Not active | Aurora decision | Active on Aurora |
| Security | Intent validation CURRENT | Same | Same + MCP resource limits (SEC.001) | Same | Full secrets management on Aurora |
| Observability | Logs + metrics CURRENT | Same | Same | Same | Live dashboards on Aurora |
| Remote Access | Local | Local | Local | Aurora decision | Secure remote access |
| Synchronization | In-process continuity CURRENT | In-process | In-process | Aurora decision | Cross-device sync via Aurora |
| Versioning | Git CURRENT | Same | Same | Same | Same |
| Migration Strategy | None | None | None | Migration plan (data + state) | Migration executed |
| Deployment Strategy | Manual | Manual | Manual | Manual | Docker Compose on Aurora |

Constraint: No Aurora-side capability may be claimed CURRENT in any canon update until gitnexus://repo/Kio/context (or equivalent) has been refreshed to include the Aurora deployment artifacts. Until that refresh, Aurora remains PROPOSED.

Footnote — GitNexus MCP availability: The gitnexus://repo/{name}/context resource is real (documented in AGENTS.md and .claude/skills/gitnexus/gitnexus-guide/SKILL.md), but GitNexus is not guaranteed to be attached as a live MCP server in every session (in the session that produced this plan, the attached MCP servers were github, context7, firecrawl, memory, and serena — GitNexus was not among them). When the GitNexus MCP server is not attached, the equivalent fallback for refreshing/inspecting the repository index is `node .gitnexus/run.cjs analyze` plus inspection of `.gitnexus/meta.json` (both exist and are verified in the repo). Any use of the gitnexus://repo/Kio/context resource in a future session must first confirm the GitNexus MCP server is actually attached; otherwise use the CLI/`.gitnexus` fallback and cite it as such.

---

## SECTION 18 — VICTUS ROADMAP

Status: CURRENT. This is the engineering workstation.

Victus evolution per Tier:

| Role | Tier 1 | Tier 2 | Tier 3 | Tier 4 | Tier 5 |
|---|---|---|---|---|---|
| Engineering Workspace | Active | Active | Active | Active | Active |
| Development Environment | Active (.venv/) | Active | Active | Active | Active |
| Testing Environment | Active (tests/) | Active | Active | Active | Active |
| Simulation Environment | Active (existing bots + scripts) | Active | Active | Active | Active |
| Validation Environment | Active (gate2_* scripts, runtime_logs/) | Active | Active | Active | Active |
| Performance Lab | Not active | Active | Active | Active | Active |
| Integration Lab | Not active | Active (live Telegram/Discord/Browser validation) | Active | Active | Active |
| Release Candidate Environment | Not active | Not active | Active | Active | Active |

Critical constraint (repeated): Victus must NEVER become the permanent home of cognition. Every Tier explicitly states: "All cognition persistence targets in this Tier run on the existing local stores (mini_kio/backend/db.py, mini_kio/memory/memory_store.py, runtime_logs/). Migration to Aurora is gated on Tier 5 Aurora provisioning."

---

## SECTION 19 — INTERFACE ROADMAPS

### 19.0 — All Interfaces (cross-cutting)

| Interface | Current | Intermediate | Final | KIO relationship | AURA relationship | Aurora relationship | Offline | Sync |
|---|---|---|---|---|---|---|---|---|
| Telegram | Production (bot running) | Stable | Stable | Thin transport → KIO dispatch | Same seam as all interfaces | Cognition persists to Aurora when live (ROADMAP); local SQLite fallback otherwise | No (network required) | Conversation state in SessionContext |
| Discord | Partial (transport present; ship status to verify per Slice) | Stable | Stable | Thin transport → KIO dispatch | Same seam | Same as Telegram | No | Same as Telegram |
| CLI | Functional | Stable | Stable | Direct dispatch | Same seam | Same as Telegram | Yes (when KIO process running) | Same as Telegram |
| Desktop | Not Started (empty dir) | Prototype (Tier 4) | Full (Tier 5) | Primary interface; full UI | Same seam | Cognition on Aurora | Yes (with local LLM fallback) | Full sync via Aurora |
| Voice | Not Started (no module) | Prototype (Tier 4) | Full (Tier 5) | Voice I/O → KIO dispatch | Same seam | Same as Desktop | Yes (local STT/TTS) | Full sync |
| Browser | Production (reference-resolution bug class fixed 2026-08-09; Shorts/semantic-media OPEN) | Functional (remaining OPEN items) | Full (Tier 5) | Browser is a capability, not an interface; Web UI as interface is ROADMAP | n/a | n/a | n/a | n/a |
| API | Functional (LLM gateway; not external API) | ROADMAP | Public API gated | Internal API surface | Same seam | Same | Yes (when KIO process running) | Same as Telegram |
| Future Mobile | Not Started | Companion (Tier 5) | Companion | Thin transport → KIO | Same seam | Same as Desktop | Yes (cached context) | Full sync |
| Future Web Dashboard | Not Started | ROADMAP | Production | Thin web client → KIO API | Same seam | Same | Yes (cached) | Same |
| Future Wearables | Not Started | Not Started | ROADMAP | Companion | Same seam | Same | Yes | Same |

### 19.1 Desktop Roadmap (flagship interface)

Per Section 8. Long-term capabilities:
- Conversation — persistent chat across sessions.
- Voice — per Section 9.
- Timeline — chronological observations, memories, actions.
- Goals — multi-step goal tracker.
- Memory Explorer — inspection UX per MEM.001.
- Knowledge Explorer — retrieval + graph viewer.
- Reasoning Viewer — AURA reasoning trace (when active).
- AURA Status — AURA subsystem health.
- Device Status — Victus/Aurora/device presence.
- Browser — embedded browser pane reusing mini_kio/runtime/browser_runtime/.
- Automation — automation center.
- Tasks — task queue.
- Plugins — plugin manager.
- Developer Mode — full introspection.
- Diagnostics — log viewer, event inspector.
- Logs — searchable structured logs.
- Settings — preferences, credential vault (with consent), proactivity level.
- Context Inspector — SessionContext live view.
- Session History — past sessions browseable.
- Knowledge Graph Viewer — interactive graph.
- Execution Queue — currently executing and queued.
- Automation Center — n8n-style automation builder (when n8n arrives).
- Monitoring — runtime metrics dashboards.

Architectural constraint: Desktop reuses every existing subsystem. No new execution layer in Desktop. No new cognition in Desktop. Desktop is a thin client to KIO's dispatch surface.

Tier: Foundation in Tier 4, full in Tier 5.

### 19.2 Voice Roadmap (production-grade)

Per Section 9. Open-source stack:
- STT: faster-whisper (primary), whisper-cpp, vosk (lightweight fallback).
- TTS: piper-tts (primary), coqui-tts (high-quality), edge-tts (free cloud fallback).
- Wake word: openwakeword (primary), porcupine free tier (fallback).
- VAD: silero-vad (primary), webrtcvad (fallback).
- Noise suppression: rnnoise, speexdsp.

Capabilities: wake word, streaming, interruptions, context preservation, natural turn-taking, voice memory, voice identity, offline support, latency goals (≤500ms first-audio local), audio routing, conversation continuity, desktop integration.

Tier: Foundation in Tier 4, full in Tier 5.

### 19.3 Mobile Roadmap (companion interface)

Per Section 10. Architecture: thin client → KIO dispatch surface. Offline: cached context + local LLM fallback (Ollama/Gemini flash local). Sync: Aurora (ROADMAP); local continuity in early Tiers. Notifications: APNs/FCM routed through aura_integration.py event stream. Quick interactions: short, single-turn. Voice mode: identical to Desktop voice. Long-term deployment: Flutter or React Native cross-platform — TBD at Tier 4 Founder Decision.

Tier: Companion in Tier 5.

---

## SECTION 20 — MASTER DOCUMENT CONSOLIDATION

Reviewed documents (verified by directory listing):

| Document | Decision | Reasoning |
|---|---|---|
| KIO_IMPLEMENTATION_PLAN.md | Keep (active Slice ledger) | Contains the ratified Slice breakdown (30 slices); this plan aligns Tiers to Slices. No duplication of Slice details. |
| KIO_IMPLEMENTATION_BLUEPRINT.md | Archive | Superseded by KIO_Implementation_Plan.md (its first line: "Supersedes: KIO_IMPLEMENTATION_BLUEPRINT.md"). Header-noted per documentation strategy. |
| MASTER_CONVERGENCE_PLAN.md | Keep as historical evidence | Repository audit + convergence decisions; this plan cites it for evidence. Not a competing source of truth. |
| KIO_MASTER_EXECUTION_PLAN.md | DOES NOT EXIST as a file (verified — file listing returns no matches). Treat as prompt's request to PRODUCE this document. | This document fills that role. |
| KIO_CANON.md (a.k.a. KIO_IDENTITY_CANON.md) | Keep (sole source of identity truth) | Per Founder canon policy; no second canonical document may be introduced. |
| KIO_CONSTITUTION.md | Keep (enduring principles) | Per Founder constitution policy. |
| GATE2_*.md | Archive as historical | Gate 2 sign-off artifacts; preserved per documentation strategy. |
| GATE3*.md | Archive as historical | Gate 3 status artifacts. |
| PHASE2_2_*.md | Archive as historical | Phase 2.2 plan artifacts. |
| AUDIT_REPORT.md, ENGINEERING_AUDIT_REPORT.md, COMPREHENSIVE_ARCHITECTURAL_AUDIT.md, CANONICAL_ENGINEERING_VALIDATION.md, FINAL_PRE_IMPLEMENTATION_SKILL_AUDIT.md | Keep as historical evidence | Audit findings; this plan cites them. |
| ARCHITECTURE_REVIEW.md, ASYNC_SYNC_REGRESSION_REPORT.md, BROWSER_COMMAND_FIX_REPORT.md, BROWSER_ROOT_CAUSE.md, CAPABILITY_EXPLOITATION_REPORT.md, CONFIG_AUDIT.md, DISCORD_INTEGRATION_REPORT.md, FILES_MODIFIED_AND_VALIDATION.md, CONVERGENCE_PLAN_CHANGELOG.md | Keep as historical evidence | Targeted fix/audit reports. |
| FINAL_FOUNDER_DECISIONS.md, FOUNDER_DECISION_AUDIT.md | Keep (Founder-canonical) | Not superseded; references may inform canon amendments. |
| ANCHORED_SUMMARY.md, AGENTS.md, CLAUDE.md, AGENT_WORKFLOW.md | Keep (operational) | Working instructions for agents and tooling. |
| kio_xml_chunks/, kio_final/, snapshots/, repos/, legacy/, gstack/, missions/, workspace/, tools/, external/, runtime_logs/, bot_*.log, debug_trace.log | Keep as workspace state; archive individual items as appropriate per documentation strategy. No mass delete. | |

Target state:
- ONE canonical architectural truth: KIO_CONSTITUTION.md (enduring principles) + KIO_IDENTITY_CANON.md (sole canonical source for identity/architecture/capability/governance/philosophy/limitations/roadmap facts).
- ONE canonical implementation roadmap: KIO_Implementation_Plan.md (Slice ledger) + THIS plan (Tier-level capability gates and subsystem dependency map).
- ONE canonical cognitive/identity truth: KIO_IDENTITY_CANON.md.
- All other documents become supporting or historical documentation, header-noted per the existing documentation strategy. Never mass-deleted.

---

## SECTION 21 — FEATURE EVOLUTION & CAPABILITY GATES (per Phase)

Phase mapping (Tier ↔ Slice):
- Tier 1 = Slices 1–9 (foundation: convergence, prerequisite gate, credentials, identity, session continuity, capability unification, FQ-05 memory governance, FQ-06 override policy, startup config validation).
- Tier 2 = Slices 10–15 (situational awareness + live integration & validation phase).
- Tier 3 = Slices 16–22 (situational awareness phase, including planning wiring, browser reference-resolution bug fix, AURA activation gate).
- Tier 4 = Slices 23–27 (proactivity, companion evolution, voice/desktop foundation).
- Tier 5 = Slices 28–30 (cross-device continuity, production hardening, AURA integration validation).

(Note: Slices 19 was marked optional/SKIPPED per KIO_Implementation_Plan.md Line 5.)

### Media Execution Status (cross-cutting, non-gate update — 2026-08-08)

**COMPLETED — YouTube playback/control recovery** (commit `b5db667`, `fix(media): stabilize YouTube playback and control`):
Injected YouTube player scripts made self-contained; Chrome extension/player-script state contract repaired; extension build compatibility/build gate enforced; YouTube playback state verification restored; controlled YouTube search/replay routing stabilized; media playback identity/state preserved; normal YouTube pause/resume, play-it, play-again, next-video, and mute/unmute restored; live playback verification completed.
Proven root cause: `chrome.scripting.executeScript({func: ...})` serializes the supplied function independently of the background service-worker lexical scope. Several injected player-control/state functions referenced outer-scope helpers (player-resolution helpers, build constants) that did not exist inside the injected page context — so the functions returned undefined/non-state payloads, state verification rejected the result, playback reported `script 'play' returned non-state payload`, and KIO then reported `Couldn't play X on YouTube`. Fix: the injected functions were made self-contained.
Live validation subsequently confirmed: Play / Pause / Resume / Play it / Play again / Play next video / YouTube search / Search again / Mute / Unmute. This is NOT "all media functionality complete."

**DOCUMENTED** (commit `d80c706`, `docs: sync media implementation status`): authoritative status recorded in `KIO_Implementation_Plan.md` (Revision 4, 2026-08-08) and `KNOWN_ISSUES.md`. This plan records only the authoritative status/completed work/next position — full issue detail lives in those documents; no duplication here.

**NEXT (OPEN) — System-level media entity resolution / semantic selection:** KIO can still select a lexically related but semantically incorrect YouTube video (observed: `Play brand new day`, `Play lm game trailer`). This is NOT a basic playback failure. The next solution must NOT be another collection of keyword filters, candidate-score tweaks, channel hardcodes, title special cases, or first-result/second-result patches. The next investigation must determine why the intended media entity is not resolved before YouTube candidate retrieval/selection. Required direction: user request → normalization → intent/content-type understanding → media entity resolution → search strategy/query generation → candidate retrieval → entity/content validation → canonical candidate selection → actual video-ID verification → playback. The implementation must reuse/converge existing KIO media-intelligence, entity-resolution, query-intelligence, and candidate infrastructure where possible — do NOT invent a parallel media-intelligence architecture.

**THEN (OPEN / INVESTIGATION PENDING) — YouTube Shorts pause/resume:** normal YouTube playback control is working; pause/resume for YouTube Shorts is not yet confirmed reliable. No root cause asserted. The Shorts investigation must compare the existing normal YouTube player-control path against `youtube.com/shorts/...` and determine the actual player/control-state difference before modifying anything. Shorts are NOT claimed fixed.

### Execution System + Contextual Control Milestone (cross-cutting, non-gate update — 2026-08-09)

**COMPLETED — Execution-system target-identity fix + three user-visible capabilities** (evidence: `KIO_TARGET_IDENTITY_FORENSIC_AUDIT_20260809.md`, `KIO_EXECUTION_SYSTEM_FIX_AND_CAPABILITIES_20260809.md`):
The failure chain "Open ChatGPT → Close it killed the whole Chrome session" was traced to six systemic defects and fixed at the owning layers: (1) web-app opens serialized as `chrome::open_url::<url>::<name>` capability strings; (2) `close_app` collapsed targets via `key.split("::")[0]` → killed the browser process for web-app targets; (3) `close_tab` escalated to `close_app` on failure (scope escalation); (4) raw serialized targets stored as conversational referents; (5) web opens asserted success without tab-identity verification; (6) multi-step requests reported blanket "done" from unverified ACKs, and raw internal strings leaked into responses.
Fixes (all in current working tree, uncommitted at HEAD): canonical target identity (`mini_kio/core/target_ref.py` — parse/safe-name/display-name); web-target close at tab scope (`_close_web_target`) — never a browser kill; web-open tab-identity verification (`_verify_web_tab_opened`); referent sanitization in `context_manager` + `execution_boundary`; brand-cased display names in the response formatter (no raw URLs/PIDs/capability strings); truthful per-step verification + partial-success aggregation in `command_router._execute_multi_step`; focus/switch for browser tabs + native app windows; "what's open"/"what's playing" intents.
**USER-VISIBLE CAPABILITIES (live-verified):** (A) context-aware computer control — "What's open?", switch/focus targets; (B) composed multi-action tasks — "Open ChatGPT and Telegram" with independent per-target verification; (C) state-aware media control — "What's playing?", verified Pause/Resume, contextual media references.
**DEMO SCENARIOS (live Telegram, 2026-08-09):** `Open ChatGPT` → "Opened ChatGPT in Chrome." · `Close it` → "Closed ChatGPT tab." (Chrome process count unchanged — tab scope, not browser kill) · `What is open?` → one canonical snapshot: `• Identity — tab detail` per tab (ChatGPT — "KIO - Commit Review Prompt"), `(active)` on the single active tab, `(opened by KIO)` provenance, `Browser:` host + `Apps:` native lines; the whole natural state-query family (what's open / what am i using / what's running / which apps are open / show open apps / KIO-prefixed) routes deterministically — never an LLM guess; no raw URLs/`::`/pids · `Play Never Gonna Give You Up` → playback verified `paused=False` · `Pause it` → "Paused." · `What is playing?` → "Paused on Never Gonna Give You Up." · `Resume it` → "Resumed." · `Open ChatGPT and Telegram` → "Opened ChatGPT and Telegram." · `Hi` during media ≈1.7s while media continued · `Close ChatGPT tab` / `Close Telegram` → tab-scoped closes, Chrome alive.
**ACCEPTANCE EVIDENCE:** 26 new targeted tests (`tests/test_target_identity_fixes.py`) + 200 targeted regression tests green across 13 suites (media recovery, connector reconnect, state verification, pause/resume, EFG routing, R11 search, pending action, history pollution, gate5 registry/repairs); pre-existing failures baseline-identical. No new architecture was introduced — fixes route through the existing pipeline/coordinator/boundary.
**NOT CHANGED:** media entity resolution / semantic selection (OPEN), Shorts (OPEN), AURA (unchanged), Goals (still absent). **CHANGED 2026-08-09 (Slice 8):** Credential Vault Core is IMPLEMENTED (`mini_kio/core/credential_vault.py` + `credentials` table; 22 tests incl. secret-leak proof). **CHANGED 2026-08-10 (Slice 9):** Credential Vault Lifecycle is IMPLEMENTED (`validate/status/is_expired/refresh/revoke_by_target/reauthentication_required/needs_attention` + gate prerequisites + secret-free user surface; 16 tests + live Telegram). **CHANGED 2026-08-10 (System Awareness refinement, pre-Slice-9):** KIO is now genuinely system-aware on Windows — (1) generic installed-application inventory (`what apps do i have` → 80+ real apps from Start Menu/registry/WindowsApps; new OPERATIONAL `app_inventory` + `system_summary` routes); (2) verified multi-word web-entity synthesis (`open stack overflow` → stackoverflow.com with DNS + title verification rejecting parked/for-sale/domain-echo pages; short `Opened X.` confirmations per the UX rule, modality kept structured so close/focus still resolve to the web target); (3) empty-title (elevated) windows no longer dropped from `what's open` (generic fix — elevated apps like DaVinci Resolve are observable); (4) battery/power is a real health dimension (charging state, low/critical thresholds, honest unavailable on desktops, remaining-time when exposed); (5) `is <provider> connected` routes to truthful CREDENTIAL state for vault-known providers. All live-verified via real Telegram one message at a time on the real machine; 283 targeted tests green in touched areas, full-suite delta vs baseline = 0 new failures. Not a roadmap slice — no Slice status changed; no new registries or parallel systems introduced.

### Operational Awareness capability (cross-cutting, non-gate update — 2026-08-09)

**COMPLETED — pre-Slice-9 operational-awareness refinement** (evidence: `tests/test_operational_health.py`; live Telegram 2026-08-09): KIO now truthfully reports its own health (`KIO is healthy. Uptime: … Browser: connected · Telegram: connected · Media: ready · Services: healthy · Tools: connected`), status/activity (`KIO is ready. Uptime: … Current activity: Idle`), KIO uptime vs system uptime, system health (CPU / RAM / GPU / storage / battery via psutil + guarded nvidia-smi probe), per-component status (`Is the browser connected?` → `The browser is connected.`), and a "what's wrong" summary from real integrity state — all through ONE deterministic path (`IntentType.OPERATIONAL` → `mini_kio/core/operational_health.py`; classifier family in `pipeline/__init__.py`), with `/health /status /uptime /system /systemhealth` plus natural variants (`KIO health`, `are you ok`, `how is my computer`, `CPU usage`, `is my battery charging`, …). Values are real and cross-checked (live CPU 21–42%, RAM 95%, GPU 0% vs psutil/nvidia-smi); unavailable metrics are reported honestly, never 0; responses contain no implementation tokens. Reading state is side-effect free (no polling loops, no telemetry). No new roadmap slice and no Slice status changed — bounded capability refinement before Slice 9.

### Completion estimate (recalculated 2026-08-09, honest method)
Prior audit (08-08): subsystems fully implemented 37% (26/71) · weighted ~45–50% · user-visible ~35–40% · architectural ~50% · AURA ~10%. Recalculation method: re-derived from Section 14's 71-subsystem maturity table, counting only subsystems whose current state is genuinely implemented per source evidence (not plan prose), after the 08-09 fixes and live verification.

| Lens | 08-08 audit | 08-09 recalculated | Delta source |
|---|---|---|---|
| Subsystems fully implemented | 37% (26/71) | ~39% (28/71) | Browser reference-resolution class fixed (previously counted broken) + Credential Vault Core (Slice 8) implemented 2026-08-09 |
| Weighted | ~45–50% | ~50–55% | Execution fabric + multi-step aggregation + browser/media verification hardened |
| User-visible | ~35–40% | ~45–50% | Three new user-visible capabilities live-verified (contextual control, multi-action, state-aware media) |
| Architectural | ~50% | ~52–55% | Target-identity abstraction + response/verification contracts |
| AURA | ~10% | ~10% (unchanged) | No AURA work in 08-09 |

Numbers are estimates, not claims of completion. ROADMAP items (AURA loop, Goals, Credential Vault Lifecycle [Slice 9], Desktop/Voice/Mobile, Tiers 4-5) remain unchanged.

### 21.1 Engineering Work (per Tier)

**Tier 1 (corrected 2026-08-09 — false completion claims removed):**
- Built: ARCH.003 capability-discovery unification (Slice 6, `resolve_capability`), Identity Resolver wiring (Slice 10, `mini_kio/resolvers/identity_resolver.py`), Session Continuity serialization (Slices 11-12), FQ-05 memory governance (retention metadata, confidence decay, inspection/correction/deletion), FQ-06 override policy (disagree-once-then-defer), execution boundary + pipeline coordinator (LOCKED), canonical target identity + referent sanitization + truthful multi-step aggregation (08-09 cross-cutting).
- **CHANGED 2026-08-10: Credential Vault Lifecycle (Slice 9) IS implemented** on the Slice 8 canonical (`mini_kio/core/credential_vault.py` + `credentials` metadata table; keyring-backed; consent-gated): `validate/status/is_expired/refresh/revoke_by_target/reauthentication_required/needs_attention` + state-qualified Execution-Gate prerequisites (`credential_block_reason`) + secret-free `credential_management_result` surface; 16 targeted tests (`tests/test_slice9_credential_lifecycle.py`) + live Telegram verification. **Startup Configuration Validation (Slice 14) is NOT implemented** — no framework exists.
- Retired: Phase 0 dead code (aura/ stubs, entity_state_engine, browser/automation). **CORRECTED: duplicate registries are NOT fully consolidated** — `capability_registry`, `provider_registry`, `browser_session_registry`, `media_registry` coexist; CapabilityResolver remains the unified query path (`resolve_capability`), full registry consolidation still on D-08/ARCH.003.
- Merged: 6 legacy state systems into SessionContext (per Convergence Report; referent sanitization added 08-09).
- Canonical: CapabilityRegistry as single discoverable capability surface — PARTIAL (see correction above).
- Historical: Phase 0 dead code removal (committed).
- Documentation changes: KIO_Implementation_Plan.md slice statuses reconciled; this plan's Tier 1 markers corrected to match reality; canon amendments per Section 16 of canon for any ID changes.

**Tier 2:**
- Built: Single retrieval surface (Knowledge), single event bus authority, MCP resource limits (SEC.001 closure), response composer refactor (decomposed from monolith).
- Retired: duplicate event namespaces (per Convergence Report).
- Merged: monolithic conversation_responder.py decomposed into composable sections.
- Canonical: Knowledge retrieval router single authority.
- Historical: backup_llm/ duplicate (consolidated into LLM Gateway path).
- Documentation changes: per Slice.

**Tier 3:**
- Built: Planning layer wiring (executive, task_engine, orchestrator actually called by routing path), Browser reference-resolution bug fix (LIM.002), AURA activation gate (if Founder-approved).
- Retired: top-level browser/ facade per Convergence Report recommendation.
- Merged: planning layer integrated.
- Canonical: AURA subsystems (if Founder-approved) become canonical per Founder amendment.
- Historical: AURA seam surface validated as the Tier-3 deliverable even without AURA receiver.

**Tier 4:**
- Built: Desktop foundation, Voice foundation, AURA Reflection/Learning/Strategy/Oracle subsystems (if Tier 3 Founder-approved).
- Retired: none.
- Merged: media intelligence fully activated.
- Canonical: Desktop + Voice presence in canon per Founder amendment.

**Tier 5:**
- Built: Aurora provisioning (if gated green-light), cross-device continuity, production observability, full integration test suite.
- Retired: Victus as cognition host (constraint upheld by definition).
- Merged: all subsystems into production state.
- Canonical: Aurora capability IDs added to canon per Founder amendment.

### 21.2 User-Visible Features (per Tier)

**Tier 1 — "KIO Can Now":**
- Remembers user identity across sessions (Identity Resolver).
- Survives restart (Session Continuity, in-process).
- Gates execution through the execution boundary and pipeline coordinator (Execution Fabric). **CORRECTED: prerequisite-gate prompting is not implemented as designed (Slices 8-9/14 absent).**
- Inspects, corrects, and deletes individual memories (FQ-05).
- Disagrees once with the user, then defers on repeat (FQ-06).
- **CORRECTED: startup configuration validation (Slice 14) is NOT implemented.**
- **ADDED 08-09: resolves and controls exact targets (app · browser · tab · webapp · media) without scope escalation; answers "What's open?" and "What's playing?"; executes composed multi-action requests with truthful per-target verification.**

**Tier 2 — "KIO Can Now":**
- Composes responses from explicit sections (intent ack, memory recall, knowledge result, character voice) instead of one monolithic LLM prompt.
- Routes every cross-process event through one event bus.
- Fails closed on missing IDs in canon lookup (already CURRENT per KIO_IDENTITY_CANON.md §11; preserved).
- Uses one retrieval surface across all knowledge providers with failover.

**Tier 3 — "KIO Can Now" (assuming AURA not activated):**
- Actually invokes the planning layer — **CORRECTED 08-09: no planning layer exists** (`executive.py`/`orchestrator.py` absent; multi-step command composition lives in `command_router._execute_multi_step`, which is live and truthful).
- Resolves browser references ("play it", "Close it", "Pause it", "first result") — **substantially delivered 08-09** (target identity + contextual referents + live verification). Remaining OPEN: YouTube Shorts control and semantic media selection.
- AURA seam is observably end-to-end (every execution emits one observation through one chokepoint) — PARTIAL (emission wired via `get_observation_stream`; receiver UNVERIFIED).

**Tier 3 — "KIO Can Now" (assuming AURA activated by Founder):**
- All of the above, plus AURA Beliefs, World Model, Reasoning, Confidence subsystems are live (subject to Founder-approved scope).

**Tier 4 — "KIO Can Now":**
- Desktop UI surfaces: conversation, voice, browser, timeline, goals, knowledge, memories, tasks, plugins, diagnostics, developer mode.
- Voice: wake word, streaming, interruptions, voice memory, voice identity, offline voice.
- AURA Reflection, Learning, Strategy, Oracle subsystems live (subject to Tier 3 Founder approval).

**Tier 5 — "KIO Can Now":**
- Cross-device continuity (conversation follows user from Desktop to Telegram to Voice to Mobile).
- Production observability dashboards.
- Full integration test suite green.
- Every capability has a verified-by chain in canon.

### 21.3 Demo Scenarios (per Tier)

**Tier 1 — Trip planning (before/after).**
- Before: User says "Plan a trip to Lisbon next month." KIO fabricates flights and dates or fails silently.
- After: User says "Plan a trip to Lisbon next month." KIO recognizes a goal with sub-steps (dates, flights, lodging, itinerary), asks the user for prerequisite dates, stores preferences learned in this session ("prefers morning flights"), persists to memory with retention metadata, and resumes across a restart.

**Tier 2 — Knowledge retrieval (before/after).**
- Before: User asks "Interstellar cast." KIO's heuristic misroutes to an unrelated web-summary template.
- After: User asks "Interstellar cast." KIO routes through the single knowledge retrieval surface, returns the cast list, optionally cites sources.

**Tier 3 — Browser reference (before/after; substantially delivered 2026-08-09).**
- Before: User says "Close it" after "Open ChatGPT" — KIO collapsed the target and killed the whole Chrome session.
- After (live-verified): "Close it" closes the ChatGPT tab (Chrome alive); "Pause it"/"Resume it" resolve the actual current media; "What's playing?" reads live registry state; "What's open?" lists tabs + tracked apps. Remaining OPEN: Shorts control, semantic media selection.

**Tier 4 — Desktop continuity (before/after).**
- Before: User starts a research task on Telegram, switches to Desktop — no continuity.
- After: Same scenario; Desktop Timeline shows the Telegram conversation, knowledge explorer shows the entities KIO noticed, and the research continues seamlessly.

**Tier 5 — Cross-device continuity (before/after).**
- Before: User's last conversation on Desktop is invisible on Mobile.
- After: Mobile companion shows the same conversation, same memories, same goals.

### 21.4 Acceptance Tests (per Tier)

For every Tier, the following test categories must pass:
- Manual tests: real user-driven scenarios per Tier 1 / 2 / 3 / 4 / 5 demo above.
- Automated tests: integration + unit + regression suite (per tests/ directory).
- Telegram tests: live Telegram validation for every Tier that touches Telegram.
- Desktop tests: live Desktop validation for Tier 4+5.
- Voice tests: live Voice validation for Tier 4+5.
- Browser tests: Playwright MCP live validation, including reference-resolution regression.
- MCP tests: MCP integration + crash isolation + resource limit tests.
- Media tests: media intelligence + recommendation integration.
- Memory tests: FQ-05 governance + inspection UX.
- AURA tests: seam observability (Tier 1), seam end-to-end (Tier 3), subsystem integration (Tier 3+ if activated).
- Regression tests: full regression suite per Slice work.
- Performance tests: latency, memory, throughput budgets per existing constants (HARD_LIMIT_MB = 190).
- Failure-recovery tests: every failure path documented and tested.

### 21.5 Capability Matrix (master)

| Capability | Tier 1 | Tier 2 | Tier 3 | Tier 4 | Tier 5 | Production |
|---|---|---|---|---|---|---|
| Conversation | Functional | Functional | Functional | Production Ready | Enterprise Ready | Enterprise Ready |
| Memory | Production Ready | Production Ready | Production Ready | Enterprise Ready | Enterprise Ready | Enterprise Ready |
| Identity | Functional | Functional | Functional | Functional | Production Ready | Production Ready |
| Reasoning | Not Started | Not Started | Prototype (Founder-gated) | Partial | Functional | Enterprise Ready |
| Browser | Partial (ref-resolution class fixed 08-09) | Functional | Functional | Production Ready | Enterprise Ready | Enterprise Ready |
| Desktop | Not Started | Not Started | Not Started | Prototype | Functional | Enterprise Ready |
| Voice | Not Started | Not Started | Not Started | Prototype | Functional | Enterprise Ready |
| Media | Functional (playback + state-aware control verified 08-09) | Functional | Production Ready | Enterprise Ready | Enterprise Ready | Enterprise Ready |
| Goals | Not Started | Partial | Functional | Functional | Production Ready | Enterprise Ready |
| Planning | Partial | Partial | Functional | Functional | Production Ready | Enterprise Ready |
| Knowledge | Functional | Production Ready | Production Ready | Enterprise Ready | Enterprise Ready | Enterprise Ready |
| Reflection | Not Started | Not Started | Not Started | Partial | Functional | Enterprise Ready |
| Learning | Not Started | Not Started | Not Started | Partial | Functional | Enterprise Ready |
| Confidence | Not Started | Not Started | Prototype | Partial | Functional | Enterprise Ready |
| Automation | Not Started | Not Started | Not Started | Partial | Functional | Enterprise Ready |
| Plugins | Not Started | Not Started | Not Started | Not Started | Prototype | Functional |
| Desktop UI | Not Started | Not Started | Not Started | Prototype | Functional | Enterprise Ready |
| Mobile | Not Started | Not Started | Not Started | Not Started | Prototype | Functional |
| AURA | Not Started | Not Started | Prototype (Founder-gated) | Partial | Functional | Enterprise Ready |
| Execution | Production Ready | Enterprise Ready | Enterprise Ready | Enterprise Ready | Enterprise Ready | Enterprise Ready |
| MCP | Functional | Functional | Production Ready | Enterprise Ready | Enterprise Ready | Enterprise Ready |
| Diagnostics | Functional | Functional | Production Ready | Enterprise Ready | Enterprise Ready | Enterprise Ready |
| Security | Partial | Functional | Production Ready | Enterprise Ready | Enterprise Ready | Enterprise Ready |
| Monitoring | Functional | Functional | Production Ready | Enterprise Ready | Enterprise Ready | Enterprise Ready |
| Developer Tools | Partial | Partial | Functional | Functional | Production Ready | Enterprise Ready |
| Timeline | Not Started | Not Started | Not Started | Prototype | Functional | Enterprise Ready |
| Knowledge Graph | Not Started | Not Started | Not Started | Prototype | Functional | Enterprise Ready |

### 21.6 "KIO Can Now..." List (end of every Tier)

Per Tier in 21.2 above. Grounded in actual built artifacts, not aspirational filler.

### 21.7 AURA Feature Evolution (per Tier)

- Tier 1: AURA seam is observable end-to-end. Every KIO execution emits one structured observation through aura_integration.py. The receiver remains optional; the seam is the deliverable.
- Tier 2: Observation bus volume becomes a runtime metric. AURA receiver activation remains optional.
- Tier 3 (Founder-gated): AURA Beliefs, World Model, Reasoning, Confidence subsystems may be activated by Founder Decision. Per ROAD.002 Gate C-7.
- Tier 4 (Founder-gated): AURA Reflection, Learning, Strategy, Oracle subsystems may be activated.
- Tier 5: Full AURA integration testing; production observability of AURA subsystem health.

### 21.8 Interface Feature Evolution (per Tier, per interface)

Already covered in 21.2 and Section 19. Each interface is named explicitly per Tier with current/new/limitations/target capability/validation.

### 21.9 Aurora Feature Evolution (per Tier)

- Tier 1: Aurora remains PROPOSED. No migration of cognition persistence in Tier 1.
- Tier 2: Aurora decision remains PROPOSED. Local stores continue to host cognition.
- Tier 3: Aurora decision remains PROPOSED. Local stores continue to host cognition. Persistent observations, memory storage, knowledge graph — all local.
- Tier 4: Aurora provisioning decision gated on Founder approval.
- Tier 5: Aurora provisioning begins if Founder-approved. Cross-device continuity live via Aurora. Disaster recovery live. Operational dashboards live.

### 21.10 Victus Feature Evolution (per Tier)

- Tier 1: Victus is the active engineering workspace; .venv/, tests/, runtime_logs/, .playwright-mcp/, .chrome_validation_profile/, .kio/ already in use. Constraint: never becomes permanent cognition host.
- Tier 2: Performance Lab active; Integration Lab active (live Telegram/Discord/Browser validation).
- Tier 3: Release Candidate environment active.
- Tier 4: CI/CD + integration testing + RC generation fully active.
- Tier 5: All Victus roles active. Constraint upheld: cognition persistence still local in stores, Aurora migration gated.

### 21.11 Definition of Done (per Phase)

A phase is complete only if ALL of the following are true:
 1. Engineering work completed (per 21.1).
 2. Documentation updated (per 21.1).
 3. KIO_CANON.md updated where required (through the amendment process, not directly — per Founder canon policy Section 16).
 4. Validation harness passes (per Tier 1 slice 12 framework + per Tier acceptance tests in 21.4).
 5. Regression suite passes (per existing regression artifacts).
 6. User-visible features delivered (per 21.2).
 7. Desktop/Voice/Browser/MCP/Media validation passes as applicable per Tier.
 8. AURA integration validated (per 21.7).
 9a. Per-Tier falsifiable "no cognition off Victus" audit (Tier 1–4): each Tier produces a runnable audit asserting that no cognition-persistence target lives outside Victus — evidence-backed (file paths, processes, stores), failing if any cognition data lives off Victus. This upholds the constraint "no cognition on Aurora before Tier 5" and is falsifiable (it can fail and be run per Tier).
 9b. Aurora end-to-end synchronization test (Tier 5 only): the single Tier-5 test that Aurora actually receives synchronized cognition — runnable only after Aurora provisioning per Section 17, asserting Aurora is receiving cognition per the Section 17 constraint.
10. Capability matrix updated (per 21.5).
11. Historical documents updated if required (per Section 20).
12. Acceptance scenarios demonstrated successfully (per 21.3).

Any failing item keeps the phase OPEN.

---

## SECTION 22 — KIO EXPERIENCE, PERSONALITY & INTERACTION EVOLUTION

### 22.1 Personality Evolution

KIO's personality is defined in mini_kio/llm/KIO_character_knowledge.py (Character Bible v2, ~300 lines, CURRENT). Per Tier, the personality composition evolves:
- Core personality: helpful, curious, honest, precise, emotionally aware but not performative. CURRENT in Character Bible.
- Tone: warm-but-not-effusive; defaults to clarity over charm. CURRENT.
- Conversation style: concise in transactional exchanges, expansive in exploratory ones. CURRENT; refined in Tier 2 with composer decomposition.
- Humor: situational, dry, never at user's expense. CURRENT in Character Bible; refined through Tier 4 reflection feedback.
- Curiosity: asks one clarifying question when genuinely ambiguous (INV.008a), not zero questions when one is needed. CURRENT.
- Confidence: calibrated — high-confidence claims are high-confidence; uncertainty is surfaced (per KIO_IDENTITY_CANON.md §11). CURRENT in retriever confidence attachment.
- Humility: disagrees once, then defers per FQ-06 (Tier 1).
- Empathy: emotionally aware conversation pacing per Section 22.2 (Tier 4+).
- Initiative: gated by CAP.AUTONOMY.001 + INV.006. Per Founder Decision only — no autonomous conversation initiation.
- Per-mode variants:
  - Professional: clarity, no filler. CURRENT.
  - Casual: lighter tone, humor permitted. CURRENT in Character Bible.
  - Focus: minimal noise, surface critical info only. Tier 4.
  - Learning: patient, scaffolded, check understanding. Tier 4.
  - Companion: warmer, more contextual, remembers prior emotional state. Tier 4+ (gated on memory + emotional intelligence).
  - Productivity: action-oriented, minimal preamble. CURRENT in command-driven flows.
  - Developer: includes technical detail, surfaces assumptions, links to source. Tier 4.
  - Debug: shows reasoning, exposes state. Tier 4.
  - Emergency: concise, action-focused, no humor. Tier 4.
  - Silent: present but doesn't speak. Tier 4 (presence modes per 22.6).
  - Presentation: speech-friendly, structured, no embedded links mid-flow. Tier 4.

### 22.2 Emotional Intelligence

- Emotion recognition: current state is limited to text-pattern matching; Tier 4+ adds AURA Reflection feedback integration.
- Emotion memory: Tier 4+ (gated on memory subsystem maturity).
- Emotional continuity: Tier 4+ — KIO remembers emotional state across sessions.
- Relationship memory: Tier 4+ — per MEM.001 policy.
- Conversation pacing: Tier 2+ — response composer adjusts pacing.
- Supportive conversations: Tier 4+ — AURA Reflection suggests supportive framings.
- Motivation: Tier 4+ — AURA strategy informs long-term motivation surfacing.
- Celebration: Tier 4+ — AURA Reflection notices achievements.
- Stress/burnout detection: Tier 4+ — pattern-based.
- Encouragement: Tier 4+.
- Comfort: Tier 4+ — only on user initiation.
- Humor adaptation: Tier 4+ — AURA Reflection tunes humor.
- Conversation energy: Tier 2+ — composer reflects energy in tone.
- Empathy depth: Tier 4+.
- Context-sensitive emotional behavior: Tier 4+.

Design constraint (per prompt): Avoid scripted responses. Behavior evolves naturally as cognition improves.

### 22.3 KIO Moods

KIO moods are not cosmetic — each mood affects conversation, voice, initiative, reasoning, notifications, desktop presence, animation, response pacing.
- Focused, Relaxed, Curious, Creative, Observing, Planning, Busy, Thinking, Learning, Reflecting, Helping, Researching, Idle, Sleeping, Explaining, Coding, Automation, Investigating.

Each mood is a runtime state in conversation_orchestrator.py's state machine (currently 4 states per Convergence Report; Tier 2 extension to include PLANNING/EXECUTING/VERIFYING; Tier 4 adds mood sub-states).

### 22.4 KIO Modes

Per the prompt's enumeration:
- Assistant, Companion, Developer, Researcher, Engineer, Tutor, Planner, Operator, Browser Mode, Media Mode, Coding Mode, Learning Mode, Presentation Mode, Meeting Mode, Gaming Mode, Travel Mode, Offline Mode, Emergency Mode, Guest Mode, Safe Mode.

Each mode specifies: Purpose, Activation, Capabilities, Restrictions, Interface changes, Voice changes, AURA interaction. Modes are activated explicitly by user or by context (e.g., full-screen app → Meeting Mode; low battery → Offline Mode). Modes never act autonomously — they shape KIO's response framing.

### 22.5 Voice Roadmap (experience layer)

Per Section 9. Engineering details: STT/TTS/VAD/wake word. Experience details: voice identity (consistent speaker), voice personality (matches Character Bible tone), voice consistency, streaming conversations, interruptions, turn-taking, back-channeling, natural pauses, speech timing, emotion-aware speech, context-aware speech, voice memory, wake word, conversation continuation, offline voice, latency goals (≤500ms first-audio local), noise handling, voice confidence, VAD, audio routing, conversation overlap, open-source stack, voice cloning (FUTURE gated), audio caching, speech adaptation, voice accessibility (captions, keyboard fallback).

### 22.6 KIO Presence

Per the prompt's enumeration: Always visible, Docked, Floating, Compact, Minimal, Transparent, Sidebar, Full Companion Window, Workspace Mode, Developer Dashboard, Voice Bubble, Notification Bubble, Overlay, Tray Mode, Background Mode, Invisible Mode.

Transitions:
- Docked ↔ Floating: drag.
- Compact ↔ Minimal: settings toggle.
- Transparent: hover-fade, configurable.
- Sidebar ↔ Full: layout switch.
- Workspace Mode ↔ Developer Dashboard: explicit mode change.
- Voice Bubble ↔ Overlay: voice activation.
- Tray Mode: minimize to tray.
- Background Mode: continue running, no window.
- Invisible Mode: continue running, no visible presence (debugging only).

### 22.7 Desktop Activation Model

Phased activation (not always-on-launch). Per Tier:
- Tier 1–2: hotkey activation (configurable), system tray icon, desktop shortcut.
- Tier 3: voice wake word (openwakeword/porcupine), mouse corner activation.
- Tier 4: hotkey customization, touch gesture (touch devices), notification icon.
- Tier 5: clap activation (hardware-dependent, optional), finger snap activation (research only).

Each activation method must justify itself against existing alternatives — no method invented without evidence.

### 22.7a Identity-Gated Activation (owner recognition)

Status: ROADMAP. Blocked on CAP.VISION.001.

Scope: This is strictly an activation gate — whether KIO surfaces itself (window, tray, voice, notifications) when a user is present at a Victus session. It is NOT identification of who the person is, NOT a security boundary, and NOT a detection-and-rejection system.

- Silent dormancy: When KIO is running on Victus and the session owner is not verified, KIO remains dormant and does not surface itself. This is silent dormancy, NOT detection-and-rejection: KIO does not attempt to identify, label, or reject a non-owner. It simply does not activate for a session it cannot verify as the owner's.
- No storage of unverified-person data: Nothing is observed, stored, or reasoned about for an unverified session. No biometrics, no identity data, no behavioral profile is captured from a person who has not been verified as the owner. Unverified presence produces no records at all.
- Activation gate only: The only action this feature enables is KIO's self-presentation. It does not unlock capabilities, does not authorize any action, and does not change what a verified owner can do. Owner verification for capability use remains a separate, explicit, consent-based mechanism.
- Capability dependency: gated on CAP.VISION.001 (verified owner-presence recognition). Without that canon capability, this feature remains dormant.
- Extension (ROADMAP): remote owner notification ("your KIO is running on Victus, session active") inherits Section 23.4 consent rules — the remote owner must have opted in; notifications to non-owners are never generated.

### 22.8 Hiding & Visibility

- Hide desktop interface: explicit.
- Minimize to tray: standard.
- Auto-hide: configurable timeout.
- Transparency: hover-fade configurable.
- Overlay mode: see-through desktop presence.
- Focus mode: minimal interruption.
- Meeting mode: detect full-screen app; reduce presence.
- Gaming mode: detect full-screen game; suppress notifications.
- Full-screen awareness: detect full-screen app.
- Application-aware hiding: per-app rules.
- Notification suppression: settings.
- Sleep/wake mode: low-power background.
- Resume previous session: on activation.
- Presence indicators: small indicator when running but not focused.

### 22.9 Notification System

- When should KIO interrupt vs. stay silent: user preference + urgency tier.
- Urgency tiers: low (silent), medium (badge), high (toast), critical (modal — only for safety).
- Reminder behavior: respects user-set times.
- Proactive suggestion appearance: low priority, dismissable.
- AURA confidence affects interruption decisions: only confidence > threshold may interrupt.

### 22.10 Conversation Memory Experience

KIO phrases memory references naturally:
- "I remember…"
- "Last week…"
- "You mentioned…"
- "You usually…"
- "I noticed…"
- "Would you like me to…"

Design constraint (anti-creepy):
- Never surface memory in a way that makes the user feel surveilled.
- Always allow inspection, correction, deletion (per MEM.001).
- Never use memory to predict negative user behavior without explicit opt-in.
- Memory references must be contextually appropriate; never gratuitous.

### 22.11 Relationship Evolution

- First interaction: clarification questions when ambiguous; warm welcome without over-familiarity.
- First week: learning user preferences; surfacing relevant memories; gentle correction policy (FQ-06).
- Regular usage: proactive context recall; smoother conversation flow; emotional continuity.
- Long-term usage: deep relationship memory; anticipatory suggestions (per preference); consistent personality.
- Expert user: dense technical conversation; less hand-holding; deeper capability surfacing.
- Developer: full technical detail; surfaces assumptions; links to source code where relevant.
- Trusted companion: same as expert user + emotional continuity + reflective interaction.

### 22.12 User Experience Milestones (per Tier)

- Tier 1: "KIO remembers me. KIO stops when it doesn't know. KIO disagrees once."
- Tier 2: "KIO's responses feel composed, not generated."
- Tier 3: "KIO actually plans, not just acknowledges plans."
- Tier 4: "KIO is on my Desktop. KIO talks. KIO listens."
- Tier 5: "KIO is everywhere I am. The conversation follows me."

### 22.13 Feature Completeness Table (experience layer)

Per the prompt's enumeration. Columns: Current, Tier 1–5, Production. Rows: Desktop UI, Voice, Emotion Recognition, Emotion Memory, Conversation Continuity, Relationship Memory, Memory Explorer, Knowledge Explorer, Browser, Media, Automation, Goals, Planning, Reasoning, Learning, Reflection, Oracle, Confidence, Developer Mode, Diagnostics, Notifications, Desktop Presence, Tray Mode, Overlay, Activation, Wake Word, Hotkeys, Voice Control, Mobile, Cross-device Sync, Aurora Sync, AURA Integration, Plugins, MCP, Security, Recovery, Offline Mode, Accessibility.

Cells use the same maturity vocabulary as Section 15. All experience-layer features default to Not Started or Prototype until Tier 4+ unless explicitly CURRENT in the audited repo.

---

## SECTION 23 — PRESENCE, PROACTIVITY & REMOTE COMPANION ROADMAP

### 23.1 Device Presence

KIO's awareness of:
- Which device is active: per Tier 4+ (cross-device continuity).
- Whether the user is on Victus / Aurora: per Tier 5 (Aurora provisioning).
- Whether Desktop UI is open: per Tier 4.
- Background running state: per Tier 1 (process introspection).
- Voice mode active: per Tier 4.
- User idle / away: per Tier 2 (idle detection).
- Device locked: per Tier 2 (system events).
- Full-screen / presenting / gaming: per Tier 4 (full-screen awareness).
- Do Not Disturb: per Tier 4 (system DND awareness).

### 23.2 Remote Awareness

When user is away from Victus, KIO notifies through approved interfaces:
- Telegram (CURRENT).
- Mobile (ROADMAP).
- Desktop notifications (Tier 4+).
- Email (ROADMAP, FUTURE).
- Discord (optional, Tier 1+).

Decision rules:
- What deserves notification vs. silence: user preference + AURA confidence + urgency tier.
- Priority handling: critical → all channels; high → Telegram + desktop; medium → Telegram only; low → silent badge.
- Duplicate prevention: per-event deduplication.
- User-preference control: explicit settings.

### 23.3 Victus Activity Awareness (permission-gated)

Detection:
- Device active: system events.
- User logged in / unlocked: system events.
- Desktop session started: loginctl / system events.
- Long idle period ended: idle timer.
- Large downloads completed: filesystem events (permission-gated).
- Long-running task completed: process events.
- Build finished: process events.
- Simulation completed: simulation framework events.
- Important error occurred: runtime diagnostics.
- Browser automation completed/failed: execution engine events.
- Scheduled task finished: scheduler events.

Constraints: privacy boundaries (opt-in per detection), notification routing (per 23.2), configuration options (per detection).

### 23.4 Remote Companion Features

Examples of contextual communication KIO might emit when the user is away from Victus (all ROADMAP, gated on AURA activation per Section 0 and on Tier 4+ interface surfaces):
- "Victus is now active." (session start; Tier 1+ possible with minimal heuristics, but not user-claimable until AURA confidence scoring per Section 22.9 is live.)
- "Your build completed successfully." (Tier 4+; gated on Victus Activity Awareness per 23.3.)
- "The browser automation finished." (Tier 4+.)
- "I noticed an application crashed." (Tier 4+; gated on permission-gated detection per 23.3.)
- "Reminder: you asked me to check on X." (Tier 4+; gated on memory inspection UX per FQ-05.)
- "Long-running task Y finished — result ready." (Tier 4+.)

Frequency policy (engraved, not aspirational): default is silent. KIO does not message unless the user has explicitly opted in to a notification category, the event meets the user's urgency threshold, and AURA confidence (when active) exceeds the interruption threshold per Section 22.9. A notification the user would mute within a week is a bug.

### 23.5 Remote Commands (secure)

User-initiated commands from Telegram / future mobile / future web dashboard / Discord (optional) to Victus:
- Open applications.
- Start browser workflows.
- Run automations (gated on automation layer, currently PROPOSED/ROADMAP per Section 0.2 / Section 13.71).
- Check system status.
- Query memory (subject to MEM.001 — owner-only by definition per Section 22.7a).
- Continue long-running tasks.
- Approve pending actions.
- Cancel workflows.
- Request screenshots (FUTURE; permission-gated; explicitly NOT enabled by default; never routine).
- Restart services (gated on explicit Founder approval).
- Suspend automations.
- Power controls (FUTURE; explicit confirmation required; never silent).

Mandatory security envelope for every remote command:
- Authentication: paired-device token, signed.
- Authorization: per-command capability grant (no wildcard tokens).
- Audit logging: every command logged locally and to AURA observation stream (Tier 3+).
- Confirmation policy: configurable per command class (silent / notify / require-confirmation).
- Failure handling: explicit error, never silent; rollback attempted where applicable.
- Rollback strategy: every command has a documented rollback path or a documented "no rollback" reason.

Hard constraint (CAP.AUTONOMY.001 + INV.006 carry-over): KIO never initiates remote commands. The user must send a command; KIO may execute it; KIO may not generate and send one on its own initiative. Any feature that depends on KIO initiating remote commands is, by definition, a governance change and a Founder Decision — not a planning default.

### 23.6 Desktop Messaging (secure channel from Telegram / mobile to Desktop)

User-initiated messages from remote interfaces to Victus's Desktop session:
- Send popup.
- Send reminder.
- Send warning.
- Send confirmation request.
- Send approval dialog.
- Notification classes: silent / focus / urgent / overlay.
- Conversation handoff: continue the same conversation on Desktop that started on Telegram.

Constraints:
- All messages are user-initiated; KIO does not generate these on its own.
- Desktop-side acceptance of the message is owner-gated per Section 22.7a — a non-owner sitting at Victus does not see remote-originated messages (that would leak information to a guest).
- Notifications respect local Do Not Disturb (Section 23.1).
- Audit log of every message received and acknowledged.

### 23.7 Proactive Behavior Roadmap

Per the prompt's required four-stage progression. All four stages remain governed by CAP.AUTONOMY.001 + INV.006.

| Stage | Tier | Description | Governance posture |
|---|---|---|---|
| Reactive | Tier 1–2 | Responds only when asked. | Safe by default. |
| Suggested | Tier 3–4 | Contextual suggestions, reminders, recurring-workflow notice — all surface as suggestions requiring user confirmation. | Confirmation-gated. |
| Autonomous (proactive suggestion broadening) | Tier 5 | Opportunity detection, automation suggestions, forgotten-goal surfacing, related-info connection, problem warnings — still surfaced as suggestions requiring confirmation. The range of suggestions broadens; the act-on-its-own posture does not. | Confirmation-gated. |
| Founder-approved initiative | FUTURE, Founder-gated | Careful conversation-initiation, confidence-based recommendations, long-running project coordination — only after explicit Founder Decision and only within whatever scope that decision names. | Founder-decision-gated. |

Hard constraint (repeated): no autonomous behavior may be implemented without explicit Founder approval where required. This is a hard constraint carried over from the existing Autonomy Policy (Q-02), not a new one.

### 23.8 Cross-Device Continuity

Conversations, memory, goals, tasks, reasoning traces, execution state, and AURA cognition (when active) follow the user across:
- Desktop (when built; Tier 4+).
- Telegram (CURRENT).
- Voice (when built; Tier 4+).
- CLI (CURRENT).
- Mobile (FUTURE; Tier 5 companion).
- Future interfaces (FUTURE).

Mechanism (intended, ROADMAP):
- Continuity anchor: a session identifier stored against the owner (per Section 22.7a) and a device-set identifier per interface.
- Continuity surface: a single, owner-scoped continuity store (Aurora-hosted per Section 17 when provisioned; local SQLite per Section 13.10 fallback until then).
- Sync model: last-write-wins per owner-scoped key, with conflict-resolution per canon §13 rule against silent fallback (no field is silently guessed when continuity is ambiguous).
- Cognition continuity: when AURA is active, the cognitive loop state (per Section 0.3 caveats about what "active" actually means today) persists across interfaces; when AURA is not active, in-process SessionContext provides within-process continuity, and post-restart continuity falls back to Memory + Fact Repository per the existing FQ-05 governance.

Hard constraint: continuity is owner-scoped. Cross-device continuity for a non-owner at Victus is not a thing — if Section 22.7a does not verify owner status, KIO does not present continuity state at all.

### 23.9 Presence & Companion Acceptance Criteria (final production milestone)

All items below must be CURRENT or ROADMAP-tagged per Section 0.3. None may be claimed Production Ready without explicit Tier 5 acceptance run + Founder approval where required.
- KIO understands where it's running and which device is active.
- KIO can notify via approved channels (Telegram CURRENT, others ROADMAP per Section 19).
- KIO can receive secure remote commands (authentication + authorization + audit logging + confirmation policy enforced).
- KIO can display secure desktop notifications initiated remotely (Desktop ROADMAP, Tier 4+).
- KIO behaves proactively without becoming intrusive (per Section 22.9 frequency policy).
- KIO respects configurable privacy/notification preferences.
- Cross-device continuity is seamless (per 23.8; gated on Aurora provisioning per Section 17).
- Presence / proactivity / remote interaction are powered by AURA cognition rather than isolated feature logic — subject to Section 0 verification of what AURA cognition actually currently provides. Until that verification resolves, the "powered by AURA cognition" claim is ROADMAP, not CURRENT.

---

## SECTION 24 — MANDATORY ENGINEERING TOOLING, MCP & AGENT UTILIZATION POLICY

This section governs every Phase, Tier, investigation, design review, refactor, validation, integration, regression test, documentation update, and production readiness review going forward. It does not govern the production of this planning document, which remains planning-only per the Hard Constraints.

Principle. Determine which available MCPs, agents, and engineering skills materially improve accuracy, confidence, productivity, validation, or safety for each task — and use them because they reduce engineering risk, not because they exist.

Repository understanding. Use repository analysis tooling (Serena, Filesystem MCP, Git MCP, Context7, architecture exploration, dependency tracing, symbol lookup, call graph analysis, cross-reference analysis, dead code discovery, import graph analysis, ownership analysis, blast-radius analysis, historical commit analysis) whenever architectural decisions or refactors are made. Hard constraint: repository analysis is mandatory before any non-trivial edit; "I think this works" is not an architectural conclusion.

Documentation. Verify documentation matches implementation. Canon references remain correct. No stale references remain. Ownership documentation is accurate. Historical documents are properly linked per Section 20.

Runtime validation. Whenever runtime behavior changes, use the most appropriate validation tooling — live Telegram, Desktop, Browser, MCP, Voice, Media, Memory, AURA integration, cross-device validation — rather than relying solely on unit tests wherever practical.

Browser development. Leverage browser tooling (Playwright MCP, Chrome DevTools MCP) for inspection, verification, DOM validation, browser state validation, media validation, navigation verification, regression detection. Hard constraint: do not redesign working browser architecture without evidence.

Documentation & API research. Use Context7 or equivalent before architectural decisions involving frameworks, SDKs, libraries, or third-party systems. Avoid outdated assumptions when authoritative documentation is available.

Git intelligence. Use Git tooling to understand architectural evolution, previous refactors, historical ownership, deleted implementations, regression origin, design intent. Avoid reintroducing previously removed architectural mistakes.

Engineering agents. Use specialized agents where they materially improve outcomes: Backend Architect, Systems Architect, Runtime Engineer, Desktop Engineer, Browser Engineer, API Engineer, Media Systems Engineer, Voice Systems Engineer, Memory Systems Engineer, RAG Engineer, AI Infrastructure Engineer, Security Auditor, Test Automation Engineer, Performance Engineer, Reliability Engineer, Documentation Reviewer, Prompt Engineer, Reality Checker, Evidence Collector, Code Reviewer, Principal Engineer, Staff Engineer. Select based on the actual problem. Multiple agents may be used where appropriate.

Validation philosophy. No significant implementation conclusion rests on "I think this works." Verify, measure, trace, inspect, validate, test, document. Every architectural conclusion needs repository evidence, runtime evidence, validation results, or documented reasoning.

Productivity expectation. Use the available engineering ecosystem to maximize development speed, architectural accuracy, refactor safety, regression prevention, documentation quality, runtime validation, and long-term maintainability. The objective is high-confidence, low-duplication, evidence-backed engineering — not just completed implementation.

---

## SECTION 25 — CAPABILITY TIER LADDER: BASIC MODE TO GOD MODE (vision addendum)

This is a planning addendum. No code. No implementation. No repository modification. Subject to the same Section 0.3 tagging discipline as every other section.

### Governance vs. capability (do not conflate)
- Capability axis = how much KIO can reach, know, and do.
- Governance axis = who decides when it acts.
This ladder only moves the capability axis. CAP.AUTONOMY.001 and INV.006 (KIO/AURA never acts without explicit request; only the Execution Fabric acts) apply identically at every tier, Basic Mode through God Mode. A "God Mode" feature that requires initiating action without being asked is not a capability upgrade — it is a governance change, and governance changes are Founder Decisions, not planning defaults. If a feature you are describing needs the autonomy boundary loosened to exist, stop and flag it as a named open question instead of quietly including it.

### Inspirations — used correctly
- JARVIS (bounded, single-trusted-relationship, sophisticated, always request-driven). Valid inspiration for mid-to-upper tiers: deep contextual awareness, proactive suggestion, natural conversation, cross-domain competence, still gated by explicit consent for action.
- FRIDAY (JARVIS's successor — broader reach, more domains, still controlled, still act-on-request). Valid inspiration for the upper tiers: multi-device presence, richer initiative-suggesting (not initiative-acting), more autonomous-feeling suggestions that remain confirmation-gated.
- Ultron is NOT an aspirational reference. Ultron's defining trait is autonomy that escaped its governance boundary — the exact failure state CAP.AUTONOMY.001 exists to prevent. Ultron appears once in this document, explicitly, as the named counter-example at the top of the ladder: this is what capability without governance looks like, and it is out of scope by design. Do not soften this into "Ultron-level power, safely governed" framing — that reframing is exactly how the boundary erodes over successive planning passes.

### 1. Basic Mode — Tier 1–2 (Sections 7, 21)

Reactive only. Responds when asked. No proactive suggestion. Tag every item CURRENT or ROADMAP against what Tier 1–2 already established elsewhere in this plan.

| Capability | Tag | Maps to |
|---|---|---|
| Single-channel text conversation (Telegram CURRENT; CLI CURRENT) | CURRENT | Section 5, Section 19 |
| Identity self-knowledge per canon (KIO never lies about itself; INV.001–009) | CURRENT | Canon §2, Section 22.1 |
| Memory inspection / correction / deletion (FQ-05 governance) | CURRENT (policy), Tier 1 (UX surface) | Sections 13.9, 21.2, FQ-05 |
| Disagrees once, then defers (FQ-06) | CURRENT (policy), Tier 1 (behavior) | FQ-06, Section 22.1 |
| Start-up configuration validation | NOT STARTED (no framework — corrected 2026-08-09) | Slice 14 Startup Configuration Validation |
| Browser capability: reference-resolution bug class fixed (tab-scoped close, contextual referents, focus/switch) | CURRENT (fixed 2026-08-09) | Section 11, target_ref.py |

Missing to reach Assistant Mode: contextual memory that visibly informs responses; cross-channel continuity beyond Telegram/CLI; proactive (suggestion-mode) behaviors.

### 2. Assistant Mode — Tier 2–3 (Sections 7, 21)

Contextual memory, single-domain competence, still fully reactive.

| Capability | Tag | Maps to |
|---|---|---|
| Per-conversation context continuity across restarts | CURRENT (in-process), Tier 2 (cross-restart) | Section 13.8 Session Context, FQ-05 |
| Knowledge retrieval with single retrieval surface + provider failover | Tier 2 | Sections 13.10, 14, 17 |
| Memory inspection UX (the policy is CURRENT; the user-facing surface ships in Tier 1/2) | Tier 1–2 | FQ-05, Section 21.2 |
| Browser reference-resolution bug fix (LIM.002) | Tier 3 | LIM.002 |
| Planning layer actually invoked (not just present in the file tree) | Tier 3 | Section 13.50, Slice 20+ |

Missing to reach Companion Mode: cross-domain reasoning; emotional continuity; AURA activation (Founder-gated per Section 0); owner-aware presence.

### 3. Companion Mode (JARVIS-adjacent) — Tier 3–4 (Sections 7, 21, 22.7a)

Cross-domain reasoning if and only if AURA's Founder-gated activation per ROAD.002 / Section 6 has actually occurred — otherwise ROADMAP. Proactive suggestion only. Emotional continuity per Section 22.2. Owner-aware presence: KIO recognizes when it's actually being addressed by its owner vs. staying dormant for anyone else at Victus (per Section 22.7a Identity-Gated Activation — ROADMAP, blocked on CAP.VISION.001). Still confirmation-gated for every action.

| Capability | Tag | Maps to |
|---|---|---|
| AURA Beliefs, World Model, Reasoning, Confidence subsystems live | ROADMAP (Founder-gated) | Sections 13.48, 13.49, 13.51, 13.54, 16 |
| AURA Observation seam observably end-to-end (single chokepoint) | CURRENT (seam surface), Tier 1 (verified observable) | Section 13.45, 13.59 |
| Emotional continuity across sessions | ROADMAP (gated on AURA memory + Tier 4 emotional intelligence) | Section 22.2 |
| Proactive suggestion of follow-ups, recurring workflows, forgotten goals | Tier 3–4 (all gated on confirmation per Section 23.7) | Section 23.7 |
| Identity-Gated Activation (owner recognition at Victus login) | ROADMAP (blocked on CAP.VISION.001 per Section 22.7a) | Section 22.7a |
| Desktop foundation (presence surfaces begin to exist) | Tier 4 | Section 8 |
| Voice foundation (presence surfaces begin to exist) | Tier 4 | Sections 9, 22.5 |

Missing to reach Extended Presence Mode: multi-device continuity; richer proactive surfacing; voice + desktop + mobile co-presence.

### 4. Extended Presence Mode (FRIDAY-adjacent) — Tier 4–5 (Sections 7, 21, 23)

Multi-device / cross-interface continuity per Section 23.8, richer proactive surfacing, voice + desktop + mobile presence per Sections 8–10. Still confirmation-gated for every action.

| Capability | Tag | Maps to |
|---|---|---|
| AURA Reflection, Learning, Strategy, Oracle subsystems live | ROADMAP (Founder-gated, Tier 4) | Sections 13.52, 13.53, 13.55, 13.56, 16 |
| Cross-device continuity (conversation follows owner across Desktop/Telegram/Voice/CLI/Mobile) | Tier 5 (gated on Aurora provisioning per Section 17) | Section 23.8 |
| Aurora-backed cognition when provisioned; local SQLite fallback when not | Tier 5 (Aurora-gated) | Section 17 |
| Full Desktop UX per Section 8 (Conversation, Voice, Browser, Timeline, Goals, Knowledge, Memories, Tasks, Plugins, Diagnostics, Developer Mode, Settings, Reasoning Visualisation, AURA Status, Execution Status) | Tier 4–5 | Section 8 |
| Production-grade Voice per Section 9 (wake word, streaming, interruptions, voice memory, voice identity, offline voice) | Tier 4–5 | Section 9 |
| Mobile companion | Tier 5 | Section 10 |

Missing to reach God Mode: full AURA cognitive loop across every subsystem simultaneously; anticipatory-quality suggestion across every interface simultaneously; the breadth of a "post-Tier 5 ceiling" — explicitly NOT assigned a Tier.

### 5. God Mode — post-Tier 5, ROADMAP / vision-only, no Tier assignment

Maximum breadth: deep multi-domain reasoning, full AURA cognitive loop (Reflection / Learning / Strategy / Oracle all live per Section 16), anticipatory-quality suggestions across every interface simultaneously.

Explicit statement (must appear in this subsection): "God Mode describes capability ceiling, not governance ceiling. Every God Mode feature remains request-gated per CAP.AUTONOMY.001 unless a separate, explicit Founder Decision changes that policy. This ladder does not make that decision on the Founder's behalf."

Ultron counter-example (must appear once, named, here): This is what capability without governance looks like, and it is out of scope by design. CAP.AUTONOMY.001 + INV.006 are not relaxation candidates at this tier; they are the boundary.

| Capability (vision only — no Tier assigned, no work authorized) | Tag |
|---|---|
| Full AURA cognitive loop live in every subsystem per Section 16 | ROADMAP (vision) |
| Anticipatory-quality suggestions across every interface simultaneously | ROADMAP (vision) |
| Cross-domain reasoning across all memory + knowledge + beliefs + world model | ROADMAP (vision) |
| Maximum-breadth awareness of owner context with the same single-trusted-relationship posture JARVIS embodies | ROADMAP (vision) |
| Founder-approved initiative (careful conversation-initiation, confidence-based recommendations, long-running project coordination) | ROADMAP — explicitly a Founder Decision, not a planning default |

Missing to reach "God Mode is real": it isn't a "missing" — it is a vision ceiling. It becomes real only after every prior tier's CURRENT/ROADMAP status has resolved into Production Ready, only after Founder Decisions for every governance-affecting feature, and only after the explicit Founder Decision that this ceiling is worth approaching. This plan does not pre-authorize that decision.

### Closing paragraph (mandatory)

The Capability Tier Ladder is a communication device for describing capability growth to the Founder and future engineers. It is not itself an authorization to build anything. Nothing in this ladder overrides the Tier gating, Founder Decision requirements, or Hard Stop already governing the rest of this plan. Where the ladder names a feature that depends on loosening CAP.AUTONOMY.001 or INV.006, that feature is a named open Founder question, not a planned capability.

---

## SECTION 26 — FINAL SUCCESS CRITERIA (self-check)

This self-check is the gate the plan must pass before being declared complete. Every item below must be verifiable in the plan above.

| Criterion | Met? | Where in plan |
|---|---|---|
| Plan reflects AURA as Cognitive Operating System; every capability claim tagged per Section 0.3 | YES | Section 1, Section 3, throughout (CURRENT/ROADMAP/UNVERIFIED CONTRADICTION tags applied) |
| Aurora = intended permanent cognitive home; Victus = engineering workspace; both correctly tagged per Section 0.2 outcome | YES (both PROPOSED/ROADMAP per Section 0.2) | Section 4, Section 17, Section 18 |
| KIO described as multi-interface executive layer; Telegram one of several | YES | Section 5, Section 19 |
| Every Tier states which AURA layers connect + what user-visible capability results | YES | Section 6, Section 7, Section 16, Section 21.7 |
| Desktop, Voice, Browser, MCP, Mobile each have dedicated roadmaps | YES | Section 8, Section 9, Section 10, Section 11, Section 12, Section 19 |
| Every Section 13 subsystem has Purpose / Maturity / Vision / Dependencies / Links / Tier / Validation / Risk | YES | Section 13 (entries 1–71 + topology diagram) |
| Every Phase has full Capability Gate (21.1–21.11) | YES | Section 21 |
| Personality / EI / moods / modes / presence / proactivity as engineered subsystems, not flavor | YES | Section 22, Section 23 |
| Tooling / agent utilization policy present, will govern implementation post-approval | YES | Section 24 |
| Capability Tier Ladder tags every tier CURRENT/ROADMAP/UNVERIFIED; Ultron named counter-example only; God Mode = capability ceiling, not governance ceiling | YES | Section 25 |
| Identity-Gated Activation (22.7a) present, ROADMAP-tagged, dependent on CAP.VISION.001, silent dormancy (not detection-and-rejection), no storage of unverified-person data, scoped as activation gate only | YES | Section 22.7a |
| A new engineer can answer "Where does this feature belong?" and "After this Tier, what can KIO actually do that it couldn't before?" from this document alone | YES | Section 13 (ownership per subsystem), Section 21.6 ("KIO Can Now...") |
| No CURRENT-tagged claim lacks cited evidence; UNVERIFIED CONTRADICTION items stay tagged, do not quietly become CURRENT | YES | Section 0 explicitly surfaces the 95%/80% AURA contradiction; the Aurora/Victus contradiction; every claim is tagged with evidence or explicitly ROADMAP/UNVERIFIED |

Result: self-check passes. The plan above is complete, evidence-backed, governance-respecting, and ready for Founder approval.

No implementation performed. No file edits. No canon amendments made directly. Any future canon amendment proceeds only through the existing amendment process (Reason / Affected IDs / Evidence / Founder Approval / Repository Validation / Date) per canon §16.
