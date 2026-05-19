# PHASE 1 IMPLEMENTATION PLAN: FOUNDATION & DIAGNOSTICS

**Version:** 1.0  
**Phase:** Gate 2.1  
**Scope:** Runtime Hardening & Contextual Awareness  

## 1. Runtime Diagnostics Expansion
*Goal: Enhanced visibility and health monitoring.*

- **Surgical Changes in `mini_kio/core/runtime.py`:**
  - Increase `_RUNTIME_CONTEXT_LIMIT` to 16.
  - Implement `get_runtime_health_score()`:
    - Base score 100.
    - Deduct for integrity warnings (weighted by category).
    - Deduct for observer degradation.
  - Update `get_runtime_snapshot()` to include the health score and refined integrity metrics.
  - Normalize `emit_runtime_trace` to ensure consistent field ordering and types for automated parsing.

## 2. Bounded Contextual Memory
*Goal: Simple anaphora resolution without semantic overhead.*

- **Structural Changes in `mini_kio/core/runtime.py`:**
  - Define `ContextBuffer` wrapper around the existing `context_items` deque.
  - Add `get_last_resolved_target(action_kind)` helper to retrieve the most recent successful target.

- **Routing Changes in `mini_kio/core/command_router.py`:**
  - Implement `_resolve_contextual_references(command)`:
    - Handle "it" -> maps to last successful app/folder target.
    - Handle "that" -> maps to last successful search/play query.
    - Handle "again" -> repeats last successful action.
  - Integrate resolver into `handle_command` BEFORE parser/operator dispatch.

## 3. Verification Groundwork
*Goal: Deterministic post-execution checks.*

- **Changes in `mini_kio/core/execution_boundary.py`:**
  - Introduce `_VERIFICATION_PROBES` (dict of action -> callback).
  - Modify `execute_action()` to:
    - Check for an optional diagnostic probe after operator success.
    - Execute probe with a strict 2-second timeout (non-blocking).
    - Capture probe outcome in the `verified` and `verification_status` fields.
  - Implement a default "Always Pass" probe for Phase 1.

## 4. Resource Discipline
- **Memory Check:** Explicitly call `gc.collect()` during idle loops if RSS delta exceeds 10MB (conservative guard).
- **Trace Size:** Cap individual trace payloads at 1024 bytes.

---
*Signed: KIO Engineering*
