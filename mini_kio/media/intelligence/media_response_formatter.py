from __future__ import annotations
import re
from mini_kio.media.intelligence.media_intelligence_models import TopicType, ArtifactType


_TOPIC_EMOJI = {
    TopicType.MOVIES: "🎬",
    TopicType.TV: "📺",
    TopicType.GAMING: "🎮",
    TopicType.SPORTS: "⚽",
    TopicType.MUSIC: "🎵",
    TopicType.TECH: "💻",
    TopicType.NEWS: "📰",
}

_FOLLOWUP_OPTIONS: dict[TopicType, list[str]] = {
    TopicType.MOVIES: ["show the trailer", "show the teaser", "show interviews", "show reveal footage"],
    TopicType.TV: ["show the trailer", "show interviews", "find episodes"],
    TopicType.GAMING: ["show gameplay", "show the trailer", "show developer update"],
    TopicType.SPORTS: ["show highlights", "show standings", "show fixtures", "show results"],
    TopicType.MUSIC: ["play music video", "show live performance", "find more tracks"],
    TopicType.TECH: ["show the reveal", "find more updates", "show the keynote"],
    TopicType.NEWS: ["tell me more", "show related updates"],
}


def _clean_snippet(raw: str, max_chars: int = 300) -> str:
    """Strip markdown noise, truncate, return clean sentence(s)."""
    text = re.sub(r"\[.*?\]\(.*?\)", "", raw)  # strip links
    text = re.sub(r"#{1,6}\s?", "", text)       # strip headings
    text = re.sub(r"\*{1,2}(.*?)\*{1,2}", r"\1", text)  # strip bold/italic
    text = re.sub(r"\s+", " ", text).strip()
    # trim to sentence boundary near max_chars
    if len(text) > max_chars:
        cut = text[:max_chars]
        last_period = max(cut.rfind(". "), cut.rfind("! "), cut.rfind("? "))
        if last_period > max_chars // 2:
            text = cut[:last_period + 1]
        else:
            text = cut.rstrip() + "…"
    return text


def format_media_response(
    subject: str,
    raw_content: str,
    topic: TopicType,
    extra_options: list[str] | None = None,
) -> str:
    emoji = _TOPIC_EMOJI.get(topic, "📌")
    label = {TopicType.MOVIES: "What to know", TopicType.TV: "What to know",
             TopicType.MUSIC: "Quick rundown", TopicType.BOOKS: "Quick rundown",
             TopicType.SPORTS: "Match view", TopicType.GAMING: "Game info",
             TopicType.TECH: "Overview", TopicType.NEWS: "Latest",
             TopicType.PEOPLE: "About"}.\
        get(topic, "Quick rundown")
    headline = f"{emoji} {subject}: {label}"

    summary = _clean_snippet(raw_content)

    options = extra_options or _FOLLOWUP_OPTIONS.get(topic, ["tell me more"])
    options_text = ", ".join(options[:3])
    offer = f"I can {options_text}."

    return f"{headline}\n\n{summary}\n\n{offer}"


def format_artifact_response(
    subject: str,
    artifact_type: ArtifactType,
    url: str | None,
    topic: TopicType,
) -> str:
    emoji = _TOPIC_EMOJI.get(topic, "📌")
    type_label = artifact_type.value.replace("_", " ").title()
    if url:
        return f"{emoji} Playing {subject} — {type_label}"
    return f"{emoji} Searching for {subject} {type_label}…"


def format_sports_response(
    competition: str,
    summary: str,
    followup_options: list[str],
) -> str:
    opts = ", ".join(followup_options[:3])
    offer = f"\nI can show {opts}." if followup_options else ""
    return f"⚽ {competition or 'Sports Update'}\n\n{summary}{offer}"


def format_fallback(query: str, topic: TopicType | None) -> str:
    emoji = _TOPIC_EMOJI.get(topic, "📌") if topic else "📌"
    return f'{emoji} Couldn\'t retrieve results for "{query}". Try rephrasing or check your connection.'
