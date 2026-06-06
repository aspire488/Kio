import logging
import re
from typing import Optional

from mini_kio.knowledge.wikipedia_provider import fetch_summary
from mini_kio.knowledge import exa_provider
from mini_kio.knowledge import tavily_provider
from mini_kio.knowledge import duckduckgo_provider
from mini_kio.knowledge import jina_reader_provider

logger = logging.getLogger(__name__)

_KNOWLEDGE_PATTERNS = [
    re.compile(r"^\s*what\s+is\s+.+", re.IGNORECASE),
    re.compile(r"^\s*what\s+are\s+.+", re.IGNORECASE),
    re.compile(r"^\s*what\s+do\s+.+", re.IGNORECASE),
    re.compile(r"^\s*what\s+does\s+.+", re.IGNORECASE),
    re.compile(r"^\s*who\s+is\s+.+", re.IGNORECASE),
    re.compile(r"^\s*who\s+created\s+.+", re.IGNORECASE),
    re.compile(r"^\s*who\s+wrote\s+.+", re.IGNORECASE),
    re.compile(r"^\s*who\s+made\s+.+", re.IGNORECASE),
    re.compile(r"^\s*explain\s+.+", re.IGNORECASE),
    re.compile(r"^\s*tell\s+me\s+about\s+.+", re.IGNORECASE),
    re.compile(r"^\s*define\s+.+", re.IGNORECASE),
    re.compile(r"^\s*how\s+does\s+.+\s+work\s*\??\s*$", re.IGNORECASE),
]

_NON_KNOWLEDGE_PATTERNS = [
    re.compile(r"^\s*what\s+is\s+the\s+weather\b", re.IGNORECASE),
    re.compile(r"^\s*what\s+is\s+the\s+temperature\b", re.IGNORECASE),
    re.compile(r"^\s*what\s+is\s+the\s+time\b", re.IGNORECASE),
    re.compile(r"^\s*what\s+is\s+the\s+date\b", re.IGNORECASE),
]


class KnowledgeRouter:
    def is_knowledge_query(self, query: str) -> bool:
        text = (query or "").strip()
        if not text:
            return False
        if any(pattern.search(text) for pattern in _NON_KNOWLEDGE_PATTERNS):
            return False
        return any(pattern.search(text) for pattern in _KNOWLEDGE_PATTERNS)

    def route(self, query: str) -> Optional[str]:
        if not self.is_knowledge_query(query):
            return None

        # Tier 1: External Search Providers
        # Try Exa
        result = exa_provider.search(query)
        if result:
            logger.debug("knowledge_router: result from exa for '%s'", query)
            return result

        # Try Tavily
        result = tavily_provider.search(query)
        if result:
            logger.debug("knowledge_router: result from tavily for '%s'", query)
            return result

        # Try DuckDuckGo
        result = duckduckgo_provider.search(query)
        if result:
            logger.debug("knowledge_router: result from duckduckgo for '%s'", query)
            return result
        
        # Tier 2: URL Reading (Jina)
        if query.startswith(("http://", "https://")):
            result = jina_reader_provider.read_url(query)
            if result:
                logger.debug("knowledge_router: result from Jina Reader for URL '%s'", query)
                return result

        # Tier 3: Wikipedia (Deterministic Topic extraction fallback)
        # We try Wikipedia on the full query first, then on extracted topic
        result = fetch_summary(query)
        if result:
            logger.debug("knowledge_router: result from wikipedia (full query) for '%s'", query)
            return result
            
        from mini_kio.llm.conversation_context import ConversationContext
        effective_topic = ConversationContext._extract_topic(query)
        if effective_topic and effective_topic.lower() != query.lower():
            result = fetch_summary(effective_topic)
            if result:
                logger.debug("knowledge_router: result from wikipedia (extracted topic: %s) for '%s'", effective_topic, query)
                return result

        logger.debug("knowledge_router: no knowledge result for '%s'", query)
        return None
