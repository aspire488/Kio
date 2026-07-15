# Gate 2.5: Phased Implementation Plan

## Phase 1: Classification Hardening
- **Task 1.1**: Update `operator_protocol.py` to include `OutcomeClass` and `FailureClass` enums.
- **Task 1.2**: Refactor `execution_boundary.py` to use the new taxonomy in `_apply_verification`.
- **Task 1.3**: Extend `_normalize_result` to ensure Gate 2.4 schema compliance is strictly enforced.

## Phase 2: Verification Probe Expansion
- **Task 2.1**: Implement `_system_lock_probe` using Win32 API.
- **Task 2.2**: Implement `_connectivity_probe` for web-based actions.
- **Task 2.3**: Update `STATIC_ACTION_TABLE` to link actions to expanded probes.

## Phase 3: Runtime Safety State Machine
- **Task 3.1**: Implement `SafetyState` management in `mini_kio/core/runtime.py`.
- **Task 3.2**: Add `check_safety_policy` to `execution_boundary.py` before operator dispatch.
- **Task 3.3**: Implement state transition logic based on execution failure counters.

## Phase 4: Audit Hardening
- **Task 4.1**: Update `emit_runtime_trace` to include mandatory policy and verification fields.
- **Task 4.2**: Implement "Fail-Closed" logic in `execution_boundary` if audit logging fails.

## Lightweight Implementation Constraints
- **Zero Framework Dependency**: Use only standard library and existing Win32 bindings.
- **RAM Cap**: Verification logic must not increase baseline RAM usage by more than **2MB**.
- **No Async Complexity**: Verification probes should be synchronous and fast (<2s) to avoid orchestration overhead.

## Rollback Strategy
- **Atomic Commits**: Each phase must be committed separately.
- **Feature Flag**: Implementation of `SafetyState` transitions should be toggleable via environment variable (`KIO_SAFETY_ENFORCED=0`).
- **Snapshot Preservation**: Gate 2.4 codebase state is preserved in `snapshots/gate2_4_final`.

## RAM Discipline Expectations
- Runtime baseline: 63-67MB.
- Gate 2.5 Target: **<70MB** total resident memory during peak verification.
- Probes must explicitly `del` large intermediate objects and avoid global state caching.
