# Gate 2.4 Implementation Phases: Runtime Stabilization

## Phase 1: ResourceGuard Foundation
- Implement `ResourceGuard` with `check_capacity()` pre-load logic.
- Integrate `psutil` for real-time RSS monitoring.
- Establish the `HARD_LIMIT_MB` (190MB) and `SOFT_LIMIT_MB` (150MB) enforcement loops.

## Phase 2: Operator Protocol Migration
- Define `KIOTool` protocol and base DTOs.
- Refactor `app_operator`, `browser_operator`, and `system_operator` into compliant tools.
- Add `ram_budget_mb` and `side_effect_class` to all registered operators.

## Phase 3: Centralized Execution Loop
- Integrate `execution_boundary.py` with `ResourceGuard`.
- Implement mandatory `elapsed_ms` telemetry for every operator call.
- Connect `audit_log.py` to record every dispatch and verification outcome.

## Phase 4: Lifecycle & Integrity Hardening
- Implement `RuntimeState` transition guards (READY -> ACTIVE -> IDLE).
- Add orphan process cleanup in `Runtime.prune_tracked_processes()`.
- Final validation of `DEGRADED` mode recovery paths.
