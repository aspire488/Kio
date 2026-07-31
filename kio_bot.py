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
from mini_kio.core.config import TELEGRAM_TOKEN, TELEGRAM_PROXY, ALLOWED_USER_IDS
from mini_kio.core.runtime import bootstrap_runtime

logger = logging.getLogger(__name__)


# ---------------------------------------------------------------------------
# Handlers
# ---------------------------------------------------------------------------

async def cmd_start(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """Handle /start command."""
    user = update.effective_user
    name = user.first_name if user else "User"
    reply = (
        f"Hey {name}! KIO is online.\n\n"
        "Send commands like:\n"
        "  open chrome\n"
        "  search python tutorial\n"
        "  play messi highlights\n"
        "  open chrome and search AI news\n"
        "Use /help for the full command list."
    )
    logger.info(f"[TELEGRAM_REPLY] /start reply={reply!r}")
    await update.message.reply_text(reply)


async def cmd_help(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """Handle /help command."""
    from mini_kio.core.routes.system_routes import _show_help
    result = _show_help()
    reply = result.get("message", "KIO help unavailable.")
    logger.info(f"[TELEGRAM_REPLY] /help reply={reply!r}")
    await update.message.reply_text(reply)


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
    Handle user text messages — Telegram adapter.
    Converts input to canonical InterfaceRequest, passes to runtime,
    renders InterfaceResponse back to Telegram.
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
        reply = await asyncio.to_thread(route, command, user_id)
        logger.info(f"[TELEGRAM_REPLY] uid={user_id} reply={reply!r}")
        await update.message.reply_text(reply)
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
    builder = (
        Application.builder()
        .token(TELEGRAM_TOKEN)
        .connect_timeout(30)
        .read_timeout(30)
        .write_timeout(30)
        .pool_timeout(30)
    )
    if TELEGRAM_PROXY:
        logger.info("[TELEGRAM_PROXY] configured: %s", TELEGRAM_PROXY)
        builder = builder.proxy(TELEGRAM_PROXY)
    else:
        logger.info("[TELEGRAM_PROXY] not configured")

    app = (
        builder
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

    # Pre-flight connectivity check
    import socket as _socket
    _tg_test_host = "api.telegram.org"
    try:
        _tg_addrs = _socket.getaddrinfo(_tg_test_host, 443)
        _tg_resolved = ", ".join(str(a[4][0]) for a in _tg_addrs[:3])
        logger.info("[TELEGRAM_PREFLIGHT] %s resolves to: %s", _tg_test_host, _tg_resolved)
    except Exception as _e:
        logger.warning("[TELEGRAM_PREFLIGHT] DNS resolution failed: %s", _e)

    if TELEGRAM_PROXY:
        print(f"Telegram proxy: {TELEGRAM_PROXY}")
    else:
        print("Telegram proxy: none (direct)")

    if runtime is None:
        runtime = bootstrap_runtime()
        print("Runtime initialized")

    global _restart_counter

    # ── run_polling auto-restart loop ───────────────────────────────
    # PTB's run_polling closes its internal event loop on exit.  On
    # restart we must replace the closed loop on the main thread so
    # that the fresh Application does not inherit a dead loop.
    # ─────────────────────────────────────────────────────────────────
    while True:
        # Reset main-thread event loop: if the previous run_polling()
        # closed its loop, replace it with a fresh one so no code path
        # ever picks up a closed loop via asyncio.get_event_loop().
        try:
            _old = asyncio.get_event_loop()
            if _old.is_closed():
                asyncio.set_event_loop(asyncio.new_event_loop())
                logger.info("[LIFECYCLE] event_loop_replaced")
        except RuntimeError:
            asyncio.set_event_loop(asyncio.new_event_loop())
            logger.info("[LIFECYCLE] event_loop_created")

        app = _build_app()
        logger.info("[LIFECYCLE] application_created restart_count=%d", _restart_counter)

        try:
            app.run_polling(
                allowed_updates=Update.ALL_TYPES,
                drop_pending_updates=True,
            )
            logger.info("[LIFECYCLE] polling_stopped reason=normal_exit")
        except KeyboardInterrupt:
            logger.warning("[LIFECYCLE] shutdown_started reason=KeyboardInterrupt")
            print("\nShutdown requested.")
            break
        except SystemExit:
            logger.warning("[LIFECYCLE] polling_stopped reason=SystemExit restart_count=%d", _restart_counter)
        except BaseException:
            logger.exception("[LIFECYCLE] polling_stopped reason=unexpected_exception restart_count=%d", _restart_counter)
        else:
            logger.warning("[LIFECYCLE] polling_stopped reason=clean_return restart_count=%d", _restart_counter)

        _restart_counter += 1
        logger.info("[LIFECYCLE] restart_executed count=%d", _restart_counter)

        import time as _time
        _time.sleep(2)

    logger.info("[LIFECYCLE] shutdown_completed")
    try:
        from mini_kio.core.runtime import get_runtime
        rt = get_runtime()
        if rt:
            import time as _time
            _time.sleep(0.5)
    except Exception:
        pass


if __name__ == "__main__":
    from mini_kio.core.runtime import run_runtime
    run_runtime()
