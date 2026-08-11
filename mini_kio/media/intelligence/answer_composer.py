from __future__ import annotations
import re
import logging
from typing import Optional, Callable, List
from mini_kio.media.intelligence.media_intelligence_models import TopicType
from mini_kio.intelligence.retrieval_router import RetrievalResult

logger = logging.getLogger(__name__)

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

    def compose(self, result: RetrievalResult, query: str,
                topic: Optional[TopicType] = None,
                subject: Optional[str] = None) -> str:
        # Guard against a raw-string result: only attribute access when the
        # result is a real RetrievalResult (callers that pass plain text always
        # supply topic/subject explicitly).
        if isinstance(result, str):
            if topic is None:
                topic = TopicType.UNKNOWN
            if subject is None:
                subject = ""
        else:
            if topic is None:
                topic = result.topic
            if subject is None:
                subject = result.entity or result.title
        raw = result if isinstance(result, str) else (result.raw_content or result.summary)

        llm_answer = self._summarize_with_llm(result, query, subject)
        if llm_answer:
            logger.info("[LLM_PROVIDER] topic=%s subject=%s", topic, subject)
            offers = self._get_contextual_offers(topic, subject, raw)
            self._last_offers = offers
            self._last_subject = subject
            return llm_answer

        logger.info("[LLM_FALLBACK] deterministic formatting for topic=%s subject=%s", topic, subject)

        # Response depth follows semantic intent: a bare definition question
        # ("what is X", "what does X do") gets ONE key sentence; an expanded
        # request ("tell me more", "everything about X", "history of X")
        # gets up to three. Never dump the full retrieved page.
        ql = query.lower()
        expanded = any(k in ql for k in (
            "tell me more", "tell me about", "everything", "all about",
            "history", "explain in detail", "in depth", "more about",
            "compare", "background", "full details", "give me everything",
        ))
        max_sentences = 3 if expanded else 1
        title = None if isinstance(result, str) else getattr(result, "title", None)
        sentences = self._extract_key_sentences(raw, title, subject=subject)
        if not sentences:
            return f"I couldn't find a solid answer on {subject}."
        body = " ".join(sentences[:max_sentences]).strip()

        # Follow-up offers are stored internally (for contextual acceptance
        # resolution) but NEVER appended to a knowledge answer — "Available:
        # Tell me more" style robotic tails are forbidden by response doctrine.
        offers = self._get_contextual_offers(topic, subject, raw)
        self._last_offers = offers
        self._last_subject = subject
        return body

    def _summarize_with_llm(self, result: RetrievalResult, query: str,
                            subject: Optional[str] = None) -> Optional[str]:
        if not self._llm_fn:
            return None
        topic = result.topic
        if not subject:
            subject = result.entity or result.title
        raw = result.raw_content or result.summary
        if not raw or len(raw) < 50:
            return None
        raw = re.sub(r"<[^>]+>", "", raw)
        raw = re.sub(r"\s+", " ", raw).strip()
        max_input = raw[:4000]

        prompt = (
            f"Source text about {subject}:\n\n{max_input}\n\n"
            f"Answer naturally about {subject} (topic: {topic.value}).\n"
            "Write a concise, conversational reply like a knowledgeable friend "
            "(2-4 sentences). No headings, no 'Quick rundown', no bullet lists, "
            "no markdown, no URLs."
        )
        try:
            answer = self._llm_fn(prompt)
            if answer and len(answer) > 30:
                answer = answer.strip()
                # Reject truncated replies: a real 2-4 sentence answer ends with
                # terminal punctuation. A cut-off stream ("Hey! Notepad is a
                # super simple text") would otherwise surface as a broken reply —
                # fall back to the deterministic extractor instead.
                if not answer.endswith((".", "!", "?")) and len(answer) < 120:
                    return None
                return answer
        except Exception:
            pass
        return None

    def _extract_key_sentences(self, text: str,
                               title: Optional[str] = None,
                               subject: Optional[str] = None) -> List[str]:
        """Return clean, answerable sentences from retrieved raw content.

        Filters generically (never app-specific): leading page-title prefixes,
        markdown table rows, navigation/CTA fragments, trace ids, heading
        labels, and cookie/promo text are all source structure that must never
        leak into a KIO answer.
        """
        if not text:
            return []
        text = re.sub(r"<[^>]+>", "", text)
        text = re.sub(r"\[([^\]]+)\]\([^)]+\)", r"\1", text)

        # Normalize whitespace while preserving line breaks so chrome can be
        # filtered per line before sentences are merged.
        text = re.sub(r"\r\n?", "\n", text)
        lines = [ln.strip() for ln in text.split("\n")]

        # Retrievers frequently echo the page <title> as its OWN first line of
        # the content ("Draw, Create and Edit with Paint | Microsoft Windows").
        # A standalone title line is pure source chrome and must never surface
        # in an answer. Only strip when the title is a full standalone line —
        # never when it merely happens to be the first word of a real sentence
        # ("Paint is a raster graphics editor...").
        if title:
            t = re.sub(r"\s+", " ", title).strip()
            first_non_empty = next((ln for ln in lines if ln), "")
            if t and first_non_empty.lower() == t.lower():
                lines[lines.index(first_non_empty)] = ""

        # Generic chrome line prefixes that must never surface in an answer:
        # trace ids, navigation/CTA prompts ("Available:", "Get", "Tell me
        # more"), heading labels, image/cookie/promo text. "included in" and
        # "now comes with" are deliberately NOT here — they often start real
        # content sentences ("Included in the latest version of Windows 11,
        # Paint is your new creative partner.").
        _CHROME_START = re.compile(
            r"(?i)^(?:this\s+is\s+the\s+trace\s+id|trace\s+id|available:|get\s+|tell\s+me\s+more|key\s+facts|history|image\s+creator|##|#|\*\*)"
        )
        # Short CTA/nav fragments that only make sense as page furniture.
        _CTA = re.compile(r"(?i)^(?:learn\s+more|read\s+more|see\s+more|sign\s+in|get\s+[a-z0-9]+|back\s+to\s+\w+|skip\s+to|share|copy\s+link)\s*$")
        kept_lines = []
        for ln in lines:
            ln = ln.strip()
            if not ln:
                continue
            # Markdown table rows / citation fragments ("| Windows Notepad | -",
            # "| Title | Link") leak raw source structure.
            if re.fullmatch(r"\s*\|.*\|.*", ln):
                continue
            # Language/nav/list rows ("Afrikaans | Afrikaans Amharic | አማርኛ...")
            # are raw source chrome: multiple short pipe-separated fragments
            # with no sentence punctuation. Never surface them.
            if ln.count("|") >= 2 and not re.search(r"[.!?]\s*$", ln):
                continue
            if _CHROME_START.match(ln) or _CTA.match(ln):
                continue
            if ln.startswith(("http://", "https://", "www.")):
                continue
            kept_lines.append(ln)

        merged = " ".join(kept_lines)
        merged = re.sub(r"\s+", " ", merged).strip()
        merged = re.sub(r"(?i)- (Channel|Length|Views|Likes|Published|Category|Keywords):\s*[^\n]+", "", merged)

        # Sources commonly repeat the page title as a heading before the intro
        # line ("Windows Notepad\n\nWindows Notepad (commonly known simply as
        # Notepad)..."). With no terminal punctuation between them the two
        # fragments merge into one sentence, surfacing as a duplicated subject
        # ("Windows Notepad Windows Notepad ..."). Collapse the doubled
        # leading fragment generically — but only when the fragment is a
        # multi-word phrase, so a legitimate repeated word ("The The" band,
        # "Never Say Never") is never mangled.
        _dup = re.match(r"^([A-Za-z][^.!?\n]{1,58}?)\s+\1", merged, re.IGNORECASE)
        if _dup and " " in _dup.group(1).strip():
            merged = merged[_dup.end(1):].lstrip()

        sentences = re.split(r"(?<=[.!?])\s+", merged)
        cleaned = []
        for s in sentences:
            s = s.strip()
            if len(s) > 20 and not s.startswith(("- Channel", "- Length", "- Views", "- Likes")):
                cleaned.append(s)

        # Prefer sentences that actually name the queried subject: a generic
        # page lead-in ("VideoLAN, a project and a non-profit organisation.")
        # is often the first sentence but does not answer "What is VLC?" as
        # directly as one that mentions VLC itself. Prefer a definitional lead
        # that STARTS with the subject's first token ("VLC is a free..."),
        # then any sentence mentioning the subject. Bounded and generic —
        # never app-specific.
        if subject and len(cleaned) > 1:
            key = subject.lower().strip()
            first_token = key.split()[0] if key.split() else key
            def _mentions(s):
                low = s.lower()
                return key in low or (len(first_token) >= 3 and low.startswith(first_token))
            # 1) definitional lead: sentence begins with the subject token
            for s in cleaned:
                if s.lower().startswith(first_token) and len(first_token) >= 3:
                    return [s] + [x for x in cleaned if x != s]
            # 2) any sentence that mentions the subject
            for s in cleaned:
                if key in s.lower():
                    return [s] + [x for x in cleaned if x != s]
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
