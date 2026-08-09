"""
test_context_response_quality.py — Context State Refinement

Verifies the canonical contextual desktop-state capability:
- semantic family classification (what's open / what am i using / what's
  running / show open apps / ...) — deterministic, never an LLM fallback
- knowledge questions still route to knowledge/conversation
- "KIO"-prefixed and politeness variants route identically
- composition: app identity + tab detail + browser host + native apps +
  KIO provenance + active state; no raw URLs / :: / pids / internal ids
- truthful empty / partial / unreadable states
- no fabrication, no side effects from reading state
"""

import pytest

from mini_kio.core.target_ref import webapp_name_from_url, display_target_name
from mini_kio.core.pipeline import Pipeline, _ExecutionCoordinator, _ResponseComposer
from mini_kio.core.pipeline.types import IntentType
from mini_kio.core.desktop_state import compose_desktop_state
from mini_kio.browser_connector.protocol import OwnedTab, TabResult


# ---------------------------------------------------------------------------
# URL -> canonical web-app identity
# ---------------------------------------------------------------------------

@pytest.mark.parametrize("url,expected", [
    ("https://chat.openai.com/c/abc123", "chatgpt"),
    ("https://chat.openai.com", "chatgpt"),
    ("https://chatgpt.com/c/abc123", "chatgpt"),
    ("https://web.telegram.org/a/#123", "telegram"),
    ("https://www.youtube.com/watch?v=dQw4w9WgXcQ", "youtube"),
    ("https://youtube.com", "youtube"),
    ("https://web.whatsapp.com", "whatsapp"),
    ("https://gemini.google.com/app", "gemini"),
    ("https://claude.ai/new", "claude"),
    ("https://github.com/owner/repo", "github"),
    ("https://www.instagram.com/", "instagram"),
])
def test_webapp_name_from_url_known(url, expected):
    assert webapp_name_from_url(url) == expected


@pytest.mark.parametrize("url", [
    "", None, "about:blank",
    "https://example.com/some/page",
    "https://unknown-site-1234.example.net/x",
    "file:///c:/temp/x.txt",
])
def test_webapp_name_from_url_unknown(url):
    # Arbitrary sites / empty / non-http must never fabricate an identity.
    assert webapp_name_from_url(url) is None


@pytest.mark.parametrize("url", [
    # Lookalike / spoof domains must never classify as a known app.
    "https://youtube.com.evil.com",
    "https://notyoutube.com",
    "https://evil-chat.openai.com",
    "https://evil.com/chat.openai.com",
    "https://chatgpt.com.evil.net",
    "https://telegram.org.evil.io",
])
def test_webapp_name_from_url_spoof_domains(url):
    assert webapp_name_from_url(url) is None


@pytest.mark.parametrize("key,expected", [
    ("chatgpt", "ChatGPT"),
    ("telegram", "Telegram"),
    ("youtube", "YouTube"),
    ("whatsapp", "WhatsApp"),
])
def test_brand_casing(key, expected):
    assert display_target_name(key) == expected


# ---------------------------------------------------------------------------
# Desktop-state composition (pure: fake connector + injected native windows)
# ---------------------------------------------------------------------------

class _FakeConn:
    """Minimal connector stand-in: connected flag + async list_tabs."""

    def __init__(self, tabs=None, connected=True, error=False):
        self._tabs = tabs or []
        self._connected = connected
        self._error = error

    def is_connected(self):
        return self._connected

    async def list_tabs(self):
        if self._error:
            raise RuntimeError("connector exploded")
        return TabResult(success=True, tabs=self._tabs)


def _tab(url, title="", is_owned=False, active=False):
    return OwnedTab(tab_id=hash(url) % 10000, url=url, title=title,
                    is_owned=is_owned, active=active)


def _win(app="OpenCode", base="opencode", title="", pid=1, foreground=False,
         browser=False, owned=False):
    return {"app": app, "base": base, "title": title, "pid": pid,
            "is_foreground": foreground, "is_browser_host": browser,
            "is_kio_owned": owned}


_LIVE = object()  # sentinel: run live observation inside compose_desktop_state


def _compose(tabs=None, connected=True, error=False, native=None, use_conn=True):
    # Deterministic default: no native windows, so tests never depend on the
    # machine's live desktop. Pass native=_LIVE to exercise the live
    # observation path (with observe_native_windows monkeypatched).
    # use_conn=False drives the browser-runtime fallback path (conn=None).
    conn = _FakeConn(tabs, connected=connected, error=error) if use_conn else None
    if native is None:
        native = []
    kwargs = {} if native is _LIVE else {"native_windows": native}
    return compose_desktop_state(conn, **kwargs)


def test_identity_and_detail_combined():
    tabs = [
        _tab("https://chat.openai.com/c/1", "KIO Commit Review Prompt"),
        _tab("https://web.telegram.org/a", "KIO Assistant"),
        _tab("https://www.youtube.com/watch?v=abc", "(17) Dangal | Official Trailer"),
    ]
    msg = _compose(tabs)["message"]
    assert "Open right now:" in msg
    assert "• Chrome — ChatGPT — KIO Commit Review Prompt" in msg
    assert "• Chrome — Telegram — KIO Assistant" in msg
    assert "• Chrome — YouTube — (17) Dangal | Official Trailer" in msg


def test_identity_alone_when_title_repeats_identity():
    tabs = [_tab("https://chat.openai.com/c/1", "ChatGPT")]
    msg = _compose(tabs)["message"]
    assert "• Chrome — ChatGPT" in msg
    assert "ChatGPT — ChatGPT" not in msg  # never redundant


def test_plain_title_when_no_identity():
    tabs = [_tab("https://example.com", "KIO Commit Review Prompt")]
    msg = _compose(tabs)["message"]
    assert "• Chrome — KIO Commit Review Prompt" in msg


def test_multiple_tabs_same_identity_keep_detail():
    tabs = [
        _tab("https://chat.openai.com/c/1", "KIO Commit Review Prompt"),
        _tab("https://chat.openai.com/c/2", "Engineering Review"),
    ]
    msg = _compose(tabs)["message"]
    assert "• Chrome — ChatGPT — KIO Commit Review Prompt" in msg
    assert "• Chrome — ChatGPT — Engineering Review" in msg


def test_genuine_duplicates_collapsed_with_count():
    tabs = [_tab("https://chat.openai.com/c/%d" % i, "ChatGPT") for i in range(3)]
    msg = _compose(tabs)["message"]
    assert "• Chrome — ChatGPT (3 tabs)" in msg
    assert msg.count("ChatGPT") == 1  # collapsed, not repeated


def test_kio_provenance_rendered_naturally():
    tabs = [_tab("https://web.telegram.org/a", "KIO Assistant", is_owned=True)]
    msg = _compose(tabs)["message"]
    assert "• Chrome — Telegram — KIO Assistant (opened by KIO)" in msg
    assert "[Opened by KIO]" not in msg


def test_active_tab_marked_only_when_single():
    tabs = [
        _tab("https://chat.openai.com/c/1", "ChatGPT", active=True),
        _tab("https://web.telegram.org/a", "Telegram"),
    ]
    msg = _compose(tabs)["message"]
    assert "• Chrome — ChatGPT (active)" in msg
    # Multi-active is unreliable -> no active claim at all (truthful).
    tabs2 = [
        _tab("https://chat.openai.com/c/1", "ChatGPT", active=True),
        _tab("https://web.telegram.org/a", "Telegram", active=True),
    ]
    msg2 = _compose(tabs2)["message"]
    assert "active" not in msg2


def test_native_and_browser_composed_together():
    tabs = [_tab("https://chat.openai.com/c/1", "ChatGPT")]
    native = [
        _win(app="OpenCode", base="opencode", title="kio_final"),
        _win(app="File Explorer", base="explorer", title="This PC"),
    ]
    msg = _compose(tabs, native=native)["message"]
    assert "• Chrome — ChatGPT" in msg
    assert "• OpenCode — kio_final" in msg
    assert "• File Explorer — This PC" in msg


def test_native_only_desktop():
    native = [_win(app="OpenCode", base="opencode", title="kio_final")]
    msg = _compose([], native=native)["message"]
    assert "Open right now:" in msg
    assert "• OpenCode — kio_final" in msg


def test_foreground_native_window_marked_active():
    native = [
        _win(app="OpenCode", base="opencode", title="kio_final", foreground=True),
        _win(app="File Explorer", base="explorer", title="This PC"),
    ]
    msg = _compose([], native=native)["message"]
    assert "• OpenCode — kio_final (active)" in msg
    assert "File Explorer" in msg


def test_browser_host_collapsed_into_tabs_when_readable():
    tabs = [_tab("https://chat.openai.com/c/1", "ChatGPT")]
    native = [
        _win(app="Chrome", base="chrome", title="ChatGPT - Google Chrome",
             pid=900, browser=True),
    ]
    msg = _compose(tabs, native=native)["message"]
    # Browser window is collapsed into its tabs; the bare window line vanishes.
    assert "• Chrome — ChatGPT" in msg
    assert "ChatGPT - Google Chrome" not in msg
    assert msg.count("Chrome") == 1


def test_browser_window_shown_when_tabs_unreadable():
    native = [
        _win(app="Chrome", base="chrome", title="ChatGPT - Google Chrome",
             pid=900, browser=True, foreground=True),
    ]
    msg = _compose([], connected=True, error=True, native=native)["message"]
    # Brand suffix stripped from the window title; window listed natively.
    assert "• Chrome — ChatGPT" in msg
    assert "Google Chrome" not in msg


def test_browser_only_state():
    msg = _compose([])["message"]
    assert msg == "Chrome is open."


def test_nothing_open_when_state_known_empty(monkeypatch):
    # Browser-runtime fallback path (conn=None) with a successfully listed,
    # empty tab set and no native windows -> truthful empty state.
    from mini_kio.core import command_router
    monkeypatch.setattr(command_router, "_check_br_available", lambda: True)
    monkeypatch.setattr(command_router, "_br_list_tabs",
                        lambda: {"success": True, "message": "Open tabs:\n"})
    msg = _compose([], use_conn=False)["message"]
    assert msg == "Nothing is open right now."


def test_cannot_read_state(monkeypatch):
    # No connector, no fallback, and native observation failed -> truthful,
    # never fabricated. Live observation is monkeypatched to a failure so the
    # test is independent of the machine's actual desktop.
    import mini_kio.core.desktop_state as ds
    from mini_kio.core import command_router
    monkeypatch.setattr(command_router, "_check_br_available", lambda: False)
    monkeypatch.setattr(ds, "observe_native_windows", lambda: ([], False))
    msg = _compose([], use_conn=False, native=_LIVE)["message"]
    assert msg == "I can't read your current desktop state right now."


def test_partial_state_browser_tabs_unreadable():
    msg = _compose([], connected=True, error=True)["message"]
    assert msg == "Chrome is open, but I couldn't read its tabs."


def test_fallback_path_sanitizes_url_lines(monkeypatch):
    # Browser-runtime fallback (conn=None) must sanitize raw URL lines out of
    # the listing before they reach the response.
    from mini_kio.core import command_router
    monkeypatch.setattr(command_router, "_check_br_available", lambda: True)
    monkeypatch.setattr(
        command_router, "_br_list_tabs",
        lambda: {"success": True, "message": "Open tabs:\n1. ChatGPT\n2. https://raw-url.example.com/path\n"},
    )
    msg = _compose([], use_conn=False)["message"]
    assert "ChatGPT" in msg
    assert "https://" not in msg
    assert "raw-url" not in msg


def test_embedded_url_in_title_sanitized():
    tabs = [_tab("https://example.com", "Visit https://evil.example/x now")]
    msg = _compose(tabs)["message"]
    assert "Visit" in msg and "now" in msg
    assert "https://" not in msg
    assert "evil.example" not in msg


def test_native_title_with_embedded_url_sanitized():
    native = [_win(app="OpenCode", base="opencode",
                   title="Repo https://raw-url.example/x now")]
    msg = _compose([], native=native)["message"]
    assert "https://" not in msg
    assert "raw-url" not in msg


def test_no_raw_url_or_pid_leakage():
    tabs = [
        _tab("https://chat.openai.com/c/1", "ChatGPT"),
        _tab("https://example.org", ""),
        _tab("https://web.telegram.org/a", "Telegram"),
    ]
    native = [_win(app="OpenCode", base="opencode", title="kio_final", pid=12345)]
    msg = _compose(tabs, native=native)["message"]
    assert "https://" not in msg
    assert "http" not in msg
    assert "::" not in msg
    assert "pid" not in msg.lower()
    assert "12345" not in msg
    assert "[Opened by KIO]" not in msg
    assert "Untitled tab" in msg  # empty-title unknown tab -> neutral name


def test_kio_owned_native_window_provenance():
    native = [_win(app="OpenCode", base="opencode", title="kio_final", owned=True)]
    msg = _compose([], native=native)["message"]
    assert "• OpenCode — kio_final (opened by KIO)" in msg


def test_external_window_no_provenance_claim():
    native = [_win(app="OpenCode", base="opencode", title="kio_final", owned=False)]
    msg = _compose([], native=native)["message"]
    assert "opened by KIO" not in msg


def test_browser_line_survives_composer_strip_leaks():
    # The real pipeline passes the composed message through
    # _ResponseComposer._strip_leaks (collapses 2+ whitespace runs). Verify the
    # single-newline structure survives intact.
    msg = _compose([
        _tab("https://chat.openai.com/c/1", "ChatGPT"),
        _tab("https://web.telegram.org/a", "Telegram"),
    ])["message"]
    stripped = _ResponseComposer()._strip_leaks(msg)
    assert stripped == "Open right now:\n• Chrome — ChatGPT\n• Chrome — Telegram"


# ---------------------------------------------------------------------------
# Semantic state-query family — deterministic routing, no LLM fallback
# ---------------------------------------------------------------------------

@pytest.mark.parametrize("query", [
    "what's open", "what is open", "whats open",
    "what's open right now", "what is open right now",
    "what am i using", "what am i currently using",
    "what apps are open", "which apps are open",
    "which applications are running",
    "what's running", "what is running",
    "what's active", "what is active",
    "what tabs are open", "which browser tabs are open",
    "show me what's open", "show open apps", "show my open windows",
    "show tabs", "what do i have open", "what do i currently have open",
    "what are you using", "what are you currently controlling",
    "what is kio controlling", "what's open in chrome",
    "what's open on my computer", "what is on my computer",
    "tell me what's open", "list tabs", "list open apps",
    "what windows are open",
    "what am i controlling", "show me my desktop", "show my desktop",
])
def test_state_query_variants_route_deterministically(query):
    d = Pipeline()._classifier.classify(query, query)
    assert d.intent_type == IntentType.BROWSER_TABS
    assert d.action == "list_tabs"


@pytest.mark.parametrize("query", [
    "kio what's open", "kio, what's open", "hey kio, what's open?",
    "KIO what am I using?", "what's open kio",
    "KIO — what's open?", "KIO — what am I using?",
    "Hey — what's open?",
])
def test_kio_invocation_prefix_does_not_break_routing(query):
    d = Pipeline()._classifier.classify(query, query)
    assert d.intent_type == IntentType.BROWSER_TABS


def test_politeness_variant_routes_via_normalizer():
    from mini_kio.core.context_manager import get_session_context
    p = Pipeline()
    ctx = get_session_context("norm_state_test")
    norm = p._normalizer.run("Can you tell me what's open?", ctx)
    d = p._classifier.classify(norm, "Can you tell me what's open?")
    assert d.intent_type == IntentType.BROWSER_TABS


@pytest.mark.parametrize("query", [
    "what is chatgpt", "what is chatgpt?",
    "tell me about chrome", "what should i use for coding",
    "what's on", "what's up", "how do I install python",
    # Queries that merely share a state-query prefix must stay on the
    # knowledge path (the state matcher is anchored, not substring-based).
    "what's open source", "what's open source software",
    "what is running time", "what running shoes should i buy",
    "what is active ingredient",
])
def test_knowledge_questions_not_routed_as_state(query):
    d = Pipeline()._classifier.classify(query, query)
    assert d.intent_type != IntentType.BROWSER_TABS


def test_what_is_chatgpt_is_knowledge():
    d = Pipeline()._classifier.classify("What is ChatGPT?", "What is ChatGPT?")
    assert d.intent_type in (IntentType.INFORMATION, IntentType.ENTITY_QUERY)


# ---------------------------------------------------------------------------
# Contextual close still intact
# ---------------------------------------------------------------------------

def test_contextual_close_still_tab_scoped():
    # "Close it" after opening a web app must resolve to the tab, never the
    # host browser — referent identity path must remain untouched.
    from mini_kio.core.target_ref import parse_target, display_target_name
    ref = parse_target("chrome::open_url::https://chat.openai.com::chatgpt")
    assert ref.kind == "webapp"
    assert ref.name == "chatgpt"
    assert display_target_name(ref.name) == "ChatGPT"
