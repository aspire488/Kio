# GATE 2 RISK MATRIX: STABILITY PRESERVATION

| Risk Area | Risk Scenario | Impact | Mitigation Strategy |
| :--- | :--- | :--- | :--- |
| **Operator Integrity** | App/Process becomes unresponsive ("Ghosting"). | Medium | Implement PID-based timeouts and process-check verification. |
| **Resource Bloat** | Contextual memory or logs grow unbounded. | High | Enforce strict `deque(maxlen=16)` and rotating log files. |
| **Discovery Failure** | Fuzzy matching maps "delete" to a similar but safe app name. | Critical | Whitelist-only discovery; require high confidence (0.9+) for matches. |
| **LLM Hallucination** | Fallback suggests a destructive command chain. | High | Boundary enforcement remains independent of LLM output; LLM cannot bypass `execution_boundary`. |
| **Regression** | Gate 2 expansion breaks Gate 1 camera/Telegram stability. | Critical | Continuous "Gate 1 Survival Suite" runs before every Gate 2 feature merge. |
| **Concurrency** | Race condition between activation and manual command. | Medium | Runtime single-thread dispatch lock (Centralized execution authority). |
| **Scaling Stress** | Scenario runner (300+) exhausts system handles/memory. | High | Batch-based validation with runtime "Cool-down" periods. |

---

## Risk Tier Definitions

- **CRITICAL:** Total runtime failure, hardware handle leak, or unauthorized destructive action.
- **HIGH:** Significant memory leak (>50MB), failed verification of core actions, or transport crash.
- **MEDIUM:** Unexpected but non-fatal error, minor discovery inaccuracy, or trace missing events.
- **LOW:** Stylistic inconsistencies in logs, minor latency increase (<100ms).

## Rollback Trigger Conditions
1. **RAM > 200MB RSS** consistently during idle.
2. **Any failure** in the "Gate 1 Survival Suite."
3. **More than 3** consecutive "Execution Failures" in a single scenario batch.
4. **Detected zombie process** left by `AppOperator`.
