# KIO Final Intelligence Architecture

Status: Final. Supersedes v1 and v2 in full. This document is the terminal answer for this design line — no v4 is anticipated unless a genuine invariant is later found to be false.

---

## 1. The Actual KIO Vision

KIO is a persistent intelligent operating companion. Not a chatbot, not a router, not a RAG wrapper, not a workflow engine. The distinguishing property: KIO must be able to **understand situations it was never told about**, using the same machinery it uses for situations it was. A system that handles N anticipated cases well is not that; a system whose primitives are derived from what *any* interaction must contain, regardless of content, is. Everything below is derived from that constraint, not from KIO's current feature list.

---

## 2. Fundamental Architectural Invariants

Independent of domain, modality, capability, or user: KIO must be able to (a) **address** anything — name it, refer to it again later; (b) **relate** any two addressable things, with the relation itself potentially uncertain or contested; (c) **attribute** any piece of content to who holds/believes/wants/asserted it; (d) **qualify** anything with time, confidence, and status; (e) **revise** anything without destroying its history; (f) **compute what's currently relevant** without that computation being a stored, hand-maintained pointer. These six requirements, and nothing else, are what the ontology in §4 is built to satisfy — they are the actual invariants; §4 is one candidate structure that satisfies them, defended below by showing no requirement in this document needs a structure beyond it.

---

## 3. What "Conversation" Actually Is

Conversation is not a message pipeline (classify → route → answer). It is a sequence of **updates and queries against a standing, persistent semantic graph**, where a single utterance can produce many simultaneous updates (inform, ask, correct, commit, reject, reference, shift tone) and a single response can draw on content from anywhere in that graph, not just the immediately preceding turn. "Turn" is a bookkeeping convenience for grouping updates by wall-clock proximity — it is not a semantic unit, and nothing in the architecture is keyed to it.

---

## 4. Final Semantic Model

**Two structural primitives, one universal metadata contract, one computed mechanism.**

### 4.1 `Node`
Anything addressable: a person, object, concept, resource, capability, participant (including KIO and the user themselves), a situation/topic, an event, or a self-contained proposition that doesn't reduce cleanly to a relation between two other things ("it's raining," free-form statements). A `kind` tag is descriptive only, never a branch point in logic.

### 4.2 `Link`
A typed, directed (or n-ary) connection between two or more `Node`s (or between a `Link` and anything, including another `Link` — reification is permitted, not mandatory). Open vocabulary: `refers_to`, `contradicts`, `supports`, `causes`, `part_of`, `wants`, `believes`, `precedes`, `compares_to`, `corrects`, `about`, `delegates_to` — new names never require new mechanism. **Most propositions ARE relations** ("X likes Y," "user wants Z," "A caused B") and are represented directly as a `Link` carrying the metadata in §4.3, not as a separate "Statement" object. Propositions that genuinely have no clean second argument use a `Node` instead, carrying the identical metadata contract — this is why Node and Link share one contract rather than each defining their own.

### 4.3 Universal Metadata Contract (carried by every `Node` and `Link`)
```
stance       — belief | desire | intention | question | commitment |
               observation | hypothesis | permission | prediction | possibility
attributed_to — one or more participants (user | KIO | external_source | a Node
                representing a third party) who hold/assert/originated this
confidence   — revisable, never silently overwritten
time         — event_time, observed_at/created_at, validity_window
status       — live | superseded | corrected | rejected | expired | unresolved
provenance   — how this came to exist (stated, inferred, retrieved, reasoned, observed — 
               and via which capability if applicable)
supersedes / superseded_by / corrects / corrected_by — links to prior versions, never deleted
```
This is the direct answer to "belief vs desire vs intention vs commitment vs recommendation vs prediction": they are not different object types, they are different `stance` values on the same contract — the BDI (belief-desire-intention) unification, generalized with a few additional stances actual conversation needs (`observation`, `question`, `commitment`, `hypothesis`, `permission`). A goal is `stance=desire` or `intention`; a recommendation is `stance=belief` (KIO's opinion) plus an attached `intention` (what it's recommending); a fact is `stance=belief` or `observation`; a plan step is `intention` with a `part_of` link to its parent plan. Nothing here required a `Statement`/`Assertion`/`Intent` split — v2 kept them separate; that split is now dissolved.

### 4.4 Activation (a computed mechanism, not a stored type)
"What's currently relevant" is a **query**, not a maintained pointer or state machine: a decaying function of (recency of reference, graph-distance from recently active Nodes/Links, explicit reactivation by the current utterance, confidence). v2's `ContextFrame` — a stored object with an explicit `ACTIVE/SUSPENDED/DORMANT` state machine — is **removed** as a primitive. A "topic" or "situation" is just an ordinary `Node` (kind=`situation`) connected via `about`/`part_of` `Link`s to whatever it concerns; its salience at any moment is computed, not transitioned. This removes an entire class of transition-management bugs (the exact kind that caused v1's stale-thread bleed) by making "what's active" always a fresh computation instead of a value that can go stale.

**Why this is smaller than v2 and still sufficient:** every v2 primitive maps onto this without loss — `Referent`→`Node`; `Assertion`→`Link`/`Node` with `stance∈{belief,observation,hypothesis}`; `Intent`→`Link`/`Node` with `stance∈{desire,intention,commitment}`; `Relation`→`Link` (unchanged); `ContextFrame`→`Node(kind=situation)` + computed activation. Nothing in this document (including the 30-scenario test in §29) required going back to a 5th or 6th stored type.

---

## 5. Final State Model

There is **one graph**. "User state," "KIO state," "world state," "capability state," "knowledge/evidence state," "temporal state," and "execution state" are not separate storage systems — they are **queries over the same graph**, filtered by `attributed_to`, `stance`, `provenance`, or `Node.kind`. E.g. "world state" = observation-stance Links/Nodes attributed to real capability execution; "user state" = anything attributed to the user participant-Node, further sliced by `time.validity_window` for session/episodic/durable behavior. This is the explicit answer to "don't call everything context, context becomes a garbage drawer": the graph is not undifferentiated — every object is precisely attributable and queryable along defined dimensions — but the differentiation is a *query facet*, not a *separate subsystem with its own lifecycle*. (Storage layer may still physically partition by access pattern for performance — that is an implementation/index decision, explicitly not a semantic one; see §33's separation of ontology from runtime structures.)

---

## 6. User / KIO / World Relationship

The user, KIO, and any third party (a person discussed, an external system) are each an ordinary `Node` (kind=`participant`). Everything "known about" them is `Link`s/`Node`s where `attributed_to` includes them. This is symmetric by construction: KIO's own opinions, commitments, and corrections use the exact same representation as the user's, which is what makes "you said Y was better" (§4.3's `attributed_to`-aware retrieval) and "I was wrong" (§23) fall out of the same mechanism rather than needing separate KIO-memory and user-memory subsystems. World state (external, unattributed-to-any-participant reality) is represented the same way, with `stance=observation` and `attributed_to` pointing at the capability/sensor that produced it, not a person.

---

## 7. Reference and Meaning Resolution

One resolver, targeting any `Node` or `Link`. Score = grammatical/structural compatibility (constrains kind, not identity) × activation (§4.4, replacing fixed recency windows) × semantic compatibility between the utterance's predicate and the candidate × discourse-structural anchors (ordered lists KIO itself produced) × attribution-awareness (filters by `attributed_to` before scoring when the utterance specifies whose statement is meant — "what you said" vs "what I said"). **"Back to what we were discussing" does not default to most-recent-topic** — it queries for the highest-activation `situation` Node matching the utterance's residual content, which may legitimately be several turns back if nothing since has reactivated it. Ambiguity (near-tied top candidates) is preserved as `status: unresolved` on the candidate Links rather than force-resolved — the Planner (§13) decides whether to ask, hedge, or defer based on the cost of guessing wrong (§25).

---

## 8. Memory and Persistence

Memory is not a separate system from the graph — it *is* the graph, persisted. What's "remembered but not currently relevant": a `durable`-scope Node/Link with near-zero current activation (§4.4) — retrievable by explicit query, uncompetitive for default resolution. Nothing is hard-deleted; "forget X" transitions `status→expired` (excluded from default resolution/recall) with true deletion reserved for explicit user-directed removal, consistent with the founder-ratified AURA memory-correctability requirement already on file. Promotion from low-confidence/inferred to durable/trusted requires either an explicit statement or multiple *independent* corroborating Links (not repetition of the same signal) — this policy needs a concrete default before implementation (flagged in §35).

---

## 9. Time and Temporal Validity

`time.event_time`, `observed_at`/`created_at`, and `validity_window` on every Node/Link (§4.3) are the entire temporal model — no separate "temporal subsystem." Relative language ("recently," "eventually," "historically," "since," "until") resolves to window queries against these fields, relative to the current computed activation window (§4.4), never string matching. Supersession (a newer, comparable-or-better-sourced Link/Node with a later `event_time` marking an older one `superseded`) is how "a recommendation becomes obsolete," "a statement was true historically but false now," and "an external event invalidates a prior decision" are all the same mechanism, not three.

---

## 10. Knowledge, Belief, Evidence, and Uncertainty

Entirely covered by `stance` + `confidence` + `provenance` + `status` (§4.3) on the same Node/Link objects — fact, evidence, belief, inference, hypothesis, user claim, KIO claim, recommendation, prediction, possibility, and rumor are `stance`/`provenance` value combinations, not ten node types. Contradiction is a `Link(contradicts)` between two live objects, surfaced to the Planner, not silently auto-resolved — genuinely unresolved disagreement stays representable indefinitely.

---

## 11. Research and Information Acquisition

A Planner decision (§13), triggered when: internal graph content for a needed claim is stale/absent, two live Links `contradict`, the user explicitly requests verification, or a pending `intention` can't be evaluated without fresher information. Raw retrieval output is never written to the graph directly — only the synthesized result, as `stance=observation, provenance=retrieved` Links attached via `about`/`supports`/`contradicts` to the *specific* claim being investigated, so a follow-up ("which one?") resolves to that specific object and only its attached evidence answers it. This is the mechanism that prevents research from becoming "permanent conversational contamination."

---

## 12. Intent, Goals, and Evolving Objectives

A goal is a `Node`/`Link` with `stance∈{desire,intention}`. **Nested goals** = child Nodes linked `part_of` to a parent goal Node — arbitrary depth, no hierarchy limit. **One goal creating another** = a new intention Link with `provenance` pointing at the triggering goal. **One goal invalidating another** = a `contradicts` or explicit `supersedes` Link between two intention-stance objects, surfaced to the Planner exactly like a factual contradiction (§10) — goals and beliefs share the contradiction mechanism because they share the same underlying representation. **Changing a goal mid-sentence** is just two intention-stance Links produced by decomposition of one utterance (§13), the second `supersedes` the first. **Abandoned/resumed plans**: `status→abandoned` (not deleted) and `status→active` again on later resumption — the plan's own Link/Node structure never needed rebuilding.

---

## 13. Planning and Reasoning

One planning pass per interaction, over the **decomposed set of updates** an utterance produces (never a single classified intent — a message can simultaneously inform, ask, correct, commit, and reject in one turn; each becomes its own Node/Link write or query against the graph). For each decomposed update: resolve references (§7); merge/supersede/flag-contradiction (§10/§12); if action-shaped, hand to Capability Resolution (§14). The Planner's holistic decision this turn — answer / ask / research / recommend / execute / acknowledge tone / stay silent — is a function of the full decomposed set plus the current activation state (§4.4), never a fixed per-message template. Any suggestion or opportunity *KIO itself* proposes is written as an ordinary `intention`-stance Link attributed to KIO with `status=proposed`, and is accepted/rejected through the identical reference-resolution-driven flow as any user-initiated intention (§7) — proactivity is not a separate engine, it is Planning noticing a high-value intention and writing it.

---

## 14. Capability Discovery and Execution

A capability is a `Node` (kind=`capability`) declaring `inputs`, `permissions_required`, `side_effects`, `outputs`, `failure_modes`, `reversibility` as attributes — not behavior baked into the conversation layer. One registry resolves an `intention`-stance object to a matching capability by declared shape, never by hardcoded name (this is where the repo's C-09 fragmentation — three uncoordinated capability-discovery systems — gets collapsed; see §31/§32, unchanged in substance from v1/v2). Execution: intention → governance (§25) → real invocation → an `observation`-stance Link/Node recording the actual outcome → the intention's `status` updates to `completed`/`failed`/`partial`. **KIO is structurally blocked from narrating any outcome without a corresponding observation object** — this is what prevents hallucinated execution, and it composes naturally with partial success (`status=partial`, with the observation content describing exactly what did and didn't happen) and cancellation (`status=cancelled`, distinguishable from `failed` by provenance).

---

## 15. External World Interaction

Same mechanism as §14's observation objects, generalized: anything KIO perceives via a capability (browser state, a file's contents, an API response, a sensor reading, a scheduled event firing) becomes `stance=observation` content attributed to that capability, with normal `time`/`confidence`/`provenance`. An asynchronous external event that changes a dormant goal's validity is simply a later-timed observation Link that `contradicts` or `supersedes` something the dormant intention depended on — the Planner surfaces this the next time that intention's chain is queried or reactivated (§4.4), it does not require a standing "watcher" subsystem beyond whatever capability is producing the observation in the first place.

---

## 16. Resources and Information Objects

A resource (webpage, document, image, video, audio, dataset, code, product, device, location, live stream, API result, or anything not yet imagined) is a `Node` (kind=`resource`) with attributes (`resource_type`, `locator`, `published_at`). No separate media ontology exists — relevance/freshness/worth-surfacing is computed by the identical intention-scoring machinery as §18's proactivity, because "should I mention this resource" and "should I suggest this action" are the same kind of decision (an unproposed high-value `intention`) over a different `Node.kind`.

---

## 17. Recommendation and Decision Support

A recommendation is a `belief`-stance object (KIO's opinion) plus an attached `intention` object (what's being recommended), scored against the candidate set using the user's live preference/rejection history (§6, `attributed_to=user` Links with `stance=desire`/`rejects`). "Why X" retrieves the belief object's content + provenance rather than regenerating a rationale. Comparing two prior plans and adopting a third that combines both: the third plan is a new `intention` Node with `part_of`/`derived_from` Links to both source plans — comparisons and syntheses are ordinary graph structure, not a special "decision support" object.

---

## 18. Proactivity

Fully covered by §13's last sentence and §16: a proactive suggestion is an ordinary KIO-authored `intention` object with `status=proposed`, surfaced only when its scored value clears an interruption-cost-adjusted threshold, and resolved through the same accept/reject reference-resolution flow as anything else. "Knowing when to stay silent" is simply that threshold not clearing — there is no separate "offer engine" to reason about.

---

## 19. Response Generation

Depth, structure, and content are computed from: the decomposed update set this turn (§13), the current activation window (§4.4, which establishes how much shared context can be assumed), and any unresolved ambiguity/ open commitments needing acknowledgment. No universal template ("Bottom line:", "Would you like me to...?") is emitted by default — a closing offer only appears when an actual `intention` object cleared the proactivity threshold (§18) and is being surfaced this turn.

---

## 20. Personality / Tone / Interaction Adaptation

Tone/register/energy signals ("yo," "bruh," sarcasm markers, formality level, urgency) are captured as lightweight attributes on the current interaction's decomposed updates — not stored as durable graph objects (they decay with the turn) and not a separate "Gen-Z subsystem" or phrase dictionary. They feed the Planner's response-generation decision (§19) as one more input alongside activation and content, the same way `confidence` feeds resolution — a numeric/categorical signal consumed generically, not pattern-matched.

---

## 21. Multimodal Interaction

A `Node` is medium-agnostic by construction — its `content` can be text, a reference to an image/audio/video artifact, or a structured payload from browser/API state; the metadata contract (§4.3) and the resolution/activation mechanisms (§7/§4.4) do not change based on modality. Mixing text, image, voice, and browser state within one interaction is simply several decomposed updates in the same turn, some with non-text content — no separate multimodal architecture is required, because nothing in §4 assumed text.

---

## 22. MCP / Agents / Skills / Tools

All are `Node(kind=capability)` instances (§14) with declared metadata. The semantic graph never references a specific tool/provider/protocol by name; adding one is a registration, not an architecture change. An agent (an autonomous multi-step actor) is represented the same way, potentially producing several `observation` objects over time rather than one — this is naturally supported since `intention→execution→observation` doesn't assume synchronous single-shot completion.

---

## 23. Self-Correction and Learning

"I was wrong" = KIO produces a new `belief`-stance object that `contradicts` or explicitly `corrects` its own prior one; the prior transitions `status→corrected` (never deleted, per §8); the new one carries `provenance` explaining what changed. "KIO discovers that an assumption underlying five earlier statements was wrong": the assumption is itself an addressable `Node`/`Link`; correcting it doesn't retroactively rewrite the five dependent statements — instead the correction is surfaced, and each dependent statement's validity becomes queryable-but-flagged (a `contradicts`/`depends_on` Link chain), letting the Planner decide, next time any of the five is referenced, whether to proactively flag the inconsistency or address it on demand. No separate "correction subsystem" — it is ordinary graph revision using the same primitives as any other update.

---

## 24. Failure and Recovery

Misunderstanding, ambiguous reference, wrong resolution, failed capability, contradictory sources, a hallucinated assumption caught late, an interrupted task — all are ordinary states within the primitives already defined: `status=unresolved` (§7), `status=failed`/`partial` (§14), `contradicts` Links (§10/§23). Nothing "poisons" conversation state, because nothing is a special exception path outside the normal graph-update flow; recovery is just another update.

---

## 25. Guardrails and Governance

Reasoning, discussing, comparing, and planning over any Node/Link is unrestricted. Only **executing** an intention through a real capability passes governance, gated on the capability's declared metadata (§14: reversibility, side-effect scope, data sensitivity, cost) plus the intention's own provenance — critically, content ingested from an untrusted source (a tool result, browser page, document) is `observation`-stance data only and can never itself become an `intention` with executable authority merely by being phrased like an instruction. New capabilities inherit governance automatically because governance reads declared metadata, not capability identity — this is what keeps the guardrail model valid for capabilities that don't exist yet. Ambiguity-cost thresholds (ask vs. guess, §7) are governance-adjacent and need a concrete default per capability class before informational vs. side-effecting decisions ship (flagged in §35).

---

## 26. Concurrency / Parallel Goals / Asynchronous Events

Multiple `intention` objects can be simultaneously `active` with no interference, because activation (§4.4) is computed per-object, not a single global pointer — this is the direct mechanism for parallel subjects, nested subjects, and multiple coexisting goals the earlier prompts required a stack-based Thread model to approximate. Delegation (KIO hands a sub-goal to another capability/agent) is an `intention` with `delegates_to` pointing at that capability-Node; its later completion is an ordinary `observation` update, processed whenever it arrives, regardless of how much other conversation happened in between — asynchronous events are not a special case, they're just updates whose timestamp lags their trigger.

---

## 27. Persistence and Cross-Session Continuity

One graph instance per user (session-scoped access, but `durable`-scope content persists across sessions by construction — `scope` was already collapsed into the `time.validity_window` + `status` fields rather than being a separate concept). "Continue where we left off" is an activation-window query (§4.4) seeded from the last session's high-activation `situation` Nodes rather than a special resume mechanism. How long a durable object should present as "resuming" vs. "starting fresh and referencing history" is a UX policy needing a default (flagged in §35) — the mechanism supports either without change.

---

## 28. Unknown-Unknown Generalization

The test stated in the brief: if a genuinely new interaction category requires a new stored type, the architecture failed. Given the model in §4, the only things that can be added for a new domain/capability/behavior are: new `Node.kind` values, new `Link` relation names, and new `stance`/`provenance` values if a genuinely new epistemic mode is discovered (none were needed for any scenario tested in §29). None of these are architecture changes — they are data. §29 is the adversarial test of this claim.

---

## 29. Adversarial Interaction Analysis (30 required scenarios)

| # | Category (from the brief) | Scenario | Resolution via existing primitives |
|---|---|---|---|
| 1 | Changing intent | User asks KIO to book a slot, then mid-sentence changes what they want booked | Two `intention` Links from one decomposed utterance (§13); second `supersedes` first |
| 2 | Contradictory intent | User simultaneously asks to "keep this simple" and "add every detail" | Both `intention` objects created; `contradicts` Link surfaced (§10/§12) to the Planner rather than picking one silently |
| 3 | Nested goals | "Plan my trip" → sub-goals for flights, hotel, itinerary | Child `intention` Nodes `part_of` the parent, arbitrary depth (§12) |
| 4 | Delayed consequences | An action taken today only shows its effect (an observation) a week later | Observation Link arrives with its own `time.event_time`; Planner reconciles against the original `intention` whenever either is next queried (§15) |
| 5 | Asynchronous events | A background monitoring capability fires mid-unrelated-conversation | New `observation` Node written independently of current activation window; surfaces next time its `about` target is queried or if it clears the proactivity threshold (§18) |
| 6 | Multiple participants | User quotes a friend's opinion into the conversation | Third `participant` Node created on the fly; the quoted opinion is a `belief`-stance object `attributed_to` that Node, not the user (§6) |
| 7 | Uncertain identity | "That guy from the meeting" with no name given | Unresolved reference (§7) — candidate scored, `status=unresolved` if margin is thin, Planner may ask |
| 8 | Self-reference | User asks KIO what it just said it would do | Direct `attributed_to=KIO` retrieval over recent `intention`/`commitment` objects (§6) |
| 9 | Hypothetical worlds | "Suppose I took the other job — what would my schedule look like?" | `stance=hypothesis` subgraph, linked `about` the real schedule but never merged into `belief`-stance state unless the user later asserts it as real |
| 10 | Counterfactuals | "If I had taken that job, would I be doing this?" | Same hypothesis subgraph, queried against the real timeline's `time` fields (§9) |
| 11 | Conditional plans | "If it rains, do X, otherwise Y" | Two `intention` objects with a `conditional_on` Link to an unresolved observation; whichever's condition resolves true transitions `active`, the other `abandoned` |
| 12 | Abandoned plans | User drops a project for months | `status=abandoned`, never deleted (§12) |
| 13 | Resumed plans | Same project picked back up later | `status→active` again; full structure intact, no rebuild |
| 14 | Competing goals | Save money vs. buy something now | Both `intention` objects live with a `contradicts` Link; Planner may surface the tension rather than silently pick one |
| 15 | Implicit goals | User describes a recurring annoyance without asking for a fix | Planner may infer a candidate `intention(stance=desire, provenance=inferred, confidence=low)` — surfaced only if it clears the proactivity threshold (§18), never silently acted on given low confidence + inferred provenance gating governance (§25) |
| 16 | Social context | User is clearly venting, not asking for solutions | Tone signal (§20) shifts Planner's response-generation mode away from action-proposing, without a "venting mode" module |
| 17 | Emotional context | Frustration expressed after a repeated failure | Tone signal + the actual `status=failed` observation history (§14) both inform response depth/tone |
| 18 | Long-range callbacks | "What did we decide about this three weeks ago?" | Direct temporal-window query (§9) over `intention`/`belief` history regardless of intervening activation |
| 19 | External state changes | A price the user was tracking changes | New `observation` supersedes the old one (§9); if a live `intention` depended on the old price, the dependency surfaces on next reference |
| 20 | Capability discovery | A new tool becomes available mid-project | New `Node(kind=capability)` registered (§14/§22); no conversation-architecture change |
| 21 | Capability failure | The tool KIO planned to use is suddenly unavailable | Capability resolution returns unavailable; Planner falls back or reports the limitation, `intention.status` reflects it honestly (§14/§24) |
| 22 | Partial success | A multi-step action completes 3 of 5 steps before failing | `observation` content records exactly which sub-intentions completed; parent `intention.status=partial` (§14) |
| 23 | User corrections | "No, I meant the other Alex" | New reference resolution re-run with corrected constraint; old binding `status=corrected` via a `corrects` Link (§23/§24), not deleted |
| 24 | KIO corrections | KIO catches its own factual error unprompted | §23's self-correction mechanism, surfaced proactively if it clears the threshold (§18) |
| 25 | Conflicting memories | Two things the user said contradict each other | `contradicts` Link between two `attributed_to=user, stance=belief` objects; Planner may ask for clarification rather than picking one (§10) |
| 26 | Newly introduced concepts | User names a new invented process mid-conversation | New `Node(kind=concept)`, zero code change (§28) |
| 27 | Invented terminology | User redefines what "the usual" means partway through | New `belief`-stance object (`attributed_to=user`) defining the term, `supersedes` any prior definition Link — subsequent resolution (§7) prefers the live definition |
| 28 | Multimodal state | User pastes a screenshot mid-discussion referencing "this error" | Image-content `Node`; "this error" resolves (§7) to it via recency + kind-compatibility, same resolver as any text reference (§21) |
| 29 | Parallel tasks | User is debugging code and separately planning dinner in the same session | Two independently-active `situation` Nodes (§4.4/§26) with no interference — no stack depth limit, no forced suspension of one to attend the other |
| 30 | Delegation | KIO hands part of a task to a sub-agent capability, and asks about it later | `delegates_to` Link (§26); later query resolves against whatever `observation` objects the delegate has produced so far, including "still pending" as a valid state |

Every row resolves without a new stored type — the claim in §28 holds for this set.

---

## 30. Architectural Invariants That Must Never Be Violated

1. An unresolved reference never reaches capability execution.
2. Untrusted-source content (`observation`, `provenance=retrieved/observed` from tools/browser/documents) can never become an executable `intention` with authority merely by being phrased as an instruction.
3. KIO never asserts an action outcome without a corresponding `observation` object from real execution.
4. Superseded/corrected objects are never deleted, only status-transitioned.
5. Evidence attached to one claim never answers a query about a different claim — resolution always targets the specific object.
6. `attributed_to=user` and `attributed_to=KIO` content is never conflated during resolution or synthesis.
7. Low-activation (dormant) content never outranks high-activation content in default resolution merely by matching keywords — activation always gates salience.
8. Ambiguity above a defined margin is preserved as `unresolved`, never silently force-resolved.
9. Governance gates execution, never reasoning or discussion; new capabilities inherit governance from declared metadata alone.
10. No new stored type, registry, or subsystem may be created for something already representable as `Node`/`Link`/metadata — the correct response to a new need is new attribute values, never new architecture.
11. KIO-authored proactive suggestions follow identical accept/reject resolution to user-initiated ones.
12. Corrections modify state via typed links and status transitions; they never trigger a full context reset.
13. Inferred, low-confidence content is never escalated to governed execution without either explicit confirmation or independent corroboration.

---

## 31. Mapping to Current KIO Repository

| Architecture element | Current repo reality | Disposition |
|---|---|---|
| `Node`/`Link` graph store | `SessionContext` (Gate C-1) — 6 sources already unified, TTL-aware | Extend as the physical persistence layer; TTLs collapse into the uniform `time.validity_window`/`status` policy |
| Capability registry | Fragmented three ways: `CommandRegistry` (C-2), planner's `ProviderRegistry`/`STATIC_ACTION_TABLE`, browser `CapabilityRegistry` (C-09, open) | Collapse into one, extending `CommandRegistry`'s handler-registration pattern — still the mandatory first implementation step |
| Response Planner | Does not exist; `conversation_responder.py`'s `INTELLIGENCE_FALLBACK` currently swallows unmatched input (identity, greetings, casual talk) into a generic lookup-and-summarize path | Replace with §13's planner; identity resolves as an ordinary `attributed_to=KIO` self-query, no bespoke identity module |
| Reference resolution | Does not exist; "play it"/"first result" pass literal text straight into execution | Build §7 as a standalone module ahead of any capability dispatch |
| `browser_runtime`, `mcp_runtime` | Real, working execution backends, inconsistently wired | Keep unchanged; called from exactly one place (the unified capability registry) |
| KIO's own opinion/stance memory | Does not exist; regenerated from last turn each time | Falls out of §6's symmetric participant model + §17, no bespoke module needed |

---

## 32. Migration Architecture

**Keep, reframed:** `SessionContext` as persistence substrate; `CommandRegistry`'s registration pattern as the seed of the unified capability registry; `browser_runtime`/`mcp_runtime` untouched.

**Discard (from both v1 and v2):** every prior bespoke node type — `Proposition`, `KioStance`, `Evidence`, `Preference`, `Opportunity`, `Thread`/`ContextFrame`, `Resource`, `Action`/`ActionResult`, and v2's `Assertion`/`Intent` split — all now represented as `Node`/`Link` with the §4.3 metadata contract. This is a real simplification, not a rename: one lifecycle (create/supersede/correct/expire) instead of N parallel ones.

**Build new:** the reference resolver (§7) and the Planner (§13) — neither exists today in any form; these are the two components with no current partial implementation to extend.

**Refactor:** `INTELLIGENCE_FALLBACK` is deleted, not patched — its behavior (generic lookup-and-summarize on unmatched input) is the literal anti-pattern this document exists to eliminate.

---

## 33. Implementation Sequence

0. **Collapse the fragmented capability registries (C-09)** into one, extending `CommandRegistry`. Nothing downstream is safe to build on a fragmented capability layer — unchanged conclusion across all three design passes.
1. **Build the Node/Link graph store** as the successor layer under `SessionContext`, with the universal metadata contract (§4.3) — this is now a two-primitive target, more specific than v2's five-partition target.
2. **Reference resolution (§7)**, inserted between raw input and everything else — fixes literal-text-into-execution bugs immediately once wired through the unified registry from step 0.
3. **Planner (§13)**, replacing `INTELLIGENCE_FALLBACK` outright.
4. **Symmetric participant model (§6)** wired into recommendation/opinion generation and self-correction (§23).
5. **Research/evidence via the unified stance+provenance mechanism (§10/§11)** and temporal supersession (§9).
6. **Recommendation (§17) and proactivity (§18)** as thin Planner-driven layers, not separate engines.
7. **Governance, recovery, observability hardening (§25/§24)**, matching the Engineering OS's existing validation-loop doctrine.
8. **Multi-interface/new integrations** (WhatsApp, GitHub, desktop automation, additional interfaces beyond Telegram) — gated on steps 0 and 3 being stable in production, unchanged conclusion from all three passes: new surfaces built on a fragmented capability/routing layer would inherit and multiply the same bugs.

---

## 34. Validation Architecture

Acceptance is not "all listed examples pass." Acceptance is: (a) the 13 invariants in §30 hold under automated property-checks on every write to the graph; (b) all 30 scenarios in §29 pass against live transcripts, not synthetic tests, since that is where every real failure so far actually surfaced; (c) a genuinely new domain — chosen at random by whoever is validating, not by whoever built the architecture — can be handled in a live conversation with zero code changes, only new `Node.kind`/`Link` vocabulary; (d) no PR introduces a new top-level stored type without an explicit written justification for why it cannot be `Node`/`Link` with new attribute values, reviewed against §2's six invariants specifically.

---

## 35. Remaining Founder Decisions

Only three, all UX/policy defaults with no correct engineering answer — everything else in this document is resolved:

1. **Corroboration threshold** (§8) — how many independent corroborating Links are required to promote inferred content to durable/trusted, and does it vary by sensitivity of the claim?
2. **Ask-vs-guess cost threshold** (§7/§25) — a concrete default per capability class (informational vs. side-effecting) for when ambiguity should be asked about rather than resolved with a hedge.
3. **Cross-session resumption presentation** (§27) — how long a durable `situation` stays "resumable" before KIO should present continuing it as resumption vs. explicitly referencing it as history while starting fresh.

None of the 8 decisions already ratified in `FINAL_FOUNDER_DECISIONS.md` are reopened by this document — the proactive-not-autonomous policy maps directly onto §18 (KIO-authored intentions always require acceptance before execution), and memory correctability maps directly onto §8/§30.4 (explicit expiration/deletion only, full history otherwise preserved).
