"""Template loading and validation from automation/library/ YAML files."""

from __future__ import annotations

import logging
import re
import time
from pathlib import Path
from typing import Any

import yaml

logger = logging.getLogger(__name__)

# Path to the automation library relative to this file
_LIBRARY_ROOT = Path(__file__).resolve().parent.parent.parent / "automation" / "library"
if not _LIBRARY_ROOT.exists():
    # Fallback: check Downloads location
    _DOWNLOADS_ROOT = Path.home() / "Downloads" / "kio_final" / "automation" / "library"
    if _DOWNLOADS_ROOT.exists():
        _LIBRARY_ROOT = _DOWNLOADS_ROOT

# Valid capability names (must match kio_template.schema.json)
VALID_CAPABILITIES = frozenset({
    "ai_reasoning", "browser", "filesystem", "artifact", "code_project",
    "communication", "workflow", "monitoring", "github", "calendar",
    "email", "mcp_tool", "media", "memory", "http",
    "knowledge", "terminal",
    # Google ecosystem capabilities (additive; existing YAMLs are unaffected)
    "drive", "contacts", "photos", "places",
})

# Valid trigger types
VALID_TRIGGER_TYPES = frozenset({
    "manual", "natural_language", "schedule", "webhook", "event",
    "file_watch", "poll", "email_received", "message_received",
})

# Valid step action patterns
_STEP_ID_RE = re.compile(r"^[a-z0-9_]+$")
_ID_RE = re.compile(r"^[a-z0-9]+(\.[a-z0-9_]+)+$")
_VERSION_RE = re.compile(r"^\d+\.\d+\.\d+$")
_TEMPLATE_REF_RE = re.compile(r"\{\{\s*([a-z0-9_]+(?:\.[a-z0-9_]+)*)\s*\}\}")


class TemplateLoadError(Exception):
    """Raised when a template fails to load or validate."""


class TemplateRecord:
    """A loaded and validated template with metadata."""

    __slots__ = (
        "template", "path", "category", "template_id",
        "load_time", "capabilities_required", "credentials_required",
        "providers_required", "steps", "trigger", "verification",
        "failure_recovery", "security_classification",
        "user_confirmation_required", "resource_expectations",
        "inputs", "config", "outputs", "provenance",
    )

    def __init__(self, template: dict[str, Any], path: Path) -> None:
        self.template = template
        self.path = path
        self.category = template.get("category", "unknown")
        self.template_id = template["id"]
        self.load_time = time.time()
        self.capabilities_required = template.get("capabilities_required", [])
        self.credentials_required = template.get("credentials_required", [])
        self.providers_required = template.get("providers_required", [])
        self.steps = template.get("steps", [])
        self.trigger = template.get("trigger", {})
        self.verification = template.get("verification", [])
        self.failure_recovery = template.get("failure_recovery", {})
        self.security_classification = template.get("security_classification", "read_only")
        self.user_confirmation_required = template.get("user_confirmation_required", False)
        self.resource_expectations = template.get("resource_expectations", {})
        self.inputs = template.get("inputs", [])
        self.config = template.get("config", [])
        self.outputs = template.get("outputs", [])
        self.provenance = template.get("provenance", {})

    def __repr__(self) -> str:
        return f"TemplateRecord(id={self.template_id!r}, category={self.category!r})"


class TemplateStore:
    """Load and manage all YAML templates from automation/library/.

    One instance per engine. Thread-safe after load(). Templates are loaded
    once at startup and cached. Reloading re-reads all YAML files.
    """

    def __init__(self, library_root: Path | None = None) -> None:
        self._root = library_root or _LIBRARY_ROOT
        self._templates: dict[str, TemplateRecord] = {}
        self._by_category: dict[str, list[TemplateRecord]] = {}
        self._loaded = False
        self._load_errors: dict[str, str] = {}

    @property
    def loaded(self) -> bool:
        return self._loaded

    @property
    def count(self) -> int:
        return len(self._templates)

    @property
    def load_errors(self) -> dict[str, str]:
        return dict(self._load_errors)

    def load(self) -> int:
        """Load all YAML templates from the library. Returns count loaded.

        Raises FileNotFoundError if the library root doesn't exist.
        """
        if not self._root.exists():
            raise FileNotFoundError(f"Library root not found: {self._root}")

        self._templates.clear()
        self._by_category.clear()
        self._load_errors.clear()

        count = 0
        for yaml_path in sorted(self._root.rglob("*.yaml")):
            try:
                record = self._load_one(yaml_path)
                if record is not None:
                    self._templates[record.template_id] = record
                    self._by_category.setdefault(record.category, []).append(record)
                    count += 1
            except Exception as exc:
                rel = str(yaml_path.relative_to(self._root))
                self._load_errors[rel] = str(exc)
                logger.warning("[TEMPLATE_STORE] failed to load %s: %s", rel, exc)

        self._loaded = True
        logger.info(
            "[TEMPLATE_STORE] loaded %d templates (%d errors) from %s",
            count, len(self._load_errors), self._root,
        )
        return count

    def get(self, template_id: str) -> TemplateRecord | None:
        return self._templates.get(template_id)

    def list_ids(self) -> list[str]:
        return sorted(self._templates.keys())

    def list_by_category(self, category: str) -> list[TemplateRecord]:
        return list(self._by_category.get(category, []))

    def categories(self) -> list[str]:
        return sorted(self._by_category.keys())

    def all_records(self) -> list[TemplateRecord]:
        return list(self._templates.values())

    def _load_one(self, path: Path) -> TemplateRecord | None:
        """Load and validate a single YAML template file."""
        with open(path, "r", encoding="utf-8") as f:
            data = yaml.safe_load(f)

        if not isinstance(data, dict):
            raise TemplateLoadError("Template is not a YAML mapping")

        # Validate required top-level fields
        missing = [k for k in ("id", "name", "description", "category", "version",
                               "trigger", "steps", "capabilities_required",
                               "credentials_required", "outputs", "verification",
                               "failure_recovery", "security_classification",
                               "user_confirmation_required", "config", "provenance")
                   if k not in data]
        if missing:
            raise TemplateLoadError(f"Missing required fields: {missing}")

        # Validate id format
        tid = data["id"]
        if not _ID_RE.match(tid):
            raise TemplateLoadError(f"Invalid id format: {tid!r} (must be dotted.lower_snake)")

        # Validate version
        ver = data["version"]
        if not _VERSION_RE.match(ver):
            raise TemplateLoadError(f"Invalid version: {ver!r} (must be X.Y.Z)")

        # Validate capabilities
        caps = data.get("capabilities_required", [])
        bad_caps = [c for c in caps if c not in VALID_CAPABILITIES]
        if bad_caps:
            raise TemplateLoadError(f"Unknown capabilities: {bad_caps}")

        # Validate steps
        steps = data.get("steps", [])
        if not steps:
            raise TemplateLoadError("Template has no steps")

        step_ids = set()
        for step in steps:
            sid = step.get("id", "")
            if not _STEP_ID_RE.match(sid):
                raise TemplateLoadError(f"Invalid step id: {sid!r}")
            if sid in step_ids:
                raise TemplateLoadError(f"Duplicate step id: {sid}")
            step_ids.add(sid)
            if "capability" not in step:
                raise TemplateLoadError(f"Step {sid!r} missing 'capability'")
            if "action" not in step:
                raise TemplateLoadError(f"Step {sid!r} missing 'action'")
            cap = step["capability"]
            if cap not in VALID_CAPABILITIES:
                raise TemplateLoadError(f"Step {sid!r} unknown capability: {cap!r}")

        # Validate depends_on references exist
        for step in steps:
            for dep in step.get("depends_on", []):
                if dep not in step_ids:
                    raise TemplateLoadError(
                        f"Step {step['id']!r} depends on unknown step {dep!r}"
                    )

        # Validate trigger type
        trigger = data.get("trigger", {})
        ttype = trigger.get("type", "")
        if ttype not in VALID_TRIGGER_TYPES:
            raise TemplateLoadError(f"Unknown trigger type: {ttype!r}")

        return TemplateRecord(data, path)
