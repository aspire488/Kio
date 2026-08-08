"""
R-B regression tests: pause/resume/stop must report truthful provider state.

Before R-B these methods lied: when the provider's pause/resume/stop failed
they returned {"success": True, "message": "Paused."/"Resumed."}, and the
no-media case returned success True too. next_track/previous_track already
propagated failure; pause/resume/stop now do the same.
"""
from mini_kio.media.media_session import MediaResult, MediaSession
from mini_kio.media.media_state import MediaState, PlayerType


class _FailingProvider:
    """Play succeeds (registers a session), transport actions fail."""

    def __init__(self):
        self.error = "player is unreachable"

    def play(self, query, media_type=None, platform=None):
        return MediaResult(
            success=True, message="Playing", player="youtube",
            session=MediaSession(player=PlayerType.YOUTUBE, state=MediaState.PLAYING),
        )

    def pause(self):
        return MediaResult(success=False, message=self.error, error=self.error)

    def resume(self):
        return MediaResult(success=False, message=self.error, error=self.error)

    def stop(self):
        return MediaResult(success=False, message=self.error, error=self.error)


def _mm_with_active_session(monkeypatch):
    from mini_kio.media.media_manager import MediaManager
    MediaManager.reset_instance()
    mm = MediaManager.get_instance()
    mm._intelligence_adapter = None
    fake = _FailingProvider()
    mm._get_provider = lambda name: fake
    play_result = mm.play("believer")
    assert play_result.get("success") is True, play_result
    return mm, fake


def _transport_action(mm, action):
    return {
        "pause": mm.pause, "resume": mm.resume, "stop": mm.stop,
    }[action]()


def test_pause_propagates_provider_failure(monkeypatch):
    mm, fake = _mm_with_active_session(monkeypatch)
    result = mm.pause()
    assert result.get("success") is False
    assert fake.error in result.get("message", "")


def test_resume_propagates_provider_failure(monkeypatch):
    mm, fake = _mm_with_active_session(monkeypatch)
    result = mm.resume()
    assert result.get("success") is False
    assert fake.error in result.get("message", "")


def test_stop_propagates_provider_failure(monkeypatch):
    mm, fake = _mm_with_active_session(monkeypatch)
    result = mm.stop()
    assert result.get("success") is False
    assert fake.error in result.get("message", "")


def test_pause_no_media_is_truthful(monkeypatch):
    from mini_kio.media.media_manager import MediaManager
    MediaManager.reset_instance()
    mm = MediaManager.get_instance()
    mm._intelligence_adapter = None
    result = mm.pause()
    assert result.get("success") is False
    assert result.get("message")


def test_resume_no_media_is_truthful(monkeypatch):
    from mini_kio.media.media_manager import MediaManager
    MediaManager.reset_instance()
    mm = MediaManager.get_instance()
    mm._intelligence_adapter = None
    result = mm.resume()
    assert result.get("success") is False
    assert result.get("message")


def test_stop_no_media_is_truthful(monkeypatch):
    from mini_kio.media.media_manager import MediaManager
    MediaManager.reset_instance()
    mm = MediaManager.get_instance()
    mm._intelligence_adapter = None
    result = mm.stop()
    assert result.get("success") is False
    assert "no media to stop" in result.get("message", "").lower()
