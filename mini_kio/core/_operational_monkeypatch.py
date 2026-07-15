"""
Global operational API interceptor for test-mode execution tracing.
Monkeypatches webbrowser.open, subprocess.Popen/run, os.startfile
to log call origins and return safe no-op results.
"""

import io
import os
import sys
import time
import traceback

TRACE_LOG = os.environ.get("KIO_EXECUTION_TRACE", "kio_execution_trace.log")

_original_webbrowser_open = None
_original_subprocess_popen = None
_original_subprocess_run = None
_original_os_startfile = None
_installed = False
_call_counter = {"total": 0, "webbrowser.open": 0, "subprocess.Popen": 0, "subprocess.run": 0, "os.startfile": 0}


def _clear_trace_log():
    with open(TRACE_LOG, "w", encoding="utf-8") as f:
        f.write("")


def _write_trace(api, args, kwargs, stack):
    _call_counter["total"] += 1
    _call_counter[api] = _call_counter.get(api, 0) + 1
    with open(TRACE_LOG, "a", encoding="utf-8") as f:
        f.write(f"[{time.strftime('%Y-%m-%d %H:%M:%S')}]\n")
        f.write(f"API: {api}\n")
        f.write(f"Args: {args}\n")
        f.write(f"Stack:\n{stack}\n")
        f.write("\n")


def _get_stack_summary():
    stack = traceback.extract_stack()
    lines = []
    for frame in stack:
        if "_operational_monkeypatch" in frame.filename:
            continue
        short = os.path.relpath(frame.filename, os.path.dirname(os.path.dirname(os.path.dirname(__file__))))
        lines.append(f"  {short}:{frame.lineno} in {frame.name}")
        if len(lines) >= 10:
            break
    return "\n".join(lines)


class _MockCompletedProcess:
    def __init__(self, args):
        self.args = args
        self.returncode = 0
        self.stdout = ""
        self.stderr = ""
    def check_returncode(self):
        pass


class _MockPopen:
    def __init__(self, *args, **kwargs):
        self.args = args
        self.pid = 0
        self.returncode = 0
        self.stdout = io.StringIO("")
        self.stderr = io.StringIO("")
    def poll(self):
        return 0
    def wait(self, timeout=None):
        return 0
    def communicate(self, input=None, timeout=None):
        return ("", "")
    def __enter__(self):
        return self
    def __exit__(self, *a):
        pass


def _traced_webbrowser_open(url, new=0, autoraise=True):
    stack = _get_stack_summary()
    _write_trace("webbrowser.open", (url, new, autoraise), {}, stack)
    return True


def _traced_subprocess_popen(*args, **kwargs):
    stack = _get_stack_summary()
    _write_trace("subprocess.Popen", args, kwargs, stack)
    return _MockPopen(*args, **kwargs)


def _traced_subprocess_run(*args, **kwargs):
    stack = _get_stack_summary()
    _write_trace("subprocess.run", args, kwargs, stack)
    return _MockCompletedProcess(args[0] if args else [])


def _traced_os_startfile(path, operation="open"):
    stack = _get_stack_summary()
    _write_trace("os.startfile", (path, operation), {}, stack)


def install_monkeypatches():
    global _original_webbrowser_open, _original_subprocess_popen
    global _original_subprocess_run, _original_os_startfile, _installed
    import webbrowser
    import subprocess

    if _installed:
        return

    _clear_trace_log()

    _original_webbrowser_open = webbrowser.open
    webbrowser.open = _traced_webbrowser_open

    _original_subprocess_popen = subprocess.Popen
    subprocess.Popen = _traced_subprocess_popen

    _original_subprocess_run = subprocess.run
    subprocess.run = _traced_subprocess_run

    if hasattr(os, "startfile"):
        _original_os_startfile = os.startfile
        os.startfile = _traced_os_startfile

    _installed = True


def uninstall_monkeypatches():
    global _installed
    import webbrowser
    import subprocess

    if _original_webbrowser_open is not None:
        webbrowser.open = _original_webbrowser_open
    if _original_subprocess_popen is not None:
        subprocess.Popen = _original_subprocess_popen
    if _original_subprocess_run is not None:
        subprocess.run = _original_subprocess_run
    if _original_os_startfile is not None:
        os.startfile = _original_os_startfile

    _installed = False


def get_call_counts():
    return dict(_call_counter)


def read_trace_log():
    try:
        with open(TRACE_LOG, "r", encoding="utf-8") as f:
            return f.read()
    except FileNotFoundError:
        return ""
