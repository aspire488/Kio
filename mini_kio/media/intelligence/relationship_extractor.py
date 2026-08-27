"""
relationship_extractor.py — Canonical semantic entity-relationship extraction
================================================================================

ONE generalized mechanism for representing, extracting and resolving entity
relationships from arbitrary natural-language evidence:

    retrieval -> evidence normalization -> relationship extraction
    -> context/entity memory -> relationship lookup -> answer / callback

The vocabulary is a small closed set of SEMANTIC RELATIONSHIP FAMILIES
(work->creator, org->leader, work->performer, team<->player, ...). Every
surface form — director/author/writer/screenwriter, developer/studio/maker,
founder/co-founder, CEO/president/leader/chairman, artist/singer/band,
publisher, manufacturer, composer, producer, owner, starring, plays for,
member of, works at — folds into ONE canonical predicate per family. New
surface words map into EXISTING families; there is no per-entity, per-title,
per-role, or per-domain code path.

Extraction is deterministic and sentence-boundary-aware (fast, no LLM — the
LLM stays the fallback inside the adapter for arbitrary forms the scan
misses). For each family it scans the evidence in both directions:

    * passive "by" forms     : "Y, directed by X" / "written by X" /
                               "developed and published by X" / "music by X"
    * "a WORK-TYPE by X"     : "a novel by Frank Herbert" (type->family map)
    * active-voice forms     : "X directed Y" / "X founded Y" / "X wrote Y" /
                               "X composed the score for Y"
    * role-noun forms        : "CEO of Y" / "Y's CEO" / "Director: X" /
                               "Jensen Huang is the CEO of Nvidia" /
                               "author Frank Herbert"
    * membership forms       : "X plays for Y" / "X is a member of Y"

Every emitted triple goes through plausibility gates (plausible name, not a
sentence-start filler like "Years", not a self-loop) so garbage never enters
the relationship store.
"""

from __future__ import annotations

import re
from typing import Optional

from mini_kio.media.intelligence.media_intelligence_models import RelationshipRecord


# ── canonical relationship families ───────────────────────────────────────────
# predicate -> family definition. surface words map into families; the
# predicate itself is the canonical stored relation.
RELATIONSHIP_FAMILIES: dict[str, dict] = {
    "directed_by": {
        "role_nouns": ("director",),
        "by_verbs": ("directed",),
        "active_verbs": ("directed", "directs"),
        "type_words": ("film", "movie", "flick", "picture", "motion picture"),
        "keyword": "director",
    },
    "written_by": {
        "role_nouns": ("author", "writer", "screenwriter", "novelist",
                       "playwright", "songwriter", "co-author", "coauthor"),
        "by_verbs": ("written", "wrote", "penned", "authored"),
        "active_verbs": ("wrote", "writes", "penned", "authored"),
        "type_words": ("novel", "book", "paper", "study", "series", "play",
                       "memoir", "biography", "story", "screenplay", "script"),
        "keyword": "author",
    },
    "developed_by": {
        "role_nouns": ("developer", "studio", "maker", "development team"),
        "by_verbs": ("developed",),
        "active_verbs": ("developed", "develops", "built", "created"),
        "type_words": ("video game", "game", "videogame", "app", "software",
                       "operating system", "console"),
        "keyword": "developer",
    },
    "published_by": {
        "role_nouns": ("publisher", "publishing house", "imprint"),
        "by_verbs": ("published",),
        "active_verbs": ("published", "publishes"),
        "type_words": (),
        "keyword": "publisher",
    },
    "manufactured_by": {
        "role_nouns": ("manufacturer", "maker"),
        "by_verbs": ("manufactured",),
        "active_verbs": ("manufactured", "manufactures", "makes"),
        "type_words": ("phone", "smartphone", "device", "product", "car",
                       "vehicle", "gadget", "laptop", "tablet", "console",
                       "processor", "chip", "gpu", "cpu"),
        "keyword": "manufacturer",
    },
    "composed_by": {
        "role_nouns": ("composer", "score composer", "music director"),
        "by_verbs": ("composed",),
        "active_verbs": ("composed", "composes", "scored", "scores"),
        "type_words": ("score", "soundtrack", "music", "song", "theme"),
        "keyword": "composer",
    },
    "produced_by": {
        "role_nouns": ("producer",),
        "by_verbs": ("produced",),
        "active_verbs": ("produced", "produces"),
        "type_words": ("film", "movie", "show", "series", "album", "record"),
        "keyword": "producer",
    },
    "created_by": {
        "role_nouns": ("creator", "co-creator", "showrunner"),
        "by_verbs": ("created",),
        "active_verbs": ("created", "creates"),
        "type_words": ("show", "series", "franchise", "universe", "character"),
        "keyword": "creator",
    },
    "performed_by": {
        "role_nouns": ("artist", "singer", "musician", "band", "rapper",
                       "performer", "duo", "group", "vocalist"),
        "by_verbs": ("performed", "sung"),
        "active_verbs": ("sang", "sings", "performed", "performs", "recorded",
                         "records"),
        "type_words": ("song", "album", "track", "single", "record", "hit"),
        "keyword": "artist",
    },
    "founded_by": {
        "role_nouns": ("founder", "co-founder", "cofounder", "co-founders",
                       "founders"),
        "by_verbs": ("founded", "co-founded", "established"),
        "active_verbs": ("founded", "co-founded", "established", "started",
                         "launched"),
        "type_words": ("company", "startup", "firm", "organization", "club",
                       "studio", "label"),
        "keyword": "founder",
    },
    "led_by": {
        "role_nouns": ("ceo", "president", "chairman", "chairwoman", "leader",
                       "boss", "head", "chief executive", "chief executive officer",
                       "managing director", "principal", "general manager",
                       "director general"),
        "by_verbs": ("led", "run", "headed"),
        "active_verbs": ("leads", "led", "heads", "runs", "manages"),
        "type_words": (),
        "keyword": "CEO",
    },
    "owned_by": {
        "role_nouns": ("owner",),
        "by_verbs": ("owned",),
        "active_verbs": ("owns", "owned"),
        "type_words": (),
        "keyword": "owner",
    },
    "starring": {
        "role_nouns": ("actor", "actress", "star", "lead", "cast member",
                       "lead actor", "lead actress"),
        "by_verbs": ("starring",),
        "active_verbs": ("starred", "stars", "plays", "played"),
        "type_words": (),
        "keyword": "starring",
    },
    "narrated_by": {
        "role_nouns": ("narrator",),
        "by_verbs": ("narrated",),
        "active_verbs": ("narrates", "narrated"),
        "type_words": (),
        "keyword": "narrator",
    },
    "voiced_by": {
        "role_nouns": ("voice actor", "voice actress", "voice artist"),
        "by_verbs": ("voiced",),
        "active_verbs": ("voices", "voiced"),
        "type_words": (),
        "keyword": "voice actor",
    },
    "plays_for": {
        "role_nouns": ("player", "member", "captain", "goalkeeper", "defender",
                       "midfielder", "forward", "attacker", "guard", "pitcher",
                       "quarterback"),
        "by_verbs": (),
        "active_verbs": ("plays for", "signed with", "joined", "played for",
                         "plays", "played"),
        "type_words": ("team", "club", "franchise", "side", "squad"),
        "keyword": "player",
    },
    "member_of": {
        "role_nouns": ("member", "vocalist", "guitarist", "drummer", "bassist",
                       "keyboardist", "frontman"),
        "by_verbs": (),
        "active_verbs": ("is a member of", "is part of", "joined"),
        "type_words": ("band", "group", "organization", "committee", "team"),
        "keyword": "member",
    },
    "works_at": {
        "role_nouns": ("employee", "engineer", "researcher", "scientist",
                       "designer", "staff member", "analyst"),
        "by_verbs": (),
        "active_verbs": ("works at", "works for", "is employed at", "joined"),
        "type_words": ("company", "firm", "organization", "lab", "university",
                       "institute"),
        "keyword": "works at",
    },
}

# role noun (lowercase, singular) -> canonical predicate
_ROLE_TO_PREDICATE: dict[str, str] = {}
for _pred, _fam in RELATIONSHIP_FAMILIES.items():
    for _rn in _fam["role_nouns"]:
        _ROLE_TO_PREDICATE[_rn] = _pred

# work-type word -> predicate family ("a novel by X" -> written_by)
_TYPE_TO_PREDICATE: dict[str, str] = {}
for _pred, _fam in RELATIONSHIP_FAMILIES.items():
    for _tw in _fam["type_words"]:
        _TYPE_TO_PREDICATE.setdefault(_tw, _pred)

# by-verb -> predicate ("directed by" / "developed and published by")
_BY_VERB_TO_PREDICATE: dict[str, str] = {}
for _pred, _fam in RELATIONSHIP_FAMILIES.items():
    for _bv in _fam["by_verbs"]:
        _BY_VERB_TO_PREDICATE.setdefault(_bv, _pred)

# active verb -> predicate ("X directed Y")
_ACTIVE_TO_PREDICATE: dict[str, str] = {}
for _pred, _fam in RELATIONSHIP_FAMILIES.items():
    for _av in _fam["active_verbs"]:
        _ACTIVE_TO_PREDICATE.setdefault(_av, _pred)


def canonical_predicate_for_role(role_noun: str) -> Optional[str]:
    """Map any surface role noun (director, CEO, founder, developer,
    manufacturer, artist, ...) to its canonical relationship predicate.

    This is the single semantic folding point: "founder", "co-founder",
    "cofounder" -> founded_by; "CEO"/"president"/"leader"/"chairman" ->
    led_by. New surface words simply join an existing family.
    """
    rl = (role_noun or "").strip().lower()
    if not rl:
        return None
    if rl in _ROLE_TO_PREDICATE:
        return _ROLE_TO_PREDICATE[rl]
    # strip articles/possessives: "the CEO" -> "ceo", "company's founder" -> founder
    rl = re.sub(r"^(?:the|a|an)\s+", "", rl)
    rl = re.sub(r"'s$", "", rl)
    return _ROLE_TO_PREDICATE.get(rl)


def retrieval_keyword_for_predicate(predicate: str) -> str:
    """Retrieval keyword for a canonical predicate (query rewriting:
    "who founded tesla" -> "tesla founder")."""
    fam = RELATIONSHIP_FAMILIES.get(predicate)
    return fam["keyword"] if fam else predicate


def canonical_predicate_for_verb(verb: str) -> Optional[str]:
    """Fold a surface role VERB (directed/wrote/founded/composed/plays for...)
    into its canonical predicate — the active-voice and by-form verbs share
    one family ("directed", "directed by" -> directed_by)."""
    v = (verb or "").strip().lower()
    if not v:
        return None
    if v in _ACTIVE_TO_PREDICATE:
        return _ACTIVE_TO_PREDICATE[v]
    if v in _BY_VERB_TO_PREDICATE:
        return _BY_VERB_TO_PREDICATE[v]
    return None


def all_role_nouns() -> tuple:
    """Every surface role noun in the canonical vocabulary (for query-shape
    detection: "who is the CEO of X", "X's founder")."""
    return tuple(sorted(_ROLE_TO_PREDICATE.keys()))


def all_role_verbs() -> tuple:
    """Every surface role verb (active + by forms) for query-shape detection
    ("who founded X", "who directed X")."""
    return tuple(sorted(set(_ACTIVE_TO_PREDICATE) | set(_BY_VERB_TO_PREDICATE)))


def verb_regex(verb: str) -> str:
    """Regex fragment matching a surface role verb. Each WORD is escaped
    separately and joined with flexible whitespace, so multi-word verbs
    ("plays for", "directed by") match real space runs. Escaping the whole
    string would also escape the whitespace marker (the classic
    re.escape("plays\\s+for") bug that made the pattern match the literal
    text "plays\\s+for")."""
    return r"\s+".join(re.escape(w) for w in (verb or "").split())


def verb_alternation(verbs) -> str:
    """Escaped alternation of role verbs, each with flexible whitespace."""
    return "|".join(verb_regex(v) for v in verbs)


def canonical_predicates() -> tuple:
    return tuple(RELATIONSHIP_FAMILIES.keys())


# ── name-run extraction helpers ───────────────────────────────────────────────

# Words that end a name run / are never entity names. Includes role-transition
# words, prepositions, and — critically — capitalized sentence-start fillers
# ("Years later, ...", "However, ...") that would otherwise be captured as the
# name after a role marker (live: "director" matched, then the next sentence
# started "Years ..." and the extracted holder was "Years").
_STOP_WORDS = frozenset({
    "written", "wrote", "directed", "director", "directors", "by", "starring",
    "stars", "with", "from", "music", "composed", "composer", "composers",
    "produced", "producer", "producers", "created", "creator", "creators",
    "developed", "developer", "developers", "based", "adapted", "screenplay",
    "story", "edited", "editor", "cinematography", "released", "release",
    "or", "also", "film", "movie", "tv", "series", "book", "novel", "game",
    "in", "on", "at", "of", "for", "to", "originally", "published",
    "publisher", "manufactured", "manufacturer", "founded", "founder",
    "co-founded", "ceo", "president", "leader", "owner", "star", "voiced",
    "narrated", "performed", "sang", "sings", "sing", "singer", "artist",
    "band", "actor", "actress", "plays", "played", "member", "joined",
    "works", "is", "are", "was", "were", "has", "have", "an", "a", "his",
    "her", "their", "its", "our", "who", "which", "that", "this", "these",
    "those", "it", "he", "she", "they", "you", "we", "i", "including",
    "along", "alongside", "opposite", "as", "well", "later", "eventually",
    "however", "meanwhile", "additionally", "furthermore", "although",
    "because", "since", "when", "while", "if", "though", "despite", "during",
    "through", "before", "after", "under", "over", "around", "about",
    "between", "among", "both", "each", "every", "many", "most", "more",
    "some", "other", "another", "one", "two", "three", "first", "second",
    "next", "last", "new", "recent", "official", "original", "according",
    "known", "features", "featuring", "follows", "tells", "set", "takes",
    "sees", "finds", "becomes", "then", "than", "now", "today", "yesterday",
    "recently", "soon", "still", "too", "just", "years", "year", "months",
    "month", "days", "day", "weeks", "week", "yet", "ever", "once", "again",
    "already", "always", "never", "often", "score", "soundtrack", "theme",
    "song", "album", "track", "single",    "video", "television", "tv", "called",
    "titled", "named", "entitled", "starring", "featuring", "the",
})

# Leading articles skipped at the START of a name run ("the Weeknd",
# "the Golden State Warriors").
_ARTICLES = frozenset({"the", "a", "an"})

# Fillers skipped at the END of a backwards name run ("Jensen Huang is the
# CEO of Nvidia" -> holder "Jensen Huang"): grammatical glue between the
# holder and the role noun.
_BACKWARDS_SKIP = frozenset({
    "is", "are", "was", "were", "be", "been", "being", "the", "a", "an",
    "also", "currently", "still", "now", "then", "as", "our", "their", "its",
    "his", "her", "currently", "former", "current", "new", "outgoing",
    "incoming", "am", "is", "and",
})

# Pronouns / fillers that can never be a relationship object.
_PRONOUNS = frozenset({
    "it", "this", "that", "these", "those", "he", "she", "they", "them",
    "him", "her", "his", "their", "our", "you", "we", "i", "me", "us",
    "one", "ones", "something", "anything", "everything", "nothing",
    "someone", "anyone", "everyone", "everybody", "somebody", "nobody",
})


def _clean_token(tok: str) -> str:
    """Strip punctuation / possessive / clause artifacts from a token."""
    tc = tok.split("(", 1)[0].split(")", 1)[0]
    tc = tc.strip("():,;.'\"\u2018\u2019\u201c\u201d-\u2014\u2013|[]")
    if tc.lower().endswith("'s") and len(tc) > 3:
        tc = tc[:-2]
    return tc


def _entity_like(tok: str) -> bool:
    """A token that can start/continue an entity name: capitalized, OR
    camelCase (iPhone, xAI, macOS — internal capital)."""
    if not tok:
        return False
    if re.fullmatch(r"[A-Z]{1,4}", tok):
        return False
    return tok[0].isupper() or any(ch.isupper() for ch in tok[1:])


def _name_run(text: str, start: int, max_tokens: int = 10) -> list[str]:
    """Run of entity-name tokens starting at `start`: skips a leading article,
    joins "and"/"&" between names (kept in the run so _split_names can split
    them), stops at lowercase words, stopwords, role-transition words,
    parentheticals, or a new clause. A comma ends the run AFTER its pre-comma
    token ("Blinding Lights, which..." -> "Blinding Lights"; "xAI, Elon
    Musk's company" -> "xAI")."""
    parts: list[str] = []
    for tok in text[start:].split()[:max_tokens]:
        raw_tok = tok
        tc = _clean_token(tok)
        if not tc:
            continue
        tcl = tc.lower()
        # a comma/ paren ends the run, keeping the pre-comma token
        if "," in raw_tok or "(" in raw_tok or ")" in raw_tok:
            if _entity_like(tc):
                parts.append(tc)
            break
        # leading article is skipped in forward (object) runs
        # ("the Golden State Warriors" -> "Golden State Warriors")
        if not parts and tcl in _ARTICLES:
            continue
        if tcl in ("and", "&"):
            if parts:
                parts.append(tcl)
                continue
            break
        if tcl in _STOP_WORDS:
            break
        if _entity_like(tc):
            parts.append(tc)
            if len(parts) >= 6:
                break
        elif parts:
            break
    # drop a trailing joiner ("Foxconn and designed by..." -> "Foxconn")
    while parts and parts[-1].lower() in ("and", "&"):
        parts.pop()
    return parts


def _name_run_backwards(text: str, max_tokens: int = 6) -> list[str]:
    """Run of entity-name tokens ending at the end of `text` (for active-voice
    forms: "Alex Garland directed ..." / "Jensen Huang is the CEO of ...").
    Skips trailing grammatical glue ("is the") while no name has been found;
    a leading article ("The Weeknd") is allowed at the front; a comma keeps
    its pre-comma token and ends the run ("Huang, announced" -> "Huang")."""
    toks = text.split()
    parts: list[str] = []
    for tok in reversed(toks[-max_tokens:]):
        raw_tok = tok
        tc = _clean_token(tok)
        if not tc:
            continue
        tcl = tc.lower()
        if "," in raw_tok or "(" in raw_tok or ")" in raw_tok:
            if _entity_like(tc):
                parts.insert(0, tc)
            break
        if not parts and tcl in _BACKWARDS_SKIP:
            continue
        # leading article kept in backwards (subject) runs: "The Weeknd",
        # "The Beatles" — the article is PART of the proper name
        if parts and tcl in _ARTICLES:
            parts.insert(0, tc)
            continue
        if tcl in ("and", "&"):
            if parts:
                parts.insert(0, tcl)
                continue
            break
        if tcl in _STOP_WORDS:
            break
        if _entity_like(tc):
            parts.insert(0, tc)
        elif parts:
            break
    while parts and parts[0].lower() in ("and", "&"):
        parts.pop(0)
    return parts


def _plausible_name(parts: list[str]) -> bool:
    if not parts:
        return False
    first = parts[0].lower()
    if len(first) < 2 or first in _PRONOUNS:
        return False
    if len(parts) == 1 and first in _STOP_WORDS:
        return False
    joined = " ".join(parts)
    if len(joined) < 2:
        return False
    return True


def _split_names(name: str) -> list[str]:
    """Split a conjoined name run ("Martin Eberhard and Marc Tarpenning")
    into individual names."""
    raw = [n.strip() for n in re.split(r"\s+(?:and|&)\s+", name, flags=re.I) if n.strip()]
    return raw or ([name] if name.strip() else [])


def _norm(e: str) -> str:
    return re.sub(r"[^a-z0-9]+", "", (e or "").lower())


def _anchor_in(text: str, anchor: Optional[str]) -> bool:
    if not anchor:
        return False
    key = _norm(anchor)
    if not key or len(key) < 2:
        return False
    return key in _norm(text)


# ── the extractor ─────────────────────────────────────────────────────────────

class RelationshipExtractor:
    """Deterministic, sentence-boundary-aware relationship extraction from
    arbitrary evidence text. One mechanism, all domains, no per-entity code."""

    # Abbreviations whose period must not end a sentence ("Tesla, Inc. was
    # founded..."): protected before the sentence split so the work and its
    # "by" clause stay in ONE sentence.
    _ABBREV_RE = re.compile(
        r"\b(?:[A-Za-z]\.|Inc\.|Ltd\.|Co\.|Corp\.|Mr\.|Mrs\.|Ms\.|Dr\.|"
        r"St\.|vs\.|etc\.|Jr\.|Sr\.|e\.g\.|i\.e\.|p\.?m\.|a\.?m\.)",
        re.I,
    )

    def extract(self, text: str, anchor: Optional[str] = None,
                session_id: str = "") -> list[RelationshipRecord]:
        if not text or not text.strip():
            return []
        records: dict[tuple, RelationshipRecord] = {}
        cleaned = re.sub(r"\s+", " ", text)
        protected = self._ABBREV_RE.sub(
            lambda m: m.group(0).replace(".", "\x00"), cleaned
        )
        for sent in re.split(r"(?<=[.!?])\s+", protected):
            self._extract_sentence(sent.replace("\x00", "."), anchor,
                                   session_id, records)
        return list(records.values())

    def _add(self, records: dict, subject: str, predicate: str, obj: str,
             session_id: str, evidence: str, confidence: float,
             source: str = "marker") -> None:
        subj = subject.strip()
        objv = obj.strip()
        rel = RelationshipRecord(
            subject=subj, predicate=predicate, object=objv,
            confidence=confidence, evidence=evidence[:220],
            source=source, session_id=session_id,
        )
        if not rel.is_valid():
            return
        key = (_norm(subj), predicate, _norm(objv))
        prev = records.get(key)
        if prev is None or rel.confidence > prev.confidence:
            records[key] = rel

    def _emit(self, records: dict, subject: str, predicate: str, obj: str,
              session_id: str, evidence: str, confidence: float,
              source: str = "marker") -> None:
        # forward triple (subject -> predicate -> object)
        self._add(records, subject, predicate, obj, session_id, evidence,
                  confidence, source)
        # inverse triple (object -> inverse -> subject) — enables
        # "what else has that director made" style lookups from the store.
        inv = RelationshipRecord(subject=subject, predicate=predicate,
                                 object=obj).inverse_predicate()
        if inv:
            self._add(records, obj, inv, subject, session_id, evidence,
                      confidence, source)

    def _extract_sentence(self, sent: str, anchor: Optional[str],
                          session_id: str, records: dict) -> None:
        if not sent or len(sent) < 8:
            return
        evidence = sent.strip()
        anchor_here = _anchor_in(sent, anchor)

        # 1. passive "by" forms: "Y, directed by X" / "written by X" /
        #    "developed and published by X" / "founded in 2003 by X" /
        #    "music by X"
        for m in re.finditer(r"\bby\b", sent, re.I):
            tail = sent[:m.start()][-100:]
            matched = []
            for vb, pred in _BY_VERB_TO_PREDICATE.items():
                # the by-verb appears in the tail, with at most a few
                # intervening lowercase tokens ("founded in 2003 by",
                # "co-founded back in 2015 by", "developed and published by")
                if re.search(
                    rf"\b{re.escape(vb)}\b(?:\s+(?:and|or)\s+\w+|\s+\w+){{0,7}}\s*$",
                    tail, re.I,
                ):
                    matched.append(pred)
            if not matched:
                # "music by X" / "score by X" / "songs by X" — composed_by
                if re.search(r"\b(?:music|score|songs?|soundtrack)\s*$", tail, re.I):
                    matched = ["composed_by"]
            if not matched:
                continue
            parts = _name_run(sent, m.end())
            if not _plausible_name(parts):
                continue
            name = " ".join(parts)
            subject = anchor if anchor_here else None
            if not subject:
                before = sent[:m.start()]
                work_parts = _name_run_backwards(before.rstrip(" ,"))
                if _plausible_name(work_parts):
                    subject = " ".join(work_parts)
            if not subject:
                continue
            for pred in dict.fromkeys(matched):
                for nm in _split_names(name):
                    self._emit(records, subject, pred, nm, session_id, evidence,
                               0.8, "by_marker")

        # 2. "a WORK-TYPE by X" — "a novel by Frank Herbert" -> written_by;
        #    "a video game by Team Cherry" -> developed_by
        for tw, pred in _TYPE_TO_PREDICATE.items():
            tm = re.search(
                rf"\b(?:a|an|the)\s+[\w\- ]{{0,14}}?\b{re.escape(tw)}\s+by\s+",
                sent, re.I,
            )
            if not tm:
                continue
            parts = _name_run(sent, tm.end())
            if not _plausible_name(parts):
                continue
            name = " ".join(parts)
            subject = anchor if anchor_here else None
            if not subject:
                work_parts = _name_run_backwards(sent[:tm.start()].rstrip(" ,"))
                if _plausible_name(work_parts):
                    subject = " ".join(work_parts)
            if not subject:
                continue
            for nm in _split_names(name):
                self._emit(records, subject, pred, nm, session_id, evidence,
                           0.75, "type_by_marker")

        # 3. active-voice forms: "X directed Y" / "X founded Y" / "X wrote Y" /
        #    "X composed the score for Y" / "X plays for Y" — subject name
        #    BEFORE the verb, object name AFTER it.
        #
        # Canonical subject orientation per predicate family: work/org
        # attribution predicates (directed_by, founded_by, ...) store the
        # WORK/ORG as subject ("Annihilation --directed_by--> Alex Garland"),
        # so the active-voice sentence is stored REVERSED; membership
        # predicates (plays_for, member_of, works_at) store the PERSON as
        # subject, so the sentence order is kept ("Stephen Curry
        # --plays_for--> Golden State Warriors").
        _SUBJECT_FORWARD = frozenset({"plays_for", "member_of", "works_at"})
        for av, pred in sorted(_ACTIVE_TO_PREDICATE.items(),
                               key=lambda kv: -len(kv[0])):
            am = re.search(rf"\b{re.escape(av)}\b", sent, re.I)
            if not am:
                continue
            before = sent[:am.start()].strip().strip(" ,")
            subj_parts = _name_run_backwards(before)
            if not _plausible_name(subj_parts):
                continue
            after = sent[am.end():]
            # skip object-describing phrases: "the score for X", "the music
            # for X", "a song called X"
            obj_start = after
            _obj_skip = re.match(
                r"\s*(?:the\s+)?(?:score|music|soundtrack|theme|song)\s+(?:for|of|to)\s+",
                after, re.I,
            )
            if _obj_skip:
                obj_start = after[_obj_skip.end():]
            obj_parts = _name_run(obj_start, 0)
            if not _plausible_name(obj_parts):
                continue
            subj = " ".join(subj_parts)
            objv = " ".join(obj_parts)
            _keep_order = pred in _SUBJECT_FORWARD
            for s in _split_names(subj):
                for o in _split_names(objv):
                    if _keep_order:
                        self._emit(records, s, pred, o, session_id, evidence,
                                   0.7, "active_marker")
                    else:
                        self._emit(records, o, pred, s, session_id, evidence,
                                   0.7, "active_marker")

        # 4. role-noun forms:
        #    a) "Jensen Huang is the CEO of Nvidia" / "X, the director of Y" /
        #       "CEO and co-founder of Nvidia" (chained role nouns)
        #    b) "the director of Y is X" / "CEO of Y: X" / "Y's CEO, X"
        #    c) "Director: X" / "Director — X" (subject = anchor)
        #    d) "author Frank Herbert" (subject = anchor)
        #
        # The role-noun chain handles the multi-role construction
        # ("CEO and co-founder of Nvidia") generically: every role noun maps
        # to its own predicate, each getting the same holder/org.
        _rn_alt = "|".join(re.escape(rn) for rn in _ROLE_TO_PREDICATE)
        _rnp_chain = rf"(?:(?:co-)?(?:{_rn_alt})(?:\s+(?:and|or)\s+(?:co-)?(?:{_rn_alt}))*)"
        # a) NAME + role-noun-chain + of + ORG
        om = re.search(
            rf"\b{_rnp_chain}\s+of\s+(?:the\s+)?([A-Z][\w.'\u2019-]*(?:\s+[A-Z][\w.'\u2019-]*)*)\b",
            sent, re.I,
        )
        if om:
            _chain_txt = om.group(0)
            org = om.group(1)
            holder_parts = _name_run_backwards(sent[:om.start()].strip(" ,"))
            if _plausible_name(holder_parts):
                holder = " ".join(holder_parts)
                for _rn2, _pred2 in _ROLE_TO_PREDICATE.items():
                    if re.search(rf"\b(?:co-)?{re.escape(_rn2)}\b", _chain_txt, re.I):
                        for h in _split_names(holder):
                            self._emit(records, org, _pred2, h, session_id,
                                       evidence, 0.85, "role_of_marker")
        # b) role-noun + of + ORG + (is|:|—|,) + NAME (single role noun)
        for rn, pred in _ROLE_TO_PREDICATE.items():
            rnp = rf"(?:co-)?{re.escape(rn)}"
            om2 = re.search(
                rf"\b{rnp}\s+of\s+(?:the\s+)?([A-Z][\w.'\u2019-]*(?:\s+[A-Z][\w.'\u2019-]*)*)\s*"
                rf"(?:is|:|\u2014|,)\s+",
                sent, re.I,
            )
            if om2:
                org = om2.group(1)
                after = sent[om2.end():]
                holder_parts = _name_run(after, 0)
                if _plausible_name(holder_parts):
                    holder = " ".join(holder_parts)
                    for h in _split_names(holder):
                        self._emit(records, org, pred, h, session_id, evidence,
                                   0.85, "role_of_is_marker")
            # b2) ORG's role-noun, NAME  ("Nvidia's CEO, Jensen Huang")
            pm = re.search(
                rf"([A-Z][\w.'\u2019-]*(?:\s+[A-Z][\w.'\u2019-]*)*)'s\s+{rnp}\s*(?:,|:|\u2014)?\s*",
                sent, re.I,
            )
            if pm:
                org = pm.group(1)
                after = sent[pm.end():]
                holder_parts = _name_run(after, 0)
                if _plausible_name(holder_parts):
                    holder = " ".join(holder_parts)
                    for h in _split_names(holder):
                        self._emit(records, org, pred, h, session_id, evidence,
                                   0.8, "possessive_marker")
            # c) "Director: X" / "Director — X" (subject = anchor in sentence)
            cm = re.search(rf"\b{rnp}\s*(?::|\u2014|-)\s*", sent, re.I)
            if cm and anchor_here:
                after = sent[cm.end():]
                holder_parts = _name_run(after, 0)
                if _plausible_name(holder_parts):
                    holder = " ".join(holder_parts)
                    for h in _split_names(holder):
                        self._emit(records, anchor, pred, h, session_id,
                                   evidence, 0.75, "role_colon_marker")
            # d) "author Frank Herbert" — role noun immediately followed by a
            #    name, subject = anchor described in this sentence.
            if anchor_here:
                dm = re.search(rf"\b{rnp}\s+", sent, re.I)
                if dm:
                    after = sent[dm.end():]
                    holder_parts = _name_run(after, 0)
                    if _plausible_name(holder_parts):
                        holder = " ".join(holder_parts)
                        # only when the name run is NOT a sentence continuation
                        if len(holder_parts) >= 2 or (
                            len(holder_parts) == 1
                            and holder_parts[0].lower() not in _STOP_WORDS
                            and len(holder_parts[0]) >= 3
                        ):
                            for h in _split_names(holder):
                                self._emit(records, anchor, pred, h, session_id,
                                           evidence, 0.65, "role_name_marker")

        # 5. membership: "X is a member of Y" -> member_of (subject = anchor
        #    or name)
        mm = re.search(
            r"\b([A-Z][\w.'\u2019-]*(?:\s+[A-Z][\w.'\u2019-]*)*)\s+is\s+a\s+member\s+of\s+"
            r"([A-Z][\w.'\u2019-]*(?:\s+[A-Z][\w.'\u2019-]*)*)\b",
            sent,
        )
        if mm:
            person = mm.group(1)
            org = mm.group(2)
            self._emit(records, person, "member_of", org, session_id, evidence,
                       0.8, "member_marker")
            self._emit(records, org, "has_member", person, session_id, evidence,
                       0.8, "member_marker")

    # ── lookup helpers (single source of truth for role holders) ────────────

    def role_holder_from_text(self, text: str, role_noun: str,
                              anchor: Optional[str] = None,
                              session_id: str = "") -> Optional[str]:
        """Best-effort deterministic resolution of {anchor}'s {role} from raw
        evidence text — the generalized marker fallback used when the LLM is
        unavailable. Returns the role holder name or None."""
        pred = canonical_predicate_for_role(role_noun)
        if not pred:
            return None
        for rel in self.extract(text, anchor=anchor, session_id=session_id):
            if rel.predicate == pred and (not anchor or rel.subject == anchor):
                return rel.object
        return None


# module-level singleton (no state)
_extractor = RelationshipExtractor()


def extract_relationships(text: str, anchor: Optional[str] = None,
                          session_id: str = "") -> list[RelationshipRecord]:
    """Deterministic relationship extraction (no-LLM fallback)."""
    return _extractor.extract(text, anchor=anchor, session_id=session_id)


# ── semantic extraction (PRIMARY mechanism) ───────────────────────────────────

_REL_FILLER = frozenset({
    "a", "an", "the", "in", "at", "of", "to", "by", "and", "or", "with",
    "for", "is", "are", "was", "were", "be", "been", "being", "it", "this",
    "that", "he", "she", "they", "them", "him", "her", "his", "their", "its",
    "who", "which", "what", "how", "as", "on", "from", "into", "about",
})


def _norm_word(w: str) -> str:
    return re.sub(r"[^a-z0-9]", "", (w or "").lower())


def relation_similarity(question_words: str, stored_relation: str) -> float:
    """Meaning-based similarity between a question's relation words and a
    stored free-form relation label (0..1). Token-overlap over content words
    with a stem-prefix bonus ("directed" vs "directed by", "ceo" vs "is the
    CEO of", "plays for" vs "plays for"). No vocabulary — pure lexical
    evidence of shared meaning."""
    q = [_norm_word(w) for w in re.findall(r"[A-Za-z0-9'-]+", question_words or "")]
    s = [_norm_word(w) for w in re.findall(r"[A-Za-z0-9'-]+", stored_relation or "")]
    q = [w for w in q if w and len(w) >= 2 and w not in _REL_FILLER]
    s = [w for w in s if w and len(w) >= 2 and w not in _REL_FILLER]
    if not q or not s:
        return 0.0
    qs, ss = set(q), set(s)
    exact = qs & ss
    if exact:
        return min(1.0, 0.5 + 0.5 * len(exact) / max(len(qs), len(ss)))
    # stem-prefix: "directed" vs "director" share "direct"; "founded" vs
    # "co-founded" share "found"
    for qw in qs:
        for sw in ss:
            prefix = min(len(qw), len(sw))
            if prefix >= 5 and qw[:prefix - 2] == sw[:prefix - 2]:
                return 0.6
    return 0.0


def semantic_extract_relationships(
    subject: str,
    evidence: str,
    llm_fn,
    session_id: str = "",
    max_facts: int = 8,
) -> list[RelationshipRecord]:
    """SEMANTIC relationship extraction — the primary mechanism for turning
    retrieved evidence into structured knowledge.

    The LLM reads the evidence and emits free-form (relation, object) pairs
    about the subject. Because the LLM interprets MEANING, arbitrary English
    formulations ("founded by", "helped establish", "co-founded", "is the
    creator of") and arbitrary domains work with ONE mechanism — there is no
    vocabulary to extend, no per-entity rule, no per-domain branch.

    Relations are emitted as verb phrases that read naturally in
    "OBJECT RELATION SUBJECT" order, so the same label is directly usable in
    store-first replies ("Alex Garland directed Annihilation.").

    Returns [] when the LLM is unavailable, the evidence is empty, or nothing
    is explicitly stated — callers fall back to the deterministic scanner
    (offline) or the live retrieval path.
    """
    if not subject or not evidence or not llm_fn:
        return []
    try:
        # Bounded, subject-focused window: 4000 chars around the subject's
        # mentions (a 77KB dump is mostly noise for the fact in question).
        text = re.sub(r"\s+", " ", evidence)
        idxs = [m.start() for m in re.finditer(re.escape(subject), text, re.I)]
        if not idxs:
            snippet = text[:4000]
        else:
            spans = [(max(0, i - 400), min(len(text), i + 700)) for i in idxs[:4]]
            spans = sorted(set(spans))
            merged = []
            for a, b in spans:
                if merged and a <= merged[-1][1]:
                    merged[-1] = (merged[-1][0], max(merged[-1][1], b))
                else:
                    merged.append((a, b))
            snippet = " ... ".join(text[a:b] for a, b in merged)[:5000]
        prompt = (
            f"Text about {subject!r}:\n\n{snippet}\n\n"
            f"Extract the facts about {subject} that are EXPLICITLY stated in "
            f"the text. For each fact output exactly one line:\n"
            f"RELATION | OBJECT\n"
            f"where RELATION is a short ACTIVE-VOICE verb phrase such that the "
            f"sentence \"OBJECT RELATION {subject}\" reads naturally (e.g. "
            f"'founded', 'is CEO of', 'directed', 'developed', 'wrote', "
            f"'plays for', 'starred in'). Never use passive 'by' forms "
            f"('developed by' is wrong; 'developed' is right). OBJECT is the "
            f"other entity or value.\n"
            f"Only include facts explicitly stated. No numbering, no bullets. "
            f"If no facts are stated, output exactly NONE."
        )
        raw = llm_fn(prompt)
        if not raw or not raw.strip():
            return []
        out: list[RelationshipRecord] = []
        for line in raw.splitlines():
            if "|" not in line:
                continue
            rel_part, obj_part = line.split("|", 1)
            rel = rel_part.strip().strip(".")
            obj = obj_part.strip().strip(".")
            if not rel or not obj:
                continue
            rel_n = rel.lower()
            obj_n = obj
            # plausible-object gate: not a filler/pronoun, not a degenerate
            # fragment, not the subject itself, bounded length.
            if len(obj_n) < 2 or len(obj_n) > 60:
                continue
            if obj_n.lower() in _REL_FILLER or obj_n.lower() in {"none", "unknown",
                                                                  "n/a", "na"}:
                continue
            if _norm_word(obj_n) == _norm_word(subject):
                continue
            if len(_norm_word(rel_n)) < 3:
                continue
            out.append(RelationshipRecord(
                subject=subject.strip(),
                predicate=rel_n,
                object=obj_n.strip(),
                confidence=0.85,
                evidence=snippet[:220],
                source="semantic",
                session_id=session_id,
            ))
            if len(out) >= max_facts:
                break
        return out
    except Exception:
        return []
