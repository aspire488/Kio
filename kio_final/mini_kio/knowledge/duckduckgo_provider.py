import logging
import os
import asyncio
from typing import Optional

# Ensure duckduckgo-search is available, if not, provide a graceful fallback
try:
    from duckduckgo_search import DDGS
except ImportError:
    DDGS = None
    logging.warning("DuckDuckGo Search library not found. DuckDuckGo provider will be unavailable.")

from mini_kio.core import config

logger = logging.getLogger(__name__)


def search(query: str) -> Optional[str]:
    """Search via DuckDuckGo Search. Returns combined text from results or None."""
    if DDGS is None or os.environ.get("KIO_TEST_MODE") == "1":
        logger.error("DuckDuckGo Search library is not installed or in test mode.")
        return None

    if not query.strip():
        return None

    try:
        # Using a context manager for DDGS as recommended
        with DDGS() as ddgs:
            # max_results can be configured, using a default for now.
            # config.EXA_MAX_RESULTS is a good proxy.
            results = ddgs.text(query, max_results=config.EXA_MAX_RESULTS)

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
