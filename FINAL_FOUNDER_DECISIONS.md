# FINAL FOUNDER DECISIONS

**Governing Documents:** `KIO_CONSTITUTION.md`, `MASTER_CONVERGENCE_PLAN.md`, `KIO_ENGINEERING_OS.md`, `FOUNDER_DECISION_AUDIT.md`
**Status:** Ratified — final strategic pass before implementation

---

# Purpose

`FOUNDER_DECISION_AUDIT.md` identified eight genuine strategic decisions that could not be resolved by engineering or architecture alone — decisions that required the founder's own judgment about vision, scope, autonomy, privacy, and product identity. This document records the founder's answers to all eight.

These decisions are now canonical. They supersede every ambiguity, open question, and suggested default that appeared in the earlier documents. Where anything in the Constitution, the Convergence Plan, or the Engineering OS reads as unresolved on these eight points, this document is what resolves it — the earlier documents are not rewritten, but they are now read through these decisions.

---

# Canonical Founder Decisions

## FQ-01 — AURA Existing Work

**Decision:** The current AURA architecture (as described in the Constitution and scoped in the Convergence Plan) is the canonical implementation target. No search for previous unfinished AURA work is required. If older work surfaces later, it is treated as historical reference only, not as a redirect for Gate C-7.

**Rationale:** Removes ambiguity about where Gate C-7 starts. Building from the current, audited architecture is faster and lower-risk than pausing implementation to search for something that may not exist in a usable form.

**Architectural Impact:** Gate C-7 proceeds on its original entry criteria (Gates C-1 and C-4 complete) with no added search phase. Contradiction C-01 is resolved: the Constitution's AURA description is confirmed as an aspirational target, not a claim about current state.

**Implementation Impact:** No new pre-Gate-C-7 task is introduced. The coding agent builds AURA fresh, per the Constitution's Layer 0–9 outline, without waiting on a discovery step.

---

## FQ-02 — Initiative Policy

**Decision:** KIO may be proactive but not autonomous. Allowed without explicit request: observations, reminders, recommendations, warnings, summaries, insights, draft generation, planning suggestions, opportunity detection. Not allowed without explicit user request or a user-approved automation: external actions, sending messages, modifying files, browser automation, purchases, API actions, system changes. AURA produces execution intent only — the Execution Fabric is what performs actions, and it still requires explicit authorization to act.

**Rationale:** Resolves the direct contradiction between `ARCHITECTURE_LOCK.md` Rule 12 ("no autonomous initiative") and Constitution §15 ("initiative within safe boundaries") with a concrete, buildable line: KIO can think, notice, and suggest on its own; it cannot act on the world on its own. This preserves the companion vision's initiative without reopening the safety doctrine's core guarantee.

**Architectural Impact:** Resolves Contradiction C-07. `ARCHITECTURE_LOCK.md` Rule 12 does not need to be weakened — it needs to be read as governing the Execution Fabric specifically, while AURA's proactive layer (observation, recommendation, drafting) operates above it, never crossing into action without authorization. This is the architectural seam Gate C-7's Action layer is built around: AURA emits intent; a separate, already-existing authorization boundary (`execution_boundary.py`) decides whether intent becomes action.

**Implementation Impact:** Gate C-7's Action layer (step 7 of its build sequence) is now fully specified rather than blocked. It implements "emit execution intent," not "take action" — the existing `execution_boundary.py` remains the sole path to real-world effects, exactly as it already is for every other KIO capability.

---

## FQ-03 — Gate Order

**Decision:** Keep the current implementation order. Architecture convergence remains the highest priority. Proceed through Gates C-1 → C-7 exactly as sequenced in `MASTER_CONVERGENCE_PLAN.md`. Do not prioritize visible features over architectural integrity.

**Rationale:** The existing sequencing already front-loads user-visible payoff (Gate C-1 alone resolves 7 of 19 documented failures) while keeping the harder architectural consolidation work ordered by actual dependency, not by what would look most impressive first.

**Architectural Impact:** None — this decision confirms the Gate Roadmap as-is. No Gate is reordered, merged, or skipped.

**Implementation Impact:** The Engineering OS's Vision Gap Analysis (step 0 of its loop) still identifies the largest gap each cycle, but "largest gap" is now explicitly read within the existing Gate sequence — it does not license jumping ahead to a later Gate's capability because it would be more visible sooner.

---

## FQ-04 — Local-First Philosophy

**Decision:** Local-first means the user owns their data. KIO runs on founder-controlled hardware. Cloud models are acceptable when intentionally selected, not by default drift. The architecture must remain provider-agnostic. Local models become preferred over cloud models as they become practical, on an ongoing basis — not a one-time switch.

**Rationale:** Resolves the tension between the Constitution's "local-first" principle and Gemini's current role as the production LLM provider. The distinction that matters is data ownership and control, not a hard ban on cloud inference — but it does require providers to remain swappable rather than the architecture quietly hardening around one cloud vendor.

**Architectural Impact:** Confirms D-08's `CapabilityProvider` disambiguation and the existing multi-provider failover chain (`llm_gateway.py`) as correct and sufficient — provider-agnosticism was already an architectural property, and this decision makes it an explicit, permanent requirement rather than an incidental one. No change to Gate C-5's provider consolidation plan.

**Implementation Impact:** Every future provider integration is evaluated against "does this preserve provider-agnosticism," not just "does this work." Local models (Ollama, etc.) are upgraded from "partial" to "actively preferred as they mature" in the Current-State Map's ongoing maintenance, without requiring an immediate migration off Gemini.

---

## FQ-05 — AURA Memory Governance

**Decision:** AURA remembers only what improves long-term assistance — not everything, by default. Memory must support inspection, correction, deletion, and configurable retention. Memory is not permanent by default. Confidence may decay over time. Knowledge may evolve or be revised. Sensitive categories of information remain under explicit user control.

**Rationale:** Answers the privacy-and-trust question left open in the Constitution: what AURA is allowed to keep forever versus what it should let go of. Ties retention directly to usefulness rather than defaulting to "store everything" — and makes correction and deletion first-class, not an afterthought bolted on later.

**Architectural Impact:** This is now a hard requirement on AURA's Knowledge and Belief layers (Gate C-7, Layers 1–2), not a design nicety: the schema must support per-item retention metadata, confidence decay, and a user-facing inspection/correction/deletion path from the start. Building this in from the beginning avoids the expensive retrofit `FOUNDER_DECISION_AUDIT.md` flagged as the specific risk of leaving FQ-05 unresolved.

**Implementation Impact:** Gate C-7's Knowledge layer (step 3 of its build sequence) now includes, as part of its exit criteria: retention is bounded by usefulness rather than unconditional, confidence values decay, and at least a minimal inspection/correction/deletion interface exists before the layer is considered done. "Sensitive categories" is deliberately left for the founder to specify per-category as they arise, rather than KIO pre-guessing an exhaustive list.

---

## FQ-06 — Override Policy

**Decision:** KIO may respectfully disagree once. After that, the user's decision prevails — unless it's already prohibited by an existing safety policy. KIO is a trusted companion, not a paternalistic authority.

**Rationale:** Confirms the audit's suggested default almost exactly: bounded disagreement, then deference. This keeps the companion relationship's "protect long-term interests" language from Constitution §15 from silently expanding into a right to refuse.

**Architectural Impact:** No new refusal category is introduced beyond what `execution_boundary.py` already enforces. The one-time-disagreement behavior is a conversational/response-layer concern (Layer 5, Gate C-4's response separation), not a new safety-gate mechanism.

**Implementation Impact:** Gate C-4's self-verification gate (`verify(goal, response)`) may express disagreement once when relevant, but nothing downstream is authorized to block a user-confirmed action on the basis of that disagreement alone. Only the existing safety boundary can do that.

---

## FQ-07 — User Scope

**Decision:** Version 1 is permanently optimized for a single persistent user. The architecture should not actively prevent future multi-user support, but no additional complexity is introduced today solely for hypothetical future users.

**Rationale:** Confirms the audit's finding that the Constitution's consistent singular "the user" framing reflects real intent, not an oversight — while leaving a door open rather than nailing it shut, at zero present cost.

**Architectural Impact:** The Context Manager (Gate C-1) and AURA's identity/belief model (Gate C-7) are built single-subject. "Don't prevent future multi-user support" means avoiding decisions that would be actively hostile to it later (e.g., baking a single global mutable identity object directly into low-level function signatures everywhere) — it does not mean building any multi-user abstraction now.

**Implementation Impact:** The Engineering OS's Telegram validation item "multiple concurrent users where the deployment model supports it" is read, per the audit's suggested default, as multiple sessions by the same person — not multiple distinct identities. No multi-user work is scheduled in any current Gate.

---

## FQ-08 — Product Scope

**Decision:** KIO is designed first as a personal lifelong companion. Avoid unnecessary hardcoding that would foreclose future open-sourcing or productization, but do not optimize for commercial distribution today.

**Rationale:** Splits the difference correctly between two extremes: neither building a generic multi-tenant product prematurely, nor making decisions so personal-specific that a future pivot would require a rewrite rather than a refactor.

**Architectural Impact:** No structural change. This is a standing constraint applied going forward: `KIO_character_knowledge.py` and similarly personal artifacts remain founder-specific, but new architecture (e.g., the Capability Registry, the Context Manager) is built at the same generality it would be built at anyway for good engineering reasons — this decision doesn't ask for extra generalization work beyond what Constitution §6 ("modular by design") already implies.

**Implementation Impact:** No Gate changes. This decision is a filter on future work: if a design choice would meaningfully block productization later at no present benefit, avoid it; if avoiding it would cost real complexity today for a hypothetical future need, don't pay that cost yet.

---

# Documents Affected

**`KIO_CONSTITUTION.md`** — No text changes. Section 15's "initiative within safe boundaries" is now read specifically through FQ-02's proactive-not-autonomous line; "protect long-term interests" is now read through FQ-06's one-time-disagreement bound; the singular "the user" framing is now confirmed, not merely descriptive, per FQ-07.

**`MASTER_CONVERGENCE_PLAN.md`** — The "Founder Questions" section (Q-01 through Q-05) is now fully resolved; those five open items should be marked answered, referencing this document. Q-05 (snapshot disposition) remains correctly excluded per the Audit's reclassification as engineering work. Gate C-7's entry criteria no longer include "pending Founder decision on Q-02" as a blocker for the whole Gate — only its Action layer was ever narrowly gated, and FQ-02 now resolves that narrowly too.

**`KIO_ENGINEERING_OS.md`** — Section 12's (Stop Conditions) treatment of Q-01, Q-02, Q-04, and Q-05 as open blockers is superseded: none of them are open anymore. The scoped-escalation mechanism itself is unaffected — it's simply no longer needed for these specific questions, since they're resolved rather than merely narrowly scoped. The "multiple users" item in the Telegram Validation Loop (Section 6) is now explicitly interpreted per FQ-07.

**`FOUNDER_DECISION_AUDIT.md`** — Every FQ-01 through FQ-08 entry's "Suggested Default" section is superseded by the actual decision recorded here (which in most cases matches the suggested default, and in FQ-02, FQ-04, and FQ-05's cases refines it into something more specific and buildable).

---

# Resolution Summary

| ID | Resolved | Reason | Impact |
|---|---|---|---|
| FQ-01 | Yes | Build from current architecture; no search for lost work | Gate C-7 starts immediately on its existing entry criteria |
| FQ-02 | Yes | Proactive-not-autonomous, with a clear allowed/disallowed list | Contradiction C-07 resolved; Gate C-7's Action layer fully specified |
| FQ-03 | Yes | Confirmed existing Gate order | No change to the roadmap |
| FQ-04 | Yes | Local-first = data ownership, not a cloud ban; provider-agnostic required | Confirms existing multi-provider architecture as correct |
| FQ-05 | Yes | Usefulness-bound memory with inspection/correction/deletion, confidence decay | New hard requirement on Gate C-7's Knowledge/Belief layers |
| FQ-06 | Yes | Disagree once, then defer, except existing safety limits | No new refusal mechanism; response-layer behavior only |
| FQ-07 | Yes | Single-user for v1, door left open, no work done for it now | Context Manager and AURA identity model stay single-subject |
| FQ-08 | Yes | Personal-first, avoid needless foreclosure, no commercial optimization | Standing filter on future design choices, no immediate change |

---

# Remaining Founder Decisions

No remaining strategic founder decisions were identified.

All eight items surfaced in `FOUNDER_DECISION_AUDIT.md` are resolved above. No new strategic ambiguity was introduced by resolving them — each decision either confirmed an existing default or narrowed an open question into a specific, buildable rule without creating a new open question in the process.

---

# Engineering Impact

**AURA:** Has a confirmed starting point (FQ-01), a bounded and buildable Action layer (FQ-02), and hard, non-negotiable requirements on its Knowledge/Belief layers (FQ-05). Gate C-7 is no longer blocked on any founder input — it's blocked only on its existing engineering dependencies (Gates C-1 and C-4).

**KIO (core/routing/context/planning):** Unaffected structurally. FQ-03, FQ-04, and FQ-07 confirm existing direction (Gate order, provider architecture, single-subject context model) rather than changing it.

**Execution Fabric:** Gains a clarified role under FQ-02 — it is now explicitly the sole boundary between AURA's intent and real-world action, reinforcing rather than changing `execution_boundary.py`'s existing responsibility.

**Gate C-7:** Goes from "the one High-risk Gate with an open Founder blocker on its Action layer" to fully specified across all seven of its build steps. Its risk register entry (R-04 in the Convergence Plan) can be closed; R-05 (AURA architecture must be defined from scratch) is unchanged and still applies.

**Implementation Planning:** No new Gates, no reordering, no scope expansion. The Engineering OS's Stop Conditions (Section 12) shed four of their five example blockers (Q-01, Q-02, Q-04, and effectively Q-05 was never a real one) — only genuinely novel future ambiguities should trigger that mechanism going forward, not any question on this list.

---

# Final Readiness Assessment

✓ **Vision Complete** — `KIO_CONSTITUTION.md`, unchanged, remains the ratified destination.
✓ **Founder Intent Complete** — all eight strategic questions identified by the audit are now answered.
✓ **Architecture Complete** — `MASTER_CONVERGENCE_PLAN.md`'s Unified Target Architecture and Gate Roadmap require no revision as a result of these decisions; they were designed to accommodate exactly this kind of resolution.
✓ **Ready for Detailed Specifications** — Gate C-7 in particular can now be specified in full detail (Knowledge layer schema, Action layer intent format) rather than deferred pending founder input.
✓ **Ready for Implementation** — Gates C-1 through C-6 were never blocked; Gate C-7 is now unblocked as well.

**Remaining blockers:** none strategic. What remains is ordinary engineering and specification work already anticipated by the existing documents — for example, the concrete schema for AURA's per-item retention metadata (FQ-05's requirement, not yet a data model), the exact intent format AURA's Action layer emits to the Execution Fabric (FQ-02's requirement, not yet an interface), and the routine Gate-by-Gate implementation work `KIO_ENGINEERING_OS.md` already governs. None of these require further founder judgment — they require engineering.

---

# Final Conclusion

Strategic work on KIO is complete. The Constitution defines what KIO is. The Convergence Plan defines the path from the current repository to that definition. The Engineering OS defines how implementation proceeds, cycle by cycle. This document closes the last gap between those three: the eight decisions only the founder could make are now made, and none of them required reopening the Constitution, redesigning the architecture, or reordering the roadmap — each one either confirmed what was already the right default or turned an open question into a specific, implementable rule.

What remains from here is engineering: building Gates C-1 through C-7 against documents that are now fully specified at the strategic level. Nothing in that remaining work requires the founder's judgment again unless implementation surfaces a genuinely new ambiguity — in which case `KIO_ENGINEERING_OS.md` Section 12's scoped-escalation mechanism, not another audit, is the right tool to raise it.
