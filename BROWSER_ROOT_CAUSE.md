# BROWSER_ROOT_CAUSE.md

## Root Cause: Browser launches wrong Chrome instance

The root cause of KIO launching separate Chrome instances instead of new tabs in the user's existing primary Chrome profile was the explicit use of `--user-data-dir` with a temporary directory and the `--new-window` command-line argument when launching Chrome. This behavior was present in two key functions within `mini_kio/core/app_operator.py`:

1.  **`execute_capability` function**: When handling browser-related capabilities (e.g., `open_url`, `search`), KIO constructed a `chrome_args` list that included `f"--user-data-dir={temp_profile_dir}"` and `"--new-window"`. This forced Chrome to open a new, isolated browser session in a new window.
2.  **`_launch_from_info` function**: This internal helper, responsible for launching applications based on registry information, also conditionally added `"--user-data-dir=" + temp_profile_dir` and `"--new-window"` when launching `chrome.exe`.

These arguments override Chrome's default behavior, preventing it from utilizing an already running instance or the user's default profile.

## Affected Files

*   `mini_kio/core/app_operator.py`

## Fix Applied

The fix involved modifying `mini_kio/core/app_operator.py` to remove the problematic arguments and associated logic:

1.  **Removal of `temp_profile_dir` creation and usage**: The logic to create temporary Chrome profiles and the `temp_profile_dir` variable itself were removed from both `execute_capability` and `_launch_from_info`.
2.  **Removal of `--user-data-dir` argument**: The argument `f"--user-data-dir={temp_profile_dir}"` was removed from the `chrome_args` list in `execute_capability`.
3.  **Removal of `--new-window` argument**: The argument `"--new-window"` was removed from the `chrome_args` list in both `execute_capability` and `_launch_from_info`.
4.  **Cleanup of orphaned code**: The global dictionary `CHROME_TEMP_PROFILE_DIRS` and the `_cleanup_chrome_temp_profile` function, which were solely related to managing temporary profiles, were removed. The `tempfile` import, no longer necessary, was also removed.

These changes ensure that when KIO instructs Chrome to open a URL, it will now defer to Chrome's default behavior, which is to open the URL in a new tab within an already running browser instance (if available) using the user's primary profile.

## Remaining Limitations

*   **PID Tracking Precision**: While the `_refine_pid_windows` function attempts to track the "real" PID of the launched browser process, the absence of dedicated, KIO-managed browser profiles means that accurately associating a specific tab or window with a KIO-initiated action might be less precise. KIO now relies on the OS and the browser's internal handling of new tabs/windows. This means KIO cannot definitively "own" a specific browser tab in the same way it could a dedicated process launched with a unique profile.
*   **Destructive Browser Closing Behavior**: The problem description explicitly requested to "avoid destructive browser closing behavior." Since KIO no longer manages separate browser instances for each action, any `close_app` command directed at a browser (e.g., "close chrome") will attempt to close the *entire* Chrome application, potentially closing all user-opened tabs and windows. KIO cannot selectively close only the tabs it opened without deeper browser integration (which is outside the scope of "no new features"). This behavior is now consistent with how `close_app` handles other singleton applications.
*   **External Browser Behavior**: KIO's ability to open URLs in new tabs versus new windows in an existing session is now entirely dependent on the default behavior of the user's configured browser (e.g., Chrome) and its internal settings for handling external URL launches. KIO explicitly removes the `--new-window` argument, trusting the browser to open in a new tab if an existing window is present.

This concludes the work for Issue 1.