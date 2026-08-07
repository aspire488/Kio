"""
context_manager.py — Unified Session Context.

Single authoritative source for: active domain/entity, continuity detection,
exchange history, topic/entity stacks, pending actions, and persistence.

Replaces:
  - SessionState.active_* / last_action / persistence
  - ConversationContext exchange history, topic/entity stacks
  - ContinuityResolver._state (class-level static)
  - IntegrationAdapter._is_continuation_query (independent pronoun/reference logic)

Usage:
    ctx = get_session_context("tg_2146008061")
    if ctx.is_continuation(text):
        text = ctx.resolved_text(text)
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
    r"^(?:play|watch|search|open|show|go|run|start|find|read|write|create)"
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

_MAX_EXCHANGES = 10


@dataclass
class PendingAction:
    action_type: str  # "search", "play", "open", etc.
    query: str = ""
    topic: str = ""
    executed: bool = False


_SESSION_CONTEXTS: dict[str, "SessionContext"] = {}

_STATE_FACT_KEY = "session_context_state_json"
_STATE_TTL_S = 3600


def get_session_context(session_id: str) -> "SessionContext":
    if session_id not in _SESSION_CONTEXTS:
        _SESSION_CONTEXTS[session_id] = SessionContext(session_id=session_id)
    return _SESSION_CONTEXTS[session_id]


def clear_session_context(session_id: str) -> None:
    _SESSION_CONTEXTS.pop(session_id, None)


class SessionContext:
    """Per-session unified state. Single source of truth."""

    def __init__(self, session_id: str):
        self.session_id = session_id
        self.active_domain: Optional[str] = None
        self.active_entity: Optional[str] = None
        self.last_action: Optional[str] = None
        self.last_target: Optional[str] = None
        self.last_command: str = ""
        self.last_success: bool = False
        self.pending_action: Optional[PendingAction] = None
        self.timestamp: float = 0.0

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
                logger.info("SessionContext restored: entity=%s domain=%s age=%.0fs",
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
        """Resolve continuity references and return the modified command string.

        P1.2: canonical home of contextual-reference resolution. Merged the
        live pipeline resolver guards (media/transport/forget passthrough,
        "again" via runtime buffer, pronoun with last-target fallback) with
        the pre-existing S1/S2 marker handling. S1/S2 are newly-live on the
        pipeline path and are covered as new surface in validation.
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
        if (
            lower == "again"
            or lower == "do it again"
            or _AGAIN_SUFFIX_RE.fullmatch(lower)
        ):
            from mini_kio.core.runtime import get_last_successful_interaction
            last = get_last_successful_interaction(must_have_target=False)
            if last:
                action = (
                    last.get("action", "")
                    .replace("_app", "")
                    .replace("_web", "")
                    .replace("_system", "")
                    .replace("_folder", "")
                    .replace("_youtube", "")
                )
                target = str(last.get("target", ""))
                resolved = f"{action} {target}".strip()
                return resolved

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

        # G5: pronoun → active_entity, then session last_target fallback
        if re.search(r"\b(it|that|this)\b", lower):
            if self.active_entity:
                resolved = re.sub(
                    r"\b(it|that|this)\b", self.active_entity, text, flags=re.IGNORECASE
                )
                if resolved != text:
                    logger.info("[CONTEXT_RESOLVE] pronoun: %r → %r", text, resolved)
                    return resolved.strip()
            if self.last_target:
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
        if target:
            clean = target.strip().rstrip(".,!?;:")
            _blocked = {"http://", "https://", "www."}
            if not any(clean.lower().startswith(p) for p in _blocked):
                self.active_entity = clean
                self.last_target = clean
        elif command.lower().startswith("play ") and not target:
            # Failed play: still remember what user tried to play
            entity = command[5:].strip()
            if entity and len(entity) > 3:
                self.active_entity = entity
                self.last_target = entity

        action = result.get("action") or ""
        if action:
            self.last_action = action

        if result.get("success"):
            self.pending_action = None  # mark executed

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
