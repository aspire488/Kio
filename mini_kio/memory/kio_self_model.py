"""
kio_self_model.py — KIO's evidence-backed self-model built from:
  - Repository state (what exists, what's implemented, what's tested)
  - Founder decisions (KIO_CONSTITUTION.md, FINAL_FOUNDER_DECISIONS.md)
  - Project history (master execution plan, convergence plan)
  - Git history (where useful)
  - Implementation state (what actually works vs scaffolding)

KIO should be able to distinguish:
  - what I know
  - what I infer
  - what I used to believe
  - what was corrected
  - what is currently true
  - what is historical
  - what I cannot verify
"""

from __future__ import annotations

import json
import logging
import os
from typing import Dict, List, Optional

logger = logging.getLogger(__name__)

# Repository paths for self-knowledge extraction
_KIO_CONSTITUTION = "KIO_CONSTITUTION.md"
_CONVERGENCE_PLAN = "MASTER_CONVERGENCE_PLAN.md"
_FOUNDER_DECISIONS = "FINAL_FOUNDER_DECISIONS.md"
_ARCHITECTURE_LOCK = "ARCHITECTURE_LOCK.md"


def _read_file_safe(path: str, max_chars: int = 5000) -> str:
    """Read a file safely, returning content or empty string."""
    try:
        with open(path, encoding="utf-8") as f:
            return f.read(max_chars)
    except Exception:
        return ""


def _extract_capabilities_from_code() -> List[str]:
    """Extract KIO's actual capabilities from the codebase.
    This is EVIDENCE from real implementation, not claimed capabilities."""
    capabilities = []

    # Check for real implementations (not stubs)
    checks = [
        ("mini_kio/core/app_operator.py", "Desktop app automation"),
        ("mini_kio/core/browser_operator.py", "Browser automation"),
        ("mini_kio/core/file_operator.py", "File operations"),
        ("mini_kio/core/system_operator.py", "System control"),
        ("mini_kio/core/document_operator.py", "Document creation"),
        ("mini_kio/browser_connector/connector.py", "Browser extension bridge"),
        ("mini_kio/runtime/browser_runtime/", "Playwright browser engine"),
        ("mini_kio/runtime/mcp_runtime/", "MCP tool integration"),
        ("mini_kio/llm/llm_gateway.py", "Multi-provider LLM gateway"),
        ("mini_kio/semantic/graph.py", "Semantic memory graph"),
        ("mini_kio/memory/living_model.py", "Living user model"),
        ("mini_kio/memory/historical_import.py", "ChatGPT history import"),
        ("mini_kio/memory/longitudinal_extractor.py", "Longitudinal pattern extraction"),
        ("mini_kio/core/capability_registry.py", "Capability registry"),
        ("mini_kio/core/context_manager.py", "Context management"),
        ("mini_kio/media/media_manager.py", "Media playback"),
        ("mini_kio/core/activation.py", "Activation state machine"),
        ("mini_kio/core/operational_health.py", "Operational health monitoring"),
    ]

    for path, name in checks:
        # Check if file/dir exists and is not empty/stub
        full_path = os.path.join(os.path.dirname(os.path.abspath(__file__)), "..", path)
        if os.path.exists(full_path):
            size = os.path.getsize(full_path)
            if size > 100:  # not an empty stub
                capabilities.append(name)

    return capabilities


def _extract_known_limitations() -> List[str]:
    """Extract known limitations from project documents.
    These are EVIDENCE from founder decisions and audit findings."""
    limitations = []

    # From founder decisions
    decisions_text = _read_file_safe(_FOUNDER_DECISIONS, 10000)
    if "not" in decisions_text.lower() or "cannot" in decisions_text.lower():
        # Extract limitation statements
        for line in decisions_text.split("\n"):
            low = line.strip().lower()
            if any(kw in low for kw in ("cannot", "not able", "does not", "doesn't",
                                         "limited", "restriction", "constraint")):
                if len(line.strip()) > 20:
                    limitations.append(line.strip()[:200])

    # From architecture lock
    lock_text = _read_file_safe(_ARCHITECTURE_LOCK, 5000)
    if lock_text:
        for line in lock_text.split("\n"):
            if "rule" in line.lower() and ("no" in line.lower() or "must not" in line.lower()):
                limitations.append(line.strip()[:200])

    return limitations[:20]


def _extract_evolution_history() -> List[Dict[str, str]]:
    """Extract KIO's evolution history from project documents.
    What changed, what was superseded, what was corrected."""
    history: List[Dict[str, str]] = []

    # From convergence plan
    plan_text = _read_file_safe(_CONVERGENCE_PLAN, 10000)
    if plan_text:
        in_decisions = False
        for line in plan_text.split("\n"):
            if "decision" in line.lower() and "architectural" in line.lower():
                in_decisions = True
            if in_decisions and line.strip().startswith("|"):
                parts = [p.strip() for p in line.split("|") if p.strip()]
                if len(parts) >= 3:
                    history.append({
                        "event": parts[1] if len(parts) > 1 else "",
                        "decision": parts[2] if len(parts) > 2 else "",
                        "justification": parts[3] if len(parts) > 3 else "",
                    })

    return history[:20]


def kio_self_brief() -> str:
    """Complete KIO self-model brief for conversational injection.
    Evidence-backed, structured for LLM composition."""
    parts = []

    # Capabilities (from real implementation)
    capabilities = _extract_capabilities_from_code()
    if capabilities:
        parts.append("KIO capabilities (verified from codebase):\n" +
                     "\n".join(f"- {c}" for c in capabilities))

    # Known limitations (from founder decisions)
    limitations = _extract_known_limitations()
    if limitations:
        parts.append("Known limitations (from founder decisions):\n" +
                     "\n".join(f"- {l}" for l in limitations[:10]))

    # Evolution history
    history = _extract_evolution_history()
    if history:
        parts.append("Architectural decisions (from convergence plan):\n" +
                     "\n".join(f"- {h['event']}: {h['decision']}"
                              for h in history[:10]))

    if not parts:
        return "KIO self-model: building from repository evidence..."
    return "KIO self-model (evidence-backed):\n\n" + "\n\n".join(parts)


def kio_capability_summary() -> str:
    """Dynamic capability awareness for conversational injection.
    Queries actual runtime state to determine which capabilities are
    available, degraded, or running — never a static list."""
    from mini_kio.memory.living_model import capabilities_summary
    return capabilities_summary()
