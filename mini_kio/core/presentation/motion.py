"""
motion.py — OOXML transitions, entrance animations, deck theme
===============================================================

python-pptx has no API for transitions or animations, so both are written
directly into the slide XML (the same shapes PowerPoint itself produces):

  - transitions: <p:transition> (fade / push / morph) on individual slides
  - animations:  <p:timing> entrance sequences (click-to-reveal fades) so
    diagrams and timelines build step by step — subtle, professional motion

Both are injected as raw well-formed XML and validated by opening the deck in
the real PowerPoint application (COM) during the verify pass; any invalid
combination is silently replaced rather than risking a repair prompt.

The deck theme (colors + fonts) is also patched here so charts/tables pick up
the palette automatically.
"""

from __future__ import annotations

import logging

from lxml import etree
from pptx.opc.constants import RELATIONSHIP_TYPE as RT
from pptx.oxml.ns import qn

from mini_kio.core.presentation.design import SLIDE_H_IN, SLIDE_W_IN, px

logger = logging.getLogger("mini_kio.core.presentation.motion")

_P_NS = "http://schemas.openxmlformats.org/presentationml/2006/main"
_A_NS = "http://schemas.openxmlformats.org/drawingml/2006/main"
_P14_NS = "http://schemas.microsoft.com/office/powerpoint/2010/main"


# ── transitions ──────────────────────────────────────────────────────────────

def add_transition(slide, kind: str = "fade", speed: str = "med") -> None:
    """Inject a slide transition. kind: fade | push | morph (morph needs
    PowerPoint 2019+; validated by the COM pass and replaced on failure)."""
    sld = slide._element
    for existing in sld.findall(qn("p:transition")):
        sld.remove(existing)
    if kind == "push":
        xml = (
            f'<p:transition xmlns:p="{_P_NS}" spd="{speed}">'
            '<p:push dir="l"/>'
            "</p:transition>"
        )
    elif kind == "morph":
        xml = (
            f'<p:transition xmlns:p="{_P_NS}" xmlns:p14="{_P14_NS}" spd="{speed}" p14:dur="400">'
            "<p:morph>"
            '<p:extLst><p:ext uri="{D6F2F2B4-31C8-4E3E-8B46-5C0A5E4B1F2E}">'
            '<p14:morph option="byObject"/>'
            "</p:ext></p:extLst>"
            "</p:morph>"
            "</p:transition>"
        )
    else:
        xml = (
            f'<p:transition xmlns:p="{_P_NS}" spd="{speed}">'
            "<p:fade/>"
            "</p:transition>"
        )
    try:
        sld.append(etree.fromstring(xml))
    except Exception as exc:  # noqa: BLE001
        logger.debug("transition injection failed: %s", exc)


def _fade_par(counter, shape_id):
    """One click-to-reveal fade effect for a shape. Returns (xml, next_id)."""
    c = counter
    xml = (
        "<p:par>"
        f'<p:cTn id="{c}" fill="hold">'
        '<p:stCondLst><p:cond delay="indefinite"/></p:stCondLst>'
        "<p:childTnLst><p:par>"
        f'<p:cTn id="{c + 1}" presetID="10" presetClass="entr" presetSubtype="0" '
        'fill="hold" nodeType="clickEffect">'
        '<p:stCondLst><p:cond delay="0"/></p:stCondLst>'
        "<p:childTnLst>"
        "<p:set>"
        "<p:cBhvr>"
        f'<p:cTn id="{c + 2}" dur="1" fill="hold">'
        '<p:stCondLst><p:cond delay="0"/></p:stCondLst>'
        "</p:cTn>"
        "</p:cBhvr>"
        '<p:to><p:stVal val="visible"/></p:to>'
        "</p:set>"
        '<p:animEffect transition="in" filter="fade">'
        "<p:cBhvr>"
        f'<p:cTn id="{c + 3}" dur="500"/>'
        f'<p:tgtEl><p:spTgt spid="{shape_id}"/></p:tgtEl>'
        "</p:cBhvr>"
        "</p:animEffect>"
        "</p:childTnLst>"
        "</p:cTn>"
        "</p:par></p:childTnLst>"
        "</p:cTn>"
        "</p:par>"
    )
    return xml, c + 4


def add_entrance_sequence(slide, shape_ids, one_click: bool = False) -> None:
    """Reveal shapes one click at a time (subtle fade entrance).

    shape_ids: ordered shape ids to animate. one_click: reveal them all on
    the first click instead of one per click.
    """
    if not shape_ids:
        return
    sld = slide._element
    for existing in sld.findall(qn("p:timing")):
        sld.remove(existing)
    counter = 1
    pars = []
    if one_click:
        # single click-effect targeting all shapes: each target gets its own
        # animEffect inside ONE clickEffect node.
        effects = []
        for sid in shape_ids:
            c = counter
            effects.append(
                '<p:animEffect transition="in" filter="fade">'
                "<p:cBhvr>"
                f'<p:cTn id="{c}" dur="500"/>'
                f'<p:tgtEl><p:spTgt spid="{sid}"/></p:tgtEl>'
                "</p:cBhvr>"
                "</p:animEffect>"
            )
            counter += 1
        set_vis = "".join(
            "<p:set><p:cBhvr>"
            f'<p:cTn id="{c}" dur="1" fill="hold">'
            '<p:stCondLst><p:cond delay="0"/></p:stCondLst>'
            "</p:cTn></p:cBhvr>"
            '<p:to><p:stVal val="visible"/></p:to>'
            "</p:set>" for c in range(counter, counter + len(shape_ids))
        )
        counter += len(shape_ids)
        xml_par = (
            "<p:par>"
            f'<p:cTn id="{counter}" fill="hold">'
            '<p:stCondLst><p:cond delay="indefinite"/></p:stCondLst>'
            "<p:childTnLst><p:par>"
            f'<p:cTn id="{counter + 1}" presetID="10" presetClass="entr" '
            'presetSubtype="0" fill="hold" nodeType="clickEffect">'
            '<p:stCondLst><p:cond delay="0"/></p:stCondLst>'
            f"<p:childTnLst>{set_vis}{''.join(effects)}</p:childTnLst>"
            "</p:cTn>"
            "</p:par></p:childTnLst>"
            "</p:cTn>"
            "</p:par>"
        )
        pars.append(xml_par)
    else:
        for sid in shape_ids:
            xml_par, counter = _fade_par(counter, sid)
            pars.append(xml_par)
    xml = (
        f'<p:timing xmlns:p="{_P_NS}" xmlns:a="{_A_NS}">'
        "<p:tnLst><p:par>"
        '<p:cTn id="1" dur="indefinite" restart="never" nodeType="tmRoot">'
        "<p:childTnLst><p:seq concurrent=\"1\" nextAc=\"seek\">"
        '<p:cTn id="2" dur="indefinite" nodeType="mainSeq">'
        f"<p:childTnLst>{''.join(pars)}</p:childTnLst>"
        "</p:cTn></p:seq></p:childTnLst></p:cTn></p:par></p:tnLst>"
        "</p:timing>"
    )
    try:
        sld.append(etree.fromstring(xml))
    except Exception as exc:  # noqa: BLE001
        logger.debug("animation injection failed: %s", exc)


def collect_animation_shapes(slide, deck):
    """Shapes eligible for entrance animation, in z-order.

    Excludes full-bleed backgrounds, footers, slide numbers, and connectors
    (a timeline's connecting line must stay static).
    """
    from pptx.enum.shapes import MSO_SHAPE_TYPE
    out = []
    for shp in slide.shapes:
        try:
            if shp.shape_type == MSO_SHAPE_TYPE.LINE:
                continue
            if shp.shape_type == MSO_SHAPE_TYPE.GROUP:
                continue
            left = shp.left / 914400.0
            top = shp.top / 914400.0
            w = shp.width / 914400.0
            h = shp.height / 914400.0
            # footer row / slide number
            if top > SLIDE_H_IN - 0.5:
                continue
            # full-bleed background
            if w > SLIDE_W_IN * 0.9 and h > SLIDE_H_IN * 0.9:
                continue
            # thin edge bands (full-width accent bars)
            if w > SLIDE_W_IN * 0.9 and h < 0.25:
                continue
            if h > SLIDE_H_IN * 0.9 and w < 0.25:
                continue
            out.append(shp.shape_id)
        except Exception:  # noqa: BLE001
            continue
    return out


# ── theme (deck-wide colors + fonts on the master) ───────────────────────────

def _scheme_set(theme, tag, rgb):
    clr = theme.find(qn("a:clrScheme"))
    if clr is None:
        return
    el = clr.find(qn(f"a:{tag}"))
    if el is None:
        return
    for child in list(el):
        el.remove(child)
    srgb = el.makeelement(qn("a:srgbClr"), {"val": "%02X%02X%02X" % rgb})
    el.append(srgb)


def apply_theme(prs, deck) -> None:
    """Patch the presentation theme so charts/tables inherit deck colors+fonts."""
    try:
        master = prs.slide_masters[0]
        theme_part = master.part.part_related_by(RT.THEME)
        theme = theme_part.theme_element
    except Exception as exc:  # noqa: BLE001
        logger.debug("theme patch skipped: %s", exc)
        return
    p = deck.palette
    _scheme_set(theme, "dk1", p["ink"])
    _scheme_set(theme, "lt1", p["bg"])
    _scheme_set(theme, "dk2", p["primary"])
    _scheme_set(theme, "lt2", tuple(min(255, int(c + (255 - c) * 0.9)) for c in p["primary"]))
    _scheme_set(theme, "accent1", p["primary"])
    _scheme_set(theme, "accent2", p["secondary"])
    _scheme_set(theme, "accent3", p["accent"])
    _scheme_set(theme, "accent4", p["positive"])
    _scheme_set(theme, "accent5", p["negative"])
    _scheme_set(theme, "accent6", p["secondary"])
    _scheme_set(theme, "hlink", p["accent"])
    _scheme_set(theme, "folHlink", p["secondary"])
    try:
        font_scheme = theme.find(qn("a:fontScheme"))
        major = font_scheme.find(qn("a:majorFont"))
        minor = font_scheme.find(qn("a:minorFont"))
        for latin in major.findall(qn("a:latin")):
            latin.set("typeface", deck.display_font)
        for latin in minor.findall(qn("a:latin")):
            latin.set("typeface", deck.body_font)
    except Exception as exc:  # noqa: BLE001
        logger.debug("font theme patch skipped: %s", exc)
