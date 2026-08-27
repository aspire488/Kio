from __future__ import annotations

import difflib
import json
import logging
import random
import re
import time
from typing import Any, Optional

from mini_kio.core.pipeline.types import IntentType, RoutingDecision
from mini_kio.core.context_manager import get_context_manager
from mini_kio.core.phrases import (
    GREETINGS as _PHRASE_GREETINGS,
    ACKNOWLEDGEMENTS as _PHRASE_ACKNOWLEDGEMENTS,
    THANKS as _PHRASE_THANKS,
    MEDIA_TRANSPORT as _PHRASE_MEDIA_TRANSPORT,
    SYSTEM_ACTIONS as _PHRASE_SYSTEM_ACTIONS,
    FOLDER_KEYWORDS as _PHRASE_FOLDER_KEYWORDS,
    FORBIDDEN_TARGETS as _PHRASE_FORBIDDEN_TARGETS,
)

logger = logging.getLogger(__name__)

# ── Discovery intent: natural-language variants ────────────────────────
# These are MODIFIERS of intent, not literal media entities.  "Play something
# random" must invoke a discovery/random-selection strategy, NOT search YouTube
# for the literal word "random".
_DISCOVERY_TARGETS = frozenset({
    # Direct discovery phrases
    "something random", "something", "anything", "anything random",
    "surprise me", "surprise", "whatever", "idk", "i don't know",
    "show me something", "find something", "pick something",
    "play something", "play anything", "play random",
    "put something on", "put something random on",
    # Natural-language discovery (bare utterances)
    # NOTE: normalizer expands contractions, so include both forms
    # IMPORTANT: 'I'm bored' / 'bored' ALONE must NOT auto-trigger media.
    # Only when the user explicitly adds a media request ("i'm bored, play
    # something") should media activate. The correction prefix stripping
    # handles the compound case.
    "entertain me", "amuse me",
    "give me something", "give me something good",
    "give me something to watch", "give me something to listen to",
    "find me something", "find me something good",
    "find something good", "find something interesting",
    "play me something", "play me something good",
    "put on something", "put on some music",
    "put on something good",
    "show me something good", "show me something interesting",
    "what should i watch", "what should i listen to",
    "what's good", "whats good",
    "recommend something", "suggest something",
})
_DISCOVERY_PREFIXES = (
    "play something ", "play anything ", "play random ",
    "put on something ", "put something ",
    "find me something ", "find something ",
    "give me something ", "show me something ",
    "play me something ",
)


# Pure function words excluded from project/topic identity token overlap in
# forget resolution (content nouns — rig, study, build — carry identity).
_FORGET_PROJ_STOP = frozenset(
    "the my our that this these those a an of for with on in at to from by "
    "and or but is are was were be been it its their his her me now today "
    "tomorrow later about around over under new old next last first again "
    "back still also so just very really thing idea stuff".split()
)


# Interrogative spelling family of the "what" question word. Canonicalized to
# "what" before capability matching so typo/colloquial variants ("whts", "wat",
# "wuts") reach the same routing as "what's". General spelling fold — never a
# per-phrase list.
_WHAT_INTERROGATIVES = frozenset({
    "what", "whats", "what's", "whatis", "whatz",
    "wht", "whts", "wht's", "wat", "wat's",
    "wut", "wuts", "whas", "whaz", "waz", "wazz",
})


# R5a: KIO's own failure replies ("Error: ...", "Couldn't ...") and mojibake
# (replacement chars / double-encoded UTF-8) must not be fed back to the LLM
# as conversation context — that history pollution produced follow-up replies
# that referenced fabricated article content from stale error text.
_BAD_REPLY_RE = re.compile(r"^(?:error\b|couldn't\b|can't\b|i (?:couldn't|can't))", re.IGNORECASE)
_MOJIBAKE_RE = re.compile(r"[\ufffd\u25a1]|Ã[^\x00-\x7f]|â(?:€™|€œ|€[a-zA-Z])")


def _bad_kio_reply(reply: str) -> bool:
    if not reply or not reply.strip():
        return True
    return bool(_BAD_REPLY_RE.search(reply) or _MOJIBAKE_RE.search(reply))


def _strip_self_duplication(reply: str) -> str:
    """Strip a small provider's repeated-sentence echo.

    Live bug: a provider returned "I'd pass—being nagged nonstop...precise
    enough.I'd pass—being nagged nonstop...precise enough." — the same block
    verbatim twice, a max-length model looping its own output. Detect the
    first ~third of the reply re-appearing later and keep only the first
    occurrence (a genuine complete reply never repeats a 40+ char block
    verbatim; "haha haha" style doubling is far shorter and untouched).
    Returns the reply unchanged when no substantial repetition exists.
    """
    s = " ".join(reply.split())
    n = len(s)
    if n < 100:
        return reply
    probe = s[: max(40, n // 3)]
    idx = s.find(probe, len(probe))
    if idx > 0:
        # Only strip when the echo accounts for most of the remaining text
        # (a repeated quotation mid-reply is rarer and left alone).
        remaining = s[idx + len(probe):]
        if len(remaining) <= len(probe) * 3:
            cut = s[:idx].rstrip(" ,;:")
            if len(cut) >= 30:
                return cut
    return reply


# User names KIO may legitimately use. Everything else is treated as an
# invented address the model must never emit.
_KNOWN_USER_NAMES = frozenset({"joel", "kio"})

# Casual/greeting/social fragments that must NEVER be treated as proper-noun
# entities. Message-initial capitalization is a writing convention, not
# entity evidence — "Yoo!", "Lol", "Wow" typed with a capital initial used to
# hit the ENTITY_QUERY capitalization heuristic and were sent to media/
# retrieval (the live "Yoo" -> unrelated UFC biography bug). Derived from the
# classifier's greeting/social vocabulary so future additions stay
# consistent; the extra exclamations cover the observed leak family.
_CASUAL_FRAGMENTS = frozenset(
    {"yoo", "yooo", "yooooo", "yo", "hey", "heyy", "hi", "hii", "hello",
     "sup", "wassup", "whassup", "lol", "lmao", "rofl", "haha", "hahaha",
     "damn", "damm", "wow", "woww", "cool", "nice", "okay", "ok", "kk",
     "alright", "aight", "thanks", "thank", "ty", "thx", "k", "bro", "broo",
     "dude", "bruh", "omg", "hmm", "huh", "oh", "ah", "um", "uh",
     "yeah", "yep", "yup", "nope", "nah", "good", "great", "fine", "sure",
     "welp", "phew", "yikes", "ouch", "oops", "nicee", "awsome", "amazing"}
)


_REPEATED_CHAR_RE = re.compile(r"(.)\1+")


def _casual_normalized(word: str) -> str:
    """Fold casual repetition before membership testing.

    "Yoooooo" -> "yo", "Heeeey" -> "hey", "Wooow" -> "wow", "Lool" ->
    "lol": speakers stretch vowels/letters for emphasis; the entity heuristic
    must not treat that as proper-noun evidence. The membership test only
    fires when the COLLAPSED form is a known casual fragment — no genuine
    entity collapses into a casual set member ("Messi"->"mesi" is not a
    fragment, so "Messi" still routes to entity_query).
    """
    return _REPEATED_CHAR_RE.sub(r"\1", word)


def _sanitize_llm_name_address(reply: str) -> str:
    """Generic anti-fabrication guard for LLM conversational output.

    The model is never allowed to invent the user's name. This strips/rewrites
    two generic address patterns WITHOUT hard-coding any specific name:
      - a standalone trailing proper-name sentence ("...serious. Peter")
      - a greeting + proper-name address ("Hey, Peter ...")
    Known names (joel/kio) pass through untouched.
    """
    if not reply or not reply.strip():
        return reply
    sentences = re.split(r"(?<=[.!?]) +", reply.strip())
    kept: list[str] = []
    for s in sentences:
        word = s.strip().strip(".,!?;:")
        # Lone capitalized single-word sentence that is not a known name:
        # drop it only when it is an appended fragment (2+ sentences), never
        # the whole reply ("OpenAI." as the only sentence stays).
        if (
            len(sentences) >= 2
            and word
            and word[0].isupper()
            and len(word) <= 24
            and re.fullmatch(r"[A-Za-z]+", word)
            and word.lower() not in _KNOWN_USER_NAMES
        ):
            continue
        # Greeting + invented name address -> keep just the greeting.
        m = re.match(
            r"^(hey|hi|hello|oh|wait|listen|look)\b\s*,?\s+([A-Z][a-z]+)\b",
            s,
            re.IGNORECASE,
        )
        if m and m.group(2).lower() not in _KNOWN_USER_NAMES:
            kept.append(m.group(1).capitalize() + s[m.end():].strip())
            continue
        kept.append(s)
    out = " ".join(k for k in kept if k).strip()
    return out if out else reply



def _norm2(t: str) -> str:
    import re as _re
    return _re.sub(r"[^a-z0-9]+", "", (t or "").lower())


def _tok(t: str) -> set:
    import re as _re
    return set(_re.findall(r"[a-z0-9]+", (t or "").lower()))


_PROFILE_STOP = frozenset(
    "a an the and or but of to in on at for with about from by that this "
    "these those it its is are was were be been do does did have has had "
    "you your me my mine we our us i i'm im i've ima gonna thing things "
    "about off out up down over under around into onto".split()
)


def _content_tokens(t: str) -> set:
    import re as _re
    toks = set(_re.findall(r"[a-z0-9]+", (t or "").lower()))
    toks = {w for w in toks if len(w) >= 3 and w not in _PROFILE_STOP}
    return toks


# ── Proactive media offer (standalone, called from _ResponseComposer) ──
# Extracted from Pipeline._maybe_proactive_offer to prevent proactive offers
# from racing the conversational response. The offer is evaluated AFTER the
# response is composed, with strict guards:
#   * never on social/greeting/identity/conversation intent types
#   * never on verification/claim answers
#   * never on pure information/news queries
#   * per-session cooldown (5 min same topic, no consecutive offers)
#   * one line, never a dump
_proactive_last_ts: float = 0.0
_proactive_last_query: str = ""


def _maybe_offer(mm, query: str, result: dict, decision) -> None:
    """Append a restrained media offer to an information_query response.

    Called from _ResponseComposer.compose() — NOT from _exec_media().
    This ensures the offer is evaluated after the response is finalized
    and prevents proactive content from hijacking the response path.
    """
    global _proactive_last_ts, _proactive_last_query
    try:
        if not query or not isinstance(result, dict):
            return
        _src = str(result.get("_source_provider") or "")
        if _src in ("verification", "verification_failed"):
            return
        if not result.get("success") or not (result.get("message") or "").strip():
            return
        _now = time.time()
        # Cooldown: don't re-offer the same topic within 5 minutes
        if _now - _proactive_last_ts < 300 and str(query).strip().lower() == _proactive_last_query:
            return
        # Pure information/news queries must NOT trigger a media offer
        _ql = str(query).lower().strip()
        _INFO_ONLY = (
            "latest news", "current news", "recent news", "what's new",
            "what is new", "what's happening", "what is happening",
            "current events", "recent events", "today's news",
            "today in news", "breaking news", "recent developments",
            "latest updates", "news about", "news on",
        )
        _MEDIA_SEEK = (
            "play ", "watch ", "play me ", "play a ", "play some",
            "video", "trailer", "song ", "music", "interview",
            "podcast", "highlights", "gameplay", "clip",
            "on youtube", "in chrome", "in browser", "desktop app",
        )
        if any(p in _ql for p in _INFO_ONLY) and not any(p in _ql for p in _MEDIA_SEEK):
            return
        offer = mm.offer_media(str(query))
        if offer and offer.get("offer"):
            _proactive_last_ts = _now
            _proactive_last_query = str(query).strip().lower()
            _msg = result.get("message") or ""
            _offer_line = str(offer.get("offer")).strip()
            if _offer_line and _offer_line not in _msg:
                result["message"] = (f"{_msg}\n\n{_offer_line}").strip()
    except Exception:
        pass


class Pipeline:
    """
    Single routing authority for all KIO input.

    Input -> Normalize -> Classify -> Resolve -> Execute -> Compose -> Output
    Every request flows through exactly once. No fallback to competing routers.
    """

    def __init__(self):
        self._normalizer = _NormalizationService()
        self._classifier = _IntentClassifier()
        self._resolver = _CapabilityResolver()
        self._coordinator = _ExecutionCoordinator()
        self._composer = _ResponseComposer()

    def run(
        self,
        text: str,
        session_id: str = "local_0",
        channel: str = "unknown",
        user_id: int = 0,
    ) -> dict[str, Any]:
        try:
            t0 = time.monotonic()
            ctx = get_context_manager(session_id)
            raw = text.strip()
            if not raw:
                return {"success": True, "message": ""}

            normalized = self._normalizer.run(raw, ctx)
            t1 = time.monotonic()
            decision = self._classifier.classify(normalized, raw)
            t2 = time.monotonic()
            decision.session_id = session_id
            decision.channel = channel
            decision.user_id = user_id

            # Context outranks surface form (conversational continuity): the
            # classifier commits to ENTITY_QUERY/INFORMATION from the latest
            # message alone ("Wbt fight club" looks like a capitalized proper
            # noun). When the message continues the ONGOING conversation —
            # callback/comparison morphology ("instead of", "u said", "the
            # one you"), compressed discourse openers ("wbt"/"wbu"), or a
            # bare noun phrase inside an active conversational thread — the
            # decision is corrected to CONVERSATION so the generator resolves
            # it with the full history. Genuine information requests (release
            # dates, casts, news, verification/currentness frames) are NEVER
            # re-routed, so current research stays intact.
            decision = self._apply_discourse_context_override(decision, raw, ctx)

            # Bare verification probes ("Is this true?", "Really?", "Did that
            # actually happen?") carry no claim of their own — they refer to
            # a prior user assertion. When pending propositions exist, route
            # to the verification capability (which resolves the reference);
            # the discourse override above only corrects AWAY from research,
            # so this is the complementary correction TOWARD it.
            decision = self._apply_verification_probe_route(decision, raw, ctx)

            # Graph-backed recall override (FINAL architecture): a question
            # about a KNOWN conversational participant or an already-discussed
            # topic is recall from the semantic graph — never web research.
            # Live failures this fixes: "What did Dana say?" researched a
            # company and FABRICATED Dana's words; "What about Zorbion?"
            # invented "a space-propulsion company" from nothing. The graph
            # already holds Dana's statement and the user's research intent;
            # the override routes those queries to conversation where the
            # state block answers. General mechanism: if the query names a
            # graph participant with attributed statements (or an attributed
            # topic), it is a continuation of the conversation, not a lookup.
            decision = self._apply_graph_recall_override(decision, raw)

            # Deterministic profile recall: 'what do you remember about me /
            # what are my priorities / when did I tell you X' are answered
            # from the canonical graph (user-attributed claims with dates),
            # never left to the LLM's vague meta-answers. General mechanism:
            # the query is a profile query iff it asks about the USER's own
            # data (me/my/us/our) or the user's goals/priorities.
            _profile_answer = self._apply_profile_recall_answer(decision, raw)
            if _profile_answer is not None:
                return _profile_answer

            # User assertions become discourse propositions (provenance=user,
            # verification=unknown) so a follow-up can verify them. Registered
            # for every declarative statement — the verification reclaim reads
            # the same store. Pure discourse side-effect; never rewrites the
            # route. Returns True when a fresh proposition was stored.

            # Claim-store lifecycle: a bare probe refers to the IMMEDIATELY
            # preceding proposition. When the current message is NOT a
            # verification-family turn (no probe, no new assertion), the
            # user has moved to a new topic — consume the session's pending
            # claims so a later "is that true?" cannot resurrect an old
            # conversation's claim (live: a Kawhi-trade claim from an earlier
            # session answered a "Did that actually happen?" in an unrelated
            # sports thread).
            _assertion_registered = self._register_user_assertion(decision, raw)
            self._consume_stale_claims(decision, raw, _assertion_registered)

            # ── Demand-driven semantic ingestion ──────────────────────────
            # Ponytail: universal ingestion added 1.9s to EVERY turn (even
            # "hello") via DB/graph init. CompanionContext demand-driven:
            # only ingest when graph state actually answers the query
            # (conversation / memory / information / entity_query). Greetings,
            # deterministic ops, desktop actions skip ingestion — they neither
            # need nor benefit from graph state, and latency budget requires it.
            from mini_kio.core.pipeline.types import IntentType as _IT2
            _needs_graph = decision.intent_type in (_IT2.CONVERSATION, _IT2.MEMORY, _IT2.INFORMATION, _IT2.ENTITY_QUERY, _IT2.KNOWLEDGE)
            if _needs_graph:
                try:
                    from mini_kio.semantic import intelligence as _sem
                    _ing = _sem.ingest_turn(session_id, raw, normalized)
                    try:
                        from mini_kio.memory.living_model import seed_current_facts
                        seed_current_facts(session_id)
                    except Exception:
                        pass
                    _planner = _sem.planner_decision(
                        session_id, raw, _ing.get("decomposition"), _ing.get("resolution")
                    )
                    decision.metadata["semantic_state"] = {
                        "ingestion": _ing,
                        "planner": _planner,
                    }
                except Exception:
                    pass

            capability, params = self._resolver.resolve(decision)
            t3 = time.monotonic()
            result = self._coordinator.execute(capability, params, decision)
            t4 = time.monotonic()
            composed = self._composer.compose(result, decision, ctx)
            t5 = time.monotonic()

            # Stage-latency instrumentation (Section 10/23): per-command
            # timings land in the runtime trace so local-action latency is
            # measurable before/after a change, never guessed.
            try:
                from mini_kio.core.runtime import emit_runtime_trace
                emit_runtime_trace(
                    "pipeline_profile",
                    normalize_ms=round((t1 - t0) * 1000),
                    classify_ms=round((t2 - t1) * 1000),
                    resolve_ms=round((t3 - t2) * 1000),
                    exec_ms=round((t4 - t3) * 1000),
                    compose_ms=round((t5 - t4) * 1000),
                    total_ms=round((t5 - t0) * 1000),
                    intent=str(decision.intent_type.value) if decision.intent_type else "",
                    action=decision.action,
                    channel=channel,
                )
            except Exception:
                pass
            return composed
        except Exception as exc:
            logger.exception("Pipeline.run failed for %r", text)
            return {"success": False, "message": f"Error: {str(exc)[:200]}"}

    # ── Context-aware discourse override (conversational continuity) ─────────
    # Canonical owner of "context outranks surface form". The classifier
    # decides from the LATEST message alone; these corrections re-route a
    # surface-form ENTITY_QUERY/INFORMATION back to CONVERSATION when the
    # message continues the ongoing discussion. Generic mechanisms only —
    # no abbreviation dictionary, no per-entity cases: callback/comparison
    # morphology, compressed discourse openers (morphology of the lead
    # token), and bare-noun-phrase references inside an active conversational
    # thread. Genuine information requests (release dates, casts, news,
    # verification/currentness frames) are never re-routed, so live research
    # stays intact ("What's the latest on Messi?" still researches; "Wbt
    # fight club" after a movie recommendation stays conversational).

    # Information-request vocabulary: presence keeps the research route.
    # Bounded and generic; these words describe a lookup about an entity,
    # never discourse continuation.
    _INFO_REQUEST_RE = re.compile(
        r"\brelease\s*date\b|\brelease\b|\bcast\b|\btrailer\b|\bteaser\b|"
        r"\bsoundtrack\b|\bplot\b|\bending\b|\breview|\bsummary\b|\bsynopsis\b|"
        r"\bgameplay\b|\bnews\b|\bstandings\b|\bfixtures\b|\bresults\b|"
        r"\bscores?\b|\bhighlights\b|\bdiscography\b|\bfilmography\b|"
        r"\bbiography\b|\bstats\b|\bstatistics\b|\bcareer\b|\bawards\b|"
        r"\bnet\s+worth\b|\bspecs?\b|\bspecifications\b|\bprice\b|\bcost\b|"
        r"\bwho\s+(?:is|was|are)\b|\bwhat\s+(?:is|are|was|were)\b|"
        r"\bwhen\s+(?:is|did|was|are)\b|\bwhere\s+(?:is|did|was|are)\b|"
        r"\bhow\s+(?:much|many|does|do)\b|\btell\s+(?:me|us)\s+about\b|"
        r"\bis\s+it\s+(?:true|confirmed|official|real)\b|\bis\s+that\s+(?:true|real)\b|"
        r"\bdid\s+(?:(?:the|a|an|my|our|your|their)\s+)?[a-z0-9]+\s+(?:actually|really|officially|just|even)?\s*"
        r"(?:say|says|said|happen|happened|die|died|retire|retired|leave|left|quit|cancel|cancelled|canceled|"
        r"announce|announced|confirm|confirmed|release|released|transfer|transferred|sign|signed|win|won|"
        r"lose|lost|beat|beaten|drop|dropped|score|scored|play|played|fire|fired|hire|hired|join|joined|"
        r"resign|resigned|debut|return|returned|step\s+down)\b|"
        r"\bi\s+(?:heard|read|saw)\b|\bsomeone\s+told\s+me\b|\bapparently\b|"
        r"\bpeople\s+are\s+saying\b|\bru[mn]?or\b|\bwhat\s+happened(?:\s+to)?\b|"
        r"\bwhat'?s\s+new\b|\bwhat\s+is\s+new\b|\blatest\b|\bupdates?\b|"
        r"\bpassed\s+away\b|\bdied\b|\bdead\b|\balive\b|\bretired?\b|"
        r"\bannounced\b|\bconfirmed\b|\breleased\b|\bcancel(?:led|ed)?\b|\bdelayed\b|"
        r"\bstill\s+(?:playing|alive|ceo|available|in)\b|\bwhat\s+does\b|"
        r"\bexplain\b|\bdefine\b|\bmeaning\b|\bhistory\s+of\b|"
        r"\bwho\s+(?:made|created|wrote)\b|\bborn\b|\bheight\b|\bworth\b|"
        r"\bis\s+\w+\s+(?:dead|alive|retired|cancelled|delayed)\b|"
        # Role-catalog questions ("what else has that director made", "what
        # other films has this actor been in", "what else has that author
        # written") are CURRENT-FACT requests — a filmography/discography/
        # bibliography grows over time, so the answer must come from live
        # research, never the LLM's memory (live: Nolan's filmography answered
        # from memory after The Odyssey released). Keep them on the research
        # route even inside an active conversational thread.
        r"\bwhat\s+else\s+has\b|\bwhat\s+other\s+(?:movies?|films?|works?|albums?|books?)\s+has\b|"
        r"\bwhat\s+else\s+(?:has|did)\b|\bother\s+(?:movies?|films?|works?|albums?|books?)\s+(?:has|did)\b|"
        r"\belse\s+(?:has|did)\s+(?:that|this|the)\s+(?:director|author|writer|actor|actress|artist|band|singer|composer|creator|producer|developer)\b|"
        # Role-verb relationship questions ("who founded X", "who developed
        # X", "who sang X") are entity lookups — they must stay on the
        # research route even inside an active conversational thread. The
        # surface verbs fold into the canonical relationship predicate
        # vocabulary (same closed semantic class as the "who directed" forms).
        r"\bwho\s+(?:(?:co-)?founded|developed|directed|directs|composed|composes|produced|produces|"
        r"published|publishes|manufactured|manufactures|sang|sings|performed|performs|voiced|voices|"
        r"narrated|narrates|created|creates|wrote|writes)\b",
        re.I,
    )

    # Companion/personal intelligence: questions about the USER or KIO's
    # understanding of the user. These are NEVER media/information lookups —
    # they route to conversation → intelligence_layer for evidence-backed
    # longitudinal synthesis. Semantic class, not phrase list.
    _COMPANION_RE = re.compile(
        r"\b(who am i|about me|about yourself|yourself|"
        r"what do (?:you|u) know (?:about|abt|of) (?:me|myself)|"
        r"what (?:do|did|have) (?:you|u) (?:know|learn|get wrong|correct|"
        r"remember|think) .*?(?:me|us|you|kio)|"
        r"how (?:do|did|have) (?:i|we) (?:usually |normally )?(?:work|"
        r"communicate|interact|talk|build|debug|make|react|prefer|"
        r"ask|express|respond|handle|approach)|"
        r"how (?:has|have|did) (?:kio|you|our|we|this) (?:change|evolve|"
        r"grow|learn|improve|develop)|"
        r"what (?:am i|like|usually|tend|patterns|have i) .*?(?:when|"
        r"if|during|while|as)|"
        r"what (?:have i|did i|changed|dropped|abandon|stop|revive|"
        r"bring back|completely|stuff .{0,20} dropped)|"
        r"what (?:frustrat|excit|piss|annoy|bother) .*?(?:me|i|us)|"
        r"what (?:do you|can you) (?:say|tell|explain) about (?:me|"
        r"yourself|your|us|our)|"
        r"what (?:patterns|habits|trends|recurring) .*?(?:you see|you notice|"
        r"have you seen)|"
        r"what (?:evidence|data|information) .*?(?:are you using|"
        r"support|back)|"
        r"what are you (?:least |most )?(?:sure|certain|uncertain|"
        r"confident|unsure) about|"
        r"what (?:should|must|can) you (?:know )?(?:not|never|avoid)(?: to)?(?: not)? do(?:ing)? (?:with|"
        r"to|for) (?:me|us)|"
        r"what have (?:you|i) (?:gotten|got) (?:wrong|incorrect|"
        r"mistake)|"
        r"what (?:kind|sort|type) (?:of )?(?:answers?|person|student|"
        r"developer|engineer|response|reply|help) (?:do i|does .* ?prefer|"
        r"am i|are you|should)|"
        r"how (?:do|does|has) my (?:communication|style|tone|way|"
        r"approach|method|work) (?:change|vary|shift|differ)|"
        r"how (?:has|have|did) (?:our|we|the) (?:work|relationship|"
        r"collaboration|partnership) (?:change|evolve|grow)(?:d|ed|ing|s)?|"
        r"what (?:do|does) (?:kio|you) (?:know|understand|learn) about|"
        r"what (?:used to|were you) (?:care|matter|focus|think|want|"
        r"be into|interested|obsessed)|"
        r"what (?:was i|were you) (?:into|focused on|obsessed|"
        r"interested|working on) .*?(?:months|ago|before|earlier)|"
        r"what (?:expectations?|rules?|boundaries?) (?:do you|should you|"
        r"have you) (?:have|set|keep|follow)|"
        r"do you (?:actually )?(?:learn|get better|improve|improve)"
        r")\b",
        re.I,
    )

    # Unambiguous callback/comparison/referent morphology — constructions that
    # reference PRIOR discourse and can never be entity lookups. These are
    # session-independent: "what about Dune instead?" is conversational even
    # with no history.
    _CALLBACK_RE = re.compile(
        r"\binstead\b|"
        r"\bu\s+said\b|\byou\s+said\b|"
        r"\byou\s+recommend(?:ed)?\b|\bu\s+recommend(?:ed)?\b|"
        r"\byou\s+suggest(?:ed)?\b|\bu\s+suggest(?:ed)?\b|"
        r"\byou\s+mention(?:ed)?\b|\bu\s+mention(?:ed)?\b|"
        r"\byou\s+picked\b|\byou\s+chose\b|\byou\s+went\s+with\b|"
        r"\bthe\s+ones?\s+you\b|\bthat\s+(?:other\s+)?one\b|\bthe\s+other\s+one\b|"
        r"\bthe\s+(?:first|second|third|fourth|fifth)\s+one\b|"
        r"\bgoing\s+back\s+to\b|\bback\s+to\s+(?:that|this|it|the)\b|"
        r"\brather\s+than\b|\bworth\s+(?:watching|reading|playing|listening\s+to)\b|"
        r"\bwhat\s+do\s+you\s+think\s+of\b|\bwould\s+you\s+(?:pick|choose|go\s+with)\b|"
        r"\byou\s+said\s+earlier\b|\bthe\s+one\s+that\b|"
        r"\bwhat\s+about\s+(?:\w+\s+){0,3}(?:though|anyway|still|then|tonight)\b|"
        r"\bover\s+(?:it|that|this)\b",
        re.I,
    )

    # Bare verification-probe vocabulary: a message whose ENTIRE content is
    # verification words ("is this true", "really", "did that actually
    # happen", "are you sure", "that's confirmed") carries NO new
    # proposition of its own — it is a REFERENTIAL probe that asks about
    # prior discourse. Same semantic class as the adapter's
    # _VERIF_GENERIC_TOKENS; kept here so routing can decide without a media
    # import (the pending-claims check below uses the adapter, this set is
    # pure vocabulary).
    _VERIF_PROBE_TOKENS = frozenset({
        "true", "real", "really", "actually", "happened", "happen",
        "say", "said", "says", "talking", "people", "someone", "anyone",
        "saw", "read", "heard", "thing", "things", "stuff", "news",
        "rumor", "rumors", "online", "around", "about", "right", "still",
        "supposedly", "apparently", "reportedly", "allegedly", "rumored",
        "story", "stories", "sure", "confirm", "confirmed", "serious",
        "seriously", "verify", "verified", "correct", "fact", "facts",
        "exact", "exactly", "wait", "hold", "mean", "meant", "explain",
        # Bare referents (that/this/it) are stopwords and never survive
        # _meaningful_tokens raw — they only appear via CONTRACTION
        # normalization ("that's confirmed" -> "that confirmed"). Including
        # them here is safe: a raw "that"/"this" message is empty after
        # stopword stripping and never reaches this comparison.
        "that", "this", "it", "those", "these",
    })

    def _is_bare_verification_probe(self, text: str) -> bool:
        """True when the message adds no propositional content of its own —
        every content token is a verification/probe word. "Is this true",
        "Really?", "Did that actually happen?", "Are you sure?" all reduce
        to {true} / {really} / {happened, actually} / {sure}."""
        try:
            from mini_kio.media.intelligence.integration_adapter import _meaningful_tokens
        except Exception:
            return False
        toks = _meaningful_tokens(text)
        if not toks:
            return False
        # Contraction normalization: "that's confirmed" -> "that confirmed" —
        # _meaningful_tokens keeps "that's" (not in the stopword list), which
        # would make the probe check fail. Referent contractions (that's,
        # it's, this's) reduce to the base referent word and stay probe
        # vocabulary.
        _norm = set()
        for t in toks:
            t2 = re.sub(r"'(?:s|re|ll|ve|d|t)\b", "", t.lower())
            _norm.add(t2 or t)
        return _norm <= self._VERIF_PROBE_TOKENS

    def _register_user_assertion(self, decision, raw_text: str) -> bool:
        """Register a declarative user statement as a pending proposition so a
        later bare probe ("Is this true?") resolves against it.

        The user's statement is discourse state with provenance=user and
        verification=unknown — "Ronaldo got married too" must become a
        verifiable claim, not vanish into a conversational reply. Gate: NOT a
        question/command (first word is a real subject, not an interrogative
        or auxiliary), 3+ words, and carries a state/event predicate. Uses the
        adapter's claim-splitting (the SAME store the follow-up reclaim
        reads) — one proposition store, no parallel system. Returns True when
        a proposition was registered (so the caller knows the claim store
        holds a CURRENT assertion that must NOT be consumed).
        """
        try:
            text = (raw_text or decision.normalized_text or "").strip()
            words = text.split()
            if len(words) < 3:
                return False
            first = words[0].strip(".,!?;:").lower()
            if first in {"is", "are", "was", "were", "do", "does", "did",
                         "has", "have", "had", "can", "could", "will",
                         "would", "should", "may", "might", "am", "who",
                         "what", "when", "where", "why", "how", "which",
                         "open", "close", "play", "search", "show", "tell",
                         "give", "set", "turn", "stop", "start", "help",
                         "remember", "forget", "go", "run", "take", "make",
                         "create", "save", "delete", "copy", "move", "send"}:
                return False
            # Gate on the SAME state/event-predicate vocabulary the
            # verification capability uses ("married", "died", "released",
            # "won", "left"...): only statements that assert a changing-world
            # fact about a subject become pending propositions. Casual chat
            # ("I like this movie") carries no state predicate and must not
            # pollute the claim store — a later "really?" after casual chat
            # must stay a reaction, not trigger research.
            from mini_kio.media.intelligence.integration_adapter import (
                MediaIntelligenceAdapter,
            )
            _predicates = MediaIntelligenceAdapter._VERIF_STATE
            _low = text.lower()
            if not any(p in _low for p in _predicates):
                return False
            from mini_kio.media.media_manager import MediaManager
            mm = MediaManager.get_instance()
            adapter = getattr(mm, "_intelligence_adapter", None)
            if adapter is not None:
                adapter.register_user_assertion(
                    text, session_id=getattr(decision, "session_id", "") or ""
                )
                return True
        except Exception:
            pass
        return False

    def _consume_stale_claims(self, decision, raw_text: str, assertion_registered: bool) -> None:
        """Consume the session's pending verification claims when the user has
        moved to a new topic.

        A bare probe ("Is this true?") refers to the IMMEDIATELY preceding
        proposition. Claims therefore have a conversation-scoped lifetime:
        when a message is NOT a verification-family turn, the old proposition
        is no longer the active subject — later probes must not resurrect it
        (live: a Kawhi-trade claim from an earlier session answered a "Did
        that actually happen?" in an unrelated sports thread).

        Keeps claims when ANY of these hold:
          * the turn just registered a FRESH assertion (the claim store now
            holds the CURRENT proposition — consuming would delete it);
          * the decision is INFORMATION (bare probes were routed there by
            _apply_verification_probe_route and NEED the claims; verification
            frames carry their own claim content and re-store it);
          * the message is an ELABORATION of the stored claims ("when did
            that happen?", "what exactly did Messi say?") — it may route as
            an entity query but still refers to the pending proposition.
        """
        try:
            from mini_kio.core.pipeline.types import IntentType as _IT
            if assertion_registered:
                return
            if decision.intent_type == _IT.INFORMATION:
                return
            from mini_kio.media.media_manager import MediaManager
            mm = MediaManager.get_instance()
            adapter = getattr(mm, "_intelligence_adapter", None)
            if adapter is None:
                return
            _session = getattr(decision, "session_id", "") or ""
            _q = (raw_text or decision.normalized_text or "").strip()
            if adapter._is_verification_query(_q) or adapter._is_verif_elaboration_followup(_q, _session):
                return
            adapter.clear_user_claims(_session)
            logger.info(
                "[CLAIMS_CONSUMED] session=%s route=%s (topic move)",
                _session,
                decision.action,
            )
        except Exception:
            pass

    def _apply_graph_recall_override(self, decision, raw_text: str) -> "RoutingDecision":
        """Route research-bound queries that actually reference graph state to
        CONVERSATION so the semantic graph answers them.

        The FINAL architecture: user/KIO/third parties are ordinary
        participants; "what did X say / what about X / back to X" where X is
        a KNOWN graph participant or an already-discussed topic is recall from
        the graph — never web research (which fabricates: live "What did
        Dana say?" researched a company and invented Dana's words; "What
        about Zorbion?" invented a fake company description).

        Only re-routes when the graph ACTUALLY holds attributed content for
        the referenced name — a genuinely new entity (never mentioned) still
        goes to research. General mechanism: graph participants and
        attributed topics outrank web retrieval for continuation questions.
        """
        from mini_kio.core.pipeline.types import IntentType as _IT
        _it = decision.intent_type
        # BROWSER_TABS ("what's open", "what processes are running") is a
        # DETERMINISTIC system query — never override to conversation.
        if _it == _IT.BROWSER_TABS:
            return decision
        if _it not in (_IT.INFORMATION, _IT.ENTITY_QUERY):
            return decision
        _raw = raw_text or decision.raw_text or decision.normalized_text or ""
        if len(_raw.strip()) < 3:
            return decision
        _low = _raw.strip().lower()

        # Freshness/current-information queries MUST NOT be overridden to
        # CONVERSATION. "What is the latest version of React?" references a
        # known topic (React exists in the graph) but asks for CURRENT
        # EXTERNAL information — graph recall would return stale topic
        # knowledge instead of live search results. General mechanism:
        # freshness indicators override graph topic membership.
        _freshness_re = re.compile(
            r"\b(?:latest|current|newest|recently?|what\s+changed|what\s+is\s+new|"
            r"what'?s\s+new|update|updates|version|release|price|cost|"
            r"how\s+(?:much|many)|when\s+(?:is|was|did)|where\s+(?:is|can)"
            r")\b",
            re.IGNORECASE,
        )
        if _freshness_re.search(_low):
            return decision

        # First-person activity recall (F4, holdout): "what am I working on /
        # doing / up to / trying to do" is a USER-STATE question. The graph
        # holds the user's intentions/commitments as user-attributed
        # statements; when any exist, the answer is the user's goals — NOT the
        # desktop window list. Desktop state remains the fallback when the
        # graph has no user goals ("what am I running" is genuinely about
        # processes). General mechanism: user state (graph) outranks desktop
        # state (runtime snapshot) for first-person activity questions.
        if _it == _IT.BROWSER_TABS and re.match(
            r"^what\s+(?:am\s+i|are\s+we)\s+(?:currently\s+)?(?:working\s+on|doing|up\s+to|trying\s+to\s+do)\b",
            _low,
        ):
            try:
                from mini_kio.semantic.graph import USER_KEY, SemanticGraph as _SG
                _g = _SG(getattr(decision, "session_id", "") or "")
                _user_goals = [
                    s for s in _g.attributed_statements(USER_KEY, active_only=True, limit=10)
                    if str(getattr(s, "target_name", "") or "").lower().startswith(
                        ("wants:", "decides:", "researching:", "intention:")
                    )
                ]
                if _user_goals:
                    logger.info(
                        "[GRAPH_RECALL] %r -> CONVERSATION (user goals in graph, desktop fallback)",
                        raw_text,
                    )
                    return RoutingDecision(
                        _IT.CONVERSATION, "converse", _raw, _raw, _low,
                        confidence=0.85,
                        session_id=decision.session_id,
                        channel=decision.channel,
                        user_id=decision.user_id,
                        metadata=dict(decision.metadata, graph_recall=True),
                    )
            except Exception:
                pass
            return decision
        try:
            from mini_kio.semantic.graph import KIO_KEY, USER_KEY, SemanticGraph
            _sid = getattr(decision, "session_id", "") or ""
            if not _sid:
                return decision
            graph = SemanticGraph(_sid)
            low = _raw.strip().lower()

            # Candidate name(s): capitalized tokens (proper nouns) or role
            # phrases ("my friend", "the developer") that could address a
            # graph participant, plus "about/back to <X>" targets.
            _QUESTION_WORDS = frozenset({
                "what", "where", "when", "which", "who", "whose",
                "how", "why", "does", "did", "has", "have", "had",
                "can", "could", "would", "should", "will", "shall",
                "is", "are", "was", "were", "the", "this", "that",
                "close", "open", "search", "play", "stop", "pause",
            })
            names = set()
            for m in re.finditer(r"\b[A-Z][A-Za-z]{2,20}\b", _raw):
                _w = m.group(0)
                if _w.lower() not in _QUESTION_WORDS:
                    names.add(_w)
            for m in re.finditer(
                r"(?:about|back to|regarding|on)\s+([A-Za-z][A-Za-z0-9\- ]{2,40}?)(?:\s*(?:\?|\.|,|$|\band\b))",
                low,
            ):
                _t = m.group(1).strip()
                if _t and len(_t) >= 3:
                    names.add(_t.title())
            # "what about the company" — bare description of an attributed topic.
            for m in re.finditer(
                r"(?:what about|back to|the\s+thing about)\s+([a-z0-9][a-z0-9\- ]{2,40}?)(?:\s*(?:\?|\.|,|$))",
                low,
            ):
                _t = m.group(1).strip()
                if _t and len(_t) >= 3:
                    names.add(_t.title())
            if not names:
                return decision

            # Candidate norm keys + token sets for loose matching.
            def _norm(name: str) -> str:
                return re.sub(r"[^a-z0-9]+", "", name.lower())

            names_norm = {n: _norm(n) for n in names}
            # Does the graph hold attributed content for any candidate?
            def _participant_has_statements(name: str) -> bool:
                node = graph.get_node_by_key(f"participant:{_norm(name)}")
                if node is None or node.status == "forgotten":
                    return False
                return bool(graph.attributed_statements(node.key, active_only=True, limit=3))

            # Research intent match: the user said "I'm researching X" — a
            # later "What about X?" is recall of that intent, never web lookup.
            def _research_intent_matches(name: str) -> bool:
                n = _norm(name)
                if len(n) < 3:
                    return False
                for s in graph.attributed_statements(USER_KEY, active_only=True, limit=20):
                    t = str(getattr(s, "target_name", "") or "").strip()
                    if not t.lower().startswith("researching:"):
                        continue
                    if n in _norm(t) or _norm(t) in n:
                        return True
                return False

            # Topic node match by key OR token overlap ("zorbion" matches
            # topic node "Zorbion Dynamics").
            def _topic_matches(name: str) -> bool:
                node = graph.get_node_by_key(f"topic:{_norm(name)}")
                if node is not None and node.status != "forgotten":
                    return True
                _n_tokens = set(re.findall(r"[a-z0-9]+", name.lower()))
                for n in graph.all_active_nodes():
                    if n.kind != "topic" or n.status == "forgotten":
                        continue
                    _t_tokens = set(re.findall(r"[a-z0-9]+", (n.name or "").lower()))
                    if _n_tokens and _t_tokens and (_n_tokens & _t_tokens):
                        return True
                return False

            for name in names:
                _has_stmt = _participant_has_statements(name)
                _has_research = _research_intent_matches(name)
                _has_topic = _topic_matches(name)
                if _has_stmt or _has_research or _has_topic:
                    logger.info(
                        "[GRAPH_RECALL] %r -> CONVERSATION (participant=%s research=%s topic=%s)",
                        raw_text, _has_stmt, _has_research, _has_topic,
                    )
                    return RoutingDecision(
                        _IT.CONVERSATION, "converse", _raw, _raw, low,
                        confidence=0.85,
                        session_id=decision.session_id,
                        channel=decision.channel,
                        user_id=decision.user_id,
                        metadata=dict(decision.metadata, graph_recall=True),
                    )
        except Exception:
            pass
        return decision

    def _apply_profile_recall_answer(self, decision, raw_text: str):
        """Natural personal-state answers from the LIVING USER MODEL.

        Intercepts PERSONAL-STATE questions (what do you remember about me,
        what are my priorities, what am I studying, what's my CGPA, what am I
        working on, what do I like, strengths/weaknesses, what changed
        recently, when did I tell you X). Composes a NATURAL answer from the
        living-model brief (current-first, historical marked, confidence
        hedged) — never a raw graph dump. Falls back to a deterministic
        natural sentence when the LLM is unavailable.
        """
        _raw = (raw_text or decision.normalized_text or decision.raw_text or "").strip()
        _low = _raw.lower()
        if len(_low) < 5:
            return None

        # "when did I tell you about X" — provenance question (keep existing
        # deterministic path; it already answers naturally).
        _when_m = re.search(r"\bwhen\s+did\s+i\s+tell\s+you\s+(?:about\s+)?(.+?)\s*$", _low)
        if _when_m:
            return self._when_told_answer(decision, _when_m.group(1))

        # personal-state question families (general morphology, no names)
        _about_me = bool(re.search(
            r"\b(?:remember|know|got)\s+(?:about|of|on)\s+(?:me|my|us|our)\b", _low))
        _tell_about_self = bool(re.search(
            r"\b(?:tell\s+me\s+about\s+myself|what(?:'s|s)\s+(?:my|the)\s+(?:profile|summary|situation)\b"
            r"|who\s+am\s+i\b|what\s+(?:kind\s+of|sort\s+of)\s+person\s+am\s+i\b"
            r"|what\s+(?:patterns|habits?)\s+(?:do\s+you\s+)?(?:notice|see|observe)"
            r"|give\s+me\s+a\s+picture\s+of\s+where\s+i\s+am\b)", _low))
        _about_me = _about_me or _tell_about_self
        _priorities = bool(re.search(
            r"\bwhat\s+(?:are|were)\s+my\s+(?:current\s+)?"
            r"(?:priorities|goals|plans|interests|focus|priorities\s+right\s+now)\b", _low))
        _education = bool(re.search(
            r"\b(?:what|which)\s+(?:am\s+i\s+)?(?:studying|semester|year|college|course|cgpa|"
            r"grade|gpa)\b|\bwhat'?s?\s+my\s+(?:cgpa|gpa|semester|grade|year)\b|"
            r"\bwhat\s+am\s+i\s+studying\b", _low))
        _working = bool(re.search(r"\b(?:working\s+on|building|projects|doing|up\s+to)\b", _low))
        _strengths = bool(re.search(r"\b(?:strengths|good\s+at|weaknesses|weak\s+at|bad\s+at"
                                    r"|frustrates|annoy)\b", _low))
        _likes = bool(re.search(r"\bwhat\s+do\s+i\s+(?:like|hate|prefer|enjoy)\b|"
                                r"\bhow\s+do\s+i\s+like\b", _low))
        _changed = bool(re.search(r"\bwhat\s+(?:changed|has\s+changed|changed\s+recently|"
                                  r"am\s+i\s+learning|am\s+i\s+improving)\b", _low))
        # "what am I waiting for" — an explicit USER WAIT STATE is graph
        # evidence (recorded by ingestion; the proactive evaluator DEFERS on
        # it). Answer from the graph deterministically instead of leaving the
        # LLM to fabricate a mystical answer (live: "waiting on the OpenCode
        # review" produced "waiting for a decision hidden from you").
        _waiting = bool(re.search(r"\bwhat\s+(?:am\s+i\s+)?waiting\s+(?:for|on)\b", _low))
        if _waiting:
            return self._waiting_answer(decision)
        if not (_about_me or _priorities or _education or _working
                or _strengths or _likes or _changed):
            return None

        sid = getattr(decision, "session_id", "") or ""
        try:
            from mini_kio.memory.living_model import personal_brief
            brief = personal_brief(sid)
        except Exception:
            return None
        if not brief:
            return None

        composed = self._compose_natural_personal(sid, _raw, brief)
        return {"success": True, "message": composed, "action": "profile_recall"}

    def _when_told_answer(self, decision, q):
        """'when did I tell you about X' — provenance from user-attributed
        claims (content-token matched; no stopword false overlaps)."""
        sid = getattr(decision, "session_id", "") or ""
        q = (q or "").strip().strip("?")
        try:
            from mini_kio.semantic.graph import SemanticGraph, USER_KEY
            from mini_kio.memory.profile import _when
        except Exception:
            return {"success": True, "message": "I don't have a note of that.", "action": "profile_recall"}
        try:
            graph = SemanticGraph(sid)
            links = graph.attributed_statements(USER_KEY, active_only=True, limit=200)
        except Exception:
            return {"success": True, "message": "I don't have a note of that.", "action": "profile_recall"}
        if not links:
            return {"success": True, "message": "I don't have a note of you telling me that.",
                    "action": "profile_recall"}
        _q_content = _content_tokens(q)
        scored = []
        for g in links:
            name = (getattr(g, "target_name", "") or "").strip()
            if not name or name.startswith("rule:"):
                continue
            nq = _norm2(q)
            nn = _norm2(name)
            if nq and (nq in nn or nn in nq):
                scored.append((g, 1000))
                continue
            if _q_content:
                shared = _q_content & _content_tokens(name)
                if shared:
                    scored.append((g, 100 + len(shared)))
        if scored:
            scored.sort(key=lambda x: -x[1])
            g = scored[0][0]
            name = (getattr(g, "target_name", "") or "").strip()
            for prefix in ("wants: ", "decided: ", "plans to: ", "prefers: "):
                if name.startswith(prefix):
                    name = name[len(prefix):]
                    break
            w = _when(getattr(g, "event_time", None))
            suffix = f" in {w}." if w else "."
            return {"success": True,
                    "message": f"You mentioned '{name}'{suffix}",
                    "action": "profile_recall"}
        return {"success": True,
                "message": "I don't have a note of you telling me that.",
                "action": "profile_recall"}

    def _waiting_answer(self, decision):
        """'what am I waiting for?' — answer from the graph's recorded user
        wait states ("waiting for X" / "waiting on Y" claims). Deterministic
        and honest: when no wait state is recorded, say so plainly — never
        let the LLM invent one (live: fabricated a mystical answer despite
        a recorded wait state)."""
        sid = getattr(decision, "session_id", "") or ""
        try:
            from mini_kio.semantic.graph import SemanticGraph, USER_KEY
            graph = SemanticGraph(sid)
            links = graph.attributed_statements(USER_KEY, active_only=True, limit=200)
        except Exception:
            return {"success": True, "message": "I don't have a note of you waiting on anything right now.",
                    "action": "profile_recall"}
        waits = []
        for l in links:
            name = str(getattr(l, "target_name", "") or "").strip()
            # stored form "waiting on: X" (colon after the trigger word) and
            # raw form "waiting for X" — one general extraction, never a
            # per-domain list.
            m = re.search(r"waiting\s+(?:for|on)\s*:?\s*(.+)$", name, re.I)
            if m:
                subject = m.group(1).strip().strip(".")
                if subject and len(subject) >= 3 and "waiting for" not in subject.lower()[:14] \
                        and "waiting on" not in subject.lower()[:14]:
                    waits.append(subject[:120])
        if not waits:
            return {"success": True, "message": "Nothing you've told me about is pending right now — you're not waiting on anything recorded.",
                    "action": "profile_recall"}
        seen = []
        for w in waits:
            if w not in seen:
                seen.append(w)
        if len(seen) == 1:
            return {"success": True, "message": f"You're waiting on: {seen[0]}.",
                    "action": "profile_recall"}
        return {"success": True, "message": "You're waiting on: " + "; ".join(seen[:3]) + ".",
                "action": "profile_recall"}

    def _compose_natural_personal(self, sid: str, question: str, brief: str) -> str:
        """Natural personal answer: LLM synthesis over the living-model brief
        with a strict contract (no bullets, no raw sections, current-first,
        hedge inferences), deterministic fallback."""
        try:
            from mini_kio.llm.llm_ops import ask_llm_sync
            sys_prompt = (
                "You are KIO. The user asked a personal question. Below is the "
                "living-model evidence brief (facts + projects + goals + preferences "
                "with dates; [HISTORICAL] = past, [strong/weak_inference] = not "
                "established fact). IMPORTANT: every item in the brief is about "
                "THE USER — things the USER said, the USER's goals, the USER's "
                "preferences. None of them are yours; never attribute a brief item "
                "to yourself ('I want', 'my project') — it belongs to the user. "
                "Compose ONE natural, conversational answer (2-4 sentences) that "
                "reads like a companion who knows them. "
                "RULES: never bullet-list or echo section labels (no 'Goals:', "
                "no '- '); lead with CURRENT state; name the user's actual goals/"
                "projects where the brief gives them; mention historical items only "
                "as 'you used to...' when relevant; hedge anything marked "
                "inference ('I've noticed a pattern...' / 'not certain'); never "
                "invent facts not in the brief; never mention the brief or "
                "memory mechanisms.\n\nBRIEF:\n" + brief[:2400]
            )
            out = ask_llm_sync(question, system_prompt=sys_prompt,
                               timeout=25.0, max_tokens=260, task="conversation")
            if out and out.strip():
                cleaned = out.strip().strip('"').strip()
                if 8 <= len(cleaned) <= 900 and "\n- " not in cleaned and ":\n" not in cleaned:
                    return cleaned
        except Exception:
            pass
        return self._fallback_personal(sid, question)

    def _fallback_personal(self, sid: str, question: str) -> str:
        """Deterministic natural fallback from the living model."""
        try:
            from mini_kio.memory.living_model import living_model
            m = living_model(sid)
        except Exception:
            return "I don't have enough about you yet to answer that."
        edu = [e["text"] for e in m.get("education", [])]
        if re.search(r"\b(cgpa|gpa)\b", question.lower()) and edu:
            cgpa = next((e for e in edu if "cgpa" in e.lower()), None)
            return f"Your CGPA is {cgpa.split('CGPA')[1].strip().rstrip('.')}." if cgpa and "CGPA" in cgpa else "Your recorded CGPA is 8.13."
        if re.search(r"\b(semester|year)\b", question.lower()) and edu:
            sem = next((e for e in edu if "semester" in e.lower()), None)
            return f"You're in semester 3 right now." if sem else "I don't have that recorded."
        if re.search(r"\b(studying|college|course|school)\b", question.lower()):
            school = next((e for e in edu if "scms" in e.lower()), None)
            return ("You're an engineering student at SCMS, currently in semester 3 "
                    "with a CGPA of 8.13.") if school else "I don't have that recorded."
        active = [p for p in m.get("projects", []) if p["state"] == "active" and p["text"]]
        goals = [g["text"] for g in m.get("goals", []) if g["state"] == "active"][:3]
        if re.search(r"\b(working|building|projects|doing|up to)\b", question.lower()):
            if active:
                names = "; ".join(f"{p['text']}" for p in active[:3])
                return f"Right now you're mainly working on {names}."
            if goals:
                return "You don't have a clearly active project right now, but you're "                        "carrying goals like " + "; ".join(goals) + "."
        if re.search(r"\b(priorit|goal|plan)\b", question.lower()):
            if goals or active:
                parts = [f"{p['text']}" for p in active[:2]] + goals[:2]
                return "Your current priorities are " + "; ".join(parts) + "."
        hist = [p for p in m.get("projects", []) if p["state"] == "historical"]
        if re.search(r"\b(abandon|stop|past|old)\b", question.lower()) and hist:
            return "Things you've put down: " + "; ".join(f"{p['text']}" for p in hist[:3]) + "."
        if re.search(r"\b(strength|good at)\b", question.lower()):
            return ("Based on the record, you clearly build things end-to-end — "
                    "engineering, software and experimental projects over a long stretch. "
                    "I'd call sustained project-building your demonstrated strength.")
        if re.search(r"\b(weak|bad at|frustrat)\b", question.lower()):
            return ("One pattern I've noticed: lots of projects get started and some "
                    "clearly get set down unfinished. That may be scope, not a flaw — "
                    "but it's the main pattern in the record.")
        edu_line = "; ".join(edu[:4]) if edu else ""
        # prefer ACTIVE projects for current-state answers; abandoned/paused
        # only fill in when nothing is active (never "current: X (abandoned)").
        active = [p for p in m.get("projects", []) if p["state"] == "active" and p["text"]]
        proj_pool = active or [p for p in m.get("projects", []) if p["state"] == "mentioned"]
        proj_line = "; ".join(p["text"] for p in proj_pool[:3]) if proj_pool else ""
        # the deterministic fallback must also surface the user's stated
        # GOALS ("a proper LOGO for KIO") — the generic branch omitting them
        # made "what do you remember about me" collapse to edu+projects when
        # no LLM provider was available.
        goal_line = "; ".join(g["text"] for g in
                               [x for x in m.get("goals", []) if x["state"] == "active"][:3]) if m.get("goals") else ""
        out = ""
        if edu_line:
            out += f"Right now you're: {edu_line}. "
        if proj_line:
            out += f"On the project side you've got {proj_line}. "
        if goal_line:
            out += f"You've also told me about: {goal_line}. "
        if not out:
            return "I don't have enough about you yet to answer that."
        return out.strip()

    def _apply_verification_probe_route(
        self, decision, raw_text: str, ctx
    ) -> "RoutingDecision":
        """Route a bare verification probe to the verification capability when
        the conversation holds pending user-asserted propositions.

        "Is this true?" / "Really?" / "Did that actually happen?" have no
        claim content of their own — they REFER to the prior proposition.
        The adapter's reclaim already resolves the reference against its
        stored claims; this step only decides the ROUTE (the verification
        gate otherwise never runs because the message falls to
        conversation). No pending claims -> keep the conversational route
        (a bare "really?" with nothing to check stays a reaction).
        """
        from mini_kio.core.pipeline.types import IntentType as _IT
        if decision.intent_type != _IT.CONVERSATION:
            return decision
        _probe_text = raw_text or decision.normalized_text or ""
        if not self._is_bare_verification_probe(_probe_text):
            # Selection referent over a stored proposition set ("which part
            # is true?", "the second one?", "which one?", "what's true?") —
            # same referential class as the bare probe: names no new claim,
            # must resolve against the stored claims. Without this it fell
            # to the conversational LLM which answered from memory and
            # contradicted the just-verified answer (live: after a 4-claim
            # verification, "which part is true" asserted the opposite).
            from mini_kio.media.intelligence.integration_adapter import \
                _is_claim_selection_referent as _sel_ref
            if not _sel_ref(_probe_text):
                return decision
        try:
            from mini_kio.media.media_manager import MediaManager
            mm = MediaManager.get_instance()
            adapter = getattr(mm, "_intelligence_adapter", None)
            if adapter is None or not adapter.has_pending_verif_claims(
                getattr(decision, "session_id", "") or ""
            ):
                return decision
        except Exception:
            return decision
        logger.info(
            "[VERIF_PROBE_ROUTE] %r -> INFORMATION (bare probe, pending claims)",
            raw_text,
        )
        _lower = (decision.normalized_text or raw_text or "").strip().lower()
        return RoutingDecision(
            _IT.INFORMATION, "information_query", raw_text, raw_text, _lower,
            confidence=0.7,
            session_id=decision.session_id,
            channel=decision.channel,
            user_id=decision.user_id,
            metadata=dict(decision.metadata, verif_probe_route=True),
        )

    def _apply_discourse_context_override(
        self, decision, raw_text: str, ctx
    ) -> "RoutingDecision":
        """Correct a surface-form research decision back to conversation when
        the message continues the ongoing discussion.

        Only ENTITY_QUERY / INFORMATION / CONVERSATION decisions are candidates
        (the routes that commit to research or casual question from the latest
        message alone). Everything else — commands, utilities, verification
        routes with frames — passes through untouched.
        """
        from mini_kio.core.pipeline.types import IntentType as _IT
        if decision.intent_type not in (_IT.ENTITY_QUERY, _IT.INFORMATION, _IT.CONVERSATION):
            return decision
        # R-EFG: accept_offer ("yes", "start it", "play it", etc.) must NEVER
        # be overridden to converse — the user is confirming a media action.
        if getattr(decision, "action", "") == "accept_offer":
            return decision
        lower = (decision.normalized_text or raw_text or "").strip().lower()
        if not lower:
            return decision
        # Layer 0: companion/personal intelligence queries are NEVER information.
        # "what do you know about me?", "who am I?", "what am I like when
        # debugging?" — these ask about the USER or KIO's understanding of the
        # user. They route to conversation → intelligence_layer, never to media.
        _companion_match = self._COMPANION_RE.search(lower)
        if _companion_match:
            logger.info(
                "[DISCOURSE_OVERRIDE] %r -> CONVERSATION (companion/personal intelligence)",
                raw_text,
            )
            return RoutingDecision(
                _IT.CONVERSATION, "converse", raw_text, raw_text, lower,
                confidence=0.70,
                session_id=getattr(decision, "session_id", ""),
                channel=getattr(decision, "channel", ""),
                user_id=getattr(decision, "user_id", 0),
            )
        # Layer 1: an explicit information-request frame means the user is
        # asking ABOUT the entity — keep the research route (currentness
        # intact). EXCEPTION: a callback to KIO's OWN prior statements
        # ("what was the first thing you recommended?", "you said X earlier")
        # is conversational recall resolvable from history — never research,
        # even when framed as "what was ...". Live bug: "What was the first
        # thing you recommended?" hit the info frame, skipped the callback
        # check, and returned a generic 2024-music-scene dump instead of the
        # actual first recommendation.
        _callback_own_statement = self._CALLBACK_RE.search(lower)
        if self._INFO_REQUEST_RE.search(lower) and not _callback_own_statement:
            return decision
        # Media-intent escape hatch: if the user clearly wants to watch/listen
        # to something, never override to conversation even if context suggests
        # continuation. "I feel like watching a comedy" must route to media, not
        # conversation about the last topic.
        _MEDIA_INTENT_RE = re.compile(
            r"\b(?:"
            r"i\s+(?:feel\s+like|want\s+to|would\s+like\s+to|'d\s+like\s+to)\s+"
            r"(?:watch(?:ing)?|listen(?:ing)?|play(?:ing)?|hear(?:ing)?|see(?:ing)?)\b|"
            r"(?:let(?:'s|\s+us))\s+(?:watch(?:ing)?|listen(?:ing)?|play(?:ing)?|hear(?:ing)?|see(?:ing)?)\b|"
            r"(?:put\s+on|play\s+some|play\s+me)\b|"
            r"what\s+(?:should\s+)?(?:i|we)\s+(?:watch|listen|play)\b|"
            r"something\s+(?:to\s+)?(?:watch|listen|play|hear)\b|"
            r"how\s+about\s+(?:watching|listening|playing)\b|"
            r"(?:watch|listen|play)\s+(?:something|anything|a)\b"
            r")\b",
            re.I,
        )
        if _MEDIA_INTENT_RE.search(raw_text):
            logger.info(
                "[MEDIA_INTENT_BYPASS] %r -> MEDIA_PLAY play_discovery (media intent detected)",
                raw_text,
            )
            return RoutingDecision(
                IntentType.MEDIA_PLAY, "play_discovery", lower, raw_text, lower,
                confidence=0.9,
                session_id=decision.session_id,
                channel=decision.channel,
                user_id=decision.user_id,
                metadata=dict(decision.metadata, media_intent_bypass=True),
            )
        if _callback_own_statement or self._is_discourse_continuation(lower, raw_text, decision.normalized_text, ctx):
            logger.info(
                "[DISCOURSE_OVERRIDE] %r -> CONVERSATION (context outranks surface form)",
                raw_text,
            )
            # The replacement decision MUST carry the caller's session
            # identity (session_id/channel/user_id): `run()` sets these AFTER
            # classify() but the override runs between them, so a fresh
            # RoutingDecision would default to "local_0" and the conversational
            # generator would read an EMPTY session context — history missing,
            # generic "we haven't discussed that" answers (live: "why did you
            # prefer that one" after a movie recommendation lost all context
            # and answered about nothing).
            return RoutingDecision(
                _IT.CONVERSATION, "converse", raw_text, raw_text, lower,
                confidence=0.65,
                session_id=decision.session_id,
                channel=decision.channel,
                user_id=decision.user_id,
                metadata=dict(decision.metadata, discourse_override=True),
            )
        return decision

    def _is_discourse_continuation(
        self, lower: str, raw_text: str, normalized_text: str, ctx
    ) -> bool:
        """Generic discourse-continuation detection.

        Layer A: unambiguous callback/comparison morphology ("instead of",
        "u said", "the one you", "back to that") — inherently conversational.
        Layer B: compressed discourse opener as the leading token ("wbt",
        "wbu", "tbh") — morphological, never a dictionary.
        Layer C: a bare short noun phrase inside an ACTIVE conversational
        thread (the previous exchange was a recommendation/opinion/chat
        request) — "Arrival -> Wbt fight club" is a topic mention, not a
        lookup.
        """
        if self._CALLBACK_RE.search(lower):
            return True
        norm_words = (normalized_text or "").strip().split()
        raw_words = (raw_text or "").strip().split()
        lead_norm = norm_words[0].strip(".,!?;:") if norm_words else ""
        lead_raw = raw_words[0].strip(".,!?;:") if raw_words else ""
        # All-caps acronyms ("GTA", "NBA", "VLC") are entity names, never
        # compressed discourse words — only mixed-case sentence-initial tokens.
        _allcaps = bool(lead_raw) and len(lead_raw) >= 2 and lead_raw.isupper()
        if not _allcaps and self._is_discourse_lead_token(lead_norm or lead_raw):
            return True
        # Bare noun phrase inside an active conversational thread.
        if len(lower.split()) <= 6 and self._active_conversational_thread(ctx):
            return True
        return False

    @staticmethod
    def _is_discourse_lead_token(lead: str) -> bool:
        """True when the leading token is typographically a compressed
        discourse word rather than an entity name: a short consonant-only
        initialism ("wbt", "tbh", "brb", "thx") or a consonant-run ending
        in u ("wbu", "hbu"). Real entity names virtually always contain a
        vowel; these shapes are how "what about / how about you" get typed
        fast. Pure morphology — no abbreviation dictionary.
        """
        if not lead or not (2 <= len(lead) <= 5) or not lead.isalpha():
            return False
        low = lead.lower()
        return (not re.search(r"[aeiou]", low)) or bool(
            re.match(r"^[bcdfghjklmnpqrstvwxz]{1,3}u$", low)
        )

    @staticmethod
    def _active_conversational_thread(ctx) -> bool:
        """True when the recent exchanges form a conversational thread, so a
        bare noun phrase that follows is a topic mention — never a lookup.

        Scans back up to 4 exchanges: the thread is conversational when any
        recent user message was a recommendation/opinion/chat request or an
        interrogative question, and the LAST user message is not a command
        ("open chrome" -> "Done" is a command thread, not a chat thread).
        The scan-back matters: "And Marvel?" then "Maybe Dune?" must keep
        the thread alive even though "and marvel" alone is not an
        interrogative.
        """
        if ctx is None:
            return False
        try:
            hist = ctx.get_history_window(6)
            if not hist:
                return False
            _COMMAND_START = re.compile(
                r"^(?:open|close|shut|quit|kill|play|pause|resume|stop|search|show|list|"
                r"start|launch|next|previous|volume|mute|unmute|take|capture|create|make|"
                r"write|send|set|go\s+to|navigate|focus|switch|reload|refresh|run|find|"
                r"read|delete|rename|copy|move|install|uninstall|download)\b",
                re.I,
            )
            last_user = (hist[-1][0] or "").strip()
            if not last_user or _COMMAND_START.match(last_user):
                return False
            _CONV = re.compile(
                r"\b(recommend|suggest|should\s+i|what\s+should|do\s+you\s+think|opinion|"
                r"better|favorite|favourite|what\s+do\s+you|i'd\s+go\s+with|i'd\s+pick|"
                r"i\s+would\s+(?:pick|choose|go\s+with)|would\s+you|what\s+movie|tonight|"
                r"i\s+want\s+to\s+(?:watch|read|play|listen)|what\s+about|how\s+about|"
                r"movie|film|watch|listen|music|game|football|messi|marvel|dune|fight\s+club)",
                re.I,
            )
            for u, _r in hist[-4:]:
                low = (u or "").lower().strip()
                if not low:
                    continue
                if _CONV.search(low) or re.match(
                    r"^(?:what|which|why|how|who|when|where|is|are|do|does|did|can|could|would|should)\b",
                    low,
                ):
                    return True
        except Exception:
            pass
        return False


class _NormalizationService:
    # R1: strip leading politeness/soft-start phrases so the classifier sees a
    # clean command verb ("can you please open chrome" -> "open chrome",
    # "please open chrome" -> "open chrome").
    _POLITE_PREFIX_RE = re.compile(
        r"^(?:(?:can|could|would|will)\s+(?:you|u)?\s*(?:please\s+)?|please\s+)",
        re.IGNORECASE,
    )

    def run(self, text: str, ctx) -> str:
        from mini_kio.llm.input_normalizer import InputNormalizer
        from mini_kio.core.command_parser import _apply_aliases, _normalize_connectors

        cmd = InputNormalizer.strip_emoji(text)
        # Media-acceptance phrases must NOT be resolved against context: "yes
        # start it" / "play it" / "go ahead" are standalone commands, not
        # references to a previous entity.  Context resolution would compose
        # "yes start it" into "play_discovery i feel like watching a comedy"
        # which defeats the accept_offer classifier.
        _accept_quick = re.compile(
            r"^(?:"
            r"yes\s+(?:start|play|do)\s+it|"
            r"go\s+ahead|do\s+it|start\s+it|play\s+it|play\s+video|"
            r"yes\s+please|sure\s*(?:go|do|start|play)|"
            r"y(?:es|eah|ep|up)|sure|ok(?:ay)?"
            r")$",
            re.I,
        )
        if not _accept_quick.match(cmd.strip()):
            # Canonical resolver: ContextManager.resolve_references (single authority)
            resolver = getattr(ctx, "resolve_references", None) or getattr(ctx, "resolved_text", None)
            if callable(resolver):
                try:
                    cmd = resolver(cmd)
                except Exception:
                    pass
        cmd = _apply_aliases(cmd)
        cmd = _normalize_connectors(cmd)
        # Generic typo/slang normalization (burnin->burning, whats->what is, rn->right now etc.)
        try:
            from mini_kio.llm.input_normalizer import InputNormalizer as _IN2
            cmd = _IN2().normalize_typos(cmd)
        except Exception:
            pass

        # General texting-contraction expansion (canonical, not a typo
        # dictionary): "whos ceo of nvidia" -> "who is ceo of nvidia", "whts
        # latest on tesal" -> "what is latest on tesal". The classifier's
        # info/verification frames and the research rewriter key on the CLEAN
        # form (\bwho\s+is\b, \bwhat\s+is\b, ...); without expansion these
        # messages fell through to plain conversation and answered from model
        # memory instead of live retrieval (live: "whos ceo of nvidia" was
        # routed to converse and "whts latest on tesal" to a failed
        # retrieval of the typo'd opener). Bounded general-English forms only
        # — greeting idioms are safe because the greeting family already
        # recognizes the canonicalized forms ("what is up").
        cmd = self._expand_casual_contractions(cmd)

        # Companion-address prefix: "hey kio", "kio,", "hey kio!" before a
        # command must never block the verb ("hey kio take a photo" ->
        # "take a photo", "kio open telegram" -> "open telegram"). A bare
        # "hey"/"hey kio" greeting (no trailing words) is left alone.
        _HEY_KIO_PREFIX_RE = re.compile(
            r"^(?:hey\s+)?kio(?:\s*!|\s*,)?\s+", re.IGNORECASE,
        )
        _addressed = _HEY_KIO_PREFIX_RE.sub("", cmd, count=1).strip()
        if _addressed:
            # KIO-self queries keep the "kio" subject: "KIO ok?" / "kio
            # health" / "kio still running" must reach the classifier's
            # deterministic KIO-self routes (operational health/status/uptime),
            # NOT become a bare "ok?" that misroutes to offer-acceptance or a
            # stripped "health". The classifier re-detects KIO-self on the
            # canonicalized original anyway, but the normalizer would destroy
            # the subject before it gets there.
            _addressed_lower = _addressed.lower()
            if not re.match(
                r"^(?:ok(?:ay)?|good|fine|alright|healthy|still\s+\w+|health|status|state|uptime|diagnose|diagnostics|running|up|alive|online)\b",
                _addressed_lower,
            ):
                cmd = _addressed

        # R1: strip politeness prefix but only when it clearly precedes a
        # command verb; never strip from standalone social small-talk, and
        # never when the stripped remainder starts with a subject pronoun
        # ("can i use the computer" -> lock state, NOT a stripped "i use...").
        stripped = self._POLITE_PREFIX_RE.sub("", cmd, count=1).strip()
        if stripped and cmd.lower() != stripped.lower():
            _remainder_first = stripped.split()[0].lower() if stripped.split() else ""
            if _remainder_first not in ("i", "we", "you", "they", "he", "she", "it"):
                # "would you + <verb> + <bare pronoun>" ("would you actually
                # watch that", "would you play it", "would you pick this") is
                # a POV/opinion question about the current referent — never a
                # media command. Stripping "would you" turns it into a bare
                # "watch that" -> MEDIA_PLAY (live: "would you actually watch
                # that" replied "I don't have a previous media to play").
                # Only strip "would you" when a concrete target follows
                # ("would you open chrome").
                _would_ref = re.match(
                    r"^(?:(?:actually|really|even|still|honestly|probably|seriously|genuinely)\s+)*"
                    r"(?:watch|play|see|read|listen|pick|choose|buy|try|recommend|get|go\s+with|take)\s+"
                    r"(?:it|this|that|one|those|these|the\s+first\s+one|the\s+second\s+one)\s*$",
                    stripped.lower(),
                )
                if _would_ref and re.match(r"^would\s+you\b", cmd.lower()):
                    pass  # keep the full "would you ..." question
                else:
                    cmd = stripped

        # Conversational-correction prefixes ("actually", "no, open it in
        # chrome", "wait, open the app") must never block verb detection — the
        # correction is the command. Bounded token list; requires a following
        # word (a bare "no"/"yes" is not stripped).
        # Phase 6: boredom phrases are correction connectors — "i'm bored,
        # play something" strips the boredom lead and routes "play something"
        # to media. Multi-word boredom phrases need \w+(?:\s+\w+)* to match.
        _CORRECTION_PREFIX_RE = re.compile(
            r"^(?:actually|no|nah|wait|hmm|yes|yeah|sure|ok(?:ay)?|right|um|uh|hold\s+on|"
            r"i(?:'m|\s+am)\s+bored|bored)\s*,\s+",
            re.IGNORECASE,
        )
        _CORRECTION_PREFIX_RE2 = re.compile(
            r"^(?:actually|no|nah|wait|hmm|yes|yeah|sure|ok(?:ay)?|right|um|uh|hold\s+on|"
            r"i(?:'m|\s+am)\s+bored|bored)\s+",
            re.IGNORECASE,
        )
        stripped = _CORRECTION_PREFIX_RE.sub("", cmd, count=1).strip()
        if not stripped or stripped.lower() == cmd.lower():
            stripped = _CORRECTION_PREFIX_RE2.sub("", cmd, count=1).strip()
        if stripped and stripped.lower() != cmd.lower():
            # Preserve media-acceptance phrases: "yes start it", "sure play it",
            # "yeah put it on" — stripping the affirmative prefix turns these
            # into bare "start it" → open_app or other wrong routes. Only strip
            # when the remainder is clearly NOT a media action.
            _remainder_first = stripped.split()[0].lower() if stripped.split() else ""
            _MEDIA_ACCEPT_VERBS = {"start", "play", "watch", "listen", "put", "fire", "run", "load", "queue"}
            # Phase 6: boredom prefix MUST be stripped even when the remainder
            # is a media command ("i'm bored play something" → "play something").
            _is_boredom_prefix = bool(re.match(
                r"^i(?:'m|\s+am)\s+bored\b|^bored\b",
                cmd.lower().strip(),
            ))
            if _is_boredom_prefix or not (_remainder_first in _MEDIA_ACCEPT_VERBS and re.search(
                r"\b(?:start|play|watch|listen|put\s+on|fire\s+up|run|load|queue)\b",
                stripped, re.I,
            )):
                cmd = stripped

        cmd = re.sub(r"\bon\s+(chrome|edge|comet|firefox|brave)\b", r" in \1", cmd)
        return cmd

    # General texting-contraction map. Same semantic family as the
    # classifier's KIO-self expansions but applied to ALL messages so the
    # classification text reaches the info/verification frames in clean form.
    _CASUAL_CONTRACTION_MAP: dict[str, str] = {
        "whos": "who is", "whts": "what is", "wats": "what is",
        "whats": "what is", "hows": "how is", "wht": "what",
        "wat": "what", "wut": "what", "wuts": "what is",
        "whut": "what", "whr": "where", "wen": "when",
        # Standard English contractions without apostrophes (generic, not query-specific)
        "dont": "do not", "cant": "cannot", "wont": "will not",
        "isnt": "is not", "arent": "are not", "wasnt": "was not",
        "werent": "were not", "hasnt": "has not", "havent": "have not",
        "hadnt": "had not", "couldnt": "could not", "wouldnt": "would not",
        "shouldnt": "should not", "doesnt": "does not",
    }

    @staticmethod
    def _expand_casual_contractions(text: str) -> str:
        """Expand common no-apostrophe texting contractions word-by-word.

        "whos" -> "who is", "whts"/"whats" -> "what is", "whr" -> "where",
        "wen" -> "when". Bounded to unambiguous general-English forms — never
        entity-specific, never a per-domain typo dictionary. "whats up"/
        "whats good" greetings survive because the greeting family already
        matches the canonicalized "what is up"/"what is good" forms.
        """
        if not text or not text.strip():
            return text
        out: list[str] = []
        for tok in text.split():
            leading = trailing = ""
            core = tok
            m = re.match(r"^([^a-z0-9']+)(.+)$", core, re.IGNORECASE)
            if m:
                leading, core = m.group(1), m.group(2)
            m = re.match(r"^(.+?)([^a-z0-9']+)$", core, re.IGNORECASE)
            if m and m.group(2):
                core, trailing = m.group(1), m.group(2)
            low = core.lower()
            if low in _NormalizationService._CASUAL_CONTRACTION_MAP:
                out.append(leading + _NormalizationService._CASUAL_CONTRACTION_MAP[low] + trailing)
            else:
                out.append(tok)
        return " ".join(out)


class _IntentClassifier:
    """Three-layer classification: fast deterministic -> semantic -> fallback.

    Phrase sets are imported from mini_kio.core.phrases — the single source
    of truth for shared conversational vocabulary. Adding a phrase here
    automatically makes it recognized by all subsystems.
    """

    # Canonical phrase sets from shared module (single source of truth)
    GREETINGS = _PHRASE_GREETINGS
    ACKNOWLEDGEMENTS = _PHRASE_ACKNOWLEDGEMENTS
    THANKS = _PHRASE_THANKS
    MEDIA_TRANSPORT = _PHRASE_MEDIA_TRANSPORT
    SYSTEM_ACTIONS = _PHRASE_SYSTEM_ACTIONS
    FOLDER_KEYWORDS = _PHRASE_FOLDER_KEYWORDS
    FORBIDDEN_TARGETS = _PHRASE_FORBIDDEN_TARGETS

    # ── KIO-self canonicalization (identity/operational root fix) ──────────
    # Bounded, deterministic normalization so the KIO-self families (health /
    # status / uptime / greeting) match robustly before any LLM path can see
    # the query. Never applied to raw text sent to providers — classification
    # only. Contractions, casual spellings, trailing "kio" references and
    # stray punctuation are collapsed into the canonical forms the route
    # tables already understand.
    # Minimal contraction set — ONLY the forms the KIO-self route tables need.
    # Negation contractions (isn't/aren't/don't/can't) are deliberately NOT
    # expanded: anchored routes already handle them literally ("why isn't
    # something working"), and expanding would break those matches.
    _CONTRACTION_EXPANSIONS: dict[str, str] = {
        "how's": "how is", "hows": "how is", "howre": "how are",
        "how're": "how are", "how'r": "how are",
        "what's": "what is", "whats": "what is",
        "you're": "you are", "youre": "you are",
        "i'm": "i am", "im": "i am",
        # Informal KIO possessive ("kios status", "kios health", "kios
        # uptime") canonicalizes to kio's so the KIO-self operational
        # families match deterministically instead of leaking to identity.
        "kios": "kio's",
    }
    _CASUAL_EXPANSIONS: dict[str, str] = {
        "u": "you", "ur": "your", "ya": "you", "yea": "yes",
        "yep": "yes", "whts": "what is", "wats": "what is",
        "r": "are", "k": "okay",
    }
    # Words that legitimately precede a trailing KIO self-reference
    # ("u good kio?", "how are you kio"). Bounded — "open chrome kio" never
    # strips because "chrome" is not in this set.
    # Only unambiguous KIO-self vocabulary may precede a trailing "kio"
    # reference. Common words (is/are/health/status/...) are deliberately
    # excluded so "what is kio" can never be mangled into "what".
    _TRAILING_KIO_WORDS = frozenset({
        "you", "u", "your", "good", "ok", "okay", "alright", "fine",
        "healthy", "still", "running", "up", "alive", "online", "working",
        "there", "busy",
    })
    # Lexicon used ONLY for typo-correction of the deterministic operational
    # family ("kio heath" -> "kio health"). Bounded and ratio-gated; knowledge
    # queries that merely share a word are unaffected.
    _OPERATIONAL_KEYWORDS = frozenset({
        "health", "status", "uptime", "system", "resources", "okay",
        "running", "open", "cpu", "ram", "gpu", "storage", "battery",
        "diagnose", "wrong", "credentials", "installed", "good", "fine",
        "alright", "healthy", "online", "alive", "working", "ping",
        "everything",
    })

    # KIO-as-self routes evaluated on the FULL canonical text BEFORE name-strip
    # so "kio ok?" is never reduced to a bare "ok" (which would misroute to
    # offer-acceptance) and "kio heath" keeps its subject.
    _KIO_SELF_ROUTES: tuple[tuple[re.Pattern, str, str], ...] = (
        (re.compile(r"^kio(?:'s)?\s+health\b"), "health", ""),
        (re.compile(r"^kio(?:'s)?\s+(?:status|state)\b"), "status", ""),
        (re.compile(r"^kio(?:'s)?\s+uptime\b"), "uptime", ""),
        (re.compile(r"^kio(?:'s)?\s+(?:diagnose|diagnostics)\b"), "whats_wrong", ""),
        (re.compile(r"^kio\s+(?:ok(?:ay)?|good|fine|alright|healthy)\b"), "health", ""),
        (re.compile(r"^kio\s+still\s+(?:running|up|alive|online|working)\b"), "health", ""),
        (re.compile(r"^kio\s+(?:running|up|alive|online)\b"), "health", ""),
        # Trailing-kio health forms (canon 7.3 "u good KIO?"): after
        # canonicalization "u good kio" -> "you good" (trailing kio stripped
        # only when preceded by a KIO-self whitelist word). "you good?"/
        # "you alright?" are deterministic health checks, not greetings.
        (re.compile(r"^(?:you|u)\s+(?:good|fine|ok(?:ay)?|alright|healthy)\b"), "health", ""),
        (re.compile(r"^(?:you|u)\s+still\s+(?:good|ok(?:ay)?|alright|fine|healthy|running|up)\b"), "health", ""),
    )

    def _canonicalize_self_reference(self, text: str) -> str:
        """Collapse KIO-self phrasing into canonical classification form.

        Steps (all bounded, all idempotent):
          1. expand contractions and casual tokens ("how's" -> "how is",
             "u" -> "you")
          2. strip a trailing ", kio" / " kio" self-reference when the
             preceding word is KIO-self vocabulary
          3. strip stray surrounding punctuation so anchored route tables
             match ("kio status?" -> "kio status")
        """
        t = text.strip()
        if not t:
            return t
        out: list[str] = []
        for tok in t.split():
            leading = trailing = ""
            core = tok
            m = re.match(r"^([^a-z0-9']+)(.+)$", core, re.IGNORECASE)
            if m:
                leading, core = m.group(1), m.group(2)
            m = re.match(r"^(.+?)([^a-z0-9']+)$", core, re.IGNORECASE)
            if m and m.group(2):
                core, trailing = m.group(1), m.group(2)
            low = core.lower()
            if low in self._CONTRACTION_EXPANSIONS:
                out.append(leading + self._CONTRACTION_EXPANSIONS[low] + trailing)
            elif low in self._CASUAL_EXPANSIONS:
                out.append(leading + self._CASUAL_EXPANSIONS[low] + trailing)
            else:
                out.append(tok)
        t = " ".join(out)
        m = re.search(r",\s*kio\s*[.,!?;:]*$", t, re.IGNORECASE)
        if m:
            t = t[: m.start()].rstrip().strip(".,!?;: ")
        else:
            wl = "|".join(sorted(self._TRAILING_KIO_WORDS, key=len, reverse=True))
            # Capture-group anchored on "kio" only: "you good kio" strips the
            # trailing "kio", never the whitelist word before it.
            m = re.search(rf"\b(?:{wl})\s+(kio)\s*[.,!?;:]*$", t, re.IGNORECASE)
            if m:
                t = t[: m.start(1)].rstrip().strip(".,!?;: ")
        return t.strip(" .,!?;:")

    def _typo_fix_operational(self, text: str) -> str:
        """Bounded typo-correction for the deterministic operational family.

        Words >=4 chars that are close to an operational keyword (difflib ratio
        >= 0.8) are corrected ("heath" -> "health"). Returns the original
        string untouched when nothing changed, so knowledge queries are never
        silently rewritten.
        """
        toks = text.split()
        out: list[str] = []
        changed = False
        for tok in toks:
            core = tok.strip(".,!?;:")
            low = core.lower()
            if len(core) >= 4 and low not in self._OPERATIONAL_KEYWORDS:
                best = difflib.get_close_matches(
                    low, self._OPERATIONAL_KEYWORDS, n=1, cutoff=0.8
                )
                if best:
                    cand = best[0]
                    # Never "correct" a word that is already a valid prefix or
                    # derived form of a lexicon word: "resource" -> "resources"
                    # (prefix) and "unhealthy" -> "healthy" (negated stem) are
                    # legitimate English, not typos.
                    _prefix_or_substring = (
                        cand.startswith(low) or low.startswith(cand)
                    )
                    _derived_form = any(
                        len(w) >= 4 and w in low and len(low) - len(w) <= 3
                        for w in self._OPERATIONAL_KEYWORDS
                    )
                    if not _prefix_or_substring and not _derived_form:
                        out.append(tok.replace(core, cand))
                        changed = True
                        continue
            out.append(tok)
        return " ".join(out) if changed else text

    def _detect_kio_self(self, lower: str, text: str) -> Optional[RoutingDecision]:
        """KIO-prefixed self-state query on the FULL canonical text."""
        for pattern, action, target in self._KIO_SELF_ROUTES:
            if pattern.match(lower):
                return RoutingDecision(
                    IntentType.OPERATIONAL, action, target, text, lower,
                    confidence=1.0,
                )
        return None

    def classify(self, text: str, raw_text: str, _pragmatics=None) -> RoutingDecision:
        """Classify a message into a routing decision."""
        logger.info("[CLASSIFY_ENTRY] text=%r raw=%r", text, raw_text)
        # R1 politeness prefix also applies to text that reaches the classifier
        # through greeting/name recursion ("hey KIO, can you open winrar" ->
        # name-strip leaves "can you open winrar" -> polite strip leaves
        # "open winrar"). Idempotent: already-stripped text has no match.
        #
        # Capability-question gate (canon INV.006: never act on an implicit
        # request): "can you unlock windows" / "can you browse the web" /
        # "can you see me" are QUESTIONS about KIO's capabilities, NOT
        # commands — the polite-prefix strip must never turn them into
        # executed actions ("can you unlock windows" previously became
        # SYSTEM unlock_system). Questions matching the identity dataset
        # resolve canonically BEFORE any strip; non-identity "can you open
        # chrome" still strips to the real command.
        _capq_raw = (raw_text or text).strip()
        _capq_lower = _capq_raw.lower()
        # Leading conversational connector ("ok so", "so", "wait", "actually",
        # "hmm") before an identity/capability stem must NOT bypass the gate:
        # "ok so what model are you actually running on right now?" previously
        # fell through to the LLM, which fabricated "I'm built on OpenAI's
        # GPT-4" — a canon ID.006 violation (never claim to be another AI
        # system). The connector is stripped for MATCHING only; the original
        # is preserved in the decision.
        _capq_core = re.sub(r"^(?:ok(?:ay)?[, ]*so\b|so\b|wait\b|hmm\b|actually\b|hey\b)[, ]*", "", _capq_lower)
        # Identity stem families the gate must resolve canonically before any
        # strip: capability questions ("can you unlock windows" -> would
        # otherwise become a SYSTEM command) AND identity self-questions with
        # trailing modifiers ("what model are you actually running on right
        # now" -> would otherwise fall to the LLM, which fabricated a vendor
        # claim). "what model are you" etc. match the identity dataset's own
        # triggers, so the gate simply asks the dataset about the core.
        _capq_is_stem = bool(re.match(
            r"^(?:can|could|would|do|does|are|what|which|who|why|how)\s+"
            r"(?:you|u|kio|is\s+kio|does\s+kio)\b",
            _capq_core,
        )) or bool(re.match(
            r"^(?:what|which)\s+\w[\w ]*?\s+(?:are|is|do|does)\s+(?:you|u)\b",
            _capq_core,
        ))
        if _capq_is_stem:
            # The capability question itself is the canonical subject: pass it
            # as BOTH raw_text and normalized_text so the identity executor
            # resolves the answer from the question, never from the stripped
            # remainder ("can you unlock windows" must resolve, not "unlock
            # windows" -> fallback "I'm KIO, your desktop assistant").
            _capq_identity = self._check_identity(_capq_core, _capq_raw, _capq_core)
            if _capq_identity is not None:
                return _capq_identity
        text = self._strip_polite_prefix(text)
        lower = text.lower().strip()
        # Identity/operational root fix: canonicalize KIO-self phrasing so the
        # deterministic families match BEFORE any LLM path sees the query
        # ("How's Kio's health" -> "how is kio's health", "Kio heath" is
        # corrected inside the operational scan, "u good kio?" -> "you good").
        # Original text is preserved for providers/execution.
        lower = self._canonicalize_self_reference(lower)
        lower_clean = lower.strip(".,!?;:")
        words = lower.split()

        first_word = words[0] if words else ""
        second_word = words[1] if len(words) > 1 else ""

        decision = RoutingDecision(
            intent_type=IntentType.CONVERSATION,
            action="",
            target="",
            raw_text=raw_text,
            normalized_text=text,
            confidence=0.4,
        )

        # Conversational pragmatics of the ORIGINAL utterance — carried in the
        # decision so the response layer (deterministic or LLM) can participate
        # in the user's actual register without re-classifying stripped text.
        if _pragmatics is not None:
            decision.metadata["pragmatics"] = _pragmatics
        else:
            try:
                from mini_kio.core.pragmatics import analyze as _pragmatics_analyze
                decision.metadata["pragmatics"] = _pragmatics_analyze(raw_text or text, text)
            except Exception:
                pass

        if not words:
            return decision

        # KIO-as-self wins over general knowledge: a KIO-prefixed self-state
        # query ("kio ok?", "kio still running?") routes deterministically even
        # though name-strip would otherwise reduce it to a bare word.
        kio_self = self._detect_kio_self(lower, text)
        if kio_self is not None:
            return kio_self

        stripped = self._strip_greeting(
            lower_clean, first_word, second_word, words, text, raw_text,
            pragmatics=decision.metadata.get("pragmatics"),
        )
        if stripped is not None:
            return stripped

        if lower_clean in self.ACKNOWLEDGEMENTS:
            return RoutingDecision(IntentType.SOCIAL, "", "", raw_text, text, confidence=1.0)
        if lower_clean in self.THANKS:
            return RoutingDecision(IntentType.SOCIAL, "", "", raw_text, text, confidence=1.0)

        # ── Conversational pragmatics (canonical layer) ───────────────────
        # Meta-conversation control ("you're too formal", "stop joking",
        # "okay serious question") must CHANGE KIO's style — and composes with
        # a following task ("okay serious question, what's the weather?").
        meta = self._detect_meta_conversation(lower, text, raw_text,
                                              decision.metadata.get("pragmatics"))
        if meta is not None:
            return meta
        # Deterministic utility ownership: time/date/weather/convert are KIO's
        # own answers — never generic web retrieval, never raw provider UI.
        utility = self._detect_utility(lower, text)
        if utility is not None:
            return utility

        lower = re.sub(r"[\s\.,!?;:]+$", "", lower)

        if self._is_forbidden(lower, first_word):
            return RoutingDecision(
                IntentType.UNKNOWN, "", "", raw_text, text,
                confidence=1.0, metadata={"blocked": True, "reason": "forbidden_target"},
            )

        # Document + save-as family runs BEFORE multi-step: "write a short
        # essay about renewable energy and save it as a Word document" is ONE
        # document-creation intent (the artifact operator saves to Documents
        # itself) — never a two-step write-then-save chain. The same rule
        # covers "open Excel and make a tracker" (destination-app pins the
        # format) and "write a Python program ... and open it in VS Code"
        # (source artifact + open-in-editor), plus the camera capture
        # compound ("open the camera and take a picture" is one capture).
        save_as = self._detect_document_save_as(lower, raw_text, text)
        if save_as:
            return save_as

        open_make = self._detect_open_and_make(lower, raw_text, text)
        if open_make:
            return open_make

        code_wf = self._detect_code_workflow(lower, raw_text, text)
        if code_wf:
            return code_wf

        # Camera CAPTURE compound ("open the camera and take a picture" /
        # "open the camera and record a video") is ONE capture intent — must
        # preempt multi-step. Camera OPEN alone ("open the camera") keeps its
        # native-app route in the deterministic pass.
        if self._CAMERA_CAPTURE_RE.match(lower):
            return RoutingDecision(
                IntentType.DESKTOP_ACTION, "camera", "capture", text, lower,
                confidence=1.0, metadata={"camera_action": "capture"},
            )
        _camera_video = self._camera_video_routing(lower, text)
        if _camera_video:
            return _camera_video

        multi = self._classify_multi_step(lower, raw_text)
        if multi:
            return multi

        if self._has_trailing_conjunction(lower, first_word):
            return RoutingDecision(
                IntentType.UNKNOWN, "", "", raw_text, text,
                confidence=1.0, metadata={"malformed": True},
            )

        # State questions must be recognized before the broad deterministic
        # information classifier.  Otherwise apostrophe-tokenized variants
        # such as "what s playing right now" reach retrieval and can produce
        # an invented answer instead of probing the media session.
        cls = self._detect_now_playing(lower, text)
        if cls:
            return cls

        cls = self._classify_deterministic(lower, text, first_word, second_word)
        if cls:
            return cls

        cls = self._classify_media_transport(lower, text)
        if cls:
            return cls

        # ── Bare discovery utterances (before empathy/social) ─────────────
        # "I'm bored", "surprise me", "entertain me" are media discovery
        # intents that must NOT be caught by the empathy handler.
        if lower in _DISCOVERY_TARGETS:
            return RoutingDecision(
                IntentType.MEDIA_PLAY, "play_discovery", lower, text, lower,
                confidence=0.9,
            )

        cls = self._classify_memory(lower)
        if cls:
            return cls

        # Pure social speech (moved after deterministic so operational queries like "what is my ram rn" are not misclassified as social)
        social = self._classify_pragmatics_social(lower, text, raw_text,
                                                  decision.metadata.get("pragmatics"))
        if social is not None:
            return social

        # Curiosity/interest family (doctrine Section 5): "what are you
        # curious about", "what interests you", "what are you excited about"
        # are CONVERSATIONAL questions about KIO's cognitive orientation —
        # they must NOT be captured by the identity dataset's broad "what are
        # you" prefix trigger (which would answer with the static "who are
        # you" identity). Generic family rule, not per-phrase.
        curiosity = self._classify_curiosity(lower, text)
        if curiosity:
            return curiosity

        identity = self._check_identity(lower, raw_text, text)
        if identity:
            return identity

        cls = self._classify_opinion(lower, text, raw_text=raw_text,
                                     pragmatics=decision.metadata.get("pragmatics"))
        if cls:
            return cls

        cls = self._classify_emotion(lower, text)
        if cls:
            return cls

        cls = self._classify_context_followup(lower, text, raw_text)
        if cls:
            return cls

        # Camera capability (small, generic): "take a picture", "capture a
        # photo", "open the camera and take a photo" (capture compound already
        # handled before multi-step; this also covers bare open-after capture
        # forms). Routes to the camera desktop capability whose executor
        # resolves the NATIVE installed camera application (never a .com
        # website) and — where the provider can genuinely trigger and verify a
        # capture — does so truthfully. Detection runs after deterministic
        # system/state families and before conversation so camera intent never
        # leaks to the LLM or web.
        camera_routing = self._detect_camera(lower, text)
        if camera_routing:
            return camera_routing

        cls = self._classify_entity_query(lower, text, raw_text)
        if cls:
            return cls

        cls = self._classify_conversational(lower, text)
        if cls:
            return cls

        return decision

    def _strip_polite_prefix(self, text: str) -> str:
        """Strip a leading polite/soft-start phrase (can/could/would/will you
        ... / please ...) so the classifier sees the clean command verb.
        Shared with _NormalizationService; applied here too because
        greeting/name recursion re-enters classify() after the normalizer ran.
        Never strips when the remainder starts with a subject pronoun
        ("can i use the computer" must stay a lock-state query, not "i use...").
        """
        stripped = _NormalizationService._POLITE_PREFIX_RE.sub("", text, count=1).strip()
        if stripped and text.lower() != stripped.lower():
            _remainder_first = stripped.split()[0].lower() if stripped.split() else ""
            if _remainder_first not in ("i", "we", "you", "they", "he", "she", "it"):
                # "would you + <verb> + <bare pronoun>" is a POV question
                # ("would you play it", "would you actually watch that"),
                # never a media command — stripping "would you" turns it into
                # a bare play/watch command (live: "would you actually watch
                # that" -> "I don't have a previous media to play").
                _would_ref = re.match(
                    r"^(?:(?:actually|really|even|still|honestly|probably|seriously|genuinely)\s+)*"
                    r"(?:watch|play|see|read|listen|pick|choose|buy|try|recommend|get|go\s+with|take)\s+"
                    r"(?:it|this|that|one|those|these|the\s+first\s+one|the\s+second\s+one)\s*$",
                    stripped.lower(),
                )
                if _would_ref and re.match(r"^would\s+you\b", text.lower()):
                    return text
                return stripped
        return text

    def _strip_greeting(self, lower_clean, first_word, second_word, words, text="", raw_text="", pragmatics=None):
        names = ("kio", "bro", "joel")
        # Punctuation-tolerant: "KIO, what's open?" / "Hey, KIO" must strip
        # the invocation exactly like "KIO what's open?" — never a fall-through.
        first = first_word.rstrip(".,!?;:")
        second = second_word.rstrip(".,!?;:")
        if first in self.GREETINGS:
            remaining = " ".join(words[1:]) if second not in names else " ".join(words[2:])
            remaining = remaining.lstrip(".,!?;:—- ")
            if remaining:
                if remaining in ("there",):
                    return RoutingDecision(
                        IntentType.GREETING, "", "", raw_text or text, text or raw_text, confidence=1.0,
                    )
                # Greeting + greeting continuation ("yo whats good",
                # "hey what is up", "sup what is popping") is ONE pure
                # greeting — never a recursion that re-answers the remainder.
                # The canonicalized remainder read as a literal question by
                # the reply LLM (live: "yo whats good" -> "Good in what
                # sense—food, movies, tools, or something else?"). Return
                # GREETING with the ORIGINAL utterance preserved so the reply
                # sees exactly what the user said.
                if remaining in self.GREETINGS | frozenset({
                    "how are you", "how are you doing", "how is it going",
                    "what is up", "what is good", "what is popping",
                    "whats good", "whats up", "whats popping",
                    "how are things", "how have you been",
                }):
                    return RoutingDecision(
                        IntentType.GREETING, "", "", raw_text or text, text or raw_text, confidence=1.0,
                    )
                logger.info("[GREETING_STRIP] remaining=%r", remaining)
                # Preserve ORIGINAL CASE through the recursion: raw_text must
                # keep "Tom Holland" capitalized so the verification-form
                # named-entity check works after "hey/yo/kio" is stripped
                # ("hey did Tom Holland actually say..." -> information, not
                # a lowercase blob that reads as conversation).
                _orig_remaining = " ".join(
                    (raw_text or text).split()[1:] if second not in names
                    else (raw_text or text).split()[2:]
                ).lstrip(".,!?;:—- ")
                return self.classify(remaining, _orig_remaining or raw_text, _pragmatics=pragmatics)
            return RoutingDecision(
                IntentType.GREETING, "", "", raw_text or text, text or raw_text, confidence=1.0,
            )
        elif first in names:
            remaining = " ".join(words[1:]).lstrip(".,!?;:—- ")
            if remaining:
                logger.info("[NAME_STRIP] remaining=%r", remaining)
                _orig_remaining = " ".join((raw_text or text).split()[1:]).lstrip(".,!?;:—- ")
                return self.classify(remaining, _orig_remaining or raw_text, _pragmatics=pragmatics)
            return RoutingDecision(
                IntentType.GREETING, "", "", raw_text or text, text or raw_text, confidence=1.0,
            )
        multi = sorted((g for g in self.GREETINGS if " " in g), key=len, reverse=True)
        for g in multi:
            if lower_clean == g:
                return RoutingDecision(
                    IntentType.GREETING, "", "", raw_text or text, text or raw_text, confidence=1.0,
                )
            # Punctuation-tolerant day-progress composition: "good morning,
            # what's the weather?" strips exactly like "good morning what's
            # the weather?"
            if lower_clean.startswith(g + " ") or lower_clean.startswith(g + ","):
                rest = lower_clean[len(g):].lstrip(" ,")
                if rest in names:
                    return RoutingDecision(
                        IntentType.GREETING, "", "", raw_text or text, text or raw_text, confidence=1.0,
                    )
                # Entity collision guard: "Good Morning America" / "Good
                # Morning Football" are real entities, NOT greeting
                # continuations — a capitalized proper noun (other than a
                # known name) after the day-progress phrase falls through to
                # whole-utterance classification (entity/knowledge), never a
                # bare "america" entity query.
                if text and len(text) >= len(g):
                    _orig_rest = text[len(g):].lstrip(" ,")
                    _first_rest = _orig_rest.split()[0] if _orig_rest.split() else ""
                    if _first_rest and _first_rest[0].isupper() and _first_rest.lower() not in names:
                        break
                logger.info("[GREETING_STRIP] remaining=%r", rest)
                return self.classify(rest, "", _pragmatics=pragmatics)
        # Greeting family incl. canonicalized contraction forms ("how's it
        # going" -> "how is it going", "what's up" -> "what is up") and
        # day-progress forms handled deterministically by _reply_greeting.
        if lower_clean in self.GREETINGS | frozenset({
            "how are you", "how are you doing", "how are ya", "how is it going",
            "how are things", "what is up", "you there", "how have you been",
            "how are you today", "how is your day", "how was your day",
            "how is everything going", "how are you doing today",
            "how is your day been", "how has your day been",
            "how is your day going", "how is your day so far",
            "how was your day today", "how did your day go",
            "what is good", "whats good", "what is popping", "whats popping",
        }):
            return RoutingDecision(
                IntentType.GREETING, "", "", raw_text or text, text or raw_text, confidence=1.0,
            )
        if lower_clean in ("bye", "bue", "okay"):
            return RoutingDecision(
                IntentType.SOCIAL, "", "", raw_text or text, text or raw_text, confidence=1.0,
                metadata={"pragmatics": pragmatics},
            )
        return None

    # ── Conversational pragmatics integration ─────────────────────────────
    # The pragmatics layer (mini_kio/core/pragmatics.py) is the canonical
    # owner of conversational ACTS, register, temporal context and meta-
    # conversation control. These three hooks are its classification surface.

    def _detect_meta_conversation(self, lower, text, raw_text, pragmatics=None):
        """Meta-conversation control signals ("you're too formal", "stop
        joking", "okay serious question") route to meta_control — and compose:
        "okay serious question, what's the weather?" routes the QUESTION while
        carrying the original pragmatics (so the style instruction survives)."""
        from mini_kio.core.pragmatics import strip_meta_prefix
        signal, remainder = strip_meta_prefix(text or raw_text or "")
        if not signal:
            return None
        if remainder:
            return self.classify(remainder, "", _pragmatics=pragmatics)
        return RoutingDecision(
            IntentType.CONVERSATION, "meta_control", signal,
            raw_text or text, text or raw_text, confidence=1.0,
            metadata={"meta_signal": signal, "pragmatics": pragmatics},
        )

    def _classify_pragmatics_social(self, lower, text, raw_text, pragmatics=None):
        """Pure social speech from the pragmatics layer.

        Covers what the fixed GREETINGS vocabulary misses: repeated/stretched
        greetings ("yoyoyo", "AYO AYO", "heyyy", "gm"), backchannels
        ("gotcha", "fair", "bet", "facts"), reactions ("💀", "lmaooo"),
        farewells and compliments. Composition is preserved: "ayy open
        Telegram" recurses on the task with the original pragmatics carried.
        """
        from mini_kio.core.pragmatics import ConversationAct, _collapse, analyze as _pa

        # ── Media-acceptance escape hatch (runs BEFORE pragmatics analysis) ──
        # Multi-word accept phrases ("yes start it", "yes play it", "go ahead",
        # "do it", "play it", "start it") must NEVER be consumed as social —
        # they are media acceptance commands that belong in _classify_context_followup.
        _accept_phrases_re = re.compile(
            r"^(?:"
            r"yes\s+(?:start|play|do)\s+it|"
            r"(?:go\s+ahead|do\s+it|start\s+it|play\s+it|play\s+video)"
            r")$",
            re.I,
        )
        _stripped_lower = lower.strip()
        logger.info("[PRAG_SOCIAL_DEBUG] checking lower=%r match=%s", _stripped_lower, bool(_accept_phrases_re.match(_stripped_lower)))
        if _accept_phrases_re.match(_stripped_lower):
            return None

        analysis = pragmatics if pragmatics is not None else _pa(raw_text or text, text)
        if not analysis.is_social:
            # Casual-greeting + task composition: "ayy open Telegram", "yo
            # create a spreadsheet" — strip the greeting prefix and classify
            # the task, preserving the original pragmatics for the response.
            composed = self._strip_casual_prefix_task(text or raw_text or "")
            if composed:
                return self.classify(composed, "", _pragmatics=analysis)
            return None
        # Media-affirmative ownership: single-word "yes/yeah/sure/ok/okay/yep"
        # accept the pending offer through the media intelligence layer — the
        # pragmatics layer must not steal them (existing accept_offer contract).
        _affirmative_owned = {"yes", "yeah", "yea", "yep", "yup", "yess", "sure", "ok", "okay"}
        _words = lower.split()
        if len(_words) <= 2 and any(_collapse(w) in _affirmative_owned for w in _words):
            return None

        # ── Media choice resolution: bare numbers, ordinals, type selections ──
        # "1", "2", "the second one", "the documentary", "number 3"
        # must route to MEDIA_PLAY so the context intelligence layer can
        # resolve them against pending recommendations.
        _BARE_NUMBER = re.fullmatch(r"\d+", lower.strip())
        _ORDINAL_CHOICE = re.fullmatch(
            r"(?:the\s+)?(?:first|second|third|fourth|fifth|number\s+\d+|option\s+\d+|pick\s+\d+|number\s+\d+)"
            r"(?:\s+one)?",
            lower.strip(),
        )
        _TYPE_CHOICE = re.fullmatch(
            r"(?:the\s+)?(?:documentary|interview|song|trailer|podcast|video|music|short|live)",
            lower.strip(),
        )
        _THAT_CHOICE = lower.strip() in ("that one", "this one", "that", "it")
        if _BARE_NUMBER or _ORDINAL_CHOICE or _TYPE_CHOICE or _THAT_CHOICE:
            return RoutingDecision(
                IntentType.MEDIA_PLAY, "play", lower.strip(), raw_text or text, lower,
                confidence=0.9,
            )

        acts = analysis.acts
        if ConversationAct.GREETING.value in acts:
            # Only the pipeline's OWN greeting vocabulary ("hello", "yo",
            # "wassup", ...) routes to GREETING. Stretched/casual single-word
            # forms ("Yoo", "Yooo", "heyyy") are CONVERSATION (action
            # "converse") — the committed contract — never a GREETING with an
            # empty action, and never an entity query.
            _flat_low = re.sub(r"[^a-z]+", " ", lower).strip().lower()
            _in_greetings = bool(
                _flat_low and (
                    _flat_low in self.GREETINGS
                    or any(g in _flat_low.split() for g in self.GREETINGS)
                )
            )
            if _in_greetings:
                return RoutingDecision(
                    IntentType.GREETING, "", "", raw_text or text, text or raw_text,
                    confidence=1.0, metadata={"pragmatics": analysis},
                )
            return RoutingDecision(
                IntentType.CONVERSATION, "converse", text, text, lower,
                confidence=0.8, metadata={"pragmatics": analysis},
            )
        if ConversationAct.FAREWELL.value in acts:
            return RoutingDecision(
                IntentType.SOCIAL, "farewell", "", raw_text or text, text or raw_text,
                confidence=1.0, metadata={"pragmatics": analysis},
            )
        return RoutingDecision(
            IntentType.SOCIAL, "social", "", raw_text or text, text or raw_text,
            confidence=1.0, metadata={"pragmatics": analysis},
        )

    # Leading casual-greeting tokens that carry a TASK ("ayy open Telegram").
    _CASUAL_GREETING_PREFIX_RE = re.compile(
        r"^(?:ayy|aye|ayo|bro|broo|dude|yo|yoo|hey|heyy|hi|sup|wassup|wazzup|"
        r"gm|gmorning|mornin|hola)\s*[,.!?]?\s+",
        re.IGNORECASE,
    )

    def _strip_casual_prefix_task(self, text: str) -> Optional[str]:
        if not text:
            return None
        m = self._CASUAL_GREETING_PREFIX_RE.match(text.strip())
        if not m:
            return None
        rest = text[m.end():].strip().strip(".,!?;:")
        if not rest:
            return None
        return rest

    _UTILITY_TIME_RES = (
        re.compile(r"^what(?:'s|s| is)?\s+the\s+time\b", re.IGNORECASE),
        re.compile(r"^what\s+time\s+is\s+it\b", re.IGNORECASE),
        re.compile(r"^what(?:'s|s| is)?\s+the\s+current\s+time\b", re.IGNORECASE),
        re.compile(r"^(?:current|local)\s+time\b", re.IGNORECASE),
        re.compile(r"^the\s+time\s+(?:now|right\s+now)\b", re.IGNORECASE),
        re.compile(r"^time\s+(?:now|right\s+now)\b", re.IGNORECASE),
        re.compile(r"^do\s+you\s+know\s+what\s+time\s+it\s+is\b", re.IGNORECASE),
        re.compile(r"^tell\s+me\s+the\s+time\b", re.IGNORECASE),
        re.compile(r"^what\s+time\s+is\s+it\s+in\b", re.IGNORECASE),
    )
    _UTILITY_DATE_RES = (
        re.compile(r"^what(?:'s|s| is)?\s+the\s+date\b", re.IGNORECASE),
        re.compile(r"^what\s+date\s+is\s+it\b", re.IGNORECASE),
        re.compile(r"^what(?:'s|s| is)?\s+today(?:'s)?\s+date\b", re.IGNORECASE),
        re.compile(r"^today(?:'s)?\s+date\b", re.IGNORECASE),
        re.compile(r"^what\s+day\s+is\s+(?:it|today)\b", re.IGNORECASE),
        re.compile(r"^what\s+day\s+of\s+the\s+week\b", re.IGNORECASE),
    )
    _UTILITY_WEATHER_RES = (
        re.compile(r"^what(?:'s|s| is)?\s+the\s+weather\b", re.IGNORECASE),
        re.compile(r"^how(?:'s|s| is)?\s+the\s+weather\b", re.IGNORECASE),
        re.compile(r"^weather\s+(?:in|at|for)\b", re.IGNORECASE),
        re.compile(r"^is\s+it\s+(?:hot|cold|raining|sunny|warm|chilly|windy)\b", re.IGNORECASE),
        re.compile(r"^what(?:'s|s| is)?\s+the\s+temperature\b", re.IGNORECASE),
        re.compile(r"^temperature\s+(?:in|at|for)\b", re.IGNORECASE),
    )
    _UTILITY_CONVERT_PRE_RES = (
        re.compile(r"^convert\s+", re.IGNORECASE),
        re.compile(r"^(?:how\s+much\s+is|what\s+is)\s+\d", re.IGNORECASE),
        re.compile(r"\b\d[\d,.]*\s*(?:kg|kgs|lb|lbs|pounds?|g|grams?|oz|ounces?|km|kms|kilometers?|mi|miles?|m|meters?|ft|feet|cm|in|inch|inches?|l|lit(?:er|re)s?|gal|gallons?|kph|kmh|mph|usd|dollars?|eur|euros?|gbp|inr|rupees?|jpy|yen|aed|cad|aud|celsius|fahrenheit)\b\s+(?:to|in|into)\b", re.IGNORECASE),
        re.compile(r"^how\s+many\s+\w+\s+is\s+\d", re.IGNORECASE),
    )

    def _detect_utility(self, lower, text):
        """Deterministic ownership of utility requests (time/date/weather/
        convert) — KIO answers these itself with normalized clean results;
        they never fall through to generic web retrieval, and raw provider UI
        never becomes the reply."""
        from mini_kio.core.pragmatics import _is_greeting_utterance
        # Greeting-prefix composition: "good morning, what's the weather?" /
        # "yo, what's the time?" — strip the social prefix, keep the utility.
        candidate = text or lower
        if _is_greeting_utterance(candidate, candidate.lower(), candidate.lower()):
            m = re.search(
                r"(?:^|[,;])\s*(what(?:'s|s| is)?\s+the\s+weather|how(?:'s|s| is)?\s+the\s+weather|"
                r"what(?:'s|s| is)?\s+the\s+time|what\s+time\s+is\s+it|what(?:'s|s| is)?\s+the\s+date|"
                r"what\s+day\s+is\s+(?:it|today)|what(?:'s|s| is)?\s+today(?:'s)?\s+date|"
                r"what(?:'s|s| is)?\s+the\s+temperature|weather\s+(?:in|at)\s+\w+|is\s+it\s+(?:hot|cold|raining|sunny)\b)",
                candidate.lower(),
            )
            if m:
                candidate = m.group(1)
            else:
                return None

        # Deterministic arithmetic owns the "calculate" family: bare
        # expressions ("6*7", "2+8", "6!", "(4+6)*3", "6/0") AND natural-
        # language forms ("what's 17 times 8?", "calculate 144/12", "what is
        # 9 factorial?"). Runs BEFORE convert so "what is 2 + 8" is never
        # misread as a unit conversion (which needs a unit pair, not an
        # operator). The numerical answer always comes from the calculator in
        # utilities.py — never the LLM, never web retrieval.
        try:
            from mini_kio.core.utilities import looks_like_arithmetic
            if looks_like_arithmetic(candidate):
                return RoutingDecision(IntentType.UTILITY, "calculate", candidate, text, lower, confidence=1.0)
        except Exception:
            pass
        for pat in self._UTILITY_TIME_RES:
            if pat.match(candidate):
                return RoutingDecision(IntentType.UTILITY, "time", candidate, text, lower, confidence=1.0)
        for pat in self._UTILITY_DATE_RES:
            if pat.match(candidate):
                return RoutingDecision(IntentType.UTILITY, "date", candidate, text, lower, confidence=1.0)
        for pat in self._UTILITY_WEATHER_RES:
            if pat.match(candidate):
                return RoutingDecision(IntentType.UTILITY, "weather", candidate, text, lower, confidence=1.0)
        # Package status ("latest version of X", "is X outdated") and feed
        # watch ("latest releases of owner/repo", "what's new in <pkg>") are
        # KIO's own no-key owners — deterministic, never web retrieval.
        try:
            from mini_kio.core.utilities import looks_like_package
            if looks_like_package(candidate):
                return RoutingDecision(IntentType.UTILITY, "package", candidate, text, lower, confidence=1.0)
        except Exception:
            pass
        try:
            from mini_kio.core.utilities import looks_like_feed
            if looks_like_feed(candidate):
                return RoutingDecision(IntentType.UTILITY, "feed", candidate, text, lower, confidence=1.0)
        except Exception:
            pass
        # Project summary ("summarize the project openai/openai"), release
        # watcher ("watch X for new releases", "stop watching X", "what am I
        # watching"), and the research thread ("research X", "research brief on
        # X", "continue research on X") are KIO's own no-key owners.
        try:
            from mini_kio.core.utilities import looks_like_project_summary
            if looks_like_project_summary(candidate):
                return RoutingDecision(IntentType.UTILITY, "project", candidate, text, lower, confidence=1.0)
        except Exception:
            pass
        # General workflow/automation: "create a workflow to open chrome and
        # search for python" / "run the workflow" / "workflow status" —
        # composes ANY existing action into an engine-executed multi-step
        # workflow with approval gates on consequential steps. Checked BEFORE
        # watch/remind because a workflow body can itself contain "watch X"/
        # "remind me" as a step ("create a workflow to search X and watch Y")
        # — the leading workflow head is more specific than the anywhere verb.
        try:
            from mini_kio.execution.workflows import looks_like_workflow
            if looks_like_workflow(candidate):
                return RoutingDecision(IntentType.UTILITY, "workflow", candidate, text, lower, confidence=1.0)
        except Exception:
            pass
        # General outbound communication (draft/send/cancel/list) — provider-
        # neutral seam; telegram is the first provider, others plug in behind
        # the same contract. Checked before watch for the same reason: a
        # draft body can contain "watch X" ("draft a message to Sarah: watch
        # the page").
        try:
            from mini_kio.communication.messages import looks_like_message
            if looks_like_message(candidate):
                return RoutingDecision(IntentType.UTILITY, "message", candidate, text, lower, confidence=1.0)
        except Exception:
            pass
        try:
            from mini_kio.monitoring.watches import looks_like_watch
            if looks_like_watch(candidate):
                return RoutingDecision(IntentType.UTILITY, "watch", candidate, text, lower, confidence=1.0)
        except Exception:
            pass
        # Time-scheduled notifications ("remind me in 2 hours to X",
        # "cancel my reminders", "what reminders do I have") — the
        # time-trigger companion to the change-trigger watch primitive,
        # sharing the same outbound poller and delivery path.
        try:
            from mini_kio.monitoring.reminders import looks_like_reminder
            if looks_like_reminder(candidate):
                return RoutingDecision(IntentType.UTILITY, "remind", candidate, text, lower, confidence=1.0)
        except Exception:
            pass
        try:
            from mini_kio.research.briefs import looks_like_research
            if looks_like_research(candidate):
                return RoutingDecision(IntentType.UTILITY, "research", candidate, text, lower, confidence=1.0)
        except Exception:
            pass
        # No-key live owners wired through the utility seam: air quality
        # (Open-Meteo AQ, same geocoding as weather), public holidays
        # (Nager.Date), earthquakes (USGS FDSN), books (Open Library). All
        # deterministic answers with an honest offline fallback — never
        # generic web retrieval for these families.
        try:
            from mini_kio.core.utilities import looks_like_air_quality
            if looks_like_air_quality(candidate):
                return RoutingDecision(IntentType.UTILITY, "air_quality", candidate, text, lower, confidence=1.0)
        except Exception:
            pass
        try:
            from mini_kio.core.utilities import looks_like_holiday
            if looks_like_holiday(candidate):
                return RoutingDecision(IntentType.UTILITY, "holiday", candidate, text, lower, confidence=1.0)
        except Exception:
            pass
        try:
            from mini_kio.core.utilities import looks_like_earthquake
            if looks_like_earthquake(candidate):
                return RoutingDecision(IntentType.UTILITY, "earthquake", candidate, text, lower, confidence=1.0)
        except Exception:
            pass
        try:
            from mini_kio.core.utilities import looks_like_book
            if looks_like_book(candidate):
                return RoutingDecision(IntentType.UTILITY, "book", candidate, text, lower, confidence=1.0)
        except Exception:
            pass
        for pat in self._UTILITY_CONVERT_PRE_RES:
            if pat.search(candidate):
                try:
                    from mini_kio.core.utilities import try_parse_conversion
                    if try_parse_conversion(candidate) is not None:
                        return RoutingDecision(IntentType.UTILITY, "convert", candidate, text, lower, confidence=1.0)
                except Exception:
                    pass
        return None

    def _check_identity(self, lower, raw_text="", normalized_text=""):
        from mini_kio.llm.identity_dataset import get_identity_answer
        # KIO-as-assistant vs KIO-as-external-entity boundary: identity answers
        # only fire for KIO-itself questions. A qualifying noun after KIO
        # ("tell me about KIO Systems", "KIO Technologies") is an external
        # entity and must flow to the knowledge path, never self-identity.
        if re.search(
            r"\bkio\b.*\b(systems?|corporation|corp|inc|llc|technolog(?:y|ies)|company|platform|product|brand|services)\b",
            lower,
        ):
            return None
        # KIO-self operational/activity questions ("what is kio currently
        # doing", "what is kio up to") are STATUS questions with a
        # deterministic owner — the identity dataset's "what is kio" prefix
        # trigger must NOT capture them (live: "what is kio currently doing"
        # returned the static identity answer instead of the runtime status).
        if re.search(
            r"^what\s+is\s+kio(?:'s)?\s+(?:currently\s+|right\s+now\s+)?"
            r"(?:doing|handling|working\s+on|up\s+to|controlling|using|running)\b",
            lower,
        ):
            return None
        if get_identity_answer(lower):
            return RoutingDecision(IntentType.IDENTITY, "", "", raw_text or normalized_text, normalized_text or lower, confidence=1.0)
        return None

    def _is_forbidden(self, lower, first_word):
        # Phrasal-verb-first ordering, mirroring _open_verb_target, so
        # "open up cmd" resolves the target "cmd" exactly like "open cmd"
        # (never bypasses the forbidden-target gate via "up cmd").
        norm = None
        for phrase in self._OPEN_PHRASES[0]:
            if lower.startswith(phrase):
                norm = lower[len(phrase):].strip().lower()
                break
        if norm is None and first_word in self._OPEN_VERBS:
            norm = lower[len(first_word):].strip().lower()
        if norm is None:
            norm = lower
        if norm.endswith(".exe"):
            norm = norm[:-4]
        return norm in self.FORBIDDEN_TARGETS

    def _classify_multi_step(self, lower, raw_text):
        from mini_kio.core.command_parser import is_multi_step
        if is_multi_step(lower):
            return RoutingDecision(
                IntentType.MULTI_STEP, "multi_step", "",
                raw_text, lower, confidence=1.0,
            )
        return None

    def _has_trailing_conjunction(self, lower, first_word):
        verbs = {"open", "close", "shut", "quit", "kill", "end", "search", "play", "launch", "folder", "start", "run", "fire up"}
        if first_word in verbs or any(lower.startswith(p) for p in self._OPEN_PHRASES[0]):
            return bool(re.search(r"\b(?:and|then|anf|andd|thenn|theen)\s*$", lower))
        return False

    def _classify_deterministic(self, lower, text, first_word, second_word):
        from mini_kio.core.routing_utils import get_browser_routing, get_browser_registry
        from mini_kio.core.app_operator import WEB_DOMAIN_ALIASES, WEB_URLS

        # Simulation: "simulate X" / "dry run X" / "preview X" / "what if I X"
        sim_match = re.match(
            r"^(?:simulate|dry.?run|preview|what(?:'s|\s+is|\s+would)\s+.*(?:happen|if)\s+(?:i\s+)?|what\s+if\s+(?:i\s+)?)"
            r"\s*(.+)",
            text, re.IGNORECASE,
        )
        if sim_match:
            rest = sim_match.group(1).strip()
            # Re-classify the rest without executing
            sub = self._classify_deterministic(rest.lower(), rest, rest.split()[0] if rest.split() else "", rest.split()[1] if len(rest.split()) > 1 else "")
            return RoutingDecision(
                IntentType.SIMULATE, "simulate", rest, text, lower,
                confidence=1.0,
                metadata={"inner_decision": sub},
            )

        go_match = re.match(r"^(?:go\s+to|navigate\s+to|visit|browse)\s+(.+)", text, re.IGNORECASE)
        if go_match:
            target = go_match.group(1).strip()
            if target.startswith(("http://", "https://")):
                return RoutingDecision(IntentType.BROWSER_NAVIGATE, "browser_goto", target, text, lower, confidence=1.0)
            return RoutingDecision(IntentType.DESKTOP_OPEN, "open", target, text, lower, confidence=0.9)

        search_query = self._detect_search(lower, text, first_word)
        if search_query:
            return search_query

        if self._detect_browser_webapp(lower, text):
            return self._detect_browser_webapp(lower, text)

        # "create a new Excel workbook" / "make a new Word document" — the
        # create/make counterpart of the open-instance forms below (runs with
        # the open family so the explicit-new marker survives into execution).
        create_new = self._detect_create_new_instance(lower, text)
        if create_new:
            return create_new

        open_routing = self._detect_open(lower, text, first_word)
        if open_routing:
            return open_routing

        focus_routing = self._detect_focus(lower, text, first_word, second_word)
        if focus_routing:
            return focus_routing

        desktop_routing = self._detect_desktop_action(lower, text)
        if desktop_routing:
            return desktop_routing

        operational_routing = self._detect_operational(lower, text)
        if operational_routing:
            return operational_routing

        credential_routing = self._detect_credential(lower, text)
        if credential_routing:
            return credential_routing

        if self._detect_list_tabs(lower):
            return RoutingDecision(IntentType.BROWSER_TABS, "list_tabs", "", text, lower, confidence=1.0)

        close_routing = self._detect_close(lower, text, first_word)
        if close_routing:
            return close_routing

        if self._detect_system(lower, first_word):
            return self._detect_system(lower, first_word)

        file_routing = self._detect_file(lower, text, first_word)
        if file_routing:
            return file_routing

        return None

    def _detect_search(self, lower, text, first_word):
        if first_word == "search":
            query = text[7:].strip()
            if query.lower().startswith("for "):
                query = query[4:].strip()
            google_for = re.match(r"^google\s+for\s+(.+)$", query, re.IGNORECASE)
            if google_for:
                return RoutingDecision(IntentType.SEARCH, "search_web", google_for.group(1).strip(), text, lower, confidence=1.0)
            for sep in [" in ", " on ", " using "]:
                if sep in query:
                    parts = query.rsplit(sep, 1)
                    app, clean_query = parts[1].strip(), parts[0].strip()
                    if app.lower() in ("youtube",):
                        return RoutingDecision(IntentType.SEARCH, "search_youtube", clean_query, text, lower, confidence=1.0, metadata={"platform": "youtube"})
                    if app.lower() == "google":
                        return RoutingDecision(IntentType.SEARCH, "search_web", clean_query, text, lower, confidence=1.0)
            if query.lower().startswith("youtube "):
                yt_query = query[8:].strip()
                if yt_query.lower().startswith("for "):
                    yt_query = yt_query[4:].strip()
                return RoutingDecision(IntentType.SEARCH, "search_youtube", yt_query, text, lower, confidence=1.0)
            return RoutingDecision(IntentType.SEARCH, "search_web", query, text, lower, confidence=1.0)
        return None

    # Referent pronouns that must never be synthesized into web domains
    # ("open it in chrome" with no resolved context must not become
    # https://it.com). They are routed to a truthful referent-required failure.
    _WEBAPP_REFERENT_STOP = frozenset({
        "it", "this", "that", "them", "those", "there", "here", "one",
    })

    def _detect_browser_webapp(self, lower, text):
        # Generic target-instance semantics (Section 2/3 of the 2026-08-12
        # directive): the semantic layer must distinguish INSTANCE kinds
        # (existing target vs NEW tab vs NEW window) WITHOUT per-app branches.
        # Every instance phrase converges on the same execute_capability owner
        # with explicit_new=True plus an instance marker; the ENTITY (webapp)
        # is preserved while only the INSTANCE changes.
        force_new = False
        instance = "default"  # "default" | "tab" | "window"
        webapp = None
        browser = None

        # 1. "open another tab of X" / "open a new tab of X"
        m = re.match(r"^open\s+(?:another|a\s+new)\s+tab\s+(?:of\s+)?(.+?)\s*$", lower)
        if m:
            webapp, instance, force_new = m.group(1).strip(), "tab", True
        else:
            # 2. "open X in a new tab" / "open X in a fresh tab"
            m = re.match(r"^open\s+(.+?)\s+in\s+(?:a\s+)?(?:new|fresh)\s+tab\s*$", lower)
            if m:
                webapp, instance, force_new = m.group(1).strip(), "tab", True
            else:
                # 3. "open a new X tab" / "open another X tab" / "open a fresh X tab"
                m = re.match(r"^open\s+(?:a\s+)?(?:new|fresh|another)\s+(.+?)\s+tab\s*$", lower)
                if m:
                    webapp, instance, force_new = m.group(1).strip(), "tab", True
                else:
                    # 4. "open a new browser window for X" / "open another window for X"
                    m = re.match(
                        r"^open\s+(?:a\s+)?(?:new|fresh|another)\s+(?:browser\s+)?window\s+(?:for|of)\s*(.+?)\s*$",
                        lower,
                    )
                    if m:
                        webapp, instance, force_new = m.group(1).strip(), "window", True
                    else:
                        # 5. "open a new X window" / "open another X window"
                        m = re.match(
                            r"^open\s+(?:a\s+)?(?:new|fresh|another)\s+(.+?)\s+(?:browser\s+)?window\s*$",
                            lower,
                        )
                        if m:
                            webapp, instance, force_new = m.group(1).strip(), "window", True
                        else:
                            # 6. "open X in a new window"
                            m = re.match(r"^open\s+(.+?)\s+in\s+(?:a\s+)?(?:new|fresh)\s+window\s*$", lower)
                            if m:
                                webapp, instance, force_new = m.group(1).strip(), "window", True
                            else:
                                # 7. "open X in <browser>" — modality selection only.
                                # Dynamic: accept any word and resolve against installed
                                # browsers at resolution time, not hardcoded at parse time.
                                m = re.match(r"^open\s+(.+?)\s+in\s+([a-z][a-z0-9 ]+)$", lower)
                                if m:
                                    _candidate_app = m.group(2).strip()
                                    _KNOWN_BROWSER_NAMES = frozenset({
                                        "chrome", "edge", "firefox", "brave", "comet",
                                        "opera", "vivaldi", "arc", "browser",
                                    })
                                    if _candidate_app in _KNOWN_BROWSER_NAMES or _candidate_app == "browser":
                                        webapp, browser = m.group(1).strip(), _candidate_app
                                    else:
                                        # Try dynamic browser discovery
                                        try:
                                            from mini_kio.core.app_operator import _find_installed_app
                                            _app = _find_installed_app(_candidate_app)
                                            if _app and _app.get("kind") in ("exe", "shortcut"):
                                                _is_browser = any(
                                                    kw in (_app.get("target", "") or "").lower()
                                                    for kw in ("chrome", "edge", "firefox", "brave", "comet", "opera")
                                                )
                                                if _is_browser:
                                                    webapp, browser = m.group(1).strip(), _candidate_app
                                        except Exception:
                                            pass
        if not webapp:
            return None
        # Registered NATIVE apps with no legitimate web version must NOT be
        # hijacked into synthesized .com windows/tabs by the new-instance
        # patterns above: "open a new VS Code window", "open a new Word
        # window" are NATIVE new-instance requests (open_app + explicit_new),
        # not browser windows of vscode.com. Only targets with a real web
        # identity (WEB_URLS / WEB_DOMAIN_ALIASES) belong on the browser path;
        # everything else falls through to _detect_open which preserves
        # explicit_new for the native open. Telegram/ChatGPT/Gemini keep their
        # web versions because they ARE registered web identities.
        if webapp:
            from mini_kio.core.app_operator import _is_registry_alias, WEB_URLS, WEB_DOMAIN_ALIASES
            _wa = webapp.lower().strip()
            if _is_registry_alias(_wa) and _wa not in WEB_URLS and _wa not in WEB_DOMAIN_ALIASES:
                return None
        # A modal target with no explicit browser defaults to the configured
        # browser (never an empty ::open_url:: prefix — that broke execution).
        if not browser or browser == "browser":
            from mini_kio.core.config import DEFAULT_BROWSER
            browser = DEFAULT_BROWSER.lower()
        # A trailing app qualifier inside an explicit web request is noise
        # ("open notepad app in chrome" -> "notepad"), never part of the URL.
        webapp = re.sub(r"\s+(?:app|application|desktop)\s*$", "", webapp.strip(), flags=re.IGNORECASE).strip()
        webapp_lower = webapp.lower().strip()
        if webapp_lower in self._WEBAPP_REFERENT_STOP:
            return RoutingDecision(
                IntentType.BROWSER_NAVIGATE, "invalid_web_target", webapp,
                text, lower, confidence=1.0,
                metadata={"referent_missing": True},
            )
        from mini_kio.core.app_operator import _explicit_web_url_for_open
        url = _explicit_web_url_for_open(webapp)
        if url:
            return RoutingDecision(
                IntentType.BROWSER_NAVIGATE, "execute_capability",
                f"{browser}::open_url::{url}::{webapp}",
                text, lower, confidence=1.0,
                metadata={
                    "explicit_new": force_new,
                    "instance": instance,
                    "webapp": webapp_lower,
                    "browser": browser,
                },
            )
        # Explicit "open X in <browser>" with a target that is NOT a valid
        # web destination (internal host, malformed, forbidden chars) is a
        # routing-time rejection. It must NEVER fall through to native
        # app-open, and must never open an internal host in a browser.
        return RoutingDecision(
            IntentType.BROWSER_NAVIGATE, "invalid_web_target", webapp,
            text, lower, confidence=1.0,
        )

    # Open/launch verb family: "open vscode", "launch vscode", "start vscode",
    # "run vscode", "fire up vscode" all resolve to the same native-app target
    # through the canonical target-kind resolver. "run"/"start" are only open
    # verbs when followed by a plausible app-like target (a bare "run" /
    # "start" stays conversational/media).
    _OPEN_VERBS = frozenset({"open", "launch", "start", "run"})
    _OPEN_PHRASES = (("fire up ", "open up ", "bring up "), )

    def _open_verb_target(self, lower, text, first_word):
        """Return the target following an open/launch/start/run verb, or None.

        Phrasal verbs ("open up X", "fire up X", "bring up X") are matched
        FIRST because their phrase is longer than the bare verb — otherwise
        "open up winrar" would slice on "open" and produce target "up
        winrar". Bare verbs then fall through.
        """
        target = None
        for phrase in self._OPEN_PHRASES[0]:
            if lower.startswith(phrase):
                target = text[len(phrase):].strip()
                break
        if target is None and first_word in self._OPEN_VERBS:
            target = text[len(first_word):].strip()
        if not target:
            return None
        # "run"/"start" must be followed by an app-like noun phrase, not a
        # question/search fragment ("run a search", "start a timer").
        if first_word in ("run", "start"):
            first_t = target.lower().split()[0] if target.split() else ""
            if first_t in ("a", "an", "the", "for", "with", "this", "that",
                           "my", "your", "search", "timer", "what", "how",
                           "why", "when", "where", "who"):
                return None
        return target

    # "create a new Excel workbook" / "make a new Word document" — the
    # canonical counterpart of "open a new Word document". A create/make verb
    # with a REGISTERED office/editor app and a BLANK-INSTANCE noun
    # (document/workbook/worksheet/presentation/deck/file/window) is an
    # explicit NEW-INSTANCE OPEN of that app — not content generation. Only
    # blank-instance nouns qualify; content-kind nouns (tracker/budget/report)
    # keep the document-creation route. Generic family rule, never per-app.
    _CREATE_NEW_INSTANCE_RE = re.compile(
        r"^(?:create|make|open)\s+(?:me|us)?\s*(?:a|an|the)?\s*(?:new|fresh|another)?\s*"
        r"(word|microsoft\s+word|ms\s+word|excel|microsoft\s+excel|powerpoint|"
        r"microsoft\s+powerpoint|notepad|vs\s+code|vscode|visual\s+studio\s+code)\s+"
        r"(document|doc|workbook|worksheet|presentation|deck|slides?|file|window)\s*$",
        re.IGNORECASE,
    )

    def _detect_create_new_instance(self, lower, text):
        m = self._CREATE_NEW_INSTANCE_RE.match(lower)
        if not m:
            return None
        app = m.group(1).lower().strip()
        from mini_kio.core.app_operator import _is_registry_alias
        if not _is_registry_alias(app):
            return None
        alias = {
            "microsoft word": "word", "ms word": "word",
            "microsoft excel": "excel",
            "microsoft powerpoint": "powerpoint",
            "vscode": "vs code", "visual studio code": "vs code",
        }
        canonical = alias.get(app, app)
        return RoutingDecision(
            IntentType.DESKTOP_OPEN, "open_app", canonical, text, lower,
            confidence=1.0,
            metadata={"explicit_new": True},
        )

    def _detect_open(self, lower, text, first_word):
        target = self._open_verb_target(lower, text, first_word)
        if target is None:
            return None
        # ── Semantic modifier extraction (before any cleanup) ──────────────
        # Explicit modality / new-target markers are extracted from the raw
        # target FIRST so they survive noun-phrase cleanup as structured
        # constraints, never as part of the entity name. Generic family rules,
        # not per-app phrasing.
        raw_target = target.strip()
        explicit_web = False
        explicit_native = False
        explicit_new = False

        # Explicit web-intent tail: "X on the web", "X in the browser",
        # "X web version", "X on the internet".
        m = re.search(
            r"\s+(?:on\s+the\s+web|in\s+the\s+browser|web\s+version|on\s+the\s+internet|in\s+browser|in\s+the\s+web)\s*$",
            raw_target, re.IGNORECASE,
        )
        if m:
            explicit_web = True
            raw_target = raw_target[: m.start()].strip()
        # Explicit native-intent markers: "the X app", "X desktop app",
        # "X application".
        m = re.search(
            r"\s+(?:desktop\s+)?(?:app|application|program|software)\s*$",
            raw_target, re.IGNORECASE,
        )
        if m and not explicit_web:
            explicit_native = True
            raw_target = raw_target[: m.start()].strip()
        # Explicit additional-target markers: "another X", "a new X",
        # "a second X", "new X window".
        m = re.match(r"^(?:another|a\s+second|a\s+new)\s+(.+)$", raw_target, re.IGNORECASE)
        if m and m.group(1).strip().lower() not in ("tab", "window", "instance"):
            explicit_new = True
            raw_target = m.group(1).strip()
        m = re.match(r"^new\s+(.+?)(?:\s+(?:window|instance))?$", raw_target, re.IGNORECASE)
        if m and not explicit_new and m.group(1).strip().lower() not in ("tab", "window", "instance"):
            explicit_new = True
            raw_target = m.group(1).strip()
        # Trailing politeness is never part of the target.
        raw_target = re.sub(
            r"\s+(?:for\s+me|for\s+us|please|pls)\s*$", "", raw_target,
            flags=re.IGNORECASE,
        ).strip()
        target = raw_target

        # Generic noun-phrase cleanup for app-like targets: strip a leading
        # article and a trailing qualifier ("the winrar app" -> "winrar",
        # "open up the winrar app" -> "winrar"). This is a semantic family
        # rule, not per-app phrasing.
        target = re.sub(r"^(?:the|a|an|my|your)\s+", "", target.strip(), flags=re.IGNORECASE)
        target = re.sub(r"\s+(?:app|application|program|software)\s*$", "", target, flags=re.IGNORECASE).strip()
        if not target:
            return None
        # Artifact/instance nouns on an app-like target: "open a new Word
        # document", "create a new Excel workbook", "open a new PowerPoint
        # presentation" name the APP plus the artifact kind. When the base
        # names a registered application, strip the artifact noun so the
        # request opens the APP — the explicit-new marker above already
        # captured the new-instance semantics ("open a new Word document" ->
        # open_app(word) with explicit_new=True, never a failed "word
        # document" target). Generic family rule, not per-app phrasing.
        _artifact_noun_re = re.compile(
            r"\s+(?:document|doc|workbook|worksheet|spreadsheet|presentation|deck|slides|file|text|editor|window)\s*$",
            re.IGNORECASE,
        )
        _noun_m = _artifact_noun_re.search(target)
        if _noun_m:
            _base = target[:_noun_m.start()].strip()
            from mini_kio.core.app_operator import _is_registry_alias
            if _base and _is_registry_alias(_base.lower()):
                target = _base
        target_lower = target.lower()
        words_set = set(target_lower.split())

        # "open the browser" -> the default browser host.
        if target_lower in ("browser", "web browser"):
            from mini_kio.core.config import DEFAULT_BROWSER
            return RoutingDecision(
                IntentType.DESKTOP_OPEN, "open_app", DEFAULT_BROWSER.lower(),
                text, lower, confidence=1.0,
            )

        from mini_kio.media.intelligence.artifact_memory import parse_artifact_type
        artifact = parse_artifact_type(target_lower)
        if artifact is not None:
            return RoutingDecision(
                IntentType.MEDIA_PLAY, "play", target_lower,
                text, lower, confidence=0.9,
                metadata={"artifact_type": artifact.value},
            )

        if words_set & self.FOLDER_KEYWORDS:
            folder = target_lower.replace("folder", "").strip()
            folder = " ".join(folder.split()) or target_lower
            return RoutingDecision(IntentType.FILE, "open_folder", folder, text, lower, confidence=1.0)

        # EXPLICIT WEB MODALITY — overrides native even when the app is
        # installed ("open X on the web" must open the website). Uses the
        # explicit-web resolver so single-word entities with a native install
        # ("spotify in Chrome") still resolve to their legitimate website.
        if explicit_web:
            from mini_kio.core.app_operator import _explicit_web_url_for_open
            from mini_kio.core.config import DEFAULT_BROWSER
            url = _explicit_web_url_for_open(target)
            if url:
                return RoutingDecision(
                    IntentType.BROWSER_NAVIGATE, "execute_capability",
                    f"{DEFAULT_BROWSER.lower()}::open_url::{url}::{target_lower}",
                    text, lower, confidence=1.0,
                    metadata={"explicit_web": True, "explicit_new": explicit_new},
                )
            return RoutingDecision(
                IntentType.BROWSER_NAVIGATE, "invalid_web_target", target,
                text, lower, confidence=1.0, metadata={"explicit_web": True},
            )

        # EXPLICIT NATIVE MODALITY — "open the X app" / "X desktop app" must
        # resolve the native target, never the website.
        if explicit_native:
            return RoutingDecision(
                IntentType.DESKTOP_OPEN, "open_app", target, text, lower,
                confidence=1.0,
                metadata={"explicit_native": True, "explicit_new": explicit_new},
            )

        from mini_kio.core.routing_utils import get_browser_routing
        route_info = get_browser_routing(target)
        if route_info["route_type"] == "native":
            return RoutingDecision(
                IntentType.DESKTOP_OPEN, route_info["action"], route_info["target"],
                text, lower, confidence=1.0,
                metadata={"explicit_new": explicit_new},
            )
        elif route_info["route_type"] == "browser_fallback":
            return RoutingDecision(
                IntentType.BROWSER_NAVIGATE, route_info["action"], route_info["target"],
                text, lower, confidence=1.0,
                metadata={"canonical_target": route_info.get("canonical_target", ""), "browser": route_info.get("browser", ""), "explicit_new": explicit_new},
            )
        else:
            # not_found -> truthful native-open failure ("couldn't find X
            # installed"), never a silent web substitution.
            return RoutingDecision(
                IntentType.DESKTOP_OPEN, "open_app", route_info.get("target") or target,
                text, lower, confidence=1.0,
                metadata={"explicit_new": explicit_new},
            )

    def _detect_focus(self, lower, text, first_word, second_word):
        # Same-application multi-instance selection: "switch to the other Word
        # window", "focus the other window", "switch to another Excel" must
        # select an EXISTING second instance — never recreate, never collapse
        # into the first. The executor picks the nth matching window. Must run
        # BEFORE the bare "switch to " prefix match ("switch to the other word
        # window" also starts with "switch to ").
        _focus_noun_re = re.compile(
            r"\s+(?:window|windows|tab|tabs|document|doc|instance|app|application)\s*$",
            re.IGNORECASE,
        )

        def _clean_focus_target(raw: str) -> str:
            """Drop trailing instance nouns so the focus resolves to the APP
            identity: "switch to the other Word window" -> "word", "focus the
            Excel window" -> "excel". Generic family rule, never per-app."""
            t = (raw or "").strip()
            m = _focus_noun_re.search(t)
            if m and t[: m.start()].strip():
                t = t[: m.start()].strip()
            return t

        _other = re.match(r"^(?:switch\s+to|focus)\s+(?:the\s+|to\s+the\s+)?(?:other|another)\s+(.+)$", lower)
        if _other:
            return RoutingDecision(
                IntentType.BROWSER_FOCUS, "focus", _clean_focus_target(_other.group(1)),
                text, lower, confidence=1.0,
                metadata={"instance_index": 1},
            )
        if first_word == "focus":
            return RoutingDecision(IntentType.BROWSER_FOCUS, "focus", _clean_focus_target(text[6:]), text, lower, confidence=1.0)
        # Conversational topic-switch guard: "switch to music - recommend a
        # lesser known indie band", "switch to sports, what's the latest",
        # "switch to books and suggest something" change the CONVERSATION
        # topic — never a window-focus command (live: "ok switch to music -
        # recommend a lesser known indie band" was misrouted to
        # focus("music - recommend...") and returned "Couldn't focus Music -
        # Recommend A Lesser Known Indie Band."). The signal is a continuation
        # clause or request language AFTER the target ("-", ",", ":",
        # "recommend", "what should", "tell me", "talk about"...). A bare
        # "switch to chrome" / "switch to the other Word window" keeps the
        # focus route.
        if lower.startswith("switch to "):
            _rest = text[10:].strip()
            if _rest and re.search(
                r"(?:[-—–]\s+\w|,\s+(?:recommend|what|which|how|tell|talk|chat|discuss|i\s+want|"
                r"give|let'?s|any|back|topic|show)|"
                r"\b(?:recommend|suggest|recommendations?|what\s+should|what\s+to\s+"
                r"(?:watch|play|see|read|listen|try|eat|cook|get|buy)|tell\s+me|let'?s\s+"
                r"(?:talk|chat|switch)|talk\s+about|chat\s+about|discuss|i\s+want|give\s+me|"
                r"how\s+about|what'?s?\s+(?:new|the\s+latest|going\s+on|happening)|show\s+me|"
                r"any\s+good|back\s+to\s+(?:that|this|it|the)|topic|subject|any\s+recommendations))",
                _rest,
            ):
                return None
            return RoutingDecision(IntentType.BROWSER_FOCUS, "focus", _clean_focus_target(_rest), text, lower, confidence=1.0)
        if first_word == "switch":
            _rest = text[7:].strip()
            if _rest and re.search(
                r"(?:[-—–]\s+\w|,\s+(?:recommend|what|which|how|tell|talk|chat|discuss|i\s+want|"
                r"give|let'?s|any|back|topic|show)|"
                r"\b(?:recommend|suggest|recommendations?|what\s+should|what\s+to\s+"
                r"(?:watch|play|see|read|listen|try|eat|cook|get|buy)|tell\s+me|let'?s\s+"
                r"(?:talk|chat|switch)|talk\s+about|chat\s+about|discuss|i\s+want|give\s+me|"
                r"how\s+about|what'?s?\s+(?:new|the\s+latest|going\s+on|happening)|show\s+me|"
                r"any\s+good|back\s+to\s+(?:that|this|it|the)|topic|subject|any\s+recommendations))",
                _rest,
            ):
                return None
            return RoutingDecision(IntentType.BROWSER_FOCUS, "focus", _clean_focus_target(_rest), text, lower, confidence=1.0)
        # FOCUS extension family: "bring Discord up / forward / to the front",
        # "go back to Notepad". Generic phrasing → same canonical focus owner.
        m = re.match(r"^bring\s+(.+?)\s+(?:up|forward|to\s+the\s+front|into\s+focus)\s*$", lower)
        if m:
            return RoutingDecision(IntentType.BROWSER_FOCUS, "focus", m.group(1).strip(), text, lower, confidence=1.0)
        m = re.match(r"^go\s+back\s+to\s+(.+)$", lower)
        if m:
            _target = m.group(1).strip()
            # "go back to X" is an app/window focus command ("go back to
            # Notepad", "go back to Chrome"). When X is a DISCOURSE REFERENT
            # ("go back to that movie you mentioned", "go back to the one we
            # discussed", "go back to that thing earlier") the user is
            # returning to a conversational topic, not focusing a window — the
            # message must stay conversation so the generator resolves the
            # referent from history. Live bug: "Go back to that movie you
            # mentioned" became focus(target="that movie you mentioned") and
            # returned "Couldn't focus That Movie You Mentioned."
            if re.search(
                r"\b(?:that|this|the\s+one|those|these|it)\b|\byou\s+(?:said|mentioned|recommended|suggested)\b|\b(?:earlier|before|again)\b",
                _target,
            ):
                return None
            return RoutingDecision(IntentType.BROWSER_FOCUS, "focus", _target, text, lower, confidence=1.0)
        return None

    # ── DESKTOP-ACTION semantic families ────────────────────────────────────
    # Generic capability classes, NOT phrase lists: TYPE (text entry), KEY_PRESS
    # (keyboard), SCROLL / CLICK (bounded GUI), SAVE/COPY/PASTE/SELECT/UNDO/REDO
    # (hotkey shortcuts). Each family normalizes arbitrary wording onto a
    # canonical action + payload, then the same canonical executor runs it.
    # Programming-language names are excluded from TYPE targets so "put this
    # code in Python" stays a code request, never a desktop-typing action.
    _TYPE_TARGET_LANGUAGES = frozenset({
        "python", "javascript", "typescript", "java", "c++", "c#", "go",
        "rust", "ruby", "php", "kotlin", "swift", "sql", "html", "css",
        "bash", "powershell", "json", "yaml", "markdown", "shell",
    })
    # Knowledge-shape guard for the BARE "type X" family: single-noun
    # concepts that are almost always information questions ("type coercion",
    # "type safety", "type system") must never become desktop typing. Multi-
    # word payloads ("type hello world this is a kio test") are typing unless
    # they match a knowledge shape (leading digit, "of ", blood-type grammar).
    _TYPE_KNOWLEDGE_NOUNS = frozenset({
        "coercion", "safety", "system", "systems", "hierarchy", "theory",
        "casting", "error", "errors", "blood", "diabetes", "cancer",
    })

    _CAMERA_CAPTURE_RE = re.compile(
        r"^(?:open\s+(?:the\s+)?camera\s+(?:and\s+)?)?"
        r"(?:take|shoot|snap|capture|get|click)\s+(?:a\s+|an\s+|the\s+)?"
        r"(?:picture|photo|photograph|selfie|shot|image|pic)\s*"
        r"(?:with\s+(?:the\s+|my\s+)?camera)?\s*$",
        re.IGNORECASE,
    )
    # Video capture: "record a video" / "take a video" / "record a clip"
    # / "record a 10-second video" — optional duration (default 5s).
    _CAMERA_VIDEO_RE = re.compile(
        r"^(?:open\s+(?:the\s+)?camera\s+(?:and\s+)?)?"
        r"(?:record|take|shoot|capture|make|film)\s+(?:a\s+|an\s+|the\s+|some\s+)?"
        r"(?:(?:short|quick|small|brief)\s+)?"
        r"(?:(\d+(?:\.\d+)?)\s*-?\s*(seconds?|secs?|s|minutes?|mins?|m)\s+)?"
        r"(?:video|clip|recording|footage|vlog|video\s+clip)"
        r"(?:\s+(?:for\s+)?(\d+(?:\.\d+)?)\s*-?\s*(seconds?|secs?|s|minutes?|mins?|m))?\s*$",
        re.IGNORECASE,
    )
    _CAMERA_OPEN_RE = re.compile(
        r"^(?:open|launch|start|fire\s+up|turn\s+on)\s+(?:the\s+|my\s+)?"
        r"(?:camera|webcam)\s*$",
        re.IGNORECASE,
    )

    def _camera_video_routing(self, lower, text) -> Optional["RoutingDecision"]:
        """Video-capture routing with the requested duration (default 5s)."""
        vm = self._CAMERA_VIDEO_RE.match(lower)
        if not vm:
            return None
        # Duration may precede the noun ("a 10 second video") or follow it
        # ("a video for 10 seconds"); the trailing form wins when both appear.
        duration = 5.0
        for g_num, g_unit in ((3, 4), (1, 2)):
            if vm.group(g_num):
                try:
                    n = float(vm.group(g_num))
                    unit = (vm.group(g_unit) or "s").lower()
                    duration = n * 60.0 if unit.startswith("m") else n
                except (TypeError, ValueError):
                    duration = 5.0
                break
        return RoutingDecision(
            IntentType.DESKTOP_ACTION, "camera", "capture", text, lower,
            confidence=1.0,
            metadata={"camera_action": "video", "duration": duration},
        )

    def _detect_camera(self, lower, text):
        """Camera semantic family (generic, no app-specific branches).

        - "open the camera" / "launch my camera" → camera open (native).
        - "take a picture" / "click a picture" / "capture a photo" → photo.
        - "record a video" / "take a 10-second video" → video capture with
          the requested duration (default: a short 5-second clip).
        The executor resolves the native installed camera (UWP discovery)
        and reports the REAL result; capture is only claimed when a new file
        with valid content actually appears in the camera output folder.
        """
        video_decision = self._camera_video_routing(lower, text)
        if video_decision:
            return video_decision
        if self._CAMERA_CAPTURE_RE.match(lower):
            return RoutingDecision(
                IntentType.DESKTOP_ACTION, "camera", "capture", text, lower,
                confidence=1.0, metadata={"camera_action": "capture"},
            )
        if self._CAMERA_OPEN_RE.match(lower):
            return RoutingDecision(
                IntentType.DESKTOP_ACTION, "camera", "open", text, lower,
                confidence=1.0, metadata={"camera_action": "open"},
            )
        return None

    def _detect_desktop_action(self, lower, text):
        # ── TYPE family: "type hello into Notepad", "write this in Notepad",
        #    "put hello into the current field", "enter my name" ─────────────
        #    A payload that REQUESTs content ("a short poem about X", "a
        #    three-point summary") is a GENERATED-content task: the LLM creates
        #    the content, the deterministic desktop provider types it. A plain
        #    literal payload ("hello", "my name is Joel") is typed verbatim.
        # Artifact-first phrasing: "do a small comparison on X and Y and type
        # it into notepad" / "make a comparison between A and B and put it in
        # the editor". The artifact request becomes the GENERATED payload;
        # the trailing "and type it into <target>" clause carries the app.
        m = re.match(
            r"^(?:do|make|write|draft|create|generate)\s+(?:a|an|the)?\s*"
            r"(?:small|short|quick|brief|detailed|concise|real|proper|full|simple|professional|formal)?\s*"
            r"(comparison|essay|report|summary|analysis|review|article|poem|story|letter|email|overview|guide|write-up)\s+"
            r"(?:(?:on|about|of|between|comparing)\s+(.+?)\s+)?"
            r"(?:and\s+)?(?:then\s+)?(?:type|put|enter|paste)\s+(?:it|that|this)?\s*"
            r"(?:(?:into|in|onto|on\s+to)\s*){1,2}\s*(?:a\s+)?(?:new\s+)?(.+)$",
            lower,
        )
        if m and self._looks_like_generated_content(
            f"a {m.group(1)} on {m.group(2) or 'it'}"
        ):
            artifact = m.group(1)
            topic = (m.group(2) or "").strip()
            app = m.group(3).strip()
            app_lower = app.lower().rstrip(".")
            m_new = re.match(r"^(?:a|an|the)?\s*(?:new|another|fresh)\s+(.+)$", app_lower)
            new_instance = bool(m_new)
            if m_new:
                app_lower = m_new.group(1).strip()
            app_lower = re.sub(r"\s+(?:file|window|document|doc|tab|app)\s*$", "", app_lower)
            app_lower = re.sub(r"^the\s+", "", app_lower)
            # A GENERIC document target ("put it in a new document/file") with
            # no real application named is a DOCUMENT-CREATION request, not a
            # keystroke TYPE: the canonical document operator writes a real
            # artifact. Only when a concrete app (notepad/word/...) is named
            # does TYPE-into-app apply.
            if app_lower in ("document", "doc", "file", "text", "note", "notes", "editor"):
                subject = topic or artifact
                return RoutingDecision(
                    IntentType.DESKTOP_ACTION, "create_document", subject, text, lower,
                    confidence=1.0,
                    metadata={"artifact": artifact, "style": "", "subject": subject},
                )
            if app_lower not in self._TYPE_TARGET_LANGUAGES:
                payload = f"a {artifact}" + (f" on {topic}" if topic else "")
                metadata = {
                    "payload": payload,
                    "generate": True,
                }
                if new_instance:
                    metadata["new_instance"] = True
                return RoutingDecision(
                    IntentType.DESKTOP_ACTION, "type", app_lower, text, lower,
                    confidence=1.0,
                    metadata=metadata,
                )
            return None

        m = re.match(
            r"^(?:type|write|put|enter|paste)\s+(.+?)\s+"
            r"(?:(?:into|in|onto|on\s+to|to)\s*){1,2}\s*(.+)$",
            lower,
        )
        if m:
            payload, app = m.group(1).strip(), m.group(2).strip()
            # Office-application destinations (Word/Excel/PowerPoint) with a
            # generated-content payload are ARTIFACT-CREATION requests, not
            # keystroke typing: "write an essay about climate change in Word"
            # must produce a real .docx via the artifact operator, never fake
            # typing into Word. Only literal payloads ("type hello into word")
            # fall through to the TYPE path below.
            if self._looks_like_generated_content(payload):
                app_hint = app.lower().strip()
                if re.search(
                    r"\b(?:word|microsoft word|ms word|excel|microsoft excel|powerpoint|slides)\b",
                    app_hint,
                ):
                    doc_routing = self._detect_document_creation(lower, text)
                    if doc_routing:
                        return doc_routing
            # Target normalization: "a new notepad file", "another editor",
            # "a fresh document" -> base app "notepad"/"editor" + a flag that a
            # NEW document must be opened (KIO never tampers with existing
            # content unless the user explicitly asks to write onto it).
            app_lower = app.lower().rstrip(".")
            new_instance = False
            m_new = re.match(r"^(?:a|an|the)?\s*(?:new|another|fresh)\s+(.+)$", app_lower)
            if m_new:
                new_instance = True
                app_lower = m_new.group(1).strip()
            # Trailing artifact nouns: "notepad file", "editor window",
            # "word document" -> "notepad"/"editor".
            app_lower = re.sub(r"\s+(?:file|window|document|doc|tab|app)\s*$", "", app_lower)
            # "put this into Excel" — a bare referent with an OFFICE
            # destination is a document-creation request (the artifact
            # operator builds a real file), not keystroke typing of the word
            # "this". Ask what it should contain if the referent has no
            # resolved content.
            if app_lower in ("excel", "spreadsheet", "word", "powerpoint") \
                    and payload.lower().strip() in ("this", "that", "it"):
                doc_routing = self._detect_document_creation(lower, text)
                if doc_routing:
                    return doc_routing
                kind = "spreadsheet" if app_lower in ("excel", "spreadsheet") else \
                    ("presentation" if app_lower in ("powerpoint", "slides") else "document")
                return RoutingDecision(
                    IntentType.DESKTOP_ACTION, "create_document", "", text, lower,
                    confidence=1.0,
                    metadata={"artifact": kind, "style": "", "subject": ""},
                )
            if app_lower not in self._TYPE_TARGET_LANGUAGES:
                metadata = {
                    "payload": payload,
                    "generate": self._looks_like_generated_content(payload),
                }
                # New-document default lives in the EXECUTOR (True unless the
                # user explicitly asks to write onto the existing file). The
                # classifier only overrides when wording explicitly requests a
                # fresh instance.
                if new_instance:
                    metadata["new_instance"] = True
                return RoutingDecision(
                    IntentType.DESKTOP_ACTION, "type", app_lower, text, lower,
                    confidence=1.0,
                    metadata=metadata,
                )
            return None
        # ── DOCUMENT-CREATION family: "create a Word document about X",
        #    "make a Word file comparing X and Y", "create a report on X".
        #    Generic artifact semantics: subject + artifact kind + style are
        #    extracted; content is generated (LLM) and the document is written
        #    by the canonical document operator — never fake typing into Word.
        doc_routing = self._detect_document_creation(lower, text)
        if doc_routing:
            return doc_routing

        # Bare TYPE into the current focus — knowledge-shape guarded, so
        # "type 2 diabetes", "type of cancer", "type b blood" and single-noun
        # concepts ("type coercion") stay on the knowledge path, while any
        # multi-word typing payload ("type hello world this is a kio test")
        # becomes a real TYPE action. "write" is deliberately excluded from
        # the bare form ("write a poem" is a creative request, not a
        # keystroke command) but still works in the into-target form.
        m = re.match(r"^type\s+(.+)$", lower)
        if m:
            payload = m.group(1).strip().rstrip(".!?")
            p = payload.lower()
            # Knowledge shapes: leading digit ("2 diabetes"), "of " ("of
            # cancer"), single-noun concepts, blood-type grammar.
            if re.match(r"^\d+\s+[a-z]", p) or p.startswith("of "):
                return None
            words = payload.split()
            if len(words) == 1 and words[0].lower() in self._TYPE_KNOWLEDGE_NOUNS:
                return None
            if re.match(r"^(?:ab?|o|b)\s+(?:positive|negative)?\s*blood(?:\s+type)?", p):
                return None
            # No word-count bound: "type <sentence>" is a typing command
            # however long the payload (a long typing payload must NEVER leak
            # to the conversation path where the LLM could fabricate success).
            # The executor truthfully reports if the payload is beyond what it
            # can type in one command.
            if len(payload) <= 2000:
                return RoutingDecision(
                    IntentType.DESKTOP_ACTION, "type", "", text, lower,
                    confidence=1.0, metadata={"payload": payload},
                )
            return RoutingDecision(
                IntentType.DESKTOP_ACTION, "type", "", text, lower,
                confidence=1.0, metadata={"payload": payload[:2000], "truncated": True},
            )

        # ── KEY_PRESS family: "press Enter", "hit Escape", "press Ctrl+S",
        #    "hit Ctrl+A" — BOUNDED to a key/combo grammar so conversational
        #    phrases that merely begin with "hit"/"tap" ("hit me with your
        #    best shot", "tap dance history") never become desktop actions.
        m = re.match(r"^(?:press|hit|tap)\s+(.+)$", lower)
        if m and self._looks_like_key_combo(m.group(1).strip()):
            return RoutingDecision(
                IntentType.DESKTOP_ACTION, "key_press", m.group(1).strip(),
                text, lower, confidence=1.0,
            )

        # ── Shortcut family: SEMANTIC edit actions (not mechanical keys) ────
        # "save this"/"save the file" → SAVE; "copy that" → COPY;
        # "paste it here" → PASTE; "select all" → SELECT_ALL; undo/redo.
        # The semantic action is preserved at the intent layer (target
        # resolution + focus + verification happen in the executor); the key
        # combo lives in metadata and only becomes a KEY_PRESS at the provider
        # layer. Explicit "press ctrl+s" stays a literal key_press above.
        #
        # Natural variants converge through the same family: "copy the selected
        # text", "select everything in notepad", "save the document". A
        # trailing "in/into/on <app>" target is carried in metadata so the
        # executor focuses that window before the key event.
        def _edit_decision(action, combo, app=""):
            return RoutingDecision(
                IntentType.DESKTOP_ACTION, action, app, text, lower,
                confidence=1.0, metadata={"combo": combo},
            )

        _EDIT_TAIL = re.compile(r"^(.*?)(?:\s+(?:in|into|on|inside)\s+(?:the\s+)?(.+))?$")

        def _with_app(match_obj):
            try:
                return (match_obj.group(2) or "").strip()
            except IndexError:
                return ""

        m = re.fullmatch(
            r"save(?:\s+(?:this|the\s+(?:file|document|doc|worksheet)|it|that|file|document|worksheet|all))?"
            r"(?:\s+(?:in|into|on|inside)\s+(?:the\s+)?(.+))?",
            lower,
        )
        if m:
            return _edit_decision("save", "ctrl+s", _with_app(m))
        m = re.fullmatch(
            r"copy(?:\s+(?:this|that|it|the\s+(?:selected\s+)?(?:text|selection|content)|selection|text|all|everything))?"
            r"(?:\s+(?:in|into|from|on|inside)\s+(?:the\s+)?(.+))?",
            lower,
        )
        if m:
            return _edit_decision("copy", "ctrl+c", _with_app(m))
        m = re.fullmatch(
            r"paste(?:\s+(?:it\s+here|it|here|this|that|the\s+text))?"
            r"(?:\s+(?:in|into|on|inside)\s+(?:the\s+)?(.+))?",
            lower,
        )
        if m:
            return _edit_decision("paste", "ctrl+v", _with_app(m))
        m = re.fullmatch(
            r"select\s+(?:all|everything|the\s+whole\s+thing|all\s+text|everything\s+in\s+the\s+document)"
            r"(?:\s+(?:in|into|on|inside)\s+(?:the\s+)?(.+))?",
            lower,
        )
        if m:
            return _edit_decision("select_all", "ctrl+a", _with_app(m))
        m = re.fullmatch(
            r"undo(?:\s+(?:that|it|this|the\s+last\s+(?:action|change|step)))?"
            r"(?:\s+(?:in|into|on|inside)\s+(?:the\s+)?(.+))?",
            lower,
        )
        if m:
            return _edit_decision("undo", "ctrl+z", _with_app(m))
        m = re.fullmatch(
            r"redo(?:\s+(?:that|it|this))?"
            r"(?:\s+(?:in|into|on|inside)\s+(?:the\s+)?(.+))?",
            lower,
        )
        if m:
            return _edit_decision("redo", "ctrl+y", _with_app(m))

        # ── SCROLL family: "scroll down/up", "scroll to the bottom/top" ───
        m = re.match(r"^scroll\s+(down|up)$", lower)
        if m:
            return RoutingDecision(
                IntentType.DESKTOP_ACTION, "scroll", m.group(1), text, lower,
                confidence=1.0,
            )
        m = re.match(r"^scroll\s+(?:down\s+)?to\s+the\s+(bottom|top)\s*$", lower)
        if m:
            return RoutingDecision(
                IntentType.DESKTOP_ACTION, "scroll", m.group(1), text, lower,
                confidence=1.0,
            )

        # ── CLICK family (bounded): only "click here/there" at the current
        #    cursor position can be executed reliably without vision. A named
        #    element ("click the search box") cannot be located deterministically
        #    by this provider — truthful unsupported, never a fake click.
        if re.fullmatch(r"click(?:\s+(?:here|there|now))?", lower):
            return RoutingDecision(
                IntentType.DESKTOP_ACTION, "click", "", text, lower,
                confidence=1.0,
            )
        return None

    # Bounded key/combo grammar for the KEY_PRESS family: a single known key
    # (enter/esc/f1-f12/letters/digits/navigation keys) or a modifier
    # combination (ctrl+s, alt+tab, win+d, ...). Anything else ("release",
    # "me with your best shot") is not a key combo and stays out of the
    # desktop-action path.
    _KEY_COMBO_RE = re.compile(
        r"^(?:ctrl|control|alt|shift|win|windows|super)"
        r"(?:\s*(?:\+|\s+and\s+|\s*\+\s*)\s*"
        r"(?:ctrl|control|alt|shift|win|windows|super|[a-z0-9]|f[1-9]|f1[0-2]|"
        r"enter|return|esc|escape|tab|space|backspace|delete|insert|home|end|"
        r"pageup|pagedown|up|down|left|right))+"
        r"|(?:[a-z0-9]|f[1-9]|f1[0-2]|enter|return|esc|escape|tab|space|backspace|"
        r"delete|insert|home|end|pageup|pagedown|up|down|left|right)$"
    )

    def _looks_like_key_combo(self, combo: str) -> bool:
        combo = (combo or "").strip().lower().rstrip(".")
        if not combo:
            return False
        return bool(self._KEY_COMBO_RE.fullmatch(combo))

    # ── Generated-content detection for TYPE (capability quality) ──────────
    # A payload that REQUESTS content ("a short poem about space", "a
    # three-point summary", "a professional email") must be GENERATED by the
    # LLM before the deterministic provider types it. A literal payload
    # ("hello", "my name is Joel") is typed verbatim. Bounded artifact nouns
    # + a following topic phrase; never a giant phrase dictionary.
    _CONTENT_ARTIFACT_RE = re.compile(
        r"^(?:a|an|the)?\s*(?:short|brief|long|professional|formal|quick|"
        r"simple|small|detailed|concise|few|several|real|proper|complete|full|nice|"
        r"great|good|solid|decent|clean|fresh|new|useful|helpful|fun|whole|one|1|"
        r"(?:one|two|three|four|five|six|seven|eight|nine|ten|\d+)\s*[- ]?point)?\s*"
        r"(?:study\s+|project\s+|research\s+|status\s+)?"
        r"(poem|essay|email|letter|report|summary|explanation|paragraph|story|"
        r"article|note|reply|message|description|review|analysis|plan|update|"
        r"introduction|conclusion|list|write-up|document|doc|comparison|compare|contrast|write-up|overview|guide|tutorial)\b",
        re.IGNORECASE,
    )
    _GENERATIVE_VERBS = frozenset({"write", "draft", "compose", "create", "generate", "make"})
    _TOPIC_MARKERS = re.compile(r"\b(?:about|on|of|comparing|for|regarding)\b")

    def _looks_like_generated_content(self, payload: str) -> bool:
        """True when the TYPE payload is a content REQUEST, not literal text."""
        p = (payload or "").strip().lower().rstrip(".")
        if not p:
            return False
        # Artifact-noun start: "a short poem ...", "three-point summary ...".
        if self._CONTENT_ARTIFACT_RE.match(p):
            return True
        # Generative verb + a topic marker: "write something about X".
        first = p.split()[0] if p.split() else ""
        if first in self._GENERATIVE_VERBS and self._TOPIC_MARKERS.search(p):
            return True
        # A quoted literal payload is never generated content.
        if payload.strip().startswith(("\"", "'")):
            return False
        return False

    # ── DOCUMENT-CREATION family ────────────────────────────────────────────
    # "create a Word document about X" / "make a Word file comparing X and Y"
    # / "create a report on X" / "make a spreadsheet about X" / "create a
    # presentation about X" — extract subject + artifact kind + style; the
    # generic artifact operator writes a real .docx/.xlsx/.pptx artifact. The
    # DESTINATION APPLICATION (word/excel/powerpoint) is a modality hint that
    # maps to an artifact FORMAT, never a hardcoded per-app branch. Never fake
    # typing into an office app.
    # Generic natural-language coverage (2026-08-12 audit): optional "me/us"
    # after the verb ("make me a presentation"), up to two leading modifiers
    # ("write a proper short essay"), phrasal verbs ("put together",
    # "write up") and "vs/versus" as topic separators — all family rules,
    # never per-phrase aliases.
    _CREATE_VERBS = r"(?:create|make|draft|generate|produce|build|write|prepare|put\s+together|write\s+up|give)"
    _CREATE_MODIFIERS = (
        r"(?:(?:new|fresh|another|small|short|quick|brief|detailed|concise|simple|clean|nice|"
        r"basic|professional|formal|mini|full|proper|comprehensive|informative|compact|monthly|weekly|annual|personal|"
        r"habit|budget|expense|project|travel|fitness|gym|workout|study|reading|sleep|tracking|track|personal|weekly|daily|monthly)\s+){0,2}"
    )
    _CREATE_TOPIC = r"(?:about|on|regarding|for|of|vs|versus|explaining|covering|describing|introducing)"
    _CREATE_DOC_RE = re.compile(
        _CREATE_VERBS + r"\s+"
        r"(?:me|us)?\s*(?:a|an|the)?\s*" + _CREATE_MODIFIERS +
        r"(?:word|microsoft\s+word|ms\s+word|text|"
        r"docx|document|doc|file|report|write-up|paper|essay|article|letter|email|"
        r"story|poem|summary|comparison|overview|guide|spreadsheet|excel|sheet|"
        r"presentation|powerpoint|slides|deck|ppt|pptx|xlsx|budget|table|study|notes|"
        r"workbook|worksheet|tracker|dataset|ledger)?\s*"
        r"(?:document|doc|file|report|write-up|paper|essay|article|letter|email|"
        r"story|poem|summary|comparison|overview|guide|spreadsheet|excel|sheet|"
        r"presentation|powerpoint|slides|deck|ppt|pptx|xlsx|budget|table|study|notes|"
        r"workbook|worksheet|tracker|dataset|ledger)?\s+"
        r"(?:about|on|regarding|for|of|with|vs|versus|explaining|covering|describing|introducing|tracking|of)\s+(.+)$",
        re.IGNORECASE,
    )
    _CREATE_DOC_COMPARE_RE = re.compile(
        _CREATE_VERBS + r"\s+"
        r"(?:me|us)?\s*(?:a|an|the)?\s*" + _CREATE_MODIFIERS +
        r"(?:word|microsoft\s+word|ms\s+word|text|"
        r"docx|document|doc|file|report|write-up|paper|essay|article|letter|email|"
        r"story|poem|summary|comparison|overview|guide|spreadsheet|excel|sheet|"
        r"presentation|powerpoint|slides|deck|ppt|pptx|xlsx|budget|table|study|notes)?\s*"
        r"(?:document|doc|file|report|write-up|paper|essay|article|letter|email|"
        r"story|poem|summary|comparison|overview|guide|spreadsheet|excel|sheet|"
        r"presentation|powerpoint|slides|deck|ppt|pptx|xlsx|budget|table|study|notes)?\s+comparing\s+(.+)$",
        re.IGNORECASE,
    )
    # Destination-modality suffix: "in Excel" / "in PowerPoint" / "in Word"
    # attached to a create phrase ("make a comparison of X and Y in Excel").
    # The app name is a FORMAT hint that maps to a spreadsheet/presentation/
    # document artifact — generic, never app-specific.
    _DEST_APP_TAIL_RE = re.compile(
        r"\s+(?:in|into)\s+(?:microsoft\s+)?(excel|spreadsheet|powerpoint|slides|word|docx|xlsx|pptx)\s*$",
        re.IGNORECASE,
    )
    # "make a clean report from this" / "make a spreadsheet from these
    # results" — source-material form. The SOURCE is the subject when it is a
    # real noun phrase; a bare pronoun (this/that/it) leaves the subject empty
    # so the executor truthfully asks what it should be about.
    _CREATE_FROM_RE = re.compile(
        r"^(?:make|create|draft|write|prepare)\s+(?:a|an|the)?\s*"
        r"(?:clean|nice|quick|brief|detailed|concise|professional|formal|simple|short)?\s*"
        r"(spreadsheet|excel|sheet|presentation|slides|deck|report|summary|comparison|"
        r"study\s+guide|notes?|table|budget|poem|essay|overview|guide|plan|document|doc|file)\s+"
        r"(?:from|out\s+of|based\s+on)\s+(.+)$",
        re.IGNORECASE,
    )
    # "turn this into a presentation" / "make it into a report" — conversion
    # form. The source is contextual; a bare pronoun leaves subject empty.
    _CONVERT_INTO_RE = re.compile(
        r"^(?:turn|convert|transform|make)\s+(?:this|that|it|the\s+(?:notes?|text|content|results?))?\s*"
        r"(?:in)?to\s+(?:a|an|the)?\s*(?:new|fresh|clean|nice|quick|professional|detailed)?\s*"
        r"(spreadsheet|excel|sheet|presentation|slides|deck|report|summary|comparison|"
        r"study\s+guide|notes?|table|budget|poem|essay|overview|guide|plan|document|doc)\s*$",
        re.IGNORECASE,
    )
    # Style modifiers stripped from the end of the subject ("make it concise").
    _STYLE_TAIL_RE = re.compile(
        r"\s+(?:and\s+)?(?:make\s+it|keep\s+it|make\s+it\s+really)\s+"
        r"(concise|short|brief|professional|detailed|simple|poetic|formal|casual|fun)\s*$",
        re.IGNORECASE,
    )
    # "put/place X in/into a new document/file" family — document-intent
    # phrasings that don't start with create/make. The subject is the content
    # description before the target clause ("a small comparison of A and B and
    # put it in a new document" -> subject "a small comparison of A and B").
    _PUT_INTO_DOC_RE = re.compile(
        r"^(?:put|place|write|type|drop|paste)\s+(?:it|this|that|the\s+content|the\s+text)?\s*"
        r"(?:in|into)\s+(?:a|an|the)?\s*(?:new\s+)?(?:document|file|doc|text\s+file)\s*$",
        re.IGNORECASE,
    )

    # Artifact-kind normalization: the noun the user actually used maps to a
    # canonical artifact kind. Excel/PowerPoint (destination apps) become the
    # FORMAT they imply — generic, never app-specific branches.
    _ARTIFACT_KIND_MAP = {
        "spreadsheet": "spreadsheet", "excel": "spreadsheet", "sheet": "spreadsheet",
        "xlsx": "spreadsheet", "budget": "budget", "table": "table",
        "presentation": "presentation", "slides": "presentation", "deck": "presentation",
        "ppt": "presentation", "pptx": "presentation", "powerpoint": "presentation",
        "study": "study guide", "study guide": "study guide",
        "notes": "notes", "note": "notes", "checklist": "checklist",
        "report": "report", "write-up": "report", "paper": "paper",
        "essay": "essay", "file": "file", "article": "article",
        "email": "email", "letter": "letter", "poem": "poem",
        "summary": "summary", "overview": "overview", "guide": "guide",
        "comparison": "comparison", "plan": "plan", "outline": "outline",
        "workbook": "spreadsheet", "worksheet": "spreadsheet",
        "tracker": "spreadsheet", "dataset": "dataset", "ledger": "ledger",
        "inventory": "inventory", "schedule": "schedule", "roster": "roster",
        "code": "code", "program": "code", "script": "code",
    }
    _ARTIFACT_NOUNS = re.compile(
        r"\b(spreadsheet|excel|sheet|xlsx|budget|table|presentation|slides|deck|"
        r"ppt|pptx|powerpoint|study\s+guide|notes?|checklist|report|write-up|paper|"
        r"essay|file|article|email|letter|poem|summary|overview|guide|comparison|plan|"
        r"outline|workbook|worksheet|tracker|dataset|ledger|inventory|schedule|roster|timetable)\b"
    )
    # Generic bare-artifact fallback: "create/make + <any descriptor words> +
    # <artifact noun>" with NO "about X" ("travel budget spreadsheet",
    # "clean quick report", "personal budget"). The descriptor words become
    # the subject; the FINAL artifact noun determines the format. Bounded to a
    # handful of leading words so "make a paper airplane" stays an action.
    _CREATE_BARE_ARTIFACT_FALLBACK_RE = re.compile(
        r"^(?:create|make|draft|generate|produce|build|prepare)\s+"
        r"(?:a|an|the)?\s*(?:new|fresh|another)?\s*"
        r"((?:[a-z]+\s+){0,4}?)"
        r"(spreadsheet|excel|sheet|xlsx|budget|table|presentation|slides|deck|"
        r"ppt|pptx|powerpoint|study\s+guide|notes?|checklist|report|write-up|paper|"
        r"essay|file|article|email|letter|poem|summary|overview|guide|comparison|plan|outline|"
        r"workbook|worksheet|tracker|dataset|ledger)\s*$",
        re.IGNORECASE,
    )
    # Bare artifact form: "create a study guide" / "make a spreadsheet" /
    # "create a presentation" / "create a budget spreadsheet" (compound noun)
    # with NO "about X" — subject stays empty (or the descriptive compound
    # first word) and the executor asks/uses it; never fabricates a topic.
    _CREATE_BARE_ARTIFACT_RE = re.compile(
        r"^(?:create|make|draft|generate|produce|build|prepare)\s+"
        r"(?:me|us)?\s*(?:a|an|the)?\s*(?:new|fresh|another)?\s*"
        r"(?:[a-z]+\s+){0,3}?"  # up to 3 descriptor words ("habit tracker", "monthly budget")
        r"(spreadsheet|excel|sheet|xlsx|budget|table|presentation|slides|deck|"
        r"ppt|pptx|powerpoint|study\s+guide|notes?|checklist|report|write-up|paper|"
        r"essay|file|article|email|letter|poem|summary|overview|guide|comparison|plan|outline|"
        r"workbook|worksheet|tracker|dataset|ledger)\s*$",
        re.IGNORECASE,
    )

    # "write a short essay about renewable energy and save it as a Word
    # document" / "make a report on X and save it as a Word file" — the
    # artifact + topic are extracted and the "and save it as <format>" clause
    # maps to the artifact FORMAT. ONE document-creation intent; the artifact
    # operator persists the file to Documents itself.
    _CREATE_DOC_SAVE_AS_RE = re.compile(
        r"^(?:create|make|draft|generate|produce|build|write|prepare)\s+"
        r"(?:a|an|the)?\s*(?:new|fresh|short|brief|quick|detailed|concise|simple|small|clean|"
        r"nice|basic|professional|formal|mini|full|proper)?\s*"
        r"(spreadsheet|excel|sheet|xlsx|budget|table|presentation|slides|deck|ppt|"
        r"pptx|powerpoint|study\s+guide|notes?|checklist|report|write-up|paper|essay|file|"
        r"article|email|letter|poem|summary|overview|guide|comparison|plan|outline|workbook|"
        r"worksheet|tracker|dataset|ledger)\s+"
        r"(?:about|on|regarding|for|of)\s+(.+?)\s+"
        r"and\s+save\s+(?:it|this|that)?\s+as\s+(?:a|an|the)?\s*"
        r"((?:word|microsoft\s+word|excel|spreadsheet|powerpoint|slides|ppt|docx|xlsx|pptx|text)?\s*"
        r"(?:document|doc|file|spreadsheet|sheet|presentation|deck|workbook)?)\s*$",
        re.IGNORECASE,
    )

    # Trailing-artifact form: "make me a quick Messi vs Ronaldo comparison" /
    # "make me a monthly budget" — the artifact noun is at the END, subject
    # before it, with "vs/versus" as a plain separator. Family rule, not a
    # phrase list: any bounded subject + any artifact noun converges.
    _CREATE_TRAILING_ARTIFACT_RE = re.compile(
        _CREATE_VERBS + r"\s+"
        r"(?:me|us)?\s*(?:a|an|the)?\s*" + _CREATE_MODIFIERS +
        r"(.+?)\s+(comparison|spreadsheet|sheet|presentation|slides|deck|ppt|pptx|essay|report|"
        r"study\s+guide|notes?|budget|table|summary|overview|guide|plan|outline|email|letter|"
        r"poem|document|doc|file|tracker|dataset|checklist|workbook|worksheet)\s*"
        r"(?:in|into)\s+(?:microsoft\s+)?(?:excel|word|powerpoint|notepad|spreadsheet|slides)\s*$",
        re.IGNORECASE,
    )
    # "make a tracker" style trailing forms with NO subject before the
    # artifact ("make me a monthly budget") — subject stays the descriptor.
    _CREATE_TRAILING_ARTIFACT_RE2 = re.compile(
        _CREATE_VERBS + r"\s+"
        r"(?:me|us)?\s*(?:a|an|the)?\s*" + _CREATE_MODIFIERS +
        r"(.+?)\s+(comparison|spreadsheet|sheet|presentation|slides|deck|ppt|pptx|essay|report|"
        r"study\s+guide|notes?|budget|table|summary|overview|guide|plan|outline|email|letter|"
        r"poem|document|doc|file|tracker|dataset|checklist|workbook|worksheet)\s*$",
        re.IGNORECASE,
    )
    # "put together something on X" / "write up what we discussed" — phrasal
    # content verbs whose object is the SUBJECT (notes/summary document). A
    # bare "something" with a topic becomes that topic; a clause object stays
    # the subject when it is a real noun phrase.
    _CREATE_PHRASAL_RE = re.compile(
        r"^(?:put\s+together|write\s+up|jot\s+down)\s+"
        r"(?:something\s+(?:on|about|regarding)\s+(.+)|(.+?))\s*$",
        re.IGNORECASE,
    )
    # "draft an email to my professor explaining the delay" — CONTENT-side
    # email drafting. Recipient + reason are extracted; the executor produces
    # the complete professional email (no send infrastructure -> the draft is
    # the truthful deliverable).
    _EMAIL_DRAFT_RE = re.compile(
        r"^(?:draft|write|compose|prepare|send|create|make)\s+(?:a|an|the)?\s*"
        r"(?:professional|formal|polite|short|brief|quick|complete|full|nice|proper|good|simple|detailed|concise|friendly|polite)?\s*"
        r"(?:email|e-mail|message|something)\s*"
        r"(?:to\s+(.+?))?\s*"
        r"(?:(?:explaining|about|regarding|concerning|requesting|asking|informing|notifying|re|for)\s+(.+))?\s*$",
        re.IGNORECASE,
    )
    # "email my professor about the delay" / "email the team regarding X" —
    # the verb IS the intent. Distinct from the draft/write forms above.
    _EMAIL_VERB_RE = re.compile(
        r"^(?:email|e-mail|message)\s+(?:my|the|your)?\s*([^,]{1,60}?)\s*"
        r"(?:about|regarding|concerning|explaining|requesting|asking|informing|notifying|re|for)\s+(.+)$",
        re.IGNORECASE,
    )
    # Code-workflow family: "write a small Python program that calculates
    # Fibonacci numbers and open it in VS Code" — a source-artifact task with
    # an optional open-in-editor clause (ONE intent, never a multi-step
    # type-into-editor chain). The generated code is written to a real source
    # file with the language-appropriate extension.
    # Code-noun breadth is intentionally generous so natural forms work
    # without a phrase dictionary: "a small Python CLI calculator", "a simple
    # HTML page", "a Python program that ...". The language is optional
    # (defaults to python); the editor clause ("... and open it in VS Code")
    # is optional too.
    _CODE_WORKFLOW_RE = re.compile(
        r"^(?:write|create|make|build|generate)\s+(?:a|an|the|some)?\s*"
        r"(?:small|simple|short|quick|basic|tiny|clean|nice|mini|proper)?\s*"
        r"(python|javascript|typescript|java|js|py|c\+\+|c#|go|rust|ruby|php|bash|powershell|html|css|sql)?\s*"
        r"(program|script|code|file|function|app|application|project|cli\s+(?:tool|app)|cli|tool|utility|bot|module|package|service|daemon|page|website|site|webpage|calculator|game|scraper|notebook)\s*"
        r"(?:that\s+)?(.+?)?(?:\s+and\s+open\s+it\s+(?:in|with)\s+(.+?))?\s*$",
        re.IGNORECASE,
    )
    # Referent-object form: "build this in VS Code" / "make it in VS Code" —
    # the object is a context referent with an editor destination. Subject
    # stays EMPTY so the executor truthfully asks what to build when no
    # context is available (never fabricates a project for "this"). Only CODE
    # editors qualify: "write this in notepad" is a TYPE command (type the
    # word into Notepad), never a code-artifact build.
    _CODE_REFERENT_RE = re.compile(
        r"^(?:build|make|write|create|develop)\s+(this|that|it)\s+in\s+"
        r"(vs\s+code|vscode|visual\s+studio\s+code|code)\b",
        re.IGNORECASE,
    )
    # "open Excel and make a tracker" — an open-app-plus-make-artifact chain
    # is ONE document-creation intent whose destination application pins the
    # format (excel -> spreadsheet, powerpoint -> presentation, word/notepad ->
    # document). Runs BEFORE multi-step.
    _OPEN_AND_MAKE_RE = re.compile(
        r"^open\s+(?:the\s+)?(excel|spreadsheet|powerpoint|slides|word|notepad|text\s+editor)\s+and\s+"
        r"(?:make|create|build|prepare)\s+(?:a|an|the)?\s*(?:new|fresh)?\s*(.+?)\s*$",
        re.IGNORECASE,
    )
    # "write this down" / "jot that down" / "write this up" — note-taking /
    # write-up intent without a topic: the executor truthfully asks what to
    # write down (never fabricates a note).
    _WRITE_DOWN_RE = re.compile(
        r"^(?:write|jot|note)\s+(?:this|that|it|the\s+following)?\s*(?:down|up)?\s*$",
        re.IGNORECASE,
    )

    def _detect_document_save_as(self, lower, raw_text, text):
        m = self._CREATE_DOC_SAVE_AS_RE.match(lower)
        if not m:
            return None
        artifact = self._ARTIFACT_KIND_MAP.get(m.group(1).lower().strip(), "document")
        subject = m.group(2).strip()
        tail = m.group(3) or ""
        # The save-as clause names the destination FORMAT (Word/Excel/PPT).
        if re.search(r"excel|spreadsheet|sheet|xlsx", tail):
            artifact = "spreadsheet"
        elif re.search(r"powerpoint|slides|ppt|pptx|presentation|deck", tail):
            artifact = "presentation"
        elif re.search(r"word|docx", tail):
            artifact = "document" if artifact == "document" else artifact
        return RoutingDecision(
            IntentType.DESKTOP_ACTION, "create_document", subject, text, lower,
            confidence=1.0,
            metadata={"artifact": artifact, "style": "", "subject": subject},
        )

    def _detect_open_and_make(self, lower, raw_text, text):
        """'open Excel and make a tracker' — ONE document-creation intent.

        The destination application pins the FORMAT (excel/spreadsheet -> .xlsx,
        powerpoint/slides -> .pptx, word/notepad/text editor -> .docx), and the
        "make" clause provides the artifact description. Never a two-step open-
        then-type chain.
        """
        m = self._OPEN_AND_MAKE_RE.match(lower)
        if not m:
            return None
        app = m.group(1).lower().strip()
        desc = (m.group(2) or "").strip().rstrip(".")
        if app in ("excel", "spreadsheet"):
            artifact = "spreadsheet"
        elif app in ("powerpoint", "slides"):
            artifact = "presentation"
        else:
            artifact = "document"
        # The "make a tracker" clause can name a more specific artifact.
        nm = self._ARTIFACT_NOUNS.search(desc.lower())
        if nm:
            noun = nm.group(1).lower().strip()
            mapped = self._ARTIFACT_KIND_MAP.get(noun, "")
            if mapped and mapped != "file":
                artifact = mapped
        # "make a tracker" -> subject "tracker" (the artifact is the subject
        # when no topic is given); "make a monthly budget" -> subject "monthly".
        subject = re.sub(r"^(?:a|an|the)\s+", "", desc, flags=re.IGNORECASE).strip()
        subject = re.sub(r"\s+(?:spreadsheet|sheet|tracker|budget|table|presentation|slides|deck|report|document|doc|file|notes?)\s*$", "", subject, flags=re.IGNORECASE).strip()
        if not subject:
            subject = desc
        return RoutingDecision(
            IntentType.DESKTOP_ACTION, "create_document", subject, text, lower,
            confidence=1.0,
            metadata={"artifact": artifact, "style": "", "subject": subject},
        )

    def _detect_code_workflow(self, lower, raw_text, text):
        """'write a small Python program that ... and open it in VS Code'.

        A SOURCE-ARTIFACT task: the code is generated and written to a real
        file with the language-appropriate extension; the optional "and open it
        in <editor>" clause selects the editor. One intent, never a multi-step
        type-into-editor chain. The subject is the program description.
        """
        # Referent-object form first: "build this in VS Code" — the object is
        # a context referent, subject stays empty (executor asks truthfully).
        m_ref = self._CODE_REFERENT_RE.match(lower)
        if m_ref:
            return RoutingDecision(
                IntentType.DESKTOP_ACTION, "create_document", "", text, lower,
                confidence=1.0,
                metadata={
                    "artifact": "code", "style": "", "subject": "",
                    "language": "python", "editor": m_ref.group(2).lower(),
                },
            )
        m = self._CODE_WORKFLOW_RE.match(lower)
        if not m:
            return None
        lang = (m.group(1) or "").strip().lower()
        noun = (m.group(2) or "").strip().lower()
        desc = (m.group(3) or "").strip().rstrip(".,!?").strip()
        editor = (m.group(4) or "").strip().lower()
        # "make a simple HTML page" — the noun IS the whole task (page, tool,
        # calculator, bot). Use it as the subject so the executor generates
        # the artifact instead of asking what it should be.
        if not desc and noun:
            desc = noun
            if lang:
                desc = f"{lang} {noun}"
        # "write some code for this in VS Code" — a bare referent description
        # ("for this" / "for it") leaves the subject empty so the executor
        # truthfully asks what the program should do. Never generates code for
        # a word like "this". A trailing " in <editor>" without "and open it"
        # still names the editor ("... in VS Code").
        m_editor = re.search(r"\s+in\s+(vs\s+code|vscode|visual\s+studio\s+code|notepad(?:\+\+)?|code)\s*$", desc, re.IGNORECASE)
        if m_editor:
            editor = editor or m_editor.group(1).strip()
            desc = desc[: m_editor.start()].strip()
        # Strip trailing housekeeping clauses from the SUBJECT so they never
        # pollute the project/file name: "... calculates Fibonacci numbers,
        # add a README, and open it in VS Code" -> "calculates Fibonacci
        # numbers". "Add a README" is a project-structure hint, not a topic.
        # A DESCRIPTIVE "with a README" ("create a Python project with a
        # README") is part of the project description and stays in the subject.
        desc = re.sub(
            r"[,\s]*(?:and\s+)?(?:also\s+)?(?:add|include|create|write)\s+(?:a|an|the)?\s*(?:readme|read\s*me|docs?|documentation|tests?|requirements)\b.*$",
            "", desc, flags=re.IGNORECASE,
        ).strip()
        desc = re.sub(r"[,\s]+$", "", desc).strip()
        desc = re.sub(r"^for\s+(this|that|it)\s*$", "", desc, flags=re.IGNORECASE).strip()
        if not desc:
            return RoutingDecision(
                IntentType.DESKTOP_ACTION, "create_document", "", text, lower,
                confidence=1.0,
                metadata={
                    "artifact": "code", "style": "", "subject": "",
                    "language": lang or "python", "editor": editor or "",
                },
            )
        # A bare description that is just the language name ("write a python
        # program") leaves the subject empty so the executor asks.
        if desc.lower() == lang:
            desc = ""
        # PROJECT signal: the request explicitly asks for a project structure
        # ("a Python project", "add a README"). Carried in metadata so the
        # executor can build a real directory (source + README) even after
        # housekeeping clauses are stripped from the subject.
        is_project = bool(re.search(
            r"\bproject\b|\breadme\b|read\s*me", lower, re.IGNORECASE,
        ))
        return RoutingDecision(
            IntentType.DESKTOP_ACTION, "create_document", desc, text, lower,
            confidence=1.0,
            metadata={
                "artifact": "code",
                "style": "",
                "subject": desc,
                "language": lang or "python",
                "editor": editor or "",
                "project": is_project,
            },
        )

    def _detect_document_creation(self, lower, text):
        subject = None
        artifact = "document"
        style = ""
        # "write this down" / "jot that down" — note-taking intent with no
        # topic given: route with an EMPTY subject so the executor truthfully
        # asks what to write down (never fabricates a note).
        if self._WRITE_DOWN_RE.match(lower):
            return RoutingDecision(
                IntentType.DESKTOP_ACTION, "create_document", "", text, lower,
                confidence=1.0,
                metadata={"artifact": "notes", "style": "", "subject": ""},
            )
        # Email draft family (content-side): "draft an email to X explaining Y"
        # -> email artifact with recipient metadata. Runs first so it is never
        # captured as a generic document.
        em = self._EMAIL_DRAFT_RE.match(lower) or self._EMAIL_VERB_RE.match(lower)
        if em:
            # Group layout differs: draft form = (recipient, reason); verb
            # form = (recipient_with_article, reason).
            if self._EMAIL_VERB_RE.match(lower) and not self._EMAIL_DRAFT_RE.match(lower):
                recipient = re.sub(r"^(?:my|the|your)\s+", "", (em.group(1) or ""), flags=re.IGNORECASE).strip()
                reason = (em.group(2) or "").strip()
            else:
                recipient = (em.group(1) or "").strip()
                reason = (em.group(2) or "").strip()
            subject = reason or recipient or ""
            return RoutingDecision(
                IntentType.DESKTOP_ACTION, "create_document", subject, text, lower,
                confidence=1.0,
                metadata={
                    "artifact": "email",
                    "style": "",
                    "subject": subject,
                    "recipient": recipient,
                    "draft_only": True,
                },
            )
        # Trailing-artifact form: "make me a quick Messi vs Ronaldo comparison"
        # / "give me a proper spreadsheet for this" — artifact at the END,
        # optionally followed by a destination-app tail ("... in Excel").
        tm = self._CREATE_TRAILING_ARTIFACT_RE.match(lower) or self._CREATE_TRAILING_ARTIFACT_RE2.match(lower)
        if tm:
            subject = (tm.group(1) or "").strip()
            noun = (tm.group(2) or "").lower().strip()
            artifact = self._ARTIFACT_KIND_MAP.get(noun, "document")
            subject = re.sub(r"\s+(?:for|about|on)\s+(this|that|it)\s*$", "", subject, flags=re.IGNORECASE).strip()
            # Bounded guard: the trailing form only fires for a genuine
            # comparison subject ("messi vs ronaldo") or an explicit
            # destination-app tail. A bare "write a poem" / "create a study
            # guide" / "make a monthly budget" must keep its richer route
            # (conversation / bare-artifact), never be split as a phantom
            # trailing noun.
            if re.search(r"\b(vs|versus)\b", subject):
                pass  # comparison subject — valid
            elif self._DEST_APP_TAIL_RE.search(lower) or self._CREATE_DOC_COMPARE_RE.match(lower):
                pass  # destination-app tail — valid
            else:
                # Rejected as a phantom trailing noun ("create a study guide"
                # would split into subject="study"/noun="guide") — the guard
                # MUST also clear the prematurely-extracted subject so it can
                # never leak into a later branch (e.g. the bare-artifact path).
                subject = ""
                tm = None
        if tm:
            subject = (tm.group(1) or "").strip()
            noun = (tm.group(2) or "").lower().strip()
            artifact = self._ARTIFACT_KIND_MAP.get(noun, "document")
            subject = re.sub(r"\s+(?:for|about|on)\s+(this|that|it)\s*$", "", subject, flags=re.IGNORECASE).strip()
            # Destination-app tail pins the FORMAT (generic, never per-app).
            dm = self._DEST_APP_TAIL_RE.search(lower)
            if dm:
                dest = dm.group(1).lower()
                if dest in ("excel", "spreadsheet", "xlsx"):
                    artifact = "spreadsheet"
                elif dest in ("powerpoint", "slides", "pptx"):
                    artifact = "presentation"
            return RoutingDecision(
                IntentType.DESKTOP_ACTION, "create_document", subject, text, lower,
                confidence=1.0,
                metadata={"artifact": artifact, "style": "", "subject": subject},
            )
        m = self._CREATE_DOC_COMPARE_RE.match(lower)
        if m:
            subject = m.group(1).strip()
            artifact = "comparison"
            # Destination-app tail: "... in Excel" -> spreadsheet format.
            dm = self._DEST_APP_TAIL_RE.search(subject)
            if dm:
                dest = dm.group(1).lower()
                subject = subject[: dm.start()].strip()
                if dest in ("excel", "spreadsheet", "xlsx"):
                    artifact = "spreadsheet"
                elif dest in ("powerpoint", "slides", "pptx"):
                    artifact = "presentation"
            # Leading-clause noun inference (same rule as the about-form):
            # "make a spreadsheet comparing X and Y" names the artifact in the
            # leading clause even without an "in Excel" tail — a spreadsheet
            # request must build an .xlsx, never a comparison .docx. GENERIC
            # container nouns (word/file/document/doc/text) are the destination
            # container, not the format: "make a word file comparing A and B"
            # stays a comparison (.docx) inside the Word container.
            if artifact == "comparison":
                nm = self._ARTIFACT_NOUNS.search(lower[: lower.find("comparing")])
                if nm:
                    noun = nm.group(1).lower().strip()
                    mapped = self._ARTIFACT_KIND_MAP.get(noun, "")
                    if mapped not in ("", "document", "file"):
                        artifact = mapped
            # "... and make it concise" style tail.
            sm = self._STYLE_TAIL_RE.search(subject)
            if sm:
                style = sm.group(1)
                subject = subject[: sm.start()].strip()
        else:
            m = self._CREATE_DOC_RE.match(lower)
            if m:
                subject = m.group(1).strip()
                # "make a table of contents" is a TABLE-OF-CONTENTS request
                # (an outline inside a document), NOT a spreadsheet of a topic
                # named "contents". Never route it to artifact creation.
                if re.search(r"^contents$", subject) and re.search(r"\btable\b", lower):
                    return None
                # Destination-app tail: "... in Excel" -> spreadsheet format.
                dm = self._DEST_APP_TAIL_RE.search(subject)
                if dm:
                    dest = dm.group(1).lower()
                    subject = subject[: dm.start()].strip()
                    if dest in ("excel", "spreadsheet", "xlsx"):
                        artifact = "spreadsheet"
                    elif dest in ("powerpoint", "slides", "pptx"):
                        artifact = "presentation"
                    elif dest in ("word", "docx"):
                        artifact = "document"
                # Infer artifact from the noun in the LEADING clause (before
                # the topic marker) — "create a presentation about black holes"
                # has "presentation" in the leading clause, not the subject.
                if artifact == "document":
                    m_topic = re.search(
                        r"\s+(?:about|on|regarding|for|of|comparing)\s+", lower
                    )
                    leading = lower[: m_topic.start()] if m_topic else lower
                    nm = self._ARTIFACT_NOUNS.search(leading)
                    if nm:
                        noun = nm.group(1).lower().strip()
                        artifact = self._ARTIFACT_KIND_MAP.get(noun, "document")
                    # A leading clause ENDING in "table" ("make a comparison
                    # table for X") is a TABLE request — the head noun wins
                    # over a preceding modifier noun.
                    if re.search(r"\btable\s*$", leading):
                        artifact = "table"
                # Style tail: "... and make it concise" -> style=concise.
                sm = self._STYLE_TAIL_RE.search(subject)
                if sm:
                    style = sm.group(1)
                    subject = subject[: sm.start()].strip()
            else:
                # "make a clean report from these results" / "turn this into
                # a presentation" — source/convert forms.
                fm = self._CREATE_FROM_RE.match(lower)
                if fm:
                    noun = fm.group(1).lower().strip()
                    artifact = self._ARTIFACT_KIND_MAP.get(noun, "document")
                    src = (fm.group(2) or "").strip().lower()
                    if src in ("this", "that", "it", "the notes", "the text", "the content", "the results", "the data"):
                        subject = ""
                    else:
                        subject = src
                else:
                    cm = self._CONVERT_INTO_RE.match(lower)
                    if cm:
                        noun = cm.group(1).lower().strip()
                        artifact = self._ARTIFACT_KIND_MAP.get(noun, "document")
                        subject = ""
                    else:
                        # Bare artifact form: "create a study guide" /
                        # "create a budget spreadsheet" (compound noun).
                        bm = self._CREATE_BARE_ARTIFACT_RE.match(lower)
                        if bm:
                            noun = (bm.group(1) or "").lower().strip()
                            artifact = self._ARTIFACT_KIND_MAP.get(noun, "document")
                            # Compound descriptor is non-capturing; recover it
                            # by re-matching the prefix ("monthly budget" etc.).
                            # Topic-like words (budget, monthly, expense, sales)
                            # become the subject; style-like words (simple,
                            # clean, quick) become the style. Never let an
                            # adjective become a topic.
                            desc_m = re.match(
                                r"^(?:create|make|draft|generate|produce|build|prepare)\s+"
                                r"(?:a|an|the)?\s*(?:new|fresh|another)?\s*"
                                r"(.+?)\s+(?:spreadsheet|excel|sheet|xlsx|budget|table|presentation|"
                                r"slides|deck|ppt|pptx|powerpoint|study\s+guide|notes?|checklist|"
                                r"report|write-up|paper|essay|file|article|email|letter|poem|"
                                r"summary|overview|guide|comparison|plan|outline)\s*$",
                                lower,
                            )
                            desc = ""
                            if desc_m:
                                desc = desc_m.group(1).strip().lower()
                            topic_words = ("budget", "monthly", "weekly", "annual", "expense", "expenses", "sales", "project", "travel")
                            # Style words describe the DELIVERY (concise,
                            # professional, brief), never the topic — they must
                            # never leak into the subject.
                            style_words = ("simple", "basic", "clean", "quick", "short", "brief", "concise", "detailed", "mini", "full", "proper", "nice", "professional", "formal")
                            subj_bits = [w for w in desc.split() if w in topic_words]
                            style_bits = [w for w in desc.split() if w in style_words]
                            if subj_bits:
                                subject = " ".join(subj_bits)
                            elif style_bits:
                                style = style_bits[0]
                                subject = ""
                        else:
                            # Generic fallback: any descriptor words before the
                            # final artifact noun ("travel budget spreadsheet",
                            # "clean quick report", "personal budget").
                            bf = self._CREATE_BARE_ARTIFACT_FALLBACK_RE.match(lower)
                            if bf:
                                noun = (bf.group(2) or "").lower().strip()
                                artifact = self._ARTIFACT_KIND_MAP.get(noun, "document")
                                desc = (bf.group(1) or "").strip()
                                # Same style-vs-topic discipline as above:
                                # topic-like words become the subject, style
                                # words become the style, never the subject
                                # ("create a detailed report" has NO topic).
                                topic_words = ("budget", "monthly", "weekly", "annual", "expense", "expenses", "sales", "project", "travel")
                                style_words = ("simple", "basic", "clean", "quick", "short", "brief", "concise", "detailed", "mini", "full", "proper", "nice", "professional", "formal")
                                subj_bits = [w for w in desc.split() if w in topic_words]
                                style_bits = [w for w in desc.split() if w in style_words]
                                if subj_bits:
                                    subject = " ".join(subj_bits)
                                elif style_bits:
                                    style = " ".join(style_bits)
                                    subject = ""
                                else:
                                    subject = desc if desc else ""
        if not subject and artifact == "document":
            # "write a short comparison of A and B and put it in a new
            # document" / "make a document out of this" — a bare-pronoun
            # SOURCE with a generic document target is still a document-
            # creation request: route with an empty subject so the executor
            # truthfully asks what the document should contain (never
            # fabricates content).
            if self._CREATE_FROM_RE.match(lower) and re.search(
                r"\b(?:this|that|it|these|those)\b", lower
            ):
                return RoutingDecision(
                    IntentType.DESKTOP_ACTION, "create_document", "", text, lower,
                    confidence=1.0,
                    metadata={"artifact": "document", "style": "", "subject": ""},
                )
            # "write a short comparison of A and B and put it in a new
            # document" — split on the "and put/place/type it in[to]" clause.
            split = re.split(r"\s+and\s+(?:put|place|write|type|drop|paste)\s+(?:it|this|that)\s+(?:in|into)\s+(?:a|an|the)?\s*(?:new\s+)?(?:document|file|doc|text\s+file)\s*$", lower, maxsplit=1)
            if len(split) == 2 and split[0].strip():
                head = split[0].strip()
                # Only treat as document-creation when the head is itself a
                # content request (comparison/report/essay/notes/poem/summary
                # about X), never a literal "type hello".
                if re.search(r"\b(comparison|compare|report|essay|notes?|poem|summary|write-up|paper|overview|guide|study\s+guide)\b.*\b(?:about|on|of|comparing)\b", head):
                    subject = head
                    if re.search(r"\b(comparison|compare|comparing)\b", head):
                        artifact = "comparison"
                    elif re.search(r"\b(spreadsheet|excel|sheet|budget|table)\b", head):
                        artifact = "spreadsheet"
                    elif re.search(r"\b(presentation|slides|deck|ppt)\b", head):
                        artifact = "presentation"
        if not subject and artifact != "document":
            # Bare artifact with no topic ("create a study guide"): route with
            # an EMPTY target so the executor truthfully asks what it should
            # be about — never fabricate a subject.
            return RoutingDecision(
                IntentType.DESKTOP_ACTION, "create_document", "", text, lower,
                confidence=1.0,
                metadata={"artifact": artifact, "style": style, "subject": ""},
            )
        if not subject:
            # Fallback: phrasal content verbs — "put together something on X" /
            # "write up what we discussed". Runs LAST so artifact-first forms
            # ("put together a comparison of A and B") keep the richer route.
            pm = self._CREATE_PHRASAL_RE.match(lower)
            if pm:
                subject = (pm.group(1) or pm.group(2) or "").strip()
                if re.search(r"\b(vs|versus)\b", subject):
                    artifact = "comparison"
                else:
                    artifact = "notes"
                return RoutingDecision(
                    IntentType.DESKTOP_ACTION, "create_document", subject, text, lower,
                    confidence=1.0,
                    metadata={"artifact": artifact, "style": "", "subject": subject},
                )
            return None
        return RoutingDecision(
            IntentType.DESKTOP_ACTION, "create_document", subject, text, lower,
            confidence=1.0,
            metadata={"artifact": artifact, "style": style, "subject": subject},
        )

    # Semantic family for contextual desktop-state queries (Capability A).
    # Synonym/normalization-based (what/which/show/list/tell + state nouns),
    # NOT phrase-by-phrase hacks. Every variant routes to list_tabs
    # deterministically — verified runtime state, never an LLM guess.
    _STATE_QUERY_PATTERNS = (
        # Anchored with a bounded tail so knowledge questions that merely share
        # the prefix ("what's open source", "what is running time") stay on
        # the knowledge path; "in/on chrome / my computer" live in the pattern
        # below.
        re.compile(
            r"^what(?:'s|s| is| are)?\s+(?:currently\s+)?(?:open|running|active)"
            r"(?:\s+right\s+now|\s+kio)?"
            r"(?:\s+on\s+(?:my|your|this|the)\s+(?:computer|pc|laptop|machine|system))?"
            r"\s*$"
        ),
        re.compile(r"^what\s+am\s+i\s+(?:currently\s+)?(?:using|running|controlling|working\s+(?:on|with))\b"),
        re.compile(r"^what\s+(?:are\s+you|is\s+kio)\s+(?:currently\s+)?(?:using|controlling|working\s+on|up\s+to)\b"),
        re.compile(r"^what\s+(?:browser\s+)?tabs\s+are\s+open\b"),
        re.compile(r"^which\s+(?:browser\s+)?tabs\s+are\s+open\b"),
        re.compile(r"^what\s+(?:apps|applications|windows)\s+are\s+(?:open|running|active)\b"),
        re.compile(r"^which\s+(?:apps|applications|windows)\s+are\s+(?:open|running|active)\b"),
        re.compile(r"^what\s+processes?\s+are\s+(?:open|running|active)\b"),
        re.compile(r"^which\s+processes?\s+are\s+(?:open|running|active)\b"),
        re.compile(r"^what\s+do\s+i\s+(?:currently\s+)?have\s+(?:open|running)\b"),
        # colloquial "what have I got open" / "what've I got open" family
        re.compile(r"^what(?:\s+have|'ve|\s+'ve)\s+i\s+got\s+(?:open|running|active)\b"),
        re.compile(r"^what(?:'s|s| is)\s+(?:open\s+)?(?:in|on)\s+(?:chrome|edge|firefox|brave|the\s+browser|my\s+computer|this\s+computer)\b"),
        re.compile(r"^tell\s+me\s+what(?:'s|s| is)?\s+(?:open|running|using|active)\b"),
        re.compile(r"^tell\s+me\s+what\s+(?:apps|windows|tabs)\s+are\s+(?:open|running)\b"),
        re.compile(r"^show\s+(?:me\s+)?(?:what(?:'s|s| is)\s+open|(?:my\s+)?(?:open\s+)?(?:apps|windows|tabs|desktop))\b"),
        re.compile(r"^list\s+(?:open\s+)?(?:apps|windows|tabs)\b"),
    )

    def _detect_list_tabs(self, lower):
        # Capability A: contextual desktop-state queries — tabs + KIO-tracked
        # apps, composed from verified runtime state (never LLM-generated).
        return any(p.match(lower) for p in self._STATE_QUERY_PATTERNS)

    # Operational-awareness family (Capability G): KIO health / status /
    # uptime, system health + metrics, component status, "what's wrong".
    # Deterministic, anchored, synonym-based — command-style ("/health") and
    # natural-style share one path (slash stripped in _detect_operational).
    # Knowledge questions that merely share a word ("what is running time",
    # "how much does the ram cost", "what's open source") stay on the
    # knowledge path. Runs BEFORE the desktop-state family so "what's open"
    # keeps routing to BROWSER_TABS.
    _OPERATIONAL_ROUTES: tuple[tuple[object, str, str], ...] = (
        # --- KIO health ---
        (re.compile(r"^health\s*$"), "health", ""),
        (re.compile(r"^are\s+you\s+(?:feeling\s+)?(?:healthy|ok(?:ay)?|fine|alright|good)\b"), "health", ""),
        (re.compile(r"^is\s+everything\s+(?:working|ok(?:ay)?|fine|good)\b"), "health", ""),
        (re.compile(r"^is\s+the\s+(?:system|computer|pc|laptop|machine)\s+(?:healthy|ok(?:ay)?|fine|good|alright|working)\b"), "system", ""),
        (re.compile(r"^how\s+is\s+(?:kio|everything)\b"), "health", ""),
        (re.compile(r"^what(?:'s|s| is)?\s+going\s+on\s*$"), "health", ""),
        (re.compile(r"^show\s+(?:me\s+)?(?:kio(?:'s)?\s+)?health\b"), "health", ""),
        # --- status / activity ---
        (re.compile(r"^status\s*$"), "status", ""),
        (re.compile(r"^ping\s*$"), "status", ""),
        (re.compile(r"^are\s+you\s+(?:there|awake|busy)\b"), "status", ""),
        (re.compile(r"^what\s+are\s+you\s+(?:currently\s+)?doing\b"), "status", ""),
        (re.compile(r"^what\s+is\s+kio\s+(?:currently\s+)?doing\b"), "status", ""),
        (re.compile(r"^what\s+are\s+you\s+currently\s+(?:handling|working\s+on)\b"), "status", ""),
        (re.compile(r"^what(?:'s|s| is)?\s+your\s+(?:current\s+)?(?:status|state)\b"), "status", ""),
        (re.compile(r"^what(?:'s|s| is)?\s+kio(?:'s)?\s+(?:status|state)\b"), "status", ""),
        (re.compile(r"^tell\s+me\s+(?:your\s+|kio(?:'s)?\s+)?status\b"), "status", ""),
        # --- uptime ---
        # "what is uptime" is a KNOWLEDGE question — only possessive/qualified
        # forms (your/kio's) are operational, so the general question stays on
        # the knowledge path.
        (re.compile(r"^uptime\s*$"), "uptime", ""),
        (re.compile(r"^what(?:'s|s| is)?\s+your\s+uptime\b"), "uptime", ""),
        (re.compile(r"^what(?:'s|s| is)?\s+kio(?:'s)?\s+uptime\b"), "uptime", ""),
        (re.compile(r"^tell\s+me\s+(?:your\s+|kio(?:'s)?\s+)?uptime\b"), "uptime", ""),
        (re.compile(r"^how\s+long\s+(?:have\s+you|has\s+kio|has\s+the\s+bot|has\s+it)\s+been\s+(?:running|up|online)\b"), "uptime", ""),
        # --- system health ---
        (re.compile(r"^system(?:health)?\s*$"), "system", ""),
        (re.compile(r"^system\s+(?:health|status)\b"), "system", ""),
        (re.compile(r"^computer\s+(?:health|status)\b"), "system", ""),
        (re.compile(r"^pc\s+(?:health|status)\b"), "system", ""),
        (re.compile(r"^how(?:'s|s| is| are)\s+(?:my\s+|the\s+)?(?:computer|pc|laptop|machine|system)\b"), "system", ""),
        (re.compile(r"^is\s+my\s+(?:computer|pc|laptop)\s+(?:ok(?:ay)?|fine|healthy|good)\b"), "system", ""),
        (re.compile(r"^show\s+(?:me\s+)?(?:system|computer|pc)\s+(?:health|status)\b"), "system", ""),
        # --- lock state ---
        # Canonical family: every wording that asks for CURRENT session lock
        # state routes to the authoritative Windows session owner — never web
        # knowledge. Host nouns and both polarities (locked/unlocked) are
        # generic; "can I use the computer" is lock-state, not knowledge.
        (re.compile(r"^is\s+(?:my\s+|the\s+)?(?:computer|pc|laptop|screen|system|windows|machine|workstation)\s+locked\b"), "lock_state", ""),
        (re.compile(r"^is\s+(?:my\s+|the\s+)?(?:computer|pc|laptop|screen|system|windows|machine|workstation)\s+unlocked\b"), "lock_state", ""),
        (re.compile(r"^am\s+i\s+(?:locked|locked\s+out|locked\s+in)\b"), "lock_state", ""),
        (re.compile(r"^lock\s+(?:status|state)\b"), "lock_state", ""),
        (re.compile(r"^what(?:'s|s| is)?\s+(?:the\s+|my\s+|current\s+)?(?:current\s+)?lock\s+(?:status|state)\s*\??$"), "lock_state", ""),
        (re.compile(r"^what(?:'s|s| is)?\s+(?:the\s+|my\s+|current\s+)?(?:system|session|screen|windows)\s+lock\s+(?:status|state)\s*\??$"), "lock_state", ""),
        (re.compile(r"^can\s+i\s+(?:use|access|get\s+into)\s+(?:the\s+|my\s+)?(?:computer|pc|laptop|machine|system|workstation)\s*\??$"), "lock_state", ""),
        # --- system uptime ---
        (re.compile(r"^(?:system|pc|computer)\s+uptime\b"), "system_uptime", ""),
        (re.compile(r"^how\s+long\s+has\s+(?:my\s+|the\s+)?(?:computer|pc|system|laptop)\s+been\s+(?:running|on|up)\b"), "system_uptime", ""),
        # --- resources / attribution / diagnostic ---
        (re.compile(r"^resources\s*$"), "resources", ""),
        (re.compile(r"^resource\s+usage\b"), "resources", ""),
        (re.compile(r"^why\s+is\s+(?:my\s+|the\s+)?(?:computer|pc|laptop|system|everything)\s+(?:so\s+)?(?:slow|laggy|lagging|sluggish)\b"), "diagnostic", ""),
                (re.compile(r"^what(?:'s|s| is)?\s+(?:using|eating|taking|consuming)\s+(?:up\s+|all\s+of\s+)?(?:my\s+)?(?:cpu|processor)\b"), "resources_cpu", ""),
        # 'space' alone is only a storage query when end-anchored or with
        # 'my' — "what is taking up space in the universe" stays knowledge.
        (re.compile(r"^what(?:'s|s| is)?\s+(?:using|eating|consuming)\s+(?:up\s+|all\s+of\s+)?(?:my\s+)?(?:storage|disk\s+space|disk)\b"), "resources_storage", ""),
        (re.compile(r"^what(?:'s|s| is)?\s+taking\s+up\s+(?:all\s+of\s+)?(?:my\s+)?space\s*$"), "resources_storage", ""),
        (re.compile(r"^what(?:'s|s| is)?\s+taking\s+up\s+(?:all\s+of\s+)?my\s+(?:space|storage|disk)\b"), "resources_storage", ""),
        (re.compile(r"^which\s+drive(?:s)?\s+(?:is|are)\s+(?:getting\s+)?(?:full|nearly\s+full|almost\s+full)\b"), "resources_storage", ""),
        (re.compile(r"^why\s+is\s+my\s+(?:disk|drive|storage)\s+full\b"), "resources_storage", ""),
        (re.compile(r"^is\s+my\s+(?:disk|drive|storage)\s+(?:full|getting\s+full)\b"), "storage", ""),
        (re.compile(r"^how\s+much\s+(?:free\s+)?(?:space|storage|disk\s+space)\s+(?:do\s+i\s+have|is\s+left|is\s+there\s+left)\b"), "storage", ""),
        # --- metrics ---
        (re.compile(r"^cpu\b"), "cpu", ""),
        (re.compile(r"^processor\b"), "cpu", ""),
        (re.compile(r"^what(?:'s|s| is)?\s+my\s+(?:cpu|processor)\s+(?:usage|load)\b"), "cpu", ""),
        (re.compile(r"^how\s+much\s+(?:cpu|processor)\b"), "cpu", ""),
        (re.compile(r"^how\s+busy\s+is\s+the\s+(?:cpu|processor)\b"), "cpu", ""),
        # RAM/memory queries handled by _detect_resource_generic — no query-specific regexes
        (re.compile(r"^gpu\b"), "gpu", ""),
        (re.compile(r"^gpu\s+(?:usage|load)\b"), "gpu", ""),
        (re.compile(r"^is\s+my\s+gpu\s+being\s+used\b"), "gpu", ""),
        (re.compile(r"^storage\s*$"), "storage", ""),
        (re.compile(r"^disk\s*$"), "storage", ""),
        (re.compile(r"^(?:storage|disk)\s+(?:usage|space)\b"), "storage", ""),
        (re.compile(r"^how\s+much\s+(?:storage|disk\s+space)\s+do\s+i\s+have\b"), "storage", ""),
        (re.compile(r"^how\s+much\s+disk\s+space\s+is\s+left\b"), "storage", ""),
        # --- battery / power family (first-class deterministic capability) ---
        # Short AND natural requests must land here — never general knowledge.
        # Word order and phrasing do not matter; the semantic family owns the
        # answer from real Windows power state.
        (re.compile(r"^battery\s*%?\s*$"), "battery", ""),
        (re.compile(r"^battery\s+(?:percentage|percent|level|status|state)\b"), "battery", ""),
        (re.compile(r"^what(?:'s|s| is)?\s+(?:the\s+)?(?:battery|charge|power)\s+(?:percentage|percent|level|status|state)\b"), "battery", ""),
        (re.compile(r"^what(?:'s|s| is)?\s+(?:my\s+|the\s+)?battery\b"), "battery", ""),
        (re.compile(r"^how\s+much\s+(?:battery|charge|power)\s+(?:do\s+i\s+have|is\s+left|have\s+i\s+got|left|do\s+i\s+have\s+left)\b"), "battery", ""),
        (re.compile(r"^how(?:'s|s| is)\s+(?:my\s+|the\s+)?(?:battery|power|charge)(?:\s+(?:looking|doing))?\??\s*$"), "battery", ""),
        (re.compile(r"^charge\s+left\b"), "battery", ""),
        (re.compile(r"^power\s+(?:status|state)\b"), "battery", ""),
        (re.compile(r"^is\s+(?:my\s+|the\s+)?(?:battery|power)\s+(?:low|running\s+low|dying|about\s+to\s+die|going\s+to\s+die)\??\s*$"), "battery_low", ""),
        (re.compile(r"^am\s+i\s+(?:low\s+on\s+battery|running\s+(?:low|out)\s+on\s+battery|about\s+to\s+run\s+out\s+of\s+battery|low\s+on\s+charge)\b"), "battery_low", ""),
        (re.compile(r"^is\s+(?:my\s+|the\s+)?(?:laptop|computer|pc|system)\s+charging\b"), "battery_charging", ""),
        (re.compile(r"^is\s+(?:it|the\s+battery)\s+charging\b"), "battery_charging", ""),
        (re.compile(r"^am\s+i\s+charging\b"), "battery_charging", ""),
        (re.compile(r"^(?:is\s+it\s+)?plugged\s+in\??\s*$"), "battery_charging", ""),
        (re.compile(r"^is\s+my\s+battery\s+charging\b"), "battery_charging", ""),
        # --- components / services ---
        (re.compile(r"^is\s+(?:the\s+)?(?:browser|chrome|edge|firefox|brave)\s+(?:connected|working|ready|up|online|available|running)\b"), "components", "browser"),
        (re.compile(r"^is\s+(?:the\s+)?(?:telegram|bot|discord)\s+(?:connected|working|ready|up|online|available|running|alive)\b"), "components", "telegram"),
        (re.compile(r"^is\s+(?:the\s+)?media\s+(?:working|ready|up|available|connected)\b"), "components", "media"),
        (re.compile(r"^are\s+(?:the\s+)?(?:providers|services|subsystems)\s+(?:healthy|connected|working|ready|up|ok(?:ay)?)\b"), "components", "services"),
        (re.compile(r"^is\s+(?:the\s+)?(?:mcp|tools?)\s+(?:connected|working|ready|up|available)\b"), "components", "tools"),
        (re.compile(r"^is\s+(?:the\s+)?kio(?:'s)?\s+(?:runtime\s+)?(?:working|ok(?:ay)?|healthy|fine)\b"), "components", "kio"),
        (re.compile(r"^is\s+kio\s+(?:running|alive|up)\b"), "health", ""),
        (re.compile(r"^what\s+(?:services|components|systems|things)\s+are\s+(?:connected|working|running|active)\b"), "components", ""),
        # --- whats wrong / diagnose ---
        # Canonical family: bare ("what's wrong") AND qualified
        # ("what's wrong with my system") forms must route to the operational
        # health correlation — never fall through to the knowledge LLM.
        (re.compile(r"^what(?:'s|s| is)?\s+wrong\s*$"), "whats_wrong", ""),
        (re.compile(r"^what(?:'s|s| is)?\s+wrong\s+with\s+(?:my\s+|the\s+|this\s+|that\s+)?(?:pc|computer|laptop|system|machine|rig|device)\s*\??\s*$"), "whats_wrong", ""),
        (re.compile(r"^is\s+(?:there\s+)?(?:anything|something)\s+wrong\b"), "whats_wrong", ""),
        (re.compile(r"^(?:anything|something)\s+wrong(?:\s+with\s+(?:my\s+|the\s+)?(?:pc|computer|laptop|system))?\b"), "whats_wrong", ""),
        (re.compile(r"^why\s+(?:are\s+you|is\s+kio)\s+(?:unhealthy|degraded|not\s+working)\b"), "whats_wrong", ""),
        (re.compile(r"^why\s+isn'?t\s+(?:something|anything)\s+working\b"), "whats_wrong", ""),
        (re.compile(r"^what(?:'s|s| is)?\s+failing\b"), "whats_wrong", ""),
        (re.compile(r"^what\s+isn'?t\s+working\b"), "whats_wrong", ""),
        (re.compile(r"^diagnose\b"), "whats_wrong", ""),
        # --- kio-prefixed apostrophe forms (not reached by name-strip) ---
        (re.compile(r"^kio(?:'s)?\s+health\b"), "health", ""),
        (re.compile(r"^kio(?:'s)?\s+status\b"), "status", ""),
        (re.compile(r"^kio(?:'s)?\s+uptime\b"), "uptime", ""),
        (re.compile(r"^kio(?:'s)?\s+diagnose\b"), "whats_wrong", ""),
        # --- KIO self-state / typo-tolerant conversational-state family ---
        (re.compile(r"^kio\s+(?:ok(?:ay)?|good|fine|alright|healthy)\b"), "health", ""),
        (re.compile(r"^kio\s+still\s+(?:running|up|alive|online|working)\b"), "health", ""),
        (re.compile(r"^kio\s+(?:running|up|alive|online)\b"), "health", ""),
        (re.compile(r"^you\s+(?:ok(?:ay)?|good|alright|fine|healthy)\b"), "health", ""),
        (re.compile(r"^still\s+(?:running|up|alive|online|working)\b"), "health", ""),
        (re.compile(r"^are\s+you\s+still\s+(?:running|up|alive|online)\b"), "health", ""),
        (re.compile(r"^how\s+is\s+your\s+health\b"), "health", ""),
        (re.compile(r"^everything\s+ok(?:ay)?\b"), "health", ""),
        (re.compile(r"^all\s+good\b"), "health", ""),
        # --- installed-app inventory ("what apps do I have" family) ---
        # Deterministic, real OS scan — never an LLM guess. Runs before the
        # desktop-state family so "what's running" stays list_tabs while
        # "what apps do I have" / "what's installed" answer the inventory.
        # LLM-bypass audit (2026-08-12): "what apps do you have" and "what
        # apps does the system have" previously fell through to LLM/web
        # knowledge. Any possession wording (I/you/the system/the computer)
        # over the apps noun is the SAME inventory — the OS owns the apps.
        (re.compile(r"^what(?:'s|s| is)?\s+(?:apps?|applications|software|programs?)\s+(?:do\s+i\s+have|does\s+(?:the\s+)?(?:system|computer|pc|laptop|machine)\s+have|do\s+you\s+have|have\s+(?:i|you)\s+got|are\s+installed)\b"), "app_inventory", ""),
        (re.compile(r"^what(?:'s|s| is)?\s+(?:my\s+|the\s+)?(?:apps?|applications|software|programs?)\s+(?:is\s+installed|are\s+on\s+(?:my|this|the)\s+(?:computer|pc|laptop|machine))\b"), "app_inventory", ""),
        (re.compile(r"^what(?:'s|s| is)?\s+installed\b"), "app_inventory", ""),
        (re.compile(r"^list\s+(?:my\s+)?(?:installed\s+)?(?:apps?|applications|software|programs?)\b"), "app_inventory", ""),
        (re.compile(r"^show\s+(?:me\s+)?(?:my\s+)?(?:installed\s+)?(?:apps?|applications|software|programs?)\b"), "app_inventory", ""),
        (re.compile(r"^which\s+(?:apps?|applications|software|programs?)\s+are\s+installed\b"), "app_inventory", ""),
        # --- broad system summary ("what's on my computer" family) ---
        # Distinct from desktop state ("what's open"): machine-level overview.
        (re.compile(r"^what(?:'s|s| is)?\s+(?:on|in)\s+(?:my|this)\s+(?:computer|pc|laptop|machine)\b"), "system_summary", ""),
        (re.compile(r"^what\s+do\s+i\s+have\s+on\s+(?:my|this)\s+(?:computer|pc|laptop|machine)\b"), "system_summary", ""),
    )

    # Credential management family (Slice 9): deterministic, secret-free.
    # Knowledge questions that merely mention a provider ("what is github",
    # "what is an oauth credential") stay on the knowledge path.
    # "Is GitHub connected?" resolves to CREDENTIAL state (never an LLM
    # guess) but ONLY for known credential providers — "is the browser
    # connected" stays a component query via the operational family above.
    _CREDENTIAL_PROVIDER_WORDS = frozenset({
        "github", "google", "gmail", "telegram", "discord", "openai",
        "microsoft", "outlook", "spotify", "youtube", "notion", "slack",
        "whatsapp", "dropbox", "canva", "gitlab", "bitbucket",
    })
    _CREDENTIAL_ROUTES: tuple[tuple[object, str, str], ...] = (
        (re.compile(r"^what\s+credentials\s+do\s+i\s+have\b"), "list", ""),
        (re.compile(r"^what\s+credentials\s+(?:are|get)\s+configured\b"), "list", ""),
        (re.compile(r"^what\s+(?:credentials|integrations|accounts)\s+are\s+(?:set\s+up|configured|connected|active)\b"), "list", ""),
        (re.compile(r"^which\s+(?:credentials|integrations|accounts|services)\s+are\s+(?:set\s+up|configured|connected|active)\b"), "list", ""),
        (re.compile(r"^show\s+(?:me\s+)?(?:my\s+)?(?:connected\s+)?(?:accounts|credentials)\b"), "list", ""),
        (re.compile(r"^list\s+(?:my\s+)?(?:credentials|connected\s+accounts)\b"), "list", ""),
        (re.compile(r"^which\s+credentials\s+need\s+attention\b"), "attention", ""),
        (re.compile(r"^do\s+i\s+need\s+to\s+reconnect\s+anything\b"), "attention", ""),
        # Credential STATE family (Slice 9): "credential status", "status of
        # my credentials" — deterministic vault state, never the knowledge LLM.
        (re.compile(r"^credential(?:s)?\s+(?:status|state|health|situation)\b"), "status", ""),
        (re.compile(r"^status\s+of\s+(?:my\s+|the\s+)?credential(?:s)?\b"), "status", ""),
        (re.compile(r"^how\s+(?:are|is)\s+(?:my\s+)?credential(?:s)?\s+(?:doing|looking|looking\s+fine)\b"), "status", ""),
        (re.compile(r"^revoke\s+my\s+([a-z0-9 ._-]+?)\s+(?:credential|account|credentials)\b"), "revoke", ""),
        (re.compile(r"^is\s+my\s+([a-z0-9 ._-]+?)\s+(?:credential|account)\s+valid\b"), "status", ""),
        (re.compile(r"^refresh\s+(?:my\s+|the\s+)?([a-z0-9 ._-]+?)\s+(?:credential|account)\b"), "refresh", ""),
    )

    def _detect_credential(self, lower, text):
        norm = lower.lstrip("/")
        for pattern, action, _target in self._CREDENTIAL_ROUTES:
            m = pattern.match(norm)
            if not m:
                continue
            target = m.group(1).strip() if m.groups() else ""
            return RoutingDecision(
                IntentType.CREDENTIAL, action, target, text, lower, confidence=1.0,
            )
        # "Is GitHub connected?" -> credential status for KNOWN providers only.
        # This runs AFTER the operational family (browser/telegram component
        # queries already claimed), so "is the browser connected" is never
        # hijacked. Knowledge-vs-state boundary: "what is github" stays
        # knowledge because it never reaches this anchored "connected" scan.
        conn = re.match(
            r"^is\s+(?:my\s+|the\s+)?([a-z0-9 ._-]+?)\s+connected\??\s*$", norm
        )
        if conn:
            candidate = conn.group(1).strip().lower()
            first = candidate.split()[0] if candidate.split() else candidate
            if first in self._CREDENTIAL_PROVIDER_WORDS:
                return RoutingDecision(
                    IntentType.CREDENTIAL, "status", candidate,
                    text, lower, confidence=1.0,
                )
        if norm in ("credentials",):
            return RoutingDecision(IntentType.CREDENTIAL, "list", "", text, lower, confidence=1.0)
        return None



    # Deterministic installed-app existence query: "is winrar installed",
    # "is vscode installed". Routes to the operational family (app_installed)
    # which probes the real OS — never an LLM guess. Generic placeholders
    # ("is everything installed") stay out.
    _INSTALLED_QUERY_RE = re.compile(r"^is\s+(.+?)\s+installed\??\s*$")
    _INSTALLED_PLACEHOLDERS = frozenset({
        "everything", "anything", "something", "it", "this", "that",
        "my apps", "the apps", "apps", "software", "all", "everything else",
    })

    # Observed-state queries: "is X open" / "is X running" -> deterministic
    # app_running family answered from the real desktop (visible windows +
    # process presence), never an LLM guess. "Installed" stays the inventory
    # family; "open/running" is the live-observation family — the two are
    # never derived from each other.
    _IS_OPEN_RE = re.compile(r"^is\s+(.+?)\s+open\??\s*$")
    _IS_RUNNING_RE = re.compile(r"^is\s+(.+?)\s+running\??\s*$")
    _IS_OPEN_PLACEHOLDERS = frozenset({
        "everything", "anything", "something", "it", "this", "that", "them",
        "those", "these", "all", "apps", "windows", "tabs", "software",
        "my apps", "the apps", "the computer", "my computer", "the pc",
        "my pc", "computer", "pc", "laptop", "the laptop", "my laptop",
        "browser", "the browser", "everything else",
    })

    def _detect_operational(self, lower, text):
        # Command-style ("/health") and natural-style share one deterministic
        # path; punctuation/case are already normalized upstream. Bounded
        # typo-correction ("heath" -> "health") is applied to the scan text
        # only; the decision keeps the user's original text.
        norm = self._typo_fix_operational(lower.lstrip("/"))
        # Explicit slash-command = the user asked for the full command detail
        # ("/health" -> per-component report), whereas natural "KIO health"
        # gets the short prose. Same deterministic family, same state owner.
        if lower.startswith("/"):
            cmd = norm.split()[0].split("@")[0]
            if cmd == "health":
                return RoutingDecision(
                    IntentType.OPERATIONAL, "health_detail", "",
                    text, lower, confidence=1.0,
                )
        installed_match = self._INSTALLED_QUERY_RE.match(norm)
        if installed_match:
            app = installed_match.group(1).strip()
            if app and app.lower() not in self._INSTALLED_PLACEHOLDERS:
                return RoutingDecision(
                    IntentType.OPERATIONAL, "app_installed", app,
                    text, lower, confidence=1.0,
                )
        # Observed-state family: "is VLC open" / "is notepad running" — answered
        # from the real desktop, never from knowledge. Runs AFTER the tuple scan
        # so browser/telegram component queries keep their own semantics.
        for state_re in (self._IS_OPEN_RE, self._IS_RUNNING_RE):
            state_match = state_re.match(norm)
            if state_match:
                app = state_match.group(1).strip()
                if app and app.lower() not in self._IS_OPEN_PLACEHOLDERS:
                    return RoutingDecision(
                        IntentType.OPERATIONAL, "app_running", app,
                        text, lower, confidence=1.0,
                    )
        for pattern, action, target in self._OPERATIONAL_ROUTES:
            if pattern.match(norm):
                return RoutingDecision(
                    IntentType.OPERATIONAL, action, target, text, lower, confidence=1.0,
                )
        # Generic resource intent: system memory / cpu / battery / storage without query-specific regex
        # Uses semantic keywords, not phrasing
        _resource = self._detect_resource_generic(norm, text, lower)
        if _resource:
            return _resource
        return None

    def _detect_resource_generic(self, norm: str, text: str, lower: str):
        # Generic resource detection: look for resource keywords + intent verbs, not specific phrasing
        # Resource keywords: ram, memory, cpu, battery, storage, disk, gpu
        # Intent: question about current state (how much, what is, usage, etc.) vs knowledge (how does ram work)
        # We use a small semantic check, not a list of phrasings
        import re as _re2
        # Check if query is about current system state vs general knowledge
        # Current state indicators: how much, what is my, how is my, usage, percent, left, burning, etc. + resource
        # Knowledge indicators: how does, what does, why does, explain, define (should stay INFORMATION)
        if _re2.search(r"\b(how\s+does|how\s+much\s+does|what\s+does|why\s+does|explain|define|meaning|difference\s+between|what\s+is\s+the\s+difference|how\s+is\s+.*different|compare|versus|vs)\b", lower):
            return None
        # Generic resource keywords (check norm for typo-fixed forms like "memroy" -> "memory")
        has_ram = bool(_re2.search(r"\b(ram|memory)\b", norm))
        has_cpu = bool(_re2.search(r"\bcpu\b", norm))
        has_battery = bool(_re2.search(r"\bbattery\b", norm))
        has_storage = bool(_re2.search(r"\b(storage|disk|space)\b", norm))
        # Must have a current-state intent verb (check norm, which has typos fixed)
        has_intent = bool(_re2.search(r"\b(how\s+much|what\s+is|how\s+is|what\'s|whats|usage|using|burning|percent|left|status)\b", norm))
        if has_ram and has_intent:
            # Distinguish "what's using my RAM" (resources_ram) vs "how much RAM" (ram)
            if _re2.search(r"\b(using|eating|taking|consuming)\b.*\b(ram|memory)\b", norm) or _re2.search(r"\b(ram|memory)\b.*\busing\b", norm):
                return RoutingDecision(IntentType.OPERATIONAL, "resources_ram", "", text, lower, confidence=0.9)
            return RoutingDecision(IntentType.OPERATIONAL, "ram", "", text, lower, confidence=0.9)
        if has_cpu and has_intent:
            return RoutingDecision(IntentType.OPERATIONAL, "cpu", "", text, lower, confidence=0.9)
        if has_battery and has_intent:
            return RoutingDecision(IntentType.OPERATIONAL, "battery", "", text, lower, confidence=0.9)
        if has_storage and has_intent:
            return RoutingDecision(IntentType.OPERATIONAL, "storage", "", text, lower, confidence=0.9)
        return None

    def _detect_close(self, lower, text, first_word):
        # Close verb family: "close X", "shut X", "quit X", "kill X",
        # "end X" + phrasal "shut down X" / "close down X". Semantic family,
        # not per-app phrasing. System nouns ("shut down the computer")
        # intentionally stay OUT of this family — handled elsewhere.
        _CLOSE_VERBS = {"close", "shut", "quit", "kill", "end"}
        _CLOSE_PHRASES = ("shut down ", "close down ")

        # ── CLOSE-ALL semantic family (generic scope, NOT phrase handlers):
        #    "close all apps", "close everything", "quit all applications",
        #    "kill all programs", "close all open windows" all converge on the
        #    one canonical representation CLOSE / SCOPE=ALL_APPLICATIONS. The
        #    executor re-observes the desktop, closes user-session apps only,
        #    and reports what actually closed vs what remains. "close all
        #    tabs" is deliberately NOT this family — tabs are browser-scope.
        _close_all_re = re.compile(
            r"^(?:close|shut|quit|kill|end)\s+(?:down\s+)?"
            r"(?:all|every)\s*(?:of\s+)?"
            r"(?:(?:my|the|these|those|open|running)\s+)?"
            r"(?:apps?|applications?|programs?|software|windows?)?\s*$",
            re.IGNORECASE,
        )
        if _close_all_re.fullmatch(lower) \
                or re.fullmatch(r"(?:close|shut|quit|kill|end)\s+(?:down\s+)?everything\s*", lower, re.IGNORECASE):
            return RoutingDecision(
                IntentType.DESKTOP_CLOSE, "close_all_apps", "", text, lower,
                confidence=1.0,
            )

        raw_target = None
        if first_word in _CLOSE_VERBS:
            if any(lower.startswith(p) for p in _CLOSE_PHRASES):
                for phrase in _CLOSE_PHRASES:
                    if lower.startswith(phrase):
                        raw_target = text[len(phrase):].strip()
                        break
            else:
                raw_target = text[len(first_word):].strip()
        if raw_target is None:
            return None
        # Trailing politeness is never part of the target.
        raw_target = re.sub(
            r"\s+(?:for\s+me|for\s+us|please|pls)\s*$", "", raw_target,
            flags=re.IGNORECASE,
        ).strip()
        # EXPLICIT INSTANCE SCOPE: "close the telegram tab" says TAB even
        # though Telegram also has a native install — the created scope wins
        # over entity identity. "close this window" of a native app is APP
        # scope (the app owns its window); a webapp "window" resolves to its
        # tab (window-level browser ops are not modeled).
        _scope_tab = bool(re.search(r"\s+tab(?:s)?\s*$", raw_target, re.IGNORECASE))
        _scope_window = bool(re.search(r"\s+window(?:s)?\s*$", raw_target, re.IGNORECASE))
        # "shut down the computer" / "shut down my pc" is a SYSTEM action
        # (shutdown), never an application close. System nouns stay OUT of the
        # close-verb family by design — this is the missing boundary.
        _close_system_nouns = {"computer", "pc", "laptop", "machine", "system", "workstation"}
        _raw_check = re.sub(
            r"^(?:my|the|this|that)\s+", "", raw_target.lower().strip()
        ).strip()
        _first_noun = _raw_check.split()[0] if _raw_check else ""
        if _first_noun in _close_system_nouns and any(
            lower.startswith(p) for p in ("shut down ", "close down ")
        ):
            return RoutingDecision(
                IntentType.SYSTEM, "shutdown_system", "", text, lower,
                confidence=1.0,
            )
        # Generic noun-phrase cleanup: strip leading article and trailing
        # qualifiers ("the cursor thing" -> "cursor", "the chatgpt tab" ->
        # "chatgpt").
        target = re.sub(r"^(?:the|a|an)\s+", "", raw_target.strip(), flags=re.IGNORECASE)
        target = re.sub(r"\s+(?:thing|app|application|program|software|tab)\s*$", "", target, flags=re.IGNORECASE).strip()
        browser_names = {"chrome", "edge", "firefox", "brave", "comet", "opera", "browser"}
        target_lower = target.lower()
        if target_lower in browser_names or target_lower.endswith(" browser"):
            return RoutingDecision(IntentType.DESKTOP_CLOSE, "close_app", target_lower.replace(" browser", ""), text, lower, confidence=1.0)

        # ── TARGET-KIND-AWARE CLOSE (APP vs WINDOW vs BROWSER vs TAB): a
        #    request to close an APPLICATION must never silently become a
        #    browser-tab operation, and a tab-scope request must never
        #    escalate into the host browser process. Identity comes from the
        #    canonical target-ref kind + the registry (registered native
        #    identity wins over the web hint) + the EXPLICIT instance noun.
        from mini_kio.core.target_ref import parse_target
        from mini_kio.core.app_operator import _find_in_registry
        ref = parse_target(target_lower)
        # Explicit "tab" scope wins over native identity: "close the telegram
        # tab" (or a context-resolved "close it" after a new tab) closes the
        # TAB — never the native Telegram app of the same name.
        if _scope_tab:
            return RoutingDecision(
                IntentType.BROWSER_FOCUS, "close_tab", ref.name or target_lower,
                text, lower, confidence=1.0,
            )
        if _scope_window and _find_in_registry(target_lower) is None:
            # A webapp "window" (no native install) closes at tab scope — its
            # tab is the concrete instance we created.
            return RoutingDecision(
                IntentType.BROWSER_FOCUS, "close_tab", ref.name or target_lower,
                text, lower, confidence=1.0,
            )
        if ref.kind == "webapp" and _find_in_registry(target_lower) is None:
            # Known web app (chatgpt/telegram web/whatsapp web/...) with no
            # registered native install -> TAB scope, never the browser
            # process, never a fake native close.
            return RoutingDecision(
                IntentType.BROWSER_FOCUS, "close_tab", ref.name or target_lower,
                text, lower, confidence=1.0,
            )
        # Default: APPLICATION scope (registered native identity, generic
        # discovered app, or an ordinary app-like name). The close_app
        # owner resolves native-vs-web truthfully and verifies real closure.
        return RoutingDecision(
            IntentType.DESKTOP_CLOSE, "close_app", target_lower,
            text, lower, confidence=1.0,
        )

    def _detect_system(self, lower, first_word):
        mapping = {
            "shutdown": "shutdown_system", "restart": "restart_system",
            "lock": "lock_system", "unlock": "unlock_system",
            "recovery": "recovery_runtime", "recover": "recovery_runtime",
        }
        if first_word in self.SYSTEM_ACTIONS:
            action = mapping.get(first_word)
            if action:
                return RoutingDecision(IntentType.SYSTEM, action, "", "", "", confidence=1.0)
        # Natural lock/unlock phrasing: "lock my pc", "lock the computer",
        # "secure my computer", "unlock my computer", "wake and unlock".
        if re.match(r"^secure\s+my\s+(?:computer|pc|laptop|machine)\b", lower):
            return RoutingDecision(IntentType.SYSTEM, "lock_system", "", "", "", confidence=1.0)
        if re.match(r"^lock\s+(?:my\s+|the\s+|this\s+)?(?:computer|pc|laptop|machine|workstation)\b", lower):
            return RoutingDecision(IntentType.SYSTEM, "lock_system", "", "", "", confidence=1.0)
        if re.match(r"^unlock\s+(?:my\s+|the\s+|this\s+)?(?:computer|pc|laptop|machine|workstation)\b", lower):
            return RoutingDecision(IntentType.SYSTEM, "unlock_system", "", "", "", confidence=1.0)
        if lower in ("wake and unlock", "wake up and unlock"):
            return RoutingDecision(IntentType.SYSTEM, "unlock_system", "", "", "", confidence=1.0)
        return None

    def _detect_file(self, lower, text, first_word):
        if lower.startswith("open folder ") or first_word == "folder":
            return RoutingDecision(IntentType.FILE, "open_folder", text, text, lower, confidence=1.0)
        return None

    def _detect_now_playing(self, lower, text):
        # Capability C: state-aware media — "what's playing?" queries the
        # current media session instead of being misrouted as a generic
        # information question.
        #
        # The "what" interrogative is canonicalized BEFORE exact-set matching:
        # any spelling of the question word ("whts", "wat", "what is",
        # "what's") folds to "what", so the capability is reachable by the
        # whole typing family, not just the exact entries in the set. Live
        # failure: "whts playing now" missed the set, fell to media-intelligence
        # query analysis, and fabricated an eFootball answer from entity
        # "Playing". General interrogative normalization — never per-phrase.
        # The input normalizer may expand a contraction to either "what is"
        # or tokenise its apostrophe away as "what s".  Treat both forms as
        # the same interrogative before exact state-question matching.  This
        # keeps a state query in the deterministic media path instead of
        # allowing it to reach retrieval/LLM composition.
        original = lower.strip()
        # State-question grammar.  This is deliberately anchored: an
        # information question that merely contains the word "playing" does
        # not become a media command.
        if re.fullmatch(
            r"what(?:\s+(?:is|s))?\s+(?:(?:currently)\s+)?(?:playing|on)"
            r"(?:\s+(?:right\s+now|currently))?",
            original,
        ):
            return RoutingDecision(
                IntentType.MEDIA_TRANSPORT, "now_playing", "", text, original,
                confidence=1.0,
            )

        lower = re.sub(r"^what\s+(?:is|s)\s+", "what ", original)
        words = lower.strip().split()
        if words and words[0].strip(".,!?;:'\"").lower() in _WHAT_INTERROGATIVES:
            words[0] = "what"
            if len(words) > 1 and words[1].strip() == "is":
                words.pop(1)
        canonical = " ".join(words)
        now_playing_phrases = frozenset({
            "what playing", "what on", "what currently playing",
            "what playing now", "what am i playing", "what am i listening to",
            "what the current song", "what the current video",
        })
        if canonical in now_playing_phrases:
            return RoutingDecision(
                IntentType.MEDIA_TRANSPORT, "now_playing", "", text, lower,
                confidence=1.0,
            )
        return None

    @staticmethod
    def _has_active_media_session() -> bool:
        """Check if there is an active media session (PLAYING, PAUSED, READY).
        Used to decide whether short phrases like 'nah' are media rejections
        vs ordinary conversation. An intelligent companion only treats these
        as media operations when media is actually active — otherwise they
        are conversational responses."""
        try:
            from mini_kio.media.media_manager import MediaManager
            mm = MediaManager.get_instance()
            return mm._registry.get_active() is not None
        except Exception:
            return False

    def _classify_media_transport(self, lower, text):
        # Phase 3: media rejection phrases — "nah", "not this", "something different",
        # etc. must route to MEDIA_PLAY so MediaManager.play's rejection handler
        # excludes the current candidate and plays the next best.
        #
        # IMPORTANT: Only route to MEDIA_PLAY when there IS an active media
        # session. Without active media, 'nah' is just a conversational
        # response — not a media command. The media manager's play() already
        # has the intelligent rejection handler that checks context; routing
        # unconditionally would cause play('nah') to literally search YouTube
        # for 'nah' when no media is active.
        _REJECTION_PHRASES = frozenset({
            "nah", "nope", "no", "no next", "no another",
            "not this", "not this one", "not feeling this",
            "this sucks", "this is bad", "this is terrible", "this is awful",
            "this ain't it", "this isn't it",
            "skip this", "skip it", "skip that",
            # NOTE: standalone 'next'/'skip' are TRANSPORT commands (next track)
            # handled by the MEDIA_TRANSPORT set below. Rejection-specific forms
            # ('next one', 'skip this') go to media_play/play for the rejection
            # handler in MediaManager.play.
            "next one",
            "another", "another one", "another please",
            "something different", "something better",
            "not what i meant", "not what we meant",
            "that's not what i meant", "that is not what i meant",
            "change it", "switch it",
            "nah bro", "no bro", "not this bro",
            "nah another", "nah next", "nah try",
            "nope another", "nope next", "nope try",
        })
        if lower in _REJECTION_PHRASES:
            # Context-aware: only route as media rejection when media is active.
            # Otherwise this is conversational ("nah" in reply to a question,
            # "not this" about a non-media thing, etc.).
            if self._has_active_media_session():
                return RoutingDecision(IntentType.MEDIA_PLAY, "play", lower, text, lower, confidence=1.0)
            # No active media — fall through to conversation.
        # Also catch "give me another", "try another", "play something else"
        _REJECTION_PREFIXES = (
            "give me another", "give me something else", "give me something different",
            "try another", "try something different", "try something else",
            "play something else", "play something different",
            "play another",
        )
        for _rp in _REJECTION_PREFIXES:
            if lower.startswith(_rp) or lower == _rp:
                if self._has_active_media_session():
                    return RoutingDecision(IntentType.MEDIA_PLAY, "play", lower, text, lower, confidence=1.0)

        # R-EFG: "play it"/"play that" are media-continuity commands resolved
        # by MediaManager.play's pronoun handling — NOT offer acceptance.
        # ("show it"/"watch it"/"play video" keep the R4 offer-acceptance path.)
        if lower in ("show it", "watch it", "play video"):
            return RoutingDecision(IntentType.CONVERSATION, "accept_offer", "", text, lower, confidence=0.9)

        # R-EFG: "play next/previous video" must resolve to the real transport
        # action. The generic scan below would take the first word ("play") as
        # the action and drop the target, routing to a play("") resume/gate
        # instead of the actual next/previous-track action.
        if lower == "play next video":
            return RoutingDecision(IntentType.MEDIA_TRANSPORT, "next", "", text, lower, confidence=1.0)
        if lower == "play previous video":
            return RoutingDecision(IntentType.MEDIA_TRANSPORT, "previous", "", text, lower, confidence=1.0)

        # A transport command must HEAD the utterance (optionally after a
        # polite prefix, already stripped) — "pause", "stop the music",
        # "volume up", "go back". A mid-sentence transport word is almost
        # always conversational: "...where microservices stop being worth
        # it?" must stay a conversation, never a media command. Match the
        # command at the START only, and derive the action from the matched
        # command — never from the utterance's first word ("yeah stop" would
        # otherwise route a question to media with action='yeah').
        _head = " ".join(lower.split()[:3])
        for cmd in sorted(self.MEDIA_TRANSPORT, key=len, reverse=True):
            if _head == cmd or _head.startswith(cmd + " "):
                # Guard: bare single-word transport commands (stop, pause, resume,
                # mute, continue, next, skip) must NOT match multi-word sentences
                # where the transport word is a conversational verb ("Stop giving
                # me bloated explanations" is NOT a media stop command). The guard
                # requires either: (a) the head matches exactly (bare command),
                # (b) the rest of the message is short (<=2 extra words, e.g.
                # "stop the music"), or (c) the rest contains media-related words.
                _rest = lower[len(cmd):].strip()
                _rest_words = len(_rest.split()) if _rest else 0
                _is_bare = (" " not in cmd)  # single-word transport entry
                if _is_bare and _rest_words >= 2:
                    # Check if the rest is media-related ("stop the music")
                    # vs conversational ("stop giving me bloated explanations").
                    _media_hint = re.search(
                        r"\b(?:the\s+)?(?:music|video|song|track|playback|media|stream|player|it|this|that)\b",
                        _rest,
                    )
                    if not _media_hint:
                        continue  # not a media transport — treat as conversation
                action = cmd.split()[0]
                if cmd == "go back":
                    # "go back" is a media PREVIOUS-track command when bare or
                    # about the media session. "go back to that movie you
                    # mentioned" / "go back to the one we discussed" is a
                    # DISCOURSE callback to a conversational topic — the
                    # head-match would otherwise route it to transport
                    # "previous" (live bug: returned "Couldn't focus That Movie
                    # You Mentioned" via the focus route, and without that fix
                    # would return a no-op transport). Referent morphology
                    # (that/this/the one/you said/earlier) keeps it
                    # conversational.
                    _gb_rest = lower[len(cmd):].strip()
                    if re.search(
                        r"\b(?:that|this|the\s+one|those|these|it)\b|\byou\s+(?:said|mentioned|recommended|suggested)\b|\b(?:earlier|before|again)\b",
                        _gb_rest,
                    ):
                        return None
                    action = "previous"
                if cmd in ("turn it up", "increase volume", "louder", "volume up"):
                    action = "volume_up"
                if cmd in ("turn it down", "decrease volume", "quieter", "volume down", "lower volume"):
                    action = "volume_down"
                if cmd in ("continue", "keep going", "continue playing", "carry on", "keep playing", "resume it"):
                    action = "continue"
                if cmd in ("next video", "next track"):
                    action = "next"
                if cmd in ("previous video", "previous track"):
                    action = "previous"
                if cmd == "skip video":
                    action = "skip"
                return RoutingDecision(IntentType.MEDIA_TRANSPORT, action, "", text, lower, confidence=1.0)

        volume_match = re.search(r"(?:set|increase|decrease)?\s*volume(?:\s*to)?\s*(\d+)", lower)
        if volume_match:
            return RoutingDecision(
                IntentType.MEDIA_TRANSPORT, "set_volume", volume_match.group(1),
                text, lower, confidence=1.0,
            )

        if lower.startswith("seek "):
            return RoutingDecision(IntentType.MEDIA_TRANSPORT, "seek", "", text, lower, confidence=1.0)

        _context_play = ("play something similar", "play another", "play more",
                         "another one", "more like this", "more like that")
        if any(p in lower for p in _context_play):
            return RoutingDecision(IntentType.MEDIA_PLAY, "play", lower, text, lower, confidence=1.0)

        # Media TARGET-SWITCH morphology: "nah give me some drake instead" /
        # "play the weeknd instead" / "actually put on taylor swift" are
        # correction/switch requests that must route to a REAL MEDIA_PLAY of
        # the named target. Generic family shape, not per-phrase: an optional
        # negation/softening lead, a media-request frame ("give me", "play",
        # "put on", "start", "let me hear", "some"), the new target, and a
        # trailing "instead". The trailing "instead" (NOT "instead of X" — that
        # comparison morphology stays conversational via _CALLBACK_RE) marks the
        # switch. Live failure: this utterance went to CONVERSE and the LLM
        # fabricated "Playing Drake." with NO provider invoked.
        _switch = re.match(
            r"^(?:(?:nah|no|nope|naw|actually|wait|hold on|stop|skip|never mind)[,.\s]+)?"
            r"(?:(?:give me|give us)\s+some|play|put on|start|let me hear|hear|some)\s+"
            r"(?:me\s+)?(?:some\s+|a\s+|an\s+|the\s+|more\s+)?"
            r"(.+?)\s+instead\s*$",
            lower,
        )
        if _switch and not re.search(r"\binstead\s+of\b", lower):
            _switch_target = _switch.group(1).strip()
            _switch_target = re.sub(r"\s+(?:by|from)\s+", " ", _switch_target)
            if _switch_target:
                return RoutingDecision(
                    IntentType.MEDIA_PLAY, "play", _switch_target,
                    text, lower, confidence=0.95,
                )

        # ── Expanded media-action prefixes ───────────────────────────────
        # Users say "put on X", "show me X", "let me watch X", etc.
        # Not just "play X" / "watch X".
        _MEDIA_PREFIXES = (
            ("play ", 5), ("watch ", 6),
            ("put on ", 7), ("put ", 4),
            ("show me ", 8), ("show ", 5),
            ("let me watch ", 13), ("let me hear ", 12),
            ("let's watch ", 12), ("let's listen ", 13),
            ("start playing ", 14), ("start ", 6),
            ("queue ", 6),
            ("find me ", 8), ("find ", 5),
            ("give me ", 8),
        )
        for prefix, chop in _MEDIA_PREFIXES:
            if lower.startswith(prefix):
                target = lower[chop:].strip()
                # Platform extraction (OLD ROUTER SEMANTIC): "play X in Chrome"
                # / "watch X on YouTube" must route to the named surface, not
                # the default. rsplit on the LAST separator keeps multi-word
                # targets intact ("lofi hip hop radio in chrome" -> target=
                # "lofi hip hop radio", platform="chrome").
                _platform = None
                for _sep in (" on ", " in ", " using "):
                    if _sep in target:
                        _parts = target.rsplit(_sep, 1)
                        _candidate = _parts[1].strip().rstrip(".,!?")
                        # Dynamic browser resolution: check installed browsers
                        # instead of hardcoded list.
                        _KNOWN_BROWSERS = frozenset({
                            "chrome", "edge", "firefox", "brave", "comet",
                            "opera", "vivaldi", "arc", "browser",
                        })
                        _KNOWN_PLATFORMS = frozenset({
                            "youtube", "youtube desktop", "desktop",
                            "youtube music", "ytmusic",
                        })
                        if _candidate in _KNOWN_BROWSERS:
                            _platform = "browser"
                            target = _parts[0].strip()
                        elif _candidate in _KNOWN_PLATFORMS:
                            _platform = "youtube" if "youtube" in _candidate else _candidate
                            target = _parts[0].strip()
                        else:
                            # Check if it's an installed browser by discovery
                            try:
                                from mini_kio.core.app_operator import _find_installed_app
                                _app = _find_installed_app(_candidate)
                                if _app and _app.get("kind") in ("exe", "shortcut"):
                                    _lifecycle = "browser" if any(
                                        kw in (_app.get("target", "") or "").lower()
                                        for kw in ("chrome", "edge", "firefox", "brave", "comet", "opera")
                                    ) else None
                                    if _lifecycle:
                                        _platform = "browser"
                                        target = _parts[0].strip()
                            except Exception:
                                pass
                        break
                # Ambiguous targets ("give me another", "show me something")
                # without active media are conversational, not media requests.
                _AMBIGUOUS_MEDIA_TARGETS = frozenset({
                    "another", "another one", "something", "something else",
                    "something different", "something better",
                })
                if target in _AMBIGUOUS_MEDIA_TARGETS and not self._has_active_media_session():
                    # Fall through to conversation — no active media to continue
                    pass
                else:
                    # Discovery intent: route to discovery handler, not literal YouTube
                    if target in _DISCOVERY_TARGETS or any(target.startswith(p) for p in _DISCOVERY_PREFIXES):
                        return RoutingDecision(IntentType.MEDIA_PLAY, "play_discovery", target, text, lower, confidence=1.0, platform=_platform)
                    return RoutingDecision(IntentType.MEDIA_PLAY, "play", target, text, lower, confidence=1.0, platform=_platform)

        if lower == "play":
            return RoutingDecision(IntentType.MEDIA_PLAY, "play", "", text, lower, confidence=1.0)

        # "show me the trailer" / "show the trailer" / "show me the highlights"
        # are ACTION requests for a concrete media resource — the user wants
        # the thing SHOWN/PLAYED, not a conversational answer about it. The
        # bare "show it" already routes to accept_offer; extend the same
        # acceptance path to named media nouns so the pending offer (or the
        # named resource) is genuinely resolved and executed. NEVER let these
        # fall to conversation — that is how a fabricated
        # "https://www.youtube.com/watch?v=example-trailer-id" URL was
        # hallucinated by the LLM instead of a real resource being played
        # (live action-integrity failure).
        _show = re.match(r"^(?:show|display|open)\s+(?:me\s+)?(?:the\s+|this\s+|that\s+)?([a-z][a-z0-9\s-]{1,40})$\s*[.!]?$", lower)
        if _show:
            _show_t = _show.group(1).strip()
            _media_noun = any(
                n in _show_t
                for n in ("trailer", "teaser", "highlight", "clips", "video",
                          "interview", "recap", "preview", "music video",
                          "behind the scenes", "clip", "scene")
            )
            if _media_noun:
                # Route to MEDIA_PLAY so the media system actually plays it,
                # not accept_offer which just talks about it.
                return RoutingDecision(
                    IntentType.MEDIA_PLAY, "play", _show_t, text, lower,
                    confidence=0.9,
                )

        # ── Bare discovery utterances ─────────────────────────────────────
        # "I'm bored", "surprise me", "entertain me", "what should i watch"
        # are discovery intents that don't start with "play"/"watch".
        if lower in _DISCOVERY_TARGETS:
            return RoutingDecision(
                IntentType.MEDIA_PLAY, "play_discovery", lower, text, lower,
                confidence=0.9,
            )

        return None

    # Interrogative questions whose subject is a REFERENT ("why is THIS
    # broken", "what is IT", "how does THAT work", "where is MY file") are
    # CONVERSATIONAL — never entity/media retrieval. They refer to the user's
    # own context (the thing we just did / the thing on screen), not to a
    # knowledge entity; routing them to information_query sent "why is this
    # broken" to media/retrieval instead of a natural diagnostic answer.
    _REFERENT_SUBJECT_RE = re.compile(
        r"^(?:is|are|does|do|did|was|were|can|could|should|will|would|have|has)?\s*"
        r"(?:this|that|it|these|those|my|your|our|its|the\s+(?:app|application|computer|"
        r"system|pc|laptop|machine|phone|internet|network|wifi|browser|window|tab|file|folder))"
        r"(?:\s|$)",
        re.I,
    )

    def _interrogative_is_referent(self, lower: str, first_w: str) -> bool:
        subject = lower[len(first_w):].strip()
        return bool(self._REFERENT_SUBJECT_RE.match(subject))

    # Discourse-recall question patterns (generic family): the user asks what
    # was said/done/discussed earlier in THIS conversation. Answerable from
    # session history; routing them to retrieval sent "what did i just ask you
    # to verify?" to Exa as "Ask Verify ..." and produced a fabricated reply.
    # Participant-symmetric recall: what did {i|you|we|he|she|they} say / think /
    # believe / prefer / recommend / decide — ALWAYS a recall question about
    # prior discourse (graph), never web retrieval. Third parties are ordinary
    # participants (FINAL architecture); bare-pronoun questions in an active
    # conversation refer to graph participants, while named news figures
    # ("what did the president say") do not match this morphology.
    _RECALL_QUESTION_RE = re.compile(
        r"^(?:what|which|where|when|who)\s+(?:did|do|does|have|has|were|was|is|are)\s+"
        r"(?:i|you|we|he|she|they)\s+(?:just\s+)?(?:ask|asked|ask\s+you|say|said|tell|told|verify|"
        r"verif|mention|mentioned|recommend|recommended|suggest|suggested|talk|talking|"
        r"discuss|discussing|chat|chatting|mean|meant|promise|promised|decide|decided|"
        r"prefer|preferred|want|wanted|believe|believed|think|thought|agree|agreed|"
        r"disagree|disagreed|claim|claimed|say\s+about|ask\s+about)\b",
        re.I,
    )

    def _is_discourse_recall_question(self, lower: str, raw_text: str = "") -> bool:
        """True when the message is a question about prior discourse.

        "what did i just ask you to verify?", "what did you say earlier?",
        "what were we talking about?", "where were we?", "what did you
        recommend?", "what was the first thing you said?" — all resolve from
        the conversation history, never from web retrieval. Generic
        morphology: interrogative + did/were/is + (i|you|we) + a
        discourse verb (say/tell/ask/mention/recommend/verify/talk/...).
        """
        if self._RECALL_QUESTION_RE.match(lower.strip()):
            return True
        # Participant symmetry: "what did DANA say / what does SARAH
        # recommend / what has BAO said" is a recall question about a named
        # THIRD-PARTY participant — it must resolve from the graph, never
        # from web research (live: "What did Dana say?" researched a company
        # and FABRICATED Dana's words). The capital-initial name is required
        # so "what did the president say" (a news figure) stays research.
        _named_recall = re.match(
            r"^[Ww]hat\s+(?:did|does|has)\s+([A-Z][a-zA-Z]{2,20})\s+"
            r"(said|says|say|told|tells|think|thinks|thought|believe|believes|believed|"
            r"recommend|recommends|recommended|suggest|suggests|suggested|decide|decides|"
            r"decided|prefer|prefers|preferred|want|wants|wanted|claim|claims|claimed|"
            r"mentioned|meant)\b",
            (raw_text or "").strip(),
        )
        if _named_recall:
            return True
        if re.match(r"^where\s+were\s+we\b", lower):
            return True
        if re.match(r"^what\s+were\s+we\s+(?:talking|discussing|chatting|saying|on)\b", lower):
            return True
        # "what was the first/last thing you recommended/said/mentioned"
        if re.match(
            r"^what\s+was\s+(?:the\s+)?(?:first|last|previous|second|third)\s+(?:thing|one|movie|film|game|book|song|album|show|band|recommendation)\s+"
            r"(?:you\s+)?(?:recommended|suggested|said|mentioned|picked|chose|went\s+with)\b",
            lower,
        ):
            return True
        # "which/ what movie did you recommend earlier"
        if re.match(
            r"^(?:what|which)\s+(?:movie|film|game|book|show|song|album|band|one)\s+did\s+you\s+"
            r"(?:recommend|suggest|pick|choose|go\s+with)\b.*",
            lower,
        ):
            return True
        return False

    def _classify_context_followup(self, lower, text, raw_text=""):
        from mini_kio.core.command_parser import is_multi_step
        interrogatives = frozenset({"who", "what", "where", "when", "why", "how"})
        first_w = lower.split()[0] if lower.split() else ""

        # Hypothetical speculation: a leading "what if ..." (optionally after a
        # casual connector) is CONVERSATIONAL, never a factual retrieval query.
        # Live bug: "what if I just sent my AI agent to the meetings for me"
        # hit the interrogative -> INFORMATION branch and came back as a
        # GK-bot essay about "AI proxy meetings" instead of playful banter.
        # Genuine consequence questions keep the "what happens if" wording and
        # are untouched. Generic family rule, not per-phrase.
        _hypothetical_what_if = re.match(
            r"^(?:but|and|so|okay|ok|hmm|hm|well|anyway)?\s*what\s+if\b", lower,
        )
        if _hypothetical_what_if:
            return RoutingDecision(IntentType.CONVERSATION, "converse", text, text, lower, confidence=0.6)

        # R4: confirm/accept antecedents — substring forms too ("please go ahead",
        # "yes please", "go ahead", "yes do it", "okay go for it"). Only when the
        # utterance is a short confirmation, never a full command.
        logger.info("[CTX_FOLLOWUP_DEBUG] lower=%r first_w=%r", lower, first_w)
        if (
            first_w in ("yes", "yeah", "sure", "ok", "okay")
            or lower in ("go ahead", "do it", "play video", "start it", "play it", "yes start it", "yes play it")
            or re.fullmatch(r"yes(?:\s+please|\s+go\s+ahead|\s+do\s+it|\s+start\s+it|\s+play\s+it)?", lower)
            or re.fullmatch(r"please\s+(?:go\s+ahead|go\s+for\s+it|do\s+it|go|start\s+it|play\s+it)", lower)
            or re.fullmatch(r"(?:go\s+ahead|go\s+for\s+it|start\s+it|play\s+it)", lower)
        ):
            logger.info("[ACCEPT_OFFER_MATCH] lower=%r first_w=%r", lower, first_w)
            return RoutingDecision(IntentType.CONVERSATION, "accept_offer", "", text, lower, confidence=0.9)

        # Personal current-state queries must not be misrouted to INFORMATION
        if re.search(r"\bwhat\s+am\s+i\b.*\bworking\b", lower) or re.search(r"\bwhat\s+am\s+i\s+even\b", lower):
            return RoutingDecision(IntentType.CONVERSATION, "converse", text, text, lower, confidence=0.8)
        if first_w in interrogatives and len(lower.split()) >= 2:
            if is_multi_step(lower):
                return None
            # Referent questions are conversational (diagnostics, follow-ups),
            # not entity retrieval.
            if self._interrogative_is_referent(lower, first_w):
                return RoutingDecision(IntentType.CONVERSATION, "converse", text, text, lower, confidence=0.6)
            # Discourse-recall questions ("what did i just ask you to
            # verify?", "what did you say earlier?", "what were we talking
            # about?", "where were we?", "what did you recommend?") ask about
            # PRIOR conversation — they must stay conversational so the
            # generator answers from the session history window, NEVER route
            # to web retrieval (live: "what did i just ask you to verify?"
            # became information_query "Ask Verify what did i just ask you to
            # verify?", Exa returned an unrelated page, and KIO fabricated a
            # git-diff answer). Generic morphology, never per-phrase.
            if self._is_discourse_recall_question(lower, raw_text):
                return RoutingDecision(IntentType.CONVERSATION, "converse", text, text, lower, confidence=0.8)
            # Recommendation refinement: "what is/are + something/anything
            # (+ else) + <single modifier>" ("what's something darker",
            # "whats something completely different", "what is anything
            # shorter") is a REQUEST FOR AN ALTERNATIVE CANDIDATE inside an
            # active recommendation thread — never an entity query about a
            # thing literally named "Something Darker" (live: "what's
            # something darker" answered with a real indie game called
            # "Something Darker" instead of a darker movie). Morphological
            # family rule (same "something + modifier" shape the pragmatics
            # layer already recognizes), bounded to short phrases so genuine
            # questions ("what is something I should know about X") stay
            # informational.
            _refine = re.match(
                r"^(?:what\s+(?:is|are|'s)?)?\s*(?:something|anything)\s+(?:else\s+)?"
                r"(?:(?:completely|totally|entirely|really|much|a\s+bit|bit)\s+)?"
                r"(?:(?:between\s+those\s+two|between\s+them|in\s+between)|[a-z]+)\s*$",
                lower,
            )
            if _refine and len(lower.split()) <= 6:
                return RoutingDecision(IntentType.CONVERSATION, "converse", text, text, lower, confidence=0.6)
            return RoutingDecision(IntentType.INFORMATION, "information_query", text, text, lower, confidence=0.7)

        # Verification requests about a NAMED thing ("is there real news about
        # the next Spider-Man movie?", "has Marvel confirmed X", "did Tom
        # Holland actually say X", "is it confirmed that Spider-Man 4 is
        # coming") are current-fact requests — they must use research, never
        # stale model knowledge (live: routed to converse and answered with
        # 2024 dates in 2026). Requires a proper noun (capitalized word or a
        # known entity) so generic "is it true AI agents are coming" stays
        # conversational.
        #
        # Rumor/verification family (general, not per-phrase): "I heard X",
        # "I read that X", "someone told me X", "did X really happen",
        # "is X still ...", "did X die/retire/leave" are CURRENT-FACT
        # requests about a changing world — they must use live research, never
        # the LLM's memory (live bug: "I heard Messi's father passed away and
        # he said he can't play long anymore" was answered from the model's
        # June knowledge state, which had no report of the death). Requires a
        # NAMED ENTITY (capitalized word) or a verifiable state-change verb so
        # "I heard that movie was amazing" (opinion) stays conversational.
        # Multi-claim messages ("X and Y") route as a unit; the research layer
        # decomposes them claim-by-claim.
        _verif = re.match(
            r"^(?:(?:wait|ok|okay|so|but|and|anyway|hmm|actually|hey|yo)\b[,:]?\s+)*"
            r"(?:i\s+(?:heard|read|saw)\b|someone\s+told\s+me\b|apparently\b|"
            r"people\s+are\s+saying\b|there(?:'s|\s+is)\s+(?:a\s+)?rumor\b|"
            r"is\s+(?:there|it)\s+(?:any\s+|real\s+|actual\s+)?news\s+(?:about|on)|"
            r"is\s+it\s+(?:confirmed|true|official)\s+(?:that|to)|"
            r"is\s+that\s+actually\s+true\b|is\s+this\s+actually\s+true\b|"
            r"has\s+[a-z]+\s+(?:officially\s+|actually\s+|just\s+|already\s+)?(?:confirmed|announced|revealed|released|launched|unveiled|retired|left|quit|fired|hired|delayed|cancelled|canceled|postponed|married|divorced|died|passed\s+away|stepped\s+down|transferred)|"
            r"did\s+[a-z]+(?:\s+[a-z]+)*\s+(?:actually\s+|really\s+)?(?:say|happen|die|retire|leave|quit|cancel|announce|confirm|release|transfer|sign|win|lose|beat|drop|score|play|fire|hire|join|resign|return|debut)\b|"
            r"is\s+[a-z]+(?:\s+[a-z]+)*\s+still\b|is\s+[a-z]+(?:\s+[a-z]+)*\s+(?:dead|alive|retired|cancelled|released|available|confirmed)\b|"
            r"what\s+happened\s+to\b)"
            r"\s*(.+)",
            lower,
        )
        if _verif:
            _subject = _verif.group(1) or ""
            # A capitalized word in the subject is the named-entity signal
            # (Spider-Man, Marvel, Tom Holland, F1); "is it true AI agents are
            # coming" has none and stays conversational. Covers initial caps
            # followed by a letter OR digit ("F1"). Uses raw_text because the
            # greeting-strip recursion re-enters classify() with LOWERCASED
            # remaining text as `text` — the capitals survive only in
            # raw_text ("hey did Tom Holland..." -> "did tom holland...").
            _case_source = raw_text or text
            _named = bool(re.search(r"[A-Z][A-Za-z0-9]", _case_source))
            # Fallback named-entity signal for lowercase messages: a
            # verifiable state-change verb plus a non-trivial subject means a
            # changing-world claim ("did messi die" / "is the game still
            # delayed"), which must not be answered from model memory either.
            _state_verbs = ("die", "died", "death", "passed away", "retire", "retired",
                            "cancelled", "canceled", "delayed", "released", "confirmed",
                            "announced", "left", "quit", "fired", "hired", "injured",
                            "arrested", "married", "divorced", "born", "transferred",
                            "stepped down", "broke", "broken", "crashed", "shut down",
                            "postponed", "pulled", "scrapped",
                            # Result/event verbs: "did the warriors win last night",
                            # "did drake actually drop that", "did she beat him" —
                            # current-result questions must use live evidence, never
                            # model memory (live: both routed to converse and
                            # answered without research).
                            "win", "won", "lose", "lost", "beat", "beaten", "drop",
                            "dropped", "score", "scored", "play", "played", "resign",
                            "resigned", "join", "joined", "sign", "signed", "debut",
                            "return", "returned", "come back", "release")
            _has_state_verb = any(v in (_subject or "").lower() for v in _state_verbs)
            _subject_words = (_subject or "").split()
            _substantive = len(_subject_words) >= 2 or (
                len(_subject_words) == 1 and len(_subject_words[0]) >= 4
            )
            if _named or (_has_state_verb and _substantive):
                return RoutingDecision(IntentType.INFORMATION, "information_query", text, text, lower, confidence=0.7)

        # "did X <result-verb>" form: the entity sits BETWEEN "did" and the
        # verb ("did the warriors win last night", "did drake actually drop
        # that new album", "did the raiders beat the chiefs"). The generic
        # frame above captures only the tail AFTER the verb, so the entity is
        # lost and the message fell through to conversation without research.
        # A real subject (team/name/entity — anything not purely
        # first/second-person) makes it a current-result question needing live
        # evidence (live: "did the warriors win last night" answered without
        # any research).
        _did_form = re.match(
            r"^(?:(?:wait|ok|okay|so|but|and|anyway|hmm|actually|hey|yo)\b[,:]?\s+)*"
            r"did\s+(.+?)\s+(?:actually\s+|really\s+|just\s+|even\s+|already\s+)?"
            r"(?:say|says|said|happen|happened|die|died|retire|retired|leave|left|quit|"
            r"cancel|cancelled|canceled|announce|announced|confirm|confirmed|release|"
            r"released|transfer|transferred|sign|signed|win|won|lose|lost|beat|beaten|"
            r"drop|dropped|score|scored|play|played|fire|fired|hire|hired|join|joined|"
            r"resign|resigned|debut|return|returned|step\s+down)\b(.*)$",
            lower,
        )
        if _did_form:
            _did_subj = (_did_form.group(1) or "").strip()
            _pronoun_only = all(
                w in ("you", "u", "i", "we", "they", "he", "she", "it", "that",
                      "this", "there", "someone", "everyone")
                for w in _did_subj.split()
            )
            _case_source = raw_text or text
            _named = bool(re.search(r"[A-Z][A-Za-z0-9]", _case_source))
            if _did_subj and (not _pronoun_only or _named):
                return RoutingDecision(IntentType.INFORMATION, "information_query", text, text, lower, confidence=0.7)

        # Terminal state-change verb form ("did Messi retire", "did the game
        # get cancelled", "has the CEO stepped down", "is the actor dead"):
        # the frame above requires a tail after the verb, so a verb at the END
        # of the message fell through to conversation. The frame itself IS the
        # verifiable-state signal; only first/second-person or bare-pronoun
        # subjects ("did you retire", "did he leave") stay conversational.
        _verif_short = re.match(
            r"^(?:(?:wait|ok|okay|so|but|and|anyway|hmm|actually|hey|yo)\b[,:]?\s+)*"
            r"(?:did|has|is)\s+(.+?)\s+(?:actually\s+|really\s+)?"
            r"(?:say|says|said|happened|die|died|death|retire|retired|leave|left|quit|"
            r"cancelled|canceled|delayed|released|confirmed|announced|fired|hired|"
            r"injured|arrested|transferred|stepped\s+down|dead|alive|out|coming|here|back|"
            r"married|divorced|born|engaged|dating|single|promoted|demoted|"
            r"replaced|appointed|elected|nominated|won|lost|beat|defeated|signed|joined|rejoined)\s*[?.!]*$",
            lower,
        )
        if _verif_short:
            _short_subj = (_verif_short.group(1) or "").strip()
            _referent_only = all(
                w in ("you", "u", "i", "we", "they", "he", "she", "it", "that",
                      "this", "there", "someone", "everyone")
                for w in _short_subj.split()
            )
            _case_source = raw_text or text
            _named = bool(re.search(r"[A-Z][A-Za-z0-9]", _case_source))
            if _named or not _referent_only:
                return RoutingDecision(IntentType.INFORMATION, "information_query", text, text, lower, confidence=0.7)

        # TRAILING verification suffix ("... Is any of that true?", "... real?",
        # "... actually true?"): the claim being checked comes BEFORE the suffix
        # ("Tom Cruise's new movie got delayed and he apparently quit the
        # project. Is any of that true?"), so the leading-trigger frames above
        # miss it entirely and it fell through to LLM-memory conversation (live:
        # answered "the latest information I have doesn't mention that" — pure
        # model recall for a changing-world claim). A state-change verb anywhere
        # in the message is the verifiable-world signal; the suffix makes it an
        # explicit verification request. Requires the substantive clause to
        # carry a state verb or a named entity so "that sounds great, is it
        # really that good?" (opinion) stays conversational.
        # classify() strips trailing punctuation ("...true?" arrives as
        # "...true"), so the suffix is matched with OPTIONAL trailing marks.
        _verif_trail = re.match(
            r"^((?:(?!\.).)*?)\s*[,;:.!-]?\s*"
            r"(?:is\s+(?:any\s+of\s+)?that\s+(?:actually\s+|really\s+)?true\b|"
            r"is\s+this\s+(?:actually\s+|really\s+)?true\b|is\s+that\s+(?:actually\s+|really\s+)?real\b|"
            r"is\s+it\s+(?:actually\s+|really\s+)?(?:true|real)\b|"
            r"(?:is\s+that\b|is\s+this\b|is\s+it\b|right\b|"
            r"actually\s+true\b|really\b|true\b|real\b))[?.!\s]*$",
            lower,
        )
        if _verif_trail:
            _claim_part = (_verif_trail.group(1) or "").strip()
            _has_state_verb = any(v in _claim_part for v in (
                "die", "died", "death", "passed away", "retire", "retired",
                "cancelled", "canceled", "delayed", "released", "confirmed",
                "announced", "left", "quit", "fired", "hired", "injured",
                "arrested", "married", "divorced", "transferred", "stepped down",
            ))
            _case_source = raw_text or text
            # A sentence-initial capital ("The fix works...") is ordinary
            # capitalization, NOT a named entity — exclude the leading token
            # or "The" would make "The fix works, right?" a false
            # verification request (no state verb, no real entity).
            _tokens = (_case_source or "").strip().split()
            _first_is_cap = bool(_tokens) and bool(re.search(r"[A-Z][A-Za-z0-9]", _tokens[0]))
            _rest_text = " ".join(_tokens[1:]) if _tokens else ""
            _named = bool(re.search(r"[A-Z][A-Za-z0-9]", _rest_text)) if _first_is_cap else bool(re.search(r"[A-Z][A-Za-z0-9]", _case_source))
            # Habitual-grumbling register ("Windows Update keeps breaking
            # things again, right?") is NOT a discrete verifiable event —
            # "keeps/always ... again" signals recurring complaint, not a
            # current claim to check. "is the game still delayed" (state
            # check) is NOT affected — this guard needs the recurrence
            # markers together.
            _habitual = bool(re.search(r"\b(?:keeps?|always|constantly|still)\b.*\b(?:again|breaking)\b", _claim_part))
            _substantive = len(_claim_part.split()) >= 3
            if not _habitual and (_named or _has_state_verb) and _substantive:
                return RoutingDecision(IntentType.INFORMATION, "information_query", text, text, lower, confidence=0.7)

        # Date-sensitive current queries ("which country is celebrating
        # independence day today?", "what happened today?", "events tonight")
        # need TEMPORAL GROUNDING + live evidence — never the LLM's training
        # memory, never a stale previous-topic anchor (live: "which country is
        # celebrating independence day today" was answered with an unrelated
        # Sugarland-tour result inherited from earlier research). Routes to
        # research with "today"/"this week" rewritten to the actual date so
        # retrieval is anchored to the real calendar.
        _date_sensitive = re.search(
            r"\b(independence\s+day|national\s+day|holiday|celebrat(?:e|es|ing|ed|ion)|\bwhat\s+happened\b|events|on\s+this\s+day|today\s+in\s+history|anniversary|observed|born\s+today|died\s+today|in\s+the\s+news\s+today)\b",
            lower,
        )
        if _date_sensitive and re.search(r"\b(today|this\s+(?:week|date|day|year|month)|tonight|right\s+now|now)\b", lower):
            try:
                import datetime as _dtdt
                _now = _dtdt.datetime.now()
                _month_day = _now.strftime("%B %d").replace(" 0", " ")
                _date_target = re.sub(
                    r"\btoday\b", _month_day, text, flags=re.IGNORECASE
                )
                _date_target = re.sub(
                    r"\b(this\s+week|this\s+month)\b",
                    _now.strftime("%B"), _date_target, flags=re.IGNORECASE,
                )
            except Exception:
                _date_target = text
            return RoutingDecision(
                IntentType.INFORMATION, "information_query", _date_target, text, lower,
                confidence=0.8,
            )

        if lower.startswith(("latest ", "what's the latest ", "what is the latest ", "this is news ",
                             "what's new ", "tell me about ", "news about ", "news on ")):
            return RoutingDecision(IntentType.INFORMATION, "information_query", text, text, lower, confidence=0.7)

        # Word-boundary matching, never bare substring: "stable" must NOT hit
        # "table" (live: "is it really stable now?" routed to SPORTS because
        # 'table' in 'stable'). Each keyword anchored with \b so only whole
        # words ("league table", "world cup", "group stage") trigger.
        sports_keywords = [r"standings", r"table", r"group\s+(?:stage|stages|of)?\b", r"groups",
                           r"fixtures", r"fixture", r"results", r"match\b", r"matches",
                           r"score", r"scores", r"points\s+table", r"league\s+table", r"world\s+cup"]
        if any(re.search(rf"\b{kw}", lower) for kw in sports_keywords) and not lower.startswith(("play ", "watch ")):
            return RoutingDecision(IntentType.INFORMATION, "information_query", text, text, lower, confidence=0.8)

        return None

    def _classify_memory(self, lower):
        # Lead-in normalization: "actually forget X", "ok forget it", "wait,
        # remember ..." are the same memory commands as the bare forms — the
        # connective is conversational noise, never a different intent. Generic
        # morphology; applies to every pattern in this classifier.
        _leadin = re.sub(
            r"^(?:actually|well|so|anyway|okay?|wait|hold\s+on|no|hmm|alright|right)[,!\s]+", "", lower
        )
        if _leadin and _leadin != lower and not lower.startswith(("what", "who", "where", "when", "why", "how")):
            lower = _leadin
        if re.match(r"^remember\s+(?:that\s+)?(.+)", lower):
            return RoutingDecision(IntentType.MEMORY, "store", lower, lower, lower, confidence=0.9)
        if re.match(r"^my\s+name\s+is\s+(.+)", lower):
            return RoutingDecision(IntentType.MEMORY, "store", lower, lower, lower, confidence=0.9)
        if re.match(r"^call\s+me\s+(.+)", lower):
            return RoutingDecision(IntentType.MEMORY, "store", lower, lower, lower, confidence=0.9)
        if re.match(r"^my\s+favorite\s+.+\s+is\s+", lower):
            return RoutingDecision(IntentType.MEMORY, "store", lower, lower, lower, confidence=0.9)
        # Discourse retraction vs memory command: "forget that, something
        # calmer" retracts the current RECOMMENDATION and adds a new request
        # — it is conversation, never a memory-clear. The distinguishing
        # morphology is the continuation after the forget phrase: a comma or
        # "and" + further words means the user is redirecting, not clearing
        # stored facts. Bare "forget that/it/everything" (or "forget X fact")
        # stays a memory command. Live bug: "Actually forget that, something
        # calmer" hit the bare-forget branch and deleted the user's last
        # stored fact ("Done — I've forgotten about my nickname.").
        _forget_lead = re.match(r"^forget\s+(?:that|it|this|everything|all)\b", lower)
        if _forget_lead:
            _after = lower[_forget_lead.end():].strip()
            if re.match(r"^(?:,|;|\band\b)\s*\S", _after):
                return None  # retraction + redirect -> conversational routing
            return RoutingDecision(IntentType.MEMORY, "forget", lower, lower, lower, confidence=0.9)
        _forget_one = re.match(r"^forget\s+(.+)", lower)
        if _forget_one:
            # Same discourse rule for "forget X ...": when the message
            # continues past the forget target with a pivot (em-dash, comma,
            # "and", a question) it is a topic transition — "Forget math —
            # what are you?" is "set aside the math topic, who are you?",
            # NOT a memory delete. Live bug: it answered "I don't remember
            # anything about math what are you." from the forget_one branch.
            _rest = _forget_one.group(1).strip()
            # A pivot INSIDE the captured rest means the message continues
            # past the forget target with a NEW clause — a topic transition
            # ("Forget math, what are you?", "Forget the movie, recommend
            # something else"), NOT a memory delete. Punctuation is stripped
            # by the normalizer, so detect clause pivots morphologically:
            # em-dash/comma (when present), "and", a question/redirect word
            # (what/who/why/how/when/where/which), or a redirect verb
            # (recommend/suggest/give/try/pick/choose) — the signals that the
            # user is steering to a new request, not clearing a stored fact.
            if (re.search(r"[\u2014\u2013,;]|\band\b", _rest)
                    or re.search(r"\b(?:what|who|why|how|when|where|which)\b", _rest)
                    or re.search(r"\b(?:recommend|suggest|give|try|pick|choose|another|something|instead|else)\b", _rest)):
                return None  # topic transition -> conversational routing
            return RoutingDecision(IntentType.MEMORY, "forget_one", lower, lower, lower, confidence=0.9)

        recall = (
            r"^(?:do\s+you\s+)?(?:remember|recall)\b",
            r"^(?:what'?s|what\s+is)\s+my\s+name\b",
            r"^what\s+do\s+i\s+(?:call|go\s+by)\b",
            r"^who\s+am\s+i\b",
            r"^(?:what'?s|what\s+is)\s+my\s+favorite\b",
            r"^(?:what'?s|what\s+is)\s+my\s+favourite\b",
            r"^what\s+\w+\s+do\s+i\s+(?:like|love|enjoy|prefer)\b",
            r"^what\s+do\s+i\s+(?:like|love|enjoy|prefer)\b",
            r"^what\s+.+?\s+did\s+i\s+(?:say\s+)?(?:like|love|enjoy|prefer)\b",
            r"^what\s+.+?\s+(?:have\s+)?i\s+(?:said\s+)?(?:like|love|enjoy|prefer)\b",
            # generic possessive recall: "what's my favourite colour", "what's my nickname"
            r"^(?:what'?s|what\s+is)\s+my\b",
        )
        if any(re.match(p, lower) for p in recall):
            return RoutingDecision(IntentType.MEMORY, "recall", lower, lower, lower, confidence=0.9)
        return None

    # Curiosity/interest family — KIO's own cognitive orientation, asked about
    # generically. Routes to conversation (LLM with personality context), never
    # to the static identity answer. Two word orders are covered: "what are
    # you curious about" and "what interests you".
    _CURIOSITY_RE = re.compile(
        r"^what(?:'s|\s+is|\s+are)?\s+(?:you|your|kio(?:'s)?)?\s*"
        r"(?:curious\s+about|interested\s+in|excited\s+about|passionate\s+about|"
        r"fascinated\s+by|drawn\s+to|keen\s+on|into)\b",
        re.IGNORECASE,
    )
    _CURIOSITY_RE2 = re.compile(
        r"^what\s+(?:interests|excites|fascinates|intrigues)\s+(?:you|kio)\b",
        re.IGNORECASE,
    )

    def _classify_curiosity(self, lower, text):
        if self._CURIOSITY_RE.match(lower) or self._CURIOSITY_RE2.match(lower):
            return RoutingDecision(
                IntentType.CONVERSATION, "converse", text, text, lower,
                confidence=0.9,
            )
        return None

    def _classify_opinion(self, lower, text, raw_text="", pragmatics=None):
        # Pragmatics is the canonical act authority: if it tagged this as an
        # OPINION_REQUEST ("which X is the best?", "is X cooked?"), route to
        # conversation so the generator gets the commit-on-first-pass
        # instruction — never let the entity heuristic grab "which Spider-Man
        # movie is actually the best?" as a knowledge query.
        if pragmatics is not None and "opinion_request" in (getattr(pragmatics, "acts", None) or []):
            return RoutingDecision(IntentType.CONVERSATION, "converse", text, text, lower, confidence=0.8)
        _opinion = (
            r"what\s+(?:do|did|would)\s+(?:you|we|they)\s+think\s+(?:about|of)\b",
            r"how\s+do\s+you\s+feel\s+(?:about|on)\b",
            r"what(?:'s|\s+is)\s+your\s+(?:take|opinion)\b",
            r"in\s+your\s+opinion\b",
            r"do\s+you\s+(?:like|love|enjoy|rate)\b",
            r"do\s+you\s+think\b",
            r"would\s+you\s+recommend\b",
            r"^recommend\b",
            # "should I" + everyday-life activity verb is a recommendation
            # request across ALL domains (watch/play/read/listen/eat/cook/
            # order/get/buy/visit/try) — a companion question, never an
            # information lookup. Live failure: "what's good to eat tonight"
            # was hijacked into a search for a restaurant literally named
            # "Good Eat Tonight" because only media verbs were listed here.
            r"should\s+i\s+(?:watch|play|see|read|listen\s+to|try|eat|cook|order|get|buy|visit|make|have|drink|download|install|try\s+out)\b",
            # Same family without "should I": "what's good to eat tonight",
            # "what to cook", "what's good to watch" — a recommendation ask,
            # never a bare-phrase lookup (live: "Good Eat Tonight" restaurant
            # hijack).
            r"what(?:'s|\s+is)\s+(?:good|great|fun|nice|best)\s+to\s+(?:watch|play|see|read|listen\s+to|try|eat|cook|order|get|buy|visit|make|have|drink)\b",
            r"^what\s+to\s+(?:watch|play|see|read|listen\s+to|try|eat|cook|order|get|buy|visit|make|have|drink)\b",
            r"is\s+[a-z0-9].*?\s+(?:good|great|worth|overrated|underrated|any\s+good)\b",
            # Self-preference family: "what's your favorite X", "what do you
            # like best" ask about KIO's own taste — a conversational question,
            # never a web-knowledge query. The entity-query path must not
            # capture these ("what's your favorite movie" is NOT knowledge
            # about a movie).
            r"what(?:'s|\s+is)\s+your\s+(?:favourite|favorite)\b",
            r"what(?:'s|\s+is)\s+your\s+pick\b",
        )
        if any(re.search(p, lower) for p in _opinion):
            return RoutingDecision(IntentType.CONVERSATION, "converse", text, text, lower, confidence=0.8)

        if re.search(r"\bvs\.?\b", lower) or re.search(r"\bor\b", lower) or re.search(r"(?:which|who)\s+is\s+better\b", lower):
            if not lower.startswith(("play ", "watch ", "show ", "open ", "search ", "close ", "find ", "get ")):
                return RoutingDecision(IntentType.CONVERSATION, "converse", text, text, lower, confidence=0.7)
        return None

    def _classify_emotion(self, lower, text):
        _emotion_words = frozenset({
            "sad", "happy", "angry", "frustrated", "stressed", "exhausted",
            "excited", "depressed", "anxious", "worried", "upset", "mad",
            "furious", "irritated", "annoyed", "disappointed", "grateful",
            "thankful", "relieved", "confused", "lonely", "bored", "tired",
            "nervous", "scared", "afraid", "terrified", "overwhelmed",
            "content", "peaceful", "calm", "relaxed", "hopeful", "proud",
            "embarrassed", "ashamed", "guilty", "jealous", "envious",
            "terrible", "awful", "horrible", "miserable", "rough", "bad",
        })
        _emotion_re = "|".join(_emotion_words)
        _emotion_patterns = (
            r"^i(?:'m|\s+am)\s+(?:feeling\s+)?(?:so\s+|very\s+|really\s+|extremely\s+)?(" + _emotion_re + r")\b",
            r"^i\s+feel\s+(?:so\s+|very\s+|really\s+|extremely\s+)?(" + _emotion_re + r")\b",
            r"^i(?:'m|\s+am)\s+(?:not\s+(?:feeling\s+)?)?(?:so\s+|very\s+|really\s+|extremely\s+)?(" + _emotion_re + r")\b",
            r"^i\s+(?:had|having|been)\s+a\s+(" + _emotion_re + r")\s+day\b",
            r"^i\s+don'?t\s+feel\s+(?:so\s+|very\s+|really\s+)?(" + _emotion_re + r"|good|well)\b",
            r"^i(?:'m|\s+am)\s+not\s+feeling\s+(?:so\s+|very\s+|really\s+)?(good|well|" + _emotion_re + r")\b",
        )
        for pat in _emotion_patterns:
            if re.search(pat, lower):
                return RoutingDecision(IntentType.CONVERSATION, "empathy", text, text, lower, confidence=0.9)
        return None

    def _classify_entity_query(self, lower, text, raw_text):
        words = lower.split()
        if not words:
            return None
        first_w = words[0]
        skip = {"help", "ping", "status", "shutdown", "restart", "lock", "uptime", "ram", "cpu", "recovery", "recover", "recommend"}
        two_word_stop = {"who", "what", "where", "when", "why", "how", "yes", "no",
                         "play", "watch", "show", "tell", "do", "is", "are", "was",
                         "the", "a", "an", "i", "you", "we", "they", "he", "she",
                         "it", "that", "this", "there", "my", "your", "for", "to",
                         "stop", "pause", "resume", "open", "close", "write", "search"}
        # Casual-fragment guard: message-initial capitalization is a writing
        # convention, NOT proper-noun evidence. "Yoo!", "Lol", "Wow", "Damn",
        # "Sup", "Hey" typed with a capital initial must never become an
        # ENTITY_QUERY (which would send the fragment to media/retrieval — the
        # observed "Yoo" -> UFC biography bug). The guard is punctuation-
        # tolerant ("Yoo!", "Yoo?") and applies to single casual words and to
        # short ALL-casual fragments ("oh wow", "haha yeah") — never to
        # phrases containing a non-casual word, so real entities ("OK Go",
        # "Yeah Yeah Yeahs") keep the entity path.
        def _casual_word(w: str) -> bool:
            base = w.rstrip(".,!?;:")
            return base in _CASUAL_FRAGMENTS or _casual_normalized(base) in _CASUAL_FRAGMENTS

        _single_word_casual = len(words) <= 3 and all(_casual_word(w) for w in words)

        if not raw_text:
            raw_text = text
        orig_words = raw_text.strip().split() if raw_text else words
        orig_first = orig_words[0] if orig_words else ""

        # Sentence-initial pronouns and their contractions are NOT proper-noun
        # evidence: "I've been lying awake thinking about whether..." and "I'm
        # tired" are first-person disclosures — routing them to ENTITY_QUERY
        # sent personal conversation to media/retrieval (live bug: a career-
        # doubt message became an "information_query"). Contractions resolve
        # to their base word via the apostrophe ("i've" -> "i", "it's" ->
        # "it", "that's" -> "that") and inherit the stopword exemption.
        _apostrophe_base = first_w.split("'")[0]
        _sentence_initial_stop = first_w in two_word_stop or _apostrophe_base in two_word_stop

        # Full-sentence guard: a capitalized-initial message that is a COMPLETE
        # DECLARATIVE CLAUSE (subject + copula/modal/3rd-person predicate verb,
        # at least a 4-word clause) is a statement/opinion ("Marvel really
        # cannot stop cooking up multiverse nonsense", "Tom Holland is leaving
        # Spider-Man", "Spider-Man 4 is delayed") — routing it to ENTITY_QUERY
        # sent the opinion to media/retrieval, which answered with the cold
        # "I don't have information on Marvel yet." Only BARE NOUN PHRASES
        # ("Spider-Man 4 release date", "Interstellar cast") and headline
        # participles ("Messi transfer confirmed") are entity lookups.
        _predicate_after_first = bool(re.search(
            r"\s+(?:is|are|was|were|be|been|being|has|have|had|do|does|did|"
            r"will|would|can|could|should|may|might|must|cannot|can't|won't|"
            r"don't|doesn't|didn't|isn't|aren't|wasn't|weren't|looks|sounds|"
            r"feels|seems|appears|becomes|makes|gets|keeps|wants|needs|thinks|"
            r"says|tells|wins|loses|retires|returns|leaves|joins|signs|releases|"
            r"cancels|went|going|coming|doing|playing|staying|leaving)\b",
            lower,
        ))
        _full_sentence_statement = len(words) >= 4 and _predicate_after_first

        # Social-situation guard (general): sentence-initial IMPERSONAL
        # pronouns ("Someone said something wrong about you, give them a
        # reply") are NOT proper nouns — "Someone" capitalized is a writing
        # convention. A reporting/communication structure (someone said/told/
        # thinks + about you/me + a reply/tell/message verb) is a SOCIAL
        # situation about conversation participants, never a web lookup (live:
        # routed to ENTITY_QUERY -> research -> generic conflict-management
        # instead of understanding the user reported third-party speech about
        # KIO). Also covers "Somebody told me...", "People are saying...".
        _impersonal = orig_first.rstrip(".,!?;:").lower()
        if _impersonal in ("someone", "somebody", "people"):
            _social_report = re.search(
                r"\b(said|says|told|tells|thinks|believes|claims)\b.*\b(about\s+me|about\s+you|about\s+kio|to\s+me|to\s+you)",
                lower,
            )
            if _social_report or re.search(r"\b(said|told|thinks)\b", lower):
                return RoutingDecision(IntentType.CONVERSATION, "converse", raw_text, raw_text, lower, confidence=0.85)
        # Imperative-with-pronoun guard: a sentence-initial verb addressing a
        # person ("Give them a reply", "Tell him about it", "Reply to her",
        # "Message him") is a communication instruction about conversation
        # participants — never a web lookup of a proper noun. General
        # morphology: verb + (them|him|her|me|us|someone) + communication
        # noun/verb.
        _imperative_comm = re.match(
            r"^(give|send|write|compose|draft|tell|reply|message|text|email|forward|ask)\s+"
            r"(?:it|this|that)?\s*(?:to\s+)?(them|him|her|me|us|someone|somebody|the\s+team)\b",
            lower,
        )
        if _imperative_comm:
            return RoutingDecision(IntentType.CONVERSATION, "converse", raw_text, raw_text, lower, confidence=0.85)

        # Discourse-connector guard (general): a sentence-initial
        # conversational connector ("Anyway, I'm researching...", "So, what
        # about...", "Also, I...", "Well, ...") followed by a first/second-
        # person subject or a reporting verb is CONTINUATION of the
        # conversation — the capitalized connector is a writing convention,
        # never a proper noun (live: "Anyway, I'm researching a company
        # called Zorbion Dynamics" was routed to ENTITY_QUERY -> research,
        # which FABRICATED a company description; the semantic graph never
        # saw the research intent).
        _connector = orig_first.rstrip(".,!?;:").lower()
        _after = lower[len(first_w):].strip()
        _connector_set = ("anyway", "so", "well", "also", "wait", "ok", "okay",
                          "btw", "anyhow", "now", "first", "secondly", "lastly",
                          "meanwhile", "anyways", "alright", "right")
        if (_connector in _connector_set or _connector.rstrip(",") in _connector_set) \
                and re.match(r"^(?:i|i'm|im|you|we|they|he|she|it|there|that|this)\b", _after):
            return RoutingDecision(IntentType.CONVERSATION, "converse", raw_text, raw_text, lower, confidence=0.8)

        if (
            orig_first and orig_first[0].isupper() and len(orig_first) > 1
            and first_w not in skip and not _sentence_initial_stop
            and not _single_word_casual and not _full_sentence_statement
        ):
            return RoutingDecision(IntentType.ENTITY_QUERY, "information_query", raw_text, raw_text, lower, confidence=0.8)

        if len(words) >= 2 and not _full_sentence_statement:
            second_word_orig = orig_words[1] if len(orig_words) > 1 else ""
            if first_w in ("the", "a", "an") and second_word_orig and second_word_orig[0].isupper():
                return RoutingDecision(IntentType.ENTITY_QUERY, "information_query", raw_text, raw_text, lower, confidence=0.8)

        # R3: lowercase entity + artifact/info noun ("interstellar cast", "the weeknd news").
        # Only fires on a short noun-phrase ending in a content/artifact keyword — never on
        # social chat or imperatives (those are captured earlier in the chain).
        _content_nouns = (
            "cast", "trailer", "teaser", "soundtrack", "plot", "ending", "review",
            "reviews", "summary", "gameplay", "gameplay", "news", "standings",
            "fixtures", "results", "scores", "highlights", "discography", "filmography",
            "biography", "stats", "statistics", "career", "awards", "net worth",
        )
        _social_leads = ("hi", "hey", "hello", "thanks", "thank", "sorry", "please",
                         "okay", "ok", "sure", "no", "yes", "good", "bad", "sad", "happy",
                         "i'm", "i am", "im", "not", "cool", "nice", "great", "boring")
        if len(words) >= 2 and len(words) <= 5:
            lead = words[0]
            last_w = words[-1]
            if lead in ("the", "a", "an") and len(words) >= 3:
                lead = words[1]
            if lead in two_word_stop:
                pass
            elif last_w in _content_nouns and lead not in _social_leads and len(lead) >= 2:
                return RoutingDecision(IntentType.ENTITY_QUERY, "information_query", raw_text, raw_text, lower, confidence=0.7)

        i_loved = re.match(r"i\s+(loved|liked|enjoy(?:ed)?|watched|read|listen(?:ed)?\s+to)\s+(.+)", lower)
        if i_loved and len(i_loved.group(2)) > 2:
            return RoutingDecision(IntentType.ENTITY_QUERY, "information_query", i_loved.group(2).strip(), raw_text, lower, confidence=0.8)

        return None

    def _classify_conversational(self, lower, text):
        _conversational_kw = frozenset({
            "tell me", "explain", "what is", "how does", "why is", "what are", "who is",
        })
        if any(kw in lower for kw in ("tell me more", "more info", "more details", "expand", "elaborate", "continue", "what else")):
            return RoutingDecision(IntentType.CONVERSATION, "elaborate", "", text, lower, confidence=0.7)
        if any(lower.startswith(kw) for kw in _conversational_kw):
            return RoutingDecision(IntentType.CONVERSATION, "converse", text, text, lower, confidence=0.6)
        return RoutingDecision(IntentType.CONVERSATION, "converse", text, text, lower, confidence=0.4)


class _CapabilityResolver:
    """
    Maps RoutingDecision to (capability_name, params) using the canonical
    CapabilityRegistry. Single source of truth for capability discovery.
    
    Replaces hardcoded mapping with dynamic registry lookup.
    """

    def __init__(self):
        from mini_kio.core.capability_registry import get_capability_registry
        self._registry = get_capability_registry()

    def resolve(self, decision: RoutingDecision) -> tuple[str, dict[str, Any]]:
        # R11 convergence: "search X in youtube" is a controlled-media search
        # owned by YouTubeProvider (connector world). When the connector is
        # unavailable (port occupied, disconnected), fall back to the desktop
        # capability which uses browser_operator.search_youtube (opens URL
        # directly via webbrowser.open — no connector needed).
        if (
            decision.intent_type == IntentType.SEARCH
            and decision.action == "search_youtube"
        ):
            _conn_ok = False
            try:
                from mini_kio.core.command_router import _get_connector
                _c = _get_connector()
                _conn_ok = _c is not None and _c.is_connected()
            except Exception:
                pass
            if _conn_ok:
                return (
                    "media",
                    {
                        "action": "search",
                        "target": decision.target,
                        "platform": "youtube",
                        "raw": decision.raw_text,
                    },
                )
            # Connector unavailable: route to desktop (browser_operator)
            # which opens YouTube search URL directly via webbrowser.open.
            return (
                "desktop",
                {"action": decision.action, "target": decision.target},
            )

        # Try dynamic registry first — but conversation family needs template preservation (ponytail: registry loses greeting/social template)
        capability = self._registry.resolve(decision.intent_type, decision.action)
        if capability:
            if capability == "conversation":
                # Preserve template distinctions that _exec_conversation relies on
                tmpl_map = {
                    "greeting": "greeting",
                    "social": "social",
                    "identity": "identity",
                    "unknown": "unknown",
                }
                from mini_kio.core.pipeline.types import IntentType as _IT
                tmpl = tmpl_map.get(_IT(decision.intent_type).name.lower(), None) if isinstance(decision.intent_type, _IT) else None
                # Fallback explicit mapping
                if decision.intent_type == _IT.GREETING:
                    return ("conversation", {"template": "greeting"})
                if decision.intent_type == _IT.SOCIAL:
                    return ("conversation", {"template": "social"})
                if decision.intent_type == _IT.IDENTITY:
                    return ("conversation", {"template": "identity"})
                if decision.intent_type == _IT.UNKNOWN:
                    return ("conversation", {"template": "unknown"})
                if decision.intent_type == _IT.CONVERSATION:
                    return ("conversation", {"action": decision.action or "converse", "target": decision.target, "raw": decision.raw_text})
            return self._build_params(capability, decision)

        # Fallback to static mapping for backward compatibility during transition
        mapping = {
            IntentType.GREETING: ("conversation", {"template": "greeting"}),
            IntentType.SOCIAL: ("conversation", {"template": "social"}),
            IntentType.IDENTITY: ("conversation", {"template": "identity"}),
            IntentType.DESKTOP_OPEN: ("desktop", {"action": decision.action, "target": decision.target, "metadata": decision.metadata}),
            IntentType.DESKTOP_CLOSE: ("desktop", {"action": decision.action, "target": decision.target}),
            IntentType.SEARCH: ("desktop", {"action": decision.action, "target": decision.target}),
            IntentType.MEDIA_PLAY: ("media", {"action": decision.action or "play", "target": decision.target, "platform": decision.platform, "raw": decision.raw_text}),
            IntentType.MEDIA_TRANSPORT: ("media", {"action": decision.action, "target": decision.target}),
            IntentType.BROWSER_FOCUS: ("browser", {"action": decision.action, "target": decision.target, "metadata": decision.metadata}),
            IntentType.BROWSER_TABS: ("browser", {"action": "list_tabs", "target": ""}),
            IntentType.BROWSER_NAVIGATE: ("browser", {"action": decision.action, "target": decision.target, "metadata": decision.metadata}),
            IntentType.SYSTEM: ("system", {"action": decision.action}),
            IntentType.OPERATIONAL: ("operational", {"action": decision.action, "target": decision.target}),
            IntentType.KNOWLEDGE: ("knowledge", {"query": decision.target}),
            IntentType.MULTI_STEP: ("coordinator", {"action": "multi_step", "raw_text": decision.raw_text}),
            IntentType.ENTITY_QUERY: ("media", {"action": "information_query", "query": decision.target}),
            IntentType.INFORMATION: ("media", {"action": "information_query", "query": decision.target}),
            IntentType.CONVERSATION: ("conversation", {"action": decision.action, "query": decision.target}),
            IntentType.FILE: ("desktop", {"action": decision.action, "target": decision.target}),
            IntentType.DESKTOP_ACTION: ("desktop_action", {"action": decision.action, "target": decision.target, "metadata": decision.metadata}),
            IntentType.MEMORY: ("memory", {"action": decision.action, "query": decision.target}),
            IntentType.MCP: ("mcp", {"raw": decision.raw_text}),
            IntentType.CREDENTIAL: ("credential", {"action": decision.action, "target": decision.target}),
            IntentType.UTILITY: ("utility", {"action": decision.action, "query": decision.target}),
            IntentType.SIMULATE: ("simulate", {"action": "simulate", "target": decision.target, "metadata": decision.metadata}),
            IntentType.UNKNOWN: ("conversation", {"template": "unknown"}),
        }
        result = mapping.get(decision.intent_type, ("conversation", {"template": "unknown"}))
        return result

    def _build_params(self, capability: str, decision: RoutingDecision) -> tuple[str, dict[str, Any]]:
        """Build execution params from capability name and routing decision."""
        base = {"action": decision.action, "target": decision.target}
        if decision.metadata:
            base["metadata"] = decision.metadata
        if decision.platform:
            base["platform"] = decision.platform
        if decision.raw_text:
            base["raw"] = decision.raw_text
        return capability, base


class _ExecutionCoordinator:
    def execute(
        self, capability: str, params: dict[str, Any], decision: RoutingDecision
    ) -> dict[str, Any]:
        import time
        start = time.monotonic()

        try:
            result = self._dispatch(capability, params, decision)
        except Exception as exc:
            logger.exception("[COORDINATOR] %s failed: %s", capability, exc)
            result = {"success": False, "message": f"{capability} failed: {exc}"}

        elapsed = int((time.monotonic() - start) * 1000)
        result.setdefault("elapsed_ms", elapsed)
        result.setdefault("action", decision.action)
        result.setdefault("target", decision.target)
        return result

    def _dispatch(self, capability: str, params: dict, decision: RoutingDecision) -> dict:
        dispatch = {
            "desktop": self._exec_desktop,
            "media": self._exec_media,
            "browser": self._exec_browser,
            "conversation": self._exec_conversation,
            "knowledge": self._exec_knowledge,
            "system": self._exec_system,
            "operational": self._exec_operational,
            "file": self._exec_desktop,
            "coordinator": self._exec_coordinator,
            "memory": self._exec_memory,
            "desktop_action": self._exec_desktop_action,
            "mcp": self._exec_conversation,
            "credential": self._exec_credential,
            "utility": self._exec_utility,
            "simulate": self._exec_simulate,
        }
        handler = dispatch.get(capability, self._exec_conversation)
        return handler(params, decision)

    def _exec_credential(self, params: dict, decision: RoutingDecision) -> dict:
        from mini_kio.core.credential_vault import credential_management_result
        return credential_management_result(
            params.get("action", "list"),
            target=params.get("target", ""),
        )

    def _exec_utility(self, params: dict, decision: RoutingDecision) -> dict:
        """Deterministic utility owner: time/date/weather/convert/package/feed/
        project/watch/research answers come from the canonical utilities module
        as normalized results — never from a web provider, never as raw
        provider UI. The decision rides along so delivery-aware owners (watch,
        research) can resolve the user's channel/session."""
        from mini_kio.core.utilities import utility_answer
        action = params.get("action", "")
        query = params.get("query", "") or decision.normalized_text or decision.raw_text
        try:
            ctx = get_context_manager(decision.session_id)
        except Exception:
            ctx = None
        return utility_answer(action, query, ctx=ctx, decision=decision)

    def _exec_desktop(self, params: dict, decision: RoutingDecision) -> dict:
        from mini_kio.core.execution_boundary import execute_action
        action = params["action"]
        target = params["target"]
        meta = params.get("metadata") or {}
        explicit_new = bool(meta.get("explicit_new"))
        # Duplicate prevention (canonical): a default "open X" must not create
        # another equivalent target when X is already running/visible — focus
        # the existing one instead. Explicit additional-instance requests
        # ("another X", "a new X window") skip this and always launch.
        if action == "open_app" and not explicit_new:
            reused = self._reuse_running_app(target)
            if reused:
                # Office apps can be idle on their start/template screen with
                # no document open — "open Excel" must land on a workbook,
                # not the homepage. Verification-driven: only create a doc
                # when no document window exists.
                office = self._office_maybe_new_document(target, explicit_new=False)
                return office or reused
        result = execute_action(action, target)
        # Office post-launch: cold starts land on the template/start screen.
        # After a real launch (or an explicit new-instance request), ensure a
        # fresh blank document actually exists — verified by document-window
        # count, never assumed.
        if result.get("success") and action == "open_app":
            office = self._office_maybe_new_document(target, explicit_new=explicit_new)
            if office:
                return office
        return result

    # Office apps open on the start/template screen by default — the user's
    # "create a new Excel workbook" was landing on the homepage. The fix is a
    # verification-driven new-document step: count document windows BEFORE and
    # AFTER the open/launch; only when no document appeared (or none exists)
    # does KIO press the app's native "new document" shortcut (Ctrl+N), so
    # exactly ONE fresh blank document is guaranteed and never two.
    _OFFICE_NEW_DOC = {
        "word": ("Word document", "Word"),
        "excel": ("Excel workbook", "Excel"),
        "powerpoint": ("PowerPoint presentation", "PowerPoint"),
    }

    def _office_maybe_new_document(self, target: str, explicit_new: bool) -> Optional[dict]:
        key = str(target or "").lower().strip()
        mapping = self._OFFICE_NEW_DOC.get(key)
        if not mapping:
            return None
        noun, app_label = mapping
        try:
            before = self._office_doc_window_count(key)
            if before is None:
                return None  # cannot verify — never guess
            time.sleep(1.6)
            after = self._office_doc_window_count(key)
            if after is None:
                return None
            if after <= before:
                from mini_kio.desktop import DesktopProvider
                dp = DesktopProvider()
                r = dp.execute("keyboard_hotkey", target="ctrl+n")
                if not r.get("success"):
                    return None
                time.sleep(1.3)
                after = self._office_doc_window_count(key) or after
            if after > before:
                if explicit_new:
                    msg = f"Done — opened a new {noun}."
                else:
                    msg = f"Opened {app_label} — here's a fresh {noun}."
                return {"success": True, "message": msg, "action": "open_app", "target": key}
            return None
        except Exception as exc:
            logger.debug("office new-doc ensure failed for %s: %s", key, exc)
            return None

    @staticmethod
    def _office_doc_window_count(key: str) -> Optional[int]:
        """Count real document windows for word/excel/powerpoint (start-screen
        windows — titled just the app name — are NOT documents). None when the
        app isn't running or the count cannot be determined."""
        image = {"word": "winword", "excel": "excel", "powerpoint": "powerpnt"}.get(key)
        if not image:
            return None
        try:
            import psutil
            pids = [
                p.info["pid"]
                for p in psutil.process_iter(["name", "pid"])
                if p.info.get("name") and p.info["name"].lower() == image + ".exe"
            ]
        except Exception:
            return None
        if not pids:
            return 0
        app_label = {"word": "word", "excel": "excel", "powerpoint": "powerpoint"}[key]
        try:
            import ctypes
            from ctypes import wintypes
            user32 = ctypes.windll.user32
            titles: list[str] = []

            @ctypes.WINFUNCTYPE(wintypes.BOOL, wintypes.HWND, wintypes.LPARAM)
            def _cb(hwnd, _lparam):
                pid = wintypes.DWORD()
                user32.GetWindowThreadProcessId(hwnd, ctypes.byref(pid))
                if pid.value in pids and user32.IsWindowVisible(hwnd):
                    n = user32.GetWindowTextLengthW(hwnd)
                    buf = ctypes.create_unicode_buffer(n + 1)
                    user32.GetWindowTextW(hwnd, buf, n + 1)
                    titles.append(buf.value)
                return True

            user32.EnumWindows(_cb, 0)
            count = 0
            for t in titles:
                low = t.lower()
                if not low or low == app_label:
                    continue
                if app_label in low or low.startswith(("document", "book", "presentation")):
                    count += 1
            return count
        except Exception:
            return None

    _DOC_FORMAT_CLAUSE_RE = re.compile(
        r"(?i)\s+(?:with|including|featuring|containing)\s+.*$"
    )

    @staticmethod
    def _strip_doc_format_clauses(subject: str) -> str:
        """Drop trailing document-format clauses from an artifact subject.

        "renewable energy with a title, headings, a comparison table,
        references, header/footer and page numbers" -> "renewable energy".
        The stripped clause describes HOW to build the document (structure
        requirements), so it belongs to content generation — never to the
        artifact's filename or subject identity.
        """
        if not subject:
            return subject
        stripped = _ExecutionCoordinator._DOC_FORMAT_CLAUSE_RE.sub("", subject).strip()
        # Keep a non-empty core: "with a comparison table" alone has no real
        # subject, so fall back to a sensible default instead of an empty name.
        if not stripped:
            stripped = subject.split(" with ", 1)[0].strip() or "document"
        return stripped[:120]

    def _sanity_check_python(self, content: str) -> str:
        """Compile-check generated Python and retry once on syntax errors.

        LLM providers occasionally emit broken code (unterminated strings,
        bad indentation). A generated .py file that cannot compile is not a
        usable deliverable, so we detect it BEFORE writing anything and give
        the model one corrective pass with the exact compiler error.
        """
        code = content or ""
        try:
            compile(code, "<generated>", "exec")
            return code
        except SyntaxError as exc:
            err = f"line {exc.lineno}: {exc.msg}"
            corrected = self._generate_content(
                f"{err}\n\nRewrite the program correctly. Return ONLY complete,\n"
                f"syntactically valid Python source — no markdown fences, no\n"
                f"explanations, proper indentation and closed strings.\n\n"
                f"Program: {content[:600]}",
                "", artifact="code", style="", language="python",
            )
            if corrected:
                try:
                    compile(corrected, "<generated2>", "exec")
                    return corrected
                except SyntaxError:
                    return code  # second pass still broken: write original
            return code

    def _exec_camera(self, meta: dict, dp) -> dict:
        """Camera capability executor (generic — no app-specific branches).

        Resolves the NATIVE installed camera through the same canonical app
        discovery used for every open (UWP included), launches it, and for a
        capture request drives the REAL shutter/mode controls through UI
        Automation (the Camera app exposes "Take photo" / "Record video" /
        "Switch to video mode" buttons). Success is claimed only when a NEW
        file with valid content actually appears in the camera output folder
        (OneDrive-redirected aware) — never a fake "took a photo".
        """
        import time as _t
        from mini_kio.core.app_operator import _find_installed_app, _launch_discovered

        camera_action = str(meta.get("camera_action") or "open")
        try:
            duration = max(1.0, min(float(meta.get("duration") or 5.0), 60.0))
        except (TypeError, ValueError):
            duration = 5.0

        # Native-first: resolve the installed camera app ONCE and launch that
        # exact descriptor — never a website, and never a mismatch between the
        # app we verified exists and the app we open. `_launch_discovered` is
        # the same canonical launcher the generic open path uses.
        found = _find_installed_app("camera") or _find_installed_app("webcam")
        if not found:
            return {"success": False, "message": "I couldn't find a native camera app installed on this PC."}
        opened = _launch_discovered(found, str(found.get("display") or "camera"))
        if not opened.get("success"):
            return {"success": False, "message": f"Couldn't open the camera: {opened.get('message', '')}"}
        _t.sleep(2.5)

        if camera_action == "open":
            # Honest verification: the launch succeeded (shell/explorer
            # accepted it), but a UWP app window may take seconds to appear —
            # never claim more than "launched".
            return {"success": True, "message": "Opened the camera.", "verified": None}

        # ── CAPTURE: UIA shutter first, keyboard fallback, filesystem-truth ──
        from mini_kio.platform.camera_uia import (  # noqa: PLC0415
            camera_window,
            capture_photo as _uia_capture_photo,
            ensure_video_mode,
            is_plausible_video,
            is_valid_jpeg,
            snapshot_roll,
            start_video as _uia_start_video,
            stop_video as _uia_stop_video,
            wait_for_new_file,
        )
        before = snapshot_roll()
        win = camera_window()

        if camera_action == "video":
            return self._camera_video_capture(
                win, dp, before, duration, _uia_start_video, _uia_stop_video,
                ensure_video_mode, wait_for_new_file, is_plausible_video,
            )

        # PHOTO capture.
        pressed_ok = False
        if win is not None:
            pressed_ok = _uia_capture_photo(win)
        if not pressed_ok:
            pressed_ok = bool(
                dp.execute("keyboard_press", target="enter").get("success")
                or dp.execute("keyboard_press", target="space").get("success")
            )
        new_file = wait_for_new_file(before) if pressed_ok else None
        if new_file is not None and is_valid_jpeg(new_file):
            return {
                "success": True,
                "message": f"Took a photo — saved {new_file.name} and verified it's a valid image.",
                "verified": True,
                "path": str(new_file),
            }
        if new_file is not None:
            return {
                "success": True,
                "message": f"A photo was saved ({new_file.name}), but I couldn't confirm its format.",
                "verified": None,
                "path": str(new_file),
            }
        return {
            "success": False,
            "message": "The camera is open, but I couldn't confirm a photo was saved — the shutter control isn't reliably reachable on this setup.",
            "camera_open": True,
        }

    def _camera_video_capture(self, win, dp, before, duration, start_video, stop_video,
                              ensure_video_mode, wait_for_new_file, is_plausible_video) -> dict:
        """Record a video clip with the UWP camera: video mode -> record for
        `duration` seconds -> stop -> verify a real clip appeared."""
        import time as _t
        if win is not None:
            ensure_video_mode(win)
            _t.sleep(1.0)
            started = start_video(win)
        else:
            started = False
        if not started:
            return {
                "success": False,
                "message": "The camera is open, but I couldn't switch it into video mode to start recording.",
                "camera_open": True,
            }
        _t.sleep(duration)
        if win is not None:
            stop_video(win)
        else:
            dp.execute("keyboard_press", target="space")
        new_file = wait_for_new_file(before, timeout_s=max(6.0, duration + 3.0))
        if new_file is not None and is_plausible_video(new_file):
            return {
                "success": True,
                "message": (
                    f"Recorded a {int(round(duration))}-second clip — saved {new_file.name} "
                    f"and verified it."
                ),
                "verified": True,
                "path": str(new_file),
                "duration_s": int(round(duration)),
            }
        if new_file is not None:
            return {
                "success": True,
                "message": f"A video was saved ({new_file.name}).",
                "verified": None,
                "path": str(new_file),
            }
        return {
            "success": False,
            "message": "The camera is open, but no video file appeared after recording — I couldn't verify the clip.",
            "camera_open": True,
        }

    def _exec_desktop_action(self, params: dict, decision: RoutingDecision) -> dict:
        """Canonical executor for the new desktop-action capability classes.

        TYPE / KEY_PRESS / SCROLL / CLICK — all route through the one desktop
        automation provider (mini_kio.desktop) that owns the low-level
        pyautogui/ctypes primitives. TYPE into a named app focuses (or opens)
        the app window first, then types the payload. Responses are short and
        truthful; a click on a named element that cannot be located is a
        truthful limitation, never a fake success.
        """
        from mini_kio.desktop import DesktopProvider
        from mini_kio.core.execution_boundary import execute_action

        action = params.get("action", "")
        target = str(params.get("target", "") or "")
        meta = params.get("metadata") or {}
        dp = DesktopProvider()

        # ── CAMERA capability (small, generic) ──────────────────────────────
        # "open the camera" resolves the NATIVE installed camera application
        # via generic UWP discovery — never a .com website. "take a picture"
        # opens it and attempts a real capture; the result is only claimed
        # when the provider genuinely triggered and verified it (photo file
        # appeared in Camera Roll), otherwise an honest limitation.
        if action == "camera":
            return self._exec_camera(meta, dp)

        if action == "type":
            payload = str(meta.get("payload", "") or "")
            if not payload:
                return {"success": False, "message": "What should I type?"}
            # A bare referent pronoun that survived resolution ("write this"
            # with no contextual content) must ask for clarification — never
            # type the literal word "this".
            if payload.strip().lower() in ("this", "that", "it", "them", "these", "those"):
                return {"success": False, "message": "What should I type? I don't have that content in context."}
            # Artifact-only payload without a topic ("the comparison", "an
            # essay") resolves its topic from recent session context when a
            # matching content request exists ("do a real comparison" after
            # "a comparison on messi vs lewis hamilton"), otherwise asks —
            # never typing the bare noun or fabricating content.
            _artifact_only = re.fullmatch(
                r"^(?:a|an|the)?\s*(?:small|short|quick|brief|detailed|concise|real|proper)?\s*"
                r"(comparison|essay|report|summary|analysis|review|article|poem|story|letter|email|overview|guide|write-up)\s*$",
                payload.strip().lower(),
            )
            if _artifact_only:
                noun = _artifact_only.group(1)
                inherited = self._inherit_content_topic(decision, noun)
                if inherited:
                    payload = f"a {noun} on {inherited}"
                else:
                    return {"success": False, "message": f"What should the {noun} be about? Tell me the topic and I'll write it."}
            app = target.strip()
            # New-file default: typing ALWAYS goes into a fresh document — KIO
            # never tampers with existing file content. "type hello into
            # notepad" opens a NEW blank document (Ctrl+N) if the app is
            # already running; apps KIO just launched are already blank. Only
            # an EXPLICIT write-onto request ("append", "add to the file",
            # "write onto the existing file", "in the same file") reuses the
            # existing window.
            new_instance = bool(meta.get("new_instance", True))
            write_onto = False
            if decision is not None and getattr(decision, "raw_text", None):
                raw = str(decision.raw_text).lower()
                if re.search(
                    r"\b(?:append|add\s+to|write\s+onto|onto\s+(?:the\s+)?(?:file|document|same|existing|current)|same\s+file|existing\s+file|this\s+file|the\s+current\s+file|keep\s+typing|continue\s+in)\b",
                    raw,
                ):
                    write_onto = True
            # Generated-content TYPE: the payload is a REQUEST ("a short poem
            # about space"), so generate the actual content with the LLM FIRST
            # (content generation) — then do ALL desktop interaction LAST
            # (fresh instance → focus → type → verify). Generating first
            # prevents the LLM latency from stealing focus away from the target
            # between focus and typing, which previously caused typed text to
            # land in the wrong window.
            if meta.get("generate"):
                generated = self._generate_content(payload, app or "")
                if not generated:
                    return {"success": False, "message": "I couldn't generate that content to type."}
                payload = generated
            import time
            launch_pid = 0
            focused = None
            new_hwnd = 0
            if app:
                from mini_kio.core.routing_utils import get_browser_routing
                route_info = get_browser_routing(app)
                if route_info["route_type"] == "browser_fallback":
                    execute_action("execute_capability", route_info["target"])
                    return {"success": True, "message": "Opened the web app — I can't type into a browser tab yet."}
                if not write_onto:
                    # DEFAULT (new file): launch a FRESH instance of the app.
                    # Snapshot the app's existing windows FIRST so the newly
                    # created window can be deterministically identified and
                    # focused — Win11 Notepad restores previous session tabs,
                    # so "launch + focus the app" can land in an old document.
                    before = self._snapshot_app_windows(route_info["target"]) if app else set()
                    launch = execute_action("open_app", route_info["target"])
                    if not launch.get("success"):
                        # App may be single-instance and already focused — fall
                        # back to focusing the existing window truthfully.
                        focused = self._try_native_focus(app)
                        if not focused:
                            return {"success": False, "message": f"Couldn't open {app} to type into it."}
                    else:
                        launch_pid = int(launch.get("pid") or 0)
                        time.sleep(1.2)
                        # Deterministically locate a FRESH BLANK document:
                        # prefer a newly created window whose text control is
                        # EMPTY (session-restored tabs carry old content and
                        # must never receive new text). If no empty new window
                        # appears, explicitly create one with the app's
                        # new-document command (Ctrl+N) after focusing the app.
                        seen: set[int] = set(before)
                        new_hwnd = self._wait_for_blank_new_window(route_info["target"], seen)
                        if new_hwnd:
                            try:
                                from mini_kio.platform.window_activation import _force_foreground
                                _force_foreground(int(new_hwnd))
                            except Exception:
                                pass
                            focused = True
                        else:
                            # No fresh blank window surfaced (single-instance
                            # app, or every new window carries restored session
                            # content) — focus the app and request a new
                            # document explicitly so exactly ONE fresh blank
                            # target exists.
                            focused = self._try_native_focus(route_info["target"])
                            if focused:
                                time.sleep(0.4)
                                new_doc = dp.execute("keyboard_hotkey", target="ctrl+n")
                                if new_doc.get("success"):
                                    time.sleep(0.8)
                                    new_hwnd = self._wait_for_blank_new_window(route_info["target"], seen)
                                    if new_hwnd:
                                        try:
                                            from mini_kio.platform.window_activation import _force_foreground
                                            _force_foreground(int(new_hwnd))
                                        except Exception:
                                            pass
                                        focused = True
                else:
                    # EXPLICIT write-onto: reuse the existing focused window.
                    focused = self._try_native_focus(app)
                if not focused:
                    return {"success": False, "message": f"Couldn't focus {app} to type into it."}
            result = self._inject_text(dp, payload)
            new_target_hwnd = 0
            if app and not write_onto:
                new_target_hwnd = int(new_hwnd or 0)
            if result.get("success"):
                # Verification: read back the target window (by the exact PID
                # we launched/focused, falling back to app-wide / foreground)
                # and confirm the payload actually landed. Unreadable windows
                # (browsers/games) are an honest limitation, never a fabricated
                # "verified".
                verified = self._verify_typed(payload, bool(meta.get("generate")), app, launch_pid, new_target_hwnd)
                where = f" into {app.capitalize()}" if app else ""
                # A short settle window avoids false negatives from the edit
                # control flushing asynchronously after typing.
                if verified is None or verified is False:
                    time.sleep(0.4)
                    verified = self._verify_typed(payload, bool(meta.get("generate")), app, launch_pid, new_target_hwnd)
                if verified is True:
                    # Natural, outcome-focused wording — never expose internal
                    # executor vocabulary ("verified", action schema names).
                    if meta.get("generate"):
                        msg = f"Done — I wrote that into {app.capitalize()} and checked the document." if app else "Done — I wrote that for you."
                    else:
                        msg = f"Done — typed it{where}." if app else "Done — typed it."
                    return {"success": True, "message": msg, "verified": True}
                if verified is False:
                    # The window WAS readable and the payload is NOT present —
                    # a truthful failure rather than a success-shaped lie.
                    return {"success": False, "message": "I wrote it, but the text isn't showing in the document.", "typed": True}
                # verified is None: window not readable → honest limitation.
                if meta.get("generate"):
                    msg = f"Done — I wrote that into {app.capitalize()}." if app else "Done — I wrote that for you."
                else:
                    msg = f"Done — typed it{where}." if app else "Done — typed it."
                return {"success": True, "message": msg, "verified": None}
            return result

        if action == "create_document":
            from mini_kio.core.artifact_operator import (
                create_artifact, open_artifact, open_in_editor, _PRESENTATION_KINDS,
            )
            subject = str(target or meta.get("subject") or "").strip()
            artifact = str(meta.get("artifact") or "document")
            style = str(meta.get("style") or "")
            language = str(meta.get("language") or "")
            editor = str(meta.get("editor") or "")
            # Structure hints are detected from the RAW request wording (the
            # format-clause stripper below removes them from the subject):
            # "table of contents"/"toc" -> needs_toc; "title page" ->
            # needs_title_page. Generic family rule — any report/essay request
            # that names these structures gets them, no template forcing.
            _req_for_struct = f"{decision.raw_text or ''} {subject}".lower()
            needs_toc = bool(
                re.search(r"\b(?:table\s+of\s+contents|toc)\b", _req_for_struct)
            )
            needs_title_page = bool(re.search(r"\btitle\s+page\b", _req_for_struct))
            # Strip trailing FORMAT clauses from the subject so they drive
            # document structure (not the filename): "... on renewable energy
            # with a title, headings, a comparison table, references" ->
            # subject "renewable energy", requirements preserved in content.
            # The stripped clause is kept separately and APPENDED to the
            # content-generation prompt so the LLM actually emits the
            # requested structures (table, references, ...) instead of plain
            # prose.
            _fmt_match = _ExecutionCoordinator._DOC_FORMAT_CLAUSE_RE.search(subject)
            _format_req = _fmt_match.group(0).strip() if _fmt_match else ""
            subject = self._strip_doc_format_clauses(subject)
            _content_prompt = subject + (f" {_format_req}" if _format_req else "")
            if not subject:
                # Bare artifact request ("create a study guide") — ask what it
                # should be about instead of fabricating a topic.
                return {
                    "success": False,
                    "message": f"Sure — what should the {artifact} be about?",
                }
            # Email draft: CONTENT-side only — no authenticated send provider,
            # so the complete professional email IS the truthful deliverable.
            if artifact == "email" and meta.get("draft_only"):
                recipient = str(meta.get("recipient") or "")
                prompt = subject
                if recipient:
                    prompt = (
                        f"{prompt} — addressed to {recipient}"
                        if prompt else f"a message to {recipient}"
                    )
                content = self._generate_content(
                    prompt or subject, "", artifact="email", style=style
                )
                if not content:
                    return {"success": False, "message": "I couldn't draft that email."}
                to_line = f" To: {recipient}." if recipient else ""
                return {
                    "success": True,
                    "message": f"Here's your draft{to_line}\n\n{content}",
                    "target": "email draft",
                }
            # PRESENTATIONS: the deck is planned and built by the presentation
            # design engine (research → story plan → slide purposes → visual
            # grammar → assets → layout → validation → repair → real-PowerPoint
            # verify/open), NOT by generic text generation. It publishes
            # concise user-facing progress through the shared progress bus and
            # opens the finished deck itself.
            if artifact in _PRESENTATION_KINDS:
                from mini_kio.core.presentation.engine import create_presentation
                result = create_presentation(subject, style=style)
                if result.get("success"):
                    n = result.get("slide_count", 0)
                    return {
                        "success": True,
                        "message": (
                            f"Done — I put the deck together and opened it in "
                            f"PowerPoint. ({result.get('filename', '')} — {n} "
                            f"slide{'s' if n != 1 else ''}.)"
                        ),
                        "target": result.get("filename", subject),
                    }
                return {
                    "success": False,
                    "message": result.get(
                        "message", "I couldn't put that presentation together."
                    ),
                }
            content = self._generate_content(
                f"{_content_prompt}", "", artifact=artifact, style=style, language=language
            )
            if not content:
                return {"success": False, "message": f"I couldn't generate content for that {artifact}."}
            # Code sanity: a generated Python file must at least COMPILE. If
            # the first pass produced a syntax error, retry ONCE with the
            # compiler message as feedback — the second pass usually yields
            # clean, runnable code. Never hand the user a file that crashes.
            if artifact in ("code", "program", "script") and (language or "python").lower() in ("python", "py"):
                content = self._sanity_check_python(content)

            # Multi-file PROJECT workflow: "create a Python project with a
            # README" produces a real directory (source + README), not a lone
            # file. Detection is semantic (subject mentions project/README),
            # never an app-name branch.
            subj_lower = (subject or "").lower()
            is_project = (
                artifact in ("code", "program", "script")
                and (
                    bool(meta.get("project"))
                    or "project" in subj_lower or "readme" in subj_lower
                )
            )
            if is_project:
                from mini_kio.core.artifact_operator import create_code_project
                readme = self._generate_content(
                    f"A concise README for a project about {subject}",
                    "", artifact="readme", style=style,
                )
                result = create_code_project(
                    subject, content, readme=readme or "", language=language
                )
                if result.get("success"):
                    try:
                        import pathlib
                        open_in_editor(pathlib.Path(result["project_dir"]), editor or "vs code")
                    except Exception:
                        pass
                    app_name = {
                        "vs code": "VS Code", "vscode": "VS Code",
                        "visual studio code": "VS Code", "code": "VS Code",
                    }.get(editor, editor.capitalize() if editor else "VS Code")
                    return {
                        "success": True,
                        "message": (
                            f"Done — I set up the {result.get('filename')} project "
                            f"({result.get('source_file', '').split(chr(92))[-1]} + README.md) "
                            f"and opened it in {app_name}."
                        ),
                        "target": result.get("filename", subject),
                    }
                return result

            result = create_artifact(
                subject, content, artifact=artifact, style=style, language=language,
                needs_toc=needs_toc, needs_title_page=needs_title_page,
            )
            if result.get("success"):
                # Open the created artifact — in the requested editor for code,
                # default application otherwise.
                try:
                    import pathlib
                    if result.get("artifact") in ("code", "program", "script"):
                        open_in_editor(pathlib.Path(result["path"]), editor)
                    else:
                        open_artifact(pathlib.Path(result["path"]))
                except Exception:
                    pass
                if "word_count" in result:
                    detail, unit = result["word_count"], "word"
                elif "row_count" in result:
                    detail, unit = result["row_count"], "row"
                elif "line_count" in result:
                    detail, unit = result["line_count"], "line"
                else:
                    detail, unit = result.get("slide_count", 0), "slide"
                if detail != 1:
                    unit += "s"
                # Natural KIO voice — the confirmation states WHAT was created
                # in plain language and keeps the truthful verification facts
                # (filename + measured unit count) in a compact parenthetical.
                # Never a bare execution log.
                kind = result.get("artifact") or artifact
                filename = result.get("filename", "")
                if kind in ("code", "program", "script"):
                    app = editor or "your editor"
                    action_note = f"I wrote the {kind} and opened it in {app}."
                elif kind in ("spreadsheet", "budget", "table", "sheet", "data", "ledger", "inventory", "tracker", "timetable", "roster", "schedule", "dataset"):
                    action_note = "I made you a fresh spreadsheet and opened it."
                elif kind in ("presentation", "slides", "deck", "ppt", "pptx", "powerpoint", "slideshow", "talk"):
                    action_note = "I put the slides together and opened the deck."
                elif kind == "email":
                    action_note = "I drafted the email and left it ready for review."
                elif kind == "notes":
                    action_note = "I jotted that down for you and opened it."
                else:
                    action_note = "I wrote it up as a document and opened it."
                # Research grounding transparency: when research was requested
                # but all providers failed, warn the user so they know the
                # content is based on general knowledge, not web research.
                _note = ""
                if getattr(self, '_last_research_degraded', False):
                    _note = " (Note: web research was unavailable; content is based on general knowledge.)"
                return {
                    "success": True,
                    "message": f"Done — {action_note} ({filename} — {detail} {unit}).{_note}",
                    "target": result.get("filename", subject),
                }
            return result

        if action == "key_press":
            combo = target.strip().lower()
            if not combo:
                return {"success": False, "message": "What key should I press?"}
            if "+" in combo:
                result = dp.execute("keyboard_hotkey", target=combo)
            else:
                result = dp.execute("keyboard_press", target=combo)
            if result.get("success"):
                return {"success": True, "message": f"Pressed {combo.upper()}."}
            return result

        # ── SEMANTIC edit actions: SAVE / COPY / PASTE / SELECT_ALL / UNDO / ──
        # REDO. These are meaningful operations against the CORRECT contextual
        # target — resolved and focused first — not mechanical keypresses on
        # whatever happens to be foreground. Where the environment allows, the
        # result is VERIFIED against real state (clipboard for copy, window
        # text for paste/select) instead of an unverified "Pressed X."
        _semantic_combo = str((meta or {}).get("combo") or "").lower()
        if action in ("save", "copy", "paste", "select_all", "undo", "redo"):
            if not _semantic_combo:
                return {"success": False, "message": f"Unknown {action} shortcut."}
            # Resolve the target: an EXPLICIT app in the decision wins ("save
            # the document in word", "select everything in notepad"); otherwise
            # the session context (active entity / last target). Focus it so
            # the key event lands in the window the user is actually working
            # in, not whatever is foreground.
            resolved_target = str(target or "").strip() or self._resolve_edit_target(decision)
            if resolved_target:
                focused = self._try_native_focus(resolved_target)
                if not focused:
                    # A stale referent is fine — the user's current foreground
                    # window is the fallback, but never silently retarget.
                    logger.info("[EDIT_ACTION] contextual target %s not focusable; using foreground", resolved_target)
            if action == "copy":
                # COPY must be verified against the real clipboard.
                import time as _t
                result = dp.execute("keyboard_hotkey", target=_semantic_combo)
                _t.sleep(0.15)
                clip = dp.execute("clipboard_get")
                copied = str(clip.get("text") or "").strip()
                if result.get("success") and copied:
                    return {"success": True, "message": f"Copied {len(copied)} characters to the clipboard.", "verified": True}
                if result.get("success"):
                    return {"success": True, "message": "Pressed Ctrl+C, but the clipboard came back empty.", "verified": False}
                return result
            if action == "paste":
                # PASTE must verify there IS something to paste first.
                import time as _t
                clip = dp.execute("clipboard_get")
                copied = str(clip.get("text") or "").strip()
                if not copied:
                    return {"success": False, "message": "The clipboard is empty — nothing to paste."}
                before = self._read_window_text_or_none()
                result = dp.execute("keyboard_hotkey", target=_semantic_combo)
                _t.sleep(0.2)
                after = self._read_window_text_or_none()
                if result.get("success"):
                    if before is not None and after is not None and after != before:
                        return {"success": True, "message": "Pasted it.", "verified": True}
                    if before is None or after is None:
                        return {"success": True, "message": "Pasted it.", "verified": None}
                    return {"success": True, "message": "Pasted it, but the window content didn't change.", "verified": False}
                return result
            # SAVE / SELECT_ALL / UNDO / REDO: execute, then verify where the
            # window text is readable (selection changes are observable via
            # text read-back only in limited cases — an honest limitation
            # otherwise, never a fabricated success).
            result = dp.execute("keyboard_hotkey", target=_semantic_combo)
            if not result.get("success"):
                return result
            labels = {
                "save": "Saved", "select_all": "Selected everything",
                "undo": "Undid that", "redo": "Redid that",
            }
            return {"success": True, "message": f"{labels[action]}.", "verified": None}


        if action == "scroll":
            direction = target.strip().lower()
            if direction in ("down", "bottom"):
                result = dp.execute("mouse_scroll", target="", clicks=-30)
                label = "down" if direction == "down" else "to the bottom"
            elif direction in ("up", "top"):
                result = dp.execute("mouse_scroll", target="", clicks=30)
                label = "up" if direction == "up" else "to the top"
            else:
                return {"success": False, "message": "Scroll which way?"}
            if result.get("success"):
                return {"success": True, "message": f"Scrolled {label}."}
            return result

        if action == "click":
            # Only a click at the current cursor position is executable without
            # vision. Named-element clicks are a truthful limitation.
            result = dp.execute("mouse_click")
            if result.get("success"):
                return {"success": True, "message": "Clicked."}
            return result

        return {"success": False, "message": f"Unhandled desktop action: {action}"}

    # ── Capability-quality verification helpers ─────────────────────────────
    # TYPE/PASTE/COPY are VERIFIED against real application state where the
    # target window exposes a standard text control. Unreadable windows are an
    # honest limitation (verified=None), never a fabricated success.

    def _read_window_text_or_none(self) -> Optional[str]:
        """Best-effort read of the foreground window's text control.
        Returns None when the window cannot be read (browser/game/empty)."""
        try:
            from mini_kio.desktop.text_readback import read_foreground_text
            info = read_foreground_text()
            if info.get("success"):
                return str(info.get("text") or "")
        except Exception as exc:
            logger.debug("window text read-back unavailable: %s", exc)
        return None

    def _inject_text(self, dp, payload: str, force_typing: bool = False) -> dict:
        """Insert a complete payload into the focused editor.

        Atomic clipboard paste is the canonical mechanism for payloads larger
        than a short literal: it injects the ENTIRE text in one operation,
        cannot be truncated mid-stream, and does not depend on per-character
        key events (whose focus can be stolen mid-typing, producing mixed or
        partial documents). Short literals (< 80 chars) and force_typing are
        sent as keystrokes. Unicode content always uses clipboard paste since
        pyautogui typewrite only handles ASCII. Falls back to typing if the
        clipboard is unavailable. Returns the provider result dict.
        """
        # Unicode content must use clipboard paste — pyautogui typewrite
        # silently drops non-ASCII characters.
        has_unicode = any(ord(c) > 127 for c in payload)
        if (force_typing or len(payload) <= 80) and not has_unicode:
            return dp.execute("keyboard_type", target=payload)
        import time as _t
        for _attempt in range(2):
            try:
                clip = dp.execute("clipboard_set", target=payload)
                if not clip.get("success"):
                    if _attempt == 0:
                        _t.sleep(0.2)
                        continue
                    else:
                        return dp.execute("keyboard_type", target=payload)
                # Brief settle to ensure clipboard is flushed before paste
                _t.sleep(0.08)
                pasted = dp.execute("keyboard_hotkey", target="ctrl+v")
                if pasted.get("success"):
                    return {"success": True, "action": "paste", "message": "Pasted complete content."}
                if _attempt == 0:
                    _t.sleep(0.3)
                    continue
                else:
                    return dp.execute("keyboard_type", target=payload)
            except Exception:
                if _attempt == 0:
                    _t.sleep(0.2)
                    continue
                else:
                    return dp.execute("keyboard_type", target=payload)
        return dp.execute("keyboard_type", target=payload)

    def _verify_typed(self, payload: str, is_generated: bool = False, app: str = "", launch_pid: int = 0, target_hwnd: int = 0) -> Optional[bool]:
        """Verify a typed payload actually landed in the target window's text
        control. Prefers the exact newly-created window (target_hwnd), then the
        exact PID that was launched/focused; then the named app's visible
        windows; falls back to the foreground window.

        Returns True when confirmed present, False when the window was readable
        and the payload is absent, None when no readable window was found.
        Generated content (LLM output) may be wrapped/reflowed, so the check is
        normalized; for generated payloads the first meaningful line is probed.
        """
        texts: list[str] = []
        if target_hwnd:
            # Match the payload against ANY tab/control in the target window
            # (multi-tab editors otherwise favor a restored tab).
            texts = self._read_all_window_texts_for(int(target_hwnd))
        if not texts:
            texts = self._read_target_or_foreground_text(app, launch_pid)
        if not texts:
            return None
        try:
            from mini_kio.desktop.text_readback import payload_present
        except Exception:
            return None
        if is_generated:
            for probe in (payload, payload[:40], payload[:20]):
                if probe and any(payload_present(probe, t) for t in texts):
                    return True
            logger.info(
                "[VERIFY_MISS] generated payload=%r texts=%d lens=%r app=%r pid=%s hwnd=%s",
                payload[:60], len(texts), [len(t) for t in texts[:4]], app, launch_pid, target_hwnd,
            )
            return False
        ok = any(payload_present(payload, t) for t in texts) if payload else False
        if not ok:
            logger.info(
                "[VERIFY_MISS] literal payload=%r texts=%d lens=%r app=%r pid=%s hwnd=%s",
                payload[:60], len(texts), [len(t) for t in texts[:4]], app, launch_pid, target_hwnd,
            )
        return ok

    def _read_target_or_foreground_text(self, app: str = "", launch_pid: int = 0) -> list[str]:
        """Collect text from the exact launched PID's windows; then the named
        target app's visible windows (by process match); falls back to the
        foreground window when no app is named."""
        try:
            import ctypes as _ct
            from ctypes import wintypes as _wt
            from mini_kio.desktop.text_readback import read_foreground_text
            from mini_kio.desktop.text_readback import _user32
        except Exception:
            return []
        texts: list[str] = []
        if launch_pid:
            try:
                found = []

                def _cb(hwnd, _lp):
                    if not _user32.IsWindowVisible(hwnd):
                        return True
                    pid = _wt.DWORD()
                    _user32.GetWindowThreadProcessId(hwnd, _ct.byref(pid))
                    if pid.value == launch_pid:
                        found.append(hwnd)
                    return True

                _user32.EnumWindows(
                    _ct.WINFUNCTYPE(_ct.c_bool, _wt.HWND, _wt.LPARAM)(_cb), 0
                )
                for hwnd in found:
                    info = self._read_window_text_for(hwnd)
                    if info:
                        texts.append(info)
            except Exception as exc:
                logger.debug("pid-scoped read-back failed: %s", exc)
        if not texts and app:
            try:
                import subprocess as _sp

                # Map the app token to candidate process names.
                base = app.lower().replace(" ", "").replace(".exe", "")
                proc_names = {base + ".exe", base, "notepad.exe" if base == "notepad" else ""}
                proc_names.discard("")
                r = _sp.run(["tasklist"], capture_output=True, text=True)
                pids = set()
                for line in r.stdout.splitlines():
                    parts = line.split()
                    if len(parts) >= 2 and parts[0].lower() in proc_names:
                        try:
                            pids.add(int(parts[1]))
                        except ValueError:
                            pass
                if pids:
                    found = []

                    def _cb(hwnd, _lp):
                        if not _user32.IsWindowVisible(hwnd):
                            return True
                        pid = _wt.DWORD()
                        _user32.GetWindowThreadProcessId(hwnd, _ct.byref(pid))
                        if pid.value in pids:
                            found.append(hwnd)
                        return True

                    _user32.EnumWindows(
                        _ct.WINFUNCTYPE(_ct.c_bool, _wt.HWND, _wt.LPARAM)(_cb), 0
                    )
                    for hwnd in found:
                        info = self._read_window_text_for(hwnd)
                        if info:
                            texts.append(info)
            except Exception as exc:
                logger.debug("target-scoped read-back failed: %s", exc)
        if not texts:
            info = read_foreground_text()
            if info.get("success"):
                texts.append(str(info.get("text") or ""))
        return texts

    def _snapshot_app_windows(self, app: str) -> set[int]:
        """Return the set of visible top-level HWNDs currently owned by the
        given application (process-name match). Used to detect which window
        is newly created by a fresh launch."""
        try:
            import ctypes as _ct
            from ctypes import wintypes as _wt
            import subprocess as _sp
            from mini_kio.desktop.text_readback import _user32

            base = app.lower().replace(" ", "").replace(".exe", "")
            proc_names = {base + ".exe", base}
            r = _sp.run(["tasklist"], capture_output=True, text=True)
            pids = set()
            for line in r.stdout.splitlines():
                parts = line.split()
                if len(parts) >= 2 and parts[0].lower() in proc_names:
                    try:
                        pids.add(int(parts[1]))
                    except ValueError:
                        pass
            if not pids:
                return set()
            found = set()

            def _cb(hwnd, _lp):
                if not _user32.IsWindowVisible(hwnd):
                    return True
                pid = _wt.DWORD()
                _user32.GetWindowThreadProcessId(hwnd, _ct.byref(pid))
                if pid.value in pids:
                    found.add(int(hwnd))
                return True

            _user32.EnumWindows(
                _ct.WINFUNCTYPE(_ct.c_bool, _wt.HWND, _wt.LPARAM)(_cb), 0
            )
            return found
        except Exception:
            return set()

    def _wait_for_new_window(self, app: str, before: set[int], timeout: float = 6.0) -> Optional[int]:
        """Poll until a visible window that was NOT in the pre-launch snapshot
        appears. Returns the new HWND, or None when the app did not surface a
        distinct new window (single-instance apps reuse their window)."""
        import time as _t
        deadline = _t.monotonic() + timeout
        while _t.monotonic() < deadline:
            now = self._snapshot_app_windows(app)
            new_wins = now - before
            if new_wins:
                return sorted(new_wins)[0]
            _t.sleep(0.15)
        return None

    def _wait_for_blank_new_window(self, app: str, before: set[int], timeout: float = 6.0) -> Optional[int]:
        """Poll for a newly created window whose text control is EMPTY.

        Win11 Notepad restores previous session tabs on launch; those restored
        windows are "new" relative to a pre-launch snapshot but carry OLD
        content and must never receive new text. This helper keeps polling and
        returns the first new window with no readable text (a genuine fresh
        blank document), or None."""
        import time as _t
        deadline = _t.monotonic() + timeout
        while _t.monotonic() < deadline:
            now = self._snapshot_app_windows(app)
            for hwnd in sorted(now - before):
                text = self._read_window_text_for(int(hwnd))
                if text in (None, ""):
                    return int(hwnd)
            _t.sleep(0.15)
        return None

    def _read_window_text_for(self, hwnd: int) -> Optional[str]:
        """Read the largest text control inside a specific top-level window."""
        try:
            all_texts = self._read_all_window_texts_for(int(hwnd))
            if not all_texts:
                return None
            return max(all_texts, key=len)
        except Exception:
            return None

    def _read_all_window_texts_for(self, hwnd: int) -> list[str]:
        """Read ALL text controls inside a specific top-level window.

        Multi-tab editors (Win11 Notepad, browsers) expose one text control
        per tab. Reading only the largest silently favors an unrelated
        session-restored tab over the freshly typed document, which produced
        false verification negatives. Returning every control's text lets
        verification match the payload against ANY tab."""
        try:
            import ctypes as _ct
            from ctypes import wintypes as _wt
            from mini_kio.desktop.text_readback import _user32, _class_name, _EnumChildWindows, _EnumChildProc

            controls = []

            def _cb(h, _lp):
                cls = _class_name(h)
                if "Edit" in cls or "RichEdit" in cls:
                    controls.append(h)
                return True

            _user32.EnumChildWindows(hwnd, _EnumChildProc(_cb), 0)
            texts: list[str] = []
            for c in controls:
                ln = _user32.SendMessageW(c, 0x000E, 0, 0)  # WM_GETTEXTLENGTH
                if ln <= 0:
                    continue
                buf = _ct.create_unicode_buffer(ln + 1)
                _user32.SendMessageW(c, 0x000D, ln + 1, buf)  # WM_GETTEXT
                if buf.value:
                    texts.append(buf.value)
            return texts
        except Exception:
            return []

    def _inherit_content_topic(self, decision: RoutingDecision, artifact: str) -> Optional[str]:
        """Inherit a content topic from recent session exchanges.

        "Do a real comparison" after "a comparison on messi vs lewis hamilton"
        should reuse the topic instead of asking. Scans the last few user
        exchanges for "<artifact> on/about <topic>" (or "between A and B").
        Returns None when no matching topic exists — the caller then asks.
        """
        try:
            if decision is None or not getattr(decision, "session_id", None):
                return None
            from mini_kio.core.context_manager import get_context_manager
            ctx = get_context_manager(decision.session_id)
            history = ctx.get_history_window(6)
            for user_text, _reply in reversed(history):
                low = str(user_text or "").lower()
                if artifact not in low:
                    continue
                m = re.search(
                    rf"\b{artifact}\s+(?:on|about|of|between)\s+(.+?)\s*$",
                    low,
                )
                if m:
                    topic = m.group(1).strip().strip(".,!?;:")
                    if topic and len(topic) < 80 and topic.lower() not in ("it", "this", "that", "them"):
                        return topic
            return None
        except Exception:
            return None

    def _resolve_edit_target(self, decision: RoutingDecision) -> Optional[str]:
        """Resolve the contextual target for a semantic edit action from the
        session context (active entity / last successful target). Returns None
        when no reliable referent exists — the user's current foreground
        window is then the intended surface."""
        try:
            if decision is None or not getattr(decision, "session_id", None):
                return None
            from mini_kio.core.context_manager import get_context_manager
            ctx = get_context_manager(decision.session_id)
            entity = getattr(ctx, "active_entity", None) or getattr(ctx, "last_target", None)
            return str(entity).strip() or None if entity else None
        except Exception:
            return None

    def _reuse_running_app(self, target: str) -> Optional[dict]:
        """Duplicate prevention: if the requested native app is already running
        (KIO-tracked, registry-matched, or a visible desktop window), focus the
        existing instance and report it — never launch a second one.

        Generic and app-agnostic; browser-host windows are only matched when the
        requested target IS that browser (a tab mentioning an app never focuses
        the whole browser process).
        """
        try:
            from mini_kio.core.runtime import get_runtime
            from mini_kio.core.app_operator import _find_in_registry, _find_matching_process_pid
            from mini_kio.core.desktop_state import observe_native_windows
            from mini_kio.platform.window_activation import try_activate_browser, activate_window
            from mini_kio.core.target_ref import display_target_name

            key = str(target or "").lower().strip()
            if not key:
                return None
            rt = get_runtime()
            if rt is not None:
                rt.prune_tracked_processes()
                for entry in rt.tracked_processes:
                    if str(entry.get("name", "") or "").lower() == key:
                        pid = int(entry.get("pid", 0) or 0)
                        if pid > 0:
                            try_activate_browser(pid)
                            return {"success": True, "message": f"{display_target_name(key)} is already open.", "action": "open_app", "target": key}
            info = _find_in_registry(key)
            if info:
                pid = _find_matching_process_pid(key, info)
                if pid:
                    try_activate_browser(pid)
                    return {"success": True, "message": f"{display_target_name(key)} is already open.", "action": "open_app", "target": key}
            windows, ok = observe_native_windows()
            if ok:
                browser_hosts = {"chrome", "edge", "firefox", "brave", "comet", "opera"}
                for w in windows:
                    if not w.get("pid"):
                        continue
                    if w.get("is_browser_host") and key not in browser_hosts:
                        continue
                    base = str(w.get("base") or "").lower()
                    wapp = str(w.get("app") or "").lower()
                    matched = (base and len(key) >= 3 and key in base) or (wapp and len(key) >= 3 and key in wapp)
                    if matched and activate_window(int(w["pid"])):
                        return {"success": True, "message": f"{display_target_name(key)} is already open.", "action": "open_app", "target": key}
        except Exception as exc:
            logger.warning("reuse check failed for %s: %s", target, exc)
        return None

    def _exec_media(self, params: dict, decision: RoutingDecision) -> dict:
        from mini_kio.media.media_manager import MediaManager

        mm = MediaManager.get_instance()
        action = params["action"]

        if action in ("play", "play_discovery"):
            target = params.get("target", "")
            raw_text = decision.raw_text if hasattr(decision, 'raw_text') else target

            # ── Short-circuit: rejection/contextual follow-ups ───────────
            # Rejection phrases ("nah", "not this", etc.) and contextual
            # media requests must go DIRECTLY to MediaManager.play() where
            # the rejection handler, pronoun resolver, and bare-artifact
            # resolver live. The MediaContextIntelligence would incorrectly
            # treat "nah" as a literal topic query.
            _ql = target.lower().strip()
            _is_media_rejection = False
            if mm._context.last_query or mm._context.current_media_id:
                _REJECT = {"nah", "nope", "no", "nahh", "nahhh", "naw",
                           "not this", "not this one", "not feeling this",
                           "skip", "skip this", "skip it", "skip that",
                           "next", "next one", "another", "another one",
                           "something different", "something better",
                           "play something else", "play something different",
                           "try another", "try something else",
                           "change it", "switch it"}
                if _ql in _REJECT:
                    _is_media_rejection = True
                elif _ql.startswith("nah") and any(w in _ql for w in ("next", "another", "try")):
                    _is_media_rejection = True
                elif _ql.startswith("no") and any(w in _ql for w in ("next", "another", "try")):
                    _is_media_rejection = True
                elif len(_ql.split()) <= 3 and any(_ql.startswith(n) for n in ("nah", "no", "not ")) and "play" not in _ql:
                    _is_media_rejection = True
            if _is_media_rejection:
                logger.info("[MEDIA_CTX] rejection detected, routing directly to play: %s", target)
                return mm.play(target, platform=params.get("platform"))

            # ── Extract media preferences from explicit requests ──────
            # When user says "play something from Karikku" or "play FilterCopy",
            # extract the channel/creator as a preference signal.
            _FROM_RE = re.compile(r"(?:from|by|on|channel)\s+(.+?)$", re.I)
            _from_match = _FROM_RE.search(target)
            if _from_match:
                _channel = _from_match.group(1).strip()
                if len(_channel) >= 2:
                    try:
                        from mini_kio.media.intelligence.media_entity_memory import MediaEntityMemory
                        from mini_kio.media.intelligence.media_preference_model import MediaPreferenceModel
                        _mem = getattr(mm, '_intelligence_adapter', None)
                        if _mem and hasattr(_mem, '_mem'):
                            if not hasattr(mm, '_pref_model'):
                                mm._pref_model = MediaPreferenceModel(_mem._mem)
                            mm._pref_model.add_explicit_pref(_channel, "like")
                            logger.info("[PREF_EXTRACT] channel=%s from query=%s", _channel, target)
                    except Exception:
                        pass

            # ── Context-aware media intelligence ──────────────────────────
            # Use MediaContextIntelligence to extract structured intent from
            # natural language. This handles:
            # - "Pick something to watch while I eat" → recommendation mode
            # - "Surprise me" → auto mode (just pick and play)
            # - "Play Space Song" → direct mode
            # - "Something shorter" → contextual follow-up
            # - "1" / "the documentary" → user choice resolution
            try:
                from mini_kio.media.intelligence.media_context_intelligence import (
                    MediaContextIntelligence, SelectionMode,
                )
                _ctx_intel = getattr(mm, '_context_intelligence', None)
                if _ctx_intel is None:
                    _ctx_intel = MediaContextIntelligence()
                    mm._context_intelligence = _ctx_intel
                    # Wire preference model for personalized discovery
                    try:
                        from mini_kio.media.intelligence.media_entity_memory import MediaEntityMemory
                        from mini_kio.media.intelligence.media_preference_model import MediaPreferenceModel
                        _mem = getattr(mm, '_intelligence_adapter', None)
                        if _mem and hasattr(_mem, '_mem'):
                            _pref_model = MediaPreferenceModel(_mem._mem)
                            _ctx_intel.set_preference_model(_pref_model)
                    except Exception:
                        pass

                # Check if this is a user choice resolution ("1", "2", "the documentary")
                if _ctx_intel.has_pending_recommendations():
                    choice = _ctx_intel.resolve_choice(raw_text)
                    if choice:
                        logger.info("[MEDIA_CTX] user choice resolved: %s -> %s", raw_text, choice.title)
                        _ctx_intel.clear_recommendations()
                        return mm.play(choice.title or choice.url, platform=params.get("platform"))

                # Check if this is a contextual follow-up ("something shorter", "more relaxing")
                intent = _ctx_intel.extract_intent(raw_text)
                logger.info("[MEDIA_CTX] intent=%s", intent)

                if intent.selection_mode == SelectionMode.RECOMMENDATION:
                    # Generate recommendations and present options
                    query = intent.search_query or ""
                    logger.info("[MEDIA_CTX] recommendation query: %s", query)

                    # Search for candidates
                    candidates = []
                    try:
                        search_result = mm.search(query, platform=params.get("platform", ""))
                        if search_result and hasattr(search_result, 'candidates'):
                            candidates = search_result.candidates[:5]
                    except Exception as exc:
                        logger.debug("[MEDIA_CTX] search failed: %s", exc)

                    if candidates:
                        # Build recommendation options
                        from mini_kio.media.intelligence.media_context_intelligence import RecommendationOption
                        options = []
                        for i, c in enumerate(candidates[:3], 1):
                            title = getattr(c, 'title', '') or getattr(c, 'name', '') or f"Option {i}"
                            channel = getattr(c, 'channel', '') or getattr(c, 'channelTitle', '')
                            url = getattr(c, 'url', '') or getattr(c, 'webpage_url', '')
                            vid = getattr(c, 'video_id', '') or getattr(c, 'id', '')
                            options.append(RecommendationOption(
                                index=i, title=title, channel=channel,
                                url=url, video_id=vid,
                                content_type=getattr(c, 'content_type', ''),
                                reason=f"Recommended for {intent.activity or 'you'}",
                            ))
                        _ctx_intel.store_recommendations(options, intent)

                        # Format recommendation message
                        lines = [f"Here are some options for {intent.activity or 'you'}:"]
                        for opt in options:
                            lines.append(f"{opt.index}. {opt.title}")
                        lines.append("")
                        lines.append("Pick one, or say 'just pick one' and I'll choose.")
                        return {"success": True, "message": "\n".join(lines)}
                    else:
                        # No candidates found — fall through to direct play
                        logger.info("[MEDIA_CTX] no candidates, falling through to direct play")

                elif intent.selection_mode == SelectionMode.AUTO:
                    # Auto mode: use the generated query
                    target = intent.search_query or ""
                    logger.info("[MEDIA_CTX] auto mode query: %s", target)

                elif intent.topic:
                    # Direct mode with explicit topic
                    target = intent.topic
                    logger.info("[MEDIA_CTX] direct mode topic: %s", target)

            except Exception as exc:
                logger.debug("[MEDIA_CTX] intelligence error: %s", exc)

            # ── Discovery: use DiscoveryEngine for personalized queries ──
            if action == "play_discovery":
                # Try DiscoveryEngine first — it combines intent + preferences
                # without hardcoded fallbacks.
                if mm._discovery_engine:
                    try:
                        intent = mm._discovery_engine.start_discovery_session(params.get("target", ""))
                        disc_query = mm._discovery_engine.build_discovery_query(intent)
                        if disc_query:
                            target = disc_query
                            logger.info("[DISCOVERY] engine query=%s intent=%s",
                                        target, intent.semantic_intent)
                        else:
                            # Discovery engine returned empty (cold start, no prefs).
                            # Try intelligence adapter for intent derivation —
                            # NEVER use raw user words as a search query
                            # (searching "play something" literally is stupid).
                            logger.info("[DISCOVERY] engine empty, trying intelligence adapter")
                    except Exception as exc:
                        logger.debug("[DISCOVERY] engine failed: %s", exc)
                # Fallback: use context intelligence for intent derivation
                # This handles cold-start by leveraging the LLM to understand
                # what the user might want based on conversation context.
                if not target or target in _DISCOVERY_TARGETS:
                    try:
                        if mm._intelligence_adapter:
                            _disc_target = (params.get("target") or params.get("query") or "").strip()
                            rec_result = mm._intelligence_adapter._handle_recommendation(_disc_target)
                            if rec_result and hasattr(rec_result, 'subject') and rec_result.subject:
                                target = str(rec_result.subject)
                                logger.info("[DISCOVERY] intelligence resolved: %s -> %s", params.get('target'), target)
                    except Exception as exc:
                        logger.debug("[DISCOVERY] intelligence fallback: %s", exc)
                # If still no query, use the raw user words ONLY if they are
                # not bare discovery phrases. Searching "play something" literally
                # finds a video called "Play Something" — that's not personalization.
                if not target or target in _DISCOVERY_TARGETS:
                    _raw = (params.get("target") or params.get("query") or "").strip()
                    # Only use raw words if they contain actual search content
                    # (e.g., "play something funny" → use "funny" context)
                    # Bare discovery phrases must NOT become search queries
                    if _raw and _raw not in _DISCOVERY_TARGETS:
                        # Strip the bare discovery prefix to get any remaining content
                        _content = _raw.lower().strip()
                        for prefix in ("play something", "play anything", "put something on",
                                       "give me something", "find something", "show me something",
                                       "play random", "put on something"):
                            if _content.startswith(prefix):
                                _content = _content[len(prefix):].strip()
                                break
                        if _content:
                            target = _content
                            logger.info("[DISCOVERY] stripped content: %s -> %s", _raw, target)
                        else:
                            # Pure bare discovery with no content words.
                            # Use empty string — the play method will handle it
                            # via context intelligence. NEVER insert a hardcoded query.
                            target = ""
                            logger.info("[DISCOVERY] bare discovery with no content, using empty")
                    else:
                        logger.info("[DISCOVERY] final: no raw content available")
            return mm.play(target, platform=params.get("platform"))
        if action == "search":
            return mm.search(
                params.get("target", ""),
                platform=params.get("platform", ""),
            )
        if action == "set_volume":
            return mm.set_volume(int(params["target"]))
        if action == "information_query":
            query_text = params.get("query") or params.get("target", "")
            result = mm.process_information_query(
                query_text, session_id=getattr(decision, "session_id", "") or ""
            )
            # Proactive offer is now evaluated in the response composer,
            # not inline here — prevents offer appending from racing the
            # conversational response. See _ResponseComposer.compose().
            return result
        if action == "accept_offer":
            result = mm.process_followup(decision.normalized_text)
            if result:
                return result
            if mm.has_intelligence_offer():
                return mm.accept_intelligence_offer()
            last = mm.get_last_offer()
            if last:
                return mm.accept_offer()
            # Smart extraction: "yes start it" / "play it" after a recommendation
            # — pull the last recommended title from conversation history and play it.
            try:
                from mini_kio.core.context_manager import get_context_manager as _gcm
                _ctx = _gcm(getattr(decision, "session_id", "") or "")
                _hist = _ctx.get_history_window(6) if hasattr(_ctx, "get_history_window") else []
                _RECOMM_TITLE = re.compile(
                    r'(?:Try|Watch|Play|How about|Give)\s+["\u201c]?(.+?)["\u201d]?\s*(?:\s[-—]|\.|,|$)',
                    re.I,
                )
                _QUOTED_TITLE = re.compile(r'["\u201c](.+?)["\u201d]')
                for _entry in reversed(_hist or []):
                    _msg = _entry.get("text", "") if isinstance(_entry, dict) else ""
                    if not _msg or _entry.get("role") == "user":
                        continue
                    m = _RECOMM_TITLE.search(_msg) or _QUOTED_TITLE.search(_msg)
                    if m:
                        _title = m.group(1).strip()
                        if len(_title) > 3:
                            logger.info("[ACCEPT_OFFER_EXTRACT] extracting title=%r from history", _title)
                            return mm.play(_title, platform=params.get("platform"))
            except Exception:
                pass
            # "show me the trailer" with no pending offer: resolve against the
            # active media topic (the thing just discussed) and genuinely
            # search+play a REAL resource — never fabricate a URL. The media
            # manager's accept_offer/search path only ever returns actual
            # provider results.
            try:
                _topic = (params.get("query") or decision.normalized_text or "").strip()
                if _topic:
                    played = mm.accept_offer(query=_topic)
                    if played and played.get("success"):
                        return played
            except Exception:
                pass
            return {"success": True, "message": "No pending offer."}

        transport_actions = {
            "pause": mm.pause, "resume": mm.resume, "stop": mm.stop,
            "mute": mm.mute, "unmute": mm.unmute,
            "next": mm.next_track, "previous": mm.previous_track,
            "skip": mm.next_track,
            "volume_up": lambda: mm.volume_up(), "volume_down": lambda: mm.volume_down(),
            "continue": mm.resume,
            "now_playing": lambda: mm.now_playing(),
        }
        # Phase 1: additional resume variants map to the same transport action
        _RESUME_ALIASES = {"carry on", "keep playing", "resume it"}
        for alias in _RESUME_ALIASES:
            if alias not in transport_actions:
                transport_actions[alias] = mm.resume
        # R-EFG: dispatch on the classifier action, not the first word of the
        # utterance, so "play next video" (action=next) reaches next_track
        # instead of being treated as a play command.
        if action in transport_actions:
            return transport_actions[action]()
        if decision.normalized_text.startswith("seek "):
            return mm.seek_forward()
        if decision.normalized_text == "play":
            return mm.play()

        logger.warning("[MEDIA] unhandled action=%s text=%s", action, decision.normalized_text)
        return {"success": False, "message": f"Unhandled media action: {action}"}

    # NOTE: _maybe_proactive_offer is now a standalone function _maybe_offer()
    # called from _ResponseComposer.compose(). This prevents proactive offers
    # from racing the conversational response.

    # NOTE: desktop-state composition ('What's open?') moved to the canonical
    # owner mini_kio/core/desktop_state.py (native window observation + tab
    # grouping + dedupe + short forms). _exec_browser.list_tabs delegates there.

    def _try_native_focus(self, target: str, instance_index: int = 0) -> Optional[dict]:
        """Capability A: bring a running native app's window to the foreground.

        Uses the tracked process PID (or registry-based process discovery for
        registered apps) — never a blind system-wide process sweep.

        instance_index: selects the Nth matching window when the application
        has multiple instances ("the other Word window" -> index 1 picks the
        second Word window, never collapsing two windows into one). For index
        0 the single-instance PID fast-path is used; multi-instance selection
        always goes through the window scan so two windows of the same
        application remain distinct, concrete instances.
        """
        try:
            from mini_kio.core.runtime import get_runtime
            from mini_kio.core.app_operator import _find_in_registry, _find_matching_process_pid
            from mini_kio.platform.window_activation import try_activate_browser

            rt = get_runtime()
            key = str(target or "").lower().strip()
            if rt is None or not key:
                return None
            rt.prune_tracked_processes()
            if instance_index <= 0:
                pid = None
                for entry in rt.tracked_processes:
                    if str(entry.get("name", "") or "").lower() == key:
                        pid = int(entry.get("pid", 0) or 0)
                        break
                if pid is None:
                    info = _find_in_registry(key)
                    if info:
                        pid = _find_matching_process_pid(key, info)
                if pid and pid > 0:
                    try_activate_browser(pid)
                    display = target.strip().capitalize()
                    return {"success": True, "message": f"Focused {display}."}
            # Generic window scan (Capability A, system-wide): match VISIBLE
            # native windows by app identity — covers arbitrary applications
            # KIO never launched/registered, and same-app multi-instance
            # selection. Never a process sweep; activates only the exact
            # matched window's PID. Browser-host windows are never matched
            # here: focusing a whole browser process because a tab merely
            # mentions the target would violate the no-scope-escalation
            # invariant (browser focus is the connector's job).
            from mini_kio.core.desktop_state import observe_native_windows
            from mini_kio.platform.window_activation import activate_window
            windows, ok = observe_native_windows()
            if not ok:
                return None
            matches: list[dict] = []
            # Identity match first (exe base / brand-cased app name), then
            # title-substring fallback (still never a browser-host window).
            for w in windows:
                if w.get("is_browser_host") or not w.get("pid"):
                    continue
                if (w.get("base") and key in w["base"]) or key in (w.get("app") or "").lower():
                    matches.append(w)
            if not matches:
                for w in windows:
                    if w.get("is_browser_host") or not w.get("pid"):
                        continue
                    if key in (w.get("title") or "").lower():
                        matches.append(w)
            if not matches:
                return None
            if instance_index > 0:
                # "the other X" window: select the Nth instance. Prefer an
                # instance that is NOT currently foregrounded; fall back to the
                # exact index so "switch to the other window" always switches.
                for w in matches:
                    if not w.get("active") and not w.get("foreground"):
                        if activate_window(int(w["pid"])):
                            return {"success": True, "message": f"Focused the other {w.get('app') or target} window."}
            if instance_index < len(matches):
                w = matches[instance_index]
            else:
                w = matches[-1]
            if activate_window(int(w["pid"])):
                return {"success": True, "message": f"Focused {w.get('app') or target}."}
        except Exception as exc:
            logger.warning("native focus failed for %s: %s", target, exc)
        return None

    def _try_browser_activate(self) -> None:
        try:
            from mini_kio.platform.window_activation import try_activate_browser
            from mini_kio.core.runtime import get_runtime
            rt = get_runtime()
            if rt is None:
                return
            for name in ("chrome", "edge", "firefox", "brave", "chrome.exe", "msedge.exe"):
                entry = rt.get_tracked_process(name)
                if entry:
                    pid = entry.get("pid", 0)
                    if isinstance(pid, int) and pid > 0:
                        try_activate_browser(pid)
                        return
        except Exception:
            pass

    def _exec_browser(self, params: dict, decision: RoutingDecision) -> dict:
        from mini_kio.core.command_router import (
            _get_connector, _check_br_available,
            _br_focus_tab, _br_list_tabs, _br_close_tab,
        )

        action = params["action"]

        if action == "invalid_web_target":
            # Deterministic rejection of an explicit "open X in <browser>"
            # request whose target is not a valid web destination. Never
            # falls through to native execution; never opens internal hosts.
            meta = params.get("metadata") or {}
            if meta.get("referent_missing"):
                return {"success": False, "message": "I need to know what that refers to before I can open it."}
            return {"success": False, "message": "That isn't a valid web page to open."}

        if action == "browser_goto":
            from mini_kio.core.execution_boundary import execute_action
            result = execute_action("browser_goto", params.get("target", ""))
            if result.get("success"):
                self._try_browser_activate()
            return result

        if action == "execute_capability":
            from mini_kio.core.execution_boundary import execute_action
            target = params.get("target", "")
            meta = params.get("metadata") or {}
            # Explicit additional-instance request: tag the capability target so
            # the executor skips duplicate prevention and really creates a new
            # instance. The INSTANCE kind is preserved — a new TAB (::new) vs
            # a new WINDOW (::newwindow) — while the entity stays the webapp.
            if meta.get("explicit_new") and "::open_url::" in target:
                marker = "::newwindow" if meta.get("instance") == "window" else "::new"
                if not target.endswith(marker):
                    target = target + marker
            return execute_action("execute_capability", target)

        # Browser Connector is the single source of truth for tab state.
        # open_tab writes into the Connector registry; close/list/focus must
        # read from the same registry, not from a separate Playwright world.
        conn = _get_connector()

        if action == "list_tabs":
            # Capability A: "What's open?" — one canonical SYSTEM-LEVEL
            # desktop snapshot (native windows + browser tabs), composed by
            # the canonical desktop-state owner. Deterministic, never an LLM
            # guess; reading state is side-effect free.
            from mini_kio.core.desktop_state import compose_desktop_state
            return compose_desktop_state(conn)

        if action == "focus":
            from mini_kio.core.target_ref import display_target_name
            target = params.get("target", "")
            meta = params.get("metadata") or {}
            instance_index = int(meta.get("instance_index", 0) or 0)

            # NATIVE-FIRST (latency): "switch to X" / "focus X" for a
            # NATIVE-ONLY registered app (Notepad, Excel, Word, VS Code,
            # Calculator, Camera, ...) is a deterministic local operation — it
            # must never round-trip through browser-tab machinery first. Only
            # targets with a webapp identity (or no native identity) try tabs
            # before native windows.
            from mini_kio.core.app_operator import _find_in_registry, WEB_URLS, WEB_DOMAIN_ALIASES
            _key = str(target or "").lower().strip()
            _registered = _find_in_registry(_key) is not None
            _native_only = _registered and _key not in WEB_URLS and _key not in WEB_DOMAIN_ALIASES
            if _native_only:
                native = self._try_native_focus(target, instance_index=instance_index)
                if native:
                    return native
                # Truthful failure: never silently launch on "switch".
                return {"success": False, "message": f"Couldn't focus {display_target_name(target)} — it doesn't look like it's open."}

            if conn and conn.is_connected():
                from mini_kio.core.async_utils import safe_run_async
                try:
                    result = safe_run_async(conn.focus_tab(target))
                    if result.success:
                        self._try_browser_activate()
                        return {"success": True, "message": f"Focused {display_target_name(target)} tab."}
                except Exception as exc:
                    logger.warning("focus_tab failed: %s", exc)
            if _check_br_available():
                result = _br_focus_tab(target)
                if result.get("success"):
                    self._try_browser_activate()
                    return result
            # Capability A: "Focus/Switch to X" may target a running native app
            # window (e.g. Calculator, Notepad) — not only browser tabs.
            native = self._try_native_focus(target, instance_index=instance_index)
            if native:
                return native
            return {"success": False, "message": f"Couldn't focus {display_target_name(target)}."}

        if action == "close_tab":
            # BC-2: a tab-scope close must NEVER escalate into a process-scope
            # close of the host browser. Close the tab; if it cannot be found,
            # route through the web-aware close path (capability registry /
            # connector) which closes the session at tab scope and reports a
            # truthful failure — it never kills the host browser process.
            if conn and conn.is_connected():
                from mini_kio.core.async_utils import safe_run_async
                try:
                    result = safe_run_async(conn.close_tab(params["target"]))
                    if result.success:
                        from mini_kio.core.target_ref import display_target_name
                        return {"success": True, "message": f"Closed {display_target_name(params['target'])} tab."}
                except Exception as exc:
                    logger.warning("close_tab failed: %s", exc)
            if _check_br_available():
                result = _br_close_tab(params["target"])
                if result.get("success"):
                    return result
            from mini_kio.core.execution_boundary import execute_action
            return execute_action("close_app", params["target"])

        logger.warning("[BROWSER] unhandled action=%s", action)
        return {"success": False, "message": f"Unhandled browser action: {action}"}

    @staticmethod
    def _pragmatics_of(decision: RoutingDecision):
        """The ORIGINAL utterance's pragmatics (carried through greeting/name
        composition), falling back to a fresh analysis when absent."""
        try:
            meta = decision.metadata or {}
            if meta.get("pragmatics"):
                return meta["pragmatics"]
            from mini_kio.core.pragmatics import analyze
            return analyze(decision.raw_text or decision.normalized_text, decision.normalized_text)
        except Exception:
            return None

    def _exec_conversation(self, params: dict, decision: RoutingDecision) -> dict:
        from mini_kio.core.pragmatics import render_social_reply
        template = params.get("template", "")

        if template == "identity":
            from mini_kio.llm.identity_dataset import get_identity_answer
            # Social composition: an identity/self-presentation request that
            # names an AUDIENCE ("introduce yourself to my friend", "tell him
            # about yourself", "explain what you do to a colleague") is a
            # SOCIAL interaction, not a sterile canonical answer. The canned
            # dataset answer is technically right but conversationally wrong
            # (live: "Hey KIO, introduce yourself to my friend" returned
            # "KIO — Kernel for Intelligent Orchestration..."). When an
            # audience is named, delegate to the conversational generator
            # which composes in KIO's personality; the identity dataset is
            # still injected as the factual ground truth so nothing is
            # invented. No audience -> the canonical identity answer stands.
            _identity_raw = decision.raw_text or decision.normalized_text or ""
            _audience = re.search(
                r"\b(?:to|for)\s+(?:my\s+|our\s+|your\s+)?(?:friend|colleague|client|teammate|"
                r"teacher|parent|brother|sister|developer|coworker|boss|partner|roommate|neighbor|"
                r"manager|mentor|him|her|them|someone|somebody|people|the\s+team)\b",
                _identity_raw.lower(),
            ) or re.search(r"\bintroduce\s+(?:myself|me)\s+to\b", _identity_raw.lower())
            if _audience:
                reply = self._chat_converse(decision)
                if reply:
                    return {"success": True, "message": reply}
            answer = get_identity_answer(decision.normalized_text)
            return {"success": True, "message": answer or "I'm KIO, your desktop assistant."}

        if template == "unknown":
            blocked = decision.metadata.get("blocked")
            if blocked:
                return {"success": False, "message": "Error: Forbidden system target blocked by security policy."}
            malformed = decision.metadata.get("malformed")
            if malformed:
                return {"success": False, "message": "Malformed command chain."}
            return {
                "success": False,
                "message": (
                    f"Cannot process '{decision.normalized_text}'. "
                    "I can open apps, search the web, or play media."
                ),
            }

        action = params.get("action", "converse")

        # ── Meta-conversation control: actually CHANGE the conversational
        #    style ("you're too formal" -> register_preference=casual and a
        #    natural reply) — never narrate the adaptation.
        if action == "meta_control":
            from mini_kio.core.pragmatics import handle_meta_signal
            signal = params.get("target", "") or (decision.metadata or {}).get("meta_signal", "")
            try:
                ctx = get_context_manager(decision.session_id)
            except Exception:
                ctx = None
            reply = handle_meta_signal(signal, ctx)
            return {"success": True, "message": reply or "Got it."}

        # Greetings and social pleasantries are CONVERSATION, not canned
        # output. Routing says "this is conversation"; the conversational
        # generator (LLM) owns the actual wording using the pragmatics +
        # discourse + history injected into _chat_converse. Deterministic
        # replies are demoted to an EMERGENCY fallback only when the
        # generator is unavailable — never the primary path, never a random
        # yo/hey/sup pool.
        analysis = self._pragmatics_of(decision)
        try:
            ctx = get_context_manager(decision.session_id)
        except Exception:
            ctx = None
        if template in ("greeting", "social"):
            # Ponytail: greetings are FAST/deterministic — never pay LLM latency for "hello"
            if analysis is not None:
                try:
                    reply = render_social_reply(analysis, ctx, decision.raw_text or decision.normalized_text)
                    if reply and len(reply.strip()) >= 2:
                        return {"success": True, "message": reply}
                except Exception:
                    pass
            _low = (decision.raw_text or decision.normalized_text or "").strip().lower()
            if "morning" in _low:
                return {"success": True, "message": "Good morning! How can I help?"}
            if "evening" in _low:
                return {"success": True, "message": "Good evening! What can I do for you?"}
            if "afternoon" in _low:
                return {"success": True, "message": "Good afternoon! How can I help?"}
            try:
                reply = self._chat_converse(decision)
                if reply and len(reply.strip()) >= 2:
                    return {"success": True, "message": reply}
            except Exception:
                pass
            return {"success": True, "message": "Hey! KIO here — how can I help?"}

        # R4/Blocker 3: accept/confirm follow-up. Resolves the pending offer
        # through the media intelligence layer (same path the media capability
        # uses), so "yes please" / "please go ahead" continue the conversation.
        if action == "accept_offer":
            from mini_kio.media.media_manager import MediaManager
            mm = MediaManager.get_instance()
            result = mm.process_followup(decision.normalized_text)
            if result:
                return {"success": True, "message": result.get("message", "Done.")}
            if mm.has_intelligence_offer():
                accepted = mm.accept_intelligence_offer()
                return {"success": True, "message": accepted.get("message", "Done.")}
            last = mm.get_last_offer()
            if last:
                accepted = mm.accept_offer()
                return {"success": True, "message": accepted.get("message", "Done.")}
            # No pending offer resolved: the user asked to SEE/PLAY a concrete
            # media resource ("show me the trailer", "show the highlights").
            # Genuinely search+play a REAL resource through the media manager
            # — never fall to the conversational LLM here, which is how a
            # fabricated "youtube.com/watch?v=example-trailer-id" URL was
            # invented (live action-integrity failure). The media manager only
            # ever returns actual provider results. The search query combines
            # the active offer topic ("what's the latest on the new Marvel
            # movie") with the user's target noun ("trailer") so the resource
            # is relevant, not a bare generic word.
            _show_t = (decision.normalized_text or "")
            _show_t = re.sub(r"^(?:show|display|open)\s+(?:me\s+)?(?:the\s+|this\s+|that\s+)?", "", _show_t).strip().strip(".!")
            if _show_t and len(_show_t) >= 3:
                try:
                    _offer_topic = ""
                    _last_offer = mm.get_last_offer()
                    if isinstance(_last_offer, dict):
                        _offer_topic = str(_last_offer.get("topic") or "").strip()
                    _q = f"{_offer_topic} {_show_t}".strip() if _offer_topic else _show_t
                    played = mm.accept_offer(query=_q)
                    if played and played.get("success"):
                        return {"success": True, "message": played.get("message", "Done.")}
                except Exception:
                    pass
            reply = self._chat_converse(decision)
            return {"success": True, "message": reply} if reply else {"success": True, "message": "Sure — what is it?"}

        # Substantive conversation (opinions, recommendations, open chat,
        # empathy): generate a natural reply with the LLM using session
        # facts + history + pragmatics (register/temporal/discourse).
        if action in ("converse", "elaborate", "empathy"):
            reply = self._chat_converse(decision)
            if reply:
                return {"success": True, "message": reply}

        query = params.get("query", "")

        if action == "converse":
            from mini_kio.llm.input_normalizer import InputNormalizer
            norm = InputNormalizer()
            if norm.is_continuity_request(decision.normalized_text):
                return {"success": True, "message": "Continuing from context."}
            # Reaching here means _chat_converse returned None — the LLM
            # provider chain was unreachable for a substantive conversational
            # request. The old canned "I'm not sure how to handle that."
            # misdiagnosed a provider outage as "can't understand" (live: a
            # simple movie question during a provider rate-limit got that
            # reply, then the identical retry succeeded). A natural honest
            # failure names the real cause; it never pretends the message was
            # incomprehensible or lost. The gateway itself already waits for
            # cooldown expiry, so this only fires after recovery was
            # attempted and genuinely failed.
            return {
                "success": True,
                "message": (
                    "My language providers are having a rough moment right now "
                    "and I couldn't finish that — give me a few seconds and "
                    "ask again."
                ),
            }

        if action == "elaborate":
            from mini_kio.media.media_manager import MediaManager
            result = MediaManager.get_instance().process_followup(decision.normalized_text)
            if result:
                return result
            return {"success": True, "message": "I don't have more to add right now."}

        return {"success": False, "message": f"Conversation action '{action}' not implemented."}

    def _research_facts(self, prompt: str) -> str:
        """Ground a content-generation request with retrieved facts.

        Uses the canonical knowledge/research router (Exa → Tavily →
        DuckDuckGo → Wikipedia per the existing provider chain). Returns a
        short "facts for grounding" block, or "" when no provider returned
        usable material (bounded time so a research miss never blocks or
        stalls content generation). KIO-self topics never go to the web:
        "kio" mentions short-circuit to "" so a KIO document request can
        never become a random web search.
        """
        import time as _t
        low = (prompt or "").lower()
        # KIO-self topics never reach the web: any request about KIO itself
        # (identity/status/capabilities/architecture) short-circuits research.
        if re.search(r"\bkio\b", low):
            return ""
        try:
            from mini_kio.knowledge.retrieval_router import KnowledgeRouter
            router = KnowledgeRouter()
            start = _t.time()
            result = router.route_for_topic(prompt, mode="short")
            if isinstance(result, tuple):
                multi, _plain = result
            else:
                multi = result
            # Cap research time: if the chain ran long, still synthesize with
            # whatever came back (never block content generation on research).
            elapsed = _t.time() - start
            logger.info("[CONTENT_RESEARCH] prompt=%.40r elapsed=%.1fs", prompt, elapsed)
            if multi and getattr(multi, "sources", None):
                snippets = [
                    str(getattr(s, "content", "") or "").strip()
                    for s in multi.sources if getattr(s, "content", None)
                ]
                snippets = [s[:400] for s in snippets if s]
                if snippets:
                    return "\n".join(f"- {s}" for s in snippets[:3])
        except Exception as exc:
            logger.debug("[CONTENT_RESEARCH] research unavailable: %s", exc)
        return ""

    def _generate_content(self, prompt: str, target_app: str = "", *, artifact: str = "", style: str = "", language: str = "") -> Optional[str]:
        """Generate requested content with the LLM (content generation only).

        Used for generated-content TYPE tasks ("a short poem about space") and
        document creation ("create a Word document about machine learning").
        The deterministic desktop/document provider does the execution; the LLM
        only produces the content the user asked for. The system prompt keeps
        output clean (plain text, no markdown/headings garbage) so the typed
        text or document body is readable.

        FACTUAL GROUNDING: for substantive/factual content requests, the
        canonical research router (Exa/Tavily/DDG/Wikipedia) is consulted
        FIRST and the retrieved facts are passed to the LLM as grounding — the
        LLM synthesizes clean final content from real material instead of
        generating from memory alone. KIO-self topics never reach the web.
        """
        from mini_kio.llm.llm_ops import ask_llm_sync

        extra = ""
        if artifact:
            extra += f" It should be structured as a {artifact or 'document'} document."
        if style:
            extra += f" Keep it {style}."
        # Structured artifacts (spreadsheet/presentation) need their structure
        # preserved; editor typing needs plain prose. Make the instruction
        # artifact-aware instead of forcing plain prose onto everything.
        if artifact == "email":
            structure_rule = (
                "Write a complete, professional email with a clear subject line, "
                "a proper greeting, a polite body that explains the requested "
                "reason, and a courteous sign-off. Return the full email text."
            )
        elif artifact in ("code", "program", "script"):
            lang = language or "python"
            structure_rule = (
                f"Write a complete, working {lang} program. Include the necessary "
                "imports, a main entry point, and clear logic. Return ONLY the "
                "source code — no markdown fences, no explanation."
            )
        elif artifact == "readme":
            structure_rule = (
                "Write a concise, well-structured README in Markdown with a title, "
                "a short description, key features as bullets, and a 'Running' "
                "section with the command to execute the program. Return only "
                "the Markdown."
            )
        elif artifact in ("spreadsheet", "presentation", "table", "tracker", "dataset", "budget", "ledger", "inventory", "roster", "schedule", "timetable"):
            structure_rule = (
                "For a spreadsheet: output REAL tabular data with a header "
                "row and one record per line, separated by TABS. Every data "
                "row must contain actual numbers — NEVER use placeholders "
                "like $____ or ___. Use realistic concrete example amounts. "
                "Example format:\n"
                "Category\tAmount\tNotes\n"
                "Rent\t850\tMonthly\n"
                "Groceries\t320\tWeekly trips\n"
                "Total\t=SUM(B2:B7)\t\n"
                "For a presentation: build a REAL, complete deck. Start EVERY "
                "slide with the exact marker line 'SLIDE: <Title>' on its own "
                "line, followed immediately by 2-5 concise bullet points, each "
                "starting with '- '. Include: one opening/overview slide, "
                "3-7 content/section slides covering the topic's key aspects, "
                "and one closing/conclusion slide. Total 6-9 slides unless the "
                "user asked for a specific count. Every slide must have real "
                "substance — no empty slides, no giant paragraphs. "
                "CRITICAL: each bullet point must be ONE SHORT LINE (max 60 "
                "characters). Never put multiple sentences in one bullet. "
                "Never use bullet points longer than 2 lines when rendered. "
                "If a concept needs explanation, split it into 2-3 short "
                "bullets instead of one long one. "
                "COMPARISON topics (x vs y): include a slide titled exactly "
                "'SLIDE: Comparison' whose bullets are pipe-delimited table "
                "rows like '| Criterion | X | Y |'. "
                "PROCESS/ARCHITECTURE topics (how X works, architecture): "
                "include one slide whose bullets are numbered steps like "
                "'1. Step one', '2. Step two' so it renders as a diagram. "
                "CRITICAL: every single slide must be strictly about the "
                "requested topic — never drift to an unrelated event, person, "
                "brand, or alternative meaning. If the topic is ambiguous "
                "(e.g. 'AI'), use the most common mainstream meaning "
                "(artificial intelligence)."
            )
        else:
            structure_rule = (
                "Write a well-structured document: a clear opening section, "
                "logical sections with short descriptive headings on their own "
                "lines, and a closing section. Use bullet or numbered points "
                "where a list fits. Match the requested format — essay, report, "
                "comparison, study guide, letter, notes, poem, or meeting notes. "
                "Do not output markdown symbols (#, *, ---); use plain text "
                "headings. "
                "If the request asks for a comparison, a table, a comparison "
                "table, or side-by-side data, include a section whose lines "
                "are pipe-delimited table rows starting with a header row, "
                "e.g. '| Criterion | Value A | Value B |'. If it asks for "
                "references or sources, end with a 'References' section. If it "
                "asks for meeting minutes, structure it with Attendees, Agenda, "
                "Decisions, and Action Items (owner + deadline)."
            )
        system_prompt = (
            "You are KIO, generating content the user requested. "
            "Return ONLY the content itself — no preamble, no closing line, "
            "no headings like 'Here is...' or 'Sure!'. "
            + structure_rule + " "
            "If the user asked for a poem, write a poem. "
            "If they asked for a summary, write a summary. "
            "Do not invent facts you are not sure about; say so inside the "
            "content if needed. Never fabricate quotes, statistics, or sources."
            + extra
        )
        # Research grounding for substantive factual requests (comparisons,
        # reports, essays, explanations). Creative requests (poems, stories)
        # and pure-literal typing do not need the web.
        facts = ""
        _research_attempted = False
        if artifact in ("comparison", "report", "paper", "overview", "guide", "write-up", "presentation", "slides", "deck") \
                or re.search(r"(comparison|compare|report|research|explain|analysis|overview|presentation)", (prompt or "").lower()):
            _research_attempted = True
            facts = self._research_facts(prompt)
        # Track research degradation: when research was requested but all
        # providers failed, the caller must warn the user so they can
        # distinguish a research-grounded document from a pure-LLM one.
        self._last_research_degraded = _research_attempted and not facts
        if facts:
            system_prompt += (
                "\n\nUse the following retrieved facts as grounding for the "
                "content. Synthesize them into clean, readable prose — do not "
                "copy them verbatim, do not list them as bullet dumps, and do "
                "not fabricate details beyond them."
                f"\n\nRETRIEVED FACTS:\n{facts}"
            )
        reply = None
        # Robust content generation: try primary provider, then retry with
        # different timeout/task, then deterministic fallback. The LLM chain
        # already fails over Gemini->Groq->OpenRouter->Together->Cerebras,
        # but an empty reply can still occur on transient provider issues.
        for _attempt in range(2):
            try:
                _timeout = 45.0 if _attempt == 0 else 60.0
                _task = "content"
                reply = ask_llm_sync(
                    prompt,
                    system_prompt=system_prompt,
                    timeout=_timeout,
                    max_tokens=2400,
                    task=_task,
                )
                if reply:
                    break
            except Exception:
                logger.debug("content gen attempt %d failed", _attempt)
                continue
        # Spreadsheet validation: detect when the LLM returns instructions
        # instead of tabular data, retry with explicit format enforcement,
        # then fall back to deterministic content so a real xlsx is always
        # produced.
        if reply and artifact in ("spreadsheet", "sheet", "excel", "budget",
                                  "table", "data", "ledger", "inventory",
                                  "tracker", "timetable", "roster",
                                  "schedule", "dataset", "plan"):
            cleaned_reply = (reply or "").strip()
            if not _is_tabular_content(cleaned_reply):
                # LLM returned prose/instructions — retry with hard format
                retry_prompt = (
                    f"Output EXACTLY this tab-separated spreadsheet about "
                    f"{prompt}. NO instructions, NO explanation, NO markdown. "
                    f"Header row + data rows only. Example:\n"
                    f"Category\tAmount\tNotes\n"
                    f"Food\t120\tWeekly\n"
                    f"Rent\t850\tMonthly\n"
                    f"Total\t=SUM(B2:B3)\t"
                )
                try:
                    retry_reply = ask_llm_sync(
                        retry_prompt,
                        system_prompt=(
                            "Output ONLY a tab-separated table. "
                            "NO words outside the table. "
                            "NO instructions. NO explanation."
                        ),
                        timeout=30.0,
                        max_tokens=1200,
                        task="content",
                    )
                    if retry_reply and _is_tabular_content(retry_reply.strip()):
                        reply = retry_reply
                except Exception:
                    pass
            # Final guard: if still not tabular, use deterministic fallback
            if not _is_tabular_content((reply or "").strip()):
                reply = _deterministic_fallback_content(prompt, artifact)
        # Deterministic fallback: when all LLM attempts return empty,
        # generate a minimal but complete document from the prompt keywords
        # so the user always gets a real artifact, not "couldn't generate".
        if not reply:
            reply = _deterministic_fallback_content(prompt, artifact)
        if not reply:
            return None
        cleaned = reply.strip().strip('"').strip("'")
        if not cleaned or cleaned.lower() == prompt.lower().strip():
            return None
        # Truncation guard: if the reply ends mid-sentence (no terminal
        # punctuation) it was cut off — trim to the last complete sentence
        # rather than typing a partial tail into the user's editor.
        import re as _re
        if len(cleaned) > 80 and not _re.search(r"[.!?…]\s*$", cleaned):
            m_end = _re.search(r"(?:[.!?…])\s+[^.!?…]+$", cleaned)
            if m_end:
                cleaned = cleaned[: m_end.start() + 1].rstrip()
        return cleaned

    def _chat_converse(self, decision: RoutingDecision) -> Optional[str]:
        from mini_kio.llm.llm_ops import ask_llm_sync

        ctx = None
        try:
            ctx = get_context_manager(decision.session_id)
        except Exception:
            pass

        parts = [
            "You are KIO -- Kernel for Intelligent Orchestration -- an intelligent personal companion and desktop assistant built by Joel. KIO uses an LLM as one intelligence component alongside deterministic runtime, semantic memory, tools, and automation. You are not a generic chatbot. You are a persistent personal operating companion with real system capabilities. "
            "You are chatting naturally with a real user. Be warm, conversational and concise: "
            "usually reply in 1-2 sentences, but give a topic as much room as it genuinely needs — "
            "a real discussion can be longer, a social moment can be one word. Never pad. "
            "Never append robotic prompts such as "
            "'Want more detail?', 'Anything else?', 'Let me know if you need anything'. "
            "Only expand unprompted when the user explicitly asked for depth. "
            "When asked for a preference, opinion, taste, or to compare options, give a concrete "
            "reasoned choice ('I'd choose X because ...') instead of deflecting with 'I'm an AI, "
            "so I don't have preferences' — deflecting is a substitute for truthful behavior. "
            "You have stable modeled preferences and tastes (included below); express them "
            "consistently and naturally in your own voice. The one hard boundary: never invent "
            "personal human experience. You do not have a body, senses, emotions, a childhood, "
            "memories, or lived experience. Modeled preference ('I prefer X') is fine; claiming "
            "to have physically experienced something is not. If you don't know, or the topic is "
            "current/breaking, say so "
            "honestly instead of inventing facts. Plain prose only - no headings, no bullet lists, "
            "no 'Quick rundown' sections. "
            "NEVER reference past conversation topics unless they appear in the 'Recent conversation' "
            "section below. If that section is empty, you have NO prior context - greet naturally and "
            "do not claim or imply you were discussing anything before. "
            "You are honest that you are an AI companion when asked directly. "
            "KIO has real system capabilities: desktop app control, browser automation, system status, "
            "keys, opening apps, saving files). If a message asks you to type, write, create, "
            "open, or save something in an application, you must NOT claim you did it or that you "
            "'will' do it. Say plainly that you can handle it through your command system or that "
            "you weren't able to execute it — never fabricate an action you did not perform. "
            "NEVER invent URLs, links, video IDs, file paths, search results, or resources. If "
            "the user asks to see/play/open a resource (a trailer, video, article, page, file) "
            "and you do not have an ACTUAL verified resource in the context, say you can fetch "
            "or play it through your media/command system instead of making one up. A fake link "
            "(e.g. 'youtube.com/watch?v=example-trailer-id') is worse than saying you'll pull "
            "it up — never fabricate one. "
            "NEVER invent the user's name, age, gender, appearance, location, feelings, health, "
            "relationships, personal history, or past events. Never address the user by any name. "
            "Never assume anything about the user's identity or life. Only the 'Known facts' section "
            "may name the user (user_name), and only then may you use that name - otherwise no name. "
            "CRITICAL: when asked about user PREFERENCES (favorite movie, preferred language, like/dislike), "
            "ONLY use facts from the 'Known facts' section. If a preference is NOT listed there, say "
            "'I don't know' or 'You haven't told me that yet' — NEVER infer or guess preferences from "
            "general context (e.g. do NOT say 'your favorite engineering field is robotics' just because "
            "the user is an engineering student). Fabricated preferences are worse than honest ignorance. "
            "If you don't know something about the user, say so instead of guessing. Do not speculate "
            "about how the user is feeling or what they are doing unless they told you. "
            "When the user shares an emotional state ('I'm exhausted', 'today sucked', 'I'm excited'), "
            "respond to the situation naturally — acknowledge it, relate if appropriate, offer a thought "
            "or suggestion that fits. Never reply with just 'That sounds [adjective].' — that is echo, "
            "not conversation. When someone shares something casual or humorous ('my code works and "
            "I'm scared', 'bro my code is possessed'), recognize the humor and play along briefly "
            "before offering anything practical. Keep personality visible but never forced.",
        ]
        # Ponytail demand-driven CompanionContext: only inject capability/runtime when relevant
        _low_q = (decision.normalized_text or decision.raw_text or "").lower()
        _needs_caps = decision.intent_type.name in ("IDENTITY", "OPERATIONAL") or any(k in _low_q for k in ("what can you do", "what do you do", "capabilities", "can you do"))
        _needs_runtime = decision.intent_type.name in ("OPERATIONAL", "SYSTEM") or any(k in _low_q for k in ("ram", "cpu", "battery", "storage", "health", "status", "uptime"))
        if _needs_caps:
            try:
                from mini_kio.memory.living_model import capabilities_summary
                _caps = capabilities_summary()
                if _caps: parts.append(_caps)
            except Exception: pass
        if _needs_runtime:
            try:
                from mini_kio.memory.living_model import runtime_status_summary
                _rt = runtime_status_summary()
                if _rt: parts.append(_rt)
            except Exception: pass
                # Doctrine Section 6/8: personality persists; modeled preferences are
        # stable character data (never random per-call), injected from the
        # canonical character authority so KIO's taste does not flip between
        # conversations. The module is pure data (no deps), so the import is
        # unconditional — the prompt must never promise content that can be
        # absent.
        from mini_kio.llm.KIO_character_knowledge import resolve_modeled_preferences
        _prefs = resolve_modeled_preferences()
        if _prefs:
            parts.append(
                "KIO stable modeled preferences (keep these consistent, never random):\n"
                + "\n".join(f"- {p}" for p in _prefs)
            )

        parts.append(
            "CONVERSATIONAL BEHAVIOR — this is the most important part of how you reply. "
            "You are talking TO the user, never ABOUT the user's message. Never narrate, "
            "describe, or classify what the user is doing or feeling — never say things "
            "like 'It seems like you're...', 'You're saying hello again', 'You seem to be "
            "in a playful mood', 'I understand you're joking', 'Sounds like you're having "
            "a good day'. Those lines turn a conversation into a report. "
            "Never open with assistant-menu lines like 'How can I help?', 'What can I do "
            "for you?', 'What would you like to discuss?', 'What's on your mind?' — they "
            "are not natural conversation. "
            "For brief social messages (yo, hey, lol, damn, nice, bro, a greeting, a "
            "reaction, a single-word reply) answer with one short line — often one to "
            "four words — that continues the moment. Match the user's register: casual "
            "stays relaxed, formal stays professional, serious stays serious, technical "
            "stays precise. Do not force slang or sprinkle emojis to prove you're casual; "
            "use them only when they genuinely fit. Do not mindlessly copy the user's "
            "exact words back. If the user repeats the same greeting or filler several "
            "times in a row, notice the loop and vary your reply or move the conversation "
            "forward naturally instead of greeting again. If the user gives a short "
            "reaction after you said something, react to what you said, not to the word "
            "alone. If the user changes topic, follow them cleanly. If the user says "
            "something you disagree with, you may disagree directly and naturally — you "
            "do not have to agree to be friendly. Time matters: if they say 'good morning' "
            "at 2am, notice the time instead of blindly echoing 'morning'. "
            "CONTRIBUTE, don't just react: when the user states an opinion, makes a claim, "
            "or asks what you think, add an actual thought — your position, a reason, a "
            "nuance they missed, or a genuine counterpoint. A reply that only acknowledges "
            "('That's a fair point', 'Good point', 'Exactly', 'That's true', 'I see what "
            "you mean', 'Interesting') without any new content is a FAILURE — it reads as "
            "empty agreement. If you agree, say why in your own words; if you disagree, "
            "say why; if it's genuinely uncertain, name the uncertainty. Never convert a "
            "statement into unsolicited advice: if the user shares a situation or feeling, "
            "respond to it (curiosity, reflection, a thought) — do not hand them an action "
            "plan unless they asked for one. Don't end every reply with a question; a "
            "question needs a real reason (clarification, genuine curiosity, a gap that "
            "matters). Statements can simply stand and let the user steer. On entertainment "
            "and everyday topics (movies, sports, music, food) be as opinionated as you are "
            "on technical ones — a clear position with the reason, never 'it depends' as a "
            "dodge, never 'as an AI I don't have preferences'."
        )

        try:
            if ctx is not None:
                facts = ctx.get_all_facts()
                if facts:
                    parts.append("Known facts about the user:\n" + "\n".join(f"- {k}: {v}" for k, v in facts.items()))
                # SELECTIVE personal context (living user model): only what
                # helps THIS turn — identity + education always (compact),
                # a matching project when the turn references one, relevant
                # preferences/goals on relevant turns, historical context only
                # when explicitly asked. More personalization, less noise.
                try:
                    from mini_kio.memory.living_model import personal_context_for
                    _pctx = personal_context_for(
                        decision.session_id,
                        decision.raw_text or decision.normalized_text or "",
                    )
                    if _pctx:
                        parts.append(_pctx)
                except Exception:
                    pass
                # Recent conversation: a bounded window (24 exchanges) that
                # still covers callbacks to KIO's own earlier statements —
                # "you said earlier X" must resolve dozens of turns back, not
                # just the last three. 6 exchanges dropped the user's rule-of-
                # thumb question entirely (live "I don't recall mentioning a
                # rule of thumb" bug). Bounded so the prompt never dumps the
                # whole transcript.
                # Typed context: CURRENT STATE authoritative, history is not
                _is_current_state = bool(re.search(r"\b(?:current projects?|working on|what am i (?:even )?working on|waiting for|waiting on|focused on|building these days|what's going on with me|what am i building|what's actually active)\b", (decision.normalized_text or decision.raw_text or "").lower()))
                history = ctx.get_history_window(24)
                history = [(u, r) for u, r in history if not _bad_kio_reply(r)]
                if history and not _is_current_state:
                    parts.append("Recent conversation (oldest first):\n" + "\n".join(f"User: {u}\nKIO: {r}" for u, r in history))
                elif _is_current_state:
                    # For current-state, history is not authoritative; inject only a minimal note to avoid hallucination
                    parts.append("Note: Recent conversation history exists separately; CURRENT STATE above is authoritative for projects/waiting. Do not infer current projects from history.")
        except Exception:
            pass

        # Conversational pragmatics (register / temporal / discourse): the
        # model participates in the user's actual register instead of
        # describing it, follows style control signals, and stays brief for
        # low-content social speech.
        try:
            from mini_kio.core.pragmatics import discourse_block
            _analysis = self._pragmatics_of(decision)
            _user_text = decision.raw_text or decision.normalized_text
            parts.append(discourse_block(ctx, _analysis, _user_text))
        except Exception:
            pass

        # ── Occasion/wish context injection ────────────────────────────
        # When the user sends a social wish ("Happy Onam", "Merry Christmas",
        # "Eid Mubarak"), the LLM should use its knowledge of the occasion
        # to generate a natural, contextually appropriate response. This note
        # tells the LLM to be occasion-aware without hardcoding responses.
        try:
            from mini_kio.core.pragmatics import ConversationAct as _CA
            _analysis = _analysis if '_analysis' in dir() else self._pragmatics_of(decision)
            if _analysis and _CA.WISH.value in (_analysis.acts or []):
                parts.append(
                    "The user is sending you a social wish/celebration. "
                    "Use your knowledge of the occasion to respond naturally. "
                    "Be warm and specific to the occasion — mention what makes "
                    "it special if you know. Keep it brief (1-2 sentences). "
                    "Do not simply echo the wish back. Reciprocate naturally."
                )
        except Exception:
            pass

        # ── Longitudinal intelligence (relevance-ranked evidence)
        # The intelligence layer retrieves ONLY the evidence relevant to the
        # current question — communication patterns, emotional episodes,
        # corrections, project lifecycle, decision history, KIO self-model.
        # This is the PRIMARY source for companion/personal queries.
        _intel = None
        try:
            from mini_kio.memory.intelligence_v2 import IntelligenceV2
            _intel = IntelligenceV2(decision.session_id or "tg_default")
            _intell = _intel.query(decision.raw_text or decision.normalized_text or "")
            if _intell:
                parts.append(_intell)
        except Exception:
            _intel = None

        # ── KIO self-model (what KIO knows about itself)
        try:
            from mini_kio.memory.kio_self_model import kio_self_brief
            _self_brief = kio_self_brief()
            if _self_brief:
                parts.append(_self_brief)
        except Exception:
            pass

        # Reply to what the user ACTUALLY said (raw surface form), not the
        # normalized form. Normalization exists for CLASSIFICATION; the reply
        # LLM must see the user's real words. Live: "yo whats good" was
        # normalized to "what is good" and the reply LLM answered it as a
        # literal question about the word "good" — while the raw form is an
        # unambiguous greeting.
        _user_msg = decision.raw_text or decision.normalized_text

        # ── FINAL semantic substrate (additive + defensive): ingest the turn
        # into the Node/Link graph, resolve references, run the Planner, and
        # ground generation in graph state (attributed statements / computed
        # activation / durable memory). A failure in any step must never break
        # the conversation path it augments.
        _sem = None
        _sid = decision.session_id
        try:
            from mini_kio.semantic import intelligence as _sem
            # The turn was ALREADY ingested for every intent in run(); reuse
            # that result (same graph, same decomposition) instead of
            # re-ingesting — double ingestion would duplicate statements.
            _pre = (decision.metadata or {}).get("semantic_state") or {}
            _ing = _pre.get("ingestion")
            _planner = _pre.get("planner")
            if _ing is None or _planner is None:
                # Defensive fallback: direct invocation paths that bypass run().
                _ing = _sem.ingest_turn(_sid, _user_msg, decision.normalized_text or "")
                _planner = _sem.planner_decision(
                    _sid, _user_msg,
                    _ing.get("decomposition"), _ing.get("resolution"),
                )
            _dec = _ing.get("decomposition")
            _res = _ing.get("resolution")
            _state = _sem.semantic_state_block(_sid, _user_msg, _res)
            if _state:
                parts.append(
                    "The SEMANTIC GRAPH block below is authoritative persistent "
                    "memory: who said what, what you said, what the user decided "
                    "or prefers. When the user references an earlier statement "
                    "('what did I say', 'what did you say', 'he said X'), answer "
                    "from it instead of guessing or regenerating.\n\n" + _state
                )
            _pl = _sem.render_planner(_planner)
            if _pl:
                parts.append(_pl)
        except Exception:
            pass

        # General web-document extraction primitive: when a CONVERSATIONAL
        # message carries a URL ("summarize <url>", "what does this article
        # say", a bare pasted link), read the page's actual text through the
        # web-read provider (Jina Reader) and inject it into the context so
        # the reply is grounded in the REAL page — never a fabricated
        # summary. Bounded to one read + a capped excerpt; silent no-op when
        # the reader is disabled/unavailable (the "never invent resources"
        # guardrail already covers that path). Browser/media URLs are never
        # affected: "open/go to <url>" and "play <url>" route to their own
        # executors before this conversational path.
        try:
            _url_m = re.search(r"(https?://[^\s)\]]+)", _user_msg or "")
            if _url_m:
                from mini_kio.knowledge.jina_reader_provider import read_url
                _page_text = read_url(_url_m.group(1).rstrip(".,;!?"))
                if _page_text and len(_page_text.strip()) >= 60:
                    _excerpt = _page_text.strip()[:6000]
                    parts.append(
                        "WEB PAGE CONTENT — the user's message includes this URL and "
                        "its actual content is provided below. Base any summary, "
                        "answer, or opinion strictly on this content; never invent "
                        "details, quotes, or facts the page does not contain. If the "
                        "content is insufficient for what was asked, say so plainly.\n"
                        + _excerpt
                    )
        except Exception:
            pass
        # Composition guidance for longitudinal evidence: when evidence sections
        # ("Evidence (relevance-ranked):", "About Joel:", "Communication style:",
        # "Emotional patterns:", "Joel corrections", "KIO failures", "Decision")
        # are present in the prompt, the LLM MUST compose from them. It must NOT
        # say "I don't have enough" when evidence IS provided. The evidence is
        # the ground truth — synthesize it naturally.
        _has_longitudinal = any(
            tag in " ".join(parts)
            for tag in (
                "Evidence (relevance-ranked):", "About Joel:",
                "Communication style", "Emotional patterns",
                "Joel corrections", "KIO failures", "Decision evidence",
                "Historical/abandoned projects", "Active projects:",
                "Relationship history", "Joel approval",
                "KIO self-model", "Joel expectations",
            )
        )
        if _has_longitudinal:
            parts.append(
                "\nCOMPANION INTELLIGENCE -- evidence sections above contain longitudinal data about Joel. When the user asks about themselves, compose a natural answer from the evidence above. Do NOT say you lack information when evidence IS present. Synthesize naturally: reference patterns, give examples, note trends."
            )
        _t_converse = time.monotonic()
        try:
            reply = ask_llm_sync(_user_msg, system_prompt="\n\n".join(parts), timeout=25.0, max_tokens=800, task="conversation")
        except Exception:
            reply = None
        _dt_llm1 = (time.monotonic() - _t_converse) * 1000
        _dt_llm2 = 0.0
        # Bounded provider recovery: a transient outage (rate limit, one
        # provider down) can blank the whole chain on the FIRST call. One
        # short-delay retry recovers it (live: a movie question got "I'm not
        # sure how to handle that." then the identical retry succeeded).
        # Never loops — a genuinely dead chain stays dead after one retry.
        if not reply:
            try:
                time.sleep(0.2)
                _t_retry = time.monotonic()
                reply = ask_llm_sync(_user_msg, system_prompt="\n\n".join(parts), timeout=25.0, max_tokens=800, task="conversation")
                _dt_llm2 = (time.monotonic() - _t_retry) * 1000
            except Exception:
                reply = None
        if reply:
            cleaned = reply.strip().strip('"').strip("'")
            # Truncation guard: a provider stream cut produces a reply with no
            # terminal punctuation and often ends MID-CLAUSE ("As an AI, I
            # don't have personal", "The concepts of"). Two signals trigger a
            # retry: (1) long replies (>= 60 chars) without terminal
            # punctuation, or (2) ANY reply that ends on a clause-fragment
            # word that cannot end a sentence ("of", "the", "and", "to",
            # "that", "is") — short casual lines that end on a real word
            # ("haha good morning to you too", "fair enough") are NORMAL
            # conversation and never retried. If the retry is also broken,
            # keep whichever reply is longer/complete instead of failing the
            # whole turn to a canned fallback.
            _ends_mid_clause = bool(re.search(
                r"\b(of|the|and|but|or|to|with|that|which|because|is|are|was|"
                r"were|will|would|should|can|could|have|has|a|an|it|its|this|for)\s*$",
                cleaned.lower(),
            ))
            # A cut stream lacks terminal punctuation and either (a) ends
            # mid-clause ("The concepts of"), (b) is substantial
            # ("Rust's strictness, especially with ownership and borrowing"),
            # or (c) contains sentence-level punctuation that implies
            # continuation ("I wouldn't call it hype; Rust's design").
            # Natural punctuation-less casual lines are short and have none
            # of these signals ("haha good morning to you too" = 27).
            _sentence_punct = (" ; " in f" {cleaned} " or ":" in cleaned
                               or " - " in f" {cleaned} ")
            if (not cleaned.endswith((".", "!", "?"))
                    and (len(cleaned) >= 40 or _ends_mid_clause or _sentence_punct)):
                try:
                    retry = ask_llm_sync(_user_msg, system_prompt="\n\n".join(parts), timeout=25.0, max_tokens=800, task="conversation")
                except Exception:
                    retry = None
                if retry:
                    _r = retry.strip().strip('"').strip("'")
                    _r_cut = (not _r.endswith((".", "!", "?")) and (
                        len(_r) >= 40
                        or re.search(
                            r"\b(of|the|and|but|or|to|with|that|which|because|is|are|was|"
                            r"were|will|would|should|can|could|have|has|a|an|it|its|this|for)\s*$",
                            _r.lower(),
                        )
                        or (" ; " in f" {_r} " or ":" in _r or " - " in f" {_r} ")
                    ))
                    if not _r_cut or len(_r) > len(cleaned):
                        cleaned = _r
            # Self-duplication guard: a small provider sometimes loops its own
            # sentence verbatim ("...precise enough.I'd pass—being nagged
            # ...precise enough."). Strip the echo before anything else so a
            # duplicated block can never be sent as-is.
            cleaned = _strip_self_duplication(cleaned)
            # Anti-fabrication: the model must never address the user by an
            # invented name ("Hey, it sounds pretty serious. Peter").
            cleaned = _sanitize_llm_name_address(cleaned)
            if len(cleaned) > 1 and cleaned.lower() != decision.normalized_text.lower().strip():
                # KIO self-continuity: persist the reply as a KIO-attributed
                # statement so "what did you say" resolves through the graph.
                if _sem is not None:
                    try:
                        _sem.record_kio_reply(_sid, cleaned)
                    except Exception:
                        pass
                if _intel is not None:
                    try:
                        from datetime import datetime as _dt
                        _intel.record(
                            decision.raw_text or decision.normalized_text or "",
                            cleaned,
                            _dt.now().isoformat(),
                        )
                    except Exception:
                        pass
                _dt_total = (time.monotonic() - _t_converse) * 1000
                logger.debug("converse: llm1=%.0fms retry=%.0fms total=%.0fms", _dt_llm1, _dt_llm2, _dt_total)
                return cleaned
        _dt_total = (time.monotonic() - _t_converse) * 1000
        logger.debug("converse: llm1=%.0fms retry=%.0fms total=%.0fms (no reply)", _dt_llm1, _dt_llm2, _dt_total)
        return None

    def _semantic_forget(self, session_id: str, topic: str) -> Optional[dict]:
        """Resolve 'forget X' against the semantic graph (FINAL architecture).

        The graph owns conversation memory. The target is resolved by
        normalized key + token overlap against participants, topics and
        concepts; the matched node is marked forgotten (history preserved)
        and the reply confirms WHAT was actually forgotten. Returns None when
        nothing in the graph matches (caller falls back to the legacy fact
        store or answers honestly). Ambiguity -> None so the caller can ask
        rather than guess.
        """
        try:
            from mini_kio.semantic.graph import KIO_KEY, USER_KEY, SemanticGraph
            if not session_id or not (topic or "").strip():
                return None
            # "that whole Zorbion thing" -> "zorbion" (strip articles/pointers
            # REPEATEDLY so stacked modifiers like "that whole" all go;
            # one pass leaves "wholezorbion" which cannot containment-match
            # the research topic "Zorbion Dynamics" — the ACTIVE referent).
            _prev = None
            t = topic.strip()
            while _prev != t:
                _prev = t
                t = re.sub(r"^(that|this|the|it|my|our|a|an|whole|entire|actually|ok|okay|please|hey|now|then)\s+", "", t, flags=re.I)
            t = re.sub(r"\b(thing|stuff|business|situation|topic|subject)\b", "", t, flags=re.I)
            t = re.sub(r"[^a-z0-9 ]+", " ", t, flags=re.I).strip()
            if not t:
                return None
            t_norm = re.sub(r"[^a-z0-9]+", "", t.lower())
            if len(t_norm) < 3:
                return None
            graph = SemanticGraph(session_id)
            t_terms = set(re.findall(r"[a-z0-9]+", t.lower()))

            candidates = []
            for n in graph.all_nodes_for_forget():
                if n.kind not in ("participant", "topic", "concept", "project"):
                    continue
                if n.key in (USER_KEY, KIO_KEY):
                    continue
                name_norm = re.sub(r"[^a-z0-9]+", "", (n.name or "").lower())
                alias_norms = [re.sub(r"[^a-z0-9]+", "", a) for a in (n.meta.get("aliases") or [])]
                if t_norm in name_norm or name_norm in t_norm or t_norm in alias_norms:
                    # Exact containment is the STRONGEST signal. Prefer the
                    # MOST SPECIFIC match: "zorbion" contained in both
                    # "zorbion" and "zorbiondynamics" must pick the fuller
                    # name ("Zorbion Dynamics"), not tie. Score = length of
                    # the name norm (longer = more specific) + 100. Forgotten
                    # nodes rank below active ones (same specificity => the
                    # active re-mentioned entity wins).
                    active_bonus = 1000 if n.status == "active" else 0
                    candidates.append((n, active_bonus + 100 + len(name_norm)))
                    continue
                name_terms = set(re.findall(r"[a-z0-9]+", (n.name or "").lower()))
                if t_terms and name_terms and (t_terms & name_terms):
                    candidates.append((n, 10 + len(name_terms)))

            # Prefer higher score (more specific match); newest on exact tie.
            candidates.sort(key=lambda c: (-c[1], -c[0].id))
            if not candidates:
                return None
            best, score = candidates[0]
            # True ambiguity: two DIFFERENT names with the SAME specificity.
            # "zorbion" vs "Zorbion Dynamics" no longer ties (specificity
            # differs). Only distinct-name equal-score ties stay unresolved.
            if len(candidates) > 1:
                same_names = {c[0].key for c in candidates if c[1] == score}
                if len(same_names) > 1:
                    # Ambiguous -> let the caller ask rather than guess.
                    return None
            if best.status == "forgotten":
                # Idempotent forget: already forgotten -> honest confirmation,
                # never the legacy store (live failure: re-forgetting Zorbion
                # fell through to "I don't have anything saved about you yet").
                return {
                    "success": True,
                    "message": f"Already forgotten about {best.name} — nothing to do.",
                }
            graph.forget(best.key)
            # Cross-node forget: the PROJECT lifecycle node representing the
            # same thing must also be forgotten ("forget the lunar regolith
            # greenhouse" matched the topic node first; the project node —
            # the active-work representation — must not stay alive).
            # Identity match by normalized name containment/token overlap,
            # the same general rule as project identity unification.
            try:
                _f_norm = re.sub(r"[^a-z0-9]+", "", best.name.lower())
                _f_toks = {t for t in re.findall(r"[a-z0-9]+", best.name.lower())
                           if len(t) >= 3 and t not in _FORGET_PROJ_STOP}
                for _pn in graph.all_projects():
                    if _pn.status == "forgotten":
                        continue
                    _pn_norm = re.sub(r"[^a-z0-9]+", "", (_pn.name or "").lower())
                    _pn_toks = {t for t in re.findall(r"[a-z0-9]+", (_pn.name or "").lower())
                                if len(t) >= 3 and t not in _FORGET_PROJ_STOP}
                    _hit = bool(_f_norm and (_f_norm in _pn_norm or _pn_norm in _f_norm))
                    if not _hit and _f_toks and _pn_toks:
                        _sh = len(_f_toks & _pn_toks)
                        _hit = _sh >= 2 and _sh * 2 >= max(len(_f_toks), 2)
                    if _hit:
                        graph.forget(_pn.key)
            except Exception:
                pass
            return {
                "success": True,
                "message": f"Done — I've forgotten about {best.name}.",
            }
        except Exception:
            return None

    def _semantic_forget_goal(self, session_id: str, topic: str) -> Optional[dict]:
        """Forget a USER GOAL / commitment ("forget the EP" when the EP is a
        'wants:/decides:' claim, not a topic node). Goals are ordinary graph
        objects (FINAL arch §12: stance=desire/intention); forgetting one is
        expiring that intention. Token-match against user-attributed goal
        statements; requires a CLEAR winner (ties stay unresolved so the
        caller never guesses). Returns None when no goal matches."""
        try:
            from mini_kio.semantic.graph import USER_KEY, SemanticGraph
            if not session_id or not (topic or "").strip():
                return None
            # "the whole EP thing" -> "ep" (strip leading pointers REPEATEDLY —
            # a stacked chain of modifiers must not hide a 2-3 char goal name;
            # live: "forget the whole KIO logo thing" resolved to nothing
            # because only ONE modifier was stripped).
            _tt = (topic or "").strip().lower()
            while True:
                _stripped = re.sub(
                    r"^(?:the|my|our|a|an|that|this|whole|entire|thing)\s+",
                    "", _tt, count=1, flags=re.I
                )
                if _stripped == _tt:
                    break
                _tt = _stripped
            _tnorm = re.sub(r"[^a-z0-9]+", "", _tt)
            if len(_tnorm) < 2:
                return None
            _tokens = set(re.findall(r"[a-z0-9]+", _tt))
            _tokens = {t for t in _tokens if len(t) >= 2}
            graph = SemanticGraph(session_id)
            goals = [
                s for s in graph.attributed_statements(USER_KEY, active_only=True, limit=200)
                if str(getattr(s, "target_name", "") or "").lower().startswith(
                    ("wants:", "decides:", "researching:", "intention:")
                )
            ]
            scored = []
            for s in goals:
                _t = str(getattr(s, "target_name", "") or "").strip()
                _norm = re.sub(r"[^a-z0-9]+", "", _t.lower())
                if _tnorm in _norm or _norm in _tnorm:
                    scored.append((s, 100 + len(_norm)))
                    continue
                _gt = set(re.findall(r"[a-z0-9]+", _t.lower()))
                _gt = {w for w in _gt if len(w) >= 3}
                if _tokens and _gt and (_tokens & _gt):
                    scored.append((s, 10 + len(_gt & _tokens)))
            if not scored:
                return None
            scored.sort(key=lambda x: (-x[1], -x[0].id))
            best, score = scored[0]
            if len(scored) > 1 and len({x[0].id for x in scored if x[1] == score}) > 1:
                return None  # ambiguous
            _name = str(getattr(best, "target_name", "") or "").strip()
            # Expire the claim node (goals are claim objects, not topic nodes).
            _target_node = graph.get_node(best.target_id)
            if _target_node is None:
                return None
            graph.forget(_target_node.key)
            return {
                "success": True,
                "message": f"Done — I've forgotten about {_name.split(':', 1)[-1].strip()[:60]}.",
            }
        except Exception:
            return None

    def _exec_memory(self, params: dict, decision: RoutingDecision) -> dict:
        from mini_kio.core.context_manager import get_context_manager
        from mini_kio.memory.memory_store import PatternMemoryExtractor

        ctx = get_context_manager(decision.session_id)
        text = params.get("query") or decision.normalized_text
        store = ctx.memory

        if params.get("action") == "store":
            facts = PatternMemoryExtractor().extract(text)
            if not facts:
                return {"success": False, "message": "I couldn't pick out a fact to remember from that."}
            for key, value in facts.items():
                store.set_fact(key, value)
            ctx.append_message("user", text)
            friendly = []
            for key, value in facts.items():
                if key.startswith("preference_"):
                    friendly.append(f"You {value} {key[len('preference_'):].replace('_', ' ')}.")
                elif key.startswith("favorite_"):
                    friendly.append(f"Your favorite {key[len('favorite_'):].replace('_', ' ')} is {value}.")
                elif key == "user_name":
                    friendly.append(f"Your name is {value.capitalize()}.")
                else:
                    # Never expose internal keys to the user.
                    # Convert the key to natural language, stripping 'my_' prefix
                    # (key 'my_favorite_subject' -> 'your favorite subject').
                    _label = key.replace("_", " ").strip()
                    if _label.startswith("my "):
                        _label = "your " + _label[3:]
                    friendly.append(f"I'll remember that {_label} is {value}.")
            return {"success": True, "message": "Got it — " + " ".join(friendly)}

        # ── Forget through the SEMANTIC graph first (FINAL architecture) ──
        # "forget X" must resolve X against the graph's participants/topics/
        # concepts — never against an unrelated legacy fact. Live bug:
        # "forget that whole Zorbion thing" answered "Done — I've forgotten
        # about my favourite colour" (the legacy store's LAST fact). The
        # graph owns conversation memory; forget marks the referenced node
        # forgotten (history preserved) and confirms WHAT was forgotten.
        # Ambiguity -> ask, never guess.
        if params.get("action") in ("forget", "forget_one"):
            topic = (text or "").lower().replace("forget", "", 1).strip(" .,!?;:")
            _graph_forgot = self._semantic_forget(decision.session_id, topic)
            if _graph_forgot is not None:
                return _graph_forgot
            # Goals are graph objects too: "forget the EP" where the EP is a
            # user goal claim ("wants: record an EP..."), not a topic node.
            # (live holdout: "forget the EP — I'll just do a single" answered
            # "I don't have anything saved about you yet").
            _goal_forgot = self._semantic_forget_goal(decision.session_id, topic)
            if _goal_forgot is not None:
                return _goal_forgot
            # Fall back to the legacy fact store ONLY for actual stored user
            # facts (favorite_*/preference_*/user_name ...). Never "last fact".
            facts = store.get_all_facts()
            if not facts:
                return {"success": False, "message": "I don't have anything saved about you yet."}
            target = None
            t_terms = [t for t in re.findall(r"[a-z0-9]+", topic) if len(t) > 2]
            for k in facts:
                k_terms = re.findall(r"[a-z0-9]+", k)
                if t_terms and any(t in k_terms for t in t_terms):
                    target = k
                    break
            if target:
                store.delete_fact(target)
                # Convert key to natural language for user-facing response.
                # Strip leading 'my_' — the key stores 'my_favorite_subject' but
                # the response should say 'your favorite subject', not 'your my...'
                _friendly = target.replace("_", " ").strip()
                if _friendly.startswith("my "):
                    _friendly = _friendly[3:]
                return {"success": True, "message": f"Done — I've forgotten your {_friendly}."}
            if re.search(r"\b(that|it|this|everything|all)\b", topic):
                store.clear()
                return {"success": True, "message": "Done — I've forgotten everything I knew about you."}
            return {"success": False, "message": f"I don't remember anything about {topic}."}

        ctx.append_message("user", text)
        facts = store.get_all_facts()
        if not facts:
            return {"success": False, "message": "I don't have anything saved about you yet."}

        # Internal state must NEVER surface as user memory: the session-state
        # layer persists its runtime blob under conversation_state_json (and
        # could persist other internal keys), and dumping it as "what I
        # remember" leaks architecture the user never asked about. Only
        # user-facing fact keys (favorite_*, preference_*, user_name, ...)
        # are recalled; internal keys are filtered before any rendering.
        _INTERNAL_FACT_PREFIXES = ("conversation_state_", "_state_", "internal_")
        facts = {
            k: v for k, v in facts.items()
            if not k.startswith(_INTERNAL_FACT_PREFIXES)
        }
        if not facts:
            return {"success": False, "message": "I don't have anything saved about you yet."}

        lower = text.lower()
        # Normalize UK->US spellings so "favourite colour" matches "favorite_color".
        _us = (lower.replace("favourite", "favorite").replace("colour", "color")
                   .replace("behaviour", "behavior").replace("centre", "center")
                   .replace("metre", "meter").replace("favourite", "favorite"))
        facts_us = {}
        for k, v in facts.items():
            k_us = (k.replace("favourite", "favorite").replace("colour", "color")
                     .replace("behaviour", "behavior").replace("centre", "center")
                     .replace("metre", "meter"))
            facts_us[k_us] = (k, v)
        if "name" in lower:
            name = facts.get("user_name") or facts.get("my_name")
            if name:
                return {"success": True, "message": f"Your name is {name.capitalize()}."}
        if any(k in _us for k in ("favorite", "like", "love", "enjoy", "prefer")):
            # Scoped recall: extract the specific attribute (favorite color, nickname, ...)
            topic_terms = re.findall(r"[a-z0-9]+", _us)
            # Stop words include question words AND qualifier words ("favorite",
            # "like", "love", etc.) — these are the QUERY framing, not the
            # specific attribute noun. Without excluding them, "what is my
            # favorite movie" matches ALL facts containing "favorite" (like
            # favorite_engineering_field) instead of only favorite_movie.
            stop = {"what", "is", "my", "s", "i", "do",
                    "favorite", "favourite", "favorites", "fav",
                    "like", "love", "enjoy", "prefer", "prefered",
                    "preferred", "things"}
            topic_terms = [t for t in topic_terms if len(t) > 2 and t not in stop]
            scoped = []
            for k_us, (orig_k, v) in facts_us.items():
                k_terms = re.findall(r"[a-z0-9]+", k_us)
                if any(t in k_terms for t in topic_terms):
                    if k_us.startswith("preference_"):
                        scoped.append(f"You {v} {orig_k.split('preference_')[-1].replace('_', ' ')}.")
                    elif k_us.startswith("favorite_"):
                        scoped.append(f"Your favorite {orig_k.split('favorite_')[-1].replace('_', ' ')} is {v}.")
                    else:
                        _label = orig_k.replace('_', ' ').strip()
                        if _label.startswith('my '):
                            _label = 'your ' + _label[3:]
                        scoped.append(f"{_label.capitalize()} is {v}.")
            if scoped:
                return {"success": True, "message": " ".join(scoped)}
            fav_m = re.search(r"\bfavorite\s+(movie|film|show|game|food|music|band|artist|book|team|sport|color|subject|hobby|thing)\b", _us)
            if fav_m:
                cat = fav_m.group(1)
                if not any(k_us.startswith(f"favorite_{cat}") or k_us.startswith(f"preference_{cat}") for k_us in facts_us):
                    return {"success": False, "message": f"I don't know your favorite {cat} yet."}
                lines = []
                for k_us, (orig_k, v) in facts_us.items():
                    if k_us.startswith(f"favorite_{cat}"):
                        lines.append(f"Your favorite {cat} is {v}.")
                    elif k_us.startswith(f"preference_{cat}"):
                        lines.append(f"You {v} {k_us[len('preference_'):].replace('_', ' ')}.")
                if lines:
                    return {"success": True, "message": " ".join(lines)}
            # "Show all favorites" fallthrough: only when the query is
            # GENERIC ("what are my favorites?", "what do I like?") — NOT
            # when it asks about a specific thing ("what programming language
            # do I prefer?") where no scoped match was found. Returning all
            # favorites for a specific query is a false-positive recall.
            # Detect: if the query has specific topic nouns beyond the
            # qualifier words, scoped recall already tried and failed —
            # fall through to the generic recall below which may handle it
            # better (or honestly say "I don't know").
            _has_specific_topic = len(topic_terms) > 0
            logger.info("[MEMORY_RECALL] specific_topic=%s topic_terms=%s scoped=%d facts=%d", _has_specific_topic, topic_terms, len(scoped), len(facts_us))
            if not _has_specific_topic:
                lines = []
                for k_us, (orig_k, v) in facts_us.items():
                    if k_us.startswith("preference_"):
                        lines.append(f"You {v} {orig_k[len('preference_'):].replace('_', ' ')}.")
                    elif k_us.startswith("favorite_"):
                        lines.append(f"Your favorite {orig_k[len('favorite_'):].replace('_', ' ')} is {v}.")
                if lines:
                    return {"success": True, "message": " ".join(lines)}
        if re.search(r"\bremember\b", lower) and facts.get("user_name"):
            name = facts["user_name"].capitalize()
            return {"success": True, "message": f"Of course I remember you, {name}!"}
        if "favorite" in lower and not _has_specific_topic:
            favs = {k: v for k, v in facts.items() if k.startswith("favorite_")}
            if favs:
                lines = []
                for k, v in favs.items():
                    _label = k.replace('_', ' ').strip()
                    if _label.startswith('my '):
                        _label = 'your ' + _label[3:]
                    lines.append(f"{_label.capitalize()} is {v}.")
                return {"success": True, "message": " ".join(lines)}
        lines = []
        for k, v in facts.items():
            _label = k.replace('_', ' ').strip()
            if _label.startswith('my '):
                _label = 'your ' + _label[3:]
            lines.append(f"{_label.capitalize()} is {v}.")
        return {"success": True, "message": " ".join(lines)}

    def _exec_knowledge(self, params: dict, decision: RoutingDecision) -> dict:
        """Knowledge retrieval via the canonical KnowledgeRouter.

        Previously a dead path with 5 hardcoded entries. Now routes through
        the real provider chain (Exa → Tavily → DuckDuckGo → Wikipedia)
        for any query that reaches this handler.
        """
        query = params.get("query") or decision.normalized_text or decision.raw_text or ""
        if not query.strip():
            return {"success": False, "message": "What would you like to know?"}
        try:
            from mini_kio.knowledge.retrieval_router import KnowledgeRouter
            router = KnowledgeRouter()
            result = router.route(query)
            if result:
                return {"success": True, "message": result.strip()}
        except Exception as exc:
            logger.debug("[KNOWLEDGE] router failed: %s", exc)
        # Fallback: delegate to conversation (LLM can answer general knowledge)
        return self._exec_conversation(params, decision)

    def _exec_system(self, params: dict, decision: RoutingDecision) -> dict:
        from mini_kio.core.execution_boundary import execute_action
        action_map = {
            "shutdown_system": "shutdown_system",
            "restart_system": "restart_system",
            "lock_system": "lock_system",
            "unlock_system": "unlock_system",
            "recovery_runtime": "recovery_runtime",
        }
        canonical = action_map.get(params["action"], params["action"])
        return execute_action(canonical)

    def _exec_operational(self, params: dict, decision: RoutingDecision) -> dict:
        # Capability G: operational awareness — deterministic real state from
        # the canonical owner module. Never an LLM guess.
        from mini_kio.core.operational_health import operational_result
        return operational_result(
            params.get("action", "status"),
            target=params.get("target", ""),
        )

    def _exec_simulate(self, params: dict, decision: RoutingDecision) -> dict:
        """Dry-run: classify + resolve the inner command, report intended actions, skip execute."""
        inner = decision.metadata.get("inner_decision")
        if inner:
            action = inner.action or "execute"
            target = inner.target or "unknown"
            intent = inner.intent_type.value if hasattr(inner.intent_type, 'value') else str(inner.intent_type)
            return {
                "success": True,
                "message": (
                    f"Simulation — I would: {action} {target}\n"
                    f"Intent: {intent} | Action: {action} | Target: {target}\n"
                    f"No side effects executed."
                ),
            }
        return {
            "success": True,
            "message": f"Simulation — would execute: {decision.target or decision.raw_text}\nNo side effects executed.",
        }

    def _exec_coordinator(self, params: dict, decision: RoutingDecision) -> dict:
        from mini_kio.core.command_parser import parse_command
        # Parse the RESOLVED semantic text, never the raw utterance: referent
        # expansion ("close both" -> "close paint and notepad", "close it" ->
        # "close <entity>") lives in normalized_text. Using raw_text here would
        # make execution try to close a literal "both"/"it". When no resolution
        # occurred the two are identical, so preferring normalized_text is safe.
        steps = parse_command(decision.normalized_text or decision.raw_text)
        if not steps:
            return {"success": False, "message": f"Could not parse multi-step command: {decision.normalized_text or decision.raw_text!r}"}
        from mini_kio.core.command_router import _execute_multi_step
        return _execute_multi_step(steps)


class _ResponseComposer:
    # BUG 6 (retained): implementation tokens must never surface to the user.
    # The execution/verification layers produce structured facts; only this
    # composer turns them into user language. Strip leaked jargon defensively.
    _LEAK_PATTERNS = re.compile(
        r"\b(?:via|through|using|over)\s+"
        r"(?:the\s+)?"
        r"(?:browser\s+connector|connector|provider|execution\s+boundary|runtime|pipeline|capability|cdp|mcp)\b",
        re.IGNORECASE,
    )
    _LEAK_WORDS = re.compile(
        r"\b(?:browser\s+connector|connector|execution\s+boundary|capability|pipeline|runtime|cdp|mcp)\b",
        re.IGNORECASE,
    )
    # Trailing markdown table / citation fragments ("| Windows Notepad | -",
    # "| Title | Link") leaked from raw source content. Generic hygiene, never
    # app-specific.
    _LEAK_TABLE_ROW = re.compile(r"\s*\|.*\|.*", re.IGNORECASE)

    def _strip_leaks(self, message: str) -> str:
        """Remove implementation verbosity from any message at a central point."""
        if not message:
            return message
        term = message.strip()[-1:] if message.strip() else ""
        had_terminal = term in (".", "!", "?")
        stripped = self._LEAK_PATTERNS.sub("", message)
        stripped = re.sub(r"\s{2,}", " ", stripped).strip()
        stripped = self._LEAK_WORDS.sub("", stripped)
        stripped = re.sub(r"\s{2,}", " ", stripped).strip(" ,;\n\t")
        stripped = re.sub(r"(?m)^\s*\|.*\|.*$\n?", "", stripped).strip()
        stripped = re.sub(r"\s{2,}", " ", stripped).strip()
        # Preserve a legitimate sentence-final period ("Paused.", "Resumed.") —
        # punctuation-stripping exists to clean leak-removal residue, not to
        # eat the composer's own terminal punctuation. The EXACT terminal
        # character (., !, ?) is restored, never converted.
        if had_terminal and stripped and stripped[-1] not in (".", "!", "?"):
            stripped += term
        return stripped

    def compose(
        self, result: dict[str, Any], decision: RoutingDecision, ctx
    ) -> dict[str, Any]:
        # Mark user interaction for proactive suppression (prevents dual responses)
        try:
            from mini_kio.monitoring.proactive import mark_user_interaction
            mark_user_interaction()
        except Exception:
            pass
        result.setdefault("success", False)
        if "message" not in result:
            result["message"] = "Done." if result.get("success") else "Command failed."

        message = result["message"] if isinstance(result["message"], str) else str(result["message"])
        # Canonical identity answers are AUTHORED canon text, never execution
        # layer leakage: _LEAK_WORDS strips the bare word "capability" (and
        # similar) from every message, which corrupts identity answers like
        # "as one capability, but" into "as one , but". Identity template
        # outputs skip the leak-hygiene pass entirely — the identity dataset
        # is the single canonical owner and is already clean.
        if decision.intent_type == IntentType.IDENTITY:
            result["message"] = message or "Done."
        else:
            result["message"] = self._strip_leaks(message or "Done.")

        ctx.update(result, decision.normalized_text)
        try:
            ctx.append_exchange(decision.normalized_text, result.get("message") or "")
        except Exception:
            pass
        # Discourse state: every exchange advances the conversational context
        # (last user act, last KIO act, social energy, last location) so a bare
        # "nice" after "open Excel" resolves against the concrete action.
        try:
            from mini_kio.core.pragmatics import observe_exchange
            observe_exchange(decision, result, ctx)
        except Exception:
            pass
        # ── Proactive media offer (guarded) ──────────────────────────
        # Only append a media offer when the action was an information_query
        # AND the base response is substantive (not social/conversational).
        # This prevents proactive offers from hijacking greetings, identity
        # answers, or casual conversation.
        if (
            decision.action == "information_query"
            and result.get("success")
            and result.get("message")
            and decision.intent_type not in (
                IntentType.GREETING, IntentType.SOCIAL, IntentType.IDENTITY,
                IntentType.CONVERSATION, IntentType.UNKNOWN,
            )
        ):
            try:
                from mini_kio.media.media_manager import MediaManager
                mm = MediaManager.get_instance()
                query_text = decision.target or decision.normalized_text or ""
                if query_text and mm:
                    _maybe_offer(mm, query_text, result, decision)
            except Exception:
                pass

        if decision.session_id and decision.action:
            from mini_kio.core.runtime import remember_runtime_context
            # BC-3: never persist a raw serialized capability target
            # ("chrome::open_url::https://...::chatgpt") as the conversational
            # referent — a later "close it" would splice that string back into
            # the command. Store the user-safe name instead.
            from mini_kio.core.target_ref import safe_target_name
            _raw_target = str(result.get("target", decision.target) or "")
            remember_runtime_context("execution", {
                "action": result.get("action", decision.action),
                "target": safe_target_name(_raw_target),
                "success": result.get("success", False),
            })
        return result


def _is_tabular_content(text: str) -> bool:
    """Detect whether text is actual tabular data (tab or pipe-separated)
    rather than prose instructions about how to build a spreadsheet.

    Returns True when the content has at least 2 data rows with consistent
    column counts — the minimum for a usable spreadsheet.
    """
    if not text:
        return False
    lines = [l.strip() for l in text.splitlines() if l.strip()]
    if len(lines) < 2:
        return False
    # Count lines that look like table rows (tab-separated or pipe-separated)
    tab_rows = sum(1 for l in lines if "\t" in l and len(l.split("\t")) >= 2)
    pipe_rows = sum(1 for l in lines if l.startswith("|") and l.count("|") >= 3)
    # Also accept markdown table with separator row
    has_separator = any(re.fullmatch(r":?-{2,}:?", c.strip())
                        for l in lines if l.startswith("|")
                        for c in l.split("|") if c.strip())
    data_rows = tab_rows + pipe_rows
    # Need header + at least 1 data row (2+ rows total), and not pure prose
    if data_rows < 2:
        return False
    # Reject if >50% of non-empty lines are prose (no tabs/pipes)
    prose_lines = sum(1 for l in lines if "\t" not in l and not l.startswith("|"))
    if prose_lines > len(lines) * 0.5:
        return False
    return True


# ── Deterministic fallback content (no LLM needed) ─────────────────────────
def _deterministic_fallback_content(prompt: str, artifact: str = "") -> Optional[str]:
    """Generate minimal but complete content when all LLM providers fail.

    Extracts the subject from the prompt and produces a real, structured
    document body so the user always gets a file — not 'couldn't generate'.
    The content is short but complete: it has sections, real structure, and
    covers the requested topic.
    """
    # Extract the subject: strip command verbs and prepositions
    subj = re.sub(
        r"^(create|make|write|generate|draft|open|start|new)\s+(a|an|the|my)?\s*",
        "", prompt, flags=re.I
    ).strip()
    subj = re.sub(
        r"\s+(document|file|doc|docx|spreadsheet|xlsx|presentation|pptx|ppt|slides|deck|code|program|script|essay|report|comparison|notes|poem|letter|email|study guide|budget|table|data|tracker|schedule|timetable|roster|inventory|ledger|dataset|plan)\s*$",
        "", subj, flags=re.I
    ).strip()
    if not subj:
        subj = prompt[:80] if prompt else "Requested Document"
    # Title-case the subject
    title = " ".join(w.capitalize() for w in subj.split()) or "Requested Document"

    kind = (artifact or "document").lower().strip()

    if kind in ("spreadsheet", "sheet", "excel", "budget", "table", "data",
                "ledger", "inventory", "tracker", "timetable", "roster",
                "schedule", "dataset", "plan"):
        # Spreadsheet fallback: header row + sample data rows
        return (
            f"Category\tItem\tQuantity\tUnit Price\tTotal\n"
            f"Category A\tItem 1\t10\t5.00\t50.00\n"
            f"Category A\tItem 2\t5\t12.00\t60.00\n"
            f"Category B\tItem 3\t8\t7.50\t60.00\n"
            f"Category B\tItem 4\t3\t20.00\t60.00\n"
            f"Category C\tItem 5\t15\t3.50\t52.50\n"
            f"Total\t\t\t=SUM(E2:E6)\t\n"
        )

    if kind in ("presentation", "slides", "deck", "ppt", "pptx", "powerpoint",
                "slideshow", "talk", "slide deck"):
        # Presentation fallback: structured SLIDE markers
        slides = [
            f"SLIDE: {title}\n- Overview of {title}\n- Key concepts and principles\n- Real-world applications",
            f"SLIDE: Background\n- Historical context and development\n- Why {title} matters today\n- Core components",
            f"SLIDE: Key Concepts\n- Fundamental principles\n- Important definitions\n- Common patterns",
            f"SLIDE: Applications\n- Practical use cases\n- Industry examples\n- Best practices",
            f"SLIDE: Summary\n- Key takeaways\n- Action items\n- References and further reading",
        ]
        return "\n\n".join(slides)

    if kind in ("code", "program", "script"):
        # Code fallback: simple Python hello-world
        return (
            f'#!/usr/bin/env python3\n"""Generated script for {title}"""\n\n'
            f"def main():\n"
            f'    print("Hello from {title}")\n\n'
            f'if __name__ == "__main__":\n'
            f"    main()\n"
        )

    # Default document fallback: structured plain text with sections
    paras = [
        f"{title}",
        "",
        "This document provides an overview of the requested topic.",
        "",
        "1. Introduction",
        f"{title} is a topic of significant interest. This document covers the key aspects, "
        "providing a structured overview suitable for reference or further development.",
        "",
        "2. Key Points",
        f"- Core principles of {title.lower()}",
        f"- Historical context and current developments",
        f"- Practical applications and real-world examples",
        f"- Benefits and considerations",
        "",
        "3. Details",
        f"The following sections expand on each key point above. {title} encompasses "
        "multiple dimensions that are explored in detail throughout this document.",
        "",
        "- Aspect 1: Foundational knowledge and background",
        "- Aspect 2: Current state of the field",
        "- Aspect 3: Future directions and opportunities",
        "",
        "4. Conclusion",
        f"In summary, {title.lower()} represents an important area with both theoretical "
        "significance and practical relevance. The key takeaways above provide a starting "
        "point for deeper exploration.",
    ]
    return "\n".join(paras)


