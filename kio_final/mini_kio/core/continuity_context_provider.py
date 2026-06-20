from __future__ import annotations

import logging
from typing import Any, Optional

logger = logging.getLogger(__name__)


class ContinuityContextProvider:
    """Read-only fail-safe interface to runtime state for continuity resolution.

    Every method uses lazy imports and try/except guards — no import errors or
    missing singletons will propagate.  Returns None / empty dict on any failure.
    """

    @staticmethod
    def get_pending_media_action() -> Optional[dict[str, str]]:
        """Return pending media action info: {action, query, domain} or None."""
        try:
            from mini_kio.media.media_manager import MediaManager
            mm = MediaManager.get_instance()
            ctx = mm.get_context()
            if ctx.pending_action and ctx.pending_media_query:
                domain = None
                if ctx.pending_media_topic:
                    domain = ctx.pending_media_topic
                logger.info("[CONTINUITY_RUNTIME] pending_media action=%s query=%s",
                            ctx.pending_action, ctx.pending_media_query)
                return {
                    "action": ctx.pending_action,
                    "query": ctx.pending_media_query,
                    "domain": domain,
                }
        except Exception:
            logger.debug("[CONTINUITY_RUNTIME] pending_media unavailable", exc_info=True)
        return None

    @staticmethod
    def get_media_entity() -> Optional[str]:
        """Return resolved entity name from MediaContext or None."""
        try:
            from mini_kio.media.media_manager import MediaManager
            mm = MediaManager.get_instance()
            ctx = mm.get_context()
            if ctx.last_resolved_entity:
                return ctx.last_resolved_entity.name
            if ctx.entity:
                return ctx.entity
        except Exception:
            pass
        return None

    @staticmethod
    def get_media_topic() -> Optional[str]:
        """Return current media topic or None."""
        try:
            from mini_kio.media.media_manager import MediaManager
            mm = MediaManager.get_instance()
            return mm.get_context().get_topic() or None
        except Exception:
            return None

    @staticmethod
    def get_last_successful_interaction(
        action_type: Optional[str] = None,
    ) -> Optional[dict[str, Any]]:
        """Return last successful execution from runtime context buffer."""
        try:
            from mini_kio.core.runtime import get_last_successful_interaction
            return get_last_successful_interaction(action_type=action_type)
        except Exception:
            return None

    @staticmethod
    def get_browser_active_tab_title() -> Optional[str]:
        """Return title of the active browser tab if available."""
        try:
            from mini_kio.core.routing_utils import get_browser_registry
            reg = get_browser_registry()
            if reg and hasattr(reg, "get_active_session"):
                session = reg.get_active_session()
                if session:
                    return session.get("title") or session.get("url")
        except Exception:
            pass
        return None

    @staticmethod
    def get_browser_sessions() -> list[dict[str, Any]]:
        """Return list of active browser sessions."""
        try:
            from mini_kio.core.routing_utils import get_browser_registry
            reg = get_browser_registry()
            if reg and hasattr(reg, "get_sessions"):
                return reg.get_sessions()
        except Exception:
            pass
        return []

    @staticmethod
    def get_artifact_memory_subject(subject: str) -> Optional[str]:
        """Resolve subject through artifact memory."""
        try:
            from mini_kio.media.intelligence.artifact_memory import ArtifactMemory
            mem = ArtifactMemory()
            records = mem.get_by_subject(subject)
            if records:
                return records[-1].subject
        except Exception:
            pass
        return None

    @staticmethod
    def get_runtime_context_items() -> list[dict[str, Any]]:
        """Return the current runtime context buffer."""
        try:
            from mini_kio.core.runtime import get_runtime_context_snapshot
            return get_runtime_context_snapshot()
        except Exception:
            return []
