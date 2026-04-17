"""
Entry point: configure logging, validate env, initialize SQLite, run the Telegram bot.

Local proactive hints use ``send_notification`` only (never Telegram). A single daemon
thread wakes every ``CONTEXT_POLL_SECONDS`` (≥60) because ``run_bot`` blocks the main thread.
"""

from __future__ import annotations

import json
import logging
import sys
import threading
import time
from logging.handlers import RotatingFileHandler
from pathlib import Path
from typing import Any

# Mutable state for context suggestions (window title / app only — no keylogging).
_VOICE_STOP = threading.Event()

_CTX_STATE: dict[str, Any] = {
    "was_editor": False,
    "fired_vscode": False,
    "was_tutorial": False,
    "fired_tutorial": False,
    "youtube_start": None,
    "fired_youtube_break": False,
}


from .logger import setup_logging
from . import event_bus
from . import plugin_loader

_ENV_PLACEHOLDERS = frozenset(
    {
        "your_groq_api_key_here",
        "your_telegram_bot_token_here",
        "your_telegram_user_id_here",
    }
)


def check_config() -> bool:
    """Validate required environment variables before starting."""
    from .config import TELEGRAM_TOKEN, GROQ_API_KEY, ALLOWED_USER_IDS

    errors: list[str] = []
    if not TELEGRAM_TOKEN:
        errors.append("TELEGRAM_TOKEN is not set")
    elif TELEGRAM_TOKEN.strip().lower() in _ENV_PLACEHOLDERS:
        errors.append("TELEGRAM_TOKEN still has a placeholder value from .env.example")

    if not GROQ_API_KEY:
        errors.append("GROQ_API_KEY is not set (primary AI provider)")
    elif GROQ_API_KEY.strip().lower() in _ENV_PLACEHOLDERS:
        errors.append("GROQ_API_KEY still has a placeholder value from .env.example")

    if not ALLOWED_USER_IDS or ALLOWED_USER_IDS == {0}:
        errors.append("ALLOWED_USER_IDS is not set — set your Telegram user ID")

    if errors:
        print("Configuration errors:")
        for e in errors:
            print(f"   - {e}")
        print("\nFix these in your .env file. See README for setup.")
        return False
    return True


def check_timers_only() -> None:
    """Fire local notifications when focus/break timers expire (SQLite-backed)."""
    from .system_skills import send_notification
    from .memory_core import pop_due_session_timer

    kind = pop_due_session_timer()
    if kind == "focus":
        send_notification("KIO Assistant", "KIO: Focus session complete. Take a break.")
    elif kind == "break":
        send_notification("KIO Assistant", "KIO: Break over. Ready to focus again?")


def check_context() -> None:
    """
    Poll active window (title + app name) and optionally nudge via local notifications.

    Never sends Telegram messages. Suggestions fire at most once per editor/tutorial session
    or once per long YouTube-in-browser stretch until the user leaves that context.
    """
    check_timers_only()

    from .config import ENABLE_CONTEXT_ASSIST

    if not ENABLE_CONTEXT_ASSIST:
        return

    from .system_skills import get_active_window, send_notification

    ctx = get_active_window()
    st = _CTX_STATE
    if not ctx:
        st["was_editor"] = False
        st["was_tutorial"] = False
        st["youtube_start"] = None
        st["fired_youtube_break"] = False
        return

    app = (ctx.get("app") or "").lower()
    title = (ctx.get("title") or "").lower()

    is_editor = (
        any(
            x in app
            for x in (
                "code",
                "cursor",
                "devenv",
                "pycharm",
                "idea64",
                "rider",
                "vim",
                "nvim",
            )
        )
        or "code.exe" in app
        or "visual studio" in app
    )

    if is_editor:
        if not st["was_editor"]:
            st["fired_vscode"] = False
        st["was_editor"] = True
        if not st["fired_vscode"]:
            send_notification(
                "KIO Assistant",
                "You've been coding for a while. Need a quick debugging tip?",
            )
            st["fired_vscode"] = True
    else:
        st["was_editor"] = False

    browser_bits = (
        "chrome",
        "firefox",
        "msedge",
        "brave",
        "opera",
        "vivaldi",
        "safari",
        "chromium",
    )
    is_browser = any(b in app for b in browser_bits) or "browser" in app
    tut_kw = (
        "w3schools",
        "tutorial",
        "docs.",
        "stackoverflow",
        "developer.mozilla",
        "mdn",
        "readthedocs",
    )
    is_tutorial = is_browser and any(k in title for k in tut_kw)

    if is_tutorial:
        if not st["was_tutorial"]:
            st["fired_tutorial"] = False
        st["was_tutorial"] = True
        if not st["fired_tutorial"]:
            send_notification(
                "KIO Assistant",
                "Browsing tutorials or docs? Want a quick code example?",
            )
            st["fired_tutorial"] = True
    else:
        st["was_tutorial"] = False

    yt = is_browser and "youtube" in title
    now = time.monotonic()
    if yt:
        if st["youtube_start"] is None:
            st["youtube_start"] = now
            st["fired_youtube_break"] = False
        elif now - st["youtube_start"] >= 20 * 60 and not st["fired_youtube_break"]:
            send_notification(
                "KIO Assistant",
                "YouTube has been active a long time. Time for a short break?",
            )
            st["fired_youtube_break"] = True
    else:
        st["youtube_start"] = None
        st["fired_youtube_break"] = False


def _context_tick_loop() -> None:
    log = logging.getLogger("main.context")
    from .config import CONTEXT_POLL_SECONDS

    while True:
        time.sleep(float(CONTEXT_POLL_SECONDS))
        try:
            check_context()
            log.debug(
                json.dumps({"evt": "context_tick", "ok": True}),
            )
        except Exception:
            log.exception(
                json.dumps({"evt": "context_tick", "ok": False}),
            )


def start_background_context_tick() -> None:
    """One daemon thread: timer checks + optional window-based nudges (≥60s interval)."""
    t = threading.Thread(
        target=_context_tick_loop,
        name="kio-context-tick",
        daemon=True,
    )
    t.start()
    logging.getLogger("main").info(
        json.dumps({"evt": "context_thread", "started": True}),
    )


def start_background_voice() -> None:
    """Optional daemon: double-clap mic activation + speech → router (no AI execution from model text)."""
    from .voice import start_voice_daemon

    t = start_voice_daemon(_VOICE_STOP)
    if t is not None:
        logging.getLogger("main").info(
            json.dumps({"evt": "voice_thread", "started": True})
        )


def _watchdog_loop() -> None:
    logger = logging.getLogger("main.watchdog")
    from . import telegram_bot
    from . import command_router
    from . import event_bus

    while True:
        try:
            # Check modules
            time.sleep(10)
            logger.debug(json.dumps({"evt": "watchdog_tick", "status": "ok"}))
            # If any module stops responding, we'd restart it here
        except Exception as e:
            logger.error(f"Watchdog error: {e}")


def main() -> None:
    # 1 load config
    if not check_config():
        sys.exit(1)

    print("=" * 50)
    print("  Mini-KIO — Lightweight Personal AI Assistant")
    print("=" * 50)

    if "--test-clap" in sys.argv:
        from .voice import test_clap_detection

        test_clap_detection()
        sys.exit(0)

    # 2 initialize logger
    setup_logging()
    logger = logging.getLogger("main")
    logger.info(json.dumps({"evt": "startup", "phase": "init"}))

    # 6 VERIFY SYSTEM IMPORTS
    modules_to_test = [
        "core.logger",
        "core.event_bus",
        "core.memory_core",
        "core.command_router",
        "core.system_skills",
        "core.telegram_bot",
        "core.plugin_loader",
    ]
    for mod in modules_to_test:
        try:
            __import__(mod)
        except Exception as e:
            logger.error(f"Failed to import {mod}: {e}")

    # 3 start event_bus
    # (event_bus is loaded via import test, we can log it)
    logger.info(json.dumps({"evt": "startup", "phase": "event_bus"}))

    plugin_loader.load_plugins()
    event_bus.publish("startup")

    # Load personality engine
    logger.info(json.dumps({"evt": "startup", "phase": "personality"}))
    from .personality_engine import format_greeting

    greeting = format_greeting()
    print(greeting)

    # 4 load memory_core
    logger.info(json.dumps({"evt": "startup", "phase": "init_db"}))
    from .memory_core import init_db

    init_db()

    start_background_context_tick()
    start_background_voice()

    # Start context engine
    logger.info(json.dumps({"evt": "startup", "phase": "context"}))
    from .context_engine import start_context_monitoring

    start_context_monitoring()

    # Start behavior scheduler
    logger.info(json.dumps({"evt": "startup", "phase": "scheduler"}))
    from .behavior_scheduler import start_scheduler

    start_scheduler()

    # 6 start UI thread
    from .ui_core import start_ui_thread

    start_ui_thread()

    # 5 start telegram_bot
    logger.info(json.dumps({"evt": "startup", "phase": "telegram"}))
    from .telegram_bot import run_bot

    t_bot = threading.Thread(target=run_bot, daemon=True, name="kio-telegram-bot")
    t_bot.start()

    # 7 start watchdog loop
    logger.info(json.dumps({"evt": "startup", "phase": "watchdog"}))
    print("KIO companion system initialized")
    _watchdog_loop()


if __name__ == "__main__":
    main()
