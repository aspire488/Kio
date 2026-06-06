import logging
import os
from typing import Optional
import requests

from mini_kio.core import config

logger = logging.getLogger(__name__)

_JINA_READER_BASE_URL = "https://r.jina.ai/"


def read_url(url: str) -> Optional[str]:
    """Reads a URL using Jina Reader and returns clean page text."""
    if not config.JINA_READER_ENABLED or os.environ.get("KIO_TEST_MODE") == "1":
        return None

    if not url or not url.startswith(("http://", "https://")):
        logger.warning(f"Jina Reader: Invalid URL provided: {url}")
        return None

    jina_url = f"{_JINA_READER_BASE_URL}{url}"
    headers = {
        "X-Return-Format": "markdown" # Request markdown for clean text
    }

    try:
        resp = requests.get(
            jina_url,
            headers=headers,
            timeout=config.JINA_READER_TIMEOUT_S,
        )
        resp.raise_for_status() # Raise an exception for HTTP errors
        return resp.text.strip()
    except requests.Timeout:
        logger.warning(f"Jina Reader: Timeout reading URL: {url}")
    except requests.RequestException as exc:
        logger.warning(
            f"Jina Reader: Request failed for '{url}' (status={getattr(exc.response, 'status_code', 'N/A')}): {exc}"
        )
    except Exception as e:
        logger.warning(f"Jina Reader: Unexpected error reading URL '{url}': {e}")
    return None
