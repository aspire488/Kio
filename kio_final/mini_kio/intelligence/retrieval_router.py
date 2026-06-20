"""
mini_kio/intelligence/retrieval_router.py

Unified Retrieval Layer
======================
Hierarchy:
  1. Exa
  2. Tavily
  3. Jina Reader
  4. Wikipedia
  5. DuckDuckGo
  6. Existing media providers (YouTube, Spotify)

Returns RetrievalResult for downstream consumption.
"""

from __future__ import annotations

import logging
import os
import re
import time
from dataclasses import dataclass
from enum import Enum
from typing import Optional, List, Dict, Any

import requests
from mini_kio.media.intelligence.media_intelligence_models import TopicType

logger = logging.getLogger(__name__)

_USER_AGENT = "KIO/1.0 (Desktop Assistant; retrieval_router)"
_HEADERS = {"User-Agent": _USER_AGENT}

@dataclass
class RetrievalResult:
    title: str
    summary: str
    source: str
    confidence: float
    entity: str
    topic: TopicType
    url: Optional[str] = None
    raw_content: str = ""

class RetrievalRouter:
    """
    Routes queries through the retrieval hierarchy.
    """

    def __init__(self, timeout_s: float = 8.0) -> None:
        self.timeout_s = timeout_s
        self.stats = {
            "exa_hits": 0,
            "tavily_hits": 0,
            "jina_hits": 0,
            "wikipedia_hits": 0,
            "ddg_hits": 0,
            "media_hits": 0,
            "total_calls": 0,
        }

    def retrieve(self, query: str, topic_hint: Optional[TopicType] = None) -> Optional[RetrievalResult]:
        """
        Main entry point for hierarchal retrieval.
        """
        self.stats["total_calls"] += 1
        q = query.strip()
        if not q:
            return None

        # 1. Exa
        try:
            res = self._try_exa(q, topic_hint)
            if res:
                self.stats["exa_hits"] += 1
                return res
        except Exception as e:
            logger.debug(f"Exa failed: {e}")

        # 2. Tavily
        try:
            res = self._try_tavily(q, topic_hint)
            if res:
                self.stats["tavily_hits"] += 1
                return res
        except Exception as e:
            logger.debug(f"Tavily failed: {e}")

        # 3. Jina Reader
        try:
            res = self._try_jina(q, topic_hint)
            if res:
                self.stats["jina_hits"] += 1
                return res
        except Exception as e:
            logger.debug(f"Jina failed: {e}")

        # 4. Wikipedia
        try:
            res = self._try_wikipedia(q, topic_hint)
            if res:
                self.stats["wikipedia_hits"] += 1
                return res
        except Exception as e:
            logger.debug(f"Wikipedia failed: {e}")

        # 5. DuckDuckGo
        try:
            res = self._try_ddg(q, topic_hint)
            if res:
                self.stats["ddg_hits"] += 1
                return res
        except Exception as e:
            logger.debug(f"DDG failed: {e}")

        # 6. Existing media providers
        try:
            res = self._try_media_providers(q, topic_hint)
            if res:
                self.stats["media_hits"] += 1
                return res
        except Exception as e:
            logger.debug(f"Media providers failed: {e}")

        return None

    def _try_exa(self, query: str, topic: Optional[TopicType]) -> Optional[RetrievalResult]:
        api_key = os.getenv("EXA_API_KEY")
        if not api_key:
            return None
        
        url = "https://api.exa.ai/search"
        headers = {
            "x-api-key": api_key,
            "Content-Type": "application/json",
            "User-Agent": _USER_AGENT
        }
        payload = {
            "query": query,
            "type": "neural",
            "numResults": 1,
            "contents": {"text": True},
        }
        resp = requests.post(url, headers=headers, json=payload, timeout=self.timeout_s)
        if resp.status_code == 200:
            data = resp.json()
            results = data.get("results", [])
            if results:
                top = results[0]
                text = top.get("text") or top.get("contents", {}).get("text", "")
                return RetrievalResult(
                    title=top.get("title", "") or "",
                    summary=text[:800],
                    source="Exa",
                    confidence=0.95,
                    entity=query,
                    topic=topic or TopicType.UNKNOWN,
                    url=top.get("url"),
                    raw_content=text
                )
        return None

    def _try_tavily(self, query: str, topic: Optional[TopicType]) -> Optional[RetrievalResult]:
        api_key = os.getenv("TAVILY_API_KEY")
        if not api_key:
            return None
        
        url = "https://api.tavily.com/search"
        payload = {
            "api_key": api_key,
            "query": query,
            "search_depth": "advanced",
            "include_answer": True,
            "max_results": 1,
        }
        resp = requests.post(url, json=payload, timeout=self.timeout_s)
        if resp.status_code == 200:
            data = resp.json()
            results = data.get("results", [])
            if results:
                top = results[0]
                content = data.get("answer") or top.get("content", "")
                return RetrievalResult(
                    title=top.get("title", ""),
                    summary=content[:800],
                    source="Tavily",
                    confidence=0.9,
                    entity=query,
                    topic=topic or TopicType.UNKNOWN,
                    url=top.get("url"),
                    raw_content=content
                )
        return None

    def _try_jina(self, query: str, topic: Optional[TopicType]) -> Optional[RetrievalResult]:
        from urllib.parse import quote_plus
        encoded_q = quote_plus(query)
        url = f"https://s.jina.ai/{encoded_q}"
        headers = {"Accept": "application/json", "User-Agent": _USER_AGENT}
        api_key = os.getenv("JINA_API_KEY")
        if api_key:
            headers["Authorization"] = f"Bearer {api_key}"
        
        resp = requests.get(url, headers=headers, timeout=self.timeout_s)
        if resp.status_code == 200:
            data = resp.json()
            results = data.get("data", [])
            if results:
                top = results[0]
                return RetrievalResult(
                    title=top.get("title", ""),
                    summary=top.get("content", "")[:800],
                    source="Jina Reader",
                    confidence=0.85,
                    entity=query,
                    topic=topic or TopicType.UNKNOWN,
                    url=top.get("url"),
                    raw_content=top.get("content", "")
                )
        return None

    def _try_wikipedia(self, query: str, topic: Optional[TopicType]) -> Optional[RetrievalResult]:
        from urllib.parse import quote
        search_url = "https://en.wikipedia.org/w/api.php"
        search_params = {
            "action": "opensearch",
            "search": query,
            "limit": 1,
            "format": "json",
        }
        resp = requests.get(search_url, params=search_params, headers=_HEADERS, timeout=self.timeout_s)
        if resp.status_code == 200:
            data = resp.json()
            if data and len(data) > 1 and data[1]:
                title = data[1][0]
                rest_url = f"https://en.wikipedia.org/api/rest_v1/page/summary/{quote(title, safe='')}"
                resp2 = requests.get(rest_url, headers=_HEADERS, timeout=self.timeout_s)
                if resp2.status_code == 200:
                    data2 = resp2.json()
                    extract = data2.get("extract", "")
                    if extract:
                        return RetrievalResult(
                            title=title,
                            summary=extract[:800],
                            source="Wikipedia",
                            confidence=0.8,
                            entity=title,
                            topic=topic or TopicType.UNKNOWN,
                            url=data2.get("content_urls", {}).get("desktop", {}).get("page"),
                            raw_content=extract
                        )
        return None

    def _try_ddg(self, query: str, topic: Optional[TopicType]) -> Optional[RetrievalResult]:
        try:
            from duckduckgo_search import DDGS
            with DDGS() as ddgs:
                results = list(ddgs.text(query, max_results=3))
            if results:
                top = results[0]
                combined = "\n".join([r.get("body", "") for r in results if r.get("body")])
                return RetrievalResult(
                    title=top.get("title", ""),
                    summary=top.get("body", "")[:800],
                    source="DuckDuckGo",
                    confidence=0.75,
                    entity=query,
                    topic=topic or TopicType.UNKNOWN,
                    url=top.get("href"),
                    raw_content=combined
                )
        except Exception:
            pass
        return None

    def _try_media_providers(self, query: str, topic: Optional[TopicType]) -> Optional[RetrievalResult]:
        try:
            from mini_kio.media.providers.youtube_provider import YouTubeProvider
            yt = YouTubeProvider()
            results = yt.search(query, limit=1)
            if results:
                top = results[0]
                return RetrievalResult(
                    title=top.name,
                    summary=f"Media result from YouTube: {top.name}",
                    source="YouTube",
                    confidence=0.7,
                    entity=top.name,
                    topic=topic or TopicType.MUSIC if "song" in query.lower() else TopicType.MOVIES,
                    url=top.url,
                    raw_content=str(top.metadata)
                )
        except Exception:
            pass
        return None

