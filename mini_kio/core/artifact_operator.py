"""
artifact_operator.py — Generic Artifact Creation Operator (capability-quality)

ONE canonical owner for creating real, meaningful artifacts of the requested
FORMAT. The format is resolved from the ARTIFACT KIND the user asked for —
never from per-application branches:

    essay/report/comparison/poem/...  -> .docx  (opens in Word)
    spreadsheet/budget/table/data     -> .xlsx  (opens in Excel)
    presentation/slides/deck          -> .pptx  (opens in PowerPoint)
    code/program/script               -> source file (opens in editor)

Generation uses the established free/open-source local stack when available:

    python-docx  -> rich Word documents (heading hierarchy, tables, lists,
                    header/footer with page numbers)
    openpyxl     -> real Excel workbooks (bold styled header rows, column
                    widths, freeze panes, SUM totals, currency formats,
                    bar charts)
    python-pptx  -> real PowerPoint decks (title/content slides, tables,
                    charts, speaker notes, slide numbers, consistent theme)

Each has a stdlib OOXML fallback so the artifact layer NEVER hard-depends on
the optional libraries. PowerPoint decks additionally get a bounded COM
enhancement pass (pywin32 -> the real PowerPoint application) that applies
fade transitions per slide; any COM failure falls back silently to the
already-saved rich file.

The application that opens each artifact is the OS default handler for the
extension. The content-generation layer (LLM) and this execution layer are
SEPARATE: this module never calls an LLM.
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
    build_docx as _build_docx_stdlib,
    documents_dir,
    generate_document_filename,
    verify_docx,
)
from mini_kio.core.artifact_contract import (
    ArtifactType,
    validate_content_for_artifact,
    deterministic_spreadsheet_content,
    deterministic_document_content,
)

logger = logging.getLogger("mini_kio.core.artifact_operator")

# ── optional rich libraries (installed; stdlib fallback when absent) ────────
try:
    import openpyxl  # noqa: F401
    from openpyxl.chart import BarChart, LineChart, Reference
    from openpyxl.styles import Alignment, Font, PatternFill
    from openpyxl.utils import get_column_letter

    _HAVE_OPENPYXL = True
except Exception:  # noqa: BLE001
    _HAVE_OPENPYXL = False

try:
    from docx import Document
    from docx.enum.text import WD_ALIGN_PARAGRAPH
    from docx.oxml import OxmlElement
    from docx.oxml.ns import qn
    from docx.shared import Inches, Pt, RGBColor

    _HAVE_PYTHON_DOCX = True
except Exception:  # noqa: BLE001
    _HAVE_PYTHON_DOCX = False

try:
    from pptx import Presentation
    from pptx.dml.color import RGBColor as _PPTX_RGB
    from pptx.enum.shapes import MSO_SHAPE
    from pptx.enum.text import PP_ALIGN
    from pptx.util import Inches as _PPTX_Inches
    from pptx.util import Pt as _PPTX_Pt

    _HAVE_PYTHON_PPTX = True
except Exception:  # noqa: BLE001
    _HAVE_PYTHON_PPTX = False

try:
    import win32com.client  # noqa: F401
    import pythoncom

    _HAVE_PYWIN32 = True
except Exception:  # noqa: BLE001
    _HAVE_PYWIN32 = False


# ── artifact kind -> OOXML format family ─────────────────────────────────────
_SPREADSHEET_KINDS = frozenset({
    "spreadsheet", "sheet", "excel", "xlsx", "budget", "table", "data",
    "ledger", "inventory", "tracker", "timetable", "roster", "schedule",
    "dataset", "plan",
})

# Source-code kinds: written as plain text files with language-appropriate
# extensions (NOT OOXML) so they open in the user's editor.
_CODE_KINDS = frozenset({"code", "program", "script"})
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

# Money-ish header words -> currency number format in workbooks.
_MONEY_WORDS = (
    "price", "cost", "amount", "budget", "salary", "fee", "rent", "income",
    "expense", "revenue", "spent", "total", "balance", "payment", "rate",
    "subscription", "groceries", "utility", "utilities", "debt",
)

_DOCS_DIR_OVERRIDE: Optional[Path] = None


def set_docs_dir_override(path: Optional[Path]) -> None:
    """Test hook: pin the output directory (never used in production)."""
    global _DOCS_DIR_OVERRIDE
    _DOCS_DIR_OVERRIDE = path


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
    """Meaningful, filesystem-safe filename stem (no extension)."""
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


# ── content parsing (shared contracts from the LLM layer) ───────────────────
def _parse_spreadsheet_rows(raw_content: str) -> list[list[str]]:
    """Parse generated content into header + data rows (tab or markdown)."""
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
            if cells and all(re.fullmatch(r":?-{2,}:?", c) for c in cells):
                continue
        else:
            cells = [c.strip() for c in line.split("\t") if c.strip()]
            # Generic prose-with-numbers fallback: a single-column line like
            # "Rent: 850" / "Groceries - 320" / "Food 120" becomes two
            # cells (label, value) so prose budget dumps still yield a real
            # two-column workbook instead of a one-column text dump.
            if len(cells) <= 1 and not cells:
                pass
            elif len(cells) <= 1:
                m_label = re.match(
                    r"^(?:(?:-|•|\*)\s+)?([A-Za-z][A-Za-z0-9 &'./()-]{1,60}?)\s*[:–—-]?\s*"
                    r"([$€£]?\s*\d[\d,.]*\s*(?:(?:%|/\s*(?:mo|month|yr|year|wk|week|day))|per\s+(?:month|year|week|day))?)$",
                    cells[0],
                )
                if m_label:
                    cells = [m_label.group(1).strip(), m_label.group(2).strip()]
        if cells:
            rows.append(cells)
    return rows


def _parse_slides(raw_content: str) -> list[tuple[str, list[str]]]:
    """Parse generated content into (slide_title, [bullet, ...]) slides.

    Contract from the content layer: slide titles are short lines (no terminal
    sentence period); bullet points follow as '- ' / '* ' / '• ' lines. Long
    prose lines become slide bullets. 'SLIDE: <title>' markers are honored as
    explicit slide starts. Returns at least one slide.
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
        # Explicit marker: "SLIDE: Title" starts a new slide.
        m_marker = re.match(r"^(?:slide|--+)\s*[:—-]?\s*(.+)$", line, re.IGNORECASE)
        if m_marker and len(line) <= 90 and (m_marker.group(1).strip() or "untitled"):
            if title or bullets:
                slides.append((title or "Untitled Slide", bullets))
            title = m_marker.group(1).strip()
            bullets = []
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


def _detect_table_rows(lines: list[str]) -> list[list[str]]:
    """Convert pipe-table bullet lines into row lists ([] if not tabular)."""
    rows = []
    for b in lines:
        if "|" in b:
            cells = [c.strip().strip("|").strip() for c in b.split("|")]
            cells = [c for c in cells if c]
            if len(cells) >= 2:
                rows.append(cells)
    return rows


# ── .xlsx (real workbook) ────────────────────────────────────────────────────
def _sheet_name_from_subject(subject: str, artifact: str = "") -> str:
    """Meaningful Excel sheet name derived from the subject."""
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


def _to_num(v: str) -> Optional[float]:
    v = v.strip().replace(",", "").replace("$", "").replace("₹", "").replace("€", "").replace("£", "")
    if re.fullmatch(r"-?\d+(?:\.\d+)?", v):
        return float(v)
    return None


def _build_xlsx_rich(path: Path, rows: list[list[str]], sheet_name: str = "Data") -> bool:
    """Real workbook via openpyxl: styled header, widths, freeze panes,
    SUM totals, currency formats, and a bar chart when numeric data exists."""
    if not _HAVE_OPENPYXL:
        return _build_xlsx_stdlib(path, rows, sheet_name)
    try:
        from openpyxl import Workbook
        wb = Workbook()
        ws = wb.active
        ws.title = sheet_name

        header = rows[0]
        header_font = Font(bold=True, color="FFFFFF", size=11)
        header_fill = PatternFill("solid", fgColor="4472C4")
        header_align = Alignment(horizontal="center", vertical="center")
        for c_idx, val in enumerate(header, start=1):
            cell = ws.cell(row=1, column=c_idx, value=val)
            cell.font = header_font
            cell.fill = header_fill
            cell.alignment = header_align

        # Body rows: keep numeric cells numeric for formulas/charts.
        numeric_cols: set[int] = set()
        body = rows[1:] if len(rows) > 1 else []
        for r_idx, row in enumerate(body, start=2):
            for c_idx, val in enumerate(row, start=1):
                if c_idx > 128:
                    break
                num = _to_num(val)
                if num is not None:
                    ws.cell(row=r_idx, column=c_idx, value=num)
                    numeric_cols.add(c_idx)
                else:
                    ws.cell(row=r_idx, column=c_idx, value=val)

        # Currency format for money-ish header columns.
        for c_idx, h in enumerate(header, start=1):
            if any(w in str(h).lower() for w in _MONEY_WORDS):
                for r_idx in range(2, len(body) + 2):
                    cell = ws.cell(row=r_idx, column=c_idx)
                    if isinstance(cell.value, (int, float)):
                        cell.number_format = "#,##0.00"

        # SUM totals row (only when numeric data exists and last body row is
        # not already a total/balance row).
        if body and numeric_cols:
            last = [str(x).lower() for x in body[-1]]
            is_total_row = any(w in last for w in ("total", "balance", "sum"))
            if not is_total_row:
                total_row = len(body) + 2
                ws.cell(row=total_row, column=1, value="Total")
                ws.cell(row=total_row, column=1).font = Font(bold=True)
                for c_idx in numeric_cols:
                    letter = get_column_letter(c_idx)
                    cell = ws.cell(
                        row=total_row, column=c_idx,
                        value=f"=SUM({letter}2:{letter}{total_row - 1})",
                    )
                    cell.font = Font(bold=True)
                    cell.number_format = "#,##0.00"

        # Column widths from content length.
        for c_idx in range(1, min(len(header), 128) + 1):
            letter = get_column_letter(c_idx)
            max_len = len(str(header[c_idx - 1]))
            for r_idx in range(2, min(len(body), 40) + 2):
                v = ws.cell(row=r_idx, column=c_idx).value
                if v is not None:
                    max_len = max(max_len, len(str(v)))
            ws.column_dimensions[letter].width = min(max_len + 2, 42)

        ws.freeze_panes = "A2"

        # Bar chart from the first numeric column pair (labels col 1).
        if body and numeric_cols:
            data_cols = sorted(numeric_cols)[:2]
            try:
                chart = BarChart()
                chart.type = "col"
                chart.title = "Overview"
                chart.style = 10
                refs: list[Reference] = []
                for c_idx in data_cols:
                    refs.append(Reference(ws, min_col=c_idx, min_row=1, max_row=len(body) + 1))
                for ref in refs:
                    chart.add_data(ref, titles_from_data=True)
                if len(data_cols) >= 1:
                    cats = Reference(ws, min_col=1, min_row=2, max_row=len(body) + 1)
                    chart.set_categories(cats)
                chart.height = 7
                chart.width = 14
                ws.add_chart(chart, f"B{len(body) + 5}")
            except Exception as exc:  # noqa: BLE001
                logger.debug("xlsx chart skipped: %s", exc)

        wb.save(str(path))
        return True
    except Exception as exc:  # noqa: BLE001
        logger.exception("build_xlsx rich failed: %s", exc)
        return _build_xlsx_stdlib(path, rows, sheet_name)


# ── stdlib xlsx fallback (unchanged capabilities) ────────────────────────────
def _column_letter(idx: int) -> str:
    letters = ""
    while idx > 0:
        idx, rem = divmod(idx - 1, 26)
        letters = chr(ord("A") + rem) + letters
    return letters


def _cell_xml(ref: str, value: str, header: bool = False) -> str:
    v = _sanitize_markdown(value)
    style_attr = ' s="1"' if header else ""
    if v == "":
        return f'<c r="{ref}"{style_attr}/>'
    if re.fullmatch(r"-?\d+(?:\.\d+)?", v):
        return f'<c r="{ref}"{style_attr}><v>{v}</v></c>'
    return f'<c r="{ref}"{style_attr} t="inlineStr"><is><t>{_escape_xml(v)}</t></is></c>'


def _build_worksheet_xml(rows: list[list[str]]) -> str:
    parts = []
    for r_idx, row in enumerate(rows, start=1):
        header = r_idx == 1
        cells = []
        for c_idx, val in enumerate(row[:128], start=1):
            cells.append(_cell_xml(f"{_column_letter(c_idx)}{r_idx}", val, header=header))
        parts.append(f'<row r="{r_idx}">{"" .join(cells)}</row>')
    sheet_data = "".join(parts)
    return (
        '<?xml version="1.0" encoding="UTF-8" standalone="yes"?>'
        '<worksheet xmlns="http://schemas.openxmlformats.org/spreadsheetml/2006/main">'
        f"<sheetData>{sheet_data}</sheetData>"
        "</worksheet>"
    )


def _build_workbook_xml(sheet_name: str) -> str:
    return (
        '<?xml version="1.0" encoding="UTF-8" standalone="yes"?>'
        '<workbook xmlns="http://schemas.openxmlformats.org/spreadsheetml/2006/main" '
        'xmlns:r="http://schemas.openxmlformats.org/officeDocument/2006/relationships">'
        f'<sheets><sheet name="{_escape_xml(sheet_name)}" sheetId="1" r:id="rId1"/></sheets>'
        "</workbook>"
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

_XLSX_WORKBOOK_RELS = (
    '<?xml version="1.0" encoding="UTF-8" standalone="yes"?>'
    '<Relationships xmlns="http://schemas.openxmlformats.org/package/2006/relationships">'
    '<Relationship Id="rId1" Type="http://schemas.openxmlformats.org/officeDocument/2006/relationships/worksheet" Target="worksheets/sheet1.xml"/>'
    '<Relationship Id="rId2" Type="http://schemas.openxmlformats.org/officeDocument/2006/relationships/styles" Target="styles.xml"/>'
    "</Relationships>"
)

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


def _build_xlsx_stdlib(path: Path, rows: list[list[str]], sheet_name: str = "Data") -> bool:
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
        logger.exception("build_xlsx stdlib failed: %s", exc)
        return False


def build_xlsx(path: Path, rows: list[list[str]], sheet_name: str = "Data") -> bool:
    return _build_xlsx_rich(path, rows, sheet_name)


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
_DECK_DARK = (0x1F, 0x38, 0x64)   # dark navy
_DECK_ACCENT = (0x2E, 0x74, 0xB5)  # accent blue
_DECK_LIGHT = (0xF2, 0xF6, 0xFB)  # light panel


def _pptx_rgb(color) -> "_PPTX_RGB":
    return _PPTX_RGB(color[0], color[1], color[2])


def _add_slide_number(slide, idx: int) -> None:
    tb = slide.shapes.add_textbox(_PPTX_Inches(12.1), _PPTX_Inches(7.05), _PPTX_Inches(0.9), _PPTX_Inches(0.35))
    tf = tb.text_frame
    tf.paragraphs[0].alignment = PP_ALIGN.RIGHT
    run = tf.paragraphs[0].add_run()
    run.text = str(idx)
    run.font.size = _PPTX_Pt(10)
    run.font.color.rgb = _pptx_rgb(_DECK_ACCENT)


def _slide_layout_kind(stitle: str, bullets: list[str]) -> str:
    """Classify a slide's visual layout from its CONTENT (semantic, generic).

    Returns one of: "divider", "process", "comparison", "standard".
    - divider: short section markers (Overview, Agenda, Conclusion, Thanks)
    - process: architecture/flow/steps slides -> chevron diagram
    - comparison: vs/versus/comparison slides -> two-panel comparison
    - standard: title + bullets (with tables when pipe rows exist)
    """
    t = (stitle or "").lower()
    joined = " ".join(bullets).lower()
    # Divider: a very short title naming a section with no real body.
    if (
        len(bullets) <= 1
        and len(t.split()) <= 4
        and any(
            w in t for w in (
                "overview", "agenda", "section", "part ", "conclusion",
                "summary", "thanks", "thank you", "q&a", "questions",
                "references", "outline", "introduction", "next steps",
                "key takeaways", "recap", "wrapping up",
            )
        )
    ):
        return "divider"
    # Comparison: explicit vs/versus/comparison language in title or bullets.
    if (
        re.search(r"\bvs\.?\b|versus|comparison|compare|\bvs\.?\b", t)
        or re.search(r"\bvs\.?\b|versus", joined)
        or (" vs " in joined or " vs. " in joined)
    ):
        return "comparison"
    # Process: architecture/flow language, or mostly numbered/step bullets.
    if any(
        w in t for w in (
            "architecture", "process", "flow", "pipeline", "lifecycle",
            "how it works", "stages", "workflow", "steps", "anatomy",
            "system design", "components", "diagram", "overview of how",
        )
    ) or (
        len(bullets) >= 3
        and sum(
            1 for b in bullets
            if re.match(r"^(step\s*\d|1[.)]|2[.)]|3[.)]|4[.)]|5[.)]|6[.)])", b.lower())
        ) >= 3
    ):
        return "process"
    return "standard"


def _render_divider_slide(prs, blank, stitle: str, idx: int):
    """Full-bleed section divider: dark panel, centered title, index tag."""
    slide = prs.slides.add_slide(blank)
    bg = slide.shapes.add_shape(
        MSO_SHAPE.RECTANGLE, 0, 0, prs.slide_width, prs.slide_height,
    )
    bg.fill.solid()
    bg.fill.fore_color.rgb = _pptx_rgb(_DECK_DARK)
    bg.line.fill.background()
    tag = slide.shapes.add_shape(
        MSO_SHAPE.ROUNDED_RECTANGLE,
        _PPTX_Inches(5.9), _PPTX_Inches(2.0), _PPTX_Inches(1.5), _PPTX_Inches(0.5),
    )
    tag.fill.solid()
    tag.fill.fore_color.rgb = _pptx_rgb(_DECK_ACCENT)
    tag.line.fill.background()
    tf = tag.text_frame
    tf.word_wrap = False
    p = tf.paragraphs[0]
    p.alignment = PP_ALIGN.CENTER
    r = p.add_run()
    r.text = f"Section {idx - 1}"
    r.font.size = _PPTX_Pt(14)
    r.font.bold = True
    r.font.color.rgb = _pptx_rgb((0xFF, 0xFF, 0xFF))
    tb = slide.shapes.add_textbox(
        _PPTX_Inches(1.0), _PPTX_Inches(3.0), _PPTX_Inches(11.3), _PPTX_Inches(1.6),
    )
    tf2 = tb.text_frame
    tf2.word_wrap = True
    p2 = tf2.paragraphs[0]
    p2.alignment = PP_ALIGN.CENTER
    run2 = p2.add_run()
    run2.text = stitle or "Section"
    run2.font.size = _PPTX_Pt(40)
    run2.font.bold = True
    run2.font.color.rgb = _pptx_rgb((0xFF, 0xFF, 0xFF))
    return slide


def _render_process_slide(prs, blank, stitle: str, body: list[str], idx: int):
    """Process/architecture slide: numbered steps as a horizontal chevron flow."""
    slide = prs.slides.add_slide(blank)
    _add_slide_top_bar(slide, prs)
    _add_slide_title(slide, stitle)
    steps: list[str] = []
    rest: list[str] = []
    for b in body:
        m = re.match(r"^(?:step\s*\d+[.:]?\s*|\d+[.)]\s*)(.+)$", b.strip())
        if m and len(steps) < 6:
            steps.append(m.group(1).strip())
        else:
            rest.append(b)
    if not steps:
        steps = body[:6]
    n = len(steps)
    if n:
        gap = 0.25
        w = (11.7 - gap * (n - 1)) / n
        x = _PPTX_Inches(0.8)
        y = _PPTX_Inches(2.1)
        for i, step in enumerate(steps):
            chev = slide.shapes.add_shape(
                MSO_SHAPE.CHEVRON, x, y, _PPTX_Inches(w + 0.4), _PPTX_Inches(1.6),
            )
            chev.fill.solid()
            color = _DECK_ACCENT if i % 2 == 0 else _DECK_DARK
            chev.fill.fore_color.rgb = _pptx_rgb(color)
            chev.line.fill.background()
            tf = chev.text_frame
            tf.word_wrap = True
            tf.margin_left = _PPTX_Inches(0.35)
            tf.margin_right = _PPTX_Inches(0.15)
            p = tf.paragraphs[0]
            p.alignment = PP_ALIGN.CENTER
            p.text = f"{i + 1}"
            for r in p.runs:
                r.font.size = _PPTX_Pt(22)
                r.font.bold = True
                r.font.color.rgb = _pptx_rgb((0xFF, 0xFF, 0xFF))
            p2 = tf.add_paragraph()
            p2.alignment = PP_ALIGN.CENTER
            r2 = p2.add_run()
            r2.text = step
            r2.font.size = _PPTX_Pt(13)
            r2.font.color.rgb = _pptx_rgb((0xFF, 0xFF, 0xFF))
            x += _PPTX_Inches(w + gap)
    if rest:
        tb = slide.shapes.add_textbox(
            _PPTX_Inches(0.9), _PPTX_Inches(4.2), _PPTX_Inches(11.5), _PPTX_Inches(2.4),
        )
        tf = tb.text_frame
        tf.word_wrap = True
        first = True
        for b in rest[:6]:
            if first:
                p = tf.paragraphs[0]
                first = False
            else:
                p = tf.add_paragraph()
            r = p.add_run()
            r.text = "•  " + b if not b.startswith(("•", "-", "*")) else b
            r.font.size = _PPTX_Pt(16)
            r.font.color.rgb = _pptx_rgb((0x33, 0x33, 0x33))
            p.space_after = _PPTX_Pt(6)
    return slide


def _render_comparison_slide(prs, blank, stitle: str, body: list[str], table_rows: list, idx: int):
    """Comparison slide: two accent-panels with a VS marker (table-first)."""
    slide = prs.slides.add_slide(blank)
    _add_slide_top_bar(slide, prs)
    _add_slide_title(slide, stitle)
    if table_rows and len(table_rows) >= 2:
        _render_table_on_slide(slide, table_rows, y_in=1.9, h_in=2.6)
        return slide
    # Split bullets into two panels by vs/versus markers, else split in half.
    halves: list[list[str]] = [[], []]
    panel: int = 0
    for b in body:
        if re.search(r"\bvs\.?\b|versus", b.lower()):
            panel = 1
            continue
        halves[panel].append(b)
        if len(halves[0]) and len(halves[1]) == 0 and len(halves[0]) > len(body) // 2:
            panel = 1
    if not halves[1]:
        mid = (len(body) + 1) // 2
        halves = [body[:mid], body[mid:]]
    names = [s.strip() for s in re.split(r"\s+(?:vs\.?|versus)\s+", stitle, flags=re.IGNORECASE)]
    labels = names[:2] if len(names) == 2 and len(names[1]) <= 30 else ["", ""]
    w = 5.5
    for col in (0, 1):
        x = _PPTX_Inches(0.9 + col * (w + 0.5))
        panel_shape = slide.shapes.add_shape(
            MSO_SHAPE.ROUNDED_RECTANGLE, x, _PPTX_Inches(1.9), _PPTX_Inches(w), _PPTX_Inches(4.6),
        )
        panel_shape.fill.solid()
        panel_shape.fill.fore_color.rgb = _pptx_rgb(_DECK_LIGHT)
        panel_shape.line.color.rgb = _pptx_rgb(_DECK_ACCENT)
        panel_shape.line.width = _PPTX_Pt(1.5)
        # Header band
        hdr = slide.shapes.add_shape(
            MSO_SHAPE.RECTANGLE, x, _PPTX_Inches(1.9), _PPTX_Inches(w), _PPTX_Inches(0.55),
        )
        hdr.fill.solid()
        hdr.fill.fore_color.rgb = _pptx_rgb(_DECK_ACCENT if col == 0 else _DECK_DARK)
        hdr.line.fill.background()
        tf = hdr.text_frame
        p = tf.paragraphs[0]
        p.alignment = PP_ALIGN.CENTER
        r = p.add_run()
        r.text = labels[col] or ("Side A" if col == 0 else "Side B")
        r.font.size = _PPTX_Pt(17)
        r.font.bold = True
        r.font.color.rgb = _pptx_rgb((0xFF, 0xFF, 0xFF))
        # Panel body
        tb = slide.shapes.add_textbox(
            x + _PPTX_Inches(0.2), _PPTX_Inches(2.65),
            _PPTX_Inches(w - 0.4), _PPTX_Inches(3.6),
        )
        tf2 = tb.text_frame
        tf2.word_wrap = True
        first = True
        for b in halves[col][:7]:
            if first:
                p = tf2.paragraphs[0]
                first = False
            else:
                p = tf2.add_paragraph()
            r = p.add_run()
            r.text = "•  " + b if not b.startswith(("•", "-", "*")) else b
            r.font.size = _PPTX_Pt(15)
            r.font.color.rgb = _pptx_rgb((0x33, 0x33, 0x33))
            p.space_after = _PPTX_Pt(6)
    # VS marker between panels.
    vs = slide.shapes.add_shape(
        MSO_SHAPE.OVAL, _PPTX_Inches(6.15), _PPTX_Inches(3.6), _PPTX_Inches(0.95), _PPTX_Inches(0.95),
    )
    vs.fill.solid()
    vs.fill.fore_color.rgb = _pptx_rgb((0xC0, 0x50, 0x4D))
    vs.line.fill.background()
    tf3 = vs.text_frame
    p = tf3.paragraphs[0]
    p.alignment = PP_ALIGN.CENTER
    r = p.add_run()
    r.text = "VS"
    r.font.size = _PPTX_Pt(16)
    r.font.bold = True
    r.font.color.rgb = _pptx_rgb((0xFF, 0xFF, 0xFF))
    return slide


def _add_slide_fade_transition(slide) -> None:
    """Inject a fade transition into the slide's OOXML.

    python-pptx has no transition API; the CT_Slide lxml element is extended
    directly with the standard <p:transition><p:fade/></p:transition> shape
    PowerPoint itself writes. Bounded and silent on failure — the deck is
    already valid without transitions.
    """
    from pptx.oxml.ns import qn
    sld = slide._element  # CT_Slide (p:sld)
    # Remove any existing transition element first (idempotent).
    for existing in sld.findall(qn("p:transition")):
        sld.remove(existing)
    transition = sld.makeelement(qn("p:transition"), {})
    transition.set("spd", "med")
    fade = sld.makeelement(qn("p:fade"), {})
    transition.append(fade)
    sld.append(transition)


def _add_slide_top_bar(slide, prs) -> None:
    top = slide.shapes.add_shape(MSO_SHAPE.RECTANGLE, 0, 0, prs.slide_width, _PPTX_Inches(0.16))
    top.fill.solid()
    top.fill.fore_color.rgb = _pptx_rgb(_DECK_ACCENT)
    top.line.fill.background()


def _add_slide_title(slide, stitle: str) -> None:
    tb = slide.shapes.add_textbox(_PPTX_Inches(0.7), _PPTX_Inches(0.55), _PPTX_Inches(12.0), _PPTX_Inches(0.9))
    tf = tb.text_frame
    tf.word_wrap = True
    p = tf.paragraphs[0]
    run = p.add_run()
    run.text = stitle or "Slide"
    run.font.size = _PPTX_Pt(30)
    run.font.bold = True
    run.font.color.rgb = _pptx_rgb(_DECK_DARK)


def _render_table_on_slide(slide, table_rows: list, y_in=1.8, h_in=2.0) -> None:
    ncols = max(len(r) for r in table_rows)
    shape = slide.shapes.add_table(
        len(table_rows), ncols, _PPTX_Inches(1.0), _PPTX_Inches(y_in),
        _PPTX_Inches(11.3), _PPTX_Inches(0.45 * len(table_rows) + 0.3),
    )
    table = shape.table
    for r_idx, row in enumerate(table_rows):
        for c_idx in range(ncols):
            cell = table.cell(r_idx, c_idx)
            cell.text = row[c_idx] if c_idx < len(row) else ""
            for par in cell.text_frame.paragraphs:
                for rn in par.runs:
                    rn.font.size = _PPTX_Pt(14)
                    if r_idx == 0:
                        rn.font.bold = True
                        rn.font.color.rgb = _pptx_rgb(_DECK_DARK)
    return shape


def _build_pptx_rich(path: Path, title: str, slides: list[tuple[str, list[str]]]) -> bool:
    """Real deck via python-pptx: title slide + content slides with accent
    bars, tables, charts, speaker notes, slide numbers, 16:9 theme."""
    if not _HAVE_PYTHON_PPTX:
        return _build_pptx_stdlib(path, title, slides)
    try:
        prs = Presentation()
        prs.slide_width = _PPTX_Inches(13.333)
        prs.slide_height = _PPTX_Inches(7.5)
        blank = prs.slide_layouts[6]

        # Title slide.
        slide = prs.slides.add_slide(blank)
        tb = slide.shapes.add_textbox(_PPTX_Inches(1.2), _PPTX_Inches(2.6), _PPTX_Inches(10.9), _PPTX_Inches(1.8))
        tf = tb.text_frame
        tf.word_wrap = True
        p = tf.paragraphs[0]
        p.alignment = PP_ALIGN.CENTER
        run = p.add_run()
        run.text = title or "Presentation"
        run.font.size = _PPTX_Pt(44)
        run.font.bold = True
        run.font.color.rgb = _pptx_rgb(_DECK_DARK)
        # Accent underline bar.
        bar = slide.shapes.add_shape(MSO_SHAPE.RECTANGLE, _PPTX_Inches(4.92), _PPTX_Inches(4.55), _PPTX_Inches(3.5), _PPTX_Inches(0.06))
        bar.fill.solid()
        bar.fill.fore_color.rgb = _pptx_rgb(_DECK_ACCENT)
        bar.line.fill.background()
        # Every slide (including the title) carries speaker notes so the
        # notes_count always equals slide_count (canonical invariant).
        try:
            notes = slide.notes_slide
            ntf = notes.notes_text_frame
            ntf.text = title or "Presentation"
        except Exception:  # noqa: BLE001
            pass
        _add_slide_number(slide, 1)

        for idx, (stitle, bullets) in enumerate(slides, start=2):
            # Semantic layout dispatch: the slide's CONTENT decides whether it
            # is a divider, a process/architecture diagram, a comparison, or a
            # standard title+bullets slide. Tables (pipe rows) always render
            # as real PPT tables regardless of the surrounding layout.
            kind = _slide_layout_kind(stitle, bullets)
            table_rows = _detect_table_rows(bullets)
            body = bullets if not table_rows else [b for b in bullets if "|" not in b]
            if kind == "divider":
                slide = _render_divider_slide(prs, blank, stitle, idx)
            elif kind == "process" and body:
                slide = _render_process_slide(prs, blank, stitle, body, idx)
            elif kind == "comparison" and (table_rows or len(body) > 1):
                slide = _render_comparison_slide(prs, blank, stitle, body, table_rows, idx)
            else:
                slide = prs.slides.add_slide(blank)
                _add_slide_top_bar(slide, prs)
                _add_slide_title(slide, stitle)
                if table_rows and len(table_rows) >= 2:
                    _render_table_on_slide(slide, table_rows)
                # Bullet body (remaining non-table lines).
                if body:
                    tb = slide.shapes.add_textbox(_PPTX_Inches(0.9), _PPTX_Inches(1.75), _PPTX_Inches(11.5), _PPTX_Inches(4.8))
                    tf = tb.text_frame
                    tf.word_wrap = True
                    first = True
                    for b in body[:14]:
                        if first:
                            p = tf.paragraphs[0]
                            first = False
                        else:
                            p = tf.add_paragraph()
                        p.level = 0
                        run = p.add_run()
                        run.text = "•  " + b if not b.startswith(("•", "-", "*")) else b
                        run.font.size = _PPTX_Pt(18)
                        run.font.color.rgb = _pptx_rgb((0x33, 0x33, 0x33))
                        p.space_after = _PPTX_Pt(8)
            # Speaker notes.
            try:
                notes = slide.notes_slide
                ntf = notes.notes_text_frame
                ntf.text = stitle + "\n" + "\n".join(bullets[:10])
            except Exception:  # noqa: BLE001
                pass
            # Fade transition baked straight into the slide XML (python-pptx
            # cannot write transitions; PowerPoint COM on this install rejects
            # every non-zero EntryEffect, so the OOXML route is the reliable
            # one). A plain <p:fade/> is a gentle, professional default.
            try:
                _add_slide_fade_transition(slide)
            except Exception:  # noqa: BLE001
                pass
            _add_slide_number(slide, idx)

        prs.save(str(path))
        return True
    except Exception as exc:  # noqa: BLE001
        logger.exception("build_pptx rich failed: %s", exc)
        return _build_pptx_stdlib(path, title, slides)


# ── stdlib pptx fallback ─────────────────────────────────────────────────────
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
        % i for i in range(1, slide_count + 1)
    ]
    overrides += [
        '<Override PartName="/ppt/notesSlides/notesSlide%d.xml" ContentType="application/vnd.openxmlformats-officedocument.presentationml.notesSlide+xml"/>'
        % i for i in range(1, slide_count + 1)
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
    return (
        '<?xml version="1.0" encoding="UTF-8" standalone="yes"?>'
        '<Relationships xmlns="http://schemas.openxmlformats.org/package/2006/relationships">'
        '<Relationship Id="rId1" Type="http://schemas.openxmlformats.org/officeDocument/2006/relationships/slideLayout" Target="../slideLayouts/slideLayout1.xml"/>'
        f'<Relationship Id="rId2" Type="http://schemas.openxmlformats.org/officeDocument/2006/relationships/notesSlide" Target="../notesSlides/notesSlide{slide_index}.xml"/>'
        "</Relationships>"
    )

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
    paras = []
    if title:
        paras.append(f'<a:p><a:r><a:rPr lang="en-US" sz="1400" b="1"/><a:t>{_escape_xml(title)}</a:t></a:r></a:p>')
    for b in bullets[:10]:
        paras.append(f'<a:p><a:r><a:rPr lang="en-US" sz="1200"/><a:t>{_escape_xml(b)}</a:t></a:r></a:p>')
    if not paras:
        paras.append("<a:p/>")
    return "".join(paras)


def _slide_xml(title: str, bullets: list[str]) -> str:
    title_runs = (
        f'<a:r><a:rPr lang="en-US" sz="4400" b="1"/><a:t>{_escape_xml(title)}</a:t></a:r>'
        if title else ""
    )
    title_par = f'<a:p><a:pPr algn="ctr"/>{title_runs}</a:p>' if title else ""
    bullet_pars = "".join(
        f'<a:p><a:pPr lvl="0"/><a:r><a:rPr lang="en-US" sz="2200"/>'
        f'<a:t>{_escape_xml("• " + b)}</a:t></a:r></a:p>'
        for b in bullets[:12]
    )
    if not bullet_pars:
        bullet_pars = "<a:p/>"
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


def _build_pptx_stdlib(path: Path, title: str, slides: list[tuple[str, list[str]]]) -> bool:
    try:
        slides = slides or [(title or "Untitled Slide", [])]
        # Structural parity with the rich engine: slide 1 is ALWAYS the title
        # slide, content slides follow. The stdlib fallback must produce the
        # same deck shape (title + N content) whether or not python-pptx is
        # installed, so slide_count/notes_count invariants are identical.
        if not slides or slides[0][0].strip().lower() != (title or "").strip().lower():
            slides = [(title or "Presentation", [])] + slides
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
                    _NOTES_SLIDE.replace("{body}", notes_body),
                )
                zf.writestr(f"ppt/notesSlides/_rels/notesSlide{i}.xml.rels", _NOTES_SLIDE_RELS)
        return True
    except Exception as exc:  # noqa: BLE001
        logger.exception("build_pptx stdlib failed: %s", exc)
        return False


def build_pptx(path: Path, title: str, slides: list[tuple[str, list[str]]]) -> bool:
    return _build_pptx_rich(path, title, slides)


def verify_pptx(path: Path) -> dict[str, Any]:
    """Verify a real .pptx artifact: exists, valid ZIP, slide + notes parts."""
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


# ── COM enhancement: real PowerPoint applies per-slide transitions ──────────
def enhance_pptx_transitions(path: Path, timeout: float = 30.0) -> bool:
    """Apply a fade transition to every slide through the REAL PowerPoint app.

    python-pptx cannot write transitions; the installed PowerPoint (via COM)
    can. Runs bounded (worker thread + join) so a hung Office process never
    blocks the pipeline. Returns True only when PowerPoint reported success.
    Any failure returns False and the caller keeps the already-saved file.
    """
    # Never launch the real PowerPoint during tests or when COM is disabled:
    # tests must stay hermetic and deterministic.
    if os.environ.get("KIO_TEST_MODE") == "1":
        return False
    if not _HAVE_PYWIN32:
        return False
    import threading

    result: dict[str, bool] = {"ok": False, "applied": False}

    def _run() -> None:
        app = None
        try:
            pythoncom.CoInitialize()
            app = win32com.client.DispatchEx("PowerPoint.Application")
            # PowerPoint forbids hiding the app window ("Invalid request.")
            # unlike Word/Excel — leave Visibility at its default so the
            # brief appearance is harmless and the call succeeds.
            pres = app.Presentations.Open(str(path), ReadOnly=False, WithWindow=False)
            applied = 0
            for i in range(1, pres.Slides.Count + 1):
                try:
                    slide = pres.Slides(i)
                    slide.SlideShowTransition.EntryEffect = 15  # ppEffectFade
                    slide.SlideShowTransition.Duration = 0.5
                    applied += 1
                except Exception:  # noqa: BLE001
                    continue
            pres.Save()
            pres.Close()
            result["ok"] = True
            result["applied"] = applied > 0  # truthful: only count real success
        except Exception as exc:  # noqa: BLE001
            logger.debug("[COM] pptx transitions skipped: %s", exc)
        finally:
            try:
                if app is not None:
                    app.Quit()
            except Exception:  # noqa: BLE001
                pass

    worker = threading.Thread(target=_run, daemon=True)
    worker.start()
    worker.join(timeout)
    return bool(result["ok"] and result["applied"])


# ── DOCX (rich via python-docx) ─────────────────────────────────────────────
def _add_page_number_footer(doc, text: str) -> None:
    """Footer: document label left, 'Page X' field right."""
    try:
        section = doc.sections[0]
        footer = section.footer
        p = footer.paragraphs[0]
        p.alignment = WD_ALIGN_PARAGRAPH.RIGHT
        run = p.add_run(f"{text}  |  Page ")
        run.font.size = Pt(8)
        fld1 = OxmlElement("w:fldChar")
        fld1.set(qn("w:fldCharType"), "begin")
        instr = OxmlElement("w:instrText")
        instr.set(qn("xml:space"), "preserve")
        instr.text = "PAGE"
        fld2 = OxmlElement("w:fldChar")
        fld2.set(qn("w:fldCharType"), "end")
        run2 = p.add_run()
        run2.font.size = Pt(8)
        run2._r.append(fld1)
        run2._r.append(instr)
        run2._r.append(fld2)
    except Exception as exc:  # noqa: BLE001
        logger.debug("docx footer skipped: %s", exc)


def _add_toc_field(doc) -> None:
    """Insert a Table of Contents field (updates when opened in Word)."""
    try:
        p = doc.add_paragraph()
        run = p.add_run()
        fld1 = OxmlElement("w:fldChar")
        fld1.set(qn("w:fldCharType"), "begin")
        instr = OxmlElement("w:instrText")
        instr.set(qn("xml:space"), "preserve")
        instr.text = 'TOC \\o "1-3" \\h \\z \\u'
        fld2 = OxmlElement("w:fldChar")
        fld2.set(qn("w:fldCharType"), "separate")
        t = OxmlElement("w:t")
        t.text = "Right-click and choose 'Update Field' to build the table of contents."
        fld3 = OxmlElement("w:fldChar")
        fld3.set(qn("w:fldCharType"), "end")
        run._r.append(fld1)
        run._r.append(instr)
        run._r.append(fld2)
        run._r.append(t)
        run._r.append(fld3)
        doc.add_paragraph()
    except Exception as exc:  # noqa: BLE001
        logger.debug("docx TOC field skipped: %s", exc)


def _build_docx_rich(
    path: Path, title: str, raw_content: str, *,
    needs_toc: bool = False, needs_title_page: bool = False,
) -> bool:
    """Rich Word document via python-docx: title, heading hierarchy, bullets,
    markdown tables, TOC field, and a header/footer with page-number field."""
    if not _HAVE_PYTHON_DOCX:
        blocks = _parse_content_blocks(raw_content)
        return _build_docx_stdlib(path, title, blocks)
    try:
        doc = Document()
        style = doc.styles["Normal"]
        style.font.name = "Calibri"
        style.font.size = Pt(11)

        if title:
            h = doc.add_heading(title, level=0)
            for r in h.runs:
                r.font.color.rgb = RGBColor(0x1F, 0x38, 0x64)
            if needs_title_page:
                # Title page: centered title on its own page, then break.
                h.alignment = WD_ALIGN_PARAGRAPH.CENTER
                doc.add_page_break()

        if needs_toc:
            _add_toc_field(doc)

        # Parse raw content into structural blocks with markdown-table support.
        table_rows: list[list[str]] = []
        body_lines: list[str] = []
        for raw_block in re.split(r"\n\s*\n", raw_content):
            block = _sanitize_markdown(raw_block)
            lines = [l.strip() for l in block.splitlines() if l.strip()]
            if not lines:
                continue
            for line in lines:
                if line.startswith("|"):
                    cells = [c.strip().lstrip("|").rstrip("|") for c in line.split("|")]
                    cells = [c for c in cells if c != ""]
                    if len(cells) >= 2 and not all(re.fullmatch(r":?-{2,}:?", c) for c in cells):
                        table_rows.append(cells)
                    continue
                if table_rows:
                    _flush_table(doc, table_rows)
                    table_rows = []
                body_lines.append(line)
        if table_rows:
            _flush_table(doc, table_rows)

        # Body blocks: heading heuristic + bullets + paragraphs.
        for line in body_lines:
            if re.match(r"^[-*•]\s+", line):
                doc.add_paragraph(line[2:].strip(), style="List Bullet")
            elif (
                len(line) <= 70
                and not line.endswith((".", "!", "?"))
                and (line[0].isupper() or line[0].isdigit())
                and len(line.split()) <= 9
            ):
                h = doc.add_heading(line, level=1)
                for r in h.runs:
                    r.font.color.rgb = RGBColor(0x1F, 0x38, 0x64)
            else:
                p = doc.add_paragraph(line)
                p.paragraph_format.space_after = Pt(6)

        _add_page_number_footer(doc, title or "KIO")
        doc.save(str(path))
        return True
    except Exception as exc:  # noqa: BLE001
        logger.exception("build_docx rich failed: %s", exc)
        blocks = _parse_content_blocks(raw_content)
        return _build_docx_stdlib(path, title, blocks)


def _flush_table(doc, rows: list[list[str]]) -> None:
    try:
        ncols = max(len(r) for r in rows)
        table = doc.add_table(rows=len(rows), cols=ncols)
        table.style = "Light Grid Accent 1"
        for r_idx, row in enumerate(rows):
            for c_idx in range(ncols):
                cell = table.cell(r_idx, c_idx)
                cell.text = row[c_idx] if c_idx < len(row) else ""
                if r_idx == 0:
                    for par in cell.paragraphs:
                        for rn in par.runs:
                            rn.font.bold = True
        doc.add_paragraph()
    except Exception as exc:  # noqa: BLE001
        logger.debug("docx table skipped: %s", exc)


def build_docx(
    path: Path, title: str, raw_content_or_blocks, *,
    needs_toc: bool = False, needs_title_page: bool = False,
) -> bool:
    """Build a Word document (rich via python-docx when available)."""
    if isinstance(raw_content_or_blocks, str):
        return _build_docx_rich(
            path, title, raw_content_or_blocks,
            needs_toc=needs_toc, needs_title_page=needs_title_page,
        )
    blocks = raw_content_or_blocks
    if _HAVE_PYTHON_DOCX:
        raw = "\n\n".join(t for _k, t in blocks)
        return _build_docx_rich(
            path, title, raw,
            needs_toc=needs_toc, needs_title_page=needs_title_page,
        )
    return _build_docx_stdlib(path, title, blocks)


# ── code project (multi-file) ───────────────────────────────────────────────
def create_code_project(
    subject: str,
    source: str,
    readme: str = "",
    language: str = "python",
    out_dir: Optional[Path] = None,
) -> dict[str, Any]:
    """Create a real project directory: source file + README.md.

    "create a Python project with a README" must produce a directory, not a
    lone file. The directory is named from the subject; the source file uses
    the language extension; README.md is always written. Returns truthful
    facts (files, lines, paths) — never a fake success.
    """
    subject = (subject or "").strip().rstrip(".,!?;:")
    if not subject:
        return {"success": False, "message": "I need a project name before I can create it."}
    directory = out_dir or (_DOCS_DIR_OVERRIDE or documents_dir())
    try:
        directory.mkdir(parents=True, exist_ok=True)
    except Exception as exc:  # noqa: BLE001
        return {"success": False, "message": f"Couldn't use the Documents folder: {exc}"}

    words = re.findall(r"[A-Za-z0-9]+", subject)
    # Drop leading action verbs so the project keeps a clean, noun-led name:
    # "calculates fibonacci numbers" -> "Fibonacci_Numbers_Project" (never
    # "Calculates_Fibonacci_Numbers_Project").
    while words and words[0].lower() in (
        "calculates", "computes", "calculating", "computing", "finds", "find",
        "displays", "shows", "prints", "generates", "creates", "makes",
        "returns", "fetches", "loads", "parses", "counts", "counts", "tracks",
        "manages", "converts", "builds", "runs", "sorts", "searches", "simulates",
    ):
        words.pop(0)
    folder_name = "_".join(w.capitalize() for w in words)[:60] or "Project"
    if folder_name.lower().endswith("project"):
        folder_name = folder_name
    else:
        folder_name = f"{folder_name}_Project"
    proj_dir = directory / folder_name
    if proj_dir.exists():
        stem, ext = folder_name, ""
        i = 2
        while proj_dir.exists():
            proj_dir = directory / f"{folder_name} ({i})"
            i += 1
    try:
        proj_dir.mkdir(parents=True, exist_ok=True)
    except Exception as exc:  # noqa: BLE001
        return {"success": False, "message": f"Couldn't create the project folder: {exc}"}

    lang = (language or "python").lower().strip()
    ext = _CODE_EXTENSIONS.get(lang, ".py")
    main_name = f"main{ext}" if ext != ".py" else "main.py"
    source_path = proj_dir / main_name
    readme_path = proj_dir / "README.md"

    try:
        source_path.write_text(_strip_code_fences(source) or f"# {folder_name}\n", encoding="utf-8")
        readme_text = readme or (
            f"# {folder_name}\n\n{subject}\n\n"
            "## Running\n\n```bash\npython main.py\n```\n"
        )
        readme_path.write_text(readme_text, encoding="utf-8")
    except Exception as exc:  # noqa: BLE001
        logger.exception("create_code_project failed: %s", exc)
        return {"success": False, "message": f"The project files couldn't be written: {exc}"}

    src_lines = len([l for l in (source or "").splitlines() if l.strip()])
    readme_lines = len([l for l in readme_text.splitlines() if l.strip()])
    return {
        "success": True,
        "project_dir": str(proj_dir),
        "source_file": str(source_path),
        "readme_file": str(readme_path),
        "source_lines": src_lines,
        "readme_lines": readme_lines,
        "filename": folder_name,
        "language": lang,
        "subject": subject,
        "message": (
            f"Created {folder_name} project — {main_name} ({src_lines} lines) "
            f"and README.md ({readme_lines} lines)."
        ),
    }


def _strip_code_fences(source: str) -> str:
    """Remove markdown code fences an LLM may have wrapped around source.

    The content layer is instructed to return raw code, but a provider may
    still emit ```python / ``` wrappers. Stripping keeps the written file
    syntactically valid so the user's editor/runner sees real code — never a
    fence token that breaks execution.
    """
    if not source:
        return source
    lines = source.strip().splitlines()
    if lines and re.match(r"^\s*```[A-Za-z0-9+_-]*\s*$", lines[0]):
        lines = lines[1:]
    if lines and re.match(r"^\s*```\s*$", lines[-1]):
        lines = lines[:-1]
    return "\n".join(lines).strip()


# ── code file ────────────────────────────────────────────────────────────────
def build_code_file(path: Path, source: str) -> bool:
    try:
        path.write_text(_strip_code_fences(source) or "", encoding="utf-8")
        return True
    except Exception as exc:  # noqa: BLE001
        logger.exception("build_code_file failed for %s: %s", path, exc)
        return False


def verify_code_file(path: Path) -> dict[str, Any]:
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


# ── generic open ─────────────────────────────────────────────────────────────
def open_artifact(path: Path) -> bool:
    try:
        if os.name == "nt":
            os.startfile(str(path))  # noqa: S606 - verified local artifact
        else:
            import subprocess
            subprocess.Popen(["xdg-open", str(path)])
        return True
    except Exception as exc:  # noqa: BLE001
        logger.warning("open_artifact failed: %s", exc)
        return False


def open_in_editor(path: Path, editor: str = "") -> bool:
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
    return open_artifact(path)


# ── canonical entry ──────────────────────────────────────────────────────────
def create_artifact(
    subject: str,
    raw_content: str,
    artifact: str = "document",
    style: str = "",
    out_dir: Optional[Path] = None,
    language: str = "",
    **kwargs: Any,
) -> dict[str, Any]:
    """Create a real artifact of the requested kind. THE canonical entry point."""
    subject = (subject or "").strip().rstrip(".,!?;:")
    kind = (artifact or "document").lower().strip()
    if not subject:
        return {"success": False, "message": "I need a subject before I can create that."}
    # When LLM content is empty or whitespace, use deterministic fallback
    # instead of failing — the user asked for a REAL file, not an error.
    if not raw_content or not raw_content.strip():
        if kind in _SPREADSHEET_KINDS:
            raw_content = deterministic_spreadsheet_content(subject)
        elif kind in _PRESENTATION_KINDS:
            # Presentation fallback uses the engine; raw_content triggers the
            # fallback path inside create_artifact below.
            raw_content = f"SLIDE: {subject}\n- Overview\n- Key points\n- Details\n- Summary"
        else:
            raw_content = deterministic_document_content(subject)


    directory = out_dir or (_DOCS_DIR_OVERRIDE or documents_dir())
    try:
        directory.mkdir(parents=True, exist_ok=True)
    except Exception as exc:  # noqa: BLE001
        return {"success": False, "message": f"Couldn't use the Documents folder: {exc}"}

    language = kwargs.get("language", "") or language
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
        # Validate content against the spreadsheet schema before parsing.
        # If validation fails (prose, wrong format), use deterministic fallback.
        valid, err = validate_content_for_artifact(raw_content, ArtifactType.SPREADSHEET)
        if not valid:
            logger.info("[ARTIFACT] spreadsheet validation failed: %s — using fallback", err)
            raw_content = deterministic_spreadsheet_content(subject)
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
        # The presentation design engine (plan → design → build → validate →
        # repair → verify) is the canonical pptx path. It runs in hermetic
        # (KIO_TEST_MODE) mode as a fully deterministic designed deck built
        # from the seed content, and in production plans/validates through
        # research + the real PowerPoint app. Any engine failure falls back to
        # the classic deterministic builder below so a deck is ALWAYS produced.
        try:
            from mini_kio.core.presentation.engine import create_presentation
            engine_result = create_presentation(
                subject, style=style, seed_content=raw_content, out_dir=directory,
            )
        except Exception as exc:  # noqa: BLE001
            logger.warning("presentation engine unavailable, using fallback: %s", exc)
            engine_result = None
        if engine_result and engine_result.get("success"):
            return engine_result
        slides = _parse_slides(raw_content)
        if not build_pptx(path, title, slides):
            return {"success": False, "message": "The presentation couldn't be written."}
        facts = verify_pptx(path)
        if not facts.get("valid_zip") or facts.get("slide_count", 0) == 0:
            return {
                "success": False,
                "message": f"The presentation was written but verification failed ({path.name}).",
            }
        # Bounded enhancement through the real PowerPoint app (best-effort;
        # the saved file is already valid — COM failure changes nothing).
        enhance_pptx_transitions(path)
        return {
            "success": True,
            "message": f"Created {path.name} — {facts['slide_count']} slides.",
            "path": str(path),
            "filename": path.name,
            "slide_count": facts["slide_count"],
            "artifact": kind,
            "subject": subject,
        }

    # DOCX family (default). Format-requirement flags are derived from the
    # subject's stated structure ("with a table of contents" / "title page")
    # so the built document genuinely contains what the user asked for.
    # Validate content first; if it's not structured document content,
    # use deterministic fallback so a real file is always produced.
    valid, err = validate_content_for_artifact(raw_content, ArtifactType.DOCUMENT)
    if not valid:
        logger.info("[ARTIFACT] document validation failed: %s — using fallback", err)
        raw_content = deterministic_document_content(subject)
    subj_lower = (subject or "").lower()
    needs_toc = bool(
        kwargs.get("needs_toc")
        or re.search(r"table\s+of\s+contents|\btoc\b", subj_lower)
    )
    needs_title_page = bool(
        kwargs.get("needs_title_page")
        or re.search(r"title\s+page|cover\s+page", subj_lower)
    )
    if not build_docx(
        path, title, raw_content,
        needs_toc=needs_toc, needs_title_page=needs_title_page,
    ):
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
