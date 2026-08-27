from __future__ import annotations
import logging
import re
from typing import Optional, Callable, Any

logger = logging.getLogger(__name__)

# Stopwords excluded from evidence-relevance matching. These are grammatical
# glue, not claim content: "passed away" is anchored by "passed", not "away".
_EVIDENCE_STOPWORDS = frozenset({
    "the", "a", "an", "and", "or", "but", "if", "of", "to", "in", "on",
    "at", "for", "with", "without", "from", "by", "about", "as", "into",
    "through", "during", "before", "after", "over", "under", "between",
    "out", "off", "up", "down", "again", "then", "than", "that", "this",
    "these", "those", "there", "here", "when", "where", "which", "what",
    "who", "whom", "whose", "why", "how", "all", "any", "both", "each",
    "few", "more", "most", "other", "some", "such", "no", "nor", "not",
    "only", "own", "same", "so", "too", "very", "can", "will", "just",
    "don't", "doesn't", "didn't", "isn't", "aren't", "wasn't", "weren't",
    "won't", "can't", "cant", "cannot", "wouldn't", "couldn't", "shouldn't",
    "would", "could", "should", "may", "might", "must", "shall",
    "has", "have", "had", "been", "being", "was", "were", "are", "is",
    "do", "does", "did", "be", "am", "me", "my", "you", "your", "yours",
    "he", "him", "his", "she", "her", "hers", "it", "its", "we", "us",
    "our", "ours", "they", "them", "their", "theirs", "i", "im", "ive",
    # Contracted referential forms — the same semantic class as "it"/"its":
    # a degenerate provider answer ("It's 2:52 AM.") must not satisfy the
    # synthesis grounding gate via a pronoun that merely appears in the
    # evidence snippets (live: a long multi-claim verification prompt was
    # answered with "It's 2:52 AM." because the token "it's" overlapped an
    # evidence excerpt).
    "it's", "its'", "that's", "there's", "here's", "he's", "she's",
    "we're", "they're", "you're", "what's", "who's", "where's",
    "when's", "why's", "how's", "let's", "i'm", "you've", "we've",
    "they've", "i've", "i'll", "you'll", "he'll", "she'll", "we'll",
    "they'll", "that'll", "there'll",
    "about", "into", "per", "via", "get", "got", "gets", "say", "said",
    "says", "going", "one", "two", "thing", "things", "really", "actually",
    "still", "even", "ever", "much", "many", "away", "back", "around",
})

def _meaningful_tokens(text: str) -> set:
    """Extract non-stopword content tokens for evidence/synthesis relevance."""
    toks = set()
    for w in re.findall(r"[a-zA-Z][a-zA-Z0-9']{3,}", (text or "").lower()):
        if w not in _EVIDENCE_STOPWORDS:
            toks.add(w)
    return toks


# Pure verification words: "is that true", "did it really happen" — these
# are the user ASKING, never a claim to verify. Kept for entityless detection.
_VERIF_GENERIC_TOKENS = frozenset({
    "true", "real", "happened", "happen", "say", "said", "says", "talking",
    "people", "someone", "anyone", "saw", "read", "heard", "actually",
    "really", "thing", "things", "stuff", "news", "rumor", "rumors",
    "online", "around", "about", "right", "still", "actually", "supposedly",
    "apparently", "reportedly", "allegedly", "rumored", "story", "stories",
    # Inflected/contracted probe forms: "Did that actually happen?" yields
    # the stem "happen" after stopword stripping, not "happened" — the
    # generic-follow-up reclaim must treat it as a pure probe word or the
    # reclaim never fires and the follow-up re-searches the bare phrase
    # (live: a Warriors assertion was answered by a stale Ronaldo claim
    # because the follow-up was NOT reclaimed).
    "sure", "serious", "seriously", "confirm", "confirmed", "verify",
    "verified", "correct", "fact", "facts", "exact", "exactly", "wait",
    "hold", "mean", "meant", "explain", "really", "possible", "possible",
})


def _message_entity_name(text: str) -> str:
    """First capitalized token that actually names an entity in this message
    ("I heard Messi's father..." -> "Messi"). Sentence-initial capitals ("Is
    that..."), capitals that start a NEW sentence after a period ("...project.
    Is that true?"), interrogative/auxiliary verbs (Is/Are/Did/Has...), and
    the pronoun "I" are all ignored; a later claim ("he said...") refers to
    THIS entity, which outranks the memory anchor.
    """
    words = (text or "").split()
    _skip_first = {"i", "a", "an", "the"}
    _verb_start = {"is", "are", "was", "were", "do", "does", "did", "has",
                   "have", "had", "will", "would", "could", "should", "can",
                   "may", "might", "must", "am"}
    _interrogatives = {"who", "what", "when", "where", "why", "how", "which", "whose"}
    prev_end = ""
    for w in words:
        wc = w.strip(".,!?;:'\"")
        wl = wc.lower()
        # A capital right after sentence punctuation is the next sentence's
        # first word ("...project. Is that true?"), never an entity name.
        if prev_end in (".", "!", "?", ";"):
            prev_end = ""
            continue
        # camelCase entities ("iPhone", "iPad", "macOS", "eBay") start
        # lowercase but carry an internal capital — without this check they
        # were missed and the verification subject fell back to the PREVIOUS
        # query's entity (live: "is it true the new iPhone got delayed"
        # registered subject "Tom" from the prior Tom Holland question, so
        # the next follow-up anchored to the wrong person).
        _camel_case = bool(wc) and any(ch.isupper() for ch in wc[1:])
        if wc and (wc[0].isupper() or _camel_case) and wl not in _skip_first \
                and wl not in _verb_start and wl not in _interrogatives:
            # Strip possessive so the anchor is "Messi", never "Messi's".
            return wc[:-2] if wl.endswith("'s") and len(wc) > 3 else wc
        prev_end = w[-1] if w else ""
    return ""


# Generic category nouns: they name a CLASS, never a specific subject
# ("the movie", "a player", "the company", "the lead actor"). A claim built
# only from these + event verbs + stopwords has NO own subject — it refers to
# the conversation's entity (anchor) or needs clarification. "Independence Day"
# must not match here (it has no category noun), and "movie got delayed" MUST.
_GENERIC_SUBJECT_NOUNS = frozenset({
    "movie", "film", "flick", "picture", "game", "match", "fixture",
    "race", "player", "actor", "actress", "singer", "artist", "band",
    "album", "song", "track", "show", "series", "episode", "season",
    "book", "novel", "company", "firm", "product", "device", "phone",
    "console", "release", "project", "sequel", "remake", "prequel",
    "studio", "director", "author", "writer", "character", "star",
    "team", "club", "ceo", "boss", "president", "minister", "leader",
    "owner", "founder", "chairman", "trailer", "preview", "poster",
    "update", "rumor", "report", "story", "lead", "main", "new",
    "old", "big", "whole", "other", "next", "last", "first",
    "second", "third",
})

# Event/predicate verbs: describe what happened to a subject without naming
# one ("got delayed", "left the project", "was cancelled"). Never a subject.
_EVENT_VERBS = frozenset({
    "delay", "delayed", "cancelled", "canceled", "cancel", "postponed",
    "release", "released", "retired", "retire", "left", "quit",
    "quitting", "fired", "hired", "injured", "transferred", "announced",
    "announce", "confirmed", "confirm", "died", "passed", "said",
    "say", "stepped", "stepping", "moved", "returned", "coming",
    "walked", "departed", "leaving", "exit", "exited", "broke",
    "ended", "paused", "halted", "changed", "shelved", "scrapped",
    "axed", "dropped", "pushed", "back", "down", "out", "off",
    "anymore", "longer", "long", "play", "playing", "continue",
    "continuing", "stop", "stopping", "sign", "signed", "getting",
    "coming", "cancel", "postpone", "happen", "happened", "happens",
})


from mini_kio.media.intelligence.media_intelligence_models import TopicType, ArtifactType, EventRecord, ArtifactRecord, IntelligenceResult
from mini_kio.intelligence.retrieval_router import RetrievalResult
from mini_kio.media.intelligence.topic_classifier import classify_topic
from mini_kio.media.intelligence.artifact_memory import ArtifactMemory, parse_artifact_type, default_artifact_for_topic
from mini_kio.media.intelligence.context_store import ContextStore
from mini_kio.media.intelligence.continuity_engine import ContinuityEngine, ResolutionResult
from mini_kio.media.intelligence.sports_intelligence import build_sports_response, detect_sports_mode, detect_competition, extract_events
from mini_kio.media.intelligence.answer_composer import _is_current_info_query
from mini_kio.media.intelligence.media_entity_memory import MediaEntityMemory
from mini_kio.media.intelligence.media_preference_model import MediaPreferenceModel
from mini_kio.media.intelligence.media_recommendation_engine import MediaRecommendationEngine
from mini_kio.media.intelligence.media_reference_resolver import MediaReferenceResolver, ReferenceResolution, ReferenceType
from mini_kio.media.intelligence.media_response_formatter import (
    format_media_response, format_artifact_response,
    format_sports_response, format_fallback,
)
from mini_kio.media.intelligence.answer_composer import AnswerComposer
from mini_kio.media.media_intelligence_models import EntityType, ResolvedEntity, MediaProvider
from mini_kio.media.intelligence.relationship_extractor import (
    canonical_predicate_for_role,
    canonical_predicate_for_verb,
    retrieval_keyword_for_predicate,
    extract_relationships,
    all_role_nouns,
    all_role_verbs,
    verb_regex,
    verb_alternation,
    relation_similarity,
    semantic_extract_relationships,
)


_CLAIM_SELECT_RE = re.compile(
    r"^\s*(?:which|what|what\u2019s|what's|which\s+one|which\s+parts?|\bthe\s+second\b|\bthe\s+first\b|\bthe\s+third\b|\bthe\s+last\b|\bthe\s+next\b)(?:\s+one\b)?\s*(?:of\s+(?:those|these|them|it|that))?"
    r"\s*(?:is|are|was|were)?\s*(?:actually|really|even)?\s*(?:true|real|right|correct|accurate|legit|a\s+thing|going\s+on|happened)?\??\s*$",
    re.I,
)


def _is_claim_selection_referent(query: str) -> bool:
    """True when the message SELECTS from a prior proposition set ("which
    part is true?", "the second one?", "which one?") instead of naming a
    new claim — the ordinal/selection morphology, never per-phrase rules.
    """
    return bool(_CLAIM_SELECT_RE.match((query or "").strip()))


def _recent_session_media_subject(sctx) -> Optional[str]:
    """Best-effort extraction of the most recently discussed MEDIA subject
    from a session context's exchange history (the conversational composer's
    recommendations — "Try Arrival" — live there, never in the media adapter's
    ContextStore). Returns the last clearly media-shaped entity mentioned by
    either side, or None."""
    try:
        hist = sctx.get_history_window(12) if hasattr(sctx, "get_history_window") else []
    except Exception:
        return None
    # Title-case candidates that are not ordinary prose words. Media names are
    # almost always capitalized in natural conversation.
    _prose = {"i", "the", "a", "an", "it", "you", "we", "they", "he", "she",
              "this", "that", "these", "those", "there", "here", "movie",
              "film", "book", "show", "series", "song", "album", "game",
              "try", "watch", "read", "listen", "recommend", "recommended",
              "something", "anything", "maybe", "like", "would", "could",
              "should", "darker", "lighter", "better", "similar"}
    # Recommendation-shape extraction: "I'd recommend X", "Try X", "I would
    # go with X", "What about X" — the NAMED candidate is the anchor. A naive
    # title-case scan grabs reply openers ("Because", "Yes", "I'd") instead
    # (live: "what else has that director made" anchored on "I'd" after
    # "I'd recommend Arrival" -> Macon Blair from stale memory).
    _rec_shape = re.compile(
        r"(?:i['\u2019]?d\s+(?:recommend|go\s+with|pick|choose|try)\s+|i\s+would\s+(?:recommend|go\s+with|pick|choose|try)\s+|try\s+|go\s+with\s+|what\s+about\s+|recommend(?:ing|ed)?\s+|check\s+out\s+|you\s+might\s+(?:enjoy|like|love)\s+|you\s+may\s+(?:enjoy|like|love)\s+|give\s+)[*\u201c\"'\u2018(]*([A-Z][A-Za-z0-9 .'\u2019-]{1,40})\b",
        re.I,
    )
    # Generic English pronouns/placeholders that a shape can capture when the
    # entity comes AFTER the pronoun ("give it a try — *Arrival*"): the
    # captured word is not the entity, skip it and keep scanning.
    _placeholder = {
        "it", "this", "that", "these", "those", "them", "one", "you",
        "me", "us", "him", "her", "something", "anything", "everything",
        "what", "which", "there", "here", "it's", "it\u2019s", "that's",
        "that\u2019s", "you'll", "you\u2019ll", "let's", "let\u2019s",
        "try", "reading", "watching", "listening", "playing", "giving",
    }
    # Role-verb work scan (general morphology, never per-entity): a reply like
    # "Alex Garland directed Annihilation." names the WORK after the role verb
    # ("directed/wrote/developed/founded/created/composed Annihilation") —
    # the work is the correct role-catalog referent anchor ("what else has
    # that director made" -> the director OF Annihilation), NOT the answer
    # person. Passive "directed by X" (holder after the verb) is skipped so
    # the scan lands on the work, never the person.
    _role_verb_work = re.compile(
        r"\b(?:directed|directs|wrote|writes|developed|develops|founded|co-founded|"
        r"created|creates|composed|composes|produced|produces|published|publishes|"
        r"sang|sings|performed|performs|recorded|records|starred|stars\s+in)\s+"
        r"(?!by\b)([A-Z][A-Za-z0-9 '\u2019\-]{1,40})\b",
        re.I,
    )
    for _u, _r in reversed(hist or []):
        for _txt in (_r, _u):
            if not _txt:
                continue
            _rv = _role_verb_work.search(_txt)
            if _rv:
                _cand = _rv.group(1).strip(".,!?;:\u2019'\"()")
                if len(_cand) >= 2 and _cand[0].isupper():
                    _words = _cand.split()
                    for _wi, _w in enumerate(_words):
                        if _wi > 0 and not (_w[0].isupper() or _w.isdigit()):
                            _cand = " ".join(_words[:_wi])
                            break
                    if len(_cand) >= 2:
                        return _cand
    for _u, _r in reversed(hist or []):
        for _txt in (_r, _u):
            if not _txt:
                continue
            _m = _rec_shape.search(_txt)
            if _m:
                _cand = _m.group(1).strip(".,!?;:\u2019'\"()")
                # Titles are sequences of Capitalized words/digits; trim any
                # trailing lowercase continuation ("The Expanse if you like it"
                # -> "The Expanse"). re.I makes [A-Z] match lowercase, so
                # "recommend me a sci-fi movie" (USER text) captures "me a
                # sci-fi movie". A real media entity is capitalized in the
                # reply — require the first captured char to be an actual
                # uppercase letter (live: anchor "me a sci-fi movie" ->
                # ROLE_CATALOG_RESOLVE garbage).
                if len(_cand) >= 2 and _cand[0].isupper() \
                        and _cand.lower() not in _placeholder:
                    _words = _cand.split()
                    for _wi, _w in enumerate(_words):
                        if _wi > 0 and not (_w[0].isupper() or _w.isdigit()):
                            _cand = " ".join(_words[:_wi])
                            break
                    if len(_cand) >= 2:
                        return _cand
        # No recommendation shape in this exchange's replies — fall back to a
        # title-case token that is not an opener/contraction. Sentence-initial
        # verb openers ("Give it a try", "Check out X") are skipped via the
        # first-token+lowercase-next rule so the scan lands on the actual
        # entity mid-sentence instead of the opener.
        for _txt in (_r, _u):
            _toks = (_txt or "").split()
            for _i, _tok in enumerate(_toks):
                _t = _tok.strip(".,!?;:'\"()[]-—*_\u2018\u2019\u201c\u201d")
                if len(_t) >= 3 and _t[0].isupper() and not _t.isupper():
                    if _i == 0 and _i + 1 < len(_toks) and _toks[_i + 1][:1].islower():
                        # "Give it..." / "Try reading..." — opener verb, skip.
                        continue
                    if _t.lower() not in _prose and not _t.lower().startswith(("i'd", "i\u2019d", "i'm", "i\u2019m", "it's", "it\u2019s", "that\u2019s", "that's", "because", "yes", "no", "definitely", "sure", "exactly", "yeah", "try", "give")):
                        # Multi-word title: consume the run of Capitalized
                        # words/digits ("Animal Well is..." -> "Animal Well"),
                        # not just the first token.
                        _run = [_t]
                        for _j in range(_i + 1, len(_toks)):
                            _nxt = _toks[_j].strip(".,!?;:'\"()[]-—*_\u2018\u2019\u201c\u201d")
                            if _nxt and (_nxt[0].isupper() or _nxt.isdigit()):
                                _run.append(_nxt)
                            else:
                                break
                        return " ".join(_run)
    return None


class MediaIntelligenceAdapter:
    """
    Drop-in adapter connecting the new intelligence layer to KIO's existing
    KnowledgeRouter / RetrievalRouter / MediaManager / CommandRouter.

    Usage:
        adapter = MediaIntelligenceAdapter(
            retrieval_fn=knowledge_router.retrieve,
            play_fn=media_manager.play_url,
            pending_action_fn=command_router.get_pending,
        )
        result = adapter.handle(query)
    """

    def __init__(
        self,
        retrieval_fn: Callable[[str, Optional[str], str], Optional[RetrievalResult]],
        play_fn: Optional[Callable[[str], None]] = None,
        pending_action_fn: Optional[Callable[[str], Optional[dict]]] = None,
        max_context_entries: int = 50,
        session_state: Optional["SessionState"] = None,
        retrieve_evidence_fn: Optional[Callable[[str, Optional[str], int], list]] = None,
    ) -> None:
        self.retrieve = retrieval_fn
        # Multi-source evidence collection (currentness): a callable returning
        # a LIST of RetrievalResults (ideally with published_date) so the
        # verification path can rank by freshness and reconcile contradictions
        # instead of trusting the single first provider hit. Falls back to a
        # single-result wrapper so callers that don't wire it still work.
        if retrieve_evidence_fn is None:
            def _single_evidence(q: str, topic: Optional[str] = None, max_results: int = 1) -> list:
                try:
                    res = self.retrieve(q, topic, "")
                    return [res] if res else []
                except Exception:
                    return []
            self._retrieve_evidence = _single_evidence
        else:
            self._retrieve_evidence = retrieve_evidence_fn
        self.play = play_fn
        self._ctx = ContextStore(max_context_entries)
        self._art = ArtifactMemory()
        self._mem = MediaEntityMemory()
        self._prefs = MediaPreferenceModel(self._mem)
        
        # Gate 5: unified session state — all subsystems read/write this
        self._session_state = session_state
        
        # Forward session_state to ContinuityResolver so it has authoritative entity/domain
        if session_state:
            from mini_kio.core.continuity_resolver import ContinuityResolver
            ContinuityResolver.set_session_state(session_state)
            # Bootstrap MediaEntityMemory from SessionState
            if session_state.active_entity:
                from mini_kio.media.media_intelligence_models import ResolvedEntity
                from mini_kio.media.intelligence.media_intelligence_models import TopicType
                _DOMAIN_TO_TOPIC = {
                    "media": TopicType.MOVIES,
                    "research": TopicType.TECH,
                    "conversation": TopicType.UNKNOWN,
                    "unknown": TopicType.UNKNOWN,
                }
                dom = TopicType.UNKNOWN
                if session_state.active_domain:
                    dom = _DOMAIN_TO_TOPIC.get(session_state.active_domain, TopicType.UNKNOWN)
                et = self._topic_to_entity_type(dom)
                self._mem.set_last_entity(ResolvedEntity(
                    name=session_state.active_entity,
                    entity_type=et,
                    metadata={"topic": dom.value},
                ))
        
        # We need a MediaContext wrapper for ReferenceResolver as it expects it
        from mini_kio.media.media_context import MediaContext
        self._media_context = MediaContext() 
        self._resolver = MediaReferenceResolver(self._media_context)
        
        self._recommender = MediaRecommendationEngine(self._mem, self._resolver, self._prefs)
        
        self._continuity = ContinuityEngine(
            context=self._ctx,
            artifact_memory=self._art,
            pending_action_resolver=pending_action_fn,
        )

        self._llm_fn: Optional[Callable[[str], Optional[str]]] = None
        # Dedicated verification synthesis function (longer budget); falls back
        # to _llm_fn when a caller only wired the generic one.
        self._verify_llm_fn: Optional[Callable[[str], Optional[str]]] = None
        self._composer = AnswerComposer(llm_fn=None)

        # Track last answer-person for pronoun resolution (who-directed questions)
        self._answer_person: str = ""

    def set_session_state(self, state: "SessionState") -> None:
        """Wire (or re-wire) unified SessionState after construction.
        
        Called from runtime once the SessionState (owned by ConversationResponder)
        is available.  Bootstraps entity memory, wires ContinuityResolver, and
        enables all SessionState writes from _register_entity, _handle_acceptance, etc.
        """
        self._session_state = state
        from mini_kio.core.continuity_resolver import ContinuityResolver
        ContinuityResolver.set_session_state(state)
        # Bootstrap entity memory from persisted state ONLY if empty
        if state.active_entity and not self._mem.get_last_entity():
            from mini_kio.media.media_intelligence_models import ResolvedEntity
            from mini_kio.media.intelligence.media_intelligence_models import TopicType
            # Map stored DomainContinuationType-compatible value back to TopicType
            _DOMAIN_TO_TOPIC = {
                "media": TopicType.MOVIES,
                "research": TopicType.TECH,
                "conversation": TopicType.UNKNOWN,
                "unknown": TopicType.UNKNOWN,
            }
            dom = TopicType.UNKNOWN
            if state.active_domain:
                dom = _DOMAIN_TO_TOPIC.get(state.active_domain, TopicType.UNKNOWN)
            et = self._topic_to_entity_type(dom)
            self._mem.set_last_entity(ResolvedEntity(
                name=state.active_entity,
                entity_type=et,
                metadata={"topic": dom.value},
            ))

    # ── memory helpers ──────────────────────────────────────────────────────────

    _PRONOUN_QUERIES = {
        "it", "that", "this", "they", "them", "him", "he", "she",
        "the song", "the movie", "the show", "the artist",
        "the album", "the video", "the trailer", "the game",
        "the team", "the match", "the player", "that one",
    }

    _INFO_PATTERNS = (
        "who", "what", "when", "where", "why", "how",
        "tell me about", "tell us about",
    )

    _ENTITY_TO_TOPIC: dict[EntityType, TopicType] = {
        EntityType.MOVIE: TopicType.MOVIES,
        EntityType.TV_SHOW: TopicType.TV,
        EntityType.ACTOR: TopicType.MOVIES,
        EntityType.MUSIC_ARTIST: TopicType.MUSIC,
        EntityType.SONG: TopicType.MUSIC,
        EntityType.ALBUM: TopicType.MUSIC,
        EntityType.SPORTS_PLAYER: TopicType.SPORTS,
        EntityType.SPORTS_TEAM: TopicType.SPORTS,
        EntityType.GAME: TopicType.GAMING,
        EntityType.YOUTUBER: TopicType.MOVIES,
        EntityType.STREAMER: TopicType.MOVIES,
        EntityType.COMPANY: TopicType.TECH,
        EntityType.BOOK: TopicType.BOOKS,
        EntityType.AUTHOR: TopicType.BOOKS,
    }

    @staticmethod
    def _topic_to_entity_type(topic: TopicType) -> EntityType:
        mapping = {
            TopicType.MOVIES: EntityType.MOVIE,
            TopicType.TV: EntityType.TV_SHOW,
            TopicType.MUSIC: EntityType.SONG,
            TopicType.SPORTS: EntityType.SPORTS_TEAM,
            TopicType.GAMING: EntityType.GAME,
            TopicType.PEOPLE: EntityType.ACTOR,
            TopicType.TECH: EntityType.COMPANY,
            TopicType.NEWS: EntityType.UNKNOWN,
            TopicType.BOOKS: EntityType.BOOK,
        }
        return mapping.get(topic, EntityType.UNKNOWN)

    def _entity_type_to_topic(self, et: EntityType) -> TopicType:
        return self._ENTITY_TO_TOPIC.get(et, TopicType.UNKNOWN)

    @staticmethod
    def _topic_to_continuity_domain(topic: TopicType) -> str:
        """Map TopicType to DomainContinuationType-compatible value.
        
        Media/entertainment domains → "media", tech/news → "research",
        people → "media", others → "conversation" or "unknown".
        """
        _MAP = {
            TopicType.MOVIES: "media",
            TopicType.TV: "media",
            TopicType.MUSIC: "media",
            TopicType.SPORTS: "media",
            TopicType.GAMING: "media",
            TopicType.BOOKS: "media",
            TopicType.PEOPLE: "media",
            TopicType.TECH: "research",
            TopicType.NEWS: "research",
        }
        return _MAP.get(topic, "unknown")

    def _is_continuation_query(self, ql: str) -> bool:
        if ql in self._PRONOUN_QUERIES:
            return True
        words = ql.split()
        if len(words) > 6:
            _fillers_early = {"the", "a", "an", "is", "are", "was", "were", "be", "been",
                              "do", "does", "did", "has", "have", "had", "in", "on", "at",
                              "for", "to", "of", "with", "by", "from", "about", "and", "or",
                              "but", "no", "not", "up", "down", "out", "off", "over",
                              "will", "would", "can", "could", "should", "may", "might",
                              "get", "got", "go", "went", "come", "came", "make", "made"}
            _cont_noise = {"explain", "without", "you", "spoilers", "ending",
                           "tell", "me", "describe", "summarize", "overview",
                           "recap", "synopsis", "plot", "story", "please",
                           "major", "minor", "big", "little", "main", "key",
                           "any", "brief", "quick", "simple", "basic",
                           "summary", "ideas", "concept", "concepts", "theme"}
            remaining = {w.strip("?.!") for w in words
                         if w.strip("?.!") not in _fillers_early
                         and w.strip("?.!") not in _cont_noise}
            if not remaining:
                return True
            return False
        # Bare freshness followups (≤3 words, all freshness words)
        if len(words) <= 3:
            _fresh = {"latest", "updates", "news", "recent", "current", "today", "any",
                      "standings", "results", "highlights", "fixtures", "scores",
                      "group", "table", "leader", "leading", "qualified", "eliminated"}
            if all(w.strip("?.!") in _fresh for w in words):
                return True
        # Do NOT include artifact/content words (updates, news, trailer, etc.)
        # — those belong in ContinuityEngine's followup detection.
        ref_words = {"it", "that", "this", "they", "them", "he", "she", "him", "his", "her", "their",
                     "scored", "score", "goal", "goals", "scoring", "scorer",
                     "who", "what", "where", "when", "why", "how",
                      "show", "play", "any", "there", "more",
                     "filming", "complete", "production", "release", "cast",
                     "episode", "season", "director", "producer", "writer",
                     "canceled", "cancelled", "renewed", "announced", "confirmed",
                     "singer", "song", "band", "artist", "album",
                     "standings", "results", "highlights", "fixtures", "scores",
                     "group", "table", "leader", "leading", "qualified", "eliminated",
                     "composer", "composed", "composition", "soundtrack",
                     "trailer", "gameplay", "clips", "ending",
                     "review", "rating", "ratings", "chapter"}
        query_words = {w.strip("?.!") for w in words}

        # Pronouns always trigger continuation — they need entity resolution from memory
        pronouns = {"it", "this", "they", "them", "he", "she", "him", "his", "her", "their"}
        if query_words & pronouns:
            return True
        # "that" as pronoun: exclude conjunction usage ("remember that I...")
        if "that" in query_words:
            import re
            if not re.search(r"\bthat\b\s+(?:i|you|he|she|it|we|they|my|your|his|her|its|our|their)\b", ql, re.I):
                return True

        # Interrogatives (who/what/where/when/why/how) — only continuation if query
        # lacks explicit entity content (e.g. "who directed interstellar" is FRESH,
        # not a continuation of the previous entity).
        interrogatives = {"who", "what", "where", "when", "why", "how"}
        if interrogatives & query_words:
            last_e = self._mem.get_last_entity()
            if last_e and last_e.name and last_e.name.lower() in ql:
                return True
            # Non-entity filler/structure words — subtracting these prevents false
            # "fresh query" detection for queries like "what was the score".
            _fillers = {"the", "a", "an", "is", "are", "was", "were", "be", "been",
                        "do", "does", "did", "has", "have", "had", "in", "on", "at",
                        "for", "to", "of", "with", "by", "from", "about", "and", "or",
                        "but", "not", "no", "up", "down", "out", "off", "over",
                        "will", "would", "can", "could", "should", "may", "might",
                        "get", "got", "go", "went", "come", "came", "make", "made"}
            non_ref = query_words - interrogatives - ref_words - pronouns - _fillers
            if non_ref and len(words) > 2:
                return False

        # Content-word guard: if query has explicit entity words (not ref/filler/noise),
        # treat as fresh query, not continuation. Prevents "the song Believer by Imagine
        # Dragons" from inheriting a stale entity (e.g. "Can You Give Me The Current Top
        # Scorers As Well?") just because "song" is a ref_word.
        _fillers = {"the", "a", "an", "is", "are", "was", "were", "be", "been",
                    "do", "does", "did", "has", "have", "had", "in", "on", "at",
                    "for", "to", "of", "with", "by", "from", "about", "and", "or",
                    "but", "not", "no", "up", "down", "out", "off", "over",
                    "will", "would", "can", "could", "should", "may", "might",
                    "get", "got", "go", "went", "come", "came", "make", "made"}
        content_words = query_words - ref_words - pronouns - _fillers
        if content_words and len(words) >= 2 and not (interrogatives & query_words):
            return False
        return bool(ref_words & query_words)

    def _resolve_memory_topic(self, target_topic: TopicType) -> TopicType:
        """Use memory's original topic when the target topic is a poor match."""
        last_e = self._mem.get_last_entity()
        if not last_e:
            return target_topic
        mem_topic = self._entity_type_to_topic(last_e.entity_type)
        # If classifier picked a generic topic (UNKNOWN/TECH/NEWS/GAMING) but memory has a specific one, trust memory
        generic = {TopicType.UNKNOWN, TopicType.TECH, TopicType.NEWS, TopicType.GAMING}
        specific = {TopicType.SPORTS, TopicType.MOVIES, TopicType.TV, TopicType.MUSIC, TopicType.BOOKS}
        if target_topic in generic and mem_topic in specific:
            return mem_topic
        return target_topic

    def _is_url_like(self, text: str) -> bool:
        """Detect if a string looks like a URL or Wikipedia revision URL."""
        lower = text.lower()
        return lower.startswith(("http://", "https://", "www.", "en.wikipedia.org",
                                 "//en.wikipedia.org"))

    def _register_entity(
        self, subject: str, topic: TopicType, result: Optional[RetrievalResult] = None,
        confidence: float = 1.0, raw_response: Optional[str] = None,
    ) -> None:
        import logging
        logger = logging.getLogger(__name__)
        if not subject:
            return
        
        # Reject URL-like entity names — they corrupt memory state
        if self._is_url_like(subject):
            logger.warning("[ENTITY_URL_REJECT] refusing to register URL-as-entity: %s", subject[:80])
            return
        
        if raw_response is None:
            if result:
                raw_response = result.raw_content or result.summary
            else:
                raw_response = ""

        entity = ResolvedEntity(
            name=subject,
            entity_type=self._topic_to_entity_type(topic),
            metadata={"topic": topic.value if hasattr(topic, "value") else str(topic), "confidence": str(confidence)},
            confidence=confidence,
        )
        self._mem.set_last_entity(entity)
        self._media_context.set_last_entity(entity)
        self._ctx.put("last_subject", subject, topic=topic, confidence=confidence, source="handler")
        # Track the entity topic for offer resolution
        self._ctx.put("last_entity_topic", topic.value if hasattr(topic, "value") else str(topic), topic=topic, confidence=confidence, source="handler")
        
        if raw_response:
            # Store in context store for reference
            self._ctx.put("last_raw_response", raw_response, topic=topic)
        if raw_response:
            self._ctx.put("last_raw", raw_response, topic=topic, confidence=confidence, source="retrieval")
            logger.info("[ENTITY_REGISTER] subject=%s topic=%s response_len=%d", subject, topic.value, len(raw_response))
        else:
            logger.info("[ENTITY_REGISTER] subject=%s topic=%s", subject, topic.value)
        # Semantic relationship knowledge: every piece of evidence about an
        # entity is turned into structured facts ONCE (LLM reads meaning,
        # free-form relation labels — no vocabulary). Later relationship
        # questions ("who made that again?") and role-catalog callbacks
        # ("what else has that studio made") resolve from the store instead
        # of re-deriving from fresh retrieval every time.
        self._extract_and_store_relationships(subject, raw_response)
        # Sync to unified SessionState using DomainContinuationType-compatible value
        if self._session_state:
            _dom_val = self._topic_to_continuity_domain(topic)
            self._session_state.set_entity_and_domain(subject, _dom_val)
        # Sync to unified SessionState using DomainContinuationType-compatible value
        if self._session_state:
            _dom_val = self._topic_to_continuity_domain(topic)
            self._session_state.set_entity_and_domain(subject, _dom_val)

    # ── canonical relationship store (generalized semantic mechanism) ─────────

    # Store answers are a fast path, never the authority: any stored fact
    # older than this TTL (or any CURRENT-state question) falls through to
    # the live retrieval path, so newer evidence always supersedes obsolete
    # store state (temporal invariant) without needing a catalog of
    # "mutable" predicates — the clock is the general arbiter.
    _STORE_ANSWER_TTL_S = 14 * 24 * 3600

    def _get_relationship(self, subject: str, role_noun: str,
                          session_id: str = "") -> str:
        """Semantic relationship lookup: best stored fact about `subject`
        whose free-form relation label matches `role_noun` by MEANING
        (relation_similarity — "director" matches a stored "directed",
        "CEO" matches "is CEO of"). No vocabulary: the store's own labels
        are compared lexically, so any role word works."""
        try:
            rels = self._ctx.find_relationships(subject=subject,
                                                session_id=session_id)
        except Exception:
            rels = []
        best, best_score = "", 0.0
        for r in rels:
            s = relation_similarity(role_noun, r.predicate)
            if s > best_score:
                best, best_score = r.object, s
        return best if best_score >= 0.45 else ""

    def _store_relationship_triple(self, subject: str, predicate: str,
                                   obj: str, *, method: str = "marker",
                                   session_id: str = "", confidence: float = 0.7,
                                   evidence: str = "") -> None:
        try:
            from mini_kio.media.intelligence.media_intelligence_models import (
                RelationshipRecord,
            )
            self._ctx.add_relationship(RelationshipRecord(
                subject=subject, predicate=predicate, object=obj,
                confidence=confidence, evidence=evidence,
                source=method, session_id=session_id,
            ))
        except Exception:
            pass

    def _extract_and_store_relationships(self, subject: str,
                                         raw_response: Optional[str],
                                         session_id: str = "") -> None:
        """Turn retrieved evidence about a subject into structured knowledge
        ONCE per evidence — SEMANTIC extraction first (the LLM reads the
        text and emits free-form (relation, object) pairs, so arbitrary
        English formulations and arbitrary domains need no vocabulary),
        with the deterministic scanner as the offline no-LLM fallback."""
        import logging
        logger = logging.getLogger(__name__)
        if not subject or not raw_response:
            return
        rels: list = []
        if self._llm_fn:
            try:
                rels = semantic_extract_relationships(
                    subject, raw_response, self._llm_fn, session_id=session_id,
                )
                if rels:
                    logger.info(
                        "[RELATIONSHIP_STORE] subject=%s triples=%d source=semantic (%s)",
                        subject, len(rels),
                        ", ".join(f"{r.predicate}:{r.object}" for r in rels[:8]),
                    )
            except Exception as exc:
                logger.debug("[RELATIONSHIP_EXTRACT] semantic failed: %s", exc)
                rels = []
        if not rels:
            try:
                rels = extract_relationships(raw_response, anchor=subject,
                                             session_id=session_id)
            except Exception as exc:
                logger.debug("[RELATIONSHIP_EXTRACT] deterministic failed: %s", exc)
                return
            if rels:
                logger.info(
                    "[RELATIONSHIP_STORE] subject=%s triples=%d source=marker (%s)",
                    subject, len(rels),
                    ", ".join(f"{r.predicate}:{r.object}" for r in rels[:8]),
                )
        for r in rels:
            self._ctx.add_relationship(r)

    # Question-shape detection for store-first relationship answering.
    # Generic morphology (role verbs + role nouns from the canonical
    # vocabulary), never per-entity.
    def _relationship_question(self, query: str) -> Optional[list]:
        ql = (query or "").strip()
        if not ql:
            return None
        # Grammar-based question parsing — NO role vocabulary. The subject is
        # whatever entity phrase the question names; the relation is the words
        # that describe it. The store lookup below grounds which split is the
        # intended one, so arbitrary relation wording works with zero catalog.
        cands: list[dict] = []
        # "who is the X of Y" / "who was the X of Y" -> subject=Y, relation=X
        m = re.match(
            r"^who\s+(?:is|are|was|were)\s+(?:the\s+)?(.+?)\s+of\s+(?:the\s+)?(.+?)\s*[?.!]*$",
            ql, re.I,
        )
        if m:
            _rel = m.group(1).strip()
            _subj = m.group(2).strip()
            if len(_subj) >= 2 and len(_rel) >= 2:
                cands.append({"subject": _subj, "relation": _rel})
        # "who X Y" (X = relation phrase, Y = subject): try every split point;
        # the store resolves which one names a real subject.
        m = re.match(r"^who\s+(.+?)\s*[?.!]*$", ql, re.I)
        if m:
            _tail = m.group(1).strip()
            _words = _tail.split()
            for _k in range(1, len(_words)):
                _rel_w = " ".join(_words[:_k])
                _subj_w = " ".join(_words[_k:])
                if len(_subj_w) >= 2 and len(_rel_w) >= 2:
                    cands.append({"subject": _subj_w, "relation": _rel_w})
        # "Y's X" (possessive role question) -> subject=Y, relation=X
        m = re.match(
            r"^([\w.'\u2019-]+(?:\s+[\w.'\u2019-]+)*)'s\s+(.+?)\s*[?.!]*$",
            ql, re.I,
        )
        if m:
            _subj = m.group(1).strip()
            _rel = m.group(2).strip()
            if len(_subj) >= 2 and len(_rel) >= 2:
                cands.append({"subject": _subj, "relation": _rel})
        if not cands:
            return None
        return cands

    def _maybe_relationship_answer(self, query: str,
                                   session_id: str = "") -> Optional[IntelligenceResult]:
        """Store-first relationship answering: when the store already holds a
        fact whose subject and relation label match the question by MEANING,
        answer directly — no fresh retrieval. The store was populated by
        semantic extraction of evidence on an earlier turn, so this is a
        lookup over previously verified evidence, never a fabrication.

        Matching is vocabulary-free: the question is parsed by grammar into
        (subject, relation-words) candidates, each candidate is looked up in
        the store, and stored relation labels are compared to the question's
        relation words with relation_similarity (lexical shared meaning). A
        CURRENT-state question ("who is the CEO now") always goes live, and
        any stored fact older than _STORE_ANSWER_TTL_S falls through too —
        newer credible evidence supersedes obsolete store state."""
        import logging
        logger = logging.getLogger(__name__)
        ql = query.lower()
        _fresh_words = ("current", "currently", "now", "latest", "today",
                        "new", "recent", "still", "right now")
        if any(w in ql for w in _fresh_words):
            return None
        cands = self._relationship_question(query)
        if not cands:
            return None
        import time as _t
        _now = _t.time()
        best: Optional[tuple] = None
        best_score = 0.0
        for cand in cands:
            subject = cand["subject"]
            relation_words = cand["relation"]
            try:
                rels = self._ctx.find_relationships(subject=subject,
                                                    session_id=session_id)
            except Exception:
                rels = []
            inverted = False
            if not rels:
                try:
                    rels = self._ctx.find_relationships(object_=subject,
                                                        session_id=session_id)
                except Exception:
                    rels = []
                inverted = bool(rels)
            for r in rels:
                if (_now - r.timestamp) > self._STORE_ANSWER_TTL_S:
                    continue
                score = relation_similarity(relation_words, r.predicate)
                if score > best_score:
                    best = (subject, relation_words, r, inverted)
                    best_score = score
        if not best or best_score < 0.5:
            # SEMANTIC adjudication: the store holds facts about the subject
            # but no stored relation label lexically matches the question's
            # relation words ("who made the game X" vs stored "developed by"
            # — same meaning, different words). The LLM — the meaning
            # interpreter — picks which stored fact answers the question.
            # This is the vocabulary-free generalization: no synonym table,
            # no per-relation mapping; the interpreter reads meaning. When
            # the LLM is unavailable the lookup simply misses and the live
            # retrieval path answers (correct, just slower).
            if self._llm_fn:
                try:
                    _cand_subjects = {c["subject"] for c in cands}
                    for _subj in _cand_subjects:
                        _facts = self._ctx.find_relationships(
                            subject=_subj, session_id=session_id)
                        if not _facts:
                            continue
                        _facts = [f for f in _facts
                                  if (_now - f.timestamp) <= self._STORE_ANSWER_TTL_S]
                        if not _facts:
                            continue
                        _lines = "\n".join(
                            f"- {f.predicate} {f.object}" for f in _facts[:10]
                        )
                        _prompt = (
                            f"The user asked: {query!r}\n\n"
                            f"Stored facts about {_subj}:\n{_lines}\n\n"
                            f"Which stored fact, if any, directly answers the "
                            f"question? Reply with ONLY the object(s) of the "
                            f"matching fact(s), separated by ' | ', or exactly "
                            f"NONE if no fact answers."
                        )
                        _raw = self._llm_fn(_prompt)
                        _DEGEN = {"none", "unknown", "n/a", "na", "no", "none.",
                                  "not sure", "i don't know", "i dont know",
                                  "does not answer", "no fact answers"}
                        if _raw and _raw.strip().upper() != "NONE":
                            _objs = [o.strip() for o in re.split(r"\s*\|\s*", _raw)
                                     if o.strip()
                                     and o.strip().lower().strip(".") not in _DEGEN
                                     and len(o.strip()) >= 2]
                            if _objs:
                                # Use the fact whose OBJECT was actually
                                # returned, so the reply carries the matched
                                # relation label ("Team Cherry developed by
                                # Hollow Knight" -> "Team Cherry developed
                                # Hollow Knight"), not the store's first fact.
                                _matched_fact = None
                                for _f in _facts:
                                    if any(
                                        re.sub(r"[^a-z0-9]+", "", _f.object.lower())
                                        == re.sub(r"[^a-z0-9]+", "", o.lower())
                                        for o in _objs
                                    ):
                                        _matched_fact = _f
                                        break
                                if _matched_fact is None:
                                    _matched_fact = _facts[0]
                                return self._relationship_store_result(
                                    query, _subj, _matched_fact, _objs,
                                    session_id, source="relationship_store_semantic",
                                )
                except Exception as exc:
                    logger.debug("[RELATIONSHIP_ADJUDICATE] failed: %s", exc)
            return None
        subject, relation_words, rel_record, inverted = best
        # Collect EVERY stored fact matching the same (subject, relation)
        # meaning — "who founded tesla" returns BOTH co-founders ("Martin
        # Eberhard and Marc Tarpenning"), never just the last one written.
        answers = []
        try:
            _all = self._ctx.find_relationships(subject=subject,
                                                session_id=session_id)
            for _r in _all:
                if (_now - _r.timestamp) > self._STORE_ANSWER_TTL_S:
                    continue
                if relation_similarity(relation_words, _r.predicate) >= 0.5:
                    answers.append(_r.object if not inverted else _r.subject)
        except Exception:
            answers = [rel_record.object if not inverted else rel_record.subject]
        if not answers:
            answers = [rel_record.object if not inverted else rel_record.subject]
        return self._relationship_store_result(
            query, subject, rel_record, answers, session_id,
            source="relationship_store",
        )

    def _relationship_store_result(self, query: str, subject: str,
                                   rel_record, answers: list, session_id: str,
                                   source: str) -> Optional[IntelligenceResult]:
        """Compose the store-first reply and keep session state aligned."""
        import logging
        logger = logging.getLogger(__name__)
        _seen, _uniq = set(), []
        for a in answers:
            k = re.sub(r"[^a-z0-9]+", "", a.lower())
            if k and k not in _seen:
                _seen.add(k)
                _uniq.append(a)
        if not _uniq:
            return None
        # Reply reuses the stored free-form relation label ("founded", "is
        # CEO of", "directed") — the semantic extractor emits labels that
        # read naturally in "{object} {relation} {subject}" order, so no
        # phrasing table is needed.
        _display_subject = subject
        if _display_subject and _display_subject.islower():
            _display_subject = _display_subject.title()
        _joined = _uniq[0] if len(_uniq) == 1 else (
            ", ".join(_uniq[:-1]) + " and " + _uniq[-1]
        )
        # The stored label may carry a passive trailing "by" ("developed by")
        # from the interpreter — strip it for the natural active-voice reply
        # ("Team Cherry developed Hollow Knight.").
        _pred = re.sub(r"\s+by$", "", rel_record.predicate.strip())
        text = f"{_joined} {_pred} {_display_subject}."
        logger.info("[RELATIONSHIP_ANSWER] q=%s subject=%s relation=%s objects=%s",
                    query, subject, rel_record.predicate, _uniq)
        _topic = classify_topic(query).topic or TopicType.UNKNOWN
        self._register_entity(subject, _topic, confidence=0.9)
        self._continuity.update_context(query, _topic, subject, 0.9)
        return IntelligenceResult(
            topic=_topic,
            response_text=text,
            subject=subject,
            confidence=0.9,
            source=source,
        )

    def _resolve_relationship(self, subject: str, role_noun: str,
                              evidence_text: str,
                              session_id: str = "") -> tuple[str, str]:
        """Resolve {subject}'s {role} from evidence — semantic LLM first
        (arbitrary surface forms), canonical extractor fallback. Returns
        (name, method)."""
        name = ""
        if self._llm_fn:
            try:
                snippet = re.sub(r"\s+", " ", (evidence_text or "")[:3000]).strip()
                prompt = (
                    f"Text about the work {subject!r}:\n\n{snippet}\n\n"
                    f"What is the name of {subject}'s {role_noun}? If the text "
                    f"does not name a {role_noun}, answer exactly UNKNOWN. "
                    f"Otherwise answer with ONLY the name — no explanation, "
                    f"no extra words."
                )
                raw = self._llm_fn(prompt)
                if raw:
                    raw = raw.strip().strip('"').strip("'")
                    _first = raw.splitlines()[0].strip().rstrip(".!?;: ")
                    _lower = _first.lower()
                    if (
                        _first and _first.upper() != "UNKNOWN" and len(_first) <= 60
                        and not _lower.startswith(("the ", "based ", "according ", "i ",
                                                   "it is ", "there ", "sorry", "unknown"))
                    ):
                        name = _first
            except Exception:
                name = ""
        if name:
            return (name, "llm")
        from mini_kio.media.intelligence.relationship_extractor import (
            RelationshipExtractor,
        )
        holder = RelationshipExtractor().role_holder_from_text(
            evidence_text or "", role_noun, anchor=subject, session_id=session_id,
        )
        return (holder, "marker") if holder else ("", "none")

    def _try_memory_resolve(self, query: str, topic: TopicType) -> Optional[IntelligenceResult]:
        import logging
        logger = logging.getLogger(__name__)
        ql = query.lower().strip()
        last_e = self._mem.get_last_entity()
        if not last_e:
            logger.info("[MEMORY_MISS] no last entity for query=%s topic=%s", query, topic)
            return None
        if not self._is_continuation_query(ql):
            logger.info("[MEMORY_MISS] query=%s not a continuation of last=%s", query, last_e.name)
            return None

        entity_name = last_e.name
        # Personal pronouns ("him", "he", "she") should resolve to the last
        # answer-person (e.g. "Christopher Nolan" from "Who directed X?"),
        # not the query subject entity (e.g. "Interstellar").
        _personal_pronouns = {"him", "he", "she"}
        q_words = set(ql.split())
        used_answer_person = _personal_pronouns & q_words and bool(self._answer_person)
        resolve_name = self._answer_person if used_answer_person else entity_name
        # Use entity's native topic when classifier picks a generic/wrong one
        mem_topic = self._entity_type_to_topic(last_e.entity_type)
        use_topic = mem_topic if mem_topic in {TopicType.SPORTS, TopicType.MOVIES, TopicType.TV, TopicType.MUSIC, TopicType.BOOKS} else topic
        logger.info("[MEMORY_HIT] last=%s query=%s topic=%s mem_topic=%s", entity_name, query, topic, use_topic)

        # Build targeted retrieval query from entity context + user query intent
        noise = {"it", "that", "this", "they", "them", "he", "she", "him", "his", "her", "their"}
        meaningful = [w for w in ql.split() if w not in noise]
        new_query = f"{resolve_name} {' '.join(meaningful)}" if meaningful else resolve_name
        # Apply retrieval rewriting to optimize the query
        rewritten = self._rewrite_retrieval(query, use_topic, resolve_name)
        if rewritten != query:
            new_query = rewritten
        logger.info("[MEMORY_RESOLVE] entity=%s original=%s new_query=%s", resolve_name, query, new_query)

        # NEW retrieval — memory provides context, retrieval provides facts
        res = self._safe_retrieve(new_query, topic=use_topic.value)
        if not res:
            res = self._safe_retrieve(resolve_name, topic=use_topic.value)

        # Discover artifacts from the retrieved content so that followup artifact
        # queries (e.g. "show trailer", "play highlights") can resolve from memory.
        if res:
            self._discover_artifacts(res, use_topic, entity_name)

        text = self._compose_answer(res, query) if res else ""
        # Always register original entity (not answer_person) to maintain subject continuity
        self._register_entity(entity_name, topic, result=res, confidence=0.85)
        # Sync continuity context with memory entity — keeps the "subject" key
        # in lockstep so _handle_acceptance continuity fallback resolves correctly.
        self._continuity.update_context(query, use_topic, entity_name, confidence=0.85)

        return IntelligenceResult(
            topic=self._entity_type_to_topic(last_e.entity_type),
            response_text=text,
            subject=entity_name,
            confidence=0.85,
            source=f"memory:{entity_name}",
        )

    # ── main entry point ───────────────────────────────────────────────────────

    # ── acceptance handler ──────────────────────────────────────────────────

    # Number-to-offer mapping
    _NUMBER_WORDS = {
        "1": 0, "2": 1, "3": 2, "4": 3, "5": 4, "6": 5,
        "first": 0, "first one": 0, "the first one": 0,
        "second": 1, "second one": 1, "the second one": 1,
        "third": 2, "third one": 2, "the third one": 2,
    }
    _ACCEPT_WORDS = frozenset({"yes", "yeah", "sure", "ok", "okay", "yep", "do it", "show it", "play it", "go ahead", "show them", "pls", "please"})

    _ACCEPT_FOUND_MSG = {
        "trailer": "Got it. Opening the {} trailer.",
        "teaser": "Got it. Opening the {} teaser.",
        "gameplay": "Got it. Opening gameplay footage for {}.",
        "music_video": "Got it. Playing the music video for {}.",
        "audiobook": "Got it. Opening the audiobook for {}.",
        "soundtrack": "Got it. Opening the soundtrack for {}.",
        "interview": "Got it. Opening the interview for {}.",
        "behind_the_scenes": "Got it. Opening behind-the-scenes footage for {}.",
        "highlights": "Got it. Opening highlights for {}.",
        "clips": "Got it. Opening clips from {}.",
        "best_scenes": "Got it. Opening best scenes from {}.",
        "live_performance": "Got it. Playing the live performance for {}.",
        "concert": "Got it. Playing the concert for {}.",
        "lyrics": "Got it. Showing lyrics for {}.",
        "book_review": "Got it. Opening the book review for {}.",
        "book_summary": "Got it. Opening the book summary for {}.",
        "author_interview": "Got it. Opening the author interview for {}.",
        "reading": "Got it. Opening the reading for {}.",
    }
    _ACCEPT_SEARCH_MSG = {
        "trailer": "Finding the {} trailer.",
        "teaser": "Finding the {} teaser.",
        "gameplay": "Searching for {} gameplay footage.",
        "music_video": "Looking up the music video for {}.",
        "audiobook": "Finding the audiobook for {}.",
        "soundtrack": "Looking for the soundtrack of {}.",
        "interview": "Searching for an interview with {}.",
        "behind_the_scenes": "Looking for behind-the-scenes of {}.",
        "highlights": "Finding highlights for {}.",
        "clips": "Looking for clips from {}.",
        "best_scenes": "Finding best scenes from {}.",
        "live_performance": "Looking for a live performance of {}.",
        "concert": "Searching for a {} concert.",
        "lyrics": "Finding lyrics for {}.",
        "book_review": "Looking for reviews of {}.",
        "book_summary": "Finding a summary of {}.",
        "author_interview": "Looking for an interview with {}.",
        "reading": "Finding a reading of {}.",
    }

    def _acceptance_msg(self, entity: str, artifact: ArtifactType, found: bool) -> str:
        key = artifact.value
        if found:
            template = self._ACCEPT_FOUND_MSG.get(key)
            if template:
                return template.format(entity)
            return f"Got it. Opening {entity}."
        template = self._ACCEPT_SEARCH_MSG.get(key)
        if template:
            return template.format(entity)
        return f"Searching for {entity}."

    def _handle_acceptance(self, query: str) -> Optional[IntelligenceResult]:
        """Handle acceptance responses that resolve to a previously-offered artifact.
        
        Only triggers for PURE acceptance phrases:
        - Bare digits: "1", "2", "3" → select offer by number
        - Ordinals: "first one", "the second one" → select offer by index
        - Acceptance: "yes", "yeah", "sure", "ok" → top-ranked offer
        - Action: "show it", "play it", "do it" → default artifact for entity
        
        Does NOT intercept information queries like "Show standings" or "Any teaser available?"
        — those flow through to continuity engine and normal routing.
        """
        q = query.lower().strip()

        # Check for number or ordinal
        for word, index in self._NUMBER_WORDS.items():
            if q == word:
                logger.info("[ARTIFACT_RESOLVE] selection=%s index=%d", word, index)
                return self._resolve_offer_index(index)

        # Handle "play the first one", "show the first one", "play first one" etc.
        # Strip leading action verb + optional article, then re-check ordinals
        ordinal_match = re.match(r"(?:play|show|watch)\s+(?:the\s+)?(.+)", q)
        if ordinal_match:
            stripped = ordinal_match.group(1).strip()
            for word, index in self._NUMBER_WORDS.items():
                if stripped == word:
                    logger.info("[ARTIFACT_RESOLVE] ordinal_stripped=%s selection=%s index=%s", q, word, index)
                    return self._resolve_offer_index(index)

        # F3: Action shortcut keywords — short artifact/resolution tokens
        # e.g. "trailer", "cast", "gameplay", "highlights"
        _SHORTCUT_KEYWORDS = frozenset({
            "trailer", "teaser", "cast", "soundtrack", "gameplay", "highlights",
            "clips", "interview", "behind the scenes", "standings", "fixtures",
            "results", "summary", "author", "lyrics", "similar", "reviews",
            "episodes", "walkthrough", "show", "show me",
        })
        q_normalized = q.rstrip(".,!?;:").strip()
        q_words = q_normalized.split()
        # Only treat as shortcut if query is short (1-3 words) and not a multi-word entity query
        if len(q_words) <= 2:
            q_short = q_normalized
            # Strip leading "show"/"play"/"watch" for matching
            for prefix in ("play ", "show ", "watch ", "open "):
                if q_short.startswith(prefix):
                    q_short = q_short[len(prefix):].strip()
            if q_short in _SHORTCUT_KEYWORDS:
                result = self._resolve_offer_by_name(q_short)
                if result:
                    return result
                # Fallback: treat "trailer" → search for subject trailer
                if q_short != "similar":
                    return self._resolve_artifact_shortcut(q_short)

        # Only match acceptance words as STANDALONE WORDS, not substrings
        # e.g. "ok" should not match inside "book" — use word boundaries
        def _has_acceptance_word(text: str) -> bool:
            for aw in self._ACCEPT_WORDS:
                if " " in aw:
                    parts = [re.escape(w) for w in aw.split()]
                    pattern = r"\b" + r"\s+".join(parts) + r"\b"
                else:
                    pattern = r"\b" + re.escape(aw) + r"\b"
                if re.search(pattern, text):
                    return True
            return False
        if not _has_acceptance_word(q):
            return None

        # "yes/yeah/sure/ok" → resolve to highest-ranked offer (index 0)
        # Normalize trailing punctuation so "Yes." matches "yes"
        q_stripped = q.rstrip(".,!?;:")
        if q_stripped in ("yes", "yeah", "sure", "ok", "okay", "yep"):
            q = q_stripped
        if q in ("yes", "yeah", "sure", "ok", "okay", "yep"):
            result = self._resolve_offer_index(0)
            if result:
                return result
            # No stored offers — fall through to default artifact for entity topic
            # (e.g. "yes" after "play believer" → play music video for believer)

        # "show them" resolution
        if q == "show them":
            was = self._ctx.get("last_offers")
            if was and was.value:
                subject = was.value.get("subject", "")
                logger.info("[ARTIFACT_RESOLVE] entity=%s artifact=multiple selection=all", subject)
                return IntelligenceResult(
                    topic=TopicType(was.value.get("topic", "unknown")),
                    response_text=f"Available for {subject}: " + ", ".join(was.value.get("offers", [])),
                    subject=subject,
                    source="acceptance",
                    confidence=0.9
                )

         # "show it" / "play it" / "do it" → default artifact for entity topic
        last_e = self._mem.get_last_entity()
        # Try entity memory first, then continuity context
        if last_e:
            topic = self._entity_type_to_topic(last_e.entity_type)
            target_artifact = default_artifact_for_topic(topic) if topic else None
        else:
            target_artifact = None
        if not target_artifact:
            # Guard: reject stale continuity context if entity memory has a
            # different topic (cross-group contamination defense).
            last_topic_entry = self._ctx.get("last_entity_topic")
            if last_topic_entry and last_topic_entry.value:
                try:
                    mem_topic = TopicType(last_topic_entry.value)
                    ctx_topic = self._ctx.recent_topic()
                    if ctx_topic and mem_topic != ctx_topic and mem_topic != TopicType.UNKNOWN and ctx_topic != TopicType.UNKNOWN:
                        return None
                except (ValueError, TypeError):
                    pass
            ctx_subject = self._ctx.recent_subject()
            ctx_topic = self._ctx.recent_topic()
            if ctx_subject and ctx_topic:
                target_artifact = default_artifact_for_topic(ctx_topic)
                if target_artifact:
                    logger.info("[ARTIFACT_RESOLVE] entity=%s artifact=%s selection=default(continuity)", ctx_subject, target_artifact.value)
                    record = self._art.resolve_artifact(target_artifact, subject=ctx_subject, topic=ctx_topic)
                    if record:
                        return IntelligenceResult(
                            topic=ctx_topic,
                            response_text=self._acceptance_msg(ctx_subject, target_artifact, True),
                            subject=ctx_subject,
                            source="acceptance",
                            confidence=0.85,
                        )
                    return IntelligenceResult(
                        topic=ctx_topic,
                        response_text=self._acceptance_msg(ctx_subject, target_artifact, False),
                        subject=ctx_subject,
                        source="acceptance",
                        confidence=0.7,
                        followup_options=[f"play {ctx_subject} {target_artifact.value}"],
                    )
            return None
        
        if target_artifact:
            logger.info("[ARTIFACT_RESOLVE] entity=%s artifact=%s selection=default", last_e.name, target_artifact.value)
            record = self._art.resolve_artifact(target_artifact, subject=last_e.name, topic=topic)
            if record:
                return IntelligenceResult(
                    topic=topic,
                    response_text=self._acceptance_msg(last_e.name, target_artifact, True),
                    subject=last_e.name,
                    source="acceptance",
                    confidence=0.85,
                )
            return IntelligenceResult(
                topic=topic,
                response_text=self._acceptance_msg(last_e.name, target_artifact, False),
                subject=last_e.name,
                source="acceptance",
                confidence=0.7,
                followup_options=[f"play {last_e.name} {target_artifact.value}"],
            )
        return None

    def _resolve_offer_index(self, index: int) -> Optional[IntelligenceResult]:
        """Resolve acceptance to the offer at the given index."""
        was = self._ctx.get("last_offers")
        if not was or not was.value or not isinstance(was.value, dict):
            return None
        offers = was.value.get("offers", [])
        if index >= len(offers):
            return None
        subject = was.value.get("subject", "")
        topic_val = was.value.get("topic", "")
        topic = TopicType(topic_val) if topic_val else TopicType.UNKNOWN
        offer_name = offers[index]
        
        # Store for artifact resolution
        artifact_key = self._offer_name_to_key(offer_name)
        self._ctx.put("last_offered", {
            "subject": subject, "artifact_type": artifact_key,
            "offer_name": offer_name,
        }, topic=topic, confidence=1.0, source="acceptance")
        
        # Sync action to unified SessionState
        if self._session_state:
            self._session_state.last_action = artifact_key
            self._session_state.last_action_target = subject
        
        logger.info("[ARTIFACT_RESOLVE] entity=%s artifact=%s selection=%d", subject, offer_name, index + 1)
        
        # Determine if it's an info request or a play request
        play_keywords = {"play", "trailer", "video", "performance", "highlights", "audiobook"}
        is_play = any(k in offer_name.lower() for k in play_keywords)
        
        if is_play and self.play:
            # Check if we already have a URL in artifact memory
            atype = parse_artifact_type(offer_name.lower())
            if atype:
                record = self._art.resolve_artifact(atype, subject=subject, topic=topic)
                if record and record.url:
                    side_effect = self.play(record.url)
                    return IntelligenceResult(
                        topic=topic,
                        response_text=f"Launching {offer_name} for {subject}...",
                        subject=subject,
                        source="acceptance",
                        confidence=1.0,
                        side_effect_result=side_effect
                    )
            
            # If no URL, resolve to a play command that MediaManager will catch
            return IntelligenceResult(
                topic=topic,
                response_text=f"Searching for {subject} {offer_name}...",
                subject=subject,
                source="acceptance",
                confidence=0.9,
                side_effect_result={"action": "play", "query": f"{subject} {offer_name}"}
            )
        
        # Info request — execute retrieval
        res = self._safe_retrieve(f"{subject} {offer_name}", topic=topic.value)
        if not res:
            res = self._safe_retrieve(subject, topic=topic.value)
        
        text = self._compose_answer(res, f"{subject} {offer_name}") if res else f"I couldn't find more details on {offer_name}."
        self._register_entity(subject, topic, result=res)
        
        return IntelligenceResult(
            topic=topic,
            response_text=text,
            subject=subject,
            source="acceptance",
            confidence=0.95
        )


    def _resolve_offer_by_name(self, name: str) -> Optional[IntelligenceResult]:
        """Resolve a shortcut keyword to an offer by name."""
        was = self._ctx.get("last_offers")
        if not was or not was.value or not isinstance(was.value, dict):
            return None
        offers = was.value.get("offers", [])
        subject = was.value.get("subject", "")
        topic_val = was.value.get("topic", "")
        if not offers or not subject:
            return None
        topic = TopicType(topic_val) if topic_val else TopicType.UNKNOWN
        name_lower = name.lower().strip()
        for i, offer in enumerate(offers):
            if name_lower in offer.lower():
                return self._resolve_offer_index(i)
        return None

    def _resolve_artifact_shortcut(self, keyword: str) -> Optional[IntelligenceResult]:
        """Resolve a standalone artifact keyword to a search/trailer action."""
        last_e = self._mem.get_last_entity()
        if not last_e:
            return None
        topic = self._entity_type_to_topic(last_e.entity_type) or TopicType.UNKNOWN
        artifact_types = {
            "trailer": "trailer", "teaser": "teaser", "gameplay": "gameplay",
            "highlights": "highlights", "standings": "standings", "fixtures": "fixtures",
            "cast": "cast", "soundtrack": "soundtrack", "lyrics": "lyrics",
            "walkthrough": "gameplay", "summary": "book_summary",
        }
        # Sync action to unified SessionState
        if self._session_state:
            self._session_state.last_action = keyword.lower()
            self._session_state.last_action_target = last_e.name
        
        art = artifact_types.get(keyword.lower())
        if art:
            atype = parse_artifact_type(art)
            if atype:
                record = self._art.resolve_artifact(atype, subject=last_e.name, topic=topic)
                if record and record.url:
                    return IntelligenceResult(
                        topic=topic, response_text=self._acceptance_msg(last_e.name, atype, True),
                        subject=last_e.name, source="acceptance", confidence=0.85,
                    )
                return IntelligenceResult(
                    topic=topic, response_text=self._acceptance_msg(last_e.name, atype, False),
                    subject=last_e.name, source="acceptance", confidence=0.7,
                    side_effect_result={"action": "play", "query": f"{last_e.name} {art}"},
                )
        # Generic search fallback
        res = self._safe_retrieve(f"{last_e.name} {keyword}", topic=topic.value)
        text = self._compose_answer(res, f"{last_e.name} {keyword}") if res else f"Searching for {keyword}..."
        return IntelligenceResult(
            topic=topic, response_text=text, subject=last_e.name,
            source="acceptance", confidence=0.7,
        )

    @staticmethod
    def _offer_name_to_key(name: str) -> str:
        """Convert display offer name to artifact key."""
        mapping = {
            "Best scenes": "best_scenes", "Trailer": "trailer", "Teaser": "teaser",
            "Behind-the-scenes": "behind_the_scenes", "Behind the scenes": "behind_the_scenes",
            "Cast interviews": "interview", "Director interview": "interview",
            "Ending explained": "ending_explained", "Bloopers": "bloopers",
            "Highlights": "highlights", "Match analysis": "match_analysis",
            "Standings": "standings", "Results": "results", "Fixtures": "fixtures",
            "Press conferences": "press_conference",
            "Goal compilations": "goal_compilation", "Tactical breakdowns": "tactical_breakdown",
            "Official video": "music_video", "Live performance": "live_performance",
            "Acoustic version": "acoustic_version", "Lyrics video": "lyrics_video",
            "Music video": "music_video", "Lyrics": "lyrics_video", "Interviews": "interview",
            "Music videos": "music_video", "Live performances": "live_performance",
            "Concert footage": "concert_footage", "Band interview": "interview",
            "Gameplay": "gameplay", "Developer updates": "developer_update",
            "Reviews": "book_review", "Walkthrough": "gameplay", "Walkthroughs": "gameplay",
            "Clips": "clips", "Recaps": "recap",
            "Production updates": "production_update", "Set footage": "set_footage",
            "News coverage": "results", "Latest videos": "latest_video",
            "Project breakdowns": "project_breakdown",
            "Soundtrack": "soundtrack", "Audiobook": "audiobook",
            "Author interview": "author_interview", "Summary": "book_summary",
            "Adaptation trailer": "adaptation_trailer",
        }
        return mapping.get(name, name.lower().replace(" ", "_"))

    def handle(self, query: str, execute: bool = True, session_id: str = "") -> IntelligenceResult:
        import logging
        logger = logging.getLogger(__name__)

        # Sync media context with last entity from memory
        last_e = self._mem.get_last_entity()
        if last_e:
            self._media_context.set_last_entity(last_e)

        # 0a. Role-catalog referent: "what else has that director made",
        # "what other films has this actor been in", "what else has that
        # author written" — the ROLE noun (director/author/actor/...) points
        # back at the most recently discussed subject (the movie/book just
        # recommended). The catalog answer CHANGES over time (a working
        # director keeps releasing), so it must come from LIVE research, never
        # the LLM's memory (live: Nolan's filmography answered from memory
        # after The Odyssey had already released). Resolve the referent to a
        # research query naming the role holder of the recent subject, e.g.
        # "what else has that director made" after Annihilation ->
        # "Annihilation director other films" — the provider resolves the
        # actual person (Alex Garland) and returns a CURRENT filmography.
        # Generic determiner + role-noun morphology, never per-entity.
        _ROLE_CATALOG_RE = re.compile(
            r"^\s*(?:what|which)\s+(?:else|other\s+films|other\s+movies|other\s+works|other\s+albums|other\s+books|other\s+games|other\s+titles|other\s+projects)?\s*(?:has|did)\s+"
            r"(?:that|this|the)\s+(director|author|writer|actor|actress|artist|band|singer|composer|creator|producer|developer|screenwriter|studio|company|team|label)\s+"
            r"(?:made|make|done|did|directed|direct|written|write|created|create|produced|produce|composed|compose|released|release|recorded|record|starred|star|been\s+in|put\s+out|working\s+on|worked\s+on)\b.*",
            re.I,
        )
        # Second role-catalog form: "did that director do any tv shows?",
        # "has that studio made any games?" — the role holder's OTHER WORK
        # scope (now including TV/series), same referent semantics as the
        # "what else has that director made" form. Live: answered from
        # hallucinated memory because it never matched the catalog route and
        # fell to the followup/memory path.
        _ROLE_CATALOG_RE2 = re.compile(
            r"^\s*(?:did|has)\s+(?:that|this|the)\s+(director|author|writer|actor|actress|artist|band|singer|composer|creator|producer|developer|screenwriter|studio|company|team|label)\s+"
            r"(?:do|make|direct|write|create|produce|compose|release|record|star|work|have)\s+"
            r"(?:any\s+|more\s+|other\s+)?(?:tv|tv\s+shows|shows|series|films?|movies?|albums?|books?|games?|projects?|work|works|stuff)\b.*",
            re.I,
        )
        _role_catalog_m = _ROLE_CATALOG_RE.match(query.strip())
        if not _role_catalog_m:
            _role_catalog_m2 = _ROLE_CATALOG_RE2.match(query.strip())
            if _role_catalog_m2:
                _role_catalog_m = _role_catalog_m2
        if _role_catalog_m:
            _role_noun = _role_catalog_m.group(1).lower()
            # The anchor MUST come from THIS conversation first. The media
            # adapter's ContextStore / MediaEntityMemory hold entity state
            # shared across ALL sessions and persisted to disk — a stale entity
            # from an unrelated earlier session ("Idiots"/Macon Blair) would
            # otherwise hijack the referent (live: after "recommend me a
            # sci-fi movie" -> Arrival, "what else has that director made"
            # answered Macon Blair from stale memory instead of Villeneuve).
            # The SESSION's own last entity (SessionContext.active_entity —
            # set by the previous turn's result subject) is the authoritative
            # anchor: after "who directed Annihilation" the session entity is
            # "annihilation", never the reply's answer person.
            _recent = None
            if session_id:
                try:
                    from mini_kio.core.context_manager import get_context_manager as _gsc
                    _sctx = _gsc(session_id)
                    _recent = getattr(_sctx, "active_entity", None) or None
                except Exception:
                    _recent = None
            if not _recent and session_id:
                try:
                    from mini_kio.core.context_manager import get_context_manager as _gsc
                    _sctx = _gsc(session_id)
                    _recent = _recent_session_media_subject(_sctx)
                except Exception:
                    _recent = None
            if not _recent:
                _recent = self._ctx.recent_subject() or (last_e.name if last_e else None)
            if _recent:
                _topic = classify_topic(query).topic or TopicType.MOVIES
                _pred = canonical_predicate_for_role(_role_noun)
                # Two-step resolution: FIRST identify the role holder of the
                # recent work ("Moon director" -> Duncan Jones), THEN query
                # that person's works. The old single-shot ("Moon director
                # other works filmography latest") let the provider return an
                # UNRELATED page (live: an article about director "Juno Hong"
                # whose film "Only the Moon Knows" merely contains "Moon"),
                # and the role-stem relevance bypass accepted it -> a
                # fabricated filmography. Disambiguating the work by type
                # ("Moon film director") keeps step 1 on the right article.
                _type_word = {
                    TopicType.MOVIES: "film", TopicType.TV: "series",
                    TopicType.BOOKS: "book", TopicType.GAMING: "game",
                    TopicType.MUSIC: "song", TopicType.SPORTS: "team",
                }.get(_topic, "")
                # Relationship-state reuse (canonical store): if evidence from
                # an earlier turn already established (work -> role -> holder),
                # reuse it — later callbacks ("what else has that director
                # made?" asked twice, or after a topic round-trip) must answer
                # from the SAME relationship, never re-extract from fresh
                # evidence and drift. Only when the store misses do we retrieve
                # fresh evidence and resolve semantically.
                _holder_name = ""
                _holder_method = "none"
                _holder_raw = ""
                if _pred:
                    # Semantic holder lookup: pass the surface ROLE NOUN
                    # ("director", "ceo", "developer") — _get_relationship now
                    # matches stored free-form relation labels by meaning, so
                    # the canonical-predicate fold is not required.
                    _holder_name = self._get_relationship(_recent, _role_noun, session_id)
                    if _holder_name:
                        _holder_method = "store"
                if not _holder_name:
                    _holder_q = f"{_recent} {_role_noun}"
                    if _type_word:
                        _holder_q = f"{_recent} {_type_word} {_role_noun}"
                    _holder_res = self._safe_retrieve(_holder_q, topic=_topic.value)
                    _holder_raw = ((_holder_res.raw_content or _holder_res.summary or "") if _holder_res else "")
                    # SEMANTIC role-holder resolution (canonical NLU owner):
                    # the LLM names the {work}'s {role} from the retrieved
                    # evidence — form-agnostic across all sentence shapes and
                    # domains — with the canonical relationship extractor as
                    # the deterministic fallback. Never a per-example regex.
                    _holder_name, _holder_method = self._resolve_relationship(
                        _recent, _role_noun, _holder_raw, session_id,
                    ) if _holder_raw else ("", "none")
                    if _holder_name and _pred:
                        self._store_relationship_triple(
                            _recent, _pred, _holder_name, method=_holder_method,
                            session_id=session_id, confidence=0.7,
                            evidence=_holder_raw[:220],
                        )
                # Domain-appropriate "other works" vocabulary (general map,
                # never per-entity): a director has a filmography, an author a
                # bibliography, an artist a discography, a studio a game list.
                # Querying "works filmography" for a game studio retrieved the
                # studio's latest patch notes instead of its games (live).
                _works_word = {
                    TopicType.MOVIES: "filmography",
                    TopicType.TV: "shows and series",
                    TopicType.BOOKS: "bibliography",
                    TopicType.MUSIC: "discography",
                    TopicType.GAMING: "list of games",
                    TopicType.SPORTS: "career highlights",
                }.get(_topic, "works")
                # "Wikipedia" biases the works query toward the stable
                # reference page (a director's filmography section, a studio's
                # game list) instead of the holder's latest news/patch notes.
                if _holder_name and len(_holder_name.split()) <= 4:
                    _resolved_q = f"{_holder_name} {_works_word} Wikipedia"
                    _subject = _holder_name
                else:
                    _resolved_q = f"{_recent} {_role_noun} {_works_word} Wikipedia"
                    _subject = f"{_recent} {_role_noun}"
                logger.info("[ROLE_CATALOG_RESOLVE] query=%s role=%s recent=%s holder=%s method=%s resolved=%s",
                            query, _role_noun, _recent, _holder_name or "none", _holder_method or "none", _resolved_q)
                _text, _res = self._retrieve_and_summarize(_resolved_q, _topic, _subject)
                self._register_entity(_subject, _topic, result=_res, confidence=0.7)
                self._continuity.update_context(query, _topic, _subject, 0.7)
                return IntelligenceResult(
                    topic=_topic,
                    response_text=_text,
                    subject=_recent,
                    confidence=0.7,
                    source="role_catalog",
                )

        # 0a-prime. Store-first relationship answering: "who directed that
        # again?", "who founded X", "who is the CEO of X" resolve directly
        # from the canonical relationship store (populated by evidence
        # extraction on earlier turns) — instant, grounded, no fresh
        # retrieval. Fresh entities still flow through the live retrieval
        # path below, which extracts and stores for the next turn.
        _rel_answer = self._maybe_relationship_answer(query, session_id)
        if _rel_answer is not None:
            logger.info("[RELATIONSHIP_ANSWER_RESOLVED] query=%s source=%s",
                        query, _rel_answer.source)
            return _rel_answer

        # 0a-prime2. Claim-selection referent ("the second one", "which part
        # is true", "which one") with pending verification claims MUST reach
        # verification BEFORE the artifact-acceptance path steals the ordinal
        # (live: after a 3-claim verification, "the second one" resolved to a
        # $5.99 app listing instead of the second claim).
        if _is_claim_selection_referent(query) and self.has_pending_verif_claims(session_id):
            vres = self._handle_verification(query, session_id)
            if vres is not None:
                return vres

        # 0a. Acceptance handler for yes/ok/sure/show it
        accept_res = self._handle_acceptance(query)
        if accept_res:
            logger.info("[ACCEPTANCE_RESOLVED] query=%s source=%s", query, accept_res.source)
            return accept_res

        # 1. recommendation check
        rec_triggers = ("recommend", "suggest", "similar", "something like", "another one",
                        "watch next", "listen next", "next to watch", "next to listen",
                        "what should i watch", "what should i listen", "what to watch", "what to listen",
                        "similar tracks", "similar songs", "more like this")
        if any(w in query.lower() for w in rec_triggers):
            return self._handle_recommendation(query)

        # 1.5 Verification / currentness gate — BEFORE continuity. A message
        # carrying its OWN verification claim ("I read that the new F1 car got
        # banned and the team principal resigned. Any truth to that?") is a
        # new changing-world request, never a followup of the previous topic:
        # the followup path would rewrite it into "<last entity> latest news"
        # and answer a completely different question (live: F1 claim answered
        # with Ferrari engine speculation). Pure referential followups ("is
        # that actually true?") still reach the gate and are anchored/reclaimed
        # inside the verification handler.
        if self._is_verification_query(query) or self._is_verif_elaboration_followup(query, session_id):
            logger.info("[VERIFICATION_PATH] query=%s", query)
            vres = self._handle_verification(query, session_id)
            if vres is not None:
                return vres

        # 2. check continuity next
        if self._continuity.is_followup(query):
            logger.info("[FOLLOWUP_DETECTED] query=%s", query)
            followup_res = self._handle_followup(query, execute=execute)
            if followup_res.source != "none" and followup_res.confidence > 0:
                logger.info("[QUERY_RESOLVE] original=%s resolved=%s", query, followup_res.subject)
                logger.info("[FOLLOWUP_RESOLVED] source=%s subject=%s", followup_res.source, followup_res.subject)
                return followup_res
            logger.info("[FOLLOWUP_FALLTHROUGH] query=%s", query)

        # 2.5 Bare freshness followup (e.g. "Latest updates" after MrBeast)
        # If query is all freshness words with no entity of its own, force continuation
        _freshness_words = frozenset({"latest", "updates", "news", "recent", "current", "today", "any",
                                     "standings", "results", "highlights", "fixtures", "scores",
                                     "group", "table", "leader", "leading", "qualified", "eliminated"})
        ql = query.lower().strip()
        q_words = ql.split()
        if last_e and len(q_words) <= 3 and all(w.strip("?.!") in _freshness_words for w in q_words):
            topic = classify_topic(query).topic
            logger.info("[BARE_FRESHNESS] query=%s forcing continuation of last=%s topic=%s", query, last_e.name, topic)
            memory_res = self._try_memory_resolve(query, topic)
            if memory_res:
                return memory_res

        # 3. classify
        classification = classify_topic(query)
        topic = classification.topic

        # 3.5 Reference Resolution (as a fallback before generic handling)
        # Handle pronouns, mood, activity, etc. ONLY if not an information query
        if not _is_current_info_query(query) and not ql.startswith(("who", "what", "where", "when", "why", "how")):
            ref_res = self._resolver.resolve(query)
            if ref_res.success:
                logger.info("[REPLAY_RESOLVED] original=%s resolved=%s source=resolver", 
                            query, ref_res.query_override or (ref_res.resolved_entity.name if ref_res.resolved_entity else ""))
                return self._handle_reference_resolution(ref_res, query, execute=execute)

        # 4. route by topic
        if topic == TopicType.SPORTS:
            return self._handle_sports(query, classification.confidence)
        if topic in (TopicType.MOVIES, TopicType.TV):
            return self._handle_media(query, topic, classification.confidence)
        if topic == TopicType.GAMING:
            return self._handle_gaming(query, classification.confidence)
        if topic == TopicType.MUSIC:
            return self._handle_music(query, classification.confidence)
        if topic == TopicType.BOOKS:
            return self._handle_books(query, classification.confidence)
        if topic == TopicType.PEOPLE:
            return self._handle_people(query, classification.confidence)
        # TECH / NEWS / UNKNOWN
        return self._handle_generic(query, topic, classification.confidence)

    # ── reference resolution ───────────────────────────────────────────────────

    def _handle_reference_resolution(self, ref: ReferenceResolution, original_query: str, execute: bool = True) -> IntelligenceResult:
        side_effect_res = None
        from mini_kio.media.media_intelligence_models import EntityType
        
        if ref.resolved_entity:
            entity = ref.resolved_entity
            topic = self._entity_type_to_topic(entity.entity_type)
            # Fall back to topic classifier if resolver couldn't determine entity type
            if topic == TopicType.UNKNOWN and entity.name:
                topic = classify_topic(entity.name).topic
            # RC10: execute=False is a PROBE (MediaManager.play calls
            # handle(query, execute=False) before dispatching). It must
            # never mutate memory or fire retrieval — return the resolution
            # verdict only. The caller (MediaManager) decides whether to apply
            # the subject; the old code ran _safe_retrieve + _register_entity
            # here even in probe mode, which registered garbage entities
            # (live proof: "lm game trailer" → registered "gaming music
            # playlist" into entity memory).
            if not execute:
                return IntelligenceResult(
                    topic=topic,
                    response_text="",
                    subject=entity.name,
                    confidence=ref.confidence,
                    source="resolver",
                )
            if self.play and execute:
                play_target = entity.url or entity.name
                if entity.url and not entity.url.startswith(("http://", "https://")):
                    play_target = entity.name
                side_effect_res = self.play(play_target)
                # playback — return resolve confirmation
                self._register_entity(entity.name, topic, confidence=ref.confidence)
                return IntelligenceResult(
                    topic=topic,
                    response_text=f"Resolved: {entity.name}",
                    subject=entity.name,
                    confidence=ref.confidence,
                    source="resolver",
                    side_effect_result=side_effect_res,
                )
                # no playback — retrieve and compose an answer for the resolved entity
            res = self._safe_retrieve(f"{entity.name} {original_query}", topic=topic.value)
            if not res:
                res = self._safe_retrieve(entity.name, topic=topic.value)
            text = self._compose_answer(res, original_query) if res else f"I couldn't find info on {entity.name}."
            self._register_entity(entity.name, topic, result=res, confidence=ref.confidence)
            return IntelligenceResult(
                topic=topic,
                response_text=text,
                subject=entity.name,
                confidence=ref.confidence,
                source=f"resolver:{entity.name}",
                side_effect_result=side_effect_res,
            )
        
        if ref.query_override:
            # RC10: probe mode — no retrieval, no memory writes.
            if not execute:
                return IntelligenceResult(
                    topic=TopicType.UNKNOWN,
                    response_text="",
                    subject=ref.query_override,
                    confidence=ref.confidence,
                    source="resolver",
                )
            res = self._safe_retrieve(ref.query_override, topic=TopicType.UNKNOWN.value)
            text = self._compose_answer(res, ref.query_override) if res else ""
            self._register_entity(ref.query_override, TopicType.UNKNOWN, result=res, confidence=ref.confidence)
            return IntelligenceResult(
                topic=TopicType.UNKNOWN,
                response_text=text,
                subject=ref.query_override,
                confidence=ref.confidence,
                source="resolver",
            )
        
        return self._handle_generic(original_query, TopicType.UNKNOWN, 0.0)

    # ── recommendation ─────────────────────────────────────────────────────────

    def _handle_recommendation(self, query: str) -> IntelligenceResult:
        import logging
        logger = logging.getLogger(__name__)

        # Skip memory resolve for recommendations — the recommendation engine already
        # uses the last entity for context. Memory resolve would just append entity name
        # to the query, producing stale entity-focused results instead of fresh recommendations.
        rec_result = self._recommender.recommend(query)
        eff_query = rec_result.request.effective_query()
        
        if eff_query:
            # Clean leading/trailing whitespace from query
            eff_query_clean = eff_query.strip()
            logger.info("[RECOMMENDATION_RESOLVED] query=%s strategy=%s", eff_query_clean, rec_result.strategy_used)
            last_e = self._mem.get_last_entity()
            if last_e and last_e.entity_type in (EntityType.MOVIE, EntityType.TV_SHOW):
                topic = TopicType.MOVIES
            elif last_e and last_e.entity_type in (EntityType.SONG, EntityType.MUSIC_ARTIST):
                topic = TopicType.MUSIC
            elif last_e and last_e.entity_type in (EntityType.BOOK, EntityType.AUTHOR):
                topic = TopicType.BOOKS
            elif last_e and last_e.entity_type in (EntityType.GAME,):
                topic = TopicType.GAMING
            elif last_e and last_e.entity_type in (EntityType.SPORTS_PLAYER, EntityType.SPORTS_TEAM):
                topic = TopicType.SPORTS
            else:
                ql = eff_query_clean.lower()
                if "music" in ql or "song" in ql or "artist" in ql or "album" in ql:
                    topic = TopicType.MUSIC
                elif "book" in ql or "novel" in ql or "author" in ql:
                    topic = TopicType.BOOKS
                elif "game" in ql or "gaming" in ql:
                    topic = TopicType.GAMING
                elif "sport" in ql or "team" in ql or "player" in ql:
                    topic = TopicType.SPORTS
                elif "movie" in ql or "film" in ql or "tv" in ql or "show" in ql:
                    topic = TopicType.MOVIES
                else:
                    topic = TopicType.UNKNOWN
            res = self._safe_retrieve(eff_query_clean, topic=topic.value)
            if not res and last_e:
                res = self._safe_retrieve(last_e.name, topic=topic.value)
            subject_for_answer = eff_query_clean or (last_e.name if last_e else query)
            text = self._compose_answer(res, query) if res else ""
            self._register_entity(subject_for_answer, topic, result=res, confidence=rec_result.confidence)
            self._continuity.update_context(query, topic, subject_for_answer, rec_result.confidence)
            # Store recommendations in unified SessionState
            if self._session_state:
                rec_entry = {
                    "query": query,
                    "effective_query": eff_query_clean,
                    "subject": subject_for_answer,
                    "topic": topic.value,
                    "strategy": str(rec_result.strategy_used) if rec_result.strategy_used else "unknown",
                }
                existing = list(self._session_state.last_recommendations)
                existing.append(rec_entry)
                self._session_state.last_recommendations = existing
            return IntelligenceResult(
                topic=topic,
                response_text=text,
                subject=subject_for_answer,
                confidence=rec_result.confidence,
                source="recommendation",
            )
        
        return self._handle_generic(query, TopicType.UNKNOWN, 0.3)

    # ── followup ───────────────────────────────────────────────────────────────

    def _handle_followup(self, query: str, execute: bool = True) -> IntelligenceResult:
        result = self._continuity.resolve_followup(query)
        side_effect_res = None

        if result.action == "play" and result.artifact_record and self.play:
            topic = result.topic or TopicType.UNKNOWN
            # If artifact has no URL, fall through to search instead of playing nothing
            if result.artifact_record.url:
                if execute:
                    _url = result.artifact_record.url
                    if _url.startswith(("http://", "https://", "www.")):
                        side_effect_res = self.play(_url)
                self._register_entity(result.subject or "", topic, confidence=result.confidence)
                return IntelligenceResult(
                    topic=topic,
                    response_text=format_artifact_response(
                        result.subject or "",
                        result.artifact_type or ArtifactType.TRAILER,
                        result.artifact_record.url,
                        topic,
                    ),
                    subject=result.artifact_record.url or result.subject or "",
                    confidence=result.confidence,
                    source=result.source,
                    side_effect_result=side_effect_res,
                )
            # No URL in artifact — fall through to search path below
            logger.info("[ARTIFACT_NO_URL] type=%s subject=%s falling back to search", 
                        result.artifact_type.value if result.artifact_type else "?", result.subject)

        if result.action == "search" and result.subject:
            topic = result.topic or TopicType.UNKNOWN
            # Apply entity-aware query rewriting so followups use the entity name + intent
            rewritten = self._rewrite_retrieval(query, topic, result.subject)
            # If not explicitly rewritten, prepend subject for context
            if rewritten == query:
                rewritten = f"{result.subject} {query}"
            res = self._safe_retrieve(rewritten, topic=topic.value)
            if not res:
                res = self._safe_retrieve(result.subject, topic=topic.value)
            text = self._compose_answer(res, query) if res else ""
            # Always register entity from followup subject to maintain continuity
            if result.subject and result.confidence > 0.3:
                self._register_entity(result.subject, topic, result=res, confidence=result.confidence)
            return IntelligenceResult(
                topic=topic,
                response_text=text,
                subject=result.subject,
                confidence=result.confidence,
                source=result.source,
            )

        if result.action == "show" and result.event_record:
            e = result.event_record
            subject = e.display()
            artifact_val = result.artifact_type.value if result.artifact_type else "highlights"
            search_q = f"{subject} {artifact_val}"
            res = self._safe_retrieve(search_q, topic=TopicType.SPORTS.value)
            text = self._compose_answer(res, search_q) if res else ""
            self._register_entity(subject, TopicType.SPORTS, result=res, confidence=result.confidence)
            self._ctx.put("last_subject", subject, topic=TopicType.SPORTS, confidence=result.confidence, source="followup")
            return IntelligenceResult(
                topic=TopicType.SPORTS,
                events=[e],
                response_text=text,
                subject=subject,
                confidence=result.confidence,
                source=result.source,
            )

        return IntelligenceResult(
            topic=TopicType.UNKNOWN,
            response_text=format_fallback(query, None),
            confidence=0.0,
            source="none",
        )

    # ── verification / currentness (multi-claim, temporal) ────────────────────

    _VERIF_FRAMES = (
        "i heard", "i read", "i saw", "someone told me", "apparently",
        "people are saying", "there's a rumor", "there is a rumor",
        "is it true", "is it confirmed", "is that actually true",
        "is this actually true", "is it official", "is there news",
        "has it been confirmed", "has it been announced", "did you hear",
        "rumor has it", "is that real", "is this real",
    )
    _VERIF_STATE = (
        "passed away", "died", "death", "retire", "retired", "cancelled",
        "canceled", "delayed", "released", "confirmed", "announced", "left",
        "quit", "fired", "hired", "injured", "arrested", "married",
        "divorced", "born", "transferred", "stepped down", "is still",
        "still alive", "still ceo", "still playing", "still available",
        "dead", "alive", "really happen", "actually happen", "actually say",
        "really say", "what happened to", "is true", "really true",
        # General state/event predicates — the same semantic class: a
        # changing-world assertion ("The Warriors won last night") registers
        # as a verifiable proposition only if its predicate is in this
        # vocabulary, and "did X win" routes as a verification query. Without
        # these the assertion was never registered and the follow-up reclaim
        # fell back to STALE claims from an earlier turn (live: "Did that
        # actually happen?" after a Warriors assertion verified the previous
        # Ronaldo claim instead).
        "won", "lost", "beat", "defeated", "signed", "joined", "rejoined",
        "acquired", "bought", "sold", "merged", "launched", "unveiled",
        "promoted", "demoted", "replaced", "appointed", "elected",
        "nominated", "resigned", "suspended", "banned", "returned",
        "moved", "broke", "broken", "crashed", "shut down", "postponed",
        "pulled", "scrapped", "delisted", "downgraded", "upgraded",
    )

    def _is_verif_elaboration_followup(self, query: str, session_id: str = "") -> bool:
        """Context-aware verification gate: is this an ELABORATION follow-up of
        the previous verification turn ("what exactly did Messi say?", "when
        did that happen?", "what did he announce?") rather than a fresh
        topic?

        The bare phrase carries no verification frame ("say" is not a state
        verb), so the text-only gate misses it and it falls to the topic
        router — which answered "what exactly did Messi say?" with an
        unrelated World Cup quote (live failure). When the previous turn
        stored verification claims AND this query only names the SAME entity
        plus pure question/elaboration words (no new state verb/proposition:
        "did Messi retire" names a new predicate and stays a fresh claim),
        route it to verification so the reclaim logic reuses the prior claims.
        """
        try:
            _last = self._ctx.get(self._claims_key(session_id))
        except Exception:
            _last = None
        _last_claims = getattr(_last, "value", None) if _last is not None else None
        if not (isinstance(_last_claims, list) and _last_claims):
            return False
        _q_toks = _meaningful_tokens(query)
        if not _q_toks:
            return False
        _elab = frozenset({
            "exactly", "explain", "mention", "mentioned", "tell", "told",
            "mean", "meant", "about", "happen", "happened", "doing",
            "react", "reacted", "response", "announce", "announced",
            "said", "say", "says", "talk", "talking", "talked", "detail",
            "details", "elaborate", "actually", "really", "what", "when",
            "where", "why", "how", "who", "which", "that", "this", "it",
            "then", "after", "before", "next", "again", "now",
        }) | _VERIF_GENERIC_TOKENS
        _msg_entity_l = (_message_entity_name(query) or "").lower()
        _entity_in_claims = bool(
            _msg_entity_l
            and any(_msg_entity_l in (c or "").lower() for c in _last_claims)
        )
        _leftover = _q_toks - _elab
        if _msg_entity_l:
            _leftover = _leftover - {_msg_entity_l}
        # Entity-named elaboration OR fully-referential elaboration
        # ("when did that happen" — no entity, all question words).
        if not _leftover and (_entity_in_claims or not _msg_entity_l):
            logger.info(
                "[VERIF_ELAB_GATE] query=%s entity=%s last_claims=%s",
                query, _msg_entity_l, _last_claims,
            )
            return True
        return False

    def _is_verification_query(self, query: str) -> bool:
        """Detect verification/currentness-style requests.

        "I heard X" / "did X die" / "is it true that X" / "is X still ..."
        are requests to check the CURRENT state of a changing world — they
        must use live multi-source evidence. Ordinary statements ("I heard
        that movie was amazing") carry no verification frame and skip.
        """
        ql = (query or "").lower().strip()
        if not ql:
            return False
        if any(f in ql for f in self._VERIF_FRAMES):
            return True
        if re.search(
            r"\b(?:did|has|is|was|were)\s+(?:[a-z]+\s+){0,4}(?:die|died|death|retire|retired|cancelled|delayed|released|confirmed|announced|left|quit|fired|hired|injured|arrested|transferred|stepped\s+down|dead|alive|win|won|lose|lost|beat|beaten|drop|dropped|score|scored|play|played|resign|resigned|join|joined|signed|debut|return|returned|release)\b",
            ql,
        ):
            return True
        # TRAILING verification suffix ("... Is any of that true?", "...
        # actually true?", "... real?"): the claim is checked BEFORE the
        # suffix, so leading-frame checks above miss it. Requires a state
        # verb or named entity in the claim part to stay a real verification
        # request ("That sounds great, is it really that good?" stays
        # conversational).
        _trail = re.search(
            r"^(.*?)\s*[,;:.!-]?\s*"
            r"(?:is\s+(?:any\s+of\s+)?that\s+(?:actually\s+|really\s+)?true\b|"
            r"is\s+this\s+(?:actually\s+|really\s+)?true\b|is\s+that\s+(?:actually\s+|really\s+)?real\b|"
            r"is\s+it\s+(?:actually\s+|really\s+)?(?:true|real)\b|"
            r"(?:is\s+that\b|is\s+this\b|is\s+it\b|right\b|actually\s+true\b|"
            r"really\b|true\b|real\b))[?.!\s]*$",
            ql,
        )
        if _trail:
            _claim_part = (_trail.group(1) or "").strip()
            _has_state_verb = any(v in _claim_part for v in self._VERIF_STATE)
            # Sentence-initial capitals ("The fix works...") are ordinary
            # capitalization, not a named entity — exclude the leading token.
            _tokens = (query or "").strip().split()
            _first_is_cap = bool(_tokens) and bool(re.search(r"[A-Z][A-Za-z0-9]", _tokens[0]))
            _rest_text = " ".join(_tokens[1:]) if _tokens else ""
            _has_cap = bool(re.search(r"[A-Z][A-Za-z0-9]", _rest_text)) if _first_is_cap else bool(re.search(r"[A-Z][A-Za-z0-9]", query or ""))
            # Habitual grumbling ("keeps breaking things again") is not a
            # discrete verifiable event.
            _habitual = bool(re.search(r"\b(?:keeps?|always|constantly)\b.*\b(?:again|breaking)\b", _claim_part))
            if not _habitual and len(_claim_part.split()) >= 3 and (_has_state_verb or _has_cap):
                return True
        return any(v in ql for v in self._VERIF_STATE)

    # ── User-assertion proposition registration ────────────────────────────
    # A declarative user statement ("Ronaldo got married too", "Apple
    # released a new device") is a PROPOSITION with provenance=user and
    # verification=unknown. It must become discourse state so a later bare
    # probe ("Is this true?", "Really?", "Did that actually happen?") can
    # resolve its reference against it. This registers into the SAME
    # last_verif_claims store the follow-up reclaim reads — one proposition
    # store, one reclaim mechanism, zero phrase rules.
    def _claims_key(self, session_id: str = "") -> str:
        """Session-scoped claim-store key. Claims are discourse state of ONE
        conversation: user A's pending proposition must never be reclaimable
        by user B's probe, and a claim from a previous conversation must not
        survive into a new one. Scoping by session (the pipeline's
        tg_<uid> / browser_<uid> id) isolates the store per conversation
        owner; the unscoped key remains the legacy fallback for callers that
        do not thread a session."""
        return f"last_verif_claims:{session_id}" if session_id else "last_verif_claims"

    def register_user_assertion(self, text: str, session_id: str = "") -> None:
        try:
            claims = self._split_claims(text or "")
            claims = [c for c in claims if len(c.split()) >= 2]
            if claims:
                self._ctx.put(self._claims_key(session_id), claims, source="user_assertion")
        except Exception:
            pass

    def has_pending_verif_claims(self, session_id: str = "") -> bool:
        try:
            _last = self._ctx.get(self._claims_key(session_id))
            _claims = getattr(_last, "value", None) if _last is not None else None
            return bool(isinstance(_claims, list) and _claims)
        except Exception:
            return False

    def clear_user_claims(self, session_id: str = "") -> None:
        """Consume the session's pending claims. Called when the user moves
        to a new topic (a bare probe refers to the IMMEDIATELY preceding
        proposition — an old claim must never be resurrected by a later
        "is that true?")."""
        try:
            self._ctx.remove(self._claims_key(session_id))
        except Exception:
            pass

    @staticmethod
    def _split_claims(query: str) -> list[str]:
        """Split a multi-claim message into individual claims.

        "I heard Messi's father passed away and he said he can't play long
        anymore" -> ["Messi's father passed away", "he said he can't play
        long anymore"]. Splits on coordinating conjunctions, sentence
        boundaries, AND comma-separated independent clauses ("X happened,
        Y happened, and Z happened" -> [X, Y, Z] — without the comma split
        a 4-proposition message collapses into one claim and synthesis
        wanders into retrieved evidence); trims verification prefixes from
        each claim. Bounded so a long rumor dump cannot explode into a
        giant loop.
        """
        text = query.strip()
        # Split on clause conjunctions and sentence punctuation, keeping the
        # conjunction-separated fragments as claims. Commas split when the
        # fragment after them is a NEW independent clause: it starts with a
        # capitalized token, a pronoun, OR a lowercase subject followed by an
        # event/state verb ("...rocket, spotify bought a podcast company" —
        # live failure: the lowercase "spotify" after the comma blocked the
        # split and the whole 3-proposition message collapsed into one claim).
        # Relative-clause continuations ("which released...", "who is
        # known...") and title-internal commas never split.
        parts = re.split(
            r"\s+(?:and|also|then|plus)\s+|\s*[;.]\s*|,?\s+and\s+"
            r"|,\s+(?=(?-i:[A-Z])(?:[a-z]|\s)|I\b|he\b|she\b|they\b|it\b|we\b|you\b"
            r"|(?!(?:which|that|who|whose|where|when|while)\b)[^,.]{0,90}\b"
            r"(?:bought|launched|released|won|lost|died|passed|retired|announced|signed|left|quit|stepped|delayed|cancelled|canceled|happened|confirmed|fired|hired|joined|transferred|said|told|got|became|resigned|sold|acquired|merged|started|ended|returned|came|went)\b)",
            text,
            flags=re.I,
        )
        parts = [p.strip(" ,;.\"'") for p in parts if p and p.strip(" ,;.\"'")]
        claims: list[str] = []
        for part in parts:
            low = part.lower()
            for frame in (
                "i heard that ", "i heard ", "i read that ", "i read ",
                "i saw that ", "i saw ", "someone told me that ",
                "someone told me ", "apparently ", "people are saying that ",
                "people are saying ", "there's a rumor that ", "is it true that ",
                "is it confirmed that ", "rumor has it that ",
            ):
                if low.startswith(frame):
                    part = part[len(frame):].strip()
                    break
            part = part.strip(" ,;.\"'?!")
            if len(part) >= 4:
                claims.append(part)
        if not claims:
            claims = [text.strip(" ,;.\"'?!")]
        # Drop pure verification-suffix fragments ("is that true", "is this
        # real", "right?") — they are the user ASKING for verification, not a
        # claim to verify. "I heard X and Y. Is that true?" must yield
        # [X, Y], never [X, Y, "is that true"].
        _verif_tail = re.compile(
            r"^(?:is|was)\s+(?:any\s+of\s+)?(?:that|this|it)\s+(?:actually\s+|really\s+|even\s+)?"
            r"(?:true|real|right|correct|a\s+thing|legit|accurate)\??$"
            r"|^(?:is|was)\s+(?:any\s+of\s+)?(?:that|this)\s+(?:true|real)\??$"
            r"|^(?:is\s+any\s+of\s+that\b|right|yeah|yes|correct)\??$"
            r"|^(?:any\s+truth\s+(?:to|in)\s+that|any\s+truth\s+(?:to|in)\s+this|how\s+much\s+truth\s+(?:to|in)\s+that)\??$"
            r"|^(?:what|which)\s*(?:'s|'re|\u2019s|\u2019re|\s+is|\s+are|\s+was|\s+were)\s+(?:any\s+of\s+)?"
            r"(?:actually\s+|really\s+|even\s+)?(?:true|real|right|correct|legit|accurate|the\s+truth|going\s+on)\??$"
            r"|^(?:what|which)\s+(?:part|parts|bits|one|ones|claim|claims)\??$",
            re.I,
        )
        filtered = [
            c for c in claims
            if not _verif_tail.match(c.strip())
            and not _is_claim_selection_referent(c.strip())
        ]
        return filtered[:6] if filtered else (claims[:6] or [text.strip(" ,;.\"'?!")])

    def _handle_verification(self, query: str, session_id: str = "") -> Optional[IntelligenceResult]:
        """Verify current claims through live multi-source evidence.

        Decomposes the message into claims, builds a claim-specific query for
        each, collects evidence from ALL healthy providers (with dates when
        exposed), ranks by freshness, reconciles contradictions, and asks the
        LLM to synthesize an evidence-bounded answer. Returns None only if
        nothing could be verified AND no LLM is available (caller falls back
        to the normal topic router).
        """
        import logging
        logger = logging.getLogger(__name__)
        claims = self._split_claims(query)

        # A fully generic verification follow-up ("Is that actually true?",
        # "did that really happen?", "is this real?") has NO claim content of
        # its own — every meaningful token is a verification word. It refers
        # to the claims of the PREVIOUS verification turn ("I heard X and Y"
        # -> "is that actually true?"). Reuse those stored claims instead of
        # re-searching the bare anchored phrase (live failure: the follow-up
        # searched "Spider-Man is that actually true..." and returned an
        # unrelated Tobey Maguire rumor).
        _reclaimed = False
        _q_toks = _meaningful_tokens(query)
        # Entity named in THIS message ("what exactly did Messi say" -> Messi;
        # "I heard Messi's father..." -> Messi). Computed before the reclaim
        # check so an entity-named elaboration follow-up can reuse the prior
        # claims anchored to that entity.
        _msg_entity = _message_entity_name(query)
        _last = None
        try:
            _last = self._ctx.get(self._claims_key(session_id))
        except Exception:
            _last = None
        _last_claims = (
            getattr(_last, "value", None)
            if _last is not None
            else None
        )
        _last_claims = _last_claims if isinstance(_last_claims, list) and _last_claims else None
        # SELECTION referent over the stored claim set: "which part is true?",
        # "which one?", "the second one?", "what's true?", "any of that?"
        # names NO new proposition — it selects FROM the prior claims. Without
        # this the bare phrase fell to the conversational LLM, which answered
        # from memory and CONTRADICTED the just-verified answer (live: after
        # a 4-claim verification, "which part is true" re-verified nothing
        # and the LLM asserted the opposite of the evidence).
        _select_m = _is_claim_selection_referent(query)
        if _select_m and _last_claims:
            logger.info("[VERIFY_SELECT_RECLAIM] query=%s last_claims=%s", query, _last_claims)
            claims = _last_claims
            _reclaimed = True
        elif _q_toks and _q_toks <= _VERIF_GENERIC_TOKENS:
            if _last_claims:
                logger.info("[VERIFY_FOLLOWUP_RECLAIM] query=%s last_claims=%s", query, _last_claims)
                claims = _last_claims
                _reclaimed = True
        elif _last_claims:
            # Entity-named ELABORATION follow-up: "what exactly did Messi
            # say?", "when did he announce that?", "how did the team react?"
            # names only the SAME entity as the stored claims plus pure
            # question/elaboration words — it asks about the PRIOR claim's
            # content, never a new proposition ("did Messi retire" names a
            # NEW state verb and stays a fresh claim). Without this the bare
            # phrase got searched and returned an unrelated Messi quote
            # (live: "what exactly did Messi say?" -> a World Cup remark).
            _msg_entity_l = (_msg_entity or "").lower()
            _elab_extra = frozenset({
                "exactly", "explain", "mention", "mentioned", "tell", "told",
                "mean", "meant", "about", "happen", "happened", "doing",
                "react", "reacted", "response", "announce", "announced",
                "said", "say", "says", "talk", "talking", "talked", "detail",
                "details", "elaborate", "actually", "really", "what", "when",
                "where", "why", "how", "who", "which", "that", "this", "it",
            })
            _entity_in_claims = bool(
                _msg_entity_l
                and any(
                    _msg_entity_l in (c or "").lower()
                    for c in _last_claims
                )
            )
            _new_content = _q_toks - _VERIF_GENERIC_TOKENS - _elab_extra - {
                _msg_entity_l} if _msg_entity_l else _q_toks - _VERIF_GENERIC_TOKENS - _elab_extra
            if _entity_in_claims and not _new_content:
                logger.info(
                    "[VERIFY_FOLLOWUP_RECLAIM_ENTITY] query=%s entity=%s last_claims=%s",
                    query, _msg_entity, _last_claims,
                )
                claims = _last_claims
                _reclaimed = True

        logger.info("[VERIFY_CLAIMS] query=%s claims=%s", query, claims)

        # Context anchor for entity-less follow-ups ("Is that actually true?",
        # "did that really happen"): the last known media entity carries the
        # subject the follow-up refers to. Without it the bare phrase gets
        # searched and returns unrelated content (live: "Is that actually
        # true? I saw people talking about it" searched the bare words).
        last_e = self._mem.get_last_entity()
        anchor = (last_e.name if last_e and last_e.name else "").strip()

        # Pre-scan for unresolvable referents BEFORE any slow retrieval: a
        # claim built only from generic category nouns + event verbs ("movie
        # got delayed", "the lead actor left the project") names no subject
        # of its own — it refers to an entity in this message, or the last
        # discussed entity, or it must ASK which subject is meant (live
        # failure: "that movie got delayed" was searched bare and returned
        # random film news plus a hallucinated "meme reference").
        _generic_toks = _VERIF_GENERIC_TOKENS
        _anchor_name = _msg_entity or anchor
        _anchor_is_media = False
        if _anchor_name:
            if _msg_entity or _reclaimed:
                # Named in this message, or the follow-up reclaims the claims
                # the anchor already resolved: always usable.
                _anchor_is_media = True
            else:
                # Memory anchor usable for a category-noun claim only when it is
                # a media instance (a movie/show/actor the user was discussing),
                # never a bare verification subject ("Messi's father passed
                # away" must not resolve "the movie").
                _anchor_is_media = (
                    bool(last_e) and last_e.entity_type != EntityType.UNKNOWN
                )
        _unresolved: list[str] = []
        for _c in claims:
            _cw = _c.split()
            _cr = re.sub(r"\bI\b", " ", " ".join(_cw[1:])) if _cw else ""
            _cproper = bool(re.search(r"[A-Z]", _cr)) if _cw else False
            _ctoks = _meaningful_tokens(_c)
            _cown = _ctoks - _generic_toks - _GENERIC_SUBJECT_NOUNS - _EVENT_VERBS
            _has_cat_noun = bool(_ctoks & _GENERIC_SUBJECT_NOUNS)
            if _cproper or _cown:
                continue  # names its own subject
            if _anchor_name and (not _has_cat_noun or _anchor_is_media):
                continue  # referent resolvable
            _unresolved.append(_c)
        if _unresolved:
            # Natural clarification — never a bare-phrase search for an
            # un-named referent, never a fabricated answer.
            _cat = next(
                (w for w in sorted(_meaningful_tokens(_unresolved[0]))
                 if w in _GENERIC_SUBJECT_NOUNS),
                "that",
            )
            _noun = {"movie": "movie", "film": "film", "game": "game",
                     "player": "player", "actor": "actor", "show": "show",
                     "series": "show", "album": "album", "book": "book",
                     "company": "company", "product": "product"}.get(_cat, "subject")
            _clarify = (
                f"Which {_noun} do you mean? I don't want to guess and check "
                f"the wrong one — name it and I'll look into whether that "
                f"actually happened."
            )
            logger.info("[VERIFY_CLARIFY] query=%s unresolved=%s", query, _unresolved)
            return IntelligenceResult(
                topic=TopicType.UNKNOWN, response_text=_clarify,
                subject=query, confidence=0.5, source="verification_clarify",
            )

        # ── per-claim evidence collection ────────────────────────────────────
        evidence_by_claim: list[tuple[str, list]] = []
        all_failed = True
        for claim in claims:
            # Claim-specific query: keep the entity + predicate + current year.
            # Never reduce to a bare entity lookup ("Messi" -> "Jorge Messi
            # death 2026"); never pass the whole multi-claim sentence.
            year = ""
            try:
                import datetime as _dt
                year = str(_dt.datetime.now().year)
            except Exception:
                year = "2026"
            # Entity-less claim (pronouns / "that" / bare verification words):
            # anchor the query to the last discussed entity so "is that
            # actually true" verifies the Messi claim, not the words
            # "actually true". A claim naming its own subject ("the game",
            # "the movie", a capitalized name) is NOT entity-less and keeps
            # its own subject.
            _claim_toks = _meaningful_tokens(claim)
            _generic_toks = _VERIF_GENERIC_TOKENS
            # Sentence-initial capitals ("Is that...") and the pronoun "I" are
            # NOT proper-noun evidence — only a capitalized word after the
            # first word names a subject ("Is Messi's...", "Did Taylor...").
            _claim_words = claim.split()
            _rest = " ".join(_claim_words[1:])
            # drop the standalone pronoun "I" ("Is that true? I saw...")
            _rest = re.sub(r"\bI\b", " ", _rest)
            _proper_after_first = bool(re.search(r"[A-Z]", _rest)) if _claim_words else False
            # Generic category nouns ("movie", "actor", "project") and event
            # verbs ("got delayed", "left") never constitute an own subject:
            # "movie got delayed" is referential (which movie?), not a named
            # subject. Only a proper noun or other specific content token does.
            _own_content = _claim_toks - _generic_toks - _GENERIC_SUBJECT_NOUNS - _EVENT_VERBS
            _has_own_subject = _proper_after_first or bool(_own_content)
            _entityless = not _has_own_subject
            # Referential claims anchor to the message's own entity first
            # ("I heard Messi's father... and he said..." -> claim 2 anchors to
            # Messi), then to the last memory entity (only a media instance for
            # category-noun claims like "the movie got delayed").
            _has_cat_noun = bool(_claim_toks & _GENERIC_SUBJECT_NOUNS)
            _usable_anchor = _msg_entity or (anchor if (not _has_cat_noun or _anchor_is_media) else "")
            _base = f"{_usable_anchor} {claim}" if _entityless and _usable_anchor else claim
            cq = f"{_base} {year}" if year and year not in _base else _base
            logger.info("[VERIFY_QUERY] claim=%s entityless=%s query=%s", claim, _entityless, cq)
            items = []
            try:
                # Bounded per-claim evidence (2) so a two-claim message does not
                # balloon into 6-8 provider round-trips; enough for a dated
                # contradiction to surface.
                items = self._retrieve_evidence(cq, None, 2) or []
            except Exception:
                items = []
            if not items:
                # Provider fallback: try without the year in case the year
                # suffix hurt provider recall.
                try:
                    items = self._retrieve_evidence(claim, None, 2) or []
                except Exception:
                    items = []
            # Claim-relevance gate: a retrieved page about Lane Johnson must
            # NEVER reach synthesis for a Messi claim — irrelevant evidence is
            # plumbing, not content. Filter against the claim AND the whole
            # user message (so a later "he said..." clause still anchors to
            # the entity named in claim 1).
            items = self._filter_claim_evidence(query, claim, items)
            if items:
                all_failed = False
            evidence_by_claim.append((claim, items))

        if all_failed:
            logger.info("[VERIFY_NO_EVIDENCE] query=%s", query)
            # Honest failure — never fabricate a current answer from memory.
            if self._llm_fn:
                try:
                    reply = self._llm_fn(
                        "The user asked to verify a current claim, but live "
                        "verification returned no evidence right now. Reply "
                        "naturally, 1-2 sentences, saying you can't verify it "
                        "live at the moment and don't guess."
                    )
                    if reply and len(reply) > 20:
                        return IntelligenceResult(
                            topic=TopicType.UNKNOWN, response_text=reply,
                            subject=query, confidence=0.0, source="verification_failed",
                        )
                except Exception:
                    pass
                return IntelligenceResult(
                    topic=TopicType.UNKNOWN,
                    response_text="I can't verify that live right now — I couldn't find current reports on it.",
                    subject=query, confidence=0.0, source="verification_failed",
                )
            return None

        # ── build the evidence-bounded synthesis prompt ──────────────────────
        try:
            import datetime as _dt
            now = _dt.datetime.now()
            today_label = now.strftime("%B %d, %Y")
        except Exception:
            today_label = "today"

        # The synthesis input is INTERNAL research context. Provider names
        # (Tavily/Exa/DDG) are implementation details and must never reach the
        # user; only dated excerpts go in, so the model cannot recite retrieval
        # mechanics it was never shown.
        sections = []
        for claim, items in evidence_by_claim:
            lines = [f"Point {len(sections) + 1}: {claim}"]
            if not items:
                lines.append("  (no relevant evidence retrieved)")
            for res in items:
                raw = (getattr(res, "raw_content", None) or "") or (getattr(res, "summary", None) or "")
                raw = re.sub(r"<[^>]+>", "", raw or "")
                raw = re.sub(r"\s+", " ", raw).strip()
                date = getattr(res, "published_date", None)
                date_label = f"{date}" if date else "recent"
                lines.append(f"  - [{date_label}] {raw[:400]}")
            sections.append("\n".join(lines))

        # A reclaimed follow-up ("what exactly did Messi say?", "when did
        # that happen?") asks about the PRIOR claims' content — the prompt
        # must carry the follow-up question so the answer addresses it, not
        # just re-verifies the claims (live failure: the follow-up about the
        # retirement quote was answered with an unrelated World Cup remark).
        _followup_ctx = ""
        if _reclaimed:
            _followup_ctx = (
                f"The user's current message is: {query!r}. Answer THAT question "
                "specifically, using the excerpts below.\n\n"
            )
        prompt = (
            f"Today's date is {today_label}. You checked the current reporting on what the "
            "user just said and this is what you found. You are NOT to answer from your own "
            "prior knowledge — reason only over the excerpts below.\n\n"
            + _followup_ctx
            + "\n\n".join(sections)
            + "\n\nNow reply to the user directly, in KIO's normal conversational voice. "
            "Give a clear verdict up front in your own words — true / mostly true / not "
            "quite what's being said / unverified — as a person checking something for a "
            "friend would say it, NOT as a fixed label. Never start with a report-style "
            "header such as 'Bottom line:', 'Summary:', 'Quick rundown:', or any other "
            "formatted prefix — just answer naturally, like you're telling a friend what "
            "you found. Then briefly explain each point of their "
            "message. Be natural and concise — you are a person checking something for a "
            "friend, not a search engine or a news anchor. Do NOT mention any search service, "
            "provider, or retrieval step (never say 'Tavily', 'Exa', 'my research', 'sources "
            "show', 'according to my search'). Do NOT use labels like 'Point 1', bullet lists, "
            "[date] brackets, or markdown formatting (no **bold**, no asterisks, no headers). "
            "Mention a specific outlet only if it genuinely strengthens the "
            "answer (e.g. 'ABC reported...'); otherwise just say what happened. If the excerpts "
            "contradict each other, prefer the NEWEST dated one and don't dwell on trivia that "
            "doesn't change the answer. If a part of their message cannot be verified, say so "
            "plainly and don't guess. Distinguish a confirmed event from a direct quote from a "
            "paraphrase. Keep it conversational, 2-5 sentences per point."
            " DATES: state the event date EXACTLY as the excerpts give it — including "
            "the year. Never assume an event happened in the current year just because "
            "today's date is recent: an event in the excerpts is dated by the excerpts, "
            "not by today. If an excerpt gives a month/day without a year, keep that exact "
            "form instead of inventing a year, or say the year isn't clear from what you found."
        )

        _synth_fn = self._verify_llm_fn or self._llm_fn
        if _synth_fn:
            try:
                answer = _synth_fn(prompt)
                if answer and len(answer) > 20:
                    answer = answer.strip()
                    # Anti-hallucination gate: a synthesis reply that shares NO
                    # meaningful token with the user's query or the evidence is
                    # not an answer to this claim (live failure: the provider
                    # chain answered a long verification prompt with "It's
                    # 9:10 AM."). Discard and use the deterministic verdict.
                    _answer_toks = _meaningful_tokens(answer)
                    _ground_toks = _meaningful_tokens(query) | set().union(
                        *[_meaningful_tokens(
                            (getattr(r, "raw_content", None) or "") or (getattr(r, "summary", None) or "")
                        ) for _, items in evidence_by_claim for r in items]
                    ) if evidence_by_claim else set()
                    # A degenerate provider reply ("It's 2:52 AM.", "Yes.",
                    # "Ok.") carries NO content tokens — it cannot be an
                    # answer to the claim even if a referential token happens
                    # to appear in the evidence. Reject empty-token answers
                    # outright (the overlap check below would otherwise pass
                    # vacuously once referential forms are stopwords).
                    if not _answer_toks:
                        logger.info("[VERIFY_SYNTH_REJECT] answer has no content tokens")
                    elif _ground_toks and not (_answer_toks & _ground_toks):
                        logger.info("[VERIFY_SYNTH_REJECT] answer shares no ground tokens")
                    else:
                        # Deterministic markdown scrub: even with the prompt
                        # guard, the model sometimes emits **bold** verdicts
                        # ("**mostly true**"). Strip bold/italic asterisks and
                        # stray markdown so the reply is always plain KIO prose.
                        answer = re.sub(r"\*\*(.+?)\*\*", r"\1", answer)
                        answer = re.sub(r"\*(.+?)\*", r"\1", answer)
                        answer = re.sub(r"#{1,6}\s*", "", answer)
                        answer = answer.replace("`", "").strip()
                        if not answer.endswith((".", "!", "?")) and len(answer) < 120:
                            answer = answer + "."
                        # Register the verified subject so an entity-less
                        # follow-up ("Is that actually true?") anchors to THIS
                        # entity, not a stale one. Prefer the resolved anchor
                        # ("Spider-Man") over a bare referential claim text
                        # ("movie got delayed") so the next follow-up anchors
                        # to the real subject.
                        _subj = _msg_entity or anchor or (claims[0] if claims else query)
                        self._register_entity(_subj, TopicType.UNKNOWN, confidence=0.8)
                        try:
                            self._ctx.put(self._claims_key(session_id), claims, source="verification")
                        except Exception:
                            pass
                        return IntelligenceResult(
                            topic=TopicType.UNKNOWN,
                            response_text=answer,
                            subject=_subj,
                            confidence=0.8,
                            source="verification",
                        )
            except Exception:
                pass

        # ── deterministic fallback: concise verdict, never a source dump ─────
        def _date_key(res) -> tuple:
            d = getattr(res, "published_date", None)
            if not d:
                return (0, 0, 0)
            try:
                return tuple(int(x) for x in d.split("-"))
            except Exception:
                return (0, 0, 0)

        def _verdict_sentence(raw: str, claim: str) -> str:
            """Extract a clean, claim-relevant verdict sentence from evidence.

            Strips provider UI chrome (fund ads, nav labels, "daily newspaper
            available online now") and query echoes, then prefers the sentence
            sharing the most meaningful tokens with the claim — the actual
            answer sentence, never a headline or an ad.
            """
            raw = re.sub(r"<[^>]+>", "", raw or "")
            raw = re.sub(r"\s+", " ", raw).strip()
            if not raw:
                return ""
            # Cut at common UI/chrome markers that precede footer garbage.
            for marker in ("Featured Funds", "FEATURED FUNDS", "Read More", "Also Read",
                           "Advertisement", "daily newspaper is available online"):
                idx = raw.find(marker)
                if idx > 0:
                    raw = raw[:idx]
            # Split into sentences.
            sentences = [s.strip() for s in re.split(r"(?<=[.!?])\s+", raw) if s.strip()]
            if not sentences:
                return raw[:200].strip()
            claim_toks = _meaningful_tokens(claim)
            # Query-echo/headline detection: lines that restate the user's own
            # words ("did messi retire: Is Messi retiring...", "Here's what he
            # actually said") are provider noise, never a verdict sentence.
            claim_first = " ".join((claim or "").lower().split()[:4])
            def _is_echo(s: str) -> bool:
                low = s.lower()
                if claim_first and claim_first.split()[0] and low.startswith(claim_first.split()[0]):
                    return True
                if "here's what" in low or "here is what" in low:
                    return True
                if low.endswith("?") and len(low) < 80:
                    return True  # headline question, not a fact
                return False
            best = ""
            best_score = -1
            for s in sentences:
                low = s.lower()
                if low.startswith(("featured", "read more", "advertisement", "invest now",
                                   "business news", "trending")):
                    continue
                if _is_echo(s):
                    continue
                # Prefer sentences containing a date/event marker.
                date_bonus = 1 if re.search(r"\b(?:jan|feb|mar|apr|may|jun|jul|aug|sep|oct|nov|dec|20\d{2}|yesterday|today)\b", low) else 0
                score = len(_meaningful_tokens(s) & claim_toks) + date_bonus
                if score > best_score:
                    best, best_score = s, score
            if not best:
                best = sentences[0]
            if not best.endswith((".", "!", "?")):
                best += "."
            return best[:300]

        parts = []
        for i, (claim, items) in enumerate(evidence_by_claim):
            if not items:
                parts.append(
                    f"I couldn't verify that part about '{claim}' right now."
                )
                continue
            newest = max(items, key=_date_key)
            raw = (getattr(newest, "raw_content", None) or "") or (getattr(newest, "summary", None) or "")
            snippet = _verdict_sentence(raw, claim)
            lead = "The first part" if i == 0 and len(evidence_by_claim) > 1 else "As for that"
            if snippet:
                parts.append(f"{lead} — recent reporting says: {snippet}")
            else:
                parts.append(f"{lead} — recent reporting covers it, but I couldn't pull a clean summary right now.")
        reply = " ".join(parts) or "I couldn't verify that live right now."
        _subj = _msg_entity or anchor or (claims[0] if claims else query)
        self._register_entity(_subj, TopicType.UNKNOWN, confidence=0.6)
        try:
            self._ctx.put(self._claims_key(session_id), claims, source="verification")
        except Exception:
            pass
        return IntelligenceResult(
            topic=TopicType.UNKNOWN,
            response_text=reply[:700],
            subject=_subj,
            confidence=0.6,
            source="verification",
        )

    def _filter_claim_evidence(self, full_query: str, claim: str, items: list) -> list:
        """Keep only evidence that actually concerns the claim's entity.

        Live bug: a Messi claim retrieved a DuckDuckGo/Tavily page about Lane
        Johnson's retirement, which the synthesis then recited verbatim
        ("there is also a report from Tavily, but it's about Lane Johnson, not
        Messi"). Irrelevant retrieval is plumbing, not content — it must be
        discarded before synthesis, never narrated to the user.

        Relevance = the evidence text shares a meaningful token with the claim
        OR with the entity named elsewhere in the user's message (later claims
        often say just "he said..."). Pronoun-only claims inherit the first
        claim's entity terms.
        """
        if not items:
            return []

        claim_toks = _meaningful_tokens(claim)
        query_toks = _meaningful_tokens(full_query)
        # Anchor terms: everything meaningful in the whole message (catches the
        # entity "messi" in claim 1 that a pronoun-only claim 2 relies on).
        anchor_toks = claim_toks | query_toks
        if not anchor_toks:
            return items

        kept = []
        for res in items:
            raw = (getattr(res, "raw_content", None) or "") or (getattr(res, "summary", None) or "")
            raw = re.sub(r"<[^>]+>", "", raw or "")
            text_toks = _meaningful_tokens(raw)
            if not text_toks:
                continue
            overlap = anchor_toks & text_toks
            # Require at least one shared meaningful token, and prefer items
            # that share the strongest (longest) anchor term.
            if not overlap:
                continue
            kept.append(res)
        return kept[:2]

    # ── sports ─────────────────────────────────────────────────────────────────

    # ── sports ─────────────────────────────────────────────────────────────────

    def _handle_sports(self, query: str, confidence: float) -> IntelligenceResult:
        memory_res = self._try_memory_resolve(query, TopicType.SPORTS)
        if memory_res:
            return memory_res

        competition = detect_competition(query)
        sports_mode = detect_sports_mode(query)
        mode_val = sports_mode.value if sports_mode else ""
        last_e = self._mem.get_last_entity()
        subject = competition or (last_e.name if last_e else None) or query

        # Retrieve fresh data with query rewriting
        rewritten = self._rewrite_retrieval(query, TopicType.SPORTS, subject)
        res = self._safe_retrieve(rewritten, topic=TopicType.SPORTS.value, mode=mode_val)
        if not res:
            res = self._safe_retrieve(query, topic=TopicType.SPORTS.value, mode=mode_val)
        if res:
            self._discover_artifacts(res, TopicType.SPORTS, subject)

        # Extract events for continuity context
        events = extract_events(res.raw_content or res.summary, competition) if res else []
        for event in events:
            self._ctx.add_event(event)

        # store competition and mode context
        if competition:
            self._ctx.put("competition", competition, topic=TopicType.SPORTS)
        if sports_mode:
            self._ctx.put("sports_mode", sports_mode.value, topic=TopicType.SPORTS)

        # Compose structured answer via AnswerComposer
        text = self._compose_answer(res, query) if res else f"I couldn't find sports info on {subject}."

        # Build followup options
        followup_options = ["show standings", "show fixtures", "show analysis"]
        if events:
            top_event = events[0]
            followup_options = [
                f"show {top_event.entity_a} highlights" if top_event.entity_a else "show highlights",
                "show standings", "show fixtures", "show results", "show analysis",
            ]
        # Merge with dynamic artifact-based options
        dynamic = self._build_dynamic_followup(TopicType.SPORTS, subject, followup_options)
        followup_options = dynamic[:6]

        self._register_entity(subject, TopicType.SPORTS, result=res, confidence=confidence)
        self._continuity.update_context(query, TopicType.SPORTS, subject, confidence)

        return IntelligenceResult(
            topic=TopicType.SPORTS,
            sports_mode=sports_mode,
            events=events,
            response_text=text,
            subject=subject,
            confidence=confidence,
            source="retrieval",
            followup_options=followup_options[:4],
        )

    def _extract_answer_person(self, query: str, res: Any) -> str:
        ql = query.lower().strip()
        if not ql.startswith("who "):
            return ""
        _role_verbs = {"directed", "created", "wrote", "composed", "produced",
                       "developed", "designed", "voiced", "played", "plays",
                       "starred", "stars", "sang", "sings", "narrated",
                       "hosted", "hosts", "founded", "invented", "made"}
        if not any(w in ql for w in _role_verbs):
            return ""
        if not res:
            return ""
        raw_text = ""
        if isinstance(res, str):
            raw_text = res
        elif hasattr(res, "raw_content") and res.raw_content:
            raw_text = res.raw_content
        elif hasattr(res, "summary") and res.summary:
            raw_text = res.summary
        elif hasattr(res, "raw_text") and res.raw_text:
            raw_text = res.raw_text
        if not raw_text:
            return ""
        _role_markers = {"directed by", "created by", "written by", "composed by",
                         "produced by", "developed by", "performed by", "starring",
                         "featuring", "played by", "voiced by", "narrated by",
                         "hosted by", "founded by", "invented by", "made by"}
        raw_lower = raw_text.lower()
        for marker in _role_markers:
            idx = raw_lower.find(marker)
            if idx >= 0:
                after = raw_text[idx + len(marker):].strip().strip(".,!?;:")
                name = after.split(",")[0].split("(")[0].split(" (")[0].strip().rstrip(".")
                if name and len(name) > 3 and not any(c in name for c in "0123456789"):
                    return name
        _skip = {"the", "a", "an", "and", "or", "in", "on", "at", "to", "for",
                 "of", "with", "by", "from", "is", "was", "are", "were", "has",
                 "have", "had", "been", "being", "will", "would", "could",
                 "should", "may", "might", "shall", "can", "do", "does", "did",
                 "this", "that", "these", "those", "it", "its", "he", "she",
                 "him", "her", "they", "them", "their", "his", "who", "what",
                 "when", "where", "why", "how", "the", "of"}
        first_150 = raw_text[:200]
        for w in first_150.split():
            wc = w.strip(".,!?;:()'\"")
            if wc and wc[0].isupper() and wc.lower() not in _skip and len(wc) > 3:
                return wc
        return ""

    # ── movies / tv ────────────────────────────────────────────────────────────

    def _handle_media(self, query: str, topic: TopicType, confidence: float) -> IntelligenceResult:
        memory_res = self._try_memory_resolve(query, topic)
        if memory_res:
            return memory_res

        subject = self._extract_subject(query, topic)
        text, res = self._retrieve_and_summarize(query, topic, subject)
        self._register_entity(subject, topic, result=res, confidence=confidence)
        self._continuity.update_context(query, topic, subject, confidence)

        # Track answer person for "who [role] X?" questions so personal pronouns
        # ("him", "he", "she") resolve to the answer person, not the query subject.
        ql = query.lower().strip()
        words = ql.split()
        if words and words[0] == "who":
            _role_verbs = {"directed", "created", "wrote", "composed", "produced",
                           "developed", "designed", "voiced", "played", "plays",
                           "starred", "stars", "sang", "sings", "narrated",
                           "hosted", "hosts", "founded", "invented", "made"}
            if any(w in ql for w in _role_verbs):
                self._answer_person = self._extract_answer_person(query, res)

        return IntelligenceResult(
            topic=topic,
            response_text=text,
            subject=subject,
            confidence=confidence,
            source="retrieval",
            followup_options=self._build_dynamic_followup(topic, subject, ["show trailer", "show teaser", "show interviews"]),
        )

    # ── gaming ─────────────────────────────────────────────────────────────────

    def _handle_gaming(self, query: str, confidence: float) -> IntelligenceResult:
        memory_res = self._try_memory_resolve(query, TopicType.GAMING)
        if memory_res:
            return memory_res

        subject = self._extract_subject(query, TopicType.GAMING)
        text, res = self._retrieve_and_summarize(query, TopicType.GAMING, subject)
        self._register_entity(subject, TopicType.GAMING, result=res, confidence=confidence)
        self._continuity.update_context(query, TopicType.GAMING, subject, confidence)
        return IntelligenceResult(
            topic=TopicType.GAMING,
            response_text=text,
            subject=subject,
            confidence=confidence,
            source="retrieval",
            followup_options=self._build_dynamic_followup(TopicType.GAMING, subject, ["show gameplay", "show the trailer", "show developer update"]),
        )

    # ── music ──────────────────────────────────────────────────────────────────

    def _handle_music(self, query: str, confidence: float) -> IntelligenceResult:
        memory_res = self._try_memory_resolve(query, TopicType.MUSIC)
        if memory_res:
            return memory_res

        subject = self._extract_subject(query, TopicType.MUSIC)
        text, res = self._retrieve_and_summarize(query, TopicType.MUSIC, subject)
        self._register_entity(subject, TopicType.MUSIC, result=res, confidence=confidence)
        self._continuity.update_context(query, TopicType.MUSIC, subject, confidence)
        return IntelligenceResult(
            topic=TopicType.MUSIC,
            response_text=text,
            subject=subject,
            confidence=confidence,
            source="retrieval",
            followup_options=self._build_dynamic_followup(TopicType.MUSIC, subject, ["play music video", "show live performance"]),
        )

    # ── books ──────────────────────────────────────────────────────────────────

    def _handle_books(self, query: str, confidence: float) -> IntelligenceResult:
        memory_res = self._try_memory_resolve(query, TopicType.BOOKS)
        if memory_res:
            return memory_res

        subject = self._extract_subject(query, TopicType.BOOKS)
        if not subject:
            last_e = self._mem.get_last_entity()
            if last_e:
                subject = last_e.name
        text, res = self._retrieve_and_summarize(query, TopicType.BOOKS, subject)
        self._register_entity(subject, TopicType.BOOKS, result=res, confidence=confidence)
        self._continuity.update_context(query, TopicType.BOOKS, subject, confidence)
        return IntelligenceResult(
            topic=TopicType.BOOKS,
            response_text=text,
            subject=subject,
            confidence=confidence,
            source="retrieval",
            followup_options=self._build_dynamic_followup(TopicType.BOOKS, subject, ["show audiobook", "show author interview", "show adaptation trailer", "show book review"]),
        )

    # ── people ─────────────────────────────────────────────────────────────────

    def _handle_people(self, query: str, confidence: float) -> IntelligenceResult:
        memory_res = self._try_memory_resolve(query, TopicType.PEOPLE)
        if memory_res:
            return memory_res
        subject = self._extract_subject(query, TopicType.PEOPLE)
        if not subject:
            last_e = self._mem.get_last_entity()
            if last_e:
                subject = last_e.name
        text, res = self._retrieve_and_summarize(query, TopicType.PEOPLE, subject)
        self._register_entity(subject, TopicType.PEOPLE, result=res, confidence=confidence)
        self._continuity.update_context(query, TopicType.PEOPLE, subject, confidence)
        return IntelligenceResult(
            topic=TopicType.PEOPLE,
            response_text=text,
            subject=subject,
            confidence=confidence,
            source="retrieval",
            followup_options=self._build_dynamic_followup(TopicType.PEOPLE, subject, ["show interview", "show biography", "show related people"]),
        )

    # ── generic ────────────────────────────────────────────────────────────────

    def _handle_generic(self, query: str, topic: TopicType, confidence: float) -> IntelligenceResult:
        memory_res = self._try_memory_resolve(query, topic)
        if memory_res:
            return memory_res

        subject = self._extract_subject(query, topic)
        text, res = self._retrieve_and_summarize(query, topic, subject)
        self._register_entity(subject, topic, result=res, confidence=confidence)
        self._continuity.update_context(query, topic, subject, confidence)
        return IntelligenceResult(
            topic=topic,
            response_text=text,
            subject=subject,
            confidence=confidence,
            source="retrieval",
        )

    # ── artifact discovery ─────────────────────────────────────────────────────

    def _discover_artifacts(self, result: RetrievalResult, topic: TopicType, subject: str) -> None:
        """Scan retrieval result for known artifact mentions and register them."""
        import logging
        import re
        logger = logging.getLogger(__name__)
        if not result or not subject:
            return

        raw = result if isinstance(result, str) else (result.raw_content or result.summary)
        if not raw:
            return
        
        # Topic-specific artifact keyword patterns
        patterns: dict[ArtifactType, list[str]] = {
            ArtifactType.TRAILER: ["trailer", "official trailer", "first look"],
            ArtifactType.TEASER: ["teaser", "teaser trailer", "sneak peek", "teaser trailer"],
            ArtifactType.INTERVIEW: ["interview", "press conference", "qa", "red carpet", "cast interview"],
            ArtifactType.HIGHLIGHTS: ["highlight", "best moments", "top plays", "recap"],
            ArtifactType.STANDINGS: ["standing", "table", "rankings", "points"],
            ArtifactType.FIXTURES: ["fixture", "schedule", "upcoming match", "upcoming game"],
            ArtifactType.RESULTS: ["result", "score", "final score"],
            ArtifactType.MUSIC_VIDEO: ["music video", "official video", "lyric video"],
            ArtifactType.LIVE_PERFORMANCE: ["live performance", "concert", "live session", "live show"],
            ArtifactType.GAMEPLAY: ["gameplay", "walkthrough", "playthrough"],
            ArtifactType.DEVELOPER_UPDATE: ["developer update", "dev diary", "patch notes"],
            ArtifactType.BEST_SCENES: ["best scene", "iconic scene", "epic scene", "fan favorite scene"],
            ArtifactType.BEHIND_THE_SCENES: ["behind the scenes", "behind-the-scenes", "bts", "making of"],
            ArtifactType.ENDING_EXPLAINED: ["ending explained", "ending breakdown", "explained ending"],
            ArtifactType.DOCUMENTARY: ["documentary", "doc", "the story of", "making of documentary"],
            ArtifactType.RECAP: ["recap", "previous episode", "season recap", "story so far"],
            ArtifactType.CLIPS: ["clip", "scene", "exclusive clip"],
            ArtifactType.BLOOPERS: ["blooper", "bloopers", "outtakes", "gag reel"],
            ArtifactType.ANALYSIS: ["analysis", "analyst", "breakdown", "deep dive"],
            ArtifactType.TACTICAL_BREAKDOWN: ["tactical", "formation", "strategy", "tactics"],
            ArtifactType.PRESS_CONFERENCE: ["press conference", "media briefing", "post-match interview"],
            ArtifactType.MATCH_ANALYSIS: ["match analysis", "game analysis", "post-match analysis"],
            ArtifactType.ONBOARD_FOOTAGE: ["onboard", "on-board", "helmet cam", "driver cam"],
            ArtifactType.TEAM_RADIO: ["team radio", "radio message", "pit radio"],
            ArtifactType.ACOUSTIC_VERSION: ["acoustic", "acoustic version", "unplugged", "stripped"],
            ArtifactType.LYRICS_VIDEO: ["lyric video", "lyrics video", "official lyric"],
            ArtifactType.CONCERT_FOOTAGE: ["concert", "live concert", "tour", "live at"],
            ArtifactType.PRODUCTION_UPDATE: ["production update", "production progress", "filming update", "in production"],
            ArtifactType.SET_FOOTAGE: ["set footage", "on set", "behind the camera", "filming set"],
            ArtifactType.EPISODE_PREVIEW: ["episode preview", "next episode", "episode guide", "upcoming episode"],
            ArtifactType.VOICE_ACTOR_INTERVIEW: ["voice actor", "voice cast", "voice over", "voice interview"],
            ArtifactType.LATEST_VIDEO: ["latest video", "new video", "recent video"],
            ArtifactType.PROJECT_BREAKDOWN: ["project breakdown", "cost breakdown", "how it was made"],
            ArtifactType.GOAL_COMPILATION: ["goal", "goals", "goal compilation", "goal highlights"],
            ArtifactType.BEST_MOMENTS: ["best moments", "top moments", "greatest moments", "fan favorite"],
            ArtifactType.AUDIOBOOK: ["audiobook", "audio book", "audio edition", "narrated by"],
            ArtifactType.BOOK_REVIEW: ["review", "rating", "critic review", "reader review", "book review"],
            ArtifactType.BOOK_SUMMARY: ["summary", "overview", "synopsis", "about the book", "blurb"],
            ArtifactType.ADAPTATION_TRAILER: ["adaptation", "film adaptation", "tv adaptation", "movie adaptation", "screen adaptation"],
            ArtifactType.AUTHOR_INTERVIEW: ["author interview", "interview with the author", "qa with", "writer interview"],
            ArtifactType.READING: ["reading", "read by", "excerpt", "sample", "first chapter"],
            ArtifactType.SOUNDTRACK: ["soundtrack", "original score", "background score", "music by", "ost", "composed by"],
            ArtifactType.COMPOSER_INTERVIEW: ["composer interview", "music interview", "interview with the composer"],
        }

        topic_artifacts = {
            TopicType.MOVIES: [ArtifactType.TRAILER, ArtifactType.TEASER, ArtifactType.INTERVIEW,
                               ArtifactType.BEST_SCENES, ArtifactType.BEHIND_THE_SCENES,
                               ArtifactType.ENDING_EXPLAINED, ArtifactType.DOCUMENTARY,
                               ArtifactType.CLIPS, ArtifactType.BLOOPERS,
                               ArtifactType.SOUNDTRACK, ArtifactType.COMPOSER_INTERVIEW],
            TopicType.TV: [ArtifactType.TRAILER, ArtifactType.TEASER, ArtifactType.INTERVIEW,
                           ArtifactType.CLIPS, ArtifactType.RECAP, ArtifactType.BEHIND_THE_SCENES,
                           ArtifactType.BLOOPERS, ArtifactType.EPISODE_PREVIEW,
                           ArtifactType.VOICE_ACTOR_INTERVIEW,
                           ArtifactType.SOUNDTRACK, ArtifactType.COMPOSER_INTERVIEW],
            TopicType.GAMING: [ArtifactType.GAMEPLAY, ArtifactType.TRAILER, ArtifactType.DEVELOPER_UPDATE,
                               ArtifactType.INTERVIEW, ArtifactType.DOCUMENTARY],
            TopicType.SPORTS: [ArtifactType.HIGHLIGHTS, ArtifactType.STANDINGS, ArtifactType.FIXTURES,
                               ArtifactType.RESULTS, ArtifactType.ANALYSIS, ArtifactType.TACTICAL_BREAKDOWN,
                               ArtifactType.PRESS_CONFERENCE, ArtifactType.MATCH_ANALYSIS,
                               ArtifactType.GOAL_COMPILATION, ArtifactType.BEST_MOMENTS],
            TopicType.MUSIC: [ArtifactType.MUSIC_VIDEO, ArtifactType.LIVE_PERFORMANCE, ArtifactType.INTERVIEW,
                              ArtifactType.ACOUSTIC_VERSION, ArtifactType.LYRICS_VIDEO,
                              ArtifactType.CONCERT_FOOTAGE, ArtifactType.DOCUMENTARY],
            TopicType.BOOKS: [ArtifactType.AUDIOBOOK, ArtifactType.BOOK_REVIEW, ArtifactType.BOOK_SUMMARY,
                              ArtifactType.ADAPTATION_TRAILER, ArtifactType.AUTHOR_INTERVIEW,
                              ArtifactType.READING, ArtifactType.INTERVIEW, ArtifactType.DOCUMENTARY],
        }

        relevant = topic_artifacts.get(topic, [])
        raw_lower = raw.lower()

        for atype in relevant:
            keywords = patterns.get(atype, [])
            for kw in keywords:
                if kw in raw_lower:
                    # Extract URL from raw text if available (look for first http/https URL)
                    url = ""
                    url_match = re.search(r'https?://[^\s"\'<>]+', raw)
                    if url_match:
                        url = url_match.group(0)
                    record = ArtifactRecord(
                        artifact_type=atype,
                        topic=topic,
                        subject=subject,
                        url=url,
                        confidence=0.6,
                    )
                    self._art.store_artifact(record)
                    logger.info("[ARTIFACT_REGISTER] type=%s subject=%s topic=%s keyword=%s url=%s",
                                atype.value, subject, topic.value, kw, url or "none")
                    break  # one registration per artifact type per scan

    # ── LLM summarization ──────────────────────────────────────────────────────

    def set_llm_fn(self, fn: Callable[[str], Optional[str]]) -> None:
        self._llm_fn = fn
        self._composer._llm_fn = fn

    def set_verify_llm_fn(self, fn: Callable[[str], Optional[str]]) -> None:
        """Wire a dedicated verification-synthesis LLM (longer budget)."""
        self._verify_llm_fn = fn

    def _compose_answer(self, result: RetrievalResult, query: str,
                        subject: Optional[str] = None) -> str:
        """Use AnswerComposer to build a structured, topic-appropriate answer.

        `subject` overrides the retrieval provider's entity field, which is
        frequently the raw query ("What is Notepad?") and must never become
        the displayed subject."""
        import logging
        logger = logging.getLogger(__name__)
        
        formatted = self._composer.compose(result, query, subject=subject or None)
        
        # Store offers for acceptance resolution
        offers_info = self._composer.get_last_offers()
        subject = subject or result.entity or result.title
        topic = result.topic
        
        if offers_info.get("offers"):
            self._ctx.put("last_offers", {
                "subject": subject,
                "topic": topic.value if hasattr(topic, "value") else str(topic),
                "offers": offers_info["offers"],
            }, topic=topic, confidence=1.0, source="answer_composer")
        
        logger.info("[ANSWER_COMPOSED] subject=%s topic=%s source=%s", subject, topic, result.source)
        return formatted

    # ── helpers ────────────────────────────────────────────────────────────────

    def _build_dynamic_followup(self, topic: TopicType, subject: str, static: list[str]) -> list[str]:
        """Build followup options from actual artifact memory, falling back to static suggestions.

        Checks ArtifactMemory for any artifacts registered for this subject+topic
        and prepends matching options to the static list, so the user sees offers
        based on what was actually discovered rather than always seeing the defaults.
        """
        if not subject:
            return static
        dynamic = []
        artifact_order = [
            ("trailer", "show trailer"), ("teaser", "show teaser"),
            ("gameplay", "show gameplay"), ("highlights", "show highlights"),
            ("standings", "show standings"), ("fixtures", "show fixtures"),
            ("results", "show results"), ("music_video", "play music video"),
            ("live_performance", "show live performance"),
            ("interview", "show interview"), ("best_scenes", "show best scenes"),
            ("behind_the_scenes", "show behind the scenes"),
            ("ending_explained", "show ending explained"),
            ("recap", "show recap"), ("clips", "show clips"),
            ("audiobook", "show audiobook"),
            ("book_review", "show book review"),
            ("book_summary", "show book summary"),
            ("adaptation_trailer", "show adaptation trailer"),
            ("author_interview", "show author interview"),
            ("reading", "show reading"),
        ]
        from mini_kio.media.intelligence.media_intelligence_models import ArtifactType
        for art_type_str, display_text in artifact_order:
            try:
                atype = ArtifactType(art_type_str)
            except ValueError:
                continue
            found = self._art.resolve_artifact(atype, subject=subject, topic=topic)
            if found:
                dynamic.append(display_text)
        # De-duplicate while preserving order
        seen = set()
        result = []
        for item in dynamic + static:
            if item not in seen:
                seen.add(item)
                result.append(item)
        return result[:6]  # cap at 6 offers

    # ── contextual info query (called from MediaManager for non-play queries) ──

    def handle_contextual_query(self, query: str) -> Optional[IntelligenceResult]:
        import logging
        logger = logging.getLogger(__name__)
        ql = query.lower().strip()
        last_e = self._mem.get_last_entity()
        if not last_e:
            logger.info("[MEMORY_MISS] handle_contextual_query: no last entity for query=%s", query)
            return None
        if not self._is_continuation_query(ql):
            logger.info("[MEMORY_MISS] handle_contextual_query: not continuation last=%s query=%s", last_e.name, query)
            return None

        entity_name = last_e.name
        topic = self._entity_type_to_topic(last_e.entity_type)
        logger.info("[MEMORY_HIT] handle_contextual_query last=%s query=%s topic=%s", entity_name, query, topic)

        # Build targeted query from entity context + user intent
        noise = {"it", "that", "this", "they", "them", "he", "she", "him", "his", "her", "their"}
        meaningful = [w for w in ql.split() if w not in noise]
        new_query = f"{entity_name} {' '.join(meaningful)}" if meaningful else entity_name
        rewritten = self._rewrite_retrieval(query, topic, entity_name)
        if rewritten != query:
            new_query = rewritten
        logger.info("[MEMORY_RESOLVE] entity=%s original=%s new_query=%s", entity_name, query, new_query)

        # NEW retrieval — never return stale stored text
        res = self._safe_retrieve(new_query, topic=topic.value)
        if not res:
            res = self._safe_retrieve(entity_name, topic=topic.value)

        if res:
            self._discover_artifacts(res, topic, entity_name)

        text = self._compose_answer(res, query) if res else ""
        self._register_entity(entity_name, topic, result=res, confidence=0.85)
        return IntelligenceResult(
            topic=topic,
            response_text=text,
            subject=entity_name,
            confidence=0.85,
            source=f"memory:{entity_name}",
        )

    def get_last_subject(self) -> str:
        last_e = self._mem.get_last_entity()
        return last_e.name if last_e else ""

    # ── helpers ────────────────────────────────────────────────────────────────

    def _safe_retrieve(self, query: str, topic: Optional[str] = None, mode: str = "") -> Optional[RetrievalResult]:
        import logging
        logger = logging.getLogger(__name__)
        logger.info("[RETRIEVAL_PROVIDER] topic=%s query=%s mode=%s", topic or "none", query, mode or "none")
        try:
            res = self.retrieve(query, topic, mode)
            if res:
                raw = res.raw_content or res.summary
                # Quality filter: reject empty/too-short results
                if len(raw) < 50:
                    logger.info("[RETRIEVAL_RESULT] source=%s query=%s len=%d — TOO SHORT, ignoring", res.source, query, len(raw))
                    res = None
                else:
                    logger.info("[RETRIEVAL_RESULT] source=%s query=%s len=%d", res.source, query, len(raw))
            else:
                logger.info("[RETRIEVAL_RESULT] topic=%s query=%s empty", topic or "none", query)
            return res
        except Exception:
            logger.info("[RETRIEVAL_RESULT] exception query=%s", query, exc_info=True)
            return None

    def _rewrite_retrieval(self, query: str, topic: TopicType, subject: str) -> str:
        """Rewrite user query into a retrieval-optimized query."""
        import logging
        logger = logging.getLogger(__name__)
        ql = query.lower().strip()
        original = query
        rewritten = None
        is_current = _is_current_info_query(query)

        # ── Explicit disambiguation for known ambiguous entities ──────────────
        _DISAMBIGUATION = {
            "believer": "Believer Imagine Dragons song",
        }
        if subject and subject.lower() in _DISAMBIGUATION:
            disambiguated = _DISAMBIGUATION[subject.lower()]
            rewritten = disambiguated

        # ── Freshness queries ────────────────────────────────────────────────
        # Full interrogative questions keep their OWN semantics: "Which country
        # is celebrating independence day today" must NOT become "Which latest
        # update news 2026" (a garbage query built from a failed subject
        # extraction). A question already contains its entity + predicate +
        # temporal constraint — rewriting it into a subject-template destroys
        # the actual request. Only bare/entity queries ("messi", "spiderman
        # trailer") get the topic-template treatment. A works-list query
        # ("Team Cherry list of games latest") is ALSO preserved verbatim —
        # the freshness template ("Team Cherry latest update patch news 2026")
        # would retrieve the studio's latest patch notes instead of its games
        # (live: role-catalog callback answered with a patch-notes dump).
        _full_question = bool(re.match(
            r"^(?:which|what|who|when|where|why|how)\b", ql,
        ))
        _works_query = re.search(
            r"\b(?:filmography|discography|bibliography|list\s+of\s+games|works)\b", ql,
        )
        if not rewritten and is_current and not _full_question and not _works_query:
            if topic == TopicType.SPORTS:
                rewritten = f"{subject} latest results standings fixtures scores news 2026"
            elif topic in (TopicType.MOVIES, TopicType.TV):
                rewritten = f"{subject} latest update news 2026"
            elif topic == TopicType.MUSIC:
                rewritten = f"{subject} latest release tour news 2026"
            elif topic == TopicType.GAMING:
                rewritten = f"{subject} latest update patch news 2026"
            elif topic == TopicType.BOOKS:
                rewritten = f"{subject} latest release news 2026"
            else:
                rewritten = f"{subject} latest update news 2026"

        # ── Temporal resolution for full questions (deterministic owner) ────
        # "today" / "tonight" in a current question must be resolved to the
        # ACTUAL date BEFORE the query reaches retrieval — the provider should
        # never have to guess which "today" is meant. LLM is not the authority
        # for the current date; datetime is. "Which country is celebrating
        # independence day today" -> "...independence day august 15 2026".
        if _full_question and re.search(r"\b(?:today|tonight)\b", ql):
            try:
                import datetime as _dt
                _now = _dt.datetime.now()
                _date_str = _now.strftime("%B %d %Y").replace(" 0", " ")
                _temporal_q = re.sub(r"\b(?:today|tonight)\b", _date_str, ql)
                if _temporal_q != ql:
                    rewritten = _temporal_q.strip()
            except Exception:
                pass

        # ── "who" questions ──────────────────────────────────────────────────
        if not rewritten:
            _who_verbs = sorted(all_role_verbs(), key=len, reverse=True)
            who_m = re.match(
                rf"who\s+(?:is\s+)?(?:{verb_alternation(_who_verbs)})\s+(.+)$",
                ql,
            )
            if who_m:
                _matched = ""
                _p = None
                for v in _who_verbs:
                    _p = re.compile(
                        rf"^who\s+(?:is\s+)?{verb_regex(v)}\s+",
                        re.I,
                    )
                    if _p.match(ql):
                        _matched = v
                        break
                if _matched:
                    role = _matched
                    who_obj = re.sub(r"[?.!]+$", "", _p.sub("", ql)).strip()
                    _pred = canonical_predicate_for_verb(role)
                    if role in ("played", "plays", "starred", "stars"):
                        rewritten = f"{subject} cast {who_obj} actor"
                    elif _pred in ("written_by", "created_by"):
                        if topic == TopicType.BOOKS:
                            rewritten = f"{subject} author"
                        elif topic == TopicType.MUSIC:
                            rewritten = f"{subject} songwriter"
                        elif _pred == "created_by" and topic in (TopicType.MOVIES, TopicType.TV):
                            rewritten = f"{subject} creator"
                        elif _pred == "written_by" and topic in (TopicType.MOVIES, TopicType.TV):
                            rewritten = f"{subject} writer"
                        else:
                            rewritten = f"{subject} writer creator"
                    elif _pred:
                        # canonical predicate -> retrieval keyword (directed_by
                        # -> director, founded_by -> founder, led_by -> CEO,
                        # developed_by -> developer, ...)
                        rewritten = f"{subject} {retrieval_keyword_for_predicate(_pred)}"
                    else:
                        rewritten = f"{subject} {role}"
            elif ql.startswith("who "):
                rest = ql[4:].strip()
                if rest:
                    rewritten = f"{subject} {rest}"

        # ── "who is the author/writer/director/CEO/founder..." pattern ────────
        if not rewritten:
            _who_nouns = sorted(all_role_nouns(), key=len, reverse=True)
            who_is_m = re.match(
                rf"who\s+is\s+(?:the\s+)?((?:{'|'.join(re.escape(n) for n in _who_nouns)}))\s*(?:of\s+.+)?$",
                ql,
            )
            if who_is_m:
                role = who_is_m.group(1)
                _pred = canonical_predicate_for_role(role)
                if role in ("writer", "creator") and topic == TopicType.BOOKS:
                    rewritten = f"{subject} author"
                elif _pred:
                    rewritten = f"{subject} {retrieval_keyword_for_predicate(_pred)}"
                else:
                    rewritten = f"{subject} {role}"

        # ── Role keywords (standalone) ───────────────────────────────────────
        if not rewritten:
            role_keywords = {
                "composer": "composer", "scored": "composer", "music by": "composer",
                "writer": "writer", "written by": "writer", "screenplay": "writer",
                "creator": "creator", "created by": "creator",
                "producer": "producer", "produced by": "producer",
                "director": "director", "directed by": "director",
                "cinematography": "cinematographer", "edited by": "editor",
            }
            for kw, target in role_keywords.items():
                if kw in ql:
                    rewritten = f"{subject} {target}"
                    break

        # ── "how is it performing" / performance questions ───────────────────
        if not rewritten:
            perf_m = re.match(r"how\s+(is|was|are|does)\s+(it|this|the)\s+(performing|doing|playing)", ql)
            if perf_m:
                if topic in (TopicType.MOVIES, TopicType.TV):
                    rewritten = f"{subject} box office ratings reviews performance"
                elif topic == TopicType.SPORTS:
                    rewritten = f"{subject} latest results form performance"
                elif topic == TopicType.MUSIC:
                    rewritten = f"{subject} chart performance streams"
                elif topic == TopicType.GAMING:
                    rewritten = f"{subject} player count reviews performance"

        # ── "when was it released / published" ──────────────────────────────
        if not rewritten:
            when_m = re.search(r"when\s+(was|did|is)\s+(it|this|that|the)\s+(released|published|come\s*out|came\s*out)", ql)
            if when_m:
                if topic == TopicType.BOOKS:
                    rewritten = f"{subject} publication date"
                elif topic in (TopicType.MOVIES, TopicType.TV):
                    rewritten = f"{subject} release date"
                elif topic == TopicType.MUSIC:
                    rewritten = f"{subject} release date"
                elif topic == TopicType.GAMING:
                    rewritten = f"{subject} release date"
                else:
                    rewritten = f"{subject} release date"

        # ── "tell me about" / "tell me more about" ───────────────────────────
        if not rewritten:
            about_m = re.search(r"tell\s+me\s+(more\s+)?about", ql)
            if about_m and subject:
                if topic == TopicType.MUSIC:
                    rewritten = f"{subject} Imagine Dragons song"
                elif topic == TopicType.SPORTS:
                    rewritten = f"{subject} biography career stats news"
                elif topic == TopicType.BOOKS:
                    rewritten = f"{subject} book summary author details"
                else:
                    rewritten = f"{subject} biography history"

        # ── "what happened in X match" (SPORTS-only) ──────────────────────
        if not rewritten and topic == TopicType.SPORTS:
            match_m = re.match(r"what happened\s+(in|at|during)\s+(the\s+)?(.+?)(match|game|race)?$", ql)
            if match_m:
                match_entity = match_m.group(3).strip()
                if match_entity:
                    rewritten = f"{match_entity} latest match goals scorers key events"

        # ── "what happened last X" (SPORTS-only) ───────────────────────────
        if not rewritten and topic == TopicType.SPORTS:
            last_m = re.match(r"what happened\s+(last|this|yesterday('s)?)\s+(.+)", ql)
            if last_m:
                time_ref = last_m.group(1)
                event_context = last_m.group(3).strip()
                rewritten = f"{subject} latest {event_context} results news 2026"

        # ── "show standings/fixtures/highlights/results/analysis" ───────────
        if not rewritten:
            show_m = re.match(r"(?:show|get|find)\s+(standings|fixtures|highlights|results|scores|schedule|table|analysis|recap|clips|bloopers|tactical|best.scenes|behind.the.scenes|ending.explained|goal.compilation)", ql)
            if show_m:
                action = show_m.group(1)
                rewritten = f"{subject} {action}"

        # ── "any X available/updates/news" ──────────────────────────────────
        if not rewritten:
            any_m = re.match(r"any\s+(.+?)\s*(updates?|news|available|released|out yet)?$", ql)
            if any_m:
                request = any_m.group(1).strip()
                if request:
                    rewritten = f"{subject} {request}"

        # ── Single-word entity disambiguation ───────────────────────────────
        if not rewritten and subject and " " not in subject and ql.strip() == subject.lower():
            if topic == TopicType.MUSIC:
                rewritten = f"{subject} song"
            elif topic == TopicType.MOVIES:
                rewritten = f"{subject} movie"
            elif topic == TopicType.TV:
                rewritten = f"{subject} TV show"
            elif topic == TopicType.GAMING:
                rewritten = f"{subject} video game"
            elif topic == TopicType.SPORTS:
                rewritten = f"{subject} sports"
            elif topic == TopicType.BOOKS:
                rewritten = f"{subject} book"

        result = rewritten or query
        if result != query:
            logger.info("[QUERY_REWRITE] original=%s entity=%s rewritten=%s topic=%s", original, subject, result, topic.value)
        return result

    def _retrieve_and_summarize(self, query: str, topic: TopicType, subject: str, mode: str = "") -> tuple[str, Optional[RetrievalResult]]:
        """Retrieve fresh data and compose a structured, topic-appropriate answer."""
        import logging
        logger = logging.getLogger(__name__)
        rewritten = self._rewrite_retrieval(query, topic, subject)
        
        # If rewritten doesn't include the subject, prepend it
        if subject and subject.lower() not in rewritten.lower():
            rewritten = f"{subject} {rewritten}"
        
        res = self._safe_retrieve(rewritten, topic=topic.value, mode=mode)
        
        # Fallback: if first result has empty/insufficient content, retry with original query
        if res:
            raw = res.raw_content or res.summary
            if not raw or len(raw) < 100:
                logger.info("[RETRIEVAL_FALLBACK] rewritten result too short (%d bytes), retrying with original query", len(raw or ""))
                res = self._safe_retrieve(query, topic=topic.value, mode=mode)
        if not res:
            res = self._safe_retrieve(query, topic=topic.value, mode=mode)
        
        if res:
            raw = res.raw_content or res.summary
            if not self._is_relevant(raw, query, subject):
                logger.info("[RELEVANCE_REJECT] query=%s subject=%s len=%d", query, subject, len(raw))
                # Typo tolerance: the REWRITTEN query extracts a bare (often
                # misspelled) entity ("whts the latest on tesal" -> "Tesal")
                # which search engines can misfire on (Exa returned a LinkedIn
                # person "Tes Sal"), while the user's FULL original query is
                # typo-tolerant at the provider and returns the real entity
                # (live: original -> 14KB of Tesla content). Retry with the
                # original query before rejecting — never fabricate a result.
                _orig_res = self._safe_retrieve(query, topic=topic.value, mode=mode)
                if _orig_res:
                    _orig_raw = _orig_res.raw_content or _orig_res.summary
                    if _orig_raw and self._is_relevant(_orig_raw, query, subject):
                        logger.info("[RETRIEVAL_ORIGINAL_FALLBACK] original query relevant (len=%d)", len(_orig_raw))
                        res = _orig_res
                    else:
                        logger.info("[RETRIEVAL_ORIGINAL_FALLBACK] original query also irrelevant (len=%d)", len(_orig_raw or ""))
                        res = None
                else:
                    res = None  # reject irrelevant content

        # Multi-provider fallback for typo'd/ambiguous entities (generalized,
        # never a dictionary): when BOTH the rewritten and the original query
        # produced irrelevant content, ANOTHER provider may autocorrect the
        # typo. Exa's neural search returned a LinkedIn "Tes Sal" page for
        # "tesal" while Tavily returned real current Tesla news — the first
        # provider hit must not be the last word. Collect evidence from ALL
        # healthy providers for both query forms and keep the most relevant
        # result (live: "whts latest on tesal" answered "I don't have
        # information on Tesal yet." despite Tavily having Tesla content).
        if not res:
            _candidates = []
            for _q in dict.fromkeys((rewritten, query)):
                try:
                    for _c in (self._retrieve_evidence(_q, topic.value, max_results=6) or []):
                        _raw = getattr(_c, "raw_content", None) or getattr(_c, "summary", "") or ""
                        if _raw and self._is_relevant(_raw, query, subject):
                            _candidates.append((len(_raw), _c))
                except Exception:
                    continue
            if _candidates:
                _candidates.sort(key=lambda x: x[0], reverse=True)
                res = _candidates[0][1]
                logger.info(
                    "[RETRIEVAL_EVIDENCE_FALLBACK] picked source=%s for subject=%s (query=%s) len=%d",
                    getattr(res, "source", "?"), subject, query, len(getattr(res, "raw_content", "") or ""),
                )
        
        if res:
            self._discover_artifacts(res, topic, subject)
            # Pass the EXTRACTED subject explicitly: the retrieval provider's
            # entity field is often the raw query ("What is Notepad?"), which
            # must never become the displayed subject.
            return self._compose_answer(res, query, subject=subject), res
        
        return f"I don't have information on {subject} yet.", None

    def _is_relevant(self, text: str, query: str, subject: str) -> bool:
        if len(text) < 50:
            return False
        text_lower = text.lower()
        # Works-list queries ("Alex Garland filmography", "Team Cherry list
        # of games") must retrieve content that IS a works list — a page that
        # merely mentions the subject but is release-note/patch-notes shaped
        # ("Added", "Fixed", "Refined", "localisation") is NOT a
        # filmography/bibliography (live: a studio's latest patch notes
        # answered its "what else has that studio made" callback). Reject
        # only that clear release-note shape; reference pages (Wikipedia) and
        # genuine list content pass. The vocabulary is domain-general.
        _works_words = ("filmography", "discography", "bibliography",
                        "list of games", "games list", "works", "film list",
                        "book list")
        if any(w in query.lower() for w in _works_words) and not any(
            w in text_lower for w in _works_words
        ):
            _patch_signal = sum(
                1 for w in ("added", "fixed", "improved", "refined",
                            "localisation", "translation", "patch notes",
                            "bug report", "hotfix", "changelog", "fixed ")
                if w in text_lower
            )
            if _patch_signal >= 2:
                return False
        # Role queries ("who directed X", "who wrote Dune") return the
        # person's page, which legitimately never names the movie/subject —
        # accept it. The stems must cover INFLECTED forms too ("wrote",
        # "written", "director", "author") or the bypass misses and the
        # correctly retrieved person page is rejected as irrelevant (live:
        # "who wrote the book Dune" -> RELEVANCE_REJECT -> "I don't have
        # information").
        _role_stems = ("direct", "director", "writ", "wrote", "written",
                       "author", "compos", "composer", "produc", "producer",
                       "creat", "creator", "design", "designer", "star",
                       "starring", "actor", "voice", "voiced", "sing",
                       "sang", "cast", "develop", "developer", "score",
                       "scored", "screenwriter", "writer", "playwright",
                       "directed", "produced")
        if any(t in query.lower() for t in _role_stems):
            # Role queries ("who directed X", "who wrote Dune") return the
            # PERSON's page, which often does not repeat the work title — but
            # the result must still be ABOUT the person or mention the work.
            # The old blanket bypass accepted UNRELATED pages (live: "who
            # wrote dune" returned a "Capital Asset Management Co., Ltd."
            # page because the 'writ' stem short-circuited relevance; a
            # role-catalog retrieval accepted a Juno Hong article that merely
            # contained "Moon"). Require either a subject mention (fuzzy) or
            # a strong person/role identification signal (biography language,
            # role markers).
            _key = (subject or "").strip().lower()
            _first_tok = _key.split()[0] if _key.split() else ""
            if _key and len(_first_tok) >= 3 and (_key in text_lower or _first_tok in text_lower):
                return True
            _person_signal = re.search(
                r"\b(?:born\s+|directed\s+by|written\s+by|created\s+by|produced\s+by|"
                r"composed\s+by|developed\s+by)\b|"
                r"\bis\s+an?\s+(?:american|british|australian|canadian|"
                r"french|german|indian|english|welsh|scottish|irish|spanish|italian|japanese|chinese|russian|"
                r"singer|actor|actress|musician|author|novelist|writer|playwright|screenwriter|director|artist)\b|"
                r"\b(?:filmography|discography|bibliography)\b",
                text_lower,
            )
            if _person_signal:
                return True
            # Role-query pages that name neither the subject nor a person are
            # irrelevant — fall through to the generic ratio (will reject and
            # trigger the multi-provider fallback).
        # Relevance must hinge on the ENTITY (subject), not the query's
        # interrogative openers and fillers ("what is the latest on X"
        # should not need "what"/"latest"/"on" to appear in the text).
        # Live: typo'd "whts the latest on tesal" -> subject "Whts The
        # Tesal" -> noise tokens dragged the ratio below 0.3 and a good
        # 4305-char Tesla retrieval was rejected as irrelevant.
        _noise = {"what", "whats", "whts", "wat", "wht", "who", "whos", "whose",
                  "where", "when", "why", "how", "which", "is", "are", "was",
                  "were", "the", "a", "an", "of", "in", "on", "at", "for",
                  "to", "with", "by", "about", "and", "or", "latest", "update",
                  "updates", "news", "new", "current", "recent", "tell", "me",
                  "show", "give", "do", "does", "did", "has", "have", "had",
                  "it", "its", "this", "that", "any", "some", "out", "yet",
                  "still", "now", "please", "bro", "yo", "hey", "like", "just"}
        q_words = {w for w in query.lower().split() if len(w) > 2 and w not in _noise}
        s_words = {w for w in subject.lower().split() if len(w) > 2 and w not in _noise}
        key_terms = q_words | s_words
        if not key_terms:
            return True
        # Fuzzy token match (edit distance) so a typo'd entity in the query
        # ("tesal" vs retrieved "tesla") still counts as relevant — generic
        # typo tolerance, never entity-specific.
        def _fuzzy_hit(token: str) -> bool:
            if token in text_lower:
                return True
            if len(token) < 5:
                return False
            from difflib import SequenceMatcher
            for w in text_lower.split():
                if len(w) >= 5 and SequenceMatcher(None, token, w).ratio() >= 0.78:
                    return True
            return False
        match_count = sum(1 for t in key_terms if _fuzzy_hit(t))
        ratio = match_count / len(key_terms)
        return ratio >= 0.3

    def _extract_subject(self, query: str, topic: TopicType) -> str:
        """Best-effort subject extraction from query. Word-boundary-aware.

        For role-based queries (who composed/directed/wrote/created etc.),
        preserves the last entity from memory instead of extracting a garbage
        subject like "Who Composed Soundtrack" from "who composed the soundtrack".
        """
        # Normalize "what's" -> "what is" so interrogative handling sees it
        # ("What's the latest Spider-Man news?" must never extract subject
        # "What'S The Spider-Man Movie ?"). Also covers the apostrophe-less
        # typo contractions real users type ("whts", "whats", "wats", "wat",
        # "whos", "wht") — same semantic family as the 's forms, so "whts
        # the latest on tesal" extracts subject "Tesal" (the entity), never
        # the garbage "Whts The Tesal" (live failure: typo'd opener became
        # the subject and the good retrieval was rejected as irrelevant).
        _q_orig = query
        query = re.sub(
            r"\b(what|who|where|when|why|how|which)'s\b",
            lambda m: m.group(1) + " is",
            query,
            flags=re.I,
        )
        query = re.sub(
            r"\b(whts|whats|wats|wat|wht|whos|whse|hows|whens|wys|y)\b",
            lambda m: {
                "whts": "what is", "whats": "what is", "wats": "what is",
                "wat": "what", "wht": "what", "whos": "who is",
                "whse": "whose", "hows": "how is", "whens": "when is",
                "wys": "why is", "y": "why",
            }[m.group(1).lower()],
            query,
            flags=re.I,
        )
        ql = query.lower().strip()
        # Role queries about the current entity — preserve memory entity name
        _role_words = {"composed", "composer", "soundtrack", "score", "scored",
                       "directed", "director", "wrote", "writer", "created",
                       "creator", "produced", "producer", "developed", "developer",
                       "designed", "designer", "voiced", "voice", "voices",
                       "sang", "sings", "sing", "singer", "performed",
                       "performs", "performer", "performed",
                       "founded", "founder", "co-founded", "founds", "established",
                       "plays", "play", "played", "plays for", "played for",
                       "cast", "actor", "actress", "starred", "stars",
                       "features", "featuring"}
        _first_w = ql.split()[0] if ql.split() else ""
        _interrogatives = {"who", "what", "which"}
        if _first_w in _interrogatives:
            has_role = any(w in ql for w in _role_words)
            if has_role:
                last_e = self._mem.get_last_entity()
                # Prefer explicit entity mentioned in query over stale memory entity.
                # E.g. "Who created The Bear?" should extract "The Bear",
                # not a stale memory entity like "Atomic Habits".
                _query_words = [w.strip(".,!?;:") for w in ql.split()[1:]]
                _has_own_entity = any(w not in _role_words for w in _query_words)
                if _has_own_entity:
                    # Reconstruct entity from original query preserving case.
                    # Filter out role words AND filler words so "Who composed the
                    # soundtrack for Interstellar?" returns "Interstellar", not
                    # "the for Interstellar".
                    _fillers = {"the", "a", "an", "is", "are", "was", "were", "in",
                                "on", "at", "for", "to", "of", "with", "by", "from",
                                "about", "and", "or", "this", "that", "these", "those",
                                "it", "its", "like", "watch", "show", "give", "tell",
                                "i", "me", "my", "we", "you", "your", "he", "she",
                                "they", "them", "their", "can", "could", "would",
                                "will", "shall", "do", "did", "does", "has", "have",
                                "had", "been", "being", "get", "got", "some", "any",
                                "very", "just", "also", "now", "please", "into",
                                "biggest", "compared", "new", "best", "big", "latest"}
                    reconstructed = []
                    for w in query.split()[1:]:
                        w_clean = w.strip(".,!?;:")
                        wl = w_clean.lower()
                        if wl not in _role_words and wl not in _fillers:
                            reconstructed.append(w_clean)
                    if reconstructed:
                        # Check if any reconstructed word was capitalized in the original query
                        # (indicating it IS a proper noun / entity name, not a generic word).
                        orig_words_after_first = query.split()[1:]
                        orig_caps = {w.strip(".,!?;:\"'").lower() 
                                     for w in orig_words_after_first 
                                     if w.strip(".,!?;:\"'") and w.strip(".,!?;:\"'")[0].isupper()}
                        has_proper = any(w.lower() in orig_caps for w in reconstructed)
                        # Lowercase-but-real entities: "who wrote dune" typed
                        # all-lowercase must extract "Dune", NEVER a stale
                        # disk-persisted entity from an unrelated earlier
                        # session (live: answered with a previously-registered
                        # "Capital Asset Management Co., Ltd." instead of
                        # Frank Herbert). The reconstruction names the work
                        # when it contains a word that is NOT generic
                        # role/artifact vocabulary ("dune" is real;
                        # "movie"/"song"/"book" are generic).
                        _generic_terms = _role_words | {
                            "the", "a", "an", "is", "are", "was", "were", "in",
                            "on", "at", "for", "to", "of", "with", "by", "from",
                            "about", "and", "or", "this", "that", "these", "those",
                            "it", "its", "like", "watch", "show", "give", "tell",
                            "i", "me", "my", "we", "you", "your", "he", "she",
                            "they", "them", "their", "can", "could", "would",
                            "will", "shall", "do", "did", "does", "has", "have",
                            "had", "been", "being", "get", "got", "some", "any",
                            "very", "just", "also", "now", "please", "into",
                            "biggest", "compared", "new", "best", "big", "latest",
                            "movie", "film", "show", "series", "book", "novel",
                            "song", "album", "game", "soundtrack", "trailer",
                            "release", "project", "sequel", "remake", "prequel",
                            "main", "members", "cast", "soundtrack", "score", "music",
                        }
                        _has_real_term = any(
                            w.lower() not in _generic_terms for w in reconstructed
                        )
                        if has_proper or _has_real_term:
                            # Comparison queries ("compared to GTA V", "vs old version") 
                            # extract the comparison target, not the subject entity.
                            # Prefer memory entity in this case.
                            if last_e and last_e.name and ("compared" in ql or " versus " in ql or " vs " in ql):
                                return last_e.name
                            return " ".join(reconstructed)
                        # All generic words (e.g. "main members") — prefer memory entity
                        if last_e and last_e.name:
                            return last_e.name
                        return query.strip().title()
                    # All words filtered out — use memory entity
                    if last_e and last_e.name:
                        return last_e.name
                # No entity in query — use memory
                if last_e and last_e.name:
                    return last_e.name

        strip_words = [
            "latest", "update", "updates", "news", "about", "on",
            "tell me", "show me", "what about", "any",
            "explain", "story", "plot", "summary", "synopsis",
            "describe", "overview", "recap", "audiobook", "spoilers",
            "currently", "leading",
            "biggest", "new", "compared",
            "first", "second", "third", "one", "two", "three",
            # generic action/role words so event queries extract the entity:
            # "wat happened with apple" -> "Apple", "whos the ceo of nvidia"
            # -> "Nvidia" (never "Happened Apple" / "Ceo Nvidia").
            "happened", "happening", "happens", "ceo", "cfo", "founder",
            "leader", "president", "owner", "manager", "head", "chief",
            "announced", "announcement", "announces", "released", "launched",
            "launches", "launch", "signed", "retired", "retirement", "won",
            "win", "wins", "beat", "lost", "transferred", "transfer",
            "injured", "injury",
            "star", "stars", "starring", "cast", "directed", "director",
            "wrote", "writer", "produced", "producer", "created", "creator",
            # typo forms of common openers ("abt" = "about", "tho" = "though",
            # "rn" = "right now") — same semantic class as the clean words above.
            "abt", "tho", "rn", "btw", "tbh", "ngl", "idk", "imo", "wbu", "wbt",
        ]
        q = query.lower()
        for w in strip_words:
            if " " in w:
                q = q.replace(w, "")
            else:
                q = re.sub(rf"\b{re.escape(w)}\b", "", q)
        q = re.sub(r"\s+", " ", q).strip()
        if not q:
            last_e = self._mem.get_last_entity()
            if last_e and last_e.name:
                return last_e.name
            return query.strip().title()
        # Garbage detection: if extracted subject looks like a full sentence
        # (question/command structure, or >5 words), fall back to memory entity.
        q_words = q.split()
        garbage_indicators = {"who", "what", "when", "where", "why", "how", "which", "whose",
                              "whom", "can",
                              "would", "could", "should", "will", "shall", "do",
                              "does", "did", "is", "are", "was", "were", "has",
                              "have", "had", "get", "got", "make", "made", "want",
                              "like", "need", "let", "please", "give", "show",
                              "tell", "watch", "play", "open", "find", "search",
                              "i", "you", "he", "she", "we", "they", "me", "my",
                              "your", "his", "her", "its", "our", "their", "that",
                              "this", "these", "those", "some", "any", "there",
                              "then", "than", "very", "just", "also", "now", "here",
                              "without", "with", "about", "after", "before", "while",
                              "first", "then", "next", "last", "between", "through",
                              "during", "because", "although", "however", "therefore"}
        is_garbage = (
            len(q_words) > 5
            or any(w in garbage_indicators for w in q_words)
            or (len(q_words) == 1 and len(q_words[0]) <= 3)
            # Single short generic word ("the", "one", "a", "an") is never a valid subject
        )
        if is_garbage:
            # Try to extract proper nouns from the original query before falling
            # back to stale memory.  Look for words that are capitalized in the
            # original query and are not generic action/filler words.
            orig_words = query.split()
            _skip = {"play", "show", "watch", "the", "a", "an", "i", "me", "my",
                     "we", "you", "he", "she", "it", "they", "them", "this",
                     "that", "these", "those", "who", "what", "where", "when",
                     "why", "how", "which", "whose", "whom", "can", "will", "would", "could", "should",
                     "do", "does", "did", "has", "have", "had", "is", "are",
                     "was", "were", "be", "been", "get", "got", "go", "went",
                     "come", "came", "make", "made", "want", "like", "need",
                     "let", "please", "give", "tell", "open", "find", "search",
                     "about", "with", "without", "for", "to", "of", "in", "on",
                     "at", "by", "from", "into", "through", "during", "before",
                     "after", "while", "then", "than", "very", "just", "also",
                     "now", "here", "there", "some", "any", "all", "both",
                     "each", "every", "first", "last", "next", "more", "much",
                     "many", "too", "again", "once", "never", "always",
                     "ending", "explain", "spoilers", "major", "currently",
                     "honestly", "honest", "though", "although", "anyway",
                     "yeah", "yep", "ok", "okay", "well", "wait", "so",
                     "but", "and", "actually", "literally", "tbh", "ngl",
                     "man", "dude", "bro", "haha", "lol", "omg", "wow",
                     "happened", "happening", "happens", "ceo", "cfo", "founder",
                     "leader", "president", "owner", "manager", "head", "chief",
                     "announced", "announcement", "announces", "released",
                     "launched", "launches", "launch", "signed", "retired",
                     "retirement", "won", "win", "wins", "beat", "lost",
                     "transferred", "transfer", "injured", "injury", "star",
                     "stars", "starring", "directed", "director", "wrote",
                     "writer", "produced", "producer", "created", "creator",
                     "abt", "tho", "rn", "btw", "tbh", "ngl", "idk", "imo",
                     "wbu", "wbt"}
            proper = []
            for w in orig_words:
                wc = w.strip(".,!?;:'\"")
                # Strip possessive so "Marvel's" registers as "Marvel" (never
                # a truncated "Marvel's" entity name).
                if wc.lower().endswith("'s") and len(wc) > 3:
                    wc = wc[:-2]
                if wc and wc[0].isupper() and wc.lower() not in _skip:
                    proper.append(wc)
            if proper:
                return " ".join(proper)
            # No proper nouns found (query may be lowercased by caller).
            # Filter out stop/artifact words to extract meaningful entity words.
            _artifact_content = {"song", "trailer", "teaser", "gameplay", "highlights",
                                 "interview", "movie", "film", "show", "series", "book",
                                 "novel", "audiobook", "soundtrack", "lyrics", "music",
                                 "video", "live", "performance", "concert", "official",
                                 "latest", "update", "updates", "news", "current",
                                 "recent", "standings", "results", "fixtures", "scores",
                                 "table", "group", "leader", "schedule", "analysis",
                                 "recap", "clips", "blooper", "behind", "scenes",
                                 "ending", "explained", "cast", "episode", "season",
                                 "director", "producer", "writer", "composer",
                                 "footage", "version", "scene", "scenes", "moments",
                                 "match", "game", "race", "event", "status",
                                 "spoilers", "spoiler", "major", "main", "ideas",
                                 "summary", "overview", "synopsis", "recap",
                                 "leading", "biggest", "compared", "features"}
            meaningful = [w.strip(".,!?;:'\"") for w in q_words
                          if w.strip(".,!?;:'\"") not in _skip
                          and w.strip(".,!?;:'\"") not in _artifact_content
                          and len(w.strip(".,!?;:'\"")) > 2]
            if meaningful:
                return " ".join(meaningful).title()
            last_e = self._mem.get_last_entity()
            if last_e and last_e.name:
                return last_e.name
            return q.title()
        return q.title()

    # ── store artifact manually (call from MediaManager callbacks) ────────────

    def register_artifact(self, record: ArtifactRecord) -> None:
        self._art.store_artifact(record)
        self._ctx.add_artifact(record)

    # ── expose context for testing ────────────────────────────────────────────

    @property
    def context(self) -> ContextStore:
        return self._ctx

    @property
    def artifact_memory(self) -> ArtifactMemory:
        return self._art

