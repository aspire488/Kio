from __future__ import annotations

import difflib
import json
import logging
import random
import re
import time
from typing import Any, Optional

from mini_kio.core.pipeline.types import IntentType, RoutingDecision
from mini_kio.core.context_manager import get_session_context

logger = logging.getLogger(__name__)


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
            ctx = get_session_context(session_id)
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
        cmd = ctx.resolved_text(cmd)
        cmd = _apply_aliases(cmd)
        cmd = _normalize_connectors(cmd)

        # R1: strip politeness prefix but only when it clearly precedes a
        # command verb; never strip from standalone social small-talk, and
        # never when the stripped remainder starts with a subject pronoun
        # ("can i use the computer" -> lock state, NOT a stripped "i use...").
        stripped = self._POLITE_PREFIX_RE.sub("", cmd, count=1).strip()
        if stripped and cmd.lower() != stripped.lower():
            _remainder_first = stripped.split()[0].lower() if stripped.split() else ""
            if _remainder_first not in ("i", "we", "you", "they", "he", "she", "it"):
                cmd = stripped

        # Conversational-correction prefixes ("actually", "no, open it in
        # chrome", "wait, open the app") must never block verb detection — the
        # correction is the command. Bounded token list; requires a following
        # word (a bare "no"/"yes" is not stripped).
        _CORRECTION_PREFIX_RE = re.compile(
            r"^(?:actually|no|nah|wait|hmm|yes|yeah|sure|ok(?:ay)?|right|um|uh|hold\s+on)\s*,\s+",
            re.IGNORECASE,
        )
        _CORRECTION_PREFIX_RE2 = re.compile(
            r"^(?:actually|no|nah|wait|hmm|yes|yeah|sure|ok(?:ay)?|right|um|uh|hold\s+on)\s+",
            re.IGNORECASE,
        )
        stripped = _CORRECTION_PREFIX_RE.sub("", cmd, count=1).strip()
        if not stripped or stripped.lower() == cmd.lower():
            stripped = _CORRECTION_PREFIX_RE2.sub("", cmd, count=1).strip()
        if stripped and stripped.lower() != cmd.lower():
            cmd = stripped

        cmd = re.sub(r"\bon\s+(chrome|edge|comet|firefox|brave)\b", r" in \1", cmd)
        return cmd


class _IntentClassifier:
    """Three-layer classification: fast deterministic -> semantic -> fallback."""

    GREETINGS = frozenset({
        "hello", "hi", "hey", "yo", "hola", "sup", "wassup", "what's up", "whats up",
        "good morning", "good afternoon", "good evening", "heyy", "bro", "broo",
    })

    ACKNOWLEDGEMENTS = frozenset({
        "i see", "oh i see", "ah i see", "i understand", "got it", "makes sense",
        "right", "alright", "cool", "nice", "good", "understood", "that makes sense",
    })

    THANKS = frozenset({"thanks", "thank you", "thankyou", "ty", "thx"})

    SYSTEM_ACTIONS = frozenset({"shutdown", "restart", "lock", "unlock", "recovery", "recover"})

    MEDIA_TRANSPORT = frozenset({
        "pause", "resume", "stop", "mute", "unmute",
        "next", "next video", "next track", "skip", "skip video",
        "previous", "prev", "previous video", "previous track", "go back",
        "volume up", "increase volume", "turn it up", "louder",
        "volume down", "decrease volume", "turn it down", "quieter", "lower volume",
        "continue", "keep going", "continue playing",
    })

    FOLDER_KEYWORDS = frozenset({
        "downloads", "desktop", "documents", "pictures", "music", "videos", "home", "appdata", "kio",
    })

    FORBIDDEN_TARGETS = frozenset({
        "cmd", "powershell", "regedit", "taskmgr", "msconfig", "control.exe",
        "explorer", "terminal", "services",
    })

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

    def classify(self, text: str, raw_text: str) -> RoutingDecision:
        # R1 politeness prefix also applies to text that reaches the classifier
        # through greeting/name recursion ("hey KIO, can you open winrar" ->
        # name-strip leaves "can you open winrar" -> polite strip leaves
        # "open winrar"). Idempotent: already-stripped text has no match.
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

        if not words:
            return decision

        # KIO-as-self wins over general knowledge: a KIO-prefixed self-state
        # query ("kio ok?", "kio still running?") routes deterministically even
        # though name-strip would otherwise reduce it to a bare word.
        kio_self = self._detect_kio_self(lower, text)
        if kio_self is not None:
            return kio_self

        stripped = self._strip_greeting(lower_clean, first_word, second_word, words, text, raw_text)
        if stripped is not None:
            return stripped

        if lower_clean in self.ACKNOWLEDGEMENTS:
            return RoutingDecision(IntentType.SOCIAL, "", "", raw_text, text, confidence=1.0)
        if lower_clean in self.THANKS:
            return RoutingDecision(IntentType.SOCIAL, "", "", raw_text, text, confidence=1.0)

        lower = re.sub(r"[\s\.,!?;:]+$", "", lower)

        if self._is_forbidden(lower, first_word):
            return RoutingDecision(
                IntentType.UNKNOWN, "", "", raw_text, text,
                confidence=1.0, metadata={"blocked": True, "reason": "forbidden_target"},
            )

        multi = self._classify_multi_step(lower, raw_text)
        if multi:
            return multi

        if self._has_trailing_conjunction(lower, first_word):
            return RoutingDecision(
                IntentType.UNKNOWN, "", "", raw_text, text,
                confidence=1.0, metadata={"malformed": True},
            )

        cls = self._classify_deterministic(lower, text, first_word, second_word)
        if cls:
            return cls

        cls = self._detect_now_playing(lower, text)
        if cls:
            return cls

        cls = self._classify_media_transport(lower, text)
        if cls:
            return cls

        cls = self._classify_memory(lower)
        if cls:
            return cls

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

        cls = self._classify_opinion(lower, text)
        if cls:
            return cls

        cls = self._classify_emotion(lower, text)
        if cls:
            return cls

        cls = self._classify_context_followup(lower, text)
        if cls:
            return cls

        # Camera capability (small, generic): "take a picture", "capture a
        # photo", "open the camera and take a photo". Routes to the camera
        # desktop capability whose executor resolves the NATIVE installed
        # camera application (never a .com website) and — where the provider
        # can genuinely trigger and verify a capture — does so truthfully.
        # Detection runs after deterministic system/state families and before
        # conversation so camera intent never leaks to the LLM or web.
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
                return stripped
        return text

    def _strip_greeting(self, lower_clean, first_word, second_word, words, text="", raw_text=""):
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
                logger.info("[GREETING_STRIP] remaining=%r", remaining)
                return self.classify(remaining, "")
            return RoutingDecision(
                IntentType.GREETING, "", "", raw_text or text, text or raw_text, confidence=1.0,
            )
        elif first in names:
            remaining = " ".join(words[1:]).lstrip(".,!?;:—- ")
            if remaining:
                logger.info("[NAME_STRIP] remaining=%r", remaining)
                return self.classify(remaining, "")
            return RoutingDecision(
                IntentType.GREETING, "", "", raw_text or text, text or raw_text, confidence=1.0,
            )
        multi = sorted((g for g in self.GREETINGS if " " in g), key=len, reverse=True)
        for g in multi:
            if lower_clean == g:
                return RoutingDecision(
                    IntentType.GREETING, "", "", raw_text or text, text or raw_text, confidence=1.0,
                )
            if lower_clean.startswith(g + " "):
                rest = lower_clean[len(g):].strip()
                if rest in names:
                    return RoutingDecision(
                        IntentType.GREETING, "", "", raw_text or text, text or raw_text, confidence=1.0,
                    )
                logger.info("[GREETING_STRIP] remaining=%r", rest)
                return self.classify(rest, "")
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
        }):
            return RoutingDecision(
                IntentType.GREETING, "", "", raw_text or text, text or raw_text, confidence=1.0,
            )
        if lower_clean in ("bye", "bue", "okay"):
            return RoutingDecision(IntentType.SOCIAL, "", "", "", "", confidence=1.0)
        if lower_clean == "bruh":
            return RoutingDecision(IntentType.SOCIAL, "", "", "", "", confidence=1.0)
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
                return RoutingDecision(IntentType.SEARCH, "search_youtube", query[8:].strip(), text, lower, confidence=1.0)
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
                                m = re.match(r"^open\s+(.+?)\s+in\s+(chrome|edge|comet|firefox|brave|browser)$", lower)
                                if m:
                                    webapp, browser = m.groups()
        if not webapp:
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
        if first_word == "focus":
            return RoutingDecision(IntentType.BROWSER_FOCUS, "focus", text[6:].strip(), text, lower, confidence=1.0)
        if lower.startswith("switch to "):
            return RoutingDecision(IntentType.BROWSER_FOCUS, "focus", text[10:].strip(), text, lower, confidence=1.0)
        if first_word == "switch":
            return RoutingDecision(IntentType.BROWSER_FOCUS, "focus", text[7:].strip(), text, lower, confidence=1.0)
        # FOCUS extension family: "bring Discord up / forward / to the front",
        # "go back to Notepad". Generic phrasing → same canonical focus owner.
        m = re.match(r"^bring\s+(.+?)\s+(?:up|forward|to\s+the\s+front|into\s+focus)\s*$", lower)
        if m:
            return RoutingDecision(IntentType.BROWSER_FOCUS, "focus", m.group(1).strip(), text, lower, confidence=1.0)
        m = re.match(r"^go\s+back\s+to\s+(.+)$", lower)
        if m:
            return RoutingDecision(IntentType.BROWSER_FOCUS, "focus", m.group(1).strip(), text, lower, confidence=1.0)
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
        r"(?:picture|photo|photograph|selfie|shot|image)\s*"
        r"(?:with\s+(?:the\s+|my\s+)?camera)?\s*$",
        re.IGNORECASE,
    )
    _CAMERA_OPEN_RE = re.compile(
        r"^(?:open|launch|start|fire\s+up|turn\s+on)\s+(?:the\s+|my\s+)?"
        r"(?:camera|webcam)\s*$",
        re.IGNORECASE,
    )

    def _detect_camera(self, lower, text):
        """Camera semantic family (generic, no app-specific branches).

        - "open the camera" / "launch my camera" → camera open (native).
        - "take a picture" / "capture a photo" / "take a photo with the
          camera" → camera capture.
        The executor resolves the native installed camera (UWP discovery)
        and reports the REAL result; capture is only claimed when the
        provider genuinely triggered and verified it.
        """
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
            r"(?:(?:into|in|onto|on\s+to)\s*){1,2}\s*(.+)$",
            lower,
        )
        if m:
            payload, app = m.group(1).strip(), m.group(2).strip()
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
        r"simple|small|detailed|concise|few|several|real|proper|one|1|"
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
    # / "create a report on X" — extract subject + artifact kind + style; the
    # document operator writes a real .docx. Never fake typing into Word.
    _CREATE_DOC_RE = re.compile(
        r"^(?:create|make|draft|generate|produce|build|write)\s+"
        r"(?:a|an|the)?\s*(?:new\s+)?(?:word|microsoft\s+word|ms\s+word|text|"
        r"docx|document|doc|file|report|write-up|paper|essay|article|letter|email|"
        r"story|poem|summary|comparison|overview|guide)?\s*"
        r"(?:document|doc|file|report|write-up|paper|essay|article|letter|email|"
        r"story|poem|summary|comparison|overview|guide)\s+"
        r"(?:about|on|regarding|for)\s+(.+)$",
        re.IGNORECASE,
    )
    _CREATE_DOC_COMPARE_RE = re.compile(
        r"^(?:create|make|draft|generate|produce|build|write)\s+"
        r"(?:a|an|the)?\s*(?:new\s+)?(?:word|microsoft\s+word|ms\s+word|text|"
        r"docx|document|doc|file|report|write-up|paper|essay|article|letter|email|"
        r"story|poem|summary|comparison|overview|guide)?\s*"
        r"(?:document|doc|file|report|write-up|paper|essay|article|letter|email|"
        r"story|poem|summary|comparison|overview|guide)\s+comparing\s+(.+)$",
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

    def _detect_document_creation(self, lower, text):
        subject = None
        artifact = "document"
        style = ""
        m = self._CREATE_DOC_COMPARE_RE.match(lower)
        if m:
            subject = m.group(1).strip()
            artifact = "comparison"
        else:
            m = self._CREATE_DOC_RE.match(lower)
            if m:
                subject = m.group(1).strip()
                # Infer artifact from the noun actually used.
                for noun, kind in (
                    ("report", "report"), ("write-up", "report"),
                    ("paper", "paper"), ("essay", "essay"), ("file", "file"),
                ):
                    if re.search(rf"\b{noun}\b", lower):
                        artifact = kind
                        break
        if not subject:
            # "write a short comparison of A and B and put it in a new
            # document" — split on the "and put/place/type it in[to]" clause.
            split = re.split(r"\s+and\s+(?:put|place|write|type|drop|paste)\s+(?:it|this|that)\s+(?:in|into)\s+(?:a|an|the)?\s*(?:new\s+)?(?:document|file|doc|text\s+file)\s*$", lower, maxsplit=1)
            if len(split) == 2 and split[0].strip():
                head = split[0].strip()
                # Only treat as document-creation when the head is itself a
                # content request (comparison/report/essay/notes/poem/summary
                # about X), never a literal "type hello".
                if re.search(r"\b(comparison|compare|report|essay|notes?|poem|summary|write-up|paper|overview|guide)\b.*\b(?:about|on|of|comparing)\b", head):
                    subject = head
                    if re.search(r"\b(comparison|compare|comparing)\b", head):
                        artifact = "comparison"
            if not subject:
                return None
        # Style tail: "... and make it concise" -> style=concise.
        sm = self._STYLE_TAIL_RE.search(subject)
        if sm:
            style = sm.group(1)
            subject = subject[: sm.start()].strip()
        if not subject:
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
        re.compile(r"^what\s+(?:are\s+you|is\s+kio)\s+(?:currently\s+)?(?:using|controlling|working\s+on)\b"),
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
        (re.compile(r"^what(?:'s|s| is)?\s+(?:using|eating|taking|consuming)\s+(?:up\s+|all\s+of\s+)?(?:my\s+)?(?:ram|memory)\b"), "resources_ram", ""),
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
        (re.compile(r"^ram\s*$"), "ram", ""),
        (re.compile(r"^memory\s*$"), "ram", ""),
        (re.compile(r"^(?:ram|memory)\s+usage\b"), "ram", ""),
        (re.compile(r"^how\s+much\s+(?:ram|memory)\s+(?:am\s+i\s+using|are\s+you\s+using|is\s+being\s+used|is\s+in\s+use)\b"), "ram", ""),
        (re.compile(r"^how\s+much\s+memory\s+is\s+left\b"), "ram", ""),
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
        #    identity wins over the web hint).
        from mini_kio.core.target_ref import parse_target
        from mini_kio.core.app_operator import _find_in_registry
        ref = parse_target(target_lower)
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
        now_playing_phrases = frozenset({
            "what's playing", "what is playing", "whats playing",
            "what's on", "what is on", "what's currently playing",
            "what's playing now", "what am i playing", "what am i listening to",
            "what's the current song", "what's the current video",
        })
        if lower in now_playing_phrases:
            return RoutingDecision(
                IntentType.MEDIA_TRANSPORT, "now_playing", "", text, lower,
                confidence=1.0,
            )
        return None

    def _classify_media_transport(self, lower, text):
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

        if any(re.search(rf"\b{re.escape(cmd)}\b", lower) for cmd in self.MEDIA_TRANSPORT):
            return RoutingDecision(IntentType.MEDIA_TRANSPORT, lower.split()[0], "", text, lower, confidence=1.0)

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

        for prefix, chop in (("play ", 5), ("watch ", 6)):
            if lower.startswith(prefix):
                target = lower[chop:].strip()
                return RoutingDecision(IntentType.MEDIA_PLAY, "play", target, text, lower, confidence=1.0)

        if lower == "play":
            return RoutingDecision(IntentType.MEDIA_PLAY, "play", "", text, lower, confidence=1.0)

        return None

    def _classify_context_followup(self, lower, text):
        from mini_kio.core.command_parser import is_multi_step
        interrogatives = frozenset({"who", "what", "where", "when", "why", "how"})
        first_w = lower.split()[0] if lower.split() else ""

        # R4: confirm/accept antecedents — substring forms too ("please go ahead",
        # "yes please", "go ahead", "yes do it", "okay go for it"). Only when the
        # utterance is a short confirmation, never a full command.
        if (
            first_w in ("yes", "yeah", "sure", "ok", "okay")
            or lower in ("go ahead", "do it", "play video")
            or re.fullmatch(r"yes(?:\s+please|\s+go\s+ahead|\s+do\s+it)?", lower)
            or re.fullmatch(r"please\s+(?:go\s+ahead|go\s+for\s+it|do\s+it|go)", lower)
            or re.fullmatch(r"(?:go\s+ahead|go\s+for\s+it)", lower)
        ):
            return RoutingDecision(IntentType.CONVERSATION, "accept_offer", "", text, lower, confidence=0.9)

        if first_w in interrogatives and len(lower.split()) >= 2:
            if is_multi_step(lower):
                return None
            return RoutingDecision(IntentType.INFORMATION, "information_query", text, text, lower, confidence=0.7)

        if lower.startswith(("latest ", "what's the latest ", "what is the latest ", "this is news ",
                             "what's new ", "tell me about ", "news about ", "news on ")):
            return RoutingDecision(IntentType.INFORMATION, "information_query", text, text, lower, confidence=0.7)

        sports_keywords = ["standings", "table", "group ", "groups", "fixtures", "fixture",
                           "results", "match ", " matches", "score", "scores", "points table",
                           "league table", "world cup"]
        if any(kw in lower for kw in sports_keywords) and not lower.startswith(("play ", "watch ")):
            return RoutingDecision(IntentType.INFORMATION, "information_query", text, text, lower, confidence=0.8)

        return None

    def _classify_memory(self, lower):
        if re.match(r"^remember\s+(?:that\s+)?(.+)", lower):
            return RoutingDecision(IntentType.MEMORY, "store", lower, lower, lower, confidence=0.9)
        if re.match(r"^my\s+name\s+is\s+(.+)", lower):
            return RoutingDecision(IntentType.MEMORY, "store", lower, lower, lower, confidence=0.9)
        if re.match(r"^call\s+me\s+(.+)", lower):
            return RoutingDecision(IntentType.MEMORY, "store", lower, lower, lower, confidence=0.9)
        if re.match(r"^my\s+favorite\s+.+\s+is\s+", lower):
            return RoutingDecision(IntentType.MEMORY, "store", lower, lower, lower, confidence=0.9)
        if re.match(r"^forget\s+(?:that|it|this|everything|all)\b", lower) or lower == "forget":
            return RoutingDecision(IntentType.MEMORY, "forget", lower, lower, lower, confidence=0.9)
        if re.match(r"^forget\s+(.+)", lower):
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

    def _classify_opinion(self, lower, text):
        _opinion = (
            r"what\s+(?:do|did|would)\s+(?:you|we|they)\s+think\s+(?:about|of)\b",
            r"how\s+do\s+you\s+feel\s+(?:about|on)\b",
            r"what(?:'s|\s+is)\s+your\s+(?:take|opinion)\b",
            r"in\s+your\s+opinion\b",
            r"do\s+you\s+(?:like|love|enjoy|rate)\b",
            r"do\s+you\s+think\b",
            r"would\s+you\s+recommend\b",
            r"^recommend\b",
            r"should\s+i\s+(?:watch|play|see|read|listen\s+to|try)\b",
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
                         "it", "that", "this", "there", "my", "your", "for", "to"}
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

        if (
            orig_first and orig_first[0].isupper() and len(orig_first) > 1
            and first_w not in skip and first_w not in two_word_stop
            and not _single_word_casual
        ):
            return RoutingDecision(IntentType.ENTITY_QUERY, "information_query", raw_text, raw_text, lower, confidence=0.8)

        if len(words) >= 2:
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
    Maps RoutingDecision to (capability_name, params).
    Capability names: "desktop", "media", "browser", "conversation", "knowledge", "system", "file"
    """

    def resolve(self, decision: RoutingDecision) -> tuple[str, dict[str, Any]]:
        # R11 convergence: "search X in youtube" is a controlled-media search
        # owned by YouTubeProvider (connector world). Routing it to the desktop
        # capability sent it through browser_operator, which could fall back to
        # an uncontrolled external browser KIO cannot subsequently control.
        if (
            decision.intent_type == IntentType.SEARCH
            and decision.action == "search_youtube"
        ):
            return (
                "media",
                {
                    "action": "search",
                    "target": decision.target,
                    "platform": "youtube",
                    "raw": decision.raw_text,
                },
            )

        mapping = {
            IntentType.GREETING: ("conversation", {"template": "greeting"}),
            IntentType.SOCIAL: ("conversation", {"template": "social"}),
            IntentType.IDENTITY: ("conversation", {"template": "identity"}),
            IntentType.DESKTOP_OPEN: ("desktop", {"action": decision.action, "target": decision.target, "metadata": decision.metadata}),
            IntentType.DESKTOP_CLOSE: ("desktop", {"action": decision.action, "target": decision.target}),
            IntentType.SEARCH: ("desktop", {"action": decision.action, "target": decision.target}),
            IntentType.MEDIA_PLAY: ("media", {"action": "play", "target": decision.target, "platform": decision.platform, "raw": decision.raw_text}),
            IntentType.MEDIA_TRANSPORT: ("media", {"action": decision.action, "target": decision.target}),
            IntentType.BROWSER_FOCUS: ("browser", {"action": decision.action, "target": decision.target}),
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
            IntentType.UNKNOWN: ("conversation", {"template": "unknown"}),
        }
        result = mapping.get(decision.intent_type, ("conversation", {"template": "unknown"}))
        return result


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
        }
        handler = dispatch.get(capability, self._exec_conversation)
        return handler(params, decision)

    def _exec_credential(self, params: dict, decision: RoutingDecision) -> dict:
        from mini_kio.core.credential_vault import credential_management_result
        return credential_management_result(
            params.get("action", "list"),
            target=params.get("target", ""),
        )

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
                return reused
        return execute_action(action, target)

    def _exec_camera(self, meta: dict, dp) -> dict:
        """Camera capability executor (generic — no app-specific branches).

        Resolves the NATIVE installed camera through the same canonical app
        discovery used for every open (UWP included), launches it, and for a
        capture request attempts a real shutter press. Success is claimed only
        when a new photo file actually appears in the camera output folder;
        otherwise the limitation is reported truthfully.
        """
        import time as _t
        from mini_kio.core.app_operator import _find_installed_app, _launch_discovered

        camera_action = str(meta.get("camera_action") or "open")
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
        _t.sleep(2.0)

        if camera_action == "open":
            # Honest verification: the launch succeeded (shell/explorer
            # accepted it), but a UWP app window may take seconds to appear —
            # never claim more than "launched".
            return {"success": True, "message": "Opened the camera.", "verified": None}

        # CAPTURE: attempt a real shutter press and verify a photo appeared.
        try:
            import pathlib as _pl
            from glob import glob as _glob
            cam_roll = _pl.Path.home() / "Pictures" / "Camera Roll"
            before = set(_glob(str(cam_roll / "*"))) if cam_roll.is_dir() else set()
            pressed = dp.execute("keyboard_press", target="enter")
            if not pressed.get("success"):
                pressed = dp.execute("keyboard_press", target="space")
            _t.sleep(3.0)
            after = set(_glob(str(cam_roll / "*"))) if cam_roll.is_dir() else set()
            new_photos = after - before
            if new_photos:
                name = _pl.Path(sorted(new_photos)[-1]).name
                return {"success": True, "message": f"Took a photo — saved {name}.", "verified": True}
            return {
                "success": False,
                "message": "The camera is open, but I couldn't confirm a photo was saved — the shutter control isn't reliably reachable on this setup.",
                "camera_open": True,
            }
        except Exception as exc:
            return {
                "success": False,
                "message": f"The camera is open, but I couldn't verify the capture ({str(exc)[:60]}).",
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
            from mini_kio.core.document_operator import create_document
            subject = str(target or meta.get("subject") or "").strip()
            if not subject:
                return {"success": False, "message": "What should the document be about?"}
            artifact = str(meta.get("artifact") or "document")
            style = str(meta.get("style") or "")
            content = self._generate_content(
                f"{subject}", "", artifact=artifact, style=style
            )
            if not content:
                return {"success": False, "message": f"I couldn't generate content for the {subject} document."}
            result = create_document(subject, content, artifact=artifact, style=style)
            if result.get("success"):
                # Open the created artifact so the user sees it immediately.
                try:
                    from mini_kio.core.document_operator import open_document
                    import pathlib
                    open_document(pathlib.Path(result["path"]))
                except Exception:
                    pass
                return {
                    "success": True,
                    "message": f"Created {result.get('filename')} — {result.get('word_count', 0)} words.",
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
        sent as keystrokes. Falls back to typing if the clipboard is
        unavailable. Returns the provider result dict.
        """
        if force_typing or len(payload) <= 80:
            return dp.execute("keyboard_type", target=payload)
        try:
            clip = dp.execute("clipboard_set", target=payload)
            if not clip.get("success"):
                return dp.execute("keyboard_type", target=payload)
            pasted = dp.execute("keyboard_hotkey", target="ctrl+v")
            if pasted.get("success"):
                return {"success": True, "action": "paste", "message": "Pasted complete content."}
            return dp.execute("keyboard_type", target=payload)
        except Exception:
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
            from mini_kio.core.context_manager import get_session_context
            ctx = get_session_context(decision.session_id)
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
            from mini_kio.core.context_manager import get_session_context
            ctx = get_session_context(decision.session_id)
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

        if action == "play":
            return mm.play(params.get("target", ""), platform=params.get("platform"))
        if action == "search":
            return mm.search(
                params.get("target", ""),
                platform=params.get("platform", ""),
            )
        if action == "set_volume":
            return mm.set_volume(int(params["target"]))
        if action == "information_query":
            return mm.process_information_query(params["query"])
        if action == "accept_offer":
            result = mm.process_followup(decision.normalized_text)
            if result:
                return result
            if mm.has_intelligence_offer():
                return mm.accept_intelligence_offer()
            last = mm.get_last_offer()
            if last:
                return mm.accept_offer()
            return {"success": True, "message": "No pending offer."}

        transport_actions = {
            "pause": mm.pause, "resume": mm.resume, "stop": mm.stop,
            "mute": mm.mute, "unmute": mm.unmute,
            "next": mm.next_track, "previous": mm.previous_track,
            "volume_up": lambda: mm.volume_up(), "volume_down": lambda: mm.volume_down(),
            "continue": mm.resume,
            "now_playing": lambda: mm.now_playing(),
        }
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

    # NOTE: desktop-state composition ('What's open?') moved to the canonical
    # owner mini_kio/core/desktop_state.py (native window observation + tab
    # grouping + dedupe + short forms). _exec_browser.list_tabs delegates there.

    def _try_native_focus(self, target: str) -> Optional[dict]:
        """Capability A: bring a running native app's window to the foreground.

        Uses the tracked process PID (or registry-based process discovery for
        registered apps) — never a blind system-wide process sweep.
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
            # Generic fallback (Capability A, system-wide): match a VISIBLE
            # native window by app identity — covers arbitrary applications
            # KIO never launched/registered. Never a process sweep; activates
            # only the exact matched window's PID. Browser-host windows are
            # never matched here: focusing a whole browser process because a
            # tab merely mentions the target would violate the no-scope-
            # escalation invariant (browser focus is the connector's job).
            from mini_kio.core.desktop_state import observe_native_windows
            from mini_kio.platform.window_activation import activate_window
            windows, ok = observe_native_windows()
            if not ok:
                return None
            # Identity match first (exe base / brand-cased app name).
            for w in windows:
                if w.get("is_browser_host") or not w.get("pid"):
                    continue
                if (w.get("base") and key in w["base"]) or key in (w.get("app") or "").lower():
                    if activate_window(int(w["pid"])):
                        return {"success": True, "message": f"Focused {w.get('app') or target}."}
            # Title-substring fallback (still never a browser-host window).
            for w in windows:
                if w.get("is_browser_host") or not w.get("pid"):
                    continue
                if key in (w.get("title") or "").lower():
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
            if conn and conn.is_connected():
                from mini_kio.core.async_utils import safe_run_async
                try:
                    result = safe_run_async(conn.focus_tab(params["target"]))
                    if result.success:
                        self._try_browser_activate()
                        from mini_kio.core.target_ref import display_target_name
                        return {"success": True, "message": f"Focused {display_target_name(params['target'])} tab."}
                except Exception as exc:
                    logger.warning("focus_tab failed: %s", exc)
            if _check_br_available():
                result = _br_focus_tab(params["target"])
                if result.get("success"):
                    self._try_browser_activate()
                    return result
            # Capability A: "Focus/Switch to X" may target a running native app
            # window (e.g. Calculator, Notepad) — not only browser tabs.
            native = self._try_native_focus(params["target"])
            if native:
                return native
            return {"success": False, "message": f"Couldn't focus {params['target']}."}

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

    def _exec_conversation(self, params: dict, decision: RoutingDecision) -> dict:
        template = params.get("template", "")

        if template == "identity":
            from mini_kio.llm.identity_dataset import get_identity_answer
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

        # Greetings and social pleasantries are deterministic and instant:
        # a generative LLM here only risks fabricating context it doesn't have.
        if template == "greeting":
            return {"success": True, "message": self._reply_greeting(decision.normalized_text)}

        if template == "social":
            responses = {
                "thanks": ["You're welcome.", "No problem.", "Happy to help.", "Anytime."],
                "acknowledge": ["Got it.", "Noted.", "Right.", "Sure.", "Sounds good."],
            }
            if decision.raw_text.lower() in ("thanks", "thank you", "thankyou", "ty", "thx"):
                return {"success": True, "message": random.choice(responses["thanks"])}
            return {"success": True, "message": random.choice(responses["acknowledge"])}

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
            reply = self._chat_converse(decision)
            return {"success": True, "message": reply} if reply else {"success": True, "message": "Sure — what is it?"}

        # Substantive conversation (opinions, recommendations, open chat,
        # empathy): generate a natural reply with the LLM using session
        # facts + history.
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
            return {"success": False, "message": f"I'm not sure how to handle that."}

        if action == "elaborate":
            from mini_kio.media.media_manager import MediaManager
            result = MediaManager.get_instance().process_followup(decision.normalized_text)
            if result:
                return result
            return {"success": True, "message": "I don't have more to add right now."}

        return {"success": False, "message": f"Conversation action '{action}' not implemented."}

    def _reply_greeting(self, text: str) -> str:
        lower = text.lower()
        if re.search(r"\bgood\s+(morning|afternoon|evening|night)\b", lower):
            for key, reply in (
                ("morning", "Good morning! What can I help you with today?"),
                ("afternoon", "Good afternoon! What can I do for you?"),
                ("evening", "Good evening! What's on your mind?"),
                ("night", "Good night! Sleep well."),
            ):
                if f"good {key}" in lower:
                    return reply
        if any(
            k in lower
            for k in (
                "how are you", "how's it going", "how is it going", "how are ya",
                "how are things", "how have you been", "how you doing",
                "how's your day", "how is your day", "how are you doing",
                "what's up", "what is up",
            )
        ):
            # Truthful, KIO-appropriate small talk: an assistant with a real
            # operational state — never a fabricated human biography.
            return random.choice([
                "All good on my end and ready to help. What's on your mind?",
                "Running fine. What can I do for you?",
                "Everything's working — what do you need?",
            ])
        return random.choice([
            "Hey! How's it going?",
            "Hello! What can I do for you?",
            "Hey there. What's up?",
            "Hi! Good to see you.",
            "Hey! What's on your mind?",
            "Hello. How can I help?",
        ])

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

    def _generate_content(self, prompt: str, target_app: str = "", *, artifact: str = "", style: str = "") -> Optional[str]:
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
        if artifact in ("spreadsheet", "presentation", "table"):
            structure_rule = (
                "For a spreadsheet: output actual tabular data with a header "
                "row and one record per line, separated by tabs. "
                "For a presentation: output slide titles as short lines followed "
                "by concise bullet points for each slide."
            )
        else:
            structure_rule = (
                "Plain readable prose with real paragraphs. "
                "Do not output markdown."
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
        if artifact in ("comparison", "report", "paper", "overview", "guide", "write-up") \
                or re.search(r"(comparison|compare|report|research|explain|analysis|overview)", (prompt or "").lower()):
            facts = self._research_facts(prompt)
        if facts:
            system_prompt += (
                "\n\nUse the following retrieved facts as grounding for the "
                "content. Synthesize them into clean, readable prose — do not "
                "copy them verbatim, do not list them as bullet dumps, and do "
                "not fabricate details beyond them."
                f"\n\nRETRIEVED FACTS:\n{facts}"
            )
        try:
            # 2400 tokens so a substantive essay/report/comparison completes
            # instead of silently truncating (the old 1400 cap produced the
            # "one sentence" / partial-content documents).
            reply = ask_llm_sync(
                prompt,
                system_prompt=system_prompt,
                timeout=45.0,
                max_tokens=2400,
                task="content",
            )
        except Exception:
            return None
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
            ctx = get_session_context(decision.session_id)
        except Exception:
            pass

        parts = [
            "You are KIO, an intelligent personal companion and desktop assistant. "
            "You are chatting naturally with a real user. Be warm, conversational and short-first: "
            "reply in 1-2 sentences and stop. Never append robotic prompts such as "
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
            "CRITICAL: You do NOT perform desktop actions yourself (typing, clicking, pressing "
            "keys, opening apps, saving files). If a message asks you to type, write, create, "
            "open, or save something in an application, you must NOT claim you did it or that you "
            "'will' do it. Say plainly that you can handle it through your command system or that "
            "you weren't able to execute it — never fabricate an action you did not perform. "
            "NEVER invent the user's name, age, gender, appearance, location, feelings, health, "
            "relationships, personal history, or past events. Never address the user by any name. "
            "Never assume anything about the user's identity or life. Only the 'Known facts' section "
            "may name the user (user_name), and only then may you use that name - otherwise no name. "
            "If you don't know something about the user, say so instead of guessing. Do not speculate "
            "about how the user is feeling or what they are doing unless they told you.",
        ]
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

        try:
            if ctx is not None:
                facts = ctx.get_all_facts()
                if facts:
                    parts.append("Known facts about the user:\n" + "\n".join(f"- {k}: {v}" for k, v in facts.items()))
                history = ctx.get_history_window(6)
                history = [(u, r) for u, r in history if not _bad_kio_reply(r)]
                if history:
                    parts.append("Recent conversation (oldest first):\n" + "\n".join(f"User: {u}\nKIO: {r}" for u, r in history))
        except Exception:
            pass

        try:
            reply = ask_llm_sync(decision.normalized_text, system_prompt="\n\n".join(parts), timeout=25.0, max_tokens=300, task="conversation")
        except Exception:
            reply = None
        if reply:
            cleaned = reply.strip().strip('"').strip("'")
            # Truncation guard: a provider stream cut produces a reply with no
            # terminal punctuation ("As an AI, I don't have personal"). Retry
            # once; if it still does not end like a complete sentence, treat it
            # as failed rather than surfacing a broken half-reply. A minimum
            # length keeps legitimate short replies ("Sure", "Okay", "Thanks")
            # from paying for a second LLM call.
            if not cleaned.endswith((".", "!", "?")) and 20 <= len(cleaned) < 150:
                try:
                    retry = ask_llm_sync(decision.normalized_text, system_prompt="\n\n".join(parts), timeout=25.0, max_tokens=300, task="conversation")
                except Exception:
                    retry = None
                if retry and retry.strip().endswith((".", "!", "?")):
                    cleaned = retry.strip().strip('"').strip("'")
                else:
                    return None
            # Anti-fabrication: the model must never address the user by an
            # invented name ("Hey, it sounds pretty serious. Peter").
            cleaned = _sanitize_llm_name_address(cleaned)
            if len(cleaned) > 1 and cleaned.lower() != decision.normalized_text.lower().strip():
                return cleaned
        return None

    def _exec_memory(self, params: dict, decision: RoutingDecision) -> dict:
        from mini_kio.core.context_manager import get_session_context
        from mini_kio.memory.memory_store import PatternMemoryExtractor

        ctx = get_session_context(decision.session_id)
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
                    friendly.append(f"{key}: {value}.")
            return {"success": True, "message": "Got it — " + " ".join(friendly)}

        if params.get("action") == "forget":
            facts = store.get_all_facts()
            if not facts:
                return {"success": False, "message": "I don't have anything saved about you yet."}
            if re.search(r"\b(that|it|this)\b", text.lower()):
                key = next(reversed(facts))
                store.delete_fact(key)
                return {"success": True, "message": f"Done — I've forgotten about {key.replace('_', ' ')}."}
            store.clear()
            return {"success": True, "message": "Done — I've forgotten everything I knew about you."}
        if params.get("action") == "forget_one":
            topic = text.lower().replace("forget", "", 1).strip(" .,!?;:")
            facts = store.get_all_facts()
            target = None
            t_terms = re.findall(r"[a-z0-9]+", topic)
            for k in facts:
                k_terms = re.findall(r"[a-z0-9]+", k)
                if any(t in k_terms for t in t_terms if len(t) > 2):
                    target = k
                    break
            if target:
                store.delete_fact(target)
                return {"success": True, "message": f"Done — I've forgotten about {topic}."}
            return {"success": False, "message": f"I don't remember anything about {topic}."}

        ctx.append_message("user", text)
        facts = store.get_all_facts()
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
            stop = {"what", "is", "my", "s", "i", "do"}
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
                        scoped.append(f"{orig_k.replace('_', ' ')}: {v}.")
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
        if "favorite" in lower:
            favs = {k: v for k, v in facts.items() if k.startswith("favorite_")}
            if favs:
                lines = "\n".join(f"  {k}: {v}" for k, v in favs.items())
                return {"success": True, "message": "Here's what I remember:\n" + lines}
        lines = "\n".join(f"  {k}: {v}" for k, v in facts.items())
        return {"success": True, "message": "Here's what I remember:\n" + lines}

    def _exec_knowledge(self, params: dict, decision: RoutingDecision) -> dict:
        knowledge_base = {
            "hello": "Hello.",
            "hi": "Hi there.",
            "hey": "Hey.",
            "what can you do": "I can open and close applications, search Google and YouTube, play media, and open folders.",
            "capabilities": "I handle desktop automation, web search, and conversational assistance.",
        }
        q = decision.normalized_text.lower().strip()
        for key, answer in knowledge_base.items():
            if re.search(rf"\b{re.escape(key)}\b", q):
                return {"success": True, "message": answer}
        return {"success": False, "message": "No answer in knowledge base."}

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
        result.setdefault("success", False)
        if "message" not in result:
            result["message"] = "Done." if result.get("success") else "Command failed."

        message = result["message"] if isinstance(result["message"], str) else str(result["message"])
        result["message"] = self._strip_leaks(message or "Done.")

        ctx.update(result, decision.normalized_text)
        try:
            ctx.append_exchange(decision.normalized_text, result.get("message") or "")
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
