from __future__ import annotations
import re
import logging
from typing import Optional, Callable, List
from mini_kio.media.intelligence.media_intelligence_models import TopicType
from mini_kio.intelligence.retrieval_router import RetrievalResult

logger = logging.getLogger(__name__)

_TOPIC_EMOJI = {
    TopicType.MOVIES: "🎬", TopicType.TV: "📺", TopicType.MUSIC: "🎵",
    TopicType.SPORTS: "⚽", TopicType.GAMING: "🎮", TopicType.BOOKS: "📚",
    TopicType.PEOPLE: "👤", TopicType.TECH: "💻", TopicType.NEWS: "📰",
    TopicType.UNKNOWN: "📍",
}

_DOMAIN_ACTIONS = {
    TopicType.MOVIES: ["Show trailer", "Similar movies", "Cast", "Soundtrack", "Behind the scenes"],
    TopicType.TV: ["Episodes", "Cast", "Trailer", "Similar shows", "Latest updates"],
    TopicType.MUSIC: ["Top songs", "Albums", "Similar artists", "Live performances", "Lyrics meaning"],
    TopicType.BOOKS: ["Summary", "Key lessons", "Similar books", "Author", "Quotes"],
    TopicType.SPORTS: ["Highlights", "Stats", "Recent matches", "Standings", "Compare players"],
    TopicType.GAMING: ["Trailer", "Gameplay", "Similar games", "Reviews", "System requirements"],
    TopicType.PEOPLE: ["Biography", "Career highlights", "Interviews", "Related people", "Latest news"],
    TopicType.TECH: ["Overview", "Specs", "Latest news", "Reviews"],
    TopicType.NEWS: ["Summary", "Context", "Related stories", "Latest updates"],
    TopicType.UNKNOWN: ["Tell me more", "Key facts", "History"],
}

class AnswerComposer:

    def __init__(self, llm_fn: Optional[Callable[[str], Optional[str]]] = None):
        self._llm_fn = llm_fn
        self._last_offers: List[str] = []

    def compose(self, result: RetrievalResult, query: str) -> str:
        topic = result.topic
        subject = result.entity or result.title
        raw = result.raw_content or result.summary

        llm_answer = self._summarize_with_llm(result, query)
        if llm_answer:
            logger.info("[LLM_PROVIDER] topic=%s subject=%s", topic, subject)
            offers = self._get_contextual_offers(topic, subject, raw)
            self._last_offers = offers
            return llm_answer

        logger.info("[LLM_FALLBACK] deterministic formatting for topic=%s subject=%s", topic, subject)
        emoji = _TOPIC_EMOJI.get(topic, "📍")
        lines = [f"{emoji} {subject}"]
        lines.append("")

        sentences = self._extract_key_sentences(raw)
        for s in sentences[:3]:
            lines.append(s)

        offers = self._get_contextual_offers(topic, subject, raw)
        if offers:
            lines.append("")
            available = "   " + "\n   ".join(offers)
            lines.append(f"Available: {available}")

        self._last_offers = offers
        return "\n".join(lines)

    def _summarize_with_llm(self, result: RetrievalResult, query: str) -> Optional[str]:
        if not self._llm_fn:
            return None
        topic = result.topic
        subject = result.entity or result.title
        raw = result.raw_content or result.summary
        if not raw or len(raw) < 50:
            return None
        raw = re.sub(r"<[^>]+>", "", raw)
        raw = re.sub(r"\s+", " ", raw).strip()
        max_input = raw[:4000]

        _topic_formats = {
            TopicType.MOVIES: "MOVIE TITLE\n\nQuick rundown\n[2-3 sentence plot summary]\n\nWhy people care\n\u2022 Fact 1\n\u2022 Fact 2\n\u2022 Fact 3",
            TopicType.TV: "SHOW TITLE\n\nQuick rundown\n[2-3 sentence summary]\n\nWhy people care\n\u2022 Fact 1\n\u2022 Fact 2\n\u2022 Fact 3",
            TopicType.MUSIC: "SONG / ARTIST\n\nQuick rundown\n[2-3 sentence description]\n\nWorth knowing\n\u2022 Fact 1\n\u2022 Fact 2\n\u2022 Fact 3",
            TopicType.SPORTS: "TEAM / EVENT\n\nQuick rundown\n[2-3 sentence summary]\n\nWorth knowing\n\u2022 Fact 1\n\u2022 Fact 2\n\u2022 Fact 3",
            TopicType.GAMING: "GAME TITLE\n\nQuick rundown\n[2-3 sentence description]\n\nWhy people care\n\u2022 Fact 1\n\u2022 Fact 2\n\u2022 Fact 3",
            TopicType.BOOKS: "BOOK TITLE\n\nQuick rundown\n[2-3 sentence summary]\n\nWhy people care\n\u2022 Fact 1\n\u2022 Fact 2\n\u2022 Fact 3",
            TopicType.PEOPLE: "PERSON NAME\n\nQuick rundown\n[2-3 sentence biography]\n\nWhy people care\n\u2022 Fact 1\n\u2022 Fact 2\n\u2022 Fact 3",
        }
        fmt = _topic_formats.get(topic, "SUBJECT NAME\n\nQuick rundown\n[2-3 sentence summary]\n\nWorth knowing\n\u2022 Fact 1\n\u2022 Fact 2\n\u2022 Fact 3")
        prompt = (
            f"Source text about {subject}:\n\n{max_input}\n\n"
            f"Write a concise answer about {subject} (topic: {topic.value}).\n"
            f"Format:\n{fmt}\n\n"
            f"No markdown. No URLs. Keep it natural."
        )
        try:
            answer = self._llm_fn(prompt)
            if answer and len(answer) > 30:
                return answer.strip()
        except Exception:
            pass
        return None

    def _extract_key_sentences(self, text: str) -> List[str]:
        if not text:
            return []
        text = re.sub(r"<[^>]+>", "", text)
        text = re.sub(r"\[([^\]]+)\]\([^)]+\)", r"\1", text)
        text = re.sub(r"\s+", " ", text).strip()
        text = re.sub(r"(?i)- (Channel|Length|Views|Likes|Published|Category|Keywords):\s*[^\n]+", "", text)
        sentences = re.split(r"(?<=[.!?])\s+", text)
        cleaned = []
        for s in sentences:
            s = s.strip()
            if len(s) > 20 and not s.startswith(("http", "www", "- Channel", "- Length", "- Views", "- Likes")):
                cleaned.append(s)
        return cleaned

    def _get_contextual_offers(self, topic: TopicType, entity: str, content: str) -> List[str]:
        return _DOMAIN_ACTIONS.get(topic, _DOMAIN_ACTIONS[TopicType.UNKNOWN])[:6]

    def get_last_offers(self) -> dict:
        return {"offers": self._last_offers, "subject": getattr(self, "_last_subject", "")}


def _is_current_info_query(query: str) -> bool:
    ql = query.lower().strip()
    _current_words = {"latest", "current", "recent", "update", "updates", "news",
                      "new", "today", "this week", "this month", "this year",
                      "2024", "2025", "2026", "fresh", "now"}
    for w in _current_words:
        if w in ql:
            return True
    return False
