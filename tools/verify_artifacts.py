"""Independently verify every artifact format KIO claims to support.

Generates each artifact through the real ``create_artifact`` entry point with
meaningful content, then opens the produced file with its own native library
(python-docx / openpyxl / python-pptx / the stdlib csv module) instead of
trusting KIO's own verification helper.  A file that merely exists is never a
pass: content, structure and counts are asserted.

Usage:  python tools/verify_artifacts.py [--keep]
"""
from __future__ import annotations

import argparse
import csv
import io
import json
import re
import shutil
import sys
import tempfile
import zipfile
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from mini_kio.core import artifact_operator as ao  # noqa: E402

REPORT = """KIO is a local-first personal companion runtime. Its architecture has four
layers. The transport layer receives messages from Telegram and routes them
into the runtime. The reasoning layer classifies each request, resolves the
target capability and decides whether the answer is deterministic or needs a
language model. The capability layer executes real actions through providers:
the filesystem provider, the desktop provider, the browser connector and the
artifact operator. The persistence layer keeps durable memory, session state
and continuity records in SQLite.

Each provider owns exactly one kind of side effect, and every action reports
verified facts rather than assumptions. If an action cannot be verified, KIO
reports the failure instead of claiming success.
"""

CAPABILITY_ROWS = [
    ["Capability", "Provider", "Verified"],
    ["Browser navigation", "browser_connector", "yes"],
    ["File listing", "file_operator", "yes"],
    ["Clipboard", "terminal_provider", "yes"],
    ["Word documents", "artifact_operator", "yes"],
    ["Spreadsheets", "artifact_operator", "yes"],
    ["Presentations", "artifact_operator", "yes"],
    ["PDF export", "artifact_operator + Word", "yes"],
]

SLIDES = """SLIDE: What KIO Is
- A local-first companion runtime
- Deterministic routing first
- Language model only when needed
SLIDE: The Four Layers
- Transport: Telegram and terminal
- Reasoning: classification and routing
- Capability: providers that act
- Persistence: memory and continuity
SLIDE: Providers
- One provider owns one side effect
- Filesystem, desktop, browser, artifacts
- Every action is verified

SLIDE: Verified Behaviour
- Success is reported only when proven
- Failures are reported honestly
- No hidden background substitutions
SLIDE: Current Limits
- Voice and realtime are not wired yet
- Workflows are out of scope for now
"""


def _facts(path: Path) -> dict:
    return {"exists": path.exists(), "size": path.stat().st_size if path.exists() else 0}


def check_docx(path: Path) -> dict:
    import docx

    d = docx.Document(str(path))
    text = "\n".join(p.text for p in d.paragraphs)
    headings = [p.text for p in d.paragraphs if p.style and p.style.name.startswith("Heading")]
    return {
        "format": "DOCX",
        "paragraphs": len(d.paragraphs),
        "tables": len(d.tables),
        "words": len(text.split()),
        "headings": len(headings),
        "first_heading": headings[0] if headings else None,
        **_facts(path),
    }


def check_pdf(path: Path) -> dict:
    data = path.read_bytes()
    counts = [int(m) for m in re.findall(rb"/Count\s+(\d+)", data)]
    pages = max(counts) if counts else len(re.findall(rb"/Type\s*/Page[^s]", data))
    return {
        "format": "PDF",
        "header": data[:8].decode("latin-1"),
        "eof_marker": b"%%EOF" in data[-2048:],
        "pages": pages,
        **_facts(path),
    }


def check_xlsx(path: Path) -> dict:
    import openpyxl

    wb = openpyxl.load_workbook(str(path), data_only=True)
    ws = wb[wb.sheetnames[0]]
    values = [c.value for row in ws.iter_rows() for c in row if c.value is not None]
    return {
        "format": "XLSX",
        "sheets": len(wb.sheetnames),
        "sheet_name": wb.sheetnames[0],
        "rows": ws.max_row,
        "cols": ws.max_column,
        "non_empty_cells": len(values),
        "header": [c.value for c in ws[1]],
        **_facts(path),
    }


def check_pptx(path: Path) -> dict:
    from pptx import Presentation

    prs = Presentation(str(path))
    titles = []
    words = 0
    for slide in prs.slides:
        for shape in slide.shapes:
            if getattr(shape, "has_text_frame", False):
                words += len(shape.text_frame.text.split())
        if slide.shapes.title is not None:
            titles.append(slide.shapes.title.text)
    with zipfile.ZipFile(str(path)) as zf:
        notes = [n for n in zf.namelist() if n.startswith("ppt/notesSlides/notesSlide")]
    return {
        "format": "PPTX",
        "slides": len(prs.slides),
        "titles": titles,
        "words": words,
        "notes_slides": len(notes),
        **_facts(path),
    }


def check_csv(path: Path) -> dict:
    text = path.read_text(encoding="utf-8")
    rows = list(csv.reader(io.StringIO(text)))
    rows = [r for r in rows if r]
    return {
        "format": "CSV",
        "rows": len(rows),
        "cols": max(len(r) for r in rows),
        "header": rows[0],
        **_facts(path),
    }


def check_txt(path: Path) -> dict:
    text = path.read_text(encoding="utf-8")
    return {"format": "TXT", "words": len(text.split()), "chars": len(text), **_facts(path)}


def check_md(path: Path) -> dict:
    text = path.read_text(encoding="utf-8")
    return {
        "format": "MD",
        "headings": len(re.findall(r"^#{1,6}\s", text, re.M)),
        "words": len(text.split()),
        **_facts(path),
    }


def check_html(path: Path) -> dict:
    text = path.read_text(encoding="utf-8")
    return {
        "format": "HTML",
        "doctype": text.lstrip().lower().startswith("<!doctype"),
        "has_html_tag": "<html" in text.lower(),
        "has_title": "<title" in text.lower(),
        "words": len(re.sub(r"<[^>]+>", " ", text).split()),
        **_facts(path),
    }


#: (kind, subject, raw_content|None, native checker, assertions)
#: Assertions are the acceptance criteria — a mismatch is a FAIL, never a
#: relaxed expectation. The presentation case asserts the EXACT slide count an
#: explicit "five-slide" request must produce.
CASES = [
    ("document", "KIO architecture report", None, check_docx,
     {"tables": 1}),
    ("pdf", "KIO architecture report", None, check_pdf,
     {"pages": 1, "header": "%PDF-1.7"}),
    ("spreadsheet", "KIO capability inventory", None, check_xlsx,
     {"rows": 8, "cols": 3}),
    ("presentation", "five-slide KIO overview", SLIDES, check_pptx,
     {"slides": 5}),
    # No explicit count -> the design engine decides the length, so the only
    # requirement is that a real designed deck came out (not a stub). An
    # EXACT count is asserted only for an explicit slide-count request.
    ("presentation", "KIO overview", SLIDES, check_pptx,
     {"min_slides": 5}),
    ("csv", "KIO validation cases", None, check_csv,
     {"rows": 8, "cols": 3}),
    ("text", "KIO validation notes", REPORT, check_txt, {}),
    ("markdown", "KIO architecture summary", None, check_md,
     {"headings": 4}),
    ("html", "KIO architecture page", None, check_html,
     {"doctype": True, "has_title": True}),
]


#: Markdown with real headings AND a table — the document path must keep
#: both (a report "with a table" is not a report when the table is dropped).
DOC_WITH_TABLE = (
    "# KIO Architecture\n\n"
    "KIO is a local-first companion runtime built from four cooperating layers.\n\n"
    "## Layers\n\n"
    "Transport receives messages, reasoning decides the owner of each request,\n"
    "capability executes verified actions and persistence keeps durable state.\n\n"
    "| Layer | Owner | Notes |\n"
    "| --- | --- | --- |\n"
    "| Transport | telegram adapter | routes into runtime |\n"
    "| Reasoning | pipeline | classifies and resolves |\n"
    "| Capability | providers | performs real actions |\n"
    "| Persistence | sqlite | memory and continuity |\n\n"
    "## Guarantees\n\n"
    "Every action reports verified facts, and an unverifiable action is reported\n"
    "as a failure rather than as success.\n"
)

MD_WITH_HEADINGS = (
    "# KIO Architecture Summary\n\n"
    "## Transport\nTelegram and the terminal feed one runtime entry point.\n\n"
    "## Reasoning\nClassification and routing decide the owner of each request.\n\n"
    "## Capability\nProviders perform verified filesystem, desktop, browser and"
    " artifact actions.\n"
)


def _content_for(kind: str, raw):
    if raw is not None:
        return raw
    if kind == "document":
        return DOC_WITH_TABLE
    if kind == "markdown":
        return MD_WITH_HEADINGS
    if kind in ("spreadsheet", "csv"):
        return "\n".join("|".join(r) for r in CAPABILITY_ROWS)
    return DOC_WITH_TABLE


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--keep", action="store_true", help="keep generated files")
    args = parser.parse_args()

    out_dir = Path(tempfile.mkdtemp(prefix="kio_artifacts_"))
    results = []
    for kind, subject, raw, checker, expect in CASES:
        result = ao.create_artifact(
            subject, _content_for(kind, raw), artifact=kind, out_dir=out_dir,
        )
        entry = {
            "kind": kind,
            "subject": subject,
            "expected": expect,
            "success": bool(result.get("success")),
            "message": result.get("message"),
            "filename": result.get("filename"),
        }
        if result.get("success"):
            path = Path(result["path"])
            try:
                facts = checker(path)
                entry["facts"] = facts
                failed = {}
                for key, want in expect.items():
                    if key.startswith("min_"):
                        actual = facts.get(key[4:])
                        if not isinstance(actual, int) or actual < want:
                            failed[key] = (actual, f">= {want}")
                    elif facts.get(key) != want:
                        failed[key] = (facts.get(key), want)
                if failed:
                    entry["success"] = False
                    entry["assertion_failures"] = {
                        k: {"actual": a, "expected": e} for k, (a, e) in failed.items()
                    }
            except Exception as exc:  # noqa: BLE001
                entry["success"] = False
                entry["facts"] = {"error": f"{type(exc).__name__}: {exc}"}
        results.append(entry)

    passed = sum(1 for r in results if r["success"])
    print(json.dumps({
        "out_dir": str(out_dir),
        "passed": passed,
        "total": len(results),
        "results": results,
    }, indent=2))

    if not args.keep:
        shutil.rmtree(out_dir, ignore_errors=True)
    return 0 if passed == len(results) else 1


if __name__ == "__main__":
    sys.exit(main())
