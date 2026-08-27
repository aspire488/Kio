"""
test_new_capability_deltas.py

Focused tests for the capability-delta batch:
  1. Release watcher (watch store, baseline-notify logic, delivery push)
  2. Research thread (brief persist / recall / continue-diff)
  3. Project summary (GitHub meta + PyPI)
  4. Media retrieval probe repair (_try_media_providers)

Network is stubbed at the same seams the owners use. Tests assert ROUTE and
RESULT shape + the notify/baseline contract — never live data.
"""

import json

from mini_kio.backend.repositories.watch_repository import WatchRepository
from mini_kio.intelligence.retrieval_router import RetrievalResult, RetrievalRouter
from mini_kio.media.media_session import MediaCandidate, MediaResult
from mini_kio.monitoring import watches as watch_mod
from mini_kio.research import briefs as research_mod

# ── fixtures ──────────────────────────────────────────────────────────────────

GITHUB_ATOM_V2 = b"""<?xml version="1.0" encoding="UTF-8"?>
<feed xmlns="http://www.w3.org/2005/Atom">
  <title>Release notes from openai/openai</title>
  <entry>
    <title>v1.2.0</title>
    <link href="https://github.com/openai/openai/releases/tag/v1.2.0"/>
    <published>2026-08-10T00:00:00Z</published>
  </entry>
  <entry>
    <title>v1.1.0</title>
    <link href="https://github.com/openai/openai/releases/tag/v1.1.0"/>
    <published>2026-07-01T00:00:00Z</published>
  </entry>
</feed>"""

GITHUB_ATOM_V3 = b"""<?xml version="1.0" encoding="UTF-8"?>
<feed xmlns="http://www.w3.org/2005/Atom">
  <title>Release notes from openai/openai</title>
  <entry>
    <title>v1.3.0</title>
    <link href="https://github.com/openai/openai/releases/tag/v1.3.0"/>
    <published>2026-08-16T00:00:00Z</published>
  </entry>
  <entry>
    <title>v1.2.0</title>
    <link href="https://github.com/openai/openai/releases/tag/v1.2.0"/>
    <published>2026-08-10T00:00:00Z</published>
  </entry>
</feed>"""

GITHUB_REPO_JSON = json.dumps({
    "description": "A test repo", "language": "Python",
    "stargazers_count": 42, "message": None,
}).encode("utf-8")

GITHUB_ISSUES_JSON = json.dumps([
    {"title": "Fix the bug", "number": 1},
    {"title": "Add feature", "number": 2},
    {"title": "WIP PR", "number": 3, "pull_request": {"url": "x"}},
]).encode("utf-8")

PYPI_JSON = json.dumps({
    "info": {"version": "9.9.9", "summary": "Test package"},
}).encode("utf-8")


class _FakeYT:
    def __init__(self, ok=True):
        self.ok = ok

    def search(self, query):
        if not self.ok:
            return MediaResult(success=False, error="offline", player="youtube")
        return MediaResult(
            success=True,
            message="Found on YouTube: Some Song",
            candidates=[MediaCandidate(title="Some Song", url="https://www.youtube.com/watch?v=ABC123", provider="youtube")],
            player="youtube",
        )


class _FakeEvidence:
    def __init__(self, findings):
        self._findings = findings

    def retrieve_evidence(self, query, max_results=4):
        return self._findings


def _stub_http(monkeypatch, route):
    # most-specific fragment first so "/repos/o/r" never shadows
    # "/repos/o/r/issues?..."
    ordered = sorted(route.items(), key=lambda kv: len(kv[0]), reverse=True)

    def _fake(url, timeout=6):
        for frag, payload in ordered:
            if frag in url:
                return payload
        return None
    monkeypatch.setattr("mini_kio.core.utilities._http_get_bytes", _fake)


# ── 1. release watcher ───────────────────────────────────────────────────────

def test_looks_like_watch_routes():
    assert watch_mod.looks_like_watch("watch openai/openai for new releases")
    assert watch_mod.looks_like_watch("watch requests")
    assert watch_mod.looks_like_watch("stop watching requests")
    assert watch_mod.looks_like_watch("unwatch fastapi")
    assert watch_mod.looks_like_watch("what am I watching")
    assert not watch_mod.looks_like_watch("what's the weather in paris")
    assert not watch_mod.looks_like_watch("latest releases of requests")
    # media offer-acceptance must never classify as a watch
    assert not watch_mod.looks_like_watch("watch it")
    assert not watch_mod.looks_like_watch("watch this")
    assert not watch_mod.looks_like_watch("watch that")


def test_watch_add_baselines(monkeypatch):
    _stub_http(monkeypatch, {"releases.atom": GITHUB_ATOM_V2})
    res = watch_mod.watch_answer("watch openai/openai for new releases")
    assert res["success"] is True
    assert res["action"] == "add"
    assert res["target"] == "openai/openai"
    assert res["kind"] == "github"
    assert "notify" in res["message"]
    assert res["baseline"].startswith("v1.2.0|")


def test_watch_remove_and_list(monkeypatch):
    _stub_http(monkeypatch, {"releases.atom": GITHUB_ATOM_V2})
    watch_mod.watch_answer("watch openai/openai for new releases")
    lst = watch_mod.watch_answer("what am I watching")
    assert lst["success"] is True
    assert any(r["target"] == "openai/openai" for r in lst["watches"])
    rm = watch_mod.watch_answer("stop watching openai/openai")
    assert rm["success"] is True
    lst2 = watch_mod.watch_answer("what am I watching")
    assert all(r["target"] != "openai/openai" for r in lst2["watches"])


def test_poll_notifies_only_on_newer_release(monkeypatch):
    _stub_http(monkeypatch, {"releases.atom": GITHUB_ATOM_V2})
    watch_mod.watch_answer("watch openai/openai for new releases")

    pushed = []
    monkeypatch.setattr(watch_mod, "send_telegram_message",
                        lambda chat, text: pushed.append((chat, text)) or True)
    # Same newest item -> no notification, baseline unchanged
    res = watch_mod.poll_watches()
    assert res["checked"] >= 1
    assert res["notified"] == 0

    # A newer release appears -> exactly one push, baseline advances
    _stub_http(monkeypatch, {"releases.atom": GITHUB_ATOM_V3})
    res2 = watch_mod.poll_watches()
    assert res2["notified"] == 1
    assert any("v1.3.0" in text for _c, text in pushed)
    # Second poll sees no further change
    res3 = watch_mod.poll_watches()
    assert res3["notified"] == 0
    # clean up so the shared in-memory DB doesn't leak this watch into other tests
    watch_mod._repo.deactivate("openai/openai", "terminal")


def test_poll_never_spams_existing_releases(monkeypatch):
    _stub_http(monkeypatch, {"releases.atom": GITHUB_ATOM_V2})
    # A watch whose baseline failed at creation must baseline on first poll,
    # not dump every existing release at the user.
    repo = WatchRepository()
    repo.add("spamtarget/openai", "github", "tg-spam-chat", last_seen_key=None)
    pushed = []
    monkeypatch.setattr(watch_mod, "send_telegram_message",
                        lambda chat, text: pushed.append(text) or True)
    res = watch_mod.poll_watches()
    assert res["notified"] == 0
    assert pushed == []
    repo.deactivate("spamtarget/openai", "tg-spam-chat")


def test_send_telegram_no_token_returns_false(monkeypatch):
    monkeypatch.setattr(watch_mod, "TELEGRAM_TOKEN", "")
    assert watch_mod.send_telegram_message("123", "hello") is False


# ── 2. research thread ───────────────────────────────────────────────────────

def test_looks_like_research_routes():
    assert research_mod.looks_like_research("research quantum computing")
    assert research_mod.looks_like_research("research brief on quantum computing")
    assert research_mod.looks_like_research("continue research on quantum computing")
    assert research_mod.looks_like_research("what did I research")
    assert not research_mod.looks_like_research("research")
    assert not research_mod.looks_like_research("what's the weather in paris")


def test_research_brief_persist_recall_continue(monkeypatch):
    f1 = RetrievalResult(title="Paper A", summary="Summary A " * 6, source="arXiv",
                         confidence=0.8, entity="Paper A", url="https://x.org/a",
                         topic=None, published_date="2026-08-01")
    monkeypatch.setattr(research_mod, "_router", _FakeEvidence([f1]))

    res = research_mod.research_answer("research quantum computing",
                                       decision=_FakeDecision("sess-1"))
    assert res["success"] is True
    assert res["action"] == "research"
    assert res["source_count"] == 1
    assert res["saved"] is True
    assert "Paper A" in res["message"]

    brief = research_mod.research_answer("research brief on quantum computing",
                                         decision=_FakeDecision("sess-1"))
    assert brief["success"] is True
    assert brief["action"] == "brief"
    assert "Paper A" in brief["message"]

    # continue with the same evidence -> nothing new
    cont = research_mod.research_answer("continue research on quantum computing",
                                        decision=_FakeDecision("sess-1"))
    assert cont["action"] == "continue"
    assert cont["new_count"] == 0

    # continue after a new source appeared -> 1 new finding
    f2 = RetrievalResult(title="Paper B", summary="Summary B " * 6, source="arXiv",
                         confidence=0.7, entity="Paper B", url="https://x.org/b",
                         topic=None, published_date="2026-08-15")
    monkeypatch.setattr(research_mod, "_router", _FakeEvidence([f1, f2]))
    cont2 = research_mod.research_answer("continue research on quantum computing",
                                         decision=_FakeDecision("sess-1"))
    assert cont2["new_count"] == 1
    assert "Paper B" in cont2["message"]


def test_research_topics_and_other_session_isolation():
    research_mod._repo.upsert("sess-x", "top-a", "topic a", "brief a", [])
    rows = research_mod.research_answer("what did I research", decision=_FakeDecision("sess-x"))
    assert rows["success"] is True
    assert any(r["topic"] == "topic a" for r in rows["topics"])
    # another session sees nothing
    rows2 = research_mod.research_answer("what did I research", decision=_FakeDecision("sess-y"))
    assert rows2["topics"] == []


# ── 3. project summary ───────────────────────────────────────────────────────

def test_looks_like_project_summary_routes():
    assert looks_like_project("summarize the project openai/openai")
    assert looks_like_project("summarize project requests")
    assert not looks_like_project("what's the latest version of requests")
    assert not looks_like_project("research openai")


def test_project_answer_github(monkeypatch):
    _stub_http(monkeypatch, {
        "/repos/openai/openai": GITHUB_REPO_JSON,
        "releases.atom": GITHUB_ATOM_V2,
        "issues?state=open&per_page=5": GITHUB_ISSUES_JSON,
    })
    res = project_answer("summarize the project openai/openai")
    assert res["success"] is True
    assert res["type"] == "project"
    assert res["project"] == "openai/openai"
    assert "Python" in res["message"]
    assert "v1.2.0" in res["message"]
    assert "Fix the bug" in res["message"]
    # PRs are not counted as issues
    assert "WIP PR" not in res["message"]


def test_project_answer_pypi(monkeypatch):
    _stub_http(monkeypatch, {"pypi.org/pypi/requests/json": PYPI_JSON})
    res = project_answer("summarize the project requests")
    assert res["success"] is True
    assert res["project"] == "requests"
    assert res["version"] == "9.9.9"


def test_project_answer_missing(monkeypatch):
    _stub_http(monkeypatch, {"/repos/nope/nope": json.dumps({"message": "Not Found"}).encode()})
    res = project_answer("summarize the project nope/nope")
    assert res["success"] is False


# ── 4. media retrieval probe repair ──────────────────────────────────────────

def test_media_probe_uses_new_search_contract(monkeypatch):
    monkeypatch.setattr("mini_kio.media.providers.youtube_provider.YouTubeProvider", _FakeYT)
    router = RetrievalRouter()
    res = router._try_media_providers("play some song", None)
    assert res is not None
    assert res.url == "https://www.youtube.com/watch?v=ABC123"
    assert "Some Song" in res.title


def test_media_probe_graceful_when_unavailable(monkeypatch):
    monkeypatch.setattr("mini_kio.media.providers.youtube_provider.YouTubeProvider", _FakeYT(ok=False))
    router = RetrievalRouter()
    assert router._try_media_providers("play some song", None) is None


def test_media_play_honest_fallback_no_connector(monkeypatch):
    # No connector object at all (connector disabled) must route to the honest
    # browser fallback — never a fake PLAYING, never a bare failure.
    from mini_kio.core import config
    from mini_kio.media.media_state import MediaState
    from mini_kio.media.providers.youtube_provider import YouTubeProvider

    monkeypatch.setattr(config, "BROWSER_CONNECTOR_ENABLED", False)
    opened = []
    monkeypatch.setattr(
        "mini_kio.core.browser_operator.open_url",
        lambda url, **kw: opened.append(url) or {"success": True, "url": url},
    )
    monkeypatch.setattr(
        "mini_kio.media.providers.youtube_provider._resolve_search_to_watch_url",
        lambda query: "https://www.youtube.com/watch?v=ABC123",
    )

    prov = YouTubeProvider()
    prov._get_conn = lambda: None
    res = prov.play("interstellar trailer", media_type="video", platform="youtube")
    assert res.success is True
    assert res.session is not None and res.session.state == MediaState.IDLE
    assert opened == ["https://www.youtube.com/watch?v=ABC123"]
    assert "can't verify playback" in res.message


def test_media_play_configured_connector_missing_is_honest_error(monkeypatch):
    # Connector configured (BROWSER_CONNECTOR_ENABLED=true) but no connector
    # object: report the unavailable connector, do not silently open a browser.
    from mini_kio.core import config
    from mini_kio.media.providers.youtube_provider import YouTubeProvider

    monkeypatch.setattr(config, "BROWSER_CONNECTOR_ENABLED", True)
    prov = YouTubeProvider()
    prov._get_conn = lambda: None
    res = prov.play("interstellar trailer", media_type="video", platform="youtube")
    assert res.success is False
    assert "Connector" in (res.error or "")


class _FakeDecision:
    def __init__(self, session_id):
        self.session_id = session_id
        self.channel = "telegram"
        self.user_id = 12345


from mini_kio.core.utilities import looks_like_project_summary as looks_like_project  # noqa: E402
from mini_kio.core.utilities import project_answer  # noqa: E402