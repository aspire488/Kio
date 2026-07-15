"""File picker automation — handle native file dialogs via Playwright file chooser."""

from __future__ import annotations

import asyncio
import logging
from pathlib import Path

from playwright.async_api import Page, FileChooser

from .types import UploadResult

logger = logging.getLogger("browser_runtime.file_picker")


class FilePickerHandler:
    """Automates native file picker dialogs.

    Playwright automatically handles <input type=file> elements.
    This handler deals with file chooser events triggered by clicks/drag-drop
    on custom elements that open the OS file picker.
    """

    def __init__(self, default_timeout_ms: int = 15_000) -> None:
        self._default_timeout_ms = default_timeout_ms
        self._expecting: dict[str, asyncio.Future] = {}

    async def expect_and_choose(self, page: Page, file_paths: list[str],
                                *, timeout_ms: int | None = None) -> UploadResult:
        """Set up a file chooser handler, trigger it, then select files.

        Usage:
            result = await handler.expect_and_choose(page, ["/path/to/file.pdf"])
        This does NOT click the trigger — the caller must perform the click
        before or after calling this (the file chooser event fires asynchronously).
        """
        timeout = timeout_ms or self._default_timeout_ms
        paths = [str(Path(p).resolve()) for p in file_paths]
        try:
            async with page.expect_file_chooser(timeout=timeout) as fc_info:
                pass
            chooser: FileChooser = await fc_info.value
            await chooser.set_files(paths)
            return UploadResult(success=True, selector="file_picker", files=paths)
        except asyncio.TimeoutError:
            return UploadResult(success=False, selector="file_picker", files=file_paths,
                                error="File chooser did not appear within timeout")
        except Exception as exc:
            return UploadResult(success=False, selector="file_picker", files=file_paths,
                                error=str(exc))

    async def set_input_files_direct(self, page: Page, selector: str, file_paths: list[str]) -> UploadResult:
        """Direct file input for <input type=file> elements (no dialog)."""
        paths = [str(Path(p).resolve()) for p in file_paths]
        try:
            locator = page.locator(selector).first
            await locator.wait_for(state="attached", timeout=self._default_timeout_ms)
            await locator.set_input_files(paths)
            return UploadResult(success=True, selector=selector, files=paths)
        except Exception as exc:
            return UploadResult(success=False, selector=selector, files=file_paths, error=str(exc))


class ClipboardIntegration:
    """Read/write browser clipboard via Playwright."""

    async def read_text(self, page: Page) -> str:
        return await page.evaluate("navigator.clipboard.readText()")

    async def write_text(self, page: Page, text: str) -> bool:
        try:
            await page.evaluate(f"navigator.clipboard.writeText({json.dumps(text)})")
            return True
        except Exception as exc:
            logger.warning("Clipboard write failed: %s", exc)
            return False

    async def read(self, page: Page) -> dict[str, Any]:
        try:
            text = await page.evaluate("""
                async () => {
                    try {
                        const items = await navigator.clipboard.read();
                        const results = [];
                        for (const item of items) {
                            for (const type of item.types) {
                                const blob = await item.getType(type);
                                const text = await blob.text();
                                results.push({type, text: text.slice(0, 10000)});
                            }
                        }
                        return {success: true, items: results};
                    } catch(e) {
                        return {success: false, error: e.message};
                    }
                }
            """)
            return text
        except Exception as exc:
            return {"success": False, "error": str(exc)}


import json
