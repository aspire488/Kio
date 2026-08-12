"""
artifact_operator.py — Generic Artifact Creation Operator (capability-quality)

ONE canonical owner for creating real, meaningful artifacts of the requested
FORMAT WITHOUT external dependencies (stdlib zipfile + XML escaping, exactly
like document_operator.py). The format is resolved from the ARTIFACT KIND the
user asked for — never from per-application branches:

    essay/report/comparison/poem/...  -> .docx  (opens in Word)
    spreadsheet/budget/table/data     -> .xlsx  (opens in Excel)
    presentation/slides/deck          -> .pptx  (opens in PowerPoint)

The application that opens each artifact is the OS default handler for the
extension — the artifact layer produces the real file; opening/verification
are generic.

Responsibilities:
  1. Map artifact kind -> OOXML format (docx / xlsx / pptx).
  2. Generate a meaningful filename from subject + artifact kind
     ("messi and ronaldo" + comparison -> Messi_And_Ronaldo_Comparison.docx,
      "black holes" + presentation -> Black_Holes_Presentation.pptx,
      "monthly budget" + spreadsheet -> Monthly_Budget_Spreadsheet.xlsx).
  3. Lay out structured content appropriate to the format:
       docx: title, headings, paragraphs, bullets
       xlsx: real header row + typed data rows
       pptx: title slide + content slides with bullets
  4. Save to the user's Documents folder, collision-safe.
  5. Verify the real artifact (exists, valid ZIP, expected OOXML parts).
  6. Open the artifact in its default application.

The content-generation layer (LLM) and this execution layer are SEPARATE:
this module never calls an LLM.
"""

from __future__ import annotations

import logging
import os
import re
import zipfile
from pathlib import Path
from typing import Any, Optional
from xml.sax.saxutils import escape

from mini_kio.core.document_operator import (
    _ARTIFACT_SUFFIX,
    _parse_content_blocks,
    _sanitize_markdown,
    build_docx,
    documents_dir,
    generate_document_filename,
    verify_docx,
)

logger = logging.getLogger("mini_kio.core.artifact_operator")

# ── artifact kind -> OOXML format family ─────────────────────────────────────
# Document-family kinds fall through to the .docx branch; only the two
# non-docx families need explicit membership (anything else IS a document).
_SPREADSHEET_KINDS = frozenset({
    "spreadsheet", "sheet", "excel", "xlsx", "budget", "table", "data",
    "ledger", "inventory", "tracker", "timetable", "roster", "schedule",
    "dataset", "plan",
})

# Source-code kinds: written as plain text files with language-appropriate
# extensions (NOT OOXML) so they open in the user's editor.
_CODE_KINDS = frozenset({"code", "program", "script"})
# language -> file extension (generic, never per-app branches).
_CODE_EXTENSIONS = {
    "python": ".py", "py": ".py", "javascript": ".js", "js": ".js",
    "typescript": ".ts", "ts": ".ts", "java": ".java",
    "c++": ".cpp", "c#": ".cs", "cs": ".cs", "go": ".go",
    "rust": ".rs", "ruby": ".rb", "php": ".php", "bash": ".sh",
    "powershell": ".ps1", "html": ".html", "css": ".css", "sql": ".sql",
}
_PRESENTATION_KINDS = frozenset({
    "presentation", "slides", "slide", "deck", "ppt", "pptx", "powerpoint",
    "slideshow", "talk", "slide deck",
})

# Extra suffix mappings for the new families (merged into the docx suffix map).
_ARTIFACT_SUFFIX_EXTRA = {
    "spreadsheet": "Spreadsheet",
    "budget": "Budget",
    "table": "Table",
    "data": "Data",
    "sheet": "Sheet",
    "presentation": "Presentation",
    "slides": "Slides",
    "deck": "Deck",
    "study guide": "Study_Guide",
    "study-guide": "Study_Guide",
    "notes": "Notes",
    "plan": "Plan",
    "checklist": "Checklist",
    "outline": "Outline",
}


def _escape_xml(text: str) -> str:
    return escape(text or "", entities={'"': "&quot;", "'": "&apos;"})


# ── filename ─────────────────────────────────────────────────────────────────
def artifact_extension(artifact: str, language: str = "") -> str:
    """Resolve the file extension for an artifact kind (canonical, not per-app)."""
    kind = (artifact or "document").lower().strip()
    if kind in _CODE_KINDS:
        return _CODE_EXTENSIONS.get((language or "python").lower().strip(), ".py")
    if kind in _SPREADSHEET_KINDS:
        return ".xlsx"
    if kind in _PRESENTATION_KINDS:
        return ".pptx"
    return ".docx"


def generate_artifact_filename(subject: str, artifact: str = "document", style: str = "") -> str:
    """Meaningful, filesystem-safe filename stem (no extension).

    Dedupes the suffix when the subject already contains it ("budget" +
    budget -> "Budget_Budget.xlsx" is wrong; "Budget_Spreadsheet.xlsx" and
    "Black_Holes_Presentation.pptx" are right).
    """
    kind = (artifact or "document").lower().strip()
    words = re.findall(r"[A-Za-z0-9]+", subject or "")
    title = "_".join(w.capitalize() for w in words) or "Untitled"
    if title.lower() == "untitled":
        return "Untitled_Document"
    suffix = (_ARTIFACT_SUFFIX_EXTRA.get(kind) or "").strip()
    if not suffix:
        suffix = _ARTIFACT_SUFFIX.get(kind, "Overview")
    if suffix and title.lower().endswith(suffix.lower()):
        return title
    return f"{title}_{suffix}" if suffix else title


def _ensure_unique(path: Path) -> Path:
    """Collision-safe path: append (2), (3), ... without overwriting."""
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


# ── .xlsx (real spreadsheet) ─────────────────────────────────────────────────
def _parse_spreadsheet_rows(raw_content: str) -> list[list[str]]:
    """Parse generated content into header + data rows.

    Accepts the LLM contract (tab-separated records) AND markdown tables
    ("| a | b |"). Never dumps a text blob into one cell.
    """
    rows: list[list[str]] = []
    if not raw_content:
        return rows
    for line in re.split(r"\r?\n", raw_content):
        line = line.strip()
        if not line:
            continue
        if line.startswith("|"):
            cells = [c.strip().lstrip("|").rstrip("|") for c in line.split("|")]
            cells = [c for c in cells if c != ""]
            # Skip markdown separator rows (| --- | --- |).
            if cells and all(re.fullmatch(r":?-{2,}:?", c) for c in cells):
                continue
        else:
            cells = [c.strip() for c in line.split("\t") if c.strip()]
        # Guard against a giant single blob: if one "row" is enormous and has
        # no structure, fall back to word tokens? NO — keep the LLM contract;
        # a single long line simply becomes one row.
        if cells:
            rows.append(cells)
    return rows


def _column_letter(idx: int) -> str:
    """1-based index -> Excel column letters (1=A, 27=AA)."""
    letters = ""
    while idx > 0:
        idx, rem = divmod(idx - 1, 26)
        letters = chr(ord("A") + rem) + letters
    return letters


def _cell_xml(ref: str, value: str, header: bool = False) -> str:
    """Write a cell: inline string by default, numeric when clearly numeric.

    header=True applies the bold header style (style index 1) — the first
    row of a real spreadsheet is a readable header, not just another row.
    """
    v = _sanitize_markdown(value)
    style_attr = ' s="1"' if header else ""
    if v == "":
        return f'<c r="{ref}"{style_attr}/>'
    # Numeric detection (int or float, no units).
    if re.fullmatch(r"-?\d+(?:\.\d+)?", v):
        return f'<c r="{ref}"{style_attr}><v>{v}</v></c>'
    return f'<c r="{ref}"{style_attr} t="inlineStr"><is><t>{_escape_xml(v)}</t></is></c>'


def _build_worksheet_xml(rows: list[list[str]]) -> str:
    parts = []
    for r_idx, row in enumerate(rows, start=1):
        header = r_idx == 1
        cells = []
        for c_idx, val in enumerate(row[:128], start=1):  # bounded width
            cells.append(_cell_xml(f"{_column_letter(c_idx)}{r_idx}", val, header=header))
        parts.append(f"<row r=\"{r_idx}\">{''.join(cells)}</row>")
    sheet_data = "".join(parts)
    return (
        '<?xml version="1.0" encoding="UTF-8" standalone="yes"?>'
        '<worksheet xmlns="http://schemas.openxmlformats.org/spreadsheetml/2006/main">'
        f"<sheetData>{sheet_data}</sheetData>"
        "</worksheet>"
    )


_XLSX_CONTENT_TYPES = (
    '<?xml version="1.0" encoding="UTF-8" standalone="yes"?>'
    '<Types xmlns="http://schemas.openxmlformats.org/package/2006/content-types">'
    '<Default Extension="rels" ContentType="application/vnd.openxmlformats-package.relationships+xml"/>'
    '<Default Extension="xml" ContentType="application/xml"/>'
    '<Override PartName="/xl/workbook.xml" ContentType="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet.main+xml"/>'
    '<Override PartName="/xl/worksheets/sheet1.xml" ContentType="application/vnd.openxmlformats-officedocument.spreadsheetml.worksheet+xml"/>'
    '<Override PartName="/xl/styles.xml" ContentType="application/vnd.openxmlformats-officedocument.spreadsheetml.styles+xml"/>'
    "</Types>"
)

_XLSX_RELS = (
    '<?xml version="1.0" encoding="UTF-8" standalone="yes"?>'
    '<Relationships xmlns="http://schemas.openxmlformats.org/package/2006/relationships">'
    '<Relationship Id="rId1" Type="http://schemas.openxmlformats.org/officeDocument/2006/relationships/officeDocument" Target="xl/workbook.xml"/>'
    "</Relationships>"
)

def _sheet_name_from_subject(subject: str, artifact: str = "") -> str:
    """Meaningful Excel sheet name derived from the subject.

    Excel limits: max 31 chars, cannot contain []:*?/ and must not be
    empty. "messi and ronaldo" + comparison -> "Messi_Ronaldo"; the
    artifact word is only appended when the subject is very short and the
    subject does not already name the artifact ("budget" -> "Budget",
    never "Budget_Budget").
    """
    words = re.findall(r"[A-Za-z0-9]+", subject or "")
    base = "_".join(w.capitalize() for w in words)
    if not base:
        base = "Data"
    if len(words) <= 1:
        kind = (artifact or "").lower().strip()
        extra = {
            "budget": "Budget", "table": "Table", "tracker": "Tracker",
            "dataset": "Data", "ledger": "Ledger", "schedule": "Schedule",
        }.get(kind, "")
        if extra and base.lower() != extra.lower():
            base = f"{base}_{extra}"
    clean = re.sub(r"[\\/*?:\[\]]", "_", base)
    return (clean[:31] or "Data")


def _build_workbook_xml(sheet_name: str) -> str:
    return (
        '<?xml version="1.0" encoding="UTF-8" standalone="yes"?>'
        '<workbook xmlns="http://schemas.openxmlformats.org/spreadsheetml/2006/main" '
        'xmlns:r="http://schemas.openxmlformats.org/officeDocument/2006/relationships">'
        f'<sheets><sheet name="{_escape_xml(sheet_name)}" sheetId="1" r:id="rId1"/></sheets>'
        "</workbook>"
    )

_XLSX_WORKBOOK_RELS = (
    '<?xml version="1.0" encoding="UTF-8" standalone="yes"?>'
    '<Relationships xmlns="http://schemas.openxmlformats.org/package/2006/relationships">'
    '<Relationship Id="rId1" Type="http://schemas.openxmlformats.org/officeDocument/2006/relationships/worksheet" Target="worksheets/sheet1.xml"/>'
    '<Relationship Id="rId2" Type="http://schemas.openxmlformats.org/officeDocument/2006/relationships/styles" Target="styles.xml"/>'
    "</Relationships>"
)

# Two cell styles: 0 = normal body, 1 = bold header (used for row 1).
_XLSX_STYLES = (
    '<?xml version="1.0" encoding="UTF-8" standalone="yes"?>'
    '<styleSheet xmlns="http://schemas.openxmlformats.org/spreadsheetml/2006/main">'
    '<fonts count="2"><font><sz val="11"/><name val="Calibri"/></font>'
    '<font><b/><sz val="11"/><name val="Calibri"/></font></fonts>'
    '<fills count="1"><fill><patternFill patternType="none"/></fill></fills>'
    '<borders count="1"><border><left/><right/><top/><bottom/><diagonal/></border></borders>'
    '<cellStyleXfs count="1"><xf numFmtId="0" fontId="0" fillId="0" borderId="0"/></cellStyleXfs>'
    '<cellXfs count="2"><xf numFmtId="0" fontId="0" fillId="0" borderId="0" xfId="0"/>'
    '<xf numFmtId="0" fontId="1" fillId="0" borderId="0" xfId="0" applyFont="1"/></cellXfs>'
    "</styleSheet>"
)


def build_xlsx(path: Path, rows: list[list[str]], sheet_name: str = "Data") -> bool:
    """Write a valid minimal .xlsx to `path`. Returns True on success."""
    try:
        with zipfile.ZipFile(str(path), "w", zipfile.ZIP_DEFLATED) as zf:
            zf.writestr("[Content_Types].xml", _XLSX_CONTENT_TYPES)
            zf.writestr("_rels/.rels", _XLSX_RELS)
            zf.writestr("xl/workbook.xml", _build_workbook_xml(sheet_name))
            zf.writestr("xl/_rels/workbook.xml.rels", _XLSX_WORKBOOK_RELS)
            zf.writestr("xl/styles.xml", _XLSX_STYLES)
            zf.writestr("xl/worksheets/sheet1.xml", _build_worksheet_xml(rows))
        return True
    except Exception as exc:  # noqa: BLE001
        logger.exception("build_xlsx failed for %s: %s", path, exc)
        return False


def verify_xlsx(path: Path) -> dict[str, Any]:
    """Verify a real .xlsx artifact: exists, valid ZIP, sheet has cells."""
    facts: dict[str, Any] = {"exists": False, "valid_zip": False, "row_count": 0, "cell_count": 0}
    try:
        if not path.exists():
            return facts
        facts["exists"] = True
        facts["size_bytes"] = path.stat().st_size
        if not zipfile.is_zipfile(str(path)):
            return facts
        with zipfile.ZipFile(str(path)) as zf:
            if zf.testzip() is not None:
                return facts
            names = set(zf.namelist())
            if "xl/worksheets/sheet1.xml" not in names:
                return facts
            facts["valid_zip"] = True
            sheet = zf.read("xl/worksheets/sheet1.xml").decode("utf-8", errors="replace")
        facts["row_count"] = sheet.count("<row ")
        facts["cell_count"] = sheet.count("<c ")
    except Exception as exc:  # noqa: BLE001
        logger.warning("verify_xlsx failed: %s", exc)
    return facts


# ── .pptx (real presentation) ────────────────────────────────────────────────
def _parse_slides(raw_content: str) -> list[tuple[str, list[str]]]:
    """Parse generated content into (slide_title, [bullet, ...]) slides.

    Contract from the content layer: slide titles are short lines (no terminal
    sentence period); bullet points follow as '- ' / '* ' / '• ' lines. Long
    prose lines become slide bullets. Returns at least one slide.
    """
    slides: list[tuple[str, list[str]]] = []
    title: str = ""
    bullets: list[str] = []
    if not raw_content:
        return slides
    for line in re.split(r"\r?\n", raw_content):
        line = _sanitize_markdown(line).strip()
        if not line:
            continue
        if re.fullmatch(r"[-–—=]{3,}", line):  # slide separator
            if title or bullets:
                slides.append((title or "Untitled Slide", bullets))
            title, bullets = "", []
            continue
        m = re.match(r"^[-*•]\s+(.+)$", line)
        if m:
            bullets.append(m.group(1).strip())
            continue
        # A short line is a new slide title unless it reads like sentence
        # prose: long text, numbered items, or a line ending in a full stop
        # (period = prose; a short question or exclamation "What Are Black
        # Holes?" / "Why It Matters!" is a legitimate slide title).
        is_title = (
            len(line) <= 90
            and not line.endswith(".")
            and not re.match(r"^\d+[.)]", line)
            and (line[0].isupper() or line[0].isdigit())
        )
        if is_title and title:
            slides.append((title, bullets))
            title, bullets = line, []
        elif is_title and not title:
            title = line
        else:
            bullets.append(line)
    if title or bullets:
        slides.append((title or "Untitled Slide", bullets))
    return slides or [("Untitled Slide", [])]


_PPTX_DEFAULT = (
    '<?xml version="1.0" encoding="UTF-8" standalone="yes"?>'
    '<Types xmlns="http://schemas.openxmlformats.org/package/2006/content-types">'
    '<Default Extension="rels" ContentType="application/vnd.openxmlformats-package.relationships+xml"/>'
    '<Default Extension="xml" ContentType="application/xml"/>'
    '<Override PartName="/ppt/presentation.xml" ContentType="application/vnd.openxmlformats-officedocument.presentationml.presentation.main+xml"/>'
    '<Override PartName="/ppt/slideMasters/slideMaster1.xml" ContentType="application/vnd.openxmlformats-officedocument.presentationml.slideMaster+xml"/>'
    '<Override PartName="/ppt/slideLayouts/slideLayout1.xml" ContentType="application/vnd.openxmlformats-officedocument.presentationml.slideLayout+xml"/>'
    '<Override PartName="/ppt/theme/theme1.xml" ContentType="application/vnd.openxmlformats-officedocument.theme+xml"/>'
)


def _pptx_content_types(slide_count: int) -> str:
    overrides = [
        '<Override PartName="/ppt/slides/slide%d.xml" ContentType="application/vnd.openxmlformats-officedocument.presentationml.slide+xml"/>'
        % i
        for i in range(1, slide_count + 1)
    ]
    overrides += [
        '<Override PartName="/ppt/notesSlides/notesSlide%d.xml" ContentType="application/vnd.openxmlformats-officedocument.presentationml.notesSlide+xml"/>'
        % i
        for i in range(1, slide_count + 1)
    ]
    overrides.append(
        '<Override PartName="/ppt/notesMasters/notesMaster1.xml" '
        'ContentType="application/vnd.openxmlformats-officedocument.presentationml.notesMaster+xml"/>'
    )
    return _PPTX_DEFAULT + "".join(overrides) + "</Types>"


_PPTX_RELS = (
    '<?xml version="1.0" encoding="UTF-8" standalone="yes"?>'
    '<Relationships xmlns="http://schemas.openxmlformats.org/package/2006/relationships">'
    '<Relationship Id="rId1" Type="http://schemas.openxmlformats.org/officeDocument/2006/relationships/officeDocument" Target="ppt/presentation.xml"/>'
    "</Relationships>"
)

_PPTX_THEME = (
    '<?xml version="1.0" encoding="UTF-8" standalone="yes"?>'
    '<a:theme xmlns:a="http://schemas.openxmlformats.org/drawingml/2006/main" name="Office">'
    "<a:themeElements>"
    '<a:clrScheme name="Office">'
    '<a:dk1><a:sysClr val="windowText" lastClr="000000"/></a:dk1>'
    '<a:lt1><a:sysClr val="window" lastClr="FFFFFF"/></a:lt1>'
    '<a:dk2><a:srgbClr val="1F497D"/></a:dk2><a:lt2><a:srgbClr val="EEECE1"/></a:lt2>'
    '<a:accent1><a:srgbClr val="4F81BD"/></a:accent1><a:accent2><a:srgbClr val="C0504D"/></a:accent2>'
    '<a:accent3><a:srgbClr val="9BBB59"/></a:accent3><a:accent4><a:srgbClr val="8064A2"/></a:accent4>'
    '<a:accent5><a:srgbClr val="4BACC6"/></a:accent5><a:accent6><a:srgbClr val="F79646"/></a:accent6>'
    '<a:hlink><a:srgbClr val="0000FF"/></a:hlink><a:folHlink><a:srgbClr val="800080"/></a:folHlink>'
    "</a:clrScheme>"
    '<a:fontScheme name="Office"><a:majorFont><a:latin typeface="Calibri"/></a:majorFont>'
    '<a:minorFont><a:latin typeface="Calibri"/></a:minorFont></a:fontScheme>'
    '<a:fmtScheme name="Office">'
    '<a:fillStyleLst><a:solidFill><a:schemeClr val="phClr"/></a:solidFill></a:fillStyleLst>'
    '<a:lnStyleLst><a:ln w="9525" cap="flat" cmpd="sng" algn="ctr"><a:solidFill><a:schemeClr val="phClr"/></a:solidFill>'
    '<a:prstDash val="solid"/></a:ln><a:ln w="25400" cap="flat" cmpd="sng" algn="ctr"><a:solidFill><a:schemeClr val="phClr"/></a:solidFill>'
    '<a:prstDash val="solid"/></a:ln><a:ln w="38100" cap="flat" cmpd="sng" algn="ctr"><a:solidFill><a:schemeClr val="phClr"/></a:solidFill>'
    '<a:prstDash val="solid"/></a:ln></a:lnStyleLst>'
    '<a:effectStyleLst><a:effectStyle><a:effectLst/></a:effectStyle>'
    '<a:effectStyle><a:effectLst/></a:effectStyle><a:effectStyle><a:effectLst/></a:effectStyle></a:effectStyleLst>'
    '<a:bgFillStyleLst><a:solidFill><a:schemeClr val="phClr"/></a:solidFill></a:bgFillStyleLst>'
    "</a:fmtScheme>"
    "</a:themeElements>"
    "</a:theme>"
)

_PPTX_MASTER = (
    '<?xml version="1.0" encoding="UTF-8" standalone="yes"?>'
    '<p:sldMaster xmlns:a="http://schemas.openxmlformats.org/drawingml/2006/main" '
    'xmlns:r="http://schemas.openxmlformats.org/officeDocument/2006/relationships" '
    'xmlns:p="http://schemas.openxmlformats.org/presentationml/2006/main">'
    "<p:cSld><p:spTree>"
    '<p:nvGrpSpPr><p:cNvPr id="1" name=""/><p:cNvGrpSpPr/><p:nvPr/></p:nvGrpSpPr>'
    "<p:grpSpPr/></p:spTree></p:cSld>"
    '<p:clrMap bg1="lt1" tx1="dk1" bg2="lt2" tx2="dk2" accent1="accent1" accent2="accent2" '
    'accent3="accent3" accent4="accent4" accent5="accent5" accent6="accent6" hlink="hlink" folHlink="folHlink"/>'
    '<p:sldLayoutIdLst><p:sldLayoutId id="1" r:id="rId1"/></p:sldLayoutIdLst>'
    "</p:sldMaster>"
)

_PPTX_MASTER_RELS = (
    '<?xml version="1.0" encoding="UTF-8" standalone="yes"?>'
    '<Relationships xmlns="http://schemas.openxmlformats.org/package/2006/relationships">'
    '<Relationship Id="rId1" Type="http://schemas.openxmlformats.org/officeDocument/2006/relationships/slideLayout" Target="../slideLayouts/slideLayout1.xml"/>'
    '<Relationship Id="rId2" Type="http://schemas.openxmlformats.org/officeDocument/2006/relationships/theme" Target="../theme/theme1.xml"/>'
    "</Relationships>"
)

_PPTX_LAYOUT = (
    '<?xml version="1.0" encoding="UTF-8" standalone="yes"?>'
    '<p:sldLayout xmlns:a="http://schemas.openxmlformats.org/drawingml/2006/main" '
    'xmlns:r="http://schemas.openxmlformats.org/officeDocument/2006/relationships" '
    'xmlns:p="http://schemas.openxmlformats.org/presentationml/2006/main" type="blank">'
    '<p:cSld name="Blank"><p:spTree>'
    '<p:nvGrpSpPr><p:cNvPr id="1" name=""/><p:cNvGrpSpPr/><p:nvPr/></p:nvGrpSpPr>'
    "<p:grpSpPr/></p:spTree></p:cSld>"
    '<p:clrMapOvr><a:overrideClrMapping bg1="lt1" tx1="dk1" bg2="lt2" tx2="dk2" '
    'accent1="accent1" accent2="accent2" accent3="accent3" accent4="accent4" '
    'accent5="accent5" accent6="accent6" hlink="hlink" folHlink="folHlink"/></p:clrMapOvr>'
    "</p:sldLayout>"
)

_PPTX_LAYOUT_RELS = (
    '<?xml version="1.0" encoding="UTF-8" standalone="yes"?>'
    '<Relationships xmlns="http://schemas.openxmlformats.org/package/2006/relationships">'
    '<Relationship Id="rId1" Type="http://schemas.openxmlformats.org/officeDocument/2006/relationships/slideMaster" Target="../slideMasters/slideMaster1.xml"/>'
    '<Relationship Id="rId2" Type="http://schemas.openxmlformats.org/officeDocument/2006/relationships/theme" Target="../theme/theme1.xml"/>'
    "</Relationships>"
)

def _slide_rels(slide_index: int) -> str:
    """Per-slide relationships: slide layout + THAT slide's own notes slide.

    Generated per index so slide N links to notesSlideN (never a shared
    notesSlide1), which keeps every slide's speaker notes correct.
    """
    return (
        '<?xml version="1.0" encoding="UTF-8" standalone="yes"?>'
        '<Relationships xmlns="http://schemas.openxmlformats.org/package/2006/relationships">'
        '<Relationship Id="rId1" Type="http://schemas.openxmlformats.org/officeDocument/2006/relationships/slideLayout" Target="../slideLayouts/slideLayout1.xml"/>'
        f'<Relationship Id="rId2" Type="http://schemas.openxmlformats.org/officeDocument/2006/relationships/notesSlide" Target="../notesSlides/notesSlide{slide_index}.xml"/>'
        "</Relationships>"
    )

# Speaker-notes parts: one notesMaster (referenced by every notesSlide) and
# per-slide notesSlides. Optional but native to the presentation format —
# PowerPoint opens decks with or without them.
_NOTES_MASTER = (
    '<?xml version="1.0" encoding="UTF-8" standalone="yes"?>'
    '<p:notesMaster xmlns:a="http://schemas.openxmlformats.org/drawingml/2006/main" '
    'xmlns:r="http://schemas.openxmlformats.org/officeDocument/2006/relationships" '
    'xmlns:p="http://schemas.openxmlformats.org/presentationml/2006/main">'
    '<p:cSld><p:spTree>'
    '<p:nvGrpSpPr><p:cNvPr id="1" name=""/><p:cNvGrpSpPr/><p:nvPr/></p:nvGrpSpPr>'
    "<p:grpSpPr/></p:spTree></p:cSld>"
    '<p:clrMap bg1="lt1" tx1="dk1" bg2="lt2" tx2="dk2" accent1="accent1" accent2="accent2" '
    'accent3="accent3" accent4="accent4" accent5="accent5" accent6="accent6" hlink="hlink" folHlink="folHlink"/>'
    '<p:notesStyle><a:lvl1pPr algn="l"><a:defRPr sz="1400"/></a:lvl1pPr></p:notesStyle>'
    "</p:notesMaster>"
)

_NOTES_MASTER_RELS = (
    '<?xml version="1.0" encoding="UTF-8" standalone="yes"?>'
    '<Relationships xmlns="http://schemas.openxmlformats.org/package/2006/relationships">'
    '<Relationship Id="rId1" Type="http://schemas.openxmlformats.org/officeDocument/2006/relationships/theme" Target="../theme/theme1.xml"/>'
    "</Relationships>"
)

_NOTES_SLIDE = (
    '<?xml version="1.0" encoding="UTF-8" standalone="yes"?>'
    '<p:notes xmlns:a="http://schemas.openxmlformats.org/drawingml/2006/main" '
    'xmlns:r="http://schemas.openxmlformats.org/officeDocument/2006/relationships" '
    'xmlns:p="http://schemas.openxmlformats.org/presentationml/2006/main">'
    '<p:cSld><p:spTree>'
    '<p:nvGrpSpPr><p:cNvPr id="1" name=""/><p:cNvGrpSpPr/><p:nvPr/></p:nvGrpSpPr>'
    "<p:grpSpPr/>"
    '<p:sp><p:nvSpPr><p:cNvPr id="2" name="Notes"/><p:cNvSpPr><a:spLocks noGrp="1"/></p:cNvSpPr><p:nvPr/></p:nvSpPr>'
    '<p:spPr><a:xfrm><a:off x="0" y="0"/><a:ext cx="9144000" cy="6858000"/></a:xfrm>'
    '<a:prstGeom prst="rect"><a:avLst/></a:prstGeom></p:spPr>'
    '<p:txBody><a:bodyPr wrap="square"><a:normAutofit/></a:bodyPr>{body}</p:txBody></p:sp>'
    "</p:spTree></p:cSld>"
    '<p:clrMapOvr><a:overrideClrMapping bg1="lt1" tx1="dk1" bg2="lt2" tx2="dk2" '
    'accent1="accent1" accent2="accent2" accent3="accent3" accent4="accent4" '
    'accent5="accent5" accent6="accent6" hlink="hlink" folHlink="folHlink"/></p:clrMapOvr>'
    "</p:notes>"
)

_NOTES_SLIDE_RELS = (
    '<?xml version="1.0" encoding="UTF-8" standalone="yes"?>'
    '<Relationships xmlns="http://schemas.openxmlformats.org/package/2006/relationships">'
    '<Relationship Id="rId1" Type="http://schemas.openxmlformats.org/officeDocument/2006/relationships/notesMaster" Target="../notesMasters/notesMaster1.xml"/>'
    "</Relationships>"
)


def _notes_body_xml(title: str, bullets: list[str]) -> str:
    """Speaker notes = slide title + the slide's bullet points (always non-
    empty, so PowerPoint never shows a blank notes pane)."""
    paras = []
    if title:
        paras.append(f'<a:p><a:r><a:rPr lang="en-US" sz="1400" b="1"/><a:t>{_escape_xml(title)}</a:t></a:r></a:p>')
    for b in bullets[:10]:
        paras.append(f'<a:p><a:r><a:rPr lang="en-US" sz="1200"/><a:t>{_escape_xml(b)}</a:t></a:r></a:p>')
    if not paras:
        paras.append('<a:p/>')
    return "".join(paras)


def _slide_xml(title: str, bullets: list[str]) -> str:
    title_runs = (
        f'<a:r><a:rPr lang="en-US" sz="4400" b="1"/><a:t>{_escape_xml(title)}</a:t></a:r>'
        if title else ""
    )
    title_par = f"<a:p><a:pPr algn=\"ctr\"/>{title_runs}</a:p>" if title else ""
    bullet_pars = "".join(
        f'<a:p><a:pPr lvl="0"/><a:r><a:rPr lang="en-US" sz="2200"/>'
        f'<a:t>{_escape_xml("• " + b)}</a:t></a:r></a:p>'
        for b in bullets[:12]
    )
    if not bullet_pars:
        bullet_pars = '<a:p/>'
    return (
        '<?xml version="1.0" encoding="UTF-8" standalone="yes"?>'
        '<p:sld xmlns:a="http://schemas.openxmlformats.org/drawingml/2006/main" '
        'xmlns:r="http://schemas.openxmlformats.org/officeDocument/2006/relationships" '
        'xmlns:p="http://schemas.openxmlformats.org/presentationml/2006/main">'
        "<p:cSld><p:spTree>"
        '<p:nvGrpSpPr><p:cNvPr id="1" name=""/><p:cNvGrpSpPr/><p:nvPr/></p:nvGrpSpPr>'
        "<p:grpSpPr/>"
        '<p:sp><p:nvSpPr><p:cNvPr id="2" name="Title"/><p:cNvSpPr><a:spLocks noGrp="1"/></p:cNvSpPr><p:nvPr/></p:nvSpPr>'
        '<p:spPr><a:xfrm><a:off x="457200" y="304800"/><a:ext cx="8229600" cy="1000000"/></a:xfrm>'
        '<a:prstGeom prst="rect"><a:avLst/></a:prstGeom></p:spPr>'
        f'<p:txBody><a:bodyPr wrap="square"/>{title_par}</p:txBody></p:sp>'
        '<p:sp><p:nvSpPr><p:cNvPr id="3" name="Body"/><p:cNvSpPr><a:spLocks noGrp="1"/></p:cNvSpPr><p:nvPr/></p:nvSpPr>'
        '<p:spPr><a:xfrm><a:off x="457200" y="1500000"/><a:ext cx="8229600" cy="4900000"/></a:xfrm>'
        '<a:prstGeom prst="rect"><a:avLst/></a:prstGeom></p:spPr>'
        f'<p:txBody><a:bodyPr wrap="square"/>{bullet_pars}</p:txBody></p:sp>'
        "</p:spTree></p:cSld>"
        '<p:clrMapOvr><a:overrideClrMapping bg1="lt1" tx1="dk1" bg2="lt2" tx2="dk2" '
        'accent1="accent1" accent2="accent2" accent3="accent3" accent4="accent4" '
        'accent5="accent5" accent6="accent6" hlink="hlink" folHlink="folHlink"/></p:clrMapOvr>'
        "</p:sld>"
    )


def _presentation_xml(slide_count: int) -> str:
    ids = "".join(
        f'<p:sldId id="{256 + i}" r:id="rId{i}"/>' for i in range(1, slide_count + 1)
    )
    rels = "".join(
        f'<Relationship Id="rId{i}" Type="http://schemas.openxmlformats.org/officeDocument/2006/relationships/slide" Target="slides/slide{i}.xml"/>'
        for i in range(1, slide_count + 1)
    )
    rels += (
        '<Relationship Id="rIdL1" Type="http://schemas.openxmlformats.org/officeDocument/2006/relationships/slideMaster" Target="slideMasters/slideMaster1.xml"/>'
        '<Relationship Id="rIdT1" Type="http://schemas.openxmlformats.org/officeDocument/2006/relationships/theme" Target="theme/theme1.xml"/>'
        '<Relationship Id="rIdN1" Type="http://schemas.openxmlformats.org/officeDocument/2006/relationships/notesMaster" Target="notesMasters/notesMaster1.xml"/>'
    )
    rels_xml = (
        '<?xml version="1.0" encoding="UTF-8" standalone="yes"?>'
        f'<Relationships xmlns="http://schemas.openxmlformats.org/package/2006/relationships">{rels}</Relationships>'
    )
    pres_xml = (
        '<?xml version="1.0" encoding="UTF-8" standalone="yes"?>'
        '<p:presentation xmlns:a="http://schemas.openxmlformats.org/drawingml/2006/main" '
        'xmlns:r="http://schemas.openxmlformats.org/officeDocument/2006/relationships" '
        'xmlns:p="http://schemas.openxmlformats.org/presentationml/2006/main">'
        f'<p:sldMasterIdLst><p:sldMasterId id="2147483648" r:id="rIdL1"/></p:sldMasterIdLst>'
        f'<p:notesMasterIdLst><p:notesMasterId r:id="rIdN1"/></p:notesMasterIdLst>'
        f"<p:sldIdLst>{ids}</p:sldIdLst>"
        '<p:sldSz cx="12192000" cy="6858000" type="screen16x9"/>'
        '<p:notesSz cx="6858000" cy="9144000"/>'
        "</p:presentation>"
    )
    return pres_xml, rels_xml


def build_pptx(path: Path, title: str, slides: list[tuple[str, list[str]]]) -> bool:
    """Write a valid minimal .pptx to `path`. Returns True on success."""
    try:
        slides = slides or [(title or "Untitled Slide", [])]
        pres_xml, rels_xml = _presentation_xml(len(slides))
        with zipfile.ZipFile(str(path), "w", zipfile.ZIP_DEFLATED) as zf:
            zf.writestr("[Content_Types].xml", _pptx_content_types(len(slides)))
            zf.writestr("_rels/.rels", _PPTX_RELS)
            zf.writestr("ppt/presentation.xml", pres_xml)
            zf.writestr("ppt/_rels/presentation.xml.rels", rels_xml)
            zf.writestr("ppt/theme/theme1.xml", _PPTX_THEME)
            zf.writestr("ppt/slideMasters/slideMaster1.xml", _PPTX_MASTER)
            zf.writestr("ppt/slideMasters/_rels/slideMaster1.xml.rels", _PPTX_MASTER_RELS)
            zf.writestr("ppt/slideLayouts/slideLayout1.xml", _PPTX_LAYOUT)
            zf.writestr("ppt/slideLayouts/_rels/slideLayout1.xml.rels", _PPTX_LAYOUT_RELS)
            zf.writestr("ppt/notesMasters/notesMaster1.xml", _NOTES_MASTER)
            zf.writestr("ppt/notesMasters/_rels/notesMaster1.xml.rels", _NOTES_MASTER_RELS)
            for i, (stitle, bullets) in enumerate(slides, start=1):
                zf.writestr(f"ppt/slides/slide{i}.xml", _slide_xml(stitle, bullets))
                zf.writestr(f"ppt/slides/_rels/slide{i}.xml.rels", _slide_rels(i))
                notes_body = _notes_body_xml(stitle, bullets)
                zf.writestr(
                    f"ppt/notesSlides/notesSlide{i}.xml",
                    # replace() not .format(): speaker-notes text is user
                    # content and may legitimately contain literal { } braces,
                    # which .format() would misread as placeholders.
                    _NOTES_SLIDE.replace("{body}", notes_body),
                )
                zf.writestr(f"ppt/notesSlides/_rels/notesSlide{i}.xml.rels", _NOTES_SLIDE_RELS)
        return True
    except Exception as exc:  # noqa: BLE001
        logger.exception("build_pptx failed for %s: %s", path, exc)
        return False


def verify_pptx(path: Path) -> dict[str, Any]:
    """Verify a real .pptx artifact: exists, valid ZIP, expected slide + notes parts."""
    facts: dict[str, Any] = {"exists": False, "valid_zip": False, "slide_count": 0, "notes_count": 0}
    try:
        if not path.exists():
            return facts
        facts["exists"] = True
        facts["size_bytes"] = path.stat().st_size
        if not zipfile.is_zipfile(str(path)):
            return facts
        with zipfile.ZipFile(str(path)) as zf:
            if zf.testzip() is not None:
                return facts
            names = set(zf.namelist())
            if "ppt/presentation.xml" not in names:
                return facts
            facts["valid_zip"] = True
            pres = zf.read("ppt/presentation.xml").decode("utf-8", errors="replace")
            notes = [n for n in names if n.startswith("ppt/notesSlides/notesSlide") and n.endswith(".xml")]
        facts["slide_count"] = pres.count("p:sldId ")
        facts["notes_count"] = len(notes)
    except Exception as exc:  # noqa: BLE001
        logger.warning("verify_pptx failed: %s", exc)
    return facts


# ── generic open / create ────────────────────────────────────────────────────
def build_code_file(path: Path, source: str) -> bool:
    """Write a real source file (plain UTF-8 text, not OOXML)."""
    try:
        path.write_text(source or "", encoding="utf-8")
        return True
    except Exception as exc:  # noqa: BLE001
        logger.exception("build_code_file failed for %s: %s", path, exc)
        return False


def verify_code_file(path: Path) -> dict[str, Any]:
    """Verify a real source artifact: exists, non-empty, lines of code."""
    facts: dict[str, Any] = {"exists": False, "line_count": 0, "char_count": 0}
    try:
        if not path.exists():
            return facts
        facts["exists"] = True
        facts["size_bytes"] = path.stat().st_size
        text = path.read_text(encoding="utf-8", errors="replace")
        facts["line_count"] = len([l for l in text.splitlines() if l.strip()])
        facts["char_count"] = len(text)
    except Exception as exc:  # noqa: BLE001
        logger.warning("verify_code_file failed: %s", exc)
    return facts


def open_artifact(path: Path) -> bool:
    """Open the artifact in its default application (Word/Excel/PowerPoint)."""
    try:
        if os.name == "nt":
            os.startfile(str(path))  # noqa: S606 - opening a verified local artifact
        else:
            import subprocess
            subprocess.Popen(["xdg-open", str(path)])
        return True
    except Exception as exc:  # noqa: BLE001
        logger.warning("open_artifact failed: %s", exc)
        return False


def open_in_editor(path: Path, editor: str = "") -> bool:
    """Open a source artifact in the requested installed editor (VS Code etc.).

    Falls back to the default handler when no editor is named or the named
    editor cannot be located. Truthful: returns False only when nothing could
    be launched.
    """
    import subprocess as _sp
    editor = (editor or "").strip().lower()
    candidates: list[str] = []
    if editor in ("vs code", "vscode", "code", "visual studio code"):
        candidates = [
            os.path.expandvars(r"%LOCALAPPDATA%\Programs\Microsoft VS Code\Code.exe"),
            r"C:\Program Files\Microsoft VS Code\Code.exe",
        ]
    elif editor in ("notepad", "notepad++", "npp"):
        candidates = [r"C:\Windows\System32\notepad.exe"]
    for cand in candidates:
        if os.path.exists(cand):
            try:
                _sp.Popen([cand, str(path)])
                return True
            except Exception as exc:  # noqa: BLE001
                logger.warning("open_in_editor failed for %s: %s", cand, exc)
                return False
    # No named editor found -> default handler (honest best effort).
    return open_artifact(path)


def create_artifact(
    subject: str,
    raw_content: str,
    artifact: str = "document",
    style: str = "",
    out_dir: Optional[Path] = None,
    language: str = "",
    **kwargs: Any,
) -> dict[str, Any]:
    """Create a real artifact of the requested kind. THE canonical entry point.

    Args:
        subject: the requested topic ("renewable energy", "messi and ronaldo").
        raw_content: generated content text (LLM-produced, cleaned here).
        artifact: artifact kind — resolves the FORMAT (docx/xlsx/pptx).
        style: optional formatting intent ("concise", "professional", "poem").
        out_dir: optional target directory (defaults to Documents).

    Returns a truthful result dict with the artifact path + verification facts.
    """
    subject = (subject or "").strip().rstrip(".,!?;:")
    kind = (artifact or "document").lower().strip()
    if not subject:
        return {"success": False, "message": "I need a subject before I can create that."}
    if not raw_content or not raw_content.strip():
        return {"success": False, "message": "I couldn't generate content for that."}

    directory = out_dir or documents_dir()
    try:
        directory.mkdir(parents=True, exist_ok=True)
    except Exception as exc:  # noqa: BLE001
        return {"success": False, "message": f"Couldn't use the Documents folder: {exc}"}

    language = kwargs.get("language", "")
    ext = artifact_extension(kind, language)
    filename = generate_artifact_filename(subject, kind, style) + ext
    path = _ensure_unique(directory / filename)
    title = " ".join(w.capitalize() for w in re.findall(r"[A-Za-z0-9]+", subject)) or "Untitled"

    if kind in _CODE_KINDS:
        if not build_code_file(path, raw_content):
            return {"success": False, "message": "The source file couldn't be written."}
        facts = verify_code_file(path)
        if not facts.get("exists") or facts.get("line_count", 0) == 0:
            return {
                "success": False,
                "message": f"The source file was written but verification failed ({path.name}).",
            }
        return {
            "success": True,
            "message": f"Created {path.name} — {facts['line_count']} lines of code.",
            "path": str(path),
            "filename": path.name,
            "line_count": facts["line_count"],
            "artifact": kind,
            "subject": subject,
            "language": language,
        }

    if kind in _SPREADSHEET_KINDS:
        rows = _parse_spreadsheet_rows(raw_content)
        if not rows:
            return {"success": False, "message": "I couldn't structure that into spreadsheet rows."}
        sheet_name = _sheet_name_from_subject(subject, kind)
        if not build_xlsx(path, rows, sheet_name=sheet_name):
            return {"success": False, "message": "The spreadsheet couldn't be written."}
        facts = verify_xlsx(path)
        if not facts.get("valid_zip") or facts.get("cell_count", 0) == 0:
            return {
                "success": False,
                "message": f"The spreadsheet was written but verification failed ({path.name}).",
            }
        return {
            "success": True,
            "message": f"Created {path.name} — {facts['row_count']} rows, {facts['cell_count']} cells.",
            "path": str(path),
            "filename": path.name,
            "row_count": facts["row_count"],
            "cell_count": facts["cell_count"],
            "artifact": kind,
            "subject": subject,
        }

    if kind in _PRESENTATION_KINDS:
        slides = _parse_slides(raw_content)
        if not build_pptx(path, title, slides):
            return {"success": False, "message": "The presentation couldn't be written."}
        facts = verify_pptx(path)
        if not facts.get("valid_zip") or facts.get("slide_count", 0) == 0:
            return {
                "success": False,
                "message": f"The presentation was written but verification failed ({path.name}).",
            }
        return {
            "success": True,
            "message": f"Created {path.name} — {facts['slide_count']} slides.",
            "path": str(path),
            "filename": path.name,
            "slide_count": facts["slide_count"],
            "artifact": kind,
            "subject": subject,
        }

    # DOCX family (default): reuse the canonical document operator.
    blocks = _parse_content_blocks(raw_content)
    if not build_docx(path, title, blocks):
        return {"success": False, "message": "The document couldn't be written."}
    facts = verify_docx(path)
    if not facts.get("valid_zip") or facts.get("word_count", 0) == 0:
        return {
            "success": False,
            "message": f"The document was written but verification failed ({path.name}).",
        }
    return {
        "success": True,
        "message": f"Created {path.name} — {facts['word_count']} words.",
        "path": str(path),
        "filename": path.name,
        "word_count": facts["word_count"],
        "artifact": kind,
        "subject": subject,
    }
