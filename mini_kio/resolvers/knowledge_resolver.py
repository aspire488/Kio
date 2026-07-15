import logging
from typing import Optional
from mini_kio.resolvers.base import BaseResolver
from mini_kio.llm.session_state import SessionState
from mini_kio.llm.trace_context import TraceContext
from mini_kio.knowledge.retrieval_router import KnowledgeRouter
from mini_kio.llm.search_hardener import SearchHardener
from mini_kio.core.freshness_classifier import FreshnessLevel, classify as classify_freshness
from mini_kio.llm.llm_ops import ask_llm_sync

logger = logging.getLogger(__name__)

class KnowledgeResolver(BaseResolver):
    """Handles search-based queries with consensus and confidence scoring."""
    
    def __init__(self):
        self._router = KnowledgeRouter()
        self._hardener = SearchHardener()

    def resolve(self, text: str, state: SessionState, trace: TraceContext) -> Optional[str]:
        # 1. Freshness Check
        freshness = classify_freshness(text)
        trace.metadata["freshness_level"] = freshness.value
        
        # REQUIRED Freshness
        if freshness == FreshnessLevel.REQUIRED:
            trace.add_step("KnowledgeResolver: freshness REQUIRED, routing to multi-source search")
            res = self._router.route_freshness(text)
            if res:
                # Persist pending search so continuity can resume across restarts
                try:
                    state.set_pending_search(text, state.recent_topic() or "")
                except Exception:
                    logger.debug("Failed to set pending search for continuity", exc_info=True)

                # Support both MultiSourceResult and str (test compatibility)
                if isinstance(res, str):
                    trace.search_providers_used = ["test"]
                    return res
                trace.search_providers_used = [s.name for s in res.sources]
                summary = self._hardener.summarize(res)
                return summary
            return "I couldn't find current information on that."

        # OPTIONAL Freshness or Knowledge Query
        is_knowledge = self._router.is_knowledge_query(text)
        if is_knowledge:
            trace.add_step("KnowledgeResolver: knowledge query detected")
            
            # Try freshness route first if optional
            if freshness == FreshnessLevel.OPTIONAL:
                res = self._router.route_freshness(text)
                if res:
                    trace.add_step("KnowledgeResolver: using optional freshness results")
                    if isinstance(res, str):
                        return res
                    return self._hardener.summarize(res)
            
            # Try multi-source summarization for NONE-freshness knowledge queries
            if freshness == FreshnessLevel.NONE:
                res = self._router.route_freshness(text)
                if res:
                    trace.add_step("KnowledgeResolver: using multi-source summarization")
                    if isinstance(res, str):
                        return res
                    summarized = self._hardener.summarize(res)
                    if summarized:
                        return summarized

            # Try Wikipedia
            wiki = self._router.route(text)
            if wiki:
                trace.add_step("KnowledgeResolver: using Wikipedia fallback")
                return wiki

        return None
