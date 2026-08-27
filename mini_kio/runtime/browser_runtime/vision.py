"""OCR and vision-based text extraction fallback for browser automation."""

from __future__ import annotations

import logging
import subprocess
import sys
from pathlib import Path
from typing import Any

logger = logging.getLogger("browser_runtime.ocr")


class OCREngine:
    """Extract text from screenshots using Tesseract OCR or fallback.

    Provides text-in-image extraction when the DOM doesn't expose text
    (e.g. canvas-rendered text, images, PDF-in-browser).
    """

    _WIN_FLAGS = 0x08000000 if sys.platform == "win32" else 0  # CREATE_NO_WINDOW

    def __init__(self, tesseract_path: str | None = None) -> None:
        self._tesseract_path = tesseract_path or self._find_tesseract()
        self._available: bool | None = None

    def _find_tesseract(self) -> str | None:
        candidates = ["tesseract", "tesseract.exe"]
        for c in candidates:
            try:
                _kw: dict = dict(capture_output=True, text=True, timeout=5)
                if self._WIN_FLAGS:
                    _kw["creationflags"] = self._WIN_FLAGS
                result = subprocess.run([c, "--version"], **_kw)
                if result.returncode == 0:
                    return c
            except (FileNotFoundError, subprocess.TimeoutExpired):
                continue
        return None

    @property
    def available(self) -> bool:
        if self._available is None:
            self._available = self._tesseract_path is not None
        return self._available

    async def extract_text(self, image_path: Path, *, lang: str = "eng") -> dict[str, Any]:
        """Run OCR on an image file and return extracted text with confidence."""
        if not self.available:
            return {"success": False, "text": "", "error": "Tesseract not installed", "confidence": 0}
        try:
            _kw: dict = dict(capture_output=True, text=True, timeout=30)
            if self._WIN_FLAGS:
                _kw["creationflags"] = self._WIN_FLAGS
            result = subprocess.run(
                [self._tesseract_path, str(image_path), "stdout", "-l", lang, "--psm", "6"],
                **_kw,
            )
            if result.returncode == 0:
                text = result.stdout.strip()
                return {"success": True, "text": text, "confidence": 0.8, "length": len(text)}
            return {"success": False, "text": "", "error": result.stderr[:200], "confidence": 0}
        except Exception as exc:
            return {"success": False, "text": "", "error": str(exc), "confidence": 0}

    async def extract_structured(self, image_path: Path, *, lang: str = "eng") -> dict[str, Any]:
        """OCR with positional data (words + bounding boxes)."""
        if not self.available:
            return {"success": False, "words": [], "error": "Tesseract not installed"}
        try:
            _kw: dict = dict(capture_output=True, text=True, timeout=30)
            if self._WIN_FLAGS:
                _kw["creationflags"] = self._WIN_FLAGS
            result = subprocess.run(
                [self._tesseract_path, str(image_path), "stdout", "-l", lang, "--psm", "6", "tsv"],
                **_kw,
            )
            if result.returncode != 0:
                return {"success": False, "words": [], "error": result.stderr[:200]}
            lines = result.stdout.strip().split("\n")
            if len(lines) < 2:
                return {"success": True, "words": []}
            headers = lines[0].split("\t")
            words = []
            for line in lines[1:]:
                cols = line.split("\t")
                if len(cols) >= 12:
                    conf = cols[10]
                    text = cols[11]
                    if conf and text and int(conf) > 30:
                        words.append({
                            "text": text, "confidence": int(conf),
                            "x": int(cols[6]), "y": int(cols[7]),
                            "w": int(cols[8]), "h": int(cols[9]),
                        })
            return {"success": True, "words": words, "count": len(words)}
        except Exception as exc:
            return {"success": False, "words": [], "error": str(exc)}


class VisionHybrid:
    """Combines DOM text extraction with OCR screenshot fallback.

    Primary: extract text via DOM
    Fallback: screenshot page, run OCR, return combined results
    """

    def __init__(self, ocr: OCREngine, screenshot_dir: Path | None = None) -> None:
        self._ocr = ocr
        self._screenshot_dir = screenshot_dir or Path.cwd() / ".kio_vision_cache"
        self._screenshot_dir.mkdir(parents=True, exist_ok=True)

    async def extract_all_text(self, page: Any, *, use_ocr_fallback: bool = True) -> dict[str, Any]:
        """Extract all visible text from a page using DOM + optional OCR."""
        result: dict[str, Any] = {"dom_text": "", "ocr_text": "", "combined": "", "sources": []}
        try:
            dom_text = await page.evaluate("document.body ? document.body.innerText : ''")
            result["dom_text"] = dom_text.strip()
            result["sources"].append("dom")
        except Exception as exc:
            logger.debug("DOM text extraction failed: %s", exc)

        if use_ocr_fallback and self._ocr.available:
            try:
                ts = int(time.time() * 1000)
                ss_path = self._screenshot_dir / f"vision_{ts}.png"
                await page.screenshot(path=str(ss_path), full_page=False)
                ocr_result = await self._ocr.extract_text(ss_path)
                if ocr_result.get("success"):
                    result["ocr_text"] = ocr_result.get("text", "")
                    result["sources"].append("ocr")
                ss_path.unlink(missing_ok=True)
            except Exception as exc:
                logger.debug("OCR fallback failed: %s", exc)

        texts = [t for t in [result["dom_text"], result["ocr_text"]] if t]
        result["combined"] = "\n".join(texts)
        result["success"] = bool(result["combined"])
        return result

    async def find_text_in_viewport(self, page: Any, query: str) -> dict[str, Any]:
        """Find text in the visible viewport using DOM search + OCR."""
        try:
            found = await page.evaluate(f"window.find('{query.replace(chr(39), '')}')")
            if found:
                return {"success": True, "method": "dom_find", "query": query}
        except Exception:
            pass
        if self._ocr.available:
            ts = int(time.time() * 1000)
            ss_path = self._screenshot_dir / f"find_{ts}.png"
            try:
                await page.screenshot(path=str(ss_path), full_page=False)
                ocr_result = await self._ocr.extract_text(ss_path)
                if query.lower() in ocr_result.get("text", "").lower():
                    return {"success": True, "method": "ocr", "query": query,
                            "context": ocr_result.get("text", "")[:500]}
            except Exception:
                pass
            finally:
                ss_path.unlink(missing_ok=True)
        return {"success": False, "method": "none", "query": query}
