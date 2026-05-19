# GATE 2 VALIDATION STRATEGY: SCENARIO SCALING

**Goal:** Verify Gate 2 capability expansion through 300+ deterministic scenarios and stress testing.

---

## 1. Verification Tiers

### Tier 1: Unit & Boundary (Integrity)
- **Constraint Checks:** Verify `ContextBuffer` limit (16).
- **Transition Guarding:** Ensure Gate 2 states don't violate Gate 1 lifecycle.
- **Permission Blocking:** Re-verify that `shutdown` remains blocked.

### Tier 2: Behavioral Scenarios (Scaling)
- **Batch 1: App Discovery (50 cases)**
  - Launching apps by common names, aliases, and partial matches.
- **Batch 2: Contextual Chains (50 cases)**
  - Testing "open X" then "close it" across various app types.
- **Batch 3: File Routing (50 cases)**
  - Deep folder access and path normalization checks.
- **Batch 4: Multi-step Stress (100 cases)**
  - Complex sequences (3+ steps) with varied connectors ("and", "then", "followed by").
- **Batch 5: Malformed & Edge (50 cases)**
  - Fuzzing the parser with unusual symbols, empty targets, and rapid-fire commands.

### Tier 3: Runtime Survival (Stress)
- **Cycle Stress:** 1000 consecutive command dispatches.
- **Memory Stability:** RSS check after 4 hours of idle vs. 1 hour of heavy activity.
- **Recovery Test:** Simulated operator failure during a 5-step chain.

## 2. Success Criteria
- **Pass Rate:** > 98% for Tier 2 scenarios.
- **Memory:** Idle RSS < 150MB.
- **Zero Orphans:** No leftover handles or zombie processes after scenario completion.
- **Deterministic Tracing:** 100% of actions captured in `runtime_trace.log`.

## 3. The "Survival Harness"
Gate 2 will utilize an expanded `gate2_survival_harness.py` that:
1. Boots the runtime.
2. Injects scenario batches.
3. Monitors `runtime_trace.log` in real-time.
4. Performs "System State Diffs" (e.g., checking process lists before/after).
5. Reports failure heatmaps by category.

---

## Testing Gates (Phased Approval)
- **Entry Gate 2.1:** Pass all Gate 1 survival tests.
- **Entry Gate 2.2:** Pass Phase 1 (Foundation) scenarios.
- **Entry Gate 2.3:** Pass Phase 2 (Operator) scenarios.
- **Final Exit:** 300+ scenarios passed + zero-leak verification.
