"""
execution/workflows.py — DISABLED. Workflows will be handled via n8n.
Stub module to prevent routing into dead code.
"""

import logging

logger = logging.getLogger(__name__)


def looks_like_workflow(query: str) -> bool:
    return False


def workflow_answer(query: str, ctx=None, decision=None) -> dict:
    return {
        "success": False,
        "message": "Workflows are handled via n8n integration — not available locally yet.",
        "type": "workflow",
    }
