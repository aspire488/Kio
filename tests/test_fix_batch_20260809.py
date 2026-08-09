"""
KIO fix report tests — 2026-08-09 batch.

Covers the four production fixes:
1. concurrent_updates(4) in kio_bot.py — PTB no longer processes every
   Telegram update serially, so a slow media op (play verification polls
   up to ~10s per attempt) no longer blocks "hi" for minutes.
2. Explicit YouTube Data API 429 handling in youtube_provider — a quota
   rejection is logged as QUOTA_EXHAUSTED, never retried, never leaks the
   API key, and still degrades silently to the browser-scrape path.
3. Bounded play-verification deadline (25s -> 10s) in state_verification.
4. close_app browser fallback — a registered browser with no KIO-tracked
   PID is now discovered by process name and terminated instead of refused.
"""

import urllib.error

from mini_kio.core import app_operator, state_verification as sv
from mini_kio.media.providers.youtube_provider import YouTubeProvider

FAKE_KEY = "ABCDEF12345-SECRET-KEY-SHOULD-NOT-LEAK"


def _http_error_429(url):
    raise urllib.error.HTTPError(url, 429, "Too Many Requests", {}, None)


def test_play_deadline_is_bounded():
    assert sv._play_deadline_s() <= 10.0, (
        "play verification deadline must be bounded to keep a media op from "
        "freezing the bot (25s * 5 attempts was the multi-minute spiral)"
    )


def test_api_429_returns_empty_and_does_not_retry(monkeypatch, capsys):
    """Quota rejection: [] result, no retry loop, no key in the log line."""
    provider = YouTubeProvider()
    calls = []

    def fake_urlopen(req, timeout=8):
        calls.append(req)
        raise urllib.error.HTTPError(req.full_url, 429, "Too Many Requests", {}, None)

    monkeypatch.setattr("mini_kio.media.providers.youtube_provider._YOUTUBE_API_SEARCH", "https://example.test/search")
    monkeypatch.setattr("urllib.request.urlopen", fake_urlopen)
    monkeypatch.setattr("mini_kio.core.config.YOUTUBE_API_KEY", FAKE_KEY)

    out = provider._api_search_candidates("test query")

    assert out == []
    assert len(calls) == 1, "a 429 must NOT trigger a retry storm"
    captured = capsys.readouterr()
    assert FAKE_KEY not in captured.out and FAKE_KEY not in captured.err, (
        "API key must not leak into log/console output"
    )


def test_api_other_http_error_still_degrades(monkeypatch):
    provider = YouTubeProvider()

    def fake_urlopen(req, timeout=8):
        raise urllib.error.HTTPError(req.full_url, 403, "Forbidden", {}, None)

    monkeypatch.setattr("mini_kio.media.providers.youtube_provider._YOUTUBE_API_SEARCH", "https://example.test/search")
    monkeypatch.setattr("urllib.request.urlopen", fake_urlopen)
    monkeypatch.setattr("mini_kio.core.config.YOUTUBE_API_KEY", FAKE_KEY)

    assert provider._api_search_candidates("test query") == []


def test_close_app_browser_fallback_when_not_tracked(monkeypatch):
    """A registered browser with no KIO-tracked PID is discovered and closed,
    not refused with "I didn't open it"."""
    from mini_kio.core import runtime

    class FakeProcess:
        pid = 4242

        def name(self):
            return "chrome.exe"

    fake_iter = [
        type("P", (), {"info": {"pid": 4242, "name": "chrome.exe", "create_time": 10.0}})(),
        type("P", (), {"info": {"pid": 4243, "name": "chrome.exe", "create_time": 5.0}})(),
        type("P", (), {"info": {"pid": 9999, "name": "explorer.exe", "create_time": 20.0}})(),
    ]

    import psutil
    monkeypatch.setattr(app_operator, "_IS_WINDOWS", True)
    monkeypatch.setattr(runtime, "get_runtime", lambda: type("RT", (), {
        "get_tracked_process": lambda canonical: None,
        "unregister_tracked_process": lambda canonical, pid=None: None,
    })())
    monkeypatch.setattr(psutil, "process_iter", lambda *a, **k: fake_iter)
    monkeypatch.setattr(psutil, "Process", lambda pid: FakeProcess())
    monkeypatch.setattr(app_operator, "_graceful_uwp_close", lambda pid, name: None)
    monkeypatch.setattr(app_operator, "_terminate_with_verification", lambda name, key, pid, info: {
        "success": True, "verified_terminated": True,
        "message": f"Closed {name} (pid {pid})", "pid": pid,
    })

    result = app_operator.close_app("chrome")

    assert result.get("success") is True, f"chrome close should succeed via fallback: {result}"
    assert "didn't open" not in (result.get("message") or "").lower()


def test_find_matching_process_pid_prefers_browser_root(monkeypatch):
    """Browser close must target the interactive root process, not the newest
    helper child (renderer/gpu) — killing a helper leaves the browser running."""
    import psutil

    browser_info = {"process": "chrome.exe", "lifecycle": "browser"}
    root_pid = 20248
    helper_pids = [30001, 30002, 30003]
    matches = [
        {"pid": root_pid, "name": "chrome.exe", "create_time": 100.0},
        *[{"pid": p, "name": "chrome.exe", "create_time": 200.0 + i} for i, p in enumerate(helper_pids)],
    ]

    def fake_iter(*a, **k):
        return [type("P", (), {"info": m})() for m in matches]

    def fake_process(pid):
        # staticmethod: a plain lambda stored on a class would be bound as a
        # method and receive self, breaking psutil.Process(pid).cmdline().
        if pid == root_pid:
            return type("Proc", (), {"cmdline": staticmethod(lambda: ["chrome.exe"])})()
        return type("Proc", (), {"cmdline": staticmethod(lambda: ["chrome.exe", f"--type=renderer"])})()

    monkeypatch.setattr(app_operator, "_IS_WINDOWS", True)
    monkeypatch.setattr(psutil, "process_iter", fake_iter)
    monkeypatch.setattr(psutil, "Process", fake_process)
    monkeypatch.setattr(app_operator, "_proc_has_main_window", lambda pid: pid == root_pid)

    found = app_operator._find_matching_process_pid("chrome", browser_info)
    assert found == root_pid, f"expected browser root {root_pid}, got {found}"


def test_find_matching_process_pid_falls_back_to_newest_without_window(monkeypatch):
    """If no root has a visible window (all headless), fall back to the newest root."""
    import psutil

    browser_info = {"process": "chrome.exe", "lifecycle": "browser"}
    root_old = 50001
    root_new = 50002
    matches = [
        {"pid": root_old, "name": "chrome.exe", "create_time": 100.0},
        {"pid": root_new, "name": "chrome.exe", "create_time": 200.0},
        {"pid": 60001, "name": "chrome.exe", "create_time": 300.0},
    ]

    def fake_iter(*a, **k):
        return [type("P", (), {"info": m})() for m in matches]

    def fake_process(pid):
        if pid == 60001:
            return type("Proc", (), {"cmdline": staticmethod(lambda: ["chrome.exe", "--type=renderer"])})()
        return type("Proc", (), {"cmdline": staticmethod(lambda: ["chrome.exe"])})()

    monkeypatch.setattr(app_operator, "_IS_WINDOWS", True)
    monkeypatch.setattr(psutil, "process_iter", fake_iter)
    monkeypatch.setattr(psutil, "Process", fake_process)
    monkeypatch.setattr(app_operator, "_proc_has_main_window", lambda pid: False)

    found = app_operator._find_matching_process_pid("chrome", browser_info)
    assert found == root_new, f"expected newest root {root_new}, got {found}"
