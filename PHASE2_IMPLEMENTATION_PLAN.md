# PHASE 2 IMPLEMENTATION PLAN: OPERATOR MATURITY

**Version:** 1.0  
**Phase:** Gate 2.2  
**Scope:** Process Awareness & Secure Discovery  

## 1. Runtime Foundation Update
*Goal: Support PID tracking at the runtime level.*

- **Surgical Changes in `mini_kio/core/runtime.py`:**
  - Add `active_pids: dict[str, int]` to `KioRuntime` dataclass.
  - Implement `register_app_pid(app_name: str, pid: int)`:
    - Update `active_pids` map.
    - Emit `runtime_pid_registered` trace.
  - Implement `unregister_app_pid(app_name: str)`:
    - Remove from `active_pids`.
    - Emit `runtime_pid_unregistered` trace.
  - Update `get_runtime_snapshot()` to include `active_pid_count`.

## 2. Deterministic App Discovery (Task 1)
*Goal: Expand and centralize application mapping.*

- **Changes in `mini_kio/core/app_operator.py`:**
  - Expand `APP_REGISTRY` with canonical aliases (e.g., "browser" -> "chrome", "editor" -> "vscode").
  - Implement `_fuzzy_app_discovery(name: str)`:
    - Use a simple string similarity check against files in `Program Files`.
    - Limit depth to `MAX_DISCOVERY_DEPTH=2`.
  - Update `_resolve_path` to use the prioritized discovery sequence defined in `PHASE2_OPERATOR_SPEC.md`.

## 3. PID-Aware Control (Task 2)
*Goal: Verify and manage processes via PIDs.*

- **Changes in `mini_kio/core/app_operator.py`:**
  - Update `_launch_from_info`:
    - After launch, use `_find_pid_by_exe(exe_name)` to capture the new PID.
    - Call `runtime.register_app_pid()`.
  - Update `close_app`:
    - Attempt PID-based termination first using `os.kill(pid, signal.SIGTERM)` or `psutil.terminate()`.
    - Fallback to `taskkill /F /IM` if PID is stale or missing.
    - Call `runtime.unregister_app_pid()` on success.

## 4. Secure File Access (Task 3)
*Goal: Prevent unauthorized directory traversal.*

- **Changes in `mini_kio/core/file_operator.py`:**
  - Implement `_is_path_safe(path: Path) -> bool`:
    - Check against `_BLOCKED_SYSTEM_DIRS` (Windows, System32).
    - Ensure path is within allowed user volumes.
  - Update `open_folder` and `_open_path` to call `_is_path_safe` before execution.
  - Implement strict `Path(p).resolve()` for all input paths.

## 5. Verification Probes (Task 4)
*Goal: Use process state for post-execution confirmation.*

- **Changes in `mini_kio/core/execution_boundary.py`:**
  - Implement `process_existence_probe(normalized_result: dict) -> dict`:
    - Use `psutil` or `tasklist` to verify the target process is running for `open_app`.
    - Verify it is ABSENT for `close_app`.
  - Register these probes in `_VERIFICATION_PROBES`.

---
*Signed: KIO Engineering*
