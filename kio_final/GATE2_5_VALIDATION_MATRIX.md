# Gate 2.5: Deterministic Validation Matrix

This matrix defines the strict validation rules for each action category.

| Action | Success Criteria (Probe) | Failure Class (If probe fails) | Verification Mode |
| :--- | :--- | :--- | :--- |
| `open_app` | PID exists in `tasklist` and is owned by Kio runtime. | `pid_not_found` | `process_liveness` |
| `close_app` | PID does not exist in `tasklist` after 1.5s grace. | `process_persists` | `process_exit` |
| `search_web` | Result dictionary contains `data` and `success: true`. | `operator_reported_failure` | `boundary_outcome_check` |
| `open_folder` | Explorer process for path is detected (optional/best effort). | `target_not_visible` | `state_delta` |
| `lock_system` | Workstation lock state detected via Win32 API. | `state_unchanged` | `state_delta` |
| `shutdown_system` | Permanent block (Gate 0/1 Policy). | `destructive_blocked` | `policy_enforcement` |
| `restart_system` | Permanent block (Gate 0/1 Policy). | `destructive_blocked` | `policy_enforcement` |
| `play_youtube` | Browser process with specific URL in command line (best effort).| `navigation_failed` | `process_liveness` |

## Verification Status Mapping
- **`passed`**: Probe criteria met.
- **`failed`**: Probe criteria NOT met (Operator reported success but state unchanged).
- **`blocked`**: Policy enforcement prevented execution.
- **`warning`**: Probe inconclusive (e.g. `open_folder` where folder opened but no PID returned).
- **`error`**: Probe exception.
