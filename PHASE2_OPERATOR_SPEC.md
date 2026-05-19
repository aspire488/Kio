# GATE 2 PHASE 2: OPERATOR MATURITY SPECIFICATION

**Version:** 1.0  
**Scope:** Deterministic App Control & Secure File Navigation  

## 1. Managed Application Registry
The `APP_REGISTRY` in `app_operator.py` will be expanded into a structured "Capability Map."

### 1.1 Registry Schema
Each entry in the registry must follow this structure:
```python
"app_id": {
    "exe": "canonical_name.exe",
    "aliases": ["alias1", "alias2"],
    "paths": ["path1", "path2"],
    "dynamic_resolver": "function_name",  # Optional
    "system": bool,                       # True if on system PATH
    "close_method": "taskkill|terminate", # Default: taskkill
}
```

### 1.2 Deterministic Discovery Protocol
Discovery will follow a strict priority sequence to minimize "lucky" launches:
1. **Direct Path:** Check known paths in registry.
2. **Dynamic Resolver:** Execute specialized logic (e.g., globbing Discord versioned folders).
3. **System PATH:** Use `shutil.which` and `where`.
4. **Fuzzy Discovery:** 
   - Scan `C:\Program Files` and `C:\Program Files (x86)` for executable matches.
   - Requirement: Levenshtein distance > 0.9 confidence.
   - *Constraint:* Limited to the first 2 levels of subdirectories to prevent disk thrashing.

## 2. Process-Aware Management
KIO will transition from "fire and forget" to "PID-aware" control.

### 2.1 PID Capture
- **Direct Launch:** When `subprocess.Popen` is used directly on an executable, capture the PID.
- **Shell Launch:** When `cmd /c start` is used, the runtime will immediately poll the process list (via `psutil` or `tasklist`) to find the new process instance and map it to the `app_id`.

### 2.2 Graceful Termination
- **Step 1:** Lookup PID in `runtime.active_pids`.
- **Step 2:** If PID exists and process is alive, attempt `terminate()`.
- **Step 3:** Fallback to `taskkill /IM {exe} /F` if PID is missing or termination fails after 2 seconds.

## 3. Secure File Operator
The `FileOperator` will enforce a "Safe Navigation" policy.

### 3.1 Path Normalization
- All paths must be resolved via `Path(p).resolve()` to prevent directory traversal (`..`).
- Environment variables (`%APPDATA%`) and home shortcuts (`~`) must be expanded before resolution.

### 3.2 Access Guard (Block List)
The following directories are blocked for modification/deletion actions (and flagged for opening):
- `C:\Windows`
- `C:\System32`
- `C:\Users\{User}\AppData\Local\Temp` (Optional: restricted access)
- System root (`C:\`)

## 4. Bounded Verification Hooks
The `ExecutionBoundary` will utilize "Outcome Probes" to confirm system state changes.

| Action | Verification Probe | Success Condition |
| :--- | :--- | :--- |
| `open_app` | `ProcessProbe` | PID found in process list within 3s. |
| `close_app` | `ProcessProbe` | PID/Name absent from process list within 2s. |
| `open_folder` | `PathProbe` | Folder exists and handle is registered (Best effort). |
| `search_web` | `BrowserProbe` | Browser process is active. |

---
*This specification prioritizes system integrity and deterministic behavior over broad autonomy.*
