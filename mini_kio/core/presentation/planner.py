"""
planner.py — Presentation planning stage
========================================

The deck is planned BEFORE it is drawn. The pipeline is:

    request → research → narrative plan → slide-purpose plan →
    visual-grammar selection → asset plan → (render) → (validate) → (repair)

plan_with_llm() asks the LLM for a COMPACT structured JSON deck plan
(archetype per slide, statistics with sources, chart data, image queries,
speaker notes). The contract is deliberately terse: providers in the KIO
chain cap output at ~1024 tokens, so every token counts and optional keys
are omitted unless a slide needs them. plan_deterministic() is the no-LLM
fallback: it still applies semantic archetype selection so even the fallback
is a designed deck, never a text dump.
"""

from __future__ import annotations

import json
import logging
import re
from dataclasses import dataclass, field
from typing import Any, Optional

from mini_kio.core.presentation.design import detect_palette

logger = logging.getLogger("mini_kio.core.presentation.planner")

# archetypes the LLM may choose, with the semantic trigger it must justify
_ARCHETYPE_DOC = """archetype ∈ {
  title_hero, section_divider, agenda, statement, image_narrative,
  comparison_2col, comparison_3col, metric_cards, statistics, timeline,
  roadmap, process, funnel, architecture_layered, architecture_system,
  data_flow, cycle, hierarchy, before_after, pros_cons, table, chart,
  quote, case_study, code, conclusion, references, credits
}
Choose by SEMANTIC CONTENT, for example:
  "how data moves through an assistant" -> data_flow
  "compare X and Y"                      -> comparison_2col (or 3col)
  "history of X" / chronological         -> timeline
  "AI architecture" / layered stack      -> architecture_layered
  "X vs Y facts and figures"             -> statistics + chart
  "solar vs wind"                        -> comparison_2col + statistics
  a striking claim                       -> statement
  a list of KPIs                         -> metric_cards
  pros and cons                          -> pros_cons
  before and after                       -> before_after
  a table of facts                       -> table
  milestones with dates                  -> roadmap (or timeline)
  an anecdote / study                    -> case_study
  a quotation                            -> quote
  steps in order                         -> process
  a funnel of narrowing stages           -> funnel
  a repeating loop                       -> cycle
  a hierarchy of components              -> hierarchy
  a system of connected parts            -> architecture_system
  code / API / command examples          -> code"""


@dataclass
class SlideSpec:
    archetype: str = "standard"
    kicker: str = ""
    title: str = ""
    subtitle_text: str = ""
    body: list[str] = field(default_factory=list)
    columns: list[list[str]] = field(default_factory=list)
    column_headers: list[str] = field(default_factory=list)
    stat: Optional[dict] = None
    stats: Optional[list] = None
    chart: Optional[dict] = None
    table: Optional[list] = None
    image: Optional[dict] = None
    quote: str = ""
    quote_attr: str = ""
    steps: Optional[list] = None
    layers: Optional[list] = None
    nodes: Optional[list] = None
    timeline: Optional[list] = None
    code: str = ""
    code_lang: str = ""
    notes: str = ""
    animation: str = ""          # "" | "sequence"
    section_number: Optional[int] = None
    section_label: str = ""


@dataclass
class DeckPlan:
    topic: str = ""
    subtitle: str = ""
    palette_key: str = "neutral"
    slides: list[SlideSpec] = field(default_factory=list)
    references: list[str] = field(default_factory=list)
    credits_rows: list[list[str]] = field(default_factory=list)


# ── research ─────────────────────────────────────────────────────────────────

def research_facts(prompt: str) -> str:
    """Retrieved facts for grounding (canonical KIO research chain)."""
    low = (prompt or "").lower()
    if re.search(r"\bkio\b", low):
        return ""
    try:
        from mini_kio.knowledge.retrieval_router import KnowledgeRouter
        router = KnowledgeRouter()
        result = router.route_for_topic(prompt, mode="short")
        if isinstance(result, tuple):
            multi, _plain = result
        else:
            multi = result
        if multi and getattr(multi, "sources", None):
            snippets = [
                str(getattr(s, "content", "") or "").strip()
                for s in multi.sources if getattr(s, "content", None)
            ]
            snippets = [s[:500] for s in snippets if s]
            if snippets:
                return "\n".join(f"- {s}" for s in snippets[:4])
    except Exception as exc:  # noqa: BLE001
        logger.debug("research unavailable: %s", exc)
    return ""


# ── LLM structured plan ──────────────────────────────────────────────────────
# Compact contract: short keys, optional keys omitted unless needed. Must fit
# comfortably inside the ~1024 output tokens the provider chain allows.

_PLAN_SYSTEM = """You are a senior presentation designer. Plan a professional
PowerPoint deck. Return ONLY a single JSON object — no markdown fences, no
comments, no prose outside the JSON.

{archetype_doc}

Rules (STRICT):
- 7 to 10 slides total. Quality over quantity, no filler.
- Vary the archetypes; never more than 2 slides with the same one.
- Every statistic MUST come from the RETRIEVED FACTS and MUST carry its
  source. Never invent numbers, quotes or sources. If the facts contain no
  numbers, use qualitative content and omit stat/chart.
- Keep it COMPACT: bullets <= 8 words each, <= 5 per slide; notes <= 25
  words; titles <= 7 words. Omit every optional key a slide does not need.
- image: only when an image materially strengthens the story (hero for the
  opening concept, side for narrative, portrait for people). Give a short
  Wikimedia Commons search query.
- animation: set "an" to "sequence" ONLY for diagrams/timelines/process/
  architecture slides (step-by-step reveal); omit otherwise.
- The topic drives the deck: sports feels like sports, technical feels
  technical, science feels like science.
- Group slides into 2-3 sections with short labels like "01 The Problem".

JSON SCHEMA (use the short keys exactly as given):
{"topic": str, "subtitle": str, "references": [str],
 "sections": [{"l": str, "s": [slide, ...]}, ...]}

slide = {"a": "archetype", "t": "Title", "k": "kicker", "b": [str],
  "n": "notes", "an": "sequence"}

Optional keys (omit unless needed):
  stat: {"v": "92%", "l": "label", "s": "source"}
  stats: [stat, ...]                       (metric cards)
  chart: {"ty": "bar|hbar|line|area|donut", "ti": "title",
          "la": [str], "se": [{"n": "series", "v": [num]}],
          "un": "0%", "src": "source"}     (data only from facts)
  table: [[str]]                           (first row = header)
  image: {"q": "search query", "r": "hero|side|portrait|grid"}
  tl: [["label", "desc"], ...]             (timeline / roadmap)
  steps: [str]                             (process / data_flow / cycle)
  layers: [{"n": "name", "d": "desc"}]     (architecture_layered)
  nodes: [{"n": "name"}]                   (architecture_system / hierarchy)
  cols: [[str], [str]], "ch": ["A", "B"]   (comparison columns + headers)
  quote: str, "qa": "attribution"
  code: str, "cl": "language\""""


def _extract_json(text: str) -> Optional[dict]:
    if not text:
        return None
    t = text.strip()
    t = re.sub(r"^```(?:json)?\s*", "", t)
    t = re.sub(r"\s*```$", "", t)
    start = t.find("{")
    end = t.rfind("}")
    if start == -1 or end <= start:
        return None
    try:
        data = json.loads(t[start:end + 1])
        return data if isinstance(data, dict) else None
    except Exception as exc:  # noqa: BLE001
        logger.debug("plan JSON parse failed: %s", exc)
        return None


def _clean(s: Any, limit: int = 140) -> str:
    if s is None:
        return ""
    t = re.sub(r"[*_`#|]", " ", str(s)).strip()
    t = re.sub(r"\s+", " ", t)
    return t[:limit]


def _clean_list(v: Any, limit: int = 8) -> list[str]:
    if not isinstance(v, list):
        return []
    out = []
    for item in v:
        if item is None:
            continue
        if isinstance(item, (list, tuple)):
            out.append(" ".join(str(x) for x in item if x is not None))
        else:
            out.append(str(item))
        if len(out) >= limit:
            break
    return [_clean(x, 200) for x in out if _clean(x, 200)]


def _g(d, *keys, default=None):
    """Get the first present key from a dict (compact + legacy names)."""
    for k in keys:
        if k in d and d[k] is not None:
            return d[k]
    return default


def _slide_from_dict(d: dict, section_label: str, section_num: int) -> SlideSpec:
    arch = str(_g(d, "a", "archetype", default="standard")).lower().strip()
    if arch not in {
        "title_hero", "section_divider", "agenda", "statement", "image_narrative",
        "comparison_2col", "comparison_3col", "metric_cards", "statistics",
        "timeline", "roadmap", "process", "funnel", "architecture_layered",
        "architecture_system", "data_flow", "cycle", "hierarchy", "before_after",
        "pros_cons", "table", "chart", "quote", "case_study", "code",
        "conclusion", "references", "credits",
    }:
        arch = "standard"
    spec = SlideSpec(
        archetype=arch,
        kicker=_clean(_g(d, "k", "kicker"), 40),
        title=_clean(_g(d, "t", "title"), 80),
        subtitle_text=_clean(_g(d, "subtitle", "sub"), 140),
        body=_clean_list(_g(d, "b", "body"), 8),
        columns=[[_clean(c, 120) for c in row] for row in (_g(d, "cols", "columns") or [])][:3],
        column_headers=_clean_list(_g(d, "ch", "column_headers"), 4),
        quote=_clean(_g(d, "quote"), 220),
        quote_attr=_clean(_g(d, "qa", "quote_attr"), 80),
        code=str(_g(d, "code") or "")[:1200],
        code_lang=_clean(_g(d, "cl", "code_lang"), 20),
        notes=_clean(_g(d, "n", "notes"), 700),
        animation="sequence" if str(_g(d, "an", "animation", default="")) == "sequence" else "",
        section_label=section_label,
        section_number=section_num,
    )
    stat = _g(d, "stat")
    if isinstance(stat, dict):
        spec.stat = {
            "value": _clean(_g(stat, "v", "value"), 24),
            "label": _clean(_g(stat, "l", "label"), 60),
            "source": _clean(_g(stat, "s", "source"), 120),
        }
    stats = _g(d, "stats")
    if isinstance(stats, list):
        spec.stats = []
        for s in stats[:6]:
            if isinstance(s, dict):
                spec.stats.append({
                    "value": _clean(_g(s, "v", "value"), 24),
                    "label": _clean(_g(s, "l", "label"), 60),
                    "source": _clean(_g(s, "s", "source"), 120),
                })
    chart = _g(d, "chart")
    if isinstance(chart, dict) and _g(chart, "la", "labels") and _g(chart, "se", "series"):
        spec.chart = {
            "type": str(_g(chart, "ty", "type", default="bar")),
            "title": _clean(_g(chart, "ti", "title"), 60),
            "labels": [str(x) for x in _g(chart, "la", "labels")][:12],
            "series": [
                {"name": _clean(_g(s, "n", "name"), 30), "values": list(_g(s, "v", "values") or [])}
                for s in _g(chart, "se", "series") if isinstance(s, dict)
            ][:4],
            "unit": str(_g(chart, "un", "unit") or ""),
            "source": _clean(_g(chart, "src", "source"), 140),
        }
    table = _g(d, "table")
    if isinstance(table, list) and table:
        spec.table = [[_clean(c, 60) for c in row] for row in table[:10] if isinstance(row, list)]
    image = _g(d, "image")
    if isinstance(image, dict) and _g(image, "q", "query"):
        role = str(_g(image, "r", "role", default="side"))
        if role not in ("hero", "side", "portrait", "grid"):
            role = "side"
        spec.image = {"query": _clean(_g(image, "q", "query"), 90), "role": role}
    tl = _g(d, "tl", "timeline")
    if isinstance(tl, list):
        spec.timeline = [
            (_clean(p[0], 40), _clean(p[1], 120))
            for p in tl[:6] if isinstance(p, (list, tuple)) and len(p) >= 2
        ]
    steps = _g(d, "steps")
    if isinstance(steps, list):
        spec.steps = _clean_list(steps, 8)
    layers = _g(d, "layers")
    if isinstance(layers, list):
        spec.layers = [
            {"name": _clean(_g(l, "n", "name"), 40), "desc": _clean(_g(l, "d", "desc"), 90)}
            for l in layers[:7] if isinstance(l, dict)
        ]
    nodes = _g(d, "nodes")
    if isinstance(nodes, list):
        spec.nodes = [{"name": _clean(_g(n, "n", "name"), 30)} for n in nodes[:6] if isinstance(n, dict)]
    return spec


def plan_with_llm(subject: str, style: str, facts: str, timeout: float = 75.0) -> Optional[DeckPlan]:
    """Ask the LLM for the full structured deck plan."""
    try:
        from mini_kio.llm.llm_ops import ask_llm_sync
    except Exception:  # noqa: BLE001
        return None
    style_txt = f" Style: {style}." if style else ""
    query = (
        f"Plan a presentation about: {subject}.{style_txt}\n\n"
        f"RETRIEVED FACTS (use only these for statistics):\n{facts or '(no retrieved facts — make the deck qualitative)'}"
    )
    # .replace() (never .format()) — the prompt body contains literal JSON
    # braces that .format() would misread as replacement fields.
    system = _PLAN_SYSTEM.replace("{archetype_doc}", _ARCHETYPE_DOC)
    try:
        reply = ask_llm_sync(query, system_prompt=system, timeout=timeout,
                             max_tokens=1100, task="content")
    except Exception as exc:  # noqa: BLE001
        logger.debug("plan LLM failed: %s", exc)
        return None
    data = _extract_json(reply)
    if not data:
        return None
    sections = data.get("sections")
    if not isinstance(sections, list) or not sections:
        return None
    plan = DeckPlan(
        topic=_clean(_g(data, "topic"), 80) or subject,
        subtitle=_clean(_g(data, "subtitle"), 160),
        palette_key=detect_palette(subject),
    )
    refs = data.get("references")
    if isinstance(refs, list):
        plan.references = _clean_list(refs, 14)
    for si, section in enumerate(sections[:4], start=1):
        if not isinstance(section, dict):
            continue
        label = _clean(_g(section, "l", "label"), 40)
        slides = _g(section, "s", "slides")
        if not isinstance(slides, list):
            continue
        for sd in slides:
            if not isinstance(sd, dict):
                continue
            spec = _slide_from_dict(sd, label, si)
            plan.slides.append(spec)
    if not plan.slides:
        return None
    return plan


# ── deterministic fallback plan ──────────────────────────────────────────────

_DIVIDER_WORDS = (
    "overview", "agenda", "section", "conclusion", "summary", "thanks",
    "thank you", "references", "introduction", "next steps", "recap",
)


def _infer_archetype(stitle: str, bullets: list[str], table_rows: list,
                     has_dates: bool) -> str:
    t = (stitle or "").lower()
    joined = " ".join(bullets).lower()
    if len(bullets) <= 1 and len(t.split()) <= 4 and any(w in t for w in _DIVIDER_WORDS):
        return "section_divider"
    if table_rows:
        return "table"
    if re.search(r"\bvs\.?\b|versus|comparison|compare", t) or re.search(r"\bvs\.?\b|versus", joined):
        return "comparison_2col"
    if has_dates:
        return "timeline"
    if any(w in t for w in ("architecture", "system", "layers", "components", "anatomy")):
        return "architecture_layered"
    if any(w in t for w in ("process", "flow", "pipeline", "stages", "workflow",
                            "how it works", "steps", "lifecycle")):
        return "process"
    if re.search(r"\b(step\s*\d|[1-6][.)])\b", joined):
        return "process"
    if re.match(r"^step\s*\d+", t):
        return "process"
    return "standard"


def parse_seed_slides(raw_content: str) -> list[SlideSpec]:
    """Parse pipeline-generated content into SlideSpecs (markers/headings)."""
    slides: list[SlideSpec] = []
    title = ""
    bullets: list[str] = []
    for line in re.split(r"\r?\n", raw_content or ""):
        line = line.strip()
        if not line:
            continue
        m_marker = re.match(r"^(?:slide|--+)\s*[:—-]?\s*(.+)$", line, re.IGNORECASE)
        if m_marker and len(line) <= 90:
            if title or bullets:
                slides.append(SlideSpec(title=_clean(title, 80), body=bullets))
            title = m_marker.group(1).strip()
            bullets = []
            continue
        if re.fullmatch(r"[-–—=]{3,}", line):
            if title or bullets:
                slides.append(SlideSpec(title=_clean(title, 80), body=bullets))
            title, bullets = "", []
            continue
        m = re.match(r"^[-*•]\s+(.+)$", line)
        if m:
            bullets.append(m.group(1).strip())
            continue
        is_title = (
            len(line) <= 90
            and not line.endswith(".")
            and not re.match(r"^\d+[.)]", line)
            and (line[0].isupper() or line[0].isdigit())
        )
        if is_title and title:
            slides.append(SlideSpec(title=_clean(title, 80), body=bullets))
            title, bullets = line, []
        elif is_title and not title:
            title = line
        else:
            bullets.append(line)
    if title or bullets:
        slides.append(SlideSpec(title=_clean(title, 80), body=bullets))
    return slides


def plan_deterministic(subject: str, seed_content: str, facts: str) -> DeckPlan:
    """No-LLM fallback: semantic archetype assignment over seed content.

    Ensures at least 7 slides for any topic by expanding sparse seed content
    with topic-appropriate structural slides.
    """
    plan = DeckPlan(topic=subject, palette_key=detect_palette(subject))
    parsed = parse_seed_slides(seed_content)
    if not parsed:
        # facts-only deck
        parsed = []
        for chunk in re.split(r"\n(?=[A-Z][^\n]{2,40}\n)", facts or ""):
            lines = [l for l in chunk.splitlines() if l.strip()]
            if lines:
                parsed.append(SlideSpec(title=_clean(lines[0], 80), body=lines[1:8]))

    # ── Ensure minimum slide count ────────────────────────────────────────
    # If the seed content produces fewer than 7 slides, expand with
    # topic-appropriate structural slides so the deck is never a 3-slide
    # demo. Generic structural templates that adapt to the subject.
    if len(parsed) < 7:
        _subj_title = " ".join(
            w.capitalize() for w in subject.split()
        ) or subject
        _structural_slides = [
            SlideSpec(
                archetype="section_divider",
                title="Overview",
                body=[f"Understanding {_subj_title}",
                       "Key themes and significance"],
            ),
            SlideSpec(
                archetype="standard",
                title="Background & Context",
                body=[
                    f"Historical context of {_subj_title}",
                    "Why this topic matters today",
                    "Current state of the field",
                ],
            ),
            SlideSpec(
                archetype="standard",
                title="Core Concepts",
                body=[
                    "Fundamental principles and definitions",
                    "Key components and their relationships",
                    "Important terminology",
                ],
            ),
            SlideSpec(
                archetype="standard",
                title="How It Works",
                body=[
                    "Mechanism or process overview",
                    "Key enabling factors",
                    "Technical foundations",
                ],
            ),
            SlideSpec(
                archetype="standard",
                title="Applications & Use Cases",
                body=[
                    "Real-world applications",
                    "Industry examples",
                    "Practical implications",
                ],
            ),
            SlideSpec(
                archetype="comparison_2col",
                title="Benefits vs Challenges",
                column_headers=["Benefits", "Challenges"],
                columns=[
                    ["Drives innovation", "Enables efficiency",
                     "Opens new possibilities"],
                    ["Complexity and cost", "Ethical considerations",
                     "Implementation barriers"],
                ],
            ),
            SlideSpec(
                archetype="standard",
                title="Future Directions",
                body=[
                    "Emerging trends and developments",
                    "Expected advancements",
                    "Opportunities ahead",
                ],
            ),
            SlideSpec(
                archetype="conclusion",
                title="Conclusion & Key Takeaways",
                body=[
                    "Summary of main points",
                    "Action items and next steps",
                    "Further reading and resources",
                ],
            ),
        ]
        # Merge: keep existing slides, add structural ones to reach 7+
        existing_titles = {s.title.lower() for s in parsed}
        for sl in _structural_slides:
            if len(parsed) >= 7:
                break
            if sl.title.lower() not in existing_titles:
                parsed.append(sl)

    for spec in parsed:
        body = spec.body or []
        table_rows = [
            re.split(r"\s*\|\s*", b.strip().strip("|")) for b in body if "|" in b
        ]
        table_rows = [r for r in table_rows if len(r) >= 2]
        has_dates = any(
            re.search(r"\b(19|20)\d{2}\b|\b(Jan|Feb|Mar|Apr|May|Jun|Jul|Aug|Sep|Oct|Nov|Dec)", b)
            for b in body
        )
        spec.archetype = _infer_archetype(spec.title, body, table_rows, has_dates)
        if spec.archetype == "table" and table_rows:
            spec.table = table_rows[:10]
            spec.body = [b for b in body if "|" not in b]
        elif spec.archetype == "comparison_2col":
            headers = [x.strip() for x in re.split(r"\s+(?:vs\.?|versus)\s+", spec.title, flags=re.IGNORECASE)]
            if len(headers) == 2:
                spec.column_headers = headers
            a, b = [], []
            for line in body:
                parts = re.split(r"\s*\|\s*|\s+vs\.?\s+|\s+versus\s+", line, maxsplit=1)
                if len(parts) == 2:
                    a.append(parts[0].strip())
                    b.append(parts[1].strip())
                else:
                    a.append(line)
            spec.columns = [a[:6], b[:6]]
            spec.body = []
        elif spec.archetype == "process":
            steps = []
            rest = []
            for b in body:
                m = re.match(r"^(?:step\s*\d+[.:]?\s*|\d+[.)]\s*)(.+)$", b.strip())
                if m:
                    steps.append(m.group(1).strip())
                else:
                    rest.append(b)
            spec.steps = steps or body[:6]
            spec.body = rest
        elif spec.archetype == "timeline":
            tl = []
            for b in body:
                m = re.match(r"^([\w\s]+?)[:\-]\s*(.+)$", b)
                if m and len(m.group(1).split()) <= 6:
                    tl.append((m.group(1).strip(), m.group(2).strip()))
            if tl:
                spec.timeline = tl[:6]
                spec.body = []
        elif spec.archetype == "architecture_layered":
            layers = []
            for b in body:
                parts = re.split(r"\s*[:–—-]\s*", b, maxsplit=1)
                layers.append({"name": parts[0].strip(), "desc": parts[1].strip() if len(parts) > 1 else ""})
            if layers:
                spec.layers = layers[:6]
                spec.body = []
        # spec.notes stays empty here: the engine builds notes from the real
        # slide content (title + points verbatim) plus presenter guidance.
    plan.slides = parsed
    return plan


def build_plan(subject: str, style: str, seed_content: str, facts: str,
               hermetic: bool = False) -> DeckPlan:
    """Plan the deck: LLM-structured plan when possible, deterministic fallback."""
    if not hermetic:
        plan = plan_with_llm(subject, style, facts)
        if plan is not None:
            return plan
    return plan_deterministic(subject, seed_content, facts)
