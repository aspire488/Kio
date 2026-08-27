"""
Regression tests for the media-subsystem recovery fixes (RC1-RC7).

RC1: VerifiedConnector surfaces a clear "extension build out of date" error
     instead of a generic "non-state payload" when play-family scripts return
     empty payloads from a stale Chrome service worker.
RC2: _resolve_media_tab must never select an audible/active non-media tab
     (e.g. Telegram Web) as the media-control target.
RC3: "play again"/"play it again"/"watch again" replay the last successful
     PLAY interaction only — never a pause/resume/search.
RC4: "search again" preserves the controlled search_youtube action (R11)
     instead of degrading into a generic Google search.
RC7: direct playback prefers the best-matching search candidate over a blind
     first-result click.
"""
import asyncio
import pytest

from mini_kio.browser_connector.protocol import TabResult
from mini_kio.core.runtime import KioRuntime, remember_runtime_context
from mini_kio.core.context_manager import SessionContext
from mini_kio.media.media_state import MediaState, PlayerType


# ---------------------------------------------------------------------------
# Current-runtime regressions — target clauses and ad truthfulness
# ---------------------------------------------------------------------------

def test_context_intent_keeps_entity_when_trailing_provider_is_specified():
    """A target phrase must never replace the requested interview entity."""
    from mini_kio.media.intelligence.media_context_intelligence import MediaContextIntelligence

    intent = MediaContextIntelligence().extract_intent(
        "Play a Sam Altman interview on YouTube"
    )

    assert intent.topic == "sam altman interview"
    assert intent.search_query == "sam altman interview"


def test_context_intent_keeps_about_subject():
    """Topical clauses still retain their semantic subject."""
    from mini_kio.media.intelligence.media_context_intelligence import MediaContextIntelligence

    intent = MediaContextIntelligence().extract_intent(
        "Show me a documentary about coral reefs"
    )

    assert intent.topic == "coral reefs"


# ---------------------------------------------------------------------------
# RC1 — stale-build detection in VerifiedConnector
# ---------------------------------------------------------------------------

class _StaleRawConn:
    """Raw connector returning empty play payloads + a mismatched build."""

    def __init__(self, build="0.0.0", has_build_info=True):
        self._build = build
        self._has_build_info = has_build_info

    async def execute_script(self, tab_id, script, args=None):
        if script == "get_build_info":
            if self._has_build_info:
                return TabResult(success=True, message={"build": self._build})
            return TabResult(success=False, error="unknown script: get_build_info")
        return TabResult(success=True, message="")


def test_rc1_stale_build_reports_clear_error():
    from mini_kio.core.state_verification import VerifiedConnector

    async def run():
        vc = VerifiedConnector(_StaleRawConn(build="0.0.0"))
        res = await vc.execute_script(7, "play")
        assert res.success is False
        assert "out of date" in (res.error or ""), res.error
        assert "reload the KIO Chrome extension" in (res.error or ""), res.error
        assert "non-state payload" not in (res.error or ""), res.error

    asyncio.run(run())


def test_rc1_matching_build_keeps_generic_error():
    from mini_kio.core.state_verification import VerifiedConnector
    from mini_kio.browser_connector.build import EXTENSION_BUILD

    async def run():
        # A build matching the current expected fingerprint must fall through
        # to the generic "non-state payload" error, not the stale-build
        # diagnostic. Uses the single source of truth (BUG 13) so the test
        # never drifts from the production expectation.
        vc = VerifiedConnector(_StaleRawConn(build=EXTENSION_BUILD))
        res = await vc.execute_script(7, "play")
        assert res.success is False
        assert "non-state payload" in (res.error or ""), res.error

    asyncio.run(run())


# ---------------------------------------------------------------------------
# RC2 — _resolve_media_tab audible/active domain filter
# ---------------------------------------------------------------------------

class _FakeTabs:
    def __init__(self, tabs):
        self._tabs = tabs

    async def list_tabs(self):
        r = TabResult(success=True)
        r.tabs = self._tabs
        return r


def _tab(tab_id, url, audible=False, active=False, is_owned=False):
    t = TabResult(success=True)
    t.tab_id = tab_id
    t.url = url
    t.audible = audible
    t.active = active
    t.is_owned = is_owned
    return t


def test_rc2_audible_telegram_tab_never_selected():
    from mini_kio.browser_connector.connector import Connector

    conn = Connector(mock=True)
    fake = _FakeTabs([
        _tab(1, "https://web.telegram.org/a/#8935872380", audible=True, active=True),
        _tab(2, "https://www.youtube.com/results?search_query=x", audible=True),
    ])
    conn.list_tabs = fake.list_tabs

    async def run():
        tab = await conn._resolve_media_tab()
        assert tab is not None
        assert tab.tab_id == 2, "must skip the audible Telegram tab"

    asyncio.run(run())


def test_rc2_only_media_tabs_selected():
    from mini_kio.browser_connector.connector import Connector

    conn = Connector(mock=True)
    fake = _FakeTabs([
        _tab(1, "https://web.telegram.org/a/#8935872380", audible=True, active=True),
        _tab(2, "https://docs.google.com/document/d/1", audible=True),
    ])
    conn.list_tabs = fake.list_tabs

    async def run():
        tab = await conn._resolve_media_tab()
        assert tab is None, "no media-domain tab must resolve to None"

    asyncio.run(run())


# ---------------------------------------------------------------------------
# RC3/RC4 — verb-scoped again-replay in SessionContext.resolved_text
# ---------------------------------------------------------------------------

def _seed_runtime(monkeypatch, items):
    rt = KioRuntime()
    monkeypatch.setattr("mini_kio.core.runtime._CURRENT_RUNTIME", rt)
    for action, target, success in items:
        remember_runtime_context(
            "execution", {"action": action, "target": target, "success": success}
        )
    return rt


def _resolve(monkeypatch, text, items):
    _seed_runtime(monkeypatch, items)
    return SessionContext(session_id="rc34_test").resolved_text(text)


def test_rc3_play_again_never_replays_pause(monkeypatch):
    # Play X, Pause, then "play again" — must NOT resolve to "pause".
    resolved = _resolve(monkeypatch, "play again", [
        ("play", "doomsday trailer", True),
        ("pause", "", True),
    ])
    assert "doomsday trailer" in resolved, resolved
    assert "pause" not in resolved, resolved


def test_rc3_play_again_with_no_play_success_falls_through(monkeypatch):
    # Only a pause succeeded: "play again" must fall through untouched so
    # MediaManager._AGAIN can answer truthfully ("Nothing to replay").
    resolved = _resolve(monkeypatch, "play again", [
        ("pause", "", True),
    ])
    assert resolved.strip().lower() == "play again", resolved


def test_rc3_play_again_ignores_newer_search(monkeypatch):
    resolved = _resolve(monkeypatch, "play again", [
        ("play", "believer", True),
        ("search_web", "messi", True),
    ])
    assert "believer" in resolved, resolved


def test_rc4_search_again_preserves_youtube(monkeypatch):
    resolved = _resolve(monkeypatch, "search again", [
        ("search_youtube", "messi", True),
    ])
    assert "messi" in resolved, resolved
    assert "youtube" in resolved, "must keep the controlled YouTube search"
    assert resolved.strip().lower() == "search messi in youtube", resolved


def test_rc4_search_again_google_stays_google(monkeypatch):
    resolved = _resolve(monkeypatch, "search again", [
        ("search_web", "weather", True),
    ])
    assert "weather" in resolved, resolved
    assert "youtube" not in resolved, resolved


# ---------------------------------------------------------------------------
# RC7 — candidate-based playback selection
# ---------------------------------------------------------------------------

@pytest.fixture(autouse=True)
def _stub_api_discovery(monkeypatch):
    """RC8: these tests exercise the controlled scrape path deterministically.
    The live YouTube Data API (real key, real network) must not influence them."""
    from mini_kio.media.providers import youtube_provider as yp
    monkeypatch.setattr(yp.YouTubeProvider, "_api_search_candidates", lambda self, q: [])


class _CandidateConn:
    def __init__(self, candidates, loaded_video_id="best"):
        self._candidates = candidates
        self._loaded_video_id = loaded_video_id
        self.navigated = None
        self.calls = []

    def is_connected(self):
        return True

    async def open_tab(self, url):
        self.calls.append(("open_tab", url))
        self.navigated = url
        r = TabResult(success=True)
        r.tab = type("_T", (), {"tab_id": 42})()
        return r

    async def execute_script(self, tab_id, script, args=None):
        self.calls.append(("execute_script", script))
        if script == "search_results":
            return TabResult(success=True, message=self._candidates)
        if script == "youtube_bootstrap":
            return TabResult(success=True, message="navigating")
        if script == "get_page_info":
            return TabResult(success=True, message={
                "url": f"https://www.youtube.com/watch?v={self._loaded_video_id}", "title": "X",
            })
        if script == "play":
            return TabResult(success=True, message={
                "status": "playing", "player_status": "playing",
                "paused": False, "currentTime": 1.0, "duration": 120.0,
            })
        if script == "get_player_state":
            return TabResult(success=True, message={"playerState": -1})
        raise AssertionError(f"unexpected script {script!r}")


def test_rc7_play_prefers_best_matching_candidate(monkeypatch):
    from mini_kio.media.providers import youtube_provider as yp
    monkeypatch.setattr(yp.time, "sleep", lambda s: None)

    # RC8 identity gate: the fake connector must report the SAME video ID that
    # the candidate selection navigated to, proving the loaded page matches the
    # selected candidate.
    conn = _CandidateConn(
        [
            {"title": "Messi goals 2026", "url": "https://www.youtube.com/watch?v=WRONG",
             "video_id": "WRONG"},
            {"title": "Doomsday - Official Trailer (2024)", "url": "https://www.youtube.com/watch?v=BEST",
             "video_id": "BEST"},
            {"title": "Random cat video", "url": "https://www.youtube.com/watch?v=CAT",
             "video_id": "CAT"},
        ],
        loaded_video_id="BEST",
    )
    prov = yp.YouTubeProvider(conn=conn)
    result = prov.play("doomsday trailer")

    assert result.success is True, result.error
    assert conn.navigated and "watch?v=BEST" in conn.navigated, (
        f"must navigate to the best-matching candidate, got {conn.navigated}"
    )


def test_rc8_identity_gate_fails_on_wrong_loaded_video(monkeypatch):
    """RC8: if Chrome loads a DIFFERENT video than the selected candidate,
    playback must be reported as a truthful failure — never a success."""
    from mini_kio.media.providers import youtube_provider as yp
    monkeypatch.setattr(yp.time, "sleep", lambda s: None)

    conn = _CandidateConn(
        [
            {"title": "Doomsday - Official Trailer (2024)", "url": "https://www.youtube.com/watch?v=BEST",
             "video_id": "BEST"},
        ],
        loaded_video_id="SOMETHING_ELSE",
    )
    prov = yp.YouTubeProvider(conn=conn)
    result = prov.play("doomsday trailer")

    assert result.success is False, "wrong video must never report success"
    # Media contract: the failure is reported naturally — internal video IDs
    # and URLs must not leak into the user-facing text.
    err = (result.error or "").lower()
    assert "couldn't start" in err, result.error
    assert "watch?v=" not in err and "id=" not in err, (
        f"internal video id leaked into failure text: {result.error!r}"
    )


def test_rc7_no_relevant_candidate_falls_back_to_bootstrap(monkeypatch):
    from mini_kio.media.providers import youtube_provider as yp
    monkeypatch.setattr(yp.time, "sleep", lambda s: None)

    # No relevant candidate: selection must return None and the flow falls
    # back to youtube_bootstrap. No candidate ID was chosen, so the identity
    # gate is not armed (nothing to verify against).
    conn = _CandidateConn([
        {"title": "Messi goals 2026", "url": "https://www.youtube.com/watch?v=WRONG",
         "video_id": "WRONG"},
    ])
    prov = yp.YouTubeProvider(conn=conn)
    result = prov.play("doomsday trailer")

    assert result.success is True, result.error
    # bootstrap path was used (no candidate scored > 0)
    assert any(s == "youtube_bootstrap" for _, s in conn.calls), conn.calls


# ---------------------------------------------------------------------------
# RC9 — unresolved pronoun truthfulness ("play it" must never play the
# literal word "it", which registers a garbage entity that poisons later
# pronoun resolutions)
# ---------------------------------------------------------------------------

def test_rc9_unresolved_pronoun_never_plays_literal_word(monkeypatch):
    from mini_kio.media.media_manager import MediaManager
    mm = MediaManager.get_instance()
    MediaManager.reset_instance()
    mm = MediaManager()

    # No entity memory, no runtime play context: "play it" must not fall
    # through to a literal YouTube search for "it".
    result = mm.play("it")
    assert result.get("success") is True, result
    assert "previous media" in result.get("message", "").lower(), result


def test_rc9_unresolved_pronoun_resolves_last_entity(monkeypatch):
    from mini_kio.media.media_manager import MediaManager
    mm = MediaManager()

    # Seed a last-played interaction through the runtime context (same source
    # G4 uses) — "play it" must resolve to it, not the literal word.
    from mini_kio.core.runtime import KioRuntime, remember_runtime_context
    rt = KioRuntime()
    monkeypatch.setattr("mini_kio.core.runtime._CURRENT_RUNTIME", rt)
    remember_runtime_context("execution", {
        "action": "play", "target": "interstellar trailer", "success": True,
    })

    # The pronoun must resolve to the seeded last play (the fake env has no
    # connector, so playback itself fails — that is fine: what matters is that
    # "it" was NOT attempted as the literal search target). Assert resolution:
    # the attempted target became "interstellar trailer", never the literal
    # word "it".
    result = mm.play("it")
    msg = result.get("message", "") or ""
    assert "interstellar" in msg.lower(), msg
    assert " play it" not in msg.lower() and not msg.lower().endswith("it"), msg


# ---------------------------------------------------------------------------
# RC10 — entity-resolution boundary: explicit media queries must NEVER be
# reinterpreted as mood/activity/variant references (the "lm game trailer" →
# "gaming music playlist" hijack), and candidate selection must reject
# audio-only content when a visual content type (trailer/review/...) is
# requested.
# ---------------------------------------------------------------------------

def test_rc10_explicit_entity_query_never_hijacked():
    """A fresh entity query containing a coincidental activity word ("game")
    must NOT resolve as an activity reference."""
    from mini_kio.media.intelligence.media_reference_resolver import (
        MediaReferenceResolver, ReferenceType,
    )
    from mini_kio.media.media_context import MediaContext

    r = MediaReferenceResolver(MediaContext())
    for q in ("lm game trailer", "play lm game trailer", "brand new day",
              "messi interview", "interstellar trailer",
              "avengers doomsday trailer"):
        res = r.resolve(q)
        assert res.success is False, f"{q!r} must not resolve as a reference"
        assert res.reference_type == ReferenceType.UNKNOWN, (
            f"{q!r} resolved as {res.reference_type.value}"
        )


def test_rc10_bare_references_still_resolve():
    from mini_kio.media.intelligence.media_reference_resolver import (
        MediaReferenceResolver, ReferenceType,
    )
    from mini_kio.media.media_context import MediaContext

    r = MediaReferenceResolver(MediaContext())
    assert r.resolve("play chill music").reference_type == ReferenceType.MOOD
    assert r.resolve("play gym music").reference_type == ReferenceType.ACTIVITY


def test_rc10_probe_mode_has_no_side_effects(monkeypatch):
    """handle(query, execute=False) must not register entities or run
    retrieval — the old code registered the hijacked "gaming music playlist"
    entity into memory even when only probing."""
    from mini_kio.media.intelligence.integration_adapter import MediaIntelligenceAdapter
    from mini_kio.media.intelligence.media_reference_resolver import (
        MediaReferenceResolver,
    )
    from mini_kio.media.media_context import MediaContext

    ctx = MediaContext()
    # A bare reference with no memory: variant/pronoun returns UNKNOWN, but
    # a resolution with query_override must not retrieve or register in probe
    # mode. Simulate by stubbing the resolver to return a variant override.
    class _FakeResolver:
        def resolve(self, utterance):
            from mini_kio.media.intelligence.media_reference_resolver import (
                ReferenceResolution, ReferenceType, VariantType,
            )
            return ReferenceResolution(
                reference_type=ReferenceType.VARIANT,
                resolved_entity=None,
                confidence=0.9,
                query_override="believer remix",
                variant=VariantType.REMIX,
            )

    adapter = MediaIntelligenceAdapter(retrieval_fn=lambda *a, **k: None)
    adapter._resolver = _FakeResolver()
    adapter._safe_retrieve = lambda *a, **k: (_ for _ in ()).throw(
        AssertionError("probe must not retrieve")
    )

    res = adapter.handle("play the remix", execute=False)
    assert res.source == "resolver", res
    assert res.subject == "believer remix", res.subject
    # No entity registered, no retrieval fired.
    assert adapter._mem.get_last_entity() is None


def test_rc10_trailer_query_rejects_audio_only_candidate():
    """For a "trailer" request, an official film trailer must outrank its own
    soundtrack/theme upload (live proof: "I'M Game Trailer Theme - Malayalam"
    from a "- Topic" auto channel beat the Wayfarer Films official trailer)."""
    from mini_kio.media.providers.youtube_provider import _score_candidate

    official = _score_candidate(
        "I'M GAME TRAILER (Malayalam) | Dulquer Salmaan | Nahas Hidhayath | Wayfarer Films Music",
        "https://www.youtube.com/watch?v=OFFICIAL",
        "lm game trailer",
        channel="Wayfarer Films Music",
        media_type="trailer",
    )
    theme = _score_candidate(
        "I'M Game Trailer Theme - Malayalam",
        "https://www.youtube.com/watch?v=THEME",
        "lm game trailer",
        channel="Jakes Bejoy - Topic",
        media_type="trailer",
    )
    emoji_reupload = _score_candidate(
        "I'm Game - Trailer 🥵🔥 Latest Update | Dulquer Salmaan",
        "https://www.youtube.com/watch?v=REUPLOAD",
        "lm game trailer",
        channel="WonDer BoSs Cafe",
        media_type="trailer",
    )

    assert official > theme, f"official({official}) must beat theme({theme})"
    assert official > emoji_reupload, (
        f"official({official}) must beat emoji reupload({emoji_reupload})"
    )


def test_rc10_no_pipe_penalty_for_official_titles():
    """A standalone pipe chain ("Title | Studio | Cast | Channel") is the
    canonical official-upload format and must NOT be penalized (RC9's own
    design comment states pipes are not penalized; a stale standalone rule
    made the official I'M GAME trailer lose to its own soundtrack)."""
    from mini_kio.media.providers.youtube_provider import _score_candidate

    s1 = _score_candidate(
        "I'M GAME TRAILER (Malayalam) | Dulquer Salmaan | Nahas Hidhayath | Wayfarer Films Music",
        "https://www.youtube.com/watch?v=A", "lm game trailer",
        channel="Wayfarer Films Music", media_type="trailer",
    )
    # Same title with a dash-chain instead of pipes: dash chains ARE the
    # multi-subject mashup signature and should score no higher.
    s2 = _score_candidate(
        "I'M GAME TRAILER - Dulquer Salmaan - Nahas Hidhayath - Wayfarer Films Music",
        "https://www.youtube.com/watch?v=B", "lm game trailer",
        channel="Wayfarer Films Music", media_type="trailer",
    )
    assert s1 > s2, f"pipe title({s1}) must outscore dash-chain title({s2})"
