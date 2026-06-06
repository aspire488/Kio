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
        result = await asyncio.to_thread(route, command, user_id)

        if isinstance(result, dict):
            msg = result.get("message", "")
        elif isinstance(result, str):
            msg = result
        else:
            msg = str(result)

        if not msg:
            msg = "Done."

        if len(msg) > 4000:
            msg = msg[:4000] + "…"

        await update.message.reply_text(msg)

    except BaseException as exc:
        logger.exception(f"[TELEGRAM] handler error: {exc}")
        await update.message.reply_text(
            "KIO encountered an error but is still running."
        )


async def handle_error(update: object, context: ContextTypes.DEFAULT_TYPE) -> None:
    """Log PTB errors without crashing the bot."""
    logger.error(f"[TELEGRAM] PTB error: {context.error}")


# ---------------------------------------------------------------------------
# PTB Lifecycle Instrumentation
# ---------------------------------------------------------------------------

async def _lifecycle_post_init(app: Application) -> None:
    """Called by PTB after initialize() — lifecycle trace point."""
    logger.info("[LIFECYCLE] post_init app.running=%s", app.running)


async def _lifecycle_post_stop(app: Application) -> None:
    """Called by PTB after stop() — lifecycle trace point."""
    logger.info("[LIFECYCLE] post_stop app.running=%s", app.running)


async def _lifecycle_post_shutdown(app: Application) -> None:
    """Called by PTB after shutdown() — lifecycle trace point."""
    logger.info("[LIFECYCLE] post_shutdown app.running=%s", app.running)


# ---------------------------------------------------------------------------
# Entry point
# ---------------------------------------------------------------------------

_restart_counter = 0


def _build_app() -> Application:
    """Build a fresh PTB Application instance with all handlers."""
    app = (
        Application.builder()
        .token(TELEGRAM_TOKEN)
        .connect_timeout(30)
        .read_timeout(30)
        .write_timeout(30)
        .pool_timeout(30)
        .post_init(_lifecycle_post_init)
        .post_stop(_lifecycle_post_stop)
        .post_shutdown(_lifecycle_post_shutdown)
        .build()
    )
    app.add_handler(CommandHandler("start", cmd_start))
    app.add_handler(CommandHandler("help", cmd_help))
    app.add_handler(MessageHandler(filters.COMMAND, handle_unknown_command))
    app.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, handle_message))
    app.add_error_handler(handle_error)
    return app


def run_bot(runtime=None) -> None:
    """Build and run the Telegram bot indefinitely.

    The bot auto-restarts if python-telegram-bot's run_polling exits
    unexpectedly (e.g. due to KeyboardInterrupt internally caught by PTB).

    Only a true OS signal (Ctrl+C / SIGTERM) stops the loop.
    """
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

    global _restart_counter

    # ── FIX: run_polling auto-restart loop ──────────────────────────
    # PTB's run_polling can exit when KeyboardInterrupt/SystemExit is
    # raised inside the event loop (caught by PTB's internal except).
    # On return the Application is shut down and must be rebuilt.
    # We loop forever so KIO survives these transient shutdowns.
    while True:
        app = _build_app()
        print("Bot running…")

        try:
            app.run_polling(
                allowed_updates=Update.ALL_TYPES,
                drop_pending_updates=True,
            )
        except KeyboardInterrupt:
            # Real Ctrl+C from terminal — stop the loop, let process exit
            logger.warning("[KIO] KeyboardInterrupt — shutting down")
            print("\nShutdown requested.")
            break
        except SystemExit:
            # SystemExit — treat as unexpected, restart
            logger.warning("[KIO] run_polling exited with SystemExit — restarting", exc_info=True)
        except BaseException:
            logger.exception("[KIO] run_polling exited with unexpected exception — restarting")
        else:
            # run_polling returned normally (caught KeyboardInterrupt inside PTB)
            logger.warning(
                "[KIO] run_polling returned without exception (restart #%d)",
                _restart_counter,
            )

        _restart_counter += 1

        # Brief pause before restart to avoid tight loop on repeated failures
        import time as _time
        _time.sleep(2)

    # Graceful shutdown of connector
    try:
        from mini_kio.core.runtime import get_runtime
        rt = get_runtime()
        if rt:
            # Give connector a moment to close gracefully
            import time as _time
            _time.sleep(0.5)
    except Exception:
        pass


if __name__ == "__main__":
    run_bot()
