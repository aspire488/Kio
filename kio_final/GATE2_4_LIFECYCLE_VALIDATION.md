# Lifecycle Validation Criteria

## 1. Process Integrity
- **Registration**: Every `subprocess.Popen` must be registered in the `KioRuntime` tracker.
- **Cleanup**: `prune_tracked_processes()` must terminate orphans on session end or shutdown.

## 2. Runtime State Consistency
- Verify state machine: `INIT -> READY -> ACTIVE -> IDLE -> READY`.
- Ensure `DEGRADED` mode prevents LLM-dependent planning while allowing local READ tools.

## 3. Operator Boundary Tests
- **Timeout**: `asyncio.wait_for` must kill hanging operators at `OPERATION_TIMEOUT` (30s).
- **Isolation**: Operator failure must not stall the `EventBus` dispatch loop.
- **Shutdown**: Final state must be `STOPPED` with 0 active threads/tasks after 5s grace.
