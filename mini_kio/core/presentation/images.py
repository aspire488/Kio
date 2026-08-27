"""
images.py — Image acquisition for presentation decks
=====================================================

Images are DESIGN ELEMENTS, not decorations: every image is selected by a
semantic query, filtered for resolution/aspect/consistency, downloaded once
into a deck-local cache, and carries attribution metadata (title, artist,
license, page URL) that lands in the speaker notes and a Credits slide.

Source: Wikimedia Commons (free, open, license-metadata-rich, no API key).
Any failure degrades gracefully to no image — a deck never depends on the
network.
"""

from __future__ import annotations

import hashlib
import logging
import re
import time
from pathlib import Path
from typing import Optional

import requests

logger = logging.getLogger("mini_kio.core.presentation.images")

_API = "https://commons.wikimedia.org/w/api.php"
_HEADERS = {"User-Agent": "KIO/1.0 (Desktop Assistant; contact: kio@local)"}
_TIMEOUT = 8
_MIN_W = 800
_MIN_H = 520

# Words that make a result unlikely to be a usable photograph (avoid logos,
# maps, diagrams, svg placeholders).
_BAD_TITLE = re.compile(
    r"\.svg|\.pdf|\.tif|logo|icon|diagram|map_of|coat of arms|flag of|"
    r"locator|orthographic|blank|placeholder|commons",
    re.IGNORECASE,
)


def _cache_dir() -> Path:
    base = Path.home() / ".kio" / "deck_images"
    base.mkdir(parents=True, exist_ok=True)
    return base


def _ext(thumburl: str, ctype: str) -> str:
    if ctype:
        m = re.search(r"image/(\w+)", ctype)
        if m:
            return {"jpeg": ".jpg", "png": ".png", "gif": ".gif", "webp": ".webp"}.get(
                m.group(1).lower(), ".img")
    m = re.search(r"\.(jpg|jpeg|png|gif|webp)(?:[?#]|$)", thumburl, re.IGNORECASE)
    return ("." + m.group(1).lower()) if m else ".img"


def _clean_url(url: str) -> str:
    # thumburls come back with a utm_source query suffix — strip it
    return re.sub(r"\?utm_source=.*$", "", url or "")


def search_images(query: str, limit: int = 8, aspect: str = "any") -> list[dict]:
    """Search Commons; return candidate image dicts (metadata only)."""
    q = (query or "").strip()
    if not q:
        return []
    params = {
        "action": "query", "format": "json", "generator": "search",
        "gsrsearch": f"{q} filetype:bitmap", "gsrnamespace": 6, "gsrlimit": limit,
        "prop": "imageinfo", "iiprop": "url|size|extmetadata",
        "iiurlwidth": 1400,
    }
    try:
        r = requests.get(_API, params=params, headers=_HEADERS, timeout=_TIMEOUT)
        r.raise_for_status()
        data = r.json()
    except Exception as exc:  # noqa: BLE001
        logger.debug("image search failed for %r: %s", query, exc)
        return []
    pages = (data.get("query") or {}).get("pages") or {}
    out = []
    for _pid, pg in pages.items():
        title = str(pg.get("title") or "")
        ii = (pg.get("imageinfo") or [{}])[0]
        if not ii:
            continue
        w = ii.get("width") or 0
        h = ii.get("height") or 0
        thumb = ii.get("thumburl") or ii.get("url") or ""
        if not thumb:
            continue
        if w < _MIN_W or h < _MIN_H:
            continue
        if _BAD_TITLE.search(title):
            continue
        ext_meta = ii.get("extmetadata") or {}
        artist_html = (ext_meta.get("Artist") or {}).get("value", "") or ""
        artist = re.sub(r"<[^>]+>", "", artist_html)
        artist = re.sub(r"\s+", " ", artist).strip()[:80]
        out.append({
            "title": title.replace("File:", ""),
            "url": _clean_url(thumb),
            "page": f"https://commons.wikimedia.org/wiki/{title.replace(' ', '_')}",
            "width": int(w), "height": int(h),
            "license": (ext_meta.get("LicenseShortName") or {}).get("value", ""),
            "artist": artist,
            "query": q,
        })
    return out


def _aspect_score(cand: dict, aspect: str) -> float:
    w, h = cand["width"], cand["height"]
    ratio = w / h if h else 1.0
    if aspect == "landscape":
        return 1.0 if 1.25 <= ratio <= 2.4 else 0.3
    if aspect == "portrait":
        return 1.0 if 0.5 <= ratio <= 0.95 else 0.3
    if aspect == "square":
        return 1.0 if 0.85 <= ratio <= 1.2 else 0.4
    return 0.8


def fetch_image(query: str, *, aspect: str = "any", min_width: int = _MIN_W,
                cache: Optional[Path] = None) -> Optional[dict]:
    """Search + download the best image for a query; returns asset dict or None."""
    cache = cache or _cache_dir()
    try:
        cache.mkdir(parents=True, exist_ok=True)
    except Exception:  # noqa: BLE001
        pass
    candidates = search_images(query, limit=8, aspect=aspect)
    if not candidates:
        return None
    candidates.sort(key=lambda c: (_aspect_score(c, aspect), c["width"] * c["height"]),
                    reverse=True)
    for cand in candidates:
        url = cand["url"]
        if not url:
            continue
        digest = hashlib.sha1((query + "|" + url).encode("utf-8")).hexdigest()[:12]
        ext = _ext(url, "image/jpeg")
        target = cache / f"{digest}{ext}"
        if not target.exists():
            try:
                resp = requests.get(url, headers=_HEADERS, timeout=_TIMEOUT)
                if resp.status_code != 200 or not resp.content:
                    continue
                target.write_bytes(resp.content)
            except Exception as exc:  # noqa: BLE001
                logger.debug("image download failed for %r: %s", query, exc)
                continue
        try:
            size = target.stat().st_size
        except Exception:  # noqa: BLE001
            continue
        if size < 15000:
            continue
        cand["path"] = str(target)
        cand["size_bytes"] = size
        return cand
    return None
