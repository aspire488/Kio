"""Tests for KIO knowledge/search capability primitives (Phase 2)."""

from __future__ import annotations

import os
import sys
from pathlib import Path

_project_root = Path(__file__).resolve().parent.parent
if str(_project_root) not in sys.path:
    sys.path.insert(0, str(_project_root))

# Override conftest's KIO_TEST_MODE=1 so KnowledgeProvider runs real handlers
os.environ.pop("KIO_TEST_MODE", None)


class TestKnowledgeProviderIdentity:
    def test_provider_id(self):
        from mini_kio.core.providers.knowledge_provider import KnowledgeProvider
        kp = KnowledgeProvider()
        assert kp.id() == "knowledge"

    def test_provider_health(self):
        from mini_kio.core.providers.knowledge_provider import KnowledgeProvider
        from mini_kio.core.provider_contract import ProviderHealth
        kp = KnowledgeProvider()
        assert kp.health() == ProviderHealth.HEALTHY

    def test_eight_capabilities_exposed(self):
        from mini_kio.core.providers.knowledge_provider import KnowledgeProvider
        kp = KnowledgeProvider()
        caps = [c.name for c in kp.capabilities()]
        assert len(caps) == 10
        for required in ("web_search", "fetch_url", "fetch_wikipedia", "healthcheck",
                         "list_new_videos", "read_feeds", "paginated_get", "verify_hmac",
                         "get_weather", "validate_lead"):
            assert required in caps, f"Missing capability: {required}"

    def test_all_read_only_category(self):
        from mini_kio.core.providers.knowledge_provider import KnowledgeProvider
        kp = KnowledgeProvider()
        for cap in kp.capabilities():
            assert cap.category == "read_only", f"{cap.name} is {cap.category}"


class TestWebSearch:
    def test_search_returns_success(self):
        from mini_kio.core.providers.knowledge_provider import KnowledgeProvider
        kp = KnowledgeProvider()
        result = kp.execute("web_search", "what is python", max_results=3)
        assert result["success"]
        assert "result" in result

    def test_search_via_boundary(self):
        from mini_kio.core.execution_boundary import execute_action
        os.environ.pop("KIO_TEST_MODE", None)
        result = execute_action("web_search", "what is asyncio in python")
        assert result["success"]

    def test_search_empty_query(self):
        from mini_kio.core.providers.knowledge_provider import KnowledgeProvider
        kp = KnowledgeProvider()
        result = kp.execute("web_search", "", max_results=3)
        assert not result["success"]
        assert "empty" in result["message"].lower()


class TestFetchUrl:
    def test_fetch_returns_content(self):
        from mini_kio.core.providers.knowledge_provider import KnowledgeProvider
        kp = KnowledgeProvider()
        result = kp.execute("fetch_url", "https://example.com")
        assert result["success"]
        assert "content" in result
        assert isinstance(result["content"], str)
        assert len(result["content"]) > 0

    def test_fetch_invalid_url(self):
        from mini_kio.core.providers.knowledge_provider import KnowledgeProvider
        kp = KnowledgeProvider()
        result = kp.execute("fetch_url", "not-a-url")
        assert not result["success"]
        assert "invalid" in result["message"].lower()

    def test_fetch_via_boundary(self):
        from mini_kio.core.execution_boundary import execute_action
        os.environ.pop("KIO_TEST_MODE", None)
        result = execute_action("fetch_url", "https://example.com")
        assert result["success"]
        assert "content" in result


class TestFetchWikipedia:
    def test_fetch_wikipedia_returns_summary(self):
        from mini_kio.core.providers.knowledge_provider import KnowledgeProvider
        kp = KnowledgeProvider()
        result = kp.execute("fetch_wikipedia", "Python (programming language)")
        assert result["success"]
        assert "summary" in result
        assert isinstance(result["summary"], str)
        assert len(result["summary"]) > 0

    def test_fetch_wikipedia_query_present(self):
        from mini_kio.core.providers.knowledge_provider import KnowledgeProvider
        kp = KnowledgeProvider()
        result = kp.execute("fetch_wikipedia", "Wikipedia")
        assert result["success"]
        assert "query" in result

    def test_fetch_wikipedia_unknown_topic(self):
        from mini_kio.core.providers.knowledge_provider import KnowledgeProvider
        kp = KnowledgeProvider()
        result = kp.execute("fetch_wikipedia", "xyznonexistenttopic12345abc")
        assert isinstance(result, dict)


class TestHealthcheck:
    def test_healthcheck_returns_status(self):
        from mini_kio.core.providers.knowledge_provider import KnowledgeProvider
        kp = KnowledgeProvider()
        result = kp.execute("healthcheck", "https://example.com")
        assert result["success"]
        assert "status_code" in result
        assert "healthy" in result

    def test_healthcheck_healthy_site(self):
        from mini_kio.core.providers.knowledge_provider import KnowledgeProvider
        kp = KnowledgeProvider()
        result = kp.execute("healthcheck", "https://example.com")
        assert result["success"]
        assert result["status_code"] == 200
        assert result["healthy"] is True

    def test_healthcheck_via_boundary(self):
        from mini_kio.core.execution_boundary import execute_action
        os.environ.pop("KIO_TEST_MODE", None)
        result = execute_action("healthcheck", "https://example.com")
        assert result["success"]
        assert "healthy" in result


class TestListNewVideos:
    def test_list_new_videos_returns_list(self):
        from mini_kio.core.providers.knowledge_provider import KnowledgeProvider
        kp = KnowledgeProvider()
        result = kp.execute("list_new_videos", "UC_xKXG3C4TjhAOyQ9RF0c8w")
        assert isinstance(result, dict)
        assert "videos" in result

    def test_list_new_videos_no_sources(self):
        from mini_kio.core.providers.knowledge_provider import KnowledgeProvider
        kp = KnowledgeProvider()
        result = kp.execute("list_new_videos", "")
        assert not result["success"]
        assert "no sources" in result["message"].lower()

    def test_list_new_videos_via_boundary(self):
        from mini_kio.core.execution_boundary import execute_action
        os.environ.pop("KIO_TEST_MODE", None)
        result = execute_action("list_new_videos", "UC_xKXG3C4TjhAOyQ9RF0c8w")
        assert isinstance(result, dict)
        assert "videos" in result


class TestReadFeeds:
    def test_read_feeds_returns_items(self):
        from mini_kio.core.providers.knowledge_provider import KnowledgeProvider
        kp = KnowledgeProvider()
        result = kp.execute("read_feeds", "https://feeds.bbci.co.uk/news/rss.xml")
        assert result["success"]
        assert "items" in result
        assert isinstance(result["items"], list)

    def test_read_feeds_invalid_url(self):
        from mini_kio.core.providers.knowledge_provider import KnowledgeProvider
        kp = KnowledgeProvider()
        result = kp.execute("read_feeds", "")
        assert not result["success"]

    def test_read_feeds_via_boundary(self):
        from mini_kio.core.execution_boundary import execute_action
        os.environ.pop("KIO_TEST_MODE", None)
        result = execute_action("read_feeds", "https://feeds.bbci.co.uk/news/rss.xml")
        assert result["success"]


class TestPaginatedGet:
    def test_paginated_get_returns_items(self):
        from mini_kio.core.providers.knowledge_provider import KnowledgeProvider
        kp = KnowledgeProvider()
        result = kp.execute("paginated_get", "https://api.github.com/repos/python/cpython/issues", max_items=3)
        assert result["success"]
        assert "items" in result
        assert isinstance(result["items"], list)

    def test_paginated_get_via_boundary(self):
        from mini_kio.core.execution_boundary import execute_action
        os.environ.pop("KIO_TEST_MODE", None)
        result = execute_action("paginated_get", "https://api.github.com/repos/python/cpython/issues", max_items=2)
        assert result["success"]


class TestVerifyHmac:
    def test_verify_hmac_valid(self):
        from mini_kio.core.providers.knowledge_provider import KnowledgeProvider
        import hmac
        import hashlib
        kp = KnowledgeProvider()
        secret = "test_secret"
        body = '{"event":"push"}'
        sig = hmac.new(secret.encode(), body.encode(), hashlib.sha256).hexdigest()
        result = kp.execute("verify_hmac", body, secret=secret, signature=sig)
        assert result["success"]
        assert result["valid"] is True

    def test_verify_hmac_invalid(self):
        from mini_kio.core.providers.knowledge_provider import KnowledgeProvider
        kp = KnowledgeProvider()
        result = kp.execute("verify_hmac", "data", secret="s", signature="bad_sig")
        assert result["success"]
        assert result["valid"] is False

    def test_verify_hmac_missing_secret(self):
        from mini_kio.core.providers.knowledge_provider import KnowledgeProvider
        kp = KnowledgeProvider()
        result = kp.execute("verify_hmac", "data", signature="sig")
        assert not result["success"]
        assert "no secret" in result["message"].lower()

    def test_verify_hmac_no_signature_returns_computed(self):
        from mini_kio.core.providers.knowledge_provider import KnowledgeProvider
        kp = KnowledgeProvider()
        result = kp.execute("verify_hmac", "data", secret="s")
        assert result["success"]
        assert result["valid"] is True
        assert "computed_hash" in result

    def test_verify_hmac_via_boundary(self):
        from mini_kio.core.execution_boundary import execute_action
        os.environ.pop("KIO_TEST_MODE", None)
        import hmac
        import hashlib
        secret = "boundary_test"
        body = "test_payload"
        sig = hmac.new(secret.encode(), body.encode(), hashlib.sha256).hexdigest()
        result = execute_action("verify_hmac", body, secret=secret, signature=sig)
        assert result["success"]
        assert result["valid"] is True


class TestStepRunnerMapping:
    def test_knowledge_actions_resolve(self):
        from mini_kio.automation.step_runner import StepRunner
        runner = StepRunner()
        expected = [
            ("knowledge", "web_search"),
            ("knowledge", "fetch_url"),
            ("knowledge", "fetch_wikipedia"),
            ("knowledge", "healthcheck"),
            ("knowledge", "list_new_videos"),
            ("knowledge", "read_feeds"),
            ("knowledge", "paginated_get"),
            ("knowledge", "verify_hmac"),
            ("knowledge", "query"),
            ("knowledge", "search"),
            ("knowledge", "retrieve"),
            ("knowledge", "batch_lookup"),
        ]
        for key in expected:
            assert key in runner._ACTION_MAP, f"Missing: {key}"

    def test_knowledge_query_fallback_to_web_search(self):
        from mini_kio.automation.step_runner import StepRunner
        runner = StepRunner()
        assert runner._ACTION_MAP[("knowledge", "query")] == "web_search"
        assert runner._ACTION_MAP[("knowledge", "search")] == "web_search"
        assert runner._ACTION_MAP[("knowledge", "batch_lookup")] == "web_search"


class TestTestMode:
    def test_test_mode_stubs_all_actions(self):
        """In KIO_TEST_MODE, all knowledge actions should return success+blocked."""
        from mini_kio.core.providers.knowledge_provider import KnowledgeProvider
        os.environ["KIO_TEST_MODE"] = "1"
        try:
            kp = KnowledgeProvider()
            for action in ["web_search", "fetch_url", "fetch_wikipedia", "healthcheck",
                           "list_new_videos", "read_feeds", "paginated_get", "verify_hmac"]:
                result = kp.execute(action, "test", query="q", url="http://x.com",
                                    secret="s", signature="sig", body="b",
                                    sources=["ch1"], feeds=["http://x.com/rss"])
                assert result["success"], f"{action} failed in test mode"
                assert result.get("test_mode") or result.get("blocked") or "Test mode" in result.get("message", "")
        finally:
            os.environ.pop("KIO_TEST_MODE", None)

    def test_test_mode_category_read_only(self):
        from mini_kio.core.providers.knowledge_provider import KnowledgeProvider
        os.environ["KIO_TEST_MODE"] = "1"
        try:
            kp = KnowledgeProvider()
            for cap in kp.capabilities():
                assert cap.category == "read_only", f"{cap.name} not read_only"
        finally:
            os.environ.pop("KIO_TEST_MODE", None)


if __name__ == "__main__":
    import pytest
    sys.exit(pytest.main([__file__, "-v"]))
