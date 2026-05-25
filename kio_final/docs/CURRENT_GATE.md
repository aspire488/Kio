# CURRENT_GATE: Gate 4 — Provider Stabilization & Operational Refinement

Branch:          gate4_foundation
Status:          PLANNING (no implementation started)
Upstream:        Gate 3 — COMPLETE (tagged gate3_complete, gate3_final_locked)
Test baseline:   89/89 passing (tests/gate3/)
Compile:         CLEAN
Working tree:    CLEAN
Snapshots:       ARCHIVED

## Sub-Gate Execution Order (strictly sequential)

4A → 4C → 4D → 4B → 4E → 4F

Each sub-gate must reach COMPLETE (tests + compile + signoff) before next begins.

## Active Sub-Gate: 4A — Provider Stabilization

Entrypoint:     mini_kio/llm/provider_manager.py
Scope:          Provider lifecycle hardening, health tracking, failover logic
Dependencies:   None (Gate 3 LLM gateway normalization already complete)
RAM budget:     +0 MB (uses existing infrastructure)
Risk:           Low — isolated to llm/ layer, no runtime changes

## Dependency Map

4A Provider Stabilization       ← Gate 3 complete
4C Bounded Memory Ingestion     ← depends on 4A (needs stable provider for context)
4D Context Intelligence         ← depends on 4C (needs memory infrastructure)
4B Conversational Refinement    ← depends on 4D (needs memory + context before refinement)
4E Operational Refinement       ← depends on 4B (needs all subsystems stable)
4F Future-Gated Integrations    ← depends on 4E (locked — DO NOT TOUCH YET)

## LOCKED (DO NOT TOUCH)

- Gate 3 orchestration pipeline (runtime.py, command_router.py)
- Runtime authority model (execution_boundary.py)
- Deterministic command routing
- All core operators (app, file, browser, system)
- task_engine.py, config.py
- Observers (camera_activation_observer.py)
- kio_bot.py

## Risk Checkpoints

| Sub-Gate | Risk | Pass Criteria |
|----------|------|---------------|
| 4A       | Provider changes destabilize existing 89 tests | All Gate 3 tests pass unchanged |
| 4C       | Memory ingestion creates injection vector | Sanitizer tests pass, no new security issues |
| 4D       | Context leaks degrade isolation | Isolation tests pass unchanged |
| 4B       | Conversational changes leak into execution | All conversational routing tests pass |
| 4E       | Operational changes introduce regressions | Full suite passes |

## RAM Budget Checkpoints

| Point | Budget | Source |
|-------|--------|--------|
| Gate 3 baseline | ~45 MB idle | kio_selftest |
| After 4A | +0 MB | No new persistent objects |
| After 4C | +10 MB | Bounded context store |
| After 4D | +3 MB | Relevance indices |
| After 4B | +2 MB | Expanded response KB |
| After 4E | +1 MB | Diagnostics/logging |
| Total target | < 65 MB | Well under 150 MB ceiling |
