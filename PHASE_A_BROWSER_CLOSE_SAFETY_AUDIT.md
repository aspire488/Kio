# PHASE A — BROWSER CLOSE SAFETY AUDIT

## 1. What happens now when user says: "Close youtube", "Close chatgpt", "Close notion"

When a user issues a command like "Close youtube", "Close chatgpt", or "Close notion", the KIO system will attempt to close the associated browser instance. The execution path is as follows:

*   **`mini_kio/core/app_operator.py` `close_app()`**: This function is the primary entry point for closing applications.
*   **`mini_kio/core/routing_utils.py` `resolve_capability_for_close(key)`**: `close_app` first calls this function to determine if the target (e.g., "youtube") corresponds to an active, KIO-managed browser capability. This function resolves the capability entry, including the `browser_pid` and, if previously used, the `temp_profile_dir`.
*   **`mini_kio/core/routing_utils.py` `close_browser_capability(cap_info)`**: If an active capability is found, `close_app` invokes `close_browser_capability`.
    *   This function retrieves the `browser_pid` associated with the capability.
    *   **Code Evidence**:
        ```python
        # From mini_kio/core/routing_utils.py, close_browser_capability function
        # ...
        logger.info("[CAPABILITY] Closing browser capability '%s' (pid %s)", target, browser_pid)
        proc = subprocess.run(
            ["taskkill", "/T", "/F", "/PID", str(browser_pid)],
            capture_output=True, text=True, timeout=10,
        )
        # ...
        ```
    *   It executes a `taskkill` command targeting the retrieved `browser_pid` with `/T` (tree kill) and `/F` (force kill) flags.
    *   It then calls `_cleanup_browser_profile(temp_profile_dir)`.

*   **`mini_kio/core/routing_utils.py` `deactivate_capability(target)`**: After attempting to close the browser process, `close_app` calls `deactivate_capability` to mark the capability as inactive in KIO's internal registry.
*   **`mini_kio/core/routing_utils.py` `_cleanup_browser_profile(temp_profile_dir)`**: This function is called by `close_browser_capability`.
    *   **Code Evidence**:
        ```python
        # From mini_kio/core/routing_utils.py, _cleanup_browser_profile function
        def _cleanup_browser_profile(temp_profile_dir: Optional[str]) -> None:
            """Remove a KIO browser temp profile directory."""
            if temp_profile_dir and os.path.isdir(temp_profile_dir):
                try:
                    shutil.rmtree(temp_profile_dir, ignore_errors=True)
                    logger.info("[CAPABILITY] Cleaned up browser profile: %s", temp_profile_dir)
                except Exception as exc:
                    logger.warning("[CAPABILITY] Failed to clean up profile %s: %s", temp_profile_dir, exc)
        ```
    *   Since `temp_profile_dir` is now `None` (as temporary profiles are no longer created), this function will execute but will not find any directory to remove, effectively doing nothing.

## 2. Does KIO: kill chrome.exe, kill a tracked PID, deactivate capability only, return false success, affect the user's entire browser

*   **Kills chrome.exe**: Yes, it attempts to kill the `chrome.exe` process identified by the `browser_pid`.
*   **Kills a tracked PID**: Yes, it uses the `browser_pid` that was captured and stored when KIO initially launched the URL.
*   **Deactivate capability only**: No, it performs process termination *in addition* to deactivating the capability in its internal registry.
*   **Return false success**: It returns success if the `taskkill` command returns successfully and process verification passes, regardless of the broader impact.
*   **Affect the user's entire browser**: **YES, critically.** After the removal of `--user-data-dir` and `--new-window`, KIO-initiated browser actions (e.g., opening YouTube) now occur within the user's existing, primary Chrome instance. Consequently, the `browser_pid` tracked by KIO for such capabilities is the PID of the user's entire running Chrome application. Executing `taskkill /T /F /PID {browser_pid}` will terminate the entire Chrome process, closing all open tabs and windows, including those not opened by KIO.

## 3. Can KIO still distinguish: user-opened Chrome tabs, KIO-opened tabs

**No, KIO cannot distinguish between user-opened Chrome tabs and KIO-opened tabs within the same browser instance.**

*   **Code Evidence**: The `register_browser_capability` function in `mini_kio/core/routing_utils.py` only stores a single `browser_pid` for a given capability.
    ```python
    # From mini_kio/core/routing_utils.py, register_browser_capability function
    def register_browser_capability(canonical_target: str, browser: str, url: str, browser_pid: Optional[int] = None, temp_profile_dir: Optional[str] = None) -> str:
        """Register a browser capability session after successful launch."""
        cap_reg = get_capability_registry()
        return cap_reg.register(canonical_target, browser, url, browser_pid=browser_pid, temp_profile_dir=temp_profile_dir)
    ```
    The `browser_pid` refers to the overall Chrome process, not a specific tab or window within it. With the removal of isolated profiles, KIO has no mechanism to differentiate between various tabs or windows within that single browser process. Its internal tracking only knows that a particular URL was opened by a Chrome process with a given PID.

## 4. Is browser-close functionality now unsafe after removal of isolated profiles?

**YES, the browser-close functionality is now unsafe.**

The core assumption underlying `close_browser_capability` in `routing_utils.py` was that: "Each KIO browser capability is launched in a separate Chrome instance... so killing its PID only closes that instance without affecting unrelated user tabs." This assumption is no longer valid.

Killing the tracked `browser_pid` will now result in the termination of the entire user's Chrome application, causing loss of unsaved work or interruption of browsing. This is a severe safety regression.

## 5. If unsafe: identify exact files/functions and propose minimal Gate 5 stabilization fix (do not patch).

**Exact Files/Functions:**

*   `mini_kio/core/app_operator.py`: The `close_app` function (specifically the call to `close_browser_capability`).
*   `mini_kio/core/routing_utils.py`: The `close_browser_capability` function (specifically the `subprocess.run(["taskkill", ...])` call).

**Proposed Minimal Gate 5 Stabilization Fix:**

Given the "no new features" constraint, introducing complex user prompts (e.g., "Are you sure you want to close your entire browser?") is out of scope. The safest and most architecturally aligned fix is to disable the process-killing aspect of `close_browser_capability` when it's not dealing with an isolated, KIO-controlled browser instance.

**Proposal:** Modify the `close_browser_capability` function in `mini_kio/core/routing_utils.py` to check if `temp_profile_dir` is `None` (or empty). If it is, KIO should *not* attempt to `taskkill` the `browser_pid`. Instead, it should log a warning, deactivate the capability internally, and return `False` (indicating it could not safely close the browser process).

*   **Rationale**: This approach prevents KIO from inadvertently terminating the user's entire browser while still allowing it to manage its internal state (deactivating the capability). It prioritizes user data safety over maintaining the old "close capability" behavior in a context where that behavior has become dangerous.

*   **Implementation Sketch (Conceptual - NOT a patch)**:
    ```python
    # In mini_kio/core/routing_utils.py -> close_browser_capability function
    def close_browser_capability(cap_info: dict) -> bool:
        browser_pid = cap_info.get("browser_pid")
        target = cap_info.get("canonical_target", "unknown")
        temp_profile_dir = cap_info.get("temp_profile_dir") # This will be None now

        if temp_profile_dir: # Only attempt to kill if it was an isolated profile
            # ... (existing taskkill logic) ...
            return True # or False based on taskkill success
        else:
            logger.warning(f"[CAPABILITY] Refusing to close browser PID {browser_pid} for '{target}' "
                           f"as it is not an isolated KIO instance. Killing it would terminate the user's entire browser.")
            # We still deactivate the capability in app_operator.py's caller, but here we prevent the kill.
            return False
    ```
    This conceptual change in `close_browser_capability` would mean the function would return `False` if `temp_profile_dir` is `None`, which would then be handled by `close_app` in `app_operator.py` to return an appropriate message like "Failed to close the X session. The browser process is still running." This accurately reflects the new safety measure.