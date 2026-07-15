"""Printing and PDF generation via Playwright."""

from __future__ import annotations

import logging
from pathlib import Path
from typing import Any

from playwright.async_api import Page

from .events import EventBus
from .types import BrowserEvent, EventType

logger = logging.getLogger("browser_runtime.printing")


class PrintManager:
    """PDF generation and print simulation from browser pages."""

    def __init__(self, event_bus: EventBus) -> None:
        self._events = event_bus

    async def pdf(self, page: Page, save_path: str | Path, **options: Any) -> dict[str, Any]:
        try:
            self._events.emit_nowait(BrowserEvent(type=EventType.PRINT_STARTED, payload={}))
            save_path = Path(save_path)
            save_path.parent.mkdir(parents=True, exist_ok=True)
            pdf_kwargs = {
                "path": str(save_path),
                "format": options.get("format", "A4"),
                "print_background": options.get("print_background", True),
                "margin": options.get("margin", {"top": "0.5in", "bottom": "0.5in", "left": "0.5in", "right": "0.5in"}),
            }
            if "scale" in options:
                pdf_kwargs["scale"] = options["scale"]
            if "landscape" in options:
                pdf_kwargs["landscape"] = options["landscape"]
            await page.pdf(**pdf_kwargs)
            size_bytes = save_path.stat().st_size if save_path.exists() else 0
            self._events.emit_nowait(
                BrowserEvent(type=EventType.PDF_GENERATED, payload={"path": str(save_path), "size_bytes": size_bytes})
            )
            self._events.emit_nowait(BrowserEvent(type=EventType.PRINT_COMPLETED, payload={"path": str(save_path)}))
            return {"success": True, "path": str(save_path), "size_bytes": size_bytes}
        except Exception as exc:
            self._events.emit_nowait(
                BrowserEvent(type=EventType.PRINT_FAILED, payload={"error": str(exc)})
            )
            return {"success": False, "error": str(exc)}
