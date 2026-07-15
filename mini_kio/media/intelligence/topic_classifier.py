from __future__ import annotations
import re
from dataclasses import dataclass
from typing import Optional
from mini_kio.media.intelligence.media_intelligence_models import TopicType


# ── keyword banks ──────────────────────────────────────────────────────────────

_MOVIES_KW = {
    "movie", "film", "cinema", "trailer", "teaser", "director", "actor", "actress",
    "oscar", "box office", "sequel", "prequel", "release date", "cast", "plot",
    "marvel", "dc", "disney", "pixar", "warner", "netflix original", "prime video",
    "avengers", "batman", "spider-man", "thor", "iron man", "captain america",
    "fantastic four", "x-men", "deadpool", "black panther", "superman", "wonder woman",
    "nolan", "scorsese", "tarantino", "spielberg",
}

_TV_KW = {
    "series", "show", "episode", "season", "premiere", "finale", "streaming",
    "netflix", "hbo", "amazon prime", "apple tv", "disney+", "hulu", "peacock",
    "stranger things", "the crown", "breaking bad", "game of thrones", "mandalorian",
    "ted lasso", "succession", "euphoria", "squid game", "wednesday",
}

_GAMING_KW = {
    "game", "gta", "gameplay", "developer", "studio", "fps", "rpg", "mmorpg",
    "esports", "console", "ps5", "xbox", "nintendo", "steam", "playstation",
    "rockstar", "activision", "ubisoft", "ea sports", "bethesda", "riot games",
    "gta 6", "gta6", "call of duty", "fortnite", "minecraft", "valorant",
    "cyberpunk", "elden ring", "zelda", "halo", "god of war", "final fantasy",
    "patch", "update", "dlc", "expansion", "mod", "speedrun",
}

_SPORTS_KW = {
    "fifa", "world cup", "premier league", "la liga", "bundesliga", "serie a",
    "champions league", "europa league", "nfl", "nba", "mlb", "nhl", "f1",
    "formula 1", "grand prix", "wimbledon", "us open", "french open",
    "olympics", "commonwealth games", "transfer", "match", "fixture", "standings",
    "table", "results", "highlights", "goal", "penalty", "red card", "offside",
    "hat trick", "assist", "clean sheet", "lineup", "squad", "manager",
    "messi", "ronaldo", "mbappe", "neymar", "haaland", "lewandowski",
    "brazil", "argentina", "germany", "france", "england", "spain", "portugal",
    "drew", "defeated", "won", "lost", "scored", "nil",
}

_MUSIC_KW = {
    "song", "album", "single", "track", "music video", "mv", "concert", "tour",
    "spotify", "billboard", "grammy", "chart", "debut", "release",
    "weeknd", "drake", "taylor swift", "beyonce", "kendrick", "bad bunny",
    "coldplay", "ed sheeran", "ariana grande", "billie eilish", "doja cat",
    "rapper", "singer", "band", "artist", "producer", "ft.", "featuring",
    "remix", "ep", "mixtape", "lyrics",
}

_TECH_KW = {
    "apple", "google", "microsoft", "openai", "anthropic", "nvidia", "amd", "intel",
    "iphone", "android", "macbook", "windows", "linux", "chatgpt", "gemini",
    "claude", "llm", "ai model", "startup", "ipo", "acquisition", "funding",
    "software", "hardware", "chip", "gpu", "server", "cloud", "cybersecurity",
    "breach", "hack", "launch", "keynote", "wwdc", "google io",
}

_NEWS_KW = {
    "election", "president", "minister", "parliament", "government", "policy",
    "war", "conflict", "economy", "inflation", "recession", "stock market",
    "climate", "earthquake", "flood", "hurricane", "protest", "summit",
    "treaty", "sanction", "refugee",
}

_BOOKS_KW = {
    "book", "novel", "author", "writer", "wrote", "audiobook", "chapter", "page",
    "bestseller", "published", "publisher", "paperback", "hardcover",
    "harry potter", "dune", "lord of the rings", "the hobbit",
    "atomic habits", "deep work", "the alchemist", "sapiens",
    "hunger games", "twilight", "percy jackson",
    "song of ice and fire", "game of thrones book",
    "think and grow rich", "rich dad poor dad", "the subtle art",
}

# high-weight single-word terms for disambiguation
_PEOPLE_KW = {
    "biography", "who is", "person", "people", "inventor", "scientist",
    "philosopher", "leader", "activist", "artist", "painter", "musician",
    "born", "died", "age", "career", "life", "early life",
    "einstein", "newton", "darwin", "galileo", "aristotle", "plato", "socrates",
    "freud", "nietzsche", "marx", "feynman", "hawking", "tesla", "edison",
    "queen", "king", "president", "prime minister", "chancellor",
    "obama", "trump", "biden", "elon", "musk",
    "influencer", "creator", "founder", "ceo",
}

_HIGH_WEIGHT: dict[TopicType, set[str]] = {
    TopicType.SPORTS: {"highlights", "standings", "fixtures", "scored", "score"},
    TopicType.MOVIES: {"trailer", "teaser", "director", "cast"},
    TopicType.TV: {"episode", "season", "series"},
    TopicType.GAMING: {"gameplay", "dlc", "patch", "mod"},
    TopicType.MUSIC: {"song", "album", "lyrics", "tour", "concert"},
    TopicType.PEOPLE: {"biography", "who is", "born", "died", "career"},
}

# priority: higher index = lower priority (topic wins leftmost)
_TOPIC_PRIORITY = [
    TopicType.MOVIES,
    TopicType.TV,
    TopicType.GAMING,
    TopicType.SPORTS,
    TopicType.MUSIC,
    TopicType.BOOKS,
    TopicType.PEOPLE,
    TopicType.TECH,
    TopicType.NEWS,
]

_TOPIC_KEYWORDS: dict[TopicType, set[str]] = {
    TopicType.MOVIES: _MOVIES_KW,
    TopicType.TV: _TV_KW,
    TopicType.GAMING: _GAMING_KW,
    TopicType.SPORTS: _SPORTS_KW,
    TopicType.MUSIC: _MUSIC_KW,
    TopicType.BOOKS: _BOOKS_KW,
    TopicType.PEOPLE: _PEOPLE_KW,
    TopicType.TECH: _TECH_KW,
    TopicType.NEWS: _NEWS_KW,
}

# entities that HARD-LOCK to a topic regardless of keyword scores
_HARD_LOCK: dict[str, TopicType] = {
    # gaming
    "gta": TopicType.GAMING,
    "gta 6": TopicType.GAMING,
    "gta6": TopicType.GAMING,
    "grand theft auto": TopicType.GAMING,
    "fortnite": TopicType.GAMING,
    "minecraft": TopicType.GAMING,
    "call of duty": TopicType.GAMING,
    "valorant": TopicType.GAMING,
    "cyberpunk": TopicType.GAMING,
    "elden ring": TopicType.GAMING,
    "zelda": TopicType.GAMING,
    "halo": TopicType.GAMING,
    # movies/tv – often misclassified as sports
    "marvel": TopicType.MOVIES,
    "avengers": TopicType.MOVIES,
    "dc": TopicType.MOVIES,
    "batman": TopicType.MOVIES,
    "spider-man": TopicType.MOVIES,
    "thor": TopicType.MOVIES,
    "iron man": TopicType.MOVIES,
    "deadpool": TopicType.MOVIES,
    "fantastic four": TopicType.MOVIES,
    "x-men": TopicType.MOVIES,
    "black panther": TopicType.MOVIES,
    "netflix": TopicType.TV,
    "hbo": TopicType.TV,
    "disney+": TopicType.TV,
    # movies
    "interstellar": TopicType.MOVIES,
    "avatar": TopicType.MOVIES,
    "mission impossible": TopicType.MOVIES,
    "mission: impossible": TopicType.MOVIES,
    "the last of us": TopicType.TV,
    "god of war ragnarok": TopicType.GAMING,
    # tv
    "young sheldon": TopicType.TV,
    "sheldon": TopicType.TV,
    "one piece": TopicType.TV,
    "live action": TopicType.TV,
    # music artists
    "weeknd": TopicType.MUSIC,
    "the weeknd": TopicType.MUSIC,
    "drake": TopicType.MUSIC,
    "taylor swift": TopicType.MUSIC,
    "beyonce": TopicType.MUSIC,
    "kendrick": TopicType.MUSIC,
    "bad bunny": TopicType.MUSIC,
    "coldplay": TopicType.MUSIC,
    "ed sheeran": TopicType.MUSIC,
    "imagine dragons": TopicType.MUSIC,
    "believer": TopicType.MUSIC,
    "starboy": TopicType.MUSIC,
    "the weeknd": TopicType.MUSIC,
    "coldplay": TopicType.MUSIC,
    "lewis hamilton": TopicType.SPORTS,
    "max verstappen": TopicType.SPORTS,
    "fc barcelona": TopicType.SPORTS,
    "mrbeast": TopicType.MOVIES,
    "severance": TopicType.TV,
    "solo leveling": TopicType.TV,
    "the bear": TopicType.TV,
    # books
    "harry potter": TopicType.BOOKS,
    "dune book": TopicType.BOOKS,
    "atomic habits": TopicType.BOOKS,
    "deep work": TopicType.BOOKS,
    "the alchemist": TopicType.BOOKS,
    "sapiens": TopicType.BOOKS,
    "think and grow rich": TopicType.BOOKS,
    "rich dad poor dad": TopicType.BOOKS,
    "the subtle art": TopicType.BOOKS,
}


@dataclass
class ClassificationResult:
    topic: TopicType
    confidence: float
    scores: dict[TopicType, float]
    hard_locked: bool = False


def classify_topic(query: str) -> ClassificationResult:
    q = query.lower().strip()

    # 1. hard lock check (exact substring)
    for entity, locked_topic in _HARD_LOCK.items():
        if entity in q:
            return ClassificationResult(
                topic=locked_topic,
                confidence=1.0,
                scores={locked_topic: 100.0},
                hard_locked=True,
            )

    # 2. keyword scoring
    scores: dict[TopicType, float] = {t: 0.0 for t in TopicType if t != TopicType.UNKNOWN}
    tokens = set(re.findall(r"\b[\w\s'-]+\b", q))

    for topic, kw_set in _TOPIC_KEYWORDS.items():
        for kw in kw_set:
            if kw in q:
                # multi-word phrases score higher
                weight = 1.0 + (kw.count(" ") * 0.5)
                scores[topic] += weight
                # single-word high-weight terms get an extra boost
                if " " not in kw and topic in _HIGH_WEIGHT and kw in _HIGH_WEIGHT[topic]:
                    scores[topic] += 0.8

    # 3. pick winner
    if all(v == 0.0 for v in scores.values()):
        return ClassificationResult(
            topic=TopicType.UNKNOWN,
            confidence=0.0,
            scores=scores,
        )

    best_topic = max(scores, key=lambda t: (scores[t], -_TOPIC_PRIORITY.index(t) if t in _TOPIC_PRIORITY else -99))
    best_score = scores[best_topic]
    total = sum(scores.values()) or 1.0
    confidence = min(best_score / total, 1.0)

    # low-confidence → UNKNOWN
    if confidence < 0.25:
        return ClassificationResult(
            topic=TopicType.UNKNOWN,
            confidence=confidence,
            scores=scores,
        )

    return ClassificationResult(
        topic=best_topic,
        confidence=confidence,
        scores=scores,
    )


def topic_from_query(query: str) -> TopicType:
    return classify_topic(query).topic
