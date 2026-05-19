# GATE 2 OPERATOR EXPANSION: MATURITY SPEC

**Goal:** Move from hard-coded "lucky" operators to deterministic, process-aware system interactors.

---

## 1. AppOperator Expansion
The AppOperator will transition from a simple `os.startfile` wrapper to a managed process controller.

- **Dynamic Discovery:** Search for executable paths in standard Windows locations (Program Files, AppData) based on a persistent `AliasRegistry`.
- **PID Awareness:** Capture and store the Process ID (PID) of launched applications.
- **Verification Hook:** `is_process_running(pid)` or `find_process_by_name(name)` used as a post-exec check.
- **Graceful Termination:** Use `taskkill` or `process.terminate()` with verification of cleanup.

## 2. FileOperator Expansion
Improving safety and reach for file-system interactions.

- **Path Normalization:** Strict resolution of `%USERPROFILE%`, `%APPDATA%`, etc.
- **Access Guard:** Block access to sensitive system directories (Windows, System32) at the operator level.
- **Lightweight Search:** Non-indexed "Top-level Search" for files within whitelisted folders (Downloads, Desktop).
- **File Context:** Remember the "Last Accessed File" in the runtime context.

## 3. SystemOperator Expansion
Controlled unlocking of power management and diagnostic tools.

- **New Actions (Allowed):**
  - `lock_system` (Preserved)
  - `restart_computer` (Added with verification)
  - `sleep_computer` (Added with verification)
- **Restricted Actions (Still Blocked):**
  - `shutdown` (Requires Expert Mode / Admin override)
- **Diagnostics:**
  - `get_system_stats` (CPU/RAM usage for runtime telemetry)
  - `check_internet_connectivity`

## 4. BrowserOperator Expansion
Moving beyond simple URL launching.

- **Query Normalization:** Improved parsing of search terms.
- **Browser Targeting:** Ability to specify browser (Chrome vs. Edge) if multiple are installed.
- **YouTube Protocol:** Bounded interaction for playlist start vs. single video play.

---

## Operator Integrity Constraints
1. **Timeout Enforcement:** No operator call may block for > 5 seconds.
2. **Return Shape:** All operators MUST return `{"success": bool, "message": str, ...}`.
3. **Side-Effect Only:** Operators must not maintain internal state; all state belongs to the Runtime Nucleus.
4. **Zero-UI Dependency:** Operators must not rely on screen-scraping or GUI automation (OCR/Coordinates) in Gate 2.
