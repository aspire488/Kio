"""Google Drive backend — Drive API v3 via the existing Google OAuth credential.

This is the *cloud storage* backend of KIO's storage surface. The local
filesystem/artifact behavior is untouched — Drive is an additional backend, not
a replacement.

Auth: reuses the ONE existing Google OAuth client/credential
(`google_oauth.get_drive_service()`). No second auth path.
"""

from __future__ import annotations

import io
import logging
import mimetypes
import os
from typing import Any

logger = logging.getLogger(__name__)

BACKEND = "google_drive"

_FOLDER_MIME = "application/vnd.google-apps.folder"
_FILE_FIELDS = "id,name,mimeType,size,modifiedTime,createdTime,parents,webViewLink,md5Checksum,owners,trashed"


def _service():
    from mini_kio.core.google_oauth import get_drive_service
    return get_drive_service()


def _file_summary(f: dict[str, Any]) -> dict[str, Any]:
    owners = f.get("owners") or []
    return {
        "id": f.get("id", ""),
        "name": f.get("name", ""),
        "mime_type": f.get("mimeType", ""),
        "size": f.get("size"),
        "modified": f.get("modifiedTime", ""),
        "created": f.get("createdTime", ""),
        "parents": f.get("parents", []),
        "web_view_link": f.get("webViewLink", ""),
        "md5": f.get("md5Checksum", ""),
        "is_folder": f.get("mimeType") == _FOLDER_MIME,
        "owner": (owners[0].get("emailAddress", "") if owners else ""),
        "trashed": bool(f.get("trashed")),
    }


def list_files(folder_id: str = "root", max_results: int = 25,
               query: str = "", include_trashed: bool = False) -> dict[str, Any]:
    """List files/folders in a Drive folder (default: My Drive root)."""
    try:
        service = _service()
        clauses = []
        if folder_id:
            clauses.append(f"'{folder_id}' in parents")
        if not include_trashed:
            clauses.append("trashed = false")
        if query:
            clauses.append(f"({query})")
        result = service.files().list(
            q=" and ".join(clauses) if clauses else None,
            pageSize=int(max_results),
            fields=f"files({_FILE_FIELDS})",
            orderBy="modifiedTime desc",
        ).execute()
        files = [_file_summary(f) for f in result.get("files", [])]
        return {"success": True, "files": files, "count": len(files),
                "folder_id": folder_id, "backend": BACKEND,
                "message": f"{len(files)} items in Google Drive"}
    except Exception as exc:
        logger.warning("[GOOGLE_DRIVE] list_files failed: %s", exc)
        return {"success": False, "message": f"Google Drive list_files failed: {exc}"}


def search_files(query: str, max_results: int = 25) -> dict[str, Any]:
    """Search Drive by name (and, if it looks like Drive query syntax, as-is)."""
    if not query:
        return {"success": False, "message": "search_files: missing query"}
    drive_query = query if "=" in query else f"name contains '{query.replace(chr(39), '')}'"
    return list_files(folder_id="", max_results=max_results, query=drive_query)


def get_metadata(file_id: str) -> dict[str, Any]:
    """Fetch metadata for a single Drive file."""
    if not file_id:
        return {"success": False, "message": "get_metadata: missing file id"}
    try:
        service = _service()
        f = service.files().get(fileId=file_id, fields=_FILE_FIELDS).execute()
        return {"success": True, "file": _file_summary(f), "backend": BACKEND,
                "message": f"Metadata for {f.get('name', file_id)}"}
    except Exception as exc:
        logger.warning("[GOOGLE_DRIVE] get_metadata failed: %s", exc)
        return {"success": False, "message": f"Google Drive get_metadata failed: {exc}"}


def create_folder(name: str, parent_id: str = "root") -> dict[str, Any]:
    """Create a Drive folder."""
    if not name:
        return {"success": False, "message": "create_folder: missing name"}
    try:
        service = _service()
        created = service.files().create(
            body={"name": name, "mimeType": _FOLDER_MIME, "parents": [parent_id]},
            fields=_FILE_FIELDS,
        ).execute()
        return {"success": True, "folder": _file_summary(created), "folder_id": created.get("id", ""),
                "backend": BACKEND, "message": f"Created Drive folder: {name}"}
    except Exception as exc:
        logger.warning("[GOOGLE_DRIVE] create_folder failed: %s", exc)
        return {"success": False, "message": f"Google Drive create_folder failed: {exc}"}


def upload_file(local_path: str, name: str = "", folder_id: str = "root") -> dict[str, Any]:
    """Upload a local file to Drive."""
    if not local_path or not os.path.exists(local_path):
        return {"success": False, "message": f"upload_file: local file not found: {local_path}"}
    try:
        from googleapiclient.http import MediaFileUpload
        service = _service()
        file_name = name or os.path.basename(local_path)
        mime = mimetypes.guess_type(local_path)[0] or "application/octet-stream"
        media = MediaFileUpload(local_path, mimetype=mime, resumable=False)
        created = service.files().create(
            body={"name": file_name, "parents": [folder_id]},
            media_body=media, fields=_FILE_FIELDS,
        ).execute()
        return {"success": True, "file": _file_summary(created), "file_id": created.get("id", ""),
                "backend": BACKEND, "message": f"Uploaded {file_name} to Google Drive"}
    except Exception as exc:
        logger.warning("[GOOGLE_DRIVE] upload_file failed: %s", exc)
        return {"success": False, "message": f"Google Drive upload_file failed: {exc}"}


def download_file(file_id: str, local_path: str) -> dict[str, Any]:
    """Download a Drive file to a local path. Google-native docs are exported."""
    if not file_id or not local_path:
        return {"success": False, "message": "download_file: need file_id and local_path"}
    try:
        from googleapiclient.http import MediaIoBaseDownload
        service = _service()
        meta = service.files().get(fileId=file_id, fields="name,mimeType").execute()
        mime = meta.get("mimeType", "")
        export_map = {
            "application/vnd.google-apps.document": "application/pdf",
            "application/vnd.google-apps.spreadsheet": "text/csv",
            "application/vnd.google-apps.presentation": "application/pdf",
        }
        if mime in export_map:
            request = service.files().export_media(fileId=file_id, mimeType=export_map[mime])
        else:
            request = service.files().get_media(fileId=file_id)
        os.makedirs(os.path.dirname(os.path.abspath(local_path)) or ".", exist_ok=True)
        with io.FileIO(local_path, "wb") as fh:
            downloader = MediaIoBaseDownload(fh, request)
            done = False
            while not done:
                _, done = downloader.next_chunk()
        return {"success": True, "path": local_path, "file_id": file_id,
                "bytes": os.path.getsize(local_path), "backend": BACKEND,
                "message": f"Downloaded {meta.get('name', file_id)} to {local_path}"}
    except Exception as exc:
        logger.warning("[GOOGLE_DRIVE] download_file failed: %s", exc)
        return {"success": False, "message": f"Google Drive download_file failed: {exc}"}


def rename_file(file_id: str, new_name: str) -> dict[str, Any]:
    """Rename a Drive file or folder."""
    if not file_id or not new_name:
        return {"success": False, "message": "rename_file: need file_id and new_name"}
    try:
        service = _service()
        updated = service.files().update(fileId=file_id, body={"name": new_name},
                                         fields=_FILE_FIELDS).execute()
        return {"success": True, "file": _file_summary(updated), "backend": BACKEND,
                "message": f"Renamed to {new_name}"}
    except Exception as exc:
        logger.warning("[GOOGLE_DRIVE] rename_file failed: %s", exc)
        return {"success": False, "message": f"Google Drive rename_file failed: {exc}"}


def move_file(file_id: str, to_folder_id: str, from_folder_id: str = "") -> dict[str, Any]:
    """Move a Drive file into another folder."""
    if not file_id or not to_folder_id:
        return {"success": False, "message": "move_file: need file_id and to_folder_id"}
    try:
        service = _service()
        remove_parents = from_folder_id
        if not remove_parents:
            current = service.files().get(fileId=file_id, fields="parents").execute()
            remove_parents = ",".join(current.get("parents", []))
        updated = service.files().update(
            fileId=file_id,
            addParents=to_folder_id,
            removeParents=remove_parents or None,
            fields=_FILE_FIELDS,
        ).execute()
        return {"success": True, "file": _file_summary(updated), "backend": BACKEND,
                "message": f"Moved {updated.get('name', file_id)}"}
    except Exception as exc:
        logger.warning("[GOOGLE_DRIVE] move_file failed: %s", exc)
        return {"success": False, "message": f"Google Drive move_file failed: {exc}"}


def delete_file(file_id: str, permanent: bool = False) -> dict[str, Any]:
    """Trash (default) or permanently delete a Drive file."""
    if not file_id:
        return {"success": False, "message": "delete_file: missing file id"}
    try:
        service = _service()
        if permanent:
            service.files().delete(fileId=file_id).execute()
            return {"success": True, "deleted": file_id, "permanent": True, "backend": BACKEND,
                    "message": f"Permanently deleted {file_id}"}
        service.files().update(fileId=file_id, body={"trashed": True}).execute()
        return {"success": True, "deleted": file_id, "permanent": False, "backend": BACKEND,
                "message": f"Trashed {file_id}"}
    except Exception as exc:
        logger.warning("[GOOGLE_DRIVE] delete_file failed: %s", exc)
        return {"success": False, "message": f"Google Drive delete_file failed: {exc}"}


GOOGLE_DRIVE_ACTIONS: dict[str, Any] = {
    "list_files": list_files,
    "search_files": search_files,
    "get_metadata": get_metadata,
    "create_folder": create_folder,
    "upload_file": upload_file,
    "download_file": download_file,
    "rename_file": rename_file,
    "move_file": move_file,
    "delete_file": delete_file,
}

__all__ = list(GOOGLE_DRIVE_ACTIONS) + ["BACKEND", "GOOGLE_DRIVE_ACTIONS"]
