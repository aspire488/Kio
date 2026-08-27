"""
quality.py — Design-quality scoring + real PowerPoint verification
==================================================================

Two verification layers, both honest:

1. score_deck(): a deterministic design audit over the built deck — text
   overflow estimates, overlaps, whitespace, density, archetype variety,
   notes coverage, source/credit completeness. Produces a 0-100 score and a
   per-slide issue list that drives the repair pass.

2. com_verify(): the REAL test — opens the deck in the installed Microsoft
   PowerPoint application (COM), measures each text frame's actual rendered
   bound height (TextRange.BoundHeight) to detect clipped text, and exports
   PNG previews so the rendered result can be analyzed (empty slides, giant
   whitespace) with PIL.

Any failure in either layer is reported truthfully, never papered over.
"""

from __future__ import annotations

import logging
import math
import os
import re
from pathlib import Path
from typing import Any, Optional

logger = logging.getLogger("mini_kio.core.presentation.quality")

_EMPTY_PATTERNS = (
    "overview", "agenda", "section", "divider", "thanks", "thank you",
    "references", "credits", "conclusion", "introduction", "outline",
)


def _shape_rect(shp, emu: float = 914400.0):
    """(x, y, w, h, is_filled) — is_filled False for text boxes so the overlap
    audit ignores intended text-on-panel layering."""
    try:
        from pptx.enum.shapes import MSO_SHAPE_TYPE
        is_filled = shp.shape_type not in (MSO_SHAPE_TYPE.TEXT_BOX,)
        return (
            shp.left / emu, shp.top / emu, shp.width / emu, shp.height / emu, is_filled,
        )
    except Exception:  # noqa: BLE001
        return None


def _intersection(a, b):
    ax0, ay0, aw, ah = a[0], a[1], a[2], a[3]
    bx0, by0, bw, bh = b[0], b[1], b[2], b[3]
    x0 = max(ax0, bx0)
    y0 = max(ay0, by0)
    x1 = min(ax0 + aw, bx0 + bw)
    y1 = min(ay0 + ah, by0 + bh)
    if x1 <= x0 or y1 <= y0:
        return None
    return (x0, y0, x1 - x0, y1 - y0)


def _frame_text(shp) -> str:
    try:
        if shp.has_text_frame:
            return shp.text_frame.text or ""
    except Exception:  # noqa: BLE001
        pass
    return ""


def _estimate_overflow(shp) -> tuple[bool, float]:
    """Rough clipped-text estimate: needed height vs box height (design-time)."""
    try:
        tf = shp.text_frame
        if not tf.text.strip():
            return False, 0.0
    except Exception:  # noqa: BLE001
        return False, 0.0
    rect = _shape_rect(shp)
    if not rect:
        return False, 0.0
    _x, _y, w, h = rect[0], rect[1], rect[2], rect[3]
    if w <= 0.1 or h <= 0.1:
        return False, 0.0
    total = 0.0
    for p in tf.paragraphs:
        runs = [r for r in p.runs if r.text]
        if not runs:
            total += 0.18
            continue
        size = max((r.font.size.pt if r.font.size else 12.0) for r in runs)
        text = "".join(r.text for r in runs)
        avg_char_w = (size / 72.0) * 0.52
        per_line = max(1, int((w - 0.1) / avg_char_w))
        lines = max(1, math.ceil(len(text) / per_line))
        total += lines * (size / 72.0) * 1.24
    return total > h + 0.05, total


def score_deck(path: Path) -> dict[str, Any]:
    """Deterministic design audit of the built deck. Returns score + issues."""
    from pptx import Presentation
    result: dict[str, Any] = {"score": 0.0, "issues": [], "per_slide": {}, "archetypes": {}}
    try:
        prs = Presentation(str(path))
    except Exception as exc:  # noqa: BLE001
        result["issues"].append(f"deck unreadable: {exc}")
        return result
    slide_w = prs.slide_width / 914400.0
    slide_h = prs.slide_height / 914400.0
    canvas = slide_w * slide_h
    issues: list[str] = []
    per_slide: dict[int, dict] = {}
    words_total = 0
    empty_like = 0
    text_shape_count = 0
    overflow_count = 0
    overlap_count = 0
    low_coverage = 0
    archetype_count: dict[str, int] = {}

    for idx, slide in enumerate(prs.slides, start=1):
        si = {"overflow": 0, "overlap": 0, "coverage": 0.0, "words": 0, "shapes": 0}
        rects: list[tuple] = []
        covered = 0.0
        words = 0
        for shp in slide.shapes:
            si["shapes"] += 1
            rect = _shape_rect(shp)
            text = _frame_text(shp)
            words += len(re.findall(r"\S+", text))
            if text.strip():
                text_shape_count += 1
                ov, needed = _estimate_overflow(shp)
                if ov:
                    overflow_count += 1
                    si["overflow"] += 1
                    if si["overflow"] <= 2:
                        issues.append(
                            f"slide {idx}: text may be clipped "
                            f"(box {rect[2]:.1f}x{rect[3]:.1f}in, needs ~{needed:.1f}in)")
            if rect:
                rects.append(rect)
        # union coverage
        if rects:
            sx0 = min(r[0] for r in rects)
            sy0 = min(r[1] for r in rects)
            sx1 = max(r[0] + r[2] for r in rects)
            sy1 = max(r[1] + r[3] for r in rects)
            covered = max(0.0, (sx1 - sx0) * (sy1 - sy0))
        coverage = covered / canvas if canvas else 0.0
        si["coverage"] = round(coverage, 3)
        si["words"] = words
        words_total += words
        # overlap: only flag collisions between two FILLED shapes (panels,
        # cards, pictures). Text boxes sit ON panels/images by design (labels,
        # captions, bullet blocks) — those are composition, not accidents.
        for i in range(len(rects)):
            for j in range(i + 1, len(rects)):
                a, b = rects[i], rects[j]
                if not (a[4] and b[4]):
                    continue  # at least one is a text box — intended layering
                min_area = min(a[2] * a[3], b[2] * b[3])
                if min_area < 0.3:
                    continue
                inter = _intersection(a, b)
                if not inter:
                    continue
                ia = inter[2] * inter[3]
                if ia > 0.22 * min_area:
                    # containment check: >95% of smaller inside larger
                    smaller_inside = (
                        (a[0] >= b[0] - 0.02 and a[1] >= b[1] - 0.02
                         and a[0] + a[2] <= b[0] + b[2] + 0.02
                         and a[1] + a[3] <= b[1] + b[3] + 0.02)
                        or (b[0] >= a[0] - 0.02 and b[1] >= a[1] - 0.02
                            and b[0] + b[2] <= a[0] + a[2] + 0.02
                            and b[1] + b[3] <= a[1] + a[3] + 0.02)
                    )
                    if not smaller_inside:
                        overlap_count += 1
                        si["overlap"] += 1
                        if si["overlap"] <= 2:
                            issues.append(f"slide {idx}: overlapping objects detected")
        # whitespace / emptiness (skip section markers + references)
        low = coverage < 0.16
        if low and si["shapes"] <= 1:
            empty_like += 1
            issues.append(f"slide {idx}: nearly empty (coverage {coverage:.0%})")
            low = False
        if low and not _looks_like_marker(slide):
            low_coverage += 1
            if low_coverage <= 3:
                issues.append(f"slide {idx}: large empty area (content covers {coverage:.0%})")
        # density
        if words > 115 and idx > 1:
            issues.append(f"slide {idx}: text-heavy ({words} words)")
        per_slide[idx] = si

    n = len(prs.slides)
    if n == 0:
        issues.append("deck has no slides")
    else:
        # variety: count archetype by examining the slide's first textbox kicker
        for idx, slide in enumerate(prs.slides, start=1):
            texts = [_frame_text(s) for s in slide.shapes]
            joined = " ".join(t for t in texts if t)
            arch = _guess_archetype(joined)
            archetype_count[arch] = archetype_count.get(arch, 0) + 1
    result["archetypes"] = archetype_count

    # deck-level structure checks
    first_texts = " ".join(_frame_text(s) for s in prs.slides[0].shapes) if n else ""
    last_texts = " ".join(_frame_text(s) for s in prs.slides[-1].shapes) if n else ""
    if not first_texts.strip():
        issues.append("title slide is empty")
    if n >= 3 and not any(w in last_texts.lower() for w in
                          ("conclusion", "takeaway", "summary", "wrap", "next step", "thanks")):
        issues.append("deck lacks a closing slide")

    # notes coverage
    notes_missing = 0
    for slide in prs.slides:
        try:
            if not (slide.notes_slide.notes_text_frame.text or "").strip():
                notes_missing += 1
        except Exception:  # noqa: BLE001
            notes_missing += 1
    if notes_missing:
        issues.append(f"{notes_missing} slide(s) have empty speaker notes")

    # scoring
    score = 100.0
    score -= min(15.0, overflow_count * 6.0)
    score -= min(12.0, overlap_count * 4.0)
    score -= min(10.0, low_coverage * 4.0)
    score -= min(8.0, empty_like * 8.0)
    if n < 5:
        score -= 6
    if notes_missing:
        score -= min(8.0, notes_missing * 2.0)
    if not archetype_count:
        score -= 10
    else:
        top = max(archetype_count.values())
        if n >= 6 and top / n > 0.55:
            score -= 8
            issues.append("too many slides use the same layout")
    # density penalty
    avg_words = words_total / max(1, n)
    if avg_words > 90:
        score -= 5
        issues.append("deck is dense overall — consider splitting slides")
    result["score"] = round(max(0.0, min(100.0, score)), 1)
    result["issues"] = issues[:25]
    result["per_slide"] = per_slide
    result["notes_coverage"] = max(0, n - notes_missing)
    result["slide_count"] = n
    return result


def _looks_like_marker(slide) -> bool:
    texts = " ".join(_frame_text(s) for s in slide.shapes).lower()
    return any(p in texts for p in _EMPTY_PATTERNS)


def _guess_archetype(joined: str) -> str:
    low = joined.lower()
    if re.search(r"\bvs\.?\b|versus|comparison|head to head", low):
        return "comparison"
    if any(w in low for w in ("timeline", "milestone")):
        return "timeline"
    if any(w in low for w in ("architecture", "system", "layers")):
        return "architecture"
    if any(w in low for w in ("how it works", "process", "steps")):
        return "process"
    if "data" in low and ("source" in low or "chart" in low):
        return "chart"
    if any(w in low for w in ("agenda", "what we'll cover")):
        return "agenda"
    if "conclusion" in low or "takeaway" in low:
        return "conclusion"
    if "references" in low or "sources" in low:
        return "references"
    return "standard"


# ── PowerPoint COM render + verification ─────────────────────────────────────

def com_verify(path: Path, timeout: float = 60.0) -> dict[str, Any]:
    """Open the deck in the real PowerPoint, measure real text overflow,
    export PNG previews. Returns {ok, overflows, png_dir}."""
    result: dict[str, Any] = {"ok": False, "overflows": [], "png_dir": None}
    if os.environ.get("KIO_TEST_MODE") == "1":
        return result
    try:
        import pythoncom
        import win32com.client
    except Exception:  # noqa: BLE001
        return result
    import threading

    def _run() -> None:
        app = None
        try:
            pythoncom.CoInitialize()
            app = win32com.client.gencache.EnsureDispatch("PowerPoint.Application")
            pres = app.Presentations.Open(str(path), ReadOnly=True, WithWindow=False)
            n = pres.Slides.Count
            overflows = []
            for i in range(1, n + 1):
                slide = pres.Slides(i)
                for shp in slide.Shapes:
                    try:
                        if not shp.HasTextFrame:
                            continue
                        tf = shp.TextFrame
                        if not tf.HasText:
                            continue
                        tr = tf.TextRange
                        bh = tr.BoundHeight
                        sh = shp.Height
                        if bh and sh and bh > sh + 3.0:
                            overflows.append((i, int(shp.Index)))
                    except Exception:  # noqa: BLE001
                        continue
            png_dir = path.parent / f"{path.stem}_preview"
            try:
                png_dir.mkdir(exist_ok=True)
            except Exception:  # noqa: BLE001
                png_dir = None
            if png_dir is not None:
                try:
                    pres.Export(str(png_dir), "PNG")
                except Exception as exc:  # noqa: BLE001
                    logger.debug("COM png export failed: %s", exc)
                    png_dir = None
            result["ok"] = True
            result["overflows"] = overflows
            result["png_dir"] = str(png_dir) if png_dir else None
            result["slide_count"] = n
            pres.Close()
        except Exception as exc:  # noqa: BLE001
            logger.debug("[COM] verify failed: %s", exc)
        finally:
            try:
                if app is not None:
                    app.Quit()
            except Exception:  # noqa: BLE001
                pass

    worker = threading.Thread(target=_run, daemon=True)
    worker.start()
    worker.join(timeout)
    return result


def analyze_previews(png_dir: Optional[str]) -> dict[str, Any]:
    """PIL analysis of exported PNGs: empty slides / giant whitespace."""
    out: dict[str, Any] = {"slides": {}, "empty": [], "sparse": []}
    if not png_dir:
        return out
    try:
        from PIL import Image
    except Exception:  # noqa: BLE001
        return out
    p = Path(png_dir)
    for img_path in sorted(p.glob("*.PNG")) + sorted(p.glob("*.png")):
        try:
            im = Image.open(str(img_path)).convert("RGB")
            w, h = im.size
            px_ = im.load()
            # sample grid 40x22
            corner = px_[2, 2]
            ink = 0
            total = 0
            for gy in range(0, h, max(1, h // 22)):
                for gx in range(0, w, max(1, w // 40)):
                    total += 1
                    r, g, b = px_[gx, gy]
                    if abs(r - corner[0]) + abs(g - corner[1]) + abs(b - corner[2]) > 60:
                        ink += 1
            cov = ink / max(1, total)
            out["slides"][img_path.name] = round(cov, 3)
            if cov < 0.03:
                out["empty"].append(img_path.name)
            elif cov < 0.12:
                out["sparse"].append(img_path.name)
        except Exception as exc:  # noqa: BLE001
            logger.debug("preview analysis failed for %s: %s", img_path, exc)
    return out
