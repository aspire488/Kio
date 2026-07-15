"""
mini_kio/intelligence/emergency_responder.py

Emergency Responder — Layer 5
================================
Absolute final safety layer. CANNOT fail. CANNOT return empty.

Called only when Layers 1–4 have all failed.

Responsibilities:
  - Guarantee a non-empty response. Always.
  - State clearly what is available offline.
  - Provide actionable next steps.
  - Never crash. Never raise. Never return empty string.

Implementation:
  Pure Python. Zero imports that can fail. Zero external calls.
  Only stdlib. Only hardcoded deterministic responses.

Contract:
  respond() returns a non-empty str under all conditions.
  This is enforced by a final hardcoded sentinel fallback
  that cannot be skipped or bypassed.
"""

from __future__ import annotations

import logging

logger = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# The absolute sentinel — if all pattern matching fails, this is returned.
# It is hardcoded, it cannot be None, it cannot be empty.
# ---------------------------------------------------------------------------
_SENTINEL = (
    "KIO is operational. Cloud intelligence is currently unavailable. "
    "Local capabilities: open/close apps, web search, file navigation, help, diagnostics. "
    "Type 'help' for available commands, or 'status' for system state."
)

_OFFLINE_CAPABILITIES = (
    "• open [app] — launch an application\n"
    "• close [app] — close an application\n"
    "• search [query] — web search\n"
    "• play [media] — YouTube search\n"
    "• status — runtime state\n"
    "• diagnostics — system check\n"
    "• help — full command list"
)

_CATEGORIES: dict[str, str] = {
    "help": (
        "KIO is available. Available commands:\n"
        + _OFFLINE_CAPABILITIES
    ),
    "status": (
        "KIO is running in local-only mode. "
        "Cloud intelligence: UNAVAILABLE. "
        "Local operations: AVAILABLE. "
        "Commands: help, open [app], close [app], search [query], status, diagnostics."
    ),
    "diagnostics": (
        "KIO Diagnostics (offline mode):\n"
        "• Runtime: ACTIVE\n"
        "• Cloud providers: UNAVAILABLE\n"
        "• Retrieval providers: UNAVAILABLE\n"
        "• Local knowledge: AVAILABLE\n"
        "• Local commands: AVAILABLE\n"
        "• Browser control: depends on extension\n"
        "Suggested actions: check internet connection, verify API keys."
    ),
    "identity": (
        "I'm KIO — a personal desktop AI assistant built by Joel. "
        "Cloud intelligence is offline right now, but I can still open apps, "
        "search the web, play media, and handle desktop commands. "
        "Type 'help' for a full list."
    ),
    "greeting": (
        "KIO online. Cloud intelligence unavailable right now. "
        "Local commands still work — type 'help' for what's available."
    ),
    "error": (
        "Something went wrong, and all intelligence layers are offline. "
        "KIO's local capabilities remain available. "
        "Type 'help' for commands, 'status' for system state, "
        "or 'diagnostics' to check what's working."
    ),
    "browser": (
        "Browser control: KIO can open URLs and search the web. "
        "Tab-level control requires the KIO browser extension. "
        "Chrome cannot be closed by tab PID — use Ctrl+W or 'close chrome'. "
        "Cloud intelligence is offline — only local browser commands are available."
    ),
    "provider": (
        "All cloud AI providers are currently unavailable. "
        "KIO continues to run in local mode. "
        "Available: desktop commands, help, diagnostics, status, and identity questions. "
        "Cloud intelligence will resume when providers are reachable."
    ),
}

_QUERY_TO_CATEGORY: list[tuple[tuple[str, ...], str]] = [
    (("help", "commands", "what can you do", "list commands"), "help"),
    (("status", "runtime", "are you running", "how are you"), "status"),
    (("diagnostics", "self check", "system check", "health"), "diagnostics"),
    (("who are you", "what are you", "what is kio", "who built", "who created"), "identity"),
    (("hello", "hi", "hey", "yo", "good morning", "good evening"), "greeting"),
    (("error", "failed", "what went wrong", "why did"), "error"),
    (("chrome", "browser", "tab", "extension"), "browser"),
    (("provider", "ai failed", "no ai", "offline", "degraded"), "provider"),
]


class EmergencyResponder:
    """
    Final intelligence layer. Always responds. Never fails.

    respond() is guaranteed to return a non-empty string regardless of:
      - query content
      - runtime_context content
      - any exception in pattern matching
    """

    def __init__(self) -> None:
        self._call_count: int = 0

    def respond(self, query: str, *, runtime_context: dict | None = None) -> str:
        """
        Return a deterministic non-empty response.
        This method CANNOT raise. CANNOT return empty string.
        """
        self._call_count += 1
        ctx = runtime_context or {}

        try:
            return self._respond_impl(query, ctx)
        except Exception as exc:
            # Belt and suspenders: if pattern matching somehow throws,
            # the sentinel is returned. This path should never be reached.
            logger.error(f"[ER] Emergency responder internal error (returning sentinel): {exc}")
            return _SENTINEL

    def _respond_impl(self, query: str, ctx: dict) -> str:
        """Implementation — can only be reached from respond(), never called directly."""
        q = (query or "").strip().lower()

        # ── Category dispatch ─────────────────────────────────────────────────
        for triggers, category in _QUERY_TO_CATEGORY:
            if any(t in q for t in triggers):
                response = _CATEGORIES.get(category, _SENTINEL)
                if response and response.strip():
                    return response

        # ── Context-aware response ────────────────────────────────────────────
        runtime_state = ctx.get("runtime_state", "")
        if runtime_state == "DEGRADED":
            return (
                "KIO is in degraded mode. Cloud intelligence is unavailable. "
                "Local operations (open, close, search, play) continue to work. "
                "Type 'status' for details, or 'help' for available commands."
            )

        failure_class = ctx.get("failure_class", "")
        if failure_class:
            return (
                f"KIO intelligence layer unavailable ({failure_class}). "
                "Local capabilities remain active. "
                "Type 'help' for commands or 'diagnostics' for system state."
            )

        # ── Query too short or empty ──────────────────────────────────────────
        if len(q) < 3:
            return (
                "KIO online. Type 'help' for available commands, "
                "'status' for system state."
            )

        # ── Unknown query — generic offline response ──────────────────────────
        # Trim query to first 60 chars for the response
        q_display = query.strip()[:60] if query.strip() else "your request"
        return (
            f"I couldn't process '{q_display}' — cloud intelligence is currently offline. "
            "I can still help with: opening apps, searching the web, playing media, "
            "and running diagnostics. Type 'help' for a full list."
        )

    def get_call_count(self) -> int:
        """Return how many times the emergency responder has been invoked."""
        return self._call_count
