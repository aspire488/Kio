"""File upload handling via set_input_files with validation."""

from __future__ import annotations

import logging
from pathlib import Path

from playwright.async_api import Page

from .events import EventBus
from .exceptions import UploadError, UploadValidationError
from .types import BrowserEvent, EventType, UploadResult

logger = logging.getLogger("browser_runtime.uploads")


class UploadManager:
    """Validates local files then attaches them to a file input element."""

    def __init__(self, event_bus: EventBus, *, max_file_size_bytes: int = 100 * 1024 * 1024) -> None:
        self._events = event_bus
        self._max_file_size_bytes = max_file_size_bytes

    def _validate(self, paths: list[Path]) -> None:
        if not paths:
            raise UploadValidationError("no files provided for upload")
        for path in paths:
            if not path.exists():
                raise UploadValidationError(f"file does not exist: {path}")
            if not path.is_file():
                raise UploadValidationError(f"not a regular file: {path}")
            size = path.stat().st_size
            if size == 0:
                raise UploadValidationError(f"file is empty: {path}")
            if size > self._max_file_size_bytes:
                raise UploadValidationError(
                    f"file exceeds max size {self._max_file_size_bytes} bytes: {path} ({size} bytes)"
                )

    async def upload(self, page: Page, selector: str, file_paths: list[str], *, timeout_ms: int = 15_000) -> UploadResult:
        paths = [Path(p).expanduser().resolve() for p in file_paths]
        await self._events.emit(BrowserEvent(type=EventType.UPLOAD_STARTED, payload={"selector": selector, "files": file_paths}))

        try:
            self._validate(paths)
            locator = page.locator(selector).first
            await locator.wait_for(state="attached", timeout=timeout_ms)
            await locator.set_input_files([str(p) for p in paths], timeout=timeout_ms)

            verified = await self._verify(page, selector, len(paths))
            if not verified:
                raise UploadError(f"upload verification failed for selector '{selector}'")

            result = UploadResult(success=True, selector=selector, files=[str(p) for p in paths])
            await self._events.emit(
                BrowserEvent(type=EventType.UPLOAD_COMPLETED, payload={"selector": selector, "count": len(paths)})
            )
            return result
        except (UploadValidationError, UploadError) as exc:
            result = UploadResult(success=False, selector=selector, files=file_paths, error=str(exc))
            await self._events.emit(BrowserEvent(type=EventType.UPLOAD_FAILED, payload={"selector": selector, "error": str(exc)}))
            raise
        except Exception as exc:  # noqa: BLE001
            result = UploadResult(success=False, selector=selector, files=file_paths, error=str(exc))
            await self._events.emit(BrowserEvent(type=EventType.UPLOAD_FAILED, payload={"selector": selector, "error": str(exc)}))
            raise UploadError(f"upload failed: {exc}") from exc

    @staticmethod
    async def _verify(page: Page, selector: str, expected_count: int) -> bool:
        try:
            file_count = await page.locator(selector).first.evaluate(
                "el => (el.files ? el.files.length : null)"
            )
            if file_count is None:
                # Not a native <input type=file> (e.g. custom widget) -- cannot
                # verify via .files, so trust set_input_files having succeeded.
                return True
            return int(file_count) == expected_count
        except Exception:  # noqa: BLE001
            return True
