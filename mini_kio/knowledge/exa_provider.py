import logging
from typing import Optional

import requests

from mini_kio.core import config

logger = logging.getLogger(__name__)

_EXA_API_URL = "https://api.exa.ai/search"


def search(query: str) -> Optional[str]:
    """Search via Exa API. Returns clean answer text or None."""
    import os
    if not config.EXA_ENABLED or os.environ.get("KIO_TEST_MODE") == "1":
        return None

    headers = {
        "x-api-key": config.EXA_API_KEY,
        "Content-Type": "application/json",
    }
    payload = {
        "query": query,
        "type": "neural",
        "numResults": config.EXA_MAX_RESULTS,
        "contents": {"text": True}, # Request full text content
    }
    try:
        resp = requests.post(
            _EXA_API_URL,
            headers=headers,
            json=payload,
            timeout=config.EXA_TIMEOUT_S,
        )
        resp.raise_for_status()
        data = resp.json()
        results = data.get("results", [])
        if not results:
            return None
        
        # Prioritize contents.text
        text = results[0].get("contents", {}).get("text", "")
        if not text:
            # Fallback to direct text field if contents.text is not available
            text = results[0].get("text", "")
            
        if text:
            return text.strip()
    except requests.Timeout:
        logger.warning("exa: timeout for '%s'", query)
    except requests.RequestException as exc:
        logger.warning(
            "exa: request failed for '%s' (status=%s)",
            query, getattr(exc.response, "status_code", "N/A"),
        )
    except (ValueError, KeyError) as exc:
        logger.warning("exa: parse failed for '%s': %s", query, exc)
    return None
