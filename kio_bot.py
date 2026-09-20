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
import time

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

# Per-session message ordering: prevent stale responses from leaking.
import threading
_session_locks = {}
_session_counter = {}
_session_completed = {}

# Concurrency isolation: long-running operations (media, document creation)
# run on a dedicated thread pool so short operations (chat, status) are never
# blocked by a slow media verification or LLM content generation.
import concurrent.futures
_LONG_OP_POOL = concurrent.futures.ThreadPoolExecutor(
    max_workers=3,
    thread_name_prefix="kio-long",
)
# Fast-path pool: greetings, acknowledgements, simple commands that must
# NEVER be blocked by a slow media/LLM operation in the long pool.
_FAST_POOL = concurrent.futures.ThreadPoolExecutor(
    max_workers=4,
    thread_name_prefix="kio-fast",
)

# Deterministic fast-path patterns: messages matching these are guaranteed
# to complete without LLM/media/browser and must never wait behind slow work.
_FAST_PATH_PATTERNS = frozenset({
    "hi", "hey", "hello", "yo", "sup", "hii", "heyy",
    "thanks", "thank you", "ty", "thx", "thankyou",
    "ok", "okay", "k", "cool", "nice", "got it", "alright",
    "pause", "pause it", "pause that", "pause the music", "pause the video",
    "resume", "resume it", "resume that", "unpause",
    "stop", "stop it", "stop playing", "stop that",
    "what is playing", "what's playing", "now playing", "what is playing?", "what's playing?",
    "what's playing now", "what is playing now",
})
# Prefixes that indicate a fast-path command (e.g., "pause it" -> "pause" prefix)
_FAST_PATH_PREFIXES = (
    "hi ", "hey ", "hello ",
    "pause ", "resume ", "stop ",
    "what is playing ", "what's playing ",
)


def _is_fast_path(text: str) -> bool:
    """Deterministic fast-path check: messages that complete without LLM/media.
    Must be O(1) and never block."""
    t = text.strip().lower()
    if not t:
        return False
    # Exact match
    if t in _FAST_PATH_PATTERNS:
        return True
    # Prefix match (strip punctuation)
    t_clean = t.rstrip(".!?;:,")
    if t_clean in _FAST_PATH_PATTERNS:
        return True
    for pfx in _FAST_PATH_PREFIXES:
        if t_clean.startswith(pfx):
            return True
    return False


def _is_failure_response(reply: str) -> bool:
    """Classify whether a reply is a user-critical failure that must NEVER be
    discarded as stale.

    Invariant: when a newer request exists for the same session, an older
    reply is discarded UNLESS it is a failure the user needs to see. Failure
    markers are strong signals ("I couldn't", "failed", "error") that
    indicate the user should know about the problem even if newer commands
    arrived. Informational content ("Nothing is playing right now.") is NOT
    a failure — it is eligible for stale-discard.
    """
    if not reply:
        return False
    rl = reply.lower()
    return (
        reply.startswith("I couldn't")
        or reply.startswith("I don't")
        or "failed" in rl
        or "error" in rl
    )

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


async def cmd_operational(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """Thin interface wiring for operational slash commands.

    /health /status /uptime /system /systemhealth /resources — the capability
    itself is system-level (deterministic classifier +
    mini_kio.core.operational_health);
    this handler only routes the command text through the same canonical path
    every message uses, so all interfaces behave identically.
    """
    if not update.effective_user or not update.message:
        return
    user_id = update.effective_user.id
    if user_id not in ALLOWED_USER_IDS:
        await update.message.reply_text("Unauthorized.")
        return
    command = (update.message.text or "/status").split()[0].split("@")[0]
    logger.info(f"[TELEGRAM] uid={user_id} cmd={command!r}")
    # Per-session sequence tracking (same as handle_message - ponytail: minimal fix for crash)
    if user_id not in _session_locks:
        _session_locks[user_id] = threading.Lock()
        _session_counter[user_id] = 0
        _session_completed[user_id] = 0
    _slock = _session_locks[user_id]
    _slock.acquire()
    try:
        _session_counter[user_id] += 1
        my_seq = _session_counter[user_id]
    finally:
        _slock.release()
    try:
        # Operational commands are deterministic and fast — use fast pool
        reply = await asyncio.get_event_loop().run_in_executor(
            _FAST_POOL, route, command, user_id,
        )
        # Discard stale: if a newer message arrived during route()
        # CRITICAL: failure responses are NEVER stale — the user needs to
        # know that an action failed, even if newer commands arrived.
        _slock.acquire()
        try:
            cur = _session_counter.get(user_id, 0)
            done = _session_completed.get(user_id, 0)
            if my_seq < cur and done < cur and not _is_failure_response(reply):
                logger.info(f"[TELEGRAM_STALE] uid={user_id} seq={my_seq}<{cur} discarded")
                return
            _session_completed[user_id] = max(done, my_seq)
        finally:
            _slock.release()
        logger.info(f"[TELEGRAM_REPLY] uid={user_id} seq={my_seq} reply={reply!r}")
        await update.message.reply_text(reply)
    except BaseException as exc:
        logger.exception(f"[TELEGRAM] operational handler error: {exc}")
        await update.message.reply_text(
            "KIO encountered an error but is still running."
        )


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

    # Per-session sequence tracking
    if user_id not in _session_locks:
        _session_locks[user_id] = threading.Lock()
        _session_counter[user_id] = 0
        _session_completed[user_id] = 0
    _slock = _session_locks[user_id]
    _slock.acquire()
    try:
        _session_counter[user_id] += 1
        my_seq = _session_counter[user_id]
    finally:
        _slock.release()

    # Lightweight round-trip diagnostic (no message secrets): proves
    # update received -> routed -> response generated -> response sent.
    from mini_kio.core.runtime import emit_runtime_trace
    _rt_start = time.monotonic()
    # Concurrency: fast-path messages (hi/hello/thanks/pause/resume/stop) go to
    # a DEDICATED fast pool so they NEVER wait behind slow media/LLM work.
    # Long ops go to the slow pool. Default pool is for everything else.
    _is_fast = _is_fast_path(command)
    _LONG_KEYWORDS = (
        "play", "next", "prev", "volume",
        "create", "make", "generate", "write", "open chrome", "open edge",
        "browse", "search", "news", "weather",
    )
    _use_long_pool = not _is_fast and any(kw in command.lower() for kw in _LONG_KEYWORDS)
    try:
        # Queue wait: measure time from handler entry to pool dispatch
        _t_queue_start = time.monotonic()
        if _is_fast:
            # Fast path: dedicated pool, never blocked by slow work
            reply = await asyncio.get_event_loop().run_in_executor(
                _FAST_POOL, route, command, user_id,
            )
        elif _use_long_pool:
            reply = await asyncio.get_event_loop().run_in_executor(
                _LONG_OP_POOL, route, command, user_id,
            )
        else:
            reply = await asyncio.to_thread(route, command, user_id)
        _rt_route_ms = int((time.monotonic() - _rt_start) * 1000)
        _queue_ms = int((time.monotonic() - _t_queue_start) * 1000) - _rt_route_ms
        # Negative queue means dispatch was instant (thread available immediately)
        _queue_ms = max(0, _queue_ms)
        # Discard stale: if a newer message arrived during route()
        # CRITICAL: failure responses are NEVER stale — the user needs to
        # know that an action failed, even if newer commands arrived.
        _slock.acquire()
        try:
            cur = _session_counter.get(user_id, 0)
            done = _session_completed.get(user_id, 0)
            if my_seq < cur and done < cur and not _is_failure_response(reply):
                logger.info(f"[TELEGRAM_STALE] uid={user_id} seq={my_seq}<{cur} discarded")
                return
            _session_completed[user_id] = max(done, my_seq)
        finally:
            _slock.release()
        logger.info(f"[TELEGRAM_REPLY] uid={user_id} seq={my_seq} reply={reply!r}")
        sent = await update.message.reply_text(reply)
        _rt_total_ms = int((time.monotonic() - _rt_start) * 1000)
        emit_runtime_trace(
            "telegram_roundtrip",
            uid=user_id,
            update_id=getattr(update, "update_id", None),
            route_ms=_rt_route_ms,
            total_ms=_rt_total_ms,
            queue_ms=_queue_ms if '_queue_ms' in dir() else 0,
            pool="fast" if _is_fast else ("long" if _use_long_pool else "default"),
            reply_len=len(reply),
            send_ok=bool(sent is not None),
        )
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
        # PTB defaults to processing updates one-by-one: a slow media op
        # (play verification polls up to ~10s per attempt) blocks every other
        # message for minutes. Allow a small concurrent pool so a "hi" is
        # answered while playback is being resolved. The connector serializes
        # extension commands on its single WS loop, so concurrent callers only
        # interleave there — no shared-state corruption.
        .concurrent_updates(8)  # was 4 — allow more concurrent Telegram messages
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
    app.add_handler(
        CommandHandler(
            ["health", "status", "uptime", "system", "systemhealth", "resources",
             "lock", "unlock", "credentials"],
            cmd_operational,
        )
    )
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

        # A graceful shutdown request (Ctrl+C / SIGTERM) must end the loop,
        # not be swallowed by the crash-restart logic.
        from mini_kio.core.runtime import get_runtime as _get_rt
        if _get_rt() is not None and _get_rt().shutdown_requested:
            logger.info("[LIFECYCLE] break_loop reason=runtime_shutdown_requested")
            break

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
    from mini_kio.core.single_instance import acquire_runtime_owner, release_runtime_owner

    if not acquire_runtime_owner():
        logger.error("[LIFECYCLE] startup refused: another KIO runtime is active")
        raise SystemExit(2)
    try:
        run_runtime()
    finally:
        release_runtime_owner()
