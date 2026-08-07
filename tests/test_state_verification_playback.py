"""
R1 regression: _verify_playback false-negative on real YouTube playback.

Live scenario reproduced (07-08-2026): `play messi on YouTube` returned
"Couldn't play messi on YouTube". The runtime trace showed the video element
loaded and reported status="playing" with a real duration, but currentTime
did not advance within the verification window (startup/buffering stall), so
_verify_playback rejected with "media position did not advance" before the
provider's own richer PLAY_VERIFY logic could run.

The fix: accept status=="playing" + a loaded duration as verified; keep the
currentTime-progression comparison as a soft positive signal only, never the
sole gate. A paused / genuinely-stalled element must still be rejected so the
loosened check cannot become an always-pass.
"""

import asyncio

from mini_kio.browser_connector.protocol import TabResult, VerificationCode
from mini_kio.core import state_verification as sv


class PlayingStalledClockRaw:
    """Video is genuinely playing (status=playing, duration loaded,
    playerState=1) but currentTime stays at 0 during startup/buffering."""

    async def execute_script(self, tab_id, script, args=None):
        if script == "sample_media":
            return TabResult(success=True, message={
                "ok": True,
                "status": "playing",
                "url": "https://www.youtube.com/watch?v=abc123",
                "paused": False,
                "ended": False,
                "currentTime": 0.0,
                "duration": 142.0,
                "readyState": 4,
                "networkState": 2,
                "muted": False,
                "volume": 1.0,
                "playerState": 1,
            })
        if script == "play":
            return TabResult(success=True, message={
                "status": "playing", "paused": False, "currentTime": 0.0,
            })
        raise AssertionError(f"unexpected script {script!r}")


class PausedStalledRaw:
    """Video loaded a duration but autoplay did not start (paused, stuck)."""

    async def execute_script(self, tab_id, script, args=None):
        if script == "sample_media":
            return TabResult(success=True, message={
                "ok": True,
                "status": "paused",
                "url": "https://www.youtube.com/watch?v=abc123",
                "paused": True,
                "ended": False,
                "currentTime": 0.0,
                "duration": 142.0,
                "readyState": 4,
                "playerState": 2,
            })
        if script == "play":
            return TabResult(success=True, message={
                "status": "paused", "paused": True, "currentTime": 0.0,
            })
        raise AssertionError(f"unexpected script {script!r}")


class NoMediaRaw:
    """No media element at all — must stay a hard failure."""

    async def execute_script(self, tab_id, script, args=None):
        if script == "sample_media":
            return TabResult(success=True, message={
                "ok": False,
                "status": "no media",
                "url": "https://www.youtube.com/results?search_query=x",
                "currentTime": 0,
                "duration": 0,
                "paused": True,
                "playerState": -1,
            })
        if script == "play":
            return TabResult(success=True, message={"status": "no media"})
        raise AssertionError(f"unexpected script {script!r}")


def _run(raw):
    conn = sv.VerifiedConnector(raw)
    return asyncio.run(conn.execute_script(1, "play"))


def test_playing_with_loaded_duration_is_verified(monkeypatch):
    monkeypatch.setattr(sv, "_play_deadline_s", lambda: 0.2)
    monkeypatch.setattr(sv, "_MUTATE_POLL_STEP_S", 0.05)
    res = _run(PlayingStalledClockRaw())
    assert res.success is True, f"play should be verified, got: {res.error}"
    assert res.verification == VerificationCode.VERIFIED.value


def test_paused_stalled_video_still_rejected(monkeypatch):
    monkeypatch.setattr(sv, "_play_deadline_s", lambda: 0.2)
    monkeypatch.setattr(sv, "_MUTATE_POLL_STEP_S", 0.05)
    res = _run(PausedStalledRaw())
    assert res.success is False, "a paused, non-advancing video is not playback"
    assert res.verification == VerificationCode.TIMEOUT.value


def test_no_media_still_hard_failure(monkeypatch):
    monkeypatch.setattr(sv, "_play_deadline_s", lambda: 0.2)
    monkeypatch.setattr(sv, "_MUTATE_POLL_STEP_S", 0.05)
    res = _run(NoMediaRaw())
    assert res.success is False
    assert res.verification in (
        VerificationCode.FAILED.value, VerificationCode.TIMEOUT.value,
        VerificationCode.NOT_VERIFIED.value,
    )
