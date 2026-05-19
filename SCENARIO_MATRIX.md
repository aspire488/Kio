# Gate 1.5 Scenario Matrix

This document defines the structured scenario categories and cases used to validate KIO's behavioral correctness, execution reliability, and runtime integrity.

## Categories Overview

| Category | focus |
|----------|-------|
| `app_control` | App launch and close operations |
| `search_play` | Web search and YouTube playback |
| `multi_step` | Sequenced multi-action command chains |
| `malformed` | Invalid connectors, trailing separators, empty targets |
| `system_control` | Power management and system lock (blocked/allowed) |
| `integrity` | Threshold-based degradation and error recovery |
| `lifecycle` | Activation state transitions and shutdown behavior |
| `folder_access` | Windows folder routing and access |

---

## 1. App Control Scenarios (`app_control`)

| ID | Input | Expected Outcome | Verification |
|----|-------|------------------|--------------|
| APP-01 | `open chrome` | Success | `success: true`, action: `open_app`, target: `chrome` |
| APP-02 | `open notepad` | Success | `success: true`, action: `open_app`, target: `notepad` |
| APP-03 | `close chrome` | Success | `success: true`, action: `close_app`, target: `chrome` |
| APP-04 | `open` | Failure | `success: false`, message: `Empty command` or parse error |
| APP-05 | `open ms edge` | Success | `success: true`, target: `edge` (alias check) |

## 2. Search & Play Scenarios (`search_play`)

| ID | Input | Expected Outcome | Verification |
|----|-------|------------------|--------------|
| SRC-01 | `search python` | Success | `success: true`, action: `search_web`, target: `python` |
| SRC-02 | `play messi` | Success | `success: true`, action: `play_youtube`, target: `messi` |
| SRC-03 | `youtube messi` | Success | `success: true`, action: `play_youtube`, target: `messi` |
| SRC-04 | `search youtube cats` | Success | `success: true`, action: `search_youtube`, target: `cats` |

## 3. Multi-Step Scenarios (`multi_step`)

| ID | Input | Expected Outcome | Verification |
|----|-------|------------------|--------------|
| MST-01 | `open chrome and search python` | Success | `success: true`, 2 steps completed |
| MST-02 | `open chrome then play music` | Success | `success: true`, 2 steps completed |
| MST-03 | `open chrome and search python and close chrome` | Success | `success: true`, 3 steps completed |

## 4. Malformed Command Scenarios (`malformed`)

| ID | Input | Expected Outcome | Verification |
|----|-------|------------------|--------------|
| MAL-01 | `open chrome and` | Failure | `success: false`, message: `Malformed command chain` |
| MAL-02 | `and search python` | Failure | `success: false`, message: `Malformed command chain` |
| MAL-03 | `open chrome and and search python` | Failure | `success: false`, message: `Malformed command chain` |
| MAL-04 | `open chrome search python` | Partial | Check if it parses as single app "chrome search python" |

## 5. System Control Scenarios (`system_control`)

| ID | Input | Expected Outcome | Verification |
|----|-------|------------------|--------------|
| SYS-01 | `lock` | Success | `success: true`, action: `lock_system` |
| SYS-02 | `shutdown` | Blocked | `success: false`, `blocked: true` (Gate 0/1 policy) |
| SYS-03 | `restart` | Blocked | `success: false`, `blocked: true` (Gate 0/1 policy) |

## 6. Folder Access Scenarios (`folder_access`)

| ID | Input | Expected Outcome | Verification |
|----|-------|------------------|--------------|
| FLD-01 | `open downloads folder` | Success | `success: true`, action: `open_folder`, target: `downloads` |
| FLD-02 | `open desktop` | Success | `success: true`, action: `open_folder`, target: `desktop` |
| FLD-03 | `folder music` | Success | `success: true`, action: `open_folder`, target: `music` |

## 7. Integrity & Degradation (`integrity`)

| ID | Input | Expected Outcome | Verification |
|----|-------|------------------|--------------|
| INT-01 | Repeated invalid commands | Degraded | Check `integrity_status` after threshold |
| INT-02 | Channel dispatch failure | Warning | Check `integrity_warnings` |

## 8. Lifecycle (`lifecycle`)

| ID | Input | Expected Outcome | Verification |
|----|-------|------------------|--------------|
| LIF-01 | Command after shutdown | Failure | `success: false`, "Runtime is not accepting input" |
| LIF-02 | Empty command | Failure | `success: false`, "Empty command" |
