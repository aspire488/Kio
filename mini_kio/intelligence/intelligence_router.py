"""
mini_kio/intelligence/intelligence_router.py

5-Layer Intelligence Fallback Router
======================================
Guarantees KIO never returns an empty response.

Layer execution order:
  1. Cloud LLM (existing ask_llm → gateway chain)
  2. Retrieval Intelligence (Exa → Tavily → DDG → Jina → Wikipedia)
  3. Internal Knowledge (identity, commands, capabilities, help)
  4. Local Reasoner (deterministic diagnostics, runtime introspection)
  5. Emergency Responder (absolute final guarantee)

Contract
---------
- route() ALWAYS returns a non-empty string.
- Each layer is attempted before the next.
- Layer failures are logged but never bubble up to caller.
- No layer touches another layer's internals.
- No autonomous action. No recursive reasoning. Pure routing.

Integration
-----------
Called from _ask_gemini() wrapper in conversation_responder.py when
ask_llm() returns None. See integration patch in llm_router.py.
"""

from __future__ import annotations

import logging
import time
from typing import Optional

logger = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# Layer timeouts — kept tight to respect <170 MB RAM / responsiveness target
# ---------------------------------------------------------------------------
_RETRIEVAL_TIMEOUT_S: float = 6.0
_REASONER_TIMEOUT_S: float = 1.0


class IntelligenceRouter:
    """
    Routes a query through 5 intelligence layers in order.
    Always returns a non-empty string.
    """

    def __init__(self) -> None:
        from mini_kio.intelligence.retrieval_synthesizer import RetrievalSynthesizer
        from mini_kio.intelligence.local_reasoner import LocalReasoner
        from mini_kio.intelligence.emergency_responder import EmergencyResponder

        self._retrieval = RetrievalSynthesizer(timeout_s=_RETRIEVAL_TIMEOUT_S)
        self._reasoner = LocalReasoner()
        self._emergency = EmergencyResponder()
        self._stats: dict[str, int] = {
            "l1_cloud_hit": 0,
            "l2_retrieval_hit": 0,
            "l3_knowledge_hit": 0,
            "l4_reasoner_hit": 0,
            "l5_emergency_hit": 0,
            "total_routed": 0,
        }

    def route(
        self,
        query: str,
        *,
        cloud_response: Optional[str] = None,
        runtime_context: Optional[dict] = None,
    ) -> str:
        """
        Route query through intelligence layers.

        Args:
            query: The user's query string.
            cloud_response: Pre-attempted cloud LLM result (None = already failed).
            runtime_context: Optional dict with keys like 'last_error', 'provider_status',
                             'runtime_state' for Layer 4 diagnostics.

        Returns:
            Non-empty string guaranteed.
        """
        self._stats["total_routed"] += 1
        start = time.monotonic()

        # ── Layer 1: Cloud LLM (passed in — already attempted by caller) ────
        if cloud_response and cloud_response.strip():
            self._stats["l1_cloud_hit"] += 1
            logger.debug(f"[IR] L1 cloud hit ({time.monotonic()-start:.3f}s)")
            return cloud_response.strip()

        # ── Layer 2: Retrieval Intelligence ──────────────────────────────────
        try:
            retrieval_result = self._retrieval.synthesize(query)
            if retrieval_result and retrieval_result.strip():
                self._stats["l2_retrieval_hit"] += 1
                logger.info(f"[IR] L2 retrieval hit ({time.monotonic()-start:.3f}s)")
                return retrieval_result.strip()
        except Exception as exc:
            logger.warning(f"[IR] L2 retrieval failed: {exc}")

        # ── Layer 3: Internal Knowledge ───────────────────────────────────────
        try:
            knowledge_result = _internal_knowledge_lookup(query)
            if knowledge_result and knowledge_result.strip():
                self._stats["l3_knowledge_hit"] += 1
                logger.info(f"[IR] L3 knowledge hit ({time.monotonic()-start:.3f}s)")
                return knowledge_result.strip()
        except Exception as exc:
            logger.warning(f"[IR] L3 knowledge failed: {exc}")

        # ── Layer 4: Local Reasoner ───────────────────────────────────────────
        try:
            reasoner_result = self._reasoner.reason(
                query, runtime_context=runtime_context or {}
            )
            if reasoner_result and reasoner_result.strip():
                self._stats["l4_reasoner_hit"] += 1
                logger.info(f"[IR] L4 reasoner hit ({time.monotonic()-start:.3f}s)")
                return reasoner_result.strip()
        except Exception as exc:
            logger.warning(f"[IR] L4 reasoner failed: {exc}")

        # ── Layer 5: Emergency Responder (cannot fail) ───────────────────────
        self._stats["l5_emergency_hit"] += 1
        result = self._emergency.respond(query, runtime_context=runtime_context or {})
        logger.info(f"[IR] L5 emergency hit ({time.monotonic()-start:.3f}s)")
        return result  # EmergencyResponder guarantees non-empty

    def get_stats(self) -> dict[str, int]:
        """Return routing statistics."""
        return dict(self._stats)


# ---------------------------------------------------------------------------
# Layer 3: Internal Knowledge — deterministic lookup against KIO assets
# ---------------------------------------------------------------------------

def _internal_knowledge_lookup(query: str) -> Optional[str]:
    """
    Query KIO's internal knowledge assets deterministically.
    Pulls from: knowledge_fallback, character_knowledge, command registry.
    No providers. No internet. No LLMs.
    """
    q = query.strip().lower()

    # ── 3a: KIO_character_knowledge canonical identity ─────────────────────
    try:
        from mini_kio.llm.KIO_character_knowledge import (
            CANONICAL_TRUTHS,
            IDENTITY,
        )

        # Identity questions
        _identity_triggers = (
            "who are you", "what are you", "what is kio", "introduce yourself",
            "tell me about yourself", "who built you", "who created you",
            "who made you", "what does kio stand for", "your name",
        )
        for trigger in _identity_triggers:
            if trigger in q:
                return (
                    f"{IDENTITY.mission_medium} "
                    f"Created by {IDENTITY.creator}."
                )

        # Capability questions (inline — resolve_capability not yet implemented)
        _capability_triggers = ("what can you do", "your capabilities", "what are you capable")
        for trigger in _capability_triggers:
            if trigger in q:
                return (
                    "KIO can open and close applications, search Google and YouTube, "
                    "play media, open folders, and execute multi-step commands."
                )

        # Limitation questions (inline — resolve_limitation not yet implemented)
        _limitation_triggers = ("what are your limitations", "what can't you", "what cannot you")
        for trigger in _limitation_triggers:
            if trigger in q:
                return (
                    "KIO operates within the capabilities available to the current runtime. "
                    "It cannot access systems, accounts, or information "
                    "that have not been made available to it."
                )

        # Canonical truth lookup
        for truth in CANONICAL_TRUTHS:
            if truth.key in q or truth.key.replace("_", " ") in q:
                return truth.statement

    except ImportError:
        pass  # KIO_character_knowledge not available — continue to next source

    # ── 3b: knowledge_fallback educational content ────────────────────────────
    try:
        from mini_kio.llm.knowledge_fallback import KnowledgeFallback
        kf = KnowledgeFallback()
        if kf.is_bootstrap_topic(query):
            result = kf.get_fallback(query)
            if result:
                return result
        # Direct knowledge lookup
        result = kf.get_knowledge(query)
        if result:
            return result
    except Exception:
        pass

    # ── 3c: _KNOWLEDGE_BASE from command_router ──────────────────────
    try:
        from mini_kio.core.command_router import _KNOWLEDGE_BASE
        sorted_keys = sorted(_KNOWLEDGE_BASE.keys(), key=len, reverse=True)
        for key in sorted_keys:
            if key in q:
                return _KNOWLEDGE_BASE[key]
    except Exception:
        pass

    # ── 3d: help / commands ───────────────────────────────────────────────────
    _help_triggers = ("help", "list commands", "what commands", "show commands")
    for trigger in _help_triggers:
        if trigger in q:
            return (
                "KIO commands: open [app], close [app], search [query], "
                "play [song/video], open [folder], status, diagnostics, help. "
                "Example: 'open chrome', 'search python tutorials'."
            )

    return None


# ---------------------------------------------------------------------------
# Module-level singleton — lazy initialized
# ---------------------------------------------------------------------------

_ROUTER: Optional[IntelligenceRouter] = None


def get_router() -> IntelligenceRouter:
    """Return the module-level IntelligenceRouter singleton."""
    global _ROUTER
    if _ROUTER is None:
        _ROUTER = IntelligenceRouter()
    return _ROUTER


def route_with_fallback(
    query: str,
    *,
    cloud_response: Optional[str] = None,
    runtime_context: Optional[dict] = None,
) -> str:
    """
    Convenience function: route through all layers.
    Guaranteed non-empty response.
    """
    return get_router().route(
        query,
        cloud_response=cloud_response,
        runtime_context=runtime_context,
    )
