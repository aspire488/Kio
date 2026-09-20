"""Windows process-creation flags for KIO's *internal* helper subprocesses.

Why this module exists
----------------------
KIO itself runs without a console (pythonw.exe / a hidden launcher window).
On Windows, a console-subsystem child started from a console-less parent gets
a brand-new **visible** console window unless ``CREATE_NO_WINDOW`` is passed.
Redirecting stdout/stderr does *not* prevent this, and some flags that look
like they would (e.g. ``CREATE_BREAKAWAY_FROM_JOB`` = 0x00100000,
``DETACHED_PROCESS`` = 0x00000008) do not either — they only change job/console
attachment, not window creation.

Verified empirically on this machine by starting ``cmd.exe`` from
``pythonw.exe`` and enumerating top-level windows:

    no flags                                  -> visible console window
    capture_output=True (piped stdio)         -> visible console window
    creationflags=0x00100000                  -> visible console window
    creationflags=0x08000000                  -> no window

So every helper process KIO spawns (cmd, powershell, tasklist, where, git,
docker, nvidia-smi, ...) must pass these kwargs, otherwise an unexplained
console window appears while KIO is running.

Scope note
----------
This is only for KIO's own internal plumbing.  A *user-requested* visible
action ("open VS Code", "open this folder", "open github.com") is a different
concern and must stay visible: those go through ``os.startfile()`` /
``explorer.exe`` / the app's own GUI subsystem, and must never be routed
through this helper.

Usage
-----
    subprocess.run(cmd, capture_output=True, **no_window())
    subprocess.Popen(cmd, creationflags=CREATE_NO_WINDOW)

On non-Windows platforms ``no_window()`` returns an empty dict, so the same
call sites stay portable.
"""

from __future__ import annotations

import sys

#: Windows ``CreateProcess`` flag: run a console app without a console window.
CREATE_NO_WINDOW = 0x08000000

IS_WINDOWS = sys.platform == "win32"


def no_window(**kwargs: object) -> dict:
    """Return *kwargs* plus ``creationflags=CREATE_NO_WINDOW`` on Windows.

    Existing ``creationflags`` are preserved (OR-ed in), so callers that pass
    their own flags keep them::

        subprocess.Popen(args, **no_window(creationflags=CREATE_BREAKAWAY))
    """
    if IS_WINDOWS:
        existing = int(kwargs.get("creationflags", 0) or 0)
        kwargs["creationflags"] = existing | CREATE_NO_WINDOW
    return kwargs
