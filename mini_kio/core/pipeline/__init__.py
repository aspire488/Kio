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
        # Explicit new-tab family: "open another tab of X", "open X in a new
        # tab" — the user explicitly asked for an ADDITIONAL target, so
        # duplicate prevention must not reuse the existing one.
        force_new = False
        webapp = None
        browser = None
        m = re.match(r"^open\s+(?:another|a\s+new)\s+tab\s+(?:of\s+)?(.+?)\s*$", lower)
        if m:
            webapp, browser, force_new = m.group(1).strip(), "", True
        else:
            m = re.match(r"^open\s+(.+?)\s+in\s+(?:a\s+)?(?:new|fresh)\s+tab\s*$", lower)
            if m:
                webapp, browser, force_new = m.group(1).strip(), "", True
            else:
                m = re.match(r"^open\s+(.+?)\s+in\s+(chrome|edge|comet|firefox|brave|browser)$", lower)
                if m:
                    webapp, browser = m.groups()
        if not webapp:
            return None
        if browser == "browser":
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
                metadata={"explicit_new": force_new, "webapp": webapp_lower},
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
        target = re.sub(r"^(?:the|a|an)\s+", "", target.strip(), flags=re.IGNORECASE)
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

    def _detect_desktop_action(self, lower, text):
        # ── TYPE family: "type hello into Notepad", "write this in Notepad",
        #    "put hello into the current field", "enter my name" ─────────────
        m = re.match(
            r"^(?:type|write|put|enter)\s+(.+?)\s+(?:into|in)\s+(.+)$",
            lower,
        )
        if m:
            payload, app = m.group(1).strip(), m.group(2).strip()
            app_lower = app.lower().rstrip(".")
            if app_lower not in self._TYPE_TARGET_LANGUAGES:
                return RoutingDecision(
                    IntentType.DESKTOP_ACTION, "type", app, text, lower,
                    confidence=1.0, metadata={"payload": payload},
                )
            return None
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

        # ── Shortcut family: normalize wording → canonical key combos ───────
        # "save this"/"save the file" → ctrl+s; "copy that" → ctrl+c;
        # "paste it here" → ctrl+v; "select all" → ctrl+a; undo/redo.
        if re.fullmatch(r"save(?:\s+(?:this|the\s+file|it|that|file|document))?", lower):
            return RoutingDecision(
                IntentType.DESKTOP_ACTION, "key_press", "ctrl+s", text, lower,
                confidence=1.0,
            )
        if re.fullmatch(r"copy(?:\s+(?:this|that|it|the\s+selection|selection))?", lower):
            return RoutingDecision(
                IntentType.DESKTOP_ACTION, "key_press", "ctrl+c", text, lower,
                confidence=1.0,
            )
        if re.fullmatch(r"paste(?:\s+(?:it\s+here|it|here|this|that))?", lower):
            return RoutingDecision(
                IntentType.DESKTOP_ACTION, "key_press", "ctrl+v", text, lower,
                confidence=1.0,
            )
        if lower in ("select all", "select everything", "select the whole thing"):
            return RoutingDecision(
                IntentType.DESKTOP_ACTION, "key_press", "ctrl+a", text, lower,
                confidence=1.0,
            )
        if lower in ("undo", "undo that", "undo it"):
            return RoutingDecision(
                IntentType.DESKTOP_ACTION, "key_press", "ctrl+z", text, lower,
                confidence=1.0,
            )
        if lower in ("redo", "redo that", "redo it"):
            return RoutingDecision(
                IntentType.DESKTOP_ACTION, "key_press", "ctrl+y", text, lower,
                confidence=1.0,
            )

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

    # Semantic family for contextual desktop-state queries (Capability A).
    # Synonym/normalization-based (what/which/show/list/tell + state nouns),
    # NOT phrase-by-phrase hacks. Every variant routes to list_tabs
    # deterministically — verified runtime state, never an LLM guess.
    _STATE_QUERY_PATTERNS = (
        # Anchored with a bounded tail so knowledge questions that merely share
        # the prefix ("what's open source", "what is running time") stay on
        # the knowledge path; "in/on chrome / my computer" live in the pattern
        # below.
        re.compile(r"^what(?:'s|s| is| are)?\s+(?:currently\s+)?(?:open|running|active)(?:\s+right\s+now|\s+kio)?\s*$"),
        re.compile(r"^what\s+am\s+i\s+(?:currently\s+)?(?:using|running|controlling|working\s+(?:on|with))\b"),
        re.compile(r"^what\s+(?:are\s+you|is\s+kio)\s+(?:currently\s+)?(?:using|controlling|working\s+on)\b"),
        re.compile(r"^what\s+(?:browser\s+)?tabs\s+are\s+open\b"),
        re.compile(r"^which\s+(?:browser\s+)?tabs\s+are\s+open\b"),
        re.compile(r"^what\s+(?:apps|applications|windows)\s+are\s+(?:open|running|active)\b"),
        re.compile(r"^which\s+(?:apps|applications|windows)\s+are\s+(?:open|running|active)\b"),
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
        (re.compile(r"^what(?:'s|s| is)?\s+(?:my\s+|the\s+)?(?:apps?|applications|software|programs?)\s+(?:do\s+i\s+have|are\s+installed|have\s+i\s+got)\b"), "app_inventory", ""),
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

        if not raw_text:
            raw_text = text
        orig_words = raw_text.strip().split() if raw_text else words
        orig_first = orig_words[0] if orig_words else ""

        if orig_first and orig_first[0].isupper() and len(orig_first) > 1 and first_w not in skip and first_w not in two_word_stop:
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

        if action == "type":
            payload = str(meta.get("payload", "") or "")
            if not payload:
                return {"success": False, "message": "What should I type?"}
            app = target.strip()
            opened_now = False
            if app:
                # TYPE into a named app: focus it first (or open it if it is
                # installed but not running), then type into its window.
                focused = self._try_native_focus(app)
                if not focused:
                    from mini_kio.core.routing_utils import get_browser_routing
                    route_info = get_browser_routing(app)
                    if route_info["route_type"] == "native":
                        execute_action("open_app", route_info["target"])
                        import time
                        time.sleep(0.8)
                        focused = self._try_native_focus(route_info["target"])
                        opened_now = True
                    elif route_info["route_type"] == "browser_fallback":
                        execute_action("execute_capability", route_info["target"])
                        return {"success": True, "message": "Opened the web app — I can't type into a browser tab yet."}
                if not focused:
                    return {"success": False, "message": f"Couldn't focus {app} to type into it."}
                if not opened_now:
                    # The app was ALREADY running, possibly with an existing
                    # file open. Open a NEW blank document (generic Ctrl+N
                    # new-document shortcut across Notepad/editors) so typed
                    # text never lands in existing content. Apps KIO just
                    # launched are already a fresh blank document.
                    import time
                    time.sleep(0.2)
                    new_doc = dp.execute("keyboard_hotkey", target="ctrl+n")
                    time.sleep(0.4)
                    if not new_doc.get("success"):
                        # The new-document shortcut failed: abort truthfully
                        # rather than typing into the existing file.
                        return {"success": False, "message": f"Couldn't open a new {target.strip().capitalize()} document to type into."}
            result = dp.execute("keyboard_type", target=payload)
            if result.get("success"):
                return {"success": True, "message": f"Typed it{(' into a new ' + target.strip().capitalize()) if target.strip() else ''}."}
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
            # Explicit additional-tab request: tag the capability target so the
            # executor skips duplicate prevention and really opens a new tab.
            if meta.get("explicit_new") and "::open_url::" in target and not target.endswith("::new"):
                target = target + "::new"
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
            "When asked for an opinion or to compare options, give a "
            "reasoned analytical perspective grounded in KIO's design philosophy (determinism, "
            "safety, honesty, human judgment) and the facts at hand. You may have opinions, but "
            "you never invent personal human experience: you do not have a body, senses, "
            "emotions, a childhood, or personal taste from living. Do not claim to like/dislike "
            "music, films, food, games, or sports from personal experience; discuss them "
            "analytically instead. If you don't know, or the topic is current/breaking, say so "
            "honestly instead of inventing facts. Plain prose only - no headings, no bullet lists, "
            "no 'Quick rundown' sections. "
            "NEVER reference past conversation topics unless they appear in the 'Recent conversation' "
            "section below. If that section is empty, you have NO prior context - greet naturally and "
            "do not claim or imply you were discussing anything before. "
            "You are honest that you are an AI companion when asked directly. "
            "NEVER invent the user's name, age, gender, appearance, location, feelings, health, "
            "relationships, personal history, or past events. Never address the user by any name. "
            "Never assume anything about the user's identity or life. Only the 'Known facts' section "
            "may name the user (user_name), and only then may you use that name - otherwise no name. "
            "If you don't know something about the user, say so instead of guessing. Do not speculate "
            "about how the user is feeling or what they are doing unless they told you.",
        ]
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
