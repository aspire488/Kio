# TESTING PROTOCOL

## Test Framework

Framework:     unittest.IsolatedAsyncioTestCase
Test root:     tests/gate3/
Discovery:     python -m unittest discover -s tests/gate3 -p "*.py" -v
Baseline:      89 tests, ALL MUST PASS

## Regression Checkpoints

Every Gate 4 change MUST pass:

- [R1] Full test suite before any change (baseline: 89/89)
- [R2] Full test suite after change (must still be 89/89)
- [R3] No new lint/type warnings
- [R4] Compile check: all modified files parse cleanly

## Test Addition Rules

- Every new function/method needs a corresponding test
- Every bug fix needs a regression test
- Tests must be deterministic (no network, no real execution)
- Test files go in tests/gate3/ with descriptive test_* names

## Gate 4A Test Requirements

- Provider lifecycle: registration, duplicate detection, health init
- Circuit breaker: threshold, cooldown, recovery, re-registration
- Failover: selection logic when primary provider degraded
- Stress: rapid registration/deregistration, concurrent health checks
