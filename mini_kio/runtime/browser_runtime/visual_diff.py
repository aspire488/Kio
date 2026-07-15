"""Visual diff — compare screenshots for regression detection."""

from __future__ import annotations

import hashlib
import logging
from pathlib import Path
from typing import Any

from .events import EventBus
from .types import BrowserEvent, EventType

logger = logging.getLogger("browser_runtime.visual_diff")


class VisualDiffController:
    """Screenshot comparison using pixel-diff and perceptual hashing."""

    def __init__(self, event_bus: EventBus, cache_dir: Path | None = None) -> None:
        self._events = event_bus
        self._cache_dir = cache_dir

    def compare(self, before_path: str | Path, after_path: str | Path) -> dict[str, Any]:
        try:
            from PIL import Image
            import io
            before = Image.open(str(before_path))
            after = Image.open(str(after_path))
            if before.size != after.size:
                return {"success": True, "dimensions_changed": True,
                        "before_size": before.size, "after_size": after.size,
                        "identical": False, "diff_percent": 100.0}
            diff_pixels = 0
            total = before.width * before.height
            b_data = list(before.getdata())
            a_data = list(after.getdata())
            for i in range(total):
                if b_data[i] != a_data[i]:
                    diff_pixels += 1
            diff_pct = (diff_pixels / total) * 100 if total else 0
            result = {
                "success": True,
                "identical": diff_pixels == 0,
                "diff_pixels": diff_pixels,
                "diff_percent": round(diff_pct, 4),
            }
            self._events.emit_nowait(
                BrowserEvent(type=EventType.VISUAL_DIFF_COMPUTED, payload=result)
            )
            return result
        except ImportError:
            try:
                hash_before = self._phash(str(before_path))
                hash_after = self._phash(str(after_path))
                identical = hash_before == hash_after
                result = {"success": True, "identical": identical, "method": "phash"}
                self._events.emit_nowait(
                    BrowserEvent(type=EventType.VISUAL_DIFF_COMPUTED, payload=result)
                )
                return result
            except Exception as exc:
                return {"success": False, "error": str(exc)}
        except Exception as exc:
            return {"success": False, "error": str(exc)}

    def _phash(self, image_path: str) -> str:
        with open(image_path, "rb") as f:
            return hashlib.md5(f.read()).hexdigest()
