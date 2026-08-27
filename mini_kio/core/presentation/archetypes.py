"""
archetypes.py — Slide archetype renderers
==========================================

Each archetype is a pure composition: it places objects on the 12-column
grid through the shared helpers — explicit placement, consistent gutters,
no arbitrary coordinates. Every slide looks like part of ONE deck because
all archetypes share the same kicker/title/stat/table vocabulary.

Supported archetypes: title_hero, section_divider, agenda, statement,
image_narrative, comparison_2col, comparison_3col, metric_cards,
statistics, timeline, roadmap, process, funnel, architecture_layered,
architecture_system, data_flow, cycle, hierarchy, before_after, pros_cons,
table, chart, quote, case_study, code, conclusion, references, credits,
standard.
"""

from __future__ import annotations

import re

from pptx.enum.shapes import MSO_SHAPE
from pptx.enum.text import MSO_ANCHOR, PP_ALIGN
from pptx.util import Inches, Pt

from mini_kio.core.presentation.design import (
    BODY_TOP_IN,
    GUTTER_IN,
    MARGIN_IN,
    SLIDE_H_IN,
    SLIDE_W_IN,
    col_w,
    center_x,
    darker,
    lighter,
    px,
)
from mini_kio.core.presentation.helpers import (
    add_arrow,
    add_chip,
    add_line,
    add_multi_bullets,
    add_picture_fit,
    add_rect,
    add_stat,
    add_table,
    add_text,
)


def add_kicker(slide, deck, text, x=None, y=0.52, color=None, size=None, w=None):
    x = MARGIN_IN if x is None else x
    w = col_w(6) if w is None else w
    color = deck.palette["secondary"] if color is None else color
    return add_text(slide, x, y, w, 0.28, str(text).upper(), font=deck.body_font,
                    size=size or deck.scale.kicker, color=color, bold=True)


def add_title(slide, deck, text, y=0.92, x=MARGIN_IN, w=None, size=None, color=None):
    w = col_w(10) if w is None else w
    color = deck.palette["ink"] if color is None else color
    return add_text(slide, x, y, w, 0.85, text, font=deck.display_font,
                    size=size or deck.scale.title, color=color, bold=True)


def add_footer(slide, deck, slide_idx: int):
    color = deck.palette["muted"]
    y = SLIDE_H_IN - 0.34
    add_text(slide, MARGIN_IN, y, 8.0, 0.24, deck.footer_text, font=deck.body_font,
             size=deck.scale.footnote, color=color)
    tb = slide.shapes.add_textbox(Inches(SLIDE_W_IN - MARGIN_IN - 1.0), Inches(y),
                                  Inches(1.0), Inches(0.24))
    tf = tb.text_frame
    tf.margin_left = 0
    p = tf.paragraphs[0]
    p.alignment = PP_ALIGN.RIGHT
    r = p.add_run()
    r.text = str(slide_idx)
    r.font.name = deck.body_font
    r.font.size = Pt(deck.scale.footnote)
    r.font.color.rgb = px(color)


# ── hero / chrome archetypes ─────────────────────────────────────────────────

def render_title_hero(slide, deck, spec, ctx):
    dark = deck.dark
    add_rect(slide, 0, 0, SLIDE_W_IN, SLIDE_H_IN, deck.palette["bg"])
    if not dark:
        add_rect(slide, 0, 0, SLIDE_W_IN, SLIDE_H_IN * 0.62, deck.palette["primary"])
    img = spec.image
    if img and img.get("path"):
        if dark:
            iw, ih = 4.9, 5.3
            add_picture_fit(slide, img, SLIDE_W_IN - iw - 0.55, (SLIDE_H_IN - ih) / 2 + 0.2,
                            iw, ih, focus=(0.5, 0.4), corner=True, deck=deck)
            add_rect(slide, SLIDE_W_IN - iw - 0.75, (SLIDE_H_IN - ih) / 2 + 0.4,
                     0.08, ih - 0.6, deck.palette["accent"])
        else:
            iw, ih = 5.4, 4.4
            add_picture_fit(slide, img, SLIDE_W_IN - iw - 0.75, (SLIDE_H_IN - ih) / 2 + 0.6,
                            iw, ih, focus=(0.5, 0.4), corner=True, deck=deck)
    tx_color = deck.palette["on_primary"] if not dark else deck.palette["ink"]
    kick = (spec.kicker or "").upper()
    if kick:
        add_text(slide, MARGIN_IN + 0.05, 1.75, col_w(8), 0.3, kick, font=deck.body_font,
                 size=deck.scale.kicker, color=deck.palette["accent"], bold=True)
    add_text(slide, MARGIN_IN + 0.03, 2.12, col_w(9.5), 1.9, spec.title or deck.deck_title,
             font=deck.display_font, size=deck.scale.display, color=tx_color, bold=True)
    sub = spec.subtitle_text or (spec.body[0] if spec.body else "")
    if sub:
        add_text(slide, MARGIN_IN + 0.05, 4.15, col_w(7.5), 0.9, sub, font=deck.body_font,
                 size=deck.scale.subtitle + 1.0,
                 color=deck.palette["muted"] if dark else lighter(deck.palette["primary"], 0.5))
    add_rect(slide, MARGIN_IN + 0.05, 5.15, 1.7, 0.055, deck.palette["accent"])
    if not dark:
        add_text(slide, MARGIN_IN + 0.05, 5.45, col_w(6), 0.3, "KIO  \u00b7  Presentation",
                 font=deck.body_font, size=deck.scale.caption,
                 color=lighter(deck.palette["primary"], 0.45))
    return [img] if img else []


def render_section_divider(slide, deck, spec, ctx):
    add_rect(slide, 0, 0, SLIDE_W_IN, SLIDE_H_IN,
             deck.palette["primary"] if not deck.dark else deck.palette["surface"])
    add_rect(slide, 0, 0, SLIDE_W_IN, 0.14, deck.palette["accent"])
    num = spec.section_number
    if num:
        add_text(slide, MARGIN_IN, 2.05, col_w(4), 0.8, f"{num:02d}", font=deck.display_font,
                 size=54, color=deck.palette["accent"], bold=True)
    add_text(slide, MARGIN_IN, 3.0, col_w(8), 1.2, spec.title, font=deck.display_font,
             size=deck.scale.section, color=deck.palette["on_primary"], bold=True)
    add_rect(slide, MARGIN_IN + 0.05, 4.35, 1.5, 0.05, deck.palette["accent"])
    if spec.body:
        add_text(slide, MARGIN_IN + 0.05, 4.6, col_w(6), 0.8, spec.body[0],
                 font=deck.body_font, size=deck.scale.subtitle,
                 color=lighter(deck.palette["primary"], 0.55))
    return []


def render_agenda(slide, deck, spec, ctx):
    add_kicker(slide, deck, "Agenda")
    add_title(slide, deck, spec.title or "What we'll cover")
    items = spec.body or []
    n = len(items)
    if n == 0:
        return []
    per_col = (n + 1) // 2
    for ci in range(2):
        for ri in range(per_col):
            idx = ci * per_col + ri
            if idx >= n:
                break
            x = MARGIN_IN + ci * (col_w(5.5) + GUTTER_IN * 2)
            y = BODY_TOP_IN + ri * 1.28
            add_rect(slide, x, y, col_w(5.5), 1.02, deck.palette["surface"],
                     line_color=lighter(deck.palette["ink"], 0.78), line_w=0.75)
            add_text(slide, x + 0.18, y + 0.18, 0.8, 0.4, f"{idx + 1:02d}",
                     font=deck.display_font, size=20, color=deck.palette["secondary"], bold=True)
            add_text(slide, x + 0.85, y + 0.22, col_w(5.5) - 1.1, 0.62, items[idx],
                     font=deck.body_font, size=deck.scale.heading, color=deck.palette["ink"],
                     bold=True)
    return []


def render_statement(slide, deck, spec, ctx):
    add_kicker(slide, deck, spec.kicker or "The big idea")
    quote = spec.body[0] if spec.body else (spec.title or "")
    add_text(slide, MARGIN_IN, 2.35, col_w(11), 2.5, quote,
             font=deck.display_font, size=deck.scale.title + 5, color=deck.palette["ink"],
             bold=True, line_spacing=1.12)
    add_rect(slide, MARGIN_IN + 0.05, 4.95, 2.2, 0.06, deck.palette["accent"])
    if len(spec.body) > 1:
        add_text(slide, MARGIN_IN + 0.05, 5.2, col_w(7), 0.8, spec.body[1],
                 font=deck.body_font, size=deck.scale.subtitle, color=deck.palette["muted"])
    return []


def render_image_narrative(slide, deck, spec, ctx):
    add_kicker(slide, deck, spec.kicker or "In context")
    add_title(slide, deck, spec.title)
    img = spec.image
    left_w = col_w(4.7)
    if img and img.get("path"):
        add_picture_fit(slide, img, MARGIN_IN, BODY_TOP_IN, left_w, 4.6,
                        focus=(0.5, 0.35), corner=True, deck=deck)
        if img.get("caption"):
            add_text(slide, MARGIN_IN, BODY_TOP_IN + 4.68, left_w, 0.5, img.get("caption"),
                     font=deck.body_font, size=deck.scale.caption, color=deck.palette["muted"],
                     italic=True)
        txt_x = MARGIN_IN + left_w + GUTTER_IN * 2.2
    else:
        add_multi_bullets(slide, MARGIN_IN, BODY_TOP_IN + 0.1, col_w(11), 4.4,
                          spec.body or [], font=deck.body_font, size=deck.scale.body + 0.5,
                          color=deck.palette["ink"], marker_color=deck.palette["accent"],
                          space_after=10, max_items=7)
        return []
    add_multi_bullets(slide, txt_x, BODY_TOP_IN + 0.1, SLIDE_W_IN - txt_x - MARGIN_IN, 4.6,
                      spec.body or [], font=deck.body_font, size=deck.scale.body,
                      color=deck.palette["ink"], marker_color=deck.palette["secondary"],
                      space_after=8, max_items=7)
    return []


def _split_comparison(spec):
    """Return (headers, col_items) — best effort from columns or body."""
    headers = list(spec.column_headers or [])
    cols = [list(c) for c in (spec.columns or [])]
    if cols and headers:
        return headers, cols
    body = list(spec.body or [])
    if len(headers) == 2 and not cols:
        a, b = [], []
        for line in body:
            parts = re.split(r"\s*\|\s*|\s+vs\.?\s+|\s+versus\s+", line, maxsplit=1)
            if len(parts) == 2:
                a.append(parts[0].strip())
                b.append(parts[1].strip())
            else:
                a.append(line)
        cols = [a, b]
    if not cols and body:
        mid = (len(body) + 1) // 2
        cols = [body[:mid], body[mid:]]
    if not headers and cols:
        headers = [f"Side {i + 1}" for i in range(len(cols))]
    return headers, cols


def render_comparison_2col(slide, deck, spec, ctx):
    add_kicker(slide, deck, spec.kicker or "Head to head")
    add_title(slide, deck, spec.title)
    headers, cols = _split_comparison(spec)
    panel_w = col_w(5.4)
    gap_x = GUTTER_IN * 2
    y = BODY_TOP_IN
    if spec.stats:
        chips_h = 0.95
        for si, st in enumerate(spec.stats[:4]):
            cx = MARGIN_IN + si * (panel_w * 0.52 + 0.12)
            add_rect(slide, cx, y, panel_w * 0.52, chips_h, deck.palette["surface"],
                     line_color=lighter(deck.palette["ink"], 0.8), line_w=0.75)
            add_stat(slide, cx + 0.16, y + 0.1, panel_w * 0.52 - 0.3, 0.6,
                     st.get("value", ""), st.get("label", ""), deck=deck,
                     value_size=deck.scale.title, value_color=deck.palette["primary"])
        y += chips_h + 0.35
    ph = 0.6
    for ci, header in enumerate(headers[:2]):
        x = MARGIN_IN + ci * (panel_w + gap_x)
        add_rect(slide, x, y, panel_w, ph,
                 deck.palette["primary"] if ci == 0 else deck.palette["secondary"])
        add_text(slide, x + 0.2, y + 0.12, panel_w - 0.4, 0.4, header or f"Side {ci + 1}",
                 font=deck.body_font, size=deck.scale.heading, color=deck.palette["on_primary"],
                 bold=True)
        items = cols[ci] if ci < len(cols) else []
        add_multi_bullets(slide, x + 0.2, y + ph + 0.25, panel_w - 0.4, 3.6, items,
                          font=deck.body_font, size=deck.scale.body, color=deck.palette["ink"],
                          marker_color=deck.palette["secondary"] if ci == 0 else deck.palette["accent"],
                          space_after=7, max_items=6)
    if headers[:2]:
        vsx = MARGIN_IN + panel_w + gap_x / 2 - 0.42
        add_rect(slide, vsx, y + ph + 1.15, 0.84, 0.84, deck.palette["accent"],
                 shape_type=MSO_SHAPE.OVAL)
        add_text(slide, vsx, y + ph + 1.28, 0.84, 0.34, "VS", font=deck.body_font,
                 size=15, color=deck.palette["on_primary"], bold=True, align=PP_ALIGN.CENTER)
    return []


def render_comparison_3col(slide, deck, spec, ctx):
    add_kicker(slide, deck, spec.kicker or "At a glance")
    add_title(slide, deck, spec.title)
    headers, cols = _split_comparison(spec)
    headers = [headers[i] if i < len(headers) else f"Option {i + 1}" for i in range(3)]
    panel_w = col_w(3.6)
    gap_x = GUTTER_IN * 1.4
    y = BODY_TOP_IN
    colors = [deck.palette["primary"], deck.palette["secondary"], deck.palette["accent"]]
    for ci in range(3):
        x = MARGIN_IN + ci * (panel_w + gap_x)
        add_rect(slide, x, y, panel_w, 0.6, colors[ci])
        add_text(slide, x + 0.18, y + 0.12, panel_w - 0.36, 0.4, headers[ci],
                 font=deck.body_font, size=deck.scale.heading, color=deck.palette["on_primary"],
                 bold=True)
        items = cols[ci] if ci < len(cols) else []
        add_rect(slide, x, y + 0.6, panel_w, 4.0, deck.palette["surface"],
                 line_color=lighter(deck.palette["ink"], 0.8), line_w=0.75)
        add_multi_bullets(slide, x + 0.2, y + 0.85, panel_w - 0.4, 3.6, items,
                          font=deck.body_font, size=deck.scale.body - 0.5,
                          color=deck.palette["ink"], marker_color=colors[ci],
                          space_after=6, max_items=7)
    return []


def render_metric_cards(slide, deck, spec, ctx):
    add_kicker(slide, deck, spec.kicker or "Key metrics")
    add_title(slide, deck, spec.title)
    stats = spec.stats or ([spec.stat] if spec.stat else [])
    n = len(stats)
    if n == 0:
        return render_standard(slide, deck, spec, ctx)
    cols = 4 if n >= 4 else n
    card_w = (col_w(11.4) - (cols - 1) * GUTTER_IN) / cols
    card_h = 2.3
    y = BODY_TOP_IN + 0.15
    for si, st in enumerate(stats[:cols]):
        x = MARGIN_IN + si * (card_w + GUTTER_IN)
        add_rect(slide, x, y, card_w, card_h, deck.palette["surface"],
                 line_color=lighter(deck.palette["ink"], 0.78), line_w=0.75)
        add_rect(slide, x, y, card_w, 0.09, deck.palette["secondary"])
        add_stat(slide, x + 0.25, y + 0.4, card_w - 0.5, 1.0, st.get("value", ""),
                 "", deck=deck, value_size=deck.scale.stat, value_color=deck.palette["primary"])
        add_text(slide, x + 0.25, y + 1.55, card_w - 0.5, 0.7, st.get("label", ""),
                 font=deck.body_font, size=deck.scale.body, color=deck.palette["muted"])
    if n > cols:
        rest = [f"{s.get('label', '')}: {s.get('value', '')}" for s in stats[cols:]]
        add_multi_bullets(slide, MARGIN_IN, y + card_h + 0.5, col_w(8), 1.6, rest,
                          font=deck.body_font, size=deck.scale.body - 0.5,
                          color=deck.palette["ink"], marker_color=deck.palette["accent"],
                          max_items=4)
    return []


def render_statistics(slide, deck, spec, ctx):
    add_kicker(slide, deck, spec.kicker or "The numbers")
    add_title(slide, deck, spec.title)
    if spec.stat:
        add_stat(slide, MARGIN_IN, BODY_TOP_IN + 0.2, col_w(4), 1.5,
                 spec.stat.get("value", ""), spec.stat.get("label", ""), deck=deck,
                 value_size=deck.scale.display - 6)
    elif spec.stats:
        for si, st in enumerate(spec.stats[:2]):
            add_stat(slide, MARGIN_IN + si * col_w(3), BODY_TOP_IN + 0.2, col_w(3), 1.5,
                     st.get("value", ""), st.get("label", ""), deck=deck, value_size=38)
    chart = spec.chart
    chart_w = col_w(6.8)
    chart_x = SLIDE_W_IN - MARGIN_IN - chart_w
    if chart:
        from mini_kio.core.presentation.viz import add_chart
        add_chart(slide, deck, chart, chart_x, BODY_TOP_IN - 0.1, chart_w, 4.2)
    else:
        add_multi_bullets(slide, chart_x, BODY_TOP_IN + 0.1, chart_w, 4.2, spec.body or [],
                          font=deck.body_font, size=deck.scale.body, color=deck.palette["ink"],
                          marker_color=deck.palette["secondary"], max_items=6)
    src = (spec.chart or {}).get("source")
    if src:
        add_text(slide, MARGIN_IN, SLIDE_H_IN - 0.72, col_w(9), 0.3, f"Source: {src}",
                 font=deck.body_font, size=deck.scale.caption, color=deck.palette["muted"])
    return []


# ── diagram archetypes ───────────────────────────────────────────────────────

def render_timeline(slide, deck, spec, ctx):
    add_kicker(slide, deck, spec.kicker or "Timeline")
    add_title(slide, deck, spec.title)
    tl = spec.timeline or []
    if not tl and spec.body:
        tl = []
        for line in spec.body:
            m = re.match(r"^([\w\s]+?)[:\-]\s*(.+)$", line)
            if m and len(m.group(1).split()) <= 6:
                tl.append((m.group(1).strip(), m.group(2).strip()))
            else:
                tl.append((f"Stage {len(tl) + 1}", line))
    if not tl:
        return render_standard(slide, deck, spec, ctx)
    tl = tl[:6]
    n = len(tl)
    line_y = 4.05
    x0, x1 = MARGIN_IN + 0.35, SLIDE_W_IN - MARGIN_IN - 0.35
    add_line(slide, x0, line_y, x1, line_y, deck.palette["muted"], width_pt=2.2)
    step = (x1 - x0) / max(1, n - 1) if n > 1 else 0
    for i, (label, desc) in enumerate(tl):
        cx = x0 + i * step
        add_rect(slide, cx - 0.11, line_y - 0.11, 0.22, 0.22, deck.palette["accent"],
                 shape_type=MSO_SHAPE.OVAL)
        add_text(slide, cx - 1.1, line_y - 1.15, 2.2, 0.9, label, font=deck.body_font,
                 size=deck.scale.heading - 1, color=deck.palette["primary"], bold=True,
                 align=PP_ALIGN.CENTER)
        add_text(slide, cx - 1.55, line_y + 0.45, 3.1, 1.3, desc, font=deck.body_font,
                 size=deck.scale.caption + 0.8, color=deck.palette["muted"],
                 align=PP_ALIGN.CENTER, line_spacing=1.1)
    return []


def render_roadmap(slide, deck, spec, ctx):
    add_kicker(slide, deck, spec.kicker or "Roadmap")
    add_title(slide, deck, spec.title)
    phases = spec.timeline or []
    if not phases and spec.body:
        phases = [(f"Phase {i + 1}", b) for i, b in enumerate(spec.body)]
    phases = phases[:4]
    n = len(phases)
    if n == 0:
        return render_standard(slide, deck, spec, ctx)
    phase_w = col_w(2.7)
    gap = GUTTER_IN * 1.6
    total_w = n * phase_w + (n - 1) * gap
    x0 = center_x(total_w)
    y = BODY_TOP_IN + 0.4
    colors = [deck.palette["primary"], deck.palette["secondary"],
              deck.palette["accent"], deck.palette["positive"]]
    for i, (label, desc) in enumerate(phases):
        x = x0 + i * (phase_w + gap)
        add_rect(slide, x, y, phase_w, 1.6, deck.palette["surface"],
                 line_color=lighter(deck.palette["ink"], 0.8), line_w=0.75)
        add_rect(slide, x, y, phase_w, 0.5, colors[i % 4])
        add_text(slide, x, y + 0.1, phase_w, 0.3, label, font=deck.body_font,
                 size=deck.scale.label, color=deck.palette["on_primary"], bold=True,
                 align=PP_ALIGN.CENTER)
        add_text(slide, x + 0.18, y + 0.65, phase_w - 0.36, 0.85, desc,
                 font=deck.body_font, size=deck.scale.caption + 0.6,
                 color=deck.palette["ink"], align=PP_ALIGN.CENTER, line_spacing=1.08)
        if i < n - 1:
            add_arrow(slide, x + phase_w + 0.06, y + 0.85, x + phase_w + gap - 0.06,
                      y + 0.85, deck.palette["muted"], width_pt=2.0)
    return []


def render_process(slide, deck, spec, ctx):
    add_kicker(slide, deck, spec.kicker or "How it works")
    add_title(slide, deck, spec.title)
    steps = spec.steps or []
    if not steps and spec.body:
        steps = []
        for b in spec.body:
            m = re.match(r"^(?:step\s*\d+[.:]?\s*|\d+[.)]\s*)(.+)$", b.strip())
            steps.append(m.group(1).strip() if m else b)
    steps = steps[:6]
    n = len(steps)
    if n == 0:
        return render_standard(slide, deck, spec, ctx)
    rows = (n + 3) // 4 if n > 4 else 1
    per_row = (n + rows - 1) // rows
    chev_w = 2.9
    chev_h = 1.5
    gap = 0.06
    colors = [deck.palette["primary"], deck.palette["secondary"], deck.palette["accent"]]
    y0 = BODY_TOP_IN + 0.55
    for i, step in enumerate(steps):
        r = i // per_row
        c = i % per_row
        total = per_row * (chev_w + gap) - gap
        x = center_x(total) + c * (chev_w + gap)
        y = y0 + r * (chev_h + 0.7)
        shp = add_rect(slide, x, y, chev_w, chev_h, colors[r % 3],
                       shape_type=MSO_SHAPE.CHEVRON)
        try:
            shp.adjustments[0] = 0.28
        except Exception:  # noqa: BLE001
            pass
        tf = shp.text_frame
        tf.word_wrap = True
        tf.margin_left = Inches(0.3)
        tf.margin_right = Inches(0.12)
        p = tf.paragraphs[0]
        p.alignment = PP_ALIGN.LEFT
        rn = p.add_run()
        rn.text = f"{i + 1}"
        rn.font.name = deck.body_font
        rn.font.size = Pt(20)
        rn.font.bold = True
        rn.font.color.rgb = px(deck.palette["on_primary"])
        p2 = tf.add_paragraph()
        p2.alignment = PP_ALIGN.LEFT
        r2 = p2.add_run()
        r2.text = step
        r2.font.name = deck.body_font
        r2.font.size = Pt(deck.scale.body - 1.5)
        r2.font.color.rgb = px(deck.palette["on_primary"])
    return []


def render_funnel(slide, deck, spec, ctx):
    add_kicker(slide, deck, spec.kicker or "Funnel")
    add_title(slide, deck, spec.title)
    items = spec.body or []
    if not items:
        items = [spec.title]
    n = min(len(items), 6)
    cw = SLIDE_W_IN - 2 * MARGIN_IN
    top_w, bottom_w = cw, cw * 0.28
    y0 = BODY_TOP_IN + 0.4
    ch = 0.82
    colors = [deck.palette["primary"], deck.palette["secondary"], deck.palette["accent"],
              deck.palette["positive"], deck.palette["secondary"], deck.palette["primary"]]
    for i in range(n):
        frac = i / max(1, n - 1)
        w = top_w - (top_w - bottom_w) * frac
        x = center_x(w)
        y = y0 + i * (ch + 0.08)
        add_rect(slide, x, y, w, ch, colors[i % 6], shape_type=MSO_SHAPE.TRAPEZOID)
        add_text(slide, x + 0.2, y + 0.18, w - 0.4, 0.5, items[i], font=deck.body_font,
                 size=deck.scale.body, color=deck.palette["on_primary"], bold=True,
                 align=PP_ALIGN.CENTER)
    return []


def _layered_items(spec):
    layers = spec.layers
    if layers:
        return [(l.get("name", ""), l.get("desc", ""), l.get("items", [])) for l in layers]
    out = []
    for b in (spec.body or []):
        parts = re.split(r"\s*[:–—-]\s*", b, maxsplit=1)
        out.append((parts[0].strip(), parts[1].strip() if len(parts) > 1 else "", []))
    return out


def render_architecture_layered(slide, deck, spec, ctx):
    add_kicker(slide, deck, spec.kicker or "Architecture")
    add_title(slide, deck, spec.title)
    layers = _layered_items(spec)
    n = len(layers)
    if n == 0:
        return render_standard(slide, deck, spec, ctx)
    n = min(n, 6)
    lw = col_w(7.4)
    lx = MARGIN_IN + (col_w(11) - lw) / 2
    y0 = BODY_TOP_IN + 0.15
    lh = 0.78
    colors = [deck.palette["primary"], deck.palette["secondary"], deck.palette["accent"],
              deck.palette["positive"], deck.palette["secondary"], deck.palette["primary"]]
    for i, (name, desc, _items) in enumerate(layers[:n]):
        y = y0 + i * (lh + 0.16)
        add_rect(slide, lx, y, lw, lh, colors[i % 6])
        add_text(slide, lx + 0.25, y + 0.16, lw - 0.5, 0.5, name, font=deck.body_font,
                 size=deck.scale.heading - 0.5, color=deck.palette["on_primary"], bold=True)
        if desc:
            add_text(slide, lx + 0.25 + col_w(3.4), y + 0.2, lw - col_w(3.4) - 0.4, 0.5,
                     desc, font=deck.body_font, size=deck.scale.caption + 0.5,
                     color=lighter(deck.palette["primary"], 0.55))
    if spec.steps:
        add_multi_bullets(slide, MARGIN_IN + col_w(7.6) + 0.3, BODY_TOP_IN + 0.2,
                          col_w(3.2), 4.4, spec.steps, font=deck.body_font,
                          size=deck.scale.caption + 0.5, color=deck.palette["muted"],
                          marker_color=deck.palette["accent"], max_items=6)
    return []


def render_architecture_system(slide, deck, spec, ctx):
    add_kicker(slide, deck, spec.kicker or "System")
    add_title(slide, deck, spec.title)
    nodes = spec.nodes or []
    if not nodes:
        return render_architecture_layered(slide, deck, spec, ctx)
    n = min(len(nodes), 5)
    cw = col_w(2.1)
    ch = 1.0
    y = 3.0
    total = n * cw + (n - 1) * (col_w(0.7) + GUTTER_IN * 2)
    x0 = center_x(total)
    colors = [deck.palette["primary"], deck.palette["secondary"], deck.palette["accent"],
              deck.palette["positive"], deck.palette["secondary"]]
    for i in range(n):
        x = x0 + i * (cw + col_w(0.7) + GUTTER_IN * 2)
        node = nodes[i]
        shp = add_rect(slide, x, y, cw, ch, colors[i % 5], shape_type=MSO_SHAPE.ROUNDED_RECTANGLE)
        try:
            shp.adjustments[0] = 0.12
        except Exception:  # noqa: BLE001
            pass
        tf = shp.text_frame
        tf.word_wrap = True
        tf.vertical_anchor = MSO_ANCHOR.MIDDLE
        p = tf.paragraphs[0]
        p.alignment = PP_ALIGN.CENTER
        r = p.add_run()
        r.text = node.get("name", f"Node {i + 1}")
        r.font.name = deck.body_font
        r.font.size = Pt(deck.scale.body)
        r.font.bold = True
        r.font.color.rgb = px(deck.palette["on_primary"])
        if i < n - 1:
            add_arrow(slide, x + cw + 0.05, y + ch / 2,
                      x + cw + col_w(0.7) + GUTTER_IN * 2 - 0.05, y + ch / 2,
                      deck.palette["muted"], width_pt=2.0)
    if spec.body:
        add_multi_bullets(slide, MARGIN_IN, BODY_TOP_IN - 0.2, col_w(11), 0.9,
                          spec.body[:3], font=deck.body_font, size=deck.scale.caption + 0.5,
                          color=deck.palette["muted"], marker_color=deck.palette["accent"],
                          max_items=3)
    return []


def render_data_flow(slide, deck, spec, ctx):
    add_kicker(slide, deck, spec.kicker or "Data flow")
    add_title(slide, deck, spec.title)
    steps = spec.steps or spec.body or []
    n = min(len(steps), 6)
    if n == 0:
        return render_standard(slide, deck, spec, ctx)
    bw, bh = col_w(2.4), 1.05
    x0 = MARGIN_IN + 0.6
    y = 3.15
    gap = 0.7
    colors = [deck.palette["primary"], deck.palette["secondary"], deck.palette["accent"]]
    for i, step in enumerate(steps[:n]):
        x = x0 + i * (bw + gap)
        add_rect(slide, x, y, bw, bh, colors[i % 3], shape_type=MSO_SHAPE.ROUNDED_RECTANGLE)
        add_text(slide, x + 0.12, y + 0.18, bw - 0.24, 0.7, step, font=deck.body_font,
                 size=deck.scale.caption + 0.8, color=deck.palette["on_primary"],
                 align=PP_ALIGN.CENTER, bold=True)
        if i < n - 1:
            add_arrow(slide, x + bw + 0.08, y + bh / 2, x + bw + gap - 0.08, y + bh / 2,
                      deck.palette["muted"], width_pt=2.2)
    return []


def render_cycle(slide, deck, spec, ctx):
    import math
    add_kicker(slide, deck, spec.kicker or "Cycle")
    add_title(slide, deck, spec.title)
    items = spec.steps or spec.body or []
    n = min(len(items), 6)
    if n == 0:
        return render_standard(slide, deck, spec, ctx)
    cx, cy = SLIDE_W_IN / 2, 4.1
    radius = 2.15
    box_w, box_h = 2.0, 0.85
    colors = [deck.palette["primary"], deck.palette["secondary"], deck.palette["accent"],
              deck.palette["positive"], deck.palette["secondary"], deck.palette["primary"]]
    for i in range(n):
        ang = -math.pi / 2 + i * (2 * math.pi / n)
        bx = cx + radius * math.cos(ang) - box_w / 2
        by = cy + radius * math.sin(ang) - box_h / 2
        add_rect(slide, bx, by, box_w, box_h, colors[i % 6], shape_type=MSO_SHAPE.ROUNDED_RECTANGLE)
        add_text(slide, bx + 0.1, by + 0.18, box_w - 0.2, 0.5, items[i], font=deck.body_font,
                 size=deck.scale.caption + 0.8, color=deck.palette["on_primary"],
                 align=PP_ALIGN.CENTER, bold=True)
        j = (i + 1) % n
        ang2 = -math.pi / 2 + j * (2 * math.pi / n)
        r_inner = radius - 0.1
        x1 = cx + r_inner * 0.62 * math.cos(ang) + box_w / 2 * math.cos(ang)
        y1 = cy + r_inner * 0.62 * math.sin(ang) + box_h / 2 * math.sin(ang)
        x2 = cx + r_inner * 0.62 * math.cos(ang2) - box_w / 2 * math.cos(ang2)
        y2 = cy + r_inner * 0.62 * math.sin(ang2) - box_h / 2 * math.sin(ang2)
        add_line(slide, x1, y1, x2, y2, deck.palette["muted"], width_pt=1.4)
    return []


def render_hierarchy(slide, deck, spec, ctx):
    add_kicker(slide, deck, spec.kicker or "Structure")
    add_title(slide, deck, spec.title)
    nodes = spec.nodes or []
    if not nodes:
        return render_standard(slide, deck, spec, ctx)
    root = nodes[0].get("name", "Root")
    kids = [n.get("name", "") for n in nodes[1:6]]
    bw, bh = col_w(3.2), 0.9
    rx = center_x(bw)
    ry = BODY_TOP_IN + 0.15
    add_rect(slide, rx, ry, bw, bh, deck.palette["primary"])
    add_text(slide, rx + 0.15, ry + 0.22, bw - 0.3, 0.5, root, font=deck.body_font,
             size=deck.scale.heading, color=deck.palette["on_primary"], bold=True,
             align=PP_ALIGN.CENTER)
    if not kids:
        return []
    ky = ry + bh + 1.15
    nk = len(kids)
    kid_w = col_w(2.4)
    total = nk * kid_w + (nk - 1) * GUTTER_IN
    kx0 = center_x(total)
    for i, k in enumerate(kids):
        kx = kx0 + i * (kid_w + GUTTER_IN)
        add_line(slide, rx + bw / 2, ry + bh, kx + kid_w / 2, ky, deck.palette["muted"],
                 width_pt=1.5)
        add_rect(slide, kx, ky, kid_w, bh, deck.palette["secondary"])
        add_text(slide, kx + 0.12, ky + 0.22, kid_w - 0.24, 0.5, k, font=deck.body_font,
                 size=deck.scale.body - 1, color=deck.palette["on_primary"], bold=True,
                 align=PP_ALIGN.CENTER)
    return []


def render_before_after(slide, deck, spec, ctx):
    add_kicker(slide, deck, spec.kicker or "Before / after")
    add_title(slide, deck, spec.title)
    headers, cols = _split_comparison(spec)
    if not cols:
        cols = [spec.body, []]
    panel_w = col_w(5.1)
    gap = GUTTER_IN * 3
    y = BODY_TOP_IN + 0.2
    pairs = [("Before", deck.palette["negative"]), ("After", deck.palette["positive"])]
    for ci, (label, color) in enumerate(pairs):
        x = MARGIN_IN + ci * (panel_w + gap)
        add_rect(slide, x, y, panel_w, 0.6, color)
        add_text(slide, x + 0.2, y + 0.12, panel_w - 0.4, 0.4,
                 headers[ci] if ci < len(headers) and headers[ci] else label,
                 font=deck.body_font, size=deck.scale.heading, color=deck.palette["on_primary"],
                 bold=True)
        items = cols[ci] if ci < len(cols) else []
        add_rect(slide, x, y + 0.6, panel_w, 3.7, deck.palette["surface"],
                 line_color=lighter(deck.palette["ink"], 0.8), line_w=0.75)
        add_multi_bullets(slide, x + 0.2, y + 0.85, panel_w - 0.4, 3.3, items,
                          font=deck.body_font, size=deck.scale.body, color=deck.palette["ink"],
                          marker_color=color, space_after=7, max_items=6)
    ax = MARGIN_IN + panel_w + gap / 2 - 0.4
    add_rect(slide, ax, y + 1.9, 0.8, 0.8, deck.palette["accent"], shape_type=MSO_SHAPE.OVAL)
    add_text(slide, ax, y + 2.03, 0.8, 0.34, "\u2192", font=deck.body_font, size=22,
             color=deck.palette["on_primary"], bold=True, align=PP_ALIGN.CENTER)
    return []


def render_pros_cons(slide, deck, spec, ctx):
    add_kicker(slide, deck, spec.kicker or "Trade-offs")
    add_title(slide, deck, spec.title)
    headers, cols = _split_comparison(spec)
    if not cols:
        cols = [spec.body, []]
    panel_w = col_w(5.1)
    gap = GUTTER_IN * 3
    y = BODY_TOP_IN + 0.2
    pairs = [("Pros", deck.palette["positive"]), ("Cons", deck.palette["negative"])]
    for ci, (label, color) in enumerate(pairs):
        x = MARGIN_IN + ci * (panel_w + gap)
        add_rect(slide, x, y, panel_w, 0.6, color)
        add_text(slide, x + 0.2, y + 0.12, panel_w - 0.4, 0.4,
                 headers[ci] if ci < len(headers) and headers[ci] else label,
                 font=deck.body_font, size=deck.scale.heading, color=deck.palette["on_primary"],
                 bold=True)
        items = cols[ci] if ci < len(cols) else []
        add_rect(slide, x, y + 0.6, panel_w, 3.9, deck.palette["surface"],
                 line_color=lighter(deck.palette["ink"], 0.8), line_w=0.75)
        for bi, item in enumerate(items[:6]):
            iy = y + 0.85 + bi * 0.62
            add_text(slide, x + 0.22, iy, 0.5, 0.5, "+" if ci == 0 else "\u2212",
                     font=deck.body_font, size=deck.scale.heading, color=color, bold=True)
            add_text(slide, x + 0.6, iy + 0.04, panel_w - 0.9, 0.6, item,
                     font=deck.body_font, size=deck.scale.body - 0.5, color=deck.palette["ink"])
    return []


# ── data / reference archetypes ──────────────────────────────────────────────

def render_table_archetype(slide, deck, spec, ctx):
    add_kicker(slide, deck, spec.kicker or "Data")
    add_title(slide, deck, spec.title)
    rows = spec.table or []
    if not rows and spec.body:
        rows = [re.split(r"\s*\|\s*", b.strip().strip("|")) for b in spec.body if "|" in b]
    if not rows:
        return render_standard(slide, deck, spec, ctx)
    if len(rows) > 9:
        rows = rows[:9]
    row_h = min(0.5, (SLIDE_H_IN - BODY_TOP_IN - 1.3) / max(1, len(rows)))
    add_table(slide, rows, MARGIN_IN + 0.2, BODY_TOP_IN - 0.05, col_w(10.6),
              deck=deck, row_h=row_h, font_size=deck.scale.body - 0.5)
    return []


def render_chart_archetype(slide, deck, spec, ctx):
    add_kicker(slide, deck, spec.kicker or "Data")
    add_title(slide, deck, spec.title)
    chart = spec.chart or {}
    from mini_kio.core.presentation.viz import add_chart
    cw = col_w(7.4)
    add_chart(slide, deck, chart, MARGIN_IN, BODY_TOP_IN - 0.05, cw, 4.35)
    if spec.body:
        add_multi_bullets(slide, MARGIN_IN + cw + GUTTER_IN * 2, BODY_TOP_IN + 0.1,
                          col_w(3.2), 4.4, spec.body, font=deck.body_font,
                          size=deck.scale.caption + 0.5, color=deck.palette["muted"],
                          marker_color=deck.palette["secondary"], max_items=5)
    src = chart.get("source")
    if src:
        add_text(slide, MARGIN_IN, SLIDE_H_IN - 0.72, col_w(9), 0.3, f"Source: {src}",
                 font=deck.body_font, size=deck.scale.caption, color=deck.palette["muted"])
    return []


def render_quote(slide, deck, spec, ctx):
    add_text(slide, MARGIN_IN, 1.6, 2.2, 2.2, "\u201C", font=deck.display_font,
             size=110, color=deck.palette["accent"], bold=True)
    quote = spec.quote or (spec.body[0] if spec.body else "")
    add_text(slide, MARGIN_IN + 0.4, 2.55, col_w(9.5), 2.4, quote, font=deck.display_font,
             size=deck.scale.title + 2, color=deck.palette["ink"], bold=True, line_spacing=1.15)
    if spec.quote_attr:
        add_text(slide, MARGIN_IN + 0.45, 5.15, col_w(6), 0.5,
                 f"\u2014 {spec.quote_attr}", font=deck.body_font, size=deck.scale.subtitle,
                 color=deck.palette["muted"])
    return []


def render_case_study(slide, deck, spec, ctx):
    add_kicker(slide, deck, spec.kicker or "Case study")
    add_title(slide, deck, spec.title)
    img = spec.image
    left_w = col_w(4.7)
    if img and img.get("path"):
        add_picture_fit(slide, img, MARGIN_IN, BODY_TOP_IN, left_w, 3.6,
                        focus=(0.5, 0.35), corner=True, deck=deck)
        tx = MARGIN_IN + left_w + GUTTER_IN * 2.2
        tw = SLIDE_W_IN - tx - MARGIN_IN
    else:
        tx, tw = MARGIN_IN, col_w(11)
    add_multi_bullets(slide, tx, BODY_TOP_IN + 0.05, tw, 3.6, spec.body or [],
                      font=deck.body_font, size=deck.scale.body, color=deck.palette["ink"],
                      marker_color=deck.palette["accent"], space_after=7, max_items=6)
    if spec.stats:
        y = BODY_TOP_IN + 3.75
        n = min(len(spec.stats), 4)
        card_w = (col_w(11) - (n - 1) * GUTTER_IN) / n
        for si, st in enumerate(spec.stats[:n]):
            x = MARGIN_IN + si * (card_w + GUTTER_IN)
            add_rect(slide, x, y, card_w, 1.15, deck.palette["surface"],
                     line_color=lighter(deck.palette["ink"], 0.8), line_w=0.75)
            add_stat(slide, x + 0.18, y + 0.14, card_w - 0.36, 0.7, st.get("value", ""),
                     "", deck=deck, value_size=deck.scale.title + 2)
            add_text(slide, x + 0.18, y + 0.78, card_w - 0.36, 0.35, st.get("label", ""),
                     font=deck.body_font, size=deck.scale.caption + 0.4,
                     color=deck.palette["muted"])
    return []


def render_code(slide, deck, spec, ctx):
    add_kicker(slide, deck, spec.kicker or "In practice")
    add_title(slide, deck, spec.title)
    code = spec.code or "\n".join(spec.body or [])
    panel = add_rect(slide, MARGIN_IN, BODY_TOP_IN - 0.05, col_w(11), 4.4,
                     darker(deck.palette["ink"], 0.9), shape_type=MSO_SHAPE.ROUNDED_RECTANGLE)
    try:
        panel.adjustments[0] = 0.06
    except Exception:  # noqa: BLE001
        pass
    add_text(slide, MARGIN_IN + 0.35, BODY_TOP_IN + 0.25, 1.6, 0.3,
             spec.code_lang or "code", font=deck.body_font, size=deck.scale.label,
             color=deck.palette["accent"], bold=True)
    lines = code.splitlines()[:16]
    tb = slide.shapes.add_textbox(Inches(MARGIN_IN + 0.35), Inches(BODY_TOP_IN + 0.62),
                                  Inches(col_w(10.3)), Inches(3.6))
    tf = tb.text_frame
    tf.word_wrap = False
    code_color = (0xD8, 0xE2, 0xEE)
    for i, ln in enumerate(lines):
        p = tf.paragraphs[0] if i == 0 else tf.add_paragraph()
        p.line_spacing = 1.25
        r = p.add_run()
        r.text = ln or " "
        r.font.name = deck.mono_font
        r.font.size = Pt(deck.scale.code)
        r.font.color.rgb = px(code_color)
    return [panel]


def render_conclusion(slide, deck, spec, ctx):
    if deck.dark:
        add_rect(slide, 0, 0, SLIDE_W_IN, SLIDE_H_IN, deck.palette["bg"])
    else:
        add_rect(slide, 0, 0, SLIDE_W_IN, SLIDE_H_IN, deck.palette["primary"])
    add_kicker(slide, deck, spec.kicker or "Takeaways", color=deck.palette["accent"])
    add_text(slide, MARGIN_IN + 0.03, 1.15, col_w(9), 1.1, spec.title or "Key takeaways",
             font=deck.display_font, size=deck.scale.title + 4,
             color=deck.palette["on_primary"] if not deck.dark else deck.palette["ink"],
             bold=True)
    items = spec.body or []
    y = 2.5
    text_color = deck.palette["on_primary"] if not deck.dark else deck.palette["ink"]
    for i, item in enumerate(items[:5]):
        add_rect(slide, MARGIN_IN + 0.05, y, 0.5, 0.5, deck.palette["accent"],
                 shape_type=MSO_SHAPE.OVAL)
        add_text(slide, MARGIN_IN + 0.05, y + 0.06, 0.5, 0.35, str(i + 1),
                 font=deck.body_font, size=deck.scale.label,
                 color=deck.palette["ink"] if deck.dark else deck.palette["primary"],
                 bold=True, align=PP_ALIGN.CENTER)
        add_text(slide, MARGIN_IN + 0.75, y - 0.03, col_w(9), 0.75, item,
                 font=deck.body_font, size=deck.scale.heading, color=text_color)
        y += 0.88
    if spec.quote:
        add_text(slide, MARGIN_IN + 0.05, 5.7, col_w(8), 0.8, spec.quote,
                 font=deck.body_font, size=deck.scale.subtitle, color=deck.palette["accent"])
    return []


def render_references(slide, deck, spec, ctx):
    add_kicker(slide, deck, spec.kicker or "Sources")
    add_title(slide, deck, spec.title or "References")
    refs = spec.body or []
    y = BODY_TOP_IN - 0.05
    tb = slide.shapes.add_textbox(Inches(MARGIN_IN + 0.05), Inches(y),
                                  Inches(col_w(10.8)), Inches(5.0))
    tf = tb.text_frame
    tf.word_wrap = True
    for i, ref in enumerate(refs[:14]):
        p = tf.paragraphs[0] if i == 0 else tf.add_paragraph()
        p.line_spacing = 1.25
        p.space_after = Pt(6)
        r = p.add_run()
        r.text = f"[{i + 1}]  {ref}"
        r.font.name = deck.body_font
        r.font.size = Pt(deck.scale.body - 1.5)
        r.font.color.rgb = px(deck.palette["muted"])
    return []


def render_credits(slide, deck, spec, ctx):
    add_kicker(slide, deck, spec.kicker or "Credits")
    add_title(slide, deck, spec.title or "Image credits")
    rows = spec.table or []
    if rows:
        add_table(slide, rows, MARGIN_IN + 0.2, BODY_TOP_IN - 0.05, col_w(10.6),
                  deck=deck, row_h=0.5, font_size=deck.scale.body - 1.5)
    else:
        add_multi_bullets(slide, MARGIN_IN + 0.05, BODY_TOP_IN, col_w(10.8), 4.6,
                          spec.body or [], font=deck.body_font, size=deck.scale.body - 1,
                          color=deck.palette["muted"], marker_color=deck.palette["accent"],
                          space_after=6, max_items=10)
    return []


def render_standard(slide, deck, spec, ctx):
    """Title + kicker + body bullets (when content doesn't fit an archetype)."""
    add_kicker(slide, deck, spec.kicker or "Overview")
    add_title(slide, deck, spec.title)
    items = spec.body or []
    if spec.stat:
        y = BODY_TOP_IN - 0.1
        add_stat(slide, MARGIN_IN, y, col_w(3.4), 1.2, spec.stat.get("value", ""),
                 spec.stat.get("label", ""), deck=deck, value_size=38)
        add_multi_bullets(slide, MARGIN_IN + col_w(3.6), y + 0.15, col_w(7.4), 3.9,
                          items, font=deck.body_font, size=deck.scale.body,
                          color=deck.palette["ink"], marker_color=deck.palette["secondary"],
                          space_after=8, max_items=7)
        return []
    add_multi_bullets(slide, MARGIN_IN, BODY_TOP_IN, col_w(10.8), 5.0, items,
                      font=deck.body_font, size=deck.scale.body + 0.5,
                      color=deck.palette["ink"], marker_color=deck.palette["secondary"],
                      space_after=9, max_items=8)
    return []


_ARCHETYPE_RENDERERS = {
    "title_hero": render_title_hero,
    "section_divider": render_section_divider,
    "agenda": render_agenda,
    "statement": render_statement,
    "image_narrative": render_image_narrative,
    "comparison_2col": render_comparison_2col,
    "comparison_3col": render_comparison_3col,
    "metric_cards": render_metric_cards,
    "statistics": render_statistics,
    "timeline": render_timeline,
    "roadmap": render_roadmap,
    "process": render_process,
    "funnel": render_funnel,
    "architecture_layered": render_architecture_layered,
    "architecture_system": render_architecture_system,
    "data_flow": render_data_flow,
    "cycle": render_cycle,
    "hierarchy": render_hierarchy,
    "before_after": render_before_after,
    "pros_cons": render_pros_cons,
    "table": render_table_archetype,
    "chart": render_chart_archetype,
    "quote": render_quote,
    "case_study": render_case_study,
    "code": render_code,
    "conclusion": render_conclusion,
    "references": render_references,
    "credits": render_credits,
    "standard": render_standard,
}


def render_slide(slide, deck, spec, ctx):
    fn = _ARCHETYPE_RENDERERS.get(spec.archetype, render_standard)
    return fn(slide, deck, spec, ctx)
