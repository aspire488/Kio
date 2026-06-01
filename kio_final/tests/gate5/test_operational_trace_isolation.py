"""Verify operational APIs are globally intercepted during tests."""

import os
import sys
import subprocess
import webbrowser
import pytest
from unittest.mock import patch


@pytest.fixture(autouse=True)
def _reset_trace_log():
    from mini_kio.core._operational_monkeypatch import _clear_trace_log
    _clear_trace_log()


def test_webbrowser_open_intercepted():
    result = webbrowser.open("https://example.com")
    assert result is True
    from mini_kio.core._operational_monkeypatch import read_trace_log
    log = read_trace_log()
    assert "webbrowser.open" in log
    assert "https://example.com" in log


def test_subprocess_popen_intercepted():
    proc = subprocess.Popen([sys.executable, "-c", "pass"])
    assert proc.pid == 0
    assert proc.returncode == 0
    from mini_kio.core._operational_monkeypatch import read_trace_log
    log = read_trace_log()
    assert "subprocess.Popen" in log


def test_subprocess_run_intercepted():
    result = subprocess.run([sys.executable, "-c", "pass"])
    assert result.returncode == 0
    from mini_kio.core._operational_monkeypatch import read_trace_log
    log = read_trace_log()
    assert "subprocess.run" in log


def test_os_startfile_intercepted():
    if hasattr(os, "startfile"):
        os.startfile("C:\\Windows\\System32\\notepad.exe")
        from mini_kio.core._operational_monkeypatch import read_trace_log
        log = read_trace_log()
        assert "os.startfile" in log


def test_interception_prevents_real_execution():
    from mini_kio.core._operational_monkeypatch import _original_webbrowser_open
    with patch.object(webbrowser, "open", wraps=webbrowser.open) as traced_spy:
        result = webbrowser.open("https://example.com")
        assert result is True
        traced_spy.assert_called_once_with("https://example.com")


def test_trace_log_contains_caller_info():
    webbrowser.open("https://example.com")
    from mini_kio.core._operational_monkeypatch import read_trace_log
    log = read_trace_log()
    assert "Caller" in log or "Stack" in log or "test_operational_trace_isolation" in log


def test_call_counts_tracked():
    from mini_kio.core._operational_monkeypatch import get_call_counts, _clear_trace_log
    _clear_trace_log()
    counts_before = get_call_counts()["total"]
    webbrowser.open("https://a.com")
    subprocess.Popen(["echo", "test"])
    counts_after = get_call_counts()
    assert counts_after["total"] == counts_before + 2
    assert counts_after["webbrowser.open"] >= 1
    assert counts_after["subprocess.Popen"] >= 1


def test_kio_test_mode_env_set():
    assert os.environ.get("KIO_TEST_MODE") == "1"
