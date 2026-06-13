"""
mini_kio/intelligence/retrieval_synthesizer.py

Retrieval Intelligence Layer (Layer 2)
========================================
Answers factual queries using KIO's existing retrieval stack when all cloud
LLM providers fail. No LLM required for synthesis — uses deterministic
extraction to produce a useful answer from retrieval results.

Provider chain (mirrors existing KIO retrieval stack):
  Exa → Tavily → DuckDuckGo → Jina Reader → Wikipedia

Each provider is attempted once. First non-empty result wins.
Results are deterministically summarized (no LLM, no embeddings).

Architecture constraints:
  - No vector databases
  - No embedding stores
  - No local models
  - No Ollama / GGUF
  - Bounded RAM — providers are called one at a time, results discarded after synthesis
  - Timeout enforced per provider

Synthesis strategy:
  1. Extract the first N sentences from the top result
  2. Strip HTML/markdown noise
  3. Trim to response length limit
  4. Prepend source attribution
"""

from __future__ import annotations

import html
import logging
import re
import time
from typing import Optional

logger = logging.getLogger(__name__)

_MAX_RESPONSE_CHARS = 500
_MAX_SENTENCES = 3


class RetrievalSynthesizer:
    """
    Attempts each retrieval provider in order.
    Returns a deterministically synthesized answer from the first success.
    """

    def __init__(self, timeout_s: float = 6.0) -> None:
        self._timeout_s = timeout_s
        self._stats: dict[str, int] = {
            "exa_hit": 0, "exa_fail": 0,
            "tavily_hit": 0, "tavily_fail": 0,
            "ddg_hit": 0, "ddg_fail": 0,
            "jina_hit": 0, "jina_fail": 0,
            "wikipedia_hit": 0, "wikipedia_fail": 0,
            "total_synthesized": 0,
            "all_failed": 0,
        }

    def synthesize(self, query: str) -> Optional[str]:
        """
        Attempt all retrieval providers in order.
        Returns synthesized text or None if all fail.
        """
        if not query or not query.strip():
            return None

        q = query.strip()

        # ── Provider 1: Exa ────────────────────────────────────────────────
        result = None
        try:
            result = self._try_exa(q)
        except Exception as exc:
            logger.debug(f"[RS] Exa provider call failed within synthesize: {exc}")
        if result:
            self._stats["exa_hit"] += 1
            self._stats["total_synthesized"] += 1
            return result
        self._stats["exa_fail"] += 1

        # ── Provider 2: Tavily ─────────────────────────────────────────────
        result = None
        try:
            result = self._try_tavily(q)
        except Exception as exc:
            logger.debug(f"[RS] Tavily provider call failed within synthesize: {exc}")
        if result:
            self._stats["tavily_hit"] += 1
            self._stats["total_synthesized"] += 1
            return result
        self._stats["tavily_fail"] += 1

        # ── Provider 3: DuckDuckGo ─────────────────────────────────────────
        result = None
        try:
            result = self._try_duckduckgo(q)
        except Exception as exc:
            logger.debug(f"[RS] DuckDuckGo provider call failed within synthesize: {exc}")
        if result:
            self._stats["ddg_hit"] += 1
            self._stats["total_synthesized"] += 1
            return result
        self._stats["ddg_fail"] += 1

        # ── Provider 4: Jina Reader ────────────────────────────────────────
        result = None
        try:
            result = self._try_jina(q)
        except Exception as exc:
            logger.debug(f"[RS] Jina provider call failed within synthesize: {exc}")
        if result:
            self._stats["jina_hit"] += 1
            self._stats["total_synthesized"] += 1
            return result
        self._stats["jina_fail"] += 1

        # ── Provider 5: Wikipedia ──────────────────────────────────────────
        result = None
        try:
            result = self._try_wikipedia(q)
        except Exception as exc:
            logger.debug(f"[RS] Wikipedia provider call failed within synthesize: {exc}")
        if result:
            self._stats["wikipedia_hit"] += 1
            self._stats["total_synthesized"] += 1
            return result
        self._stats["wikipedia_fail"] += 1

        self._stats["all_failed"] += 1
        logger.warning(f"[RS] All retrieval providers failed for: {q[:60]}")
        return None

    # ── Provider implementations ───────────────────────────────────────────

    def _try_exa(self, query: str) -> Optional[str]:
        try:
            from exa_py import Exa  # type: ignore
            import os
            api_key = os.getenv("EXA_API_KEY", "")
            if not api_key:
                return None
            client = Exa(api_key=api_key)
            results = client.search_and_contents(
                query,
                num_results=1,
                text={"max_characters": 600},
                type="neural",
            )
            if results and results.results:
                top = results.results[0]
                text = getattr(top, "text", "") or ""
                title = getattr(top, "title", "") or ""
                url = getattr(top, "url", "") or ""
                return _synthesize(text, source=title or url)
        except Exception as exc:
            logger.debug(f"[RS] Exa failed: {exc}")
        return None

    def _try_tavily(self, query: str) -> Optional[str]:
        try:
            from tavily import TavilyClient  # type: ignore
            import os
            api_key = os.getenv("TAVILY_API_KEY", "")
            if not api_key:
                return None
            client = TavilyClient(api_key=api_key)
            response = client.search(query, max_results=1, search_depth="basic")
            results = response.get("results", [])
            if results:
                top = results[0]
                content = top.get("content", "") or top.get("snippet", "")
                title = top.get("title", "")
                return _synthesize(content, source=title)
        except Exception as exc:
            logger.debug(f"[RS] Tavily failed: {exc}")
        return None

    def _try_duckduckgo(self, query: str) -> Optional[str]:
        try:
            from duckduckgo_search import DDGS  # type: ignore
            with DDGS() as ddgs:
                results = list(ddgs.text(query, max_results=1))
            if results:
                top = results[0]
                body = top.get("body", "") or top.get("snippet", "")
                title = top.get("title", "")
                return _synthesize(body, source=title)
        except Exception as exc:
            logger.debug(f"[RS] DuckDuckGo failed: {exc}")
        return None

    def _try_jina(self, query: str) -> Optional[str]:
        """Jina Reader: fetch a URL's clean text. Requires a URL-form query or fallback."""
        try:
            import urllib.request
            import os
            # Jina r.jina.ai/{url} — only useful if query is a URL or we derive one
            # For plain text queries, skip unless JINA_API_KEY is set for search endpoint
            api_key = os.getenv("JINA_API_KEY", "")
            if not api_key:
                return None
            # Use Jina search API
            import json
            encoded_q = urllib.parse.quote_plus(query)  # type: ignore
            req = urllib.request.Request(
                f"https://s.jina.ai/{encoded_q}",
                headers={
                    "Authorization": f"Bearer {api_key}",
                    "Accept": "application/json",
                },
            )
            with urllib.request.urlopen(req, timeout=self._timeout_s) as resp:
                data = json.loads(resp.read().decode())
            results = data.get("data", [])
            if results:
                top = results[0]
                content = top.get("content", "") or top.get("description", "")
                title = top.get("title", "")
                return _synthesize(content, source=title)
        except Exception as exc:
            logger.debug(f"[RS] Jina failed: {exc}")
        return None

    def _try_wikipedia(self, query: str) -> Optional[str]:
        """
        Wikipedia REST API — no API key required.
        Searches for the query and returns the extract from the top article.
        Pure stdlib urllib — zero new dependencies.
        """
        try:
            import json
            import urllib.request
            import urllib.parse

            # Step 1: search for the article title
            search_url = (
                "https://en.wikipedia.org/w/api.php?"
                "action=query&list=search&format=json&srsearch="
                + urllib.parse.quote_plus(query)
                + "&srlimit=1"
            )
            with urllib.request.urlopen(search_url, timeout=self._timeout_s) as resp:
                search_data = json.loads(resp.read().decode())

            search_results = search_data.get("query", {}).get("search", [])
            if not search_results:
                return None

            title = search_results[0].get("title", "")
            if not title:
                return None

            # Step 2: fetch extract for that title
            extract_url = (
                "https://en.wikipedia.org/w/api.php?"
                "action=query&prop=extracts&exintro=1&explaintext=1"
                "&format=json&redirects=1&titles="
                + urllib.parse.quote_plus(title)
            )
            with urllib.request.urlopen(extract_url, timeout=self._timeout_s) as resp:
                extract_data = json.loads(resp.read().decode())

            pages = extract_data.get("query", {}).get("pages", {})
            for page in pages.values():
                extract = page.get("extract", "")
                if extract:
                    return _synthesize(extract, source=f"Wikipedia: {title}")

        except Exception as exc:
            logger.debug(f"[RS] Wikipedia failed: {exc}")
        return None

    def get_stats(self) -> dict[str, int]:
        return dict(self._stats)


# ---------------------------------------------------------------------------
# Deterministic synthesis — no LLM, no embeddings
# ---------------------------------------------------------------------------

def _synthesize(raw_text: str, source: str = "") -> Optional[str]:
    """
    Extract the first N meaningful sentences from raw text.
    Strip HTML, normalize whitespace. Prepend source if available.
    Returns None if nothing meaningful remains.
    """
    if not raw_text:
        return None

    try:
        # Strip HTML entities and tags
        text = html.unescape(raw_text)
        text = re.sub(r"<[^>]+>", " ", text)

        # Strip markdown formatting
        text = re.sub(r"\*{1,3}([^*]+)\*{1,3}", r"\1", text)
        text = re.sub(r"_{1,3}([^_]+)_{1,3}", r"\1", text) # Added for underscore markdown
        text = re.sub(r"#{1,6}\s+", "", text)
        text = re.sub(r"\[([^\]]+)\]\([^)]+\)", r"\1", text)  # [text](url) -> text
        text = re.sub(r"`{1,3}[^`]*`{1,3}", "", text)

        # Normalize whitespace
        text = re.sub(r"\s+", " ", text).strip()

        if not text:
            return None

        # Extract first N sentences
        sentences = _split_sentences(text)
        sentences = [s.strip() for s in sentences if s.strip()] # Removed length filter
        if not sentences:
            return None

        excerpt = " ".join(sentences[:_MAX_SENTENCES])
        excerpt = excerpt[:_MAX_RESPONSE_CHARS]

        if source:
            source_clean = source[:80].strip()
            return f"{excerpt}\n\nSource: {source_clean}" # Changed format
        return excerpt
    except Exception as exc:
        logger.debug(f"[RS] Error during synthesis: {exc}")
        return None


def _split_sentences(text: str) -> list[str]:
    """Simple sentence splitter — no NLTK dependency."""
    # Split on '. ', '! ', '? ' with at least 1 char before the punctuation
    parts = re.split(r"(?<=[.!?])\s+(?=[A-Z])", text)
    return [p for p in parts if p.strip()]


# ---------------------------------------------------------------------------
# urllib.parse import fix (used in Jina provider above)
# ---------------------------------------------------------------------------
import urllib.parse  # noqa: E402 — ensures it's available for the Jina method
