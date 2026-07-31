# KIO Implementation Blueprint

## KIO's First Principles

1. **KIO exists to help the user achieve goals, not merely answer prompts.**
2. **Memory should change future behaviour, not only retrieve information.**
3. **Every capability should make KIO more understandable, not more magical.**
4. **Intelligence emerges from the interaction of memory, reasoning, planning, and learning — not from prompts alone.**
5. **Deterministic systems and learned systems complement each other.**
6. **The assistant should explain important decisions when appropriate.**
7. **Safety and user agency always override autonomy.**
8. **Reasoning, planning, memory, and learning are separate concerns. An LLM is one possible backend for each — never the definition of any.**

---

## Loaded Skills

| Skill | Why Selected | Section Contribution |
|-------|-------------|---------------------|
| **karpathy-guidelines** | Surgical changes, goal-driven execution, surface tradeoffs | Engineering principles, quality gates, engineering workflow |
| **gitnexus-exploring** | Architecture context from codebase exploration | Dependency graph, implementation streams |
| **ponytail** | Laziest correct solution, no over-engineering | Anti-pattern catalogue, engineering principles, contracts (keep them minimal) |
| *(incremental-implementation, planning-and-task-breakdown, spec-driven-development, test-driven-development, security-and-hardening — read in earlier audit, principles incorporated)* | | |

---

## 1. Engineering Principles

Every implementation must satisfy these principles, in priority order:

| # | Principle | Rule | Violation example |
|---|-----------|------|-------------------|
| 1 | **Surgical change** | Touch only what the requirement mandates. No adjacent cleanup, no refactoring of unrelated code. | Fixing memory retrieval and "while we're here" reformatting execution_boundary.py |
| 2 | **Single canonical owner** | Every capability lives in exactly one subsystem. No duplicate implementations. | Two context managers (mini_kio/context/ + mini_kio/core/) — fix by consolidating |
| 3 | **Deterministic before LLM** | If a deterministic solution exists, use it. LLM only when the problem requires genuine language understanding or generation. | Using LLM to classify intent that a regex could handle |
| 4 | **Intelligence ≠ LLM** | Reasoning, planning, memory, and learning are separate capabilities. An LLM is one possible backend for each, never the definition of any. KIO must remain modular if the model changes or local inference is added. | Architecting "reasoning" as "call LLM" instead of a reasoning engine that can use LLM, local model, or deterministic strategy |
| 5 | **Behaviour before optimisation** | Make it work, make it right, make it fast — in that order. No optimisation during initial implementation. | Adding caching before the query path is verified correct |
| 6 | **Thin vertical slice** | Every implementation delivers working value in one commit. No partial subsystems merged over multiple PRs. | "Add vector index" without a query path — until you can store AND retrieve, it's not done |
| 7 | **Test before merge** | Every non-trivial change includes a test that fails before the change and passes after. | TDD: RED → GREEN → REFACTOR for all new logic |
| 8 | **Architecture before convenience** | If the right architecture is harder, build it anyway. Shortcuts that violate contracts become permanent debt. | Adding a global variable because passing context through the call chain is "too many changes" |
| 9 | **Memory influences behaviour** | Memory is not a decoration. Retrieved memories must observably change system behaviour. | Returning memory in context assembly but never acting on it |
| 10 | **Reasoning before execution** | No action is taken without a reasoning step that justifies it. | Blindly executing the first matched command |
| 11 | **Safety before autonomy** | KIO can veto any action, including its own. Safety state transitions must be conservative. | A proactive suggestion that could execute destructive commands |
| 12 | **Explainability over hidden behaviour** | Every decision must be loggable and traceable to a rule or reasoning step. | Black-box LLM output with no provenance |
| 13 | **No heuristic chain for reasoning** | If you need a chain of 3+ heuristics, replace with a proper inference step. | Pattern-matching chain in local_reasoner.py that mimics but isn't reasoning |
| 14 | **One integration point per external dependency** | Every provider (LLM, search, browser) has exactly one integration point. No scattered ad-hoc calls. | Direct DuckDuckGo call in intelligence_router.py bypassing provider abstraction |

---

## 2. Implementation Strategy

### Strategy: Parallel foundation streams → sequential cognitive layers

Two categories of work:

**Foundation streams** (can be implemented in any order, independently):
- Fix existing architecture issues identified in audits
- Build infrastructure that cognitive layers will depend on

**Cognitive layers** (strictly sequential — each layer depends on the previous):
- Each layer adds one cognitive capability
- Each layer makes KIO observably more intelligent
- Layers are not "features" — they are behavioural upgrades

This strategy minimises:
- **Regression risk** — foundational fixes touch existing code; cognitive layers add new code
- **Architectural drift** — contracts defined before implementation
- **Duplicate work** — single canonical owner per capability
- **Rewrites** — cognitive layers build on foundation, not replace it
- **Unnecessary abstractions** — YAGNI: don't build what no layer needs

---

## 3. Capability Evolution Strategy

The order in which intelligence emerges is determined by dependency: each layer requires the layer before it.

```text
Layer 1: Reliable Execution  ← you are here (almost)
             │
             ▼
Layer 2: Context Awareness   ← semantic memory enables this
             │
             ▼
Layer 3: Behavioural Memory  ← memory influencing behaviour
             │
             ▼
Layer 4: Reasoning           ← local inference + knowledge graph
             │
             ▼
Layer 5: Planning            ← reasoning enables planning
             │
             ▼
Layer 6: Reflection          ← self-critique improves all layers
             │
             ▼
Layer 7: Learning            ← behaviour adaptation from interaction
             │
             ▼
Layer 8: Proactivity         ← AURA implementation
             │
             ▼
Layer 9: Autonomy            ← initiative with safety constraints
```

**Why this order:**

- **Reliable Execution first** — KIO must do what it already does without breaking before adding new capabilities. The safety architecture, tool execution, and multi-path routing must be stable bedrock.

- **Context Awareness before Behavioural Memory** — KIO must know what's happening NOW before it can remember what happened BEFORE. Semantic memory (embeddings + similarity search) is the foundation for all memory-guided behaviour.

- **Behavioural Memory before Reasoning** — Reasoning requires facts to reason over. Without memory that influences behaviour, there's nothing to reason about.

- **Reasoning before Planning** — Planning is applied reasoning over a goal. The system must be able to compare alternatives and justify conclusions before it can decompose goals into tasks.

- **Planning before Reflection** — You can only reflect on plans you've made. Self-critique requires a planning output to evaluate.

- **Reflection before Learning** — Learning requires self-evaluation. Without reflection, there's no signal for what to learn from.

- **Learning before Proactivity** — Proactive suggestions must be grounded in learned user preferences and patterns. Cold-start proactivity recommends randomly.

- **Proactivity before Autonomy** — Autonomous action requires understanding what the user values. Proactivity teaches the system's initiative boundaries safely before full autonomy.

---

## 4. The Cognitive Loop

Once all layers exist, KIO's runtime should operate as a continuous loop — not a request-response pipeline. Every user interaction and every autonomous cycle follows this loop:

```text
Observe
  │ (capture: user input, desktop state, browser tab, time, system events)
  ▼
Understand
  │ (classify intent, resolve references, identify goal relevance)
  ▼
Retrieve Memory
  │ (semantic: similar past situations; episodic: relevant history;
  │  procedural: learned patterns; factual: stored knowledge)
  ▼
Reason
  │ (compare alternatives, detect uncertainty, check for contradictions)
  ▼
Plan
  │ (decompose goal into tasks, build dependency graph,
  │  parallelise where possible)
  ▼
Decide
  │ (select action or response, apply safety governor,
  │  verify against contracts)
  ▼
Execute
  │ (run action, capture outcome, enforce resource bounds)
  ▼
Verify
  │ (did it work? compare outcome to expected result)
  ▼
Reflect
  │ (self-critique: what could be better?
  │  was the reasoning sound? was the response appropriate?)
  ▼
Learn
  │ (update preferences, adjust confidence, reinforce or decay memories)
  ▼
Update Memory
  │ (store episode, update facts, consolidate if needed)
  │
  └──────────────────────────→ Wait (for next trigger or idle cycle)
```

This loop is the heart of the assistant. Every cognitive layer plugs into it. In early stages, the loop is thin (Observe → Understand → Decide → Execute → Verify). As layers are added, the loop fills out. The architectural goal is that by Layer 9, KIO runs this full cycle on every interaction.

**Implementation note:** Build this loop incrementally. Start with the current request-response flow as a degenerate loop (Observe → Decide → Execute). Add Understand when Layer 1 ships. Add Retrieve Memory when Layer 2 ships. The loop structure exists from day one but only the implemented stages are active.

---

## 5. Goal Management

Goals are different from plans. A goal persists. Plans change. The Goal Manager exists to track what KIO is working toward across sessions.

### Goal types

| Type | Example | Lifespan |
|------|---------|----------|
| **Session goal** | "Help Joel debug the reasoning module" | Current session |
| **Project goal** | "Help Joel build KIO" | Weeks to months |
| **User goal** | "Keep my desktop organised" | Indefinite |
| **System goal** | "Maintain safety state < DEGRADED" | Always active |

### Goal Manager Contract

| Property | Specification |
|----------|--------------|
| **Responsibilities** | Register, prioritise, track progress, and archive goals. Detect goal completion or abandonment. Surface active goals to other subsystems (planning, proactivity, reflection). |
| **Inputs** | Goal statement (natural language or structured), priority, lifespan, success criteria |
| **Outputs** | Active goal list ranked by priority + urgency, goal status updates, completion/abandonment events |
| **Ownership** | Single: `goals/` package. GoalManager is the public API. |
| **Success** | Goals progress toward completion. Completed goals are archived with outcome summary. |
| **Failure** | Unreachable goal → flag as blocked with reason. Goal abandoned due to inactivity → archive with note. |

### How it fits the layers

- **Layer 1-3:** Goal Manager exists but has only session goals (implicit from conversation).
- **Layer 4 (Reasoning):** Goal Manager starts detecting goal relevance in user input — "I want to..." creates a goal.
- **Layer 5 (Planning):** Plans become goal-derived. Planner takes a goal from Goal Manager, decomposes it.
- **Layer 6 (Reflection):** Reflection evaluates whether actions moved toward active goals.
- **Layer 7 (Learning):** Learning updates goal priority based on user behaviour.
- **Layer 8 (Proactivity):** AURA checks Goal Manager for stalled goals to follow up on.
- **Layer 9 (Autonomy):** Autonomous execution loop is Goal Manager-driven — select goal → plan → execute → verify → reflect → iterate.

---

## 6. Implementation Streams

### Foundation Stream A: Architecture Consolidation

**Purpose:** Fix known architectural problems before building new capabilities. Eliminate duplicate systems, monolithic routing, and split ownership.

**Prerequisites:** None — can start immediately.

**Dependencies:** None — independent of all other streams.

**Work items:**
1. Consolidate two context managers (mini_kio/context/ + mini_kio/core/) into one with single ownership
2. Decompose `_route_builtin()` (800+ lines) into dispatched handler modules by domain
3. Establish single canonical provider abstraction for all external services
4. Add decision logging to all three routing paths
5. Remove or flag dead code identified in audits

**Expected outcomes:** Clean architecture baseline. Single context manager. Modular routing. Decision traceability.

**Validation criteria:**
- Existing test suite passes
- ContextManager in exactly one location
- No handler exceeds 200 lines
- Every routed decision produces a log entry

**Regression risks:**
- Consolidating context managers may break callers. Requires grep of all imports before moving.
- Decomposing `_route_builtin()` risks breaking routing logic. Must be done with test coverage for each extracted handler.

**Required skills:** ponytail (delete before add), karpathy-guidelines (surgical), code-simplification

---

### Foundation Stream B: Vector Embedding Infrastructure

**Purpose:** Build the vector storage and retrieval infrastructure that all cognitive layers depend on. This is the single biggest enabler for intelligence.

**Prerequisites:** None — independent of architecture consolidation.

**Dependencies:** None — can be built alongside Stream A.

**Work items:**
1. Choose local embedding model (e.g., sentence-transformers/all-MiniLM-L6-v2 — 384-dim, runs on CPU, 80MB)
2. Build embedding service: text → vector conversion with batch support
3. Build vector store abstraction (swap-able backend: SQLite + numpy prototype, then Chroma/Faiss if needed)
4. Build similarity search: query → top-k results with score
5. Build CRUD for vectors with metadata
6. Wire into existing MemoryStore as optional backend (existing key-value remains as fallback)

**Expected outcomes:** KIO can store vectors with metadata and retrieve by semantic similarity. This is a library, not a behaviour — no user-facing change yet.

**Validation criteria:**
- Store 100+ text entries with embeddings
- Semantic query returns correct top-5 by cosine similarity
- Batch insert of 1000 entries completes in < 5s
- Existing tests pass (no regressions — this is additive)

**Regression risks:** Minimal — entirely additive. Only risk is if embedding model import breaks existing dependencies. Pin the version.

**Required skills:** ponytail (smallest embedding model that works), test-driven-development, incremental-implementation

---

### Foundation Stream C: Runtime State Persistence

**Purpose:** Make runtime state survive restarts. Currently, context buffer, session state, and safety state are in-memory only.

**Prerequisites:** None — independent.

**Dependencies:** None — can run parallel to A and B.

**Work items:**
1. Add runtime state snapshot/restore to existing SQLite backend
2. Context buffer persistence (serialize deque to DB on clean shutdown)
3. Session state continuity across restarts (currently partial via SessionState)

**Expected outcomes:** KIO resumes close to where it left off after restart.

**Validation criteria:**
- Runtime state restored after restart
- Context buffer non-empty after restart
- SessionState rehydrates same data after restart

**Regression risks:** Low — touches runtime startup/shutdown, not hot paths.

**Required skills:** incremental-implementation, test-driven-development

---

### Cognitive Layer 1: Context Awareness

**Purpose:** KIO understands what is happening NOW — active window, browser tab, desktop state, time context, recent user activity.

**Prerequisites:** Foundation Stream B (vector storage for context snapshots)

**Dependencies:** Vector embedding infrastructure must exist.

**Work items:**
1. Active window tracker (poll OS for foreground window title/process)
2. Browser active tab tracker (via existing browser connector or extension API)
3. Periodic context snapshot (vectorised capture of current state)
4. Context fusion: merge active state + recent snapshots + conversation history into structured context
5. Replace flat text context assembly with structured multi-modal context

**Expected outcomes:** KIO knows what app the user is in, what browser tab is open, what they were doing 5 minutes ago. Context assembly produces structured output (not flat text).

**Validation criteria:**
- KIO can answer "what app am I in?" with active window detection
- KIO can answer "what tab did I have open?" from context snapshots
- Context assembly passes structured sections (not flat text) to LLM
- No regression in conversation quality

**Regression risks:** Medium — the context assembly change affects every response. Must compare response quality before/after.

**Required skills:** gitnexus-impact-analysis (blast radius on context assembly), code-review-and-quality, ponytail

---

### Cognitive Layer 2: Behavioural Memory

**Purpose:** Memory changes behaviour, not just prompt text. Retrieval influences action selection, response style, and decision making.

**Prerequisites:** Foundation Stream B (vector infrastructure), Cognitive Layer 1 (context awareness)

**Dependencies:** Vector store must have data. Context awareness must be active so KIO knows when memories are relevant.

**Work items:**
1. Upgrade PatternMemoryExtractor: add semantic fact extraction (embed + store patterns, not just regex)
2. Add implicit preference learning: detect preference signals in conversation, embed, store with confidence
3. Build memory-guided response ranker: retrieved memories re-rank candidate responses
4. Build episodic memory summarisation: compress conversation segments into storable episodes
5. Add memory consolidation cron: periodic working → long-term transfer

**Expected outcomes:** KIO's responses observably change based on past interactions. Preference memories influence suggestions. Episodic memories allow "remember when we...".

**Validation criteria:**
- After storing "user prefers dark mode", KIO suggests dark mode
- After 10 conversations about Python, KIO references Python knowledge without re-prompting
- Memory consolidation reduces context size without losing relevant information
- Existing fact extraction continues working (backward compatible)

**Regression risks:** Medium — memory retrieval added to every response could slow response time. Must measure and cap retrieval cost.

**Required skills:** test-driven-development, incremental-implementation, performance-optimization (measure before cap)

---

### Cognitive Layer 3: Reasoning

**Purpose:** KIO can reason through problems, compare alternatives, justify conclusions, identify uncertainty, and detect contradictions. This replaces the pattern-matching "local reasoner" with an actual reasoning engine that can use multiple backends (LLM, local model, deterministic strategies).

**Prerequisites:** Foundation Stream B (vectors), Cognitive Layer 2 (behavioural memory)

**Dependencies:** Vector store for grounding facts. Memory for context. Nothing else.

**Work items:**
1. Build reasoning engine abstraction (supports multiple backends: local model, LLM-as-reasoner, deterministic strategy)
2. Implement self-critique loop: generate → evaluate → refine
3. Implement alternative generation + comparison
4. Implement uncertainty quantification (confidence score per conclusion)
5. Implement contradiction detection across memory + context + new information
6. Replace Local Reasoner pattern-matching with actual inference (or wrap as one strategy in the reasoning engine)

**Expected outcomes:** KIO can say "I'm not sure" with justification. Can present alternatives with pros/cons. Can detect when new information contradicts stored facts. Can reason step-by-step without LLM dependency via local model.

**Validation criteria:**
- Given a multi-step problem, KIO produces structured reasoning (not just answer)
- KIO can identify uncertainty and express it appropriately
- KIO detects contradiction between stored fact and new information
- Local model (if available) provides offline reasoning capability
- Pattern-matching reasoner remains as fallback (never remove existing capability)
- Reasoning engine works if the LLM backend is swapped — proves intelligence ≠ LLM

**Regression risks:** High — this touches the core response pipeline. Every response path feeds through or bypasses reasoning. Must gate carefully: reasoning engine on/off toggle for A/B comparison.

**Required skills:** gitnexus-impact-analysis (critical — reasoning touches every path), security-and-hardening (reasoning about security boundaries), test-driven-development, karpathy-guidelines (surgical, don't refactor existing paths until new path is verified)

---

### Cognitive Layer 4: Planning

**Purpose:** KIO can decompose goals into tasks, execute in parallel, recover from failure, re-plan when context changes, and track progress across sessions.

**Prerequisites:** Cognitive Layer 3 (reasoning — planning requires comparison and justification)

**Dependencies:** Reasoning engine must be operational.

**Work items:**
1. Upgrade Planner: DAG-based task graph (not flat list)
2. Add parallel task execution via thread pool
3. Add re-planning on failure (not just retry)
4. Add checkpoint/resume for interrupted plans
5. Add plan tracking across sessions (persisted plan state)
6. Add dependency reasoning (what tasks block others)
7. Wire Planner to Goal Manager (plans become goal-derived)

**Expected outcomes:** KIO can execute complex multi-step tasks with parallelism, recover from sub-task failure by re-planning, and resume interrupted plans after restart.

**Validation criteria:**
- 3+ task plan executes with at least 2 tasks in parallel
- Task failure triggers re-plan, not just retry
- Interrupted plan resumes from last checkpoint after session restart
- Dependency graph correctly blocks downstream tasks
- Plan is associated with a goal from Goal Manager

**Regression risks:** High — changes to Planner affect every multi-step task. MissionPipeline wraps Planner — must keep backward compatibility.

**Required skills:** gitnexus-impact-analysis, code-review-and-quality, ponytail (DAG can be over-engineered — start with flat + parallel flag)

---

### Cognitive Layer 5: Reflection

**Purpose:** KIO evaluates its own outputs before delivery. Self-critique catches hallucination, contradiction, quality issues, and missed context.

**Prerequisites:** Cognitive Layer 3 (reasoning — reflection requires reasoning over own output)

**Dependencies:** Reasoning engine.

**Work items:**
1. Build output evaluator: score response on accuracy, relevance, safety, completeness
2. Build iterative refinement: low score → regenerate with critique
3. Build hallucination detector: compare response against grounded facts + retrieved memories
4. Add reflection step to ConversationGovernor (currently quality enforcement without self-critique)
5. Wire reflection into the Cognitive Loop as a mandatory post-execution stage

**Expected outcomes:** KIO catches its own mistakes before the user sees them. Responses that contradict stored facts are flagged and corrected. Low-confidence responses include appropriate hedging.

**Validation criteria:**
- Reflection catches intentionally planted contradiction in LLM output
- Reflection improves response quality score by measurable margin (A/B test)
- Hallucination detector flags ungrounded claims
- Reflection adds < 500ms to response time
- Reflection step fires after every execution in the Cognitive Loop

**Regression risks:** Medium — added latency to every response. Must cap refinement iterations (max 2). Must not degrade good responses.

**Required skills:** performance-optimization (latency budget), test-driven-development, code-review-and-quality

---

### Cognitive Layer 6: Learning

**Purpose:** KIO improves with use. Behaviour adapts based on interaction history, correction patterns, and user feedback.

**Prerequisites:** Cognitive Layer 5 (reflection — learning requires self-evaluation signal), Cognitive Layer 2 (behavioural memory — learning updates memory)

**Dependencies:** Reflection provides the learning signal. Behavioural memory stores learned patterns.

**Work items:**
1. Build feedback signal model: explicit (thumbs up/down) + implicit (repeat request, rephrase, abandon)
2. Build preference update loop: detected preference → confidence-weighted update → stored in memory
3. Build behaviour adaptation: learned preferences influence response style, suggestion ordering, tool selection
4. Build forgetting mechanism: decay confidence for unused memories, archive after threshold
5. Wire learning into the Cognitive Loop as a post-reflection stage

**Expected outcomes:** KIO gets better at predicting what the user wants. Repeated corrections reduce over time. Preferences are learned, not just declared.

**Validation criteria:**
- After 3 corrections on response style, style adjusts
- Implicit preference detection identifies repeated pattern without explicit declaration
- Confidence-weighted updates correctly handle conflicting signals (recency vs frequency)
- Forgetting prunes unused memories without losing recently reinforced ones
- Learning updates persist across sessions

**Regression risks:** Low-medium — learning is additive. Only risk is learned preferences degrading response quality for edge cases. Add user-level reset capability.

**Required skills:** security-and-hardening (preference data is personal data), test-driven-development, ponytail (simplest feedback model that works)

---

### Cognitive Layer 7: Proactivity (AURA)

**Purpose:** KIO initiates unprompted — suggestions, warnings, follow-ups, relevant information surfacing. This is the AURA placeholder becoming real.

**Prerequisites:** Cognitive Layer 6 (learning — proactive suggestions must be grounded in learned preferences), Cognitive Layer 2 (behavioural memory), Cognitive Layer 1 (context awareness)

**Dependencies:** Learning provides the preference model. Memory provides the history. Context awareness provides the trigger conditions.

**Work items:**
1. Build proactive trigger model: context + learned preferences + Goal Manager active goals → opportunity detection
2. Build suggestion engine: generate proactive suggestions ranked by relevance + confidence
3. Build follow-up tracker: check Goal Manager for stalled goals, prompt continuation
4. Build warning system: detect risky patterns (repeated crashes, resource pressure, security events)
5. Build initiative arbiter: when to act vs when to ask vs when to stay silent (confidence threshold)
6. Implement idle-time processing: background analysis, consolidation, preparation

**Expected outcomes:** KIO proactively offers help without being asked. Suggests relevant information based on current context. Follows up on stalled goals. Warns about potential issues.

**Validation criteria:**
- KIO suggests relevant action based on current desktop/browser context without prompt
- KIO follows up on stalled goal from Goal Manager
- Warning triggers on detected risk pattern
- Initiative arbiter correctly suppresses low-confidence suggestions
- User can tune proactivity level (off/low/medium/high)

**Regression risks:** Highest of all layers — proactive behaviour can annoy, distract, or trigger actions user doesn't want. Must set conservative confidence thresholds. Must have off switch.

**Required skills:** security-and-hardening (proactive actions are autonomous), ponytail (start with 1 trigger type, expand from evidence), gitnexus-impact-analysis

---

### Cognitive Layer 8: Autonomy

**Purpose:** KIO can independently pursue goals within defined boundaries. Balances initiative with user control. Self-corrects when wrong.

**Prerequisites:** Cognitive Layer 7 (proactivity — autonomy requires initiative), Cognitive Layer 5 (reflection — autonomy requires self-correction), Cognitive Layer 4 (planning — autonomy requires goal decomposition)

**Dependencies:** All prior layers.

**Work items:**
1. Build goal registry: user-defined + Goal Manager-detected goals with priority and status
2. Build autonomous execution loop: select goal → plan → execute → verify → reflect → iterate (the full Cognitive Loop)
3. Build intervention model: when to stop and ask, when to proceed, when to escalate
4. Build safety governor: hard boundaries (no destructive actions autonomously, no spending, no data deletion)
5. Build explainability layer: every autonomous action produces explanation trace

**Expected outcomes:** KIO can be given a high-level goal ("keep my desktop organised") and independently work toward it within constraints. Can explain every autonomous action.

**Validation criteria:**
- KIO accepts a background goal and makes progress without prompting
- KIO stops and asks before any action outside defined safety boundaries
- Every autonomous action produces human-readable explanation
- User can cancel any in-progress autonomous action
- Safety governor prevents destructive actions regardless of goal priority

**Regression risks:** Critical — autonomous behaviour is the highest-risk layer. Every action must be logged, explainable, and cancellable. Safety governor must be absolute (no override from any layer).

**Required skills:** security-and-hardening (paramount), gitnexus-impact-analysis, code-review-and-quality, ponytail (start with read-only autonomy, add write autonomy last)

---

## 7. Dependency Graph

```text
Foundation A         Foundation B           Foundation C
(Arch Consolidation) (Vector Infrastructure)(State Persistence)
         |                  |                      |
         |                  ▼                      |
         |        ┌─────────────────┐              |
         |        │  Goal Manager   │              |
         |        │  (exists early,  │              |
         |        │   fills in as    │              |
         |        │   layers ship)   │              |
         |        └────────┬────────┘              |
         |                 │                       |
         |                 ▼                       |
         |        Cognitive Layer 1                |
         |        (Context Awareness)              |
         |                 |                       |
         |                 ▼                       |
         |        Cognitive Layer 2                |
         |        (Behavioural Memory)             |
         |                 |                       |
         |                 ▼                       |
         |        Cognitive Layer 3                |
         |        (Reasoning)                      |
         |                 |                       |
         |                 ▼                       |
         |        Cognitive Layer 4                |
         |        (Planning + Goal Manager wired)  |
         |                 |                       |
         |                 ▼                       |
         |        Cognitive Layer 5                |
         |        (Reflection)                     |
         |                 |                       |
         |                 ▼                       |
         |        Cognitive Layer 6                |
         |        (Learning)                       |
         |                 |                       |
         |                 ▼                       |
         |        Cognitive Layer 7                |
         |        (Proactivity / AURA)             |
         |                 |                       |
         |                 ▼                       |
         |        Cognitive Layer 8                |
         |        (Autonomy)                       |
         |                                         |
         ▼                                         ▼
    Can run in parallel    Critical path (sequential)
```

**Critical path:** Foundation B → Goal Manager (skeleton) → Layer 1 → Layer 2 → Layer 3 → Layer 4 → Layer 5 → Layer 6 → Layer 7 → Layer 8. Each layer depends on the previous.

**Independent work (parallel):** Foundation A, Foundation B, Foundation C can all be implemented simultaneously.

**Parallel opportunity within layers:** Layer 1 (context awareness) requires Foundation B. But context source development (window tracker, tab tracker) can be built in parallel with vector infrastructure.

**Goal Manager placement:** Build a skeleton Goal Manager early (simple CRUD for goals) so Layer 4 can wire into it. The Goal Manager fills in as each layer ships — it doesn't need full implementation up front.

---

## 8. Contracts

### Memory Contract

| Property | Specification |
|----------|--------------|
| **Responsibilities** | Store, retrieve, consolidate, and expire information across sessions. Support episodic, semantic, and procedural memory types. |
| **Inputs** | Text content, metadata (timestamp, session, source, type), optional embedding vector |
| **Outputs** | Retrieved memories ranked by relevance with confidence scores |
| **Ownership** | Single: `memory/` package. MemoryStore is the public API. |
| **Success** | Store succeeds. Query returns relevant results within latency budget. Consolidation runs without data loss. |
| **Failure** | Store fails → log + continue without persistence. Query fails → empty results + log. Consolidation fails → retry next cycle. |

### Reasoning Contract

| Property | Specification |
|----------|--------------|
| **Responsibilities** | Accept a problem or question. Produce structured reasoning, alternatives, confidence score, and conclusion. Detect uncertainty and contradiction. Backend-agnostic — supports LLM, local model, or deterministic strategies. |
| **Inputs** | Natural language query + context (memories, conversation state, facts) |
| **Outputs** | Structured: `{steps: [], alternatives: [], confidence: 0-1, conclusion: string, contradictions: []}` |
| **Ownership** | Single: `reasoning/` package. ReasoningEngine is the public API. |
| **Success** | Output contains valid structured reasoning. Confidence score correlates with correctness (measured). |
| **Failure** | Cannot reason → return null confidence with explanation. Contradiction detected → flag in output. Timeout → return partial reasoning. Swapping the backend (LLM → local model) produces equivalent-quality reasoning (proves intelligence ≠ LLM). |

### Planning Contract

| Property | Specification |
|----------|--------------|
| **Responsibilities** | Decompose goal into tasks with dependency graph. Execute, monitor, re-plan on failure. Persist plan state for interruption recovery. Plans are derived from Goal Manager goals. |
| **Inputs** | Goal (from Goal Manager), available capabilities (from CapabilityRegister), context |
| **Outputs** | Task graph (DAG), execution status per task, final outcome |
| **Ownership** | Single: `planning/` package. Planner is the public API. |
| **Success** | All tasks complete. Outcome matches goal intent. |
| **Failure** | Unreachable goal → explain why. Task failure → re-plan or skip with explanation. Timeout → return partial completion. |

### Context Contract

| Property | Specification |
|----------|--------------|
| **Responsibilities** | Aggregate, structure, and deliver context from all sources (conversation, desktop, browser, memory, time, session state) to any consumer. |
| **Inputs** | Context source registrations (polled or pushed), query for current context |
| **Outputs** | Structured context sections (not flat text): `{conversation: [], desktop: {}, browser: {}, memory: [], session: {}}` |
| **Ownership** | Single: `context/` package. ContextManager is the public API. Must be exactly one. |
| **Success** | Context assembly returns within latency budget. All registered sources contribute. No stale data (>TTL). |
| **Failure** | Source unavailable → exclude with log. Assembly timeout → return partial context. |

### Execution Contract

| Property | Specification |
|----------|--------------|
| **Responsibilities** | Dispatch actions to registered handlers with safety checks, resource bounds, and result capture. |
| **Inputs** | Action name + parameters, execution context (session, safety state, budget) |
| **Outputs** | Action result (success/failure, data, error, duration) |
| **Ownership** | Single: `execution/` package. ExecutionBoundary is the public API. |
| **Success** | Action completes. Result captured. Log produced. |
| **Failure** | Action fails → return structured error. Safety violation → veto with explanation. Timeout → cancel + return timeout error. |

### AURA (Proactivity) Contract

| Property | Specification |
|----------|--------------|
| **Responsibilities** | Detect opportunities for proactive action. Generate ranked suggestions. Respect initiative arbiter thresholds. Never violate safety boundaries. Check Goal Manager for stalled goals. |
| **Inputs** | Current context snapshot, learned preferences, Goal Manager active goals, recent history |
| **Outputs** | Suggestions ranked by relevance + confidence + urgency: `[{action, reason, confidence, urgency}]` |
| **Ownership** | Single: `aura/` package. ProactivityEngine is the public API. |
| **Success** | Suggestions match user needs (measured by acceptance rate). No inappropriate suggestions. |
| **Failure** | Low confidence → suppress. Safety violation → suppress + log. User proactivity=off → no suggestions. |

### Goal Manager Contract

| Property | Specification |
|----------|--------------|
| **Responsibilities** | Register, prioritise, track progress, and archive goals. Detect goal completion or abandonment. Surface active goals to planning, proactivity, and reflection subsystems. |
| **Inputs** | Goal statement, priority, lifespan, success criteria |
| **Outputs** | Active goal list ranked by priority + urgency, goal status updates, completion/abandonment events |
| **Ownership** | Single: `goals/` package. GoalManager is the public API. |
| **Success** | Goals progress toward completion. Completed goals are archived with outcome summary. |
| **Failure** | Unreachable goal → flag as blocked with reason. Goal abandoned due to inactivity → archive with note. |

---

## 9. Quality Gates

### Per-Stream Gate

```text
[ ] Definition of Done signed off
[ ] Required tests: RED → GREEN for all new logic
[ ] Regression checks: existing test suite passes
[ ] Acceptance criteria: each criterion demonstrated
[ ] Rollback criteria defined: what triggers revert
[ ] Architectural validation: no contract violations, no duplicate ownership
[ ] Impact analysis complete: blast radius documented
[ ] Decision log: every routing change logged
```

### Gate Detail Template

```text
Definition of Done:
  - Code merged to target branch
  - Tests pass (new + existing)
  - Acceptance criteria met
  - Documentation updated (if applicable)

Required tests:
  - Unit tests for new functions/classes
  - Integration test for the capability end-to-end
  - Regression test for existing behaviour

Acceptance criteria:
  - [Criterion 1]: <verifiable condition>
  - [Criterion 2]: <verifiable condition>

Rollback criteria:
  - Test suite regressions
  - Performance degradation > 20%
  - Observed user-facing bugs not present before

Architectural validation:
  - No new duplicates created
  - Contract signed off
  - Single canonical owner
```

---

## 10. Engineering Workflow

Every implementation task follows this workflow:

```text
Phase 1: Understand
  ├── Read relevant documents (this blueprint, relevant audit, contracts)
  ├── Read existing code — trace the full flow
  ├── Run impact analysis (gitnexus-impact-analysis) on every symbol you will touch
  └── State assumptions and uncertainties (karpathy-guidelines)

Phase 2: Design
  ├── Write thin spec for the change (spec-driven-development)
  ├── Break into smallest verifiable tasks (planning-and-task-breakdown)
  └── Surface tradeoffs explicitly (karpathy-guidelines)

Phase 3: Implement
  ├── Start with test: RED (test-driven-development)
  ├── Build laziest correct solution (ponytail)
  ├── One thin vertical slice per commit (incremental-implementation)
  ├── Simplify as you go (code-simplification)
  └── Run impact analysis on each changed symbol

Phase 4: Verify
  ├── GREEN test passes
  ├── Run full test suite
  ├── Code review: five-axis (code-review-and-quality)
  ├── Over-engineering check (ponytail-review)
  └── Security review (security-and-hardening)

Phase 5: Validate
  ├── Acceptance criteria met
  ├── Rollback criteria checked
  ├── Decision log reviewed
  └── Architectural validation

Phase 6: Document
  ├── Update ADR if architectural change
  └── No inline documentation — code is documentation

Phase 7: Merge
  ├── Squash to atomic commit
  ├── Meaningful commit message
  └── Run detect_changes() (gitnexus)
```

---

## 11. Required Skills Per Implementation Stream

| Stream | Required Skills |
|--------|----------------|
| Foundation A: Architecture Consolidation | ponytail, ponytail-review, karpathy-guidelines, code-simplification, gitnexus-impact-analysis |
| Foundation B: Vector Infrastructure | ponytail, test-driven-development, incremental-implementation |
| Foundation C: State Persistence | test-driven-development, incremental-implementation |
| Goal Manager (skeleton) | test-driven-development, ponytail |
| Layer 1: Context Awareness | gitnexus-impact-analysis, code-review-and-quality, ponytail |
| Layer 2: Behavioural Memory | test-driven-development, incremental-implementation, performance-optimization |
| Layer 3: Reasoning | gitnexus-impact-analysis, security-and-hardening, test-driven-development, karpathy-guidelines |
| Layer 4: Planning | gitnexus-impact-analysis, code-review-and-quality, ponytail |
| Layer 5: Reflection | performance-optimization, test-driven-development, code-review-and-quality |
| Layer 6: Learning | security-and-hardening, test-driven-development, ponytail |
| Layer 7: Proactivity (AURA) | security-and-hardening, ponytail, gitnexus-impact-analysis |
| Layer 8: Autonomy | security-and-hardening, gitnexus-impact-analysis, code-review-and-quality, ponytail |

---

## 12. Anti-Pattern Catalogue

| # | Anti-Pattern | Why It's Harmful | Instead |
|---|-------------|------------------|---------|
| 1 | **Duplicate subsystem** | Two implementations of the same concept diverge. Fixes apply to one, bugs hide in the other. | Single canonical owner. If you need a second, consolidate first. |
| 2 | **Temporary hack** | Nothing is more permanent than a temporary fix. | Build the right thing at smaller scope, not a wrong thing fast. |
| 3 | **Growing the monolith** | Adding 50-line if/else blocks to `_route_builtin()` because it's faster than extracting a module. | Extract to module before adding. One function, one responsibility. |
| 4 | **Global mutable state** | Hidden coupling between unrelated subsystems. Testing becomes impossible. | Pass context explicitly. Runtime singleton is the ONLY global state. |
| 5 | **Hidden dependency** | Import that isn't declared in requirements. Works on dev machine, breaks on deploy. | Every dependency declared. CI verifies clean install. |
| 6 | **Contract violation** | Calling a subsystem's internals instead of its public API. Bypasses safety, breaks encapsulation. | If the public API doesn't support what you need, extend the API — don't bypass it. |
| 7 | **Mixed responsibilities** | A function that routes AND executes AND logs AND checks safety. | One function, one responsibility. Compose from single-purpose functions. |
| 8 | **Heuristic chain** | 3+ pattern-matching rules that together approximate reasoning. | Replace with single inference step. Heuristics are brittle and unmaintainable. |
| 9 | **Prompt over architecture** | Using an LLM prompt where a deterministic function would work. | Deterministic before LLM. Prompt only for genuine language tasks. |
| 10 | **LLM for everything** | Routing every decision through an LLM because "it's smarter." | LLM is expensive, slow, non-deterministic, and can hallucinate. Use it only where language understanding is required. Treat LLM as one backend, not the definition of intelligence. |
| 11 | **Speculative abstraction** | Interface with one implementation. Factory that creates one product. Config for a value that never changes. | YAGNI. Build the concrete thing. Abstract when you have evidence of a second variant. |
| 12 | **Silent degradation** | Adding fallback paths that mask failures instead of logging them. | Every fallback logs why it triggered. Degradation is visible, not silent. |
| 13 | **Unsafe autonomous default** | KIO taking action without explicit user confirmation because it's "confident." | Safety before autonomy. High-confidence suggestion is STILL a suggestion, not an action. |
| 14 | **Ignoring the lazy path** | Building a complex solution when a simpler one works. | ponytail ladder: YAGNI → codebase has it → stdlib → platform → installed dep → one line → minimum code. |
| 15 | **Cold-start proactivity** | Suggesting before learning user preferences. | Learn first, suggest second. Layer 6 (Learning) before Layer 7 (Proactivity). |
| 16 | **Goal-less autonomy** | Autonomous action without a goal context. Wanders. | Every autonomous action traces to a Goal Manager goal. If no goal applies, don't act. |

---

## 13. Final Implementation Readiness Assessment

| Condition | Status | Evidence |
|-----------|--------|----------|
| Architecture baseline documented | ✅ | Architecture Audit, Runtime Audit |
| Cognitive target defined | ✅ | Cognitive Architecture Review |
| Runtime cognitive loop defined | ✅ | Section 4 of this document |
| Goal Management defined | ✅ | Section 5 of this document |
| First principles established | ✅ | Front matter of this document |
| Implementation principles established | ✅ | Section 1 of this document |
| Implementation order defined | ✅ | Sections 3-6 of this document |
| Contracts defined | ✅ | Section 8 of this document |
| Quality gates defined | ✅ | Section 9 of this document |
| Engineering workflow defined | ✅ | Section 10 of this document |
| Anti-patterns catalogued | ✅ | Section 12 of this document |
| Skills mapped to streams | ✅ | Section 11 of this document |
| Critical path identified | ✅ | Foundation B → all cognitive layers sequentially |
| Independent work identified | ✅ | Foundation A, B, C can run in parallel |
| Biggest risk identified | ✅ | Reasoning layer (Layer 3) — highest regression risk, touches every response path |

**Ready to implement.** The strategy is complete. Begin with Foundation Streams A, B, and C in parallel. Then proceed sequentially through cognitive layers 1-8. No timeline estimates — implement in order, verify each layer before advancing to the next.
