from __future__ import annotations

import json
import logging
import random
import re
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
            ctx = get_session_context(session_id)
            raw = text.strip()
            if not raw:
                return {"success": True, "message": ""}

            normalized = self._normalizer.run(raw, ctx)
            decision = self._classifier.classify(normalized, raw)
            decision.session_id = session_id
            decision.channel = channel
            decision.user_id = user_id

            capability, params = self._resolver.resolve(decision)
            result = self._coordinator.execute(capability, params, decision)
            return self._composer.compose(result, decision, ctx)
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
        # command verb; never strip from standalone social small-talk.
        stripped = self._POLITE_PREFIX_RE.sub("", cmd, count=1).strip()
        if stripped and cmd.lower() != stripped.lower():
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

    SYSTEM_ACTIONS = frozenset({"shutdown", "restart", "lock", "recovery", "recover"})

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

    def classify(self, text: str, raw_text: str) -> RoutingDecision:
        lower = text.lower().strip()
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

    def _strip_greeting(self, lower_clean, first_word, second_word, words, text="", raw_text=""):
        names = ("kio", "bro", "joel")
        if first_word in self.GREETINGS:
            remaining = " ".join(words[1:]) if second_word not in names else " ".join(words[2:])
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
        elif first_word in names:
            remaining = " ".join(words[1:])
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
        if lower_clean in self.GREETINGS | frozenset({"how are you", "how are you doing", "how are ya"}):
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
        if get_identity_answer(lower):
            return RoutingDecision(IntentType.IDENTITY, "", "", raw_text or normalized_text, normalized_text or lower, confidence=1.0)
        return None

    def _is_forbidden(self, lower, first_word):
        norm = lower[5:].strip().lower() if first_word == "open" else lower
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
        verbs = {"open", "close", "search", "play", "launch", "folder"}
        if first_word in verbs:
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

    def _detect_browser_webapp(self, lower, text):
        match = re.match(r"^open\s+(.+?)\s+in\s+(chrome|edge|comet|firefox|brave)$", lower)
        if match:
            webapp, browser = match.groups()
            from mini_kio.core.app_operator import _normalize_web_target_to_url
            url = _normalize_web_target_to_url(webapp)
            if url:
                return RoutingDecision(
                    IntentType.BROWSER_NAVIGATE, "execute_capability",
                    f"{browser}::open_url::{url}::{webapp}",
                    text, lower, confidence=1.0,
                )
        return None

    def _detect_open(self, lower, text, first_word):
        if not first_word == "open":
            return None
        target = text[5:].strip()
        target_lower = target.lower()
        words_set = set(target_lower.split())

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

        from mini_kio.core.routing_utils import get_browser_routing
        route_info = get_browser_routing(target)
        if route_info["route_type"] == "native":
            return RoutingDecision(IntentType.DESKTOP_OPEN, route_info["action"], route_info["target"], text, lower, confidence=1.0)
        elif route_info["route_type"] == "browser_fallback":
            return RoutingDecision(
                IntentType.BROWSER_NAVIGATE, route_info["action"], route_info["target"],
                text, lower, confidence=1.0,
                metadata={"canonical_target": route_info.get("canonical_target", ""), "browser": route_info.get("browser", "")},
            )
        else:
            return RoutingDecision(IntentType.SEARCH, "search_web", target, text, lower, confidence=0.6)

    def _detect_focus(self, lower, text, first_word, second_word):
        if first_word == "focus":
            return RoutingDecision(IntentType.BROWSER_FOCUS, "focus", text[6:].strip(), text, lower, confidence=1.0)
        if lower.startswith("switch to "):
            return RoutingDecision(IntentType.BROWSER_FOCUS, "focus", text[10:].strip(), text, lower, confidence=1.0)
        if first_word == "switch":
            return RoutingDecision(IntentType.BROWSER_FOCUS, "focus", text[7:].strip(), text, lower, confidence=1.0)
        return None

    def _detect_list_tabs(self, lower):
        return lower in ("list tabs", "list open tabs", "what tabs are open", "show tabs")

    def _detect_close(self, lower, text, first_word):
        if first_word == "close":
            target = text[6:].strip()
            browser_names = {"chrome", "edge", "firefox", "brave", "comet", "browser"}
            if target.lower() in browser_names or target.lower().endswith(" browser"):
                return RoutingDecision(IntentType.DESKTOP_CLOSE, "close_app", target.lower().replace(" browser", ""), text, lower, confidence=1.0)
            return RoutingDecision(IntentType.BROWSER_FOCUS, "close_tab", target, text, lower, confidence=1.0)
        return None

    def _detect_system(self, lower, first_word):
        if first_word in self.SYSTEM_ACTIONS:
            mapping = {"shutdown": "shutdown_system", "restart": "restart_system", "lock": "lock_system", "recovery": "recovery_runtime", "recover": "recovery_runtime"}
            return RoutingDecision(IntentType.SYSTEM, mapping[first_word], "", "", "", confidence=1.0)
        return None

    def _detect_file(self, lower, text, first_word):
        if lower.startswith("open folder ") or first_word == "folder":
            return RoutingDecision(IntentType.FILE, "open_folder", text, text, lower, confidence=1.0)
        return None

    def _classify_media_transport(self, lower, text):
        # R4: bare offer-acceptance followups that look like media commands
        # ("play it", "show it", "watch it") — classified as accept_offer before
        # the play-target branch can grab them.
        if lower in ("play it", "play that", "show it", "watch it", "play video"):
            return RoutingDecision(IntentType.CONVERSATION, "accept_offer", "", text, lower, confidence=0.9)

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
        mapping = {
            IntentType.GREETING: ("conversation", {"template": "greeting"}),
            IntentType.SOCIAL: ("conversation", {"template": "social"}),
            IntentType.IDENTITY: ("conversation", {"template": "identity"}),
            IntentType.DESKTOP_OPEN: ("desktop", {"action": decision.action, "target": decision.target}),
            IntentType.DESKTOP_CLOSE: ("desktop", {"action": decision.action, "target": decision.target}),
            IntentType.SEARCH: ("desktop", {"action": decision.action, "target": decision.target}),
            IntentType.MEDIA_PLAY: ("media", {"action": "play", "target": decision.target, "platform": decision.platform, "raw": decision.raw_text}),
            IntentType.MEDIA_TRANSPORT: ("media", {"action": decision.action, "target": decision.target}),
            IntentType.BROWSER_FOCUS: ("browser", {"action": decision.action, "target": decision.target}),
            IntentType.BROWSER_TABS: ("browser", {"action": "list_tabs", "target": ""}),
            IntentType.BROWSER_NAVIGATE: ("browser", {"action": decision.action, "target": decision.target, "metadata": decision.metadata}),
            IntentType.SYSTEM: ("system", {"action": decision.action}),
            IntentType.KNOWLEDGE: ("knowledge", {"query": decision.target}),
            IntentType.MULTI_STEP: ("coordinator", {"action": "multi_step", "raw_text": decision.raw_text}),
            IntentType.ENTITY_QUERY: ("media", {"action": "information_query", "query": decision.target}),
            IntentType.INFORMATION: ("media", {"action": "information_query", "query": decision.target}),
            IntentType.CONVERSATION: ("conversation", {"action": decision.action, "query": decision.target}),
            IntentType.FILE: ("desktop", {"action": decision.action, "target": decision.target}),
            IntentType.MEMORY: ("memory", {"action": decision.action, "query": decision.target}),
            IntentType.MCP: ("mcp", {"raw": decision.raw_text}),
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
            "file": self._exec_desktop,
            "coordinator": self._exec_coordinator,
            "memory": self._exec_memory,
            "mcp": self._exec_conversation,
        }
        handler = dispatch.get(capability, self._exec_conversation)
        return handler(params, decision)

    def _exec_desktop(self, params: dict, decision: RoutingDecision) -> dict:
        from mini_kio.core.execution_boundary import execute_action
        return execute_action(params["action"], params["target"])

    def _exec_media(self, params: dict, decision: RoutingDecision) -> dict:
        from mini_kio.media.media_manager import MediaManager

        mm = MediaManager.get_instance()
        action = params["action"]

        if action == "play":
            return mm.play(params.get("target", ""), platform=params.get("platform"))
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
        }
        first_word = decision.normalized_text.split()[0] if decision.normalized_text.split() else ""
        if first_word in transport_actions:
            return transport_actions[first_word]()
        if decision.normalized_text.startswith("seek "):
            return mm.seek_forward()
        if decision.normalized_text == "play":
            return mm.play()

        logger.warning("[MEDIA] unhandled action=%s text=%s", action, decision.normalized_text)
        return {"success": False, "message": f"Unhandled media action: {action}"}

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

        if action == "browser_goto":
            from mini_kio.core.execution_boundary import execute_action
            result = execute_action("browser_goto", params.get("target", ""))
            if result.get("success"):
                self._try_browser_activate()
            return result

        if action == "execute_capability":
            from mini_kio.core.execution_boundary import execute_action
            target = params.get("target", "")
            return execute_action("execute_capability", target)

        # Browser Connector is the single source of truth for tab state.
        # open_tab writes into the Connector registry; close/list/focus must
        # read from the same registry, not from a separate Playwright world.
        conn = _get_connector()

        if action == "list_tabs":
            if conn and conn.is_connected():
                from mini_kio.core.async_utils import safe_run_async
                try:
                    result = safe_run_async(conn.list_tabs())
                    if result.success and result.tabs:
                        lines = []
                        for idx, t in enumerate(result.tabs, start=1):
                            title = t.title or t.url
                            suffix = " [Opened by KIO]" if getattr(t, "is_owned", False) else ""
                            lines.append(f"{idx}. {title}{suffix}")
                        return {"success": True, "message": "Open tabs:\n" + "\n".join(lines)}
                    elif result.success:
                        return {"success": True, "message": "No tabs open."}
                except Exception as exc:
                    logger.warning("list_tabs failed: %s", exc)
            if _check_br_available():
                return _br_list_tabs()
            return {"success": False, "message": "Browser not available."}

        if action == "focus":
            if conn and conn.is_connected():
                from mini_kio.core.async_utils import safe_run_async
                try:
                    result = safe_run_async(conn.focus_tab(params["target"]))
                    if result.success:
                        self._try_browser_activate()
                        return {"success": True, "message": f"Focused {params['target'].capitalize()} tab."}
                except Exception as exc:
                    logger.warning("focus_tab failed: %s", exc)
            if _check_br_available():
                result = _br_focus_tab(params["target"])
                if result.get("success"):
                    self._try_browser_activate()
                return result
            return {"success": False, "message": f"Couldn't focus {params['target']}."}

        if action == "close_tab":
            if conn and conn.is_connected():
                from mini_kio.core.async_utils import safe_run_async
                try:
                    result = safe_run_async(conn.close_tab(params["target"]))
                    if result.success:
                        return {"success": True, "message": f"Closed {params['target'].capitalize()} tab."}
                except Exception as exc:
                    logger.warning("close_tab failed: %s", exc)
            elif _check_br_available():
                return _br_close_tab(params["target"])
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
                "how are you", "how's it going", "how are ya", "how are things",
                "how have you been", "how you doing", "how's your day",
                "how is your day", "how are you doing",
            )
        ):
            return random.choice([
                "I'm doing great, thanks for asking! How about you?",
                "Feeling good and ready to help. What's on your mind?",
                "All good on my end. What can I do for you?",
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
            "reply in 1-2 sentences, then offer to go deeper (e.g. 'Want more detail?'). "
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
            "You are honest that you are an AI companion when asked directly.",
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
            "recovery_runtime": "recovery_runtime",
        }
        canonical = action_map.get(params["action"], params["action"])
        return execute_action(canonical)

    def _exec_coordinator(self, params: dict, decision: RoutingDecision) -> dict:
        from mini_kio.core.command_parser import parse_command
        steps = parse_command(decision.raw_text or decision.normalized_text)
        if not steps:
            return {"success": False, "message": f"Could not parse multi-step command: {decision.raw_text!r}"}
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

    def _strip_leaks(self, message: str) -> str:
        """Remove implementation verbosity from any message at a central point."""
        if not message:
            return message
        stripped = self._LEAK_PATTERNS.sub("", message)
        stripped = re.sub(r"\s{2,}", " ", stripped).strip()
        stripped = self._LEAK_WORDS.sub("", stripped)
        stripped = re.sub(r"\s{2,}", " ", stripped).strip(" .,;\n\t")
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
            remember_runtime_context("execution", {
                "action": result.get("action", decision.action),
                "target": result.get("target", decision.target),
                "success": result.get("success", False),
            })
        return result
