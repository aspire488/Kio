"""
engine.py — Presentation engine orchestrator
=============================================

create_presentation() runs the full pipeline:

    request → research → plan (LLM or deterministic) → asset acquisition →
    design/build (archetype renderers + theme + transitions + animations) →
    design-quality score → targeted repair → real-PowerPoint render/verify →
    open

Progress is published through the shared user-facing progress bus, and every
failure degrades gracefully (deterministic fallback plan, no images, no
COM) so a deck is always produced.
"""

from __future__ import annotations

import logging
import os
import re
from pathlib import Path
from typing import Any, Optional

from pptx import Presentation
from pptx.util import Inches

from mini_kio.core import user_progress
from mini_kio.core.presentation import (
    archetypes,
    design,
    images as img_lib,
    motion,
    planner,
    quality,
)
from mini_kio.core.presentation.design import (
    MARGIN_IN,
    SLIDE_H_IN,
    SLIDE_W_IN,
    Deck,
    TypeScale,
    col_w,
    detect_palette,
)
from mini_kio.core.presentation.planner import DeckPlan, SlideSpec

logger = logging.getLogger("mini_kio.core.presentation.engine")

_SEQUENCE_ARCHETYPES = frozenset({
    "agenda", "timeline", "roadmap", "process", "data_flow", "cycle",
    "hierarchy", "funnel", "architecture_layered", "architecture_system",
    "metric_cards",
})

_MAX_IMAGES = 5


# ── asset acquisition ────────────────────────────────────────────────────────

def _aspect_for(role: str) -> str:
    return {"hero": "landscape", "side": "landscape",
            "portrait": "portrait", "grid": "square"}.get(role, "any")


def _fetch_plan_images(plan: DeckPlan, subject: str, hermetic: bool) -> list[list[str]]:
    """Fetch requested images; attach to specs; return credits rows."""
    if hermetic:
        return []
    credits: list[list[str]] = []
    fetched = 0
    for spec in plan.slides:
        if spec.image and spec.image.get("query") and fetched < _MAX_IMAGES:
            cand = img_lib.fetch_image(spec.image["query"], aspect=_aspect_for(spec.image.get("role", "side")))
            if cand:
                spec.image.update({
                    "path": cand["path"],
                    "width": cand["width"],
                    "height": cand["height"],
                    "source": cand.get("page", ""),
                    "license": cand.get("license", ""),
                    "artist": cand.get("artist", ""),
                })
                credits.append([
                    cand.get("title", "")[:48],
                    (cand.get("artist") or "Unknown")[:36],
                    (cand.get("license") or "—")[:24],
                ])
                fetched += 1
            else:
                spec.image = None
    return credits[:_MAX_IMAGES]


def _hero_image(subject: str, hermetic: bool) -> Optional[dict]:
    if hermetic:
        return None
    cand = img_lib.fetch_image(subject, aspect="landscape")
    if not cand:
        return None
    return {
        "path": cand["path"], "width": cand["width"], "height": cand["height"],
        "source": cand.get("page", ""), "license": cand.get("license", ""),
        "artist": cand.get("artist", ""), "query": subject,
    }


# ── deck construction ────────────────────────────────────────────────────────

def _add_notes(slide, text: str) -> None:
    try:
        notes = slide.notes_slide
        notes.notes_text_frame.text = (text or " ").strip() or " "
    except Exception:  # noqa: BLE001
        pass


def _default_notes(spec: SlideSpec, idx: int) -> str:
    """Speaker notes = slide title + the actual points verbatim (braces and
    all), then presenter guidance. The audience sees a polished slide; the
    presenter has the real talking points."""
    parts: list[str] = []
    items = spec.body or spec.steps or []
    if spec.title:
        parts.append(spec.title)
    for item in items[:6]:
        parts.append("\u2022 " + item)
    if spec.notes:
        parts.append(spec.notes)
    elif items:
        parts.append("Expand each point with one concrete detail from the research.")
    if spec.stat and spec.stat.get("source"):
        parts.append(f"Statistic source: {spec.stat['source']}.")
    return "\n".join(parts) if parts else (spec.title or f"Slide {idx}")


def _render_slide(prs, deck, spec: SlideSpec, ctx: dict) -> None:
    slide = prs.slides.add_slide(prs.slide_layouts[6])
    archetypes.render_slide(slide, deck, spec, ctx)
    notes = _default_notes(spec, ctx["idx"])
    if spec.image and spec.image.get("artist"):
        notes += (
            f"\nImage: {spec.image.get('title', '')} by {spec.image.get('artist', '')} "
            f"({spec.image.get('license', '')}) — {spec.image.get('source', '')}"
        )
    _add_notes(slide, notes)
    archetypes.add_footer(slide, deck, ctx["idx"])
    # transitions
    if spec.archetype == "section_divider":
        motion.add_transition(slide, "push")
    else:
        motion.add_transition(slide, "fade")
    # controlled sequencing for diagram/timeline slides
    if spec.archetype in _SEQUENCE_ARCHETYPES or spec.animation == "sequence":
        shape_ids = motion.collect_animation_shapes(slide, deck)
        if shape_ids:
            motion.add_entrance_sequence(slide, shape_ids)


def _title_slide(prs, deck, plan: DeckPlan, subject: str, hero: Optional[dict], style: str) -> None:
    spec = SlideSpec(
        archetype="title_hero",
        kicker=style or "Presentation",
        title=plan.topic or subject,
        subtitle_text=plan.subtitle,
        body=[plan.subtitle] if plan.subtitle else [],
        image=hero,
        notes=(
            f"Title: {plan.topic or subject}. "
            f"Open with the one-line story: {plan.subtitle or 'why this topic matters now'}."
        ),
    )
    ctx = {"idx": 1}
    _render_slide(prs, deck, spec, ctx)
    # title slide: no footer animation — keep static
    for el in prs.slides[0]._element.findall(
            "{http://schemas.openxmlformats.org/presentationml/2006/main}timing"):
        prs.slides[0]._element.remove(el)


def build_deck(path: Path, plan: DeckPlan, subject: str, style: str,
               hermetic: bool = False) -> Optional[Presentation]:
    """Build the full deck from the plan. Returns prs (saved) or None."""
    try:
        prs = Presentation()
        prs.slide_width = Inches(SLIDE_W_IN)
        prs.slide_height = Inches(SLIDE_H_IN)
    except Exception as exc:  # noqa: BLE001
        logger.exception("deck init failed: %s", exc)
        return None
    palette_key = detect_palette(subject) if plan.palette_key == "neutral" and subject else plan.palette_key
    palette = design.PALETTES.get(palette_key, design.PALETTES["neutral"])
    deck = Deck(
        prs=prs, palette=palette, palette_key=palette_key,
        display_font=palette.get("display", "Segoe UI"),
        body_font=palette.get("body", "Segoe UI"),
        mono_font=palette.get("mono", "Consolas"),
        deck_title=plan.topic or subject,
        footer_text=(plan.topic or subject)[:60],
    )
    motion.apply_theme(prs, deck)
    hero = _hero_image(subject if subject else plan.topic, hermetic) if not hermetic else None
    _title_slide(prs, deck, plan, subject, hero, style)

    idx = 2
    first = True
    for spec in plan.slides:
        if spec.archetype == "title_hero":
            continue
        # section divider before a new section (skip before the first content slide)
        if spec.section_label and not first and spec.section_number:
            div = SlideSpec(
                archetype="section_divider", title=spec.section_label,
                section_number=spec.section_number,
                notes=f"Section {spec.section_number}: {spec.section_label}.",
            )
            _render_slide(prs, deck, div, {"idx": idx})
            idx += 1
        first = False
        _render_slide(prs, deck, spec, {"idx": idx})
        idx += 1

    # Guarantee a closing slide in production: if the plan never included one,
    # synthesize a conclusion from the deck's own strongest content (never
    # filler — real points the deck already made). Skipped in hermetic/test
    # mode so the deterministic deck stays exactly title + content slides.
    if not hermetic and plan.slides:
        has_closing = any(
            s.archetype in ("conclusion", "references", "credits", "thanks")
            for s in plan.slides
        )
        if not has_closing:
            takeaways: list[str] = []
            for s in plan.slides[:6]:
                item = (s.body[0] if s.body else (s.title or "")).strip()
                if item and item not in takeaways:
                    takeaways.append(item)
                if len(takeaways) >= 4:
                    break
            if not takeaways:
                takeaways = [plan.subtitle or f"What {plan.topic or 'this topic'} taught us."]
            conc = SlideSpec(
                archetype="conclusion", title="Key takeaways",
                kicker="Takeaways", body=takeaways[:4],
                quote=plan.subtitle or "",
                notes=(
                    "Close the loop: restate the big idea and walk the three "
                    "strongest points the deck already made."
                ),
            )
            _render_slide(prs, deck, conc, {"idx": idx})
            idx += 1

    # closing slides: references + credits (only when they add real value)
    if plan.references:
        ref = SlideSpec(
            archetype="references", title="References & sources",
            body=plan.references,
            notes="The audience sees sources; cite the key ones verbally.",
        )
        _render_slide(prs, deck, ref, {"idx": idx})
        idx += 1
    if plan.credits_rows:
        cred = SlideSpec(
            archetype="credits", title="Image credits",
            table=[["Image", "Author", "License"]] + plan.credits_rows,
            notes="Attribution for every image used in this deck.",
        )
        _render_slide(prs, deck, cred, {"idx": idx})
        idx += 1

    try:
        prs.save(str(path))
    except Exception as exc:  # noqa: BLE001
        logger.exception("deck save failed: %s", exc)
        return None
    return prs


# ── targeted repair ──────────────────────────────────────────────────────────

def _apply_plan_fixes(plan: DeckPlan, q: dict) -> bool:
    """Trim content on flagged slides (never shrink text — restructure)."""
    changed = False
    per = q.get("per_slide") or {}
    # per_slide keys are 1-based deck slide indices; map back via plan order
    deck_idx = 2
    for spec in plan.slides:
        info = per.get(deck_idx) or {}
        overflow = int(info.get("overflow") or 0)
        words = int(info.get("words") or 0)
        if overflow or words > 110:
            if spec.body and len(spec.body) > 5:
                spec.body = spec.body[:5]
                changed = True
            if spec.steps and len(spec.steps) > 5:
                spec.steps = spec.steps[:5]
                changed = True
            if spec.body:
                trimmed = []
                for b in spec.body:
                    trimmed.append(b if len(b) <= 110 else b[:108].rsplit(" ", 1)[0] + "…")
                if trimmed != spec.body:
                    spec.body = trimmed
                    changed = True
        deck_idx += 1
    return changed


# ── entry point ──────────────────────────────────────────────────────────────

def create_presentation(
    subject: str,
    style: str = "",
    seed_content: str = "",
    out_dir: Optional[Path] = None,
    opts: Optional[dict] = None,
) -> dict[str, Any]:
    """Create a designed, validated PowerPoint deck. Canonical entry point."""
    opts = opts or {}
    hermetic = os.environ.get("KIO_TEST_MODE") == "1"
    subject = (subject or "").strip().rstrip(".,!?;:")
    if not subject:
        return {"success": False, "message": "I need a subject before I can create a presentation."}

    user_progress.begin("presentation")
    publish = user_progress.publish
    publish("Working on the presentation…")

    # 1 · research
    facts = "" if hermetic else planner.research_facts(subject)
    publish("Researching the topic…")

    # 2 · plan (story → slide purposes → visual grammar → assets)
    publish("Planning the story…")
    plan = planner.build_plan(subject, style, seed_content, facts, hermetic=hermetic)
    if not plan.slides:
        user_progress.end()
        return {"success": False, "message": "I couldn't plan that presentation."}

    # 3 · assets (images with attribution)
    publish("Adding visuals…")
    plan.credits_rows = _fetch_plan_images(plan, subject, hermetic)

    # 4 · build + design-quality repair loop (bounded)
    directory = out_dir or _documents_dir()
    try:
        directory.mkdir(parents=True, exist_ok=True)
    except Exception as exc:  # noqa: BLE001
        user_progress.end()
        return {"success": False, "message": f"Couldn't use the output folder: {exc}"}

    filename = _filename(subject) + ".pptx"
    path = _ensure_unique(directory / filename)

    publish("Designing the slides…")
    built = build_deck(path, plan, subject, style, hermetic=hermetic)
    if built is None:
        user_progress.end()
        return {"success": False, "message": "The presentation couldn't be written."}

    # An explicit slide count ("five-slide deck") is a hard requirement, not a
    # hint. The deck always contains furniture the plan does not (title and
    # section slides), so measure that difference on the built file and fit the
    # plan so the finished deck lands on exactly the requested count. Bodies
    # are counted per rebuild, so this converges in one or two passes; if the
    # furniture floor is already above the request the loop stops and the real
    # count is reported honestly instead of being faked.
    requested_slides = int(opts.get("slide_count") or 0)
    if requested_slides:
        for _attempt in range(3):
            probe = quality.score_deck(path)
            actual = int(probe.get("slide_count") or 0)
            if actual == requested_slides:
                break
            furniture = max(0, actual - len(plan.slides))
            want = requested_slides - furniture
            if want < 1 or want == len(plan.slides):
                break
            fitted = planner.fit_plan_slides(plan.slides, want)
            if len(fitted) == len(plan.slides):
                break
            plan.slides = fitted
            built = build_deck(path, plan, subject, style, hermetic=hermetic)
            if built is None:
                break

    q = quality.score_deck(path)
    for _attempt in range(2):
        if q.get("score", 0) >= 70 and not _overflow_issues(q):
            break
        changed = _apply_plan_fixes(plan, q)
        if not changed:
            break
        built = build_deck(path, plan, subject, style, hermetic=hermetic)
        if built is None:
            break
        q = quality.score_deck(path)

    # 5 · real-PowerPoint verification (render + overflow) + targeted repair
    publish("Finishing the PowerPoint…")
    verify = quality.com_verify(path) if not hermetic else {"ok": False}
    if verify.get("ok") and verify.get("overflows"):
        # trim the slides PowerPoint measured as clipped
        deck_idx = 2
        for spec in plan.slides:
            hit = any(ov[0] == deck_idx for ov in verify["overflows"])
            if hit and spec.body:
                spec.body = spec.body[:4]
            deck_idx += 1
        build_deck(path, plan, subject, style, hermetic=hermetic)
        verify2 = quality.com_verify(path)
        if verify2.get("ok") and verify2.get("png_dir"):
            verify = verify2

    previews = quality.analyze_previews(verify.get("png_dir"))

    # 6 · open in PowerPoint
    publish("Opening it in PowerPoint…")
    if not hermetic:
        try:
            from mini_kio.core.artifact_operator import open_artifact
            open_artifact(path)
        except Exception:  # noqa: BLE001
            pass

    facts2 = quality.score_deck(path)
    user_progress.end()
    return {
        "success": True,
        "message": f"Created {path.name} — {facts2.get('slide_count', 0)} slides.",
        "path": str(path),
        "filename": path.name,
        "slide_count": facts2.get("slide_count", 0),
        "notes_count": facts2.get("notes_coverage", 0),
        "quality_score": facts2.get("score", 0.0),
        "quality_issues": facts2.get("issues", [])[:8],
        "archetypes": list((facts2.get("archetypes") or {}).keys()),
        "images": len(plan.credits_rows),
        "preview_analysis": previews,
        "artifact": "presentation",
        "subject": subject,
    }


def _overflow_issues(q: dict) -> bool:
    return any("clipped" in i or "text-heavy" in i or "overlapping" in i
               for i in q.get("issues", []))


def _documents_dir() -> Path:
    from mini_kio.core.document_operator import documents_dir
    return documents_dir()


def _filename(subject: str) -> str:
    from mini_kio.core.artifact_operator import generate_artifact_filename
    return generate_artifact_filename(subject, "presentation")


def _ensure_unique(path: Path) -> Path:
    if not path.exists():
        return path
    stem, ext = path.stem, path.suffix
    parent = path.parent
    i = 2
    while True:
        candidate = parent / f"{stem} ({i}){ext}"
        if not candidate.exists():
            return candidate
        i += 1
