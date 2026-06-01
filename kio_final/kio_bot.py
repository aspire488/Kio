"""
kio_bot.py — KIO Telegram Bot
===============================
Gate 5.7: Direct Provider Migration + FreeLLM Decommission
- dotenv loaded ONCE at bootstrap
- FreeLLM is optional experimental backend (ENABLE_FREELLM=true)
- Direct provider orchestration: Gemini → Groq → OpenRouter → Together → Cerebras
- KIO boots without freellm server or npm dependency
"""

from __future__ import annotations

import asyncio
import logging

from dotenv import load_dotenv
load_dotenv()

from telegram import Update
from telegram.ext import (
    Application,
    CommandHandler,
    ContextTypes,
    MessageHandler,
    filters,
)

from mini_kio.core.command_router import route
from mini_kio.core.config import TELEGRAM_TOKEN, ALLOWED_USER_IDS
from mini_kio.core.runtime import bootstrap_runtime

logger = logging.getLogger(__name__)


# ---------------------------------------------------------------------------
# Handlers
# ---------------------------------------------------------------------------

async def cmd_start(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """Handle /start command."""
    user = update.effective_user
    name = user.first_name if user else "User"
    await update.message.reply_text(
        f"Hey {name}! KIO is online.\n\n"
        "Send commands like:\n"
        "  open chrome\n"
        "  search python tutorial\n"
        "  play messi highlights\n"
        "  open chrome and search AI news\n"
        "Use /help for the full command list."
    )


async def cmd_help(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """Handle /help command."""
    from mini_kio.core.command_router import _show_help
    result = _show_help()
    await update.message.reply_text(result.get("message", "KIO help unavailable."))


async def handle_unknown_command(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """Handle unrecognized /commands — prevents silent drop."""
    if not update.effective_user or not update.message:
        return
    user_id = update.effective_user.id
    if user_id not in ALLOWED_USER_IDS:
        await update.message.reply_text("Unauthorized.")
        return
    command = update.message.text or ""
    await update.message.reply_text(
        f"Unknown command: {command}\nUse /help to see available commands."
    )


async def handle_message(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """
    Handle user text messages.

    BUG-08 FIX: result type is guarded before calling .get().
    route() returns str, but the guard protects against any future refactor.
    """
    if not update.effective_user or not update.message:
        return

    user_id = update.effective_user.id
    if user_id not in ALLOWED_USER_IDS:
        await update.message.reply_text("Unauthorized.")
        return

    command = update.message.text or ""
    if not command.strip():
        return

    logger.info(f"[TELEGRAM] uid={user_id} cmd={command!r}")
    await update.message.chat.send_action("typing")

    try:
        # route() runs synchronous blocking code — use to_thread to avoid
        # blocking the asyncio event loop
        result = await asyncio.to_thread(route, command, user_id)

        # BUG-08 FIX: safe multi-type handling
        if isinstance(result, dict):
            msg = result.get("message", "")
        elif isinstance(result, str):
            msg = result
        else:
            msg = str(result)

        if not msg:
            msg = "Done."

        # Telegram max message length is 4096 chars
        if len(msg) > 4000:
            msg = msg[:4000] + "…"

        await update.message.reply_text(msg)

    except Exception as exc:
        logger.exception(f"[TELEGRAM] handler error: {exc}")
        await update.message.reply_text(
            "KIO encountered an error but is still running."
        )


async def handle_error(update: object, context: ContextTypes.DEFAULT_TYPE) -> None:
    """Log PTB errors without crashing the bot."""
    logger.error(f"[TELEGRAM] PTB error: {context.error}")


# ---------------------------------------------------------------------------
# Entry point
# ---------------------------------------------------------------------------

def run_bot(runtime=None) -> None:
    """Build and run the Telegram bot (blocks until Ctrl-C)."""
    if not TELEGRAM_TOKEN:
        logger.error("TELEGRAM_TOKEN not set — bot cannot start")
        print("ERROR: TELEGRAM_TOKEN not configured in .env")
        return

    print("=" * 50)
    print("KIO TELEGRAM BOT")
    print("=" * 50)

    if runtime is None:
        runtime = bootstrap_runtime()
        print("Runtime initialized")

    # Apply bounded timeouts for network resilience (30s max)
    app = (
        Application.builder()
        .token(TELEGRAM_TOKEN)
        .connect_timeout(30)
        .read_timeout(30)
        .write_timeout(30)
        .pool_timeout(30)
        .build()
    )

    app.add_handler(CommandHandler("start", cmd_start))
    app.add_handler(CommandHandler("help",  cmd_help))
    # Catch-all for unrecognized /commands — prevents silent drop
    app.add_handler(MessageHandler(filters.COMMAND, handle_unknown_command))
    app.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, handle_message))
    app.add_error_handler(handle_error)

    print("Bot running… Press Ctrl-C to stop.")
    # BUG-09 FIX: PTB's run_polling handles its own loops, but we catch
    # initial startup networking failures (like TimedOut) to exit cleanly.
    try:
        app.run_polling(
            allowed_updates=Update.ALL_TYPES,
            drop_pending_updates=True,
        )
    except Exception as exc:
        logger.error(f"Telegram bot failed to start: {exc}")
        print(f"\nERROR: Telegram network failure: {exc}")


if __name__ == "__main__":
    run_bot()
