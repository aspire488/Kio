import logging
import re
from typing import Optional, List
from mini_kio.knowledge.knowledge_models import MultiSourceResult

logger = logging.getLogger(__name__)

# Pattern to strip structured metadata from LLM responses.
# Captures CONFIDENCE, AGREEMENT, SUMMARY, and SOURCES lines.
_METADATA_PATTERN = re.compile(
    r"^(?:CONFIDENCE|AGREEMENT|SOURCES):\s*.*(?:\n|$)",
    re.MULTILINE | re.IGNORECASE,
)
_SUMMARY_PREFIX = re.compile(r"^SUMMARY:\s*", re.IGNORECASE)


class SearchHardener:
    """Hardens search results via claim extraction, consensus analysis, and confidence scoring.

    Internal metadata (CONFIDENCE, AGREEMENT, SOURCES) is stored for debugging
    but stripped from the user-visible response.
    """

    def __init__(self):
        self.last_confidence: Optional[str] = None
        self.last_agreement: Optional[str] = None
        self.last_sources: Optional[str] = None

    def summarize(self, result: MultiSourceResult) -> str:
        # Accept plain string as passthrough (backward compat for tests)
        if isinstance(result, str):
            return result
        if result.is_empty():
            return "No search results found to summarize."

        # Import here to avoid circular dependencies
        from mini_kio.llm.conversation_responder import _ask_gemini

        # 1. Prepare sources for LLM
        source_blocks = []
        for i, s in enumerate(result.sources):
            # Bound each source to 1500 chars to avoid context overflow
            content = s.content[:1500].strip()
            source_blocks.append(f"SOURCE {i+1} ({s.name}):\n{content}")

        system_prompt = (
            "You are a Truthfulness Auditor. Analyze the following search results to produce a verified summary.\n\n"
            "INSTRUCTIONS:\n"
            "1. Extract core claims from each source.\n"
            "2. Check for CONSENSUS: Do all sources agree? If not, highlight conflicts.\n"
            "3. Assign CONFIDENCE: \n"
            "   - High: Multiple reputable sources agree on the same facts.\n"
            "   - Medium: Sources partially agree or only one source provides the info.\n"
            "   - Low: Sources conflict significantly.\n"
            "   - Unknown: No information found or sources are too vague.\n"
            "4. Generate a concise SUMMARY (1-5 lines).\n\n"
            "OUTPUT FORMAT (Strict):\n"
            "CONFIDENCE: [High/Medium/Low/Unknown]\n"
            "AGREEMENT: [Yes/No]\n"
            "SUMMARY: [Your summarized answer with source citations like (Source 1)]\n"
            "SOURCES: [List names of sources used]\n"
        )

        full_input = "\n\n".join(source_blocks)
        raw_response = _ask_gemini(full_input, system_prompt=system_prompt)

        if not raw_response:
            return "Failed to summarize search results."

        # Extract metadata for internal tracking
        self._extract_metadata(raw_response)

        # Extract just the summary text for user-visible output
        clean = self._strip_metadata(raw_response)

        # Post-process for truthfulness requirements
        if self.last_confidence == "Low":
            return "I found conflicting information. " + clean
        if self.last_confidence == "Unknown":
            return "I cannot verify that information based on the search results."

        return clean

    def _extract_metadata(self, response: str) -> None:
        """Parse and store metadata labels from LLM response."""
        for line in response.split("\n"):
            line_stripped = line.strip()
            lower = line_stripped.lower()
            if lower.startswith("confidence:"):
                self.last_confidence = line_stripped.split(":", 1)[1].strip()
            elif lower.startswith("agreement:"):
                self.last_agreement = line_stripped.split(":", 1)[1].strip()
            elif lower.startswith("sources:"):
                self.last_sources = line_stripped.split(":", 1)[1].strip()

    def _strip_metadata(self, response: str) -> str:
        """Remove CONFIDENCE/AGREEMENT/SOURCES lines; return only summary text."""
        # Remove the metadata header lines
        cleaned = _METADATA_PATTERN.sub("", response).strip()
        # Remove the "SUMMARY:" prefix if present
        cleaned = _SUMMARY_PREFIX.sub("", cleaned).strip()
        if not cleaned:
            return response
        return cleaned
