# Gate 2.5: Execution Governance and Audit Integrity

## 1. Destructive Action Governance
Destructive actions (`destructive_system`) are subject to strict "Gate 0/1 Freeze" policy.

### 1.1 Policy Rules
1. **Freeze Policy**: Actions like `shutdown_system` and `restart_system` are permanently blocked in the `execution_boundary` during current development gates.
2. **Override Mechanism**: Only an explicit `GOVERNANCE_OVERRIDE` environment variable can bypass the freeze.
3. **Verification Requirement**: Any potentially destructive action MUST have a `State Delta` probe that verifies the system state after execution.

## 2. Audit Integrity
The audit trail is the source of truth for all side-effects.

### 2.1 Audit Event Schema
Every execution event recorded by `emit_runtime_trace` must include:
- `execution_id`: Unique GUID.
- `timestamp`: ISO 8601.
- `state_before`: `NORMAL | DEGRADED | ...`.
- `action_requested`: The canonical action name.
- `verification_result`: `passed | failed | blocked`.
- `failure_class`: (If applicable).
- `ram_peak`: From operator telemetry.

### 2.2 Integrity Rules
- **Non-Repudiation**: The runtime must log the `handler` module/function name to prevent "shadow execution".
- **Append-Only**: The `runtime_trace.log` is treated as an append-only stream.
- **Fail-Closed**: If the audit logger fails (e.g. disk full), the `execution_boundary` must transition to `EMERGENCY` state and block further side-effects.

## 3. Blocked Action Discipline
When an action is blocked by policy:
1. It is logged as `outcome_class: BLOCKED`.
2. The `failure_class` is set to `blocked_action` or `policy_violation`.
3. The response to the requester (Core Brain) must clearly state the reason for the block without leaking internal safety thresholds.

## 4. Policy Enforcement Point (PEP)
The `execution_boundary.py` serves as the primary PEP.
- It validates the `OperatorDescriptor` before dispatch.
- It checks the current `Runtime` safety state.
- It executes the `VerificationProbe`.
- It finalizes the `Outcome` classification.
