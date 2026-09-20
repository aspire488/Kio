"""Google Photos — Library API (post-April-2025 surface) + Photos Picker API.

IMPORTANT API LIMITATION (verified against Google's own docs, not assumed):
On 2025-03-31 Google removed `photoslibrary`, `photoslibrary.readonly` and
`photoslibrary.sharing`. After that date:

  * Listing/searching/retrieving albums and media items works ONLY for content
    created by this application (`photoslibrary.readonly.appcreateddata`).
  * Shared-album methods (share/unshare/get/join/leave/list) return
    403 PERMISSION_DENIED — they are not available at all.
  * Reading a user's own library is only possible through the Photos Picker
    API (`photospicker.mediaitems.readonly`), where the USER selects the items
    and only the selected items are returned.

So "search the whole library" is NOT implementable today. This module does not
fake it: `search_media` is scoped to app-created content and the picker actions
implement the only supported whole-library path.

Same OAuth client/account as every other Google service here.
"""

from __future__ import annotations

import logging
import mimetypes
from typing import Any

logger = logging.getLogger(__name__)

BACKEND = "google_photos"


def _service():
    from mini_kio.core.google_oauth import get_photos_service
    return get_photos_service()


def _picker_service():
    """Picker API is a separate discovery document from the Library API."""
    from googleapiclient.discovery import build
    from mini_kio.core.google_oauth import _get_credentials
    creds = _get_credentials()
    if creds is None:
        raise RuntimeError("Google OAuth not authorized.")
    return build("photospicker", "v1", credentials=creds, static_discovery=False)


def _album_summary(album: dict[str, Any]) -> dict[str, Any]:
    return {
        "id": album.get("id", ""),
        "title": album.get("title", ""),
        "media_items_count": album.get("mediaItemsCount"),
        "product_url": album.get("productUrl", ""),
        "is_writeable": album.get("isWriteable"),
    }


def _media_summary(item: dict[str, Any]) -> dict[str, Any]:
    meta = item.get("mediaMetadata", {}) or {}
    return {
        "id": item.get("id", ""),
        "filename": item.get("filename", ""),
        "mime_type": item.get("mimeType", ""),
        "description": item.get("description", ""),
        "base_url": item.get("baseUrl", ""),
        "product_url": item.get("productUrl", ""),
        "creation_time": meta.get("creationTime", ""),
        "width": meta.get("width", ""),
        "height": meta.get("height", ""),
    }


def _scope_error(exc: Exception) -> str:
    text = str(exc)
    lowered = text.lower()
    if "insufficient" in lowered or "PERMISSION_DENIED" in text or "403" in text:
        return (
            "Google Photos scope not granted (or the scope was removed by Google on "
            "2025-03-31). Listing/searching a user's whole library is no longer "
            "supported by the Library API — use the picker actions, and run the OAuth "
            "consent once to add the photo scopes (existing client/credential). "
            f"Detail: {text[:200]}"
        )
    return f"Google Photos API failed: {text[:300]}"


def list_albums(page_size: int = 25, page_token: str = "") -> dict[str, Any]:
    """List albums created by this application."""
    try:
        service = _service()
        params: dict[str, Any] = {"pageSize": int(page_size)}
        if page_token:
            params["pageToken"] = page_token
        result = service.albums().list(**params).execute()
        albums = [_album_summary(a) for a in result.get("albums", [])]
        return {"success": True, "albums": albums, "count": len(albums),
                "next_page_token": result.get("nextPageToken", ""),
                "scope": "app_created_only", "backend": BACKEND,
                "message": f"{len(albums)} app-created albums"}
    except Exception as exc:
        logger.warning("[GOOGLE_PHOTOS] list_albums failed: %s", exc)
        return {"success": False, "message": _scope_error(exc)}


def get_album(album_id: str) -> dict[str, Any]:
    """Get one album (app-created)."""
    if not album_id:
        return {"success": False, "message": "get_album: missing album_id"}
    try:
        service = _service()
        album = service.albums().get(albumId=album_id).execute()
        return {"success": True, "album": _album_summary(album), "backend": BACKEND,
                "message": f"Album {album.get('title', album_id)}"}
    except Exception as exc:
        logger.warning("[GOOGLE_PHOTOS] get_album failed: %s", exc)
        return {"success": False, "message": _scope_error(exc)}


def create_album(title: str) -> dict[str, Any]:
    """Create an album (photoslibrary.appendonly)."""
    if not title:
        return {"success": False, "message": "create_album: missing title"}
    try:
        service = _service()
        album = service.albums().create(body={"album": {"title": title}}).execute()
        return {"success": True, "album": _album_summary(album),
                "album_id": album.get("id", ""), "backend": BACKEND,
                "message": f"Created album '{title}'"}
    except Exception as exc:
        logger.warning("[GOOGLE_PHOTOS] create_album failed: %s", exc)
        return {"success": False, "message": _scope_error(exc)}


def list_media(page_size: int = 25, page_token: str = "") -> dict[str, Any]:
    """List media items created by this application."""
    try:
        service = _service()
        params: dict[str, Any] = {"pageSize": int(page_size)}
        if page_token:
            params["pageToken"] = page_token
        result = service.mediaItems().list(**params).execute()
        items = [_media_summary(i) for i in result.get("mediaItems", [])]
        return {"success": True, "media_items": items, "count": len(items),
                "next_page_token": result.get("nextPageToken", ""),
                "scope": "app_created_only", "backend": BACKEND,
                "message": f"{len(items)} app-created media items"}
    except Exception as exc:
        logger.warning("[GOOGLE_PHOTOS] list_media failed: %s", exc)
        return {"success": False, "message": _scope_error(exc)}


def search_media(album_id: str = "", page_size: int = 25,
                 filters: dict[str, Any] | None = None) -> dict[str, Any]:
    """Search media items. Limited to app-created content by the API itself."""
    try:
        service = _service()
        body: dict[str, Any] = {"pageSize": int(page_size)}
        if album_id:
            body["albumId"] = album_id
        if filters:
            body["filters"] = filters
        result = service.mediaItems().search(body=body).execute()
        items = [_media_summary(i) for i in result.get("mediaItems", [])]
        return {"success": True, "media_items": items, "count": len(items),
                "scope": "app_created_only", "backend": BACKEND,
                "message": (f"{len(items)} app-created media items "
                            "(whole-library search is removed by Google)")}
    except Exception as exc:
        logger.warning("[GOOGLE_PHOTOS] search_media failed: %s", exc)
        return {"success": False, "message": _scope_error(exc)}


def get_media(media_item_id: str) -> dict[str, Any]:
    """Get one media item (app-created)."""
    if not media_item_id:
        return {"success": False, "message": "get_media: missing media_item_id"}
    try:
        service = _service()
        item = service.mediaItems().get(mediaItemId=media_item_id).execute()
        return {"success": True, "media_item": _media_summary(item), "backend": BACKEND,
                "message": f"Media item {item.get('filename', media_item_id)}"}
    except Exception as exc:
        logger.warning("[GOOGLE_PHOTOS] get_media failed: %s", exc)
        return {"success": False, "message": _scope_error(exc)}


def upload_media(local_path: str, description: str = "", album_id: str = "") -> dict[str, Any]:
    """Upload a local image/video: raw upload, then mediaItems.batchCreate."""
    import os
    if not local_path or not os.path.exists(local_path):
        return {"success": False, "message": f"upload_media: local file not found: {local_path}"}
    try:
        import requests
        from mini_kio.core.google_oauth import _get_credentials
        creds = _get_credentials()
        if creds is None:
            return {"success": False, "message": "Google OAuth not authorized."}
        from google.auth.transport.requests import Request
        if not creds.valid:
            creds.refresh(Request())
        mime = mimetypes.guess_type(local_path)[0] or "application/octet-stream"
        with open(local_path, "rb") as fh:
            raw = fh.read()
        token_resp = requests.post(
            "https://photoslibrary.googleapis.com/v1/uploads",
            headers={
                "Authorization": f"Bearer {creds.token}",
                "Content-Type": "application/octet-stream",
                "X-Goog-Upload-Content-Type": mime,
                "X-Goog-Upload-Protocol": "raw",
            },
            data=raw, timeout=60,
        )
        if token_resp.status_code != 200:
            return {"success": False,
                    "message": f"Google Photos upload failed ({token_resp.status_code}): "
                               f"{token_resp.text[:200]}"}
        upload_token = token_resp.text
        service = _service()
        new_item: dict[str, Any] = {"simpleMediaItem": {"uploadToken": upload_token}}
        if description or local_path:
            new_item["description"] = description or os.path.basename(local_path)
        body: dict[str, Any] = {"newMediaItems": [new_item]}
        if album_id:
            body["albumId"] = album_id
        result = service.mediaItems().batchCreate(body=body).execute()
        results = result.get("newMediaItemResults", [])
        item = (results[0].get("mediaItem") if results else {}) or {}
        return {"success": True, "media_item": _media_summary(item),
                "media_item_id": item.get("id", ""), "backend": BACKEND,
                "message": f"Uploaded {os.path.basename(local_path)} to Google Photos"}
    except Exception as exc:
        logger.warning("[GOOGLE_PHOTOS] upload_media failed: %s", exc)
        return {"success": False, "message": _scope_error(exc)}


def create_picker_session() -> dict[str, Any]:
    """Create a Photos Picker session — the supported whole-library read path."""
    try:
        service = _picker_service()
        session = service.sessions().create(body={}).execute()
        return {"success": True, "session": session,
                "session_id": session.get("id", ""),
                "picker_uri": session.get("pickerUri", ""), "backend": BACKEND,
                "message": ("Picker session created. The user selects items in the "
                            "picker UI; then call list_picked_items.")}
    except Exception as exc:
        logger.warning("[GOOGLE_PHOTOS] create_picker_session failed: %s", exc)
        return {"success": False, "message": _scope_error(exc)}


def list_picked_items(session_id: str, page_size: int = 50) -> dict[str, Any]:
    """List the media items the user selected in a picker session."""
    if not session_id:
        return {"success": False, "message": "list_picked_items: missing session_id"}
    try:
        service = _picker_service()
        result = service.sessions().mediaItems().list(
            sessionId=session_id, pageSize=int(page_size),
        ).execute()
        items = []
        for entry in result.get("mediaItems", []):
            media = entry.get("mediaFile", {}) or {}
            items.append({
                "id": entry.get("id", ""),
                "type": entry.get("type", ""),
                "filename": media.get("filename", ""),
                "mime_type": media.get("mimeType", ""),
                "base_url": media.get("baseUrl", ""),
                "create_time": entry.get("createTime", ""),
                "pick_time": entry.get("pickTime", ""),
            })
        return {"success": True, "media_items": items, "count": len(items),
                "backend": BACKEND,
                "message": f"{len(items)} items picked by the user"}
    except Exception as exc:
        logger.warning("[GOOGLE_PHOTOS] list_picked_items failed: %s", exc)
        return {"success": False, "message": _scope_error(exc)}


GOOGLE_PHOTOS_ACTIONS: dict[str, Any] = {
    "list_albums": list_albums,
    "get_album": get_album,
    "create_album": create_album,
    "list_media": list_media,
    "search_media": search_media,
    "get_media": get_media,
    "upload_media": upload_media,
    "create_picker_session": create_picker_session,
    "list_picked_items": list_picked_items,
}

# Operations the API no longer supports — recorded so nothing silently pretends
# to implement them (see the module docstring for the source).
UNSUPPORTED_OPERATIONS: dict[str, str] = {
    "search_whole_library": "photoslibrary/photoslibrary.readonly removed 2025-03-31; use the Picker API",
    "list_shared_albums": "sharedAlbums.* return 403 PERMISSION_DENIED since 2025-03-31",
    "share_album": "albums.share removed 2025-03-31",
    "join_shared_album": "sharedAlbums.join removed 2025-03-31",
}

__all__ = list(GOOGLE_PHOTOS_ACTIONS) + ["BACKEND", "GOOGLE_PHOTOS_ACTIONS", "UNSUPPORTED_OPERATIONS"]
