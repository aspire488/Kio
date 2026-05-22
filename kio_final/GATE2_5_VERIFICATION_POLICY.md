# Gate 2.5: Verification Policy and Failure Classification

## 1. Verification Strategy
Verification is the deterministic validation that a side-effect occurred as requested. It is performed by the `execution_boundary` using specialized probes.

### 1.1 Probe Categories
| Category | Mechanism | Example Action |
| :--- | :--- | :--- |
| **Process Liveness** | PID presence/activity check | `open_app` |
| **Process Exit** | PID absence/termination check | `close_app` |
| **State Delta** | Environment/Registry/File change | `lock_system`, `open_folder` |
| **Connectivity** | Socket/Service availability | `search_web` (basic HTTP check) |
| **Null Probe** | Always passes if operator returns success | `execute_capability` (legacy) |

## 2. Outcome Classification Taxonomy
Every execution result MUST be tagged with an `outcome_class`.

| Outcome Class | Definition | Verification Status |
| :--- | :--- | :--- |
| **SUCCESS** | Action performed and verified. | `passed` |
| **PARTIAL** | Action performed but verification inconclusive. | `warning` |
| **FAILURE** | Action failed or verification confirmed failure. | `failed` |
| **BLOCKED** | Action prevented by runtime policy. | `blocked` |
| **ERROR** | Runtime exception during execution/verification. | `error` |

## 3. Failure Classification Discipline
When `success` is false or verification fails, a `failure_class` must be assigned.

### 3.1 Operator-Level Failures
- `operator_timeout`: Operator exceeded its `timeout_seconds`.
- `operator_exception`: Unhandled Python exception in operator code.
- `operator_logic_error`: Operator returned `success: false` with specific reason.
- `invalid_result_schema`: Operator returned data not conforming to Gate 2.4 schema.

### 3.2 Environment-Level Failures
- `dependency_missing`: Required binary or service not found.
- `access_denied`: OS-level permission error.
- `resource_exhausted`: Disk full, memory pressure (non-Kio), etc.

### 3.3 Verification-Level Failures
- `probe_mismatch`: Operator said success, but probe found no change.
- `probe_timeout`: Verification probe exceeded its time budget.
- `probe_error`: Exception during the verification probe itself.

### 3.4 Governance-Level Failures
- `policy_violation`: Action blocked by current safety state.
- `ram_budget_exceeded`: Blocked by ResourceGuard admission.
- `destructive_blocked`: Explicit block of Gate 0/1 restricted actions.

## 4. Verification Rules
1. **Pessimistic Default**: If no probe is defined, `verification_status` is `boundary_check` (Gate 2.4 legacy) -> upgrade to `unverified_success` if operator returns success.
2. **Atomic Verification**: Verification probes must be side-effect free (Read-only).
3. **Grace Periods**: `Process Exit` probes allow up to 1.5s for OS cleanup before declaring failure.
4. **Contextual Integrity**: Verification must use the `target` and `metadata` (e.g. `pid`) from the operator result.
