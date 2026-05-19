# PHASE 2 RISK ASSESSMENT: OPERATOR MATURITY

**Goal:** Identify and mitigate risks associated with expanded system control.

---

## 1. Technical Risks

| Risk Area | Scenario | Impact | Mitigation |
| :--- | :--- | :--- | :--- |
| **Process Integrity** | App launches but PID capture fails (e.g., app spawns child and exits). | Medium | Implement secondary "Process Name Search" if direct PID capture fails. |
| **Resource Leak** | `active_pids` grows with stale PIDs if app is closed externally. | Medium | Add a "Garbage Collection" pass to `active_pids` during idle loops (check if PID exists). |
| **Discovery Failure** | Fuzzy matching maps a command to a destructive but similarly named executable. | High | Strict 0.9 confidence threshold; restrict fuzzy search to known safe volumes. |
| **File Safety Bypass** | Complex symbolic link usage to bypass path normalization. | Medium | Use `Path.resolve()` which follows symlinks to the real target. |
| **Regression** | Gate 2 operator changes break Gate 1 Telegram transport. | Critical | Mandatory Gate 1 Survival Suite execution before any Phase 2 merge. |

## 2. Stability Constraints

- **Execution Timeout:** No operator call (including discovery) may exceed 5 seconds.
- **Verification Latency:** Outcome probes must complete within 2 seconds.
- **Memory Ceiling:** Phase 2 must maintain < 150MB RSS during idle.

## 3. Rollback Triggers

1. **Any failure** in the "Gate 1 Survival Suite."
2. **Detection of "Ghost Processes"** (KIO thinks an app is closed but it's still running).
3. **Unexpected File Access:** Any unauthorized access to `C:\Windows` during validation.
4. **Memory Leak:** RSS increases > 10MB after 50 open/close cycles.

---
*Risk profile remains LOW-MEDIUM if mitigation strategies are strictly followed.*
