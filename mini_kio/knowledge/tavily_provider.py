import logging
from typing import Optional

import requests

from mini_kio.core import config

logger = logging.getLogger(__name__)

_TAVILY_API_URL = "https://api.tavily.com/search"


def search(query: str) -> Optional[str]:
    """Search via Tavily API. Returns clean answer text or None."""
    import os
    if not config.TAVILY_ENABLED or os.environ.get("KIO_TEST_MODE") == "1":
        return None

    headers = {"Content-Type": "application/json"}
    payload = {
        "api_key": config.TAVILY_API_KEY,
        "query": query,
        "search_depth": "basic",
        "include_answer": True,
        "max_results": config.TAVILY_MAX_RESULTS,
    }
    try:
        resp = requests.post(
            _TAVILY_API_URL,
            headers=headers,
            json=payload,
            timeout=config.TAVILY_TIMEOUT_S,
        )
        resp.raise_for_status()
        data = resp.json()
        answer = data.get("answer", "")
        if answer:
            return answer.strip()
        results = data.get("results", [])
        if results:
            snippets = [r.get("content", "") for r in results if r.get("content")]
            if snippets:
                return " ".join(snippets).strip()
    except requests.Timeout:
        logger.warning("tavily: timeout for '%s'", query)
    except requests.RequestException as exc:
        logger.warning(
            "tavily: request failed for '%s' (status=%s)",
            query, getattr(exc.response, "status_code", "N/A"),
        )
    except (ValueError, KeyError) as exc:
        logger.warning("tavily: parse failed for '%s': %s", query, exc)
    return None
