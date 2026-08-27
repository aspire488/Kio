import logging
import re
from typing import Optional, Dict
from mini_kio.resolvers.base import BaseResolver
from mini_kio.llm.session_state import SessionState
from mini_kio.llm.trace_context import TraceContext

logger = logging.getLogger(__name__)

_MEMORY_PATTERNS: list[tuple[re.Pattern, str]] = [
    # ── Semantic Recall (search graph claims for a topic) ──
    (re.compile(r"^\s*what\s+(?:did|do)\s+(?:i|we)\s+(?:say|mention|tell|talk|discuss)\s+(?:about|regarding|on)\s+(.+?)\s*\??\s*$", re.IGNORECASE), "semantic_recall"),
    (re.compile(r"^\s*what\s+(?:was|were|did)\s+(?:i|we)\s+(?:planning|thinking|considering|working|doing)\s+(?:about|with|on|for)\s+(.+?)\s*\??\s*$", re.IGNORECASE), "semantic_recall"),
    (re.compile(r"^\s*what\s+(?:did|do)\s+(?:i|we)\s+(?:decide|choose|settle)\s+(?:about|on|for)\s+(.+?)\s*\??\s*$", re.IGNORECASE), "semantic_recall"),
    (re.compile(r"^\s*remember\s+(?:when|that)\s+(?:i|we)\s+(.+?)\s*\??\s*$", re.IGNORECASE), "semantic_recall"),
    # ── Topic Continuity (general conversation recall) ──
    (re.compile(r"^\s*what\s+(?:were|was)\s+(?:we|you)\s+(?:discuss(?:ing)?|talk(?:ing)?|chat(?:ting)?|going)\s*\??\s*$", re.IGNORECASE), "topic_continuity"),
    (re.compile(r"^\s*what\s+(?:were|was)\s+(?:we|you)\s+(?:just\s+)?(?:talking|discussing|chatting)\s+about\s*\??\s*$", re.IGNORECASE), "topic_continuity"),
    (re.compile(r"^\s*where\s+(?:were|are)\s+we\s*\??\s*$", re.IGNORECASE), "topic_continuity"),
    (re.compile(r"^\s*back\s+to\s+(?:the\s+)?(.+?)\s*\??\s*$", re.IGNORECASE), "semantic_recall"),
    (re.compile(r"^\s*what\s+(?:did|do)\s+(?:i|we)\s+(?:just\s+)?(?:say|mention)\s*\??\s*$", re.IGNORECASE), "topic_continuity"),
    (re.compile(r"^\s*what\s+(?:was|were)\s+(?:i|we)\s+(?:just\s+)?(?:talking|discussing|working)\s+(?:about|on)\s+(.+?)\s*\??\s*$", re.IGNORECASE), "semantic_recall"),
    # ── Fact Retrieval (must precede conversation history patterns) ──
    (re.compile(r"^\s*what\s+is\s+my\s+favou?rite\s+(.+?)\s*\??\s*$", re.IGNORECASE), "fact_retrieval"),
    (re.compile(r"^\s*what'?s\s+my\s+favou?rite\s+(.+?)\s*\??\s*$", re.IGNORECASE), "fact_retrieval"),
    (re.compile(r"^\s*do\s+you\s+remember\s+my\s+favou?rite\s+(.+?)\s*\??\s*$", re.IGNORECASE), "fact_retrieval"),
    (re.compile(r"^\s*what\s+did\s+i\s+tell\s+you\s+about\s+my\s+favou?rite\s+(.+?)\s*\??\s*$", re.IGNORECASE), "fact_retrieval"),
    (re.compile(r"^\s*what\s+did\s+i\s+tell\s+you\s+about\s+my\s+(.+?)\s*\??\s*$", re.IGNORECASE), "fact_retrieval"),
    (re.compile(r"^\s*what\s+(.+?)\s+do\s+i\s+(like|love)\s*\??\s*$", re.IGNORECASE), "fact_retrieval"),
    (re.compile(r"^\s*what\s+(.+?)\s+do\s+i\s+(dislike|hate)\s*\??\s*$", re.IGNORECASE), "fact_retrieval"),
    (re.compile(r"^\s*who\s+is\s+my\s+favou?rite\s+(.+?)\s*\??\s*$", re.IGNORECASE), "fact_retrieval"),
    (re.compile(r"^\s*who'?s\s+my\s+favou?rite\s+(.+?)\s*\??\s*$", re.IGNORECASE), "fact_retrieval"),
    (re.compile(r"^\s*who\s+do\s+i\s+(like|love)\s+most\s*\??\s*$", re.IGNORECASE), "fact_top_person"),
    # ── Conversation History ──
    (re.compile(r"^\s*what\s+(was|were)\s+my\s+(first|last)\s+(command|question|message|query|input)\s*\??\s*$", re.IGNORECASE), "first_user"),
    (re.compile(r"^\s*what\s+(was|were)\s+my\s+(first|last)\s+(command|question|message|query|input)\s+", re.IGNORECASE), "first_user_last"),
    (re.compile(r"^\s*what\s+(was|were)\s+my\s+(first|last)\s+(thing)\s+(i|we)\s+(said|asked)\s*\??\s*$", re.IGNORECASE), "first_user_thing"),
    (re.compile(r"^\s*what\s+(was|were)\s+(my|the)\s+(first)\s+(message|thing)\s+(in|of)\s+(this|the)\s+(session|chat|conversation)\s*\??\s*$", re.IGNORECASE), "first_user"),
    (re.compile(r"^\s*what\s+did\s+(i|we)\s+(ask|say|talk|talked)\s+(\d+)\s+(messages|questions|commands|turns|hours|minutes|days)\s+ago\s*\??\s*$", re.IGNORECASE), "n_ago"),
    (re.compile(r"^\s*(summarize|recap|summarise)\s+(this|the)\s+(session|conversation|chat|discussion)\s*\??\s*$", re.IGNORECASE), "summarize"),
    (re.compile(r"^\s*what\s+(have|did)\s+(we|i)\s+(talked|discussed|talk)\s+about\s*\??\s*$", re.IGNORECASE), "summarize"),
]

# Preference value display mappings
_PREFERENCE_VALUES = {
    "like": "like",
    "love": "love",
    "dislike": "dislike",
    "hate": "hate",
}

# British-to-American spelling normalization for fact key matching
_SPELLING_MAP = {
    "colour": "color",
    "favourite": "favorite",
    "flavour": "flavor",
    "centre": "center",
    "metre": "meter",
    "behaviour": "behavior",
    "neighbour": "neighbor",
    "defence": "defense",
    "offence": "offense",
    "licence": "license",
    "organise": "organize",
    "recognise": "recognize",
}


def _normalize_subject(raw: str) -> str:
    subject = raw.strip().lower().replace(" ", "_")
    # Apply British→American spelling normalization
    for brit, american in _SPELLING_MAP.items():
        # Replace both variants (e.g., "colour" → "color", "colourful" → "colorful")
        subject = subject.replace(brit, american)
    return subject


def _retrieve_fact(facts: Dict[str, str], subject: str) -> Optional[tuple[str, str]]:
    """Look up a stored fact by subject. Returns (value, matched_key) or None."""
    normalized = subject.strip().lower().replace(" ", "_")

    # Build candidate subjects: original + American spelling
    candidates = {normalized, _normalize_subject(subject)}

    # 1. Exact key match — favorite_ prefix (try each candidate)
    for cand in candidates:
        key = f"favorite_{cand}"
        if key in facts:
            return facts[key], key

    # 2. Exact key match — preference_ prefix (try each candidate)
    for cand in candidates:
        key = f"preference_{cand}"
        if key in facts:
            return facts[key], key

    # 3. Partial match — any stored key containing any candidate
    for cand in candidates:
        for fact_key, fact_value in facts.items():
            if cand in fact_key:
                return fact_value, fact_key

    return None


class MemoryResolver(BaseResolver):
    """Handles deterministic memory recall queries."""

    def resolve(self, text: str, state: SessionState, trace: TraceContext) -> Optional[str]:
        text_lower = text.lower().strip()

        for pattern, action in _MEMORY_PATTERNS:
            match = pattern.search(text_lower)
            if match:
                trace.add_step(f"MemoryResolver: triggered action '{action}'")

                if action == "fact_retrieval":
                    subject = match.group(1).strip()
                    facts = state.get_all_facts()
                    if facts:
                        result = _retrieve_fact(facts, subject)
                    if result:
                        value, matched_key = result
                        logger.info("[MEMORY_HIT] subject=%s matched_key=%s", subject, matched_key)
                        if matched_key.startswith("preference_"):
                            disp_val = _PREFERENCE_VALUES.get(value.lower(), value)
                            return f"You said you {disp_val} {subject.strip().lower()}."
                        if matched_key.startswith("favorite_"):
                            _topic = matched_key[len("favorite_"):].replace("_", " ")
                            return f"Your favorite {_topic} is {value}."
                        if matched_key == "user_name":
                            return f"Your name is {value}."
                        # Generic fallback: strip underscores, never expose raw keys
                        _label = matched_key.replace("_", " ").strip()
                        if _label.startswith("my "):
                            _label = "your " + _label[3:]
                        return f"Your {_label} is {value}."
                    return None

                if action == "fact_top_person":
                    facts = state.get_all_facts()
                    if facts and "favorite_person" in facts:
                        logger.info("[MEMORY_HIT] subject=person matched_key=favorite_person")
                        return f"Your favorite person is {facts['favorite_person']}."
                    return None

                if action == "first_user":
                    msg = state.memory.first_user_message()
                    return f'Your first message was: "{msg}"' if msg else "I don't have any memory of that."

                if action == "n_ago":
                    try:
                        n = int(match.group(3))
                        entries = state.memory.last_n_messages(n)
                        if len(entries) < n:
                            return f"I only have {len(entries)} messages in memory, not {n}."
                        target = entries[0]
                        return f'{n} messages ago you said: "{target.message}"'
                    except (ValueError, IndexError):
                        pass

                if action == "summarize":
                    return state.memory.summarize_session()

                if action == "semantic_recall":
                    topic = match.group(1).strip()
                    if not topic:
                        return None
                    try:
                        from mini_kio.memory.living_model import recall_about_topic
                        # Pass session context so recall can search exchange history
                        # (not just graph claims) — critical for 'what did I just say?' queries
                        ctx = getattr(state, 'context', None)
                        results = recall_about_topic(state.session_id, topic,
                                                    session_context=ctx)
                        if results:
                            lines = [f"Regarding '{topic}':"]
                            for r in results[:5]:
                                text = r.get("text", "")
                                when = r.get("when", "")
                                rel = r.get("relation", "")
                                prov = r.get("provenance", "")
                                when_str = f" ({when})" if when else ""
                                hist = " [historical]" if prov.startswith("chatgpt_export") else ""
                                conv = " [recent conversation]" if prov == "conversation" else ""
                                lines.append(f"- You {rel} {text}{when_str}{hist}{conv}")
                            return "\n".join(lines)
                    except Exception:
                        pass
                    return None

                if action == "topic_continuity":
                    # 'what were we discussing?' / 'where were we?' / 'what did I just say?'
                    # Returns recent conversation topics and last few exchanges
                    try:
                        ctx = getattr(state, 'context', None)
                        if ctx is None:
                            return None
                        lines = []
                        # Recent topics
                        topics = ctx.recent_topics_summary(max_topics=5)
                        if topics:
                            lines.append(topics)
                        # Last 3 exchanges as context
                        recent = ctx.get_history_window(3)
                        if recent:
                            lines.append("Most recent exchanges:")
                            for user_text, kio_reply in recent:
                                u_short = user_text[:100] + ("..." if len(user_text) > 100 else "")
                                r_short = kio_reply[:100] + ("..." if len(kio_reply) > 100 else "") if kio_reply else ""
                                lines.append(f"  You: {u_short}")
                                if r_short:
                                    lines.append(f"  KIO: {r_short}")
                        if lines:
                            return "\n".join(lines)
                    except Exception:
                        pass
                    return None

                break
        return None
