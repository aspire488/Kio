"""Accessibility tree snapshot — extract AX tree from Playwright pages."""

from __future__ import annotations

import logging
from typing import Any

from playwright.async_api import Page

from .events import EventBus
from .types import BrowserEvent, EventType

logger = logging.getLogger("browser_runtime.accessibility")


class AccessibilityController:
    """Snapshots the browser accessibility tree for screen reader / a11y analysis."""

    def __init__(self, event_bus: EventBus) -> None:
        self._events = event_bus

    async def snapshot(self, page: Page, *, interesting_only: bool = True) -> dict[str, Any]:
        try:
            snap = await page.accessibility.snapshot(interesting_only=interesting_only)
            self._events.emit_nowait(
                BrowserEvent(type=EventType.ACCESSIBILITY_SNAPSHOT, payload={"has_tree": snap is not None})
            )
            return {"success": True, "tree": snap}
        except Exception as exc:
            logger.warning("Accessibility snapshot failed: %s", exc)
            return {"success": False, "error": str(exc)}

    async def get_focused(self, page: Page) -> dict[str, Any]:
        try:
            snap = await page.accessibility.snapshot()
            if snap is None:
                return {"success": False, "error": "no accessibility tree"}
            return {"success": True, "focused_node": self._find_focused(snap)}
        except Exception as exc:
            return {"success": False, "error": str(exc)}

    def _find_focused(self, node: dict[str, Any] | None) -> dict[str, Any] | None:
        if node is None:
            return None
        if node.get("focused"):
            return node
        for child in node.get("children", []):
            result = self._find_focused(child)
            if result:
                return result
        return None
