# Gate 1.5 Scenario Hardening Report

**Generated:** 2026-05-19 11:57:53

## Summary Statistics

- **Total Scenarios:** 15
- **Passed:** 15
- **Failed:** 0
- **Pass Rate:** 100.0%

## Category Breakdown

| Category | Passed | Total | Rate |
|----------|--------|-------|------|
| `app_control` | 3 | 3 | 100.0% |
| `search_play` | 2 | 2 | 100.0% |
| `multi_step` | 1 | 1 | 100.0% |
| `malformed` | 1 | 1 | 100.0% |
| `system_control` | 2 | 2 | 100.0% |
| `folder_access` | 1 | 1 | 100.0% |
| `integrity` | 3 | 3 | 100.0% |
| `lifecycle` | 2 | 2 | 100.0% |

## Detailed Results

| ID | Category | Input | Result | Error / Note |
|----|----------|-------|--------|--------------|
| APP-01 | `app_control` | `open chrome` | ✅ PASS | - |
| APP-03 | `app_control` | `close chrome` | ✅ PASS | - |
| APP-05 | `app_control` | `open ms edge` | ✅ PASS | - |
| SRC-01 | `search_play` | `search python` | ✅ PASS | - |
| SRC-02 | `search_play` | `play messi` | ✅ PASS | - |
| MST-01 | `multi_step` | `open chrome and search python` | ✅ PASS | - |
| MAL-01 | `malformed` | `open chrome and` | ✅ PASS | - |
| SYS-01 | `system_control` | `lock` | ✅ PASS | - |
| SYS-02 | `system_control` | `shutdown` | ✅ PASS | - |
| FLD-01 | `folder_access` | `open downloads folder` | ✅ PASS | - |
| INT-01-F1 | `integrity` | `open fail_me` | ✅ PASS | - |
| INT-01-F2 | `integrity` | `open fail_me` | ✅ PASS | - |
| INT-01-F3 | `integrity` | `open fail_me` | ✅ PASS | - |
| LIF-01 | `lifecycle` | `shutdown` | ✅ PASS | - |
| LIF-02 | `lifecycle` | `  ` | ✅ PASS | - |
