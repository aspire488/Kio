"""
R3 regression tests: "again"-suffixed variants ("search again", "play it
again", "watch again") must resolve through G4 to the last successful
interaction, matching the P1.2-validated bare "again" path.

G4 now runs before G1 so media verbs with an "again" suffix reach it instead
of the playback passthrough; G1/G2/G3/S1/S2 blocks are unchanged.
"""
import pytest
from mini_kio.core.runtime import KioRuntime, remember_runtime_context


@pytest.fixture
def seeded_runtime(monkeypatch):
    def _seed(action="search_web", target="Interstellar", success=True):
        rt = KioRuntime()
        monkeypatch.setattr("mini_kio.core.runtime._CURRENT_RUNTIME", rt)
        remember_runtime_context(
            "execution", {"action": action, "target": target, "success": success}
        )
        return rt

    return _seed


def _resolve(text, seeded_runtime, **value):
    from mini_kio.core.context_manager import SessionContext

    seeded_runtime(**value)
    ctx = SessionContext(session_id="r3_again_suffix_test")
    return ctx.resolved_text(text)


def test_bare_again_repeats_last_success(seeded_runtime):
    resolved = _resolve("again", seeded_runtime, action="search_web", target="Interstellar")
    assert "Interstellar" in resolved


def test_search_again_repeats_last_success(seeded_runtime):
    resolved = _resolve("search again", seeded_runtime, action="search_web", target="Interstellar")
    assert "Interstellar" in resolved
    assert resolved.strip().lower() != "search again"


def test_play_it_again_repeats_last_success(seeded_runtime):
    resolved = _resolve("play it again", seeded_runtime, action="play", target="believer")
    assert "believer" in resolved


def test_play_again_repeats_last_success(seeded_runtime):
    resolved = _resolve("play again", seeded_runtime, action="play", target="believer")
    assert "believer" in resolved


def test_watch_again_repeats_last_success(seeded_runtime):
    resolved = _resolve("watch again", seeded_runtime, action="play", target="believer")
    assert "believer" in resolved


def test_targeted_play_again_keeps_target(seeded_runtime):
    # "play messi again" has a real target — must NOT be swallowed by G4.
    resolved = _resolve("play messi again", seeded_runtime, action="play", target="believer")
    assert resolved == "play messi again"


def test_g1_media_passthrough_unchanged(seeded_runtime):
    from mini_kio.core.context_manager import SessionContext

    seeded_runtime(action="search_web", target="Interstellar")
    ctx = SessionContext(session_id="r3_g1_test")
    # G1 still passes through plain playback verbs untouched.
    assert ctx.resolved_text("play jazz") == "play jazz"
    assert ctx.resolved_text("watch it") == "watch it"
