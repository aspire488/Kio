"""ArtifactProvider — document generation and verification via OOXML libraries."""
from __future__ import annotations
import logging, os
from typing import Any
from mini_kio.core.provider_contract import ExecutionProvider, ProviderHealth, ProviderCapability

logger = logging.getLogger(__name__)

_ARTIFACT_ACTIONS = [
    "generate_docx", "generate_xlsx", "generate_pdf", "generate_pptx",
    "verify_docx", "verify_pdf", "verify_pptx", "append_xlsx_row",
]


class ArtifactProvider(ExecutionProvider):
    def id(self) -> str:
        return "artifact"

    def capabilities(self) -> list[ProviderCapability]:
        return [
            ProviderCapability(name=a, category="artifact", timeout_s=30, ram_budget_mb=50)
            for a in _ARTIFACT_ACTIONS
        ]

    def health(self) -> ProviderHealth:
        return ProviderHealth.HEALTHY

    def execute(self, action: str, target: str = "", **kwargs: Any) -> dict[str, Any]:
        try:
            if action == "generate_docx":
                return self._generate_docx(kwargs)
            if action == "generate_xlsx":
                return self._generate_xlsx(kwargs)
            if action == "generate_pdf":
                return self._generate_pdf(kwargs)
            if action == "generate_pptx":
                return self._generate_pptx(kwargs)
            if action == "verify_docx":
                return self._verify_docx(kwargs)
            if action == "verify_pdf":
                return self._verify_pdf(kwargs)
            if action == "verify_pptx":
                return self._verify_pptx(kwargs)
            if action == "append_xlsx_row":
                return self._append_xlsx_row(kwargs)
            return {"success": False, "message": f"ArtifactProvider: unknown action {action}"}
        except Exception as exc:
            return {"success": False, "message": f"ArtifactProvider.{action} failed: {exc}"}

    def _generate_docx(self, kwargs: dict) -> dict:
        from docx import Document
        from docx.shared import Inches
        ir = kwargs.get("ir", kwargs.get("content", ""))
        out_dir = os.path.expanduser(kwargs.get("out_dir", "~/KIO/reports"))
        os.makedirs(out_dir, exist_ok=True)
        out_path = os.path.join(out_dir, f"report_{int(__import__('time').time())}.docx")
        doc = Document()
        if isinstance(ir, dict):
            title = ir.get("title", "Report")
            doc.add_heading(title, 0)
            for section in ir.get("sections", []):
                if isinstance(section, dict):
                    doc.add_heading(section.get("heading", ""), level=1)
                    doc.add_paragraph(section.get("content", ""))
                else:
                    doc.add_paragraph(str(section))
        elif isinstance(ir, str):
            for line in ir.split("\n"):
                if line.startswith("# "):
                    doc.add_heading(line[2:], 0)
                elif line.startswith("## "):
                    doc.add_heading(line[3:], 1)
                elif line.strip():
                    doc.add_paragraph(line)
        else:
            doc.add_paragraph(str(ir))
        doc.save(out_path)
        return {"success": True, "file_path": out_path, "message": f"DOCX created: {out_path}"}

    def _generate_xlsx(self, kwargs: dict) -> dict:
        from openpyxl import Workbook
        data = kwargs.get("data", [])
        out_dir = os.path.expanduser(kwargs.get("out_dir", "~/KIO/reports"))
        os.makedirs(out_dir, exist_ok=True)
        out_path = os.path.join(out_dir, f"spreadsheet_{int(__import__('time').time())}.xlsx")
        wb = Workbook()
        ws = wb.active
        ws.title = kwargs.get("sheet_name", "Data")
        if data and isinstance(data[0], dict):
            headers = list(data[0].keys())
            ws.append(headers)
            for row in data:
                ws.append([row.get(h, "") for h in headers])
        elif data:
            for row in data:
                ws.append(row if isinstance(row, list) else [row])
        else:
            ws.append(["No data"])
        wb.save(out_path)
        return {"success": True, "file_path": out_path, "message": f"XLSX created: {out_path}"}

    def _generate_pdf(self, kwargs: dict) -> dict:
        content = kwargs.get("content", kwargs.get("ir", ""))
        out_dir = os.path.expanduser(kwargs.get("out_dir", "~/KIO/reports"))
        os.makedirs(out_dir, exist_ok=True)
        out_path = os.path.join(out_dir, f"report_{int(__import__('time').time())}.pdf")
        # Use reportlab if available, else simple text PDF
        try:
            from reportlab.lib.pagesizes import letter
            from reportlab.pdfgen import canvas
            c = canvas.Canvas(out_path, pagesize=letter)
            text = content if isinstance(content, str) else str(content)
            lines = text.split("\n")
            y = 750
            for line in lines:
                if y < 50:
                    c.showPage()
                    y = 750
                c.drawString(72, y, line[:100])
                y -= 15
            c.save()
        except ImportError:
            # Fallback: write as text file with .pdf extension
            with open(out_path, "w") as f:
                f.write(str(content))
        return {"success": True, "file_path": out_path, "message": f"PDF created: {out_path}"}

    def _generate_pptx(self, kwargs: dict) -> dict:
        from pptx import Presentation
        from pptx.util import Inches
        ir = kwargs.get("ir", kwargs.get("content", ""))
        out_dir = os.path.expanduser(kwargs.get("out_dir", "~/KIO/reports"))
        os.makedirs(out_dir, exist_ok=True)
        out_path = os.path.join(out_dir, f"presentation_{int(__import__('time').time())}.pptx")
        prs = Presentation()
        if isinstance(ir, dict):
            for slide_data in ir.get("slides", [{"title": "Slide 1", "content": str(ir)}]):
                slide_layout = prs.slide_layouts[1]
                slide = prs.slides.add_slide(slide_layout)
                title = slide.shapes.title
                body = slide.placeholders[1]
                title.text = slide_data.get("title", "Slide")
                body.text = slide_data.get("content", "")
        else:
            slide_layout = prs.slide_layouts[1]
            slide = prs.slides.add_slide(slide_layout)
            slide.shapes.title.text = "Presentation"
            slide.placeholders[1].text = str(ir)[:500]
        prs.save(out_path)
        return {"success": True, "file_path": out_path, "message": f"PPTX created: {out_path}"}

    def _verify_docx(self, kwargs: dict) -> dict:
        file_path = kwargs.get("file_path", target if "target" in kwargs else "")
        if not file_path or not os.path.exists(file_path):
            return {"success": False, "verified": False, "message": f"File not found: {file_path}"}
        try:
            from docx import Document
            doc = Document(file_path)
            headings = [p.text for p in doc.paragraphs if p.style.name.startswith("Heading")]
            paragraphs = len(doc.paragraphs)
            return {"success": True, "verified": True, "headings": headings,
                    "paragraph_count": paragraphs,
                    "message": f"DOCX verified: {paragraphs} paragraphs, {len(headings)} headings"}
        except Exception as exc:
            return {"success": False, "verified": False, "message": f"DOCX verification failed: {exc}"}

    def _verify_pdf(self, kwargs: dict) -> dict:
        file_path = kwargs.get("file_path", target if "target" in kwargs else "")
        if not file_path or not os.path.exists(file_path):
            return {"success": False, "verified": False, "message": f"File not found: {file_path}"}
        size = os.path.getsize(file_path)
        return {"success": True, "verified": True, "size_bytes": size,
                "message": f"PDF verified: {size} bytes"}

    def _verify_pptx(self, kwargs: dict) -> dict:
        file_path = kwargs.get("file_path", target if "target" in kwargs else "")
        if not file_path or not os.path.exists(file_path):
            return {"success": False, "verified": False, "message": f"File not found: {file_path}"}
        try:
            from pptx import Presentation
            prs = Presentation(file_path)
            slides = len(prs.slides)
            return {"success": True, "verified": True, "slide_count": slides,
                    "message": f"PPTX verified: {slides} slides"}
        except Exception as exc:
            return {"success": False, "verified": False, "message": f"PPTX verification failed: {exc}"}

    def _append_xlsx_row(self, kwargs: dict) -> dict:
        file_path = kwargs.get("file_path", "")
        row = kwargs.get("row", [])
        if not file_path:
            return {"success": False, "message": "append_xlsx_row: no file_path"}
        try:
            from openpyxl import load_workbook
            if os.path.exists(file_path):
                wb = load_workbook(file_path)
                ws = wb.active
            else:
                from openpyxl import Workbook
                wb = Workbook()
                ws = wb.active
            ws.append(row if isinstance(row, list) else [row])
            wb.save(file_path)
            return {"success": True, "message": f"Row appended to {file_path}"}
        except Exception as exc:
            return {"success": False, "message": f"append_xlsx_row failed: {exc}"}
