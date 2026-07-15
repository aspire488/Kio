import logging
import os
import asyncio
from typing import Optional

# Ensure duckduckgo-search is available, if not, provide a graceful fallback
try:
    from duckduckgo_search import DDGS as _DDGS_NEW
    DDGS = _DDGS_NEW
except ImportError:
    try:
        from duckduckgo_search import ddgs as _DDGS_OLD
        DDGS = _DDGS_OLD
    except ImportError:
        DDGS = None
        logging.warning("DuckDuckGo Search library not found. DuckDuckGo provider will be unavailable.")

from mini_kio.core import config

logger = logging.getLogger(__name__)


def search(query: str, timelimit: Optional[str] = None) -> Optional[str]:
    """Search via DuckDuckGo Search. Returns combined text from results or None.
    
    Arguments:
        query: The search query string.
        timelimit: Optional DuckDuckGo time filter: "d" (day), "w" (week), 
                   "m" (month), "y" (year). Passed through to ddgs.text().
    """
    if DDGS is None or os.environ.get("KIO_TEST_MODE") == "1":
        logger.error("DuckDuckGo Search library is not installed or in test mode.")
        return None

    if not query.strip():
        return None

    try:
        # Using a context manager for DDGS as recommended
        with DDGS() as ddgs:
            kwargs = dict(max_results=config.EXA_MAX_RESULTS)
            if timelimit:
                kwargs["timelimit"] = timelimit
            results = ddgs.text(query, **kwargs)

        if not results:
            return None

        # Combine the 'body' of multiple results to return meaningful text
        combined_text = "\n".join([r.get("body", "") for r in results if r.get("body")])
        if combined_text:
            return combined_text.strip()
        
    except Exception as e:
        logger.warning(f"DuckDuckGo search failed for '{query}': {e}")
        return None

    return None
