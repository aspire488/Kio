"""
companion/external_world.py — External-World Intelligence.

Connects KIO's existing capabilities (web search, browser, GitHub) to
the companion model for context-aware tool selection and result integration.

NOT a new tool system. This is the reasoning layer that decides:
1. When external information is needed
2. Which existing capability to use
3. How to incorporate results into companion reasoning

Existing capabilities consumed:
- DuckDuckGo search (duckduckgo_search)
- HTTP fetch (httpx/requests)
- Browser automation (connector.py)
- Knowledge routing (retrieval_router.py)
"""

from __future__ import annotations

import logging
import re
from dataclasses import dataclass, field
from typing import Any, Dict, List, Optional, Tuple

logger = logging.getLogger(__name__)


# ── External Information Need Detection ────────────────────────────────────

_EXTERNAL_NEED_PATTERNS = {
    "current_info": re.compile(
        r"\b(what(?:'s| is) (?:the )?(?:latest|current|new|recent|now|today)|"
        r"check (?:the |recent )|look up|find out|is (?:there|it) (?:a |any )?(?:new|update|change)|"
        r"has (?:it|this|there) (?:been|changed|updated|happened)|"
        r"what (?:changed|happened|is happening)|"
        r"(?:search|google|look) (?:for|up|into)|"
        r"(?:latest|recent|current|new) (?:version|release|update|news|status))\b",
        re.I,
    ),
    "repository_info": re.compile(
        r"\b(repo(?:sitory)?|github|git|code|commit|branch|merge|pull request|"
        r"issue|pr|diff|changelog|release|version)\b",
        re.I,
    ),
    "tool_evaluation": re.compile(
        r"\b(worth (?:using|it)|should (?:i|we) (?:use|adopt|switch)|"
        r"how does .+ compare|alternative|better (?:than|option)|"
        r"(?:free|open.source|library|package|framework|tool) .+ (?:for|to)|"
        r"recommend|suggest .+ (?:tool|library|package))\b",
        re.I,
    ),
    "fact_check": re.compile(
        r"\b(is (?:that|this) (?:true|correct|accurate|real)|"
        r"(?:verify|confirm|check) .+ (?:fact|claim|statement)|"
        r"(?:actually|really) (?:true|correct|exists|available)|"
        r"what(?:'s| is) (?:the |actually )?(?:status|price|version|number))\b",
        re.I,
    ),
}


@dataclass
class ExternalNeed:
    """Detected need for external information."""
    need_type: str  # "current_info", "repository_info", "tool_evaluation", "fact_check"
    confidence: float = 0.5
    query_hint: str = ""  # suggested search query
    context: str = ""


def detect_external_need(user_text: str) -> Optional[ExternalNeed]:
    """Detect whether the user's message requires external information."""
    low = user_text.lower()

    for need_type, pattern in _EXTERNAL_NEED_PATTERNS.items():
        matches = pattern.findall(low)
        if matches:
            # Extract a search query from the text
            query = _extract_search_query(user_text, need_type)
            return ExternalNeed(
                need_type=need_type,
                confidence=min(0.8, 0.4 + 0.1 * len(matches)),
                query_hint=query,
                context=user_text[:200],
            )

    return None


def _extract_search_query(text: str, need_type: str) -> str:
    """Extract a search query from the user's message."""
    # Remove common prefixes
    query = text.strip()
    for prefix in ["can you ", "could you ", "please ", "help me ", "what is ",
                   "what's ", "tell me about ", "look up ", "search for "]:
        if query.lower().startswith(prefix):
            query = query[len(prefix):]
            break

    # Remove question marks
    query = query.rstrip("?!.").strip()

    # Limit length
    return query[:200]


# ── Tool Selection ─────────────────────────────────────────────────────────

@dataclass
class ToolResult:
    """Result from an external tool."""
    source: str  # "web_search", "web_fetch", "browser", "github"
    content: str
    url: str = ""
    confidence: float = 0.5
    metadata: Dict[str, Any] = field(default_factory=dict)


def select_and_execute_tool(
    need: ExternalNeed,
    session_id: str = "",
) -> Optional[ToolResult]:
    """Select the appropriate tool and execute it.

    Uses KIO's existing capabilities — no new tools added.
    """
    query = need.query_hint
    if not query:
        return None

    # Try web search first (most general)
    if need.need_type in ("current_info", "tool_evaluation", "fact_check"):
        result = _web_search(query)
        if result:
            return result

    # Try repository info
    if need.need_type == "repository_info":
        result = _web_search(query)
        if result:
            return result

    # Fallback: web search for anything
    result = _web_search(query)
    return result


def _web_search(query: str, max_results: int = 3) -> Optional[ToolResult]:
    """Perform a web search using DuckDuckGo (ddgs package).
    
    Tries the new `ddgs` package first, falls back to deprecated `duckduckgo_search`.
    """
    try:
        # Try new ddgs package first
        try:
            from ddgs import DDGS
        except ImportError:
            from duckduckgo_search import DDGS
        
        with DDGS() as ddgs:
            results = list(ddgs.text(query, max_results=max_results))
            if results:
                summaries = []
                for r in results[:max_results]:
                    title = r.get("title", "")
                    body = r.get("body", "")
                    url = r.get("href", "")
                    if title and body:
                        summaries.append(f"{title}: {body[:200]}")

                content = "\n".join(summaries)
                return ToolResult(
                    source="web_search",
                    content=content[:2000],
                    url=results[0].get("href", ""),
                    confidence=0.7,
                    metadata={"query": query, "result_count": len(results)},
                )
    except Exception as exc:
        logger.debug("[EXTERNAL] Web search failed: %s", exc)

    return None


# ── Result Integration ─────────────────────────────────────────────────────

def integrate_external_result(
    result: ToolResult,
    user_text: str,
) -> str:
    """Format an external result for inclusion in the reasoning context.

    Returns a string that can be added to the situation model or projection.
    """
    if not result:
        return ""

    parts = [f"EXTERNAL INFORMATION (source: {result.source}):"]

    # Add the content
    parts.append(result.content[:1500])

    # Add URL if available
    if result.url:
        parts.append(f"Source URL: {result.url}")

    # Add confidence marker
    parts.append(f"[confidence: {result.confidence:.2f}]")

    return "\n".join(parts)


def should_use_external_info(
    user_text: str,
    companion_model=None,
) -> bool:
    """Determine whether external information would materially help the response.

    Returns True if the query benefits from current external information.
    Returns False for purely companion/self-model/relationship queries.
    """
    need = detect_external_need(user_text)
    if need and need.confidence > 0.4:
        return True

    # Also check if the query is purely about the user/model/relationship
    pure_companion = re.compile(
        r"\b(what do you know|know about me|how do i|what am i|"
        r"describe me|my (?:strength|weakness|pattern|style)|"
        r"our (?:relationship|working)|what have you learned|"
        r"your (?:weakness|strength|capability|limitation)|"
        r"how (?:have|are) (?:you|i)(?: changed| evolved| doing)|"
        r"what (?:are you|have you) (?:bad|good|learned|evolved)|"
        r"what kind of project|how should .+ approach)\b",
        re.I,
    )

    if pure_companion.search(user_text):
        return False

    return False
