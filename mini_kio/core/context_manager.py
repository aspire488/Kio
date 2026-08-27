"""
context_manager.py — Canonical Session Context Manager.

Single authoritative source for ALL session/continuity/conversation state.
Consolidates and replaces:
  - SessionState (mini_kio/llm/session_state.py)
  - ConversationContext (mini_kio/llm/conversation_context.py)
  - ContinuityResolver (mini_kio/core/continuity_resolver.py)
  - MediaEntityMemory (mini_kio/media/intelligence/media_entity_memory.py)
  - ArtifactMemory (mini_kio/media/intelligence/artifact_memory.py)
  - MediaContext (mini_kio/media/media_context.py)
  - IntegrationAdapter continuity logic (mini_kio/media/intelligence/integration_adapter.py)

Usage:
    ctx = get_context_manager("tg_2146008061")
    if ctx.is_continuation(text):
        text = ctx.resolve_references(text)
    ctx.update(result, command, domain)
    ctx.append_exchange(user_text, reply)
"""

from __future__ import annotations

import json
import logging
import re
import time
from dataclasses import dataclass, field
from typing import Optional

logger = logging.getLogger(__name__)

# ── Continuation detection primitives ──

_CONTINUATION_MARKERS: set[str] = {
    "continue", "continue please", "go on", "keep going", "proceed",
}

_AFFIRMATIVE_MARKERS: set[str] = {
    "yes", "yeah", "sure", "ok", "okay", "do it", "go ahead",
}

_MEDIA_KEYWORDS: set[str] = {
    "play ", "watch ", "pause", "resume", "stop",
    "next track", "next video", "next song",
    "previous track", "previous video", "previous song",
    "play highlight", "play trailer",
    "trailer", "highlights", "gameplay", "music video",
    "standings", "fixtures", "scores", "score ",
    "what happened", "who scored",
    "play more", "play something similar",
    "latest ", "what's the latest", "news about",
    "fifa", "world cup", "premier league", "nba", "nfl",
    "match ", " matches", "next match",
    "seek ", "volume", "mute", "unmute",
}

_BROWSER_KEYWORDS: set[str] = {
    "close ", "focus ", "switch to ",
    "next result", "previous result", "list tabs",
    "tabs", "chrome", "edge", "firefox",
    "refresh", "reload", "new tab",
    "summarize this page", "go back", "go forward",
    "open url", "open link",
}

_RESEARCH_KEYWORDS: set[str] = {
    "research ", "summarize ", "compare ",
    "give sources", "show sources", "references",
    "expand on",
}

_CONVERSATION_KEYWORDS: set[str] = {
    "tell me", "explain", "what is", "how does",
    "why is", "what are", "who is",
    "give example", "expand", "elaborate",
    "hello", "hi", "hey", "bye",
    "how are you", "what's up",
}

_FILE_KEYWORDS: set[str] = {
    "open folder", "create file", "create python file",
    "save ", "edit ", "fix bug",
    "list directory", "list files", "show files",
}

_PRONOUNS: set[str] = {"it", "this", "they", "them", "he", "she", "him", "his", "her", "their"}

_RUNTIME_REF_RE = re.compile(r"\b(again|do that again|do it again)\b", re.I)
# R3: again-suffixed variants ("search again", "play again", "play it again",
# "watch again", "open again", ...). Deliberately verb-scoped so phrases with
# a real target ("play messi again") do not match — they keep their target.
_AGAIN_SUFFIX_RE = re.compile(
    r"^(play|watch|search|open|show|go|run|start|find|read|write|create)"
    r"(?:\s+(?:it|that|this))?\s+again$",
    re.I,
)
_TELL_MORE_RE = re.compile(r"(tell me more|more info|more details|expand|elaborate)", re.I)
_ORDINAL_RE = re.compile(
    r"\b(first( one)?|second( one)?|third( one)?|fourth( one)?|fifth( one)?)\b", re.I
)
_THAT_CONJUNCTION_RE = re.compile(
    r"\bthat\b\s+(?:i|you|he|she|it|we|they|my|your|his|her|its|our|their)\b", re.I
)

_PRONOMINAL_STOPWORDS = frozenset({
    "it", "this", "that", "they", "them", "he", "she", "him", "her",
    "you", "me", "we", "us", "i", "my", "your", "his", "her", "its",
    "our", "their", "mine", "yours", "theirs",
})

_KNOWN_ENTITIES = frozenset({
    "python", "javascript", "typescript", "java", "rust", "go",
    "ruby", "php", "swift", "kotlin", "scala", "r", "matlab",
    "linux", "windows", "macos", "ubuntu", "debian", "fedora",
    "git", "docker", "kubernetes", "vscode", "chrome",
})

# Conversation retention: a real 30-50 turn companion conversation must stay
# coherent — KIO must remember its own opinions/statements from dozens of turns
# back ("you said earlier that X"). 10 exchanges pruned everything older than
# five turns and broke long-form recall. 60 retains a full active conversation
# in-session; the LLM prompt still injects a bounded RECENT window.
_MAX_EXCHANGES = 60

# BC-5: results from cognition-only owners (conversation, identity, status,
# operational readings) never produce an actionable referent. Their "target"
# is either the user's own sentence (converse) or an empty/synthetic value —
# storing it would poison the NEXT command's pronoun splice ("open it" ->
# "open <previous conversational sentence>"). Gating by action KIND is
# canonical: short one-word replies ("sure", "cool!") are covered even
# though the length guard below would let them through.
_NON_REFERENT_ACTIONS = frozenset({
    "converse", "identity", "health", "status", "battery", "uptime",
    "app_inventory", "lock_state", "system", "system_status",
    "list_tabs", "greeting", "acknowledge", "capability", "capabilities",
    "recommend", "search", "information_query", "entity_query",
    # Deterministic utility results (arithmetic, conversions, time/date)
    # produce a NUMBER or expression, NEVER a conversational referent.
    # Live failure: "6!" -> active_entity="6" poisoned the NEXT message's
    # pronoun splice, turning "why did you prefer that one" into
    # "why did you prefer 6 one" (LLM replied "I chose the sixth option").
    "calculate", "convert", "time", "date", "weather", "utility",
})


@dataclass
class PendingAction:
    action_type: str  # "search", "play", "open", etc.
    query: str = ""
    topic: str = ""
    executed: bool = False


_CONTEXT_MANAGERS: dict[str, "ContextManager"] = {}

_STATE_FACT_KEY = "session_context_state_json"
_STATE_TTL_S = 3600


def get_context_manager(session_id: str) -> "ContextManager":
    """Get the canonical ContextManager for a session."""
    if session_id not in _CONTEXT_MANAGERS:
        _CONTEXT_MANAGERS[session_id] = ContextManager(session_id=session_id)
    return _CONTEXT_MANAGERS[session_id]


def clear_context_manager(session_id: str) -> None:
    _CONTEXT_MANAGERS.pop(session_id, None)


# Backward compatibility aliases
get_session_context = get_context_manager
clear_session_context = clear_context_manager


class ContextManager:
    """Per-session unified state. Single source of truth for all context."""

    def __init__(self, session_id: str):
        self.session_id = session_id
        self.active_domain: Optional[str] = None
        self.active_entity: Optional[str] = None
        self.last_action: Optional[str] = None
        self.last_target: Optional[str] = None
        # Instance kind of the last successful action ("tab"/"window"/""):
        # structured metadata so a later "close it" operates on the CONCRETE
        # instance that was created ("open a new Telegram tab" then "close
        # it" must close that tab — never the native Telegram app).
        self.last_instance: Optional[str] = None
        self.last_command: str = ""
        self.last_success: bool = False
        self.pending_action: Optional[PendingAction] = None
        self.timestamp: float = 0.0
        # Canonical multi-target context: bounded collection of recent
        # successful targets (each keeps its own identity) so referent-set
        # commands ("close both", "close those apps", "the first and second")
        # resolve to the actual targets, never to a single last-target.
        self.recent_targets: list[dict] = []
        # Conversational pragmatics discourse state (owned by
        # mini_kio/core/pragmatics.py): user-set style preference from
        # meta-conversation control ("you're too formal" -> "casual"), the
        # running social energy, the last user/KIO acts, and the last
        # mentioned location (for "what time is it there").
        self.register_preference: str = "auto"
        self.social_energy: int = 0
        self.last_user_act: str = ""
        self.last_kio_act: str = ""
        self.last_location: str = ""

        self._exchanges: list[tuple[str, str]] = []
        self._topic_stack: list[str] = []
        self._entity_stack: list[str] = []

        self.rotation_counters: dict[str, int] = {}
        self._updated_at: float = time.time()
        self._persist_repo = None
        self._memory_override = None

    def set_entity_and_domain(self, entity: str, domain: str) -> None:
        self.active_entity = entity
        self.active_domain = domain

    # ── Exchange history (absorbed from ConversationContext) ──

    def append_exchange(self, user_text: str, reply: str) -> None:
        topic = self._extract_topic(user_text)
        if topic:
            self._topic_stack.append(topic)
        entities = self._extract_entities(user_text)
        for e in entities:
            if e.lower() not in (self._entity_stack[-1].lower() if self._entity_stack else ""):
                self._entity_stack.append(e)
        self._exchanges.append((user_text, reply))
        self._prune_exchanges()
        # Persist to DB so history survives process restarts
        try:
            from mini_kio.memory.memory_store import MemoryStore
            ms = MemoryStore(session_id=self.session_id)
            ms.append("user", user_text)
            ms.append("assistant", reply)
        except Exception:
            pass

    def _prune_exchanges(self) -> None:
        while len(self._exchanges) > _MAX_EXCHANGES:
            self._exchanges.pop(0)
        while len(self._topic_stack) > _MAX_EXCHANGES:
            self._topic_stack.pop(0)
        while len(self._entity_stack) > _MAX_EXCHANGES:
            self._entity_stack.pop(0)

    def sync_from_memory(self, memory_store) -> None:
        try:
            history = memory_store.last_n_messages(_MAX_EXCHANGES * 2)
            self._exchanges.clear()
            user_msg = None
            for entry in history:
                if getattr(entry, 'role', None) == "user":
                    user_msg = getattr(entry, 'message', str(entry))
                elif getattr(entry, 'role', None) == "assistant" and user_msg is not None:
                    self._exchanges.append((user_msg, getattr(entry, 'message', str(entry))))
                    user_msg = None
        except Exception:
            pass

    def get_history_window(self, n: int = 10) -> list[tuple[str, str]]:
        return self._exchanges[-n:] if self._exchanges else []

    def exchange_count(self) -> int:
        return len(self._exchanges)

    def recent_topic(self) -> Optional[str]:
        if self._topic_stack:
            return self._topic_stack[-1]
        return None

    def recent_entity(self) -> Optional[str]:
        if self._entity_stack:
            return self._entity_stack[-1]
        return self.recent_topic()

    def last_user_input(self) -> Optional[str]:
        if self._exchanges:
            return self._exchanges[-1][0]
        return None

    def last_assistant_reply(self) -> Optional[str]:
        if self._exchanges:
            return self._exchanges[-1][1]
        return None

    def search_exchanges(self, topic: str, limit: int = 5) -> list[tuple[str, str]]:
        """Search exchange history for topic-matching user statements.
        Returns matching (user_text, kio_reply) pairs, most recent first.
        Used for 'what did I say about X?' / 'what were we discussing?' queries."""
        if not topic or not self._exchanges:
            return []
        topic_low = topic.lower().strip()
        stop = {"the", "about", "what", "that", "this", "with", "from", "have",
                "were", "was", "been", "being", "does", "doing", "will",
                "would", "could", "should", "tell", "said", "asked"}
        words = [w for w in __import__('re').findall(r'[a-z]{3,}', topic_low)
                 if w not in stop]
        if not words:
            return []
        matches: list[tuple[float, tuple[str, str]]] = []
        for user_text, kio_reply in reversed(self._exchanges):
            if not user_text:
                continue
            ul = user_text.lower()
            score = 0.0
            if topic_low in ul:
                score = 1.0
            else:
                matched = sum(1 for w in words if w in ul)
                if matched > 0:
                    score = matched / len(words) * 0.8
            if score > 0:
                matches.append((score, (user_text, kio_reply)))
            if len(matches) >= limit * 2:
                break
        matches.sort(key=lambda x: -x[0])
        return [m[1] for m in matches[:limit]]

    def recent_topics_summary(self, max_topics: int = 5) -> str:
        """Compact summary of recent conversation topics.
        Injected into the prompt so the LLM knows what was discussed."""
        if not self._topic_stack:
            return ""
        # Deduplicate consecutive same topics
        unique = []
        for t in reversed(self._topic_stack):
            if not unique or t != unique[-1]:
                unique.append(t)
            if len(unique) >= max_topics:
                break
        if not unique:
            return ""
        return "Recent topics: " + ", ".join(reversed(unique)) + "."

    @staticmethod
    def _extract_topic(text: str) -> Optional[str]:
        lower = text.lower().strip().strip(".,!?;:")
        if not lower:
            return None
        _prefixes = [
            "what is ", "what are ", "tell me about ", "what does ", "what do ",
            "what's ", "whats ", "explain ", "define ", "teach me ",
            "who created ", "who is ", "who made ", "who wrote ",
            "who do you think ", "who do you ",
        ]
        for prefix in _prefixes:
            if lower.startswith(prefix):
                topic = text[len(prefix):].strip().strip(".,!?;:")
                if topic and len(topic) < 60 and topic.lower() not in _PRONOMINAL_STOPWORDS:
                    return topic
        m = re.search(
            r"(?:what|how)\s+(?:is|are|does|do)\s+(.+?)\s+(?:work|mean|do|used|look\s+like)", lower
        )
        if m:
            topic = m.group(1).strip()
            if topic.lower() not in _PRONOMINAL_STOPWORDS:
                return topic
        m = re.search(r"tell\s+me\s+more\s+about\s+(.+)", lower)
        if m:
            topic = m.group(1).strip()
            if topic.lower() not in _PRONOMINAL_STOPWORDS:
                return topic
        words = lower.split()
        for word in words:
            clean = word.strip(".,!?;:'\"")
            if clean in _KNOWN_ENTITIES:
                return clean
        original_words = text.split()
        for i, word in enumerate(original_words):
            if i == 0:
                continue
            clean = word.strip(".,!?;:'\"")
            if clean and clean[0].isupper() and len(clean) > 1 and clean.lower() not in _PRONOMINAL_STOPWORDS:
                return clean
        return None

    @staticmethod
    def _extract_entities(text: str) -> list[str]:
        entities: list[str] = []
        for word in text.split():
            clean = word.strip(".,!?;:'\"()")
            if len(clean) > 1 and clean[0].isupper() and clean.lower() not in _PRONOMINAL_STOPWORDS:
                entities.append(clean)
        return entities

    # ── Persistence via FactRepository (absorbed from SessionState) ──

    def _get_repo(self):
        if self._persist_repo is None:
            try:
                from mini_kio.backend.repositories import FactRepository
                self._persist_repo = FactRepository()
            except Exception:
                pass
        return self._persist_repo

    def _state_to_dict(self) -> dict:
        return {
            "active_domain": self.active_domain,
            "active_entity": self.active_entity,
            "last_action": self.last_action,
            "last_target": self.last_target,
            "last_command": self.last_command,
            "updated_at": self._updated_at,
        }

    def _persist_state(self) -> None:
        repo = self._get_repo()
        if repo is None:
            return
        try:
            repo.set_fact(self.session_id, _STATE_FACT_KEY, json.dumps(self._state_to_dict()))
            self._updated_at = time.time()
        except Exception as e:
            logger.debug("Failed to persist session context: %s", e)

    def _hydrate_state(self) -> None:
        repo = self._get_repo()
        if repo is None:
            return
        try:
            raw = repo.get_fact(self.session_id, _STATE_FACT_KEY)
            if raw:
                data = json.loads(raw)
                self.active_domain = data.get("active_domain")
                self.active_entity = data.get("active_entity")
                self.last_action = data.get("last_action")
                self.last_target = data.get("last_target")
                self.last_command = data.get("last_command", "")
                self._updated_at = data.get("updated_at", time.time())
                age = time.time() - self._updated_at
                if age > _STATE_TTL_S:
                    self.reset()
                    return
                logger.info("ContextManager restored: entity=%s domain=%s age=%.0fs",
                            self.active_entity, self.active_domain, age)
        except Exception as e:
            logger.debug("Failed to hydrate session context: %s", e)

    # ── Fact/memory access (absorbed from SessionState) ──

    def get_all_facts(self) -> dict[str, str]:
        repo = self._get_repo()
        if repo is None:
            return {}
        try:
            return repo.get_all_facts(self.session_id)
        except Exception:
            return {}

    @property
    def memory(self):
        if self._memory_override is not None:
            return self._memory_override
        try:
            from mini_kio.memory.memory_store import MemoryStore
            from mini_kio.backend.repositories import MemoryRepository, FactRepository
            return MemoryStore(
                session_id=self.session_id,
                memory_repo=MemoryRepository(),
                fact_repo=FactRepository(),
            )
        except Exception:
            from mini_kio.memory.memory_store import MemoryStore
            return MemoryStore(session_id=self.session_id)

    @memory.setter
    def memory(self, value):
        self._memory_override = value

    def append_message(self, role: str, content: str) -> None:
        try:
            self.memory.append(role, content)
        except Exception:
            pass

    def clear_pending_action(self) -> None:
        self.pending_action = None

    def has_pending_action(self) -> bool:
        return self.pending_action is not None and not self.pending_action.executed

    def persist_trace(self, trace) -> None:
        try:
            from mini_kio.backend.repositories import TraceRepository
            TraceRepository().save(self.session_id, trace)
        except Exception:
            pass

    def refresh_ttl(self) -> None:
        self._updated_at = time.time()

    @property
    def context(self):
        return self

    def clear_topic_stack(self) -> None:
        self._topic_stack.clear()

    def clear_entity_stack(self) -> None:
        self._entity_stack.clear()

    def get_lesson_state(self) -> tuple[bool, int]:
        return False, 0

    def get_session_mode(self) -> str:
        return "conversational"

    def set_session_mode(self, mode: str) -> None:
        pass

    def get_diagnostics(self) -> dict:
        return {
            "exchange_count": len(self._exchanges),
            "topic_count": len(self._topic_stack),
            "entity_count": len(self._entity_stack),
            "active_domain": self.active_domain,
            "active_entity": self.active_entity,
        }

    # ── Continuity detection (single authoritative check) ──

    def is_continuation(self, text: str) -> bool:
        """Returns True if `text` is a continuation of the current session context."""
        if not text or not self.active_domain:
            return False
        lower = text.lower().strip()
        if not lower:
            return False

        # Pure continuation markers
        if lower.rstrip(".") in _CONTINUATION_MARKERS:
            return True

        # Pure affirmative markers  
        if lower.rstrip(".") in _AFFIRMATIVE_MARKERS:
            return True

        # Runtime references ("again")
        if _RUNTIME_REF_RE.search(lower):
            return True

        # Domain keyword detection
        domain = self._detect_domain(lower)

        # Pronoun reference — only if NOT conjunction "that"
        if self._has_pronoun(lower):
            if domain is None:
                domain = self.active_domain
            return True

        # Tell-more / ordinal patterns
        if _TELL_MORE_RE.search(lower) or _ORDINAL_RE.search(lower):
            return True

        return False

    def resolved_text(self, text: str) -> str:
        """Backward-compat alias for resolve_references (tests + legacy callers)."""  
        return self.resolve_references(text)

    def resolve_references(self, text: str) -> str:
        """Resolve continuity references and return the modified command string.

        Canonical home of contextual-reference resolution. Merged the
        live pipeline resolver guards (media/transport/forget passthrough,
        "again" via runtime buffer, pronoun with last-target fallback) with
        the pre-existing S1/S2 marker handling.
        """
        if not text:
            return text
        lower = text.lower().strip()

        # G4: "again" → repeat last successful interaction (runtime buffer).
        # Live source is get_last_successful_interaction(must_have_target=False),
        # which is success-gated and permits no-target records — the old
        # _RUNTIME_TRACKER (target-guarded write) could not represent either.
        # R3: extended to again-suffixed variants ("search again", "play it
        # again", "watch again", ...). Placed before G1 so media verbs with an
        # "again" suffix reach it instead of the playback passthrough; the
        # variant regex is verb-scoped, so targets ("play messi again") still
        # fall through to G1 untouched. G1/G2/G3/S1/S2 blocks are unchanged.
        # RC3/RC4: verb-scoped again-replay.
        # - "play again"/"play it again"/"watch again" must replay the last
        #   successful PLAY interaction only — never a pause/resume/search
        #   (previously "play again" replayed the last arbitrary success, so
        #   "Play X, Pause, Play again" replied "Paused").
        # - "search again" must re-run the same controlled action:
        #   search_youtube is preserved so the R11 controlled path is reused
        #   instead of degrading into a generic Google search.
        _again_match = _AGAIN_SUFFIX_RE.fullmatch(lower)
        _again_verb = _again_match.group(1).lower() if _again_match else None
        if _again_verb or lower in ("again", "do it again"):
            from mini_kio.core.runtime import get_last_successful_interaction
            last = None
            if _again_verb in ("play", "watch"):
                last = get_last_successful_interaction(
                    action_type="play", must_have_target=True,
                )
                if not last:
                    # Fall through: MediaManager._AGAIN handles bare "play
                    # again" truthfully ("Nothing to replay") when no play
                    # has succeeded yet.
                    return text
            elif _again_verb in ("search", "find"):
                for _at in ("search_youtube", "search", "search_web"):
                    last = get_last_successful_interaction(
                        action_type=_at, must_have_target=True,
                    )
                    if last:
                        break
                if not last:
                    return text
            else:
                last = get_last_successful_interaction(must_have_target=False)
            if last:
                action = (
                    last.get("action", "")
                    .replace("_app", "")
                    .replace("_web", "")
                    .replace("_system", "")
                    .replace("_folder", "")
                )
                # "_youtube" is intentionally preserved above: "Search again"
                # must keep the controlled search_youtube action (R11), not
                # become a generic Google search_web.
                target = str(last.get("target", ""))
                if action == "search_youtube" and target:
                    return f"search {target} in youtube"
                if action == "play":
                    return f"play {target}" if target else "play"
                resolved = f"{action} {target}".strip()
                if resolved:
                    return resolved
            return text

        # G1: media passthrough — do not resolve pronouns inside playback verbs
        if lower.startswith(("play ", "watch ", "seek ", "turn ")):
            return text

        # G2: transport passthrough
        if lower in ("pause", "resume", "stop", "next", "previous", "mute", "unmute"):
            return text

        # G3: forget passthrough — memory commands own their own semantics
        if lower.startswith("forget"):
            return text

        # S1: continuation markers → reuse last target [NEWLY LIVE]
        if lower.rstrip(".") in _CONTINUATION_MARKERS:
            if self.last_target:
                action = self.last_action or "search"
                if action == "search_web":
                    action = "search for"
                return f"{action} {self.last_target}"
            return text

        # S2: affirmative → proceed with pending [NEWLY LIVE]
        if lower.rstrip(".") in _AFFIRMATIVE_MARKERS:
            if self.pending_action and not self.pending_action.executed:
                return f"{self.pending_action.action_type} {self.pending_action.query}"
            return text

        # S3: affirmative + imperative pronoun ("yeah do that", "okay do it",
        # "sure go ahead") inherits the pending action or the last successful
        # interaction — the user is confirming the previous concrete action,
        # not starting a fresh vague command.
        _AFFIRM_DO_RE = re.compile(
            r"^(?:yeah|yes|yep|yup|sure|ok|okay|alright|aight)\s+"
            r"(?:do|go|run|make|open|close|create|search|play|show|start|launch)\s+"
            r"(?:it|that|this)$",
            re.I,
        )
        if _AFFIRM_DO_RE.match(lower):
            if self.pending_action and not self.pending_action.executed:
                return f"{self.pending_action.action_type} {self.pending_action.query}"
            from mini_kio.core.runtime import get_last_successful_interaction
            last = get_last_successful_interaction(must_have_target=False)
            if last:
                action = str(last.get("action", "") or "")
                for _suffix in ("_app", "_web", "_system", "_folder"):
                    action = action.replace(_suffix, "")
                target = str(last.get("target", "") or "")
                resolved = f"{action} {target}".strip()
                if resolved:
                    return resolved
            return text

        # Power-family passthrough: "is it charging" / "how's the battery" are
        # deterministic battery queries — their referents must never be
        # rewritten by generic pronoun resolution ("it" has no app antecedent).
        if re.search(r"\b(battery|charge|charging|power|plugged)\b", lower):
            return text

        # Multi-referent close family: "close both", "shut these two",
        # "close those apps", "close the first and second" resolve to the
        # recent target collection and reuse the multi-step machinery so each
        # target closes independently (one failure never corrupts the others).
        _multi_ref = re.match(
            r"^(?:close|shut|quit|kill|end)\s+"
            r"(?:both|these\s+two|those\s+two|the\s+two|these|those|all\s+(?:of\s+)?(?:them|those|these))"
            r"(?:\s+(?:apps?|applications|windows|tabs|ones?))?\s*$",
            lower,
        )
        _ordinal_ref = re.match(
            r"^(?:close|shut|quit|kill|end)\s+(?:the\s+)?(first|second|third|fourth|fifth)"
            r"\s+and\s+(?:the\s+)?(first|second|third|fourth|fifth)\s*$",
            lower,
        )
        # recent_targets only ever holds successful executions (update() is the
        # sole writer and gates on result success), so a name presence check is
        # the correct filter — failed executions never become context.
        refs = [r for r in self.recent_targets if r.get("name")]
        names = [str(r["name"]) for r in refs]
        if _multi_ref and len(names) >= 2:
            picks = names[-2:]
            return f"close {picks[0]} and {picks[1]}"
        if _ordinal_ref and len(names) >= 2:
            order = {"first": 0, "second": 1, "third": 2, "fourth": 3, "fifth": 4}
            i, j = order[_ordinal_ref.group(1)], order[_ordinal_ref.group(2)]
            if i < len(names) and j < len(names) and i != j:
                return f"close {names[i]} and {names[j]}"

        # Referent phrases: "open the app" / "open the website" — a
        # conversational modality correction must preserve entity identity
        # while changing modality ("Open X. Actually open the app." -> native
        # X; "...open the website." -> web X). Only fires when an active
        # entity exists — "the app" without any antecedent stays untouched.
        _referent_phrase = re.search(
            r"\b(?:the\s+)?(?:desktop\s+)?(app|application|program|software|website|web\s+version|webpage|site)\b",
            lower,
        )
        if _referent_phrase and self.active_entity:
            # NEVER expand when the command already names the entity —
            # "open the Spotify app" must stay "spotify", not become
            # "open the Spotify the spotify app". The phrase is only a
            # bare referent when no entity token is present at all.
            if re.search(r"\b" + re.escape(self.active_entity.lower()) + r"\b", lower):
                return text
            phrase = _referent_phrase.group(1).lower()
            if phrase in ("website", "web version", "webpage", "site"):
                return re.sub(
                    r"\b(?:the\s+)?(?:website|web\s+version|webpage|site)\b",
                    f"{self.active_entity} on the web", text, flags=re.IGNORECASE, count=1,
                )
            return re.sub(
                r"\b(?:the\s+)?(?:desktop\s+)?(?:app|application|program|software)\b",
                f"the {self.active_entity} app", text, flags=re.IGNORECASE, count=1,
            )

        # INSTANCE-AWARE close/focus: after "open a new Telegram tab" the
        # referent "it" means the CREATED TAB — "close it" must close that
        # exact tab, never the native Telegram app of the same name. The last
        # successful action's instance kind ("tab"/"window") is structured
        # context and scopes the rewrite BEFORE generic pronoun substitution.
        _inst_pronoun = re.match(
            r"^(close|shut|quit|kill|end|focus|switch\s+to)\s+(?:the\s+)?"
            r"(it|that|this)(?:\s+(?:tab|window))?\s*$",
            lower,
        )
        if _inst_pronoun and self.active_entity and self.last_instance in ("tab", "window"):
            verb = _inst_pronoun.group(1).lower()
            entity = self.active_entity
            # Tab instance: always tab scope ("close <entity> tab" -> close_tab).
            if self.last_instance == "tab":
                if verb in ("focus", "switch to"):
                    return f"focus {entity}"
                return f"close {entity} tab"
            # Window instance: native apps close at app scope; webapps close
            # their tab (window-scope browser ops aren't modeled — never a
            # fake window close).
            try:
                from mini_kio.core.app_operator import _find_in_registry
                is_native = _find_in_registry(entity) is not None
            except Exception:
                is_native = False
            if verb == "close":
                return f"close the {entity} window" if is_native else f"close {entity} tab"
            return f"focus {entity}"

        # G5: pronoun → active_entity, then session last_target fallback
        # A pronoun in a QUALITY-MODIFIER construction ("make it concise",
        # "keep it short", "write it as a poem", "turn it professional") is
        # a style/format modifier, NEVER a target referent — splicing the
        # active entity in produced "make notepad concise" inside a document
        # request. Bounded modifier verb + style noun/adj grammar.
        if re.search(
            r"\b(?:make|keep|set|turn|render|leave|write|put)\s+"
            r"(?:it|that|this)\s+(?:(?:into|as)\s+)?(?:a|an|the)?\s*"
            r"(?:concise|short|brief|professional|formal|detailed|simple|poetic|"
            r"casual|fun|long|clear|clean|neat|poem|essay|report|bullet|list|table)\b",
            lower,
        ):
            return text
        # SEMANTIC-EDIT guard: "copy it", "paste that", "save this",
        # "select it", "undo it" are SEMANTIC ACTIONS whose pronoun is the
        # generic object of the action — the classifier recognizes the action
        # (COPY / PASTE / SAVE / SELECT_ALL / UNDO / REDO) and the executor
        # resolves the contextual target. Splicing the entity here produced
        # "copy notepad", which the classifier could not recognize and the
        # whole request fell to the LLM/conversation path. Bounded verb list.
        if re.search(
            r"\b(?:copy|paste|save|select|undo|redo|cut|delete|erase)\s+\b(it|that|this|them|these|those)\b",
            lower,
        ):
            return text
        # DISCOURSE guard: the G5 pronoun splice exists for COMMAND
        # referents ("open it", "play that", "close this", "focus the
        # second one") — a pronoun anchored by an imperative/action verb. It
        # must NEVER fire on conversational discourse ("why did you prefer
        # that one", "would you pick it", "what about the other one", "do
        # you still like this") — those refer to the discussion's subject
        # and are resolved by the conversational generator with full
        # history, not by splicing a stale command entity. Live failure:
        # after a math turn left active_entity="6", the splice rewrote
        # "why did you prefer that one" -> "why did you prefer 6 one" and
        # the LLM answered "I chose the sixth option". Rule: only splice a
        # pronoun when an ACTION VERB appears in the message (the command
        # frame) and the message is not a discourse question about prior
        # talk. Generic verb list, never per-phrase.
        _COMMAND_ANCHOR_RE = re.compile(
            r"\b(?:open|close|shut|quit|kill|end|play|pause|resume|stop|search|show|"
            r"list|start|launch|focus|switch\s+to|navigate|go\s+to|find|get|run|"
            r"install|uninstall|download|read|delete|rename|copy|move|take|capture|"
            r"create|make|write|send|set|turn\s+on|turn\s+off)\b",
            re.I,
        )
        _DISCOURSE_QUESTION_RE = re.compile(
            r"\b(?:why|what|which|who|how|would|could|should|do|does|did)\b.*"
            r"\b(it|that|this|one|ones)\b|"
            r"\b(?:prefer|think|recommend|suggest|pick|choose|go\s+with|like|enjoy)\b.*"
            r"\b(it|that|this|one|ones)\b|"
            r"\b(?:instead|rather\s+than|compared\s+to|vs\.?|over)\b.*"
            r"\b(it|that|this|one|ones)\b|"
            r"^\s*(?:what|how)\s+about\b.*\b(it|that|this|one|ones)\b|"
            # Media modifier commands: "turn it up", "make it louder" —
            # "it" is the generic media object (volume/playback), NEVER a
            # referent to splice ("turn 6 up" would be garbage).
            r"\b(?:turn|make|set|get)\s+(?:it|that|this)\s+(?:up|down|louder|quieter|softer|higher|lower)\b"
        )
        # Only splice when an ACTION VERB anchors the pronoun — the command
        # frame. A bare discourse reference ("why did you prefer that one")
        # with no command verb is never spliced; the conversational generator
        # resolves it from history instead.
        if (
            re.search(r"\b(it|that|this)\b", lower)
            and _COMMAND_ANCHOR_RE.search(lower)
            and not _DISCOURSE_QUESTION_RE.search(lower)
        ):
            # BC-4: never splice a sentence-length referent. A conversational
            # question stored by mistake (or any long entity) would be injected
            # verbatim into a fresh command. Referents must look like concise
            # entity names to be spliced.
            def _spliceable(ref: str) -> bool:
                ref = (ref or "").strip()
                return bool(ref) and len(ref) <= 48 and ref.count(" ") <= 6 \
                    and not any(ch in ref for ch in "?!/;:()")

            if self.active_entity and _spliceable(self.active_entity):
                resolved = re.sub(
                    r"\b(it|that|this)\b", self.active_entity, text, flags=re.IGNORECASE
                )
                if resolved != text:
                    logger.info("[CONTEXT_RESOLVE] pronoun: %r → %r", text, resolved)
                    return resolved.strip()
            if self.last_target and _spliceable(self.last_target):
                resolved = re.sub(
                    r"\b(it|that|this)\b", self.last_target, text, flags=re.IGNORECASE
                )
                if resolved != text:
                    logger.info("[CONTEXT_RESOLVE] pronoun: %r → %r", text, resolved)
                    return resolved.strip()

        return text

    # ── State update ──

    def update(self, result: dict, command: str, domain: str = "") -> None:
        self.last_command = command
        self.last_success = bool(result.get("success", False))
        self.timestamp = time.time()
        if domain:
            self.active_domain = domain

        target = result.get("target") or result.get("subject") or ""
        clean = None
        # BC-5: cognition-only results never feed the action-referent store.
        # A conversational reply (action="converse"), an identity/status
        # answer, or an operational reading (health/battery/inventory) has NO
        # actionable referent — a later "open it" must not splice the reply
        # text into a command. This gates by ACTION KIND (canonical), not by
        # length: even a one-word conversational reply ("sure", "cool!") can
        # never become the referent that poisons the next request.
        action_kind = result.get("action") or ""
        if action_kind in _NON_REFERENT_ACTIONS:
            target = ""
        # Failed executions MUST NOT become conversational context — only
        # successful results may set the referent (a failed "open X" never
        # makes a later "close it" target X). Exception: a failed PLAY keeps
        # what the user asked for so a retry follow-up can re-attempt it —
        # media has its own retry machinery and "play X, continue" must retry.
        if result.get("success") and target:
            # BC-3: the stored conversational referent must be a user-safe name.
            # Raw serialized capability targets ("chrome::open_url::https://...")
            # and raw URLs must NEVER become the referent that a later
            # "close it"/"open that" splices back into a command.
            from mini_kio.core.target_ref import safe_target_name
            clean = safe_target_name(str(target)).strip().rstrip(".,!?;:")
            # BC-4: belt-and-suspenders length guard on top of the action-kind
            # gate above — a sentence-length referent must never be stored, it
            # would be spliced into the NEXT command. Only concise entity-like
            # names are valid referents.
            if clean and (
                len(clean) > 48
                or clean.count(" ") > 6
                or any(ch in clean for ch in "?!/;:()")
            ):
                clean = None
            if clean:
                self.active_entity = clean
                self.last_target = clean
        elif command.lower().startswith("play ") and not result.get("success"):
            # Failed play: still remember what user tried to play (retry path)
            entity = command[5:].strip()
            if entity and len(entity) > 3:
                self.active_entity = entity
                self.last_target = entity

        action = result.get("action") or ""
        if action:
            self.last_action = action
        # Remember the concrete instance kind created ("tab"/"window") so a
        # later referent command ("close it") operates at that scope. Only
        # successful results set it — a failed open never claims an instance.
        if result.get("success"):
            inst = result.get("instance") or ""
            self.last_instance = str(inst) if str(inst) in ("tab", "window") else None

        if result.get("success"):
            self.pending_action = None  # mark executed

        # Multi-target context maintenance: only successful executions become
        # referents (failed executions must NEVER become context). Consecutive
        # duplicates merge — a repeated "open X" is the same target, not two.
        if result.get("success") and clean:
            entry = {"name": clean, "action": action, "ts": time.time()}
            if self.recent_targets and self.recent_targets[-1].get("name") == clean:
                self.recent_targets[-1] = entry
            else:
                self.recent_targets.append(entry)
                if len(self.recent_targets) > 8:
                    self.recent_targets.pop(0)

        logger.info(
            "[CONTEXT_UPDATE] domain=%s entity=%s action=%s success=%s",
            self.active_domain, self.active_entity, self.last_action, result.get("success"),
        )

    def set_pending_search(self, query: str, topic: str = "") -> None:
        self.pending_action = PendingAction(action_type="search", query=query, topic=topic)

    def has_pending_search(self) -> bool:
        return self.pending_action is not None and not self.pending_action.executed

    def mark_pending_executed(self) -> None:
        if self.pending_action:
            self.pending_action.executed = True

    def clear_exchanges(self) -> None:
        self._exchanges.clear()
        self._topic_stack.clear()
        self._entity_stack.clear()

    def reset(self) -> None:
        self.active_domain = None
        self.active_entity = None
        self.last_action = None
        self.last_target = None
        self.last_command = ""
        self.last_success = False
        self.pending_action = None
        self.timestamp = 0.0
        self.register_preference = "auto"
        self.social_energy = 0
        self.last_user_act = ""
        self.last_kio_act = ""
        self.last_location = ""
        self.clear_exchanges()

    # ── Internal helpers ──

    def _detect_domain(self, lower: str) -> Optional[str]:
        checks = [
            (_MEDIA_KEYWORDS, "media"),
            (_FILE_KEYWORDS, "file"),
            (_BROWSER_KEYWORDS, "browser"),
            (_RESEARCH_KEYWORDS, "research"),
            (_CONVERSATION_KEYWORDS, "conversation"),
        ]
        for keywords, domain in checks:
            for kw in keywords:
                if lower.startswith(kw) or f" {kw}" in lower:
                    logger.debug("[CONTEXT_DOMAIN] keyword=%r → %s", kw, domain)
                    return domain
        return None

    def _has_pronoun(self, lower: str) -> bool:
        # Check _PRONOUNS word set
        words = set(lower.split())
        if words & _PRONOUNS:
            return True
        # "that" — only if NOT conjunction usage
        if "that" in words:
            if not _THAT_CONJUNCTION_RE.search(lower):
                return True
        return False

# Backward-compat alias
SessionContext = ContextManager
