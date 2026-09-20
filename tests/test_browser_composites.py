"""Tests for KIO browser composite capability actions (Phase 3)."""

from __future__ import annotations

import os
import sys
from pathlib import Path
from unittest.mock import MagicMock, AsyncMock, patch

_project_root = Path(__file__).resolve().parent.parent
if str(_project_root) not in sys.path:
    sys.path.insert(0, str(_project_root))

# Override conftest's KIO_TEST_MODE=1 so browser handlers can execute real paths
os.environ.pop("KIO_TEST_MODE", None)

_PATCH_TARGET = "mini_kio.core.command_router._get_connector"
_BRIDGE_PATCH = "mini_kio.browser_connector.js_bridge.get_js_bridge"


def _mock_tab_result(success=True, tab_id=1, url="", error=""):
    from mini_kio.browser_connector.protocol import TabResult, OwnedTab
    tab = OwnedTab(tab_id=tab_id, url=url or "https://example.com", title="Mock")
    return TabResult(success=success, tab=tab, error=error)


def _mock_connector(content="Extracted body text: Hello World"):
    """Async-aware mock connector for browser composite tests."""
    conn = MagicMock()
    conn.is_connected.return_value = True
    conn.open_tab = AsyncMock(return_value=_mock_tab_result(success=True, tab_id=42, url="https://example.com"))
    conn.execute_script = AsyncMock(return_value=_mock_tab_result(success=True, tab_id=42, error=content))
    return conn


def _mock_bridge(content="Extracted body text: Hello World"):
    """Mock JS bridge that returns content as the execute_js result."""
    bridge = MagicMock()
    bridge.is_connected.return_value = True
    bridge.execute_js = MagicMock(return_value={
        "success": True,
        "message": content,
        "tab_id": 42,
    })
    return bridge


def _mock_bridge_sequence(*contents):
    """Mock JS bridge with a sequence of responses for multi-call actions."""
    bridge = MagicMock()
    bridge.is_connected.return_value = True
    bridge.execute_js = MagicMock(side_effect=[
        {"success": True, "message": c, "tab_id": 42} for c in contents
    ])
    return bridge


def _combined_patches(content="Extracted body text: Hello World"):
    """Context manager that patches both connector and bridge."""
    from contextlib import ExitStack
    stack = ExitStack()
    stack.enter_context(patch(_PATCH_TARGET, return_value=_mock_connector(content)))
    stack.enter_context(patch(_BRIDGE_PATCH, return_value=_mock_bridge(content)))
    return stack


# ── Registration tests ─────────────────────────────────────────────────

class TestBrowserCompositesRegistered:
    def test_five_composites_in_handlers(self):
        from mini_kio.core.browser_operator import BROWSER_HANDLERS
        for name in ("browser_fetch_region", "browser_extract_records",
                      "browser_crawl_extract", "browser_snapshot_sources",
                      "browser_extract_price"):
            assert name in BROWSER_HANDLERS, f"{name} missing from BROWSER_HANDLERS"

    def test_handler_count(self):
        from mini_kio.core.browser_operator import BROWSER_HANDLERS
        assert len(BROWSER_HANDLERS) == 19

    def test_composites_in_static_action_table(self):
        from mini_kio.core.execution_boundary import STATIC_ACTION_TABLE
        for name in ("browser_fetch_region", "browser_extract_records",
                      "browser_crawl_extract", "browser_snapshot_sources",
                      "browser_extract_price"):
            assert name in STATIC_ACTION_TABLE, f"{name} missing from STATIC_ACTION_TABLE"

    def test_action_map_has_aliases(self):
        from mini_kio.core.execution_boundary import _ACTION_MAP
        assert _ACTION_MAP.get("fetch_region") == "browser_fetch_region"
        assert _ACTION_MAP.get("extract_records") == "browser_extract_records"
        assert _ACTION_MAP.get("crawl_extract") == "browser_crawl_extract"
        assert _ACTION_MAP.get("snapshot_sources") == "browser_snapshot_sources"
        assert _ACTION_MAP.get("extract_price") == "browser_extract_price"

    def test_step_runner_maps(self):
        from mini_kio.automation.step_runner import StepRunner
        sr = StepRunner.__new__(StepRunner)
        assert sr._ACTION_MAP.get(("browser", "fetch_region")) == "browser_fetch_region"

    def test_prerequisite_resolvers_covered(self):
        from mini_kio.core.execution_boundary import _BROWSER_BACKEND_ACTIONS
        for name in ("browser_fetch_region", "browser_extract_records",
                      "browser_crawl_extract", "browser_snapshot_sources",
                      "browser_extract_price"):
            assert name in _BROWSER_BACKEND_ACTIONS


# ── fetch_region tests ─────────────────────────────────────────────────

class TestFetchRegion:
    def test_fetch_region_with_connector(self):
        from mini_kio.core.browser_operator import browser_fetch_region
        with _combined_patches():
            result = browser_fetch_region("https://example.com", selector="body")
        assert result["success"]
        assert result["action"] == "browser_fetch_region"
        assert "content" in result

    def test_fetch_region_empty_url(self):
        from mini_kio.core.browser_operator import browser_fetch_region
        result = browser_fetch_region("")
        assert not result["success"]
        assert "No URL" in result["message"]

    def test_fetch_region_via_boundary(self):
        from mini_kio.core.execution_boundary import execute_action
        with _combined_patches():
            result = execute_action("browser_fetch_region", "https://example.com",
                                    selector="body", extract="text")
        assert result["success"]


# ── extract_records tests ──────────────────────────────────────────────

class TestExtractRecords:
    def test_extract_records_json(self):
        from mini_kio.core.browser_operator import browser_extract_records
        with _combined_patches('[{"name":"item1"},{"name":"item2"}]'):
            result = browser_extract_records("https://example.com/data.json")
        assert result["success"]
        assert result.get("record_count", 0) >= 1

    def test_extract_records_empty_url(self):
        from mini_kio.core.browser_operator import browser_extract_records
        result = browser_extract_records("")
        assert not result["success"]

    def test_extract_records_via_boundary(self):
        from mini_kio.core.execution_boundary import execute_action
        with _combined_patches('[{"a":1}]'):
            result = execute_action("browser_extract_records", "https://example.com/data.json")
        assert result["success"]


# ── crawl_extract tests ───────────────────────────────────────────────

class TestCrawlExtract:
    def test_crawl_extract_with_connector(self):
        from mini_kio.core.browser_operator import browser_crawl_extract
        # crawl_extract calls bridge.execute_js twice: once for text, once for links
        bridge = _mock_bridge_sequence(
            "Page text content",
            '[{"href":"https://example.com/a","text":"Link A"}]',
        )
        with patch(_PATCH_TARGET, return_value=_mock_connector()), \
             patch(_BRIDGE_PATCH, return_value=bridge):
            result = browser_crawl_extract("https://example.com")
        assert result["success"]
        assert "link_count" in result

    def test_crawl_extract_empty_url(self):
        from mini_kio.core.browser_operator import browser_crawl_extract
        result = browser_crawl_extract("")
        assert not result["success"]

    def test_crawl_extract_via_boundary(self):
        from mini_kio.core.execution_boundary import execute_action
        bridge = _mock_bridge_sequence("Content", "[]")
        with patch(_PATCH_TARGET, return_value=_mock_connector()), \
             patch(_BRIDGE_PATCH, return_value=bridge):
            result = execute_action("browser_crawl_extract", "https://example.com")
        assert result["success"]


# ── snapshot_sources tests ─────────────────────────────────────────────

class TestSnapshotSources:
    def test_snapshot_single_source(self):
        from mini_kio.core.browser_operator import browser_snapshot_sources
        bridge = _mock_bridge_sequence("snapshot1")
        with patch(_PATCH_TARGET, return_value=_mock_connector()), \
             patch(_BRIDGE_PATCH, return_value=bridge):
            result = browser_snapshot_sources("https://example.com", urls=["https://example.com"])
        assert result["success"]
        assert result["source_count"] == 1

    def test_snapshot_multiple_sources(self):
        from mini_kio.core.browser_operator import browser_snapshot_sources
        bridge = _mock_bridge_sequence("snap1", "snap2", "snap3")
        with patch(_PATCH_TARGET, return_value=_mock_connector()), \
             patch(_BRIDGE_PATCH, return_value=bridge):
            result = browser_snapshot_sources(
                "https://a.com",
                urls=["https://a.com", "https://b.com", "https://c.com"]
            )
        assert result["success"]
        assert result["source_count"] == 3

    def test_snapshot_no_urls(self):
        from mini_kio.core.browser_operator import browser_snapshot_sources
        result = browser_snapshot_sources("")
        assert not result["success"]
        assert "No URLs" in result["message"]

    def test_snapshot_via_boundary(self):
        from mini_kio.core.execution_boundary import execute_action
        bridge = _mock_bridge_sequence("s1", "s2")
        with patch(_PATCH_TARGET, return_value=_mock_connector()), \
             patch(_BRIDGE_PATCH, return_value=bridge):
            result = execute_action("browser_snapshot_sources", "https://a.com",
                                    urls=["https://a.com", "https://b.com"])
        assert result["success"]


# ── extract_price tests ────────────────────────────────────────────────

class TestExtractPrice:
    def test_extract_price_found(self):
        from mini_kio.core.browser_operator import browser_extract_price
        with _combined_patches("Product costs $49.99 plus tax"):
            result = browser_extract_price("https://shop.example.com/product")
        assert result["success"]
        assert result.get("price") is not None
        assert "49.99" in str(result.get("price_value") or result.get("price", ""))

    def test_extract_price_not_found(self):
        from mini_kio.core.browser_operator import browser_extract_price
        with _combined_patches("No price on this page, just text"):
            result = browser_extract_price("https://example.com")
        assert result["success"]
        assert result.get("price") is None

    def test_extract_price_euro(self):
        from mini_kio.core.browser_operator import browser_extract_price
        with _combined_patches("Price: \u20ac129.00"):
            result = browser_extract_price("https://eu-shop.example.com", currency="\u20ac")
        assert result["success"]
        assert result.get("price") is not None

    def test_extract_price_empty_url(self):
        from mini_kio.core.browser_operator import browser_extract_price
        result = browser_extract_price("")
        assert not result["success"]

    def test_extract_price_via_boundary(self):
        from mini_kio.core.execution_boundary import execute_action
        with _combined_patches("Only $9.99 today!"):
            result = execute_action("browser_extract_price", "https://shop.example.com", currency="$")
        assert result["success"]


# ── descriptor tests ───────────────────────────────────────────────────

class TestBrowserDescriptor:
    def test_version_bumped(self):
        from mini_kio.core.browser_operator import BROWSER_OPERATOR_DESCRIPTOR
        assert BROWSER_OPERATOR_DESCRIPTOR["tool_version"] == "2.0.0"

    def test_five_new_actions_in_descriptor(self):
        from mini_kio.core.browser_operator import BROWSER_OPERATOR_DESCRIPTOR
        actions = BROWSER_OPERATOR_DESCRIPTOR["supported_actions"]
        for name in ("browser_fetch_region", "browser_extract_records",
                      "browser_crawl_extract", "browser_snapshot_sources",
                      "browser_extract_price"):
            assert name in actions
