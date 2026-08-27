"""
media_context_intelligence.py
KIO Media Intelligence Layer — Context-Aware Media Intent

Extracts structured media intent from natural language:
  activity, media_mode, attention, mood, duration, content_type, selection_mode

Manages recommendation state:
  recommendation_set, pending_recommendations, activity context

Resolves user choices:
  "1", "2", "the second one", "the documentary", "play that"

Supports contextual follow-ups that modify attributes:
  "something shorter", "more relaxing", "music instead"

Architecture:
  User utterance
    → MediaContextIntelligence.extract_intent()
    → structured MediaIntent
    → if selection_mode == RECOMMENDATION:
        → generate recommendations
        → present options to user
    → if selection_mode == DIRECT or user selects:
        → resolve to YouTube query
        → MediaManager.play()
    → verify actual playback
    → truthful response
"""

from __future__ import annotations

import re
from dataclasses import dataclass, field
from enum import Enum
from typing import Any, Dict, List, Optional, Tuple


# ─────────────────────────── enums ───────────────────────────────────────

class MediaMode(str, Enum):
    """What the user wants to do with the media."""
    WATCH = "watch"
    LISTEN = "listen"
    BACKGROUND = "background"  # background audio/video, low attention
    ANY = "any"


class AttentionLevel(str, Enum):
    """How much attention the user will devote."""
    FULL = "full"          # watching actively
    PARTIAL = "partial"    # glancing occasionally
    LOW = "low"            # background, mostly listening
    NONE = "none"          # sleeping, pure ambient
    ANY = "any"            # not specified


class SelectionMode(str, Enum):
    """How the user wants to select media."""
    DIRECT = "direct"           # user specified what to play
    RECOMMENDATION = "recommendation"  # user wants options
    AUTO = "auto"               # user delegated choice ("just pick one")


class MediaType(str, Enum):
    """Content type the user wants."""
    SONG = "song"
    MUSIC_VIDEO = "music_video"
    TRAILER = "trailer"
    DOCUMENTARY = "documentary"
    INTERVIEW = "interview"
    PODCAST = "podcast"
    EDUCATIONAL = "educational"
    ENTERTAINMENT = "entertainment"
    NEWS = "news"
    LIVE = "live"
    SHORT = "short"
    ANY = "any"


class Mood(str, Enum):
    """Emotional quality the user wants."""
    CHILL = "chill"
    ENERGETIC = "energetic"
    FOCUS = "focus"
    RELAXING = "relaxing"
    HAPPY = "happy"
    SAD = "sad"
    ROMANTIC = "romantic"
    UNKNOWN = "unknown"


# ─────────────────────────── dataclasses ─────────────────────────────────

@dataclass
class MediaIntent:
    """Structured representation of what the user wants."""
    # Core
    raw_text: str
    activity: str = ""           # eating, studying, coding, workout, etc.
    media_mode: MediaMode = MediaMode.ANY
    attention: AttentionLevel = AttentionLevel.ANY
    mood: Mood = Mood.UNKNOWN
    content_type: MediaType = MediaType.ANY
    selection_mode: SelectionMode = SelectionMode.DIRECT
    topic: str = ""              # specific entity/topic if mentioned
    
    # Duration/preference hints
    duration_hint: str = ""      # "short", "long", "background"
    
    # Confidence
    confidence: float = 0.0
    
    # Derived
    search_query: str = ""       # what to actually search for
    is_contextual: bool = False  # has activity/mood context
    
    def __str__(self) -> str:
        parts = []
        if self.activity:
            parts.append(f"activity={self.activity}")
        if self.media_mode != MediaMode.ANY:
            parts.append(f"mode={self.media_mode.value}")
        if self.mood != Mood.UNKNOWN:
            parts.append(f"mood={self.mood.value}")
        if self.content_type != MediaType.ANY:
            parts.append(f"type={self.content_type.value}")
        if self.selection_mode != SelectionMode.DIRECT:
            parts.append(f"selection={self.selection_mode.value}")
        if self.topic:
            parts.append(f"topic={self.topic}")
        return f"MediaIntent({', '.join(parts)})"


@dataclass
class RecommendationOption:
    """A single recommendation to present to the user."""
    index: int                  # 1-based
    title: str
    channel: str = ""
    url: str = ""
    video_id: str = ""
    duration: str = ""
    content_type: str = ""
    reason: str = ""            # why this was recommended


@dataclass
class RecommendationSet:
    """A set of recommendations stored in context for user selection."""
    options: List[RecommendationOption] = field(default_factory=list)
    activity: str = ""
    media_mode: str = ""
    mood: str = ""
    query: str = ""
    timestamp: float = 0.0
    
    def get_option(self, selection: str) -> Optional[RecommendationOption]:
        """Resolve user selection to a specific option."""
        s = selection.lower().strip()
        
        # "1", "2", "3" etc.
        if s.isdigit():
            idx = int(s) - 1  # 0-based
            if 0 <= idx < len(self.options):
                return self.options[idx]
        
        # "number 2", "option 3", "pick 1"
        m = re.match(r"(?:number|option|pick|#)?\s*(\d+)", s)
        if m:
            idx = int(m.group(1)) - 1
            if 0 <= idx < len(self.options):
                return self.options[idx]
        
        # "the first one", "the second one", "the third one"
        ordinals = {"first": 0, "second": 1, "third": 2, "fourth": 3, "fifth": 4}
        for word, idx in ordinals.items():
            if word in s and idx < len(self.options):
                return self.options[idx]
        
        # "the documentary", "the interview", "the song" — match content type
        for opt in self.options:
            if opt.content_type and opt.content_type.lower() in s:
                return opt
        
        # "that one", "that", "it" — return first if only one context
        if s in ("that one", "that", "it", "this one", "this"):
            if len(self.options) == 1:
                return self.options[0]
        
        # Fuzzy title match
        for opt in self.options:
            if opt.title.lower() in s or s in opt.title.lower():
                return opt
        
        return None


# ─────────────────────────── intent extraction ───────────────────────────

# Activity patterns — what the user is doing
_ACTIVITY_PATTERNS: List[Tuple[re.Pattern, str, MediaMode]] = [
    # Eating
    (re.compile(r"\b(?:while\s+)?(?:i(?:'m|\s+am)?\s+)?(?:eat(?:ing|s)?|having\s+(?:breakfast|lunch|dinner|a\s+meal|food)|dinner|breakfast|lunch)\b", re.I), "eating", MediaMode.WATCH),
    (re.compile(r"\b(?:while\s+)?(?:i(?:'m|\s+am)?\s+)?(?:cooking|making\s+(?:food|dinner|lunch|breakfast))\b", re.I), "cooking", MediaMode.WATCH),
    
    # Study/Work
    (re.compile(r"\b(?:while\s+)?(?:i(?:'m|\s+am)?\s+)?(?:study|studying|doing\s+homework)\b", re.I), "studying", MediaMode.LISTEN),
    (re.compile(r"\b(?:while\s+)?(?:i(?:'m|\s+am)?\s+)?(?:cod(?:e|ing)|programming|working\s+on\s+(?:code|a\s+project))\b", re.I), "coding", MediaMode.LISTEN),
    (re.compile(r"\b(?:while\s+)?(?:i(?:'m|\s+am)?\s+)?(?:work(?:ing)?|doing\s+(?:work|tasks))\b", re.I), "working", MediaMode.BACKGROUND),
    
    # Exercise
    (re.compile(r"\b(?:while\s+)?(?:i(?:'m|\s+am)?\s+)?(?:work(?:ing)?\s+out|exercis(?:e|ing)|at\s+the\s+gym|gym)\b", re.I), "exercising", MediaMode.LISTEN),
    (re.compile(r"\b(?:while\s+)?(?:i(?:'m|\s+am)?\s+)?(?:run(?:ning|s)?|jogg?ing)\b", re.I), "running", MediaMode.LISTEN),
    
    # Relaxation
    (re.compile(r"\b(?:while\s+)?(?:i(?:'m|\s+am)?\s+)?(?:read(?:ing|s)?)\b", re.I), "reading", MediaMode.LISTEN),
    (re.compile(r"\b(?:while\s+)?(?:i(?:'m|\s+am)?\s+)?(?:relax(?:ing|ed)?|winding\s+down|chill(?:ing)?)\b", re.I), "relaxing", MediaMode.BACKGROUND),
    (re.compile(r"\b(?:i(?:'m|\s+am)?\s+)?(?:going\s+to\s+sleep|sleep(?:ing|y)?|bed(?:time)?)\b", re.I), "sleeping", MediaMode.LISTEN),
    
    # Commute
    (re.compile(r"\b(?:while\s+)?(?:i(?:'m|\s+am)?\s+)?(?:commut(?:e|ing)|driv(?:e|ing)|on\s+(?:the\s+)?(?:train|bus|subway))\b", re.I), "commuting", MediaMode.ANY),
    
    # Cleaning
    (re.compile(r"\b(?:while\s+)?(?:i(?:'m|\s+am)?\s+)?(?:clean(?:ing|s)?|tidy(?:ing|s)?)\b", re.I), "cleaning", MediaMode.BACKGROUND),
    
    # Background
    (re.compile(r"\b(?:in\s+the\s+background|background\s+(?:music|audio|noise|sound))\b", re.I), "background", MediaMode.BACKGROUND),
]

# Mood patterns
_MOOD_PATTERNS: List[Tuple[re.Pattern, Mood]] = [
    (re.compile(r"\b(?:chill|chill(?:ing|ed)?|relax(?:ing|ed)?|calm|peaceful|serene|mellow)\b", re.I), Mood.CHILL),
    (re.compile(r"\b(?:energetic|pump(?:ed)?|hype|high\s+energy|upbeat|power)\b", re.I), Mood.ENERGETIC),
    (re.compile(r"\b(?:focus|focused|concentration|deep\s+work|productive)\b", re.I), Mood.FOCUS),
    (re.compile(r"\b(?:relaxing|soothing|gentle|soft|quiet|ambient)\b", re.I), Mood.RELAXING),
    (re.compile(r"\b(?:happy|cheerful|joyful|feel[\s-]good|positive|bright)\b", re.I), Mood.HAPPY),
    (re.compile(r"\b(?:sad|melancholy|emotional|heartbreak|blue|somber)\b", re.I), Mood.SAD),
    (re.compile(r"\b(?:romantic|love|date\s+night|sweet|intimate)\b", re.I), Mood.ROMANTIC),
    # Extended mood patterns for arbitrary phrasing
    (re.compile(r"\b(?:fun(?:ny)?|amusing|hilarious|laugh(?:ing|ter)?|comedy|comedic)\b", re.I), Mood.HAPPY),
    (re.compile(r"\b(?:interesting|intriguing|fascinating|cool)\b", re.I), Mood.CHILL),
    (re.compile(r"\b(?:tired|sleepy|exhausted|drained)\b", re.I), Mood.RELAXING),
    (re.compile(r"\b(?:bored|boring|nothing\s+to\s+do)\b", re.I), Mood.HAPPY),
]

# Content type patterns
_CONTENT_TYPE_PATTERNS: List[Tuple[re.Pattern, MediaType]] = [
    (re.compile(r"\b(?:documentary|docu(?:ry|ment)?)\b", re.I), MediaType.DOCUMENTARY),
    (re.compile(r"\b(?:interview|interviews)\b", re.I), MediaType.INTERVIEW),
    (re.compile(r"\b(?:podcast|podcasts)\b", re.I), MediaType.PODCAST),
    (re.compile(r"\b(?:trailer|teaser)\b", re.I), MediaType.TRAILER),
    (re.compile(r"\b(?:music\s+video|mv)\b", re.I), MediaType.MUSIC_VIDEO),
    (re.compile(r"\b(?:song|songs|track|tracks|music)\b", re.I), MediaType.SONG),
    (re.compile(r"\b(?:educational|tutorial|learn(?:ing)?|explained?)\b", re.I), MediaType.EDUCATIONAL),
    (re.compile(r"\b(?:news|latest|update|current)\b", re.I), MediaType.NEWS),
    (re.compile(r"\b(?:live\s+(?:stream|performance|concert|show))\b", re.I), MediaType.LIVE),
    (re.compile(r"\b(?:short(?:s)?|reel|clip)\b", re.I), MediaType.SHORT),
]

# Selection mode patterns
_SELECTION_PATTERNS: List[Tuple[re.Pattern, SelectionMode]] = [
    # Direct delegation
    (re.compile(r"\b(?:just\s+pick|choose\s+(?:for\s+me|one)|surprise\s+me|whatever\s+you\s+(?:think|want|pick)|don'?t\s+(?:give|show)\s+(?:me\s+)?options|play\s+something|don'?t\s+(?:bother|care))\b", re.I), SelectionMode.AUTO),
    # Extended direct delegation for arbitrary phrasing
    (re.compile(r"\b(?:you\s+(?:pick|choose|decide|select)|your\s+choice|up\s+to\s+you|anything\s+(?:is\s+fine|works|goes))\b", re.I), SelectionMode.AUTO),
    # Recommendation request
    (re.compile(r"\b(?:pick\s+(?:something|one|a\s+video|a\s+song)|give\s+me\s+(?:something|options|a\s+few)|show\s+me\s+(?:some|a\s+few|options|what\s+you\s+got)|recommend|what\s+(?:should|do)\s+(?:i|you)\s+(?:watch|listen|play))\b", re.I), SelectionMode.RECOMMENDATION),
    # Extended recommendation for "find something"
    (re.compile(r"\b(?:find\s+(?:something|me\s+something|a\s+(?:video|song|thing)))\b", re.I), SelectionMode.RECOMMENDATION),
]

# Duration patterns
_DURATION_PATTERNS: List[Tuple[re.Pattern, str]] = [
    (re.compile(r"\b(?:short|quick|brief|something\s+short)\b", re.I), "short"),
    (re.compile(r"\b(?:long|extended|something\s+long|for\s+a\s+(?:while|long\s+time))\b", re.I), "long"),
    (re.compile(r"\b(?:background|ambient|low[\s-]?(?:key|effort))\b", re.I), "background"),
]

# Media mode override patterns (override inferred mode)
_MEDIA_MODE_OVERRIDE: List[Tuple[re.Pattern, MediaMode]] = [
    (re.compile(r"\b(?:watch(?:ing)?|show\s+me|let\s+me\s+see|see|view(?:ing)?)\b", re.I), MediaMode.WATCH),
    (re.compile(r"\b(?:listen(?:ing)?|hear(?:ing)?|play|audio)\b", re.I), MediaMode.LISTEN),
]

# Activity context extraction from "while I ..." clauses
_WHILE_CLAUSE = re.compile(
    r"\b(?:while|when|as)\s+(?:i(?:'m|\s+am)?\s+)?(.+?)(?:\.|,|$)",
    re.I,
)


# ─────────────────────────── query generation ────────────────────────────

# Activity → YouTube search query templates
_ACTIVITY_SEARCH: Dict[str, Dict[str, List[str]]] = {
    "eating": {
        "watch": [
            "interesting documentary to watch",
            "fun video to watch while eating",
            "light entertainment video",
            "interesting interview to watch",
            "video essay interesting topic",
        ],
        "listen": [
            "background music for eating",
            "chill music playlist",
        ],
    },
    "cooking": {
        "watch": [
            "cooking show",
            "recipe video",
            "food documentary",
        ],
        "listen": [
            "cooking music playlist",
            "upbeat cooking music",
        ],
    },
    "studying": {
        "listen": [
            "study music lofi",
            "focus music deep work",
            "concentration playlist",
            "study beats instrumental",
        ],
        "watch": [
            "educational video easy to follow",
            "interesting documentary",
        ],
    },
    "coding": {
        "listen": [
            "coding music instrumental",
            "focus music programming",
            "ambient music for coding",
            "lofi coding beats",
        ],
        "watch": [],
    },
    "working": {
        "listen": [
            "focus music for work",
            "productivity music",
            "instrumental background music",
        ],
        "watch": [],
    },
    "exercising": {
        "listen": [
            "workout music playlist",
            "high energy workout songs",
            "gym motivation music",
        ],
        "watch": [],
    },
    "running": {
        "listen": [
            "running playlist 2024",
            "jogging motivation songs",
            "cardio workout music",
        ],
        "watch": [],
    },
    "reading": {
        "listen": [
            "ambient music for reading",
            "calm instrumental music",
            "reading background music",
        ],
        "watch": [],
    },
    "relaxing": {
        "listen": [
            "relaxing music",
            "ambient sounds",
            "chill beats",
        ],
        "watch": [
            "relaxing video to watch",
            "satisfying video",
            "nature documentary",
        ],
    },
    "sleeping": {
        "listen": [
            "sleep music",
            "rain sounds",
            "white noise sleep",
            "ambient sleep music",
        ],
        "watch": [],
    },
    "commuting": {
        "listen": [
            "podcast interesting topics",
            "audiobook excerpt",
            "chill commute music",
        ],
        "watch": [],
    },
    "cleaning": {
        "listen": [
            "cleaning music playlist",
            "upbeat music for cleaning",
            "feel good music",
        ],
        "watch": [],
    },
    "background": {
        "listen": [
            "background music",
            "ambient music",
            "lofi beats background",
        ],
        "watch": [
            "interesting video background",
            "satisfying video compilation",
        ],
    },
}

# Mood → search query templates
_MOOD_SEARCH: Dict[Mood, List[str]] = {
    Mood.CHILL: ["chill vibes playlist", "lofi chill beats", "calm music mix"],
    Mood.ENERGETIC: ["high energy music", "pump up playlist", "workout motivation"],
    Mood.FOCUS: ["focus music deep work", "concentration playlist", "study beats"],
    Mood.RELAXING: ["relaxing music ambient", "peaceful instrumental", "calm piano music"],
    Mood.HAPPY: ["feel good songs", "happy music playlist", "upbeat positive music"],
    Mood.SAD: ["sad songs playlist", "emotional music", "melancholy instrumental"],
    Mood.ROMANTIC: ["romantic songs playlist", "love songs", "date night music"],
}


# ─────────────────────────── main class ──────────────────────────────────

class MediaContextIntelligence:
    """
    Context-aware media intelligence layer.
    
    Extracts structured intent from natural language, manages recommendation
    state, and resolves user choices.
    
    Usage:
        intelligence = MediaContextIntelligence()
        
        # Extract intent
        intent = intelligence.extract_intent("pick something to watch while I eat")
        # → MediaIntent(activity="eating", media_mode=WATCH, selection_mode=RECOMMENDATION)
        
        # Generate search query
        query = intelligence.generate_query(intent)
        # → "interesting documentary to watch"
        
        # Store recommendations
        intelligence.store_recommendations([...])
        
        # Resolve user choice
        option = intelligence.resolve_choice("the documentary")
        # → RecommendationOption(index=1, title="...", ...)
    """
    
    def __init__(self) -> None:
        self._recommendations: Optional[RecommendationSet] = None
        self._last_intent: Optional[MediaIntent] = None
        self._preference_model: Optional[object] = None  # MediaPreferenceModel

    def set_preference_model(self, model) -> None:
        """Inject the preference model for personalized discovery queries."""
        self._preference_model = model
    
    def extract_intent(self, text: str) -> MediaIntent:
        """Extract structured media intent from natural language."""
        t = text.lower().strip()
        
        intent = MediaIntent(raw_text=text)
        
        # 1. Extract activity
        for pattern, activity, mode in _ACTIVITY_PATTERNS:
            if pattern.search(t):
                intent.activity = activity
                if intent.media_mode == MediaMode.ANY:
                    intent.media_mode = mode
                intent.is_contextual = True
                break
        
        # Also check "while I ..." clauses
        if not intent.activity:
            m = _WHILE_CLAUSE.search(t)
            if m:
                clause = m.group(1).lower().strip()
                for pattern, activity, mode in _ACTIVITY_PATTERNS:
                    # Re-check with the clause content
                    if pattern.search(clause) or pattern.search(t):
                        intent.activity = activity
                        if intent.media_mode == MediaMode.ANY:
                            intent.media_mode = mode
                        intent.is_contextual = True
                        break
        
        # 2. Extract mood
        for pattern, mood in _MOOD_PATTERNS:
            if pattern.search(t):
                intent.mood = mood
                intent.is_contextual = True
                break
        
        # 3. Extract content type
        for pattern, ct in _CONTENT_TYPE_PATTERNS:
            if pattern.search(t):
                intent.content_type = ct
                break
        
        # 4. Extract selection mode
        for pattern, mode in _SELECTION_PATTERNS:
            if pattern.search(t):
                intent.selection_mode = mode
                break
        
        # 5. Extract duration
        for pattern, duration in _DURATION_PATTERNS:
            if pattern.search(t):
                intent.duration_hint = duration
                break
        
        # 6. Override media mode if explicit
        for pattern, mode in _MEDIA_MODE_OVERRIDE:
            if pattern.search(t):
                intent.media_mode = mode
                break
        
        # 7. Extract topic (explicit entity mention)
        # Remove activity/mood/selection words to find the topic
        topic = self._extract_topic(t, intent)
        if topic:
            intent.topic = topic
            intent.selection_mode = SelectionMode.DIRECT
        
        # 8. Determine selection mode from context
        # Bare discovery phrases → AUTO (just pick and play)
        if self._is_bare_discovery(t):
            intent.selection_mode = SelectionMode.AUTO
        elif self._is_recommendation_request(t):
            intent.selection_mode = SelectionMode.RECOMMENDATION
        elif intent.selection_mode == SelectionMode.DIRECT and not intent.topic:
            if intent.is_contextual:
                # Contextual request without explicit topic → auto-play
                intent.selection_mode = SelectionMode.AUTO
        
        # 9. Generate search query
        intent.search_query = self.generate_query(intent)
        
        # 10. Set confidence
        intent.confidence = self._estimate_confidence(intent)
        
        # 11. Track last contextual intent for follow-ups
        if intent.is_contextual or intent.activity:
            self._last_intent = intent
        
        return intent
    
    def generate_query(self, intent: MediaIntent) -> str:
        """Generate a YouTube search query from structured intent."""
        # If explicit topic, use it directly
        if intent.topic:
            return intent.topic
        
        # Build query from activity + mood + content type
        parts = []
        
        # Activity-based query
        if intent.activity and intent.activity in _ACTIVITY_SEARCH:
            mode_key = intent.media_mode.value if intent.media_mode != MediaMode.ANY else "listen"
            queries = _ACTIVITY_SEARCH[intent.activity].get(mode_key, [])
            if queries:
                # Use mood to pick the best query
                if intent.mood != Mood.UNKNOWN and intent.mood in _MOOD_SEARCH:
                    mood_q = _MOOD_SEARCH[intent.mood][0]
                    # Combine activity + mood
                    parts.append(f"{intent.activity} {mood_q}")
                else:
                    parts.append(queries[0])
        
        # Mood-based query (if no activity)
        elif intent.mood != Mood.UNKNOWN and intent.mood in _MOOD_SEARCH:
            parts.append(_MOOD_SEARCH[intent.mood][0])
        
        # Content type
        if intent.content_type != MediaType.ANY:
            ct_map = {
                MediaType.DOCUMENTARY: "documentary",
                MediaType.INTERVIEW: "interview",
                MediaType.PODCAST: "podcast",
                MediaType.TRAILER: "trailer",
                MediaType.MUSIC_VIDEO: "music video",
                MediaType.SONG: "song",
                MediaType.EDUCATIONAL: "educational video",
                MediaType.NEWS: "news",
                MediaType.LIVE: "live performance",
                MediaType.SHORT: "short video",
            }
            if intent.content_type in ct_map:
                parts.append(ct_map[intent.content_type])
        
        # Duration
        if intent.duration_hint == "short":
            parts.append("short")
        
        if parts:
            return " ".join(parts)
        
        # Fallback: use preference model for personalized discovery
        if self._preference_model:
            try:
                prefs = self._preference_model.get_summary()
                # Build query from top preference signals
                _pf = []
                if prefs.top_channels:
                    _pf.append(prefs.top_channels[0][0])  # top channel/creator
                elif prefs.top_artists:
                    _pf.append(prefs.top_artists[0][0])   # top artist
                if prefs.top_genres:
                    _pf.append(prefs.top_genres[0][0])    # top genre
                if prefs.top_languages:
                    _pf.append(prefs.top_languages[0][0]) # preferred language
                if _pf:
                    return " ".join(_pf[:3])
            except Exception:
                pass
        # No preference data — use the user's own words from raw_text.
        # NEVER insert hardcoded generic queries like "Popular Songs".
        # The user's utterance IS the best signal we have for discovery.
        if intent.raw_text and intent.raw_text.strip():
            return intent.raw_text.strip()
        # Truly empty — return empty string; callers MUST handle this
        # by using the original user request as the search query.
        return ""
    
    def store_recommendations(
        self,
        options: List[RecommendationOption],
        intent: Optional[MediaIntent] = None,
    ) -> None:
        """Store recommendation options for user selection."""
        import time
        self._recommendations = RecommendationSet(
            options=options,
            activity=intent.activity if intent else "",
            media_mode=intent.media_mode.value if intent else "",
            mood=intent.mood.value if intent else "",
            query=intent.search_query if intent else "",
            timestamp=time.time(),
        )
        self._last_intent = intent
    
    def resolve_choice(self, selection: str) -> Optional[RecommendationOption]:
        """Resolve user selection to a specific recommendation."""
        if not self._recommendations:
            return None
        return self._recommendations.get_option(selection)
    
    def has_pending_recommendations(self) -> bool:
        """Check if there are pending recommendations."""
        return self._recommendations is not None and len(self._recommendations.options) > 0
    
    def clear_recommendations(self) -> None:
        """Clear stored recommendations."""
        self._recommendations = None
    
    def modify_context(self, modification: str) -> Optional[MediaIntent]:
        """Modify the current context based on follow-up.
        
        E.g., "something shorter" → same activity + short duration
        "more relaxing" → same activity + relaxing mood
        "music instead" → same activity + LISTEN mode
        """
        if not self._last_intent:
            return None
        
        m = modification.lower().strip()
        intent = MediaIntent(
            raw_text=modification,
            activity=self._last_intent.activity,
            media_mode=self._last_intent.media_mode,
            attention=self._last_intent.attention,
            mood=self._last_intent.mood,
            content_type=self._last_intent.content_type,
            selection_mode=SelectionMode.RECOMMENDATION,
            topic="",
            is_contextual=True,
        )
        
        # Duration modification
        if "shorter" in m or "quick" in m or "brief" in m:
            intent.duration_hint = "short"
        elif "longer" in m or "long" in m:
            intent.duration_hint = "long"
        
        # Mood modification
        for pattern, mood in _MOOD_PATTERNS:
            if pattern.search(m):
                intent.mood = mood
                break
        
        # Mode modification
        if re.search(r"\b(?:music|audio|listen|song)\b", m):
            intent.media_mode = MediaMode.LISTEN
        elif re.search(r"\b(?:watch|video|see|show)\b", m):
            intent.media_mode = MediaMode.WATCH
        
        intent.search_query = self.generate_query(intent)
        return intent
    
    # Words that are NOT topics — mood/activity/selection/function words
    _STOP_WORDS = frozenset({
        "play", "put", "on", "show", "me", "give", "something", "anything",
        "for", "while", "please", "want", "need", "find", "pick", "choose",
        "just", "the", "a", "an", "to", "some", "that", "this", "it",
        "my", "can", "you", "would", "could", "should", "do", "does",
        "is", "are", "was", "were", "be", "been", "having", "have", "has",
        "with", "and", "or", "but", "in", "at", "of", "from",
        "about", "like", "as", "i", "im", "i'm", "am", "one", "two",
        "three", "four", "five", "bored", "entertain", "entertain me",
        "surprise", "surprise me", "good", "interesting", "nice", "great",
        "best", "random", "whatever", "music", "song", "songs",
        "video", "videos", "watch", "listen", "hear", "audio",
        "instead", "rather", "shorter", "longer", "more", "less",
        "calm", "chill", "relaxing", "energetic", "focus", "focused",
        "background", "workout", "exercise", "gym", "dinner", "breakfast",
        "lunch", "coding", "working", "studying", "reading", "sleeping",
        "relaxing", "commuting", "cleaning", "cooking", "eating",
        "won't", "wont", "distract", "mostly", "entertainment",
        "entertaining", "educational", "easy", "follow",
        "don't", "doesn't", "didn't", "isn't", "aren't", "wasn't",
        "can't", "couldn't", "wouldn't", "shouldn't", "won't",
        "it's", "that's", "there's", "here's", "what's", "who's",
        "clean", "code", "focus", "study", "work", "read", "sleep",
        "relax", "eat", "cook", "commute", "exercise", "workout",
    })
    
    def _extract_topic(self, text: str, intent: MediaIntent) -> str:
        """Extract the specific topic/entity from the text.
        
        Only extracts genuine entity names/topics, not mood/activity/selection words.
        """
        t = text.lower()
        
        # Explicit topical clauses are stronger than the residual-word path.
        # Do not treat every "on X" phrase as a subject: in natural media
        # requests it commonly specifies an execution target ("... on a
        # browser/provider") rather than the requested work.  Residual-word
        # extraction below still handles "a video on quantum computing".
        m = re.search(r"\b(?:about|regarding|concerning)\s+(.+)", t)
        if m:
            topic = m.group(1).strip().rstrip(".!?")
            # Clean stop words from the topic
            words = [w for w in topic.split() if w.lower() not in self._STOP_WORDS]
            if words:
                return " ".join(words)
        
        # Remove bare discovery phrases first — these have no topic
        # Sort longest-first so "watch me after i ask" beats "watch me"
        for disc in sorted(self._BARE_DISCOVERY, key=len, reverse=True):
            t = t.replace(disc, "")
        # Strip "I feel like watching/listening to" mood frames — the mood is
        # already extracted; the residual "feel comedy" must not become a topic.
        t = re.sub(r"\b(?:i(?:'m|\s+am)?\s+)?feel\s+like\s+(?:watch(?:ing)?|listen(?:ing)?|play(?:ing)?|see(?:ing)?|hear(?:ing)?)\s*(?:a\s+|some\s+|the\s+)?", "", t)
        # Remove known patterns to isolate the topic
        for pattern, _, _ in _ACTIVITY_PATTERNS:
            t = pattern.sub("", t)
        # Mood/activity patterns: only strip when there's other content
        # remaining — if the mood word IS the only substantive word (e.g.
        # "comedy" in "I feel like watching a comedy"), keep it as the
        # topic.  Stripping it would leave nothing and the fallback query
        # would ignore what the user actually asked for.
        _before_mood = t
        for pattern, _ in _MOOD_PATTERNS:
            t = pattern.sub("", t)
        # Check if stripping mood words left nothing useful
        _residual = [w for w in t.split() if w.strip(".,!?") and len(w.strip(".,!?")) >= 2]
        if not _residual and _before_mood.strip():
            t = _before_mood
        for pattern, _ in _SELECTION_PATTERNS:
            t = pattern.sub("", t)
        for pattern, _ in _DURATION_PATTERNS:
            t = pattern.sub("", t)
        for pattern, _ in _MEDIA_MODE_OVERRIDE:
            t = pattern.sub("", t)

        # A trailing "on <provider>" is an execution constraint, not the
        # entity being searched.  Keep this deliberately provider-agnostic:
        # any single trailing service/browser token is discarded and target
        # selection remains the responsibility of the execution layer.
        t = re.sub(r"\b(?:on|in|via|through)\s+[\w.-]+\s*$", "", t).strip()
        
        # Clean up stop words
        words = t.split()
        content_words = []
        for w in words:
            w_clean = w.strip(".,!?;:'\"\"")
            if w_clean and w_clean not in self._STOP_WORDS and len(w_clean) >= 2:
                content_words.append(w_clean)
        
        if len(content_words) >= 2:
            return " ".join(content_words)
        if len(content_words) == 1 and len(content_words[0]) >= 3:
            # Single long word might be a topic (e.g., "Interstellar")
            return content_words[0]
        
        return ""
    
    # Bare discovery phrases — user delegates choice completely
    _BARE_DISCOVERY = frozenset({
        "i'm bored", "im bored", "i am bored", "bored",
        "i'm tired", "im tired", "i am tired", "tired",
        "surprise me", "surprise", "entertain me", "amuse me",
        "pick something", "choose something", "pick one",
        "anything", "whatever", "something", "something random",
        "play something", "put something on", "show me something",
        "give me something", "find something", "recommend something",
        "suggest something", "what should i watch", "what should i listen to",
        "what's good", "whats good", "just pick one", "choose for me",
        "don't give me options", "just play something", "don't bother me with options",
        "you pick", "you choose", "you decide", "your choice",
        "i don't know what to watch", "i don't know what to listen to",
        "idk what to watch", "idk what to listen to",
        "nothing to watch", "nothing to listen to",
        "can't decide", "cant decide",
        "watch me after i ask", "watch me",
        "listen to what you think i want", "play what you think i want",
        "what do you think i want", "what would you play for me",
    })
    
    def _is_bare_discovery(self, text: str) -> bool:
        """Check if this is a bare discovery request where KIO should just pick.
        
        These are requests where the user fully delegates the choice:
        'I'm bored', 'surprise me', 'entertain me', 'just pick one'
        
        NOT 'pick something to watch while I eat' — that's a recommendation
        request where the user wants options.
        """
        t = text.lower().strip()
        if t in self._BARE_DISCOVERY:
            return True
        # "I'm bored", "entertain me" — bare discovery
        if re.match(r"^i(?:'m|\s+am)\s+bored", t):
            return True
        if re.match(r"^(?:entertain|amuse|cheer)\s+me", t):
            return True
        if re.match(r"^watch\s+me\s+after\s+I\s+ask", t, re.IGNORECASE):
            return True
        if re.match(r"^(?:listen|play)\s+to\s+what\s+you\s+think\s+I\s+want", t, re.IGNORECASE):
            return True
        return False
    
    # Recommendation request patterns — user wants options
    _RECOMMENDATION_REQUEST = re.compile(
        r"\b(?:pick\s+(?:something|one|a)|give\s+me\s+(?:something|options|a\s+few)|"
        r"show\s+me\s+(?:some|a\s+few|options|what\s+you\s+got)|"
        r"recommend|what\s+(?:should|do)\s+(?:i|you)\s+(?:watch|listen|play)|"
        r"find\s+(?:something|me\s+something))\b",
        re.I,
    )
    
    def _is_recommendation_request(self, text: str) -> bool:
        """Check if this is a recommendation request (user wants options)."""
        return bool(self._RECOMMENDATION_REQUEST.search(text))
    
    def _estimate_confidence(self, intent: MediaIntent) -> float:
        """Estimate confidence in the intent extraction."""
        score = 0.0
        
        if intent.activity:
            score += 0.3
        if intent.mood != Mood.UNKNOWN:
            score += 0.2
        if intent.content_type != MediaType.ANY:
            score += 0.2
        if intent.topic:
            score += 0.3
        if intent.is_contextual:
            score += 0.1
        
        return min(1.0, score)
