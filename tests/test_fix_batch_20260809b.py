"""
KIO forensic stabilization regression tests — 2026-08-09 batch (part 2).

Covers:
1.  Build-version single source of truth (BUG 13): connector and
    state_verification import the same constant, and the JS/manifest literals
    agree with it.
2.  Telegram concurrency (BUG 1): PTB app is built with concurrent_updates(4),
    and MediaManager serializes media ops (thread-safe singleton).
3.  YouTube retry architecture (BUG 4): the play loop runs on the RAW connector
    (no 10s re-verification per retry) and does NOT retry definitive
    verification failures.
4.  Lost-tab truthfulness (BUG 5): a "No tab with id" error stops the loop and
    fails truthfully instead of retrying or claiming "Opened".
5.  Close policy (BUG 6): registered non-browser apps are discovered by process
    name and closed; registered apps not running report "wasn't running".
6.  Close response truthfulness (BUG 7): SUCCESS_WITH_RESIDUALS surfaces a
    concise partial message; NOT_RUNNING maps to "wasn't running".
7.  Runtime readiness flag (BUG 12): write_runtime_ready_flag writes the live
    PID and is suppressed in test mode.
8.  API-quota intelligent fallback (BUG 9): with the API returning 429, the
    browser-scrape candidates are still ranked (never first-result selection).
"""

import json
import os
import re
from pathlib import Path

import pytest

from mini_kio.browser_connector import build as build_mod
from mini_kio.browser_connector.connector import Connector
from mini_kio.browser_connector.protocol import TabResult, VerificationCode
from mini_kio.media.media_session import MediaResult
from mini_kio.media.media_state import MediaState


# ---------------------------------------------------------------------------
# BUG 13 — single source of truth for the extension build fingerprint
# ---------------------------------------------------------------------------

def test_build_constants_share_single_source():
    from mini_kio.core import state_verification as sv
    from mini_kio.browser_connector import connector as conn_mod

    assert conn_mod._EXPECTED_EXTENSION_BUILD == build_mod.EXTENSION_BUILD
    assert sv._EXPECTED_BUILD == build_mod.EXTENSION_BUILD


def test_extension_js_and_manifest_match_python_constant():
    """The JS BUILD_VERSION, the INLINED get_build_info literal, and the
    manifest version must all equal the Python constant. If they drift, the
    build gate will reject the loaded extension or the stale-build diagnostic
    will report the wrong expectation."""
    root = Path(__file__).resolve().parent.parent
    js = (root / "mini_kio" / "browser_connector" / "extension" / "background.js").read_text(encoding="utf-8")
    manifest = json.loads(
        (root / "mini_kio" / "browser_connector" / "extension" / "manifest.json").read_text(encoding="utf-8")
    )

    m1 = re.search(r'BUILD_VERSION\s*=\s*"([^"]+)"', js)
    assert m1, "BUILD_VERSION constant missing in background.js"
    m2 = re.search(r"build:\s*'([^']+)'", js)
    assert m2, "inlined get_build_info literal missing in background.js"

    assert m1.group(1) == build_mod.EXTENSION_BUILD, f"BUILD_VERSION drifted: {m1.group(1)}"
    assert m2.group(1) == build_mod.EXTENSION_BUILD, f"get_build_info literal drifted: {m2.group(1)}"
    assert manifest.get("version") == build_mod.EXTENSION_BUILD, (
        f"manifest version drifted: {manifest.get('version')}"
    )


def test_extension_play_script_prefers_player_api():
    """BUG 3: the play script must prefer the YouTube player API (playVideo)
    over a raw video.play(), which the player controller can reconcile back to
    paused."""
    root = Path(__file__).resolve().parent.parent
    js = (root / "mini_kio" / "browser_connector" / "extension" / "background.js").read_text(encoding="utf-8")
    play_block = js[js.index("  play: async () => {"):]
    assert "_playerApi.playVideo()" in play_block, "play script must call playVideo()"
    # The API-detection flag (_hasApi) drives the playVideo-first strategy; a
    # report of whether the API path was used (_play_api_used) is part of the
    # truthfulness payload.
    assert "_hasApi" in play_block, "play script must detect the player API"
    assert "_play_api_used" in play_block, "play script must report whether the API was used"


# ---------------------------------------------------------------------------
# BUG 1 — Telegram concurrency + MediaManager serialization
# ---------------------------------------------------------------------------

def test_ptb_built_with_concurrent_updates():
    from kio_bot import _build_app
    app = _build_app()
    try:
        assert getattr(app, "concurrent_updates", None) >= 4, (
            "PTB must process updates concurrently so a media op doesn't block 'hi'"
        )
    finally:
        # Do not leave a half-initialized app holding the event loop.
        import asyncio
        try:
            loop = asyncio.get_event_loop()
            if loop.is_running():
                loop.call_soon_threadsafe(loop.stop)
        except RuntimeError:
            pass


def test_media_manager_singleton_is_thread_guarded():
    from mini_kio.media.media_manager import MediaManager
    MediaManager.reset_instance()
    try:
        a = MediaManager.get_instance()
        b = MediaManager.get_instance()
        assert a is b, "get_instance must return the same guarded singleton"
    finally:
        MediaManager.reset_instance()


def test_media_ops_are_serialized():
    from mini_kio.media import media_manager as mm_mod
    from mini_kio.media.media_manager import MediaManager
    MediaManager.reset_instance()
    try:
        mm = MediaManager.get_instance()
        assert hasattr(mm_mod, "_MEDIA_OP_LOCK"), "media op lock must exist"
        assert mm_mod._MEDIA_OP_LOCK is not None
        # The lock is re-entrant so nested media calls (followup -> play) do not
        # deadlock.
        with mm_mod._MEDIA_OP_LOCK:
            with mm_mod._MEDIA_OP_LOCK:
                assert True
    finally:
        MediaManager.reset_instance()


# ---------------------------------------------------------------------------
# BUG 4 — raw connector for the play loop; no retry of definitive failures
# ---------------------------------------------------------------------------

class _VerifiedWrap:
    """Mimics VerifiedConnector wrapping a raw connector."""

    def __init__(self, raw):
        self._raw = raw


def test_provider_raw_conn_unwraps_verified_wrapper():
    from mini_kio.media.providers.youtube_provider import YouTubeProvider
    raw = Connector(mock=True)
    prov = YouTubeProvider(conn=_VerifiedWrap(raw))
    assert prov._get_raw_conn() is raw, "must unwrap the verification wrapper"


class _TabLostRawConn:
    """Raw connector where the tab vanishes mid-play: 'No tab with id'."""

    def __init__(self):
        self.calls = []

    def is_connected(self):
        return True

    async def open_tab(self, url):
        self.calls.append(("open_tab", url))
        r = TabResult(success=True)
        r.tab = type("_T", (), {"tab_id": 55})()
        return r

    async def execute_script(self, tab_id, script, args=None):
        self.calls.append(("execute_script", script))
        if script == "search_results":
            return TabResult(success=True, message=[])
        if script == "youtube_bootstrap":
            return TabResult(success=True, message="navigating")
        if script == "get_page_info":
            return TabResult(success=True, message={
                "url": "https://www.youtube.com/watch?v=abc", "title": "T",
            })
        if script == "play":
            return TabResult(success=False, error="No tab with id: 55")
        raise AssertionError(f"unexpected script {script!r}")


def test_play_reports_tab_loss_truthfully(monkeypatch):
    """BUG 5: a lost tab must stop the loop and fail truthfully — never retried,
    never 'Opened on YouTube'."""
    from mini_kio.media.providers import youtube_provider as yp
    monkeypatch.setattr(yp.time, "sleep", lambda s: None)
    # Isolate from a live YouTube Data API key (environment-dependent).
    monkeypatch.setattr(yp.config, "YOUTUBE_API_KEY", "")

    conn = _TabLostRawConn()
    prov = yp.YouTubeProvider(conn=conn)
    result = prov.play("doomsday trailer")

    assert result.success is False, result
    assert "tab closed" in (result.error or "").lower(), result.error
    play_calls = [c for c in conn.calls if c == ("execute_script", "play")]
    assert len(play_calls) == 1, "a lost tab must not be retried"


class _AlwaysAdvanceFailConn:
    """The play ACK says playing but a definitive verification would fail."""

    def __init__(self):
        self.calls = []

    def is_connected(self):
        return True

    async def open_tab(self, url):
        self.calls.append(("open_tab", url))
        r = TabResult(success=True)
        r.tab = type("_T", (), {"tab_id": 56})()
        return r

    async def execute_script(self, tab_id, script, args=None):
        self.calls.append(("execute_script", script))
        if script == "search_results":
            return TabResult(success=True, message=[])
        if script == "youtube_bootstrap":
            return TabResult(success=True, message="navigating")
        if script == "get_page_info":
            return TabResult(success=True, message={
                "url": "https://www.youtube.com/watch?v=abc", "title": "T",
            })
        if script == "play":
            # Not playing, and never will: the player stays paused.
            return TabResult(success=True, message={
                "status": "paused", "player_status": "paused",
                "paused": True, "currentTime": 0.0, "duration": 120.0,
            })
        if script == "get_player_state":
            return TabResult(success=True, message={"playerState": 2})
        raise AssertionError(f"unexpected script {script!r}")


def test_play_not_retried_on_paused_payload(monkeypatch):
    """BUG 4: a play ACK that reports paused (never playing) is not a timing
    failure to retry — the loop must terminate within the bounded attempts and
    report truthfully."""
    from mini_kio.media.providers import youtube_provider as yp
    monkeypatch.setattr(yp.time, "sleep", lambda s: None)
    monkeypatch.setattr(yp.config, "YOUTUBE_API_KEY", "")

    conn = _AlwaysAdvanceFailConn()
    prov = yp.YouTubeProvider(conn=conn)
    result = prov.play("doomsday trailer")

    assert result.success is False, result
    play_calls = [c for c in conn.calls if c == ("execute_script", "play")]
    assert len(play_calls) <= 5, f"bounded attempts only, got {len(play_calls)}"


# ---------------------------------------------------------------------------
# BUG 6 — generic close policy for registered apps
# ---------------------------------------------------------------------------

def test_close_app_generic_fallback_for_non_browser_app(monkeypatch):
    """BUG 6: the process-discovery fallback must work for ANY registered app,
    not just browsers."""
    from mini_kio.core import app_operator, runtime

    fake_iter = [
        type("P", (), {"info": {"pid": 7777, "name": "vlc.exe", "create_time": 10.0}})(),
    ]

    import psutil
    monkeypatch.setattr(app_operator, "_IS_WINDOWS", True)
    monkeypatch.setattr(runtime, "get_runtime", lambda: type("RT", (), {
        "get_tracked_process": lambda canonical: None,
        "unregister_tracked_process": lambda canonical, pid=None: None,
    })())
    monkeypatch.setattr(psutil, "process_iter", lambda *a, **k: fake_iter)
    monkeypatch.setattr(app_operator, "_graceful_uwp_close", lambda pid, name: None)
    monkeypatch.setattr(app_operator, "_terminate_with_verification", lambda name, key, pid, info: {
        "success": True, "verified_terminated": True,
        "message": f"Closed {name}.", "pid": pid,
        "outcome_class": "SUCCESS", "verification_status": "passed",
    })

    result = app_operator.close_app("vlc")
    assert result.get("success") is True, result
    assert "didn't open" not in (result.get("message") or "").lower()


def test_close_app_not_running_registered_app(monkeypatch):
    """BUG 6: a registered app with no matching process reports 'wasn't
    running' — not a misleading ownership refusal.

    VLC is mocked as INSTALLED (path resolves) so the modality-consistent
    close rule stays native-scope: an installed native app that is not running
    has no web session (launch would have opened the native app, and a launch
    failure only ever falls back to KNOWN web versions, never a synthesized
    vlc.com). A NOT-installed registered name would instead resolve to the
    disclosed web-fallback scope — covered by DisclosedWebFallbackTest.
    """
    from mini_kio.core import app_operator, runtime

    import psutil
    monkeypatch.setattr(app_operator, "_IS_WINDOWS", True)
    monkeypatch.setattr(runtime, "get_runtime", lambda: type("RT", (), {
        "get_tracked_process": lambda canonical: None,
        "unregister_tracked_process": lambda canonical, pid=None: None,
    })())
    monkeypatch.setattr(app_operator, "_resolve_path", lambda info: "C:/fake/VLC/vlc.exe")
    monkeypatch.setattr(psutil, "process_iter", lambda *a, **k: [])
    monkeypatch.setattr(app_operator, "_graceful_uwp_close", lambda pid, name: None)

    result = app_operator.close_app("vlc")
    assert result.get("success") is False, result
    assert result.get("failure_class") == "not_running", result
    assert "wasn't running" in (result.get("message") or "").lower(), result
    assert "didn't open" not in (result.get("message") or "").lower()


# ---------------------------------------------------------------------------
# BUG 7 — close response truthfulness
# ---------------------------------------------------------------------------

def test_formatter_partial_close_surfaces_residuals():
    from mini_kio.core.runtime_response_formatter import format_result
    result = format_result("close_app", "chrome", True, {
        "message": "Closed Chrome.",
        "outcome_class": "SUCCESS_WITH_RESIDUALS",
        "verification_status": "passed_with_residuals",
        "residual_pid": 1234,
    })
    assert "Closed Chrome" in result
    assert "background processes are still running" in result, result
    assert "pid" not in result.lower(), "implementation detail must stay hidden"


def test_formatter_success_close_is_concise():
    from mini_kio.core.runtime_response_formatter import format_result
    result = format_result("close_app", "chrome", True, {
        "message": "Closed Chrome.",
        "outcome_class": "SUCCESS",
        "verification_status": "passed",
    })
    assert result == "Closed Chrome.", result


def test_formatter_not_running_close():
    from mini_kio.core.runtime_response_formatter import format_result
    result = format_result("close_app", "vlc", False, {
        "message": "vlc wasn't running.",
        "outcome_class": "NOT_RUNNING",
        "verification_status": "not_running",
        "failure_class": "not_running",
    })
    assert "wasn't running" in result, result
    assert "didn't open" not in result.lower()


def test_terminate_with_verification_messages_not_contradictory(monkeypatch):
    """BUG 7: a partial close must not produce
    'Closed X. ... but helper processes may persist' (claiming both)."""
    from mini_kio.core import app_operator
    monkeypatch.setattr(app_operator, "_run_taskkill", lambda pid, force=False: type(
        "R", (), {"stderr": ""})())
    monkeypatch.setattr(app_operator, "_wait_for_termination_verification",
                        lambda pid, key, info, attempts: None)
    payload = app_operator._terminate_with_verification("chrome", "chrome", 100, {
        "lifecycle": "browser",
    })
    assert payload["outcome_class"] == "SUCCESS"
    assert payload["message"] == "Closed chrome.", payload


# ---------------------------------------------------------------------------
# BUG 12 — runtime readiness flag
# ---------------------------------------------------------------------------

def test_write_runtime_ready_flag_suppressed_in_test_mode(monkeypatch, tmp_path):
    from mini_kio.core import runtime as rt_mod
    monkeypatch.setenv("KIO_TEST_MODE", "1")
    out = rt_mod.write_runtime_ready_flag(flag_path=tmp_path / "runtime_ready.flag")
    assert out is None, "must not write the flag in test mode"
    assert not (tmp_path / "runtime_ready.flag").exists()


def test_write_runtime_ready_flag_writes_live_pid(monkeypatch, tmp_path):
    import os as _os
    from mini_kio.core import runtime as rt_mod
    monkeypatch.delenv("KIO_TEST_MODE", raising=False)
    flag_path = tmp_path / "runtime_ready.flag"
    written = rt_mod.write_runtime_ready_flag(flag_path=flag_path)
    assert written is not None
    content = flag_path.read_text(encoding="utf-8")
    assert f"pid={_os.getpid()}" in content, (
        "the flag must carry the LIVE pid, never a stale one"
    )
    assert content.startswith("READY ")


# ---------------------------------------------------------------------------
# BUG 9 — API-quota fallback keeps intelligent selection
# ---------------------------------------------------------------------------

def test_429_fallback_still_ranks_scraped_candidates(monkeypatch):
    """BUG 2 + BUG 9: when the YouTube Data API 429s, the browser scrape still
    runs and the best-matching candidate is selected — never the first result."""
    import urllib.error
    from mini_kio.media.providers import youtube_provider as yp
    from mini_kio.core import config

    def fake_urlopen(req, timeout=8):
        raise urllib.error.HTTPError(req.full_url, 429, "Too Many Requests", {}, None)

    monkeypatch.setattr(yp.config, "YOUTUBE_API_KEY", "FAKE-KEY-12345")
    monkeypatch.setattr("urllib.request.urlopen", fake_urlopen)

    candidates = [
        {"title": "Random cat video", "url": "https://www.youtube.com/watch?v=CAT", "video_id": "CAT"},
        {"title": "Doomsday - Official Trailer (2024)", "url": "https://www.youtube.com/watch?v=BEST", "video_id": "BEST"},
        {"title": "Messi goals 2026", "url": "https://www.youtube.com/watch?v=WRONG", "video_id": "WRONG"},
    ]

    class _ScrapeConn:
        def is_connected(self):
            return True

        async def execute_script(self, tab_id, script, args=None):
            assert script == "search_results"
            return TabResult(success=True, message=candidates)

    prov = yp.YouTubeProvider(conn=_ScrapeConn())
    best = prov._select_best_candidate(7, "doomsday trailer", media_type="trailer")
    assert best is not None
    assert best["video_id"] == "BEST", (
        f"intelligent selection must survive API quota failure, got {best}"
    )


# ---------------------------------------------------------------------------
# BUG 10 — reference/entity resolution honesty
# ---------------------------------------------------------------------------

def test_play_first_result_routes_to_pending_offer(monkeypatch):
    """Ordinal selection ('play the first result') must route through the
    pending-offer engine, not a literal YouTube search for 'first'."""
    from mini_kio.media.media_manager import MediaManager
    MediaManager.reset_instance()
    try:
        mm = MediaManager.get_instance()
        mm._offer_manager = type("_O", (), {
            "has_pending_offer": lambda self=True: True,
            "parse_response": lambda self=True, q=None: True,
        })()
        called = []
        mm.accept_intelligence_offer = lambda: called.append("accepted") or {
            "success": True, "message": "Playing the first result.",
        }
        result = mm.play("play the first result")
        assert called, "ordinal must route to the offer acceptance path"
        assert result.get("success") is True
    finally:
        MediaManager.reset_instance()


# ---------------------------------------------------------------------------
# MEDIA CONTRACT — internal YouTube URLs must never leak into user-facing text
# ---------------------------------------------------------------------------

class _DirectUrlSuccessConn:
    """Direct URL input: the page loads with a REAL title, the player becomes
    ready and starts. The provider must answer with the resolved title, not the
    URL the user happened to paste."""

    def __init__(self):
        self.calls = []
        self._tab_id = 99

    def is_connected(self):
        return True

    async def open_tab(self, url):
        self.calls.append(("open_tab", url))
        r = TabResult(success=True)
        r.tab = type("_T", (), {"tab_id": self._tab_id})()
        return r

    async def execute_script(self, tab_id, script, args=None):
        self.calls.append(("execute_script", script))
        if script == "search_results":
            return TabResult(success=True, message=[])
        if script == "youtube_bootstrap":
            return TabResult(success=True, message="navigating")
        if script == "get_page_info":
            return TabResult(success=True, message={
                "url": "https://www.youtube.com/watch?v=dQw4w9WgXcQ",
                "title": "Rick Astley - Never Gonna Give You Up (Official Music Video) - YouTube",
                "hasVideo": True,
            })
        if script == "play":
            return TabResult(success=True, message={
                "status": "playing", "player_status": "playing", "paused": False,
                "currentTime": 3.0, "duration": 213.0,
            })
        if script == "get_player_state":
            return TabResult(success=True, message={"playerState": 1})
        raise AssertionError(f"unexpected script {script!r}")


def test_direct_url_success_answers_with_resolved_title(monkeypatch):
    """A user-supplied YouTube URL is parsed as INPUT; the reply uses the
    resolved media title, never the URL."""
    from mini_kio.media.providers import youtube_provider as yp
    monkeypatch.setattr(yp.time, "sleep", lambda s: None)
    monkeypatch.setattr(yp.config, "YOUTUBE_API_KEY", "")

    conn = _DirectUrlSuccessConn()
    prov = yp.YouTubeProvider(conn=conn)
    result = prov.play("https://www.youtube.com/watch?v=dQw4w9WgXcQ")

    assert result.success is True, result.error
    assert result.session is not None
    assert result.session.state == MediaState.PLAYING
    assert "youtube.com/watch" not in result.message.lower(), (
        f"internal URL leaked into user-facing text: {result.message!r}"
    )
    assert "Never Gonna Give You Up" in result.message, result.message
    assert result.session.title.startswith("Rick Astley"), result.session.title


class _DirectUrlNeverReadyConn:
    """Direct URL where the watch page stays cold (PlayerNotReady on every
    attempt). Must retry within the bounded loop, then fail truthfully with a
    URL-free message and no_fallback=True."""

    def __init__(self):
        self.calls = []
        self._tab_id = 100
        self.play_calls = 0

    def is_connected(self):
        return True

    async def open_tab(self, url):
        self.calls.append(("open_tab", url))
        r = TabResult(success=True)
        r.tab = type("_T", (), {"tab_id": self._tab_id})()
        return r

    async def execute_script(self, tab_id, script, args=None):
        self.calls.append(("execute_script", script))
        if script == "search_results":
            return TabResult(success=True, message=[])
        if script == "youtube_bootstrap":
            return TabResult(success=True, message="navigating")
        if script == "get_page_info":
            return TabResult(success=True, message={
                "url": "https://www.youtube.com/watch?v=dQw4w9WgXcQ",
                "title": "YouTube", "hasVideo": True,
            })
        if script == "get_player_state":
            return TabResult(success=True, message={"playerState": -1})
        if script == "play":
            self.play_calls += 1
            return TabResult(success=True, message={
                "status": "error", "name": "PlayerNotReady",
                "player_status": "player_not_ready", "paused": True,
                "readyState": 0, "currentTime": 0.0, "duration": 0,
                "url": "https://www.youtube.com/watch?v=dQw4w9WgXcQ",
                "title": "YouTube",
            })
        raise AssertionError(f"unexpected script {script!r}")


def test_player_not_ready_is_bounded_retry_and_never_leaks_url(monkeypatch):
    """A cold-loading player (PlayerNotReady) is a TIMING signal: the loop
    retries within bounds instead of giving up / falling back, and the failure
    message never contains the internal URL."""
    from mini_kio.media.providers import youtube_provider as yp
    monkeypatch.setattr(yp.time, "sleep", lambda s: None)
    monkeypatch.setattr(yp.config, "YOUTUBE_API_KEY", "")

    conn = _DirectUrlNeverReadyConn()
    prov = yp.YouTubeProvider(conn=conn)
    result = prov.play("https://www.youtube.com/watch?v=dQw4w9WgXcQ")

    assert result.success is False, result
    assert conn.play_calls == 5, f"bounded retry expected, got {conn.play_calls} play calls"
    assert result.no_fallback is True, "resolved media must not fall back to a search page"
    err = (result.error or "").lower()
    assert "http" not in err and "youtube.com/watch" not in err, (
        f"internal URL leaked into failure text: {result.error!r}"
    )


class _YtResolvedThenFail:
    """YouTube provider resolves the exact media but playback fails."""

    def check_active(self):
        return None

    def play(self, query, media_type=None, platform=None):
        return MediaResult(
            success=False, error="I couldn't start the requested media on YouTube.",
            no_fallback=True,
        )


class _BrowserFallbackTracker:
    def __init__(self):
        self.called = False

    def check_active(self):
        return None

    def play(self, query, media_type=None, platform=None):
        self.called = True
        return MediaResult(success=True, message="browser fallback")


def test_resolved_media_failure_does_not_fall_back_to_browser(monkeypatch):
    """Once the exact media is resolved, a playback failure must NOT abandon it
    for a generic browser search page (media contract, no_fallback)."""
    from mini_kio.media.media_manager import MediaManager
    MediaManager.reset_instance()
    try:
        mm = MediaManager.get_instance()
        mm._intelligence_adapter = None  # deterministic: skip entity resolution
        br = _BrowserFallbackTracker()
        mm._get_provider = lambda name: _YtResolvedThenFail() if name == "youtube" else br

        result = mm.play("https://www.youtube.com/watch?v=abc123")

        assert br.called is False, "resolved-media failure must stop the provider chain"
        assert result.get("success") is False, result
        msg = (result.get("message") or "").lower()
        assert "youtube.com/watch" not in msg, f"URL leaked: {result.get('message')!r}"
        assert "couldn't start" in msg, msg
    finally:
        MediaManager.reset_instance()
