"""Download handling placeholder for BrowserFacade.
"""

from __future__ import annotations

def list_downloads() -> list[dict]:
    return []

def cancel_download(download_id: str) -> bool:
    return False

__all__ = ["list_downloads", "cancel_download"]
