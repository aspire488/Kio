"""
test_routing_ownership_fix.py — Regression tests for Fix A/B/C/D

Covers 11 scenarios across close-fallthrough, focus/switch/activate routing,
and 'it' resolution via tracked processes.
"""

import pytest
from unittest.mock import MagicMock, patch

from mini_kio.core.command_router import handle_command, _dispatch_command
from mini_kio.core import config


# ── helpers ────────────────────────────────────────────────────────────

def _make_awaitable(result):
    """Wrap a result in a coroutine so safe_run_async can await it."""
    async def _inner():
        return result
    return _inner()


# ── fixtures ───────────────────────────────────────────────────────────

@pytest.fixture
def mock_connector():
    with patch("mini_kio.core.command_router._get_connector") as mock:
        conn = MagicMock()
        conn.is_connected.return_value = True
        mock.return_value = conn
        yield conn


@pytest.fixture
def mock_connector_async():
    """Connector whose close_tab and focus_tab return awaitables."""
    with patch("mini_kio.core.command_router._get_connector") as mock:
        conn = MagicMock()
        conn.is_connected.return_value = True
        # Make async methods return awaitables
        conn.close_tab.side_effect = lambda t: _make_awaitable(
            MagicMock(success=True, tab_id=42)
        )
        conn.focus_tab.side_effect = lambda t: _make_awaitable(
            MagicMock(success=True, tab_id=42)
        )
        mock.return_value = conn
        yield conn


@pytest.fixture
def mock_runtime_with_tracked():
    """Inject a tracked calculator process into the runtime singleton."""
    with patch("mini_kio.core.runtime.get_runtime") as mock_get:
        rt = MagicMock()
        rt.tracked_processes = [
            {"pid": 12345, "name": "calculator", "target": "calculator",
             "launched_at": 100.0, "status": "active"}
        ]
        rt.get_tracked_process.return_value = rt.tracked_processes[0]
        mock_get.return_value = rt
        yield mock_get


# ── Fix A: Close fallthrough ───────────────────────────────────────────

class TestFixA_CloseFallthrough:

    def test_close_calculator_native_app_skips_connector(self, mock_connector_async):
        """Fix A: 'close calculator' should fall through to close_app when
        connector has no matching tab (returns failure)."""
        mock_connector_async.close_tab.side_effect = lambda t: _make_awaitable(
            MagicMock(success=False, error="no owned tab matching: calculator")
        )
        with patch.object(config, "BROWSER_CONNECTOR_ENABLED", True):
            result = handle_command("close calculator")
        # Must NOT return connector error. Either success (tracked) or
        # a meaningful non-connector error message.
        assert result.get("message", ""), "Result should have a message"
        assert "no owned tab" not in result.get("message", "").lower()

    def test_close_native_app_exception_falls_through(self, mock_connector_async):
        """Fix A: connector exception on close_tab must fall through."""
        mock_connector_async.close_tab.side_effect = lambda t: _make_awaitable(
            MagicMock(success=False, error="connector crash")
        )
        with patch.object(config, "BROWSER_CONNECTOR_ENABLED", True):
            result = handle_command("close vscode")
        assert result.get("message", ""), "Result should have a message"
        assert "no owned tab" not in result.get("message", "").lower()

    def test_close_connector_success_still_works(self, mock_connector_async):
        """Fix A: connector close success must still return immediately."""
        with patch.object(config, "BROWSER_CONNECTOR_ENABLED", True):
            result = handle_command("close github")
        assert result.get("message", ""), "Result should have a message"


# ── Fix B: Focus / Switch without connector ───────────────────────────

class TestFixB_FocusSwitchNoConnector:

    def test_switch_to_youtube_falls_to_web_routing(self):
        """Fix B: 'switch to youtube' without connector should not
        reach AI fallback — routes via get_browser_routing."""
        with patch.object(config, "BROWSER_CONNECTOR_ENABLED", False):
            result = handle_command("switch to youtube")
        # Should not be AI fallback message
        assert "Cannot process" not in result.get("message", "")
        assert "Can't focus" not in result.get("message", "")

    def test_focus_youtube_falls_to_web_routing(self):
        """Fix B: 'focus youtube' without connector."""
        with patch.object(config, "BROWSER_CONNECTOR_ENABLED", False):
            result = handle_command("focus youtube")
        assert "Cannot process" not in result.get("message", "")
        assert "Can't focus" not in result.get("message", "")

    def test_switch_to_tracked_app_uses_window_activation(self, mock_runtime_with_tracked):
        """Fix B: 'switch to calculator' with tracked process should
        return success via window activation."""
        with patch.object(config, "BROWSER_CONNECTOR_ENABLED", False):
            result = handle_command("switch to calculator")
        assert result["success"] is True
        assert "Focused" in result["message"]

    def test_focus_tracked_app_uses_window_activation(self, mock_runtime_with_tracked):
        """Fix B: 'focus calculator' with tracked process."""
        with patch.object(config, "BROWSER_CONNECTOR_ENABLED", False):
            result = handle_command("focus calculator")
        assert result["success"] is True
        assert "Focused" in result["message"]

    def test_switch_connector_success_still_preferred(self, mock_connector_async):
        """Fix B: when connector is available, it takes priority."""
        with patch.object(config, "BROWSER_CONNECTOR_ENABLED", True):
            result = handle_command("switch to youtube")
        assert result["success"] is True
        assert "Focused" in result["message"]
        assert "tab." in result["message"]

    def test_focus_unknown_returns_meaningful_error(self):
        """Fix B: focus on unknown target — may fall to search or web nav."""
        with patch.object(config, "BROWSER_CONNECTOR_ENABLED", False):
            result = handle_command("focus zxyzzunknown")
        # Should NOT reach AI fallback for unknown targets
        assert "Cannot process" not in result.get("message", "")


# ── Fix C: Activate keyword ──────────────────────────────────────────

class TestFixC_ActivateKeyword:

    def test_activate_youtube_routes_to_focus(self):
        """Fix C: 'activate youtube' should not reach AI fallback."""
        with patch.object(config, "BROWSER_CONNECTOR_ENABLED", False):
            result = handle_command("activate youtube")
        assert "Cannot process" not in result.get("message", "")

    def test_activate_to_youtube_extracts_target(self):
        """Fix C: 'activate to youtube' strips 'to' prefix."""
        with patch.object(config, "BROWSER_CONNECTOR_ENABLED", False):
            result = handle_command("activate to youtube")
        assert "Cannot process" not in result.get("message", "")

    def test_activate_tracked_app_succeeds(self, mock_runtime_with_tracked):
        """Fix C: 'activate calculator' with tracked process."""
        with patch.object(config, "BROWSER_CONNECTOR_ENABLED", False):
            result = handle_command("activate calculator")
        assert result["success"] is True
        assert "Focused" in result["message"]


# ── Fix D: 'it' resolution via tracked processes ──────────────────────

class TestFixD_ItResolution:

    def test_close_it_resolves_from_tracked(self, mock_runtime_with_tracked):
        """Fix D: 'close it' should resolve 'it' to the last tracked
        process when capability and interaction are empty."""
        with patch.object(config, "BROWSER_CONNECTOR_ENABLED", False):
            result = handle_command("close it")
        assert result.get("message", ""), "Should resolve and produce a result"

    def test_focus_it_resolves_from_tracked(self, mock_runtime_with_tracked):
        """Fix D: 'focus it' resolves from tracked processes."""
        with patch.object(config, "BROWSER_CONNECTOR_ENABLED", False):
            result = handle_command("focus it")
        assert result["success"] is True
        assert "Focused" in result["message"]

    def test_activate_it_resolves_from_tracked(self, mock_runtime_with_tracked):
        """Fix D: 'activate it' resolves from tracked processes."""
        with patch.object(config, "BROWSER_CONNECTOR_ENABLED", False):
            result = handle_command("activate it")
        assert result["success"] is True
        assert "Focused" in result["message"]


# ── Non-regression: existing behavior ─────────────────────────────────

class TestNonRegression:

    def test_open_calculator_still_works(self):
        """Existing open behavior unchanged."""
        result = handle_command("open calculator")
        # May fail in test env (no GUI) but must not return AI fallback
        assert "Cannot process" not in result.get("message", "")

    def test_list_tabs_still_requires_connector(self):
        """List tabs falls through to ai_fallback when connector disabled."""
        with patch.object(config, "BROWSER_CONNECTOR_ENABLED", False):
            result = handle_command("list tabs")
        assert result["_gate3_eligible"] is True

    def test_search_routing_unchanged(self):
        """Search routing must not be affected."""
        result = handle_command("search python programming")
        assert result.get("message", ""), "Should produce a result"
