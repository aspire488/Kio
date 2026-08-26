"""
pragmatics.py — Conversational Pragmatics Layer (canonical owner)
==================================================================

KIO's first-class conversational pragmatics layer. It determines not only
WHAT the user said but WHAT THEY ARE DOING WITH THOSE WORDS:

    semantic content  +  pragmatic intent  +  conversational act
        +  affect/tone  +  register  +  discourse context
        +  temporal context  +  relationship/context  +  response policy

It is deliberately NOT a greeting dictionary and NOT a sentiment analyzer.
It is the architectural layer between "raw message" and "response/action"
that decides:

    - which conversational acts the message performs (greeting, backchannel,
      reaction, agreement, meta-conversation control, ...)
    - what register the user is writing in (casual / playful / technical /
      formal / serious ...) as continuous dimensions
    - the temporal context (period of day, relative day)
    - whether this is pure low-content social speech (no task, no question)
    - whether retrieval / external research is warranted
    - what response length fits the social function
    - whether the message is a meta-conversational control signal that must
      CHANGE KIO's style ("you're too formal", "stop joking", "be serious")

Everything here is deterministic and fast (regex + bounded vocabularies,
never an LLM call and never an external provider) so simple conversational
messages stay cheap (milliseconds, zero retrieval). Substantive conversation
still flows to the LLM — with this analysis injected so it participates in
the right register instead of describing the user's behavior.

The module never emits internal diagnostics to the user.
"""

from __future__ import annotations

import random
import re
from dataclasses import dataclass, field
from datetime import datetime
from enum import Enum
from typing import Optional


# ── Conversational acts ──────────────────────────────────────────────────────

class ConversationAct(str, Enum):
    GREETING = "greeting"
    FAREWELL = "farewell"
    ACKNOWLEDGMENT = "acknowledgment"
    AGREEMENT = "agreement"
    DISAGREEMENT = "disagreement"
    AFFIRMATION = "affirmation"
    THANKS = "thanks"
    APOLOGY = "apology"
    BACKCHANNEL = "backchannel"
    SURPRISE = "surprise"
    AMUSEMENT = "amusement"
    FRUSTRATION = "frustration"
    EXCITEMENT = "excitement"
    REACTION = "reaction"
    COMPLIMENT = "compliment"
    COMPLAINT = "complaint"
    CORRECTION = "correction"
    TEASING = "teasing"
    PLAYFUL_BANTER = "playful_banter"
    DIRECT_ADDRESS = "direct_address"
    META_CONVERSATION = "meta_conversation"
    TOPIC_TRANSITION = "topic_transition"
    TOPIC_RESUME = "topic_resume"
    SMALL_TALK = "small_talk"
    REQUEST_ATTENTION = "request_attention"
    QUESTION = "question"
    OPINION_REQUEST = "opinion_request"
    COMMAND = "command"
    STATEMENT = "statement"
    WISH = "wish"


# ── Register (continuous dimensions, not a single label) ────────────────────

@dataclass
class Register:
    """Continuous register dimensions.

    formality:   -2 very casual  ..  +2 very formal
    playfulness:  0 serious      ..  +2 highly playful
    technicality: 0 .. 1
    energy:       0 calm         ..  2 high-energy (caps / repeated letters)
    emotion:      None or a short affective label ("amusement", "frustration",
                  "surprise", ...) — inferred, never a diagnosis.
    """

    formality: int = 0
    playfulness: int = 0
    technicality: int = 0
    energy: int = 0
    emotion: Optional[str] = None

    @property
    def label(self) -> str:
        if self.emotion == "amusement" and self.playfulness >= 2:
            return "playful"
        if self.technicality:
            return "casual technical" if self.formality <= 0 else "professional technical"
        if self.playfulness >= 2:
            return "playful"
        if self.playfulness == 1:
            return "lighthearted"
        if self.formality <= -1:
            return "casual"
        if self.formality >= 2:
            return "formal"
        if self.formality == 1:
            return "professional"
        return "neutral"


# ── Temporal context ─────────────────────────────────────────────────────────

@dataclass
class TemporalContext:
    now: datetime = field(default_factory=datetime.now)
    period: str = "day"          # early_morning/morning/afternoon/evening/night/late_night
    time_label: str = ""         # "8:52 PM"
    date_label: str = ""         # "Thursday, August 15"

    def describe(self) -> str:
        return f"it is {self.time_label} ({self.period})"


def _period_of(now: datetime) -> str:
    h = now.hour
    if 5 <= h < 8:
        return "early_morning"
    if 8 <= h < 12:
        return "morning"
    if 12 <= h < 17:
        return "afternoon"
    if 17 <= h < 21:
        return "evening"
    if 21 <= h < 24:
        return "night"
    return "late_night"


def _time_label(now: datetime) -> str:
    return now.strftime("%I:%M %p").lstrip("0")


def _date_label(now: datetime) -> str:
    label = now.strftime("%A, %B %d")
    # Windows strftime has no %-d; strip the leading zero of the day manually.
    label = re.sub(r"\b0(\d)", r"\1", label)
    return label


def current_temporal() -> TemporalContext:
    now = datetime.now()
    return TemporalContext(now=now, period=_period_of(now), time_label=_time_label(now), date_label=_date_label(now))


# ── Vocabulary (bounded — the architecture, not a slang dictionary) ─────────

_CASUAL_VOCAB = frozenset({
    "yo", "yoo", "hey", "heyy", "hi", "hii", "hello", "sup", "wassup", "wazzup",
    "whatsup", "wassgood", "ayy", "aye", "ayo", "hola", "howdy", "mornin",
    "gud", "bro", "broo", "bruh", "broski", "dude", "buddy", "homie", "man",
    "lol", "lmao", "lmfao", "rofl", "haha", "hahaha", "hehe", "lolll", "lmaooo",
    "damn", "damm", "daamn", "wow", "woww", "woah", "whoa", "cool", "nice",
    "nicee", "okay", "ok", "kk", "k", "alright", "aight", "gotcha", "mhm",
    "mm", "yeah", "yea", "yep", "yup", "nope", "nah", "nahh", "naah", "noo",
    "sure", "yess", "bet", "facts", "fr", "ong", "ngl", "tbh", "idk", "rly",
    "rlly", "omg", "omgg", "hmm", "huh", "oh", "ah", "um", "uh", "welp",
    "phew", "yikes", "ouch", "oops", "woops", "jeez", "gosh", "bruh", "damn",
    "great", "good", "fine", "awesome", "amazing", "sick", "lit", "fire",
    "dope", "crazy", "wild", "insane", "legit", "chill", "vibes", "vibe",
    "wbu", "wyd", "rn", "ty", "thx", "thanks", "thank", "pls", "plz", "gonna",
    "wanna", "gotta", "kinda", "sorta", "dunno", "cmon", "bruh", "heyy",
    "brooo", "broooo", "yooooo", "heyyyy", "hiii", "wassup", "lmaooo",
    "sorry", "sry", "my", "bad", "nahh", "hmm", "okkk", "yeahh", "huhh",
    "one", "job", "luck",
})

_GREETING_TOKENS = frozenset({
    "yo", "yoo", "yooo", "hey", "heyy", "hi", "hii", "hiii", "hello", "sup",
    "wassup", "wazzup", "whatsup", "wassgood", "ayy", "aye", "ayo", "hola",
    "howdy", "mornin", "morning", "gm", "gmorning", "goodmorning", "greetings",
    "namaste", "howdy", "yo", "bro", "broo", "bruh", "bruhh", "dude", "man",
})

_AMUSEMENT_TOKENS = frozenset({"lol", "lmao", "lmfao", "rofl", "haha", "hahaha", "hehe", "lolll", "lmaooo"})
_SURPRISE_TOKENS = frozenset({"wow", "woww", "damn", "damm", "daamn", "whoa", "woah", "omg", "omgg", "what", "whaat", "whattt", "no", "way"})
_AGREEMENT_TOKENS = frozenset({"yeah", "yea", "yep", "yup", "sure", "ok", "okay", "kk", "right", "exactly", "facts", "true", "fair", "bet", "agreed", "correct", "makes", "sense"})
_DISAGREEMENT_TOKENS = frozenset({"nah", "nahh", "nope", "noo", "naah", "not", "really", "disagree"})
# Confirmation-checking reactions ("fr?", "ong", "no cap", "seriously?") —
# surprise-family "for real?" disbelief/confirmation, not agreement tokens.
_CONFIRMATION_TOKENS = frozenset({"fr", "frr", "ong", "seriously", "deadass"})
_FAREWELL_TOKENS = frozenset({"bye", "goodbye", "gtg", "cya", "see", "ya", "later", "peace", "night", "goodnight", "gn", "out"})
_EMOJI_RE = re.compile(r"[\U0001F300-\U0001FAFF\u2600-\u27BF\uFE0F]+")
_AMUSEMENT_EMOJI = frozenset({"\U0001F602", "\U0001F923", "\U0001F480", "\U0001F602", "\U0001F92D", "\U0001F606"})  # 😂🤣💀😭😆
_REPEATED_CHAR_RE = re.compile(r"(.)\1+")
# Collapse only runs of 3+ repeated characters: 'yooo' -> 'yo', 'heyyy' ->
# 'hey', 'lmaooo' -> 'lmao'. Runs of exactly 2 are kept so real words keep
# their spelling: 'good' stays 'good', 'wassup' stays 'wassup', 'ayy' stays
# 'ayy' — the 2+-rule collapsed 'good' into 'god' and broke greeting detection.
_COLLAPSE3_RE = re.compile(r"(.)\1{2,}")


def _collapse(word: str) -> str:
    return _COLLAPSE3_RE.sub(r"\1", word)


def _alpha(text: str) -> str:
    return re.sub(r"[^a-z0-9\s]", "", text.lower())


def _is_repeated_greeting(text: str) -> bool:
    """Whole-utterance repeated-greeting check: 'yoyoyo', 'AYO AYO', 'yo yo'.

    Covers CONCATENATED repeats ('yoyoyo', 'heyhey', 'ayoayo') and stretched
    single words ('yooo', 'heyyy', 'hiii' — the stretch is handled by the
    collapsed-token membership check in _is_greeting_utterance). 'yo-yo ma'
    (the cellist) never matches because 'ma' is not greeting material.
    """
    flat = re.sub(r"[^a-z]", "", text.lower())
    if len(flat) < 3 or len(flat) > 24:
        return False
    for stem in (r"(yo){2,}", r"(ay+o?){2,}", r"(hey){2,}", r"(he+y+){2,}",
                 r"(hi){2,}", r"(bro){2,}", r"(sup){2,}", r"(wassup){2,}",
                 r"(aight){2,}", r"(ok){2,}"):
        if re.fullmatch(stem, flat):
            return True
    return False


# ── Meta-conversation control signals ────────────────────────────────────────

_META_SIGNALS: tuple[tuple[re.Pattern, str], ...] = (
    (re.compile(r"^(?:ok(?:ay)?|okay|right|alright)\s*,?\s*serious\s+question\b", re.I), "serious_turn"),
    (re.compile(r"^serious\s+question\b", re.I), "serious_turn"),
    (re.compile(r"^(?:you(?:'| a)?re|ur|you are)\s+too\s+(?:formal|robotic|stiff|rigid|customer\s+service|professional)\b", re.I), "less_formal"),
    (re.compile(r"^too\s+(?:formal|robotic|stiff|rigid)\b", re.I), "less_formal"),
    (re.compile(r"^stop\s+talking\s+like\s+(?:customer\s+support|a\s+robot|a\s+bot|that)\b", re.I), "less_formal"),
    (re.compile(r"^talk\s+normally\b", re.I), "neutral"),
    (re.compile(r"^be\s+normal\b", re.I), "neutral"),
    (re.compile(r"^(?:be|talk)\s+more\s+casual\b", re.I), "casual"),
    (re.compile(r"^(?:be|get)\s+casual\b", re.I), "casual"),
    (re.compile(r"^chill\b", re.I), "casual"),
    (re.compile(r"^(?:be|get)\s+serious\b", re.I), "serious"),
    (re.compile(r"^stop\s+joking\b", re.I), "serious"),
    (re.compile(r"^don'?t\s+joke\s+around\b", re.I), "serious"),
    (re.compile(r"^be\s+concise\b", re.I), "concise"),
    (re.compile(r"^don'?t\s+overdo\s+it\b", re.I), "concise"),
    (re.compile(r"^stop\s+explaining\s+everything\b", re.I), "concise"),
    (re.compile(r"^(?:be|keep\s+it|stay)\s+technical\b", re.I), "technical"),
    (re.compile(r"^give\s+me\s+the\s+technical\s+version\b", re.I), "technical"),
    (re.compile(r"^keep\s+it\s+(?:technical|professional)\b", re.I), "technical"),
    (re.compile(r"^you(?:'| a)?re\s+being\s+weird\b", re.I), "less_playful"),
    (re.compile(r"^that'?s\s+too\s+much\b", re.I), "less_playful"),
    (re.compile(r"^(?:you(?:'| a)?re|ur)\s+actually\s+funny\b", re.I), "compliment"),
    (re.compile(r"^(?:you(?:'| a)?re|ur)\s+funny\b", re.I), "compliment"),
)

_META_REPLIES: dict[str, tuple[str, ...]] = {
    "less_formal": ("lmao fair 😭", "fair 😭 my bad", "hahaha okay, fair"),
    "neutral": ("fair enough 😄", "okay okay, got it"),
    "casual": ("okay okay 😎", "got it 😎", "say less"),
    "serious": ("got it.", "understood."),
    "concise": ("fair.", "got it — short and sweet."),
    "technical": ("on it.", "sure — technical mode."),
    "less_playful": ("okay, dialing it back 😄", "fair 😄"),
    "serious_turn": ("go ahead.", "shoot.", "go on."),
    "compliment": ("lol thanks 😎", "appreciate it 😎"),
}

# Topic-movement discourse signals (generic families — "anyway", "speaking
# of", "by the way", "on another note", "random question", "forget that",
# "oh and" start a NEW subject; "back to", "going back to", "as i was
# saying", "where were we" RESUME an earlier thread). Never per-phrase
# response tables — these only steer the generator's thread focus.
_TOPIC_TRANSITION_RE = re.compile(
    r"\b(anyway|speaking\s+of|on\s+(?:a\s+|the\s+)?(?:different|another|unrelated|random)\s+(?:note|topic|subject|thing|question)|random\s+question|by\s+the\s+way|btw\b|forget\s+that|whatever,|oh\s+and|also,|meanwhile|completely\s+different|side\s+note|one\s+more\s+thing|that\s+reminds\s+me|so\s+anyway|anyway\s+back|but\s+anyway)\b",
    re.I,
)
_TOPIC_RESUME_RE = re.compile(
    r"\b(back\s+to\s+(?:that|the|our|this|what)|going\s+back\s+to|returning\s+to|as\s+i\s+was\s+saying|where\s+were\s+we|what\s+were\s+we\s+talking\s+about|that\s+(?:mentorship|codebase|architecture|ai|project|thing)\s+(?:thing|we\s+discussed)|the\s+earlier|that\s+thread|that\s+whole\s+thing)\b",
    re.I,
)

_REGISTER_PREF_MAP: dict[str, str] = {
    "less_formal": "casual",
    "neutral": "neutral",
    "casual": "casual",
    "serious": "serious",
    "concise": "concise",
    "technical": "technical",
    "less_playful": "neutral",
}


# ── Pragmatic analysis result ────────────────────────────────────────────────

@dataclass
class PragmaticAnalysis:
    acts: list[str] = field(default_factory=list)
    register: Register = field(default_factory=Register)
    temporal: TemporalContext = field(default_factory=current_temporal)
    is_social: bool = False          # pure low-content social (no task/question)
    is_question: bool = False
    has_command: bool = False
    retrieval_policy: str = "allowed"   # "forbidden" | "allowed"
    response_length: str = "normal"     # "minimal" | "short" | "normal" | "detailed"
    meta_signal: Optional[str] = None
    direct_address: bool = False
    emoji_only: bool = False


_QUESTION_RE = re.compile(
    r"(^|\s)(who|what|when|where|why|how|do|does|did|can|could|would|will|is|are|was|were|"
    r"should|have|has)\b|\?\s*$",
    re.I,
)
_COMMAND_VERBS = frozenset({
    "open", "close", "shut", "quit", "kill", "end", "launch", "start", "run",
    "search", "play", "pause", "resume", "stop", "mute", "unmute", "next",
    "previous", "focus", "switch", "create", "make", "write", "save", "copy",
    "paste", "select", "undo", "redo", "type", "take", "capture", "send",
    "delete", "list", "show", "go", "navigate", "refresh", "reload", "fold",
    "convert", "translate", "turn", "prepare", "build", "generate", "draft",
    "compose", "write", "put",
})


def detect_meta_signal(text: str) -> Optional[str]:
    """Return the meta-conversation control signal for `text`, if any."""
    low = re.sub(r"\s+", " ", text.strip().lower())
    if not low:
        return None
    for pattern, signal in _META_SIGNALS:
        if pattern.match(low):
            return signal
    return None


def strip_meta_prefix(text: str) -> tuple[Optional[str], str]:
    """Return (signal, remainder) when `text` starts with a meta-conversation
    control phrase. The remainder (original case preserved) is the actual
    request that follows the control phrase, e.g. "okay serious question,
    what's the weather?" -> ("serious_turn", "what's the weather?")."""
    low = re.sub(r"\s+", " ", text.strip().lower())
    if not low:
        return (None, "")
    for pattern, signal in _META_SIGNALS:
        m = pattern.match(low)
        if m:
            remainder = text[m.end():].lstrip(" ,:-\t")
            return (signal, remainder)
    return (None, "")


def analyze(text: str, normalized: str = "") -> PragmaticAnalysis:
    """Analyze a raw message into its conversational pragmatics.

    Deterministic, fast, no I/O. `normalized` (contractions expanded) is used
    as a second view for matching; `text` provides case/emoji/energy signals.
    """
    raw = text or ""
    low = _alpha(raw)
    norm_low = _alpha(normalized) if normalized else low
    words = low.split()
    acts: list[str] = []

    # Temporal
    temporal = current_temporal()

    # Register signals
    reg = _detect_register(raw, low, words)

    # Emoji-only reaction ("💀", "😂", "😭💀")
    emoji = _EMOJI_RE.findall(raw)
    emoji_only = bool(emoji) and not words
    if emoji_only:
        acts.append(ConversationAct.REACTION.value)

    # Meta-conversation control
    meta = detect_meta_signal(raw) or detect_meta_signal(normalized)
    if meta:
        acts.append(ConversationAct.META_CONVERSATION.value)

    # Topic movement: transition signals ("anyway", "speaking of", "by the
    # way", "on another note", "random question") and explicit returns
    # ("back to X", "going back to Y", "where were we") are FIRST-CLASS
    # discourse acts — the generator must follow a NEW subject instead of
    # tunneling on the old one, and must pick up the right thread on a
    # return. Generic family rules, not per-phrase dictionaries.
    if _TOPIC_TRANSITION_RE.search(low):
        acts.append(ConversationAct.TOPIC_TRANSITION.value)
    if _TOPIC_RESUME_RE.search(low):
        acts.append(ConversationAct.TOPIC_RESUME.value)

    # Direct address — only when the message actually ADDRESSES someone:
    # "hey kio", "kio open X", "u good kio", "yo bro", "ayy". A KIO mention
    # as a TOPIC ("KIO architecture", "Yo-Yo Ma") is never an address.
    _kio_addr = (
        re.match(r"^(?:hey|yo|hi|hello|ayy)\s+kio\b", raw, re.I)
        or re.match(r"^kio\s*[,!]?\s*(?:can|could|would|please|open|close|play|"
                    r"search|create|make|take|show|what|how|are|is|do|you)\b", raw, re.I)
        or re.search(r"\bkio\b\s*[.,!?]?\s*$", raw, re.I)
    )
    _greet_head = re.match(r"^(?:yo|hey|ayy|ayo|bro|bruh|dude|sup|man)\b", raw, re.I)
    if _kio_addr or (_greet_head and _is_greeting_utterance(raw, low, norm_low)):
        acts.append(ConversationAct.DIRECT_ADDRESS.value)

    # Greeting family (including glued / dashed / repeated forms)
    if not emoji_only:
        if _is_repeated_greeting(raw) or _is_greeting_utterance(raw, low, norm_low):
            acts.append(ConversationAct.GREETING.value)

    # Farewell
    if _is_farewell(raw, low):
        acts.append(ConversationAct.FAREWELL.value)

    # Wish / celebration ("Happy Onam", "Merry Christmas", "Eid Mubarak")
    # Social act — the LLM generates a natural occasion-aware response.
    if _is_wish_utterance(raw, low):
        acts.append(ConversationAct.WISH.value)

    # Thanks / apology
    if re.search(r"\b(thanks|thank you|thankyou|thx|ty|tysm|appreciate it)\b", low):
        acts.append(ConversationAct.THANKS.value)
    if re.search(r"\b(sorry|my bad|apologies|i apologize)\b", low):
        acts.append(ConversationAct.APOLOGY.value)

    # Agreement / disagreement / backchannel single words
    single = len(words) <= 2
    if single and not acts:
        collapsed = [_collapse(w) for w in words]
        # Single-word reactions only — a multi-word utterance like "Good
        # Charlotte" (the band) or "nice weather" is never a backchannel; the
        # second word must itself be casual social material.
        _two_ok = len(words) == 2 and all(
            w in _CASUAL_VOCAB for w in collapsed
        )
        if len(words) == 1 or _two_ok:
            if any(w in _AGREEMENT_TOKENS for w in collapsed):
                acts.append(ConversationAct.AGREEMENT.value)
            elif any(w in _DISAGREEMENT_TOKENS for w in collapsed):
                acts.append(ConversationAct.DISAGREEMENT.value)
            elif any(w in _CONFIRMATION_TOKENS for w in collapsed):
                acts.append(ConversationAct.SURPRISE.value)
            elif any(w in _SURPRISE_TOKENS for w in collapsed):
                acts.append(ConversationAct.SURPRISE.value)
            elif any(w in _AMUSEMENT_TOKENS for w in collapsed):
                acts.append(ConversationAct.AMUSEMENT.value)
            elif any(w in _FAREWELL_TOKENS for w in collapsed):
                acts.append(ConversationAct.FAREWELL.value)
            elif any(w in ("gotcha", "mhm", "mm", "alright", "aight", "kk", "okay", "ok") for w in collapsed):
                acts.append(ConversationAct.BACKCHANNEL.value)
            elif any(w in ("nice", "nicee", "cool", "good", "great", "awesome", "amazing",
                           "sick", "dope", "fire", "lit") for w in collapsed):
                acts.append(ConversationAct.ACKNOWLEDGMENT.value)

    # Amusement (multi-token: "lmaooo", "hahahaha", "that's hilarious") and
    # reaction emoji (💀/😭/😂/🤣/👀) are amusement/reaction acts — "bro 💀"
    # is a reaction, not a hello.
    if _AMUSEMENT_TOKENS & {_collapse(w) for w in words} \
            or re.fullmatch(r"(ha)+", low) \
            or re.search(r"\b(hilarious|funny|😂|🤣)\b", raw) \
            or bool(_AMUSEMENT_EMOJI & set(emoji)):
        if ConversationAct.AMUSEMENT.value not in acts:
            acts.append(ConversationAct.AMUSEMENT.value)
    if _EMOJI_RE.search(raw) and not words:
        if ConversationAct.REACTION.value not in acts:
            acts.append(ConversationAct.REACTION.value)

    # Surprise / frustration phrases
    if re.search(r"\b(wow|damn|whoa|no way|what the|what the hell|wtf|whattt|"
                 r"crazy|wild|insane|that's crazy)\b", low):
        if ConversationAct.SURPRISE.value not in acts:
            acts.append(ConversationAct.SURPRISE.value)
    # Confirmation-checking reactions ("fr?", "for real?", "no cap", "ong",
    # "seriously?") — disbelief/confirmation, rendered as a reaction.
    if re.search(r"\b(fr fr|for real|no cap|deadass|ong|fr)\s*\??$", low):
        if ConversationAct.SURPRISE.value not in acts:
            acts.append(ConversationAct.SURPRISE.value)
    if re.search(r"\b(wtf|what the hell|this sucks|so annoying|ugh|f\*ck|annoying|garbage|broken)\b", low):
        if ConversationAct.FRUSTRATION.value not in acts:
            acts.append(ConversationAct.FRUSTRATION.value)

    # Compliment
    if re.search(r"\b(you'?re (?:funny|great|awesome|good|amazing|the best)|nice (?:job|work)|good (?:bot|job)|love it|this is (?:awesome|amazing|great))\b", low):
        acts.append(ConversationAct.COMPLIMENT.value)

    # Complaint
    if re.search(r"\b(this (?:sucks|is (?:garbage|broken|terrible))|it'?s (?:broken|not working))\b", low):
        acts.append(ConversationAct.COMPLAINT.value)

    # Question / command. A casual greeting form that merely LOOKS like a
    # question ("what's good?", "how you doing?", "what's up?") is
    # pragmatically a greeting, not an information request — the greeting act
    # wins so these render as conversation, never as a query.
    is_question = bool(_QUESTION_RE.search(raw.strip())) or raw.strip().endswith("?")
    has_command = bool(words) and _looks_like_command(norm_low or low, words)
    if is_question and ConversationAct.GREETING.value in acts \
            and _is_greeting_utterance(raw, low, norm_low) and len(words) <= 4:
        is_question = False

    # OPINION REQUEST: the user is asking for KIO's own judgment, preference,
    # ranking or recommendation ("do you prefer X or Y?", "what's your take on
    # X?", "which is better?", "should I watch X?"). This is the signal that
    # lets the generator COMMIT to a position on first pass instead of
    # offering a balanced "both have their advantages" hedge — the exact
    # failure observed live ("live or recorded?" -> balanced until "pick
    # one"). Generic family rules, not per-phrase.
    _opinion = bool(re.search(
        r"\b(what\s+(?:do|did|would)\s+(?:you|we|they)\s+think\s+(?:about|of)|how\s+do\s+you\s+feel\s+(?:about|on)|"
        r"whats?\s+(?:your\s+)?(?:take|opinion|verdict|read|call|favourite|favorite)\b|"
        r"in\s+your\s+opinion|do\s+you\s+(?:prefer|like|love|enjoy|rate|think|believe)\b|"
        r"would\s+you\s+(?:recommend|pick|choose|go\s+with|rather)\b|"
        r"which\s+(?:[a-z0-9]+\s+){0,5}?(?:is|are|has|have)\s+(?:(?:actually|really|definitely|honestly)\s+)?(?:(?:the|a)\s+)?(?:better|best|worse|worst|more\s+enjoyable|more\s+fun|your\s+favourite|your\s+favorite)\b|"
        r"which\s+(?:is|are)\s+(?:better|best|worse|worst|the\s+best|your\s+favourite|your\s+favorite)\b|"
        r"whats?\s+(?:the\s+)?(?:best|worst|better|worse|most\s+overrated|most\s+underrated)\s+[a-z0-9 -]+\b|"
        r"(?:is|was|are|were)\s+(?:the\s+)?[a-z0-9].*?\s+(?:good|great|worth|overrated|underrated|any\s+good|cooked|over\s+hyped|worth\s+it)\b|"
        r"should\s+i\s+(?:watch|play|see|read|listen\s+to|try|buy|get)\b|"
        r"(?:^|\s)(?:or|vs|versus)\s*$)",
        low,
    )) or (len(words) <= 6 and re.search(r"\b(?:or|vs\.?|versus)\b", low) and re.search(r"\?$", raw.strip()))
    if _opinion and is_question:
        acts.append(ConversationAct.OPINION_REQUEST.value)

    # Pure social decision: only social acts, no question, no command, low content
    _SOCIAL_ACTS = {
        ConversationAct.GREETING.value, ConversationAct.FAREWELL.value,
        ConversationAct.ACKNOWLEDGMENT.value, ConversationAct.AGREEMENT.value,
        ConversationAct.DISAGREEMENT.value, ConversationAct.AFFIRMATION.value,
        ConversationAct.THANKS.value, ConversationAct.APOLOGY.value,
        ConversationAct.BACKCHANNEL.value, ConversationAct.SURPRISE.value,
        ConversationAct.AMUSEMENT.value, ConversationAct.REACTION.value,
        ConversationAct.COMPLIMENT.value, ConversationAct.PLAYFUL_BANTER.value,
        ConversationAct.TEASING.value, ConversationAct.DIRECT_ADDRESS.value,
        ConversationAct.META_CONVERSATION.value, ConversationAct.SMALL_TALK.value,
        ConversationAct.REQUEST_ATTENTION.value, ConversationAct.WISH.value,
    }
    is_social = bool(acts) and not is_question and not has_command \
        and all(a in _SOCIAL_ACTS for a in acts) \
        and len(words) <= 6
    # Proper-noun guard: "Good Charlotte" (band), "Nice One" — a message that
    # reads as a proper name (2+ capitalized words) is never pure social speech
    # unless it is actually a greeting/farewell/wish.
    if is_social and not (ConversationAct.GREETING.value in acts
                          or ConversationAct.FAREWELL.value in acts
                          or ConversationAct.WISH.value in acts):
        _proper_toks = re.findall(r"\b[A-Z][a-z]+\b", raw)
        if len(_proper_toks) >= 2:
            is_social = False

    # Retrieval policy: pure social speech never needs retrieval
    retrieval_policy = "forbidden" if is_social else "allowed"

    # Response length follows social function
    if is_social:
        response_length = "minimal" if len(words) <= 3 else "short"
    elif is_question or has_command:
        response_length = "normal"
    else:
        response_length = "short"

    if _is_repeated_greeting(raw):
        reg.energy = min(2, reg.energy + 1)
        reg.playfulness = max(reg.playfulness, 1)

    direct = ConversationAct.DIRECT_ADDRESS.value in acts
    if not acts:
        acts.append(ConversationAct.STATEMENT.value)
    # Direct-address is informational (kept in the field); it never dictates
    # the response act by itself.
    acts = [a for a in acts if a != ConversationAct.DIRECT_ADDRESS.value] or acts

    return PragmaticAnalysis(
        acts=acts,
        register=reg,
        temporal=temporal,
        is_social=is_social,
        is_question=is_question,
        has_command=has_command,
        retrieval_policy=retrieval_policy,
        response_length=response_length,
        meta_signal=meta,
        direct_address=direct,
        emoji_only=emoji_only,
    )


def _is_greeting_utterance(raw: str, low: str, norm_low: str) -> bool:
    """Greeting detection that tolerates typos/gluing/case variants.

    'goodmorning', 'gud morning', 'mornin', 'heyyy', 'yooo', 'wassup',
    'gm', 'gmorning', 'good-morning', 'good_morning', 'sup', 'ayy',
    'how are you', 'how's it going', 'u good' ... all count as greetings.
    Never fires when a proper noun follows ('Good Morning America' has the
    capitalized proper noun and is handled by the caller's whole-utterance
    intent; 'yo-yo ma' fails because 'ma' is not a greeting token).
    """
    flat = re.sub(r"[\s\-_,.!?;:]+", " ", low).strip()
    if not flat:
        return False
    toks = flat.split()
    collapsed = [_collapse(t) for t in toks]

    # Single greeting token (or repeated-letter variant)
    if len(toks) == 1:
        if collapsed[0] in _GREETING_TOKENS:
            return True
        return False

    # 'good morning' family (incl. glued 'goodmorning' already split? handled
    # via the collapsed token test above for single tokens)
    head = " ".join(collapsed[:2])
    if head in ("good morning", "good afternoon", "good evening", "good night",
                "gud morning", "gud afternoon", "gud evening", "gud night"):
        # Whole-utterance check: 'Good Morning America' / 'Good Morning
        # Football' (real entities) are NOT greetings — a capitalized proper
        # noun following the day-progress phrase demotes the greeting so the
        # full phrase keeps its entity meaning.
        orig_toks = re.findall(r"[A-Za-z]+", raw)
        if len(orig_toks) > 2:
            tail = orig_toks[2:]
            if any(t and t[0].isupper() and t.lower() not in ("kio", "bro", "joel")
                   for t in tail):
                return False
        return True

    # 'how are you' / 'what's up' / 'what's good' family — a greeting ONLY
    # when the utterance IS the phrase plus an optional benign tail (address
    # word, "today", "with you", ...). Content after the phrase demotes it:
    # "what's good to eat?" / "what's good around here?" / "what's good for
    # a sore throat?" are real recommendation/info requests, never greetings.
    # `flat` has punctuation/apostrophes stripped: "what's good" -> "whats good".
    _how_tail_ok = {"bro", "bruh", "broo", "dude", "man", "kio", "there",
                    "today", "tonight", "doing", "you", "with", "yall",
                    "everyone", "everybody"}
    # Leading attention token tolerated: "so what's good?" / "hey what's up" /
    # "okay so what's good" — the phrase still starts the real utterance.
    _lead = re.match(r"^(?:so|hey|heyy|yo|yoo|ayy|ayo|ok|okay|alright|aight)\s+", flat)
    _how_src = flat[_lead.end():] if _lead else flat
    _how_toks = _how_src.split()
    _collapsed_how = [_collapse(t) for t in _how_toks]
    _HOW_FAMILY = (
        "how are you doing today", "how is your day going", "how are you doing",
        "how are you", "how are ya", "how are things", "how is it going",
        "hows it going", "how is everything", "how have you been",
        "what is up", "whats up", "what is good", "whats good",
        "what we saying", "how you doing", "how u doing", "you good",
        "u good", "how was your day", "how is your day", "how is your day so far",
        "how has your day been", "how is everything going", "how are things going",
        "how are you feeling", "how you feel", "how are you today",
    )
    for _h in _HOW_FAMILY:
        if _collapsed_how == _h.split():
            return True
        if len(_collapsed_how) > len(_h.split()) and _collapsed_how[:len(_h.split())] == _h.split():
            _tail = _collapsed_how[len(_h.split()):]
            if all(t in _how_tail_ok for t in _tail):
                return True

    # All tokens are greeting tokens ('hey there', 'yo bro', 'sup man')
    if len(toks) <= 4 and all(t in _GREETING_TOKENS for t in collapsed):
        return True
    return False


# Generic wish/celebration detection — "Happy Onam", "Merry Christmas",
# "Eid Mubarak", "Happy Birthday", "Happy [any occasion]".
# This is a SOCIAL ACT, not an entity query. The response should be
# generated by the LLM using its knowledge of the occasion, not by a
# deterministic template.
_WISH_OPENERS = frozenset({
    "happy", "merry", "blessed", "joyful", "cheerful", "wonderful",
    "great", "fantastic", "amazing", "beautiful",
})
_WISH_TAILORS = frozenset({
    "mubarak", "mubarek", "subh", "shubh",
})

def _is_wish_utterance(raw: str, low: str) -> bool:
    """Detect social wishes/celebrations: 'Happy Onam', 'Merry Christmas',
    'Eid Mubarak', 'Happy Birthday', etc.

    Generic pattern, not a holiday dictionary. Any 'Happy [X]' or
    '[X] Mubarak' is a social wish — the LLM uses its knowledge of
    the occasion to respond naturally.
    """
    flat = re.sub(r"[\s\-_,.!?;:]+", " ", low).strip()
    if not flat:
        return False
    words = flat.split()
    if len(words) < 2 or len(words) > 6:
        return False
    # 'Happy [occasion]' / 'Merry [occasion]'
    if words[0] in _WISH_OPENERS:
        return True
    # '[occasion] Mubarak' / 'Eid Mubarak'
    if words[-1] in _WISH_TAILORS:
        return True
    return False


def _is_farewell(raw: str, low: str) -> bool:
    toks = low.split()
    collapsed = [_collapse(t) for t in toks]
    if len(toks) == 1 and collapsed[0] in _FAREWELL_TOKENS:
        return True
    if re.search(r"\b(gotta go|see ya|see you|catch you later|talk to you later|have a good (?:one|night)|good night|goodnight)\b", low):
        return True
    return False


def _looks_like_command(low: str, words: list[str]) -> bool:
    """A command verb ANYWHERE in the utterance means this is not pure social
    speech: 'yo open Telegram', 'ayy create a spreadsheet', 'bro switch to VS
    Code' must never be classified as a bare greeting."""
    if not words:
        return False
    if any(_collapse(w) in _COMMAND_VERBS for w in words):
        return True
    if re.search(r"\b(tell me|show me|open up|fire up|bring up)\b", low):
        return True
    return False


# ── Register detection ───────────────────────────────────────────────────────

_SLANG_RE = re.compile(
    r"\b(yo|bro|bruh|dude|gonna|wanna|gotta|kinda|sorta|idk|ngl|tbh|fr|rn|"
    r"wbu|wyd|bet|cap|sus|lit|fire|dope|vibes|vibe|af|asf|lowkey|highkey|"
    r"lol|lmao|lmfao|rofl|hella|mad|straight|fr fr|no cap|ong|dawg|homie)\b",
    re.I,
)
_PROFANITY_RE = re.compile(
    r"\b(fuck|fucking|f\*ck|shit|bitch|ass|damn|hell|crap|wtf|tf|what the hell)\b",
    re.I,
)
_TECHNICAL_RE = re.compile(
    r"\b(architecture|process|module|memory|ram|cpu|gpu|latency|throughput|"
    r"exception|stack trace|debug|deploy|compile|api|endpoint|database|"
    r"function|class|variable|algorithm|thread|queue|cache|binary|config|"
    r"regression|refactor|schema|server|client|socket|kernel|processes|"
    r"task manager|performance|benchmark)\b",
    re.I,
)
_FORMAL_RE = re.compile(
    r"\b(could you|would you|please|kindly|perhaps|appreciate|"
    r"i would like|i'd like|may i|if possible|thank you for|regards|"
    r"nevertheless|furthermore|however|regarding)\b",
    re.I,
)
_FORMAL_QUESTION_RE = re.compile(r"^(could|could you|would|would you|may|please)\b", re.I)

# Distress / low / reflective disclosure markers: negative-affect states and
# emotionally loaded situations. Signal-only — never a diagnosis. Matched
# FIRST in register emotion so "this week has been rough" / "i've been lying
# awake questioning whether..." are treated seriously instead of "lighthearted".
_DISTRESS_RE = re.compile(
    r"\b(rough|dread(?:ing)?|exhausted|exhausting|burn(?:t)?\s*out|burned\s*out|"
    r"overwhelmed|hopeless|miserable|awful|terrible|horrible|hate(?:d|s|ing)?|"
    r"stuck|frustrated|frustrating|stressed|stressful|anxious|worried|depressed|"
    r"unhappy|drained|fed up|questioning (?:whether|everything)|lying awake|"
    r"can'?t sleep|no sleep|not sleeping|wanna quit|want to quit|feel like giving up|"
    r"giving up|can'?t take it|had enough|so done|went wrong|went badly|broke up|"
    r"worse day|worst day|don'?t know what to do|ruined|so tired of|sick of)\b",
    re.I,
)
# Sarcasm/irony detection: positive irony openers ("wow great", "oh
# wonderful", "perfect", "just what I needed", "so glad") paired with
# hyperbolic negative consequences ("my life is ruined", "total disaster",
# "everything's broken", "can't trust you") in a trivial context reads as
# sarcasm, not genuine distress. Generic polarity-contrast family rule.
_SARCASM_RE = re.compile(
    r"\b(wow\s+(?:great|wonderful|perfect|awesome|just\s+what\s+i\s+needed)|"
    r"oh\s+(?:great|wonderful|perfect|lovely|brilliant|fantastic)|"
    r"(?:great|perfect|wonderful|lovely|awesome|fantastic|amazing),?\s+(?:just\s+)?what\s+i\s+needed|"
    r"just\s+what\s+i\s+needed|that'?s\s+just\s+great|perfect,?\s+exactly\s+what\s+i\s+needed|"
    r"so\s+(?:glad|happy|excited)\b|what\s+fun\b|great,?\s+another)\b",
    re.I,
)
# The negative leg of the irony: either hyperbolic consequence ("my life is
# ruined") or a mundane negative event ("the build broke again", "another
# meeting") that contrasts with the positive opener. Both legs are required
# so a lone "wow great" (genuine excitement) is never misread.
_IRONY_SCALE_RE = re.compile(
    r"\b(ruined|disaster|everything'?s?\s+broken|can'?t\s+trust|life\s+is\s+over|"
    r"worst\s+(?:day|thing)|total\s+disaster|point\s+of\s+anything|nothing\s+works|"
    r"so\s+done\b|broke\s+again|failed\s+again|another\s+(?:meeting|deadline|build|email|issue)|"
    r"went\s+wrong|again\b|today\b|meeting|deadline|schedule|traffic|queue|error)\b",
    re.I,
)

# First-person low-affect framing: "i'm tired" / "i feel sad" / "i am so
# overwhelmed" are emotional disclosures (bare "tired" mid-tech-talk is not).
# Negative lookaheads keep specific complaints out: "i'm tired of waiting"
# and "i'm done with the pizza" are about a thing, not a low state.
_DISTRESS_FIRST_PERSON_RE = re.compile(
    r"\b(?:i(?:'m| am)|i feel|feeling)\s+(?:so\s+|really\s+|very\s+|pretty\s+|kinda\s+)?"
    r"(?:tired(?!\s+of\b)|sad|down|low|overwhelmed|stressed|exhausted|drained|miserable|awful|over it|done(?=\s*$|\s+with\s+(?:this|it|everything)|\s+for\s+the\s+day))\b",
    re.I,
)


def _detect_register(raw: str, low: str, words: list[str]) -> Register:
    formality = 0
    playfulness = 0
    technicality = 0
    energy = 0
    emotion: Optional[str] = None

    if _SLANG_RE.search(low):
        formality -= 1
        playfulness += 1
    if _PROFANITY_RE.search(low):
        formality -= 1
        energy += 1
    if _EMOJI_RE.search(raw):
        playfulness += 1
    if _FORMAL_RE.search(low):
        formality += 1
        playfulness = max(playfulness - 1, 0)
    if _TECHNICAL_RE.search(low):
        technicality = 1
        playfulness = max(playfulness - 1, 0)

    # Stretched letters / caps / exclamations → energy + playfulness.
    # Runs of 3+ ("yooo", "heyyy", "broooo") are emphasis; runs of exactly 2
    # are ordinary English words ("been", "keep", "engineer", "good") and
    # must never push a serious disclosure into "lighthearted" — live bug:
    # "I've been lying awake thinking about whether I even want to keep being
    # an engineer" got playfulness=1 from 'been'/'keep'/'engineer' and KIO
    # replied with upbeat generic advice.
    repeats = sum(1 for w in words if _COLLAPSE3_RE.search(w))
    if repeats:
        energy += 1
        playfulness += 1
    if raw.isupper() and len(raw) >= 3:
        energy += 1
    if raw.count("!") >= 2:
        energy += 1
    if _AMUSEMENT_TOKENS & {_collapse(w) for w in words} or _EMOJI_RE.search(raw):
        playfulness = min(playfulness + 1, 2)
    if _QUESTION_RE.search(raw) and not _FORMAL_QUESTION_RE.match(raw.strip()):
        pass  # casual questions stay casual

    # Emotion label (inferred, calibrated — never a diagnosis)
    # Sarcasm/irony is checked BEFORE distress: "wow great, my whole life is
    # ruined" (about a trivial topic) is contradictory polarity — positive
    # surprise opener + negative hyperbole — NOT a genuine low moment. Live
    # bug: "my whole life is ruined. forget pineapple..." triggered the
    # distress path and KIO replied with earnest empathy + a forced question.
    # The presence of a strong positive word alongside a strong negative one
    # in the same short utterance signals irony; genuine disclosures never
    # pair "great/wonderful/perfect" with "ruined/disaster".
    if _SARCASM_RE.search(low) and _IRONY_SCALE_RE.search(low):
        emotion = "sarcasm"
        playfulness = max(playfulness, 1)
    elif _DISTRESS_RE.search(low) or _DISTRESS_FIRST_PERSON_RE.search(raw):
        emotion = "distress"
        playfulness = 0
        energy = min(energy, 1)
    elif _AMUSEMENT_TOKENS & {_collapse(w) for w in words} or re.search(r"😂|🤣", raw):
        emotion = "amusement"
    elif re.search(r"\b(wow|damn|whoa|no way|whattt)\b", low):
        emotion = "surprise"
    elif re.search(r"\b(wtf|what the hell|this sucks|ugh|annoying|f\*ck)\b", low):
        emotion = "frustration"
    elif re.search(r"\b(omg|yess|awesome|amazing|so excited|can't wait)\b", low):
        emotion = "excitement"

    formality = max(-2, min(2, formality))
    playfulness = max(0, min(2, playfulness))
    energy = max(0, min(2, energy))
    return Register(formality=formality, playfulness=playfulness,
                    technicality=technicality, energy=energy, emotion=emotion)


# ── Discourse state (session-attached) ───────────────────────────────────────

def effective_register(ctx, analysis: PragmaticAnalysis) -> Register:
    """Blend the user's explicit style preference (meta signals) with the
    current message register. The explicit preference wins — 'be serious'
    persists until the user lifts it; otherwise KIO follows the message."""
    pref = getattr(ctx, "register_preference", "auto") if ctx is not None else "auto"
    if pref == "serious":
        return Register(formality=1, playfulness=0, technicality=analysis.register.technicality,
                        energy=0, emotion=None)
    if pref == "casual":
        return Register(formality=-1, playfulness=max(1, analysis.register.playfulness),
                        technicality=analysis.register.technicality, energy=analysis.register.energy,
                        emotion=analysis.register.emotion)
    if pref == "playful":
        return Register(formality=-1, playfulness=2, technicality=0, energy=1, emotion="amusement")
    if pref == "formal":
        return Register(formality=2, playfulness=0, technicality=analysis.register.technicality,
                        energy=0, emotion=None)
    if pref == "technical":
        return Register(formality=0, playfulness=0, technicality=1, energy=0, emotion=None)
    if pref == "concise":
        return Register(formality=analysis.register.formality, playfulness=0,
                        technicality=analysis.register.technicality, energy=0, emotion=None)
    if pref == "neutral":
        return Register(formality=0, playfulness=0, technicality=analysis.register.technicality,
                        energy=0, emotion=None)
    return analysis.register


def observe_exchange(decision, result: dict, ctx) -> None:
    """Update session discourse state after any pipeline exchange.

    Called from the response composer so EVERY message (action, query,
    conversation) advances discourse state — this is what makes a bare 'nice'
    after 'open excel' resolve against the concrete action rather than a
    generic conversational reply.
    """
    if ctx is None:
        return
    try:
        text = getattr(decision, "raw_text", "") or getattr(decision, "normalized_text", "")
        analysis = analyze(text, getattr(decision, "normalized_text", ""))
        acts = analysis.acts
        primary = acts[0] if acts else "statement"
        ctx.last_user_act = primary
        if analysis.register.energy:
            ctx.social_energy = min(5, (getattr(ctx, "social_energy", 0) or 0) + 1)
        else:
            ctx.social_energy = max(0, (getattr(ctx, "social_energy", 0) or 0) - 1)
        # KIO's act: what we actually did
        action = str(result.get("action", "") or "")
        if getattr(decision, "intent_type", None) is not None:
            intent = str(getattr(decision, "intent_type", ""))
            if "GREETING" in intent:
                action = "greeting"
            elif "SOCIAL" in intent and not action:
                action = "chat"
        if not action:
            action = "chat"
        ctx.last_kio_act = action
        # Remember a location mention for "what time is it there" resolution
        loc = _extract_location(text)
        if loc:
            ctx.last_location = loc
    except Exception:
        pass


def _extract_location(text: str) -> Optional[str]:
    """Best-effort named-location extraction from a user message."""
    if not text:
        return None
    m = re.search(r"\b(?:in|at|for|from)\s+([A-Z][a-z]+(?:\s+[A-Z][a-z]+)?)\b", text)
    if m:
        return m.group(1).strip().lower()
    return None


# ── Natural social reply rendering ───────────────────────────────────────────

def render_social_reply(analysis: PragmaticAnalysis, ctx, user_text: str = "") -> Optional[str]:
    """Deterministic, register/temporal/discourse-aware reply for pure social
    messages. Returns None when the message is not one KIO should answer
    deterministically (caller falls back to the LLM). Never narrates the
    classification — it participates."""
    acts = analysis.acts
    if not analysis.is_social or not acts:
        return None

    # Meta-conversation control is handled by handle_meta_signal; a pure
    # meta message ('chill', 'be serious') is still 'social' but needs the
    # state update, so handle it there and return its reply.
    if analysis.meta_signal:
        return handle_meta_signal(analysis.meta_signal, ctx)

    energy = analysis.register.energy
    playful = analysis.register.playfulness >= 1
    period = analysis.temporal.period
    low_user = (user_text or "").strip().lower()
    raw_user = user_text or ""

    # ── Farewell ──
    if ConversationAct.FAREWELL.value in acts:
        base = random.choice(["cya 😎", "later bro", "peace ✌️", "see ya", "gn 😴", "night!"])
        if re.search(r"\bgood\s?night\b", low_user) or low_user in ("gn", "night", "goodnight"):
            return random.choice(["night 😴", "gn, sleep well", "night 🌙"])
        return base

    # ── Amusement / reaction — emotional acts outrank a co-occurring greeting
    #    ('bro 💀' is a reaction, not a hello).
    if ConversationAct.AMUSEMENT.value in acts or ConversationAct.REACTION.value in acts:
        return _render_amusement(analysis, ctx, low_user)

    # ── Thanks ──
    if ConversationAct.THANKS.value in acts:
        if playful:
            return random.choice(["anytime 😎", "np!", "anytime bro", "👍", "always 😄"])
        return random.choice(["anytime 😄", "no problem", "you're welcome!"])

    # ── Apology ──
    if ConversationAct.APOLOGY.value in acts:
        return random.choice(["no worries 👍", "all good 😄", "you're fine, no stress"])

    # ── Disagreement ──
    if ConversationAct.DISAGREEMENT.value in acts:
        if playful:
            return random.choice(["fair 😭", "nahhh 😂", "okay okay, whatever you say 😄"])
        return random.choice(["fair enough", "okay, your call"])

    # ── Greeting ──
    if ConversationAct.GREETING.value in acts:
        return _render_greeting(analysis, ctx, low_user, raw_user)

    # ── Agreement / backchannel / acknowledgment ──
    if (ConversationAct.AGREEMENT.value in acts
            or ConversationAct.BACKCHANNEL.value in acts
            or ConversationAct.ACKNOWLEDGMENT.value in acts):
        return _render_acknowledgment(analysis, ctx, playful, low_user)

    # ── Surprise ──
    if ConversationAct.SURPRISE.value in acts:
        if playful:
            return random.choice(["right?? 😭", "yeah 😅", "i know right", "crazy"])
        return random.choice(["yeah, right?", "indeed"])

    # ── Compliment ──
    if ConversationAct.COMPLIMENT.value in acts:
        return random.choice(["lol thanks 😎", "appreciate it 😄", "🙏"])

    return None


def _render_greeting(analysis: PragmaticAnalysis, ctx, low_user: str, raw_user: str = "") -> str:
    energy = analysis.register.energy
    playful = analysis.register.playfulness >= 1
    period = analysis.temporal.period

    # Day-progress greeting — temporal-aware, never a blind mirror
    if re.search(r"\bgood[\s\-]*?(morning|afternoon|evening|night)\b", low_user) \
            or "mornin" in low_user or low_user in ("gm", "gmorning"):
        if "morning" in low_user or low_user in ("gm", "gmorning") or "mornin" in low_user:
            if period in ("night", "late_night"):
                return "morning 😭 you're still awake?"
            return "morning 😎"
        if "afternoon" in low_user:
            return random.choice(["afternoon 😎", "good afternoon!"])
        if "evening" in low_user:
            return random.choice(["evening 😎", "yo, good evening"])
        if "night" in low_user or low_user in ("gn", "goodnight"):
            return random.choice(["night 😴", "gn 🌙", "night! sleep well"])

    # How-are-you family — respond truthfully, then hand back
    if re.search(r"\b(how are you|how's it going|how is it going|how are things|"
                 r"how have you been|how you doing|what's up|what is up|wassup|"
                 r"whats up|how's your day|how is your day|sup)\b", low_user):
        if playful:
            return random.choice(["all good on my end 😎 you?", "yo 😎 not much, what's up?",
                                  "chillin 😄 what's good?"])
        return random.choice(["all good on my end. you?", "running fine — what's up with you?"])

    # Generic greeting — mirror energy and caps
    if raw_user.isupper() and len(raw_user.strip()) <= 12:
        return random.choice(["YOOO 😂", "AYYY 😎", "YOOOO", "YO 😂"])
    if energy >= 2 or (ctx is not None and (getattr(ctx, "social_energy", 0) or 0) >= 3):
        return random.choice(["YOOO 😂", "yoooo", "AYYY 😎", "yo yo 😂"])
    if playful:
        return random.choice(["yo 😎", "ayy what's good?", "heyy 😄", "yo 🫡", "sup?"])
    return random.choice(["yo", "hey 😄", "hi!", "hey there"])


def _render_acknowledgment(analysis: PragmaticAnalysis, ctx, playful: bool, user_low: str = "") -> str:
    """Backchannels ('nice', 'cool', 'sure', 'fair', 'gotcha') resolve against
    what actually just happened, not the word itself."""
    last_kio_act = getattr(ctx, "last_kio_act", "") if ctx is not None else ""
    last_success = getattr(ctx, "last_success", False) if ctx is not None else False
    low = (getattr(ctx, "last_user_input", "") or "").lower() if ctx is not None else ""

    _ACTION_ACTS = ("open_app", "close_app", "execute_capability", "browser",
                    "media", "desktop", "create_document", "type", "file",
                    "utility", "search_web", "search_youtube", "system", "camera")
    after_action = last_success and any(a in last_kio_act for a in _ACTION_ACTS)
    after_info = last_kio_act in ("converse", "elaborate", "knowledge",
                                  "information_query", "entity_query", "chat", "greeting")

    if re.search(r"\b(sure|ok|okay|kk|gotcha|alright|aight|mhm|mm)\b", user_low):
        return random.choice(["👍", "yep", "sounds good", "got it 😎"]) if playful else random.choice(["got it.", "👍", "sure thing"])
    if re.search(r"\b(fair|facts|true|exactly|right|bet|agreed|correct)\b", user_low) \
            or "makes sense" in user_low:
        return random.choice(["fair 😂", "facts 😎", "right?", "exactly", "bet 😎"])
    # nice / cool / good / great / awesome — reaction to what just happened
    if after_action:
        return random.choice(["😎", "yep, done", "👍", "nice"])
    if after_info:
        return random.choice(["right??", "yeah 😄", "glad it helped", "fr"])
    return random.choice(["😎", "👍", "nice"])


def _render_amusement(analysis: PragmaticAnalysis, ctx, low_user: str) -> str:
    energy = analysis.register.energy
    if re.search(r"💀", low_user):
        return random.choice(["💀", "bro 😭", "nahhh 💀"])
    if re.search(r"😂|🤣", low_user) or re.search(r"\b(lol|lmao|rofl|haha)\b", low_user):
        if energy >= 2:
            return random.choice(["LMAOOO 😂", "lmaooo", "😭😂"])
        return random.choice(["😂", "lol right", "😭"])
    if re.search(r"😭", low_user):
        return random.choice(["😭", "bro 😭", "nooo 😭"])
    return random.choice(["😂", "😎", "lol"])


# ── Meta-conversation: actually change behavior ──────────────────────────────

def handle_meta_signal(signal: str, ctx) -> Optional[str]:
    """Apply a meta-conversation control signal: update the persistent
    register preference and reply naturally (participate, never explain)."""
    pref = _REGISTER_PREF_MAP.get(signal)
    if ctx is not None and pref:
        ctx.register_preference = pref
    replies = _META_REPLIES.get(signal)
    if replies:
        return random.choice(replies)
    return None


def discourse_block(ctx, analysis: Optional[PragmaticAnalysis] = None, user_text: str = "") -> str:
    """Build the conversational-context block injected into the LLM so it
    participates in the right register/temporal/discourse frame."""
    if analysis is None:
        analysis = analyze(user_text or "")
    eff = effective_register(ctx, analysis)
    lines = [
        "Conversation context:",
        f"- Time: {analysis.temporal.period} ({analysis.temporal.time_label}).",
        f"- User's current register: {analysis.register.label}.",
        f"- Effective register for your reply: {eff.label}.",
    ]
    if ctx is not None:
        if getattr(ctx, "last_user_act", ""):
            lines.append(f"- Your previous act: {ctx.last_kio_act or 'reply'} (their act: {ctx.last_user_act}).")
    reg_rule = _register_instruction(eff, analysis)
    if reg_rule:
        lines.append(reg_rule)
    # OPINION REQUEST: commit on first pass. "Do you prefer live or recorded
    # music?" is a direct ask for KIO's judgment — the reply must OPEN with a
    # clear position and then the reason, not a balanced "both have their
    # advantages" hedge that waits for the user to say "pick one".
    acts = set(analysis.acts or [])
    if ConversationAct.OPINION_REQUEST.value in acts:
        lines.append(
            "The user is directly asking for YOUR opinion / preference / "
            "recommendation. Commit on the first pass: open with a clear "
            "position ('I'd take X', 'X wins', 'I'd pick X'), then give the "
            "main reason, then acknowledge a strong counterpoint only if it "
            "genuinely sharpens the answer. Do NOT start with 'both are good', "
            "'it depends', 'there's no right answer', or a symmetric list of "
            "both sides' pros and cons — that reads as dodging the question. "
            "Legitimate uncertainty (can't know, not confirmed) is fine to name, "
            "but a preference question deserves a preference."
        )
    # Topic movement is a first-class discourse signal: a transition marker
    # means FOLLOW the new subject (never keep deepening the old one — the
    # topic-tunnel failure); a resume marker means PICK UP the earlier thread
    # named by the user instead of treating it as brand new.
    # Resume wins over transition: "anyway, back to the mentorship thing"
    # contains BOTH signals but the user's intent is to resume, not switch.
    if ConversationAct.TOPIC_RESUME.value in acts:
        lines.append(
            "The user is returning to an earlier thread (back to / as I was "
            "saying / where were we). Pick up THAT thread with the context "
            "already established — do not treat it as a new topic and do not "
            "ask them to restate the background."
        )
    elif ConversationAct.TOPIC_TRANSITION.value in acts:
        lines.append(
            "The user just signaled a subject change (anyway / speaking of / "
            "by the way / random question / ...). Follow them cleanly: respond "
            "to the NEW subject they raised. Do not drag the previous topic "
            "back into your reply, do not keep explaining the old topic, and do "
            "not ask a question that reopens it."
        )
    # REFERENT / CALLBACK / COMPARISON frames (conversational continuity):
    # the user's message often refers to prior discourse instead of naming
    # things fresh ("wbt fight club", "watching it tonight instead of arrival
    # u said of", "that other one", "would you pick it over X"). The model
    # must resolve these against the 'Recent conversation' section — generic
    # morphology, never per-entity cases, never an abbreviation dictionary.
    _ref = re.compile(
        r"\binstead\b|\bu\s+said\b|\byou\s+said\b|\byou\s+recommend|\byou\s+suggest|"
        r"\byou\s+mention|\bthe\s+ones?\s+you\b|\bthat\s+(?:other\s+)?one\b|"
        r"\bthe\s+other\s+one\b|\bthe\s+(?:first|second|third|fourth|fifth)\s+one\b|"
        r"\bgoing\s+back\s+to\b|\bback\s+to\s+(?:that|this|it|the)\b|\brather\s+than\b|"
        r"\bwould\s+you\s+(?:pick|choose|go\s+with)\b|\bover\s+(?:it|that|this)\b|"
        r"\bwbt\b|\bwbu\b|\bearlier\b|"
        # Role referents: "what else has that director/author/actor made",
        # "who directed that" — the role noun points back at the most
        # recently discussed subject (the movie/book/game just mentioned),
        # so the LLM must resolve the ROLE against the current thread, not an
        # older entity still in the window (live: "that director" after
        # Annihilation answered with Christopher Nolan because no referent
        # instruction was injected and the LLM anchored on an earlier
        # Interstellar exchange). Generic determiner + role-noun morphology,
        # never per-entity.
        r"\b(?:that|this)\s+(?:director|author|writer|creator|actor|actress|star|cast|"
        r"band|artist|singer|rapper|producer|studio|label|developer|team|coach|manager|"
        r"player|screenwriter|composer|cinematographer)\b|"
        r"\b(?:directed|written|created|produced|composed)\s+(?:by\s+)?(?:that|this)\b",
        re.I,
    )
    # KIO's OWN recent recommendations are explicit discourse state (brief
    # Section 9): "I'd go with Arrival" must stay reachable so a later "what
    # about Fight Club instead?" compares against it. Generic extraction from
    # the recent replies — never a per-entity mapping.
    _rec_subjects: list[str] = []
    if ctx is not None:
        try:
            # Broad recommendation-shape extraction: "I'd go with Arrival",
            # "Try The Royal Biryani House", "I'd recommend X", "go with X".
            # Any reply that COMMITS to a named candidate is discourse state —
            # a later "something different" refines it. The old regex only
            # caught "I'd go with X" shapes, so "Try X" recommendations were
            # never registered and a bare "Something completely different"
            # lost the thread (live bug).
            # Character class stops at sentence punctuation (.,!?) so the
            # captured candidate is the NAMED ENTITY, not trailing prose
            # ("try The Royal Biryani House, which..." -> "The Royal Biryani
            # House", never "...House, which...").
            _rec_re = re.compile(
                r"(?:i'd|i\s+would|i'll|i\s+would\s+recommend)\s+(?:go\s+with|pick|choose|take|recommend(?:ed)?\s+[a-z]+\s+)?"
                r"([A-Z][A-Za-z0-9 .'\-]{1,40})\b|"
                r"\b(?:try|go\s+with|pick)\s+([A-Z][A-Za-z0-9 .'\-]{1,40})\b",
                re.I,
            )
            for _u, _r in (ctx.get_history_window(10) or []):
                for _m in _rec_re.finditer(_r or ""):
                    # Two capture groups (the "I'd go with X" shape and the
                    # "try X" shape); either may be None, and a None.strip()
                    # would abort the WHOLE extraction via the except guard —
                    # which is exactly why "Try X" recommendations never
                    # registered. Pick whichever group matched.
                    _cand = (_m.group(1) or _m.group(2) or "").strip().strip(".,!?;:")
                    # Truncate prose continuations: the regex allows spaces
                    # and hyphens (multi-word names, "The Three-Body
                    # Problem"), so trim at the typical clause markers
                    # (" - ", " — ", " , ") to keep the NAMED ENTITY
                    # only.
                    for _sep in (" - ", " \u2014 ", " \u2013 ", " , "):
                        if _sep in _cand:
                            _cand = _cand.split(_sep, 1)[0]
                    if _cand and _cand not in _rec_subjects:
                        _rec_subjects.append(_cand)
        except Exception:
            pass
    if _rec_subjects:
        lines.append(
            "Your recent recommendations (from this conversation): "
            + ", ".join(_rec_subjects[:4])
            + "."
        )
        # Bare refinement request inside an active recommendation thread:
        # "Something completely different", "something darker", "something
        # shorter" — the user is MODIFYING the standing recommendation
        # (same category, new constraint), not changing topic. Live bug: a
        # restaurant thread asked "Something completely different" and KIO
        # answered with black-hole trivia instead of another restaurant,
        # because the bare phrase carried no explicit referent. The rule is
        # morphological ("something" + modifier), never category-specific.
        if re.match(r"^(?:something|anything|something\s+else)\b.*", (user_text or "").strip(), re.I):
            lines.append(
                "The user is refining a standing recommendation ('something "
                "darker', 'something completely different', 'something "
                "shorter'). Stay in the SAME recommendation category you just "
                "offered and give a new candidate that satisfies the modifier — "
                "do not change subject, do not answer with trivia or facts, and "
                "do not ask what they mean."
            )
    if _ref.search(user_text):
        lines.append(
            "The user is referring back to the conversation (pronouns like "
            "'it'/'that', shorthand like 'wbt X'/'u said', comparisons like "
            "'instead of Y'/'X over Y', or callbacks like 'you said earlier'). "
            "Resolve these against the 'Recent conversation' section: the most "
            "recently discussed subject wins for pronouns, and a callback to "
            "something YOU said must be acknowledged from that history — never "
            "claim you don't recall or lack context when it is present there. "
            "If they compare two options ('instead of', 'X over Y', 'would you "
            "pick X or Y'), keep it to the two options already on the table and "
            "give an actual comparison with a clear judgment in your own voice — "
            "do NOT introduce a brand-new third option and do not just restate "
            "the question."
        )
    lines.append(
        "Match the user's register and participate naturally. NEVER describe "
        "or classify the user's behavior ('it seems like you're...', 'you seem "
        "to be in a...mood', 'you're continuing the greeting...') — respond "
        "directly to what they said. Be brief unless depth was explicitly asked for."
    )
    return "\n".join(lines)


def _register_instruction(eff: Register, analysis: PragmaticAnalysis) -> str:
    if eff.emotion == "sarcasm":
        return ("The user is being sarcastic / ironic (positive words paired with "
                "hyperbolic negatives — 'wow great, my life is ruined'). Do NOT take "
                "it literally and do NOT respond with earnest empathy. Play along: "
                "match the dry tone, keep it light, and engage with the actual point "
                "underneath the sarcasm if there is one.")
    if eff.emotion == "distress":
        return ("The user is having a low/rough moment — respond proportionately and seriously: "
                "acknowledge what they said plainly, no forced cheerfulness, no therapy-speak "
                "('I'm sorry you're going through this, your feelings are valid'), no unsolicited "
                "advice essay. Be a normal person: engage with the actual content, keep it short, "
                "and only offer a suggestion if it fits naturally.")
    if eff.playfulness >= 2:
        return "The user is being playful — match the energy with a short playful reply; banter is welcome."
    if eff.playfulness == 1:
        return "The user is lighthearted — keep it warm and a little relaxed, not stiff."
    if eff.formality >= 2:
        return "The user is formal — reply professionally and precisely; no slang, no emoji."
    if eff.technicality:
        return "The user wants technical precision — be rigorous and specific; relaxed tone is fine but substance first."
    if eff.formality <= -1:
        return "The user is casual — reply in plain relaxed language, short and natural; no corporate phrasing."
    if eff.formality <= 0:
        return "Keep the reply natural and conversational, not corporate."
    return "Reply in natural professional English — clear and warm, not stiff."
