# Gate 2.5: Runtime Safety and Degradation Handling

## 1. Runtime Safety States
Kio operates in one of four deterministic safety states. The state governs which operator categories are permitted.

| State | Permitted Categories | Trigger |
| :--- | :--- | :--- |
| **NORMAL** | ALL (except `destructive_system` in Phase 0) | System startup; successful health check. |
| **DEGRADED** | `external_open`, `external_control`, `read_only` | 3+ consecutive `operator_exception` or `ram_budget_exceeded`. |
| **EMERGENCY** | `system_control` (Lock), `read_only` | Critical ResourceGuard failure or 5+ consecutive execution failures. |
| **LOCKDOWN** | NONE | Security violation or manual operator trigger. |

## 2. State Transition Triggers
Transitions are handled by the `Runtime` core.

- **NORMAL -> DEGRADED**: 
    - ResourceGuard reports RAM usage > 90% of budget for 30s.
    - Operator failure rate > 50% over last 10 executions.
- **DEGRADED -> EMERGENCY**:
    - ResourceGuard critical overflow (RAM > 100MB for the whole process).
    - Failure to execute `system_control` actions.
- **EMERGENCY -> NORMAL**:
    - Successful "Self-Test" execution.
    - Manual reset.

## 3. Degradation Handling Protocols
When in **DEGRADED** state:
1. **Admission Control**: ResourceGuard halves all `ram_budget_mb` limits in operator descriptors.
2. **Execution Throttling**: 500ms mandatory delay between `execute_action` calls.
3. **Verbose Auditing**: Every execution event includes a full `get_runtime_snapshot()`.

## 4. Recovery Boundaries
- **Operator Recovery**: If an operator causes a `DEGRADED` state, it is flagged in the registry and prevented from loading until a system restart or explicit "Clear Flags" command.
- **Process Cleanup**: In `EMERGENCY` state, the runtime attempts to terminate all non-essential tracked processes (tracked via `Runtime.register_tracked_process`).
- **File System Integrity**: No file-system write operations are allowed in `DEGRADED` or lower states unless they are part of the audit trail.

## 5. Audit Integrity
- The audit trail is "Write-Only" during safety transitions.
- Every state transition MUST be logged with `failure_class` and `trigger_event` details.
- Audit logs are synchronized to disk before any `EMERGENCY` state shutdown.
