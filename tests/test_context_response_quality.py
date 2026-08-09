"""
test_context_response_quality.py — "What's open?" context-response quality patch

Verifies:
- canonical web-app identity resolution from tab URLs (ChatGPT / Telegram /
  YouTube / ...) reusing the existing registered URL maps — arbitrary sites
  never fabricate an identity
- brand casing via display_target_name
- natural desktop-state composition (mixed tabs + browser host line,
  duplicate collapse, browser-only, truthful empty state)
- no raw URL / '::' chain / ownership-marker / process-id leakage
- "what's open" classifier routing still lands on list_tabs
- contextual "it" referent resolution still works (target identity intact)
"""

import pytest

from mini_kio.core.target_ref import webapp_name_from_url, display_target_name
from mini_kio.core.pipeline import Pipeline, _ExecutionCoordinator
from mini_kio.core.pipeline.types import IntentType
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
# Desktop-state composition (pure: fake connector)
# ---------------------------------------------------------------------------

class _FakeConn:
    """Minimal connector stand-in: connected flag + async list_tabs."""

    def __init__(self, tabs, connected=True):
        self._tabs = tabs
        self._connected = connected

    def is_connected(self):
        return self._connected

    async def list_tabs(self):
        return TabResult(success=True, tabs=self._tabs)


def _compose(tabs, connected=True):
    return _ExecutionCoordinator()._compose_desktop_state(_FakeConn(tabs, connected=connected))


def test_mixed_state_identities():
    tabs = [
        OwnedTab(tab_id=1, url="https://chat.openai.com/c/1", title="ChatGPT", is_owned=True),
        OwnedTab(tab_id=2, url="https://web.telegram.org/a", title="Telegram"),
        OwnedTab(tab_id=3, url="https://example.com", title="KIO Commit Review Prompt"),
    ]
    msg = _compose(tabs)["message"]
    assert "Open right now:" in msg
    assert "• ChatGPT" in msg
    assert "• Telegram" in msg
    assert "• KIO Commit Review Prompt" in msg
    # Browser reported as a host line on its own line (must not be flattened
    # onto the last bullet — the composer collapses 2+ whitespace runs, so no
    # blank separator is used; the single newline must survive).
    assert "\nBrowser: Chrome" in msg
    assert "Telegram Browser" not in msg
    # Ownership markers and internal serialization must not leak.
    assert "[Opened by KIO]" not in msg
    assert "::" not in msg


def test_browser_line_survives_composer_strip_leaks():
    # The real pipeline passes the composed message through
    # _ResponseComposer._strip_leaks (collapses 2+ whitespace runs). Verify
    # the single-newline browser line survives that transformation intact.
    from mini_kio.core.pipeline import _ResponseComposer

    msg = _compose([
        OwnedTab(tab_id=1, url="https://chat.openai.com/c/1", title="ChatGPT"),
        OwnedTab(tab_id=2, url="https://web.telegram.org/a", title="Telegram"),
    ])["message"]
    stripped = _ResponseComposer()._strip_leaks(msg)
    assert stripped == "Open right now:\n• ChatGPT\n• Telegram\nBrowser: Chrome"


def test_duplicate_identities_collapsed_with_count():
    tabs = [
        OwnedTab(tab_id=1, url="https://chat.openai.com/c/1", title="ChatGPT"),
        OwnedTab(tab_id=2, url="https://chat.openai.com/c/2", title="ChatGPT"),
        OwnedTab(tab_id=3, url="https://chat.openai.com/c/3", title="ChatGPT"),
    ]
    msg = _compose(tabs)["message"]
    assert "• ChatGPT (3 tabs)" in msg
    assert msg.count("ChatGPT") == 1  # collapsed, not repeated


def test_browser_only_state():
    msg = _compose([])["message"]
    assert msg == "Chrome is open."


def test_nothing_open_state():
    msg = _compose([], connected=False)["message"]
    assert msg == "Nothing is open right now."


def test_no_raw_url_or_pid_leakage():
    tabs = [
        OwnedTab(tab_id=1, url="https://chat.openai.com/c/1", title="ChatGPT"),
        OwnedTab(tab_id=2, url="https://example.org", title=""),
        OwnedTab(tab_id=3, url="https://web.telegram.org/a", title="Telegram"),
    ]
    msg = _compose(tabs)["message"]
    assert "https://" not in msg
    assert "http" not in msg
    assert "::" not in msg
    assert "pid=" not in msg.lower()
    assert "[Opened by KIO]" not in msg
    assert "Untitled tab" in msg  # empty-title unknown tab -> neutral name


def test_embedded_url_in_title_sanitized():
    tabs = [OwnedTab(tab_id=1, url="https://example.com", title="Visit https://evil.example/x now")]
    msg = _compose(tabs)["message"]
    assert "Visit" in msg
    assert "now" in msg
    assert "https://" not in msg
    assert "evil.example" not in msg


def test_fallback_path_sanitizes_url_lines(monkeypatch):
    from mini_kio.core import command_router

    monkeypatch.setattr(command_router, "_check_br_available", lambda: True)
    monkeypatch.setattr(
        command_router, "_br_list_tabs",
        lambda: {"success": True, "message": "Open tabs:\n1. ChatGPT\n2. https://raw-url.example.com/path\n"},
    )
    msg = _compose([], connected=False)["message"]
    assert "ChatGPT" in msg
    assert "https://" not in msg
    assert "raw-url" not in msg


def test_unknown_tab_uses_title_not_url():
    tabs = [OwnedTab(tab_id=1, url="https://example.com/page", title="The Best Writing On The Internet")]
    msg = _compose(tabs)["message"]
    assert "• The Best Writing On The Internet" in msg
    assert "example.com" not in msg


# ---------------------------------------------------------------------------
# Classifier routing + contextual referent intact
# ---------------------------------------------------------------------------

@pytest.mark.parametrize("query", [
    "what's open", "what is open", "whats open",
    "what am i using", "list tabs", "what apps are open",
])
def test_classifier_routes_state_queries(query):
    d = Pipeline()._classifier.classify(query, query)
    assert d.intent_type == IntentType.BROWSER_TABS
    assert d.action == "list_tabs"


def test_contextual_close_still_tab_scoped():
    # "Close it" after opening a web app must resolve to the tab, never the
    # host browser — referent identity path must remain untouched.
    from mini_kio.core.target_ref import parse_target, display_target_name
    ref = parse_target("chrome::open_url::https://chat.openai.com::chatgpt")
    assert ref.kind == "webapp"
    assert ref.name == "chatgpt"
    assert display_target_name(ref.name) == "ChatGPT"
