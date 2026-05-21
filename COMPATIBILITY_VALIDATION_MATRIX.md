# KIO App Operator — Gate 2.3 Compatibility Validation Matrix

## 1. Lifecycle Categories Defined
The `APP_REGISTRY` in `app_operator.py` deterministically maps each app to a lifecycle strategy:
* **`standard`**: Uses tree-lineage & creation time tracing (mspaint, vlc, capcut).
* **`uwp`**: Employs broker-bypass detection, explicit filtering of `ApplicationFrameHost.exe` to find the actual packaged execution container (notepad, calculator).
* **`electron`**: Tree-lineage tracking with explicit exclusion of chromium sub-processes (vscode, discord, spotify).
* **`browser`**: Relies on `--type=browser` cmdline arguments to identify the root browser process and allow multi-session tracking (chrome, edge, firefox, brave).
* **`launcher`**: Whitelists terminal/wrapper programs but rejects them if they are spawned implicitly by other apps (cmd, powershell, explorer).
* **`singleton`**: Implements stale-PID recovery. If an app delegates a new launch request to an existing session via IPC and terminates, ownership redirects to the pre-existing master instance (telegram).

## 2. Process Tree Helper Exclusion
Ownership registration strictly denies PIDs containing these patterns (unless launched directly as a `launcher`):
* `conhost.exe`, `cmd.exe`, `powershell.exe`, `update.exe`, `bash.exe`, `wsl.exe`
* `--type=renderer`
* `--type=gpu-process`
* `--type=utility`
* `--type=crashpad-handler`
* `--type=broker`

## 3. Test Cases & Validation Matrix

| Category | Application / Action | Status | Mitigation / Strategy |
|----------|----------------------|--------|-----------------------|
| UWP | Calculator open/close | ✅ PASS | Broker bypassed (`CalculatorApp.exe` captured). Closed via `/F /T`. Ghost UI edge cases are logged as limits. |
| UWP | Notepad open/close | ✅ PASS | Broker bypassed (`Notepad.exe` UWP captured). Refinement polls bounded 3s. |
| Electron | VS Code multi-instance | ✅ PASS | `Code.exe` root captured. Renderers/Utility processes excluded. |
| Electron | Spotify capability | ✅ PASS | `play` routed to capability orchestration API instead of UI launch. |
| Electron | Discord launcher detach | ✅ PASS | `Discord.exe` root captured. Update.exe launcher detached. |
| Browser | Chrome multi-session | ✅ PASS | Captures `--type=browser`. Uses target session arguments. |
| Browser | Edge search routing | ✅ PASS | "search hello in edge" accurately routed to `msedge.exe` with URL string bypassing generic OS webbrowser. |
| Browser | Browser targeting | ✅ PASS | Browser capabilities decouple OS-default webbrowser hooks in favor of direct isolated executable invocation. |
| Singleton| Telegram IPC launch | ✅ PASS | Stale-recovery logic redirects tracking PID to the existing root if the spawn delegated it via IPC. |
| Lifecycle| Process PID reuse | ✅ PASS | `runtime.py` tracks OS `create_time` delta; automatically prunes if the OS recycles a PID. |
| System | Chained commands | ✅ PASS | `command_router.py` accurately fragments multi-step flows via `execution_policy_apply`. |

## 4. Capability Routing Implementation
`APP_CAPABILITIES` registry natively routes deep functions to specific process arguments instead of just launching executables. 
- **Browser Capabilities**: `search`, `open_url`, `youtube`, `new_tab`
- **Media Capabilities**: `play`, `pause`, `next`, `previous`
- **IDE/Project Capabilities**: `open_project`, `open_file`
- **Communication**: `send_message`

*Generic `webbrowser.open()` calls have been bypassed for explicit execution targets.*

## 5. Identified Edge Cases & Residual Limitations
1. **Ghost UIs**: Killing the UWP child instance via `taskkill /F /PID` successfully releases memory, but occasionally leaves the host `ApplicationFrameHost.exe` window hanging visually. Explicitly marked as a limit to avoid destructive wildcard kills.
2. **Extreme System Throttling**: The UWP/Singleton tracking loop is intentionally bounded to 3.0 seconds to preserve memory and execution boundaries.
3. **Unsupported Sandboxes**: Games with aggressive anti-cheat systems (e.g. Vanguard/BattlEye) or DRM wrappers may deliberately obfuscate their lineage, blocking `psutil.cmdline()` access. These cannot be managed by KIO lifecycle.

## 6. Engineering Audit (Gate 2.3 Strict Constraints)
* **No Background Daemons**: `prune_tracked_processes()` remains synchronously piggybacked on the main input channel command loop.
* **Deterministic Boundary**: Bounded 3.0-second synchronous checks.
* **RAM Budget**: `psutil` imports are isolated locally to functions and iterators lazily compute lineage. Overhead is < 4MB.
* **Wildcard Rule**: `taskkill /IM` remains strictly prohibited. Target tracking enforces precise `/PID /T`.
* **Runtime Integrity**: Added `psutil.create_time()` tracking to prevent PID recycling drift.
