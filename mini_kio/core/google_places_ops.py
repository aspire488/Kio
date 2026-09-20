"""Google Places API (New) — location / place search.

Auth note (this is the reason Places is different from the other Google
services here): Places API (New) is a *public data* API. It is billed and
authorized per-project with an **API key**, not with the OAuth grant that
represents a user's own Google data. Using the OAuth credential would both be
unsupported for these endpoints and would conflate KIO's user-data identity
with a public-data quota.

So Places reads its API key from CredentialVault (provider=google,
credential_type=api_key, metadata["service"]="places") via
`google_oauth.get_places_service()`. That is NOT a second OAuth identity — no
second client, project or account is created.

The key is never logged, returned, or embedded in a result payload.
"""

from __future__ import annotations

import logging
from typing import Any

logger = logging.getLogger(__name__)

BACKEND = "google_places"
_BASE = "https://places.googleapis.com/v1"

_SEARCH_FIELDS = (
    "places.id,places.displayName,places.formattedAddress,places.shortFormattedAddress,"
    "places.location,places.types,places.rating,places.userRatingCount,"
    "places.websiteUri,places.internationalPhoneNumber,places.businessStatus"
)
_DETAILS_FIELDS = (
    "id,displayName,formattedAddress,addressComponents,location,types,rating,"
    "userRatingCount,websiteUri,internationalPhoneNumber,nationalPhoneNumber,"
    "regularOpeningHours,businessStatus,googleMapsUri,editorialSummary"
)


def _api_key() -> str:
    """Read the Places API key from CredentialVault. Raises if not configured."""
    from mini_kio.core.google_oauth import get_places_service
    cred = get_places_service()
    key = (cred or {}).get("api_key", "") if isinstance(cred, dict) else ""
    if not key:
        raise RuntimeError("Google Places API key not configured in CredentialVault")
    return key


def _post(path: str, body: dict[str, Any], field_mask: str, timeout: int = 20) -> dict[str, Any]:
    import requests
    response = requests.post(
        f"{_BASE}/{path}",
        json=body,
        headers={
            "Content-Type": "application/json",
            "X-Goog-Api-Key": _api_key(),
            "X-Goog-FieldMask": field_mask,
        },
        timeout=timeout,
    )
    if response.status_code != 200:
        raise RuntimeError(f"Places API {response.status_code}: {response.text[:300]}")
    return response.json()


def _get(path: str, field_mask: str, timeout: int = 20) -> dict[str, Any]:
    import requests
    response = requests.get(
        f"{_BASE}/{path}",
        headers={"X-Goog-Api-Key": _api_key(), "X-Goog-FieldMask": field_mask},
        timeout=timeout,
    )
    if response.status_code != 200:
        raise RuntimeError(f"Places API {response.status_code}: {response.text[:300]}")
    return response.json()


def _place_summary(place: dict[str, Any]) -> dict[str, Any]:
    display = place.get("displayName") or {}
    location = place.get("location") or {}
    return {
        "place_id": place.get("id", ""),
        "name": display.get("text", "") if isinstance(display, dict) else str(display),
        "address": place.get("formattedAddress", "") or place.get("shortFormattedAddress", ""),
        "latitude": location.get("latitude"),
        "longitude": location.get("longitude"),
        "types": place.get("types", []),
        "rating": place.get("rating"),
        "user_rating_count": place.get("userRatingCount"),
        "website": place.get("websiteUri", ""),
        "phone": place.get("internationalPhoneNumber", "") or place.get("nationalPhoneNumber", ""),
        "business_status": place.get("businessStatus", ""),
        "maps_uri": place.get("googleMapsUri", ""),
    }


def _fail(exc: Exception) -> dict[str, Any]:
    text = str(exc)
    if "not configured" in text:
        return {"success": False,
                "message": ("Google Places API key not configured. Store it in "
                            "CredentialVault (provider=google, type=api_key, "
                            "metadata.service=places). Places uses API-key auth, "
                            "not the OAuth credential.")}
    if "API_KEY_INVALID" in text or "400" in text:
        return {"success": False, "message": f"Google Places API key rejected: {text[:200]}"}
    if "PERMISSION_DENIED" in text or "403" in text:
        return {"success": False,
                "message": ("Places API (New) not enabled for this project or the key is "
                            f"restricted. Enable 'Places API (New)' in the existing Google "
                            f"Cloud project. Detail: {text[:200]}")}
    return {"success": False, "message": f"Google Places API failed: {text[:300]}"}


def text_search(query: str, max_results: int = 5, language: str = "en") -> dict[str, Any]:
    """Places API (New) text search — `places:searchText`."""
    if not query:
        return {"success": False, "message": "text_search: missing query"}
    try:
        data = _post("places:searchText",
                     {"textQuery": query, "maxResultCount": int(max_results),
                      "languageCode": language},
                     _SEARCH_FIELDS)
        places = [_place_summary(p) for p in data.get("places", [])]
        return {"success": True, "places": places, "count": len(places),
                "query": query, "backend": BACKEND,
                "message": f"{len(places)} places for '{query}'"}
    except Exception as exc:
        logger.warning("[GOOGLE_PLACES] text_search failed: %s", exc)
        return _fail(exc)


def place_details(place_id: str, fields: list[str] | None = None) -> dict[str, Any]:
    """Places API (New) place details — `places/{place_id}`."""
    if not place_id:
        return {"success": False, "message": "place_details: missing place_id"}
    mask = ",".join(fields) if fields else _DETAILS_FIELDS
    bare_id = place_id.split("/")[-1]
    try:
        data = _get(f"places/{bare_id}", mask)
        return {"success": True, "place": _place_summary(data), "backend": BACKEND,
                "message": f"Details for {data.get('id', bare_id)}"}
    except Exception as exc:
        logger.warning("[GOOGLE_PLACES] place_details failed: %s", exc)
        return _fail(exc)


def nearby_search(latitude: float | None, longitude: float | None,
                  radius: float = 1000.0, included_types: list[str] | None = None,
                  max_results: int = 5) -> dict[str, Any]:
    """Places API (New) nearby search — `places:searchNearby`."""
    if latitude is None or longitude is None:
        return {"success": False, "message": "nearby_search: need latitude and longitude"}
    if not (0 < float(radius) <= 50000):
        return {"success": False, "message": "nearby_search: radius must be 1..50000 metres"}
    body: dict[str, Any] = {
        "locationRestriction": {
            "circle": {
                "center": {"latitude": float(latitude), "longitude": float(longitude)},
                "radius": float(radius),
            }
        },
        "maxResultCount": int(max_results),
    }
    if included_types:
        body["includedTypes"] = list(included_types)
    try:
        data = _post("places:searchNearby", body, _SEARCH_FIELDS)
        places = [_place_summary(p) for p in data.get("places", [])]
        return {"success": True, "places": places, "count": len(places),
                "center": {"latitude": float(latitude), "longitude": float(longitude)},
                "radius_m": float(radius), "backend": BACKEND,
                "message": f"{len(places)} places nearby"}
    except Exception as exc:
        logger.warning("[GOOGLE_PLACES] nearby_search failed: %s", exc)
        return _fail(exc)


GOOGLE_PLACES_ACTIONS: dict[str, Any] = {
    "text_search": text_search,
    "place_details": place_details,
    "nearby_search": nearby_search,
}

__all__ = list(GOOGLE_PLACES_ACTIONS) + ["BACKEND", "GOOGLE_PLACES_ACTIONS"]
