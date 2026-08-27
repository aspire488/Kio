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


def _normalize_date(value: str) -> Optional[str]:
    """Normalize a provider date to a sortable YYYY-MM-DD string.

    Accepts ISO timestamps ("2026-08-10T14:03:00Z"), bare dates
    ("2026-08-10"), and common prose dates ("August 10, 2026",
    "10 Aug 2026"). Returns None when the value cannot be parsed.
    """
    if not value:
        return None
    try:
        import datetime as _dt
        v = str(value).strip()
        if not v:
            return None
        # ISO / bare date
        m = re.match(r"^(\d{4})-(\d{1,2})-(\d{1,2})", v)
        if m:
            y, mo, d = int(m.group(1)), int(m.group(2)), int(m.group(3))
            return f"{y:04d}-{mo:02d}-{d:02d}"
        # "August 10, 2026" / "10 Aug 2026" / "Aug 10 2026"
        m = re.match(
            r"^(?:([A-Za-z]{3,9})\s+(\d{1,2}),?\s+(\d{4})|(\d{1,2})\s+([A-Za-z]{3,9})\s+(\d{4}))$",
            v,
        )
        if m:
            parts = m.groups()
            if parts[0]:
                mon, day, year = parts[0], int(parts[1]), int(parts[2])
            else:
                mon, day, year = parts[4], int(parts[3]), int(parts[5])
            month_num = {
                "january": 1, "february": 2, "march": 3, "april": 4,
                "may": 5, "june": 6, "july": 7, "august": 8,
                "september": 9, "october": 10, "november": 11, "december": 12,
            }
            for name, num in month_num.items():
                if mon.lower().startswith(name[:3]) and mon.lower() in (name, name[:3]):
                    return f"{int(year):04d}-{num:02d}-{day:02d}"
        # epoch seconds
        if v.replace(".", "", 1).isdigit() and len(v) >= 9:
            try:
                dt = _dt.datetime.fromtimestamp(float(v))
                return dt.strftime("%Y-%m-%d")
            except Exception:
                return None
    except Exception:
        return None
    return None

def _reconstruct_abstract(inverted: Optional[dict]) -> str:
    """Rebuild an abstract from OpenAlex's word->positions inverted index."""
    if not inverted:
        return ""
    n = 0
    for pos_list in inverted.values():
        n = max(n, max(pos_list, default=-1) + 1)
    words = [""] * n
    for word, positions in inverted.items():
        for p in positions:
            if 0 <= p < n:
                words[p] = word
    return " ".join(w for w in words if w).strip()


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
    # ── temporal evidence fields (currentness) ─────────────────────────────
    # Capture the article's own temporal signal so freshness can be ranked:
    # published_date is the primary evidence date; event_date is the date the
    # reported event happened when the article explicitly states it (e.g. an
    # August 10 article reporting an August 7 event). Both are best-effort
    # strings ("2026-08-07" / "2026-08-10") — None when the provider did not
    # expose them. A trustworthy OLD article can be obsolete; these fields let
    # the evidence layer demote it.
    published_date: Optional[str] = None
    updated_date: Optional[str] = None
    event_date: Optional[str] = None

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
            "openalex_hits": 0,
            "ddg_hits": 0,
            "media_hits": 0,
            "total_calls": 0,
        }

    def retrieve_evidence(self, query: str, topic_hint: Optional[TopicType] = None,
                          max_results: int = 4) -> List[RetrievalResult]:
        """Collect evidence from ALL healthy providers (not just the first).

        Currentness requirement: for changing-world questions, the first
        provider hit can be an OLD article that outranks newer reporting. This
        collects every provider that returns a result so the evidence layer can
        rank by publication date and reconcile contradictions instead of
        trusting one stale source. Each result carries its published_date when
        the provider exposes it.

        Bounded: never more than `max_results` total; a provider failure only
        skips that provider.
        """
        self.stats["total_calls"] += 1
        q = query.strip()
        if not q:
            return []
        results: List[RetrievalResult] = []
        try:  # noqa: S110
            for probe in (self._try_exa, self._try_tavily, self._try_jina,
                          self._try_wikipedia, self._try_openalex,
                          self._try_arxiv, self._try_ddg,
                          self._try_media_providers):
                if len(results) >= max_results:
                    break
                try:
                    res = probe(q, topic_hint)
                except Exception as exc:
                    logger.debug("[RETRIEVAL_EVIDENCE] provider failed: %s", exc)
                    continue
                if res and (res.raw_content or res.summary) and len((res.raw_content or res.summary)) >= 50:
                    results.append(res)
        except Exception:
            pass
        return results

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

        # 5. OpenAlex (scholarly, no key)
        try:
            res = self._try_openalex(q, topic_hint)
            if res:
                self.stats["openalex_hits"] += 1
                return res
        except Exception as e:
            logger.debug(f"OpenAlex failed: {e}")

        # 6. DuckDuckGo
        try:
            res = self._try_ddg(q, topic_hint)
            if res:
                self.stats["ddg_hits"] += 1
                return res
        except Exception as e:
            logger.debug(f"DDG failed: {e}")

        # 7. Existing media providers
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
                # Exa exposes publishedDate ("2026-08-10T...") and publishedTime
                # ("2026-08-10") — capture it so freshness can be ranked.
                pub = top.get("publishedDate") or top.get("publishedTime") or ""
                return RetrievalResult(
                    title=top.get("title", "") or "",
                    summary=text[:800],
                    source="Exa",
                    confidence=0.95,
                    entity=query,
                    topic=topic or TopicType.UNKNOWN,
                    url=top.get("url"),
                    raw_content=text,
                    published_date=_normalize_date(pub),
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
                # Tavily exposes published_date ("2026-08-10") — capture it.
                pub = top.get("published_date") or ""
                return RetrievalResult(
                    title=top.get("title", ""),
                    summary=content[:800],
                    source="Tavily",
                    confidence=0.9,
                    entity=query,
                    topic=topic or TopicType.UNKNOWN,
                    url=top.get("url"),
                    raw_content=content,
                    published_date=_normalize_date(pub),
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

    def _try_openalex(self, query: str, topic: Optional[TopicType]) -> Optional[RetrievalResult]:
        from urllib.parse import quote
        url = ("https://api.openalex.org/works?filter="
               + quote("default.search:" + query, safe="")
               + "&per-page=1&sort=relevance_score:desc")
        resp = requests.get(url, headers=_HEADERS, timeout=self.timeout_s)
        if resp.status_code == 200:
            data = resp.json()
            results = data.get("results") or []
            if results:
                top = results[0]
                title = top.get("display_name") or ""
                abstract = _reconstruct_abstract(top.get("abstract_inverted_index")) or title
                if not abstract:
                    return None
                return RetrievalResult(
                    title=title,
                    summary=abstract[:800],
                    source="OpenAlex",
                    confidence=0.8,
                    entity=query,
                    topic=topic or TopicType.UNKNOWN,
                    url=top.get("doi") or top.get("id"),
                    raw_content=abstract,
                    published_date=_normalize_date(top.get("publication_date") or ""),
                )
        return None

    def _try_arxiv(self, query: str, topic: Optional[TopicType]) -> Optional[RetrievalResult]:
        """arXiv API (no key) — scholarly preprints for science/math/CS
        queries. Complements OpenAlex: arXiv carries the full abstract and
        publication date for preprints the citation index may lag."""
        from urllib.parse import quote
        url = ("https://export.arxiv.org/api/query?search_query="
               + quote("all:" + query, safe="")
               + "&start=0&max_results=1&sortBy=submittedDate&sortOrder=descending")
        resp = requests.get(url, headers=_HEADERS, timeout=self.timeout_s)
        if resp.status_code != 200:
            return None
        import xml.etree.ElementTree as ET
        try:
            root = ET.fromstring(resp.content)
        except Exception:
            return None
        ns = {"a": "http://www.w3.org/2005/Atom"}
        entries = root.findall("a:entry", ns)
        if not entries:
            return None
        top = entries[0]
        title = (top.findtext("a:title", default="", namespaces=ns) or "").strip().replace("\n", " ")
        summary = (top.findtext("a:summary", default="", namespaces=ns) or "").strip().replace("\n", " ")
        published = (top.findtext("a:published", default="", namespaces=ns) or "").strip()
        link = top.findtext("a:id", default="", namespaces=ns) or ""
        if not title or not summary:
            return None
        return RetrievalResult(
            title=title[:300],
            summary=summary[:800],
            source="arXiv",
            confidence=0.8,
            entity=query,
            topic=topic or TopicType.UNKNOWN,
            url=link,
            raw_content=summary,
            published_date=_normalize_date(published),
        )

    def _try_ddg(self, query: str, topic: Optional[TopicType]) -> Optional[RetrievalResult]:
        try:
            from duckduckgo_search import DDGS
            with DDGS() as ddgs:
                results = list(ddgs.text(query, max_results=3))
            if results:
                top = results[0]
                combined = "\n".join([r.get("body", "") for r in results if r.get("body")])
                # DDG results carry a date field when the page has one.
                pub = top.get("date") or ""
                return RetrievalResult(
                    title=top.get("title", ""),
                    summary=top.get("body", "")[:800],
                    source="DuckDuckGo",
                    confidence=0.75,
                    entity=query,
                    topic=topic or TopicType.UNKNOWN,
                    url=top.get("href"),
                    raw_content=combined,
                    published_date=_normalize_date(pub),
                )
        except Exception:
            pass
        return None

    def _try_media_providers(self, query: str, topic: Optional[TopicType]) -> Optional[RetrievalResult]:
        try:
            from mini_kio.media.providers.youtube_provider import YouTubeProvider
            yt = YouTubeProvider()
            res = yt.search(query)
            if not res or not res.success or not res.candidates:
                return None
            top = res.candidates[0]
            entity = top.title or query
            return RetrievalResult(
                title=entity,
                summary=f"Media result from YouTube: {entity}",
                source="YouTube",
                confidence=0.7,
                entity=entity,
                topic=topic or (TopicType.MUSIC if "song" in query.lower() else TopicType.MOVIES),
                url=top.url,
                raw_content=entity,
            )
        except Exception:
            pass
        return None

