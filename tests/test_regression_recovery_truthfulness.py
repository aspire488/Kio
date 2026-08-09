"""
Regression tests for the recovery-fix session (A / E / C / 11).

A:  "Couldn't play X on YouTube" while the video actually plays — the
    extension play-script payload carried a stale pre-play `paused: true`
    over a `playing` status; the provider's acceptance check must not let
    that stale field veto a verified playing state.
E:  "Play next video" must prove the video actually changed (URL), never
    claim success on a click that didn't navigate.
C:  Pause must be proven from observed Chrome state, not the ACK alone.
11: "search X in youtube" must route to the media capability (YouTubeProvider
    / connector world), not the desktop browser_operator escape path.
"""
import asyncio

from mini_kio.browser_connector.protocol import TabResult, VerificationCode
from mini_kio.media.media_state import MediaState, PlayerType
from mini_kio.media.media_session import MediaResult, MediaSession


# ---------------------------------------------------------------------------
# A: play acceptance with the legacy self-contradictory payload
# ---------------------------------------------------------------------------
# Truthful-playback contract (BUG 3): a payload claiming status='playing'
# with paused=true is SELF-CONTRADICTORY. The pre-0.3.3 extension reported
# 'playing' while the element sat paused at 0:00 — the exact false-success
# KIO must never emit. The provider must REJECT such a payload (no
# stabilization retry spiral, no "Playing" success), because the observed
# element state is paused. Only YouTube's own getPlayerState()==1 overrides
# the script's paused field.

class _PlayStalePausedConn:
    """Simulates the raw connector + legacy contradictory payload: the play
    ACK says status=playing but paused=true (the 0:00/paused false-success).
    Must be REJECTED by the truthful acceptance contract."""

    def __init__(self):
        self.calls = []
        self._tab_id = 7

    def is_connected(self):
        return True

    async def open_tab(self, url):
        self.calls.append(("open_tab", url))
        r = TabResult(success=True)
        r.tab = _Tab(self._tab_id)
        return r

    async def execute_script(self, tab_id, script, args=None):
        self.calls.append(("execute_script", tab_id, script))
        if script == "youtube_bootstrap":
            return TabResult(success=True, message="navigating")
        if script == "search_results":
            # no candidates scraped -> play() falls back to youtube_bootstrap
            return TabResult(success=True, message=[])
        if script == "get_page_info":
            return TabResult(success=True, message={
                "url": f"https://www.youtube.com/watch?v=abc{tab_id}",
                "title": "Doomsday - Official Trailer", "hasVideo": True,
            })
        if script == "play":
            return TabResult(success=True, message={
                "status": "playing", "player_status": "playing",
                "paused": True, "currentTime": 3.2, "duration": 120.0,
            })
        if script == "get_player_state":
            return TabResult(success=True, message={"playerState": -1})
        raise AssertionError(f"unexpected script {script!r}")


class _Tab:
    def __init__(self, tab_id):
        self.tab_id = tab_id


def _provider(conn):
    from mini_kio.media.providers.youtube_provider import YouTubeProvider
    return YouTubeProvider(conn=conn)


def test_play_rejects_self_contradictory_playing_paused_payload(monkeypatch):
    """BUG 3 regression: 'playing' + paused=true must NOT be accepted as
    success — that payload was the 0:00/paused false-success. The element is
    observed paused, so the play must fail truthfully and never claim
    'Playing'."""
    from mini_kio.media.providers import youtube_provider as yp
    monkeypatch.setattr(yp.time, "sleep", lambda s: None)
    # These mock-connector tests assume no API candidates (the mock's
    # search_results returns []). A live YOUTUBE_API_KEY in .env would arm the
    # RC8 identity gate against a mock-loaded URL, so isolate discovery.
    monkeypatch.setattr(yp.config, "YOUTUBE_API_KEY", "")

    conn = _PlayStalePausedConn()
    prov = _provider(conn)

    result = prov.play("doomsday trailer")

    assert result.success is False, (
        "self-contradictory playing+paused=true payload must be rejected"
    )
    assert result.error and "couldn't" in result.error.lower(), (
        f"natural truthful failure expected, got: {result.error}"
    )
    # The truthful failure must not leak the internal URL/video id.
    assert "watch?v=" not in result.error
    assert "doomsday" in result.error.lower()


def test_play_accepts_playing_when_observed_unpaused(monkeypatch):
    """A truthful payload (status=playing, paused=false) must be accepted on
    the first attempt — playback was observed with currentTime advancing."""
    from mini_kio.media.providers import youtube_provider as yp
    monkeypatch.setattr(yp.time, "sleep", lambda s: None)
    monkeypatch.setattr(yp.config, "YOUTUBE_API_KEY", "")

    class _ObservedPlayingConn(_PlayStalePausedConn):
        async def execute_script(self, tab_id, script, args=None):
            self.calls.append(("execute_script", tab_id, script))
            if script == "youtube_bootstrap":
                return TabResult(success=True, message="navigating")
            if script == "search_results":
                return TabResult(success=True, message=[])
            if script == "get_page_info":
                return TabResult(success=True, message={
                    "url": f"https://www.youtube.com/watch?v=abc{tab_id}",
                    "title": "Doomsday - Official Trailer", "hasVideo": True,
                })
            if script == "play":
                return TabResult(success=True, message={
                    "status": "playing", "player_status": "playing",
                    "paused": False, "currentTime": 3.2, "duration": 120.0,
                    "volume": 0.9, "muted": False,
                })
            if script == "get_player_state":
                return TabResult(success=True, message={"playerState": -1})
            raise AssertionError(f"unexpected script {script!r}")

    conn = _ObservedPlayingConn()
    prov = _provider(conn)

    result = prov.play("doomsday trailer")

    assert result.success is True, f"observed playing must succeed, got: {result.error}"
    assert result.session is not None
    assert result.session.state == MediaState.PLAYING
    # Media contract: the reply is a natural titled sentence, never a
    # provider-qualified string or an internal URL.
    assert result.message.startswith("Playing ")
    assert "youtube.com" not in result.message.lower()
    assert "watch?v=" not in result.message
    assert sum(1 for c in conn.calls if c[0] == "execute_script" and c[2] == "play") == 1, (
        "a truthful payload must be accepted on the first attempt, not after retries"
    )


# ---------------------------------------------------------------------------
# E: next/previous track must prove the video changed
# ---------------------------------------------------------------------------

class _NextFakeConn:
    def __init__(self, url_before, url_after, url_changed=None):
        self.calls = []
        self._url_before = url_before
        self._url_after = url_after
        self._url_changed = url_changed

    def is_connected(self):
        return True

    async def execute_script(self, tab_id, script, args=None):
        self.calls.append(("execute_script", tab_id, script))
        if script == "next_track":
            return TabResult(success=True, message={
                "status": "navigating" if self._url_before != self._url_after else "no_change",
                "action": "next", "button_found": True, "clicked": True,
                "url_before": self._url_before, "url_after": self._url_after,
                "url_changed": self._url_changed,
            })
        if script == "get_page_info":
            return TabResult(success=True, message={"url": self._url_after})
        raise AssertionError(f"unexpected script {script!r}")


def _provider_with_tab(conn):
    from mini_kio.media.providers.youtube_provider import YouTubeProvider
    prov = YouTubeProvider(conn=conn)
    prov._tab_id = 9
    prov._session = MediaSession(
        player=PlayerType.YOUTUBE, tab_id=9, state=MediaState.PLAYING,
    )
    return prov


def test_next_track_fails_when_url_unchanged(monkeypatch):
    from mini_kio.media.providers import youtube_provider as yp
    monkeypatch.setattr(yp.time, "sleep", lambda s: None)

    conn = _NextFakeConn("https://www.youtube.com/watch?v=AAA", "https://www.youtube.com/watch?v=AAA")
    prov = _provider_with_tab(conn)

    result = prov.next_track()

    assert result.success is False, "next must not claim success when the video did not change"
    assert "next video" in result.error.lower()


def test_next_track_verified_when_url_changes(monkeypatch):
    from mini_kio.media.providers import youtube_provider as yp
    monkeypatch.setattr(yp.time, "sleep", lambda s: None)

    conn = _NextFakeConn("https://www.youtube.com/watch?v=AAA", "https://www.youtube.com/watch?v=BBB")
    prov = _provider_with_tab(conn)

    result = prov.next_track()

    assert result.success is True
    assert "next_track_verified" in result.message


def test_next_track_legacy_payload_fallback_probe(monkeypatch):
    """Older extension payloads carry url_before==url_after read synchronously;
    a follow-up page probe must catch the SPA navigation."""
    from mini_kio.media.providers import youtube_provider as yp
    monkeypatch.setattr(yp.time, "sleep", lambda s: None)

    conn = _NextFakeConn(
        "https://www.youtube.com/watch?v=AAA", "https://www.youtube.com/watch?v=AAA",
        url_changed=False,  # legacy: no url_changed key -> falsy
    )
    # The probe's get_page_info returns _url_after; simulate a slow SPA where
    # the URL only changes after the second probe.
    conn._url_after = "https://www.youtube.com/watch?v=AAA"  # will be overridden below
    real_execute = conn.execute_script

    async def _slow_execute(tab_id, script, args=None):
        if script == "get_page_info" and len(conn.calls) >= 3:
            return TabResult(success=True, message={"url": "https://www.youtube.com/watch?v=BBB"})
        return await real_execute(tab_id, script, args=args)

    conn.execute_script = _slow_execute
    prov = _provider_with_tab(conn)

    result = prov.next_track()

    assert result.success is True
    assert "next_track_verified" in result.message


# ---------------------------------------------------------------------------
# C: pause must be proven from observed Chrome state
# ---------------------------------------------------------------------------

class _PauseHonestRaw:
    async def execute_script(self, tab_id, script, args=None):
        if script == "pause":
            return TabResult(success=True, message={"status": "paused", "paused": True})
        if script == "sample_media":
            return TabResult(success=True, message={
                "ok": True, "status": "paused", "paused": True,
                "currentTime": 12.0, "duration": 120.0, "playerState": 2,
            })
        raise AssertionError(f"unexpected script {script!r}")


class _PauseLyingRaw:
    """ACKs 'paused' but the element is still playing — must be rejected."""

    async def execute_script(self, tab_id, script, args=None):
        if script == "pause":
            return TabResult(success=True, message={"status": "paused", "paused": True})
        if script == "sample_media":
            return TabResult(success=True, message={
                "ok": True, "status": "playing", "paused": False,
                "currentTime": 15.0, "duration": 120.0, "playerState": 1,
            })
        raise AssertionError(f"unexpected script {script!r}")


def _verified_connector(raw):
    from mini_kio.core import state_verification as sv
    return sv.VerifiedConnector(raw)


def test_pause_verified_when_element_reports_paused(monkeypatch):
    from mini_kio.core import state_verification as sv
    monkeypatch.setattr(sv, "_PAUSE_DEADLINE_S", 0.5)
    monkeypatch.setattr(sv, "_MUTATE_POLL_STEP_S", 0.05)
    res = asyncio.run(_verified_connector(_PauseHonestRaw()).execute_script(1, "pause"))
    assert res.success is True
    assert res.verification == VerificationCode.VERIFIED.value


def test_pause_rejected_when_element_still_playing(monkeypatch):
    from mini_kio.core import state_verification as sv
    monkeypatch.setattr(sv, "_PAUSE_DEADLINE_S", 0.2)
    monkeypatch.setattr(sv, "_MUTATE_POLL_STEP_S", 0.02)
    res = asyncio.run(_verified_connector(_PauseLyingRaw()).execute_script(1, "pause"))
    assert res.success is False, "pause must not be claimed while the element still plays"
    assert res.verification == VerificationCode.TIMEOUT.value


# ---------------------------------------------------------------------------
# 11: search_youtube converges onto the media capability
# ---------------------------------------------------------------------------

def test_search_youtube_routes_to_media_capability():
    from mini_kio.core.pipeline import Pipeline, IntentType

    p = Pipeline()
    d = p._classifier.classify("search messi in youtube", "search messi in youtube")
    assert d.intent_type == IntentType.SEARCH
    assert d.action == "search_youtube"

    capability, params = p._resolver.resolve(d)
    assert capability == "media"
    assert params["action"] == "search"
    assert params["platform"] == "youtube"
    assert params["target"] == "messi"


def test_exec_media_search_dispatches_to_mm_search(monkeypatch):
    from mini_kio.media.media_manager import MediaManager
    from mini_kio.core.pipeline import _ExecutionCoordinator, RoutingDecision, IntentType

    class _FakeMM:
        def __init__(self):
            self.searches = []

        def search(self, query, platform=""):
            self.searches.append((query, platform))
            return {"success": True, "message": "ok"}

        def play(self, *a, **k):
            return {"success": True, "message": "ok"}

    fake = _FakeMM()
    monkeypatch.setattr(MediaManager, "get_instance", classmethod(lambda cls: fake))
    coord = _ExecutionCoordinator()
    d = RoutingDecision(IntentType.SEARCH, "search_youtube", "messi", "search messi in youtube", "search messi in youtube", confidence=1.0)
    result = coord._exec_media({"action": "search", "target": "messi", "platform": "youtube"}, d)
    assert fake.searches == [("messi", "youtube")]
    assert result.get("success") is True


# ---------------------------------------------------------------------------
# A (live): the play loop must retry timing/no-media failures instead of
# giving up while the watch page is still building its <video> element
# ---------------------------------------------------------------------------

class _SlowLoadConn:
    """Watch page needs a few attempts before its <video> element exists
    (extension reports a non-state/no-media payload on early attempts)."""

    def __init__(self):
        self.calls = []
        self._tab_id = 11
        self.play_calls = 0

    def is_connected(self):
        return True

    async def open_tab(self, url):
        self.calls.append(("open_tab", url))
        r = TabResult(success=True)
        r.tab = _Tab(self._tab_id)
        return r

    async def execute_script(self, tab_id, script, args=None):
        self.calls.append(("execute_script", tab_id, script))
        if script == "youtube_bootstrap":
            return TabResult(success=True, message="navigating")
        if script == "search_results":
            # no candidates scraped -> play() falls back to youtube_bootstrap
            return TabResult(success=True, message=[])
        if script == "get_page_info":
            return TabResult(success=True, message={
                "url": f"https://www.youtube.com/watch?v=xyz{tab_id}",
                "title": "T", "hasVideo": True,
            })
        if script == "get_player_state":
            return TabResult(success=True, message={"playerState": -1})
        if script == "play":
            self.play_calls += 1
            if self.play_calls < 3:
                # timing: the <video> element has not rendered yet
                return TabResult(success=False, message="",
                                 error="script 'play' returned non-state payload")
            return TabResult(success=True, message={
                "status": "playing", "player_status": "playing",
                "paused": False, "currentTime": 1.0, "duration": 120.0,
            })
        raise AssertionError(f"unexpected script {script!r}")


def test_play_retries_timing_failure_until_playing(monkeypatch):
    from mini_kio.media.providers import youtube_provider as yp
    monkeypatch.setattr(yp.time, "sleep", lambda s: None)
    # Same API isolation as the stale-paused test above.
    monkeypatch.setattr(yp.config, "YOUTUBE_API_KEY", "")

    conn = _SlowLoadConn()
    prov = _provider(conn)

    result = prov.play("doomsday trailer")

    assert result.success is True, f"play must retry timing failures, got: {result.error}"
    assert result.session is not None
    assert result.session.state == MediaState.PLAYING
    assert conn.play_calls == 3, "the loop must retry until the element loads"


# ---------------------------------------------------------------------------
# A (live): a resolved play query that is scraped page text / a URL must be
# rejected before it reaches the provider ("Couldn't play <url> on YouTube")
# ---------------------------------------------------------------------------

class _BadResolvingAdapter:
    def __init__(self):
        self.queries = []

    def handle(self, query, execute=False):
        self.queries.append(query)
        _R = type("_R", (), {})
        r = _R()
        r.source = "artifact"
        r.subject = "https://www.youtube.com/about/)[Press](https://www.youtube.com/about/press/)"
        return r


class _RecordingProvider:
    def __init__(self):
        self.queries = []

    def play(self, query, media_type=None, platform=None):
        self.queries.append(query)
        return MediaResult(
            success=True, message="Playing", player="youtube",
            session=MediaSession(player=PlayerType.YOUTUBE, state=MediaState.PLAYING),
        )


def test_play_rejects_url_resolved_query(monkeypatch):
    from mini_kio.media.media_manager import MediaManager
    MediaManager.reset_instance()
    mm = MediaManager.get_instance()
    mm._intelligence_adapter = _BadResolvingAdapter()
    fake = _RecordingProvider()
    mm._get_provider = lambda name: fake

    result = mm.play("doomsday trailer")

    assert fake.queries, "provider must be invoked"
    assert fake.queries[0] == "doomsday trailer", (
        f"scraped/URL resolution must be rejected, got query {fake.queries[0]!r}"
    )
    assert result.get("success") is True
