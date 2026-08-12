"""
document_operator.py — Canonical Document Creation Operator (capability-quality)

Creates real, meaningful Word (.docx) documents WITHOUT external dependencies:
python-docx and win32com are NOT required. A .docx is a ZIP of OOXML parts, so
the stdlib (zipfile + XML escaping) is sufficient to build a valid document
that Microsoft Word opens natively.

Responsibilities (the ONE canonical owner):
  1. Generate a meaningful filename from the requested subject + artifact
     ("renewable energy" + report -> "Renewable_Energy_Report.docx",
      "messi and ronaldo" + comparison -> "Messi_And_Ronaldo_Comparison.docx").
  2. Lay out clean structured content: title, headings, paragraphs, bullets —
     never raw LLM/markdown garbage.
  3. Save to the user's Documents folder with safe collision handling.
  4. Verify the artifact (exists, valid ZIP, document body has real text).
  5. Open the artifact in the default editor (Word on Windows).

The content-generation layer (LLM) and this execution layer are SEPARATE:
this module never calls an LLM. It consumes clean text blocks and formats them.
"""

from __future__ import annotations

import logging
import os
import re
import zipfile
from pathlib import Path
from typing import Any, Optional, Tuple
from xml.sax.saxutils import escape

logger = logging.getLogger("mini_kio.core.document_operator")

# Artifact noun -> filename suffix. "document"/"overview" default to Overview.
_ARTIFACT_SUFFIX = {
    "report": "Report",
    "comparison": "Comparison",
    "poem": "Poem",
    "essay": "Essay",
    "email": "Email",
    "letter": "Letter",
    "summary": "Summary",
    "overview": "Overview",
    "document": "Overview",
    "doc": "Overview",
    "paper": "Paper",
    "write-up": "Overview",
    "file": "Document",
}

# Heading look-alikes: short lines, no terminal sentence period, or explicit
# section markers. Never marks a long body paragraph as a heading.
_HEADING_RE = re.compile(
    r"^(?:section\s*\d+|part\s*\d+|chapter\s*\d+|step\s*\d+|"
    r"\d+[.):]\s+|\d+\s*[-–—]\s+|[ivx]+[.):]\s+)",
    re.IGNORECASE,
)


def _sanitize_markdown(text: str) -> str:
    """Strip markdown/leak garbage so document content stays clean.

    Removes: leading #/*/_- heading markers, bold/italic ** and *, fenced
    code markers, inline backticks, HTML tags, stray control chars, and
    collapses duplicate whitespace. Keeps real punctuation and structure.
    """
    if not text:
        return ""
    t = text.strip()
    t = re.sub(r"```[a-zA-Z0-9_]*", "", t)
    t = re.sub(r"`", "", t)
    t = re.sub(r"<[^>]+>", "", t)
    t = re.sub(r"(?m)^\s*#{1,6}\s*", "", t)
    t = re.sub(r"(?m)^\s*(?:\*\*|__)", "", t)
    t = re.sub(r"(?m)(?:\*\*|__)\s*$", "", t)
    t = re.sub(r"\*\*", "", t)
    t = re.sub(r"(?m)^\s*>\s?", "", t)
    t = re.sub(r"\\[nrt]", " ", t)
    t = re.sub(r"[\x00-\x08\x0b\x0c\x0e-\x1f]", "", t)
    t = re.sub(r"[ \t]{2,}", " ", t)
    return t.strip()


def generate_document_filename(subject: str, artifact: str = "document", style: str = "") -> str:
    """Return a meaningful, filesystem-safe filename (no extension).

    Examples:
      "renewable energy" + report -> "Renewable_Energy_Report"
      "messi and ronaldo" + comparison -> "Messi_And_Ronaldo_Comparison"
      "machine learning" + overview -> "Machine_Learning_Overview"
    """
    words = re.findall(r"[A-Za-z0-9]+", subject or "")
    title = "_".join(w.capitalize() for w in words) or "Untitled"
    if title.lower() == "untitled":
        return "Untitled_Document"
    suffix = _ARTIFACT_SUFFIX.get((artifact or "document").lower(), "Overview")
    return f"{title}_{suffix}"


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


def _escape_xml(text: str) -> str:
    return escape(text or "", entities={'"': "&quot;", "'": "&apos;"})


def _block_kind(line: str) -> str:
    """Classify a cleaned text line as 'heading' | 'bullet' | 'body'."""
    if re.match(r"^[-*•]\s+", line):
        return "bullet"
    stripped = line.strip()
    if not stripped:
        return "body"
    # Heading heuristic: short, no terminal sentence punctuation (or an
    # explicit section marker), capitalized start.
    if len(stripped) <= 70:
        if _HEADING_RE.match(stripped):
            return "heading"
        if not stripped.endswith((".", "!", "?")) and (
            stripped[0].isupper() or stripped[0].isdigit()
        ):
            # "Machine Learning", "Key Takeaways" — a plausible heading.
            if len(stripped.split()) <= 9:
                return "heading"
    return "body"


def _p_xml(runs: str, *, style: str = "") -> str:
    ppr = ""
    if style == "title":
        ppr = (
            '<w:pPr><w:jc w:val="center"/>'
            '<w:spacing w:after="240" w:before="120"/></w:pPr>'
        )
    elif style == "heading":
        ppr = '<w:pPr><w:spacing w:before="200" w:after="100"/></w:pPr>'
    elif style == "bullet":
        ppr = '<w:pPr><w:ind w:left="360"/></w:pPr>'
    else:
        ppr = '<w:pPr><w:spacing w:after="120"/></w:pPr>'
    return f"<w:p>{ppr}{runs}</w:p>"


def _run_xml(text: str, *, bold: bool = False, size_half_points: Optional[int] = None) -> str:
    rpr = ""
    if bold or size_half_points:
        bits = []
        if bold:
            bits.append("<w:b/>")
        if size_half_points:
            bits.append(f'<w:sz w:val="{size_half_points}"/>')
            bits.append(f'<w:szCs w:val="{size_half_points}"/>')
        if bits:
            rpr = "<w:rPr>" + "".join(bits) + "</w:rPr>"
    return f"<w:r>{rpr}<w:t xml:space=\"preserve\">{_escape_xml(text)}</w:t></w:r>"


def _build_document_xml(title: str, blocks: list[Tuple[str, str]]) -> str:
    """Build the word/document.xml body from (kind, text) blocks."""
    parts = []
    if title:
        parts.append(_p_xml(_run_xml(title, bold=True, size_half_points=56), style="title"))
    for kind, text in blocks:
        text = text.strip()
        if not text:
            continue
        if kind == "bullet":
            body = text[2:].strip() if text[:2] in ("- ", "* ") else text
            parts.append(_p_xml(_run_xml("•  " + body), style="bullet"))
        elif kind == "heading":
            parts.append(_p_xml(_run_xml(text, bold=True, size_half_points=28), style="heading"))
        else:
            parts.append(_p_xml(_run_xml(text)))
    body = "".join(parts)
    return (
        '<?xml version="1.0" encoding="UTF-8" standalone="yes"?>'
        '<w:document xmlns:w="http://schemas.openxmlformats.org/wordprocessingml/2006/main">'
        f"<w:body>{body}"
        '<w:sectPr><w:pgSz w:w="12240" w:h="15840"/><w:pgMar w:top="1440" w:right="1440" '
        'w:bottom="1440" w:left="1440" w:header="720" w:footer="720" w:gutter="0"/></w:sectPr>'
        "</w:body></w:document>"
    )


_CONTENT_TYPES = (
    '<?xml version="1.0" encoding="UTF-8" standalone="yes"?>'
    '<Types xmlns="http://schemas.openxmlformats.org/package/2006/content-types">'
    '<Default Extension="rels" ContentType="application/vnd.openxmlformats-package.relationships+xml"/>'
    '<Default Extension="xml" ContentType="application/xml"/>'
    '<Override PartName="/word/document.xml" '
    'ContentType="application/vnd.openxmlformats-officedocument.wordprocessingml.document.main+xml"/>'
    "</Types>"
)

_RELS = (
    '<?xml version="1.0" encoding="UTF-8" standalone="yes"?>'
    '<Relationships xmlns="http://schemas.openxmlformats.org/package/2006/relationships">'
    '<Relationship Id="rId1" '
    'Type="http://schemas.openxmlformats.org/officeDocument/2006/relationships/officeDocument" '
    'Target="word/document.xml"/></Relationships>'
)


def build_docx(path: Path, title: str, blocks: list[Tuple[str, str]]) -> bool:
    """Write a valid minimal .docx to `path`. Returns True on success."""
    try:
        document_xml = _build_document_xml(title, blocks)
        with zipfile.ZipFile(str(path), "w", zipfile.ZIP_DEFLATED) as zf:
            zf.writestr("[Content_Types].xml", _CONTENT_TYPES)
            zf.writestr("_rels/.rels", _RELS)
            zf.writestr("word/document.xml", document_xml)
        return True
    except Exception as exc:  # noqa: BLE001
        logger.exception("build_docx failed for %s: %s", path, exc)
        return False


def _parse_content_blocks(raw_content: str) -> list[Tuple[str, str]]:
    """Convert generated content text into clean (kind, text) blocks.

    Raw LLM output is normalized: markdown stripped, blank-line separated
    blocks classified as heading / bullet / body. Never leaks markdown.
    """
    blocks: list[Tuple[str, str]] = []
    if not raw_content:
        return blocks
    for raw_block in re.split(r"\n\s*\n", raw_content):
        raw_block = _sanitize_markdown(raw_block)
        if not raw_block:
            continue
        lines = [l for l in raw_block.splitlines() if l.strip()]
        if not lines:
            continue
        for line in lines:
            kind = _block_kind(line)
            blocks.append((kind, _sanitize_markdown(line)))
    return blocks


def verify_docx(path: Path) -> dict[str, Any]:
    """Verify a real, readable .docx artifact. Returns a facts dict."""
    facts: dict[str, Any] = {"exists": False, "valid_zip": False, "word_count": 0}
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
            facts["valid_zip"] = True
            doc = zf.read("word/document.xml").decode("utf-8", errors="replace")
        text = re.sub(r"<[^>]+>", "", doc)
        words = [w for w in text.split() if re.search(r"[A-Za-z0-9]", w)]
        facts["word_count"] = len(words)
    except Exception as exc:  # noqa: BLE001
        logger.warning("verify_docx failed: %s", exc)
    return facts


def documents_dir() -> Path:
    """Return the user's Documents folder (Windows), falling back to HOME."""
    try:
        import ctypes
        from ctypes import wintypes

        buf = ctypes.create_unicode_buffer(260)
        if ctypes.windll.shell32.SHGetFolderPathW(None, 5, None, 0, buf) == 0:  # CSIDL_MYDOCUMENTS
            p = Path(buf.value)
            if p.exists():
                return p
    except Exception:  # noqa: BLE001
        pass
    home = Path(os.path.expanduser("~"))
    cand = home / "Documents"
    return cand if cand.exists() else home


def open_document(path: Path) -> bool:
    """Open the artifact in the default editor (Word on Windows)."""
    try:
        if os.name == "nt":
            os.startfile(str(path))  # noqa: S606 - opening a verified local artifact
        else:
            import subprocess
            subprocess.Popen(["xdg-open", str(path)])
        return True
    except Exception as exc:  # noqa: BLE001
        logger.warning("open_document failed: %s", exc)
        return False


def create_document(
    subject: str,
    raw_content: str,
    artifact: str = "document",
    style: str = "",
    out_dir: Optional[Path] = None,
) -> dict[str, Any]:
    """Create a meaningful Word document. The single canonical entry point.

    Args:
        subject: the requested topic ("renewable energy", "messi and ronaldo").
        raw_content: generated content text (LLM-produced, cleaned here).
        artifact: document kind ("report", "comparison", "poem", "document").
        style: optional formatting intent ("concise", "professional", "poem").
        out_dir: optional target directory (defaults to Documents).

    Returns a truthful result dict with the artifact path + verification facts.
    """
    subject = (subject or "").strip().rstrip(".,!?;:")
    if not subject:
        return {"success": False, "message": "I need a subject before I can create a document."}
    if not raw_content or not raw_content.strip():
        return {"success": False, "message": "I couldn't generate content for that document."}

    directory = out_dir or documents_dir()
    try:
        directory.mkdir(parents=True, exist_ok=True)
    except Exception as exc:  # noqa: BLE001
        return {"success": False, "message": f"Couldn't use the Documents folder: {exc}"}

    filename = generate_document_filename(subject, artifact, style) + ".docx"
    path = _ensure_unique(directory / filename)

    blocks = _parse_content_blocks(raw_content)
    title = (subject or "").strip()
    title = " ".join(w.capitalize() for w in re.findall(r"[A-Za-z0-9]+", title)) or "Document"

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
        "message": f"Created {path.name} with {facts['word_count']} words.",
        "path": str(path),
        "filename": path.name,
        "word_count": facts["word_count"],
        "artifact": artifact,
        "subject": subject,
    }
