"""Real Playwright download handling with progress, events, cancellation."""

from __future__ import annotations

import asyncio
import logging
import time
from pathlib import Path

from playwright.async_api import Download, Page

from .events import EventBus
from .exceptions import DownloadError, DownloadTimeoutError
from .types import BrowserEvent, DownloadInfo, EventType

logger = logging.getLogger("browser_runtime.downloads")


class DownloadManager:
    """Tracks in-flight downloads triggered on a Page.

    Usage: call `await manager.expect_download(page, trigger_coro, save_dir)`
    where trigger_coro is an awaitable that performs the click/action which
    starts the download (e.g. `page.click("#export")`).
    """

    def __init__(self, event_bus: EventBus, default_timeout_ms: int = 60_000) -> None:
        self._events = event_bus
        self._default_timeout_ms = default_timeout_ms
        self._downloads: dict[str, DownloadInfo] = {}
        self._cancelled: set[str] = set()

    def get(self, download_id: str) -> DownloadInfo:
        info = self._downloads.get(download_id)
        if info is None:
            raise DownloadError(f"unknown download_id '{download_id}'")
        return info

    def list_downloads(self) -> list[DownloadInfo]:
        return list(self._downloads.values())

    async def expect_download(
        self,
        page: Page,
        trigger,
        save_dir: Path,
        *,
        timeout_ms: int | None = None,
        rename_to: str | None = None,
    ) -> DownloadInfo:
        timeout = (timeout_ms or self._default_timeout_ms) / 1000
        save_dir.mkdir(parents=True, exist_ok=True)

        info = DownloadInfo(state="pending")
        self._downloads[info.download_id] = info

        try:
            async with page.expect_download(timeout=timeout_ms or self._default_timeout_ms) as dl_info:
                await trigger()
            download: Download = await dl_info.value
        except asyncio.TimeoutError as exc:
            info.state = "failed"
            info.error = "timeout waiting for download to start"
            info.finished_at = time.time()
            await self._events.emit(BrowserEvent(type=EventType.DOWNLOAD_FAILED, payload={"download_id": info.download_id}))
            raise DownloadTimeoutError(info.error) from exc
        except Exception as exc:  # noqa: BLE001
            info.state = "failed"
            info.error = str(exc)
            info.finished_at = time.time()
            await self._events.emit(BrowserEvent(type=EventType.DOWNLOAD_FAILED, payload={"download_id": info.download_id}))
            raise DownloadError(f"download trigger failed: {exc}") from exc

        info.state = "in_progress"
        info.url = download.url
        info.suggested_filename = download.suggested_filename
        await self._events.emit(
            BrowserEvent(type=EventType.DOWNLOAD_STARTED, payload={"download_id": info.download_id, "url": info.url})
        )

        if info.download_id in self._cancelled:
            await download.cancel()
            info.state = "cancelled"
            info.finished_at = time.time()
            await self._events.emit(BrowserEvent(type=EventType.DOWNLOAD_CANCELLED, payload={"download_id": info.download_id}))
            return info

        filename = rename_to or download.suggested_filename or f"download_{info.download_id}"
        target_path = save_dir / filename

        try:
            await asyncio.wait_for(download.save_as(str(target_path)), timeout=timeout)
        except asyncio.TimeoutError as exc:
            info.state = "failed"
            info.error = "timeout saving download"
            info.finished_at = time.time()
            await self._events.emit(BrowserEvent(type=EventType.DOWNLOAD_FAILED, payload={"download_id": info.download_id}))
            raise DownloadTimeoutError(info.error) from exc
        except Exception as exc:  # noqa: BLE001
            failure = await download.failure()
            info.state = "failed"
            info.error = failure or str(exc)
            info.finished_at = time.time()
            await self._events.emit(BrowserEvent(type=EventType.DOWNLOAD_FAILED, payload={"download_id": info.download_id}))
            raise DownloadError(f"download failed: {info.error}") from exc

        try:
            info.bytes_received = target_path.stat().st_size
            info.total_bytes = info.bytes_received
        except OSError:
            pass

        info.save_path = target_path
        info.state = "completed"
        info.finished_at = time.time()
        await self._events.emit(
            BrowserEvent(
                type=EventType.DOWNLOAD_COMPLETED,
                payload={"download_id": info.download_id, "path": str(target_path), "bytes": info.bytes_received},
            )
        )
        return info

    def cancel(self, download_id: str) -> None:
        """Marks a download for cancellation. Only effective if called
        before the Playwright download object resolves inside
        expect_download; for downloads already in flight, this is a no-op
        signal recorded on the info object for observability."""
        self._cancelled.add(download_id)
        info = self._downloads.get(download_id)
        if info is not None and info.state in ("pending", "in_progress"):
            info.state = "cancelled"
