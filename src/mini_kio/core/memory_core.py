"""
Mini-KIO persistence: SQLite for ideas, tasks, key-value pairs, and short chat history.

Each public function opens one connection, runs work, and closes—keeps idle RAM low.
"""

from __future__ import annotations

import sqlite3
import time
from typing import Any

from .config import DB_PATH

MAX_IDEA_LEN = 4000
MAX_TASK_LEN = 500
MAX_KV_KEY_LEN = 200
MAX_KV_VALUE_LEN = 4000
MAX_CHAT_MESSAGE_LEN = 8000
MAX_STORED_IDEAS = 100
LIST_IDEAS_DEFAULT_LIMIT = 100

# Internal KV keys for focus/break timers (not user-facing)
_KIO_TIMER_KIND = "_kio:timer_kind"
_KIO_TIMER_DEADLINE = "_kio:timer_deadline"


def _connect() -> sqlite3.Connection:
    conn = sqlite3.connect(DB_PATH)
    conn.row_factory = sqlite3.Row
    return conn


def init_db() -> None:
    """Create application tables if they are missing (idempotent)."""
    with _connect() as conn:
        conn.executescript("""
            CREATE TABLE IF NOT EXISTS ideas (
                id      INTEGER PRIMARY KEY AUTOINCREMENT,
                content TEXT    NOT NULL,
                tags    TEXT    DEFAULT '',
                ts      INTEGER DEFAULT (strftime('%s','now'))
            );

            CREATE TABLE IF NOT EXISTS tasks (
                id      INTEGER PRIMARY KEY AUTOINCREMENT,
                title   TEXT    NOT NULL,
                done    INTEGER DEFAULT 0,
                ts      INTEGER DEFAULT (strftime('%s','now'))
            );

            CREATE TABLE IF NOT EXISTS kv (
                key     TEXT PRIMARY KEY,
                value   TEXT NOT NULL,
                ts      INTEGER DEFAULT (strftime('%s','now'))
            );

            CREATE TABLE IF NOT EXISTS chat_history (
                id      INTEGER PRIMARY KEY AUTOINCREMENT,
                role    TEXT    NOT NULL,
                content TEXT    NOT NULL,
                ts      INTEGER DEFAULT (strftime('%s','now'))
            );
        """)


def count_ideas() -> int:
    """Return total number of rows in ``ideas`` (parameterized query)."""
    with _connect() as conn:
        row = conn.execute("SELECT COUNT(*) AS c FROM ideas").fetchone()
        return int(row["c"]) if row else 0


def save_idea(content: str, tags: str = "") -> int:
    """Insert an idea; returns new row id. Trims content and enforces ``MAX_STORED_IDEAS``."""
    content = content[:MAX_IDEA_LEN]
    tags = tags[:200]
    with _connect() as conn:
        cur = conn.execute(
            "INSERT INTO ideas (content, tags) VALUES (?, ?)", (content, tags)
        )
        new_id = int(cur.lastrowid)
        row = conn.execute("SELECT COUNT(*) AS c FROM ideas").fetchone()
        n = int(row["c"]) if row else 0
        if n > MAX_STORED_IDEAS:
            to_drop = n - MAX_STORED_IDEAS
            conn.execute(
                """
                DELETE FROM ideas WHERE id IN (
                    SELECT id FROM ideas ORDER BY ts ASC, id ASC LIMIT ?
                )
                """,
                (to_drop,),
            )
        return new_id


def list_ideas(limit: int | None = None) -> list[dict[str, Any]]:
    """Return up to ``limit`` ideas, newest first (default: ``LIST_IDEAS_DEFAULT_LIMIT``)."""
    lim = LIST_IDEAS_DEFAULT_LIMIT if limit is None else min(int(limit), LIST_IDEAS_DEFAULT_LIMIT)
    with _connect() as conn:
        rows = conn.execute(
            "SELECT id, content, tags, ts FROM ideas ORDER BY ts DESC, id DESC LIMIT ?",
            (lim,),
        ).fetchall()
        return [dict(r) for r in rows]


def delete_idea(idea_id: int) -> bool:
    with _connect() as conn:
        cur = conn.execute("DELETE FROM ideas WHERE id = ?", (idea_id,))
        return cur.rowcount > 0


def add_task(title: str) -> int:
    title = title[:MAX_TASK_LEN]
    with _connect() as conn:
        cur = conn.execute("INSERT INTO tasks (title) VALUES (?)", (title,))
        return int(cur.lastrowid)


def list_tasks(show_done: bool = False) -> list[dict[str, Any]]:
    with _connect() as conn:
        query = "SELECT id, title, done, ts FROM tasks"
        if not show_done:
            query += " WHERE done = 0"
        query += " ORDER BY ts DESC LIMIT 20"
        rows = conn.execute(query).fetchall()
        return [dict(r) for r in rows]


def complete_task(task_id: int) -> bool:
    with _connect() as conn:
        cur = conn.execute("UPDATE tasks SET done = 1 WHERE id = ?", (task_id,))
        return cur.rowcount > 0


def delete_task(task_id: int) -> bool:
    with _connect() as conn:
        cur = conn.execute("DELETE FROM tasks WHERE id = ?", (task_id,))
        return cur.rowcount > 0


def kv_set(key: str, value: str) -> None:
    key = key[:MAX_KV_KEY_LEN]
    value = value[:MAX_KV_VALUE_LEN]
    with _connect() as conn:
        conn.execute(
            "INSERT OR REPLACE INTO kv (key, value) VALUES (?, ?)", (key, value)
        )


def kv_get(key: str) -> str | None:
    key = key[:MAX_KV_KEY_LEN]
    with _connect() as conn:
        row = conn.execute("SELECT value FROM kv WHERE key = ?", (key,)).fetchone()
        return str(row["value"]) if row else None


def kv_delete(key: str) -> bool:
    with _connect() as conn:
        cur = conn.execute("DELETE FROM kv WHERE key = ?", (key,))
        return cur.rowcount > 0


def kv_list() -> list[dict[str, Any]]:
    with _connect() as conn:
        rows = conn.execute("SELECT key, value, ts FROM kv ORDER BY key").fetchall()
        return [dict(r) for r in rows]


def set_session_timer(kind: str, minutes: int) -> float:
    """
    Store a focus/break timer deadline (wall clock). ``kind`` is ``focus`` or ``break``.

    Returns deadline unix timestamp.
    """
    kind = kind.strip()[:32]
    if minutes < 1:
        minutes = 1
    if minutes > 24 * 60:
        minutes = 24 * 60
    deadline = time.time() + minutes * 60.0
    kv_set(_KIO_TIMER_KIND, kind)
    kv_set(_KIO_TIMER_DEADLINE, f"{deadline:.3f}")
    return deadline


def clear_session_timer() -> None:
    """Remove active focus/break timer."""
    kv_delete(_KIO_TIMER_KIND)
    kv_delete(_KIO_TIMER_DEADLINE)


def pop_due_session_timer() -> str | None:
    """
    If stored deadline has passed, clear timer keys and return kind (``focus``/``break``).

    Otherwise return ``None``. Safe to call frequently.
    """
    kind = kv_get(_KIO_TIMER_KIND)
    end_s = kv_get(_KIO_TIMER_DEADLINE)
    if not kind or not end_s:
        return None
    try:
        end = float(end_s)
    except ValueError:
        clear_session_timer()
        return None
    if time.time() >= end:
        clear_session_timer()
        return kind
    return None


def save_message(role: str, content: str) -> None:
    """Append a chat turn and trim history to the last 50 rows."""
    if role not in ("user", "assistant"):
        role = "user"
    content = content[:MAX_CHAT_MESSAGE_LEN]
    with _connect() as conn:
        conn.execute(
            "INSERT INTO chat_history (role, content) VALUES (?, ?)", (role, content)
        )
        conn.execute("""
            DELETE FROM chat_history WHERE id NOT IN (
                SELECT id FROM chat_history ORDER BY ts DESC LIMIT 50
            )
        """)


def get_history(limit: int = 10) -> list[dict[str, Any]]:
    """Last ``limit`` messages in chronological order for model context."""
    with _connect() as conn:
        rows = conn.execute(
            "SELECT role, content FROM chat_history ORDER BY ts DESC LIMIT ?",
            (limit,),
        ).fetchall()
        return [dict(r) for r in reversed(rows)]
