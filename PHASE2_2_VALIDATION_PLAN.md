# Gate 2 Phase 2.2: Validation Plan - PID-Aware Lifecycle Control

## 1. Unit & Integration Tests

### T2.2.1: PID Capture Accuracy
- **Scenario**: Launch "Notepad".
- **Expectation**: Operator returns a valid PID. Registry contains exactly 1 entry for "notepad" with that PID.
- **Verification**: Cross-reference PID with `tasklist`.

### T2.2.2: Registry Bounding (Capacity Limit)
- **Scenario**: Launch 17 different applications (or dummy processes if mocked).
- **Expectation**: Registry size remains at 16. The first application launched is evicted.
- **Verification**: Inspect `get_runtime_snapshot()` or registry state.

### T2.2.3: Ownership Discipline (Selective Close)
- **Scenario**: 
    1. Manually open one Notepad instance.
    2. Tell KIO to "open notepad".
    3. Tell KIO to "close notepad".
- **Expectation**: ONLY the Notepad instance launched by KIO is closed. The manual one remains open.
- **Verification**: Visual check and `tasklist` count.

### T2.2.4: Deterministic Pruning (Stale Cleanup)
- **Scenario**:
    1. Tell KIO to "open notepad".
    2. Manually close the Notepad window.
    3. Send "ping" to KIO.
- **Expectation**: Registry entry for Notepad is removed during the "ping" dispatch (pruning phase).
- **Verification**: Trace `runtime_process_pruned` should appear.

## 2. Robustness & Stability

### T2.2.5: Graceful Termination Verification
- **Scenario**: Close a process that has unsaved changes (e.g., Notepad with text).
- **Expectation**: `taskkill` (graceful) is issued. Process might stay alive (waiting for user). KIO should report success of the *command* but the *verification probe* should reflect actual state.
- **Verification**: Check `verification_status` in execution result.

### T2.2.6: Resource Integrity
- **Scenario**: Run KIO for 1 hour, opening and closing apps repeatedly.
- **Expectation**: Idle RAM remains <150MB. No "zombie" entries in `runtime_trace.log`.
- **Verification**: Monitor `health_score` and memory usage.

## 3. Success Criteria
1.  All KIO-launched apps are tracked by PID.
2.  "Close" commands prioritize PID over image name.
3.  Registry never exceeds 16 entries.
4.  Registry accurately reflects system state after any interaction.
