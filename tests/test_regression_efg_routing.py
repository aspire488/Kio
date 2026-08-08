"""
R-EFG regression tests.

E: "play next/previous video" must resolve to the real next/previous-track
   transport action (not a play-with-empty-target that resumes/gates).
F: "play it"/"play that" are media-continuity commands resolved by
   MediaManager.play's pronoun handling — NOT the offer-acceptance path.
G: bare "play again" with no prior media must reply truthfully instead of
   searching the word "again"; with a prior successful play it replays it.
"""
from mini_kio.core.pipeline import Pipeline
from mini_kio.core.pipeline import RoutingDecision
from mini_kio.core.pipeline import IntentType
from mini_kio.media.media_session import MediaResult, MediaSession
from mini_kio.media.media_state import MediaState, PlayerType


def _classify(text: str):
    p = Pipeline()
    return p._classifier.classify(text, text)


# ── E: classifier transport routing ─────────────────────────────────

def test_play_next_video_is_next_transport():
    d = _classify("play next video")
    assert d.intent_type == IntentType.MEDIA_TRANSPORT
    assert d.action == "next"


def test_play_previous_video_is_previous_transport():
    d = _classify("play previous video")
    assert d.intent_type == IntentType.MEDIA_TRANSPORT
    assert d.action == "previous"


def test_bare_next_video_unchanged():
    d = _classify("next video")
    assert d.intent_type == IntentType.MEDIA_TRANSPORT
    assert d.action == "next"


# ── E: exec dispatch reaches the transport handler ──────────────────

class _FakeMM:
    def __init__(self):
        self.calls = []

    def next_track(self):
        self.calls.append("next_track")
        return {"success": True, "message": "next"}

    def previous_track(self):
        self.calls.append("previous_track")
        return {"success": True, "message": "previous"}

    def _noop(self):
        return {"success": True, "message": "ok"}

    pause = resume = stop = mute = unmute = volume_up = volume_down = _noop


def _exec_media(action, text, monkeypatch):
    from mini_kio.media.media_manager import MediaManager
    from mini_kio.core.pipeline import _ExecutionCoordinator
    fake = _FakeMM()
    monkeypatch.setattr(MediaManager, "get_instance", classmethod(lambda cls: fake))
    coord = _ExecutionCoordinator()
    d = RoutingDecision(IntentType.MEDIA_TRANSPORT, action, "", text, text, confidence=1.0)
    coord._exec_media({"action": action, "target": ""}, d)
    return fake


def test_exec_play_next_video_calls_next_track(monkeypatch):
    assert _exec_media("next", "play next video", monkeypatch).calls == ["next_track"]


def test_exec_play_previous_video_calls_previous_track(monkeypatch):
    assert _exec_media("previous", "play previous video", monkeypatch).calls == ["previous_track"]


def test_exec_bare_next_video_calls_next_track(monkeypatch):
    assert _exec_media("next", "next video", monkeypatch).calls == ["next_track"]


# ── F: "play it"/"play that" are media plays, not offer acceptance ──

def test_play_it_is_media_play():
    d = _classify("play it")
    assert d.intent_type == IntentType.MEDIA_PLAY
    assert d.target == "it"


def test_play_that_is_media_play():
    d = _classify("play that")
    assert d.intent_type == IntentType.MEDIA_PLAY
    assert d.target == "that"


def test_show_it_still_offer_acceptance():
    d = _classify("show it")
    assert d.intent_type == IntentType.CONVERSATION
    assert d.action == "accept_offer"


def test_watch_it_still_offer_acceptance():
    d = _classify("watch it")
    assert d.intent_type == IntentType.CONVERSATION


def test_play_it_again_unchanged():
    d = _classify("play it again")
    assert d.intent_type == IntentType.MEDIA_PLAY
    assert d.target == "it again"


# ── G: bare "play again" in MediaManager.play ───────────────────────

class _FakeProvider:
    def __init__(self):
        self.calls = []
        self.last_query = ""

    def play(self, query, media_type=None, platform=None):
        self.calls.append(("play", query))
        self.last_query = query
        return MediaResult(
            success=True, message="Playing", player="youtube",
            session=MediaSession(player=PlayerType.YOUTUBE, state=MediaState.PLAYING),
        )


def _fresh_mm(monkeypatch):
    from mini_kio.media.media_manager import MediaManager
    MediaManager.reset_instance()
    mm = MediaManager.get_instance()
    mm._intelligence_adapter = None
    return mm


def test_play_again_no_last_interaction_is_truthful(monkeypatch):
    from mini_kio.core.runtime import drop_runtime_context
    drop_runtime_context("execution")
    mm = _fresh_mm(monkeypatch)
    result = mm.play("again")
    assert result.get("success") is True
    assert "no previous media" in result.get("message", "").lower()


def test_play_again_replays_last_successful_media(monkeypatch):
    from mini_kio.core.runtime import KioRuntime, remember_runtime_context
    rt = KioRuntime()
    monkeypatch.setattr("mini_kio.core.runtime._CURRENT_RUNTIME", rt)
    remember_runtime_context("execution", {"action": "play", "target": "believer", "success": True})

    mm = _fresh_mm(monkeypatch)
    fake = _FakeProvider()
    mm._get_provider = lambda name: fake

    result = mm.play("again")

    assert fake.last_query == "believer"
    assert result.get("success") is True
