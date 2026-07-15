# Gate 2.4: Operator Migration Plan (Orchestration Alignment)

## 1. Objective
This document defines the Gate 2.4 migration plan for operators under the locked KIO Architecture v1.1 model. It preserves centralized execution authority, deterministic operator contracts, ResourceGuard discipline, and runtime lifecycle integrity.

## 2. Architecture Principles
- Operators are deterministic executors only. They must not implement decision-making, replanning, verification intelligence, or autonomous behavior.
- Deterministic execution validation belongs to the orchestration/runtime layer. Operators return execution results and telemetry; the runtime layer performs deterministic execution validation and lifecycle enforcement.
- ResourceGuard enforces capacity boundaries and rejects or aborts operators when budget limits are exceeded.
- Centralized execution authority remains intact. Operator dispatch, error handling, and recovery decisions are made outside operator modules.
- Runtime must stay lightweight and RAM-disciplined. Operator contracts must expose resource usage without internal heuristics.

## 3. Operator Contract Rules
- **Stateless execution:** Operators must not persist state across calls.
- **Execution boundary:** Each operator call is wrapped in a hard timeout (e.g. `asyncio.wait_for`) and explicit RAM budget checks.
- **Declared budgets:** Every operator must declare `ram_budget_mb` and `timeout_seconds`.
- **Result-only semantics:** Operators return `success`, `data`, `error`, `telemetry`, and `metadata`. They do not return confidence scores, verification judgments, or replanning instructions.
- **No autonomous logic:** No operator may contain branching that attempts to self-correct, retry, or reassess results beyond a single deterministic execution path.
- **No intelligence fields:** Remove any `confidence_score`, `verification` verdict, or equivalent inference metadata from operator output.

## 4. Phased Migration Order
1. **Phase A - Core I/O tooling:** Migrate filesystem, process control, and system interaction operators first. These provide the foundation for safe execution and lifecycle tracking.
2. **Phase B - Application and process lifecycle:** Migrate application launch/close and process tracking operators with explicit PID/handle metadata.
3. **Phase C - Auxiliary tooling:** Migrate network, browser, and helper operators once the core runtime and ResourceGuard are stable.

## 5. Compatibility and Rollback
- **Dual-dispatch migration compatibility:** Support both legacy operators and Gate 2.4-compliant operators only during the migration window; this is temporary and not a permanent architecture pattern.
- **Rollback trigger:** Any operator or registry failure that breaches runtime stability, exceeding the RAM ceiling or producing malformed results, should trigger a controlled fallback to legacy dispatch and mark the runtime as `DEGRADED`.
- **Integrity check:** New operators must be validated against the `GATE2_4_RESULT_SCHEMA` before being admitted into the execution pipeline.

## 6. Runtime and ResourceGuard Integration
- **ResourceGuard role:** Enforce capacity, monitor telemetry, and abort executions that exceed declared budgets. It must not perform replanning, semantic reasoning, or autonomous verification.
- **Telemetry feed:** Operator telemetry is consumed by runtime for health monitoring and post-execution auditing.
- **Lifecycle safety:** Operators must expose lifecycle metadata such as `pid`, `side_effect`, and `lifecycle` so the runtime can manage process cleanup and drift.

## 7. Execution Boundary Compatibility
- Operators should remain compatible with existing `ExecutionBoundary` semantics.
- Operator outputs must support downstream validation decisions without embedding verification logic.
- The runtime should treat operators as black-box executors and use standardized output fields to enforce orchestration decisions.
