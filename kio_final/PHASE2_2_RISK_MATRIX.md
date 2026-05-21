# Gate 2 Phase 2.2: Risk Matrix - PID-Aware Lifecycle Control

| Risk ID | Risk Description | Severity | Probability | Mitigation Strategy |
| :--- | :--- | :--- | :--- | :--- |
| **R2.2.1** | **PID Reuse**: Process dies and OS reassigns PID to a new unrelated process before KIO prunes it. | Medium | Low | Store `launched_at` timestamp. Future hardening could verify process creation time via `tasklist`. |
| **R2.2.2** | **Launcher Exit**: App (e.g. Chrome) launches a child and the initial process exits immediately. | Low | High | KIO tracks the initial PID. If it exits, pruning removes it. KIO remains stable but tracking is lost for that app. |
| **R2.2.3** | **Permission Denied**: KIO lacks privileges to kill a process it launched (rare on Windows). | Low | Very Low | Report "operator_reported_failure" and mark runtime as "degraded" if integrity thresholds met. |
| **R2.2.4** | **Registry Overflow**: Rapid-fire launches overwhelm the 16-entry limit. | Low | Low | FIFO eviction ensures the most recent (and likely relevant) processes are kept. |
| **R2.2.5** | **Zombie Entries**: Pruning fails or isn't triggered, leading to registry bloat. | Medium | Low | Mandatory pruning before every command dispatch. 16-entry hard limit prevents unbounded bloat. |
| **R2.2.6** | **Graceful Hang**: Process ignores graceful `taskkill` and hangs in "terminating" state. | Medium | Medium | Post-close verification probe detects persistent process and flags it. KIO avoids `/F` to prevent data loss. |
