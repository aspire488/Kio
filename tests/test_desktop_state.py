"""
test_desktop_state.py — System-Level Desktop State / Context Awareness

Verifies the canonical desktop snapshot model:
- native window observation is window-driven (EnumWindows), NOT process-driven:
  background processes without a visible window never appear
- arbitrary unknown GUI applications are observed through the same generic
  mechanism (no terminal/explorer/browser special cases in detection)
- hierarchical composition: Application — Window — Browser tab
- active/foreground marking only from real state
- duplicates deduplicated, provenance preserved naturally
- empty / partial / unreadable states are truthful
- raw URLs / :: / pids / internal ids never leak
- deterministic snapshot -> deterministic response (no LLM anywhere)
- knowledge questions are never stolen by the state family
"""

import pytest

from mini_kio.core.pipeline import Pipeline
from mini_kio.core.pipeline.types import IntentType
from mini_kio.core.desktop_state import (
    compose_desktop_state,
    observe_native_windows,
    native_app_display_name,
    _exe_name_for_pid,
)
from mini_kio.browser_connector.protocol import OwnedTab, TabResult
from mini_kio.platform import window_activation


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

class _FakeConn:
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


def _compose(tabs=None, connected=True, error=False, native=None, use_conn=True):
    conn = _FakeConn(tabs, connected=connected, error=error) if use_conn else None
    if native is None:
        native = []
    return compose_desktop_state(conn, native_windows=native)


# ---------------------------------------------------------------------------
# Observation layer — window-driven, generic, honest
# ---------------------------------------------------------------------------

def test_observation_is_window_driven_not_process_driven(monkeypatch):
    # The enumerator only yields VISIBLE top-level windows. A background
    # process (no window) is simply not enumerated — it never appears.
    monkeypatch.setattr(
        window_activation, "list_visible_windows",
        lambda: [{"pid": 111, "title": "kio_final", "is_foreground": True}],
    )
    monkeypatch.setattr("mini_kio.core.desktop_state._exe_name_for_pid",
                        lambda pid: "opencode.exe")
    windows, ok = observe_native_windows()
    assert ok is True
    assert len(windows) == 1
    assert windows[0]["app"] == "OpenCode"
    # A window the enumerator does NOT return (background process) is absent.
    assert all(w["pid"] != 999 for w in windows)


def test_arbitrary_unknown_application_is_observed(monkeypatch):
    # A brand-new arbitrary GUI app tomorrow is observed via the same path.
    monkeypatch.setattr(
        window_activation, "list_visible_windows",
        lambda: [{"pid": 222, "title": "untitled-1", "is_foreground": False}],
    )
    monkeypatch.setattr("mini_kio.core.desktop_state._exe_name_for_pid",
                        lambda pid: "mybrandnewapp.exe")
    windows, ok = observe_native_windows()
    assert ok and len(windows) == 1
    assert windows[0]["app"] == "Mybrandnewapp"
    assert windows[0]["title"] == "untitled-1"
    assert windows[0]["is_browser_host"] is False


def test_known_binaries_get_brand_casing_only_in_presentation(monkeypatch):
    assert native_app_display_name("code") == "VS Code"
    assert native_app_display_name("windowsterminal") == "Windows Terminal"
    assert native_app_display_name("explorer") == "File Explorer"
    assert native_app_display_name("notepad") == "Notepad"
    # Detection never consults the display map: an unknown base is prettified.
    assert native_app_display_name("myapp") == "Myapp"


def test_wrapper_overlay_exes_are_skipped(monkeypatch):
    monkeypatch.setattr(
        window_activation, "list_visible_windows",
        lambda: [
            {"pid": 1, "title": "conhost title", "is_foreground": False},
            {"pid": 2, "title": "Real app", "is_foreground": True},
        ],
    )
    monkeypatch.setattr("mini_kio.core.desktop_state._exe_name_for_pid",
                        lambda pid: {1: "conhost.exe", 2: "opencode.exe"}[pid])
    windows, ok = observe_native_windows()
    assert ok
    assert len(windows) == 1
    assert windows[0]["app"] == "OpenCode"


def test_uwp_broker_window_uses_real_app_title(monkeypatch):
    # ApplicationFrameHost owns the visible window for packaged apps; the
    # window title carries the real identity.
    monkeypatch.setattr(
        window_activation, "list_visible_windows",
        lambda: [{"pid": 333, "title": "Settings", "is_foreground": True}],
    )
    monkeypatch.setattr("mini_kio.core.desktop_state._exe_name_for_pid",
                        lambda pid: "applicationframehost.exe")
    windows, ok = observe_native_windows()
    assert ok and len(windows) == 1
    assert windows[0]["app"] == "Settings"


def test_browser_host_windows_classified_not_as_plain_app(monkeypatch):
    monkeypatch.setattr(
        window_activation, "list_visible_windows",
        lambda: [{"pid": 444, "title": "ChatGPT - Google Chrome",
                  "is_foreground": True}],
    )
    monkeypatch.setattr("mini_kio.core.desktop_state._exe_name_for_pid",
                        lambda pid: "chrome.exe")
    windows, ok = observe_native_windows()
    assert ok and len(windows) == 1
    assert windows[0]["is_browser_host"] is True
    assert windows[0]["title"] == "ChatGPT"  # brand suffix stripped


def test_unresolvable_exe_is_listed_honestly(monkeypatch):
    # When the process image can't be resolved, the window is still listed
    # with a neutral identity — never dropped, never fabricated.
    monkeypatch.setattr(
        window_activation, "list_visible_windows",
        lambda: [{"pid": 999999, "title": "Some Window", "is_foreground": False}],
    )
    monkeypatch.setattr("mini_kio.core.desktop_state._exe_name_for_pid",
                        lambda pid: "")
    windows, ok = observe_native_windows()
    assert ok and len(windows) == 1
    assert windows[0]["app"] != ""
    assert windows[0]["base"] == ""


def test_enumeration_failure_is_truthful(monkeypatch):
    monkeypatch.setattr(window_activation, "list_visible_windows",
                        lambda: (_ for _ in ()).throw(RuntimeError("boom")))
    windows, ok = observe_native_windows()
    assert windows == []
    assert ok is False


def test_broker_duplicate_windows_collapsed(monkeypatch):
    # The UWP broker window and the packaged app's own window can both be
    # enumerated with the same app+title — collapse so it never doubles.
    monkeypatch.setattr(
        window_activation, "list_visible_windows",
        lambda: [
            {"pid": 501, "title": "Settings", "is_foreground": False},
            {"pid": 502, "title": "Settings", "is_foreground": False},
        ],
    )
    monkeypatch.setattr("mini_kio.core.desktop_state._exe_name_for_pid",
                        lambda pid: "applicationframehost.exe")
    windows, ok = observe_native_windows()
    assert ok and len(windows) == 1


# ---------------------------------------------------------------------------
# Composition layer — hierarchical App — Window — Tab
# ---------------------------------------------------------------------------

def test_browser_tabs_grouped_under_host():
    tabs = [
        _tab("https://chat.openai.com/c/1", "KIO Commit Review Prompt"),
        _tab("https://web.telegram.org/a", "KIO Assistant"),
    ]
    msg = _compose(tabs)["message"]
    assert "Open right now:" in msg
    assert "• Chrome — ChatGPT — KIO Commit Review Prompt" in msg
    assert "• Chrome — Telegram — KIO Assistant" in msg


def test_native_only_desktop():
    msg = _compose([], native=[_win(app="OpenCode", title="kio_final")])["message"]
    assert "• OpenCode — kio_final" in msg


def test_browser_plus_native_composition():
    tabs = [_tab("https://chat.openai.com/c/1", "ChatGPT")]
    native = [
        _win(app="OpenCode", base="opencode", title="kio_final"),
        _win(app="File Explorer", base="explorer", title="This PC"),
    ]
    msg = _compose(tabs, native=native)["message"]
    assert "• Chrome — ChatGPT" in msg
    assert "• OpenCode — kio_final" in msg
    assert "• File Explorer — This PC" in msg


def test_multiple_windows_one_application():
    native = [
        _win(app="OpenCode", base="opencode", title="kio_final"),
        _win(app="OpenCode", base="opencode", title="module2"),
    ]
    msg = _compose([], native=native)["message"]
    assert "• OpenCode — kio_final" in msg
    assert "• OpenCode — module2" in msg


def test_identical_windows_deduplicated_with_count():
    native = [
        _win(app="OpenCode", base="opencode", title="kio_final"),
        _win(app="OpenCode", base="opencode", title="kio_final"),
    ]
    msg = _compose([], native=native)["message"]
    assert "• OpenCode — kio_final (2 windows)" in msg


def test_active_foreground_window_marked_only_when_known():
    native = [
        _win(app="OpenCode", base="opencode", title="kio_final", foreground=True),
        _win(app="File Explorer", base="explorer", title="This PC"),
    ]
    msg = _compose([], native=native)["message"]
    assert "• OpenCode — kio_final (active)" in msg
    assert "File Explorer" in msg
    assert "(active)" in msg  # exactly one active claim


def test_active_not_invented_when_unknown():
    native = [_win(app="OpenCode", base="opencode", title="kio_final")]
    msg = _compose([], native=native)["message"]
    assert "(active)" not in msg


def test_foreground_native_window_suppresses_stale_tab_active():
    # Windows Terminal is genuinely foreground -> the connector's stale tab
    # "active" flag must NOT claim a browser tab is active too (only one
    # thing can be foreground).
    tabs = [_tab("https://chat.openai.com/c/1", "ChatGPT", active=True)]
    native = [
        _win(app="Windows Terminal", base="windowsterminal",
             title="kio_final", foreground=True),
        _win(app="Chrome", base="chrome", title="ChatGPT - Google Chrome",
             browser=True),
    ]
    msg = _compose(tabs, native=native)["message"]
    assert "• Windows Terminal — kio_final (active)" in msg
    # The ChatGPT tab must not be marked active while another window is on top.
    assert "ChatGPT (active)" not in msg
    assert "• Chrome — ChatGPT" in msg  # tab still listed, just not claimed active


def test_browser_only_state_is_truthful():
    assert _compose([])["message"] == "Chrome is open."


def test_empty_desktop_known_empty(monkeypatch):
    from mini_kio.core import command_router
    monkeypatch.setattr(command_router, "_check_br_available", lambda: True)
    monkeypatch.setattr(command_router, "_br_list_tabs",
                        lambda: {"success": True, "message": "Open tabs:\n"})
    assert _compose([], use_conn=False)["message"] == "Nothing is open right now."


def test_partial_state_tabs_unreadable_native_visible():
    native = [_win(app="OpenCode", base="opencode", title="kio_final")]
    msg = _compose([], connected=True, error=True, native=native)["message"]
    assert "Open right now:" in msg
    assert "• OpenCode — kio_final" in msg


def test_no_url_or_pid_or_internal_leak():
    tabs = [
        _tab("https://chat.openai.com/c/1", "ChatGPT"),
        _tab("https://evil.example.com", "https://raw.example.com/x"),
    ]
    native = [_win(app="OpenCode", base="opencode", title="Repo", pid=12345)]
    msg = _compose(tabs, native=native)["message"]
    assert "https://" not in msg
    assert "http" not in msg
    assert "::" not in msg
    assert "pid" not in msg.lower()
    assert "12345" not in msg
    assert "raw.example.com" not in msg


def test_spoof_domain_never_classified_as_known_app():
    # A lookalike domain in a title/URL must never fabricate a brand identity.
    tabs = [_tab("https://chat.openai.com.evil.net", "Login")]
    msg = _compose(tabs)["message"]
    assert "ChatGPT" not in msg
    assert "• Chrome — Login" in msg


def test_kio_owned_provenance_preserved_naturally():
    native = [_win(app="OpenCode", base="opencode", title="kio_final", owned=True)]
    msg = _compose([], native=native)["message"]
    assert "• OpenCode — kio_final (opened by KIO)" in msg
    assert "[Opened by KIO]" not in msg


def test_external_launch_gets_no_provenance_claim():
    native = [_win(app="OpenCode", base="opencode", title="kio_final")]
    msg = _compose([], native=native)["message"]
    assert "opened by KIO" not in msg


def test_same_state_produces_deterministic_response():
    tabs = [_tab("https://chat.openai.com/c/1", "ChatGPT")]
    native = [_win(app="OpenCode", base="opencode", title="kio_final")]
    a = _compose(tabs, native=native)["message"]
    b = _compose(tabs, native=native)["message"]
    assert a == b  # deterministic snapshot -> deterministic response


# ---------------------------------------------------------------------------
# Classifier — family routes to the canonical path, knowledge is untouched
# ---------------------------------------------------------------------------

@pytest.mark.parametrize("query", [
    "what's open", "what is open right now", "what am i using",
    "what am i currently using", "which apps are open", "what windows are open",
    "what's running", "what's active", "what am i controlling",
    "what is kio controlling", "show me my desktop", "show my open windows",
    "what do i have open", "what's open in chrome",
])
def test_state_family_routes_to_canonical_path(query):
    d = Pipeline()._classifier.classify(query, query)
    assert d.intent_type == IntentType.BROWSER_TABS
    assert d.action == "list_tabs"


@pytest.mark.parametrize("query", [
    "what is chrome", "what is chatgpt", "what is an open source license",
    "what is running time", "what should i use for coding",
    "tell me about file explorer", "what is vs code", "what's open source",
])
def test_knowledge_questions_never_stolen(query):
    d = Pipeline()._classifier.classify(query, query)
    assert d.intent_type != IntentType.BROWSER_TABS
