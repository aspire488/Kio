import logging
import time
from collections import OrderedDict
from typing import Optional
from urllib.parse import quote

import requests

logger = logging.getLogger(__name__)

_WIKIPEDIA_API = "https://en.wikipedia.org/w/api.php"
_WIKIPEDIA_REST = "https://en.wikipedia.org/api/rest_v1/page/summary"
_TIMEOUT_S = 4

_HEADERS = {
    "User-Agent": "KIO/1.0 (Desktop Assistant)",
}
_MAX_EXTRACT_LENGTH = 1200
_CACHE_TTL_S = 300
_CACHE_MAX_ENTRIES = 64

_CACHE: "OrderedDict[str, tuple[float, Optional[str]]]" = OrderedDict()


def _cache_get(query: str) -> Optional[Optional[str]]:
    item = _CACHE.get(query)
    if item is None:
        return None

    expires_at, value = item
    if expires_at < time.monotonic():
        _CACHE.pop(query, None)
        return None

    _CACHE.move_to_end(query)
    return value


def _cache_set(query: str, value: Optional[str]) -> None:
    _CACHE[query] = (time.monotonic() + _CACHE_TTL_S, value)
    _CACHE.move_to_end(query)
    while len(_CACHE) > _CACHE_MAX_ENTRIES:
        _CACHE.popitem(last=False)


def _search_topic(query: str) -> Optional[str]:
    params = {
        "action": "opensearch",
        "search": query,
        "limit": 1,
        "format": "json",
    }
    try:
        resp = requests.get(_WIKIPEDIA_API, params=params, headers=_HEADERS, timeout=_TIMEOUT_S)
        resp.raise_for_status()
        data = resp.json()
        if data and len(data) > 1 and data[1]:
            return str(data[1][0])
    except requests.Timeout:
        logger.warning("wikipedia: search timeout for '%s'", query)
    except requests.RequestException as exc:
        logger.warning(
            "wikipedia: search request failed for '%s' (status=%s, type=%s)",
            query, getattr(exc.response, 'status_code', 'N/A'), type(exc).__name__,
        )
    except ValueError:
        logger.warning("wikipedia: search parse failed for '%s'", query)
    return None


def fetch_summary(query: str) -> Optional[str]:
    normalized_query = (query or "").strip()
    if not normalized_query:
        return None

    cached = _cache_get(normalized_query)
    if cached is not None:
        return cached

    page_title = _search_topic(normalized_query)
    if not page_title:
        _cache_set(normalized_query, None)
        return None

    try:
        resp = requests.get(
            f"{_WIKIPEDIA_REST}/{quote(page_title, safe='')}",
            headers=_HEADERS,
            timeout=_TIMEOUT_S,
        )
        if resp.status_code == 404:
            _cache_set(normalized_query, None)
            return None
        resp.raise_for_status()
        data = resp.json()
        extract = data.get("extract")
        if not isinstance(extract, str) or not extract.strip():
            _cache_set(normalized_query, None)
            return None
        extract = extract.strip()
        if len(extract) > _MAX_EXTRACT_LENGTH:
            extract = extract[:_MAX_EXTRACT_LENGTH].rsplit(".", 1)[0].strip()
            if extract and not extract.endswith("."):
                extract += "."
        _cache_set(normalized_query, extract)
        return extract
    except requests.Timeout:
        logger.warning("wikipedia: summary timeout for '%s'", page_title)
    except requests.RequestException as exc:
        logger.warning(
            "wikipedia: summary request failed for '%s' (status=%s, type=%s)",
            page_title, getattr(exc.response, 'status_code', 'N/A'), type(exc).__name__,
        )
    except ValueError:
        logger.warning("wikipedia: summary parse failed for '%s'", page_title)

    _cache_set(normalized_query, None)
    return None
