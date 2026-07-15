# Gate 2 Phase 2.2: Implementation Plan - PID-Aware Lifecycle Control

## Phase 1: Registry Foundation (Runtime)
**Goal**: Establish the storage and management logic for tracked processes.

1.  **Modify `KioRuntime`**:
    *   Add `tracked_processes: list[dict]` to `KioRuntime` dataclass in `mini_kio/core/runtime.py`.
    *   Implement `register_tracked_process(pid: int, name: str, target: str)`:
        *   Handle max 16 entries (pop oldest).
        *   Emit trace: `runtime_process_registered`.
    *   Implement `get_tracked_process(name: str) -> dict | None`:
        *   Search by canonical name.
    *   Implement `prune_tracked_processes()`:
        *   Check `os.kill(pid, 0)` (Unix) or `tasklist` (Windows) to verify liveness.
        *   Remove dead entries.

2.  **Handoff Integration**:
    *   Call `prune_tracked_processes()` inside `dispatch_channel_input` before routing the command.

## Phase 2: PID-Aware Operators (App Operator)
**Goal**: Update launch/close logic to handle specific PIDs.

1.  **Update `launch_app`**:
    *   Modify `_launch_from_info` and `_launch_path` to return the PID.
    *   Switch to direct `subprocess.Popen` where possible to avoid `cmd /c start` PID loss.
2.  **Update `close_app`**:
    *   Accept optional `pid` argument.
    *   If `pid` is present, use `taskkill /PID <pid>`.
    *   Only fall back to `taskkill /IM <process> /F` if no PID is available or target is whitelisted.

## Phase 3: Boundary Orchestration (Execution Boundary)
**Goal**: Link runtime tracking with operator execution.

1.  **Modify `execute_action`**:
    *   **On "open_app" success**: Extract `pid` from result and call `runtime.register_tracked_process`.
    *   **On "close_app" request**:
        *   Look up PID in `runtime`.
        *   Pass PID to `close_app`.
2.  **Implement Verification Probes**:
    *   `_process_liveness_probe(result)`: Confirms PID is active for "open" actions.
    *   `_process_exit_probe(result)`: Confirms PID is gone for "close" actions.
    *   Register probes via `register_verification_probe`.

## Phase 4: Safety & Synchronization
**Goal**: Ensure state consistency and prevent resource leaks.

1.  **Update `KioRuntime.request_shutdown`**:
    *   (Optional for this phase) Attempt graceful close of all tracked processes.
2.  **Trace Hardening**:
    *   Ensure all process lifecycle events (capture, tracking, pruning, exit) are emitted as runtime traces for auditability.
