# PHASE 1 VALIDATION PLAN: NUCLEUS STABILITY

**Goal:** Verify Gate 2 Phase 1 features while ensuring 0% regression of Gate 1 survival metrics.

---

## 1. Functional Validation (New Features)

### 1.1: Contextual Resolution
| Test ID | Sequence | Expected Resolution | Status |
| :--- | :--- | :--- | :--- |
| CON-01 | `open chrome` -> `close it` | `close chrome` | PENDING |
| CON-02 | `search python` -> `search that again` | `search python` | PENDING |
| CON-03 | `open downloads` -> `open it again` | `open downloads` | PENDING |
| CON-04 | `lock` -> `do it again` | `lock` | PENDING |

### 1.2: Health Scoring
| Test ID | Action | Expected Score | Status |
| :--- | :--- | :--- | :--- |
| HLT-01 | Boot | 100 | PENDING |
| HLT-02 | Inject 3 Malformed Commands | < 90 | PENDING |
| HLT-03 | Degrade Camera Observer | < 70 | PENDING |

### 1.3: Verification Probes
| Test ID | Action | Expected Metadata | Status |
| :--- | :--- | :--- | :--- |
| VRF-01 | `open chrome` | `verification_mode: boundary_probe` | PENDING |
| VRF-02 | Probe Timeout | `verification_status: probe_timeout` | PENDING |

## 2. Regression & Stability

### 2.1: Gate 1 Survival Suite
- Run `gate1_survival_harness.py`.
- **Target:** 10/10 PASS.

### 2.2: Scenario Matrix (Gate 1.5)
- Run `scenario_runner.py`.
- **Target:** 100% Pass Rate.

### 2.3: Resource Profile
- **Idle RSS:** < 150MB.
- **Peak RSS:** < 180MB (during stress).
- **Leak Check:** 100 consecutive context-heavy commands.

## 3. Rollback Criteria
- Any failure in the Gate 1 Survival Suite.
- Context buffer exceeding 16 items.
- Diagnostic probe blocking the runtime for > 2 seconds.
