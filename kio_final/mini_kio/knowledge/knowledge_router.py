import logging
import re
from typing import Optional

from mini_kio.knowledge.wikipedia_provider import fetch_summary

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

        result = fetch_summary(query)
        if result:
            return result

        logger.debug("knowledge_router: no wikipedia result for '%s'", query)
        return None
