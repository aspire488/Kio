from __future__ import annotations

import logging
import re
import time
from dataclasses import dataclass, field
from enum import Enum
from typing import Optional, Pattern, Tuple

from typing import TYPE_CHECKING
from mini_kio.core.continuity_context_provider import ContinuityContextProvider

if TYPE_CHECKING:
    from mini_kio.media.intelligence.media_entity_memory import MediaEntityMemory

logger = logging.getLogger(__name__)

_RUNTIME_REF_PATTERNS = [re.compile(r"\b(again|do that again|do it again)\b")]

# merged from continuity_engine.py
_PLAY_IT_RE = re.compile(r"^play\s*(it|this|that)?$", re.I)
_SHOW_IT_RE = re.compile(r"^show\s*(it|this|that)?$", re.I)
_TELL_MORE_RE = re.compile(r"(tell me more|more info|more details|expand|elaborate)", re.I)

# merged from media_followup_engine.py
_CONTINUATION_PATTERNS_FU = re.compile(
    r"\b(another one|next one|one more|play more|more like (this|that)|another song|another track)\b", re.I
)

_ORDINAL_PATTERNS: dict[Pattern, int] = {
    re.compile(r"\b(first( one)?|number (one|1)|#?1|the first)\b",    re.I): 0,
    re.compile(r"\b(second( one)?|number (two|2)|#?2|the second)\b",  re.I): 1,
    re.compile(r"\b(third( one)?|number (three|3)|#?3|the third)\b",   re.I): 2,
    re.compile(r"\b(fourth( one)?|number (four|4)|#?4|the fourth)\b",  re.I): 3,
    re.compile(r"\b(fifth( one)?|number (five|5)|#?5|the fifth)\b",   re.I): 4,
}

_AFFIRMATIVES_FU: set[str] = {"yes", "yeah", "yep", "sure", "ok", "okay",
                                "play it", "play", "go ahead", "yup", "do it", "absolutely"}
_NEGATIVES_FU: set[str] = {"no", "nope", "nah", "skip", "not now", "pass",
                            "no thanks", "never mind", "cancel", "forget it"}

# merged from media_reference_resolver.py
_PRONOUN_REF_PATTERNS: list[Tuple[Pattern, str]] = [
    (re.compile(r"\b(him|his)\b",            re.I), "artist_male"),
    (re.compile(r"\b(her|she|hers)\b",       re.I), "artist_female"),
    (re.compile(r"\b(them|their|they)\b",    re.I), "artist_group"),
    (re.compile(r"\b(it|that one|this one|that song|that track|that video|that trailer)\b", re.I), "last_entity"),
]

_REPLAY_PATTERNS = [
    re.compile(r"\bplay (that |it |the same )?(again|once more)\b", re.I),
    re.compile(r"\breplay\b", re.I),
    re.compile(r"\bplay (that (song|track|video|one))\b", re.I),
]


class DomainContinuationType(Enum):
    MEDIA = "media"
    BROWSER = "browser"
    RESEARCH = "research"
    CONVERSATION = "conversation"
    FILE = "file"
    TASK = "task"
    SYSTEM = "system"
    UNKNOWN = "unknown"


@dataclass
class ContinuationContext:
    domain: DomainContinuationType = DomainContinuationType.UNKNOWN
    original_input: str = ""
    resolved_input: str = ""
    continuity_active: bool = False
    reference_type: str = ""
    active_subject: str = ""
    active_action: str = ""
    runtime_source: str = ""


@dataclass
class ResolvedContinuation:
    domain: DomainContinuationType = DomainContinuationType.UNKNOWN
    resolved_text: str = ""
    is_continuation: bool = False
    context: Optional[ContinuationContext] = None


@dataclass
class ContinuityState:
    active_domain: Optional[DomainContinuationType] = None
    active_subject: str = ""  # subject for current active_domain (backward compat)
    subjects: dict[str, str] = field(default_factory=dict)  # domain-scoped subjects
    active_action: str = ""
    last_command: str = ""
    last_resolved: str = ""
    last_success: bool = False
    timestamp: float = 0.0


class ContinuityResolver:
    _state: ContinuityState = ContinuityState()
    _provider: ContinuityContextProvider = ContinuityContextProvider()
    _entity_memory: Optional["MediaEntityMemory"] = None
    _session_state: Optional["SessionState"] = None

    @classmethod
    def set_entity_memory(cls, mem: "MediaEntityMemory") -> None:
        cls._entity_memory = mem

    @classmethod
    def set_session_state(cls, state: "SessionState") -> None:
        """Wire unified SessionState as authoritative source for entity/domain.
        
        Once set, resolve() reads active_entity/active_domain from SessionState
        and update_state() writes back to it, keeping ContinuityState in sync.
        """
        cls._session_state = state
        # Bootstrap ContinuityState from session state (if any)
        if state.active_entity:
            cls._state.active_subject = state.active_entity
            cls._state.subjects["media"] = state.active_entity
        if state.active_domain:
            try:
                cls._state.active_domain = DomainContinuationType(state.active_domain.lower())
            except (ValueError, TypeError):
                pass

    _MEDIA_KEYWORDS: set[str] = {
        "play ", "watch ", "pause", "resume", "stop",
        "next track", "next video", "next song",
        "previous track", "previous video", "previous song",
        "play it", "play that", "show it",
        "play highlight", "play trailer",
        "show highlight", "show trailer", "show gameplay",
        "trailer", "highlights", "gameplay", "music video",
        "standings", "fixtures", "scores", "score ",
        "what happened", "who scored",
        "play another", "play more", "play something similar",
        "latest ", "what's the latest", "news about",
        "fifa", "world cup", "premier league", "nba", "nfl",
        "match ", " matches", "next match",
        "seek ", "volume", "mute", "unmute",
    }

    _BROWSER_KEYWORDS: set[str] = {
        "close ", "focus ", "switch to ",
        "next result", "previous result", "list tabs",
        "search ", "search in chrome", "search in edge",
        "tabs", "chrome", "edge", "firefox", "brave", "comet",
        "in chrome", "in edge", "in firefox",
        "refresh", "reload", "new tab",
        "summarize this page", "go back", "go forward",
        "open url", "open link",
    }

    _RESEARCH_KEYWORDS: set[str] = {
        "research ", "summarize ", "compare ",
        "give sources", "show sources", "references",
        "source list",
        "expand on",
    }

    _FILE_KEYWORDS: set[str] = {
        "open folder", "open the folder",
        "create file", "create python file",
        "save ", "edit ", "fix bug",
        "list directory", "list files", "show files",
    }

    _TASK_KEYWORDS: set[str] = {
        "todo", "task", "add task", "remove task",
        "mark done", "show tasks", "list tasks",
        "next task", "clear tasks",
    }

    _SYSTEM_KEYWORDS: set[str] = {
        "settings", "brightness", "shutdown", "restart",
        "lock ", "recovery",
        "increase ", "decrease ",
        "turn it up", "turn it down", "louder", "quieter",
        "do that again", "again", "do it again",
    }

    _CONVERSATION_KEYWORDS: set[str] = {
        "tell me", "explain", "what is", "how does",
        "why is", "what are", "who is",
        "give example", "expand", "elaborate",
        "hello", "hi", "hey", "bye",
        "how are you", "what's up",
    }

    _CONTINUATION_MARKERS: set[str] = {
        "continue", "continue please", "go on", "keep going", "proceed",
    }

    _AFFIRMATIVE_MARKERS: set[str] = {
        "yes", "yeah", "sure", "ok", "okay", "do it", "go ahead",
    }

    _PRONOUN_PATTERNS = [re.compile(r"\bit\b"), re.compile(r"\bthat\b"),
                         re.compile(r"\bthis\b"), re.compile(r"\bthere\b"),
                         re.compile(r"\bhim\b"), re.compile(r"\bher\b"),
                         re.compile(r"\bthem\b"), re.compile(r"\bthey\b"),
                         re.compile(r"\bhe\b"), re.compile(r"\bshe\b")]

    _NEXT_MARKERS: set[str] = {"next", "more", "another", "next one", "one more", "play more"}
    _PENDING_ACTION_TRIGGERS: set[str] = {"play it", "play that", "show it", "watch it",
                                           "watch that", "show that", "play",
                                           "yes", "yeah", "sure", "ok", "okay",
                                           "do it", "go ahead"}

    @classmethod
    def resolve(cls, command: str) -> ResolvedContinuation:
        text = command.strip()
        if not text:
            return ResolvedContinuation()

        lower = text.lower()
        ctx = ContinuationContext(original_input=text)

        # T8-1: Explicit runtime references in context buffer
        runtime_resolved = cls._resolve_runtime_reference(lower, ctx)
        if runtime_resolved:
            return cls._build_resolved(text, ctx, override_resolved=runtime_resolved)

        # T8-2: Pending action resolution (MediaContext pending state)
        pending_resolved = cls._resolve_pending_action(lower, ctx)
        if pending_resolved:
            return cls._build_resolved(text, ctx, override_resolved=pending_resolved)

        # Current Step 1: Pure continuation markers ("continue", "go on")
        if cls._resolve_continuation_markers(lower, ctx):
            return cls._build_resolved(text, ctx)

        # Current Step 2: Pure affirmative markers ("yes", "ok", "do it")
        if cls._resolve_affirmative_markers(lower, ctx):
            return cls._build_resolved(text, ctx)

        # T8-5: Keyword inference (domain detection)
        cls._detect_domain(lower, ctx)

        # T8-3/T8-4: Active domain + subject pronoun resolution
        if cls._has_pronoun(lower):
            # _target_domain: keyword-detected domain takes priority over active state domain
            _target_domain = ctx.domain if ctx.reference_type == "explicit" else cls._get_best_domain()
            # _subject_domain: which domain's subject to use for pronoun resolution
            _subject_domain = ctx.domain if ctx.reference_type == "explicit" else cls._state.active_domain
            if _target_domain and _target_domain != DomainContinuationType.UNKNOWN:
                # Original logic: try keyword domain's subject FIRST, then active state's subject
                domain_subject = ""
                if _subject_domain:
                    domain_subject = cls._state.subjects.get(_subject_domain.value, "")
                if not domain_subject:
                    domain_subject = cls._get_best_subject()
                if domain_subject:
                    ctx.continuity_active = True
                    ctx.reference_type = "pronoun"
                    ctx.active_subject = domain_subject
                    ctx.domain = _target_domain  # preserve keyword-detected domain
                    return cls._build_resolved(text, ctx)

        # Merged: Tell more / replay patterns — only when domain not detected by keywords
        best_domain = cls._get_best_domain()
        if ctx.domain == DomainContinuationType.UNKNOWN and best_domain:
            if cls._matches_tell_more(lower) or cls._matches_replay(lower):
                ctx.domain = best_domain
                ctx.continuity_active = True
                ctx.reference_type = "continuation"
                return cls._build_resolved(text, ctx)

        # Merged: Continuation patterns (another one/one more/play more) + ordinal with active domain
        if best_domain and (lower in cls._NEXT_MARKERS
                            or cls._matches_continuation_fu(lower)
                            or cls._matches_ordinal(lower)):
            ctx.domain = best_domain
            ctx.continuity_active = True
            ctx.reference_type = "continuation"
            return cls._build_resolved(text, ctx)

        # T8-6: Active domain fallback when no domain was detected
        _WEAK_REF = frozenset({"it", "that", "this", "again", "same", "more", "continue"})
        if ctx.domain == DomainContinuationType.UNKNOWN and best_domain and best_domain != DomainContinuationType.UNKNOWN:
            lower = text.lower().strip()
            words = set(lower.split())
            if words & _WEAK_REF:
                ctx.domain = best_domain
                ctx.continuity_active = True
                ctx.reference_type = "continuation"
                return cls._build_resolved(text, ctx)

        return ResolvedContinuation(
            domain=ctx.domain,
            resolved_text=text,
            is_continuation=False,
            context=ctx,
        )

    @classmethod
    def _session_state_subject(cls) -> str:
        """Get active entity from SessionState (unified state)."""
        if cls._session_state and cls._session_state.active_entity:
            return cls._session_state.active_entity
        return ""

    @classmethod
    def _session_state_domain_val(cls) -> str:
        """Get active domain from SessionState (unified state)."""
        if cls._session_state and cls._session_state.active_domain:
            return cls._session_state.active_domain
        return ""

    @classmethod
    def _get_best_subject(cls) -> str:
        """Resolve subject from: SessionState -> ContinuityState -> EntityMemory."""
        subj = cls._session_state_subject()
        if subj:
            return subj
        if cls._state.active_subject:
            return cls._state.active_subject
        if cls._entity_memory:
            mem_entity = cls._entity_memory.get_last_entity()
            if mem_entity and mem_entity.name:
                return mem_entity.name
        return ""

    @classmethod
    def _get_best_domain(cls) -> Optional["DomainContinuationType"]:
        """Resolve domain from: SessionState -> ContinuityState.
        
        SessionState stores domain as a DomainContinuationType-compatible value
        (e.g. "media", "research", "conversation", "unknown").
        Falls back to ContinuityState if SessionState value doesn't match.
        """
        dom_val = cls._session_state_domain_val()
        if dom_val:
            try:
                return DomainContinuationType(dom_val.lower())
            except (ValueError, TypeError):
                pass
        return cls._state.active_domain

    @classmethod
    def _resolve_runtime_reference(cls, lower: str, ctx: ContinuationContext) -> Optional[str]:
        if not _RUNTIME_REF_PATTERNS[0].search(lower):
            return None
        # Skip runtime ref when command has its own domain-specific verb
        # e.g., "play it again" → should go through media pipeline, not resolve to browser action
        _media_verbs = ("play ", "show ", "watch ", "listen ")
        _browser_verbs = ("search ", "open ", "close ", "focus ", "switch ")
        _research_verbs = ("research ", "summarize ", "compare ")
        _file_verbs = ("create ", "save ", "edit ")
        _conversation_verbs = ("tell ", "explain ")
        if lower.startswith(_media_verbs + _browser_verbs + _research_verbs + _file_verbs + _conversation_verbs):
            return None
        last = cls._provider.get_last_successful_interaction()
        if not last:
            return None
        action = str(last.get("action", ""))
        target = str(last.get("target", ""))
        resolved = f"{action} {target}".strip()
        if not resolved:
            return None
        ctx.continuity_active = True
        ctx.reference_type = "runtime_ref"
        ctx.runtime_source = "runtime_context"
        ctx.domain = cls._state.active_domain or DomainContinuationType.UNKNOWN
        ctx.active_subject = target
        logger.info("[CONTINUITY_RUNTIME] runtime_ref original=%r resolved=%r domain=%s",
                    lower, resolved, ctx.domain.value)
        return resolved

    @classmethod
    def _resolve_pending_action(cls, lower: str, ctx: ContinuationContext) -> Optional[str]:
        pending = cls._provider.get_pending_media_action()
        if not pending:
            return None
        # Do NOT hijack interrogative queries (who/what/where/when/why/how) —
        # these are information requests, not action continuations.
        # "who directed it" must go to info resolution, not pending-action play.
        _interrogatives = frozenset({"who", "what", "where", "when", "why", "how"})
        first_word = lower.split()[0] if lower.split() else ""
        if first_word in _interrogatives:
            return None
        if lower not in cls._PENDING_ACTION_TRIGGERS and not cls._has_pronoun(lower):
            return None
        query = pending.get("query", "")
        action = pending.get("action", "")
        if not query:
            return None
        ctx.continuity_active = True
        ctx.reference_type = "pending_action"
        ctx.runtime_source = "media_context"
        ctx.active_subject = query
        ctx.domain = DomainContinuationType.MEDIA
        logger.info("[CONTINUITY_MEDIA] pending_action action=%s query=%s original=%r",
                    action, query, lower)
        resolved = lower
        if cls._has_pronoun(lower):
            resolved = re.sub(r"\b(it|that|this)\b", query, lower, flags=re.IGNORECASE)
        elif lower in ("yes", "yeah", "sure", "ok", "okay", "do it", "go ahead"):
            resolved = f"play {query}"
        return resolved

    @classmethod
    def _build_resolved(cls, text: str, ctx: ContinuationContext,
                        override_resolved: Optional[str] = None) -> ResolvedContinuation:
        if override_resolved is not None:
            resolved = override_resolved
        else:
            resolved = cls._resolve_with_context(text, ctx)
        tag = "CONTINUITY_RESOLVE"
        if ctx.runtime_source == "runtime_context":
            tag = "CONTINUITY_RUNTIME"
        elif ctx.runtime_source == "media_context":
            tag = "CONTINUITY_MEDIA"
        logger.info("[%s] domain=%s ref=%s original=%r resolved=%r",
                    tag, ctx.domain.value, ctx.reference_type, text, resolved)
        return ResolvedContinuation(
            domain=ctx.domain,
            resolved_text=resolved,
            is_continuation=True,
            context=ctx,
        )

    @classmethod
    def _detect_domain(cls, lower: str, ctx: ContinuationContext) -> None:
        domain_checks: list[tuple[set[str], DomainContinuationType]] = [
            (cls._MEDIA_KEYWORDS, DomainContinuationType.MEDIA),
            (cls._FILE_KEYWORDS, DomainContinuationType.FILE),
            (cls._TASK_KEYWORDS, DomainContinuationType.TASK),
            (cls._BROWSER_KEYWORDS, DomainContinuationType.BROWSER),
            (cls._RESEARCH_KEYWORDS, DomainContinuationType.RESEARCH),
            (cls._SYSTEM_KEYWORDS, DomainContinuationType.SYSTEM),
            (cls._CONVERSATION_KEYWORDS, DomainContinuationType.CONVERSATION),
        ]
        for keywords, domain in domain_checks:
            for kw in keywords:
                if lower.startswith(kw) or f" {kw}" in lower:
                    ctx.domain = domain
                    ctx.reference_type = "explicit"
                    logger.info("[CONTINUITY_DOMAIN] domain=%s keyword=%r", domain.value, kw)
                    return

    @classmethod
    def _resolve_continuation_markers(cls, lower: str, ctx: ContinuationContext) -> bool:
        clean = lower.rstrip(".")
        for marker in cls._CONTINUATION_MARKERS:
            if clean == marker or clean.startswith(marker + " "):
                if cls._state.active_domain:
                    ctx.domain = cls._state.active_domain
                    ctx.continuity_active = True
                    ctx.reference_type = "continuation"
                    ctx.active_subject = cls._state.subjects.get(cls._state.active_domain.value, "")
                    logger.info("[CONTINUITY_RESOLVE] continuation -> domain=%s",
                                cls._state.active_domain.value)
                    return True
                return False
        return False

    @classmethod
    def _resolve_affirmative_markers(cls, lower: str, ctx: ContinuationContext) -> bool:
        clean = lower.rstrip(".")
        if clean in cls._AFFIRMATIVE_MARKERS:
            if cls._state.active_domain:
                ctx.domain = cls._state.active_domain
                ctx.continuity_active = True
                ctx.reference_type = "affirmative"
                logger.info("[CONTINUITY_RESOLVE] affirmative -> domain=%s",
                            cls._state.active_domain.value)
                return True
            return False
        return False

    @classmethod
    def _has_pronoun(cls, lower: str) -> bool:
        for pattern in cls._PRONOUN_PATTERNS:
            if pattern.search(lower):
                return True
        return False

    @classmethod
    def _has_pronoun_ref(cls, lower: str) -> bool:
        """Check for him/her/them/they pronoun references (merged from reference_resolver)."""
        for pattern, _meaning in _PRONOUN_REF_PATTERNS:
            if pattern.search(lower):
                return True
        return False

    @classmethod
    def _matches_play_it_or_show_it(cls, lower: str) -> bool:
        return bool(_PLAY_IT_RE.match(lower) or _SHOW_IT_RE.match(lower))

    @classmethod
    def _matches_tell_more(cls, lower: str) -> bool:
        return bool(_TELL_MORE_RE.search(lower))

    @classmethod
    def _matches_replay(cls, lower: str) -> bool:
        return any(p.search(lower) for p in _REPLAY_PATTERNS)

    @classmethod
    def _matches_continuation_fu(cls, lower: str) -> bool:
        return bool(_CONTINUATION_PATTERNS_FU.search(lower))

    @classmethod
    def _matches_ordinal(cls, lower: str) -> bool:
        return any(p.search(lower) for p in _ORDINAL_PATTERNS)

    @classmethod
    def _resolve_with_context(cls, text: str, ctx: ContinuationContext) -> str:
        if not ctx.continuity_active:
            return text
        result = text
        subject = cls._state.subjects.get(cls._state.active_domain.value, "") if cls._state.active_domain else cls._state.active_subject
        if subject:
            # Only replace impersonal pronouns (it/that/this) — personal pronouns
            # (him/he/she/they) are resolved by MediaIntelligenceAdapter which
            # has a separate _answer_person context for who-questions.
            result = re.sub(r"\b(it|that|this)\b", subject, result,
                            flags=re.IGNORECASE)
        # Strip trailing " again" / " once more" for replay patterns
        # so "play believer again" becomes "play believer" (no fresh search with "again")
        lower = result.lower()
        if lower.endswith(" again"):
            result = result[:-6]
        elif lower.endswith(" once more"):
            result = result[:-10]
        ctx.resolved_input = result
        return result

    @classmethod
    def _clean_subject(cls, raw: str) -> str:
        """Remove trailing punctuation and leading noise words from extracted subject."""
        s = raw.strip().rstrip(".,!?;:")
        # Remove leading noise words: "the", "a", "an", "this", "that"
        _lead_noise = frozenset({"the", "a", "an", "this", "that"})
        words = s.split()
        while words and words[0].lower() in _lead_noise:
            words = words[1:]
        return " ".join(words).strip()

    @classmethod
    def update_state(cls, result: dict, command: str, domain: DomainContinuationType) -> None:
        cls._state.active_domain = domain
        cls._state.last_command = command
        cls._state.last_success = result.get("success", False)
        cls._state.timestamp = time.time()
        subject = result.get("target") or result.get("subject") or ""
        if not subject and result.get("success"):
            lower = command.lower().strip()
            for prefix in ("play ", "watch ", "show ", "search "):
                if lower.startswith(prefix):
                    rest = lower[len(prefix):].strip().strip("\"'").strip()
                    if rest:
                        subject = rest
                        break
        if subject:
            clean = cls._clean_subject(subject)
            if clean:
                subject = clean
            cls._state.active_subject = subject
            cls._state.subjects[domain.value] = subject
        action = result.get("action") or ""
        if action:
            cls._state.active_action = action
        if result.get("success"):
            cls._state.last_resolved = command
        # Sync to SessionState (unified state) when available
        if cls._session_state:
            if subject:
                cls._session_state.set_entity_and_domain(subject, domain.value)
            if action:
                cls._session_state.last_action = action
                cls._session_state.last_action_target = subject or command
        logger.info("[CONTINUITY_CONTEXT] domain=%s command=%r subject=%r success=%s",
                    domain.value, command, cls._state.active_subject,
                    result.get("success", False))

    @classmethod
    def reset(cls) -> None:
        cls._state = ContinuityState()
        cls._provider = ContinuityContextProvider()
        logger.info("[CONTINUITY_CONTEXT] reset")

    @classmethod
    def get_state(cls) -> ContinuityState:
        return cls._state

    @classmethod
    def set_state_subject(cls, subject: str, domain: Optional[DomainContinuationType] = None) -> None:
        cls._state.active_subject = subject
        if domain:
            cls._state.subjects[domain.value] = subject
        elif cls._state.active_domain:
            cls._state.subjects[cls._state.active_domain.value] = subject
        # Sync to SessionState
        if cls._session_state:
            dom_val = domain.value if domain else (cls._state.active_domain.value if cls._state.active_domain else "")
            if dom_val:
                cls._session_state.set_entity_and_domain(subject, dom_val)
            else:
                cls._session_state.active_entity = subject

    @classmethod
    def set_state_domain(cls, domain: DomainContinuationType) -> None:
        cls._state.active_domain = domain
        # Sync to SessionState
        if cls._session_state:
            cls._session_state.active_domain = domain.value
