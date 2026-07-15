from __future__ import annotations
import re
import time
from typing import Optional
from mini_kio.media.intelligence.media_intelligence_models import EventRecord, EventStatus

# ── known team/country corpus ─────────────────────────────────────────────────

KNOWN_TEAMS: set[str] = {
    # international
    "brazil", "argentina", "germany", "france", "england", "spain", "portugal",
    "netherlands", "belgium", "croatia", "morocco", "senegal", "nigeria",
    "japan", "south korea", "australia", "usa", "mexico", "colombia",
    "uruguay", "chile", "ecuador", "peru", "cameroon", "ghana", "ivory coast",
    "italy", "poland", "denmark", "sweden", "norway", "switzerland",
    "turkey", "ukraine", "czech republic", "hungary", "austria", "scotland",
    "wales", "ireland", "canada", "new zealand", "saudi arabia", "iran",
    "qatar", "south africa", "egypt", "algeria", "tunisia",
    # club - premier league
    "manchester city", "arsenal", "liverpool", "chelsea", "tottenham",
    "manchester united", "newcastle", "aston villa", "west ham", "brighton",
    # club - la liga
    "real madrid", "barcelona", "atletico madrid", "seville", "valencia",
    # club - bundesliga
    "bayern munich", "borussia dortmund", "rb leipzig", "bayer leverkusen",
    # club - serie a
    "juventus", "inter milan", "ac milan", "napoli", "roma", "lazio",
    # club - others
    "psg", "porto", "benfica", "ajax", "celtic",
    # nba
    "lakers", "celtics", "warriors", "bulls", "knicks", "heat", "nets",
    "bucks", "suns", "nuggets", "clippers", "sixers", "raptors",
    # nfl
    "chiefs", "eagles", "49ers", "cowboys", "patriots", "packers",
    # cricket
    "india", "pakistan", "australia", "west indies", "new zealand",
    "sri lanka", "bangladesh", "england", "south africa", "zimbabwe",
}

# filler words that cannot be entity_a or entity_b
FILLER_WORDS: set[str] = {
    "a", "an", "the", "in", "at", "of", "to", "for", "on", "by",
    "and", "or", "but", "with", "from", "into", "after", "before",
    "during", "while", "that", "this", "it", "its", "their", "our",
    "match", "game", "update", "news", "latest", "today", "yesterday",
    "defeated", "drew", "scored", "won", "lost", "beat", "nil",
}

# regex patterns for event extraction
_SCORE_PATTERN = re.compile(
    r"([A-Za-z ]{2,30?})\s+(\d{1,2})[‐\-–—](\d{1,2})\s+([A-Za-z ]{2,30})",
    re.IGNORECASE,
)

_DREW_PATTERN = re.compile(
    r"([A-Za-z ]{2,30?})\s+drew\s+([A-Za-z ]{2,30?})\s+(\d{1,2})[‐\-–—](\d{1,2})",
    re.IGNORECASE,
)

_DEFEATED_PATTERN = re.compile(
    r"([A-Za-z ]{2,30?})\s+defeated\s+([A-Za-z ]{2,30?})\s+(\d{1,2})[‐\-–—](\d{1,2})",
    re.IGNORECASE,
)

_BEAT_PATTERN = re.compile(
    r"([A-Za-z ]{2,30?})\s+beat\s+([A-Za-z ]{2,30?})\s+(\d{1,2})[‐\-–—](\d{1,2})",
    re.IGNORECASE,
)

_VS_PATTERN = re.compile(
    r"([A-Za-z ]{2,30?})\s+(?:vs\.?|versus|v\.?)\s+([A-Za-z ]{2,30})",
    re.IGNORECASE,
)


def _clean(s: str) -> str:
    return re.sub(r"\s+", " ", s).strip().lower()


def _is_valid_entity(name: str) -> bool:
    n = _clean(name)
    if not n or len(n) < 2:
        return False
    if n in FILLER_WORDS:
        return False
    # allow known teams OR proper noun (capital first letter)
    if n in KNOWN_TEAMS:
        return True
    # accept if it starts with capital (proper noun) and isn't pure filler
    if name.strip()[0].isupper() and n not in FILLER_WORDS:
        return True
    return False


def _confidence_for_entities(a: str, b: str) -> float:
    ca = 1.0 if _clean(a) in KNOWN_TEAMS else 0.6
    cb = 1.0 if _clean(b) in KNOWN_TEAMS else 0.6
    return (ca + cb) / 2.0


def _extract_competition(text: str) -> str:
    t = text.lower()
    comps = [
        ("world cup", "FIFA World Cup"),
        ("premier league", "Premier League"),
        ("champions league", "UEFA Champions League"),
        ("la liga", "La Liga"),
        ("bundesliga", "Bundesliga"),
        ("serie a", "Serie A"),
        ("europa league", "UEFA Europa League"),
        ("nba", "NBA"),
        ("nfl", "NFL"),
        ("ipl", "IPL"),
        ("t20", "T20"),
        ("odi", "ODI"),
    ]
    for key, label in comps:
        if key in t:
            return label
    return ""


def extract_events(text: str, competition_hint: str = "") -> list[EventRecord]:
    records: list[EventRecord] = []
    competition = competition_hint or _extract_competition(text)

    # 1. drew pattern
    for m in _DREW_PATTERN.finditer(text):
        a, b = m.group(1).strip(), m.group(2).strip()
        sa, sb = int(m.group(3)), int(m.group(4))
        if _is_valid_entity(a) and _is_valid_entity(b):
            conf = _confidence_for_entities(a, b)
            records.append(EventRecord(
                entity_a=a.title(), entity_b=b.title(),
                score_a=sa, score_b=sb,
                event_type="match", competition=competition,
                status=EventStatus.COMPLETED,
                confidence=conf, raw_text=text,
                timestamp=time.time(),
            ))

    # 2. defeated pattern
    for m in _DEFEATED_PATTERN.finditer(text):
        a, b = m.group(1).strip(), m.group(2).strip()
        sa, sb = int(m.group(3)), int(m.group(4))
        if _is_valid_entity(a) and _is_valid_entity(b):
            conf = _confidence_for_entities(a, b)
            records.append(EventRecord(
                entity_a=a.title(), entity_b=b.title(),
                score_a=sa, score_b=sb,
                event_type="match", competition=competition,
                status=EventStatus.COMPLETED,
                confidence=conf, raw_text=text,
                timestamp=time.time(),
            ))

    # 3. beat pattern
    for m in _BEAT_PATTERN.finditer(text):
        a, b = m.group(1).strip(), m.group(2).strip()
        sa, sb = int(m.group(3)), int(m.group(4))
        if _is_valid_entity(a) and _is_valid_entity(b):
            conf = _confidence_for_entities(a, b)
            records.append(EventRecord(
                entity_a=a.title(), entity_b=b.title(),
                score_a=sa, score_b=sb,
                event_type="match", competition=competition,
                status=EventStatus.COMPLETED,
                confidence=conf, raw_text=text,
                timestamp=time.time(),
            ))

    # 4. score inline pattern (Team1 2-1 Team2)
    for m in _SCORE_PATTERN.finditer(text):
        a, b = m.group(1).strip(), m.group(4).strip()
        sa, sb = int(m.group(2)), int(m.group(3))
        if _is_valid_entity(a) and _is_valid_entity(b):
            # avoid dupe
            key = (_clean(a), _clean(b))
            already = any((_clean(r.entity_a), _clean(r.entity_b)) == key for r in records)
            if not already:
                conf = _confidence_for_entities(a, b)
                records.append(EventRecord(
                    entity_a=a.title(), entity_b=b.title(),
                    score_a=sa, score_b=sb,
                    event_type="match", competition=competition,
                    status=EventStatus.COMPLETED,
                    confidence=conf, raw_text=text,
                    timestamp=time.time(),
                ))

    # 5. vs pattern (upcoming / no score)
    for m in _VS_PATTERN.finditer(text):
        a, b = m.group(1).strip(), m.group(2).strip()
        if _is_valid_entity(a) and _is_valid_entity(b):
            key = (_clean(a), _clean(b))
            already = any((_clean(r.entity_a), _clean(r.entity_b)) == key for r in records)
            if not already:
                conf = _confidence_for_entities(a, b) * 0.8  # lower for fixtures
                records.append(EventRecord(
                    entity_a=a.title(), entity_b=b.title(),
                    score_a=None, score_b=None,
                    event_type="fixture", competition=competition,
                    status=EventStatus.UPCOMING,
                    confidence=conf, raw_text=text,
                    timestamp=time.time(),
                ))

    # filter invalid
    valid = [r for r in records if r.is_valid()]
    # deduplicate: keep highest confidence per entity pair
    seen: dict[tuple[str, str], EventRecord] = {}
    for r in valid:
        key = (_clean(r.entity_a), _clean(r.entity_b))
        if key not in seen or r.confidence > seen[key].confidence:
            seen[key] = r
    return list(seen.values())


def best_event(events: list[EventRecord]) -> Optional[EventRecord]:
    if not events:
        return None
    completed = [e for e in events if e.status == EventStatus.COMPLETED]
    pool = completed or events
    return max(pool, key=lambda e: (e.confidence, e.timestamp))
