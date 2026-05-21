# ResourceGuard Plan: RAM-Aware Orchestration

## 1. Admission Control (Pre-load)
- Before any lazy-load of an operator or observer:
  - `current_rss + module.ram_budget_mb > HARD_LIMIT_MB` -> `RamBudgetError`.
  - Core Brain catches error to initiate replanning without the heavy module.

## 2. Audit Loop (60s Interval)
- **Soft Limit (150MB)**: Trigger `unload_idle()` for all observers.
- **Hard Limit (190MB)**: Trigger `unload_all()`, run `gc.collect()`, and notify user of resource pressure.

## 3. Degradation Behavior
- If RAM cannot be cleared below `HARD_LIMIT_MB`:
  - Enter `DEGRADED` state.
  - Disable non-essential observers.
  - Reject all `proc:spawn` requests.
