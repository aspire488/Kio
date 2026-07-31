# FOUNDER DECISION AUDIT

**Scope:** `KIO_CONSTITUTION.md`, `MASTER_CONVERGENCE_PLAN.md`, `KIO_ENGINEERING_OS.md`
**Objective:** Identify every decision across all three documents that requires the founder's judgment specifically — not architecture, not engineering, not implementation detail.

---

## Method

Started from the 5 questions already logged in `MASTER_CONVERGENCE_PLAN.md` (Q-01–Q-05) and re-tested each against the stricter bar in this audit: *would an engineer or architect be able to decide this without changing the product's vision?* One (Q-05) fails that test in the other direction — it's actually pure engineering housekeeping, not a founder question, despite being logged as one. Then swept all three documents for latent founder-level decisions that were never logged anywhere: places where the Constitution states a principle but leaves a scope or boundary genuinely open. Four were found. Total after reclassification: **8 genuine Founder Questions.**

---

## FQ-01 — AURA's Real State

**Source Document:** `MASTER_CONVERGENCE_PLAN.md` (Founder Questions Q-01, Contradiction C-01); `KIO_CONSTITUTION.md` §1, 2, 7
**Section:** Contradiction Log C-01 / AURA Current-State Map
**Original Text:** Constitution describes AURA as having "17 subsystems implemented; 11 agents pending activation... ~40 chapter canonical document." Audit found a 35-line stub README and no cognitive-loop code.
**Founder Question:** Is the Constitution's AURA description the *target* to build toward from scratch, or does prior AURA work exist outside the audited repository that should be located and restored instead of rebuilt?
**Why This Requires Founder Input:** Only the founder can know whether prior work exists elsewhere — this isn't discoverable by auditing the current repository, no matter how thoroughly.
**Architectural Impact:** Determines whether Gate C-7 starts from zero or resumes an existing architecture.
**Product Impact:** Affects both timeline and whether AURA's design already reflects considered intent that shouldn't be re-derived.
**Suggested Default:** Treat as aspirational and build fresh (the Convergence Plan's current working assumption) unless the founder produces prior material.

---

## FQ-02 — Autonomy and Initiative Policy

**Source Document:** `KIO_CONSTITUTION.md` §15; `MASTER_CONVERGENCE_PLAN.md` Contradiction C-07 / Q-02; referenced `ARCHITECTURE_LOCK.md` Rule 12
**Section:** Founder's Vision (Constitution §15) vs. ARCHITECTURE_LOCK Rule 12
**Original Text:** Rule 12: *"No uncontrolled autonomy — all actions require explicit user request or deterministic trigger. No autonomous initiative."* Constitution §15: *"Initiative and curiosity within safe boundaries — the ability to explore and propose."*
**Founder Question:** Should KIO have autonomous initiative at all — and if so, in which specific domains or action types (proactive reminders, flagging risks, drafting but not sending, taking real-world actions without per-instance approval), under what approval model?
**Why This Requires Founder Input:** This is a core AI-autonomy and product-identity decision. How much agency KIO has directly shapes trust, safety exposure, and what "companion, not assistant" means in practice — no architectural analysis resolves this, because there is no objectively correct answer, only a preferred one.
**Architectural Impact:** Gates the entire Action/initiative layer of AURA (Gate C-7); determines whether `ARCHITECTURE_LOCK.md` Rule 12 needs formal amendment.
**Product Impact:** Fundamentally shapes the character of the companion relationship.
**Suggested Default:** No safe universal default exists. If forced to proceed provisionally: start narrow — propose-but-don't-act — and expand only per explicit founder approval, domain by domain.

---

## FQ-03 — Convergence Scope and Gate Priority

**Source Document:** `MASTER_CONVERGENCE_PLAN.md` (Founder Questions Q-03)
**Section:** Founder Questions
**Original Text:** *"Are the gates in this convergence plan (C-1 through C-7) the right sequence toward that companion vision, or is there additional guidance on what 'companion' means in practice for the next 3 months?"*
**Founder Question:** Should architectural convergence (C-1–C-6) proceed first as sequenced, or does the founder want a specific slice of companion-facing behavior prioritized ahead of the invisible architecture cleanup?
**Why This Requires Founder Input:** Prioritization among legitimate, equally-valid orderings is a judgment call about what "visible progress" should feel like — not something the architecture itself dictates.
**Architectural Impact:** Could reorder or interleave Gates; doesn't change what any individual Gate does.
**Product Impact:** Affects how soon the founder sees companion-facing behavior versus infrastructure convergence.
**Suggested Default:** Proceed with the current sequencing — Gate C-1 alone resolves 7 of 19 documented user-visible failures, so the "invisible" work has visible payoff early.

---

## FQ-04 — Deployment Model and Inference-Location Policy

**Source Document:** `KIO_CONSTITUTION.md` §6 ("Local-first where practical"); `MASTER_CONVERGENCE_PLAN.md` Founder Questions Q-04; Current-State Map (Gemini as production LLM provider)
**Section:** Guiding Principles (Constitution §6) vs. actual provider configuration
**Original Text:** Constitution: *"Local-first where practical."* Current-State Map: *"Gemini and mock are production"* — a cloud provider is the primary active LLM.
**Founder Question:** Does "local-first" mean (a) the KIO process runs on a machine the founder physically controls, (b) LLM inference itself must be local/on-device wherever feasible, or (c) both — and separately, should the target deployment stay a single desktop machine or move toward an always-on server/multi-device model?
**Why This Requires Founder Input:** This trades privacy (data leaving the machine via a cloud LLM call) against capability and cost — a values-and-resources trade-off, not an engineering one. It's also already being decided implicitly by default (Gemini in production) without an explicit founder ruling.
**Architectural Impact:** Resource-budget assumptions, provider prioritization (local models vs. cloud), persistence architecture.
**Product Impact:** Directly shapes the privacy story of a system designed to accumulate deep, permanent personal knowledge.
**Suggested Default:** Keep the current de facto state — single desktop machine, Gemini as primary cloud provider, local models as fallback — until explicitly changed.

---

## FQ-05 — AURA Data Governance and Privacy Philosophy

**Source Document:** `KIO_CONSTITUTION.md` §15, §7
**Section:** Founder's Vision — Cognitive Identity; The Role of AURA
**Original Text:** *"Its own persistent internal state that accumulates experience, confidence, uncertainty, context, priorities, relationships, and lessons learned."* AURA: *"accumulated knowledge, experience, preferences, project history, reasoning history... long-term goals."*
**Founder Question:** What does AURA retain indefinitely, what expires or can be forgotten, and can the founder view, correct, or delete what AURA believes about them? Is any category of interaction off-limits for persistence entirely?
**Why This Requires Founder Input:** This is a privacy-and-trust decision inseparable from what "trustworthy companion" actually means. No amount of architecture review determines what should be remembered forever versus deliberately forgotten — that's a values call.
**Architectural Impact:** Shapes AURA's Knowledge/Belief layer schema and retention/deletion mechanisms (Gate C-7) — expensive to retrofit once built.
**Product Impact:** Central to whether the companion relationship feels safe rather than surveilled.
**Suggested Default:** None recommended. This should be answered before Gate C-7's Knowledge layer is designed, not after.

---

## FQ-06 — Override and Refusal Policy

**Source Document:** `KIO_CONSTITUTION.md` §15
**Section:** Founder's Vision — companion relationship in practice
**Original Text:** *"It should respectfully disagree when evidence suggests the user is making a poor decision... protect the user's long-term interests."*
**Founder Question:** When KIO disagrees and the founder insists anyway, does KIO always comply after voicing its objection once — or are there categories of request where KIO can decline even after being overridden?
**Why This Requires Founder Input:** This is a paternalism-boundary decision. How far "protect long-term interests" is allowed to go against explicit instruction is a values call about the outer edge of the companion relationship, not a technical one.
**Architectural Impact:** Determines whether the execution/safety boundary needs a distinct "soft refusal" behavior beyond today's hard safety gate (`execution_boundary.py`).
**Product Impact:** Defines whether KIO is ultimately a partner or a compliant tool at the edges.
**Suggested Default:** User override always wins after one clear objection, with no new refusal category beyond what the existing safety gate already covers, until the founder decides otherwise.

---

## FQ-07 — Single-User vs. Multi-User Scope

**Source Document:** `KIO_ENGINEERING_OS.md` §6; `KIO_CONSTITUTION.md` §15 (singular "the user" throughout)
**Section:** Production Telegram Validation Loop; Founder's Vision
**Original Text:** Engineering OS: *"multiple concurrent users where the deployment model supports it."* Constitution: consistently refers to "the user," singular, throughout.
**Founder Question:** Is KIO permanently a single-user companion for the founder, or should the architecture anticipate other people (family, collaborators) eventually having their own relationship with KIO, or their own instance?
**Why This Requires Founder Input:** This changes what "know the user deeply" even means — a system built around one continuous identity relationship is a fundamentally different product than one built for several.
**Architectural Impact:** Affects the Context Manager and AURA's identity/belief model — a single-subject vs. multi-subject data model is far cheaper to decide now than to retrofit later.
**Product Impact:** Core to "lifelong companion" — companion to whom, specifically.
**Suggested Default:** Single-user only, matching the Constitution's consistent framing. Read the Engineering OS's "multiple users" checklist item as multiple chat sessions by the same person, not multiple distinct identities, unless the founder says otherwise.

---

## FQ-08 — Productization and Sharing Intent

**Source Document:** Not addressed in any of the three documents — a genuine gap, not a stated contradiction.
**Section:** N/A
**Original Text:** N/A
**Founder Question:** Is KIO purely a personal system for the founder, or is there any intent — now or later — to share, open-source, or productize it for other people?
**Why This Requires Founder Input:** A pure business/product-scope decision that no engineering analysis of the current documents can infer.
**Architectural Impact:** Affects how tightly the Character Bible (`KIO_character_knowledge.py`) and personal data handling can be hardcoded versus needing to be configurable or generalized.
**Product Impact:** Determines whether today's hyper-personal design choices are permanent assets or future liabilities.
**Suggested Default:** Assume personal-only, matching every current design decision. Revisit only if the founder raises it.

---

## Excluded: Q-05 (Snapshot Archive Disposition)

`MASTER_CONVERGENCE_PLAN.md` logs this as a Founder Question, but it fails this audit's bar: whether to move 16 historical snapshot directories (~1.3 GB) to cold storage is a housekeeping/ops decision an engineer can make unilaterally — it doesn't touch vision, scope, or product identity. **Reclassified as engineering work, not a Founder Question.** Recommend removing it from the Founder Questions list in `MASTER_CONVERGENCE_PLAN.md` and handling it as ordinary technical debt (already reflected as Low-priority debt in that document).

---

## Final Analysis

### 1. Total Founder Questions Found: 8

(5 originally logged, minus 1 reclassified as engineering, plus 4 newly identified.)

### 2. Categories

| Category | Questions |
|---|---|
| AURA | FQ-01, FQ-05 |
| Safety / AI Autonomy | FQ-02 |
| Privacy | FQ-04 (partial), FQ-05 |
| Scope / Long-term Strategy | FQ-03, FQ-07, FQ-08 |
| Product / UX Philosophy | FQ-06 |
| Deployment / Business Trade-off | FQ-04 |

### 3–4. Deduplicated, Rewritten as Single Founder Decisions

| ID | One-Line Decision |
|---|---|
| FQ-01 | Is AURA built fresh, or does prior work exist to restore instead? |
| FQ-02 | How much autonomous initiative, if any, is KIO allowed — and in which domains? |
| FQ-03 | Does architecture convergence proceed first as sequenced, or should companion-facing work jump the queue? |
| FQ-04 | Does "local-first" constrain LLM inference location too, and is desktop or server the target deployment? |
| FQ-05 | What does AURA remember forever, what can it forget, and can the founder inspect or edit it? |
| FQ-06 | Can KIO ever refuse a request after voicing disagreement, or does the founder's word always win? |
| FQ-07 | Is KIO single-user forever, or should multi-user identity be designed for now? |
| FQ-08 | Personal system only, or eventual product for others? |

### 5. Ranked by Importance

| Rank | ID | Reason |
|---|---|---|
| **Critical** | FQ-02 | Blocks the core companion-identity question and the entire AURA Action layer; no safe default exists |
| **Critical** | FQ-01 | Blocks Gate C-7's starting assumptions; costs real time if guessed wrong |
| **High** | FQ-05 | Expensive to retrofit once AURA's Knowledge layer is built; should precede Gate C-7, not follow it |
| **High** | FQ-04 | Shapes resource and provider architecture across the whole remaining build |
| **Medium** | FQ-06 | Has a safe, stated default; can proceed now, revisit later |
| **Medium** | FQ-07 | Has a safe, stated default; cheap to hold the default, expensive to reverse later if ignored too long |
| **Low** | FQ-03 | Current sequencing is already well-justified; low risk either way |
| **Low** | FQ-08 | Doesn't block near-term implementation at all |

### 6. How Many Genuine Founder Decisions Remain Before KIO and AURA Can Proceed to Implementation?

**Zero block Gates C-1 through C-6.** All six can proceed today under the Engineering OS's scoped-escalation rule — none of the 8 questions above touch context management, routing, planning wiring, response separation, provider consolidation, or documentation reconciliation.

**Three should be resolved before Gate C-7 (AURA) begins in earnest:** FQ-01 (what AURA actually is), FQ-02 (how much initiative it's allowed), and FQ-05 (what it's allowed to remember). These three aren't just risky to guess — two of them (FQ-02, FQ-05) are expensive specifically because AURA's Action and Knowledge layers are hard to redesign after they're built, not just inconvenient to redo.

**The remaining five (FQ-03, FQ-04, FQ-06, FQ-07, FQ-08) all have stated, safe defaults** and don't need to block anything — they can be confirmed opportunistically, whenever convenient, without costing the project time now.
