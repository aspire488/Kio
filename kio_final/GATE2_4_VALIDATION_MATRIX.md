# KIO Gate 2.4: Validation Matrix

| Category | Test Case | Expected Result |
| :--- | :--- | :--- |
| **Startup** | Runtime Integrity Check | Process reaches READY in < 3s with all operators registered. |
| **Execution** | Browser Routing Integrity | URL opening returns verified PID or window handle, not just `True`. |
| **Execution** | App Launch Verification | `launch_app` confirms process presence via `psutil` after dispatch. |
| **Regression** | Command Parsing | Complex multi-step strings still parse into valid command lists. |
| **Stability** | Async Loop Integrity | Telegram remains responsive; heavy I/O offloaded to threads (v1.1 §4). |
| **Resource** | Pre-load RAM Guard | `check_capacity` prevents operator load if RAM > HARD_LIMIT. |
| **Integrity** | Process Lifecycle | Closing an app correctly prunes it from the runtime's tracked process list. |
| **RAM** | Memory Ceiling | Cumulative RAM stays below 170MB with browser and file tools active. |
| **Safety** | Graceful Degradation | Missing dependencies (e.g., `cv2`) do not crash the primary command router. |
