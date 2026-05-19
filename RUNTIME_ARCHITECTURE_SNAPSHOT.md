# Runtime Architecture Snapshot

## Scope
This snapshot documents the current stabilized runtime nucleus after Gate 0 work.

Primary modules:

- `C:\Users\HP\OneDrive\Desktop\Kio\kio_fixed_v3\kio_final\mini_kio\core\runtime.py`
- `C:\Users\HP\OneDrive\Desktop\Kio\kio_fixed_v3\kio_final\mini_kio\core\execution_boundary.py`
- `C:\Users\HP\OneDrive\Desktop\Kio\kio_fixed_v3\kio_final\mini_kio\core\command_router.py`
- `C:\Users\HP\OneDrive\Desktop\Kio\kio_fixed_v3\kio_final\mini_kio\core\task_engine.py`
- operator modules under `mini_kio/core`

## Runtime Ownership Map
Current ownership is split intentionally as follows:

- `runtime.py`
  owns boot, lifecycle state, persistent host behavior, runtime context, observer governance, integrity state, and trace emission

- `execution_boundary.py`
  owns side-effect handoff, execution classification, destructive-action blocking, normalized execution results, verification preparation, and failure-to-integrity signaling

- `command_router.py`
  remains an intent/dispatch surface, but no longer owns direct side-effect execution

- `task_engine.py`
  remains a sequential task runner, but no longer owns direct operator execution

- operator modules
  remain low-level side-effect adapters only

## Lifecycle Flow
Current lifecycle flow:

```text
process start
  -> bootstrap_runtime()
  -> ready
  -> idle or running
  -> degraded (if needed)
  -> stopped
```

State semantics:

- `init`
  runtime object exists but bootstrap not complete

- `ready`
  runtime initialized and eligible to host or attach a channel

- `idle`
  persistent host is alive and waiting

- `running`
  channel attached and active

- `degraded`
  runtime detected a meaningful operational failure condition

- `stopped`
  runtime terminated intentionally or after lifecycle end

Transition control is enforced through:

- [transition_to()](<C:\Users\HP\OneDrive\Desktop\Kio\kio_fixed_v3\kio_final\mini_kio\core\runtime.py:95>)

## Execution Flow
Current execution flow:

```text
input
  -> command_router or task_engine
  -> execution_boundary.execute_action()
  -> operator resolution
  -> operator invocation
  -> normalized result
  -> verification classification
  -> runtime trace + integrity/context updates
```

Execution responsibility is centralized in:

- [execute_action()](<C:\Users\HP\OneDrive\Desktop\Kio\kio_fixed_v3\kio_final\mini_kio\core\execution_boundary.py:188>)

Execution result semantics include:

- `success`
- `message`
- `action`
- `target`
- `category`
- `elapsed_ms`
- `handler`
- `verified`
- `verification_status`
- `verification_mode`
- `outcome_class`
- `failure_class`

## Runtime Context Flow
Current runtime-context flow:

```text
runtime event or execution event
  -> remember_runtime_context()
  -> bounded deque storage
  -> optional TTL expiry
  -> snapshot via get_runtime_context_snapshot()
  -> explicit drop via drop_runtime_context()
```

Current context producers:

- lifecycle transitions
- execution outcomes
- observer-state changes
- integrity warnings

Current context characteristics:

- bounded by count
- short-lived by TTL
- explicitly droppable
- runtime-owned
- trace-visible

## Observer Governance Structure
Current observer structure is registry-only.

Observer functions:

- [register_runtime_observer()](<C:\Users\HP\OneDrive\Desktop\Kio\kio_fixed_v3\kio_final\mini_kio\core\runtime.py:351>)
- [set_runtime_observer_enabled()](<C:\Users\HP\OneDrive\Desktop\Kio\kio_fixed_v3\kio_final\mini_kio\core\runtime.py:395>)
- [update_runtime_observer_health()](<C:\Users\HP\OneDrive\Desktop\Kio\kio_fixed_v3\kio_final\mini_kio\core\runtime.py:430>)
- [get_runtime_observer_snapshot()](<C:\Users\HP\OneDrive\Desktop\Kio\kio_fixed_v3\kio_final\mini_kio\core\runtime.py:478>)

Observer record fields:

- `name`
- `source`
- `enabled`
- `health`
- `last_error`
- `last_change_ms`

Observer health states:

- `inactive`
- `ready`
- `degraded`

No observer is started automatically.

## Integrity Structure
Current integrity structure is a bounded ledger.

Integrity components:

- `integrity_status`
- `integrity_counts`
- `integrity_warnings`

Integrity functions:

- [record_runtime_integrity_warning()](<C:\Users\HP\OneDrive\Desktop\Kio\kio_fixed_v3\kio_final\mini_kio\core\runtime.py:217>)
- [get_runtime_integrity_snapshot()](<C:\Users\HP\OneDrive\Desktop\Kio\kio_fixed_v3\kio_final\mini_kio\core\runtime.py:246>)

Current warning categories:

- `execution_failure`
- `invalid_transition`
- `observer_degraded`
- `runtime_degraded`

Degraded escalation is threshold-based and explicit.

## Runtime Trace Structure
Trace ownership remains local and file-based.

Trace sink:

- `C:\Users\HP\OneDrive\Desktop\Kio\kio_fixed_v3\kio_final\mini_kio\debug\runtime_trace.log`

Trace event families currently include:

- runtime bootstrap events
- lifecycle transition events
- host start/stop events
- execution dispatch/result/failure events
- context remember/drop events
- observer registration/state/health events
- integrity warning events

Trace event format:

- JSON payload logged through the standard runtime logger
- lightweight snapshots embedded where useful
- no telemetry backend
- no metrics pipeline

## Module Responsibility Map
`runtime.py`

- runtime bootstrap
- persistent host
- lifecycle state governance
- trace emission
- short-lived runtime context
- observer governance preparation
- integrity preparation
- runtime snapshots

`execution_boundary.py`

- action classification
- handler resolution
- destructive action blocking
- operator invocation
- normalized result shaping
- lightweight verification preparation
- execution-failure integrity signaling

`command_router.py`

- command interpretation
- direct dispatch into execution boundary or task engine

`task_engine.py`

- sequential multi-step task execution
- step-by-step delegation into execution boundary

`app_operator.py`

- app launch
- app close
- web search

`browser_operator.py`

- YouTube/open-browser behavior

`file_operator.py`

- folder open behavior

`system_operator.py`

- system-control side effects

`kio_bot.py`

- disposable prototype channel adapter
- not a runtime owner

## Bottom Line
The current architecture snapshot shows a small runtime nucleus with clear ownership lines:

- runtime owns lifecycle and state
- execution boundary owns side-effect handoff
- router and task engine are no longer side-effect owners
- observers are governed but passive
- integrity is explicit but bounded
- traces are local and readable

This is the correct stabilized base to carry into Gate 1, with the remaining runtime-context expiry defect tracked separately as a hygiene issue rather than an architectural gap.
