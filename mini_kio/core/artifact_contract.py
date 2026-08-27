"""Artifact generation contracts — formalizes the document creation
pipeline traced during discovery. Every artifact type must conform
to these interfaces so the pipeline can generate, validate, and
recover uniformly.

Contracts enforced:
  1. Content generation (LLM output must match artifact schema)
  2. Output validation (tabular data for spreadsheets, etc.)
  3. Deterministic fallback (always produce a real file)
  4. Artifact lifecycle (plan → generate → validate → build → verify)
"""

from __future__ import annotations

import enum
import re
from abc import ABC, abstractmethod
from dataclasses import dataclass, field
from typing import Any, Optional


class ArtifactType(enum.Enum):
    """Supported artifact types."""
    DOCUMENT = "document"       # .docx
    SPREADSHEET = "spreadsheet" # .xlsx
    PRESENTATION = "presentation"  # .pptx
    PDF = "pdf"
    TEXT = "text"
    CODE = "code"
    UNKNOWN = "unknown"


class GenerationStatus(enum.Enum):
    """Status of artifact generation."""
    SUCCESS = "success"
    PARTIAL = "partial"       # generated but degraded quality
    FALLBACK = "fallback"     # deterministic fallback used
    FAILED = "failed"
    UNSUPPORTED = "unsupported"


@dataclass
class ArtifactSpec:
    """Specification for an artifact to generate."""
    artifact_type: ArtifactType
    prompt: str
    filename: Optional[str] = None
    extra: dict[str, Any] = field(default_factory=dict)


@dataclass
class ArtifactResult:
    """Result of artifact generation."""
    status: GenerationStatus
    file_path: Optional[str] = None
    filename: Optional[str] = None
    content_hash: Optional[str] = None  # for deduplication
    generation_method: str = "llm"  # "llm", "deterministic", "hybrid"
    error_message: Optional[str] = None
    metadata: dict[str, Any] = field(default_factory=dict)


@dataclass
class ContentSchema:
    """Schema for validating LLM output for a specific artifact type."""
    artifact_type: ArtifactType
    required_fields: list[str] = field(default_factory=list)
    min_rows: int = 0  # minimum data rows (for spreadsheets)
    min_columns: int = 0  # minimum columns
    format_rules: dict[str, Any] = field(default_factory=dict)


# ── Artifact schemas ────────────────────────────────────────────────────────

ARTIFACT_SCHEMAS: dict[ArtifactType, ContentSchema] = {
    ArtifactType.SPREADSHEET: ContentSchema(
        artifact_type=ArtifactType.SPREADSHEET,
        required_fields=["header_row", "data_rows"],
        min_rows=2,  # header + at least 1 data row
        min_columns=2,
        format_rules={
            "separator": "tab",  # tab-separated values
            "no_prose": True,  # no instructions/explanations
            "numeric_cells": True,  # numbers should be parseable
        },
    ),
    ArtifactType.DOCUMENT: ContentSchema(
        artifact_type=ArtifactType.DOCUMENT,
        required_fields=["title", "body"],
        format_rules={
            "has_sections": True,
            "min_paragraphs": 2,
        },
    ),
    ArtifactType.PRESENTATION: ContentSchema(
        artifact_type=ArtifactType.PRESENTATION,
        required_fields=["slides"],
        min_rows=3,  # at least 3 slides
        format_rules={
            "slide_format": "title_bullets",
        },
    ),
    ArtifactType.PDF: ContentSchema(
        artifact_type=ArtifactType.PDF,
        required_fields=["content"],
        format_rules={
            "has_sections": True,
        },
    ),
}


# ── Content validation ──────────────────────────────────────────────────────

def validate_spreadsheet_content(content: str) -> tuple[bool, str]:
    """Validate that LLM output is actual tabular data, not instructions.

    Returns (is_valid, error_message).
    """
    if not content or not content.strip():
        return False, "Empty content"

    lines = [l.strip() for l in content.splitlines() if l.strip()]
    if len(lines) < 2:
        return False, f"Need at least 2 rows (header + data), got {len(lines)}"

    # Count tab-separated rows
    tab_rows = sum(1 for l in lines if "\t" in l and len(l.split("\t")) >= 2)
    # Count pipe-separated rows (markdown tables)
    pipe_rows = sum(1 for l in lines if l.startswith("|") and l.count("|") >= 3)

    data_rows = tab_rows + pipe_rows
    if data_rows < 2:
        return False, f"Need at least 2 data rows, got {data_rows}"

    # Check for prose/instructions (more than 50% non-tabular lines)
    prose_lines = sum(1 for l in lines if "\t" not in l and not l.startswith("|"))
    if prose_lines > len(lines) * 0.5:
        return False, f"Too much prose: {prose_lines}/{len(lines)} lines are not tabular"

    # Check column consistency (header and data rows should have same column count)
    if tab_rows > 0:
        header_cols = len(lines[0].split("\t"))
        for i, line in enumerate(lines[1:], 1):
            if "\t" in line:
                cols = len(line.split("\t"))
                if abs(cols - header_cols) > 1:  # allow some tolerance
                    return False, f"Row {i+1} has {cols} columns, header has {header_cols}"

    return True, "Valid tabular content"


def _is_section_header(line: str) -> bool:
    """Check if a line is a section header in any common format:
    markdown (#/##/###), colon-ending, or ALL CAPS."""
    if line.endswith(":"):
        return True
    if line.isupper() and len(line) > 3:
        return True
    if re.match(r'^#{1,6}\s', line):
        return True
    return False


def validate_document_content(content: str) -> tuple[bool, str]:
    """Validate that LLM output is a structured document, not random text.

    Recognizes markdown headers (#/##/###), colon-ending headers,
    and ALL-CAPS headers.

    Returns (is_valid, error_message).
    """
    if not content or not content.strip():
        return False, "Empty content"

    lines = [l.strip() for l in content.splitlines() if l.strip()]
    if len(lines) < 3:
        return False, f"Document too short: {len(lines)} lines"

    # Check for section headers (markdown, colon-ending, or all caps)
    has_headers = any(_is_section_header(l) for l in lines)
    if not has_headers:
        return False, "No section headers found"

    # Check for paragraphs (blocks of text between headers)
    paragraphs = 0
    in_paragraph = False
    for line in lines:
        if _is_section_header(line):
            in_paragraph = False
        elif len(line.split()) > 5:  # substantial text line
            if not in_paragraph:
                paragraphs += 1
                in_paragraph = True

    if paragraphs < 2:
        return False, f"Need at least 2 paragraphs, found {paragraphs}"

    return True, "Valid document content"


def validate_content_for_artifact(
    content: str,
    artifact_type: ArtifactType,
) -> tuple[bool, str]:
    """Validate content against the schema for a given artifact type.

    Returns (is_valid, error_message).
    """
    if artifact_type == ArtifactType.SPREADSHEET:
        return validate_spreadsheet_content(content)
    elif artifact_type == ArtifactType.DOCUMENT:
        return validate_document_content(content)
    else:
        # No validation for other types (yet)
        return True, "No validation defined"


# ── Artifact provider contract ──────────────────────────────────────────────

class ArtifactProvider(ABC):
    """Contract that every artifact provider must implement.

    Providers handle the actual file creation for each artifact type.
    The pipeline calls generate() after content validation passes.
    """

    @abstractmethod
    def id(self) -> str:
        """Unique provider identifier (e.g., 'docx', 'xlsx', 'pptx')."""
        ...

    @abstractmethod
    def supported_types(self) -> list[ArtifactType]:
        """Artifact types this provider can create."""
        ...

    @abstractmethod
    def generate(
        self,
        spec: ArtifactSpec,
        content: str,
        output_dir: str,
    ) -> ArtifactResult:
        """Generate an artifact from validated content.

        Args:
            spec: The artifact specification
            content: Validated content from LLM or fallback
            output_dir: Directory to write the file to

        Returns:
            ArtifactResult with file path and status
        """
        ...

    def verify(self, result: ArtifactResult) -> ArtifactResult:
        """Verify the generated artifact. Default: no verification."""
        result.metadata["verification"] = "passed"
        return result

    def repair(self, result: ArtifactResult) -> ArtifactResult:
        """Attempt to repair a failed/partial artifact. Default: no repair."""
        return result

    def health(self) -> dict[str, Any]:
        return {"status": "healthy", "provider": self.id()}


# ── Deterministic fallback generators ───────────────────────────────────────

def deterministic_spreadsheet_content(prompt: str) -> str:
    """Generate minimal but valid tab-separated content when LLM fails.

    This is the last-resort fallback — it always produces parseable content.
    """
    # Extract subject from prompt
    import re
    subj = re.sub(
        r"^(create|make|write|generate|draft|open|start|new)\s+(a|an|the|my)?\s*",
        "",
        prompt.lower(),
        flags=re.IGNORECASE,
    ).strip()
    subj = re.sub(r"\s+(spreadsheet|sheet|excel|table|budget|data).*", "", subj).strip()
    if not subj:
        subj = "data"

    # Generate generic but valid tab-separated content
    return (
        f"Item\tQuantity\tCost\n"
        f"{subj.title()} Item 1\t10\t100.00\n"
        f"{subj.title()} Item 2\t5\t50.00\n"
        f"{subj.title()} Item 3\t3\t30.00\n"
        f"Total\t18\t180.00\n"
    )


def deterministic_document_content(prompt: str) -> str:
    """Generate minimal but valid document content when LLM fails."""
    import re
    subj = re.sub(
        r"^(create|make|write|generate|draft|open|start|new)\s+(a|an|the|my)?\s*",
        "",
        prompt.lower(),
        flags=re.IGNORECASE,
    ).strip()
    subj = re.sub(r"\s+(document|doc|docx|file|report|essay|article).*", "", subj).strip()
    if not subj:
        subj = "this topic"

    return (
        f"# {subj.title()}\n\n"
        f"## Overview\n\n"
        f"This document covers {subj}.\n\n"
        f"## Key Points\n\n"
        f"- Point 1: Important aspect of {subj}\n"
        f"- Point 2: Another consideration\n"
        f"- Point 3: Practical implications\n\n"
        f"## Conclusion\n\n"
        f"In summary, {subj} is a significant topic that warrants further exploration.\n"
    )
