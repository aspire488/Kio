# PHASE 2 VALIDATION PLAN: OPERATOR MATURITY

**Goal:** Verify deterministic app/file control and process-aware verification.

---

## 1. Functional Validation (Operator Maturity)

### 1.1: PID-Aware Control
| Test ID | Action | Expected Behavior | Status |
| :--- | :--- | :--- | :--- |
| PID-01 | `open notepad` | `active_pids` contains notepad PID. | PENDING |
| PID-02 | `close notepad` | Notepad process terminated; `active_pids` cleared. | PENDING |
| PID-03 | Kill process externally | `ProcessProbe` detects failure in next `close` call. | PENDING |
| PID-04 | Ghost Process | Launch app that closes immediately; `active_pids` remains empty. | PENDING |

### 1.2: App Discovery & Aliases
| Test ID | Command | Expected Registry Match | Status |
| :--- | :--- | :--- | :--- |
| DSC-01 | `open browser` | Maps to `chrome` or `edge`. | PENDING |
| DSC-02 | `open editor` | Maps to `vscode`. | PENDING |
| DSC-03 | `open calc` | Maps to `calculator`. | PENDING |
| DSC-04 | Fuzzy Match | `open chrime` -> `open chrome` (if confidence > 0.9). | PENDING |

### 1.3: Secure File Access
| Test ID | Action | Expected Outcome | Status |
| :--- | :--- | :--- | :--- |
| SAF-01 | `open C:\Windows` | BLOCKED or WARNING (based on policy). | PENDING |
| SAF-02 | `open ..\..\Windows` | BLOCKED (Directory Traversal). | PENDING |
| SAF-03 | `open documents` | SUCCESS (Normalized path). | PENDING |

## 2. Verification Probes (Execution Boundary)

| Test ID | Action | Probe Type | Success Criteria |
| :--- | :--- | :--- | :--- |
| VRF-P1 | `open chrome` | `ProcessProbe` | `verified: True`, `verification_mode: process_probe`. |
| VRF-P2 | `close chrome` | `ProcessProbe` | `verified: True`, process absent from tasklist. |

## 3. Regression & Stress

### 3.1: Gate 1 Survival
- Run `gate1_survival_harness.py`.
- **Target:** 10/10 PASS.

### 3.2: Multi-step Scaling
- Test 3-step chains: `open notepad and open calculator and close notepad`.
- Verify PIDs are tracked/untracked correctly across the chain.

### 3.3: Resource Discipline
- **Memory:** Verify zero leak after 100 app open/close cycles.
- **Handles:** Verify no stale subprocess handles left open.

---
*Success requires 100% pass rate on PID-01, PID-02, and SAF-02.*
