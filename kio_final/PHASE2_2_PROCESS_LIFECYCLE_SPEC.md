# Gate 2 Phase 2.2: PID-Aware Lifecycle Control Specification

## 1. Overview
This specification defines the "PID-Aware Lifecycle Control" for KIO, transitioning process management from image-name-based broad control to specific, tracked process ownership. This ensures KIO only manages processes it initiated and can verify their state deterministically.

## 2. Tracked Process Registry
The registry is the single source of truth for processes owned by the current KIO session.

- **Storage**: `KioRuntime.tracked_processes` (Dictionary or Bounded List).
- **Capacity**: Maximum 16 entries.
- **Eviction Policy**: First-In-First-Out (FIFO) when capacity is reached.
- **Entry Schema**:
    ```python
    {
        "pid": int,           # Captured System PID
        "name": str,          # Canonical app name (e.g., "chrome")
        "target": str,        # Original launch target/argument
        "launched_at": float, # monotonic() timestamp
        "status": str         # "active" | "terminating" | "exited"
    }
    ```

## 3. PID Capture Protocol
Operators MUST attempt to capture the PID of the primary process during launch.

### 3.1 Windows Implementation
1. **Direct Launch**: Use `subprocess.Popen([path])` with `DETACHED_PROCESS` flag.
2. **PID Retrieval**: Capture `.pid` from the `Popen` object.
3. **Verification**: Confirm PID exists in `tasklist` immediately after launch.
4. **Fallback (Legacy/Shell apps)**: If `cmd /c start` is required, use a 1.0s post-launch probe to find the newest process matching the executable name.

### 3.2 Ownership Discipline
- A process is only added to the registry if it was successfully launched by `app_operator.launch_app`.
- KIO will NOT track or kill processes found on the system that it did not launch, unless they match an explicit system-wide whitelist (future phase).

## 4. Lifecycle Operations

### 4.1 Graceful Close Handling
When "close <app>" is requested:
1. **Lookup**: Retrieve PID from registry by canonical name.
2. **Signal**: Issue `taskkill /PID <pid>` (without `/F` for graceful termination).
3. **Wait**: Allow a 1.5s grace period for the process to exit.
4. **Escalation (Optional)**: If the process persists, report failure to the user (do NOT force-kill unless specifically instructed in a later step).

### 4.2 Deterministic Cleanup
To prevent "zombie" entries in the registry (tracking dead processes):
- **Pruning Trigger**: Before every command dispatch (`dispatch_channel_input`).
- **Logic**: Iterate through registry and remove entries where `pid` is no longer alive in the system.

## 5. Verification Probes
Two specialized probes will be registered in `execution_boundary`:
- `launch_verification_probe`: Confirms PID is alive and registry is updated.
- `close_verification_probe`: Confirms PID is dead and registry is cleared.

## 6. Constraints
- **Idle RAM**: Must remain under 150MB. Registry overhead must be negligible (<1KB).
- **Polling**: No background polling loops. All checks are event-driven or piggybacked on commands.
- **Concurrency**: Operations are sequential; no async process management.
