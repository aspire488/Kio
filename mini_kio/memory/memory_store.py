"""
memory_store.py — Backward-compatible memory store delegating to repositories.

Provides the same public API as the original PostgreSQL-backed MemoryStore
but internally delegates all persistence to MemoryRepository and FactRepository
via SQLAlchemy + SQLite (singleton engine from mini_kio.backend.db).
"""

from __future__ import annotations

import logging
import os
import re
import threading
from dataclasses import dataclass, field
from datetime import datetime, timezone
from typing import Optional

from mini_kio.backend.repositories import MemoryRepository, FactRepository

logger = logging.getLogger(__name__)

# Global in-memory store for backward compatibility with tests that bypass SQLite
_GLOBAL_MEMORY_STORE: dict[str, dict] = {}
_GLOBAL_LOCK = threading.Lock()


@dataclass
class MemoryEntry:
    role: str
    message: str
    timestamp: datetime = field(default_factory=lambda: datetime.now(timezone.utc))


class PatternMemoryExtractor:
    """Deterministic extraction of facts from user input."""
    
    # Patterns for deterministic fact extraction
    # key_template, value_template
    _PATTERNS = [
        (re.compile(r"^\s*i\s+(like|love)\s+(.+?)\s*$", re.I), ("preference_{1}", "like")),
        (re.compile(r"^\s*i\s+(dislike|hate)\s+(.+?)\s*$", re.I), ("preference_{1}", "dislike")),
        (re.compile(r"^\s*my\s+favorite\s+(.+?)\s+is\s+(.+?)\s*$", re.I), ("favorite_{0}", "{1}")),
        (re.compile(r"^\s*remember\s+(?:that\s+)?my\s+favorite\s+(.+?)\s+is\s+(.+?)\s*$", re.I), ("favorite_{0}", "{1}")),
        (re.compile(r"^\s*remember\s+(?:that\s+)?(.+?)\s+is\s+(.+?)\s*$", re.I), ("{0}", "{1}")),
        (re.compile(r"^\s*call\s+me\s+(.+?)\s*$", re.I), ("user_name", "{0}")),
        (re.compile(r"^\s*my\s+name\s+is\s+(.+?)\s*$", re.I), ("user_name", "{0}")),
        (re.compile(r"^\s*remember\s+this\s*:\s*(.+?)\s*$", re.I), ("note", "{0}")),
    ]

    # Third-party markers to exclude (Ownership validation)
    _THIRD_PARTY_MARKERS = [
        "friend", "mom", "dad", "brother", "sister", "wife", "husband", 
        "boss", "colleague", "they", "he", "she", "someone", "people"
    ]

    def extract(self, text: str) -> dict[str, str]:
        text_clean = text.strip().strip(".,!?;:")
        low = text_clean.lower()
        
        # Ownership: Reject if mentions third parties
        if any(marker in low for marker in self._THIRD_PARTY_MARKERS):
            return {}

        results = {}
        for pattern, (k_temp, v_temp) in self._PATTERNS:
            match = pattern.match(text_clean)
            if match:
                groups = match.groups()
                
                # Format key
                key = k_temp
                for i, val in enumerate(groups):
                    token = "{" + str(i) + "}"
                    if token in key:
                        key = key.replace(token, val.lower().strip().replace(" ", "_"))
                
                # Format value
                value = v_temp
                for i, val in enumerate(groups):
                    token = "{" + str(i) + "}"
                    if token in value:
                        value = value.replace(token, val.strip())
                
                results[key] = value
        return results


class MemoryStore:
    def __init__(self, session_id: str = "default", memory_repo=None, fact_repo=None):
        self._session_id = session_id
        self._lock = _GLOBAL_LOCK
        self._extractor = PatternMemoryExtractor()
        self._memory_repo = memory_repo or MemoryRepository()
        self._fact_repo = fact_repo or FactRepository()
        # Global shared store for backward compatibility
        with _GLOBAL_LOCK:
            if session_id not in _GLOBAL_MEMORY_STORE:
                _GLOBAL_MEMORY_STORE[session_id] = {"messages": [], "facts": {}}
            self._global = _GLOBAL_MEMORY_STORE[session_id]

    def append(self, role: str, message: str):
        self._memory_repo.append(self._session_id, role, message)
        with self._lock:
            self._global["messages"].append(MemoryEntry(role=role, message=message))
        if role == "user":
            extracted = self._extractor.extract(message)
            for k, v in extracted.items():
                self.set_fact(k, v)

    def get_history(self) -> list[MemoryEntry]:
        rows = self._memory_repo.get_history(self._session_id)
        return [MemoryEntry(role=r["role"], message=r["content"], timestamp=r["timestamp"]) for r in rows]

    def count(self) -> int:
        return self._memory_repo.count(self._session_id)

    def first_user_message(self) -> Optional[str]:
        return self._memory_repo.first_user_message(self._session_id)

    def last_n_messages(self, n: int) -> list[MemoryEntry]:
        rows = self._memory_repo.last_n_messages(self._session_id, n)
        return [MemoryEntry(role=r["role"], message=r["content"], timestamp=r["timestamp"]) for r in rows]

    def summarize_session(self) -> str:
        history = self.get_history()
        if not history:
            return "Session is empty."
        total = len(history)
        user_count = sum(1 for e in history if e.role == "user")
        words = sum(len(e.message.split()) for e in history if e.message)
        return f"Session: {total} messages ({user_count} user), ~{words} words."

    def set_fact(self, key: str, value: str):
        self._fact_repo.set_fact(self._session_id, key, value)
        with self._lock:
            self._global["facts"][key] = value

    def get_fact(self, key: str) -> Optional[str]:
        return self._fact_repo.get_fact(self._session_id, key)

    def get_all_facts(self) -> dict[str, str]:
        return self._fact_repo.get_all_facts(self._session_id)

    def clear(self):
        self._memory_repo.clear(self._session_id)
        self._fact_repo.clear_facts(self._session_id)
        with self._lock:
            self._global["messages"].clear()
            self._global["facts"].clear()

    def close(self):
        try:
            from mini_kio.backend.db import close_db
            close_db()
        except Exception:
            pass
