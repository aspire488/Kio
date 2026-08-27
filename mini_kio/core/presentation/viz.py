"""
viz.py — Real PowerPoint charts + diagram primitives
=====================================================

Charts are native PPT chart parts (bar / horizontal bar / line / area /
donut) created through python-pptx's chart API — real, editable charts with
labels, readable scales and restrained styling — NOT pictures of charts.

Diagram primitives (layered containers, node-connector pipelines) are drawn
with real shapes + connectors + arrowheads, and are composed by the
archetype renderers.
"""

from __future__ import annotations

import re
from typing import Any, Optional

from pptx.chart.data import CategoryChartData
from pptx.enum.chart import XL_CHART_TYPE, XL_LEGEND_POSITION
from pptx.enum.text import PP_ALIGN
from pptx.util import Inches, Pt

from mini_kio.core.presentation.design import darker, lighter, px

_NUM_RE = re.compile(r"^-?\d+(?:\.\d+)?$")


def _num(v) -> Optional[float]:
    if v is None:
        return None
    s = str(v).strip().replace(",", "").replace("%", "").replace("$", "")
    if _NUM_RE.match(s):
        try:
            return float(s)
        except ValueError:
            return None
    return None


def _chart_type(kind: str):
    kind = (kind or "bar").lower()
    return {
        "bar": XL_CHART_TYPE.COLUMN_CLUSTERED,
        "hbar": XL_CHART_TYPE.BAR_CLUSTERED,
        "line": XL_CHART_TYPE.LINE_MARKERS,
        "area": XL_CHART_TYPE.AREA,
        "donut": XL_CHART_TYPE.DOUGHNUT,
        "pie": XL_CHART_TYPE.DOUGHNUT,
        "stacked": XL_CHART_TYPE.COLUMN_STACKED,
        "column": XL_CHART_TYPE.COLUMN_CLUSTERED,
    }.get(kind, XL_CHART_TYPE.COLUMN_CLUSTERED)


def add_chart(slide, deck, chart: dict, x, y, w, h) -> Optional[Any]:
    """Add a real, styled native chart to the slide.

    chart contract: {"type", "title", "unit", "source", "labels": [...],
    "series": [{"name", "values"}], "sort"}
    """
    labels = list(chart.get("labels") or [])
    series = list(chart.get("series") or [])
    if not labels or not series:
        return None
    ctype = _chart_type(chart.get("type", "bar"))
    chart_data = CategoryChartData()
    chart_data.categories = [str(l) for l in labels]
    for s in series:
        vals = [_num(v) for v in (s.get("values") or [])]
        chart_data.add_series(str(s.get("name") or "Series"), vals)
    try:
        gf = slide.shapes.add_chart(ctype, Inches(x), Inches(y), Inches(w), Inches(h), chart_data)
    except Exception as exc:  # noqa: BLE001
        return None
    chart = gf.chart
    if chart.has_title:
        chart.chart_title.text_frame.text = str(chart.get("title") or "")
    elif chart.get("title"):
        try:
            chart.has_title = True
            chart.chart_title.text_frame.text = str(chart.get("title"))
        except Exception:  # noqa: BLE001
            pass
    # restrained styling
    try:
        plot = chart.plots[0]
        if ctype in (XL_CHART_TYPE.COLUMN_CLUSTERED, XL_CHART_TYPE.BAR_CLUSTERED,
                     XL_CHART_TYPE.COLUMN_STACKED):
            plot.gap_width = 80
        if ctype == XL_CHART_TYPE.DOUGHNUT:
            plot.gap_width = 60
        if ctype == XL_CHART_TYPE.LINE_MARKERS:
            for s in plot.series:
                s.smooth = False
                s.marker.style = 2  # circle
        # value axis: readable scale, no gridline clutter
        try:
            va = chart.value_axis
            va.has_major_gridlines = False
            va.tick_labels.font.size = Pt(deck.scale.caption)
            va.tick_labels.font.name = deck.body_font
            va.tick_labels.font.color.rgb = px(deck.palette["muted"])
            va.format.line.color.rgb = px(lighter(deck.palette["ink"], 0.75))
            if chart.get("unit"):
                va.tick_labels.number_format = chart.get("unit")
        except Exception:  # noqa: BLE001
            pass
        try:
            ca = chart.category_axis
            ca.tick_labels.font.size = Pt(deck.scale.caption)
            ca.tick_labels.font.name = deck.body_font
            ca.tick_labels.font.color.rgb = px(deck.palette["muted"])
            ca.format.line.color.rgb = px(lighter(deck.palette["ink"], 0.75))
        except Exception:  # noqa: BLE001
            pass
    except Exception:  # noqa: BLE001
        pass
    # series fills from the palette
    palette_colors = [deck.palette["secondary"], deck.palette["accent"],
                      deck.palette["primary"], deck.palette["positive"],
                      deck.palette["negative"]]
    try:
        for si, s in enumerate(chart.plots[0].series):
            col = palette_colors[si % len(palette_colors)]
            s.format.fill.solid()
            s.format.fill.fore_color.rgb = px(col)
            s.format.line.fill.background()
    except Exception:  # noqa: BLE001
        pass
    try:
        chart.has_legend = len(series) > 1
        if chart.has_legend:
            chart.legend.position = XL_LEGEND_POSITION.BOTTOM
            chart.legend.include_in_layout = False
            chart.legend.font.size = Pt(deck.scale.caption)
            chart.legend.font.name = deck.body_font
    except Exception:  # noqa: BLE001
        pass
    # data labels for single-series charts (readable numbers)
    try:
        if len(series) == 1 and ctype != XL_CHART_TYPE.AREA:
            plot = chart.plots[0]
            plot.has_data_labels = True
            dl = plot.data_labels
            dl.number_format = chart.get("unit") or "General"
            dl.font.size = Pt(deck.scale.caption + 0.5)
            dl.font.bold = True
            dl.font.color.rgb = px(deck.palette["ink"])
            dl.position = 4  # outside end
    except Exception:  # noqa: BLE001
        pass
    return gf


def add_chart_from_pairs(slide, deck, pairs, x, y, w, h, *, unit="0.0\"\"",
                         source="", title="", kind="bar"):
    """Chart from [(label, value), ...] pairs — used by the deterministic path."""
    labels = [str(p[0]) for p in pairs]
    values = [_num(p[1]) for p in pairs]
    chart = {
        "type": kind, "labels": labels,
        "series": [{"name": "Value", "values": values}],
        "source": source, "title": title, "unit": unit,
    }
    return add_chart(slide, deck, chart, x, y, w, h)
