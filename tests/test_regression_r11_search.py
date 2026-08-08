"""
R11 regression tests: YouTube search must stay a controlled search.

Before R11, youtube_provider.search() aliased play(), so "search youtube X"
triggered the full bootstrap/autoplay loop and accept_offer (which calls
prov.search() for candidates then plays the best) played twice. Search must
route through the controlled browser connector and return candidates, never
start playback.
"""
from mini_kio.browser_connector.protocol import TabResult


class _FakeConn:
    def __init__(self):
        self.calls = []
        self._id = 7

    def is_connected(self):
        return True

    async def open_tab(self, url):
        self.calls.append(("open_tab", url))
        return _OkResult(tab=_Tab(self._id))

    async def execute_script(self, tab_id, script, args=None):
        self.calls.append(("execute_script", tab_id, script))
        if script == "eval":
            return TabResult(success=True, message=[
                {"title": "Believer - Imagine Dragons", "url": "https://www.youtube.com/watch?v=7wtfhZwyrcc", "video_id": "7wtfhZwyrcc"},
                {"title": "Believer - Imagine Dragons (Lyrics)", "url": "https://www.youtube.com/watch?v=wGB0xDDDEFAULT", "video_id": "wGB0xDDDEFAULT"},
            ])
        raise AssertionError(f"unexpected script {script!r}")

    async def close_tab(self, tab_id):
        self.calls.append(("close_tab", tab_id))
        return _OkResult()


class _Tab:
    def __init__(self, tab_id):
        self.tab_id = tab_id


class _OkResult:
    def __init__(self, tab=None):
        self.success = True
        self.tab = tab


def _provider(conn):
    from mini_kio.media.providers.youtube_provider import YouTubeProvider
    return YouTubeProvider(conn=conn)


def test_search_returns_candidates_not_playback():
    conn = _FakeConn()
    prov = _provider(conn)

    result = prov.search("believer imagine dragons")

    assert result.success is True
    assert result.candidates, "search must return scraped candidates"
    assert "7wtfhZwyrcc" in result.candidates[0].url
    assert not result.session, "a search must not create a playback session"
    assert not result.candidates[0].url.endswith("/watch"), "search must not navigate to a player"


def test_search_goes_through_controlled_connector():
    conn = _FakeConn()
    prov = _provider(conn)

    prov.search("believer imagine dragons")

    assert any(action == "open_tab" for action, *_ in conn.calls)
    assert any(
        args[2] == "eval" for args in conn.calls if args[0] == "execute_script"
    ), "search must scrape results through the connector, not webbrowser.open"


def test_search_never_invokes_play():
    conn = _FakeConn()
    prov = _provider(conn)

    prov.search("believer imagine dragons")

    assert not any(
        args[2] in ("play", "youtube_bootstrap")
        for args in conn.calls if args[0] == "execute_script"
    ), "search must not start the bootstrap/play loop"
