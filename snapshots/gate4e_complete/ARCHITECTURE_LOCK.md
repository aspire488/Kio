# ARCHITECTURE LOCK — IMMUTABLE RULES

These rules must survive ANY Gate 4 change. No exception.

## Core Rules

1. **Centralized runtime authority** — runtime.py is the single dispatch
   source of truth. No parallel dispatch paths.
2. **Deterministic orchestration** — no probabilistic execution paths.
   LLM proposes, runtime decides.
3. **Bounded memory** — strict RAM caps enforced at every ingestion point.
   No unbounded growth.
4. **Runtime veto supremacy** — SafetyState.LOCKDOWN/EMERGENCY overrides
   all dispatch, including Gate 3 pipeline.
5. **Lightweight runtime** — stdlib only in core paths. No heavy
   frameworks, no async event loops beyond asyncio.
6. **RAM-aware design** — every subsystem has a measured budget.
   Target idle: < 150 MB.
7. **Phased stabilization-first** — each sub-gate must stabilize before
   next starts. No parallel sub-gate work.
8. **Modular operators** — app/file/browser/system operators are
   independent, single-responsibility. No cross-operator coupling.
9. **Fail-closed execution** — any validation failure = no execution.
   No partial success propagation.
10. **Validation-before-execution** — classify → validate → orchestrate →
    handoff. Fixed pipeline order.
11. **Conversational isolation** — LLM output never reaches execution
    unvalidated. CONVERSATIONAL_ONLY blocks all dispatch.
12. **No uncontrolled autonomy** — all actions require explicit user
    request or deterministic trigger. No autonomous initiative.

## Lock Enforcement

- Merge to main requires all ARCHITECTURE_LOCK rules to hold
- Any change that weakens runtime authority is automatically rejected
- New modules must declare which rule they preserve
- Code review must verify lock compliance before approval
