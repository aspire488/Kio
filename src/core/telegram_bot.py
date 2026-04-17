"""
Mini-KIO Telegram client: whitelist, per-user rate limits, and ``router.route`` dispatch.

Plain-text replies; all free-text from the phone goes through ``router.route`` for remote control.
"""

from __future__ import annotations

import asyncio
import json
import logging
import re
import time
from collections import deque
from pathlib import Path
from typing import Any

from telegram import Update
from telegram.ext import (
    Application,
    CommandHandler,
    ContextTypes,
    MessageHandler,
    filters,
)

from .config import ALLOWED_USER_IDS, TELEGRAM_TOKEN

logger = logging.getLogger(__name__)

RATE_MAX = 5
RATE_WINDOW_SEC = 10.0
_user_command_times: dict[int, deque[float]] = {}

# Monotonic time when ``run_bot()`` entered (for /status uptime)
_BOT_START_MONO: float | None = None


def _log(evt: str, **fields: Any) -> None:
    payload: dict[str, Any] = {"evt": evt}
    payload.update(fields)
    logger.info(json.dumps(payload, default=str))


def format_status_message() -> str:
    """
    Build /status body: AI provider, idea count, DB path existence, bot uptime.

    Does not log or embed API keys.
    """
    from .config import CLAUDE_API_KEY, DB_PATH, GEMINI_API_KEY, GROQ_API_KEY
    from .memory_core import count_ideas

    if GROQ_API_KEY:
        provider = "Groq"
    elif CLAUDE_API_KEY:
        provider = "Claude"
    elif GEMINI_API_KEY:
        provider = "Gemini"
    else:
        provider = "none configured"

    n_ideas = count_ideas()
    db_path = Path(DB_PATH)
    db_status = "ok" if db_path.exists() else "missing on disk"

    if _BOT_START_MONO is not None:
        elapsed = time.monotonic() - _BOT_START_MONO
        h, rem = divmod(int(elapsed), 3600)
        m, s = divmod(rem, 60)
        uptime_str = f"{h}h {m}m {s}s"
    else:
        uptime_str = "n/a"

    lines = [
        "Mini-KIO status",
        "",
        f"AI provider: {provider}",
        f"Saved ideas count: {n_ideas}",
        f"Database: {db_status}",
        f"Database path: {DB_PATH}",
        f"Bot uptime: {uptime_str}",
    ]
    return "\n".join(lines)


def _rate_allow(user_id: int) -> bool:
    """Allow at most ``RATE_MAX`` calls per ``RATE_WINDOW_SEC`` per Telegram user id."""
    now = time.monotonic()
    dq = _user_command_times.setdefault(user_id, deque())
    while dq and now - dq[0] > RATE_WINDOW_SEC:
        dq.popleft()
    if len(dq) >= RATE_MAX:
        return False
    dq.append(now)
    return True


def _is_allowed(update: Update) -> bool:
    user_id = update.effective_user.id if update.effective_user else None
    if user_id is None or user_id not in ALLOWED_USER_IDS:
        _log("telegram_deny", user_id=user_id, reason="not_whitelisted")
        return False
    return True


_TOKEN_LIKE = re.compile(
    r"\b(?:gsk_[A-Za-z0-9_-]{10,}|"
    r"sk-ant-[A-Za-z0-9_-]{10,}|"
    r"AIza[0-9A-Za-z_-]{10,}|"
    r"\d{8,10}:[A-Za-z0-9_-]{30,})\b"
)


def _safe_message_log_summary(text: str | None, max_len: int = 72) -> dict[str, object]:
    """Return log fields for a user message: length and redacted or truncated preview."""
    if not text:
        return {"text_len": 0, "preview": ""}
    t = text.replace("\r", "").replace("\n", " ")
    if _TOKEN_LIKE.search(t):
        return {"text_len": len(text), "preview_redacted": True}
    if len(t) > max_len:
        t = t[:max_len] + "…"
    return {"text_len": len(text), "preview": t}


async def _send(update: Update, text: str) -> None:
    """Chunk and send plain text (Telegram limit 4096; we use 4000)."""
    if not text:
        return
    max_len = 4000
    for i in range(0, len(text), max_len):
        await update.message.reply_text(text[i : i + max_len])


async def _route_and_send(update: Update, uid: int, payload: str) -> None:
    from .command_router import route

    response = await asyncio.to_thread(route, payload, uid)
    await _send(update, response)


async def cmd_start(
    update: Update,
    _context: ContextTypes.DEFAULT_TYPE,
) -> None:
    if not _is_allowed(update):
        await update.message.reply_text("Unauthorized.")
        return
    if not _rate_allow(update.effective_user.id):
        await update.message.reply_text("Too many requests. Wait a few seconds.")
        return
    user = update.effective_user.first_name or "User"
    await _send(
        update,
        f"Hey {user}! Mini-KIO is online.\n\n"
        "Remote control: send commands like open youtube, screenshot, idea …, "
        "or use /ideas, /status, /help.",
    )


async def cmd_help(
    update: Update,
    _context: ContextTypes.DEFAULT_TYPE,
) -> None:
    if not _is_allowed(update):
        return
    uid = update.effective_user.id
    if not _rate_allow(uid):
        await update.message.reply_text("Too many requests. Wait a few seconds.")
        return
    _log("telegram_cmd", cmd="help", user_id=uid)
    await _route_and_send(update, uid, "help")


async def cmd_ideas(
    update: Update,
    _context: ContextTypes.DEFAULT_TYPE,
) -> None:
    if not _is_allowed(update):
        return
    uid = update.effective_user.id
    if not _rate_allow(uid):
        await update.message.reply_text("Too many requests. Wait a few seconds.")
        return
    _log("telegram_cmd", cmd="ideas", user_id=uid)
    await _route_and_send(update, uid, "what ideas do i have")


async def cmd_status(
    update: Update,
    _context: ContextTypes.DEFAULT_TYPE,
) -> None:
    if not _is_allowed(update):
        return
    uid = update.effective_user.id
    if not _rate_allow(uid):
        await update.message.reply_text("Too many requests. Wait a few seconds.")
        return
    _log("telegram_cmd", cmd="status", user_id=uid)

    body = format_status_message()
    from .system_skills import get_system_info

    r = get_system_info()
    if r.get("success"):
        d = r.get("data") or {}
        body += (
            "\n\nHost\n"
            f"OS: {d.get('os', 'N/A')} {d.get('version', '')}\n"
            f"Python: {d.get('python', 'N/A')}\n"
            f"RAM Total: {d.get('ram_total_mb', 'N/A')} MB\n"
            f"RAM Used: {d.get('ram_used_mb', 'N/A')} MB\n"
            f"RAM Free: {d.get('ram_available_mb', 'N/A')} MB"
        )
    else:
        body += f"\n\nHost: {r.get('message', 'unavailable')}"

    await _send(update, body)


async def handle_message(
    update: Update,
    _context: ContextTypes.DEFAULT_TYPE,
) -> None:
    if not _is_allowed(update):
        await update.message.reply_text("Unauthorized.")
        return

    uid = update.effective_user.id
    if not _rate_allow(uid):
        await update.message.reply_text(
            "Too many requests (max 5 per 10 seconds). Slow down."
        )
        return

    text = update.message.text
    if not text:
        return

    print(f"[TELEGRAM RECEIVED] {text}")
    _log("telegram_message", user_id=uid, **_safe_message_log_summary(text))

    await update.message.chat.send_action("typing")

    try:
        from .command_router import route

        response = await asyncio.to_thread(route, text, uid)
    except Exception:
        logger.exception(json.dumps({"evt": "telegram_router_error", "user_id": uid}))
        response = "Something went wrong. Please try again."

    await _send(update, response)


async def handle_error(_update: object, context: ContextTypes.DEFAULT_TYPE) -> None:
    err = context.error
    logger.error(
        json.dumps(
            {
                "evt": "telegram_handler_error",
                "error_type": type(err).__name__,
                "error": str(err)[:500],
            },
            default=str,
        ),
    )


def run_bot() -> None:
    """Build handlers and block on long-polling until interrupted."""
    global _BOT_START_MONO

    if not TELEGRAM_TOKEN:
        raise ValueError("TELEGRAM_TOKEN not set in environment")

    _BOT_START_MONO = time.monotonic()

    app = Application.builder().token(TELEGRAM_TOKEN).build()

    app.add_handler(CommandHandler("start", cmd_start))
    app.add_handler(CommandHandler("help", cmd_help))
    app.add_handler(CommandHandler("ideas", cmd_ideas))
    app.add_handler(CommandHandler("status", cmd_status))
    app.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, handle_message))
    app.add_error_handler(handle_error)

    _log("telegram_bot_start", polling=True)
    print("Mini-KIO is running. Press Ctrl+C to stop.")

    app.run_polling(
        allowed_updates=Update.ALL_TYPES,
        drop_pending_updates=True,
    )
