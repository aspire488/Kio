"""BrowserProvider — wraps browser_operator.py under ExecutionProvider contract."""

from __future__ import annotations

import logging
from typing import Any

from mini_kio.core.provider_contract import (
    ExecutionProvider, ProviderHealth, ProviderCapability,
)
from mini_kio.core.browser_operator import (
    play_youtube, search_youtube, BROWSER_OPERATOR_DESCRIPTOR,
)

logger = logging.getLogger(__name__)
_DESC = BROWSER_OPERATOR_DESCRIPTOR


class BrowserProvider(ExecutionProvider):
    def __init__(self):
        # Lazy import of BrowserFacade implementation
        from browser.facade import BrowserFacadeImpl
        self._facade = BrowserFacadeImpl()

    def id(self) -> str:
        return "browser"

    def capabilities(self) -> list[ProviderCapability]:
        return [
            ProviderCapability(name="play_youtube", category="external_open",
                               timeout_s=_DESC.get("timeout_seconds", 10),
                               ram_budget_mb=int(_DESC.get("ram_budget_mb", 8))),
            ProviderCapability(name="search_youtube", category="external_open",
                               timeout_s=_DESC.get("timeout_seconds", 10),
                               ram_budget_mb=int(_DESC.get("ram_budget_mb", 8))),
            # Workflow-declared browser capabilities
            ProviderCapability(name="browser", category="external_open",
                               timeout_s=30, ram_budget_mb=50),
            ProviderCapability(name="fetch_region", category="external_open",
                               timeout_s=30, ram_budget_mb=50),
            ProviderCapability(name="extract_price", category="external_open",
                               timeout_s=30, ram_budget_mb=50),
            ProviderCapability(name="extract_records", category="external_open",
                               timeout_s=30, ram_budget_mb=50),
            ProviderCapability(name="snapshot_sources", category="external_open",
                               timeout_s=60, ram_budget_mb=100),
            ProviderCapability(name="crawl_extract", category="external_open",
                               timeout_s=60, ram_budget_mb=100),
        ]

    def health(self) -> ProviderHealth:
        return ProviderHealth.HEALTHY

    def execute(self, action: str, target: str, **kwargs: Any) -> dict[str, Any]:
        # Delegate navigation and simple actions to BrowserFacade
        if action == "play_youtube":
            return dict(play_youtube(target))
        if action == "search_youtube":
            return dict(search_youtube(target))
        if action in ("open_url", "fetch_region", "crawl_extract"):
            url = kwargs.get("url", target)
            self._facade.navigate(url)
            # For crawl_extract, also extract tables and links
            if action == "crawl_extract":
                tables = self._facade.extract_tables()
                links = self._facade.extract_links()
                text = self._facade.get_text()
                return {"success": True, "url": url, "tables": tables,
                        "links": links, "text": text[:5000],
                        "message": f"Extracted content from {url}"}
            if action == "fetch_region":
                selector = kwargs.get("selector", "body")
                text = self._facade.get_text(selector)
                return {"success": True, "url": url, "text": text,
                        "message": f"Fetched region from {url}"}
            return {"success": True, "message": f"Opened {url}"}
        if action == "extract_price":
            url = kwargs.get("url", target)
            selector = kwargs.get("selector", "")
            self._facade.navigate(url)
            text = self._facade.get_text(selector) if selector else self._facade.get_text()
            return {"success": True, "url": url, "text": text,
                    "message": f"Extracted price data from {url}"}
        if action == "extract_records":
            url = kwargs.get("url", target)
            selector = kwargs.get("selector", "table")
            self._facade.navigate(url)
            tables = self._facade.extract_tables(selector)
            text = self._facade.get_text(selector if selector != "table" else "body")
            return {"success": True, "url": url, "tables": tables,
                    "text": text[:5000], "message": f"Extracted records from {url}"}
        if action == "snapshot_sources":
            urls = kwargs.get("urls", [target]) if isinstance(kwargs.get("urls"), list) else [target]
            snapshots = []
            for u in urls:
                try:
                    self._facade.navigate(u)
                    text = self._facade.get_text()
                    snapshots.append({"url": u, "text": text[:3000], "success": True})
                except Exception as exc:
                    snapshots.append({"url": u, "error": str(exc), "success": False})
            return {"success": True, "snapshots": snapshots,
                    "message": f"Snapshot {len(snapshots)} sources"}
        if action == "click":
            self._facade.click(target)
            return {"success": True, "message": f"Clicked {target}"}
        if action == "get_text":
            text = self._facade.get_text(target)
            return {"success": True, "text": text}
        return {"success": False, "message": f"BrowserProvider: unknown action {action}"}

    def verify(self, action: str, result: dict[str, Any]) -> dict[str, Any]:
        result.setdefault("probe_used", "browser_action")
        if result.get("success"):
            result.setdefault("verification_status", "passed")
            result.setdefault("outcome_class", "SUCCESS")
        else:
            result.setdefault("verification_status", "failed")
            result.setdefault("outcome_class", "FAILURE")
        return result
