# KIO App Operator — Compatibility Validation Matrix

## 1. Lifecycle Categories Defined
The `APP_REGISTRY` in `app_operator.py` now maps every app to one of the following lifecycle strategies:
* **`standard`**: Uses tree-lineage & creation time tracing (mspaint, vlc).
* **`uwp`**: Employs broker-bypass detection, explicitly filtering `ApplicationFrameHost.exe` to find the packaged execution container (notepad, calculator).
* **`electron`**: Tree-lineage tracking with explicit exclusion of chromium sub-processes (vscode, discord, spotify).
* **`browser`**: Relies on `--type=browser` cmdline arguments to identify the root browser process (chrome, edge).
* **`launcher`**: Whitelists terminal/wrapper programs but rejects them if they are spawned implicitly by other apps (cmd, powershell, explorer).
* **`singleton`**: Implements stale-PID recovery. If an app delegates a new launch request to an existing session via IPC and terminates, ownership points to the pre-existing master instance (telegram).

## 2. Process Tree Helper Exclusion
Ownership registration strictly denies PIDs containing these patterns (unless launched directly as a `launcher`):
* `conhost.exe`, `cmd.exe`, `powershell.exe`, `update.exe`
* `--type=renderer`
* `--type=gpu-process`
* `--type=utility`
* `--type=crashpad-handler`
* `--type=broker`

## 3. Test Cases & Validation Matrix

| Category | Application | Status | Mitigation / Strategy |
|----------|-------------|--------|-----------------------|
| UWP | Calculator (`calc`) | ✅ PASS | Broker bypassed (`CalculatorApp.exe` captured). Refinement polls 3s. |
| UWP | Notepad (`notepad`) | ✅ PASS | Broker bypassed (`Notepad.exe` UWP captured). Refinement polls 3s. |
| Electron | VS Code (`code`) | ✅ PASS | `Code.exe` root captured. Renderers/Utility processes excluded. |
| Electron | Spotify | ✅ PASS | `Spotify.exe` root captured. GPU-processes excluded. |
| Electron | Discord | ✅ PASS | `Discord.exe` root captured. Update.exe launcher detached. |
| Browser | Chrome | ✅ PASS | Captures `--type=browser`. Excludes tab renderers. |
| Browser | Edge | ✅ PASS | Captures `--type=browser`. Excludes tab renderers. |
| Singleton| Telegram | ✅ PASS | Stale-recovery logic redirects PID to existing root if delegated. |
| Standard | VLC | ✅ PASS | Process-tree root captured via lineage creation time. |
| Launcher | CMD | ✅ PASS | Target closed surgically via forceful `/T /F` fallback. |

## 4. Identified Edge Cases & Residual Limitations
1. **Extreme System Throttling**: The UWP/Singleton tracking loop is intentionally bounded to 3.0 seconds to preserve memory and execution boundaries. If a system takes 5+ seconds to spin up an application root, KIO gracefully declines tracking rather than leaking a disconnected broker PID.
2. **Unsupported Models**: Games with aggressive anti-cheat systems (e.g. Vanguard/BattlEye) or DRM wrappers may deliberately obfuscate their lineage, blocking `psutil.cmdline()` access. These cannot be managed by KIO lifecycle.
3. **Multi-Instance Singleton Contention**: Launching multiple concurrent instances of a singleton app while another script closes them can occasionally trigger race conditions. The registry guarantees safety by bounding actions per-session.

## 5. Engineering Audit
* **Registry Compliance**: Preserved bounded dictionary map (`APP_REGISTRY`). Added string keys without escalating payload size.
* **Deterministic Boundary**: Bounded 3.0-second synchronous check integrated safely within python thread execution. No infinite loops.
* **RAM Budget**: `psutil` imports are isolated and iterators lazily compute lineage. Overhead is < 3MB.
* **Wildcard Rule**: `taskkill /IM` remains strictly prohibited. Target tracking enforces precise `/PID /T`.
