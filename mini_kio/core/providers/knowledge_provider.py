"""KnowledgeProvider — wraps existing search/fetch infrastructure under ExecutionProvider contract.

Actions:
  web_search      — routed through KnowledgeRouter (Exa→Tavily→DDG→Wikipedia)
  fetch_url       — routed through Jina Reader (clean markdown extraction)
  fetch_wikipedia — routed through Wikipedia provider (summary extraction)
  healthcheck     — HTTP health probe (status code, latency, optional marker)
  list_new_videos — YouTube channel video listing (YouTube Data API or DDG fallback)
  read_feeds      — RSS/Atom feed parsing (needs feedparser; graceful fallback)
  paginated_get   — paginated REST API fetch (page-based pagination)
  verify_hmac     — HMAC signature verification (deterministic, no network)
"""

from __future__ import annotations

import hashlib
import hmac
import logging
import os
import time
from typing import Any

from mini_kio.core.provider_contract import ExecutionProvider, ProviderHealth, ProviderCapability

logger = logging.getLogger(__name__)

_KIO_TEST_MODE_CACHED = os.environ.get("KIO_TEST_MODE") == "1"


def _is_test_mode() -> bool:
    """Check KIO_TEST_MODE at call time (not import time) so tests can toggle it."""
    return os.environ.get("KIO_TEST_MODE") == "1"


class KnowledgeProvider(ExecutionProvider):
    def id(self) -> str:
        return "knowledge"

    def capabilities(self) -> list[ProviderCapability]:
        return [
            ProviderCapability(name="web_search", category="read_only", timeout_s=10, ram_budget_mb=10),
            ProviderCapability(name="fetch_url", category="read_only", timeout_s=15, ram_budget_mb=10),
            ProviderCapability(name="fetch_wikipedia", category="read_only", timeout_s=10, ram_budget_mb=5),
            ProviderCapability(name="healthcheck", category="read_only", timeout_s=15, ram_budget_mb=5),
            ProviderCapability(name="list_new_videos", category="read_only", timeout_s=15, ram_budget_mb=10),
            ProviderCapability(name="read_feeds", category="read_only", timeout_s=15, ram_budget_mb=10),
            ProviderCapability(name="paginated_get", category="read_only", timeout_s=30, ram_budget_mb=10),
            ProviderCapability(name="verify_hmac", category="read_only", timeout_s=1, ram_budget_mb=1),
            ProviderCapability(name="get_weather", category="read_only", timeout_s=10, ram_budget_mb=5),
            ProviderCapability(name="validate_lead", category="read_only", timeout_s=15, ram_budget_mb=10),
            ProviderCapability(name="vector_search", category="read_only", timeout_s=10, ram_budget_mb=50),
        ]

    def health(self) -> ProviderHealth:
        return ProviderHealth.HEALTHY

    def execute(self, action: str, target: str, **kwargs: Any) -> dict[str, Any]:
        if _is_test_mode():
            return self._test_stub(action, target, **kwargs)

        handlers = {
            "web_search": self._web_search,
            "fetch_url": self._fetch_url,
            "fetch_wikipedia": self._fetch_wikipedia,
            "healthcheck": self._healthcheck,
            "list_new_videos": self._list_new_videos,
            "read_feeds": self._read_feeds,
            "paginated_get": self._paginated_get,
            "verify_hmac": self._verify_hmac,
            "get_weather": self._get_weather,
            "validate_lead": self._validate_lead,
            "vector_search": self._vector_search,
        }
        handler = handlers.get(action)
        if handler:
            return handler(target, **kwargs)
        return {"success": False, "message": f"KnowledgeProvider: unknown action '{action}'"}

    # ── web_search ───────────────────────────────────────────────────
    def _web_search(self, target: str, **kwargs: Any) -> dict[str, Any]:
        """Search the web via KnowledgeRouter (Exa→Tavily→DDG→Wikipedia)."""
        query = kwargs.get("query", target)
        if not query or not query.strip():
            return {"success": False, "message": "web_search: empty query"}

        try:
            from mini_kio.knowledge.retrieval_router import KnowledgeRouter
            router = KnowledgeRouter()
            result = router.route(query)
            if not result:
                # route() requires is_knowledge_query(); fall back to route_freshness()
                result = router.route_freshness(query)
            if result:
                return {
                    "success": True,
                    "query": query,
                    "result": result,
                    "source": "knowledge_router",
                    "message": f"Web search returned results for '{query}'",
                }
            return {
                "success": False,
                "query": query,
                "message": f"No results found for '{query}'",
            }
        except Exception as exc:
            logger.warning("web_search failed for '%s': %s", query, exc)
            return {"success": False, "message": f"web_search error: {exc}"}

    # ── fetch_url ────────────────────────────────────────────────────
    def _fetch_url(self, target: str, **kwargs: Any) -> dict[str, Any]:
        """Fetch and extract content from a URL via Jina Reader."""
        url = kwargs.get("url", target)
        if not url or not url.startswith(("http://", "https://")):
            return {"success": False, "message": f"fetch_url: invalid URL '{url}'"}

        try:
            from mini_kio.knowledge.jina_reader_provider import read_url
            content = read_url(url)
            if content:
                return {
                    "success": True,
                    "url": url,
                    "content": content,
                    "content_length": len(content),
                    "message": f"Fetched {len(content)} chars from {url}",
                }
            return {
                "success": False,
                "url": url,
                "message": f"fetch_url: no content returned for {url}",
            }
        except Exception as exc:
            logger.warning("fetch_url failed for '%s': %s", url, exc)
            return {"success": False, "message": f"fetch_url error: {exc}"}

    # ── fetch_wikipedia ──────────────────────────────────────────────
    def _fetch_wikipedia(self, target: str, **kwargs: Any) -> dict[str, Any]:
        """Fetch a Wikipedia summary for a topic."""
        query = kwargs.get("query", target)
        if not query or not query.strip():
            return {"success": False, "message": "fetch_wikipedia: empty query"}

        try:
            from mini_kio.knowledge.wikipedia_provider import fetch_summary
            summary = fetch_summary(query)
            if summary:
                return {
                    "success": True,
                    "query": query,
                    "summary": summary,
                    "source": "wikipedia",
                    "message": f"Wikipedia summary for '{query}'",
                }
            return {
                "success": False,
                "query": query,
                "message": f"No Wikipedia article found for '{query}'",
            }
        except Exception as exc:
            logger.warning("fetch_wikipedia failed for '%s': %s", query, exc)
            return {"success": False, "message": f"fetch_wikipedia error: {exc}"}

    # ── healthcheck ──────────────────────────────────────────────────
    def _healthcheck(self, target: str, **kwargs: Any) -> dict[str, Any]:
        """HTTP health probe: GET URL, check status code, latency, optional marker."""
        import requests as _requests

        url = kwargs.get("url", target)
        if not url or not url.startswith(("http://", "https://")):
            return {"success": False, "message": f"healthcheck: invalid URL '{url}'"}

        marker = kwargs.get("marker", "")
        slow_ms = int(kwargs.get("slow_ms", 3000))

        try:
            start = time.monotonic()
            resp = _requests.get(url, timeout=10, allow_redirects=True)
            elapsed_ms = int((time.monotonic() - start) * 1000)

            status_code = resp.status_code
            body = resp.text or ""
            marker_ok = True
            if marker:
                marker_ok = marker in body

            is_slow = elapsed_ms > slow_ms
            is_down = status_code >= 400
            healthy = not is_down and marker_ok and not is_slow

            return {
                "success": True,
                "status_code": status_code,
                "response_ms": elapsed_ms,
                "marker_ok": marker_ok,
                "is_slow": is_slow,
                "is_down": is_down,
                "healthy": healthy,
                "url": url,
                "message": f"HTTP {status_code} in {elapsed_ms}ms" + (" (SLOW)" if is_slow else ""),
            }
        except _requests.Timeout:
            return {
                "success": True,
                "status_code": 0,
                "response_ms": -1,
                "marker_ok": False,
                "is_slow": False,
                "is_down": True,
                "healthy": False,
                "url": url,
                "message": f"healthcheck: timeout for {url}",
            }
        except Exception as exc:
            return {
                "success": True,
                "status_code": 0,
                "response_ms": -1,
                "marker_ok": False,
                "is_slow": False,
                "is_down": True,
                "healthy": False,
                "url": url,
                "message": f"healthcheck: error for {url}: {exc}",
            }

    # ── list_new_videos ──────────────────────────────────────────────
    def _list_new_videos(self, target: str, **kwargs: Any) -> dict[str, Any]:
        """List recent videos from YouTube channels via YouTube Data API or DDG fallback."""
        sources = kwargs.get("sources", [])
        if isinstance(sources, str):
            sources = [s.strip() for s in sources.split(",") if s.strip()]
        if not sources and target:
            sources = [target.strip()] if target.strip() else []
        if not sources:
            return {"success": False, "message": "list_new_videos: no sources provided"}

        all_videos: list[dict[str, Any]] = []

        for source in sources[:5]:  # cap at 5 channels
            videos = self._fetch_channel_videos(source)
            all_videos.extend(videos)

        if all_videos:
            return {
                "success": True,
                "videos": all_videos,
                "count": len(all_videos),
                "message": f"Found {len(all_videos)} videos across {len(sources)} sources",
            }
        return {
            "success": False,
            "videos": [],
            "message": "No videos found from any source",
        }

    def _fetch_channel_videos(self, channel_id: str) -> list[dict[str, Any]]:
        """Fetch recent videos from a YouTube channel."""
        import requests as _requests
        from mini_kio.core import config

        # Try YouTube Data API first
        if config.YOUTUBE_ENABLED and config.YOUTUBE_API_KEY:
            try:
                url = "https://www.googleapis.com/youtube/v3/search"
                params = {
                    "part": "snippet",
                    "channelId": channel_id,
                    "order": "date",
                    "maxResults": 5,
                    "type": "video",
                    "key": config.YOUTUBE_API_KEY,
                }
                resp = _requests.get(url, params=params, timeout=10)
                resp.raise_for_status()
                data = resp.json()
                videos = []
                for item in data.get("items", []):
                    snippet = item.get("snippet", {})
                    videos.append({
                        "video_id": item.get("id", {}).get("videoId", ""),
                        "title": snippet.get("title", ""),
                        "channel": snippet.get("channelTitle", ""),
                        "published_at": snippet.get("publishedAt", ""),
                        "description": snippet.get("description", "")[:200],
                    })
                return videos
            except Exception as exc:
                logger.debug("YouTube API failed for '%s': %s", channel_id, exc)

        # Fallback: DuckDuckGo search
        try:
            from mini_kio.knowledge import duckduckgo_provider
            result = duckduckgo_provider.search(f"site:youtube.com {channel_id} latest videos")
            if result:
                return [{"video_id": "", "title": result[:100], "channel": channel_id, "source": "ddg"}]
        except Exception:
            pass

        return []

    # ── read_feeds ───────────────────────────────────────────────────
    def _read_feeds(self, target: str, **kwargs: Any) -> dict[str, Any]:
        """Parse RSS/Atom feeds and return items."""
        feeds = kwargs.get("feeds", [])
        if isinstance(feeds, str):
            feeds = [f.strip() for f in feeds.split(",") if f.strip()]
        if not feeds and target:
            # Single URL as target → treat as one feed
            feeds = [target.strip()] if target.strip() else []
        if not feeds:
            return {"success": False, "message": "read_feeds: no feeds provided"}

        try:
            import feedparser
        except ImportError:
            return {
                "success": False,
                "message": "read_feeds: feedparser package not installed (pip install feedparser)",
            }

        import requests as _requests

        all_items: list[dict[str, Any]] = []
        for feed_url in feeds[:10]:  # cap at 10 feeds
            try:
                resp = _requests.get(feed_url, timeout=10, headers={"User-Agent": "KIO/1.0"})
                resp.raise_for_status()
                parsed = feedparser.parse(resp.text)
                for entry in parsed.entries[:20]:  # cap per feed
                    all_items.append({
                        "title": entry.get("title", ""),
                        "link": entry.get("link", ""),
                        "summary": entry.get("summary", "")[:500],
                        "published": entry.get("published", ""),
                        "feed_url": feed_url,
                    })
            except Exception as exc:
                logger.debug("read_feeds: failed for '%s': %s", feed_url, exc)

        if all_items:
            return {
                "success": True,
                "items": all_items,
                "count": len(all_items),
                "message": f"Parsed {len(all_items)} items from {len(feeds)} feeds",
            }
        return {
            "success": False,
            "items": [],
            "message": "No items found from any feed",
        }

    # ── paginated_get ────────────────────────────────────────────────
    def _paginated_get(self, target: str, **kwargs: Any) -> dict[str, Any]:
        """Paginated REST API fetch with configurable page parameter."""
        import requests as _requests

        url = kwargs.get("url", target)
        if not url or not url.startswith(("http://", "https://")):
            return {"success": False, "message": f"paginated_get: invalid URL '{url}'"}

        page_param = kwargs.get("page_param", "page")
        auth = kwargs.get("auth", "")
        max_pages = int(kwargs.get("max_pages", 10))

        headers: dict[str, str] = {}
        if auth:
            headers["Authorization"] = f"Bearer {auth}"

        all_items: list[Any] = []
        current_page = 1

        try:
            while current_page <= max_pages:
                params = {page_param: current_page}
                resp = _requests.get(url, params=params, headers=headers, timeout=10)
                resp.raise_for_status()
                data = resp.json()

                # Handle different response shapes
                if isinstance(data, list):
                    items = data
                elif isinstance(data, dict):
                    items = data.get("results", data.get("items", data.get("data", [])))
                    if not items and data:
                        items = [data]
                else:
                    break

                if not items:
                    break

                all_items.extend(items)
                current_page += 1

                # If fewer items than expected, last page
                if len(items) < 10:
                    break

            return {
                "success": True,
                "items": all_items,
                "count": len(all_items),
                "pages_fetched": current_page - 1,
                "message": f"Fetched {len(all_items)} items across {current_page - 1} pages",
            }
        except Exception as exc:
            return {
                "success": bool(all_items),
                "items": all_items,
                "count": len(all_items),
                "message": f"paginated_get stopped at page {current_page}: {exc}",
            }

    # ── verify_hmac ──────────────────────────────────────────────────
    def _verify_hmac(self, target: str, **kwargs: Any) -> dict[str, Any]:
        """Verify HMAC signature on a webhook payload. Pure computation, no network."""
        import hmac as _hmac

        payload = kwargs.get("payload", target or "")
        secret = kwargs.get("secret", "")
        signature = kwargs.get("signature", "")
        algorithm = kwargs.get("algorithm", "sha256")

        if not secret:
            return {"success": False, "message": "verify_hmac: no secret provided"}

        if isinstance(payload, dict):
            import json
            payload = json.dumps(payload, separators=(",", ":"))

        try:
            expected = _hmac.new(
                secret.encode("utf-8"),
                payload.encode("utf-8"),
                getattr(hashlib, algorithm, hashlib.sha256),
            ).hexdigest()

            if signature:
                valid = _hmac.compare_digest(expected, signature)
            else:
                # No signature provided — return computed hash for user comparison
                valid = True
                signature = expected

            return {
                "success": True,
                "valid": valid,
                "computed_hash": expected,
                "algorithm": algorithm,
                "message": "HMAC verified" if valid else "HMAC mismatch",
            }
        except Exception as exc:
            return {"success": False, "message": f"verify_hmac error: {exc}"}

    # ── get_weather ──────────────────────────────────────────────────
    def _get_weather(self, target: str, **kwargs: Any) -> dict[str, Any]:
        """Get weather for a location via Open-Meteo (no API key required)."""
        location = kwargs.get("location", target)
        if not location or not location.strip():
            return {"success": False, "message": "get_weather: empty location"}
        try:
            from mini_kio.core.utilities import weather_answer
            result = weather_answer(location)
            return {
                "success": bool(result.get("success")),
                "location": location,
                "answer": result.get("answer", ""),
                "temperature": result.get("temperature"),
                "unit": result.get("unit", "celsius"),
                "message": result.get("message", f"Weather for {location}"),
            }
        except Exception as exc:
            return {"success": False, "message": f"get_weather error: {exc}"}

    # ── validate_lead ───────────────────────────────────────────────
    def _validate_lead(self, target: str, **kwargs: Any) -> dict[str, Any]:
        """Validate a lead by cross-referencing name, email, or company against the web."""
        import re as _re

        query = kwargs.get("query", target)
        if not query or not str(query).strip():
            return {"success": False, "message": "validate_lead: empty query"}

        company = kwargs.get("company", "")
        email = kwargs.get("email", "")

        # 1. Email domain verification
        domain_valid = False
        if email and "@" in str(email):
            domain = str(email).split("@")[-1]
            result = self._fetch_url(f"https://{domain}", max_chars=500)
            domain_valid = result.get("success", False)

        # 2. Company existence check
        company_found = False
        search_term = company or str(query).strip()
        web_result = self._web_search(f'"{search_term}" company', max_results=3)
        if web_result.get("success") and web_result.get("result"):
            company_found = True

        # 3. Wikipedia cross-ref
        wiki_result = self._fetch_wikipedia(search_term)
        has_wiki = wiki_result.get("success", False)

        # 4. Email pattern check
        email_pattern_valid = False
        if email:
            email_pattern_valid = bool(_re.match(
                r'^[a-zA-Z0-9._%+-]+@[a-zA-Z0-9.-]+\.[a-zA-Z]{2,}$', str(email)
            ))

        # Composite confidence
        score = sum([
            domain_valid * 0.3,
            company_found * 0.35,
            has_wiki * 0.15,
            email_pattern_valid * 0.2,
        ])
        confidence = round(score, 2)

        return {
            "success": True,
            "valid": confidence >= 0.5,
            "confidence": confidence,
            "checks": {
                "domain_reachable": domain_valid,
                "company_found_online": company_found,
                "has_wikipedia": has_wiki,
                "email_pattern_valid": email_pattern_valid,
            },
            "message": f"Lead validation: confidence={confidence:.0%} ({'VALID' if confidence >= 0.5 else 'SUSPICIOUS'})",
        }

    # ── vector_search ────────────────────────────────────────────────
    def _vector_search(self, target: str, **kwargs: Any) -> dict[str, Any]:
        """Semantic vector search over provided documents using sentence-transformers."""
        query = kwargs.get("query", target)
        if not query or not str(query).strip():
            return {"success": False, "message": "vector_search: empty query"}

        documents = kwargs.get("documents", [])
        if not documents:
            return {"success": False, "message": "vector_search: no documents provided; pass documents=[...]"}

        try:
            from mini_kio.companion.semantic import compute_embedding, compute_embeddings
            import numpy as np

            query_vec = compute_embedding(str(query))
            if query_vec is None:
                return {"success": False, "message": "vector_search: embedding model unavailable (sentence-transformers not installed)"}

            doc_texts = [d if isinstance(d, str) else d.get("text", str(d)) for d in documents]
            doc_vecs = compute_embeddings(doc_texts)
            if doc_vecs is None:
                return {"success": False, "message": "vector_search: failed to compute document embeddings"}

            # Cosine similarity (embeddings are normalized)
            scores = np.dot(doc_vecs, query_vec)
            top_k = int(kwargs.get("top_k", 5))
            top_indices = np.argsort(scores)[::-1][:top_k]

            results = []
            for idx in top_indices:
                i = int(idx)
                results.append({
                    "rank": len(results) + 1,
                    "score": float(scores[i]),
                    "text": doc_texts[i][:500],
                    "index": i,
                })

            return {
                "success": True,
                "query": str(query),
                "results": results,
                "count": len(results),
                "message": f"vector_search: {len(results)} results for '{query}'",
            }
        except Exception as exc:
            logger.warning("vector_search failed for '%s': %s", query, exc)
            return {"success": False, "message": f"vector_search error: {exc}"}

    # ── test stub ────────────────────────────────────────────────────
    def _test_stub(self, action: str, target: str, **kwargs: Any) -> dict[str, Any]:
        """Deterministic stub for test mode — returns structured success."""
        stubs = {
            "web_search": lambda: {
                "success": True, "query": kwargs.get("query", target),
                "result": f"[TEST MODE] search results for '{kwargs.get('query', target)}'",
                "source": "test_stub", "message": "Test mode web_search",
            },
            "fetch_url": lambda: {
                "success": True, "url": kwargs.get("url", target),
                "content": f"[TEST MODE] content from {kwargs.get('url', target)}",
                "content_length": 50, "message": "Test mode fetch_url",
            },
            "fetch_wikipedia": lambda: {
                "success": True, "query": kwargs.get("query", target),
                "summary": f"[TEST MODE] Wikipedia summary for '{kwargs.get('query', target)}'",
                "source": "test_stub", "message": "Test mode fetch_wikipedia",
            },
            "healthcheck": lambda: {
                "success": True, "status_code": 200, "response_ms": 42,
                "marker_ok": True, "is_slow": False, "is_down": False,
                "healthy": True, "url": kwargs.get("url", target),
                "message": "Test mode healthcheck",
            },
            "list_new_videos": lambda: {
                "success": True, "videos": [
                    {"video_id": "test123", "title": "Test Video", "channel": "Test Channel"}
                ], "count": 1, "message": "Test mode list_new_videos",
            },
            "read_feeds": lambda: {
                "success": True, "items": [
                    {"title": "Test Item", "link": "http://example.com", "summary": "Test summary"}
                ], "count": 1, "message": "Test mode read_feeds",
            },
            "paginated_get": lambda: {
                "success": True, "items": [{"id": 1, "name": "test"}],
                "count": 1, "pages_fetched": 1, "message": "Test mode paginated_get",
            },
            "verify_hmac": lambda: {
                "success": True, "valid": True, "computed_hash": "test_hash",
                "algorithm": "sha256", "message": "Test mode verify_hmac",
            },
            "get_weather": lambda: {
                "success": True, "location": kwargs.get("location", target),
                "answer": "[TEST MODE] Weather data", "temperature": 20,
                "unit": "celsius", "message": "Test mode get_weather",
            },
            "validate_lead": lambda: {
                "success": True, "valid": True, "confidence": 0.85,
                "checks": {"domain_reachable": True, "company_found_online": True,
                           "has_wikipedia": True, "email_pattern_valid": True},
                "message": "Test mode validate_lead: VALID (85%)",
            },
            "vector_search": lambda: {
                "success": True, "query": kwargs.get("query", target),
                "results": [{"rank": 1, "score": 0.95, "text": "[TEST MODE] top result", "index": 0}],
                "count": 1, "message": "Test mode vector_search",
            },
        }
        stub = stubs.get(action)
        if stub:
            return stub()
        return {"success": False, "message": f"KnowledgeProvider: unknown action '{action}' (test mode)"}
