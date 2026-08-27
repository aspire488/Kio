"""
design.py — Presentation design system (tokens, palettes, typography, canvas)
=============================================================================

The deck-level design language used by every slide archetype:

  - domain palettes (tech/energy/sports/academic/space/product/education/
    finance/neutral) — restrained, subject-related identities, never random
    per-slide colors
  - presentation-wide type roles (display/title/kicker/body/stat/label/
    caption/footnote) with a coherent font pairing
  - a 13.333 x 7.5 inch canvas with real margins, gutters and a 12-column
    grid so every object is placed mathematically (no arbitrary coordinates)

All renderers consume Canvas + tokens; nothing hardcodes pixel coordinates.
"""

from __future__ import annotations

import math
from dataclasses import dataclass, field
from typing import Optional

from pptx.dml.color import RGBColor
from pptx.enum.text import MSO_ANCHOR, PP_ALIGN
from pptx.util import Inches, Pt


# ── geometry ─────────────────────────────────────────────────────────────────
SLIDE_W_IN = 13.333
SLIDE_H_IN = 7.5
MARGIN_IN = 0.62          # outer safety margin
GUTTER_IN = 0.24          # gutter between grid columns / cards
CONTENT_W_IN = SLIDE_W_IN - 2 * MARGIN_IN   # 12.093
COL_W_IN = (CONTENT_W_IN - 11 * GUTTER_IN) / 12.0
TITLE_TOP_IN = 0.55
BODY_TOP_IN = 1.78


def col_x(col: int, span: int = 1, *, margin: float = MARGIN_IN) -> float:
    """Left edge (inches) of a 12-col grid column starting at `col` (0-based)."""
    return margin + col * (COL_W_IN + GUTTER_IN)


def col_w(span: int) -> float:
    """Width (inches) of `span` grid columns (with gutters between)."""
    return span * COL_W_IN + (span - 1) * GUTTER_IN


def center_x(width_in: float) -> float:
    return (SLIDE_W_IN - width_in) / 2.0


def rect_union(rects) -> Optional[tuple[float, float, float, float]]:
    """Union of (x, y, w, h) rects; None when empty."""
    if not rects:
        return None
    x0 = min(r[0] for r in rects)
    y0 = min(r[1] for r in rects)
    x1 = max(r[0] + r[2] for r in rects)
    y1 = max(r[1] + r[3] for r in rects)
    return (x0, y0, x1 - x0, y1 - y0)


def rects_overlap(a, b, tol: float = 0.02) -> bool:
    ax0, ay0, aw, ah = a
    bx0, by0, bw, bh = b
    if ax0 + aw <= bx0 + tol or bx0 + bw <= ax0 + tol:
        return False
    if ay0 + ah <= by0 + tol or by0 + bh <= ay0 + tol:
        return False
    return True


# ── palettes (restrained, subject-related) ───────────────────────────────────
# Each palette: bg (canvas), surface (cards), ink (body text), muted,
# primary, secondary, accent, positive, negative, on_primary (text on primary).
PALETTES: dict[str, dict[str, tuple[int, int, int]]] = {
    "tech": {
        "bg": (0xF5, 0xF7, 0xFA), "surface": (0xFF, 0xFF, 0xFF),
        "ink": (0x14, 0x21, 0x3D), "muted": (0x5C, 0x6B, 0x80),
        "primary": (0x14, 0x21, 0x3D), "secondary": (0x1D, 0x4E, 0xD8),
        "accent": (0x0E, 0xA5, 0xA4), "positive": (0x16, 0xA3, 0x4A),
        "negative": (0xDC, 0x26, 0x26), "on_primary": (0xFF, 0xFF, 0xFF),
        "display": "Segoe UI", "body": "Segoe UI", "mono": "Consolas",
    },
    "energy": {
        "bg": (0xF4, 0xF7, 0xF2), "surface": (0xFF, 0xFF, 0xFF),
        "ink": (0x12, 0x28, 0x1F), "muted": (0x55, 0x6B, 0x5E),
        "primary": (0x0B, 0x3D, 0x2E), "secondary": (0x2F, 0x7D, 0x4F),
        "accent": (0xE9, 0xA2, 0x3B), "positive": (0x2F, 0x8F, 0x5B),
        "negative": (0xC0, 0x50, 0x3D), "on_primary": (0xFF, 0xFF, 0xFF),
        "display": "Segoe UI", "body": "Segoe UI", "mono": "Consolas",
    },
    "sports": {
        "bg": (0xF6, 0xF7, 0xF9), "surface": (0xFF, 0xFF, 0xFF),
        "ink": (0x13, 0x17, 0x22), "muted": (0x5A, 0x64, 0x78),
        "primary": (0x0F, 0x17, 0x2A), "secondary": (0xE1, 0x1D, 0x48),
        "accent": (0xF5, 0x9E, 0x0B), "positive": (0x16, 0xA3, 0x4A),
        "negative": (0xDC, 0x26, 0x26), "on_primary": (0xFF, 0xFF, 0xFF),
        "display": "Segoe UI", "body": "Segoe UI", "mono": "Consolas",
    },
    "academic": {
        "bg": (0xFA, 0xF7, 0xF0), "surface": (0xFF, 0xFF, 0xFF),
        "ink": (0x1A, 0x1A, 0x1A), "muted": (0x66, 0x60, 0x55),
        "primary": (0x8C, 0x2F, 0x39), "secondary": (0x24, 0x34, 0x4D),
        "accent": (0xB4, 0x8A, 0x3B), "positive": (0x2F, 0x6B, 0x2F),
        "negative": (0xA6, 0x35, 0x2D), "on_primary": (0xFF, 0xFF, 0xFF),
        "display": "Georgia", "body": "Segoe UI", "mono": "Consolas",
    },
    "space": {
        "bg": (0x0B, 0x10, 0x26), "surface": (0x15, 0x1B, 0x3D),
        "ink": (0xE8, 0xEC, 0xF8), "muted": (0x9D, 0xA6, 0xC7),
        "primary": (0x0B, 0x10, 0x26), "secondary": (0x4C, 0x6E, 0xF5),
        "accent": (0xF5, 0xC5, 0x42), "positive": (0x34, 0xD3, 0x99),
        "negative": (0xF8, 0x71, 0x71), "on_primary": (0xFF, 0xFF, 0xFF),
        "display": "Segoe UI", "body": "Segoe UI", "mono": "Consolas",
    },
    "product": {
        "bg": (0xF7, 0xF8, 0xFC), "surface": (0xFF, 0xFF, 0xFF),
        "ink": (0x1E, 0x23, 0x30), "muted": (0x5F, 0x67, 0x7D),
        "primary": (0x5B, 0x21, 0xB6), "secondary": (0x1D, 0x4E, 0xD8),
        "accent": (0x06, 0xB6, 0xD4), "positive": (0x16, 0xA3, 0x4A),
        "negative": (0xDC, 0x26, 0x26), "on_primary": (0xFF, 0xFF, 0xFF),
        "display": "Segoe UI", "body": "Segoe UI", "mono": "Consolas",
    },
    "education": {
        "bg": (0xFB, 0xF7, 0xF0), "surface": (0xFF, 0xFF, 0xFF),
        "ink": (0x2B, 0x21, 0x18), "muted": (0x6E, 0x62, 0x50),
        "primary": (0x2F, 0x6F, 0xED), "secondary": (0xE2, 0x72, 0x5B),
        "accent": (0xF4, 0xB9, 0x42), "positive": (0x2E, 0x8B, 0x57),
        "negative": (0xC0, 0x4A, 0x3C), "on_primary": (0xFF, 0xFF, 0xFF),
        "display": "Georgia", "body": "Segoe UI", "mono": "Consolas",
    },
    "finance": {
        "bg": (0xF6, 0xF8, 0xF6), "surface": (0xFF, 0xFF, 0xFF),
        "ink": (0x12, 0x21, 0x1B), "muted": (0x55, 0x68, 0x5D),
        "primary": (0x06, 0x5F, 0x46), "secondary": (0x11, 0x5E, 0x59),
        "accent": (0xB4, 0x53, 0x09), "positive": (0x1B, 0x7F, 0x4B),
        "negative": (0xB3, 0x3A, 0x2E), "on_primary": (0xFF, 0xFF, 0xFF),
        "display": "Segoe UI", "body": "Segoe UI", "mono": "Consolas",
    },
    "neutral": {
        "bg": (0xF5, 0xF6, 0xF8), "surface": (0xFF, 0xFF, 0xFF),
        "ink": (0x1F, 0x29, 0x37), "muted": (0x5B, 0x66, 0x74),
        "primary": (0x1F, 0x29, 0x37), "secondary": (0x37, 0x41, 0x51),
        "accent": (0x25, 0x63, 0xEB), "positive": (0x16, 0xA3, 0x4A),
        "negative": (0xDC, 0x26, 0x26), "on_primary": (0xFF, 0xFF, 0xFF),
        "display": "Segoe UI", "body": "Segoe UI", "mono": "Consolas",
    },
}

# Domain detection: subject keywords -> palette key. Topic drives the visual
# identity (tech vs sports vs space must feel different).
_DOMAIN_RULES: list[tuple[str, tuple[str, ...]]] = [
    ("tech", ("artificial intelligence", "ai ", " ai", "machine learning", "neural",
              "software", "computer", "code", "chatbot", "assistant", "tech",
              "robot", "algorithm", "cloud", "app", "developer", "data science",
              "llm", "model", "programming", "cyber", "digital", "platform")),
    ("space", ("black hole", "space", "astronomy", "universe", "galaxy", "planet",
               "star", "cosmos", "nasa", "mars", "astrophysics", "nebula",
               "event horizon", "cosmolog")),
    ("energy", ("renewable", "energy", "solar", "wind", "power", "climate",
                "carbon", "environment", "sustainab", "grid", "electric",
                "emission", "greenhouse", "clean energy", "turbine", "panel")),
    ("sports", ("football", "soccer", "messi", "ronaldo", "nba", "cricket",
                "olympics", "tennis", "athlete", "sport", "team", "league",
                "world cup", "basketball", "baseball", "f1", "formula one")),
    ("finance", ("budget", "finance", "investment", "stock", "banking",
                 "financial", "economy", "tax", "portfolio", "market", "crypto",
                 "money", "savings", "interest")),
    ("product", ("startup", "pitch", "business", "company", "launch", "product",
                 "investor", "funding", "revenue", "growth", "market",
                 "strategy", "venture")),
    ("education", ("study guide", "course", "learn", "lesson", "teaching",
                   "exam", "classroom", "tutorial", "curriculum", "school",
                   "study notes")),
    ("academic", ("history", "science", "philosophy", "economics", "biology",
                  "chemistry", "physics", "research", "literature", "theory",
                  "essay", "paper", "study")),
]


def detect_palette(subject: str) -> str:
    low = (" " + (subject or "").lower() + " ").replace("_", " ")
    for key, words in _DOMAIN_RULES:
        for w in words:
            if w in low:
                return key
    return "neutral"


# ── typography roles ─────────────────────────────────────────────────────────
@dataclass
class TypeScale:
    display: float = 50.0   # hero titles
    title: float = 27.0     # slide titles
    subtitle: float = 16.0
    section: float = 34.0
    kicker: float = 10.5    # small caps kickers
    heading: float = 16.0   # panel headings
    body: float = 13.5      # body text
    stat: float = 42.0      # big numbers
    label: float = 10.0     # caps labels
    caption: float = 9.5
    footnote: float = 8.0
    code: float = 12.0


def px(color: tuple[int, int, int]) -> RGBColor:
    return RGBColor(color[0], color[1], color[2])


def lighter(color: tuple[int, int, int], factor: float = 0.88) -> tuple[int, int, int]:
    """Blend toward white — muted surface tints derived from a single accent."""
    return tuple(int(c + (255 - c) * factor) for c in color)


def darker(color: tuple[int, int, int], factor: float = 0.82) -> tuple[int, int, int]:
    """Blend toward black."""
    return tuple(int(c * factor) for c in color)


# ── Canvas: one deck's design tokens + geometry helpers ──────────────────────
@dataclass
class Deck:
    prs: object
    palette: dict[str, tuple[int, int, int]] = field(default_factory=lambda: PALETTES["neutral"])
    palette_key: str = "neutral"
    scale: TypeScale = field(default_factory=TypeScale)
    display_font: str = "Segoe UI"
    body_font: str = "Segoe UI"
    mono_font: str = "Consolas"
    deck_title: str = ""
    footer_text: str = ""

    @property
    def dark(self) -> bool:
        bg = self.palette["bg"]
        return (bg[0] * 299 + bg[1] * 587 + bg[2] * 114) / 1000 < 130

    def text_color_on(self, bg: tuple[int, int, int]) -> tuple[int, int, int]:
        lum = (bg[0] * 299 + bg[1] * 587 + bg[2] * 114) / 1000
        return (0x1A, 0x1A, 0x1A) if lum > 150 else (0xFF, 0xFF, 0xFF)


def estimate_text_lines(text: str, width_in: float, font_pt: float) -> int:
    """Rough line-count estimate for overflow pre-checks (design-time guard)."""
    if not text:
        return 0
    avg_char_w_in = (font_pt / 72.0) * 0.52
    if avg_char_w_in <= 0:
        return 1
    per_line = max(1, int(width_in / avg_char_w_in))
    lines = 0
    for para in text.split("\n"):
        if not para:
            lines += 1
            continue
        lines += max(1, math.ceil(len(para) / per_line))
    return lines


def estimate_text_height(text: str, width_in: float, font_pt: float,
                         line_gap: float = 1.24) -> float:
    lines = estimate_text_lines(text, width_in, font_pt)
    return lines * (font_pt / 72.0) * line_gap


def in_pt(value_in: float) -> float:
    return value_in * 72.0


def pt_in(value_pt: float) -> float:
    return value_pt / 72.0
