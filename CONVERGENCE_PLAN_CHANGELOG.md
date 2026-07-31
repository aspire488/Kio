# Convergence Plan — Revision Changelog

**Version:** 1.0 → 1.1
**Date:** 2026-07-23
**Change type:** Refinement pass (no redesign, no architecture changes, no gate reordering)

---

## Change 1: Repository-scoped evidence language (6 locations)

**Rationale:** Replace definitive/absolute claims about AURA's non-existence with evidence-scoped wording that only concludes what the audited repository supports.

### 1a — Executive Summary (Section 0)
- **Before:** `AURA is named but not present.`
- **After:** `AURA is named in the Constitution but no implementation was found in the audited repository.`

### 1b — AURA Continuity Layer table (Section 1.3)
- **Before:** `Missing` / `Does not exist in filesystem` / `No code or architecture doc exists` / `No code exists`
- **After:** `Not found in repository` / `No evidence of this document was located in the audited repository` / `No implementation was found during this audit in the audited repository`

### 1c — Contradiction C-01 (Section 2)
- **Before:** `aura/README.md is a 35-line stub. aura_integration.py emits observations to nowhere (stubbed receiver). No cognitive loop code exists. No canonical document exists.`
- **After:** `The audited repository contains a 35-line stub README at aura/README.md and a 200-line integration API. No cognitive loop implementation was found. No canonical architecture document was located.`
- **Before:** `The Constitution's foundational claim about AURA's existence level is incorrect.`
- **After:** `The Constitution describes AURA at a level of existence that the audited repository does not currently reflect.`

### 1d — Convergence Decision D-01 (Section 3)
- **Before:** `...not from assumed-existing 40-chapter doc.`
- **After:** `...No pre-existing AURA implementation was found to extend.`

### 1e — Unified Architecture Layer 6 note (Section 4)
- **Before:** `the cognitive layer does not`
- **After:** `the cognitive layer was not found during this audit`

### 1f — Founder Question Q-01 (Section 7)
- **Before:** `The AURA directory is a stub README` / `The canonical document does not exist in the filesystem` / `No cognitive loop, no agents, no Layer 0-9 hierarchy exists`
- **After:** `The aura/ directory contains a stub README` / `No evidence of the canonical architecture document was located` / `No cognitive loop, agent implementations, or Layer 0-9 hierarchy were found`
- **Before:** `or was there a version of AURA that has been lost/moved?`
- **After:** `or does an AURA implementation exist outside this repository that should be integrated?`

### 1g — Summary (Section 9)
- **Before:** `AURA is named in the Constitution but absent from the codebase.`
- **After:** `AURA is described in the Constitution but no implementation was found in the audited repository.`

---

## Change 2: Remove all timeline estimates (7 locations)

**Rationale:** Replace calendar-based duration estimates with dependency-driven prerequisites and dependencies.

### 2a-2g — Gate headers (Section 5, Gates C-1 through C-7)

Removed `Duration:` line from every gate.

Added `Prerequisites:` field to every gate:
- **C-1:** `None` (was previously implicit; Duration was the only time reference)
- **C-2:** `Gate C-1 must be complete (unified context provides the state management that capabilities will query)`
- **C-3:** `Gate C-2 must be complete (capability registry provides the discoverable routing that the planner will target)`
- **C-4:** `Gate C-1 must be complete... Gate C-3 must be complete...`
- **C-5:** `None`
- **C-6:** `Gates C-1 through C-5 must be complete (documentation must reflect converged codebase)`
- **C-7:** `Founder decision on C-07... Gate C-1 must be complete... Gate C-4 must be complete...`

### 2h — Risk Register R-04 (Section 6)
- **Before:** `All other gates (C-1 through C-6, ~6-8 weeks) can proceed.`
- **After:** `All other gates (C-1 through C-6) can proceed.`

### 2i — Risk Register R-07 (Section 6)
- **Before:** `Gate C-1 through C-6 produce 6+ weeks of changes`
- **After:** `Gate C-1 through C-6 produce extensive changes`

### 2j — Found Question Q-03 (Section 7)
- **Before:** `in practice for the next 3 months?`
- **After:** `in practice for the practical execution horizon?`

### 2k — Summary (Section 9)
- **Before:** `Estimated timeline: C-1 through C-6 (architecture convergence): 6-8 weeks. C-7 (AURA foundation): 2-3 weeks post-Founder decision. Total: 8-11 weeks.`
- **After:** `Execution ordering: Gates C-1 through C-4 are strictly sequential... Gate C-5 is independent... Gate C-6 must follow all preceding gates. Gate C-7 depends on the C-07 founder decision and gates C-1 and C-4. See each gate's prerequisites and dependencies for exact ordering.`

---

## Change 3: Quality pass — soften unsupported certainty (3 locations)

### 3a — Contradiction C-03 (Section 2)
- **Before:** `Years of planning-layer engineering is unused.`
- **After:** `Existing planning-layer engineering is unused.`

(Removes the implicit claim about how long the engineering took — the files exist, but their development duration is not audited evidence.)

### 3b — Duplicate line in architecture diagram (Section 4)
- **Before:** `Long-term memory consolidation` appeared twice (duplicate artifact from edit)
- **After:** Single occurrence.

---

## Summary of preservation

The following were NOT changed:
- Current-state map structure and recommendations
- Contradiction log (8 contradictions preserved, only wording scoped)
- Convergence decisions (16 decisions preserved)
- Unified target architecture and layer boundary rules
- Gate ordering and step definitions
- Risk register entries (7 risks preserved)
- Founder questions (5 questions preserved)
- Implementation philosophy (no-rewrite, reuse-first)
- Deliverables checklist
